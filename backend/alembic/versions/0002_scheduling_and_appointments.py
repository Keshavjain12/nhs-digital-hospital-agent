"""Migration 002: slots, holds and appointments.

The three constraints here are what make booking correct. They are database constraints
rather than application checks on purpose: an application check can be bypassed by a
second process running the same check at the same moment, and the booking race is exactly
that scenario.

  1. uq_appointment_active_slot - a partial unique index on the slot of any appointment in
     a live state. Two concurrent bookings for one slot cannot both commit; the loser gets
     a unique-violation the service turns into 409 APPOINTMENT_CONFLICT.

  2. ex_slot_no_staff_overlap - a GiST exclusion constraint stopping two slots for the same
     clinician from overlapping in time. Prevents building an impossible timetable in the
     first place.

  3. uq_slot_hold_one_per_slot - one live hold per slot, so two patients cannot both be
     told a slot is theirs while they finish choosing.

Revision ID: 0002
Revises: 0001
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

LIVE_APPOINTMENT_STATES = "'BOOKED', 'CHECKED_IN', 'IN_PROGRESS'"


def upgrade() -> None:
    # --- Enums ---------------------------------------------------------------
    slot_status = postgresql.ENUM("AVAILABLE", "BLOCKED", name="slot_status", schema="operational")
    slot_status.create(op.get_bind(), checkfirst=True)

    slot_type = postgresql.ENUM(
        "ROUTINE", "URGENT", "FOLLOW_UP", "TELEPHONE", name="slot_type", schema="operational"
    )
    slot_type.create(op.get_bind(), checkfirst=True)

    appointment_status = postgresql.ENUM(
        "BOOKED",
        "CHECKED_IN",
        "IN_PROGRESS",
        "COMPLETED",
        "CANCELLED",
        "DID_NOT_ATTEND",
        name="appointment_status",
        schema="operational",
    )
    appointment_status.create(op.get_bind(), checkfirst=True)

    priority = postgresql.ENUM(
        "EMERGENCY", "URGENT", "SOON", "ROUTINE", name="appointment_priority", schema="operational"
    )
    priority.create(op.get_bind(), checkfirst=True)

    slot_status_ref = postgresql.ENUM(name="slot_status", schema="operational", create_type=False)
    slot_type_ref = postgresql.ENUM(name="slot_type", schema="operational", create_type=False)
    appt_status_ref = postgresql.ENUM(
        name="appointment_status", schema="operational", create_type=False
    )
    priority_ref = postgresql.ENUM(
        name="appointment_priority", schema="operational", create_type=False
    )

    # --- operational.appointment_slots ---------------------------------------
    op.create_table(
        "appointment_slots",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "department_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("operational.departments.id"),
            nullable=False,
        ),
        sa.Column("staff_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("identity.staff.id")),
        sa.Column(
            "site_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("operational.sites.id"),
            nullable=False,
        ),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("slot_type", slot_type_ref, nullable=False, server_default="ROUTINE"),
        sa.Column("status", slot_status_ref, nullable=False, server_default="AVAILABLE"),
        sa.Column("data_origin", sa.String(20), nullable=False, server_default="SYNTHETIC"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint("ends_at > starts_at", name="ck_slot_ends_after_start"),
        schema="operational",
    )

    # Finding free slots is the hottest query in the system, so the index covers exactly
    # that predicate rather than the whole table.
    op.create_index(
        "ix_slots_open_by_department",
        "appointment_slots",
        ["department_id", "starts_at"],
        schema="operational",
        postgresql_where=sa.text("status = 'AVAILABLE'"),
    )
    op.create_index("ix_slots_starts_at", "appointment_slots", ["starts_at"], schema="operational")

    # Constraint 2. Requires btree_gist (enabled in migration 001) for the uuid equality
    # operator. A clinician cannot be in two places at once, so the timetable must not be
    # able to say they are.
    op.execute(
        """
        ALTER TABLE operational.appointment_slots
        ADD CONSTRAINT ex_slot_no_staff_overlap
        EXCLUDE USING gist (
            staff_id WITH =,
            tstzrange(starts_at, ends_at) WITH &&
        )
        WHERE (status <> 'BLOCKED' AND staff_id IS NOT NULL)
        """
    )

    # --- operational.slot_holds ----------------------------------------------
    # A short soft reservation while a patient confirms. Constraint 3 is the plain UNIQUE
    # on slot_id: expiry is enforced by the service, which deletes a lapsed hold before
    # taking a new one. `now()` cannot appear in an index predicate - it is not immutable -
    # so the rule lives in one place in the service rather than half here and half there.
    op.create_table(
        "slot_holds",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "slot_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("operational.appointment_slots.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column(
            "patient_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("clinical.patients.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        schema="operational",
    )
    op.create_index("ix_slot_holds_expiry", "slot_holds", ["expires_at"], schema="operational")

    # --- operational.appointments --------------------------------------------
    op.execute("CREATE SEQUENCE IF NOT EXISTS operational.appointment_reference_seq START 1000")

    op.create_table(
        "appointments",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        # Human-quotable on the phone. Generated by sequence so it is short and ordered,
        # unlike the uuid, which nobody can read aloud.
        sa.Column(
            "reference",
            sa.String(24),
            nullable=False,
            unique=True,
            server_default=sa.text(
                "'APT-' || to_char(now(), 'YYYY') || '-' || "
                "lpad(nextval('operational.appointment_reference_seq')::text, 6, '0')"
            ),
        ),
        sa.Column(
            "patient_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("clinical.patients.id"),
            nullable=False,
        ),
        sa.Column(
            "slot_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("operational.appointment_slots.id"),
            nullable=False,
        ),
        sa.Column(
            "department_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("operational.departments.id"),
            nullable=False,
        ),
        sa.Column("staff_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("identity.staff.id")),
        sa.Column("status", appt_status_ref, nullable=False, server_default="BOOKED"),
        sa.Column("priority", priority_ref),
        sa.Column("reason_text", sa.Text()),
        sa.Column(
            "booked_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("identity.users.id"),
            nullable=False,
        ),
        # A reschedule links the new appointment to the one it replaces, so the chain is
        # readable rather than looking like a cancellation next to an unrelated booking.
        sa.Column(
            "previous_appointment_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("operational.appointments.id"),
        ),
        sa.Column("cancelled_at", sa.DateTime(timezone=True)),
        sa.Column("cancellation_reason", sa.String(200)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        schema="operational",
    )

    # Constraint 1. THE booking guarantee.
    #
    # A slot can carry at most one appointment in a live state. Cancelled and
    # did-not-attend rows are excluded, so a cancelled slot can be rebooked while the
    # history of the cancellation survives.
    op.execute(
        f"""
        CREATE UNIQUE INDEX uq_appointment_active_slot
        ON operational.appointments (slot_id)
        WHERE status IN ({LIVE_APPOINTMENT_STATES})
        """
    )

    op.create_index(
        "ix_appointments_patient",
        "appointments",
        ["patient_id", "created_at"],
        schema="operational",
    )
    op.create_index(
        "ix_appointments_department_status",
        "appointments",
        ["department_id", "status"],
        schema="operational",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_appointments_department_status", table_name="appointments", schema="operational"
    )
    op.drop_index("ix_appointments_patient", table_name="appointments", schema="operational")
    op.execute("DROP INDEX IF EXISTS operational.uq_appointment_active_slot")
    op.drop_table("appointments", schema="operational")
    op.execute("DROP SEQUENCE IF EXISTS operational.appointment_reference_seq")

    op.drop_index("ix_slot_holds_expiry", table_name="slot_holds", schema="operational")
    op.drop_table("slot_holds", schema="operational")

    op.execute(
        "ALTER TABLE operational.appointment_slots DROP CONSTRAINT IF EXISTS ex_slot_no_staff_overlap"
    )
    op.drop_index("ix_slots_starts_at", table_name="appointment_slots", schema="operational")
    op.drop_index(
        "ix_slots_open_by_department", table_name="appointment_slots", schema="operational"
    )
    op.drop_table("appointment_slots", schema="operational")

    op.execute("DROP TYPE IF EXISTS operational.appointment_priority")
    op.execute("DROP TYPE IF EXISTS operational.appointment_status")
    op.execute("DROP TYPE IF EXISTS operational.slot_type")
    op.execute("DROP TYPE IF EXISTS operational.slot_status")
