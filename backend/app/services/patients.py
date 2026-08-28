"""Patient access service.

Implements the access model in docs/security/rbac-and-audit.md:

- A patient reads their own record and nothing else.
- A clinician reads a record they hold a care assignment for.
- A clinician may override that with break-glass, which requires a typed justification,
  expires, and raises a high-severity audit event.
- An **administrator cannot read clinical records at all**. Operational authority is not
  clinical authority: an admin can see that a ward is full without being entitled to know
  why any individual is in it.

Search is treated differently from reading. Finding the right person is a precondition of
care, so any clinician may search; the results carry identity only, and every search is
audited.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import PermissionDenied, ResourceNotFound, ValidationFailed
from app.models.audit import AuditAction
from app.models.base import AuditResult, UserRole
from app.models.clinical import Patient
from app.models.identity import BreakglassGrant, CareAssignment
from app.schemas.patients import (
    AccessBasis,
    PatientListItem,
    PatientSummary,
)
from app.services.audit import AuditService
from app.services.auth import RequestContext
from app.services.triage_review import TriageReviewService

BREAKGLASS_DURATION = timedelta(hours=4)
MIN_BREAKGLASS_REASON = 20


def _triage_summary(result: object):  # type: ignore[no-untyped-def]
    """Adapter kept here so the patients router does not import the triage router."""
    from app.api.v1.triage import to_summary

    return to_summary(result)  # type: ignore[arg-type]


def _age(born: date) -> int:
    today = date.today()
    return today.year - born.year - ((today.month, today.day) < (born.month, born.day))


class PatientService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self.audit = AuditService(session)

    # --- Search ---------------------------------------------------------------

    async def search(
        self,
        *,
        actor_user_id: uuid.UUID,
        actor_role: UserRole,
        staff_id: uuid.UUID | None,
        query: str | None,
        page: int,
        page_size: int,
        context: RequestContext,
    ) -> tuple[list[PatientListItem], int]:
        if actor_role is UserRole.ADMIN:
            # Deliberate. See the module docstring: administrators get aggregates, never
            # the identities behind them.
            await self._deny(actor_user_id, actor_role, context, reason="admin_no_clinical_access")
            raise PermissionDenied(
                "Administrator accounts cannot view patient records. "
                "This is by design, not a configuration problem."
            )

        stmt = select(Patient).where(Patient.deleted_at.is_(None))

        if query:
            term = f"%{query.strip().lower()}%"
            digits = "".join(ch for ch in query if ch.isdigit())
            conditions = [
                func.lower(Patient.family_name).like(term),
                func.lower(Patient.given_name).like(term),
            ]
            if digits:
                conditions.append(Patient.nhs_number.like(f"%{digits}%"))
            stmt = stmt.where(or_(*conditions))

        total = (
            await self._session.execute(select(func.count()).select_from(stmt.subquery()))
        ).scalar_one()

        rows = (
            (
                await self._session.execute(
                    stmt.order_by(Patient.family_name, Patient.given_name)
                    .offset((page - 1) * page_size)
                    .limit(page_size)
                )
            )
            .scalars()
            .all()
        )

        assigned = await self._assigned_patient_ids(staff_id)
        # One query for the whole page rather than one per row.
        triage_by_patient = await TriageReviewService(self._session).latest_for_patients(
            [row.id for row in rows]
        )

        await self.audit.record(
            action="PATIENT_SEARCH",
            actor_user_id=actor_user_id,
            actor_role=actor_role,
            request_id=context.request_id,
            ip_hash=context.ip_hash,
            # The search term is not recorded: it is typically a patient's name, and the
            # audit log is not a place to accumulate identities.
            metadata={"resultCount": len(rows), "hadQuery": bool(query)},
        )

        return [
            PatientListItem(
                id=row.id,
                given_name=row.given_name,
                family_name=row.family_name,
                nhs_number=row.nhs_number,
                date_of_birth=row.date_of_birth,
                age=_age(row.date_of_birth),
                interpreter_needed=row.interpreter_needed,
                preferred_language=row.preferred_language,
                data_origin=row.data_origin,
                assigned_to_me=row.id in assigned,
                latest_triage=(
                    _triage_summary(triage_by_patient[row.id])
                    if row.id in triage_by_patient
                    else None
                ),
            )
            for row in rows
        ], int(total)

    # --- Read -----------------------------------------------------------------

    async def get_for_actor(
        self,
        patient_id: uuid.UUID,
        *,
        actor_user_id: uuid.UUID,
        actor_role: UserRole,
        actor_patient_id: uuid.UUID | None,
        staff_id: uuid.UUID | None,
        context: RequestContext,
    ) -> tuple[PatientSummary, AccessBasis, object | None]:
        patient = await self._session.get(Patient, patient_id)
        if patient is None or patient.deleted_at is not None:
            raise ResourceNotFound()

        basis = await self._authorise_read(
            patient_id,
            actor_user_id=actor_user_id,
            actor_role=actor_role,
            actor_patient_id=actor_patient_id,
            staff_id=staff_id,
            context=context,
        )

        await self.audit.record(
            action=AuditAction.PATIENT_RECORD_VIEW,
            actor_user_id=actor_user_id,
            actor_role=actor_role,
            resource_type="Patient",
            resource_id=patient_id,
            request_id=context.request_id,
            ip_hash=context.ip_hash,
            metadata={"accessBasis": basis.basis},
        )

        latest = (await TriageReviewService(self._session).latest_for_patients([patient_id])).get(
            patient_id
        )
        return self._to_summary(patient), basis, (_triage_summary(latest) if latest else None)

    async def _authorise_read(
        self,
        patient_id: uuid.UUID,
        *,
        actor_user_id: uuid.UUID,
        actor_role: UserRole,
        actor_patient_id: uuid.UUID | None,
        staff_id: uuid.UUID | None,
        context: RequestContext,
    ) -> AccessBasis:
        if actor_role is UserRole.PATIENT:
            if actor_patient_id == patient_id:
                return AccessBasis(basis="SELF")
            await self._deny(actor_user_id, actor_role, context, reason="not_own_record")
            # 404 rather than 403: a 403 would confirm the record exists, which leaks the
            # existence of a patient to anyone able to guess an identifier.
            raise ResourceNotFound()

        if actor_role is UserRole.ADMIN:
            await self._deny(actor_user_id, actor_role, context, reason="admin_no_clinical_access")
            raise PermissionDenied(
                "Administrator accounts cannot view patient records. "
                "This is by design, not a configuration problem."
            )

        if staff_id is None:
            await self._deny(actor_user_id, actor_role, context, reason="no_staff_record")
            raise PermissionDenied("Your account is not linked to a staff record.")

        if patient_id in await self._assigned_patient_ids(staff_id):
            return AccessBasis(basis="CARE_ASSIGNMENT")

        grant = await self._active_breakglass(staff_id, patient_id)
        if grant is not None:
            return AccessBasis(basis="BREAKGLASS", expires_at=grant.expires_at)

        await self._deny(actor_user_id, actor_role, context, reason="no_care_relationship")
        raise PermissionDenied(
            "You are not part of this patient's care team.",
            # Lets the UI offer the emergency-access dialog rather than presenting this as
            # a dead end. Carries no information about the patient.
            hint="breakglass_available",
        )

    # --- Break-glass ----------------------------------------------------------

    async def grant_breakglass(
        self,
        patient_id: uuid.UUID,
        *,
        reason: str,
        actor_user_id: uuid.UUID,
        actor_role: UserRole,
        staff_id: uuid.UUID | None,
        context: RequestContext,
    ) -> BreakglassGrant:
        """Emergency access to a record outside the care team.

        This exists because clinical reality does not respect assignment tables: a patient
        can arrive unconscious in front of a clinician who has no prior relationship with
        them, and refusing access there would be unsafe. Access is granted, but loudly.
        """
        if actor_role not in {UserRole.DOCTOR, UserRole.NURSE} or staff_id is None:
            raise PermissionDenied("Only clinical staff can use emergency access.")

        cleaned = reason.strip()
        if len(cleaned) < MIN_BREAKGLASS_REASON:
            # Also enforced by a CHECK constraint in migration 001. "urgent" is not a
            # justification, and a free-text box nobody validates becomes one.
            raise ValidationFailed(
                f"Give a reason of at least {MIN_BREAKGLASS_REASON} characters explaining "
                "why you need access to this record."
            )

        patient = await self._session.get(Patient, patient_id)
        if patient is None or patient.deleted_at is not None:
            raise ResourceNotFound()

        grant = BreakglassGrant(
            staff_id=staff_id,
            patient_id=patient_id,
            reason=cleaned,
            expires_at=datetime.now(UTC) + BREAKGLASS_DURATION,
        )
        self._session.add(grant)
        await self._session.flush()

        await self.audit.record(
            action=AuditAction.BREAKGLASS_INVOKED,
            actor_user_id=actor_user_id,
            actor_role=actor_role,
            resource_type="Patient",
            resource_id=patient_id,
            request_id=context.request_id,
            ip_hash=context.ip_hash,
            metadata={"expiresAt": grant.expires_at.isoformat()},
            # The justification is stored on the grant and referenced here rather than
            # copied, so it exists in exactly one place.
            detail="Emergency access invoked outside the care team.",
        )

        return grant

    # --- Helpers --------------------------------------------------------------

    async def _assigned_patient_ids(self, staff_id: uuid.UUID | None) -> set[uuid.UUID]:
        if staff_id is None:
            return set()
        rows = (
            await self._session.execute(
                select(CareAssignment.patient_id).where(
                    CareAssignment.staff_id == staff_id,
                    CareAssignment.valid_to.is_(None),
                )
            )
        ).scalars()
        return set(rows)

    async def _active_breakglass(
        self, staff_id: uuid.UUID, patient_id: uuid.UUID
    ) -> BreakglassGrant | None:
        return (
            await self._session.execute(
                select(BreakglassGrant)
                .where(
                    BreakglassGrant.staff_id == staff_id,
                    BreakglassGrant.patient_id == patient_id,
                    BreakglassGrant.expires_at > datetime.now(UTC),
                )
                .order_by(BreakglassGrant.expires_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()

    async def _deny(
        self,
        actor_user_id: uuid.UUID,
        actor_role: UserRole,
        context: RequestContext,
        *,
        reason: str,
    ) -> None:
        await self.audit.record(
            action=AuditAction.PERMISSION_DENIED,
            result=AuditResult.DENIED,
            actor_user_id=actor_user_id,
            actor_role=actor_role,
            request_id=context.request_id,
            ip_hash=context.ip_hash,
            metadata={"reason": reason},
        )
        # Committed before the caller raises, so the refusal survives the rollback that
        # the exception triggers. A denial nobody can see afterwards is not an audit.
        await self._session.commit()

    @staticmethod
    def _to_summary(patient: Patient) -> PatientSummary:
        return PatientSummary(
            id=patient.id,
            given_name=patient.given_name,
            family_name=patient.family_name,
            nhs_number=patient.nhs_number,
            date_of_birth=patient.date_of_birth,
            age=_age(patient.date_of_birth),
            sex_at_birth=patient.sex_at_birth,
            email=patient.email,
            phone_e164=patient.phone_e164,
            address_line1=patient.address_line1,
            city=patient.city,
            postcode=patient.postcode,
            preferred_language=patient.preferred_language,
            interpreter_needed=patient.interpreter_needed,
            accessibility_needs=patient.accessibility_needs,
            data_origin=patient.data_origin,
            registered_at=patient.created_at,
        )
