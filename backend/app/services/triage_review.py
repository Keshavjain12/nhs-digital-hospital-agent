"""Clinician review of triage output.

The point of this module is the distinction it preserves. `TriageResult.severity` is what
the engine said and is immutable by database trigger. A clinician agreeing writes
CLINICIAN_CONFIRMED; a clinician disagreeing writes `clinician_severity` alongside. The
engine's band is never edited.

That matters for two separate reasons:

- Clinically, "the system said EMERGENCY and a doctor downgraded it, with this reason, at
  this time" is a different fact from "it was always ROUTINE", and only the first is
  reviewable after an incident.
- For the AI/ML domain, the gap between engine output and clinician decision is the only
  honest measure of how the engine is performing. Overwriting the original destroys the
  evaluation data.

Administrators are excluded here as everywhere else: a triage band is clinical content.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import Case, Text, case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import PermissionDenied, ResourceNotFound, ValidationFailed
from app.models.base import UserRole
from app.models.chat import TriageResult, TriageReviewStatus
from app.models.clinical import Patient
from app.services.audit import AuditService
from app.services.auth import RequestContext
from app.services.triage import Severity

MIN_OVERRIDE_NOTE = 10

#: Sort weight per band. Expressed here rather than relying on the enum's storage order,
#: which is an implementation detail of the type and not a clinical ordering.
_SEVERITY_RANK: dict[str, int] = {
    "EMERGENCY": 0,
    "URGENT": 1,
    "SOON": 2,
    "ROUTINE": 3,
    "SELF_CARE": 4,
}


def _severity_rank() -> Case[int]:
    """SQL CASE mapping a severity to its sort weight."""
    return case(
        dict(_SEVERITY_RANK),
        value=func.cast(TriageResult.severity, Text),
        else_=99,
    )


class AuditAction:
    TRIAGE_REVIEWED = "TRIAGE_REVIEWED"
    TRIAGE_OVERRIDDEN = "TRIAGE_OVERRIDDEN"


@dataclass(frozen=True, slots=True)
class TriageQueueItem:
    result: TriageResult
    patient: Patient


class TriageReviewService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self.audit = AuditService(session)

    async def pending_queue(
        self, *, actor_role: UserRole, only_pending: bool, limit: int
    ) -> list[TriageQueueItem]:
        self._require_clinician(actor_role)

        stmt = (
            select(TriageResult, Patient)
            .join(Patient, Patient.id == TriageResult.patient_id)
            .where(Patient.deleted_at.is_(None))
            # Most urgent first, then oldest first within a band: someone who has waited
            # on an URGENT result should not be pushed down by a newer one.
            .order_by(_severity_rank(), TriageResult.created_at)
            .limit(limit)
        )
        if only_pending:
            stmt = stmt.where(TriageResult.review_status == TriageReviewStatus.PENDING_REVIEW)

        rows = (await self._session.execute(stmt)).all()
        return [TriageQueueItem(result=result, patient=patient) for result, patient in rows]

    async def latest_for_patients(
        self, patient_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, TriageResult]:
        """The most recent triage per patient, for the queue's priority column.

        One query rather than one per row: a clinician list of fifty patients would
        otherwise issue fifty extra round trips to render a single column.
        """
        if not patient_ids:
            return {}

        ranked = (
            select(
                TriageResult,
                func.row_number()
                .over(
                    partition_by=TriageResult.patient_id,
                    order_by=TriageResult.created_at.desc(),
                )
                .label("rank"),
            )
            .where(TriageResult.patient_id.in_(patient_ids))
            .subquery()
        )

        rows = (
            await self._session.execute(
                select(TriageResult)
                .join(ranked, ranked.c.id == TriageResult.id)
                .where(ranked.c.rank == 1)
            )
        ).scalars()

        return {row.patient_id: row for row in rows}

    async def review(
        self,
        result_id: uuid.UUID,
        *,
        agrees: bool,
        clinician_severity: str | None,
        note: str | None,
        actor_user_id: uuid.UUID,
        actor_role: UserRole,
        staff_id: uuid.UUID | None,
        context: RequestContext,
    ) -> TriageResult:
        self._require_clinician(actor_role)
        if staff_id is None:
            raise PermissionDenied("Your account is not linked to a staff record.")

        result = await self._session.get(TriageResult, result_id)
        if result is None:
            raise ResourceNotFound()

        if result.review_status is not TriageReviewStatus.PENDING_REVIEW:
            # Not an error worth blocking on, but re-reviewing should be a deliberate act
            # rather than an accident of a double-submitted form.
            raise ValidationFailed("This result has already been reviewed.")

        if agrees:
            result.review_status = TriageReviewStatus.CLINICIAN_CONFIRMED
            result.clinician_severity = None
        else:
            if clinician_severity is None:
                raise ValidationFailed("Choose the urgency you think is correct.")
            try:
                Severity(clinician_severity)
            except ValueError as exc:
                raise ValidationFailed("That is not a valid urgency.") from exc
            if not note or len(note.strip()) < MIN_OVERRIDE_NOTE:
                # An override with no reason is unreviewable later, and is exactly the
                # record an incident investigation needs.
                raise ValidationFailed(
                    f"Give a reason of at least {MIN_OVERRIDE_NOTE} characters for changing "
                    "the urgency."
                )
            result.review_status = TriageReviewStatus.CLINICIAN_OVERRIDDEN
            result.clinician_severity = clinician_severity

        result.clinician_note = (note or "").strip() or None
        result.reviewed_by_staff_id = staff_id
        result.reviewed_at = datetime.now(UTC)
        await self._session.flush()

        await self.audit.record(
            action=(AuditAction.TRIAGE_REVIEWED if agrees else AuditAction.TRIAGE_OVERRIDDEN),
            actor_user_id=actor_user_id,
            actor_role=actor_role,
            resource_type="TriageResult",
            resource_id=result.id,
            request_id=context.request_id,
            ip_hash=context.ip_hash,
            # Bands and the engine, never the patient's words or the clinician's free text.
            metadata={
                "engineSeverity": result.severity,
                "clinicianSeverity": result.clinician_severity,
                "engine": f"{result.engine}@{result.engine_version}",
            },
        )
        return result

    @staticmethod
    def _require_clinician(actor_role: UserRole) -> None:
        """Defence in depth.

        Routes already guard this with RequireClinician, which refuses first - so this
        message is not what an HTTP caller sees. It exists for any future caller that
        reaches the service directly, where the check would otherwise be absent entirely.
        """
        if actor_role not in {UserRole.DOCTOR, UserRole.NURSE}:
            raise PermissionDenied(
                "Only clinical staff can review triage results. Administrator accounts "
                "cannot see clinical content."
            )


def effective_severity(result: TriageResult) -> str:
    """The band that should drive care: the clinician's if they set one, else the engine's.

    Callers must not reimplement this. Reading `severity` alone silently ignores an
    override; reading `clinician_severity` alone is null for everything unreviewed.
    """
    return result.clinician_severity or result.severity
