"""Patient record access-control tests.

Covers the security cases from docs/security/rbac-and-audit.md that need a real database:
S1 (unauthenticated), S2 (patient reaching another patient), S3 (wrong role),
S4 (administrator reaching clinical data), plus care-assignment and break-glass.
"""

from __future__ import annotations

from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.integration

AUTH = "/api/v1/auth"
PATIENTS = "/api/v1/patients"
ADMIN = "/api/v1/admin"
PASSWORD = "correct-horse-battery-staple"


async def make_patient(api: AsyncClient, email: str, family: str) -> dict[str, Any]:
    response = await api.post(
        f"{AUTH}/register",
        json={
            "email": email,
            "password": PASSWORD,
            "givenName": "Test",
            "familyName": family,
            "dateOfBirth": "1990-01-01",
        },
    )
    assert response.status_code == 201, response.text
    return dict(response.json())


async def token_for(api: AsyncClient, email: str) -> str:
    response = await api.post(f"{AUTH}/login", json={"email": email, "password": PASSWORD})
    assert response.status_code == 200, response.text
    return str(response.json()["accessToken"])


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def make_staff(db_session: AsyncSession, email: str, role: str, code: str) -> None:
    """Create a staff user directly.

    There is no endpoint for this on purpose: staff accounts are provisioned
    administratively, never self-registered.
    """
    from app.core.security import hash_password

    await db_session.execute(
        text(
            "INSERT INTO identity.users (email, password_hash, role, status) "
            "VALUES (:email, :hash, :role, 'ACTIVE')"
        ),
        {"email": email, "hash": hash_password(PASSWORD), "role": role},
    )
    await db_session.execute(
        text(
            "INSERT INTO identity.staff "
            "(user_id, staff_code, given_name, family_name, job_title) "
            "SELECT id, :code, 'Test', :code, 'Clinician' "
            "FROM identity.users WHERE email = :email"
        ),
        {"email": email, "code": code},
    )
    await db_session.flush()


# --- S1 / S2: patients reaching records that are not theirs -------------------


async def test_patient_can_read_their_own_record(api: AsyncClient) -> None:
    created = await make_patient(api, "self@example.test", "Self")
    token = await token_for(api, "self@example.test")

    response = await api.get(f"{PATIENTS}/{created['patientId']}", headers=auth(token))

    assert response.status_code == 200
    assert response.json()["access"]["basis"] == "SELF"


async def test_patient_cannot_read_another_patients_record(api: AsyncClient) -> None:
    """S2. Returns 404 rather than 403.

    A 403 would confirm the record exists, leaking the existence of a patient to anyone
    able to guess an identifier. The response must also not echo any of their data.
    """
    victim = await make_patient(api, "victim@example.test", "Victim")
    await make_patient(api, "attacker@example.test", "Attacker")
    token = await token_for(api, "attacker@example.test")

    response = await api.get(f"{PATIENTS}/{victim['patientId']}", headers=auth(token))

    assert response.status_code == 404
    assert "Victim" not in response.text


async def test_patient_cannot_search_patients(api: AsyncClient) -> None:
    """S3: a patient has no business enumerating other patients."""
    await make_patient(api, "nosy@example.test", "Nosy")
    token = await token_for(api, "nosy@example.test")

    assert (await api.get(PATIENTS, headers=auth(token))).status_code == 403


async def test_unauthenticated_access_is_refused(api: AsyncClient) -> None:
    """S1."""
    assert (await api.get(PATIENTS)).status_code == 401


# --- S4: administrators and clinical data -------------------------------------


async def test_admin_cannot_search_patients(api: AsyncClient, db_session: AsyncSession) -> None:
    """S4. Operational authority is not clinical authority.

    This is the rule most likely to be "fixed" by someone assuming it is a bug, so it is
    asserted explicitly rather than left implied.
    """
    await make_staff(db_session, "ops@example.test", "ADMIN", "ADM1")
    token = await token_for(api, "ops@example.test")

    assert (await api.get(PATIENTS, headers=auth(token))).status_code == 403


async def test_admin_cannot_read_a_patient_record(
    api: AsyncClient, db_session: AsyncSession
) -> None:
    created = await make_patient(api, "someone@example.test", "Someone")
    await make_staff(db_session, "ops2@example.test", "ADMIN", "ADM2")
    token = await token_for(api, "ops2@example.test")

    response = await api.get(f"{PATIENTS}/{created['patientId']}", headers=auth(token))

    assert response.status_code == 403
    assert "Someone" not in response.text


async def test_clinician_cannot_read_the_audit_trail(
    api: AsyncClient, db_session: AsyncSession
) -> None:
    """The mirror of the rule above: reviewing access is an operational function."""
    await make_staff(db_session, "doc@example.test", "DOCTOR", "DOC1")
    token = await token_for(api, "doc@example.test")

    assert (await api.get(f"{ADMIN}/audit", headers=auth(token))).status_code == 403


async def test_admin_can_read_the_audit_trail(api: AsyncClient, db_session: AsyncSession) -> None:
    await make_staff(db_session, "ops3@example.test", "ADMIN", "ADM3")
    token = await token_for(api, "ops3@example.test")

    response = await api.get(f"{ADMIN}/audit", headers=auth(token))

    assert response.status_code == 200
    assert "items" in response.json()


# --- Care assignment and break-glass ------------------------------------------


async def test_clinician_without_a_care_relationship_is_refused(
    api: AsyncClient, db_session: AsyncSession
) -> None:
    created = await make_patient(api, "unassigned@example.test", "Unassigned")
    await make_staff(db_session, "doc2@example.test", "DOCTOR", "DOC2")
    token = await token_for(api, "doc2@example.test")

    response = await api.get(f"{PATIENTS}/{created['patientId']}", headers=auth(token))

    assert response.status_code == 403
    # The hint lets the UI offer emergency access rather than presenting a dead end.
    assert response.headers.get("X-Permission-Hint") == "breakglass_available"


async def test_breakglass_requires_a_real_justification(
    api: AsyncClient, db_session: AsyncSession
) -> None:
    """A free-text box nobody validates is not a justification."""
    created = await make_patient(api, "bg@example.test", "Breakglass")
    await make_staff(db_session, "doc3@example.test", "DOCTOR", "DOC3")
    token = await token_for(api, "doc3@example.test")

    response = await api.post(
        f"{PATIENTS}/{created['patientId']}/breakglass",
        json={"reason": "urgent"},
        headers=auth(token),
    )

    assert response.status_code == 400


async def test_breakglass_grants_access_and_is_audited(
    api: AsyncClient, db_session: AsyncSession
) -> None:
    created = await make_patient(api, "bg2@example.test", "Emergency")
    await make_staff(db_session, "doc4@example.test", "DOCTOR", "DOC4")
    token = await token_for(api, "doc4@example.test")
    patient_id = created["patientId"]

    assert (await api.get(f"{PATIENTS}/{patient_id}", headers=auth(token))).status_code == 403

    granted = await api.post(
        f"{PATIENTS}/{patient_id}/breakglass",
        json={"reason": "Patient arrived unconscious with no assigned care team present"},
        headers=auth(token),
    )
    assert granted.status_code == 200

    after = await api.get(f"{PATIENTS}/{patient_id}", headers=auth(token))
    assert after.status_code == 200
    assert after.json()["access"]["basis"] == "BREAKGLASS"

    invocations = (
        await db_session.execute(
            text("SELECT count(*) FROM audit.audit_logs WHERE action = 'BREAKGLASS_INVOKED'")
        )
    ).scalar_one()
    assert invocations == 1


async def test_patient_cannot_use_breakglass(api: AsyncClient) -> None:
    """Emergency access is a clinical function, not a way around the ownership check."""
    victim = await make_patient(api, "target@example.test", "Target")
    await make_patient(api, "sneaky@example.test", "Sneaky")
    token = await token_for(api, "sneaky@example.test")

    response = await api.post(
        f"{PATIENTS}/{victim['patientId']}/breakglass",
        json={"reason": "I would very much like to read this record thank you"},
        headers=auth(token),
    )

    assert response.status_code == 403


# --- Audit --------------------------------------------------------------------


async def test_reading_a_record_is_audited_with_its_basis(
    api: AsyncClient, db_session: AsyncSession
) -> None:
    created = await make_patient(api, "audited@example.test", "Audited")
    token = await token_for(api, "audited@example.test")

    await api.get(f"{PATIENTS}/{created['patientId']}", headers=auth(token))

    basis = (
        await db_session.execute(
            text(
                "SELECT metadata->>'accessBasis' FROM audit.audit_logs "
                "WHERE action = 'PATIENT_RECORD_VIEW' ORDER BY id DESC LIMIT 1"
            )
        )
    ).scalar_one()

    assert basis == "SELF"


async def test_a_refused_read_is_still_audited(api: AsyncClient, db_session: AsyncSession) -> None:
    """The denial must survive the rollback that its own exception triggers.

    An access attempt nobody can see afterwards is not an audit trail.
    """
    victim = await make_patient(api, "v2@example.test", "Victim2")
    await make_patient(api, "a2@example.test", "Attacker2")
    token = await token_for(api, "a2@example.test")

    await api.get(f"{PATIENTS}/{victim['patientId']}", headers=auth(token))

    denials = (
        await db_session.execute(
            text(
                "SELECT count(*) FROM audit.audit_logs "
                "WHERE action = 'PERMISSION_DENIED' AND result = 'DENIED'"
            )
        )
    ).scalar_one()

    assert denials >= 1


async def test_audit_metadata_never_contains_a_patient_name(
    api: AsyncClient, db_session: AsyncSession
) -> None:
    created = await make_patient(api, "named@example.test", "Distinctive")
    token = await token_for(api, "named@example.test")
    await api.get(f"{PATIENTS}/{created['patientId']}", headers=auth(token))

    blob = (
        await db_session.execute(
            text("SELECT string_agg(metadata::text, ' ') FROM audit.audit_logs")
        )
    ).scalar_one()

    assert blob is not None
    assert "Distinctive" not in blob
    assert "named@example.test" not in blob
