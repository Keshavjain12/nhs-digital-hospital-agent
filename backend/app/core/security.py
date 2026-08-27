"""Password hashing, token issuing and verification.

Two token types with deliberately different handling:

- **Access token**: a short-lived JWT, stateless, held in browser memory. Never in
  localStorage, which is readable by any XSS.
- **Refresh token**: long-lived, opaque, stored **hashed** server-side and sent as an
  httpOnly cookie the page's JavaScript cannot read.

Neither alone is enough for an attacker holding a single class of vulnerability. And
because only the hash is stored, a database dump yields no usable session.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

from app.core.config import get_settings
from app.core.errors import AuthenticationRequired, TokenExpired

# Argon2id with the library defaults, which follow current OWASP guidance.
_hasher = PasswordHasher()

# A precomputed hash of a throwaway value. Verifying against it when an account does not
# exist keeps the failure path the same cost as the success path, so response timing does
# not reveal whether an email is registered.
_DUMMY_HASH = _hasher.hash("timing-equalisation-placeholder")

TokenType = Literal["access"]


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str | None) -> bool:
    """Verify a password, in constant-ish time whether or not the user exists.

    Callers pass `None` when no account was found; the dummy verification still runs.
    """
    target = password_hash or _DUMMY_HASH
    try:
        _hasher.verify(target, password)
    except (VerifyMismatchError, InvalidHashError):
        return False
    return password_hash is not None


def needs_rehash(password_hash: str) -> bool:
    """True when the stored hash predates the current cost parameters."""
    return _hasher.check_needs_rehash(password_hash)


# --- Opaque tokens (refresh, password reset) ---------------------------------


def generate_opaque_token() -> str:
    """A high-entropy token returned to the client exactly once."""
    return secrets.token_urlsafe(48)


def hash_token(token: str) -> str:
    """Hash an opaque token for storage.

    SHA-256 rather than Argon2: these are 384-bit random values, not user-chosen
    secrets, so there is nothing to brute-force and the lookup must stay fast enough to
    run on every refresh.
    """
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def tokens_equal(candidate: str, stored_hash: str) -> bool:
    return hmac.compare_digest(hash_token(candidate), stored_hash)


def hash_for_audit(value: str | None) -> str | None:
    """Hash an IP address or user agent for the audit log.

    An IP address is personal data under UK GDPR. The audit trail needs to distinguish
    sessions, not to identify a location, and a hash does the first without the second.
    """
    if not value:
        return None
    settings = get_settings()
    return hmac.new(
        settings.jwt_secret.encode("utf-8"), value.encode("utf-8"), hashlib.sha256
    ).hexdigest()


# --- Access tokens (JWT) -----------------------------------------------------


def create_access_token(
    *,
    user_id: uuid.UUID,
    role: str,
    patient_id: uuid.UUID | None = None,
    staff_id: uuid.UUID | None = None,
) -> tuple[str, int]:
    """Return (token, expires_in_seconds).

    The role and the patient/staff identity are embedded so ordinary requests need no
    extra query. They are *not* trusted for authorisation on their own: every
    patient-scoped route still re-checks the relationship server-side, because a token
    issued before a role change would otherwise keep working.
    """
    settings = get_settings()
    now = datetime.now(UTC)
    expires_in = settings.jwt_access_ttl_seconds

    payload: dict[str, Any] = {
        "sub": str(user_id),
        "role": role,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=expires_in)).timestamp()),
        "jti": str(uuid.uuid4()),
        "typ": "access",
    }
    if patient_id is not None:
        payload["pid"] = str(patient_id)
    if staff_id is not None:
        payload["sid"] = str(staff_id)

    token = jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    return token, expires_in


def decode_access_token(token: str) -> dict[str, Any]:
    """Decode and validate an access token.

    Raises TokenExpired or AuthenticationRequired. The distinction matters to the client:
    expiry means "refresh and retry", anything else means "sign in again".
    """
    settings = get_settings()
    try:
        payload: dict[str, Any] = jwt.decode(
            token,
            settings.jwt_secret,
            # Pinned explicitly. Accepting the token's own `alg` is how algorithm-
            # confusion attacks work, including the "none" algorithm.
            algorithms=[settings.jwt_algorithm],
            options={"require": ["exp", "sub", "typ"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise TokenExpired() from exc
    except jwt.InvalidTokenError as exc:
        # Deliberately uniform: never reveal whether the signature, the claims or the
        # structure was wrong.
        raise AuthenticationRequired() from exc

    if payload.get("typ") != "access":
        # A refresh token presented as a Bearer credential must not be accepted.
        raise AuthenticationRequired()

    return payload


def refresh_token_expiry() -> datetime:
    return datetime.now(UTC) + timedelta(days=get_settings().refresh_token_ttl_days)


def password_reset_expiry() -> datetime:
    return datetime.now(UTC) + timedelta(minutes=get_settings().password_reset_ttl_minutes)
