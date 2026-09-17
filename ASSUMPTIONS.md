# Assumption Register

Every design decision in `docs/` traces back to an entry here. Classification per project brief §37.

| Status | Meaning |
|---|---|
| **CONFIRMED** | Explicitly stated in the supplied project documents |
| **INFERRED** | Not stated, but the only reasonable reading of the documents |
| **PROPOSED** | My engineering recommendation; reversible; needs your agreement |
| **BLOCKED** | Cannot proceed correctly without further information or an external dependency |

---

## CONFIRMED (traceable to a supplied document)

| # | Assumption | Source |
|---|---|---|
| C1 | Frontend is React or Next.js | Task Plan, Full Stack S1; Analysis Report §4 |
| C2 | Backend is Python, FastAPI or Django REST | Task Plan, Python S1; Analysis Report §5 |
| C3 | Full Stack domain has exactly 19 tasks: 5 / 5 / 4 / 5 across four bi-weekly sprints | Task Plan, Consolidated Domain Task Summary |
| C4 | Design system must follow the **NHS Digital Service Manual** | Task Plan, Full Stack S1 task 3 |
| C5 | WCAG 2.1 AA is a legal requirement, not a nice-to-have | Task Plan, Full Stack S2/S4; Compliance Checklist |
| C6 | HL7 FHIR UK Core, SNOMED CT and NHS number are the interoperability standards | Compliance Checklist |
| C7 | NHS number must be validated with the **Modulus 11** algorithm | Task Plan, Python S2 |
| C8 | All AI-generated clinical content requires clinician review before it is acted on | Compliance Checklist "Human oversight"; Analysis Report §7 |
| C9 | Staff authentication is OAuth2 / NHS CIS2, stubbed in Sprint 1 | Task Plan, Python S1 |
| C10 | Default to synthetic/open data; real patient data only once governance is actually in place | Dataset Guide, "Golden rule" |
| C11 | Multi-language support is required for patient-facing screens | Task Plan, Full Stack S3 |
| C12 | Some features will realistically remain prototypes within 8 weeks | Analysis Report §10 |
| C13 | **Data source: Synthea + a purpose-built operational generator.** All generated data labelled `SYNTHETIC`. | Decision 2026-08-27, resolving B1 |
| C15 | **Welsh (cy-GB) is the second locale.** Welsh language provision is a statutory duty for public bodies in Wales, which makes it the requirement most likely to be real rather than aspirational. The shipped Welsh is machine-drafted and marked DRAFT: it demonstrates the mechanism and must be replaced by professional translation, with a clinical check of every string carrying advice, before any real use. | Decision 2026-08-28, resolving D5 |
| C14 | **Full Stack owns both frontend and backend** in this repository. The OpenAPI contract is kept as a clean seam so a Python-domain implementation could replace the backend without frontend changes. | Decision 2026-08-27, resolving B6 |

## INFERRED

| # | Assumption | Basis |
|---|---|---|
| I1 | This is an academic / portfolio project, not a real NHS procurement | No trust named, no DPIA, no Clinical Safety Officer, synthetic-data-first instruction |
| I2 | No live NHS integration is available; a sandbox/mock FHIR server is the ceiling | Task Plan scopes only a "test/sandbox FHIR server" (S1); real integration is never scoped |
| I3 | Triage, no-show, readmission and forecasting **models are owned by the AI/ML and Data Science domains**, not Full Stack | Task Plan assigns them there; the Full Stack S3 task is "*surface* AI/ML outputs in UI" |
| I4 | Single-tenant, single-trust scope | No multi-tenancy appears anywhere in the documents |
| I5 | English (en-GB) is the primary locale; a second language proves the i18n mechanism works | C11 requires multi-language without naming languages |

## PROPOSED (my recommendations)

| # | Proposal | Rationale |
|---|---|---|
| P1 | **Next.js 16 App Router + TypeScript** rather than a plain React SPA | Route groups map 1:1 onto the three portals; built-in i18n routing satisfies C11 without a bolt-on; server components keep data-heavy dashboard bundles small; middleware gives one place for role-based redirects. |
| P2 | **PostgreSQL**, with analytics separated as its own schema rather than its own server | Analysis Report §8 requires clinical/operational data kept apart from analytics workloads. Separate schemas now, separate stores later; running two engines during an 8-week build is not worth the cost. |
| P3 | **Tailwind CSS + a local component library** using tokens taken from the NHS.UK design system | C4. Adopting `nhsuk-frontend` wholesale drags in non-React patterns; taking its tokens and re-implementing accessible React components honours the Service Manual and stays idiomatic. |
| P4 | **Recharts** for dashboards | SVG output we can inject `<title>`/`<desc>` into, and pair each chart with a visually-hidden data table. Canvas-based libraries make WCAG compliance materially harder. |
| P5 | **Outbox table + polling worker** for notifications in Sprints 1–2; Celery/Redis only if load justifies it | Reminders are low-volume and latency-tolerant. An outbox is testable with no extra infrastructure. Note the queue itself is a **Python-domain** task (S2), not Full Stack. |
| P6 | **Argon2id** password hashing; 15-minute JWT access token + rotating refresh token stored hashed | Refresh-token rotation gives real revocation. A single long-lived JWT does not. |
| P7 | **Relationship-based access control** for staff→patient, with an audited break-glass override | Brief §9 says "assigned/relevant patient records". "Any doctor sees any patient" is the lazy reading and is not how NHS access control works. |
| P8 | **Synthea** as the canonical synthetic clinical source, plus a purpose-built operational generator | See `docs/data/dataset-strategy.md`. Synthea emits FHIR directly, which serves C6. |
| P9 | The triage engine fails **toward** escalation, never away from it | If the model is unavailable or low-confidence, return a higher urgency band and flag for human review. A safe failure state cannot be "assume the patient is fine". |
| P10 | AI-generated content is stored **immutably**; clinician edits create revisions | Brief §16 forbids a draft silently becoming the record. Append-only storage makes that structurally impossible rather than merely discouraged. |

## BLOCKED

> **Resolved 2026-08-27:** B1 (no dataset) and B6 (backend ownership) are closed — see C13 and C14.
> The remaining blockers are constraints to design around, not decisions awaiting an answer.

| # | Blocker | Impact | What unblocks it |
|---|---|---|---|
| **B2** | No Tier 1 or Tier 2 source contains **clinician availability or appointment slots**. Synthea emits encounters that already happened; HES is aggregate. | The scheduling engine — the most important Full Stack module (§12) — has no source data. | Build a development-only `availability_rules` + `appointment_slots` generator, clearly labelled synthetic. See `dataset-strategy.md` §4. |
| **B3** | No labelled **triage severity** ground truth exists in any Tier 1/2 source. | An ML triage classifier cannot be trained or evaluated. | AI/ML domain owns this (Task Plan S1: "Collect and label a sample dataset"). Full Stack builds against the rule-based engine and a stable API contract regardless. |
| **B4** | No **bed occupancy or live waiting-time** series exists at the granularity the admin dashboard needs. | Admin KPI charts have no real backing data. | Derive from generated encounters plus a synthetic occupancy snapshot job, and label every admin chart as synthetic in the UI. |
| **B5** | **DCB0129 / DCB0160 require a named Clinical Safety Officer.** No such person exists on this project. | A valid clinical safety case cannot be produced. | Outside engineering control. We build the technical foundations (audit trail, human-in-the-loop gates, provenance tracking) and document them as *supporting evidence for a future safety case* — never as compliance. |


### Open defects

| # | Defect | Impact | Status |
|---|---|---|---|
| **D-FORWARDED-FOR** | The API takes the client IP from the left-most `X-Forwarded-For` entry (`backend/app/core/deps.py`), which the client controls. Confirmed against the running production stack on 17 Sep 2026: three requests with three spoofed values created three separate login rate-limit counters. | Each spoofed value gets a fresh allowance, so the per-IP login limit - and the password-spraying protection it gives - can be bypassed, and audit-log IP hashes can be forged. Per-account lockout still applies. | **Open.** The obvious fix, trusting the proxy's own right-most entry, would put every web user behind the web service's single egress IP on Render's free tier, where the API must be public - so fifteen bad sign-ins by one person would lock everyone out. The correct fix is a shared secret between the web and API services, with the web service passing the client IP it received from Render's edge. |

### Defects found and closed

| # | Defect | Outcome |
|---|---|---|
| **D-REFRESH-RACE** (was D-WEBKIT-SESSION) | The session provider exchanged the refresh cookie on every page load without going through the deduplication in `lib/api.ts`. Two overlapping loads replayed a spent token, the server read that as theft, and **every session for that user on every device** was revoked. | **Closed 2 Sep 2026.** Client restores through the shared single-flight path; the server allows a ten-second window where a rotated token replayed while its replacement is live is refused without revoking anything, recorded as `TOKEN_REFRESH_RACE`. Theft outside that window still ends every session, and a test ages the rotation past it to prove that branch still runs. **Recorded first as a WebKit cookie-storage bug, which was wrong twice over** — see `docs/testing/cross-browser.md` §3. All three engines now pass 30/30 with nothing skipped. |
| **D-RATE-LIMIT-WORKERS** | The rate limiter kept counters in process memory. The production stack runs 4 uvicorn workers, so the effective login limit was about four times the configured one and reset on every deploy. | **Closed 2 Sep 2026.** Counters moved to Redis with an atomic sliding window in Lua. Measured against the running production stack with 4 workers: exactly 15 attempts allowed, then 429. Production refuses to start without `REDIS_URL`, and the in-process limiter remains for development and the test suite. |
| **D-UK-TIME** | Clinic hours were generated in UTC and every screen formatted times in the viewer's device zone. In British Summer Time clinics ran 10:00-18:00; on a device set to India time the booking page offered appointments at 22:10. Dates of birth could also render as the previous day west of Greenwich. | **Closed 12 Sep 2026.** Clinic hours defined in Europe/London in the seeder; every formatter pinned to Europe/London, dates of birth formatted as calendar dates. Unit tests assert UK time independently of the zone they run in. 1,260 out-of-hours future slots removed from the demo database - only unbooked, synthetic ones. |
| **D-BOOKING-DEPARTMENTS** | The booking page built its department list from whichever slots were loaded, so choosing a department shrank the list to that one; and loading every department at once used the whole request on a single day, so no later date was reachable. | **Closed 12 Sep 2026.** New read-only `GET /departments`; department chosen first, then that department's times across several days, grouped by UK day and labelled by clinician. |
| **D-FALSE-DELIVERY-CLAIMS** | After booking, the page said "We have sent a confirmation to your email address"; the password-reset page said "Check your email... check your spam folder or try again". This build has no email delivery, so both told people to wait for messages that could never arrive. A code comment also claimed reset tokens were logged at debug level - they were not, but the comment invited it. | **Closed 12 Sep 2026.** Copy corrected on both pages and in the API message; the comment corrected; a regression test plants a known reset token and asserts it reaches no log record. |
| **D-PAGE-SHELL** | The landing, not-found and not-authorised pages had no footer - so no "not affiliated with the NHS" line on the most public page - and the landing page duplicated the header markup. There was no error boundary, so a production error showed Next's bare "Application error" screen. | **Closed 12 Sep 2026.** Shared header; footer rendered once from the root layout so no page can omit it; `error.tsx` and `global-error.tsx` point to NHS 111 and 999 and never show a stack trace. |

---

## Explicit non-claims

This project does **not** and will not claim to be:

NHS-approved · DTAC-assessed · DSPT-certified · DCB0129/0160-compliant ·
FHIR UK Core conformance-tested · clinically validated · fit for patient use.

Any screen or document that could be mistaken for such a claim must carry the
non-clinical banner defined in `docs/architecture/04-frontend-spec.md`.
