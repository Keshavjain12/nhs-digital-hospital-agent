"""Identity and access models.

`users` is authentication; `staff` is the organisational record. They are deliberately
separate so a clinician who leaves can have their login disabled while their historical
authorship of notes and approvals stays intact (03-data-model.md §7).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import ENUM as PgEnum
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.base import (
    TimestampMixin,
    UserRole,
    UserStatus,
    UUIDPrimaryKeyMixin,
)

user_role_enum = PgEnum(
    UserRole,
    name="user_role",
    schema="identity",
    create_type=False,
    values_callable=lambda e: [m.value for m in e],
)
user_status_enum = PgEnum(
    UserStatus,
    name="user_status",
    schema="identity",
    create_type=False,
    values_callable=lambda e: [m.value for m in e],
)


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "users"
    __table_args__ = {"schema": "identity"}

    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[UserRole] = mapped_column(user_role_enum, nullable=False)
    status: Mapped[UserStatus] = mapped_column(
        user_status_enum, nullable=False, server_default=UserStatus.ACTIVE.value
    )
    failed_logins: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    @property
    def is_locked(self) -> bool:
        from datetime import UTC

        if self.status is not UserStatus.ACTIVE:
            return True
        return self.locked_until is not None and self.locked_until > datetime.now(UTC)


class RefreshToken(UUIDPrimaryKeyMixin, Base):
    """Refresh tokens are stored hashed and rotated on every use.

    `replaced_by` builds a chain. Presenting a token that has already been rotated is a
    strong signal of theft, so the whole chain is revoked rather than just that token -
    an attacker with a stolen token and the legitimate user cannot both keep a session.
    """

    __tablename__ = "refresh_tokens"
    __table_args__ = (
        Index(
            "ix_refresh_tokens_active_user",
            "user_id",
            postgresql_where=text("revoked_at IS NULL"),
        ),
        {"schema": "identity"},
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("identity.users.id", ondelete="CASCADE"), nullable=False
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    replaced_by: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("identity.refresh_tokens.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )


class PasswordResetToken(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "password_reset_tokens"
    __table_args__ = {"schema": "identity"}

    user_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("identity.users.id", ondelete="CASCADE"), nullable=False
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )


class Staff(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "staff"
    __table_args__ = {"schema": "identity"}

    user_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("identity.users.id"), unique=True, nullable=False
    )
    staff_code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    given_name: Mapped[str] = mapped_column(String(100), nullable=False)
    family_name: Mapped[str] = mapped_column(String(100), nullable=False)
    job_title: Mapped[str] = mapped_column(String(120), nullable=False)
    department_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("operational.departments.id")
    )
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    data_origin: Mapped[str] = mapped_column(String(20), nullable=False, server_default="SYNTHETIC")

    @property
    def display_name(self) -> str:
        return f"{self.given_name} {self.family_name}"


class CareAssignment(UUIDPrimaryKeyMixin, Base):
    """Relationship-based access control: which staff may see which patient.

    See rbac-and-audit.md §2. Blanket "any doctor sees any patient" is not how NHS access
    control works, and is the lazy reading of the brief's "assigned/relevant records".
    """

    __tablename__ = "care_assignments"
    __table_args__ = (
        Index(
            "uq_care_assignment_active",
            "staff_id",
            "patient_id",
            unique=True,
            postgresql_where=text("valid_to IS NULL"),
        ),
        {"schema": "identity"},
    )

    staff_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("identity.staff.id"), nullable=False
    )
    patient_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("clinical.patients.id"), nullable=False
    )
    department_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("operational.departments.id")
    )
    valid_from: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reason: Mapped[str | None] = mapped_column(Text)


class BreakglassGrant(UUIDPrimaryKeyMixin, Base):
    """Emergency access with a mandatory typed justification.

    Exists because clinical reality does not respect assignment tables: a patient can
    arrive unconscious in front of a clinician with no prior relationship to them, and
    blocking that would be unsafe. Access is granted, but loudly - it expires, and it
    raises a high-severity audit event.
    """

    __tablename__ = "breakglass_grants"
    __table_args__ = (
        CheckConstraint("length(trim(reason)) >= 20", name="ck_breakglass_reason_length"),
        {"schema": "identity"},
    )

    staff_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("identity.staff.id"), nullable=False
    )
    patient_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("clinical.patients.id"), nullable=False
    )
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    granted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
