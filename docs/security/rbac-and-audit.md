# RBAC, Authorisation and Audit

Covers brief §41 part H, plus §9, §17, §18.

---

## 1. The governing principle

> **Frontend route protection is user experience. It is not security.**

Next.js middleware stops a patient from *navigating* to `/admin`. It does nothing to stop them
sending `GET /api/v1/admin/models` with curl. Every sensitive endpoint therefore performs its own
authorisation, independently, server-side, with no reference to what the frontend believes.

Authorisation is evaluated at three levels, all of which must pass:

| Level | Question | Where |
|---|---|---|
| **Authentication** | Is this a valid, unexpired token for an active account? | FastAPI dependency `get_current_user` |
| **Role** | Does this role have this capability at all? | Route dependency `require_role(...)` |
| **Resource** | Does this *specific* principal have a relationship to this *specific* record? | Service layer, before any data is read |

Level 3 is the one that gets skipped in real systems, and it is the one that causes IDOR
vulnerabilities. `GET /patients/{id}` guarded only by `require_role(DOCTOR)` lets any doctor read
any patient in the trust. That is the bug we are designing out.

---

## 2. Roles

Four roles, fixed at build time (see `03-data-model.md` §7 for why this is an enum rather than a table).

### PATIENT

| Can | Cannot |
|---|---|
| View and edit own profile | View any other patient's anything |
| View own appointments | See clinician rosters or department capacity |
| Book, reschedule, cancel own appointments | Book on behalf of another person |
| Start chat sessions, view own history | View clinical notes written about them by staff *(scoped out of MVP — see note)* |
| View own triage results | Override a triage result |
| View own approved documents | View draft or unapproved AI documents |

**Note on patient access to clinical notes.** In a real NHS deployment this would be governed by
the trust's policy on patient record access, which is a clinical and legal decision, not an
engineering one. It is deliberately out of MVP scope rather than guessed at.

### NURSE

| Can | Cannot |
|---|---|
| View the department patient queue | Approve AI-generated discharge letters |
| View records of assigned patients | Access admin dashboards or model controls |
| Book and reschedule on a patient's behalf | Change appointment status outside their department |
| Record observations | Deactivate a model version |
| Edit and reject AI drafts | Approve AI drafts |
| Invoke break-glass with justification | Invoke break-glass silently |

### DOCTOR

Everything NURSE can do, plus:

| Can | Cannot |
|---|---|
| **Approve** AI-generated clinical documents | Access admin model monitoring |
| Confirm or override triage results | Change another clinician's approval |
| Record conditions and prescribe | Delete audit records |

### ADMIN

Deliberately **operational, not clinical**:

| Can | Cannot |
|---|---|
| View operational dashboards and KPIs | **Read patient clinical records** |
| Manage departments, slots, capacity | Approve clinical documents |
| View the model registry, activate / roll back versions | Alter a clinical override reason |
| View the audit log | Delete or edit audit entries |
| Provision staff accounts | Grant themselves a clinical role |

This is the most consequential decision in this document. It is tempting to make ADMIN a superuser
because it is convenient during development. It is also how administrative accounts become the
highest-value target in a hospital breach. An operations manager does not need to read a patient's
diagnosis to manage bed capacity, and giving them the ability anyway creates risk with no benefit.

Analytics endpoints therefore return **aggregates only** for ADMIN. Where an admin genuinely needs
patient-level operational data (e.g. contacting a patient about a cancelled clinic), the API
returns identity and appointment fields with clinical fields omitted entirely — not merely hidden
in the UI.

---

## 3. Permission matrix

`✔` allowed · `✔*` allowed only for own/assigned resources · `✔⚠` allowed with mandatory justification · `✘` denied

| Capability | PATIENT | NURSE | DOCTOR | ADMIN |
|---|:--:|:--:|:--:|:--:|
| `auth.login` | ✔ | ✔ | ✔ | ✔ |
| `profile.read` | ✔* | ✔* | ✔* | ✔* |
| `patient.search` | ✘ | ✔ | ✔ | ✘ |
| `patient.demographics.read` | ✔* | ✔* | ✔* | ✔ (non-clinical fields only) |
| `patient.clinical.read` | ✘ | ✔* | ✔* | ✘ |
| `patient.clinical.write` | ✘ | ✔* | ✔* | ✘ |
| `patient.breakglass` | ✘ | ✔⚠ | ✔⚠ | ✘ |
| `appointment.read` | ✔* | ✔* | ✔* | ✔ |
| `appointment.create` | ✔* | ✔ | ✔ | ✔ |
| `appointment.cancel` | ✔* | ✔* | ✔* | ✔ |
| `appointment.status.set` | ✘ | ✔* | ✔* | ✘ |
| `slot.read` | ✔ | ✔ | ✔ | ✔ |
| `slot.manage` | ✘ | ✘ | ✘ | ✔ |
| `chat.own` | ✔* | ✘ | ✘ | ✘ |
| `chat.read.escalated` | ✘ | ✔ | ✔ | ✘ |
| `triage.request` | ✔* | ✔ | ✔ | ✘ |
| `triage.review` | ✘ | ✔ | ✔ | ✘ |
| `document.read` | ✔* (approved only) | ✔* | ✔* | ✘ |
| `document.edit` | ✘ | ✔* | ✔* | ✘ |
| `document.approve` | ✘ | ✘ | ✔* | ✘ |
| `analytics.aggregate.read` | ✘ | ✔ (own dept) | ✔ (own dept) | ✔ |
| `model.registry.read` | ✘ | ✘ | ✘ | ✔ |
| `model.status.change` | ✘ | ✘ | ✘ | ✔⚠ |
| `model.output.override` | ✘ | ✔⚠ | ✔⚠ | ✔⚠ |
| `audit.read` | ✘ | ✘ | ✘ | ✔ |
| `audit.write` | — | — | — | ✘ (system only) |

Note `model.output.override` is available to clinicians, not only admins: overriding a triage
severity is a **clinical** judgement, and routing it through an administrator would insert a
non-clinician into a clinical decision. Admins can override operational model outputs (forecasts),
which is why the row is not admin-exclusive either.

---

## 4. Implementation pattern

```python
# app/core/deps.py

async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    session: AsyncSession = Depends(get_session),
) -> Principal:
    """Level 1: authentication."""
    payload = decode_access_token(token)          # raises TOKEN_EXPIRED / AUTH_REQUIRED
    user = await user_repo.get_active(session, payload.sub)
    if user is None:
        raise AuthenticationRequired()
    return Principal(id=user.id, role=user.role, staff_id=user.staff_id)


def require_role(*roles: UserRole):
    """Level 2: coarse capability gate."""
    async def _check(principal: Principal = Depends(get_current_user)) -> Principal:
        if principal.role not in roles:
            raise PermissionDenied()
        return principal
    return _check


async def require_patient_access(
    patient_id: UUID,
    principal: Principal = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Principal:
    """Level 3: resource-level relationship check. The one that actually matters."""
    if principal.role is UserRole.PATIENT:
        if principal.patient_id != patient_id:
            raise ResourceNotFound()          # 404, not 403 — do not confirm existence
        return principal

    if principal.role in (UserRole.NURSE, UserRole.DOCTOR):
        if await access_repo.has_care_relationship(session, principal.staff_id, patient_id):
            return principal
        if await access_repo.has_active_breakglass(session, principal.staff_id, patient_id):
            return principal
        raise PermissionDenied(hint="breakglass_available")

    raise PermissionDenied()                  # ADMIN reaches here: no clinical access
```

Usage:

```python
@router.get("/patients/{patient_id}/observations")
async def list_observations(
    patient_id: UUID,
    principal: Principal = Depends(require_patient_access),   # all three levels
    session: AsyncSession = Depends(get_session),
) -> ObservationListResponse:
    await audit.record(session, principal, "PATIENT_RECORD_VIEW",
                       "Patient", patient_id, result="SUCCESS")
    return await record_service.list_observations(session, patient_id)
```

The dependency is the only way to get a `Principal` into a patient-scoped handler. A developer who
forgets the check has no `principal` object to work with and the route will not compile cleanly —
the safe path is the path of least resistance.

`PermissionDenied(hint="breakglass_available")` is what lets the frontend offer the break-glass
dialog instead of a dead end, without the error itself confirming the patient exists.

---

## 5. Audit events

Recorded per brief §18. Every entry carries `actor`, `action`, `resource`, `timestamp`, `result`.

| Action | Trigger | Severity |
|---|---|---|
| `USER_LOGIN` | Login attempt (SUCCESS and DENIED both recorded) | Info / Warn |
| `USER_LOGOUT` | Refresh token revoked | Info |
| `PASSWORD_RESET_REQUESTED` / `_COMPLETED` | Reset flow | Info |
| `ACCOUNT_LOCKED` | Threshold of failed logins | Warn |
| `PATIENT_RECORD_VIEW` | Any read of a patient-scoped clinical route | Info |
| `PATIENT_DATA_UPDATED` | Demographics or preferences changed | Info |
| `BREAKGLASS_INVOKED` | Emergency access granted | **High** |
| `PERMISSION_DENIED` | Any Level-2 or Level-3 rejection | Warn |
| `APPOINTMENT_CREATED` / `_RESCHEDULED` / `_CANCELLED` | Booking lifecycle | Info |
| `APPOINTMENT_STATUS_CHANGED` | Check-in, complete, DNA | Info |
| `TRIAGE_ASSESSED` | Triage result produced | Info |
| `AI_OUTPUT_GENERATED` | LLM draft created | Info |
| `AI_OUTPUT_REVIEWED` | Clinician edited a draft | Info |
| `AI_OUTPUT_APPROVED` / `_REJECTED` | Review decision | **High** |
| `MODEL_OVERRIDE` | Triage or risk output overridden | **High** |
| `MODEL_STATUS_CHANGED` | Version activated / rolled back | **High** |
| `RATE_LIMIT_EXCEEDED` | Throttle triggered | Warn |

### What audit records must never contain

```python
FORBIDDEN_IN_AUDIT_METADATA = {
    "password", "token", "refresh_token", "authorization",
    "content", "generated_content", "symptoms", "diagnosis", "notes",
    "nhs_number", "date_of_birth", "email", "phone",
}
```

`audit_logs.metadata` holds identifiers and outcomes, never clinical or authentication content.
The audit log answers *who touched what, when, and did it succeed* — it is not a second copy of
the medical record, and treating it as one would multiply the blast radius of a breach.

This is enforced by a serialiser that strips forbidden keys, plus a unit test that asserts a
payload containing each forbidden key comes back stripped. A convention nobody tests is a
convention nobody follows.

### Append-only enforcement

```sql
REVOKE UPDATE, DELETE ON audit.audit_logs FROM app_user;
GRANT  INSERT, SELECT ON audit.audit_logs TO   app_user;
```

Enforced by database grant, not by application discipline. If the application is compromised, it
still cannot erase its own tracks.

---

## 6. Security test cases (brief §29)

Each becomes a test in `backend/tests/security/`.

| # | Scenario | Expected |
|---|---|---|
| S1 | Unauthenticated request to any protected route | 401 `AUTHENTICATION_REQUIRED` |
| S2 | Patient A requests Patient B's record | 404 `RESOURCE_NOT_FOUND` — never 403 |
| S3 | Patient A requests Patient B's appointment by ID | 404 |
| S4 | Patient passes `patientId` of another patient to `GET /appointments` | Own appointments only; param ignored |
| S5 | Patient posts `{"role": "ADMIN"}` to `/auth/register` | Account created as PATIENT |
| S6 | NURSE calls `POST /documents/{id}/approve` | 403 `PERMISSION_DENIED` |
| S7 | ADMIN calls `GET /patients/{id}/observations` | 403 — admin has no clinical access |
| S8 | DOCTOR reads a patient with no care relationship | 403 with `breakglass_available` hint |
| S9 | Break-glass with a 5-character reason | 400 `VALIDATION_ERROR` |
| S10 | Break-glass with a valid reason | 201 + `BREAKGLASS_INVOKED` audit event at High |
| S11 | Expired access token | 401 `TOKEN_EXPIRED` |
| S12 | Token signed with the wrong key | 401, no detail about why |
| S13 | Reusing an already-rotated refresh token | 401 + entire token chain revoked |
| S14 | `'; DROP TABLE patients;--` in a search field | Treated as a literal string; no SQL error surfaced |
| S15 | `<script>alert(1)</script>` in `reasonText` | Stored escaped; rendered inert; no `dangerouslySetInnerHTML` anywhere |
| S16 | 6 failed logins in 15 minutes | 429 `RATE_LIMITED` with `Retry-After` |
| S17 | Force a 500 | Response contains no stack trace, no SQL, no file path |
| S18 | Inspect logs after a full booking journey | No password, token, NHS number or clinical text present |
| S19 | Attempt `UPDATE` on `audit.audit_logs` as `app_user` | Permission denied by Postgres |
| S20 | Attempt to `UPDATE ai_documents SET generated_content=...` | Trigger raises; draft is immutable |

S5, S7 and S20 are the three most valuable tests in this list. Each one guards a rule that is easy
to state, easy to agree with, and easy to break accidentally during a late-sprint refactor.
