"""Wire-format contract tests.

The API contract (docs/api/api-contract-v1.md) specifies camelCase JSON. The frontend's
generated TypeScript types depend on it, so a regression here silently breaks the client
rather than failing a build. These tests pin the boundary.
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.errors import ErrorBody, ErrorResponse
from app.schemas.base import CamelModel


async def test_health_serialises_camel_case(client: AsyncClient) -> None:
    body = (await client.get("/health")).json()

    assert "uptimeSeconds" in body
    assert "uptime_seconds" not in body


async def test_error_envelope_serialises_camel_case(app) -> None:
    from fastapi import APIRouter

    from app.core.errors import AppointmentConflict

    router = APIRouter()

    @router.get("/_test/conflict")
    async def conflict() -> None:
        raise AppointmentConflict()

    app.include_router(router)
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        body = (await c.get("/_test/conflict")).json()

    assert "requestId" in body["error"]
    assert "request_id" not in body["error"]


def test_camel_model_accepts_either_spelling_on_input() -> None:
    """Be liberal in what we accept: both spellings deserialise identically."""
    from_camel = ErrorBody(code="X", message="m", requestId="abc")  # type: ignore[call-arg]
    from_snake = ErrorBody(code="X", message="m", request_id="abc")

    assert from_camel.request_id == from_snake.request_id == "abc"


def test_camel_model_omits_none_fields_when_asked() -> None:
    """`details` and `requestId` are optional in the contract and must not appear as null."""
    payload = ErrorResponse(error=ErrorBody(code="X", message="m")).model_dump(
        mode="json", by_alias=True, exclude_none=True
    )

    assert payload == {"error": {"code": "X", "message": "m"}}


@pytest.mark.parametrize(
    ("python_name", "wire_name"),
    [
        ("request_id", "requestId"),
        ("data_origin", "dataOrigin"),
        ("page_size", "pageSize"),
        ("total_items", "totalItems"),
    ],
)
def test_alias_generator_matches_the_documented_names(python_name: str, wire_name: str) -> None:
    """The generator's output must match the field names written in the API contract."""
    from app.schemas.base import PageMeta, ResponseMeta

    model: type[CamelModel] = (
        PageMeta if python_name in {"page_size", "total_items"} else ResponseMeta
    )

    assert model.model_fields[python_name].alias == wire_name
