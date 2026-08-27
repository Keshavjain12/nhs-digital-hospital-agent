"""Request dependencies: authentication, authorisation and rate limiting.

This module is the server-side gate. Frontend route protection is a usability feature -
it stops a user landing on a page that will not work. It is not security, and nothing
here trusts it (brief §9).

Every sensitive route declares its requirement explicitly. There is no "default allow":
a route without a dependency has no authenticated principal to work with.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Callable, Coroutine
from dataclasses import dataclass
from typing import Annotated, Any

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.errors import AuthenticationRequired, PermissionDenied, RateLimited
from app.core.logging import get_logger
from app.core.ratelimit import (
    ANONYMOUS_LIMIT,
    AUTHENTICATED_LIMIT,
    RateLimit,
    get_rate_limiter,
)
from app.core.security import decode_access_token, hash_for_audit
from app.models.base import UserRole
from app.services.auth import RequestContext

logger = get_logger(__name__)

DbSession = Annotated[AsyncSession, Depends(get_session)]


@dataclass(frozen=True, slots=True)
class Principal:
    """The authenticated caller.

    `patient_id` and `staff_id` come from the token for convenience. They are never the
    sole basis for authorising access to a *specific* record - see `require_patient_access`
    in the patients router, which re-checks the relationship against the database.
    """

    user_id: uuid.UUID
    role: UserRole
    patient_id: uuid.UUID | None = None
    staff_id: uuid.UUID | None = None

    @property
    def is_staff(self) -> bool:
        return self.role in {UserRole.DOCTOR, UserRole.NURSE}

    @property
    def is_clinical(self) -> bool:
        """Admins are excluded: operational authority is not clinical authority.

        See docs/security/rbac-and-audit.md §3. An administrator can see that a ward is
        full without being able to read why any individual patient is in it.
        """
        return self.role in {UserRole.DOCTOR, UserRole.NURSE}


def get_request_context(request: Request) -> RequestContext:
    client_ip = request.headers.get("x-forwarded-for", "").split(",")[0].strip() or (
        request.client.host if request.client else None
    )
    return RequestContext(
        request_id=getattr(request.state, "request_id", None),
        ip_hash=hash_for_audit(client_ip),
        user_agent_hash=hash_for_audit(request.headers.get("user-agent")),
    )


RequestCtx = Annotated[RequestContext, Depends(get_request_context)]


def _bearer_token(request: Request) -> str | None:
    header = request.headers.get("authorization")
    if not header:
        return None
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        return None
    return token.strip()


async def get_current_principal(request: Request) -> Principal:
    """Resolve the caller from the Bearer token, or reject.

    The token's signature and expiry are verified here. Whether the *account* is still
    active is re-checked by `get_current_user` for routes that need it, because a token
    stays valid for its full lifetime even if the account is disabled a moment after
    issue.
    """
    token = _bearer_token(request)
    if token is None:
        raise AuthenticationRequired()

    payload = decode_access_token(token)

    try:
        user_id = uuid.UUID(payload["sub"])
        role = UserRole(payload["role"])
    except (KeyError, ValueError) as exc:
        raise AuthenticationRequired() from exc

    return Principal(
        user_id=user_id,
        role=role,
        patient_id=uuid.UUID(payload["pid"]) if payload.get("pid") else None,
        staff_id=uuid.UUID(payload["sid"]) if payload.get("sid") else None,
    )


CurrentPrincipal = Annotated[Principal, Depends(get_current_principal)]


async def get_verified_principal(principal: CurrentPrincipal, session: DbSession) -> Principal:
    """As above, but confirms the account is still active in the database.

    Used on state-changing and clinical routes. The extra query is the price of being able
    to disable an account and have it take effect before the access token expires.
    """
    from app.repositories.user import UserRepository

    user = await UserRepository(session).get_active_by_id(principal.user_id)
    if user is None:
        raise AuthenticationRequired()
    if user.role is not principal.role:
        # Role changed since the token was issued; the token's claim is stale.
        raise AuthenticationRequired()
    return principal


VerifiedPrincipal = Annotated[Principal, Depends(get_verified_principal)]


def require_roles(
    *allowed: UserRole,
) -> Callable[..., Coroutine[Any, Any, Principal]]:
    """Restrict a route to the given roles.

    Denials are audited. A pattern of PERMISSION_DENIED events for one actor is one of the
    few reliable signals of either a compromised account or a broken client.
    """
    allowed_set = frozenset(allowed)

    async def dependency(
        principal: VerifiedPrincipal, session: DbSession, context: RequestCtx
    ) -> Principal:
        if principal.role not in allowed_set:
            from app.models.audit import AuditAction
            from app.models.base import AuditResult
            from app.services.audit import AuditService

            await AuditService(session).record(
                action=AuditAction.PERMISSION_DENIED,
                result=AuditResult.DENIED,
                actor_user_id=principal.user_id,
                actor_role=principal.role,
                request_id=context.request_id,
                ip_hash=context.ip_hash,
                metadata={"requiredRoles": sorted(role.value for role in allowed_set)},
            )
            await session.commit()
            raise PermissionDenied()
        return principal

    return dependency


RequireAdmin = Annotated[Principal, Depends(require_roles(UserRole.ADMIN))]
RequireClinician = Annotated[Principal, Depends(require_roles(UserRole.DOCTOR, UserRole.NURSE))]
RequirePatient = Annotated[Principal, Depends(require_roles(UserRole.PATIENT))]
RequireStaff = Annotated[
    Principal, Depends(require_roles(UserRole.DOCTOR, UserRole.NURSE, UserRole.ADMIN))
]


def rate_limit(limit: RateLimit, *, scope: str) -> Callable[..., Coroutine[Any, Any, None]]:
    """Apply a rate limit keyed by client identity.

    Keyed on the hashed client IP for anonymous routes. This is coarse behind a shared
    NAT, which is the accepted trade-off: the alternative - keying on the submitted email -
    lets an attacker spread an attack across addresses for free.
    """

    async def dependency(request: Request, context: RequestCtx) -> None:
        key = f"{scope}:{context.ip_hash or 'unknown'}"
        verdict = await get_rate_limiter().check(key, limit)
        if not verdict.allowed:
            logger.warning(
                "rate_limit_exceeded",
                extra={"scope": scope, "request_id": context.request_id},
            )
            raise RateLimited(
                headers={"Retry-After": str(verdict.retry_after_seconds)},
            )

    return dependency


async def anonymous_rate_limit(request: Request, context: RequestCtx) -> None:
    await rate_limit(ANONYMOUS_LIMIT, scope="anon")(request, context)


async def authenticated_rate_limit(request: Request, context: RequestCtx) -> None:
    await rate_limit(AUTHENTICATED_LIMIT, scope="auth")(request, context)


async def db_transaction(session: DbSession) -> AsyncIterator[AsyncSession]:
    """Commit on success, roll back on any exception.

    Routes should not call commit themselves. Centralising it here is what makes the
    audit entry and the action it describes succeed or fail together.
    """
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise


TransactionalSession = Annotated[AsyncSession, Depends(db_transaction)]
