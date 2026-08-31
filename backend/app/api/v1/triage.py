"""Clinician-facing triage routes.

Clinical staff only. A triage band is clinical content, so administrators are refused here
exactly as they are on patient records - they can see in the model-monitoring panel that
overrides are happening and how often, without seeing whose.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.core.deps import (
    RequestCtx,
    RequireClinician,
    TransactionalSession,
    authenticated_rate_limit,
)
from app.core.errors import ErrorResponse
from app.models.chat import TriageResult
from app.schemas.base import ResponseMeta
from app.schemas.triage import (
    TriageQueueItemSchema,
    TriageQueueResponse,
    TriageReviewRequest,
    TriageReviewResponse,
    TriageSummary,
)
from app.services.triage_review import TriageReviewService, effective_severity

router = APIRouter(
    prefix="/triage", tags=["Triage review"], dependencies=[Depends(authenticated_rate_limit)]
)

_ERRORS: dict[int | str, dict[str, object]] = {
    401: {"model": ErrorResponse, "description": "Not signed in"},
    403: {"model": ErrorResponse, "description": "Clinical staff only"},
    404: {"model": ErrorResponse, "description": "Not found"},
}


def to_summary(result: TriageResult) -> TriageSummary:
    return TriageSummary(
        id=result.id,
        engine_severity=result.severity,
        clinician_severity=result.clinician_severity,
        effective_severity=effective_severity(result),
        recommended_action=result.recommended_action,
        red_flags=result.red_flags,
        engine=result.engine,
        engine_version=result.engine_version,
        confidence=float(result.confidence) if result.confidence is not None else None,
        review_status=result.review_status.value,
        clinician_note=result.clinician_note,
        reviewed_at=result.reviewed_at,
        created_at=result.created_at,
    )


@router.get(
    "",
    response_model=TriageQueueResponse,
    summary="Triage results awaiting review",
    responses=_ERRORS,
)
async def triage_queue(
    principal: RequireClinician,
    session: TransactionalSession,
    context: RequestCtx,
    only_pending: Annotated[bool, Query(alias="onlyPending")] = True,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> TriageQueueResponse:
    items = await TriageReviewService(session).pending_queue(
        actor_role=principal.role, only_pending=only_pending, limit=limit
    )
    return TriageQueueResponse(
        items=[
            TriageQueueItemSchema(
                triage=to_summary(item.result),
                patient_id=item.patient.id,
                patient_name=item.patient.display_name,
                patient_nhs_number=item.patient.nhs_number,
            )
            for item in items
        ],
        meta=ResponseMeta(request_id=context.request_id, data_origin="SYNTHETIC"),
    )


@router.post(
    "/{result_id}/review",
    response_model=TriageReviewResponse,
    summary="Confirm or change an automated urgency",
    responses=_ERRORS,
)
async def review_triage(
    result_id: uuid.UUID,
    payload: TriageReviewRequest,
    principal: RequireClinician,
    session: TransactionalSession,
    context: RequestCtx,
) -> TriageReviewResponse:
    """Record a clinician decision.

    Agreeing marks the result confirmed. Disagreeing stores the clinician's band
    *alongside* the engine's, which is never edited - so what the system said and what the
    clinician decided remain separately answerable, and the gap between them stays
    measurable.
    """
    result = await TriageReviewService(session).review(
        result_id,
        agrees=payload.agrees,
        clinician_severity=payload.clinician_severity,
        note=payload.note,
        actor_user_id=principal.user_id,
        actor_role=principal.role,
        staff_id=principal.staff_id,
        context=context,
    )
    return TriageReviewResponse(
        triage=to_summary(result),
        message=(
            "Recorded as confirmed."
            if payload.agrees
            else "Recorded. The original automated result has been kept alongside your decision."
        ),
    )
