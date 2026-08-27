"""Application errors and the single error envelope.

Implements the contract in docs/api/api-contract-v1.md §1. Two rules hold throughout:

1. Every error the client sees is one of these classes. Nothing else reaches the wire.
2. `message` is always safe to display verbatim to an end user. Stack traces, SQL,
   file paths and internal identifiers stay in the server log (brief §11, §17).
"""

from __future__ import annotations

from typing import Any, cast

from fastapi import Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.schemas.base import CamelModel


class ErrorDetail(CamelModel):
    field: str
    issue: str


class ErrorBody(CamelModel):
    code: str
    message: str
    details: list[ErrorDetail] | None = None
    request_id: str | None = None  # serialised as "requestId"


class ErrorResponse(CamelModel):
    error: ErrorBody


class AppError(Exception):
    """Base class for every error that is allowed to reach a client."""

    status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR
    code: str = "INTERNAL_ERROR"
    message: str = "Something went wrong. Please try again."

    def __init__(
        self,
        message: str | None = None,
        *,
        details: list[ErrorDetail] | None = None,
        headers: dict[str, str] | None = None,
        log_context: dict[str, Any] | None = None,
    ) -> None:
        self.message = message or self.message
        self.details = details
        self.headers = headers
        # Server-side only. Never serialised into the response.
        self.log_context = log_context or {}
        super().__init__(self.message)


# --- 4xx ---------------------------------------------------------------------


class ValidationFailed(AppError):
    status_code = status.HTTP_400_BAD_REQUEST
    code = "VALIDATION_ERROR"
    message = "Some of the information provided is not valid."


class AuthenticationRequired(AppError):
    status_code = status.HTTP_401_UNAUTHORIZED
    code = "AUTHENTICATION_REQUIRED"
    message = "You need to sign in to continue."


class TokenExpired(AppError):
    status_code = status.HTTP_401_UNAUTHORIZED
    code = "TOKEN_EXPIRED"
    message = "Your session has expired. Please sign in again."


class PermissionDenied(AppError):
    status_code = status.HTTP_403_FORBIDDEN
    code = "PERMISSION_DENIED"
    message = "You do not have permission to do that."

    def __init__(self, *args: Any, hint: str | None = None, **kwargs: Any) -> None:
        """`hint` lets the frontend offer a next step (e.g. the break-glass dialog).

        It deliberately carries no information about the resource itself.
        """
        super().__init__(*args, **kwargs)
        self.hint = hint


class ResourceNotFound(AppError):
    """Also returned when a resource exists but is not visible to this principal.

    Returning 403 there would confirm the resource exists, which leaks the existence of a
    patient record to anyone able to guess an identifier. See rbac-and-audit.md §1.
    """

    status_code = status.HTTP_404_NOT_FOUND
    code = "RESOURCE_NOT_FOUND"
    message = "We could not find what you were looking for."


class AppointmentConflict(AppError):
    status_code = status.HTTP_409_CONFLICT
    code = "APPOINTMENT_CONFLICT"
    message = "The selected appointment slot is no longer available."


class SlotHoldExpired(AppError):
    status_code = status.HTTP_409_CONFLICT
    code = "SLOT_HOLD_EXPIRED"
    message = "Your reserved time has expired. Please choose a slot again."


class InvalidStateTransition(AppError):
    status_code = status.HTTP_409_CONFLICT
    code = "INVALID_STATE_TRANSITION"
    message = "That action is not possible for the current status."


class NhsNumberInvalid(AppError):
    status_code = 422  # Unprocessable Content
    code = "NHS_NUMBER_INVALID"
    message = "That NHS number is not valid. Please check and try again."


class RateLimited(AppError):
    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    code = "RATE_LIMITED"
    message = "Too many attempts. Please wait a moment and try again."


# --- 5xx ---------------------------------------------------------------------


class UpstreamUnavailable(AppError):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    code = "UPSTREAM_UNAVAILABLE"
    message = "That service is temporarily unavailable. Please try again shortly."


class InternalError(AppError):
    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    code = "INTERNAL_ERROR"
    message = "Something went wrong. Please try again."


# --- Rendering ---------------------------------------------------------------


# Applied here as well as in SecurityHeadersMiddleware. Starlette's ServerErrorMiddleware
# sits outside the application middleware stack, so a 500 response is returned without
# passing back through it. Setting these at the render layer means every error response
# carries them regardless of where in the stack the failure occurred.
_ERROR_RESPONSE_HEADERS: dict[str, str] = {
    "Cache-Control": "no-store",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
}


def render_error(
    *,
    code: str,
    message: str,
    status_code: int,
    request_id: str | None = None,
    details: list[ErrorDetail] | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    body = ErrorResponse(
        error=ErrorBody(code=code, message=message, details=details, request_id=request_id)
    )
    response_headers = dict(_ERROR_RESPONSE_HEADERS)
    if request_id:
        # The one piece of correlation a user can quote back to us.
        response_headers["X-Request-ID"] = request_id
    response_headers.update(headers or {})

    return JSONResponse(
        status_code=status_code,
        content=body.model_dump(mode="json", by_alias=True, exclude_none=True),
        headers=response_headers,
    )


def _request_id(request: Request) -> str | None:
    return getattr(request.state, "request_id", None)


async def app_error_handler(request: Request, exc: Exception) -> JSONResponse:
    # Registered only for AppError; cast rather than assert, since `python -O` strips
    # asserts and an exception handler must never depend on a statement that can vanish.
    error = cast(AppError, exc)
    headers = dict(error.headers or {})
    if isinstance(error, PermissionDenied) and error.hint:
        headers["X-Permission-Hint"] = error.hint
    return render_error(
        code=error.code,
        message=error.message,
        status_code=error.status_code,
        request_id=_request_id(request),
        details=error.details,
        headers=headers or None,
    )


async def validation_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """Translate Pydantic's validation output into our envelope.

    Pydantic's raw errors include input values, which for this application can mean
    passwords and clinical free text. Only the field location and the error type are
    forwarded; the offending value never leaves the process.
    """
    validation_error = cast(RequestValidationError, exc)
    details = [
        ErrorDetail(
            field=".".join(str(part) for part in error["loc"][1:]) or str(error["loc"][0]),
            issue=str(error["type"]),
        )
        for error in validation_error.errors()
    ]
    return render_error(
        code=ValidationFailed.code,
        message=ValidationFailed.message,
        status_code=status.HTTP_400_BAD_REQUEST,
        request_id=_request_id(request),
        details=details,
    )


async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """Last line of defence.

    Anything reaching here is a bug. It is logged with full detail and returned to the
    client as a bare INTERNAL_ERROR carrying only the request id, so a user reporting a
    problem can be correlated to the log entry without the response revealing anything.
    """
    from app.core.logging import get_logger

    get_logger(__name__).exception(
        "unhandled_exception",
        extra={"request_id": _request_id(request), "path": request.url.path},
    )
    return render_error(
        code=InternalError.code,
        message=InternalError.message,
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        request_id=_request_id(request),
    )
