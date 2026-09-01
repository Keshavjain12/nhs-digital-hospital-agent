"""Integration test fixtures.

These tests run against a real PostgreSQL database, because the behaviours they cover -
partial unique indexes, the append-only audit trigger, transactional rollback - do not
exist in SQLite. Testing them against a substitute would verify the substitute.

The database is created once per session and migrated with the real Alembic migrations,
so the schema under test is the schema that ships. Each test runs inside a transaction
that is rolled back, which keeps tests isolated without re-migrating between them.

If no database is reachable the whole module skips rather than fails: a contributor
without Docker running should get a clear skip, not a wall of connection errors.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator, Iterator
from urllib.parse import urlsplit, urlunsplit

import pytest
import pytest_asyncio
from alembic.config import Config
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from alembic import command
from app.core.config import get_settings

TEST_DB_NAME = "hospital_test"


def _admin_url() -> str:
    """Connection URL for the maintenance database, used to CREATE DATABASE."""
    base = os.environ["DATABASE_URL"]
    parts = urlsplit(base)
    return urlunsplit((parts.scheme, parts.netloc, "/postgres", "", ""))


def _test_url() -> str:
    base = os.environ["DATABASE_URL"]
    parts = urlsplit(base)
    return urlunsplit((parts.scheme, parts.netloc, f"/{TEST_DB_NAME}", "", ""))


@pytest.fixture(scope="session")
def database_url() -> Iterator[str]:
    """Create the test database and run migrations against it.

    Deliberately a *synchronous* fixture. Alembic's env.py calls asyncio.run() itself, and
    asyncio.run() cannot be nested inside an already-running loop - which is what an async
    fixture would give it. Keeping this sync lets Alembic own its event loop, exactly as it
    does when a developer runs `alembic upgrade head` from a shell.
    """

    async def _create_database() -> None:
        """Drop and recreate, so the schema always matches the migrations on disk.

        Creating only when absent left a stale database behind: `alembic upgrade head` is a
        no-op once the version table says head, so editing an unreleased migration changed
        nothing here. That produced failures with no relationship to the code under test -
        a column default fixed in the migration was still the old one in the test database.

        A test database is disposable. Rebuilding it each session costs a second and
        removes an entire class of confusing failure.
        """
        engine = create_async_engine(_admin_url(), isolation_level="AUTOCOMMIT")
        try:
            async with engine.connect() as conn:
                # Any connection still open would block the drop.
                await conn.execute(
                    text(
                        "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                        "WHERE datname = :name AND pid <> pg_backend_pid()"
                    ),
                    {"name": TEST_DB_NAME},
                )
                await conn.execute(text(f'DROP DATABASE IF EXISTS "{TEST_DB_NAME}"'))
                await conn.execute(text(f'CREATE DATABASE "{TEST_DB_NAME}"'))
        finally:
            await engine.dispose()

    try:
        asyncio.run(_create_database())
    except Exception as exc:
        pytest.skip(f"PostgreSQL not reachable, skipping integration tests: {exc}")

    url = _test_url()
    previous = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = url
    get_settings.cache_clear()

    try:
        # The real migrations, not metadata.create_all: several of these tests exist to
        # verify triggers and partial indexes that create_all would never produce.
        config = Config("alembic.ini")
        config.set_main_option("script_location", "alembic")
        command.upgrade(config, "head")
        yield url
    finally:
        if previous is not None:
            os.environ["DATABASE_URL"] = previous
        get_settings.cache_clear()


@pytest_asyncio.fixture
async def db_session(database_url: str) -> AsyncIterator[AsyncSession]:
    """A session bound to an outer transaction that is always rolled back.

    Nothing a test writes survives it, so tests can run in any order and leave no
    residue - including in the audit table, which cannot be cleaned up by deletion.
    """
    engine = create_async_engine(database_url, poolclass=None)
    connection = await engine.connect()
    transaction = await connection.begin()
    factory = async_sessionmaker(
        bind=connection,
        expire_on_commit=False,
        # Each commit/rollback inside the application acts on a SAVEPOINT rather than the
        # outer transaction. Without this, a request that legitimately rolls back - a 404
        # on someone else's record, a booking conflict - unwinds the test's own setup with
        # it, and the next assertion fails for reasons that have nothing to do with the
        # behaviour under test. In production every request has its own session, so a
        # rollback is already isolated; this makes the harness match.
        join_transaction_mode="create_savepoint",
    )
    session = factory()

    try:
        yield session
    finally:
        await session.close()
        if transaction.is_active:
            await transaction.rollback()
        await connection.close()
        await engine.dispose()


@pytest_asyncio.fixture
async def api(db_session: AsyncSession, database_url: str) -> AsyncIterator[AsyncClient]:
    """An HTTP client whose requests share the test's transaction."""
    os.environ["DATABASE_URL"] = database_url
    # The suite uses the in-process limiter even where REDIS_URL is set in the environment.
    # Tests should not depend on external infrastructure being up, and a shared Redis
    # counter persists across cases: with one window covering the whole run, the first
    # fifteen logins spend the allowance and everything after them fails with a 429 that
    # has nothing to do with what the test was checking. The Redis path is verified
    # against a live server instead - see docs/deployment.md.
    os.environ["REDIS_URL"] = ""
    get_settings.cache_clear()

    from app.core.db import get_session
    from app.core.ratelimit import InMemoryRateLimiter, get_rate_limiter, reset_rate_limiter
    from app.main import create_app

    reset_rate_limiter()

    application = create_app()

    async def override_session() -> AsyncIterator[AsyncSession]:
        yield db_session

    application.dependency_overrides[get_session] = override_session

    # Rate-limit state is process-global; clearing it stops one test's requests from
    # exhausting another's allowance and producing order-dependent failures.
    #
    # Asserted rather than duck-typed. This used to be `if hasattr(limiter, "_events")`,
    # which silently did nothing once the limiter could be Redis-backed - the counters kept
    # accumulating and a hundred tests failed with 429s that looked like unrelated
    # breakage. A wrong limiter should fail loudly here, not quietly there.
    limiter = get_rate_limiter()
    assert isinstance(limiter, InMemoryRateLimiter), "tests must not share a live limiter"
    limiter._events.clear()

    transport = ASGITransport(app=application, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
