"""FastAPI application factory.

NHS Digital Hospital Agent - student project. Not an NHS service, not clinically
validated, not for real patient care. See README.md.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import admin, auth, health, patients
from app.core.config import Settings, get_settings
from app.core.db import dispose_engine
from app.core.errors import (
    AppError,
    app_error_handler,
    unhandled_error_handler,
    validation_error_handler,
)
from app.core.logging import configure_logging, get_logger
from app.core.middleware import RequestContextMiddleware, SecurityHeadersMiddleware

logger = get_logger(__name__)

DESCRIPTION = """
Backend API for the NHS Digital Hospital Agent.

**This is a student project.** It is not an NHS service and is not approved, assessed or
certified by any NHS body. It is not DTAC-assessed, DSPT-certified, DCB0129/0160-compliant,
FHIR UK Core conformance-tested, or clinically validated, and it must not be used for real
patient care. All data is synthetic; no record describes a real person.
""".strip()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    logger.info(
        "application_starting",
        extra={"environment": settings.environment.value, "version": settings.version},
    )
    yield
    await dispose_engine()
    logger.info("application_stopped")


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)

    app = FastAPI(
        title=settings.app_name,
        description=DESCRIPTION,
        version=settings.version,
        lifespan=lifespan,
        # Interactive docs are a development convenience, not a production surface.
        docs_url=None if settings.is_production else "/docs",
        redoc_url=None,
        openapi_url=None if settings.is_production else "/openapi.json",
    )

    # Middleware is applied bottom-up, so RequestContextMiddleware is added last to run
    # first: every downstream log line and error response needs the request id to exist.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,  # required for the httpOnly refresh cookie
        allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID", "Idempotency-Key"],
        expose_headers=["X-Request-ID", "X-Permission-Hint", "Retry-After"],
    )
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(RequestContextMiddleware)

    # Every exception leaving a handler is rendered through the one envelope.
    app.add_exception_handler(AppError, app_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(Exception, unhandled_error_handler)

    # Health probes stay unversioned at the root: orchestrators and load balancers
    # should not have to track an API version to know whether the process is alive.
    app.include_router(health.router)
    app.include_router(auth.router, prefix=settings.api_v1_prefix)
    app.include_router(patients.router, prefix=settings.api_v1_prefix)
    app.include_router(admin.router, prefix=settings.api_v1_prefix)

    return app


app = create_app()
