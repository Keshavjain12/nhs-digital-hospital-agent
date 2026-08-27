"""Slot and appointment routes.

Contract: docs/api/api-contract-v1.md §4.

Booking is patient-scoped: the patient identity comes from the verified token, never from
the request body. A `patientId` field a caller could set would be an obvious way to book
appointments in someone else's name.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.core.deps import (
    RequestCtx,
    RequirePatient,
    TransactionalSession,
    VerifiedPrincipal,
    authenticated_rate_limit,
)
from app.core.errors import AuthenticationRequired, ErrorResponse
from app.models.scheduling import Appointment, AppointmentSlot
from app.schemas.base import ResponseMeta
from app.schemas.booking import (
    AppointmentDetailResponse,
    AppointmentItem,
    AppointmentListResponse,
    BookingCreatedResponse,
    BookRequest,
    CancelRequest,
    HoldResponse,
    RescheduleRequest,
    SlotItem,
    SlotListResponse,
)
from app.services.booking import BookingService

router = APIRouter(tags=["Appointments"], dependencies=[Depends(authenticated_rate_limit)])

_ERRORS: dict[int | str, dict[str, object]] = {
    401: {"model": ErrorResponse, "description": "Not signed in"},
    403: {"model": ErrorResponse, "description": "Not permitted"},
    404: {"model": ErrorResponse, "description": "Not found"},
    409: {"model": ErrorResponse, "description": "Slot no longer available"},
}


def _to_item(
    appointment: Appointment, slot: AppointmentSlot, department: str, site: str
) -> AppointmentItem:
    return AppointmentItem(
        id=appointment.id,
        reference=appointment.reference,
        status=appointment.status.value,
        priority=appointment.priority.value if appointment.priority else None,
        starts_at=slot.starts_at,
        ends_at=slot.ends_at,
        department_name=department,
        site_name=site,
        clinician_name=None,
        reason_text=appointment.reason_text,
        is_cancellable=appointment.is_cancellable,
        cancelled_at=appointment.cancelled_at,
        cancellation_reason=appointment.cancellation_reason,
    )


# --- Slots -------------------------------------------------------------------


@router.get(
    "/slots",
    response_model=SlotListResponse,
    summary="Appointment times available to book",
    responses=_ERRORS,
)
async def list_slots(
    principal: VerifiedPrincipal,
    session: TransactionalSession,
    context: RequestCtx,
    department_id: Annotated[uuid.UUID | None, Query(alias="departmentId")] = None,
    from_date: Annotated[datetime | None, Query(alias="from")] = None,
    to_date: Annotated[datetime | None, Query(alias="to")] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> SlotListResponse:
    slots = await BookingService(session).list_open_slots(
        department_id=department_id, from_date=from_date, to_date=to_date, limit=limit
    )
    return SlotListResponse(
        items=[
            SlotItem(
                id=slot.id,
                starts_at=slot.starts_at,
                ends_at=slot.ends_at,
                slot_type=slot.slot_type,
                department_id=slot.department_id,
                department_name=slot.department_name,
                site_name=slot.site_name,
                clinician_name=slot.clinician_name,
            )
            for slot in slots
        ],
        meta=ResponseMeta(request_id=context.request_id, data_origin="SYNTHETIC"),
    )


@router.post(
    "/slots/{slot_id}/hold",
    response_model=HoldResponse,
    summary="Reserve a time briefly while confirming",
    responses=_ERRORS,
)
async def hold_slot(
    slot_id: uuid.UUID,
    principal: RequirePatient,
    session: TransactionalSession,
    context: RequestCtx,
) -> HoldResponse:
    if principal.patient_id is None:
        raise AuthenticationRequired()

    expires_at = await BookingService(session).hold_slot(
        slot_id, patient_id=principal.patient_id, context=context
    )
    return HoldResponse(
        slot_id=slot_id,
        expires_at=expires_at,
        expires_in_seconds=max(0, int((expires_at - datetime.now(UTC)).total_seconds())),
    )


# --- Appointments -------------------------------------------------------------


@router.post(
    "/appointments",
    response_model=BookingCreatedResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Book an appointment",
    responses=_ERRORS,
)
async def create_appointment(
    payload: BookRequest,
    principal: RequirePatient,
    session: TransactionalSession,
    context: RequestCtx,
) -> BookingCreatedResponse:
    if principal.patient_id is None:
        raise AuthenticationRequired()

    service = BookingService(session)
    appointment = await service.book(
        payload.slot_id,
        patient_id=principal.patient_id,
        actor_user_id=principal.user_id,
        actor_role=principal.role,
        reason=payload.reason,
        priority=None,
        previous_appointment_id=None,
        context=context,
    )
    _, slot, department, site = await service.get_detail(
        appointment.id, patient_id=principal.patient_id, actor_role=principal.role
    )
    return BookingCreatedResponse(
        appointment=_to_item(appointment, slot, department, site),
        message="Your appointment is booked.",
    )


@router.get(
    "/appointments",
    response_model=AppointmentListResponse,
    summary="Your appointments",
    responses=_ERRORS,
)
async def list_appointments(
    principal: RequirePatient,
    session: TransactionalSession,
    context: RequestCtx,
    include_past: Annotated[bool, Query(alias="includePast")] = False,
) -> AppointmentListResponse:
    if principal.patient_id is None:
        raise AuthenticationRequired()

    rows = await BookingService(session).list_for_patient(
        principal.patient_id, include_past=include_past
    )
    return AppointmentListResponse(
        items=[_to_item(a, s, d, site) for a, s, d, site in rows],
        meta=ResponseMeta(request_id=context.request_id, data_origin="SYNTHETIC"),
    )


@router.get(
    "/appointments/{appointment_id}",
    response_model=AppointmentDetailResponse,
    summary="One appointment",
    responses=_ERRORS,
)
async def get_appointment(
    appointment_id: uuid.UUID,
    principal: VerifiedPrincipal,
    session: TransactionalSession,
    context: RequestCtx,
) -> AppointmentDetailResponse:
    appointment, slot, department, site = await BookingService(session).get_detail(
        appointment_id, patient_id=principal.patient_id, actor_role=principal.role
    )
    return AppointmentDetailResponse(
        appointment=_to_item(appointment, slot, department, site),
        meta=ResponseMeta(request_id=context.request_id, data_origin="SYNTHETIC"),
    )


@router.post(
    "/appointments/{appointment_id}/cancel",
    response_model=AppointmentDetailResponse,
    summary="Cancel an appointment",
    responses=_ERRORS,
)
async def cancel_appointment(
    appointment_id: uuid.UUID,
    payload: CancelRequest,
    principal: VerifiedPrincipal,
    session: TransactionalSession,
    context: RequestCtx,
) -> AppointmentDetailResponse:
    """Cancel rather than delete.

    The row stays, with a status and a timestamp: a deleted appointment is indistinguishable
    from one that never existed, and did-not-attend reporting depends on the difference.
    """
    service = BookingService(session)
    appointment = await service.cancel(
        appointment_id,
        patient_id=principal.patient_id,
        actor_user_id=principal.user_id,
        actor_role=principal.role,
        reason=payload.reason,
        context=context,
    )
    _, slot, department, site = await service.get_detail(
        appointment.id, patient_id=principal.patient_id, actor_role=principal.role
    )
    return AppointmentDetailResponse(
        appointment=_to_item(appointment, slot, department, site),
        meta=ResponseMeta(request_id=context.request_id, data_origin="SYNTHETIC"),
    )


@router.post(
    "/appointments/{appointment_id}/reschedule",
    response_model=BookingCreatedResponse,
    summary="Move an appointment to a different time",
    responses=_ERRORS,
)
async def reschedule_appointment(
    appointment_id: uuid.UUID,
    payload: RescheduleRequest,
    principal: VerifiedPrincipal,
    session: TransactionalSession,
    context: RequestCtx,
) -> BookingCreatedResponse:
    service = BookingService(session)
    replacement = await service.reschedule(
        appointment_id,
        new_slot_id=payload.new_slot_id,
        patient_id=principal.patient_id,
        actor_user_id=principal.user_id,
        actor_role=principal.role,
        context=context,
    )
    _, slot, department, site = await service.get_detail(
        replacement.id, patient_id=principal.patient_id, actor_role=principal.role
    )
    return BookingCreatedResponse(
        appointment=_to_item(replacement, slot, department, site),
        message="Your appointment has been moved.",
        kind="rescheduled",
    )
