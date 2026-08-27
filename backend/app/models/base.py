"""Shared model mixins and enums.

Schema layout follows docs/architecture/03-data-model.md §1.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, String, func
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column


class UserRole(StrEnum):
    PATIENT = "PATIENT"
    NURSE = "NURSE"
    DOCTOR = "DOCTOR"
    ADMIN = "ADMIN"


class UserStatus(StrEnum):
    ACTIVE = "ACTIVE"
    LOCKED = "LOCKED"
    DISABLED = "DISABLED"


class AuditResult(StrEnum):
    SUCCESS = "SUCCESS"
    DENIED = "DENIED"
    ERROR = "ERROR"


class DataOrigin(StrEnum):
    """Provenance of a row.

    Carried through to the API response and on to the UI notice, so synthetic data
    cannot reach a screen unlabelled (brief §7).
    """

    SYNTHETIC = "SYNTHETIC"
    USER_ENTERED = "USER_ENTERED"


class UUIDPrimaryKeyMixin:
    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class DataOriginMixin:
    data_origin: Mapped[str] = mapped_column(
        String(20), nullable=False, default=DataOrigin.SYNTHETIC.value
    )
