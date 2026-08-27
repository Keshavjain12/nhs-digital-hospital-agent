"""ORM models. Imported here so Alembic's autogenerate sees every table."""

from app.models.audit import AuditAction, AuditLog
from app.models.base import (
    AuditResult,
    DataOrigin,
    TimestampMixin,
    UserRole,
    UserStatus,
    UUIDPrimaryKeyMixin,
)
from app.models.clinical import Patient
from app.models.identity import (
    BreakglassGrant,
    CareAssignment,
    PasswordResetToken,
    RefreshToken,
    Staff,
    User,
)
from app.models.operational import Department, Site
from app.models.scheduling import (
    Appointment,
    AppointmentPriority,
    AppointmentSlot,
    AppointmentStatus,
    SlotHold,
    SlotStatus,
    SlotType,
)

__all__ = [
    "Appointment",
    "AppointmentPriority",
    "AppointmentSlot",
    "AppointmentStatus",
    "AuditAction",
    "AuditLog",
    "AuditResult",
    "BreakglassGrant",
    "CareAssignment",
    "DataOrigin",
    "Department",
    "PasswordResetToken",
    "Patient",
    "RefreshToken",
    "Site",
    "SlotHold",
    "SlotStatus",
    "SlotType",
    "Staff",
    "TimestampMixin",
    "UUIDPrimaryKeyMixin",
    "User",
    "UserRole",
    "UserStatus",
]
