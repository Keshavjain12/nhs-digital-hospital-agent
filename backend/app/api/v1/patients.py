"""Patient record routes.

Every route here authorises server-side against the database, not against the token's
claims. Frontend route guards are a usability feature; this is the control that matters
(brief §9).
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.core.deps import (
    RequestCtx,
    RequireClinician,
    TransactionalSession,
    VerifiedPrincipal,
    authenticated_rate_limit,
)
from app.core.errors import ErrorResponse
from app.schemas.base import PageMeta
from app.schemas.patients import (
    BreakglassRequest,
    BreakglassResponse,
    PatientDetailResponse,
    PatientListResponse,
)
from app.services.patients import PatientService

router = APIRouter(
    prefix="/patients",
    tags=["Patients"],
    dependencies=[Depends(authenticated_rate_limit)],
)

_ERRORS: dict[int | str, dict[str, object]] = {
    401: {"model": ErrorResponse, "description": "Not signed in"},
    403: {"model": ErrorResponse, "description": "Not permitted"},
    404: {"model": ErrorResponse, "description": "Not found or not visible"},
}


@router.get(
    "",
    response_model=PatientListResponse,
    summary="Search patients (clinical staff only)",
    responses=_ERRORS,
)
async def list_patients(
    principal: RequireClinician,
    session: TransactionalSession,
    context: RequestCtx,
    q: Annotated[str | None, Query(max_length=100, description="Name or NHS number")] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100, alias="pageSize")] = 20,
) -> PatientListResponse:
    items, total = await PatientService(session).search(
        actor_user_id=principal.user_id,
        actor_role=principal.role,
        staff_id=principal.staff_id,
        query=q,
        page=page,
        page_size=page_size,
        context=context,
    )

    return PatientListResponse(
        items=items,
        meta=PageMeta(
            request_id=context.request_id,
            data_origin="SYNTHETIC",
            page=page,
            page_size=page_size,
            total_items=total,
            total_pages=max(1, (total + page_size - 1) // page_size),
        ),
    )


@router.get(
    "/{patient_id}",
    response_model=PatientDetailResponse,
    summary="Read one patient record",
    responses=_ERRORS,
)
async def get_patient(
    patient_id: uuid.UUID,
    principal: VerifiedPrincipal,
    session: TransactionalSession,
    context: RequestCtx,
) -> PatientDetailResponse:
    """Read a record.

    A patient may read their own. A clinician may read a record they are assigned to, or
    one they have active emergency access for. Every read is written to the audit trail
    with the basis on which it was allowed.
    """
    patient, access, latest_triage = await PatientService(session).get_for_actor(
        patient_id,
        actor_user_id=principal.user_id,
        actor_role=principal.role,
        actor_patient_id=principal.patient_id,
        staff_id=principal.staff_id,
        context=context,
    )
    return PatientDetailResponse(patient=patient, access=access, latest_triage=latest_triage)


@router.post(
    "/{patient_id}/breakglass",
    response_model=BreakglassResponse,
    summary="Emergency access to a record outside your care team",
    responses=_ERRORS,
)
async def breakglass(
    patient_id: uuid.UUID,
    payload: BreakglassRequest,
    principal: RequireClinician,
    session: TransactionalSession,
    context: RequestCtx,
) -> BreakglassResponse:
    grant = await PatientService(session).grant_breakglass(
        patient_id,
        reason=payload.reason,
        actor_user_id=principal.user_id,
        actor_role=principal.role,
        staff_id=principal.staff_id,
        context=context,
    )
    return BreakglassResponse(
        granted_until=grant.expires_at,
        message=(
            "Emergency access granted and recorded. This access is time-limited and has "
            "been logged against your account for review."
        ),
    )
