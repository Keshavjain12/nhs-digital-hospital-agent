"""Symptom-check conversation service.

A scripted intake, not a generative assistant. Every reply is drawn from a fixed set of
strings in this module, so what the system can say to a patient is enumerable and
reviewable. When the Gen AI domain replaces this with an LLM, the safety rules below are
what that replacement has to keep.

Rules the conversation obeys:

- A red flag ends the intake immediately. No further questions, no appointment offered.
- The assistant never diagnoses, never says a clinician is unnecessary, and never states
  what a patient does or does not have.
- Every reply that carries a triage judgement says it came from an automated check and
  has not been seen by a clinician.
- Escalation is a state the patient is told about, not a silent flag.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import InvalidStateTransition, ResourceNotFound, ValidationFailed
from app.core.logging import get_logger
from app.models.base import UserRole
from app.models.chat import (
    ChatMessage,
    ChatRole,
    ChatSession,
    ChatSessionStatus,
    ChatStage,
    TriageResult,
)
from app.services.audit import AuditService
from app.services.auth import RequestContext
from app.services.triage import Severity, TriageAssessment, get_triage_engine

logger = get_logger(__name__)

MAX_MESSAGE_LENGTH = 1000
MAX_MESSAGES_PER_SESSION = 40


class AuditAction:
    CHAT_STARTED = "CHAT_STARTED"
    CHAT_ESCALATED = "CHAT_ESCALATED"
    TRIAGE_COMPLETED = "TRIAGE_COMPLETED"


# --- Fixed replies -------------------------------------------------------------
# Every string the assistant can say. Enumerable on purpose: "what can this tell a
# patient" must be answerable by reading one file.

OPENING = (
    "Hello. Tell me what has been happening, in your own words. "
    "I am an automated check, not a clinician."
)

ASK_DURATION = "Thank you. How long has this been going on?"

ASK_SEVERITY = "And how much is it affecting what you can do today?"

EMERGENCY_PREFIX = (
    "Based on what you have told me, you need emergency help now.\n\n"
    "Call 999, or go to your nearest A&E. Do not wait for an appointment and do not "
    "drive yourself."
)

ESCALATION_NOTICE = (
    "I have passed this conversation to a member of staff to look at. "
    "I have stopped asking questions."
)

CLOSING_TEMPLATE = (
    "Thank you. Based on what you have told me, {action}\n\n"
    "This is an automated suggestion to help you choose an appointment. It is not a "
    "diagnosis, and a clinician has not yet seen it."
)

SAFETY_FOOTER = (
    "If you feel worse at any point, call NHS 111, or 999 if it is an emergency. "
    "You do not need to wait for an appointment."
)


@dataclass(frozen=True, slots=True)
class ChatTurn:
    session: ChatSession
    messages: list[ChatMessage]
    triage: TriageResult | None


# --- PII redaction -------------------------------------------------------------
# Applied before anything derived from a message is logged. The message itself is stored
# intact - a clinician needs the patient's own words - but nothing derived from it carries
# identifiers outward.

_NHS_NUMBER = re.compile(r"\b\d{3}[ -]?\d{3}[ -]?\d{4}\b")
_PHONE = re.compile(r"\b(?:\+?44|0)\s?\d{4}[\s-]?\d{6}\b")
_EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")
_POSTCODE = re.compile(r"\b[A-Z]{1,2}\d[A-Z\d]?\s?\d[A-Z]{2}\b", re.IGNORECASE)


def redact_for_logging(text: str) -> str:
    """Strip direct identifiers from text before it is logged or summarised.

    Patients volunteer phone numbers and NHS numbers in free text constantly. This does not
    make the text anonymous - a description of symptoms can identify someone by itself -
    which is why the redacted form is only ever used for logs, never treated as safe to
    share more widely.
    """
    text = _EMAIL.sub("[email]", text)
    text = _NHS_NUMBER.sub("[nhs-number]", text)
    text = _PHONE.sub("[phone]", text)
    return _POSTCODE.sub("[postcode]", text)


class ChatService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self.audit = AuditService(session)
        self.engine = get_triage_engine()

    # --- Session lifecycle ----------------------------------------------------

    async def start(
        self, *, patient_id: uuid.UUID, actor_user_id: uuid.UUID, context: RequestContext
    ) -> ChatTurn:
        chat = ChatSession(
            patient_id=patient_id,
            status=ChatSessionStatus.ACTIVE,
            stage=ChatStage.AWAITING_SYMPTOMS.value,
        )
        self._session.add(chat)
        await self._session.flush()

        opening = self._add_message(chat, ChatRole.ASSISTANT, OPENING, produced_by="script")
        await self._session.flush()

        await self.audit.record(
            action=AuditAction.CHAT_STARTED,
            actor_user_id=actor_user_id,
            actor_role=UserRole.PATIENT,
            resource_type="ChatSession",
            resource_id=chat.id,
            request_id=context.request_id,
            ip_hash=context.ip_hash,
        )
        return ChatTurn(session=chat, messages=[opening], triage=None)

    async def get(self, session_id: uuid.UUID, *, patient_id: uuid.UUID) -> ChatTurn:
        chat = await self._load_own_session(session_id, patient_id)
        messages = await self._messages(chat.id)
        triage = await self._latest_triage(chat.id)
        return ChatTurn(session=chat, messages=messages, triage=triage)

    async def list_sessions(self, patient_id: uuid.UUID) -> list[ChatSession]:
        return list(
            (
                await self._session.execute(
                    select(ChatSession)
                    .where(ChatSession.patient_id == patient_id)
                    .order_by(ChatSession.started_at.desc())
                    .limit(20)
                )
            )
            .scalars()
            .all()
        )

    # --- The turn -------------------------------------------------------------

    async def send(
        self,
        session_id: uuid.UUID,
        text: str,
        *,
        patient_id: uuid.UUID,
        actor_user_id: uuid.UUID,
        context: RequestContext,
    ) -> ChatTurn:
        chat = await self._load_own_session(session_id, patient_id)

        if chat.status is not ChatSessionStatus.ACTIVE:
            raise InvalidStateTransition(
                "This conversation has ended. Start a new one if you need to."
            )

        cleaned = text.strip()
        if not cleaned:
            raise ValidationFailed("Type a message before sending.")
        if len(cleaned) > MAX_MESSAGE_LENGTH:
            raise ValidationFailed(f"Please keep messages under {MAX_MESSAGE_LENGTH} characters.")

        history = await self._messages(chat.id)
        if len(history) >= MAX_MESSAGES_PER_SESSION:
            # Bounded rather than open-ended: an intake that never concludes is a way of
            # never reaching a clinician.
            await self._escalate(chat, "conversation_length", actor_user_id, context)
            return await self.get(session_id, patient_id=patient_id)

        patient_message = self._add_message(chat, ChatRole.PATIENT, cleaned)
        await self._session.flush()

        patient_history = [m.content for m in history if m.role is ChatRole.PATIENT]
        assessment = self.engine.assess(cleaned, history=patient_history)

        patient_message.safety_flags = list(assessment.red_flags) or None

        if assessment.is_emergency:
            return await self._handle_emergency(
                chat, assessment, actor_user_id, context, patient_id
            )

        return await self._advance(chat, assessment, actor_user_id, context, patient_id)

    # --- Branches -------------------------------------------------------------

    async def _handle_emergency(
        self,
        chat: ChatSession,
        assessment: TriageAssessment,
        actor_user_id: uuid.UUID,
        context: RequestContext,
        patient_id: uuid.UUID,
    ) -> ChatTurn:
        """A red flag ends the intake.

        No follow-up question, no appointment. Continuing to ask about duration while
        someone describes a heart attack would be actively harmful.
        """
        reasons = " ".join(assessment.explanations)
        self._add_message(
            chat,
            ChatRole.ASSISTANT,
            f"{EMERGENCY_PREFIX}\n\n{reasons}",
            produced_by=f"{assessment.engine}@{assessment.engine_version}",
            safety_flags=list(assessment.red_flags),
        )
        self._add_message(chat, ChatRole.SYSTEM, ESCALATION_NOTICE, produced_by="script")

        triage = await self._record_triage(chat, assessment, patient_id)
        await self._escalate(chat, "red_flag", actor_user_id, context, flags=assessment.red_flags)

        return ChatTurn(session=chat, messages=await self._messages(chat.id), triage=triage)

    async def _advance(
        self,
        chat: ChatSession,
        assessment: TriageAssessment,
        actor_user_id: uuid.UUID,
        context: RequestContext,
        patient_id: uuid.UUID,
    ) -> ChatTurn:
        stage = ChatStage(chat.stage)

        if stage is ChatStage.AWAITING_SYMPTOMS:
            self._add_message(chat, ChatRole.ASSISTANT, ASK_DURATION, produced_by="script")
            chat.stage = ChatStage.AWAITING_DURATION.value
            triage = None

        elif stage is ChatStage.AWAITING_DURATION:
            self._add_message(chat, ChatRole.ASSISTANT, ASK_SEVERITY, produced_by="script")
            chat.stage = ChatStage.AWAITING_SEVERITY.value
            triage = None

        else:
            closing = CLOSING_TEMPLATE.format(action=assessment.recommended_action.lower())
            self._add_message(
                chat,
                ChatRole.ASSISTANT,
                f"{closing}\n\n{SAFETY_FOOTER}",
                produced_by=f"{assessment.engine}@{assessment.engine_version}",
            )
            chat.stage = ChatStage.FINISHED.value
            chat.status = ChatSessionStatus.COMPLETED
            chat.ended_at = datetime.now(UTC)
            triage = await self._record_triage(chat, assessment, patient_id)

            await self.audit.record(
                action=AuditAction.TRIAGE_COMPLETED,
                actor_user_id=actor_user_id,
                actor_role=UserRole.PATIENT,
                resource_type="TriageResult",
                resource_id=triage.id,
                request_id=context.request_id,
                ip_hash=context.ip_hash,
                # The band and the engine, never the symptoms.
                metadata={
                    "severity": assessment.severity.value,
                    "engine": assessment.engine,
                    "needsHumanReview": assessment.needs_human_review,
                },
            )

        await self._session.flush()
        return ChatTurn(session=chat, messages=await self._messages(chat.id), triage=triage)

    async def _escalate(
        self,
        chat: ChatSession,
        reason: str,
        actor_user_id: uuid.UUID,
        context: RequestContext,
        flags: tuple[str, ...] = (),
    ) -> None:
        chat.status = ChatSessionStatus.ESCALATED
        chat.stage = ChatStage.ESCALATED.value
        chat.escalated_at = datetime.now(UTC)
        chat.escalation_reason = reason
        await self._session.flush()

        await self.audit.record(
            action=AuditAction.CHAT_ESCALATED,
            actor_user_id=actor_user_id,
            actor_role=UserRole.PATIENT,
            resource_type="ChatSession",
            resource_id=chat.id,
            request_id=context.request_id,
            ip_hash=context.ip_hash,
            # Rule names, never the patient's words.
            metadata={"reason": reason, "redFlags": list(flags)},
        )
        logger.warning(
            "chat_escalated",
            extra={"request_id": context.request_id, "reason": reason},
        )

    # --- Helpers --------------------------------------------------------------

    def _add_message(
        self,
        chat: ChatSession,
        role: ChatRole,
        content: str,
        *,
        produced_by: str | None = None,
        safety_flags: list[str] | None = None,
    ) -> ChatMessage:
        message = ChatMessage(
            session_id=chat.id,
            role=role,
            content=content,
            produced_by=produced_by,
            safety_flags=safety_flags or None,
        )
        self._session.add(message)
        return message

    async def _record_triage(
        self, chat: ChatSession, assessment: TriageAssessment, patient_id: uuid.UUID
    ) -> TriageResult:
        result = TriageResult(
            patient_id=patient_id,
            session_id=chat.id,
            engine=assessment.engine,
            engine_version=assessment.engine_version,
            severity=assessment.severity.value,
            confidence=None,
            red_flags=list(assessment.red_flags) or None,
            contributing_factors=dict(assessment.contributing_factors),
            recommended_action=assessment.recommended_action,
        )
        self._session.add(result)
        await self._session.flush()
        return result

    async def _load_own_session(self, session_id: uuid.UUID, patient_id: uuid.UUID) -> ChatSession:
        chat = await self._session.get(ChatSession, session_id)
        # 404 rather than 403 when it belongs to someone else: a 403 would confirm the
        # conversation exists.
        if chat is None or chat.patient_id != patient_id:
            raise ResourceNotFound("That conversation could not be found.")
        return chat

    async def _messages(self, session_id: uuid.UUID) -> list[ChatMessage]:
        return list(
            (
                await self._session.execute(
                    select(ChatMessage)
                    .where(ChatMessage.session_id == session_id)
                    .order_by(ChatMessage.created_at, ChatMessage.id)
                )
            )
            .scalars()
            .all()
        )

    async def _latest_triage(self, session_id: uuid.UUID) -> TriageResult | None:
        return (
            await self._session.execute(
                select(TriageResult)
                .where(TriageResult.session_id == session_id)
                .order_by(TriageResult.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()


def bookable_window_days(severity: str) -> int | None:
    """How far ahead an appointment may be offered for a severity band.

    None for EMERGENCY: no appointment is ever offered for an emergency, and the caller
    must treat that as "do not show the booking flow" rather than "no limit".
    """
    from app.services.triage import BOOKABLE_WITHIN_DAYS

    try:
        return BOOKABLE_WITHIN_DAYS.get(Severity(severity))
    except ValueError:
        return None
