"""Security header tests.

Includes a regression test for the docs page rendering blank: the strict API CSP blocked
Swagger UI's assets, and the symptom was a white screen with no console-free clue that a
response header was responsible.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.core.middleware import API_CSP


@pytest.mark.security
async def test_api_routes_use_the_strict_policy(client: AsyncClient) -> None:
    response = await client.get("/health")

    assert response.headers["Content-Security-Policy"] == API_CSP


@pytest.mark.security
async def test_docs_page_actually_renders(client: AsyncClient) -> None:
    """The page must be able to load the scripts it depends on.

    Asserting only on status would have passed while the page was blank: the HTML was
    served with 200 and every asset inside it was blocked.
    """
    response = await client.get("/docs")

    assert response.status_code == 200
    csp = response.headers["Content-Security-Policy"]

    assert "cdn.jsdelivr.net" in csp, "Swagger UI assets would be blocked"
    for asset in ("swagger-ui.css", "swagger-ui-bundle.js"):
        assert asset in response.text


@pytest.mark.security
async def test_docs_policy_still_forbids_framing_and_base_uri(client: AsyncClient) -> None:
    """Relaxing the docs policy must not relax clickjacking protection with it."""
    csp = (await client.get("/docs")).headers["Content-Security-Policy"]

    assert "frame-ancestors 'none'" in csp
    assert "base-uri 'none'" in csp
    assert "default-src 'none'" in csp


@pytest.mark.security
async def test_docs_relaxation_does_not_leak_to_api_routes(client: AsyncClient) -> None:
    for path in ("/health", "/ready", "/api/v1/auth/me"):
        csp = (await client.get(path)).headers["Content-Security-Policy"]

        assert "cdn.jsdelivr.net" not in csp, f"{path} must keep the strict policy"


@pytest.mark.security
@pytest.mark.parametrize(
    ("header", "expected"),
    [
        ("X-Content-Type-Options", "nosniff"),
        ("X-Frame-Options", "DENY"),
        ("Referrer-Policy", "no-referrer"),
        ("Cache-Control", "no-store"),
    ],
)
async def test_baseline_headers_are_present(
    client: AsyncClient, header: str, expected: str
) -> None:
    response = await client.get("/health")

    assert response.headers[header] == expected
