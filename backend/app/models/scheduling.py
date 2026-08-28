"""Scheduling and appointment models.

The invariants these tables carry live in migration 002 as database constraints, not here.
SQLAlchemy mirrors them so autogenerate does not try to drop them, but the database is the
enforcer - an application-level check cannot survive two processes running it at the same
instant, which is exactly the booking race.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import ENUM as PgEnum
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin


class SlotStatus(StrEnum):
    AVAILABLE = "AVAILABLE"
    BLOCKED = "BLOCKED"


class SlotType(StrEnum):
    ROUTINE = "ROUTINE"
    URGENT = "URGENT"
    FOLLOW_UP = "FOLLOW_UP"
    TELEPHONE = "TELEPHONE"


class AppointmentStatus(StrEnum):
    BOOKED = "BOOKED"
    CHECKED_IN = "CHECKED_IN"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    DID_NOT_ATTEND = "DID_NOT_ATTEND"


class AppointmentPriority(StrEnum):
    EMERGENCY = "EMERGENCY"
    URGENT = "URGENT"
    SOON = "SOON"
    ROUTINE = "ROUTINE"


#: States in which an appointment occupies its slot. Mirrors the predicate of
#: uq_appointment_active_slot in migration 002 - if one changes, the other must.
LIVE_APPOINTMENT_STATUSES: frozenset[AppointmentStatus] = frozenset(
    {
        AppointmentStatus.BOOKED,
        AppointmentStatus.CHECKED_IN,
        AppointmentStatus.IN_PROGRESS,
    }
)

#: States a patient may still act on.
CANCELLABLE_STATUSES: frozenset[AppointmentStatus] = frozenset(
    {AppointmentStatus.BOOKED, AppointmentStatus.CHECKED_IN}
)


def _enum(enum_cls: type[StrEnum], name: str) -> PgEnum:
    return PgEnum(
        enum_cls,
        name=name,
        schema="operational",
        create_type=False,
        values_callable=lambda e: [m.value for m in e],
    )


class AppointmentSlot(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "appointment_slots"
    __table_args__ = (
        CheckConstraint("ends_at > starts_at", name="ck_slot_ends_after_start"),
        Index(
            "ix_slots_open_by_department",
            "department_id",
            "starts_at",
            postgresql_where=text("status = 'AVAILABLE'"),
        ),
        Index("ix_slots_starts_at", "starts_at"),
        {"schema": "operational"},
    )

    department_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("operational.departments.id"), nullable=False
    )
    staff_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("identity.staff.id")
    )
    site_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("operational.sites.id"), nullable=False
    )
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    slot_type: Mapped[SlotType] = mapped_column(
        _enum(SlotType, "slot_type"), nullable=False, server_default=SlotType.ROUTINE.value
    )
    status: Mapped[SlotStatus] = mapped_column(
        _enum(SlotStatus, "slot_status"), nullable=False, server_default=SlotStatus.AVAILABLE.value
    )
    data_origin: Mapped[str] = mapped_column(String(20), nullable=False, server_default="SYNTHETIC")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )


class SlotHold(UUIDPrimaryKeyMixin, Base):
    """A short reservation while a patient confirms.

    Not a booking: it stops two people being told the same slot is theirs while they read
    the confirmation screen. Expiry is enforced by the service, because `now()` cannot
    appear in an index predicate.
    """

    __tablename__ = "slot_holds"
    __table_args__ = (
        Index("ix_slot_holds_expiry", "expires_at"),
        {"schema": "operational"},
    )

    slot_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("operational.appointment_slots.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    patient_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("clinical.patients.id", ondelete="CASCADE"),
        nullable=False,
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )


class Appointment(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "appointments"
    __table_args__ = (
        Index("ix_appointments_patient", "patient_id", "created_at"),
        Index("ix_appointments_department_status", "department_id", "status"),
        {"schema": "operational"},
    )

    # server_default is what makes SQLAlchemy leave this column out of the INSERT. Without
    # it the ORM sends an explicit NULL, overriding the database default and failing the
    # NOT NULL constraint - the column looks defaulted but never is.
    reference: Mapped[str] = mapped_column(
        String(24),
        unique=True,
        nullable=False,
        server_default=text(
            "'APT-' || to_char(now(), 'YYYY') || '-' || "
            "lpad(nextval('operational.appointment_reference_seq')::text, 6, '0')"
        ),
    )
    patient_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("clinical.patients.id"), nullable=False
    )
    slot_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("operational.appointment_slots.id"), nullable=False
    )
    department_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("operational.departments.id"), nullable=False
    )
    staff_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("identity.staff.id")
    )
    status: Mapped[AppointmentStatus] = mapped_column(
        _enum(AppointmentStatus, "appointment_status"),
        nullable=False,
        server_default=AppointmentStatus.BOOKED.value,
    )
    priority: Mapped[AppointmentPriority | None] = mapped_column(
        _enum(AppointmentPriority, "appointment_priority")
    )
    reason_text: Mapped[str | None] = mapped_column(Text)
    booked_by_user_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("identity.users.id"), nullable=False
    )
    previous_appointment_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("operational.appointments.id")
    )
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancellation_reason: Mapped[str | None] = mapped_column(String(200))

    @property
    def occupies_slot(self) -> bool:
        return self.status in LIVE_APPOINTMENT_STATUSES

    @property
    def is_cancellable(self) -> bool:
        return self.status in CANCELLABLE_STATUSES
