"""Data access for identity and patient records.

Repositories own SQL. Services own decisions. Keeping them apart is what makes the
service layer testable without a database, and keeps query changes from rippling into
business logic.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any, cast

from sqlalchemy import CursorResult, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.clinical import Patient
from app.models.identity import PasswordResetToken, RefreshToken, Staff, User


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_email(self, email: str) -> User | None:
        # Matched case-insensitively, against the functional unique index created in
        # migration 001. Email addresses are not case-sensitive in practice, and treating
        # them as such creates accounts users cannot log back into.
        stmt = select(User).where(func.lower(User.email) == email.strip().lower())
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def get_by_id(self, user_id: uuid.UUID) -> User | None:
        return await self._session.get(User, user_id)

    async def get_active_by_id(self, user_id: uuid.UUID) -> User | None:
        user = await self._session.get(User, user_id)
        if user is None or user.is_locked:
            return None
        return user

    async def email_exists(self, email: str) -> bool:
        stmt = (
            select(func.count())
            .select_from(User)
            .where(func.lower(User.email) == email.strip().lower())
        )
        return bool((await self._session.execute(stmt)).scalar_one())

    async def add(self, user: User) -> User:
        self._session.add(user)
        await self._session.flush()
        return user

    async def record_successful_login(self, user: User) -> None:
        user.failed_logins = 0
        user.locked_until = None
        user.last_login_at = datetime.now(UTC)
        await self._session.flush()

    async def record_failed_login(
        self, user: User, *, max_attempts: int, lockout: datetime
    ) -> bool:
        """Increment the failure counter; lock the account at the threshold.

        Returns True when this attempt caused a lockout, so the caller can raise the
        matching audit event.
        """
        user.failed_logins += 1
        if user.failed_logins >= max_attempts:
            user.locked_until = lockout
            await self._session.flush()
            return True
        await self._session.flush()
        return False


class PatientRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, patient_id: uuid.UUID) -> Patient | None:
        patient = await self._session.get(Patient, patient_id)
        if patient is None or patient.deleted_at is not None:
            return None
        return patient

    async def get_by_user_id(self, user_id: uuid.UUID) -> Patient | None:
        stmt = select(Patient).where(Patient.user_id == user_id, Patient.deleted_at.is_(None))
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def nhs_number_exists(self, nhs_number: str) -> bool:
        stmt = select(func.count()).select_from(Patient).where(Patient.nhs_number == nhs_number)
        return bool((await self._session.execute(stmt)).scalar_one())

    async def add(self, patient: Patient) -> Patient:
        self._session.add(patient)
        await self._session.flush()
        return patient


class StaffRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_user_id(self, user_id: uuid.UUID) -> Staff | None:
        stmt = select(Staff).where(Staff.user_id == user_id, Staff.active.is_(True))
        return (await self._session.execute(stmt)).scalar_one_or_none()


class RefreshTokenRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, token: RefreshToken) -> RefreshToken:
        self._session.add(token)
        await self._session.flush()
        return token

    async def get_by_hash(self, token_hash: str) -> RefreshToken | None:
        stmt = select(RefreshToken).where(RefreshToken.token_hash == token_hash)
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def revoke(self, token: RefreshToken) -> None:
        token.revoked_at = datetime.now(UTC)
        await self._session.flush()

    async def revoke_all_for_user(self, user_id: uuid.UUID) -> int:
        """Revoke every live token for a user.

        Used on reuse detection: presenting an already-rotated token means either the
        legitimate user or an attacker holds a copy, and we cannot tell which. Ending
        every session is the only safe response - the real user re-authenticates, and the
        attacker is locked out.
        """
        stmt = (
            update(RefreshToken)
            .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=datetime.now(UTC))
        )
        result = cast(CursorResult[Any], await self._session.execute(stmt))
        return int(result.rowcount or 0)


class PasswordResetRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, token: PasswordResetToken) -> PasswordResetToken:
        self._session.add(token)
        await self._session.flush()
        return token

    async def get_usable_by_hash(self, token_hash: str) -> PasswordResetToken | None:
        stmt = select(PasswordResetToken).where(
            PasswordResetToken.token_hash == token_hash,
            PasswordResetToken.used_at.is_(None),
            PasswordResetToken.expires_at > datetime.now(UTC),
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def mark_used(self, token: PasswordResetToken) -> None:
        token.used_at = datetime.now(UTC)
        await self._session.flush()
