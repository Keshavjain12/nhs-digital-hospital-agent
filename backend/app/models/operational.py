"""Operational models.

Migration 001 covers only sites and departments, which staff records depend on.
Slots, appointments, beds and notifications arrive in migration 002 (Sprint 2).
"""

from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.base import UUIDPrimaryKeyMixin


class Site(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "sites"
    __table_args__ = {"schema": "operational"}

    code: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    address_line1: Mapped[str | None] = mapped_column(String(200))
    city: Mapped[str | None] = mapped_column(String(100))
    postcode: Mapped[str | None] = mapped_column(String(10))
    data_origin: Mapped[str] = mapped_column(String(20), nullable=False, server_default="SYNTHETIC")


class Department(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "departments"
    __table_args__ = {"schema": "operational"}

    site_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("operational.sites.id"), nullable=False
    )
    code: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    specialty_snomed: Mapped[str | None] = mapped_column(String(20))
    data_origin: Mapped[str] = mapped_column(String(20), nullable=False, server_default="SYNTHETIC")
