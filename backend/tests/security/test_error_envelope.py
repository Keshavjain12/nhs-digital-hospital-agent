"""Error envelope tests.

Brief §11 and §17, security test S17: no stack trace, SQL, file path or internal
identifier may reach a client. These tests assert that against the actual HTTP response,
not against the intent of the code.
"""

from __future__ import annotations

import pytest
from fastapi import APIRouter
from httpx import ASGITransport, AsyncClient

from app.core.errors import (
    AppointmentConflict,
    PermissionDenied,
    ResourceNotFound,
    ValidationFailed,
)

DB_LEAK_MARKERS = (
    "Traceback",
    "sqlalchemy",
    "asyncpg",
    "psycopg",
    "SELECT ",
    "site-packages",
    ".py",
    "app/core",
    "10.0.4.12",
)


@pytest.fixture
def error_app(app):
    """Mount routes that raise, so the handlers can be exercised end to end."""
    router = APIRouter()

    @router.get("/_test/boom")
    async def boom() -> None:
        # A realistic internal failure carrying infrastructure detail in its message.
        raise RuntimeError(
            'relation "clinical.patients" does not exist at 10.0.4.12:5432 '
            "(sqlalchemy.exc.ProgrammingError)"
        )

    @router.get("/_test/conflict")
    async def conflict() -> None:
        raise AppointmentConflict()

    @router.get("/_test/forbidden")
    async def forbidden() -> None:
        raise PermissionDenied(hint="breakglass_available")

    @router.get("/_test/missing")
    async def missing() -> None:
        raise ResourceNotFound()

    @router.get("/_test/invalid")
    async def invalid() -> None:
        raise ValidationFailed()

    app.include_router(router)
    return app


@pytest.fixture
async def error_client(error_app):
    # raise_app_exceptions=False lets the 500 handler render, as it does in a real server.
    transport = ASGITransport(app=error_app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.mark.security
async def test_unhandled_exception_leaks_nothing(error_client: AsyncClient) -> None:
    response = await error_client.get("/_test/boom")

    assert response.status_code == 500
    body = response.json()
    assert body["error"]["code"] == "INTERNAL_ERROR"
    assert body["error"]["message"] == "Something went wrong. Please try again."

    for marker in DB_LEAK_MARKERS:
        assert marker not in response.text, f"500 response leaked {marker!r}"

    # The table name from the original exception must not survive either.
    assert "clinical.patients" not in response.text


@pytest.mark.security
async def test_unhandled_exception_still_returns_a_request_id(
    error_client: AsyncClient,
) -> None:
    """The user gets a correlation id and nothing else.

    This is what makes "it said something went wrong" a diagnosable report without the
    response itself having disclosed anything.
    """
    response = await error_client.get("/_test/boom")

    request_id = response.json()["error"]["requestId"]
    assert request_id
    assert response.headers["X-Request-ID"] == request_id


@pytest.mark.security
async def test_error_responses_keep_security_headers(error_client: AsyncClient) -> None:
    """A 500 bypasses the application middleware stack; the headers must survive anyway.

    Starlette's ServerErrorMiddleware sits outside our middleware, so the response never
    passes back through SecurityHeadersMiddleware. Without headers set at the render
    layer, the responses least under our control would be the only unprotected ones.
    """
    response = await error_client.get("/_test/boom")

    assert response.headers["Cache-Control"] == "no-store"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"


@pytest.mark.parametrize(
    ("path", "expected_status", "expected_code"),
    [
        ("/_test/conflict", 409, "APPOINTMENT_CONFLICT"),
        ("/_test/forbidden", 403, "PERMISSION_DENIED"),
        ("/_test/missing", 404, "RESOURCE_NOT_FOUND"),
        ("/_test/invalid", 400, "VALIDATION_ERROR"),
    ],
)
async def test_app_errors_use_the_documented_envelope(
    error_client: AsyncClient, path: str, expected_status: int, expected_code: str
) -> None:
    response = await error_client.get(path)

    assert response.status_code == expected_status
    body = response.json()
    assert set(body) == {"error"}
    assert body["error"]["code"] == expected_code
    assert body["error"]["message"]
    assert body["error"]["requestId"]


@pytest.mark.security
async def test_permission_hint_is_a_header_not_a_body_field(
    error_client: AsyncClient,
) -> None:
    """The hint tells the frontend a next step exists without confirming the resource does."""
    response = await error_client.get("/_test/forbidden")

    assert response.headers["X-Permission-Hint"] == "breakglass_available"
    assert "breakglass" not in response.json()["error"]["message"].lower()


@pytest.mark.security
async def test_validation_errors_never_echo_the_submitted_value(
    error_client: AsyncClient,
) -> None:
    """Pydantic's raw errors include the input. For this app that can be a password.

    Only the field location and error type are forwarded.
    """
    response = await error_client.post(
        "/_test/conflict", json={"password": "hunter2", "nhsNumber": "9990000018"}
    )

    assert "hunter2" not in response.text
    assert "9990000018" not in response.text
