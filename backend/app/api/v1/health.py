"""Liveness and readiness endpoints.

Brief §33: these must not disclose internal detail. `/ready` reports whether the database
is reachable as a bare "ok" or "unavailable" — never the host, driver, version or the
connection error, all of which are useful to an attacker mapping the estate.
"""

from __future__ import annotations

import time
from typing import Literal

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.db import get_session
from app.core.logging import get_logger
from app.schemas.base import CamelModel

router = APIRouter(tags=["system"])
logger = get_logger(__name__)

_STARTED_AT = time.monotonic()


class HealthResponse(CamelModel):
    status: Literal["ok"]
    version: str
    uptime_seconds: int  # serialised as "uptimeSeconds"


class ReadyResponse(CamelModel):
    status: Literal["ready", "not_ready"]
    database: Literal["ok", "unavailable"]


@router.get("/health", response_model=HealthResponse, summary="Liveness probe")
async def health(settings: Settings = Depends(get_settings)) -> HealthResponse:
    """Is the process alive? Deliberately checks nothing else.

    A liveness probe that touches the database will restart a healthy API during a brief
    database blip, turning a partial outage into a total one.
    """
    return HealthResponse(
        status="ok",
        version=settings.version,
        uptime_seconds=int(time.monotonic() - _STARTED_AT),
    )


@router.get("/ready", response_model=ReadyResponse, summary="Readiness probe")
async def ready(
    response: Response,
    session: AsyncSession = Depends(get_session),
) -> ReadyResponse:
    """Can this instance serve traffic? Checks the database round trip."""
    try:
        await session.execute(text("SELECT 1"))
    except Exception:
        # Full detail to the log; two words to the caller.
        logger.exception("readiness_check_failed")
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return ReadyResponse(status="not_ready", database="unavailable")

    return ReadyResponse(status="ready", database="ok")
