"""Chat and triage models.

`chat_messages.content` is the most sensitive free text in the system: a patient describing
their own health in their own words. It lives here and nowhere else - never copied into the
audit log, never into application logs.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, Numeric, String, Text, text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.dialects.postgresql import ENUM as PgEnum
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.base import UUIDPrimaryKeyMixin


class ChatSessionStatus(StrEnum):
    ACTIVE = "ACTIVE"
    ESCALATED = "ESCALATED"
    COMPLETED = "COMPLETED"
    CLOSED = "CLOSED"


class ChatRole(StrEnum):
    PATIENT = "PATIENT"
    ASSISTANT = "ASSISTANT"
    SYSTEM = "SYSTEM"


class TriageReviewStatus(StrEnum):
    PENDING_REVIEW = "PENDING_REVIEW"
    CLINICIAN_CONFIRMED = "CLINICIAN_CONFIRMED"
    CLINICIAN_OVERRIDDEN = "CLINICIAN_OVERRIDDEN"


class ChatStage(StrEnum):
    """Where the scripted intake has reached.

    Stored rather than inferred from the messages, so changing the script cannot
    reinterpret a conversation already in progress.
    """

    OPENING = "OPENING"
    AWAITING_SYMPTOMS = "AWAITING_SYMPTOMS"
    AWAITING_DURATION = "AWAITING_DURATION"
    AWAITING_SEVERITY = "AWAITING_SEVERITY"
    FINISHED = "FINISHED"
    ESCALATED = "ESCALATED"


def _enum(enum_cls: type[StrEnum], name: str) -> PgEnum:
    return PgEnum(
        enum_cls,
        name=name,
        schema="ai",
        create_type=False,
        values_callable=lambda e: [m.value for m in e],
    )


severity_enum = PgEnum(
    "EMERGENCY",
    "URGENT",
    "SOON",
    "ROUTINE",
    "SELF_CARE",
    name="triage_severity",
    schema="ai",
    create_type=False,
)


class ChatSession(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "chat_sessions"
    __table_args__ = (
        Index("ix_chat_sessions_patient", "patient_id", "started_at"),
        {"schema": "ai"},
    )

    patient_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("clinical.patients.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[ChatSessionStatus] = mapped_column(
        _enum(ChatSessionStatus, "chat_session_status"),
        nullable=False,
        server_default=ChatSessionStatus.ACTIVE.value,
    )
    locale: Mapped[str] = mapped_column(String(10), nullable=False, server_default="en-GB")
    stage: Mapped[str] = mapped_column(String(40), nullable=False, server_default="OPENING")
    escalated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    escalation_reason: Mapped[str | None] = mapped_column(String(200))
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ChatMessage(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "chat_messages"
    __table_args__ = (
        Index("ix_chat_messages_session", "session_id", "created_at"),
        {"schema": "ai"},
    )

    session_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("ai.chat_sessions.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[ChatRole] = mapped_column(_enum(ChatRole, "chat_role"), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    produced_by: Mapped[str | None] = mapped_column(String(60))
    safety_flags: Mapped[list[str] | None] = mapped_column(ARRAY(String(60)))
    # clock_timestamp(), not now() - see migration 003. Transcript order depends on it.
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("clock_timestamp()"), nullable=False
    )


class TriageResult(UUIDPrimaryKeyMixin, Base):
    """The engine's output, plus any clinician decision about it.

    `severity` is what the engine said and is immutable by database trigger. A clinician
    disagreeing writes `clinician_severity`; the original is never rewritten, so "what did
    the system say, and what did the clinician decide" stays answerable.
    """

    __tablename__ = "triage_results"
    __table_args__ = (
        Index("ix_triage_patient", "patient_id", "created_at"),
        {"schema": "ai"},
    )

    patient_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("clinical.patients.id", ondelete="CASCADE"), nullable=False
    )
    session_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("ai.chat_sessions.id", ondelete="SET NULL")
    )
    engine: Mapped[str] = mapped_column(String(40), nullable=False)
    engine_version: Mapped[str] = mapped_column(String(20), nullable=False)
    severity: Mapped[str] = mapped_column(severity_enum, nullable=False)
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(4, 3))
    red_flags: Mapped[list[str] | None] = mapped_column(ARRAY(String(60)))
    contributing_factors: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    recommended_action: Mapped[str] = mapped_column(Text, nullable=False)
    review_status: Mapped[TriageReviewStatus] = mapped_column(
        _enum(TriageReviewStatus, "triage_review_status"),
        nullable=False,
        server_default=TriageReviewStatus.PENDING_REVIEW.value,
    )
    reviewed_by_staff_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("identity.staff.id")
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    clinician_severity: Mapped[str | None] = mapped_column(severity_enum)
    clinician_note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )
