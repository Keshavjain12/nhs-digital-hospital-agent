# API Contract v1

Covers brief §41 part F, and satisfies brief §31 (contract defined before frontend integration).

**This document is the single source of truth for the frontend/backend seam.** FastAPI generates
`openapi.json` from the Pydantic schemas; the frontend generates `types/generated/api.ts` from
that. CI fails if the generated types differ from what is committed. Neither side may invent a
shape independently.

Base path: `/api/v1` · Content type: `application/json` · All times ISO 8601 UTC with offset.

---

## 1. Conventions

### Response envelope

Single resource and collections:

```jsonc
// GET /appointments/{id}
{ "data": { ... }, "meta": { "requestId": "8f2c...", "dataOrigin": "SYNTHETIC" } }

// GET /appointments
{ "data": [ ... ],
  "meta": { "requestId": "8f2c...", "dataOrigin": "SYNTHETIC",
            "page": 1, "pageSize": 20, "totalItems": 47, "totalPages": 3 } }
```

`dataOrigin` is mandatory on every response derived from generated data. The frontend uses it to
decide whether to render `<SyntheticDataNotice />`. This is how the "never present synthetic data
as real" rule (brief §7) is enforced mechanically rather than by discipline.

### Error envelope

Exactly as brief §11 specifies:

```jsonc
{ "error": {
    "code": "APPOINTMENT_CONFLICT",
    "message": "The selected appointment slot is no longer available.",
    "details": [ { "field": "slotId", "issue": "already_booked" } ],
    "requestId": "8f2c..." } }
```

`message` is safe to display to a user verbatim. Stack traces, SQL, and internal identifiers never
appear (brief §11, §17).

### Error codes

| Code | HTTP | Meaning |
|---|---|---|
| `VALIDATION_ERROR` | 400 | Request failed schema validation |
| `AUTHENTICATION_REQUIRED` | 401 | Missing or malformed credentials |
| `TOKEN_EXPIRED` | 401 | Access token expired; client should refresh |
| `PERMISSION_DENIED` | 403 | Authenticated but not authorised for this resource |
| `RESOURCE_NOT_FOUND` | 404 | Not found, **or** exists but not visible to this principal |
| `APPOINTMENT_CONFLICT` | 409 | Slot taken between selection and confirmation |
| `SLOT_HOLD_EXPIRED` | 409 | The 5-minute hold lapsed |
| `INVALID_STATE_TRANSITION` | 409 | e.g. cancelling an already-completed appointment |
| `NHS_NUMBER_INVALID` | 422 | Failed Modulus 11 check |
| `RATE_LIMITED` | 429 | Includes `Retry-After` header |
| `UPSTREAM_UNAVAILABLE` | 503 | FHIR / LLM / model service down |
| `INTERNAL_ERROR` | 500 | Generic; details only in server logs |

**404-over-403 rule:** when a patient requests another patient's resource we return
`RESOURCE_NOT_FOUND`, not `PERMISSION_DENIED`. Returning 403 confirms the resource exists, which
leaks the existence of a patient record to anyone who can guess an ID.

### Authentication

`Authorization: Bearer <access_token>` on everything except `/health`, `/ready`, and the
`/auth/login|register|password-reset|refresh` endpoints.

### Idempotency

`POST /appointments` accepts an optional `Idempotency-Key` header. Replaying a key within 24h
returns the original response rather than creating a second appointment — protects against
double-submit on a flaky mobile connection.

### Rate limits

| Scope | Limit |
|---|---|
| `POST /auth/login` | 5 / 15 min per IP **and** per email |
| `POST /auth/register`, `/auth/password-reset` | 3 / hour per IP |
| `POST /chat/**` | 30 / min per user |
| Authenticated general | 300 / min per user |
| Unauthenticated general | 60 / min per IP |

---

## 2. Auth

| Method | Path | Auth | Roles | Purpose |
|---|---|---|---|---|
| POST | `/auth/register` | — | — | Patient self-registration only |
| POST | `/auth/login` | — | — | Exchange credentials for tokens |
| POST | `/auth/refresh` | cookie | any | Rotate refresh token, issue new access token |
| POST | `/auth/logout` | Bearer | any | Revoke refresh token |
| POST | `/auth/password-reset` | — | — | Request reset email |
| POST | `/auth/password-reset/confirm` | — | — | Consume token, set new password |
| GET | `/auth/me` | Bearer | any | Current principal + profile |

### POST /auth/register

```jsonc
// request
{ "email": "patient@example.test",
  "password": "<min 12 chars>",
  "givenName": "Alex", "familyName": "Morgan",
  "dateOfBirth": "1988-04-12",
  "nhsNumber": "9990000018",          // optional
  "preferredLanguage": "en-GB" }

// 201
{ "data": { "userId": "...", "patientId": "...", "email": "...", "role": "PATIENT" },
  "meta": { "requestId": "..." } }
```

Errors: `VALIDATION_ERROR` (weak password, malformed DOB), `NHS_NUMBER_INVALID`, `RATE_LIMITED`.

Registration always returns 201 even if the email is already registered, with a confirmation email
sent to the existing account instead. Returning a distinct error would turn this endpoint into an
account-enumeration oracle.

**Role is never accepted from the request body.** `/auth/register` can only create `PATIENT`.
Staff and admin accounts are provisioned separately. A registration endpoint that trusts a `role`
field from the client is a privilege-escalation vulnerability, and it is a common one.

### POST /auth/login

```jsonc
// request
{ "email": "doctor@example.test", "password": "..." }

// 200 — refresh token is set as httpOnly cookie, NOT in this body
{ "data": { "accessToken": "eyJ...", "expiresIn": 900, "tokenType": "Bearer",
            "user": { "id": "...", "role": "DOCTOR", "displayName": "Dr S. Patel" } },
  "meta": { "requestId": "..." } }
```

Errors: `AUTHENTICATION_REQUIRED` (401, identical message for wrong email and wrong password),
`RATE_LIMITED`, 403 if the account is locked.

---

## 3. Slots and scheduling

| Method | Path | Auth | Roles | Purpose |
|---|---|---|---|---|
| GET | `/slots` | Bearer | all | Search available slots |
| POST | `/slots/{id}/hold` | Bearer | PATIENT, NURSE, ADMIN | Take a 5-minute soft hold |
| DELETE | `/slots/{id}/hold` | Bearer | owner | Release a hold early |

### GET /slots

Query: `departmentId`, `from` (date), `to` (date), `priority` (`EMERGENCY|URGENT|SOON|ROUTINE`),
`slotType`, `siteId`, `page`, `pageSize`.

```jsonc
// 200
{ "data": [
    { "id": "...", "startsAt": "2026-09-03T09:15:00Z", "endsAt": "2026-09-03T09:30:00Z",
      "slotType": "ROUTINE",
      "department": { "id": "...", "name": "Cardiology" },
      "site": { "id": "...", "name": "Queen's Park Hospital" },
      "clinician": { "id": "...", "displayName": "Dr S. Patel", "jobTitle": "Consultant" } } ],
  "meta": { "page": 1, "pageSize": 20, "totalItems": 62, "dataOrigin": "SYNTHETIC" } }
```

`priority` narrows the search window rather than unlocking hidden slots: `URGENT` returns slots in
the next 48h, `SOON` two weeks, `ROUTINE` the full horizon. The triage signal influences *what the
patient is offered*, which is the point of the priority signal in the plan — but it does not let
software allocate scarce urgent capacity autonomously.

### POST /slots/{id}/hold

```jsonc
// 200
{ "data": { "holdToken": "hld_9f3...", "expiresAt": "2026-08-27T14:35:00Z" } }
```

Errors: `RESOURCE_NOT_FOUND`, `APPOINTMENT_CONFLICT` (already held or booked).

---

## 4. Appointments

| Method | Path | Auth | Roles | Purpose |
|---|---|---|---|---|
| GET | `/appointments` | Bearer | all | List — scoped by role |
| POST | `/appointments` | Bearer | PATIENT, NURSE, ADMIN | Book |
| GET | `/appointments/{id}` | Bearer | owner / assigned staff / ADMIN | Detail |
| PATCH | `/appointments/{id}` | Bearer | owner / staff | Reschedule or update reason |
| POST | `/appointments/{id}/cancel` | Bearer | owner / staff | Cancel with reason |
| POST | `/appointments/{id}/status` | Bearer | NURSE, DOCTOR | Check-in / complete / DNA |

Note `POST /{id}/cancel` rather than `DELETE /{id}`: an appointment is never deleted. Cancellation
is a state transition that must remain visible for audit and for no-show analytics. Brief §12
lists `DELETE`; this is a deliberate, documented deviation.

### GET /appointments — role scoping

| Role | Returns |
|---|---|
| PATIENT | Own appointments only. A `patientId` query param is **ignored**, not honoured. |
| NURSE / DOCTOR | Appointments in their department, or for assigned patients |
| ADMIN | All, with mandatory `departmentId` or date filter to prevent unbounded scans |

### POST /appointments

```jsonc
// request
{ "slotId": "...", "holdToken": "hld_9f3...",
  "reasonText": "Follow-up on blood pressure",
  "triageResultId": "...",              // optional
  "patientId": "..." }                  // staff-booking-on-behalf only; ignored for PATIENT

// 201
{ "data": { "id": "...", "reference": "APT-2026-000123", "status": "BOOKED",
            "priority": "ROUTINE",
            "startsAt": "2026-09-03T09:15:00Z", "endsAt": "2026-09-03T09:30:00Z",
            "department": { ... }, "clinician": { ... },
            "reminderScheduledFor": "2026-09-02T09:15:00Z" } }
```

Errors: `APPOINTMENT_CONFLICT` (409 — slot taken, the race-condition case), `SLOT_HOLD_EXPIRED`
(409), `VALIDATION_ERROR`, `PERMISSION_DENIED` (patient supplying another patient's `patientId`).

### PATCH /appointments/{id} — reschedule

```jsonc
{ "newSlotId": "...", "holdToken": "hld_...", "reason": "Work conflict" }
```

Implemented as: cancel the old appointment, create a new one with
`previousAppointmentId` set, both inside one transaction. If the new slot fails to book, the old
appointment is **not** cancelled. A reschedule that leaves the patient with no appointment at all
is worse than a failed reschedule.

---

## 5. Patients and records

| Method | Path | Auth | Roles | Purpose |
|---|---|---|---|---|
| GET | `/patients` | Bearer | NURSE, DOCTOR, ADMIN | Search — requires a query term |
| GET | `/patients/{id}` | Bearer | self / assigned staff / ADMIN | Demographics |
| PATCH | `/patients/{id}` | Bearer | self / ADMIN | Update contact + preferences |
| GET | `/patients/{id}/encounters` | Bearer | assigned staff / self | FHIR-shaped encounters |
| GET | `/patients/{id}/observations` | Bearer | assigned staff / self | Observations, filterable by code |
| GET | `/patients/{id}/conditions` | Bearer | assigned staff / self | Conditions |
| GET | `/patients/{id}/medications` | Bearer | assigned staff / self | Medication requests |
| GET | `/patients/{id}/risk-scores` | Bearer | assigned staff | Readmission / no-show |
| POST | `/patients/{id}/breakglass` | Bearer | DOCTOR, NURSE | Emergency access with justification |

`GET /patients` requires a non-empty search term of at least 3 characters. An endpoint that
returns the entire patient list on an empty query is a data-exfiltration convenience.

**Every one of these routes writes a `PATIENT_RECORD_VIEW` audit event before returning data.**

### POST /patients/{id}/breakglass

```jsonc
// request
{ "reason": "Unconscious patient in resus, no prior care relationship on record" }
// 201
{ "data": { "expiresAt": "2026-08-27T18:00:00Z", "auditEventId": "..." } }
```

`reason` must be ≥20 characters. Raises a high-severity audit event and, in a real deployment,
would notify the Caldicott Guardian. Access is granted for 4 hours.

---

## 6. Triage and chat

| Method | Path | Auth | Roles | Purpose |
|---|---|---|---|---|
| POST | `/triage/assess` | Bearer | PATIENT, NURSE | Assess a symptom intake |
| GET | `/triage/{id}` | Bearer | self / staff | Retrieve a result |
| POST | `/triage/{id}/review` | Bearer | DOCTOR, NURSE | Confirm or override |
| POST | `/chat/sessions` | Bearer | PATIENT | Start a session |
| GET | `/chat/sessions/{id}` | Bearer | owner / staff | History |
| POST | `/chat/sessions/{id}/messages` | Bearer | owner | Send a message |
| POST | `/chat/sessions/{id}/escalate` | Bearer | owner / system | Escalate to a human |

### POST /triage/assess

```jsonc
// request
{ "chatSessionId": "...",
  "symptoms": [ { "description": "chest tightness", "durationHours": 3, "severity": 7 } ],
  "onsetAt": "2026-08-27T08:00:00Z" }

// 200
{ "data": {
    "id": "...",
    "severity": "EMERGENCY",
    "confidence": null,                         // null for the rule-based engine — it does not estimate one
    "engine": "RULES",
    "modelVersion": "triage-rules-1.0.0",
    "redFlags": ["CHEST_PAIN_WITH_EXERTION"],
    "contributingFactors": [
      { "factor": "Chest pain reported", "influence": "increases urgency" } ],
    "recommendedAction": "Call 999 now or go to your nearest A&E department.",
    "requiresHumanReview": true,
    "disclaimer": "This is not a diagnosis. It is an assessment to help decide how quickly you should be seen.",
    "status": "PENDING_REVIEW" } }
```

Three contract rules that are not negotiable:

1. `confidence` is nullable and the UI must handle null. A rule-based engine does not produce a
   calibrated probability, and rendering a fabricated "97% confident" would be a lie the UI tells
   on the model's behalf.
2. `severity: "EMERGENCY"` **always** carries `requiresHumanReview: true` and a
   `recommendedAction` that points at emergency services.
3. If the engine errors or times out, the endpoint returns `severity: "URGENT"` with
   `requiresHumanReview: true` and `engine: "FALLBACK"` — **not** a 503. Failing toward escalation
   (ASSUMPTIONS P9). A patient who sees an error message may simply give up.

### POST /triage/{id}/review

```jsonc
{ "decision": "OVERRIDDEN", "newSeverity": "SOON", "reason": "Reviewed; symptoms consistent with musculoskeletal strain" }
```

Writes `ai.model_overrides` with the original preserved. `reason` is mandatory, ≥10 characters.

---

## 7. AI clinical documents

| Method | Path | Auth | Roles | Purpose |
|---|---|---|---|---|
| POST | `/documents` | Bearer | DOCTOR, NURSE | Request an AI draft |
| GET | `/documents` | Bearer | DOCTOR, NURSE | List, filter by status |
| GET | `/documents/{id}` | Bearer | assigned staff | Draft + revisions + review history |
| PATCH | `/documents/{id}/content` | Bearer | DOCTOR, NURSE | Save an edit (creates a revision) |
| POST | `/documents/{id}/approve` | Bearer | DOCTOR | Approve |
| POST | `/documents/{id}/reject` | Bearer | DOCTOR, NURSE | Reject with reason |
| POST | `/documents/{id}/regenerate` | Bearer | DOCTOR, NURSE | New draft; old becomes SUPERSEDED |

### GET /documents/{id}

```jsonc
{ "data": {
    "id": "...", "kind": "DISCHARGE_LETTER", "status": "IN_REVIEW",
    "provenance": "AI_GENERATED",
    "generatedContent": "...",               // immutable original, always returned
    "currentContent": "...",                 // latest revision, or generatedContent if none
    "revisions": [ { "id": "...", "revisedBy": "Dr S. Patel", "revisedAt": "...", "note": "..." } ],
    "reviews": [],
    "modelVersion": "discharge-drafter-0.3.1",
    "createdAt": "...",
    "disclaimer": "AI-generated draft. Not part of the clinical record until approved by a clinician." } }
```

Returning both `generatedContent` and `currentContent` lets the review UI render a diff, which is
the concrete countermeasure against automation bias — a clinician who can see exactly what changed
is far less likely to rubber-stamp.

Approval is `DOCTOR`-only. Nurses can edit and reject but not approve, matching the plan's
"clinician review before acting on it" for content that carries prescribing and follow-up
instructions.

---

## 8. Analytics and admin

| Method | Path | Auth | Roles | Purpose |
|---|---|---|---|---|
| GET | `/analytics/kpis` | Bearer | ADMIN, DOCTOR | KPI card values |
| GET | `/analytics/occupancy` | Bearer | ADMIN | Bed occupancy series |
| GET | `/analytics/waiting-times` | Bearer | ADMIN | Wait-time series |
| GET | `/analytics/departments` | Bearer | ADMIN | Per-department breakdown |
| GET | `/analytics/alerts` | Bearer | ADMIN, NURSE | Active operational alerts |
| GET | `/admin/models` | Bearer | ADMIN | Model registry |
| GET | `/admin/models/{id}` | Bearer | ADMIN | Detail: metrics, drift, model card |
| POST | `/admin/models/{id}/status` | Bearer | ADMIN | Activate / deprecate / roll back |
| GET | `/admin/overrides` | Bearer | ADMIN | Override log |
| GET | `/admin/audit` | Bearer | ADMIN | Audit search |

### GET /analytics/kpis

```jsonc
{ "data": {
    "periodStart": "2026-08-20", "periodEnd": "2026-08-27",
    "kpis": [
      { "key": "totalAppointments", "label": "Total appointments", "value": 1284,
        "unit": "count", "changePct": 3.2, "trend": "up" },
      { "key": "noShowRate", "label": "No-show rate", "value": 11.4,
        "unit": "percent", "changePct": -0.8, "trend": "down", "inverted": true },
      { "key": "bedOccupancy", "label": "Bed occupancy", "value": 87.2, "unit": "percent",
        "threshold": { "warn": 85, "critical": 95 } } ] },
  "meta": { "dataOrigin": "SYNTHETIC" } }
```

`inverted: true` tells the UI that "down is good" for this metric, so the trend arrow is not
coloured green/red incorrectly. `trend` is a word, not only a colour — colour alone would fail
WCAG 1.4.1 (brief §20).

---

## 9. Notifications and system

| Method | Path | Auth | Roles |
|---|---|---|---|
| GET | `/notifications` | Bearer | self |
| POST | `/notifications/{id}/read` | Bearer | self |
| PATCH | `/me/notification-preferences` | Bearer | self |
| GET | `/health` | — | — |
| GET | `/ready` | — | — |

```jsonc
// GET /health  →  200
{ "status": "ok", "version": "1.4.0", "uptimeSeconds": 84210 }
```

`/health` returns liveness only. `/ready` checks database and migration state but reports
`{"database": "ok"}`, never a connection string, host, or version. Brief §33.

---

## 10. Contract enforcement in CI

```
backend:  pytest → FastAPI app → export openapi.json
          ↓
          diff against docs/api/openapi.json    ← fails on unreviewed change
          ↓
frontend: openapi-typescript → types/generated/api.ts
          ↓
          git diff --exit-code                 ← fails if types are stale
          ↓
          tsc --noEmit                          ← fails if code uses a removed field
```

A backend field rename that breaks the frontend fails at build time rather than in a demo.
