"""Authentication request and response schemas.

These are the contract in docs/api/api-contract-v1.md §2. Note what is absent: no schema
here accepts a `role` field. Role is assigned by the server, never by the client.
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import Annotated, Literal

from pydantic import Field, field_validator

from app.schemas.base import CamelModel
from app.schemas.fields import EmailAddress
from app.utils import nhs_number as nhs

# 12 characters minimum. NCSC guidance favours length over composition rules, which push
# people toward predictable substitutions (P@ssw0rd1) without adding real entropy.
Password = Annotated[str, Field(min_length=12, max_length=128)]


class RegisterRequest(CamelModel):
    email: EmailAddress
    password: Password
    given_name: Annotated[str, Field(min_length=1, max_length=100)]
    family_name: Annotated[str, Field(min_length=1, max_length=100)]
    date_of_birth: date
    nhs_number: Annotated[str, Field(max_length=14)] | None = None
    preferred_language: Annotated[str, Field(max_length=10)] = "en-GB"

    @field_validator("nhs_number")
    @classmethod
    def _validate_nhs_number(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        normalised = nhs.normalise(value)
        if not nhs.is_valid(normalised):
            raise ValueError("nhs_number_invalid")
        return normalised

    @field_validator("date_of_birth")
    @classmethod
    def _validate_dob(cls, value: date) -> date:
        from datetime import date as date_type

        if value > date_type.today():
            raise ValueError("date_of_birth_in_future")
        if value.year < 1900:
            raise ValueError("date_of_birth_implausible")
        return value


class RegisterResponse(CamelModel):
    user_id: uuid.UUID
    patient_id: uuid.UUID
    email: str
    role: Literal["PATIENT"]


class LoginRequest(CamelModel):
    email: EmailAddress
    password: Annotated[str, Field(min_length=1, max_length=128)]


class UserSummary(CamelModel):
    id: uuid.UUID
    email: str
    role: str
    display_name: str
    patient_id: uuid.UUID | None = None
    staff_id: uuid.UUID | None = None
    #: The patient's stored language preference, so the interface follows them between
    #: devices rather than living in one browser. Null for staff, who work in English.
    preferred_language: str | None = None


class LoginResponse(CamelModel):
    """The refresh token is deliberately absent.

    It is set as an httpOnly cookie so page JavaScript cannot read it. Returning it in
    the body would put it within reach of any XSS and defeat the point of the split.
    """

    access_token: str
    token_type: Literal["Bearer"] = "Bearer"
    expires_in: int
    user: UserSummary


class RefreshResponse(CamelModel):
    access_token: str
    token_type: Literal["Bearer"] = "Bearer"
    expires_in: int


class PasswordResetRequest(CamelModel):
    email: EmailAddress


class PasswordResetConfirm(CamelModel):
    token: Annotated[str, Field(min_length=16, max_length=128)]
    new_password: Password


class MessageResponse(CamelModel):
    message: str
