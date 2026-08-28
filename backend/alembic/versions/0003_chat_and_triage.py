"""Migration 003: chat sessions, messages and triage results.

Two storage decisions here carry the safety and privacy properties:

  1. `chat_messages.content` holds text a patient typed about their health. It is the most
     sensitive free text in the system, so the redaction and retention rules apply to it
     rather than to a copy of it somewhere else. It is never duplicated into the audit log.

  2. `triage_results` keeps the engine's output and the engine's identity separately from
     any clinician decision about it. A clinician confirming or overriding a severity
     writes a new row's worth of state; the original band the engine produced is never
     edited, so "what did the system say, and what did the clinician decide" stays
     answerable after the fact.

Revision ID: 0003
Revises: 0002
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    session_status = postgresql.ENUM(
        "ACTIVE", "ESCALATED", "COMPLETED", "CLOSED", name="chat_session_status", schema="ai"
    )
    session_status.create(op.get_bind(), checkfirst=True)

    message_role = postgresql.ENUM("PATIENT", "ASSISTANT", "SYSTEM", name="chat_role", schema="ai")
    message_role.create(op.get_bind(), checkfirst=True)

    severity = postgresql.ENUM(
        "EMERGENCY",
        "URGENT",
        "SOON",
        "ROUTINE",
        "SELF_CARE",
        name="triage_severity",
        schema="ai",
    )
    severity.create(op.get_bind(), checkfirst=True)

    review_status = postgresql.ENUM(
        "PENDING_REVIEW",
        "CLINICIAN_CONFIRMED",
        "CLINICIAN_OVERRIDDEN",
        name="triage_review_status",
        schema="ai",
    )
    review_status.create(op.get_bind(), checkfirst=True)

    status_ref = postgresql.ENUM(name="chat_session_status", schema="ai", create_type=False)
    role_ref = postgresql.ENUM(name="chat_role", schema="ai", create_type=False)
    severity_ref = postgresql.ENUM(name="triage_severity", schema="ai", create_type=False)
    review_ref = postgresql.ENUM(name="triage_review_status", schema="ai", create_type=False)

    # --- ai.chat_sessions -----------------------------------------------------
    op.create_table(
        "chat_sessions",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "patient_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("clinical.patients.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("status", status_ref, nullable=False, server_default="ACTIVE"),
        sa.Column("locale", sa.String(10), nullable=False, server_default="en-GB"),
        # Which step of the scripted intake the conversation is on. Stored rather than
        # inferred from the messages, so a change to the script cannot silently reinterpret
        # a conversation that is already in progress.
        sa.Column("stage", sa.String(40), nullable=False, server_default="OPENING"),
        sa.Column("escalated_at", sa.DateTime(timezone=True)),
        sa.Column("escalation_reason", sa.String(200)),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("ended_at", sa.DateTime(timezone=True)),
        schema="ai",
    )
    op.create_index(
        "ix_chat_sessions_patient", "chat_sessions", ["patient_id", "started_at"], schema="ai"
    )
    op.create_index(
        "ix_chat_sessions_escalated",
        "chat_sessions",
        ["escalated_at"],
        schema="ai",
        postgresql_where=sa.text("status = 'ESCALATED'"),
    )

    # --- ai.chat_messages -----------------------------------------------------
    op.create_table(
        "chat_messages",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "session_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("ai.chat_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role", role_ref, nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        # Which component produced an assistant turn. Null for patient messages. Makes
        # "what said this" answerable when the rule engine is later replaced by a model.
        sa.Column("produced_by", sa.String(60)),
        # Red flags matched on this turn, for clinician review. Terms, not free text.
        sa.Column("safety_flags", postgresql.ARRAY(sa.String(60))),
        # clock_timestamp(), not now(). now() returns the *transaction* start time, so every
        # message written during one request would share a timestamp and the transcript
        # would order by a random uuid - rendering the answer before the question. This is
        # the one table whose row order is meaningful to a reader.
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("clock_timestamp()"),
        ),
        schema="ai",
    )
    op.create_index(
        "ix_chat_messages_session", "chat_messages", ["session_id", "created_at"], schema="ai"
    )

    # --- ai.triage_results ----------------------------------------------------
    op.create_table(
        "triage_results",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "patient_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("clinical.patients.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "session_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("ai.chat_sessions.id", ondelete="SET NULL"),
        ),
        # The engine that produced this and its version. Not decoration: a severity band
        # is meaningless for review without knowing what produced it.
        sa.Column("engine", sa.String(40), nullable=False),
        sa.Column("engine_version", sa.String(20), nullable=False),
        sa.Column("severity", severity_ref, nullable=False),
        sa.Column("confidence", sa.Numeric(4, 3)),
        sa.Column("red_flags", postgresql.ARRAY(sa.String(60))),
        sa.Column("contributing_factors", postgresql.JSONB()),
        sa.Column("recommended_action", sa.Text(), nullable=False),
        sa.Column("review_status", review_ref, nullable=False, server_default="PENDING_REVIEW"),
        sa.Column(
            "reviewed_by_staff_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("identity.staff.id"),
        ),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
        # A clinician's decision lives alongside the engine's output, never on top of it.
        # `severity` above is what the engine said and is never rewritten.
        sa.Column("clinician_severity", severity_ref),
        sa.Column("clinician_note", sa.Text()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        schema="ai",
    )
    op.create_index(
        "ix_triage_patient", "triage_results", ["patient_id", "created_at"], schema="ai"
    )
    op.create_index(
        "ix_triage_pending",
        "triage_results",
        ["created_at"],
        schema="ai",
        postgresql_where=sa.text("review_status = 'PENDING_REVIEW'"),
    )

    # The engine's own output is immutable, by the same reasoning as the audit trail: a
    # record of what the system said is worthless if it can be edited after the fact.
    # Clinician review columns stay writable.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION ai.prevent_triage_output_rewrite() RETURNS trigger AS $fn$
        BEGIN
            IF NEW.severity IS DISTINCT FROM OLD.severity
               OR NEW.engine IS DISTINCT FROM OLD.engine
               OR NEW.engine_version IS DISTINCT FROM OLD.engine_version
               OR NEW.red_flags IS DISTINCT FROM OLD.red_flags
               OR NEW.recommended_action IS DISTINCT FROM OLD.recommended_action THEN
                RAISE EXCEPTION
                    'the triage engine output is immutable; record a clinician decision in '
                    'clinician_severity instead'
                    USING ERRCODE = 'integrity_constraint_violation';
            END IF;
            RETURN NEW;
        END
        $fn$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_triage_output_immutable
            BEFORE UPDATE ON ai.triage_results
            FOR EACH ROW EXECUTE FUNCTION ai.prevent_triage_output_rewrite();
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_triage_output_immutable ON ai.triage_results")
    op.execute("DROP FUNCTION IF EXISTS ai.prevent_triage_output_rewrite()")
    op.drop_table("triage_results", schema="ai")
    op.drop_table("chat_messages", schema="ai")
    op.drop_table("chat_sessions", schema="ai")
    op.execute("DROP TYPE IF EXISTS ai.triage_review_status")
    op.execute("DROP TYPE IF EXISTS ai.triage_severity")
    op.execute("DROP TYPE IF EXISTS ai.chat_role")
    op.execute("DROP TYPE IF EXISTS ai.chat_session_status")
