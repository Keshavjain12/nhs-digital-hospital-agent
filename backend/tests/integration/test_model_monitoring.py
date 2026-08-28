"""Model monitoring.

Two properties are load-bearing and both are easy to lose to a well-meaning refactor:

- A model that does not exist reports no metrics at all. Rendering zeroes for it would
  read as a healthy model rather than an absent one.
- Override direction is reported separately. Averaging both directions into one "accuracy"
  number would hide under-triage - the only direction that harms anyone - inside a figure
  that looks fine.
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
MODELS = "/api/v1/admin/models"
PASSWORD = "correct-horse-battery-staple"


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def make_staff(db_session: AsyncSession, email: str, role: str, code: str) -> None:
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


async def token_for(api: AsyncClient, email: str) -> str:
    response = await api.post(f"{AUTH}/login", json={"email": email, "password": PASSWORD})
    return str(response.json()["accessToken"])


#: Deliberately unlike any word this endpoint can legitimately emit. "Monitor" was tried
#: first and matched the word "Monitoring" inside a caveat, so the leak test failed on its
#: own wording rather than on a real disclosure.
SYNTHETIC_SURNAME = "Vexbourne"


async def triage_for(api: AsyncClient, email: str, message: str) -> str:
    await api.post(
        f"{AUTH}/register",
        json={
            "email": email,
            "password": PASSWORD,
            "givenName": "Test",
            "familyName": SYNTHETIC_SURNAME,
            "dateOfBirth": "1990-01-01",
        },
    )
    token = await token_for(api, email)
    session_id = (await api.post(f"{CHAT}/sessions", headers=auth(token))).json()["session"]["id"]
    turn = await api.post(
        f"{CHAT}/sessions/{session_id}/messages", json={"content": message}, headers=auth(token)
    )
    for follow_up in ("a few days", "manageable"):
        if turn.json().get("triage"):
            break
        turn = await api.post(
            f"{CHAT}/sessions/{session_id}/messages",
            json={"content": follow_up},
            headers=auth(token),
        )
    return str(turn.json()["triage"]["id"])


def metric(card: dict, key: str) -> dict:
    return next(m for m in card["metrics"] if m["key"] == key)


def card_for(body: dict, key: str) -> dict:
    return next(c for c in body["items"] if c["key"] == key)


# --- Access control --------------------------------------------------------------


async def test_monitoring_requires_authentication(api: AsyncClient) -> None:
    assert (await api.get(MODELS)).status_code == 401


async def test_a_clinician_cannot_read_model_monitoring(
    api: AsyncClient, db_session: AsyncSession
) -> None:
    """Monitoring is an operational function, mirroring the audit trail."""
    await make_staff(db_session, "doc@example.test", "DOCTOR", "MDOC1")
    token = await token_for(api, "doc@example.test")

    assert (await api.get(MODELS, headers=auth(token))).status_code == 403


async def test_an_administrator_can_read_model_monitoring(
    api: AsyncClient, db_session: AsyncSession
) -> None:
    await make_staff(db_session, "ops@example.test", "ADMIN", "MADM1")
    token = await token_for(api, "ops@example.test")

    response = await api.get(MODELS, headers=auth(token))

    assert response.status_code == 200
    assert response.json()["items"]


# --- Honesty about what exists ----------------------------------------------------


async def test_models_that_do_not_exist_report_no_metrics(
    api: AsyncClient, db_session: AsyncSession
) -> None:
    """Zeroes would read as a healthy model rather than an absent one."""
    await make_staff(db_session, "ops2@example.test", "ADMIN", "MADM2")
    token = await token_for(api, "ops2@example.test")

    body = (await api.get(MODELS, headers=auth(token))).json()
    not_built = [c for c in body["items"] if c["status"] == "NOT_BUILT"]

    assert not_built, "planned but unbuilt models must still be listed"
    for card in not_built:
        assert card["metrics"] == []
        assert card["version"] is None
        assert any("not built" in caveat.lower() for caveat in card["caveats"])


async def test_the_live_model_declares_it_is_not_a_trained_model(
    api: AsyncClient, db_session: AsyncSession
) -> None:
    await make_staff(db_session, "ops3@example.test", "ADMIN", "MADM3")
    token = await token_for(api, "ops3@example.test")

    card = card_for((await api.get(MODELS, headers=auth(token))).json(), "triage")
    caveats = " ".join(card["caveats"]).lower()

    assert "not a trained model" in caveats
    assert "confidence" in caveats
    assert "synthetic" in caveats


async def test_monitoring_states_it_is_not_clinical_governance(
    api: AsyncClient, db_session: AsyncSession
) -> None:
    """Required by the brief: monitoring must not be presented as sufficient oversight."""
    await make_staff(db_session, "ops4@example.test", "ADMIN", "MADM4")
    token = await token_for(api, "ops4@example.test")

    card = card_for((await api.get(MODELS, headers=auth(token))).json(), "triage")

    assert any("not clinical governance" in c.lower() for c in card["caveats"])


# --- The numbers -------------------------------------------------------------------


async def test_a_downgrade_counts_as_over_triage(
    api: AsyncClient, db_session: AsyncSession
) -> None:
    """Clinician chose a LESS urgent band: the engine over-triaged. Safe, but tracked."""
    result_id = await triage_for(api, "down@example.test", "I have crushing chest pain")
    await make_staff(db_session, "doc2@example.test", "DOCTOR", "MDOC2")
    await make_staff(db_session, "ops5@example.test", "ADMIN", "MADM5")
    doctor = await token_for(api, "doc2@example.test")
    await api.post(
        f"{TRIAGE}/{result_id}/review",
        json={"agrees": False, "clinicianSeverity": "ROUTINE", "note": "Not cardiac in nature"},
        headers=auth(doctor),
    )

    admin = await token_for(api, "ops5@example.test")
    card = card_for((await api.get(MODELS, headers=auth(admin))).json(), "triage")

    assert metric(card, "over_triage")["value"] == "1"
    assert metric(card, "under_triage")["value"] == "0"
    # Over-triage is expected behaviour for this engine, so it is not flagged.
    assert metric(card, "over_triage")["tone"] == "neutral"


async def test_an_upgrade_counts_as_under_triage_and_is_flagged(
    api: AsyncClient, db_session: AsyncSession
) -> None:
    """Clinician chose a MORE urgent band: the engine missed something.

    This is the direction that harms people, so it is reported separately and flagged.
    """
    result_id = await triage_for(api, "up@example.test", "I have an itchy rash")
    await make_staff(db_session, "doc3@example.test", "DOCTOR", "MDOC3")
    await make_staff(db_session, "ops6@example.test", "ADMIN", "MADM6")
    doctor = await token_for(api, "doc3@example.test")
    await api.post(
        f"{TRIAGE}/{result_id}/review",
        json={
            "agrees": False,
            "clinicianSeverity": "EMERGENCY",
            "note": "Spreading rapidly with systemic signs",
        },
        headers=auth(doctor),
    )

    admin = await token_for(api, "ops6@example.test")
    card = card_for((await api.get(MODELS, headers=auth(admin))).json(), "triage")

    assert metric(card, "under_triage")["value"] == "1"
    assert metric(card, "under_triage")["tone"] == "attention"


async def test_the_two_directions_are_never_merged(
    api: AsyncClient, db_session: AsyncSession
) -> None:
    """One overall 'accuracy' figure would hide under-triage inside a healthy-looking number."""
    await make_staff(db_session, "ops7@example.test", "ADMIN", "MADM7")
    token = await token_for(api, "ops7@example.test")

    card = card_for((await api.get(MODELS, headers=auth(token))).json(), "triage")
    keys = {m["key"] for m in card["metrics"]}

    assert "under_triage" in keys
    assert "over_triage" in keys
    assert "accuracy" not in keys


async def test_rates_show_a_dash_rather_than_zero_when_there_is_no_data(
    api: AsyncClient, db_session: AsyncSession
) -> None:
    """0 of 0 is not 0% - reporting it that way invents a failure where there is no data."""
    await make_staff(db_session, "ops8@example.test", "ADMIN", "MADM8")
    token = await token_for(api, "ops8@example.test")

    # A window in which nothing was produced.
    body = (await api.get(f"{MODELS}?windowDays=1", headers=auth(token))).json()
    card = card_for(body, "triage")

    if metric(card, "total")["value"] == "0":
        assert metric(card, "agreement")["value"] == "—"


async def test_no_patient_identity_appears_anywhere_in_the_response(
    api: AsyncClient, db_session: AsyncSession
) -> None:
    """Administrators see that overrides happen, never whose care they concerned."""
    await triage_for(api, "identifiable@example.test", "I have crushing chest pain")
    await make_staff(db_session, "ops9@example.test", "ADMIN", "MADM9")
    token = await token_for(api, "ops9@example.test")

    response = await api.get(MODELS, headers=auth(token))

    assert "identifiable@example.test" not in response.text
    assert SYNTHETIC_SURNAME not in response.text
