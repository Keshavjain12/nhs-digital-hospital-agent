"""Patient and staff-queue schemas.

Note what a list row deliberately does *not* carry: no contact details, no address, no
clinical content. A search result is visible to any signed-in clinician, so it holds only
what is needed to identify the right person. Detail requires opening the record, which is
separately authorised and separately audited.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from app.schemas.base import CamelModel, PageMeta


class PatientListItem(CamelModel):
    id: uuid.UUID
    given_name: str
    family_name: str
    nhs_number: str | None
    date_of_birth: date
    age: int
    interpreter_needed: bool
    preferred_language: str
    data_origin: str
    # Whether this clinician has a care relationship with the patient. Drives the UI's
    # "assigned to you" marker and whether opening the record needs break-glass.
    assigned_to_me: bool


class PatientSummary(CamelModel):
    id: uuid.UUID
    given_name: str
    family_name: str
    nhs_number: str | None
    date_of_birth: date
    age: int
    sex_at_birth: str | None
    email: str | None
    phone_e164: str | None
    address_line1: str | None
    city: str | None
    postcode: str | None
    preferred_language: str
    interpreter_needed: bool
    accessibility_needs: list[str] | None
    data_origin: str
    registered_at: datetime


class PatientListResponse(CamelModel):
    items: list[PatientListItem]
    meta: PageMeta


class AccessBasis(CamelModel):
    """How this view was authorised. Shown in the UI so the clinician knows they are
    on the record under an emergency override rather than an ordinary assignment."""

    basis: str  # CARE_ASSIGNMENT | BREAKGLASS | SELF
    expires_at: datetime | None = None


class PatientDetailResponse(CamelModel):
    patient: PatientSummary
    access: AccessBasis


class BreakglassRequest(CamelModel):
    reason: str


class BreakglassResponse(CamelModel):
    granted_until: datetime
    message: str
