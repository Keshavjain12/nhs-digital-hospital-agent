"""Administrator routes.

Operational visibility only. Nothing here returns a patient identity or any clinical
content - see docs/security/rbac-and-audit.md §3. An administrator can see that a ward is
full, or that a record was accessed under emergency override, without being entitled to
know who the patient is or why they are there.

The audit reader is the one place an admin sees identifiers, and only of *staff*: knowing
who accessed what is the whole purpose of an audit trail, and someone has to be able to
review it.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select

from app.core.deps import (
    RequestCtx,
    RequireAdmin,
    TransactionalSession,
    authenticated_rate_limit,
)
from app.core.errors import ErrorResponse
from app.models.audit import AuditLog
from app.models.base import AuditResult, UserRole
from app.models.clinical import Patient
from app.models.identity import Staff, User
from app.models.operational import Department
from app.schemas.admin import (
    AuditEntry,
    AuditListResponse,
    DepartmentSummary,
    KpiCard,
    OverviewResponse,
)
from app.schemas.base import PageMeta, ResponseMeta

router = APIRouter(
    prefix="/admin",
    tags=["Administration"],
    dependencies=[Depends(authenticated_rate_limit)],
)

_ERRORS: dict[int | str, dict[str, object]] = {
    401: {"model": ErrorResponse, "description": "Not signed in"},
    403: {"model": ErrorResponse, "description": "Administrator role required"},
}


@router.get(
    "/overview",
    response_model=OverviewResponse,
    summary="Operational overview",
    responses=_ERRORS,
)
async def overview(
    principal: RequireAdmin, session: TransactionalSession, context: RequestCtx
) -> OverviewResponse:
    """Aggregate counts only. No identity, no clinical content."""
    since = datetime.now(UTC) - timedelta(hours=24)

    registered_patients = (
        await session.execute(
            select(func.count()).select_from(Patient).where(Patient.deleted_at.is_(None))
        )
    ).scalar_one()

    active_staff = (
        await session.execute(select(func.count()).select_from(Staff).where(Staff.active.is_(True)))
    ).scalar_one()

    signins_24h = (
        await session.execute(
            select(func.count())
            .select_from(AuditLog)
            .where(
                AuditLog.action == "USER_LOGIN",
                AuditLog.result == AuditResult.SUCCESS,
                AuditLog.occurred_at >= since,
            )
        )
    ).scalar_one()

    denied_24h = (
        await session.execute(
            select(func.count())
            .select_from(AuditLog)
            .where(AuditLog.result == AuditResult.DENIED, AuditLog.occurred_at >= since)
        )
    ).scalar_one()

    breakglass_24h = (
        await session.execute(
            select(func.count())
            .select_from(AuditLog)
            .where(
                AuditLog.action == "BREAKGLASS_INVOKED",
                AuditLog.occurred_at >= since,
            )
        )
    ).scalar_one()

    record_views_24h = (
        await session.execute(
            select(func.count())
            .select_from(AuditLog)
            .where(
                AuditLog.action == "PATIENT_RECORD_VIEW",
                AuditLog.occurred_at >= since,
            )
        )
    ).scalar_one()

    departments = (
        (await session.execute(select(Department).order_by(Department.name))).scalars().all()
    )

    return OverviewResponse(
        cards=[
            KpiCard(
                key="registeredPatients",
                label="Registered patients",
                value=int(registered_patients),
                caption="Synthetic records in this environment",
            ),
            KpiCard(
                key="activeStaff",
                label="Active staff accounts",
                value=int(active_staff),
                caption="Clinical and operational users",
            ),
            KpiCard(
                key="signins24h",
                label="Sign-ins (24h)",
                value=int(signins_24h),
                caption="Successful authentications",
            ),
            KpiCard(
                key="deniedActions24h",
                label="Refused actions (24h)",
                value=int(denied_24h),
                caption="Failed sign-ins and permission denials",
                # A refusal count is not automatically bad; a sudden change in it is what
                # matters, which is why the caption avoids implying a target of zero.
                tone="neutral",
            ),
            KpiCard(
                key="recordViews24h",
                label="Record accesses (24h)",
                value=int(record_views_24h),
                caption="Patient records opened by staff",
            ),
            KpiCard(
                key="breakglass24h",
                label="Emergency overrides (24h)",
                value=int(breakglass_24h),
                caption="Access outside the care team",
                # The one card that always deserves attention: each of these is a
                # clinician reading a record they were not assigned to.
                tone="attention" if int(breakglass_24h) > 0 else "neutral",
            ),
        ],
        departments=[
            DepartmentSummary(id=d.id, code=d.code, name=d.name, data_origin=d.data_origin)
            for d in departments
        ],
        meta=ResponseMeta(request_id=context.request_id, data_origin="SYNTHETIC"),
    )


@router.get(
    "/audit",
    response_model=AuditListResponse,
    summary="Read the audit trail",
    responses=_ERRORS,
)
async def audit_trail(
    principal: RequireAdmin,
    session: TransactionalSession,
    context: RequestCtx,
    action: Annotated[str | None, Query(max_length=60)] = None,
    result: Annotated[str | None, Query(max_length=20)] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100, alias="pageSize")] = 25,
) -> AuditListResponse:
    stmt = select(AuditLog)
    if action:
        stmt = stmt.where(AuditLog.action == action)
    if result:
        stmt = stmt.where(AuditLog.result == result)

    total = (await session.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()

    rows = (
        (
            await session.execute(
                stmt.order_by(AuditLog.occurred_at.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        )
        .scalars()
        .all()
    )

    # Resolve actor emails in one query rather than per row.
    actor_ids = {row.actor_user_id for row in rows if row.actor_user_id}
    actors: dict[object, str] = {}
    if actor_ids:
        actors = {
            user.id: user.email
            for user in (await session.execute(select(User).where(User.id.in_(actor_ids))))
            .scalars()
            .all()
        }

    return AuditListResponse(
        items=[
            AuditEntry(
                id=row.id,
                action=row.action,
                result=row.result.value,
                # Staff identity, never patient identity. `resource_id` stays an opaque
                # identifier: an admin can see that a record was read without learning
                # whose it was.
                actor=actors.get(row.actor_user_id, "system") if row.actor_user_id else "system",
                actor_role=row.actor_role.value if row.actor_role else None,
                resource_type=row.resource_type,
                resource_id=str(row.resource_id) if row.resource_id else None,
                metadata=row.metadata_,
                occurred_at=row.occurred_at,
            )
            for row in rows
        ],
        meta=PageMeta(
            request_id=context.request_id,
            data_origin="SYNTHETIC",
            page=page,
            page_size=page_size,
            total_items=int(total),
            total_pages=max(1, (int(total) + page_size - 1) // page_size),
        ),
    )


@router.get(
    "/roles",
    summary="Role and permission reference",
    responses=_ERRORS,
)
async def roles(principal: RequireAdmin) -> dict[str, object]:
    """The access model, served from the code that enforces it.

    Documentation drifts from behaviour. Serving this from the same enum the
    authorisation dependencies use means the reference cannot silently go stale.
    """
    return {
        "roles": [
            {
                "role": UserRole.PATIENT.value,
                "canRead": ["Their own record", "Their own appointments"],
                "cannot": ["Any other patient's record"],
            },
            {
                "role": UserRole.NURSE.value,
                "canRead": ["Assigned patients", "Patient search"],
                "cannot": ["Unassigned records without emergency access"],
            },
            {
                "role": UserRole.DOCTOR.value,
                "canRead": ["Assigned patients", "Patient search"],
                "cannot": ["Unassigned records without emergency access"],
            },
            {
                "role": UserRole.ADMIN.value,
                "canRead": ["Operational aggregates", "Audit trail"],
                "cannot": [
                    "Patient records",
                    "Patient search",
                    "Any clinical content",
                ],
            },
        ],
        "note": (
            "Administrators are deliberately excluded from clinical data. Operational "
            "authority is not clinical authority."
        ),
    }
