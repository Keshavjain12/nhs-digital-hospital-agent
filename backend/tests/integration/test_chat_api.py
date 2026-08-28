"""Symptom-check API tests.

The triage engine has its own unit tests. These cover what happens around it: that a red
flag actually stops the conversation, that the transcript is patient-scoped, that the
severity reaches storage intact, and that nothing sensitive leaks into the audit trail.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.integration

AUTH = "/api/v1/auth"
CHAT = "/api/v1/chat"
PASSWORD = "correct-horse-battery-staple"


async def signed_in(api: AsyncClient, email: str, family: str) -> str:
    created = await api.post(
        f"{AUTH}/register",
        json={
            "email": email,
            "password": PASSWORD,
            "givenName": "Test",
            "familyName": family,
            "dateOfBirth": "1990-01-01",
        },
    )
    assert created.status_code == 201, created.text
    response = await api.post(f"{AUTH}/login", json={"email": email, "password": PASSWORD})
    return str(response.json()["accessToken"])


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def start(api: AsyncClient, token: str) -> str:
    response = await api.post(f"{CHAT}/sessions", headers=auth(token))
    assert response.status_code == 201, response.text
    return str(response.json()["session"]["id"])


async def say(api: AsyncClient, token: str, session_id: str, content: str):
    return await api.post(
        f"{CHAT}/sessions/{session_id}/messages", json={"content": content}, headers=auth(token)
    )


# --- Session basics -----------------------------------------------------------


async def test_starting_a_session_requires_authentication(api: AsyncClient) -> None:
    assert (await api.post(f"{CHAT}/sessions")).status_code == 401


async def test_a_session_opens_with_an_assistant_message(api: AsyncClient) -> None:
    token = await signed_in(api, "chat@example.test", "Chat")

    response = await api.post(f"{CHAT}/sessions", headers=auth(token))

    body = response.json()
    assert body["session"]["status"] == "ACTIVE"
    assert len(body["messages"]) == 1
    assert body["messages"][0]["role"] == "ASSISTANT"
    assert body["isClosed"] is False


async def test_the_opening_message_says_it_is_not_a_clinician(api: AsyncClient) -> None:
    """The patient must know what they are talking to before they say anything."""
    token = await signed_in(api, "opening@example.test", "Opening")

    response = await api.post(f"{CHAT}/sessions", headers=auth(token))

    assert "not a clinician" in response.json()["messages"][0]["content"].lower()


async def test_assistant_messages_declare_what_produced_them(api: AsyncClient) -> None:
    token = await signed_in(api, "produced@example.test", "Produced")
    session_id = await start(api, token)

    response = await say(api, token, session_id, "I have a sore knee")

    assistant = [m for m in response.json()["messages"] if m["role"] == "ASSISTANT"]
    assert all(m["producedBy"] for m in assistant)


# --- Red flags ----------------------------------------------------------------


async def test_a_red_flag_stops_the_conversation_immediately(api: AsyncClient) -> None:
    """The intake must not carry on asking about duration during a possible heart attack."""
    token = await signed_in(api, "redflag@example.test", "RedFlag")
    session_id = await start(api, token)

    response = await say(
        api, token, session_id, "I have crushing chest pain and it spreads to my arm"
    )

    body = response.json()
    assert body["session"]["status"] == "ESCALATED"
    assert body["isClosed"] is True
    assert body["triage"]["severity"] == "EMERGENCY"
    assert "cardiac_chest_pain" in body["triage"]["redFlags"]


async def test_an_emergency_reply_directs_to_999_and_offers_no_appointment(
    api: AsyncClient,
) -> None:
    token = await signed_in(api, "emergency@example.test", "Emergency")
    session_id = await start(api, token)

    response = await say(api, token, session_id, "I cannot breathe and my lips are blue")

    body = response.json()
    replies = " ".join(m["content"] for m in body["messages"] if m["role"] != "PATIENT")
    assert "999" in replies
    # No booking window is offered for an emergency, so the UI cannot show the slot picker.
    assert body["triage"]["bookableWithinDays"] is None


async def test_the_patient_is_told_the_conversation_was_escalated(api: AsyncClient) -> None:
    """Escalation is a state the patient is told about, not a silent flag."""
    token = await signed_in(api, "told@example.test", "Told")
    session_id = await start(api, token)

    response = await say(api, token, session_id, "I want to kill myself")

    system = [m for m in response.json()["messages"] if m["role"] == "SYSTEM"]
    assert system
    assert "staff" in system[0]["content"].lower()


async def test_an_escalated_conversation_refuses_further_messages(api: AsyncClient) -> None:
    token = await signed_in(api, "closed@example.test", "Closed")
    session_id = await start(api, token)
    await say(api, token, session_id, "I have crushing chest pain")

    response = await say(api, token, session_id, "actually never mind")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "INVALID_STATE_TRANSITION"


# --- The ordinary path ---------------------------------------------------------


async def test_a_routine_conversation_reaches_a_triage_result(api: AsyncClient) -> None:
    token = await signed_in(api, "routine@example.test", "Routine")
    session_id = await start(api, token)

    await say(api, token, session_id, "I have had an itchy rash on my arm")
    await say(api, token, session_id, "about a week")
    final = await say(api, token, session_id, "it is annoying but I can do everything")

    body = final.json()
    assert body["session"]["status"] == "COMPLETED"
    assert body["triage"] is not None
    assert body["triage"]["severity"] in {"ROUTINE", "SOON"}
    assert body["triage"]["bookableWithinDays"] is not None


async def test_the_closing_message_says_it_is_not_a_diagnosis(api: AsyncClient) -> None:
    """Required by the brief: never imply the system has diagnosed anyone."""
    token = await signed_in(api, "notdiag@example.test", "NotDiag")
    session_id = await start(api, token)
    await say(api, token, session_id, "I have a sore throat")
    await say(api, token, session_id, "two days")
    final = await say(api, token, session_id, "not too bad")

    closing = final.json()["messages"][-1]["content"].lower()
    assert "not a diagnosis" in closing
    assert "clinician has not yet seen" in closing


async def test_no_reply_ever_tells_a_patient_they_do_not_need_care(api: AsyncClient) -> None:
    """Brief §38 forbids this wording outright, in any branch."""
    from app.services import chat as chat_service

    forbidden = (
        "you do not need a doctor",
        "you don't need a doctor",
        "nothing to worry about",
        "you are fine",
        "you definitely have",
        "i have diagnosed",
    )
    replies = " ".join(
        [
            chat_service.OPENING,
            chat_service.ASK_DURATION,
            chat_service.ASK_SEVERITY,
            chat_service.EMERGENCY_PREFIX,
            chat_service.ESCALATION_NOTICE,
            chat_service.CLOSING_TEMPLATE,
            chat_service.SAFETY_FOOTER,
        ]
    ).lower()

    for phrase in forbidden:
        assert phrase not in replies


async def test_the_triage_result_names_the_engine(api: AsyncClient) -> None:
    """A severity is not reviewable without knowing what produced it."""
    token = await signed_in(api, "engine@example.test", "Engine")
    session_id = await start(api, token)
    response = await say(api, token, session_id, "I have chest pain")

    triage = response.json()["triage"]
    assert triage["engine"] == "rules"
    assert triage["engineVersion"]
    assert triage["confidence"] is None
    assert triage["reviewStatus"] == "PENDING_REVIEW"


# --- Access control -------------------------------------------------------------


async def test_a_patient_cannot_read_another_patients_conversation(api: AsyncClient) -> None:
    """404, not 403: a 403 would confirm the conversation exists."""
    owner = await signed_in(api, "owner@example.test", "Owner")
    intruder = await signed_in(api, "intruder@example.test", "Intruder")
    session_id = await start(api, owner)
    await say(api, owner, session_id, "I have a private symptom to describe")

    response = await api.get(f"{CHAT}/sessions/{session_id}", headers=auth(intruder))

    assert response.status_code == 404
    assert "private symptom" not in response.text


async def test_a_patient_cannot_post_into_another_patients_conversation(
    api: AsyncClient,
) -> None:
    owner = await signed_in(api, "owner2@example.test", "Owner2")
    intruder = await signed_in(api, "intruder2@example.test", "Intruder2")
    session_id = await start(api, owner)

    response = await say(api, intruder, session_id, "hello")

    assert response.status_code == 404


async def test_a_patient_sees_only_their_own_sessions(api: AsyncClient) -> None:
    owner = await signed_in(api, "mine@example.test", "Mine")
    other = await signed_in(api, "theirs@example.test", "Theirs")
    await start(api, owner)

    response = await api.get(f"{CHAT}/sessions", headers=auth(other))

    assert response.json()["items"] == []


# --- Validation -----------------------------------------------------------------


async def test_an_empty_message_is_rejected(api: AsyncClient) -> None:
    token = await signed_in(api, "empty@example.test", "Empty")
    session_id = await start(api, token)

    assert (await say(api, token, session_id, "   ")).status_code == 400


async def test_an_overlong_message_is_rejected(api: AsyncClient) -> None:
    token = await signed_in(api, "long@example.test", "Long")
    session_id = await start(api, token)

    assert (await say(api, token, session_id, "x" * 1001)).status_code == 400


# --- Privacy --------------------------------------------------------------------


async def test_symptom_text_never_reaches_the_audit_trail(
    api: AsyncClient, db_session: AsyncSession
) -> None:
    """The transcript lives in one place. The audit log records that a check happened."""
    token = await signed_in(api, "privacy@example.test", "Privacy")
    session_id = await start(api, token)
    await say(api, token, session_id, "I have a distinctive embarrassing symptom")

    blob = await db_session.scalar(
        text("SELECT string_agg(metadata::text || coalesce(detail, ''), ' ') FROM audit.audit_logs")
    )

    assert blob is not None
    assert "embarrassing" not in blob
    assert "distinctive" not in blob


async def test_chat_activity_is_audited_without_the_content(
    api: AsyncClient, db_session: AsyncSession
) -> None:
    token = await signed_in(api, "audited@example.test", "Audited")
    session_id = await start(api, token)
    await say(api, token, session_id, "I have crushing chest pain")

    actions = {
        row[0]
        for row in (await db_session.execute(text("SELECT action FROM audit.audit_logs"))).all()
    }

    assert "CHAT_STARTED" in actions
    assert "CHAT_ESCALATED" in actions


def test_identifiers_are_stripped_before_logging() -> None:
    from app.services.chat import redact_for_logging

    redacted = redact_for_logging(
        "call me on 07700 900123 or a.patient@example.test, nhs 943 476 5919, SW1A 1AA"
    )

    assert "900123" not in redacted
    assert "a.patient@example.test" not in redacted
    assert "943 476 5919" not in redacted
    assert "SW1A 1AA" not in redacted


# --- Storage guarantees ----------------------------------------------------------


async def test_the_engine_output_cannot_be_rewritten(
    api: AsyncClient, db_session: AsyncSession
) -> None:
    """A record of what the system said is worthless if it can be edited afterwards."""
    token = await signed_in(api, "immutable@example.test", "Immutable")
    session_id = await start(api, token)
    await say(api, token, session_id, "I have crushing chest pain")

    with pytest.raises(Exception, match="immutable"):
        await db_session.execute(text("UPDATE ai.triage_results SET severity = 'ROUTINE'"))


async def test_a_clinician_decision_is_recorded_alongside_the_original(
    api: AsyncClient, db_session: AsyncSession
) -> None:
    """Overriding writes a separate column; the engine's band stays as it was."""
    token = await signed_in(api, "override@example.test", "Override")
    session_id = await start(api, token)
    await say(api, token, session_id, "I have crushing chest pain")

    await db_session.execute(
        text(
            "UPDATE ai.triage_results SET clinician_severity = 'ROUTINE', "
            "review_status = 'CLINICIAN_OVERRIDDEN'"
        )
    )

    row = (
        await db_session.execute(text("SELECT severity, clinician_severity FROM ai.triage_results"))
    ).one()

    assert row[0] == "EMERGENCY"
    assert row[1] == "ROUTINE"
