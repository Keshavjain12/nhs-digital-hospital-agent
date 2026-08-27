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
        engine = create_async_engine(_admin_url(), isolation_level="AUTOCOMMIT")
        try:
            async with engine.connect() as conn:
                exists = await conn.scalar(
                    text("SELECT 1 FROM pg_database WHERE datname = :name"),
                    {"name": TEST_DB_NAME},
                )
                if not exists:
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
    factory = async_sessionmaker(bind=connection, expire_on_commit=False)
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
    get_settings.cache_clear()

    from app.core.db import get_session
    from app.core.ratelimit import get_rate_limiter
    from app.main import create_app

    application = create_app()

    async def override_session() -> AsyncIterator[AsyncSession]:
        yield db_session

    application.dependency_overrides[get_session] = override_session

    # Rate-limit state is process-global; clearing it stops one test's requests from
    # exhausting another's allowance and producing order-dependent failures.
    limiter = get_rate_limiter()
    if hasattr(limiter, "_events"):
        limiter._events.clear()

    transport = ASGITransport(app=application, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
