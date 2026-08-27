"""Clinical models (FHIR-shaped).

These borrow FHIR resource boundaries and field names so the mapping in FHIRService is
mechanical. They are **not** conformance-tested against UK Core, and no conformance is
claimed. See ASSUMPTIONS.md non-claims.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, ForeignKey, Index, String, text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin


class Patient(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "patients"
    __table_args__ = (
        CheckConstraint(
            "nhs_number IS NULL OR nhs_number ~ '^[0-9]{10}$'",
            name="ck_patient_nhs_number_format",
        ),
        Index(
            "ix_patients_name_dob",
            "family_name",
            "date_of_birth",
            postgresql_where=text("deleted_at IS NULL"),
        ),
        {"schema": "clinical"},
    )

    user_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("identity.users.id"), unique=True
    )

    # Nullable: a patient can self-register before their NHS number is verified. Making it
    # NOT NULL would force us to invent one at registration, which is the exact failure
    # mode the brief warns against (§7).
    nhs_number: Mapped[str | None] = mapped_column(String(10), unique=True)

    given_name: Mapped[str] = mapped_column(String(100), nullable=False)
    family_name: Mapped[str] = mapped_column(String(100), nullable=False)
    date_of_birth: Mapped[date] = mapped_column(Date, nullable=False)
    sex_at_birth: Mapped[str | None] = mapped_column(String(30))
    gender_identity: Mapped[str | None] = mapped_column(String(60))

    phone_e164: Mapped[str | None] = mapped_column(String(20))
    email: Mapped[str | None] = mapped_column(String(320))
    address_line1: Mapped[str | None] = mapped_column(String(200))
    address_line2: Mapped[str | None] = mapped_column(String(200))
    city: Mapped[str | None] = mapped_column(String(100))
    postcode: Mapped[str | None] = mapped_column(String(10))

    preferred_language: Mapped[str] = mapped_column(
        String(10), nullable=False, server_default="en-GB"
    )
    # Stored because the staff UI must surface these prominently. A reasonable-adjustments
    # flag nobody sees is not a reasonable adjustment.
    interpreter_needed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    accessibility_needs: Mapped[list[str] | None] = mapped_column(ARRAY(String(60)))

    data_origin: Mapped[str] = mapped_column(String(20), nullable=False, server_default="SYNTHETIC")
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    @property
    def display_name(self) -> str:
        return f"{self.given_name} {self.family_name}"
