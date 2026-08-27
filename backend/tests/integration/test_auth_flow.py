"""Authentication flow tests against a real database.

Covers the registration/login/refresh/logout journey and the security cases from
docs/security/rbac-and-audit.md: S1 (unauthenticated access), S5 (invalid token),
S11 (account enumeration), S12 (lockout), S13 (token reuse).
"""

from __future__ import annotations

from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

AUTH = "/api/v1/auth"
VALID_PASSWORD = "correct-horse-battery-staple"

pytestmark = pytest.mark.integration


def registration_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "email": "alex.morgan@example.test",
        "password": VALID_PASSWORD,
        "givenName": "Alex",
        "familyName": "Morgan",
        "dateOfBirth": "1988-04-12",
        "preferredLanguage": "en-GB",
    }
    payload.update(overrides)
    return payload


async def register(api: AsyncClient, **overrides: Any) -> dict[str, Any]:
    response = await api.post(f"{AUTH}/register", json=registration_payload(**overrides))
    assert response.status_code == 201, response.text
    return dict(response.json())


async def login(api: AsyncClient, email: str, password: str) -> Any:
    return await api.post(f"{AUTH}/login", json={"email": email, "password": password})


# --- Registration ------------------------------------------------------------


async def test_patient_can_register(api: AsyncClient) -> None:
    body = await register(api)

    assert body["role"] == "PATIENT"
    assert body["email"] == "alex.morgan@example.test"
    assert body["userId"] and body["patientId"]


async def test_registration_never_returns_the_password(api: AsyncClient) -> None:
    response = await api.post(f"{AUTH}/register", json=registration_payload())

    assert VALID_PASSWORD not in response.text


async def test_registration_rejects_a_short_password(api: AsyncClient) -> None:
    response = await api.post(f"{AUTH}/register", json=registration_payload(password="short"))

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


async def test_registration_rejects_an_invalid_nhs_number(api: AsyncClient) -> None:
    response = await api.post(f"{AUTH}/register", json=registration_payload(nhsNumber="9434765918"))

    assert response.status_code == 400


async def test_registration_accepts_a_valid_nhs_number(api: AsyncClient) -> None:
    response = await api.post(
        f"{AUTH}/register", json=registration_payload(nhsNumber="943 476 5919")
    )

    assert response.status_code == 201


async def test_registration_cannot_self_assign_a_role(api: AsyncClient) -> None:
    """Privilege escalation via the request body must be impossible, not just undocumented."""
    response = await api.post(
        f"{AUTH}/register", json=registration_payload(role="ADMIN", status="ACTIVE")
    )

    assert response.status_code == 201
    assert response.json()["role"] == "PATIENT"


async def test_duplicate_registration_does_not_confirm_the_account_exists(
    api: AsyncClient,
) -> None:
    """S11: registration must not become an account-enumeration oracle."""
    await register(api)

    second = await api.post(f"{AUTH}/register", json=registration_payload())

    assert second.status_code == 400
    body = second.json()["error"]["message"].lower()
    assert "already" not in body
    assert "exists" not in body
    assert "registered" not in body


async def test_email_is_stored_case_insensitively(api: AsyncClient) -> None:
    await register(api, email="Alex.Morgan@Example.Test")

    response = await login(api, "alex.morgan@example.test", VALID_PASSWORD)

    assert response.status_code == 200


# --- Login -------------------------------------------------------------------


async def test_login_succeeds_and_sets_an_httponly_cookie(api: AsyncClient) -> None:
    await register(api)

    response = await login(api, "alex.morgan@example.test", VALID_PASSWORD)

    assert response.status_code == 200
    body = response.json()
    assert body["tokenType"] == "Bearer"
    assert body["expiresIn"] > 0
    assert body["user"]["role"] == "PATIENT"
    assert body["user"]["displayName"] == "Alex Morgan"

    cookie = response.headers.get("set-cookie", "")
    assert "refresh_token=" in cookie
    assert "HttpOnly" in cookie
    assert "SameSite=lax" in cookie.replace("samesite", "SameSite")


async def test_refresh_token_is_not_in_the_response_body(api: AsyncClient) -> None:
    """It lives in an httpOnly cookie; putting it in the body would expose it to XSS."""
    await register(api)

    response = await login(api, "alex.morgan@example.test", VALID_PASSWORD)

    assert "refreshToken" not in response.json()


async def test_login_with_a_wrong_password_is_rejected(api: AsyncClient) -> None:
    await register(api)

    response = await login(api, "alex.morgan@example.test", "wrong-password-entirely")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTHENTICATION_REQUIRED"


async def test_unknown_and_known_accounts_give_identical_responses(api: AsyncClient) -> None:
    """S11: the response must not distinguish 'no such account' from 'wrong password'."""
    await register(api)

    known = await login(api, "alex.morgan@example.test", "wrong-password-entirely")
    unknown = await login(api, "nobody@example.test", "wrong-password-entirely")

    assert known.status_code == unknown.status_code
    assert known.json()["error"]["code"] == unknown.json()["error"]["code"]
    assert known.json()["error"]["message"] == unknown.json()["error"]["message"]


async def test_account_locks_after_repeated_failures(api: AsyncClient) -> None:
    """S12: five failures lock the account; the sixth attempt is refused even if correct."""
    await register(api)

    for _ in range(5):
        await login(api, "alex.morgan@example.test", "wrong-password-entirely")

    response = await login(api, "alex.morgan@example.test", VALID_PASSWORD)

    assert response.status_code == 403
    assert "locked" in response.json()["error"]["message"].lower()


# --- Authenticated access ----------------------------------------------------


async def test_me_returns_the_signed_in_user(api: AsyncClient) -> None:
    await register(api)
    token = (await login(api, "alex.morgan@example.test", VALID_PASSWORD)).json()["accessToken"]

    response = await api.get(f"{AUTH}/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    assert response.json()["email"] == "alex.morgan@example.test"


async def test_me_requires_authentication(api: AsyncClient) -> None:
    """S1: an unauthenticated request to a protected route is refused."""
    response = await api.get(f"{AUTH}/me")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTHENTICATION_REQUIRED"


@pytest.mark.parametrize(
    "header",
    [
        "Bearer not-a-jwt",
        "Bearer eyJhbGciOiJub25lIn0.eyJzdWIiOiJhZG1pbiJ9.",  # alg=none
        "Basic YWRtaW46YWRtaW4=",
        "bearer",
        "",
    ],
)
async def test_malformed_credentials_are_refused(api: AsyncClient, header: str) -> None:
    """S5: including the 'none' algorithm, which must never be accepted."""
    response = await api.get(f"{AUTH}/me", headers={"Authorization": header})

    assert response.status_code == 401


async def test_a_token_signed_with_the_wrong_key_is_refused(api: AsyncClient) -> None:
    import jwt

    forged = jwt.encode(
        {
            "sub": "00000000-0000-0000-0000-000000000001",
            "role": "ADMIN",
            "typ": "access",
            "exp": 9999999999,
        },
        "an-attackers-own-signing-key-not-ours",
        algorithm="HS256",
    )

    response = await api.get(f"{AUTH}/me", headers={"Authorization": f"Bearer {forged}"})

    assert response.status_code == 401


# --- Refresh and logout ------------------------------------------------------


async def test_refresh_rotates_the_session(api: AsyncClient) -> None:
    await register(api)
    first = await login(api, "alex.morgan@example.test", VALID_PASSWORD)

    response = await api.post(f"{AUTH}/refresh")

    assert response.status_code == 200
    assert response.json()["accessToken"] != first.json()["accessToken"]


async def test_reusing_a_rotated_refresh_token_revokes_every_session(
    api: AsyncClient, db_session: AsyncSession
) -> None:
    """S13: token reuse is treated as theft, so the whole chain is revoked.

    A stolen refresh token and the legitimate user are indistinguishable at this point,
    so the only safe response is to end every session and make the real user sign in.
    """
    await register(api)
    await login(api, "alex.morgan@example.test", VALID_PASSWORD)

    stolen = api.cookies.get("refresh_token")
    assert stolen

    # Legitimate rotation - the stolen value is now spent.
    assert (await api.post(f"{AUTH}/refresh")).status_code == 200

    replayed = await api.post(f"{AUTH}/refresh", cookies={"refresh_token": stolen})
    assert replayed.status_code == 401

    # And the session issued by the legitimate rotation is dead too.
    from app.models.identity import RefreshToken

    live = (
        (await db_session.execute(select(RefreshToken).where(RefreshToken.revoked_at.is_(None))))
        .scalars()
        .all()
    )
    assert live == []


async def test_logout_is_idempotent(api: AsyncClient) -> None:
    await register(api)
    await login(api, "alex.morgan@example.test", VALID_PASSWORD)

    assert (await api.post(f"{AUTH}/logout")).status_code == 200
    assert (await api.post(f"{AUTH}/logout")).status_code == 200


async def test_refresh_after_logout_is_refused(api: AsyncClient) -> None:
    await register(api)
    await login(api, "alex.morgan@example.test", VALID_PASSWORD)
    await api.post(f"{AUTH}/logout")

    assert (await api.post(f"{AUTH}/refresh")).status_code == 401


# --- Password reset ----------------------------------------------------------


@pytest.mark.parametrize("email", ["alex.morgan@example.test", "nobody@example.test"])
async def test_password_reset_response_is_identical_for_any_address(
    api: AsyncClient, email: str
) -> None:
    """S11: this endpoint must not reveal whether someone is a patient here."""
    await register(api)

    response = await api.post(f"{AUTH}/password-reset", json={"email": email})

    assert response.status_code == 200
    assert response.json()["message"] == (
        "If that email address has an account, we have sent a reset link to it."
    )


async def test_password_reset_never_returns_the_token(api: AsyncClient) -> None:
    await register(api)

    response = await api.post(f"{AUTH}/password-reset", json={"email": "alex.morgan@example.test"})

    assert "token" not in response.text.lower()


# --- Storage guarantees ------------------------------------------------------


async def test_passwords_are_stored_hashed_with_argon2(
    api: AsyncClient, db_session: AsyncSession
) -> None:
    await register(api)

    stored = await db_session.scalar(text("SELECT password_hash FROM identity.users"))

    assert stored is not None
    assert VALID_PASSWORD not in stored
    assert stored.startswith("$argon2id$")


async def test_refresh_tokens_are_stored_hashed(api: AsyncClient, db_session: AsyncSession) -> None:
    """A database dump must not yield usable sessions."""
    await register(api)
    await login(api, "alex.morgan@example.test", VALID_PASSWORD)
    raw = api.cookies.get("refresh_token")

    stored = await db_session.scalar(text("SELECT token_hash FROM identity.refresh_tokens"))

    assert stored is not None
    assert raw is not None
    assert stored != raw
    assert len(stored) == 64  # sha256 hex


# --- Audit -------------------------------------------------------------------


async def test_registration_and_login_are_audited(
    api: AsyncClient, db_session: AsyncSession
) -> None:
    await register(api)
    await login(api, "alex.morgan@example.test", VALID_PASSWORD)

    actions = (
        await db_session.execute(text("SELECT action, result FROM audit.audit_logs ORDER BY id"))
    ).all()
    recorded = {row[0] for row in actions}

    assert "USER_REGISTERED" in recorded
    assert "USER_LOGIN" in recorded


async def test_failed_login_is_audited_as_denied(
    api: AsyncClient, db_session: AsyncSession
) -> None:
    await register(api)
    await login(api, "alex.morgan@example.test", "wrong-password-entirely")

    denied = await db_session.scalar(
        text("SELECT count(*) FROM audit.audit_logs WHERE result = 'DENIED'")
    )

    assert denied and denied >= 1


async def test_audit_metadata_holds_no_credentials_or_identifiers(
    api: AsyncClient, db_session: AsyncSession
) -> None:
    """The audit trail records who did what, never a second copy of sensitive data."""
    await register(api, nhsNumber="943 476 5919")
    await login(api, "alex.morgan@example.test", VALID_PASSWORD)

    blob = await db_session.scalar(
        text("SELECT string_agg(metadata::text, ' ') FROM audit.audit_logs")
    )

    assert blob is not None
    assert VALID_PASSWORD not in blob
    assert "9434765919" not in blob
    assert "alex.morgan@example.test" not in blob


async def test_audit_log_rejects_updates(db_session: AsyncSession) -> None:
    """The append-only guarantee is enforced by the database, not by convention."""
    await db_session.execute(
        text("INSERT INTO audit.audit_logs (action, result) VALUES ('TEST_EVENT', 'SUCCESS')")
    )

    with pytest.raises(Exception, match="append-only"):
        await db_session.execute(text("UPDATE audit.audit_logs SET action = 'TAMPERED'"))
