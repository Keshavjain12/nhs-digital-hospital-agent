"""Audit service.

Every entry carries actor, action, resource, timestamp and result (brief §18).

The metadata scrubber here is the same idea as the log formatter's: the rule that audit
records hold identifiers and outcomes but never clinical or authentication content is
enforced at the write, not left to each caller to remember.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import REDACTED_KEYS, get_logger
from app.models.audit import AuditLog
from app.models.base import AuditResult, UserRole

logger = get_logger(__name__)

# Mirrors FORBIDDEN_IN_AUDIT_METADATA in docs/security/rbac-and-audit.md §5.
FORBIDDEN_METADATA_KEYS = REDACTED_KEYS

_MAX_METADATA_KEYS = 20
_MAX_VALUE_LENGTH = 200


def scrub_metadata(metadata: dict[str, Any] | None) -> dict[str, Any]:
    """Strip forbidden keys and cap size.

    The audit log answers "who touched what, when, and did it succeed". It is not a second
    copy of the medical record, and letting it become one would multiply the blast radius
    of any breach of it.
    """
    if not metadata:
        return {}

    clean: dict[str, Any] = {}
    for key, value in list(metadata.items())[:_MAX_METADATA_KEYS]:
        if str(key).lower() in FORBIDDEN_METADATA_KEYS:
            continue
        if isinstance(value, str) and len(value) > _MAX_VALUE_LENGTH:
            value = value[:_MAX_VALUE_LENGTH] + "…"
        clean[str(key)] = value
    return clean


class AuditService:
    """Writes audit events. Never raises into the caller's path."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def record(
        self,
        *,
        action: str,
        result: AuditResult = AuditResult.SUCCESS,
        actor_user_id: uuid.UUID | None = None,
        actor_role: UserRole | None = None,
        resource_type: str | None = None,
        resource_id: uuid.UUID | None = None,
        request_id: str | None = None,
        ip_hash: str | None = None,
        user_agent_hash: str | None = None,
        metadata: dict[str, Any] | None = None,
        detail: str | None = None,
    ) -> None:
        entry = AuditLog(
            actor_user_id=actor_user_id,
            actor_role=actor_role,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            result=result,
            request_id=request_id,
            ip_hash=ip_hash,
            user_agent_hash=user_agent_hash,
            metadata_=scrub_metadata(metadata),
            detail=detail,
        )
        self._session.add(entry)
        # Flushed, not committed: the audit entry shares the caller's transaction, so an
        # action that is rolled back does not leave an audit record claiming it happened.
        await self._session.flush()

        logger.info(
            "audit_event",
            extra={
                "action": action,
                "result": result.value,
                "resource_type": resource_type,
                "request_id": request_id,
            },
        )
