"""Booking schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import Field

from app.schemas.base import CamelModel, ResponseMeta


class SlotItem(CamelModel):
    id: uuid.UUID
    starts_at: datetime
    ends_at: datetime
    slot_type: str
    department_id: uuid.UUID
    department_name: str
    site_name: str
    clinician_name: str | None


class SlotListResponse(CamelModel):
    items: list[SlotItem]
    meta: ResponseMeta


class DepartmentItem(CamelModel):
    id: uuid.UUID
    code: str
    name: str


class DepartmentListResponse(CamelModel):
    items: list[DepartmentItem]
    meta: ResponseMeta


class HoldResponse(CamelModel):
    slot_id: uuid.UUID
    expires_at: datetime
    # Seconds rather than only a timestamp: the UI counts down, and a countdown driven by
    # clock arithmetic across a client/server skew drifts.
    expires_in_seconds: int


class BookRequest(CamelModel):
    slot_id: uuid.UUID
    reason: Annotated[str, Field(max_length=500)] | None = None


class CancelRequest(CamelModel):
    reason: Annotated[str, Field(max_length=200)] | None = None


class RescheduleRequest(CamelModel):
    new_slot_id: uuid.UUID


class AppointmentItem(CamelModel):
    id: uuid.UUID
    reference: str
    status: str
    priority: str | None
    starts_at: datetime
    ends_at: datetime
    department_name: str
    site_name: str
    clinician_name: str | None
    reason_text: str | None
    is_cancellable: bool
    cancelled_at: datetime | None
    cancellation_reason: str | None


class AppointmentListResponse(CamelModel):
    items: list[AppointmentItem]
    meta: ResponseMeta


class AppointmentDetailResponse(CamelModel):
    appointment: AppointmentItem
    meta: ResponseMeta


class BookingCreatedResponse(CamelModel):
    appointment: AppointmentItem
    message: str
    kind: Literal["created", "rescheduled"] = "created"
