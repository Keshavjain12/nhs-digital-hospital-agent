"""Triage review schemas.

`engine_severity`, `clinician_severity` and `effective_severity` are three separate fields
on purpose. Collapsing them into one would lose exactly the distinction the whole review
workflow exists to preserve: what the system said, what the clinician decided, and which
one should drive care.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from pydantic import Field

from app.schemas.base import CamelModel, ResponseMeta


class TriageSummary(CamelModel):
    id: uuid.UUID
    #: What the engine produced. Immutable.
    engine_severity: str
    #: Set only when a clinician disagreed.
    clinician_severity: str | None
    #: The band that should drive care. Never recompute this in a client.
    effective_severity: str
    recommended_action: str
    red_flags: list[str] | None
    engine: str
    engine_version: str
    confidence: float | None
    review_status: str
    clinician_note: str | None
    reviewed_at: datetime | None
    created_at: datetime


class TriageQueueItemSchema(CamelModel):
    triage: TriageSummary
    patient_id: uuid.UUID
    patient_name: str
    patient_nhs_number: str | None


class TriageQueueResponse(CamelModel):
    items: list[TriageQueueItemSchema]
    meta: ResponseMeta


class TriageReviewRequest(CamelModel):
    #: True to confirm the engine's band, false to replace it.
    agrees: bool
    #: Required when disagreeing.
    clinician_severity: str | None = None
    note: Annotated[str, Field(max_length=1000)] | None = None


class TriageReviewResponse(CamelModel):
    triage: TriageSummary
    message: str
