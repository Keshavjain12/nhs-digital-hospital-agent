"""CORS tests.

Regression: the frontend moved to port 3001 while CORS_ORIGINS still listed only 3000.
Every request was refused at preflight, which the UI reported as "we could not reach the
service" - and nothing appeared in the API logs, because the request never arrived. A
configuration failure that is invisible on the server and misleading on the client is
exactly the kind worth pinning with a test.

These assert the *mechanism* against a known configuration rather than the deployed value,
so they stay meaningful when the environment changes.
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import Environment, Settings
from app.main import create_app

ALLOWED = "http://localhost:3000"
ALSO_ALLOWED = "http://localhost:3001"
NOT_ALLOWED = "https://evil.test"


def _settings() -> Settings:
    return Settings(
        environment=Environment.TESTING,
        database_url="postgresql+asyncpg://test:test@localhost:5432/t",  # type: ignore[arg-type]
        jwt_secret="test-only-secret-value-at-least-32-characters-long",
        cors_origins=f"{ALLOWED},{ALSO_ALLOWED}",  # type: ignore[arg-type]
    )


@pytest.fixture
async def cors_client() -> AsyncClient:
    app = create_app(_settings())
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    return AsyncClient(transport=transport, base_url="http://test")


@pytest.mark.security
@pytest.mark.parametrize("origin", [ALLOWED, ALSO_ALLOWED])
async def test_a_listed_origin_passes_preflight(cors_client: AsyncClient, origin: str) -> None:
    response = await cors_client.options(
        "/api/v1/auth/login",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == origin


@pytest.mark.security
async def test_an_unlisted_origin_is_refused(cors_client: AsyncClient) -> None:
    response = await cors_client.options(
        "/api/v1/auth/login",
        headers={"Origin": NOT_ALLOWED, "Access-Control-Request-Method": "POST"},
    )

    assert response.headers.get("access-control-allow-origin") != NOT_ALLOWED


@pytest.mark.security
async def test_credentials_are_allowed_for_the_refresh_cookie(cors_client: AsyncClient) -> None:
    """The httpOnly refresh cookie only travels when credentials are permitted.

    Without this the session silently fails to restore on reload, and the user is
    signed out every time they refresh the page.
    """
    response = await cors_client.options(
        "/api/v1/auth/refresh",
        headers={"Origin": ALLOWED, "Access-Control-Request-Method": "POST"},
    )

    assert response.headers["access-control-allow-credentials"] == "true"


@pytest.mark.security
async def test_the_authorization_header_is_permitted(cors_client: AsyncClient) -> None:
    """Every authenticated request sends it; omitting it from the allowlist breaks all of them."""
    response = await cors_client.options(
        "/api/v1/appointments",
        headers={
            "Origin": ALLOWED,
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "authorization",
        },
    )

    allowed = response.headers.get("access-control-allow-headers", "").lower()
    assert "authorization" in allowed


@pytest.mark.security
def test_origins_parse_from_a_comma_separated_string() -> None:
    """.env files hold a plain string, not JSON - the validator must split it."""
    settings = _settings()

    assert settings.cors_origins == [ALLOWED, ALSO_ALLOWED]


@pytest.mark.security
def test_a_wildcard_origin_is_never_configured() -> None:
    """`*` cannot be combined with credentials, and would expose the API to any site."""
    settings = _settings()

    assert "*" not in settings.cors_origins
