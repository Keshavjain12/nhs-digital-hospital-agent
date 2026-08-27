# 01 — Project Analysis, Full Stack Scope, Risks and MVP

Covers brief §41 parts A, B, K, L.

---

## A. Executive understanding

The NHS Digital Hospital Agent is **not an AI feature bolted onto a hospital system**. It is a
hospital platform in which AI is inserted at four specific points where it demonstrably saves
human time, with a human gate in front of every clinical consequence.

The system follows one patient journey end to end:

```
A patient types one sentence about how they feel
        │
        ▼
 chatbot intake ──► triage severity ──► priority signal
        │                                    │
        ▼                                    ▼
  escalation to human            slot availability filtered by urgency
  (if red flag or out of scope)             │
                                             ▼
                                     booking + conflict check
                                             │
                                             ▼
                              appointment written to patient record
                                             │
                                             ▼
                          staff queue ──► clinician opens record
                                             │
                                             ▼
                    AI drafts summary / discharge letter (DRAFT only)
                                             │
                                             ▼
                     clinician reviews → edits → approves → record
                                             │
                                             ▼
                        activity data ──► analytics ──► manager dashboard
```

Three user groups, three portals, one data spine.

### The four points where AI is used

| Point | AI role | Human gate |
|---|---|---|
| Symptom intake | Conversational collection, FAQ answering over a RAG knowledge base | Escalation to a human on red flags or out-of-scope queries |
| Triage | Severity classification producing a **priority signal**, not a diagnosis | Clinician can confirm or override; override is recorded, original preserved |
| Clinical documentation | Drafts note summaries and discharge letters | Clinician must approve before the document becomes part of the record |
| Prediction | No-show, readmission risk, bed/staff demand forecast | Advisory only; surfaced as decision support beside the clinician's own judgement |

### What the documents emphasise most

Reading the plan closely, roughly a full sprint of 24 tasks goes to testing, compliance and
sign-off. The Analysis Report makes the point explicitly: *"in healthcare a system that works but
cannot be trusted is worth nothing."* That shapes the engineering priorities in this repository:
audit trail, provenance, human-in-the-loop gates and accessibility are treated as P0 features, not
as polish deferred to Sprint 4.

### The tension the plan itself acknowledges

112 tasks in 8 weeks across 6 domains is not deliverable at production quality. The Analysis
Report says so in §10 and recommends cutting scope for v1. This repository takes that advice:
we build a **narrow vertical slice that genuinely works end to end** and is honest about which
parts are prototypes. See §L.

---

## B. Full Stack scope — the 19 tasks mapped to modules

Full Stack owns 19 of the 112 tasks. Mapping each to a concrete deliverable in this repository:

### Sprint 1 — 5 tasks

| # | Task (verbatim from plan) | Module | Deliverable |
|---|---|---|---|
| FS-1.1 | Create UX wireframes: patient portal, staff dashboard, chatbot widget | Design | `docs/architecture/04-frontend-spec.md` + wireframe canvas |
| FS-1.2 | Set up frontend repo (React/Next.js) with component library | Frontend shell | `frontend/` Next.js 16 + TS + Tailwind, CI-ready |
| FS-1.3 | Build design system per NHS Digital Service Manual | Design system | `frontend/components/ui/*` — 19 primitives, all keyboard-accessible |
| FS-1.4 | Build basic auth pages (login, registration, password reset) | Auth UI | `(public)` route group + protected-route middleware |
| FS-1.5 | Connect frontend skeleton to backend API stub | Integration | Typed API client, generated from the OpenAPI contract |

### Sprint 2 — 5 tasks

| # | Task | Module | Deliverable |
|---|---|---|---|
| FS-2.1 | Patient portal: booking flow, profile, chatbot widget embed | Patient portal | Booking wizard, profile, chat panel |
| FS-2.2 | Staff dashboard: patient queue, priority flags, alerts | Staff portal | Queue with filter/sort/search, priority column, alert rail |
| FS-2.3 | Integrate frontend with booking and records APIs | Integration | TanStack Query hooks over the typed client; optimistic-safe booking |
| FS-2.4 | Responsive design across mobile/tablet/desktop | Responsive | Card-collapse pattern for tables; per-breakpoint layouts, not shrunk desktop |
| FS-2.5 | Accessibility pass targeting WCAG 2.1 AA | Accessibility | axe-core in CI, keyboard traversal tests, focus management |

### Sprint 3 — 4 tasks

| # | Task | Module | Deliverable |
|---|---|---|---|
| FS-3.1 | Surface AI/ML outputs in UI (triage flags, readmission risk) | AI surfacing | `ProvenanceBadge`, `TriageResultCard`, `RiskIndicator`, forecast charts |
| FS-3.2 | Admin panel for model monitoring and override controls | Admin portal | Model registry table, drift indicators, override flow |
| FS-3.3 | Multi-language support for patient-facing screens | i18n | `next-intl`, locale-prefixed routes, zero hard-coded strings in patient UI |
| FS-3.4 | Performance optimisation pass | Performance | Measure first (Lighthouse + API p95 baseline), then act |

### Sprint 4 — 5 tasks

| # | Task | Module | Deliverable |
|---|---|---|---|
| FS-4.1 | UAT with clinical staff and patient representatives | Testing | Scripted scenarios in `docs/testing/uat-scenarios.md` |
| FS-4.2 | Full accessibility audit with remediation | Accessibility | Manual audit report + fix log |
| FS-4.3 | Cross-browser and cross-device testing | Testing | Playwright matrix: Chromium, Firefox, WebKit |
| FS-4.4 | Bug fixing and polish pass | Quality | Structured defect register per brief §35 |
| FS-4.5 | Production deployment and smoke testing | Deployment | Docker Compose staging, health checks, rollback plan |

### Boundary note — what Full Stack does NOT own

Per ASSUMPTIONS I3 and B6, these belong to other domains and Full Stack consumes them via API
contract only:

- Triage / no-show / readmission / forecasting **models** — AI/ML and Data Science
- LLM prompts, RAG index, guardrails — Gen AI
- BI dashboards in Power BI / Metabase — Data Analytics (our admin dashboard is the *in-app* view)
- Booking API, scheduling engine, FHIR integration, notification service — **Python domain per the
  plan**, though the Full Stack brief instructs me to build them. Unresolved: ASSUMPTIONS B6.

Because of B6, the backend in this repository is built so that it can either be *ours* or be
*replaced by the Python domain's implementation* without touching the frontend — the OpenAPI
contract is the seam.

---

## K. Risks

Ranked by expected impact on delivery.

### Technical

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Scope: 19 Full Stack tasks each expand into 5–10 real subtasks | High | High | Deliver the P0 vertical slice first (§L); explicitly mark prototypes as prototypes |
| Booking race conditions under concurrent load | Medium | High | Prevented at the **database** level via a partial unique index, not in application code. See `03-data-model.md` §4 |
| Frontend/backend contract drift | Medium | Medium | Single OpenAPI spec is the source of truth; TS types generated from it, CI fails on drift |
| Next.js App Router server/client boundary mistakes leaking secrets | Medium | High | Auth token never in a client component; server-only module marker on the API client |

### Dataset

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| **No dataset exists** (BLOCKER B1) | Certain | High | Synthea + operational generator; every row labelled `SYNTHETIC` |
| Operational data has no source at all (B2, B4) | Certain | High | Purpose-built generator, calibrated against Tier 2 aggregates, labelled in UI |
| Synthetic data behaves differently from real data | Certain | Medium | Never present model metrics from synthetic data as predictive of real performance |
| Synthea's US shape leaks into a "UK" product | High | Medium | UK identity overlay; explicit conversion step, not incidental |

### Integration

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Sandbox FHIR server is well-behaved; real EHRs are not | Certain | Medium (deferred) | `FHIRService` interface with a deliberately hostile mock for testing missing fields |
| LLM provider latency or outage blocks the chat UI | Medium | Medium | Chat degrades to a clear error + escalation path, never a hang |
| Model endpoints unavailable | Medium | High | **Fail toward escalation** (P9). Triage unavailable ⇒ higher urgency + human review flag |

### Security

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Patient reads another patient's record (IDOR) | Medium | Critical | Server-side ownership check on every patient-scoped route; explicit test case |
| Frontend-only route protection mistaken for security | Medium | Critical | Middleware is UX convenience only; every endpoint independently authorises |
| Clinical content leaks into logs | Medium | High | Structured logging with an allowlist; `audit_logs.metadata` carries identifiers only |
| Stack traces exposed to users | Low | Medium | Global exception handler returns coded errors; traces to server logs only |

### Accessibility

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Charts inaccessible to screen readers | High | High (legal, C5) | Every chart paired with a visually-hidden data table; never colour alone |
| Urgency communicated by colour alone | High | High | `PriorityFlag` always renders icon + text + colour |
| Modal focus traps done wrong | Medium | Medium | One audited `Dialog` primitive; never hand-rolled per feature |
| Accessibility deferred to Sprint 4 and then unaffordable | High | High | Built into the primitives in Sprint 1; Sprint 4 audits rather than retrofits |

### Clinical safety

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| UI implies the AI has diagnosed the patient | Medium | Critical | Copy rules in `04-frontend-spec.md`; provenance badge mandatory on all AI output |
| AI draft becomes the record without review | Low | Critical | Structurally impossible: `ai_documents` is immutable, approval is a separate row |
| Patient with an emergency uses the chatbot instead of calling 999 | Medium | Critical | Red-flag detection short-circuits the conversation with emergency-services guidance; persistent banner |
| Clinician automation bias — rubber-stamping AI drafts | Medium | High | UI shows the diff between generated and approved text; approval requires an explicit action, never a default |
| No Clinical Safety Officer exists (B5) | Certain | Blocking for real use | Documented as a non-claim; system labelled non-clinical throughout |

---

## L. MVP definition

**The MVP is one vertical slice that works end to end for all three roles.** Breadth is the enemy
here; the plan already contains more breadth than 8 weeks can support.

### P0 — must work, fully, before anything else starts

1. **Auth + RBAC** — register, login, refresh, logout; four roles; server-side authorisation on
   every endpoint; a patient provably cannot read another patient's data.
2. **Appointment booking** — list slots, hold, book, reschedule, cancel; double-booking prevented
   at the database level; race conditions return a clean `409 APPOINTMENT_CONFLICT`.
3. **Patient portal** — dashboard, appointment list and detail, profile.
4. **Staff queue and patient record** — queue with priority column; record view with encounters,
   observations, conditions, medications; every record view audited.
5. **Responsive + accessible** to WCAG 2.1 AA across every P0 screen.
6. **Audit logging** on all of the above.

### P1 — the project is not recognisable without these, but they can be thinner

7. Chatbot UI with escalation state and safety messaging.
8. Rule-based triage producing a priority signal that actually filters slot availability.
9. AI document review workflow — draft, edit, approve, with immutable original.
10. Admin dashboard with the six KPI cards and two charts.
11. Notification outbox and reminder scheduling.

### P2 — build only if P0 and P1 are genuinely finished

12. Model monitoring panel with drift indicators.
13. Model override UI.
14. Forecast visualisations.
15. Second locale.
16. Performance optimisation beyond the measured baseline.

### Definition of done for the MVP

A single scripted demo runs without intervention:

```
patient@example.test  registers → describes a symptom → receives a priority signal
                      → sees slots filtered by urgency → books → gets confirmation
doctor@example.test   logs in → sees that patient in the queue with a priority flag
                      → opens the record → reads an AI draft summary
                      → edits it → approves it
admin@example.test    logs in → sees the appointment reflected in the KPI cards
                      → sees the record-view event in the audit log
```

Every step above is covered by an automated test. If the demo cannot run unattended, the MVP is
not done regardless of how many individual features exist.
