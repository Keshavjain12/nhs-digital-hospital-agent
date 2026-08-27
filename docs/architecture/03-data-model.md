# 03 — Data Model

Covers brief §41 part E. PostgreSQL 16. Types shown in SQL; ORM mapping is 1:1.

Design rules applied throughout:

1. **Do not store what we do not need.** UK GDPR data minimisation, and every stored field is a
   field that can leak.
2. **Append-only where a record must be defensible** — audit logs, AI documents, model overrides.
3. **Constraints in the database, not just the application.** Anything the application merely
   *promises* will eventually be broken by a refactor.
4. Only entities the project actually needs. Brief §10 lists candidates; several are omitted below
   with a reason.

---

## 1. Schema layout

| Schema | Contents | Access pattern |
|---|---|---|
| `identity` | users, tokens, staff, care assignments | Read-heavy, tiny |
| `clinical` | patients, encounters, observations, conditions, medications, allergies | Read-heavy, FHIR-shaped |
| `operational` | departments, sites, wards, beds, slots, appointments, notifications | Write-heavy, latency-sensitive |
| `ai` | chat, triage, risk scores, documents, model registry, overrides | Mixed |
| `audit` | audit_logs | Append-only, never updated or deleted |
| `analytics` | snapshots and materialised views | Read-heavy, may be slow; isolated so reports cannot slow booking |

---

## 2. Identity and access

```sql
CREATE TYPE user_role AS ENUM ('PATIENT','NURSE','DOCTOR','ADMIN');
CREATE TYPE user_status AS ENUM ('ACTIVE','LOCKED','DISABLED');

CREATE TABLE identity.users (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    email           citext NOT NULL UNIQUE,
    password_hash   text NOT NULL,                  -- argon2id
    role            user_role NOT NULL,
    status          user_status NOT NULL DEFAULT 'ACTIVE',
    failed_logins   smallint NOT NULL DEFAULT 0,
    locked_until    timestamptz,
    last_login_at   timestamptz,
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE identity.refresh_tokens (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         uuid NOT NULL REFERENCES identity.users(id) ON DELETE CASCADE,
    token_hash      text NOT NULL UNIQUE,           -- SHA-256; plaintext never stored
    expires_at      timestamptz NOT NULL,
    revoked_at      timestamptz,
    replaced_by     uuid REFERENCES identity.refresh_tokens(id),
    created_at      timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ON identity.refresh_tokens (user_id) WHERE revoked_at IS NULL;

CREATE TABLE identity.password_reset_tokens (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     uuid NOT NULL REFERENCES identity.users(id) ON DELETE CASCADE,
    token_hash  text NOT NULL UNIQUE,
    expires_at  timestamptz NOT NULL,
    used_at     timestamptz,
    created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE identity.staff (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         uuid NOT NULL UNIQUE REFERENCES identity.users(id),
    staff_code      text NOT NULL UNIQUE,
    given_name      text NOT NULL,
    family_name     text NOT NULL,
    job_title       text NOT NULL,
    department_id   uuid NOT NULL REFERENCES operational.departments(id),
    active          boolean NOT NULL DEFAULT true,
    data_origin     text NOT NULL DEFAULT 'SYNTHETIC'
);
```

`replaced_by` implements refresh-token rotation: presenting an already-rotated token is a strong
signal of theft, and the whole chain can be revoked at once.

### Relationship-based access (ASSUMPTIONS P7)

```sql
CREATE TABLE identity.care_assignments (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    staff_id      uuid NOT NULL REFERENCES identity.staff(id),
    patient_id    uuid NOT NULL REFERENCES clinical.patients(id),
    department_id uuid NOT NULL REFERENCES operational.departments(id),
    valid_from    timestamptz NOT NULL DEFAULT now(),
    valid_to      timestamptz,
    reason        text
);
CREATE UNIQUE INDEX ON identity.care_assignments (staff_id, patient_id)
    WHERE valid_to IS NULL;

CREATE TABLE identity.breakglass_grants (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    staff_id    uuid NOT NULL REFERENCES identity.staff(id),
    patient_id  uuid NOT NULL REFERENCES clinical.patients(id),
    reason      text NOT NULL CHECK (length(trim(reason)) >= 20),
    granted_at  timestamptz NOT NULL DEFAULT now(),
    expires_at  timestamptz NOT NULL
);
```

Break-glass exists because clinical reality does not respect assignment tables — a patient can
arrive unconscious in front of a clinician who has no prior relationship with them. Blocking that
would be unsafe. So access is granted, but it requires a typed justification of at least 20
characters, expires, and raises a high-severity audit event. Access control that clinicians can
route around silently is worse than none; access control they can route around *loudly* is the
correct design.

---

## 3. Clinical (FHIR-shaped)

```sql
CREATE TABLE clinical.patients (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id             uuid UNIQUE REFERENCES identity.users(id),
    nhs_number          char(10) UNIQUE,           -- Modulus-11 valid, 999 test range only
    given_name          text NOT NULL,
    family_name         text NOT NULL,
    date_of_birth       date NOT NULL,
    sex_at_birth        text,
    gender_identity     text,
    phone_e164          text,
    email               citext,
    address_line1       text,
    address_line2       text,
    city                text,
    postcode            text,
    preferred_language  text NOT NULL DEFAULT 'en-GB',
    interpreter_needed  boolean NOT NULL DEFAULT false,
    accessibility_needs text[],
    data_origin         text NOT NULL DEFAULT 'SYNTHETIC',
    created_at          timestamptz NOT NULL DEFAULT now(),
    updated_at          timestamptz NOT NULL DEFAULT now(),
    deleted_at          timestamptz               -- soft delete, right to erasure
);
CREATE INDEX ON clinical.patients (family_name, date_of_birth) WHERE deleted_at IS NULL;
```

`nhs_number` is nullable because a patient can self-register before their NHS number is verified.
Making it `NOT NULL` would force us to invent one at registration, which is exactly the failure
mode brief §7 warns against.

`accessibility_needs` and `interpreter_needed` are stored because the staff UI must surface them
prominently — a reasonable-adjustments flag that nobody sees is not a reasonable adjustment.

```sql
CREATE TYPE encounter_class  AS ENUM ('AMB','EMER','IMP','VR');
CREATE TYPE encounter_status AS ENUM ('planned','arrived','in-progress','finished','cancelled');

CREATE TABLE clinical.encounters (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    patient_id      uuid NOT NULL REFERENCES clinical.patients(id),
    appointment_id  uuid REFERENCES operational.appointments(id),
    department_id   uuid NOT NULL REFERENCES operational.departments(id),
    class           encounter_class NOT NULL,
    status          encounter_status NOT NULL,
    period_start    timestamptz NOT NULL,
    period_end      timestamptz,
    primary_staff_id uuid REFERENCES identity.staff(id),
    reason_snomed   text,
    reason_display  text,
    disposition     text,
    data_origin     text NOT NULL DEFAULT 'SYNTHETIC',
    CONSTRAINT period_ordered CHECK (period_end IS NULL OR period_end >= period_start)
);
CREATE INDEX ON clinical.encounters (patient_id, period_start DESC);
CREATE INDEX ON clinical.encounters (department_id, status) WHERE status IN ('arrived','in-progress');

CREATE TABLE clinical.observations (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    patient_id      uuid NOT NULL REFERENCES clinical.patients(id),
    encounter_id    uuid REFERENCES clinical.encounters(id),
    code_system     text NOT NULL,                  -- 'http://loinc.org' | SNOMED
    code            text NOT NULL,
    display         text NOT NULL,
    value_quantity  numeric,
    value_unit      text,
    value_string    text,
    value_code      text,
    reference_low   numeric,
    reference_high  numeric,
    effective_at    timestamptz NOT NULL,
    status          text NOT NULL DEFAULT 'final',
    performer_staff_id uuid REFERENCES identity.staff(id),
    data_origin     text NOT NULL DEFAULT 'SYNTHETIC',
    CONSTRAINT has_a_value CHECK (
        value_quantity IS NOT NULL OR value_string IS NOT NULL OR value_code IS NOT NULL)
);
CREATE INDEX ON clinical.observations (patient_id, code, effective_at DESC);

CREATE TABLE clinical.conditions (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    patient_id     uuid NOT NULL REFERENCES clinical.patients(id),
    encounter_id   uuid REFERENCES clinical.encounters(id),
    snomed_code    text NOT NULL,
    snomed_display text NOT NULL,
    clinical_status text NOT NULL,        -- active | resolved | remission
    onset_date     date,
    recorded_at    timestamptz NOT NULL DEFAULT now(),
    recorded_by_staff_id uuid REFERENCES identity.staff(id),
    data_origin    text NOT NULL DEFAULT 'SYNTHETIC'
);

CREATE TABLE clinical.medication_requests (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    patient_id    uuid NOT NULL REFERENCES clinical.patients(id),
    encounter_id  uuid REFERENCES clinical.encounters(id),
    code          text NOT NULL,                    -- dm+d or RxNorm
    display       text NOT NULL,
    dosage_text   text,
    status        text NOT NULL,
    authored_on   timestamptz NOT NULL,
    prescriber_staff_id uuid REFERENCES identity.staff(id),
    data_origin   text NOT NULL DEFAULT 'SYNTHETIC'
);

CREATE TABLE clinical.allergies (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    patient_id   uuid NOT NULL REFERENCES clinical.patients(id),
    snomed_code  text NOT NULL,
    display      text NOT NULL,
    criticality  text,                              -- low | high | unable-to-assess
    recorded_at  timestamptz NOT NULL DEFAULT now(),
    data_origin  text NOT NULL DEFAULT 'SYNTHETIC'
);
```

**These tables are FHIR-*shaped*, not FHIR-conformant.** They borrow the resource boundaries and
field names so the mapping in `FHIRService` is mechanical, but no conformance testing against UK
Core profiles has been done and none is claimed (ASSUMPTIONS non-claims).

---

## 4. Operational — scheduling and booking

This is the heart of the system and where the constraints matter most.

```sql
CREATE TABLE operational.sites (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    code text NOT NULL UNIQUE, name text NOT NULL,
    address_line1 text, city text, postcode text
);

CREATE TABLE operational.departments (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    site_id uuid NOT NULL REFERENCES operational.sites(id),
    code text NOT NULL UNIQUE,
    name text NOT NULL,
    specialty_snomed text
);

-- DEVELOPMENT-ONLY table. No Tier 1/2 dataset provides this (BLOCKER B2).
CREATE TABLE operational.availability_rules (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    staff_id      uuid NOT NULL REFERENCES identity.staff(id),
    department_id uuid NOT NULL REFERENCES operational.departments(id),
    weekday       smallint NOT NULL CHECK (weekday BETWEEN 0 AND 6),
    start_time    time NOT NULL,
    end_time      time NOT NULL,
    slot_minutes  smallint NOT NULL DEFAULT 15,
    valid_from    date NOT NULL,
    valid_to      date,
    data_origin   text NOT NULL DEFAULT 'SYNTHETIC',
    CONSTRAINT time_ordered CHECK (end_time > start_time)
);

CREATE TYPE slot_type   AS ENUM ('ROUTINE','URGENT','FOLLOW_UP','TELEPHONE');
CREATE TYPE slot_status AS ENUM ('AVAILABLE','HELD','BOOKED','BLOCKED');

CREATE TABLE operational.appointment_slots (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    department_id uuid NOT NULL REFERENCES operational.departments(id),
    staff_id      uuid REFERENCES identity.staff(id),
    site_id       uuid NOT NULL REFERENCES operational.sites(id),
    starts_at     timestamptz NOT NULL,
    ends_at       timestamptz NOT NULL,
    slot_type     slot_type NOT NULL DEFAULT 'ROUTINE',
    status        slot_status NOT NULL DEFAULT 'AVAILABLE',
    version       integer NOT NULL DEFAULT 0,
    data_origin   text NOT NULL DEFAULT 'SYNTHETIC',
    created_at    timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT slot_ordered CHECK (ends_at > starts_at)
);

-- Fast lookup for the availability query, which is the hottest read in the system.
CREATE INDEX idx_slots_search ON operational.appointment_slots
    (department_id, starts_at) WHERE status = 'AVAILABLE';

-- A clinician cannot be in two places at once. Enforced by the database.
CREATE EXTENSION IF NOT EXISTS btree_gist;
ALTER TABLE operational.appointment_slots ADD CONSTRAINT no_clinician_overlap
    EXCLUDE USING gist (
        staff_id WITH =,
        tstzrange(starts_at, ends_at) WITH &&
    ) WHERE (status <> 'BLOCKED' AND staff_id IS NOT NULL);
```

```sql
CREATE TABLE operational.slot_holds (
    id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    slot_id    uuid NOT NULL REFERENCES operational.appointment_slots(id),
    patient_id uuid NOT NULL REFERENCES clinical.patients(id),
    token_hash text NOT NULL,
    expires_at timestamptz NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ON operational.slot_holds (slot_id, expires_at);
CREATE INDEX ON operational.slot_holds (expires_at);   -- reaper job
```

Holds solve a real UX problem: a patient takes 60–90 seconds to complete a booking wizard, and
without a hold two patients can both see the same slot as free and only discover the clash at
submit. A 5-minute hold converts that into a rare, well-handled `409` instead of a common one.

```sql
CREATE TYPE appointment_status AS ENUM
    ('BOOKED','CHECKED_IN','IN_PROGRESS','COMPLETED','CANCELLED','DID_NOT_ATTEND');
CREATE TYPE priority_band AS ENUM ('EMERGENCY','URGENT','SOON','ROUTINE');

CREATE TABLE operational.appointments (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    reference       text NOT NULL UNIQUE,           -- APT-2026-000123, safe to read aloud
    patient_id      uuid NOT NULL REFERENCES clinical.patients(id),
    slot_id         uuid NOT NULL REFERENCES operational.appointment_slots(id),
    department_id   uuid NOT NULL REFERENCES operational.departments(id),
    staff_id        uuid REFERENCES identity.staff(id),
    status          appointment_status NOT NULL DEFAULT 'BOOKED',
    priority        priority_band,
    triage_result_id uuid REFERENCES ai.triage_results(id),
    reason_text     text,
    booked_by_user_id uuid NOT NULL REFERENCES identity.users(id),
    previous_appointment_id uuid REFERENCES operational.appointments(id),
    cancelled_at    timestamptz,
    cancellation_reason text,
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now()
);

-- ►►► The double-booking guarantee. Brief §12. ◄◄◄
CREATE UNIQUE INDEX uq_slot_single_active_appointment
    ON operational.appointments (slot_id)
    WHERE status IN ('BOOKED','CHECKED_IN','IN_PROGRESS');

CREATE INDEX ON operational.appointments (patient_id, created_at DESC);
CREATE INDEX ON operational.appointments (department_id, status, created_at DESC);
```

That partial unique index is the single most important line in this schema. It permits a slot to
be re-booked after a cancellation (cancelled rows fall outside the predicate) while making two
simultaneous active bookings on one slot **impossible at the storage layer**. No amount of
application-code error can violate it.

`previous_appointment_id` makes rescheduling a chain rather than a mutation, so "this patient has
moved their appointment four times" stays visible — clinically relevant, and impossible to see if
reschedule just overwrites the row.

### Wards and beds

```sql
CREATE TABLE operational.wards (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    department_id uuid NOT NULL REFERENCES operational.departments(id),
    name text NOT NULL, bed_count smallint NOT NULL
);

CREATE TYPE bed_status AS ENUM ('AVAILABLE','OCCUPIED','CLEANING','CLOSED');

CREATE TABLE operational.beds (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    ward_id uuid NOT NULL REFERENCES operational.wards(id),
    bed_label text NOT NULL,
    status bed_status NOT NULL DEFAULT 'AVAILABLE',
    UNIQUE (ward_id, bed_label)
);
```

### Notifications (outbox pattern, ASSUMPTIONS P5)

```sql
CREATE TYPE notification_channel AS ENUM ('EMAIL','SMS','IN_APP');
CREATE TYPE notification_status  AS ENUM ('QUEUED','SENT','FAILED','CANCELLED');

CREATE TABLE operational.notifications (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    patient_id    uuid NOT NULL REFERENCES clinical.patients(id),
    appointment_id uuid REFERENCES operational.appointments(id),
    channel       notification_channel NOT NULL,
    template_key  text NOT NULL,          -- key only; never the rendered clinical content
    template_vars jsonb NOT NULL DEFAULT '{}'::jsonb,
    status        notification_status NOT NULL DEFAULT 'QUEUED',
    scheduled_for timestamptz NOT NULL,
    sent_at       timestamptz,
    attempts      smallint NOT NULL DEFAULT 0,
    last_error_code text,
    created_at    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ON operational.notifications (status, scheduled_for)
    WHERE status = 'QUEUED';
```

Storing `template_key` + variables rather than rendered body means the notification table never
becomes a shadow copy of clinical text, and cancelling an appointment can cancel its pending
reminders with one `UPDATE`.

---

## 5. AI schema

```sql
CREATE TYPE chat_status AS ENUM ('ACTIVE','ESCALATED','CLOSED');

CREATE TABLE ai.chat_sessions (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    patient_id  uuid NOT NULL REFERENCES clinical.patients(id),
    status      chat_status NOT NULL DEFAULT 'ACTIVE',
    locale      text NOT NULL DEFAULT 'en-GB',
    started_at  timestamptz NOT NULL DEFAULT now(),
    ended_at    timestamptz,
    escalated_at timestamptz,
    escalation_reason text
);

CREATE TYPE chat_role AS ENUM ('PATIENT','ASSISTANT','SYSTEM');

CREATE TABLE ai.chat_messages (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id    uuid NOT NULL REFERENCES ai.chat_sessions(id) ON DELETE CASCADE,
    role          chat_role NOT NULL,
    content       text NOT NULL,        -- PII-redacted before write (Gen AI S2)
    citations     jsonb,                -- RAG sources, for the citation UI
    safety_flags  text[],               -- e.g. {RED_FLAG_CHEST_PAIN}
    model_version_id uuid REFERENCES ai.model_versions(id),
    created_at    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ON ai.chat_messages (session_id, created_at);

CREATE TYPE triage_severity AS ENUM ('EMERGENCY','URGENT','SOON','ROUTINE','SELF_CARE');
CREATE TYPE triage_status   AS ENUM ('PENDING_REVIEW','CLINICIAN_CONFIRMED','CLINICIAN_OVERRIDDEN');

CREATE TABLE ai.triage_results (
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    patient_id       uuid NOT NULL REFERENCES clinical.patients(id),
    chat_session_id  uuid REFERENCES ai.chat_sessions(id),
    engine           text NOT NULL,               -- 'RULES' | 'ML'
    model_version_id uuid REFERENCES ai.model_versions(id),
    severity         triage_severity NOT NULL,
    confidence       numeric CHECK (confidence BETWEEN 0 AND 1),
    red_flags        text[],
    contributing_factors jsonb,                   -- feeds the explanation UI
    recommended_action text NOT NULL,
    status           triage_status NOT NULL DEFAULT 'PENDING_REVIEW',
    created_at       timestamptz NOT NULL DEFAULT now()
);

CREATE TYPE risk_kind AS ENUM ('READMISSION_30D','NO_SHOW');
CREATE TYPE risk_band AS ENUM ('LOW','MODERATE','HIGH');

CREATE TABLE ai.risk_scores (
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    patient_id       uuid NOT NULL REFERENCES clinical.patients(id),
    appointment_id   uuid REFERENCES operational.appointments(id),
    kind             risk_kind NOT NULL,
    score            numeric NOT NULL CHECK (score BETWEEN 0 AND 1),
    band             risk_band NOT NULL,
    model_version_id uuid NOT NULL REFERENCES ai.model_versions(id),
    explanation      jsonb,
    computed_at      timestamptz NOT NULL DEFAULT now(),
    valid_until      timestamptz
);
CREATE INDEX ON ai.risk_scores (patient_id, kind, computed_at DESC);
```

### AI documents — the human-in-the-loop core

```sql
CREATE TYPE ai_doc_kind   AS ENUM ('CLINICAL_SUMMARY','DISCHARGE_LETTER');
CREATE TYPE ai_doc_status AS ENUM ('DRAFT','IN_REVIEW','APPROVED','REJECTED','SUPERSEDED');

CREATE TABLE ai.ai_documents (
    id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    patient_id        uuid NOT NULL REFERENCES clinical.patients(id),
    encounter_id      uuid REFERENCES clinical.encounters(id),
    kind              ai_doc_kind NOT NULL,
    status            ai_doc_status NOT NULL DEFAULT 'DRAFT',
    generated_content text NOT NULL,          -- IMMUTABLE. Enforced by trigger below.
    model_version_id  uuid NOT NULL REFERENCES ai.model_versions(id),
    prompt_ref        text NOT NULL,          -- versioned prompt id, not the prompt text
    created_at        timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE ai.ai_document_revisions (
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id      uuid NOT NULL REFERENCES ai.ai_documents(id) ON DELETE CASCADE,
    revised_content  text NOT NULL,
    revised_by_staff_id uuid NOT NULL REFERENCES identity.staff(id),
    note             text,
    revised_at       timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE ai.ai_document_reviews (
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id      uuid NOT NULL REFERENCES ai.ai_documents(id),
    reviewer_staff_id uuid NOT NULL REFERENCES identity.staff(id),
    decision         text NOT NULL CHECK (decision IN ('APPROVED','REJECTED','EDITS_REQUESTED')),
    comment          text,
    final_revision_id uuid REFERENCES ai.ai_document_revisions(id),
    decided_at       timestamptz NOT NULL DEFAULT now()
);

-- The AI draft can never be rewritten. Brief §16.
CREATE OR REPLACE FUNCTION ai.protect_generated_content() RETURNS trigger AS $$
BEGIN
    IF NEW.generated_content IS DISTINCT FROM OLD.generated_content THEN
        RAISE EXCEPTION 'generated_content is immutable (document %)', OLD.id;
    END IF;
    RETURN NEW;
END $$ LANGUAGE plpgsql;

CREATE TRIGGER trg_protect_generated_content
    BEFORE UPDATE ON ai.ai_documents
    FOR EACH ROW EXECUTE FUNCTION ai.protect_generated_content();
```

Three tables rather than one status column, because the questions that matter later are
"what did the model produce", "what did the human change", and "who accepted it" — and those are
three different facts with three different owners. Collapsing them into one mutable row destroys
exactly the evidence a clinical incident review would need.

### Model registry and overrides

```sql
CREATE TYPE model_status AS ENUM ('SHADOW','ACTIVE','DEPRECATED','ROLLED_BACK');

CREATE TABLE ai.model_versions (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name          text NOT NULL,
    version       text NOT NULL,
    kind          text NOT NULL,          -- TRIAGE | NO_SHOW | READMISSION | FORECAST | LLM
    status        model_status NOT NULL DEFAULT 'SHADOW',
    trained_at    timestamptz,
    deployed_at   timestamptz,
    metrics       jsonb,                  -- precision/recall/F1 per plan, not just accuracy
    drift_status  text,                   -- OK | WATCH | ALERT
    last_evaluated_at timestamptz,
    model_card_url text,
    UNIQUE (name, version)
);
-- Only one ACTIVE version per model kind.
CREATE UNIQUE INDEX ON ai.model_versions (kind) WHERE status = 'ACTIVE';

CREATE TABLE ai.model_overrides (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    subject_type   text NOT NULL CHECK (subject_type IN ('TRIAGE_RESULT','RISK_SCORE')),
    subject_id     uuid NOT NULL,
    original_value jsonb NOT NULL,        -- snapshot; the source row is never mutated
    override_value jsonb NOT NULL,
    reason         text NOT NULL CHECK (length(trim(reason)) >= 10),
    overridden_by_user_id uuid NOT NULL REFERENCES identity.users(id),
    created_at     timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ON ai.model_overrides (subject_type, subject_id);
```

Overrides are captured rather than applied destructively for two reasons: brief §16 requires the
original be preserved, and the Analysis Report §10 suggests feeding clinician overrides back into
model improvement. A destructive override throws away the training signal.

---

## 6. Audit

```sql
CREATE TYPE audit_result AS ENUM ('SUCCESS','DENIED','ERROR');

CREATE TABLE audit.audit_logs (
    id             bigserial PRIMARY KEY,
    actor_user_id  uuid,
    actor_role     user_role,
    action         text NOT NULL,        -- USER_LOGIN, PATIENT_RECORD_VIEW, ...
    resource_type  text,
    resource_id    uuid,
    result         audit_result NOT NULL,
    request_id     uuid,
    ip_hash        text,                 -- hashed, not raw: it is personal data
    user_agent_hash text,
    metadata       jsonb NOT NULL DEFAULT '{}'::jsonb,  -- identifiers only, no clinical content
    occurred_at    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ON audit.audit_logs (resource_type, resource_id, occurred_at DESC);
CREATE INDEX ON audit.audit_logs (actor_user_id, occurred_at DESC);
CREATE INDEX ON audit.audit_logs (action, occurred_at DESC);

REVOKE UPDATE, DELETE ON audit.audit_logs FROM app_user;   -- append-only by grant
```

The application role is granted `INSERT` and `SELECT` only. An audit log the application can
rewrite is not evidence of anything.

---

## 7. Entities from brief §10 deliberately omitted

| Entity | Why not |
|---|---|
| `roles` table | Four fixed roles, no runtime role management in scope. An enum is correct until permissions become data. |
| `users`/`staff` merged | Kept separate: `users` is authentication, `staff` is the organisational record. Merging them means a clinician who leaves cannot have their login disabled while their historical authorship remains intact. |
| `ai_reviews` as a generic table | Split into `ai_document_reviews` and `model_overrides`; the two have different fields and different retention needs. |

---

## 8. Relationship summary

```
users ──1:1─► patients                (patient self-service accounts)
users ──1:1─► staff                   (clinical/admin accounts)
staff ──1:N─► care_assignments ──N:1─► patients
sites ──1:N─► departments ──1:N─► wards ──1:N─► beds
departments ──1:N─► availability_rules ──generates─► appointment_slots
appointment_slots ──1:1(active)─► appointments      [partial unique index]
appointments ──0:1─► triage_results
appointments ──self-ref─► previous_appointment_id   (reschedule chain)
patients ──1:N─► encounters ──1:N─► observations | conditions | medication_requests
patients ──1:N─► chat_sessions ──1:N─► chat_messages
encounters ──1:N─► ai_documents ──1:N─► revisions, reviews
model_versions ──1:N─► triage_results | risk_scores | ai_documents | chat_messages
everything    ──N:1─► audit_logs (by resource_type + resource_id)
```
