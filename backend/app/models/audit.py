"""Audit log.

Append-only, enforced by database grant rather than application discipline (see
migration 001). If the application is compromised it must still be unable to erase its
own tracks.

`metadata_` holds identifiers and outcomes only. It is never a second copy of the medical
record; treating it as one would multiply the blast radius of a breach.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, Index, String, Text, text
from sqlalchemy.dialects.postgresql import ENUM as PgEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.base import AuditResult, UserRole

audit_result_enum = PgEnum(
    AuditResult,
    name="audit_result",
    schema="audit",
    create_type=False,
    values_callable=lambda e: [m.value for m in e],
)

user_role_ref = PgEnum(
    UserRole,
    name="user_role",
    schema="identity",
    create_type=False,
    values_callable=lambda e: [m.value for m in e],
)


class AuditAction:
    """Audit action names, per rbac-and-audit.md §5."""

    USER_LOGIN = "USER_LOGIN"
    USER_LOGOUT = "USER_LOGOUT"
    USER_REGISTERED = "USER_REGISTERED"
    PASSWORD_RESET_REQUESTED = "PASSWORD_RESET_REQUESTED"
    PASSWORD_RESET_COMPLETED = "PASSWORD_RESET_COMPLETED"
    ACCOUNT_LOCKED = "ACCOUNT_LOCKED"
    TOKEN_REFRESHED = "TOKEN_REFRESHED"
    TOKEN_REUSE_DETECTED = "TOKEN_REUSE_DETECTED"
    PERMISSION_DENIED = "PERMISSION_DENIED"
    PATIENT_RECORD_VIEW = "PATIENT_RECORD_VIEW"
    PATIENT_DATA_UPDATED = "PATIENT_DATA_UPDATED"
    BREAKGLASS_INVOKED = "BREAKGLASS_INVOKED"
    RATE_LIMIT_EXCEEDED = "RATE_LIMIT_EXCEEDED"


class AuditLog(Base):
    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_resource", "resource_type", "resource_id", "occurred_at"),
        Index("ix_audit_actor", "actor_user_id", "occurred_at"),
        Index("ix_audit_action", "action", "occurred_at"),
        {"schema": "audit"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(PgUUID(as_uuid=True))
    actor_role: Mapped[UserRole | None] = mapped_column(user_role_ref)
    action: Mapped[str] = mapped_column(String(60), nullable=False)
    resource_type: Mapped[str | None] = mapped_column(String(60))
    resource_id: Mapped[uuid.UUID | None] = mapped_column(PgUUID(as_uuid=True))
    result: Mapped[AuditResult] = mapped_column(audit_result_enum, nullable=False)
    request_id: Mapped[str | None] = mapped_column(String(64))
    # Hashed, not raw: an IP address is personal data under UK GDPR.
    ip_hash: Mapped[str | None] = mapped_column(String(64))
    user_agent_hash: Mapped[str | None] = mapped_column(String(64))
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )
    detail: Mapped[str | None] = mapped_column(Text)
