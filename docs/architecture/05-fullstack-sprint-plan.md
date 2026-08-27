# 05 — Full Stack Sprint Plan

Covers brief §41 part J. Maps the 19 Full Stack tasks to dated, testable deliverables.

Ordering principle from brief §23 and §44: **the P0 vertical slice must work before any P1 feature
starts.** The plan below is deliberately sequenced so that if the project runs out of time at any
point, what exists is a working narrower system rather than a broad broken one.

---

## Sprint 1 — Foundation & Discovery (Weeks 1–2)

**Sprint goal:** a user can register, log in, and see a real page served by a real API backed by a
real database. Nothing is mocked in the request path.

### Week 1

| Day | Work | Task | Output |
|---|---|---|---|
| 1 | Repo init, monorepo layout, `.env.example`, Docker Compose (postgres + api + web) | FS-1.2 | `docker compose up` starts three healthy containers |
| 1 | Resolve BLOCKER B6 (backend ownership) and B1 (dataset approval) | — | Decisions recorded in `ASSUMPTIONS.md` |
| 2 | Backend skeleton: FastAPI app, config, structured logging, error envelope, `/health`, `/ready` | FS-1.5 | `GET /health` returns 200 |
| 2–3 | Alembic migration 001: identity + clinical + operational core tables | FS-1.5 | `alembic upgrade head` succeeds |
| 3 | Synthea run + UK identity overlay + `import_synthea.py` | (B1) | ~200 synthetic patients loaded |
| 3–4 | `generate_operational_data.py`: departments, staff, availability, slots, historic appointments | (B2) | 12-week slot horizon populated |
| 4–5 | Auth: register, login, refresh rotation, logout, password reset; argon2id; audit on each | FS-1.4 | Security tests S1, S5, S11, S12, S13 pass |
| 5 | Wireframes for all three portals | FS-1.1 | Wireframe canvas + `04-frontend-spec.md` sign-off |

### Week 2

| Day | Work | Task | Output |
|---|---|---|---|
| 6 | Next.js scaffold: App Router, `[locale]`, route groups, Tailwind with NHS tokens | FS-1.2 | Dev server, lint, typecheck all green |
| 6–8 | Design system: all 19 primitives + the three clinical-safety components | FS-1.3 | Every primitive keyboard-operable; axe clean |
| 8–9 | Auth pages: patient login, registration, password reset, staff login | FS-1.4 | Full round trip against the live API |
| 9 | Protected routes: middleware, session handling, role-based redirect, `?next=` preservation | FS-1.4 | Patient hitting `/admin` redirects, not 500s |
| 9–10 | Typed API client: OpenAPI export → `openapi-typescript` → CI drift check | FS-1.5 | CI fails on a deliberate contract change |
| 10 | CI pipeline: lint, typecheck, pytest, vitest, axe, contract drift | FS-1.2 | Green build on `main` |

**Definition of done for Sprint 1**

- `docker compose up` from a clean clone produces a working system.
- A new user registers through the UI, logs in, and lands on a dashboard.
- No page in the app renders hardcoded data.
- Security tests S1, S5, S11, S12, S13 pass.
- Every design-system primitive has a keyboard test.

**Explicitly not in Sprint 1:** booking, chat, any AI, any chart. Sprint 1 that "looks finished"
but has a fake login is a Sprint 1 that has to be redone.

---

## Sprint 2 — Core Feature Build (Weeks 3–4)

**Sprint goal:** the P0 slice is complete. Book an appointment; a clinician sees it and opens the
record. Every access audited.

### Week 3 — booking

| Day | Work | Task |
|---|---|---|
| 11 | Migration 002: slots, holds, appointments + the partial unique index + GiST exclusion | FS-2.3 |
| 11–12 | `SchedulingService`: availability search, priority-banded windows, hold/release | FS-2.3 |
| 12–13 | `BookingService`: book, reschedule chain, cancel, status transitions | FS-2.3 |
| 13 | **Concurrency tests** — the most important tests in the project | FS-2.3 |
| 14–15 | Booking wizard UI: 4 steps, hold countdown, conflict recovery | FS-2.1 |
| 15 | Patient dashboard, appointment list, appointment detail, cancel/reschedule flows | FS-2.1 |

The concurrency test suite, run against real Postgres, not SQLite:

| # | Test | Expected |
|---|---|---|
| B1 | Patient books an available slot | 201, slot `BOOKED`, reminder queued |
| B2 | **20 concurrent bookings of one slot** | Exactly 1 × 201, 19 × 409 `APPOINTMENT_CONFLICT` |
| B3 | Book against an expired hold | 409 `SLOT_HOLD_EXPIRED` |
| B4 | Book against another patient's hold | 409 |
| B5 | Cancel, then rebook the freed slot | Both succeed; partial index permits it |
| B6 | Reschedule where the new slot fails | Original appointment intact |
| B7 | Cancel an already-completed appointment | 409 `INVALID_STATE_TRANSITION` |
| B8 | Patient reads another patient's appointment | 404 |
| B9 | Same `Idempotency-Key` submitted twice | One appointment, identical response |
| B10 | Slot booked between list and confirm | 409, wizard recovers at step 3 with input preserved |

B2 is run 50 times in CI. A race condition that fails one time in twenty is still a double-booked
clinic.

### Week 4 — records, queue, responsive, accessibility

| Day | Work | Task |
|---|---|---|
| 16 | Migration 003: encounters, observations, conditions, medications, care assignments | FS-2.3 |
| 16–17 | `RecordService` + patient-scoped routes with three-level authorisation + audit | FS-2.3 |
| 17 | Break-glass flow, end to end | FS-2.2 |
| 18 | Staff queue: filters in URL state, sort, search, priority column | FS-2.2 |
| 18–19 | Patient record shell: tabs, demographics, timeline, observations, conditions, medications | FS-2.2 |
| 19 | Responsive pass: table→card collapse, accordion record, per-breakpoint layouts | FS-2.4 |
| 20 | Accessibility pass: axe in CI, keyboard traversal, focus management, contrast | FS-2.5 |
| 20 | Profile page; notification outbox + reminder scheduling | FS-2.1 |

**Definition of done for Sprint 2 — the MVP gate**

The scripted demo in `01-analysis-and-scope.md` §L runs unattended. Security tests S1–S20 pass.
All booking tests B1–B10 pass. Zero axe violations on P0 screens at 375px, 768px and 1440px.

If Sprint 2 does not close, **Sprint 3 does not start.** Surfacing model outputs on top of a broken
booking flow produces a demo, not a system.

---

## Sprint 3 — Intelligence & Integration (Weeks 5–6)

**Sprint goal:** AI outputs are visible, clearly attributed, always reviewable, and never final.

| Week | Work | Task |
|---|---|---|
| 5 | Migration 004: chat, triage, risk scores, AI documents + immutability trigger, model registry | FS-3.1 |
| 5 | `TriageEngine` protocol + `RuleBasedTriageEngine` with red-flag rules and fail-toward-escalation | FS-3.1 |
| 5 | Chat UI: thread, states, citations, escalation, persistent 999 banner | FS-3.1 |
| 5 | Symptom intake → triage result → priority-filtered slot search, wired end to end | FS-3.1 |
| 5 | `TriageResultCard`, `RiskIndicator`, `PriorityFlag` with provenance badges | FS-3.1 |
| 6 | AI document review screen: side-by-side diff, revisions, approve/reject, audit | FS-3.1 |
| 6 | Admin model registry: list, version, status, drift, last evaluation, model card link | FS-3.2 |
| 6 | Model override UI: view recommendation, override with mandatory reason, original preserved | FS-3.2 |
| 6 | i18n: `next-intl` wiring, extract remaining strings, second locale, `Intl` formatting | FS-3.3 |
| 6 | Performance: **measure first**, then act on what the measurement shows | FS-3.4 |

### FS-3.4 approach

Brief §5 says do not optimise prematurely. So the task begins with a baseline, not with changes:

1. Record Lighthouse scores for the six highest-traffic routes.
2. Record API p50/p95 for the ten most-called endpoints under a 50-user load.
3. Run `EXPLAIN ANALYZE` on the slot search and queue queries.
4. Record the production bundle size per route.

Only then act, in the order the data indicates. Likely candidates, to be confirmed rather than
assumed: slot-search index coverage, queue N+1 queries, chart library code-splitting, cursor
pagination for the audit log.

Baselines and post-change figures both go in `docs/testing/performance-baseline.md`. An
optimisation with no before-figure is a guess.

**Sprint 3 done when:** a triage signal measurably changes which slots the patient is offered; an AI
draft can be edited and approved with the original still retrievable; the admin panel shows real
registry rows; a full patient journey works in the second locale.

---

## Sprint 4 — Testing, Compliance & Deployment (Weeks 7–8)

| Week | Work | Task |
|---|---|---|
| 7 | Write and run UAT scenarios for all three roles | FS-4.1 |
| 7 | Manual accessibility audit: keyboard-only, NVDA, focus order, contrast, zoom to 200% | FS-4.2 |
| 7 | Remediate accessibility findings | FS-4.2 |
| 7 | Playwright matrix: Chromium, Firefox, WebKit × desktop, tablet, mobile viewports | FS-4.3 |
| 8 | Bug fixing in the brief §35 priority order | FS-4.4 |
| 8 | Production build, staging deploy, migrations, health checks, smoke tests, rollback | FS-4.5 |
| 8 | Documentation completion and handover | FS-4.5 |

### FS-4.1 — UAT scenarios

Written as scripts a non-technical reviewer can follow unaided, in
`docs/testing/uat-scenarios.md`. 21 scenarios: 7 patient, 8 staff, 6 admin. Each records
task-completion, time taken, errors encountered, and verbatim participant comments.

Two scenarios exist specifically to test whether the safety design actually works on real people:

- **UAT-P4:** a participant describes emergency symptoms to the chatbot. *Do they understand they
  should call 999?* If they do not, the copy has failed regardless of what the design intended.
- **UAT-S6:** a clinician is given an AI draft containing a deliberate factual error. *Do they catch
  it before approving?* This measures automation bias directly rather than assuming the diff view
  prevents it.

These two are the most valuable tests in the project, because they are the only ones that check
whether the clinical safety design survives contact with a human being.

### FS-4.4 — Defect register

Per brief §35, in `docs/testing/defect-register.md`:

```
ID | Severity | Module | Description | Steps | Expected | Actual | Status | Fix
```

Fixed in the priority order of brief §44: security → data integrity → authentication → booking
correctness → clinical workflow → accessibility → performance → visual polish.

### FS-4.5 — Deployment

Staging only. Per brief §6 and §41-K, **no claim of NHS production deployment is made.**

- Multi-stage Docker builds, non-root containers.
- Compose stack: postgres, api, web, worker, reverse proxy with security headers.
- Migrations run as a separate job before the API starts, never on API boot — an API that migrates
  on startup will race itself the moment it runs more than one replica.
- Health checks wired to container orchestration.
- Rollback: previous image tag + `alembic downgrade` tested as part of the drill, not documented and
  hoped for.
- Smoke tests: 12 checks covering login, booking, record view, and audit write.

---

## Cross-sprint: ongoing work

| Workstream | Cadence |
|---|---|
| Accessibility | Built into primitives in S1; audited in S2; formally reviewed in S4 |
| Security tests | S1–S20 added as the surfaces they guard are built; all green at every sprint close |
| Audit coverage | Every new sensitive endpoint ships with its audit event, same commit |
| Documentation | Updated in the same PR as the change; stale docs treated as defects |
| `ASSUMPTIONS.md` | Reviewed at every sprint boundary; resolved blockers moved to CONFIRMED |

---

## Contingency

The Analysis Report §10 predicts some features will remain prototypes. Planning for that now is
better than discovering it in week 7. Descope order, first to go:

1. Second locale beyond the mechanism proof (FS-3.3 reduced to a demonstrated pipeline)
2. Forecast visualisations
3. Model drift indicators (registry list retained)
4. Admin alerts page
5. Chatbot multi-turn memory (single-turn intake retained)

**Never descoped, at any cost:** authentication, RBAC and resource-level authorisation, booking
correctness, audit logging, the human-in-the-loop approval gate, and WCAG 2.1 AA on P0 screens.
Those are the properties that distinguish this from a demo, and every one of them is a property
you cannot bolt on afterwards.
