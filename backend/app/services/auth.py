"""Authentication service.

Holds the decisions; the repositories hold the SQL and the router holds the HTTP.

Three behaviours here are deliberate and easy to "simplify" into vulnerabilities:

1. Login and password reset never reveal whether an account exists.
2. A refresh token presented twice revokes the entire chain rather than just itself.
3. Failed logins are counted per account *and* rate-limited per client, because either
   control alone leaves an obvious gap.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import (
    AuthenticationRequired,
    PermissionDenied,
    ValidationFailed,
)
from app.core.logging import get_logger
from app.core.security import (
    create_access_token,
    generate_opaque_token,
    hash_password,
    hash_token,
    needs_rehash,
    password_reset_expiry,
    refresh_token_expiry,
    verify_password,
)
from app.models.audit import AuditAction
from app.models.base import AuditResult, DataOrigin, UserRole, UserStatus
from app.models.clinical import Patient
from app.models.identity import PasswordResetToken, RefreshToken, User
from app.repositories.user import (
    PasswordResetRepository,
    PatientRepository,
    RefreshTokenRepository,
    StaffRepository,
    UserRepository,
)
from app.schemas.auth import RegisterRequest, UserSummary
from app.services.audit import AuditService

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class RequestContext:
    """Who is making the request, for audit purposes. Values are already hashed."""

    request_id: str | None = None
    ip_hash: str | None = None
    user_agent_hash: str | None = None


@dataclass(frozen=True, slots=True)
class IssuedSession:
    access_token: str
    expires_in: int
    refresh_token: str
    refresh_expires_at: datetime
    user: UserSummary


class AuthService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self.users = UserRepository(session)
        self.patients = PatientRepository(session)
        self.staff = StaffRepository(session)
        self.refresh_tokens = RefreshTokenRepository(session)
        self.password_resets = PasswordResetRepository(session)
        self.audit = AuditService(session)

    # --- Registration --------------------------------------------------------

    async def register_patient(
        self, payload: RegisterRequest, context: RequestContext
    ) -> tuple[User, Patient]:
        """Register a patient account.

        Role is hard-coded to PATIENT. There is no code path by which a request body can
        influence it - self-registration as staff or admin must be impossible, not merely
        undocumented.
        """
        email = payload.email.strip().lower()

        if payload.nhs_number and await self.patients.nhs_number_exists(payload.nhs_number):
            # Deliberately vague. Confirming an NHS number is already registered would
            # turn this endpoint into a check for whether a person is a patient here.
            raise ValidationFailed("We could not complete registration with those details.")

        user = User(
            email=email,
            password_hash=hash_password(payload.password),
            role=UserRole.PATIENT,
            status=UserStatus.ACTIVE,
        )

        try:
            await self.users.add(user)
        except IntegrityError as exc:
            await self._session.rollback()
            # An account already exists. The response is the same shape as a validation
            # failure so registration cannot be used to enumerate accounts.
            logger.info("registration_conflict", extra={"request_id": context.request_id})
            raise ValidationFailed(
                "We could not complete registration with those details."
            ) from exc

        patient = Patient(
            user_id=user.id,
            nhs_number=payload.nhs_number,
            given_name=payload.given_name.strip(),
            family_name=payload.family_name.strip(),
            date_of_birth=payload.date_of_birth,
            email=email,
            preferred_language=payload.preferred_language,
            data_origin=DataOrigin.USER_ENTERED.value,
        )
        await self.patients.add(patient)

        await self.audit.record(
            action=AuditAction.USER_REGISTERED,
            actor_user_id=user.id,
            actor_role=UserRole.PATIENT,
            resource_type="Patient",
            resource_id=patient.id,
            request_id=context.request_id,
            ip_hash=context.ip_hash,
            user_agent_hash=context.user_agent_hash,
            metadata={"nhsNumberSupplied": payload.nhs_number is not None},
        )

        return user, patient

    # --- Login ---------------------------------------------------------------

    async def authenticate(
        self, email: str, password: str, context: RequestContext
    ) -> IssuedSession:
        settings = get_settings()
        user = await self.users.get_by_email(email)

        # Runs even when the user is absent, so a missing account and a wrong password
        # take the same time. Without this, response latency enumerates accounts.
        password_ok = verify_password(password, user.password_hash if user else None)

        if user is None or not password_ok:
            if user is not None:
                locked = await self.users.record_failed_login(
                    user,
                    max_attempts=settings.max_failed_logins,
                    lockout=datetime.now(UTC) + timedelta(minutes=settings.account_lockout_minutes),
                )
                await self.audit.record(
                    action=AuditAction.ACCOUNT_LOCKED if locked else AuditAction.USER_LOGIN,
                    result=AuditResult.DENIED,
                    actor_user_id=user.id,
                    actor_role=user.role,
                    request_id=context.request_id,
                    ip_hash=context.ip_hash,
                    user_agent_hash=context.user_agent_hash,
                    metadata={"reason": "invalid_credentials", "failedLogins": user.failed_logins},
                )
            else:
                await self.audit.record(
                    action=AuditAction.USER_LOGIN,
                    result=AuditResult.DENIED,
                    request_id=context.request_id,
                    ip_hash=context.ip_hash,
                    user_agent_hash=context.user_agent_hash,
                    metadata={"reason": "unknown_account"},
                )
            # Committed before raising. The router's transaction dependency rolls back on
            # exception, which would otherwise discard both the audit record of the failure
            # and the incremented attempt counter - leaving failed logins invisible and
            # making the lockout threshold unreachable, since the count never survived a
            # request. Security controls must not depend on the request succeeding.
            await self._session.commit()
            raise AuthenticationRequired("Your email address or password is incorrect.")

        if user.is_locked:
            await self.audit.record(
                action=AuditAction.USER_LOGIN,
                result=AuditResult.DENIED,
                actor_user_id=user.id,
                actor_role=user.role,
                request_id=context.request_id,
                ip_hash=context.ip_hash,
                metadata={"reason": "account_locked"},
            )
            # Distinct from bad credentials: the user needs to know waiting will help.
            # This reveals nothing an attacker who triggered the lockout does not know.
            await self._session.commit()
            raise PermissionDenied(
                "This account is temporarily locked after repeated sign-in attempts. "
                "Please try again later."
            )

        # Transparent upgrade if the cost parameters have moved on since this hash was made.
        if needs_rehash(user.password_hash):
            user.password_hash = hash_password(password)

        await self.users.record_successful_login(user)
        session = await self._issue_session(user, context)

        await self.audit.record(
            action=AuditAction.USER_LOGIN,
            actor_user_id=user.id,
            actor_role=user.role,
            request_id=context.request_id,
            ip_hash=context.ip_hash,
            user_agent_hash=context.user_agent_hash,
        )
        return session

    # --- Session issuing -----------------------------------------------------

    async def build_summary(self, user: User) -> UserSummary:
        patient_id: uuid.UUID | None = None
        staff_id: uuid.UUID | None = None
        display_name = user.email

        if user.role is UserRole.PATIENT:
            patient = await self.patients.get_by_user_id(user.id)
            if patient:
                patient_id = patient.id
                display_name = patient.display_name
        else:
            staff = await self.staff.get_by_user_id(user.id)
            if staff:
                staff_id = staff.id
                display_name = staff.display_name

        return UserSummary(
            id=user.id,
            email=user.email,
            role=user.role.value,
            display_name=display_name,
            patient_id=patient_id,
            staff_id=staff_id,
        )

    async def _issue_session(
        self, user: User, context: RequestContext, *, replaces: RefreshToken | None = None
    ) -> IssuedSession:
        summary = await self.build_summary(user)
        access_token, expires_in = create_access_token(
            user_id=user.id,
            role=user.role.value,
            patient_id=summary.patient_id,
            staff_id=summary.staff_id,
        )

        raw_refresh = generate_opaque_token()
        expires_at = refresh_token_expiry()
        stored = RefreshToken(
            user_id=user.id,
            token_hash=hash_token(raw_refresh),
            expires_at=expires_at,
        )
        await self.refresh_tokens.add(stored)

        if replaces is not None:
            replaces.replaced_by = stored.id
            await self._session.flush()

        return IssuedSession(
            access_token=access_token,
            expires_in=expires_in,
            refresh_token=raw_refresh,
            refresh_expires_at=expires_at,
            user=summary,
        )

    # --- Refresh -------------------------------------------------------------

    async def refresh(self, raw_token: str, context: RequestContext) -> IssuedSession:
        stored = await self.refresh_tokens.get_by_hash(hash_token(raw_token))

        if stored is None:
            raise AuthenticationRequired("Your session has expired. Please sign in again.")

        if stored.revoked_at is not None:
            # Reuse of an already-rotated token. Either the legitimate holder replayed an
            # old value or an attacker is using a stolen copy, and the two are
            # indistinguishable from here. Ending every session for this user is the only
            # safe response: the real user signs in again, the attacker loses access.
            revoked = await self.refresh_tokens.revoke_all_for_user(stored.user_id)
            await self.audit.record(
                action=AuditAction.TOKEN_REUSE_DETECTED,
                result=AuditResult.DENIED,
                actor_user_id=stored.user_id,
                resource_type="RefreshToken",
                resource_id=stored.id,
                request_id=context.request_id,
                ip_hash=context.ip_hash,
                user_agent_hash=context.user_agent_hash,
                metadata={"sessionsRevoked": revoked},
                detail="Refresh token reuse detected; all sessions revoked.",
            )
            logger.warning(
                "refresh_token_reuse_detected",
                extra={"request_id": context.request_id, "sessions_revoked": revoked},
            )
            # The revocation is the security response to a suspected stolen token. Letting
            # it roll back with the 401 would leave every session alive - the opposite of
            # what this branch exists to do.
            await self._session.commit()
            raise AuthenticationRequired("Your session has expired. Please sign in again.")

        if stored.expires_at <= datetime.now(UTC):
            raise AuthenticationRequired("Your session has expired. Please sign in again.")

        user = await self.users.get_active_by_id(stored.user_id)
        if user is None:
            # Disabled or locked since the token was issued. A live refresh token must not
            # outlive the account's right to use it.
            await self.refresh_tokens.revoke_all_for_user(stored.user_id)
            raise AuthenticationRequired("Your session has expired. Please sign in again.")

        await self.refresh_tokens.revoke(stored)
        session = await self._issue_session(user, context, replaces=stored)

        await self.audit.record(
            action=AuditAction.TOKEN_REFRESHED,
            actor_user_id=user.id,
            actor_role=user.role,
            request_id=context.request_id,
            ip_hash=context.ip_hash,
        )
        return session

    # --- Logout --------------------------------------------------------------

    async def logout(self, raw_token: str | None, context: RequestContext) -> None:
        if not raw_token:
            return
        stored = await self.refresh_tokens.get_by_hash(hash_token(raw_token))
        if stored is None or stored.revoked_at is not None:
            return

        await self.refresh_tokens.revoke(stored)
        await self.audit.record(
            action=AuditAction.USER_LOGOUT,
            actor_user_id=stored.user_id,
            request_id=context.request_id,
            ip_hash=context.ip_hash,
        )

    # --- Password reset ------------------------------------------------------

    async def request_password_reset(self, email: str, context: RequestContext) -> str | None:
        """Create a reset token if the account exists.

        Returns the raw token for the notification service, or None. The *caller* always
        responds identically either way - this endpoint must not reveal whether an
        address is registered.
        """
        user = await self.users.get_by_email(email)

        await self.audit.record(
            action=AuditAction.PASSWORD_RESET_REQUESTED,
            result=AuditResult.SUCCESS if user else AuditResult.DENIED,
            actor_user_id=user.id if user else None,
            request_id=context.request_id,
            ip_hash=context.ip_hash,
            metadata={"accountFound": user is not None},
        )

        if user is None:
            return None

        raw_token = generate_opaque_token()
        await self.password_resets.add(
            PasswordResetToken(
                user_id=user.id,
                token_hash=hash_token(raw_token),
                expires_at=password_reset_expiry(),
            )
        )
        return raw_token

    async def confirm_password_reset(
        self, raw_token: str, new_password: str, context: RequestContext
    ) -> None:
        stored = await self.password_resets.get_usable_by_hash(hash_token(raw_token))
        if stored is None:
            raise ValidationFailed("This reset link is invalid or has expired.")

        user = await self.users.get_by_id(stored.user_id)
        if user is None:
            raise ValidationFailed("This reset link is invalid or has expired.")

        user.password_hash = hash_password(new_password)
        user.failed_logins = 0
        user.locked_until = None
        await self.password_resets.mark_used(stored)

        # Every existing session ends. If the reset was triggered because the account was
        # compromised, leaving the attacker's session alive would defeat the whole point.
        revoked = await self.refresh_tokens.revoke_all_for_user(user.id)

        await self.audit.record(
            action=AuditAction.PASSWORD_RESET_COMPLETED,
            actor_user_id=user.id,
            actor_role=user.role,
            request_id=context.request_id,
            ip_hash=context.ip_hash,
            metadata={"sessionsRevoked": revoked},
        )
