"""Shared test fixtures.

Test settings are injected through the environment before `app.core.config` is first
read, so tests never depend on a developer's local `.env`.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator, Iterator

import pytest

# Must be set before any `app.*` import triggers Settings construction.
os.environ.setdefault("ENVIRONMENT", "testing")
os.environ.setdefault("LOG_LEVEL", "WARNING")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost:5432/hospital_test")
os.environ.setdefault("JWT_SECRET", "test-only-secret-value-at-least-32-characters-long")
os.environ.setdefault("CORS_ORIGINS", "http://localhost:3000")

from httpx import ASGITransport, AsyncClient

from app.core.config import Settings, get_settings
from app.main import create_app


@pytest.fixture(scope="session")
def settings() -> Settings:
    get_settings.cache_clear()
    return get_settings()


@pytest.fixture
def app(settings: Settings):
    return create_app(settings)


@pytest.fixture
async def client(app) -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as async_client:
        yield async_client


@pytest.fixture
def caplog_json(caplog) -> Iterator[object]:
    """Capture log records for assertions about what is and is not logged."""
    import logging

    caplog.set_level(logging.INFO)
    yield caplog
