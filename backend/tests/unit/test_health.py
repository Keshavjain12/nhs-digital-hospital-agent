"""Health and readiness endpoint tests.

Brief §33: health endpoints must not disclose internal information.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.core.db import get_session


async def test_health_returns_ok(client: AsyncClient) -> None:
    response = await client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["version"]
    assert isinstance(body["uptimeSeconds"], int)


async def test_health_does_not_touch_the_database(client: AsyncClient) -> None:
    """Liveness must not depend on the database.

    If it did, a brief database blip would restart every healthy API instance and turn a
    partial outage into a total one. No DB is configured in this test run, so a passing
    request here is the proof.
    """
    response = await client.get("/health")
    assert response.status_code == 200


async def test_health_leaks_no_internal_detail(client: AsyncClient) -> None:
    body = response_text = (await client.get("/health")).text.lower()

    for leak in ("postgres", "asyncpg", "localhost", "5432", "secret", "password", "traceback"):
        assert leak not in body, f"health response disclosed {leak!r}"
    assert "uptimeseconds" in response_text


async def test_ready_reports_unavailable_without_detail(app, client: AsyncClient) -> None:
    """A failing readiness check reports two words, never the underlying error.

    The failure is raised from `execute`, not from dependency resolution, because that is
    how a real outage presents: SQLAlchemy connects lazily, so the connection error
    surfaces on first statement execution inside the handler's try block.
    """

    class _BrokenSession:
        async def execute(self, _statement: object) -> None:
            raise ConnectionRefusedError("could not connect to server at 10.0.4.12:5432")

    async def failing_session():
        yield _BrokenSession()

    app.dependency_overrides[get_session] = failing_session
    try:
        response = await client.get("/ready")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 503
    assert response.json() == {"status": "not_ready", "database": "unavailable"}
    # Nothing about the infrastructure reaches the caller.
    for leak in ("10.0.4.12", "5432", "ConnectionRefused", "Traceback"):
        assert leak not in response.text


async def test_ready_succeeds_when_database_responds(app, client: AsyncClient) -> None:
    class _StubSession:
        async def execute(self, _statement: object) -> None:
            return None

    async def working_session():
        yield _StubSession()

    app.dependency_overrides[get_session] = working_session
    try:
        response = await client.get("/ready")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {"status": "ready", "database": "ok"}


@pytest.mark.parametrize("path", ["/health", "/ready"])
async def test_security_headers_present(app, client: AsyncClient, path: str) -> None:
    async def working_session():
        class _S:
            async def execute(self, _s: object) -> None:
                return None

        yield _S()

    app.dependency_overrides[get_session] = working_session
    try:
        response = await client.get(path)
    finally:
        app.dependency_overrides.clear()

    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Cache-Control"] == "no-store"
    assert "frame-ancestors 'none'" in response.headers["Content-Security-Policy"]


async def test_request_id_is_echoed(client: AsyncClient) -> None:
    """A caller-supplied request id is preserved so logs correlate across services."""
    supplied = "11111111-2222-3333-4444-555555555555"
    response = await client.get("/health", headers={"X-Request-ID": supplied})

    assert response.headers["X-Request-ID"] == supplied


async def test_request_id_is_generated_when_absent(client: AsyncClient) -> None:
    response = await client.get("/health")

    assert response.headers.get("X-Request-ID")
