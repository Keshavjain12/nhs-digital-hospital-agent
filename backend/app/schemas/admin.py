"""Administrator view schemas.

Nothing here carries a patient identity. `AuditEntry.resource_id` stays an opaque
identifier so an administrator can see *that* a record was accessed without learning
whose it was.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from app.schemas.base import CamelModel, PageMeta, ResponseMeta


class KpiCard(CamelModel):
    key: str
    label: str
    value: int
    caption: str
    # Drives an icon and a text label as well as colour, never colour alone.
    tone: Literal["neutral", "attention"] = "neutral"


class DepartmentSummary(CamelModel):
    id: uuid.UUID
    code: str
    name: str
    data_origin: str


class OverviewResponse(CamelModel):
    cards: list[KpiCard]
    departments: list[DepartmentSummary]
    meta: ResponseMeta


class AuditEntry(CamelModel):
    id: int
    action: str
    result: str
    actor: str
    actor_role: str | None
    resource_type: str | None
    resource_id: str | None
    metadata: dict[str, Any]
    occurred_at: datetime


class AuditListResponse(CamelModel):
    items: list[AuditEntry]
    meta: PageMeta
