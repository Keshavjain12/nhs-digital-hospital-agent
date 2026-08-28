"""Clinician review of triage output.

The property under test throughout: the engine's band and the clinician's decision are
kept separately. Losing that would destroy both the clinical record of what happened and
the only honest measure of how the engine performs.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.integration

AUTH = "/api/v1/auth"
CHAT = "/api/v1/chat"
TRIAGE = "/api/v1/triage"
PASSWORD = "correct-horse-battery-staple"


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def patient_with_triage(api: AsyncClient, email: str, message: str) -> str:
    """Register a patient, run a symptom check, return the triage result id."""
    await api.post(
        f"{AUTH}/register",
        json={
            "email": email,
            "password": PASSWORD,
            "givenName": "Test",
            "familyName": "Triage",
            "dateOfBirth": "1990-01-01",
        },
    )
    token = (await api.post(f"{AUTH}/login", json={"email": email, "password": PASSWORD})).json()[
        "accessToken"
    ]
    session_id = (await api.post(f"{CHAT}/sessions", headers=auth(token))).json()["session"]["id"]

    turn = await api.post(
        f"{CHAT}/sessions/{session_id}/messages", json={"content": message}, headers=auth(token)
    )
    # A red flag produces a result on the first turn and ends the conversation. Anything
    # else has to complete the three-step intake first, which is the behaviour under test
    # elsewhere - so the helper follows it rather than assuming one message is enough.
    for follow_up in ("a few days", "manageable but annoying"):
        if turn.json().get("triage"):
            break
        turn = await api.post(
            f"{CHAT}/sessions/{session_id}/messages",
            json={"content": follow_up},
            headers=auth(token),
        )

    triage = turn.json().get("triage")
    assert triage is not None, f"expected a triage result for {message!r}"
    return str(triage["id"])


async def make_staff(db_session: AsyncSession, email: str, role: str, code: str) -> str:
    from app.core.security import hash_password

    await db_session.execute(
        text(
            "INSERT INTO identity.users (email, password_hash, role, status) "
            "VALUES (:e, :h, :r, 'ACTIVE')"
        ),
        {"e": email, "h": hash_password(PASSWORD), "r": role},
    )
    await db_session.execute(
        text(
            "INSERT INTO identity.staff (user_id, staff_code, given_name, family_name, job_title) "
            "SELECT id, :c, 'Test', :c, 'Clinician' FROM identity.users WHERE email = :e"
        ),
        {"e": email, "c": code},
    )
    await db_session.flush()
    return email


async def staff_token(api: AsyncClient, email: str) -> str:
    response = await api.post(f"{AUTH}/login", json={"email": email, "password": PASSWORD})
    return str(response.json()["accessToken"])


# --- Access control ------------------------------------------------------------


async def test_the_queue_requires_authentication(api: AsyncClient) -> None:
    assert (await api.get(TRIAGE)).status_code == 401


async def test_a_patient_cannot_read_the_triage_queue(api: AsyncClient) -> None:
    await patient_with_triage(api, "nosy@example.test", "I have a cough")
    token = (
        await api.post(f"{AUTH}/login", json={"email": "nosy@example.test", "password": PASSWORD})
    ).json()["accessToken"]

    assert (await api.get(TRIAGE, headers=auth(token))).status_code == 403


async def test_an_administrator_cannot_read_the_triage_queue(
    api: AsyncClient, db_session: AsyncSession
) -> None:
    """A triage band is clinical content, so the admin exclusion applies here too."""
    await make_staff(db_session, "ops@example.test", "ADMIN", "ADM9")
    token = await staff_token(api, "ops@example.test")

    response = await api.get(TRIAGE, headers=auth(token))

    assert response.status_code == 403
    # The refusal explains that this is deliberate. A bare "you do not have permission"
    # reads as a misconfiguration and gets reported as a bug.
    message = response.json()["error"]["message"].lower()
    assert "administrator" in message
    assert "by design" in message


async def test_a_clinician_can_read_the_queue(api: AsyncClient, db_session: AsyncSession) -> None:
    await patient_with_triage(api, "seen@example.test", "I have crushing chest pain")
    await make_staff(db_session, "doc@example.test", "DOCTOR", "DOC9")
    token = await staff_token(api, "doc@example.test")

    response = await api.get(TRIAGE, headers=auth(token))

    assert response.status_code == 200
    assert response.json()["items"]


# --- Ordering -------------------------------------------------------------------


async def test_the_queue_is_ordered_most_urgent_first(
    api: AsyncClient, db_session: AsyncSession
) -> None:
    """A routine result arriving later must not sit above an emergency."""
    await patient_with_triage(api, "routine@example.test", "I have an itchy rash")
    await patient_with_triage(api, "urgent@example.test", "I cannot breathe")
    await make_staff(db_session, "doc2@example.test", "DOCTOR", "DOC10")
    token = await staff_token(api, "doc2@example.test")

    items = (await api.get(TRIAGE, headers=auth(token))).json()["items"]
    bands = [i["triage"]["engineSeverity"] for i in items]

    assert bands[0] == "EMERGENCY"


# --- Review ---------------------------------------------------------------------


async def test_confirming_records_the_clinician_agreed(
    api: AsyncClient, db_session: AsyncSession
) -> None:
    result_id = await patient_with_triage(api, "confirm@example.test", "I have chest pain")
    await make_staff(db_session, "doc3@example.test", "DOCTOR", "DOC11")
    token = await staff_token(api, "doc3@example.test")

    response = await api.post(
        f"{TRIAGE}/{result_id}/review", json={"agrees": True}, headers=auth(token)
    )

    assert response.status_code == 200
    triage = response.json()["triage"]
    assert triage["reviewStatus"] == "CLINICIAN_CONFIRMED"
    assert triage["engineSeverity"] == "EMERGENCY"
    assert triage["clinicianSeverity"] is None
    assert triage["effectiveSeverity"] == "EMERGENCY"


async def test_an_override_keeps_the_engine_band_alongside(
    api: AsyncClient, db_session: AsyncSession
) -> None:
    """The headline guarantee of this module."""
    result_id = await patient_with_triage(api, "override@example.test", "I have chest pain")
    await make_staff(db_session, "doc4@example.test", "DOCTOR", "DOC12")
    token = await staff_token(api, "doc4@example.test")

    response = await api.post(
        f"{TRIAGE}/{result_id}/review",
        json={
            "agrees": False,
            "clinicianSeverity": "SOON",
            "note": "Pain reproducible on palpation, not cardiac in nature",
        },
        headers=auth(token),
    )

    triage = response.json()["triage"]
    assert triage["engineSeverity"] == "EMERGENCY", "the engine band must never be rewritten"
    assert triage["clinicianSeverity"] == "SOON"
    assert triage["effectiveSeverity"] == "SOON", "care follows the clinician"
    assert triage["reviewStatus"] == "CLINICIAN_OVERRIDDEN"


async def test_an_override_without_a_reason_is_refused(
    api: AsyncClient, db_session: AsyncSession
) -> None:
    """An override with no reason is unreviewable, and is exactly what an incident needs."""
    result_id = await patient_with_triage(api, "noreason@example.test", "I have chest pain")
    await make_staff(db_session, "doc5@example.test", "DOCTOR", "DOC13")
    token = await staff_token(api, "doc5@example.test")

    response = await api.post(
        f"{TRIAGE}/{result_id}/review",
        json={"agrees": False, "clinicianSeverity": "ROUTINE"},
        headers=auth(token),
    )

    assert response.status_code == 400


async def test_an_override_without_a_band_is_refused(
    api: AsyncClient, db_session: AsyncSession
) -> None:
    result_id = await patient_with_triage(api, "noband@example.test", "I have chest pain")
    await make_staff(db_session, "doc6@example.test", "DOCTOR", "DOC14")
    token = await staff_token(api, "doc6@example.test")

    response = await api.post(
        f"{TRIAGE}/{result_id}/review",
        json={"agrees": False, "note": "I disagree with this assessment"},
        headers=auth(token),
    )

    assert response.status_code == 400


async def test_an_invalid_band_is_refused(api: AsyncClient, db_session: AsyncSession) -> None:
    result_id = await patient_with_triage(api, "badband@example.test", "I have chest pain")
    await make_staff(db_session, "doc7@example.test", "DOCTOR", "DOC15")
    token = await staff_token(api, "doc7@example.test")

    response = await api.post(
        f"{TRIAGE}/{result_id}/review",
        json={"agrees": False, "clinicianSeverity": "NOT_A_BAND", "note": "some reason here"},
        headers=auth(token),
    )

    assert response.status_code == 400


async def test_reviewing_twice_is_refused(api: AsyncClient, db_session: AsyncSession) -> None:
    result_id = await patient_with_triage(api, "twice@example.test", "I have chest pain")
    await make_staff(db_session, "doc8@example.test", "DOCTOR", "DOC16")
    token = await staff_token(api, "doc8@example.test")
    await api.post(f"{TRIAGE}/{result_id}/review", json={"agrees": True}, headers=auth(token))

    response = await api.post(
        f"{TRIAGE}/{result_id}/review", json={"agrees": True}, headers=auth(token)
    )

    assert response.status_code == 400


async def test_a_patient_cannot_review_their_own_triage(api: AsyncClient) -> None:
    """Otherwise a patient could mark their own emergency as routine."""
    result_id = await patient_with_triage(api, "self@example.test", "I have chest pain")
    token = (
        await api.post(f"{AUTH}/login", json={"email": "self@example.test", "password": PASSWORD})
    ).json()["accessToken"]

    response = await api.post(
        f"{TRIAGE}/{result_id}/review", json={"agrees": True}, headers=auth(token)
    )

    assert response.status_code == 403


# --- Surfacing in the patient list ------------------------------------------------


async def test_the_patient_list_carries_the_latest_band(
    api: AsyncClient, db_session: AsyncSession
) -> None:
    await patient_with_triage(api, "listed@example.test", "I have crushing chest pain")
    await make_staff(db_session, "doc9@example.test", "DOCTOR", "DOC17")
    token = await staff_token(api, "doc9@example.test")

    items = (await api.get("/api/v1/patients?pageSize=100", headers=auth(token))).json()["items"]
    with_triage = [i for i in items if i["latestTriage"]]

    assert with_triage
    assert with_triage[0]["latestTriage"]["effectiveSeverity"] == "EMERGENCY"


async def test_a_patient_without_a_check_has_no_band(
    api: AsyncClient, db_session: AsyncSession
) -> None:
    """Null is a real state - most patients have not done a symptom check.

    It must not be rendered as a default band, which would invent a clinical judgement.
    """
    await api.post(
        f"{AUTH}/register",
        json={
            "email": "nocheck@example.test",
            "password": PASSWORD,
            "givenName": "No",
            "familyName": "Check",
            "dateOfBirth": "1990-01-01",
        },
    )
    await make_staff(db_session, "doc10@example.test", "DOCTOR", "DOC18")
    token = await staff_token(api, "doc10@example.test")

    items = (await api.get("/api/v1/patients?pageSize=100", headers=auth(token))).json()["items"]
    match = next(i for i in items if i["familyName"] == "Check")

    assert match["latestTriage"] is None


# --- Audit -------------------------------------------------------------------------


async def test_an_override_is_audited_without_the_clinical_note(
    api: AsyncClient, db_session: AsyncSession
) -> None:
    result_id = await patient_with_triage(api, "audited@example.test", "I have chest pain")
    await make_staff(db_session, "doc11@example.test", "DOCTOR", "DOC19")
    token = await staff_token(api, "doc11@example.test")

    await api.post(
        f"{TRIAGE}/{result_id}/review",
        json={
            "agrees": False,
            "clinicianSeverity": "ROUTINE",
            "note": "Distinctive clinical reasoning here",
        },
        headers=auth(token),
    )

    rows = (
        await db_session.execute(
            text(
                "SELECT action, metadata::text FROM audit.audit_logs "
                "WHERE action = 'TRIAGE_OVERRIDDEN'"
            )
        )
    ).all()

    assert rows, "an override must be audited"
    blob = " ".join(row[1] for row in rows)
    assert "EMERGENCY" in blob and "ROUTINE" in blob
    # The bands are recorded; the clinician's free text stays on the result row.
    assert "Distinctive clinical reasoning" not in blob
