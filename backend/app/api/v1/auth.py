"""Authentication routes.

Contract: docs/api/api-contract-v1.md §2.

The refresh token travels as an httpOnly cookie rather than in the response body, so page
JavaScript cannot read it. That is what keeps a single XSS from yielding a durable
session rather than a 15-minute one.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, Request, Response, status

from app.core.config import get_settings
from app.core.deps import (
    CurrentPrincipal,
    RequestCtx,
    TransactionalSession,
    rate_limit,
)
from app.core.errors import AuthenticationRequired, ErrorResponse
from app.core.logging import get_logger
from app.core.ratelimit import LOGIN_LIMIT, PASSWORD_RESET_LIMIT, REGISTRATION_LIMIT
from app.repositories.user import UserRepository
from app.schemas.auth import (
    LoginRequest,
    LoginResponse,
    MessageResponse,
    PasswordResetConfirm,
    PasswordResetRequest,
    RefreshResponse,
    RegisterRequest,
    RegisterResponse,
    UserSummary,
)
from app.services.auth import AuthService, IssuedSession

router = APIRouter(prefix="/auth", tags=["Authentication"])
logger = get_logger(__name__)

REFRESH_COOKIE_NAME = "refresh_token"

# Scoped to the refresh and logout paths only. A cookie sent on every request would be
# exposed far more widely than it needs to be.
REFRESH_COOKIE_PATH = "/api/v1/auth"

_ERRORS: dict[int | str, dict[str, object]] = {
    400: {"model": ErrorResponse, "description": "Validation failed"},
    401: {"model": ErrorResponse, "description": "Authentication failed"},
    429: {"model": ErrorResponse, "description": "Rate limit exceeded"},
}


def _set_refresh_cookie(response: Response, session: IssuedSession) -> None:
    settings = get_settings()
    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=session.refresh_token,
        httponly=True,
        # Not sent on cross-site requests, which is the primary CSRF control for this
        # cookie. The state-changing routes that use it are POSTs to our own origin.
        samesite="lax",
        secure=settings.cookie_secure,
        path=REFRESH_COOKIE_PATH,
        max_age=settings.refresh_token_ttl_days * 24 * 60 * 60,
    )


def _clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(key=REFRESH_COOKIE_NAME, path=REFRESH_COOKIE_PATH)


@router.post(
    "/register",
    response_model=RegisterResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a patient account",
    responses=_ERRORS,
    dependencies=[Depends(rate_limit(REGISTRATION_LIMIT, scope="register"))],
)
async def register(
    payload: RegisterRequest, session: TransactionalSession, context: RequestCtx
) -> RegisterResponse:
    """Create a patient account.

    Patients only. Staff and admin accounts are provisioned administratively, never
    through a public endpoint.
    """
    user, patient = await AuthService(session).register_patient(payload, context)
    return RegisterResponse(
        user_id=user.id, patient_id=patient.id, email=user.email, role="PATIENT"
    )


@router.post(
    "/login",
    response_model=LoginResponse,
    summary="Sign in",
    responses=_ERRORS,
    dependencies=[Depends(rate_limit(LOGIN_LIMIT, scope="login"))],
)
async def login(
    payload: LoginRequest,
    response: Response,
    session: TransactionalSession,
    context: RequestCtx,
) -> LoginResponse:
    issued = await AuthService(session).authenticate(payload.email, payload.password, context)
    _set_refresh_cookie(response, issued)
    return LoginResponse(
        access_token=issued.access_token, expires_in=issued.expires_in, user=issued.user
    )


@router.post(
    "/refresh",
    response_model=RefreshResponse,
    summary="Exchange a refresh token for a new access token",
    responses=_ERRORS,
)
async def refresh(
    request: Request,
    response: Response,
    session: TransactionalSession,
    context: RequestCtx,
    refresh_token: Annotated[str | None, Cookie(alias=REFRESH_COOKIE_NAME)] = None,
) -> RefreshResponse:
    """Rotate the session.

    The old refresh token is revoked and a new one issued. Presenting a token that has
    already been rotated revokes every session for that user - see AuthService.refresh.
    """
    raw = refresh_token or request.cookies.get(REFRESH_COOKIE_NAME)
    if not raw:
        raise AuthenticationRequired("Your session has expired. Please sign in again.")

    issued = await AuthService(session).refresh(raw, context)
    _set_refresh_cookie(response, issued)
    return RefreshResponse(access_token=issued.access_token, expires_in=issued.expires_in)


@router.post(
    "/logout",
    response_model=MessageResponse,
    summary="Sign out",
)
async def logout(
    request: Request,
    response: Response,
    session: TransactionalSession,
    context: RequestCtx,
    refresh_token: Annotated[str | None, Cookie(alias=REFRESH_COOKIE_NAME)] = None,
) -> MessageResponse:
    """Idempotent: signing out twice is not an error, and an absent cookie is not either."""
    await AuthService(session).logout(
        refresh_token or request.cookies.get(REFRESH_COOKIE_NAME), context
    )
    _clear_refresh_cookie(response)
    return MessageResponse(message="You have been signed out.")


@router.post(
    "/password-reset",
    response_model=MessageResponse,
    summary="Request a password reset link",
    responses=_ERRORS,
    dependencies=[Depends(rate_limit(PASSWORD_RESET_LIMIT, scope="pwreset"))],
)
async def request_password_reset(
    payload: PasswordResetRequest, session: TransactionalSession, context: RequestCtx
) -> MessageResponse:
    """Always returns the same message.

    Responding differently for a known and an unknown address would turn this endpoint
    into an account-enumeration oracle, which for a hospital reveals that a person is a
    patient here - a disclosure in itself, regardless of any clinical detail.
    """
    raw_token = await AuthService(session).request_password_reset(payload.email, context)

    if raw_token is not None:
        # Sprint 2 hands this to the notification outbox. Until then it is logged at debug
        # level in development only, and never returned in the response.
        logger.debug(
            "password_reset_token_issued",
            extra={"request_id": context.request_id},
        )

    return MessageResponse(
        message="If that email address has an account, we have sent a reset link to it."
    )


@router.post(
    "/password-reset/confirm",
    response_model=MessageResponse,
    summary="Set a new password using a reset token",
    responses=_ERRORS,
)
async def confirm_password_reset(
    payload: PasswordResetConfirm,
    response: Response,
    session: TransactionalSession,
    context: RequestCtx,
) -> MessageResponse:
    await AuthService(session).confirm_password_reset(payload.token, payload.new_password, context)
    _clear_refresh_cookie(response)
    return MessageResponse(
        message="Your password has been changed. Please sign in with your new password."
    )


@router.get(
    "/me",
    response_model=UserSummary,
    summary="The signed-in user",
    responses={401: _ERRORS[401]},
)
async def me(principal: CurrentPrincipal, session: TransactionalSession) -> UserSummary:
    user = await UserRepository(session).get_active_by_id(principal.user_id)
    if user is None:
        # Token still valid but the account was disabled or deleted since it was issued.
        raise AuthenticationRequired()
    return await AuthService(session).build_summary(user)
