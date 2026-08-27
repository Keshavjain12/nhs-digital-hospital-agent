"""Booking and scheduling service.

The whole module exists to get one thing right: two patients wanting the same slot at the
same instant. The defence is layered, and the layers are not redundant:

  1. `SELECT ... FOR UPDATE` on the slot row serialises concurrent bookers, so the common
     case is a short wait rather than a failure.
  2. The partial unique index `uq_appointment_active_slot` is the guarantee. If two
     transactions still race past the lock - different connections, a retried request, a
     future code path that forgets to lock - the database refuses the second one.
  3. The IntegrityError from that index is translated into 409 APPOINTMENT_CONFLICT, so the
     loser gets a clean answer instead of a 500.

Layer 2 is the one that must never be removed. Layers 1 and 3 make it pleasant; layer 2
makes it correct.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, cast

from sqlalchemy import CursorResult, delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import (
    AppointmentConflict,
    InvalidStateTransition,
    PermissionDenied,
    ResourceNotFound,
    SlotHoldExpired,
    ValidationFailed,
)
from app.core.logging import get_logger
from app.models.base import AuditResult, UserRole
from app.models.operational import Department, Site
from app.models.scheduling import (
    LIVE_APPOINTMENT_STATUSES,
    Appointment,
    AppointmentPriority,
    AppointmentSlot,
    AppointmentStatus,
    SlotHold,
    SlotStatus,
)
from app.services.audit import AuditService
from app.services.auth import RequestContext

logger = get_logger(__name__)

HOLD_DURATION = timedelta(minutes=5)

#: The constraints whose violation genuinely means "someone got there first".
_CONFLICT_CONSTRAINTS = frozenset({"uq_appointment_active_slot", "slot_holds_slot_id_key"})


def _is_booking_conflict(exc: IntegrityError) -> bool:
    """Whether an IntegrityError is a lost race rather than a defect.

    Translating *every* IntegrityError into 409 hides real bugs behind a plausible
    message: a NOT NULL violation once surfaced to the caller as "this slot is no longer
    available", which is both wrong and impossible to debug from the outside. Only the
    named constraints mean a conflict; anything else propagates and becomes a 500, which
    is what an unexpected failure should look like.
    """
    constraint = getattr(getattr(exc, "orig", None), "constraint_name", None)
    if constraint is None:
        # Some drivers surface the name only in the message text.
        message = str(getattr(exc, "orig", exc))
        return any(name in message for name in _CONFLICT_CONSTRAINTS)
    return constraint in _CONFLICT_CONSTRAINTS


#: How far ahead a patient may book. Beyond this a clinic timetable is provisional.
MAX_BOOKING_HORIZON = timedelta(days=84)

#: Cancelling with less notice than this still works, but is recorded as late so the
#: no-show reporting can tell a late cancellation from a simple absence.
LATE_CANCELLATION_WINDOW = timedelta(hours=24)


class AuditAction:
    APPOINTMENT_CREATED = "APPOINTMENT_CREATED"
    APPOINTMENT_CANCELLED = "APPOINTMENT_CANCELLED"
    APPOINTMENT_RESCHEDULED = "APPOINTMENT_RESCHEDULED"
    SLOT_HELD = "SLOT_HELD"
    BOOKING_CONFLICT = "BOOKING_CONFLICT"


@dataclass(frozen=True, slots=True)
class SlotView:
    id: uuid.UUID
    starts_at: datetime
    ends_at: datetime
    slot_type: str
    department_id: uuid.UUID
    department_name: str
    site_name: str
    clinician_name: str | None
    held: bool


class BookingService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self.audit = AuditService(session)

    # --- Availability ---------------------------------------------------------

    async def list_open_slots(
        self,
        *,
        department_id: uuid.UUID | None,
        from_date: datetime | None,
        to_date: datetime | None,
        limit: int,
    ) -> list[SlotView]:
        """Slots a patient could still book.

        A slot is offered only when it is AVAILABLE, in the future, carries no live
        appointment and is not under someone else's unexpired hold. All four are checked in
        the query rather than filtered afterwards, so paging cannot return a short page of
        mostly-unbookable rows.
        """
        now = datetime.now(UTC)
        start = max(from_date or now, now)
        end = to_date or (now + MAX_BOOKING_HORIZON)

        if end <= start:
            raise ValidationFailed("The end of the date range must be after the start.")

        from app.models.identity import Staff

        taken = (
            select(Appointment.slot_id)
            .where(Appointment.status.in_(LIVE_APPOINTMENT_STATUSES))
            .scalar_subquery()
        )
        held = select(SlotHold.slot_id).where(SlotHold.expires_at > now).scalar_subquery()

        stmt = (
            select(AppointmentSlot, Department.name, Site.name, Staff)
            .join(Department, Department.id == AppointmentSlot.department_id)
            .join(Site, Site.id == AppointmentSlot.site_id)
            .outerjoin(Staff, Staff.id == AppointmentSlot.staff_id)
            .where(
                AppointmentSlot.status == SlotStatus.AVAILABLE,
                AppointmentSlot.starts_at >= start,
                AppointmentSlot.starts_at <= end,
                AppointmentSlot.id.notin_(taken),
                AppointmentSlot.id.notin_(held),
            )
            .order_by(AppointmentSlot.starts_at)
            .limit(limit)
        )
        if department_id is not None:
            stmt = stmt.where(AppointmentSlot.department_id == department_id)

        rows = (await self._session.execute(stmt)).all()

        return [
            SlotView(
                id=slot.id,
                starts_at=slot.starts_at,
                ends_at=slot.ends_at,
                slot_type=slot.slot_type.value,
                department_id=slot.department_id,
                department_name=department_name,
                site_name=site_name,
                clinician_name=staff.display_name if staff else None,
                held=False,
            )
            for slot, department_name, site_name, staff in rows
        ]

    # --- Holds ----------------------------------------------------------------

    async def hold_slot(
        self, slot_id: uuid.UUID, *, patient_id: uuid.UUID, context: RequestContext
    ) -> datetime:
        """Reserve a slot briefly while the patient confirms.

        Returns when the hold expires. Taking a hold is not a booking: if the patient walks
        away, it lapses and the slot returns to the pool without anyone intervening.
        """
        slot = await self._lock_slot(slot_id)
        await self._assert_bookable(slot)

        now = datetime.now(UTC)

        # Clear a lapsed hold first. The UNIQUE on slot_id means an expired row would
        # otherwise block a legitimate new hold forever.
        await self._session.execute(
            delete(SlotHold).where(SlotHold.slot_id == slot_id, SlotHold.expires_at <= now)
        )

        existing = (
            await self._session.execute(select(SlotHold).where(SlotHold.slot_id == slot_id))
        ).scalar_one_or_none()

        if existing is not None:
            if existing.patient_id != patient_id:
                raise AppointmentConflict(
                    "Someone else is booking this time. Please choose another."
                )
            # Same patient returning: extend rather than refuse.
            existing.expires_at = now + HOLD_DURATION
            await self._session.flush()
            return existing.expires_at

        hold = SlotHold(slot_id=slot_id, patient_id=patient_id, expires_at=now + HOLD_DURATION)
        self._session.add(hold)

        try:
            await self._session.flush()
        except IntegrityError as exc:
            await self._session.rollback()
            if not _is_booking_conflict(exc):
                raise
            raise AppointmentConflict(
                "Someone else is booking this time. Please choose another."
            ) from exc

        await self.audit.record(
            action=AuditAction.SLOT_HELD,
            resource_type="AppointmentSlot",
            resource_id=slot_id,
            request_id=context.request_id,
            ip_hash=context.ip_hash,
            metadata={"expiresInSeconds": int(HOLD_DURATION.total_seconds())},
        )
        return hold.expires_at

    # --- Booking --------------------------------------------------------------

    async def book(
        self,
        slot_id: uuid.UUID,
        *,
        patient_id: uuid.UUID,
        actor_user_id: uuid.UUID,
        actor_role: UserRole,
        reason: str | None,
        priority: AppointmentPriority | None,
        previous_appointment_id: uuid.UUID | None,
        context: RequestContext,
    ) -> Appointment:
        slot = await self._lock_slot(slot_id)
        await self._assert_bookable(slot)

        now = datetime.now(UTC)
        hold = (
            await self._session.execute(select(SlotHold).where(SlotHold.slot_id == slot_id))
        ).scalar_one_or_none()

        if hold is not None and hold.expires_at > now and hold.patient_id != patient_id:
            await self._record_conflict(
                slot_id, actor_user_id, actor_role, context, "held_by_other"
            )
            raise AppointmentConflict("Someone else is booking this time. Please choose another.")

        if hold is not None and hold.patient_id == patient_id and hold.expires_at <= now:
            # Their own hold lapsed. Distinguished from a plain conflict so the UI can say
            # "your reserved time expired" rather than implying someone else took it - the
            # slot may well still be free.
            await self._session.execute(delete(SlotHold).where(SlotHold.id == hold.id))
            raise SlotHoldExpired()

        appointment = Appointment(
            patient_id=patient_id,
            slot_id=slot_id,
            department_id=slot.department_id,
            staff_id=slot.staff_id,
            status=AppointmentStatus.BOOKED,
            priority=priority,
            reason_text=reason,
            booked_by_user_id=actor_user_id,
            previous_appointment_id=previous_appointment_id,
        )
        self._session.add(appointment)

        try:
            await self._session.flush()
        except IntegrityError as exc:
            await self._session.rollback()
            if not _is_booking_conflict(exc):
                # A different constraint failed, which means a defect rather than a race.
                # Let it become a 500 so it is visible instead of masquerading as a busy
                # slot.
                logger.exception(
                    "booking_integrity_error", extra={"request_id": context.request_id}
                )
                raise
            # uq_appointment_active_slot fired: another transaction booked this slot
            # between our lock and our insert. This is the race the index exists for, and
            # reaching here means it worked.
            logger.info(
                "booking_conflict",
                extra={"request_id": context.request_id, "slot_id": str(slot_id)},
            )
            raise AppointmentConflict() from exc

        if hold is not None:
            await self._session.execute(delete(SlotHold).where(SlotHold.id == hold.id))

        await self._session.refresh(appointment, ["reference"])

        await self.audit.record(
            action=AuditAction.APPOINTMENT_CREATED,
            actor_user_id=actor_user_id,
            actor_role=actor_role,
            resource_type="Appointment",
            resource_id=appointment.id,
            request_id=context.request_id,
            ip_hash=context.ip_hash,
            metadata={"reference": appointment.reference},
        )
        return appointment

    # --- Cancel ---------------------------------------------------------------

    async def cancel(
        self,
        appointment_id: uuid.UUID,
        *,
        patient_id: uuid.UUID | None,
        actor_user_id: uuid.UUID,
        actor_role: UserRole,
        reason: str | None,
        context: RequestContext,
    ) -> Appointment:
        appointment = await self._get_for_actor(appointment_id, patient_id, actor_role)

        if not appointment.is_cancellable:
            raise InvalidStateTransition(
                f"This appointment cannot be cancelled because it is "
                f"{appointment.status.value.replace('_', ' ').lower()}."
            )

        slot = await self._session.get(AppointmentSlot, appointment.slot_id)
        now = datetime.now(UTC)
        late = bool(slot and slot.starts_at - now < LATE_CANCELLATION_WINDOW)

        appointment.status = AppointmentStatus.CANCELLED
        appointment.cancelled_at = now
        appointment.cancellation_reason = (reason or "").strip()[:200] or None
        await self._session.flush()

        await self.audit.record(
            action=AuditAction.APPOINTMENT_CANCELLED,
            actor_user_id=actor_user_id,
            actor_role=actor_role,
            resource_type="Appointment",
            resource_id=appointment.id,
            request_id=context.request_id,
            ip_hash=context.ip_hash,
            # The reason is free text a patient typed; it stays on the appointment and out
            # of the audit metadata.
            metadata={"reference": appointment.reference, "lateCancellation": late},
        )
        return appointment

    # --- Reschedule -----------------------------------------------------------

    async def reschedule(
        self,
        appointment_id: uuid.UUID,
        *,
        new_slot_id: uuid.UUID,
        patient_id: uuid.UUID | None,
        actor_user_id: uuid.UUID,
        actor_role: UserRole,
        context: RequestContext,
    ) -> Appointment:
        """Move an appointment to a different slot.

        The new booking is taken *before* the old one is released. Cancelling first would
        risk losing both: if the new slot turns out to be gone, the patient would be left
        with no appointment at all.
        """
        original = await self._get_for_actor(appointment_id, patient_id, actor_role)

        if not original.is_cancellable:
            raise InvalidStateTransition(
                "This appointment can no longer be changed. Please book a new one."
            )
        if original.slot_id == new_slot_id:
            raise ValidationFailed("That is the time this appointment is already booked for.")

        replacement = await self.book(
            new_slot_id,
            patient_id=original.patient_id,
            actor_user_id=actor_user_id,
            actor_role=actor_role,
            reason=original.reason_text,
            priority=original.priority,
            previous_appointment_id=original.id,
            context=context,
        )

        original.status = AppointmentStatus.CANCELLED
        original.cancelled_at = datetime.now(UTC)
        original.cancellation_reason = "Rescheduled"
        await self._session.flush()

        await self.audit.record(
            action=AuditAction.APPOINTMENT_RESCHEDULED,
            actor_user_id=actor_user_id,
            actor_role=actor_role,
            resource_type="Appointment",
            resource_id=replacement.id,
            request_id=context.request_id,
            ip_hash=context.ip_hash,
            metadata={"from": original.reference, "to": replacement.reference},
        )
        return replacement

    # --- Reads ----------------------------------------------------------------

    async def list_for_patient(
        self, patient_id: uuid.UUID, *, include_past: bool
    ) -> list[tuple[Appointment, AppointmentSlot, str, str]]:
        stmt = (
            select(Appointment, AppointmentSlot, Department.name, Site.name)
            .join(AppointmentSlot, AppointmentSlot.id == Appointment.slot_id)
            .join(Department, Department.id == Appointment.department_id)
            .join(Site, Site.id == AppointmentSlot.site_id)
            .where(Appointment.patient_id == patient_id)
            .order_by(AppointmentSlot.starts_at.desc())
        )
        if not include_past:
            stmt = stmt.where(AppointmentSlot.starts_at >= datetime.now(UTC))

        rows = (await self._session.execute(stmt)).all()
        return [(a, s, d, site) for a, s, d, site in rows]

    async def get_detail(
        self, appointment_id: uuid.UUID, *, patient_id: uuid.UUID | None, actor_role: UserRole
    ) -> tuple[Appointment, AppointmentSlot, str, str]:
        appointment = await self._get_for_actor(appointment_id, patient_id, actor_role)
        slot = await self._session.get(AppointmentSlot, appointment.slot_id)
        if slot is None:
            raise ResourceNotFound()

        department = await self._session.get(Department, appointment.department_id)
        site = await self._session.get(Site, slot.site_id)
        return appointment, slot, department.name if department else "", site.name if site else ""

    # --- Internals ------------------------------------------------------------

    async def _lock_slot(self, slot_id: uuid.UUID) -> AppointmentSlot:
        """Take a row lock so concurrent bookers queue rather than collide.

        This is an optimisation, not the guarantee - see the module docstring.
        """
        slot = (
            await self._session.execute(
                select(AppointmentSlot).where(AppointmentSlot.id == slot_id).with_for_update()
            )
        ).scalar_one_or_none()

        if slot is None:
            raise ResourceNotFound("That appointment time could not be found.")
        return slot

    async def _assert_bookable(self, slot: AppointmentSlot) -> None:
        now = datetime.now(UTC)

        if slot.status is not SlotStatus.AVAILABLE:
            raise AppointmentConflict()
        if slot.starts_at <= now:
            raise ValidationFailed("That appointment time is in the past.")
        if slot.starts_at > now + MAX_BOOKING_HORIZON:
            raise ValidationFailed(
                "That date is too far ahead to book yet. Please choose a nearer time."
            )

        occupied = (
            await self._session.execute(
                select(func.count())
                .select_from(Appointment)
                .where(
                    Appointment.slot_id == slot.id,
                    Appointment.status.in_(LIVE_APPOINTMENT_STATUSES),
                )
            )
        ).scalar_one()

        if occupied:
            raise AppointmentConflict()

    async def _get_for_actor(
        self, appointment_id: uuid.UUID, patient_id: uuid.UUID | None, actor_role: UserRole
    ) -> Appointment:
        appointment = await self._session.get(Appointment, appointment_id)
        if appointment is None:
            raise ResourceNotFound()

        if actor_role is UserRole.PATIENT:
            if appointment.patient_id != patient_id:
                # 404, not 403: a 403 would confirm the appointment exists and belongs to
                # someone else, which is itself a disclosure.
                raise ResourceNotFound()
            return appointment

        if actor_role is UserRole.ADMIN:
            raise PermissionDenied("Administrator accounts cannot open individual appointments.")

        return appointment

    async def _record_conflict(
        self,
        slot_id: uuid.UUID,
        actor_user_id: uuid.UUID,
        actor_role: UserRole,
        context: RequestContext,
        reason: str,
    ) -> None:
        await self.audit.record(
            action=AuditAction.BOOKING_CONFLICT,
            result=AuditResult.DENIED,
            actor_user_id=actor_user_id,
            actor_role=actor_role,
            resource_type="AppointmentSlot",
            resource_id=slot_id,
            request_id=context.request_id,
            ip_hash=context.ip_hash,
            metadata={"reason": reason},
        )


async def purge_expired_holds(session: AsyncSession) -> int:
    """Delete lapsed holds.

    Correctness does not depend on this - every read filters on `expires_at` and every
    write clears a lapsed row first. It exists to stop the table growing without bound.
    """
    result = cast(
        CursorResult[Any],
        await session.execute(delete(SlotHold).where(SlotHold.expires_at <= datetime.now(UTC))),
    )
    return int(result.rowcount or 0)
