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


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Baseline security headers (brief §17).

    The API serves JSON only, so the CSP is maximally restrictive: it needs to load
    nothing, and `frame-ancestors 'none'` prevents an API error page being framed.
    """

    async def dispatch(self, request: Request, call_next: RequestHandler) -> Response:
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'none'; frame-ancestors 'none'; base-uri 'none'",
        )
        response.headers.setdefault(
            "Permissions-Policy", "geolocation=(), microphone=(), camera=()"
        )
        # Clinical and personal data must never be cached by an intermediary.
        response.headers.setdefault("Cache-Control", "no-store")
        return response
