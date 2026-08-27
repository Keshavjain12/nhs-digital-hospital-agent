"""Request-scoped middleware: correlation IDs, access logging, security headers."""

from __future__ import annotations

import time
import uuid
from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.logging import get_logger

logger = get_logger(__name__)

RequestHandler = Callable[[Request], Awaitable[Response]]

# Paths excluded from access logging: they are polled constantly by the orchestrator and
# would otherwise drown out everything worth reading.
_QUIET_PATHS = frozenset({"/health", "/ready"})


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Attach a request id, log the request, and return the id to the client.

    The id is what lets a user-reported error ("it said something went wrong, id 8f2c…")
    be found in the logs without the error response having disclosed anything else.
    """

    async def dispatch(self, request: Request, call_next: RequestHandler) -> Response:
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        request.state.request_id = request_id

        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            # Logged here with timing, then re-raised for the exception handler to render.
            logger.exception(
                "request_failed",
                extra={
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "duration_ms": round((time.perf_counter() - started) * 1000, 2),
                },
            )
            raise

        duration_ms = round((time.perf_counter() - started) * 1000, 2)
        response.headers["X-Request-ID"] = request_id

        if request.url.path not in _QUIET_PATHS:
            logger.info(
                "request_completed",
                extra={
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": response.status_code,
                    "duration_ms": duration_ms,
                },
            )
        return response


# The API itself returns JSON and needs to load nothing at all.
API_CSP = "default-src 'none'; frame-ancestors 'none'; base-uri 'none'"

# The one exception. FastAPI's /docs is an HTML page that pulls Swagger UI from a CDN, so
# the strict policy above renders it as a blank white screen - the document loads, every
# script and stylesheet is blocked, and nothing paints. The failure gives no visible clue
# that a header caused it.
#
# Scoped to the documentation routes only, and those routes do not exist in production
# (create_app sets docs_url=None there), so this relaxation cannot reach a deployed
# environment. Hardening step if that ever changes: vendor the Swagger UI assets and serve
# them from 'self', which also removes the external request this page currently makes.
DOCS_CSP = (
    "default-src 'none'; "
    "script-src 'self' https://cdn.jsdelivr.net 'unsafe-inline'; "
    "style-src 'self' https://cdn.jsdelivr.net 'unsafe-inline'; "
    "img-src 'self' data: https://fastapi.tiangolo.com; "
    "font-src 'self' https://cdn.jsdelivr.net; "
    "connect-src 'self'; "
    "frame-ancestors 'none'; "
    "base-uri 'none'"
)

DOCS_PATHS = frozenset({"/docs", "/docs/oauth2-redirect", "/redoc", "/openapi.json"})


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Baseline security headers (brief §17)."""

    async def dispatch(self, request: Request, call_next: RequestHandler) -> Response:
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault(
            "Content-Security-Policy",
            DOCS_CSP if request.url.path in DOCS_PATHS else API_CSP,
        )
        response.headers.setdefault(
            "Permissions-Policy", "geolocation=(), microphone=(), camera=()"
        )
        # Clinical and personal data must never be cached by an intermediary.
        response.headers.setdefault("Cache-Control", "no-store")
        return response
