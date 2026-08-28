"""Symptom-check conversation routes.

Patient-scoped throughout: the session must belong to the caller, and a conversation
belonging to someone else returns 404 rather than 403, since a 403 would confirm it exists.

Clinical staff do not read conversations through these routes. Reaching a symptom-check
transcript is a patient-record access, and belongs behind the same care relationship and
audit trail as the rest of the record.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, status

from app.core.deps import (
    RequestCtx,
    RequirePatient,
    TransactionalSession,
    authenticated_rate_limit,
)
from app.core.errors import AuthenticationRequired, ErrorResponse
from app.models.chat import ChatMessage, ChatSession, ChatSessionStatus, TriageResult
from app.schemas.base import ResponseMeta
from app.schemas.chat import (
    ChatMessageItem,
    ChatSessionItem,
    ChatSessionListResponse,
    ChatTurnResponse,
    SendMessageRequest,
    TriageResultItem,
)
from app.services.chat import ChatService, ChatTurn, bookable_window_days

router = APIRouter(
    prefix="/chat", tags=["Symptom check"], dependencies=[Depends(authenticated_rate_limit)]
)

_ERRORS: dict[int | str, dict[str, object]] = {
    401: {"model": ErrorResponse, "description": "Not signed in"},
    403: {"model": ErrorResponse, "description": "Not permitted"},
    404: {"model": ErrorResponse, "description": "Not found"},
    409: {"model": ErrorResponse, "description": "Conversation has ended"},
}


def _session_item(chat: ChatSession) -> ChatSessionItem:
    return ChatSessionItem(
        id=chat.id,
        status=chat.status.value,
        stage=chat.stage,
        escalated_at=chat.escalated_at,
        escalation_reason=chat.escalation_reason,
        started_at=chat.started_at,
        ended_at=chat.ended_at,
    )


def _message_item(message: ChatMessage) -> ChatMessageItem:
    return ChatMessageItem(
        id=message.id,
        role=message.role.value,
        content=message.content,
        produced_by=message.produced_by,
        safety_flags=message.safety_flags,
        created_at=message.created_at,
    )


def _triage_item(result: TriageResult | None) -> TriageResultItem | None:
    if result is None:
        return None
    return TriageResultItem(
        id=result.id,
        severity=result.severity,
        recommended_action=result.recommended_action,
        red_flags=result.red_flags,
        engine=result.engine,
        engine_version=result.engine_version,
        confidence=float(result.confidence) if result.confidence is not None else None,
        review_status=result.review_status.value,
        bookable_within_days=bookable_window_days(result.severity),
        created_at=result.created_at,
    )


def _turn(turn: ChatTurn, request_id: str | None) -> ChatTurnResponse:
    return ChatTurnResponse(
        session=_session_item(turn.session),
        messages=[_message_item(m) for m in turn.messages],
        triage=_triage_item(turn.triage),
        is_closed=turn.session.status is not ChatSessionStatus.ACTIVE,
        # USER_ENTERED, not SYNTHETIC: this is text a real person typed about themselves,
        # even in a demo environment.
        meta=ResponseMeta(request_id=request_id, data_origin="USER_ENTERED"),
    )


@router.post(
    "/sessions",
    response_model=ChatTurnResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Start a symptom check",
    responses=_ERRORS,
)
async def start_session(
    principal: RequirePatient, session: TransactionalSession, context: RequestCtx
) -> ChatTurnResponse:
    if principal.patient_id is None:
        raise AuthenticationRequired()

    turn = await ChatService(session).start(
        patient_id=principal.patient_id, actor_user_id=principal.user_id, context=context
    )
    return _turn(turn, context.request_id)


@router.get(
    "/sessions",
    response_model=ChatSessionListResponse,
    summary="Your previous symptom checks",
    responses=_ERRORS,
)
async def list_sessions(
    principal: RequirePatient, session: TransactionalSession, context: RequestCtx
) -> ChatSessionListResponse:
    if principal.patient_id is None:
        raise AuthenticationRequired()

    sessions = await ChatService(session).list_sessions(principal.patient_id)
    return ChatSessionListResponse(
        items=[_session_item(s) for s in sessions],
        meta=ResponseMeta(request_id=context.request_id, data_origin="USER_ENTERED"),
    )


@router.get(
    "/sessions/{session_id}",
    response_model=ChatTurnResponse,
    summary="Read one conversation",
    responses=_ERRORS,
)
async def get_session(
    session_id: uuid.UUID,
    principal: RequirePatient,
    session: TransactionalSession,
    context: RequestCtx,
) -> ChatTurnResponse:
    if principal.patient_id is None:
        raise AuthenticationRequired()

    turn = await ChatService(session).get(session_id, patient_id=principal.patient_id)
    return _turn(turn, context.request_id)


@router.post(
    "/sessions/{session_id}/messages",
    response_model=ChatTurnResponse,
    summary="Send a message",
    responses=_ERRORS,
)
async def send_message(
    session_id: uuid.UUID,
    payload: SendMessageRequest,
    principal: RequirePatient,
    session: TransactionalSession,
    context: RequestCtx,
) -> ChatTurnResponse:
    if principal.patient_id is None:
        raise AuthenticationRequired()

    turn = await ChatService(session).send(
        session_id,
        payload.content,
        patient_id=principal.patient_id,
        actor_user_id=principal.user_id,
        context=context,
    )
    return _turn(turn, context.request_id)
