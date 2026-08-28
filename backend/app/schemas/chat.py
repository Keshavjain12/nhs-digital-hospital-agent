"""Chat and triage wire schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from pydantic import Field

from app.schemas.base import CamelModel, ResponseMeta


class ChatMessageItem(CamelModel):
    id: uuid.UUID
    role: str
    content: str
    #: What produced an assistant turn - "script", or "rules@0.3.0". Surfaced so the UI can
    #: label machine-generated content rather than letting it read as a person.
    produced_by: str | None
    safety_flags: list[str] | None
    created_at: datetime


class TriageResultItem(CamelModel):
    id: uuid.UUID
    severity: str
    recommended_action: str
    red_flags: list[str] | None
    engine: str
    engine_version: str
    #: Always null for the rule engine. Present in the contract so a future model can
    #: populate it without a breaking change.
    confidence: float | None
    review_status: str
    #: How far ahead an appointment may be offered. Null for an emergency, where the UI
    #: must not show booking at all.
    bookable_within_days: int | None
    created_at: datetime


class ChatSessionItem(CamelModel):
    id: uuid.UUID
    status: str
    stage: str
    escalated_at: datetime | None
    escalation_reason: str | None
    started_at: datetime
    ended_at: datetime | None


class ChatTurnResponse(CamelModel):
    session: ChatSessionItem
    messages: list[ChatMessageItem]
    triage: TriageResultItem | None
    #: True when the conversation has stopped and the patient should not keep typing.
    is_closed: bool
    meta: ResponseMeta


class SendMessageRequest(CamelModel):
    content: Annotated[str, Field(min_length=1, max_length=1000)]


class ChatSessionListResponse(CamelModel):
    items: list[ChatSessionItem]
    meta: ResponseMeta
