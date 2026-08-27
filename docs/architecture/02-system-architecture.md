# 02 — System Architecture and Repository Structure

Covers brief §41 parts C and D.

---

## C. System architecture

### Layered view

```
┌──────────────────────────────────────────────────────────────────────────┐
│  PRESENTATION — Next.js 15 (App Router, TypeScript, Tailwind)            │
│                                                                          │
│   Patient portal        Staff portal           Admin portal              │
│   ─────────────         ────────────           ────────────              │
│   dashboard             queue                  KPI dashboard             │
│   chat + intake         patient record         occupancy / wait times    │
│   triage result         AI document review     alerts                    │
│   booking wizard        risk indicators        model monitoring          │
│   appointments          clinical summary       override controls         │
│   profile               discharge letter       audit viewer              │
│                                                                          │
│   shared: design system · i18n · a11y primitives · provenance badges     │
└───────────────────────────────┬──────────────────────────────────────────┘
                                │  HTTPS, JSON, typed client generated
                                │  from OpenAPI. No direct FHIR/LLM calls.
┌───────────────────────────────▼──────────────────────────────────────────┐
│  API — FastAPI                                                           │
│   routers: auth · users · patients · appointments · slots · records      │
│            triage · chat · documents · notifications · analytics         │
│            admin · models · audit · health                               │
│   cross-cutting: authn · authz · validation · rate limit · request-id    │
│                  error envelope · audit middleware · CORS · headers      │
└───────────────────────────────┬──────────────────────────────────────────┘
                                │
┌───────────────────────────────▼──────────────────────────────────────────┐
│  SERVICE — business logic, framework-agnostic, unit-testable             │
│   AuthService      SchedulingService    TriageService                    │
│   PatientService   BookingService       DocumentReviewService            │
│   RecordService    NotificationService  AnalyticsService                 │
│   AuditService     ModelRegistryService OverrideService                  │
└───────┬────────────────────────────────────────┬─────────────────────────┘
        │                                        │
┌───────▼──────────────────┐        ┌────────────▼─────────────────────────┐
│  REPOSITORY              │        │  INTEGRATIONS (ports & adapters)      │
│  SQLAlchemy 2.0          │        │   FHIRService      ─► sandbox / local │
│  one repo per aggregate  │        │   TriageEngine     ─► rules | ML API  │
│  no ORM objects escape   │        │   LLMProvider      ─► Claude API      │
│  above this line         │        │   NotificationSink ─► console | SMTP  │
└───────┬──────────────────┘        │   IdentityProvider ─► local | CIS2    │
        │                           └──────────────────────────────────────┘
┌───────▼──────────────────────────────────────────────────────────────────┐
│  DATA — PostgreSQL 16                                                    │
│   schema `clinical`     patients, encounters, observations, conditions   │
│   schema `operational`  slots, appointments, beds, notifications, staff  │
│   schema `ai`           chat, triage, risk scores, documents, models     │
│   schema `audit`        audit_logs (append-only)                         │
│   schema `analytics`    materialised views + snapshots (read-heavy)      │
└──────────────────────────────────────────────────────────────────────────┘
```

### Why every integration is behind an interface

The four adapters above are not architectural decoration. Each one exists because the underlying
dependency is either **unavailable** (CIS2, a real FHIR server), **owned by another domain**
(triage model, LLM prompts), or **dangerous to run for real in a demo** (SMS to a live handset).

```python
class TriageEngine(Protocol):
    def assess(self, intake: SymptomIntake) -> TriageAssessment: ...
```

Sprint 1 ships `RuleBasedTriageEngine`. When the AI/ML domain delivers a model, it ships
`MLTriageEngine` and the swap is one line of dependency wiring. The frontend does not change,
the API contract does not change, and the tests do not change. That is the seam that makes
parallel work across six domains possible at all.

### Critical data flows

#### Booking (the flow most likely to be got wrong)

```
1. GET /slots?departmentId&from&to&priority
   └─ SchedulingService filters by availability AND by triage priority band
2. POST /slots/{id}/hold           → 5-minute soft hold, returns holdToken
   └─ prevents two patients racing through a 4-step wizard
3. POST /appointments {slotId, holdToken}
   └─ BEGIN
      SELECT ... FROM appointment_slots WHERE id=? FOR UPDATE   ← row lock
      validate hold is ours and unexpired
      INSERT INTO appointments ...
        ↳ partial unique index on (slot_id) WHERE status IN (BOOKED,CHECKED_IN,IN_PROGRESS)
          raises IntegrityError if anyone beat us here
      UPDATE appointment_slots SET status='BOOKED', version=version+1
      INSERT INTO audit_logs (APPOINTMENT_CREATED)
      INSERT INTO notifications (reminder, scheduled_for = starts_at - 24h)
      COMMIT
   └─ IntegrityError ⇒ 409 { code: "APPOINTMENT_CONFLICT" }
```

The row lock handles the common case; the unique index is the guarantee. Application code cannot
create a double booking even if the lock logic is later refactored incorrectly. Brief §12 requires
conflict prevention "at the backend/database level" — this is what that means concretely.

#### AI clinical document review

```
POST /documents  {patientId, encounterId, kind}
  └─ assemble context ─► LLMProvider ─► ai_documents INSERT (status=DRAFT)
                                        generated_content is IMMUTABLE from here on
  └─ audit: AI_OUTPUT_GENERATED

PATCH /documents/{id}/content  (clinician edits)
  └─ INSERT ai_document_revisions   ← never an UPDATE of generated_content
  └─ audit: AI_OUTPUT_REVIEWED

POST /documents/{id}/approve
  └─ INSERT ai_document_reviews (decision=APPROVED, reviewer, timestamp,
                                 final_content_revision_id)
  └─ UPDATE ai_documents SET status='APPROVED'
  └─ audit: AI_OUTPUT_APPROVED
```

The original draft, every clinician edit, and the approval decision are three separate rows.
Reconstructing "what did the AI actually say, and what did the clinician change" is a query, not
an archaeology exercise. This is the technical substrate a DCB0129 safety case would need — though
per ASSUMPTIONS B5 we do not claim to have produced one.

#### Authentication

```
POST /auth/login  ─► AuthService ─► IdentityProvider (local | CIS2 later)
   └─ verify argon2id hash, constant-time
   └─ issue access JWT (15 min, role + subject claims)
   └─ issue refresh token → store SHA-256 hash in refresh_tokens
   └─ set refresh as httpOnly + Secure + SameSite=Strict cookie
   └─ audit: USER_LOGIN (result SUCCESS | DENIED)

Every subsequent request:
   Authorization: Bearer <access>
   └─ decode → load user → attach principal
   └─ route dependency asserts role AND resource ownership
   └─ audit middleware records sensitive reads
```

Note the split: the **access token** lives in memory in the browser (never `localStorage`, which is
XSS-readable); the **refresh token** lives in an httpOnly cookie the JS cannot touch. Neither alone
is sufficient for an attacker with a single class of vulnerability.

---

## D. Repository structure

Monorepo, matching brief §22 with deviations explained below.

```
nhs-digital-hospital-agent/
│
├── frontend/
│   ├── app/
│   │   └── [locale]/
│   │       ├── (public)/        login, register, forgot-password, reset-password
│   │       ├── (patient)/       dashboard, chat, appointments, profile
│   │       ├── (staff)/         queue, patients/[id], documents/[id]/review
│   │       ├── (admin)/         dashboard, models, alerts, audit
│   │       ├── layout.tsx
│   │       └── error.tsx / not-found.tsx / loading.tsx
│   ├── components/
│   │   ├── ui/                  design system primitives (19 components)
│   │   ├── charts/              accessible chart wrappers
│   │   └── layout/              header, sidebar, breadcrumbs, skip-link
│   ├── features/                vertical slices: booking, triage, records, chat, admin
│   ├── hooks/                   useAuth, useSession, useMediaQuery, useAnnounce
│   ├── lib/                     apiClient, auth, i18n, formatters, nhsNumber
│   ├── types/                   generated/api.ts  ← from OpenAPI, do not hand-edit
│   ├── messages/                en-GB.json, <second-locale>.json
│   ├── styles/
│   ├── public/
│   └── tests/                   unit (vitest) · e2e (playwright) · a11y (axe)
│
├── backend/
│   ├── app/
│   │   ├── api/v1/              routers, one per resource
│   │   ├── core/                config, security, deps, errors, logging, ratelimit
│   │   ├── models/              SQLAlchemy ORM
│   │   ├── schemas/             Pydantic request/response — the API contract
│   │   ├── services/            business logic
│   │   ├── repositories/        data access
│   │   ├── integrations/        fhir/ triage/ llm/ notifications/ identity/
│   │   └── main.py
│   ├── alembic/                 migrations
│   ├── scripts/                 seed_demo.py, generate_operational_data.py, import_synthea.py
│   └── tests/                   unit · integration · security · contract
│
├── data/
│   ├── raw/                     Synthea output (gitignored)
│   ├── processed/               transformed, UK-overlaid (gitignored)
│   └── README.md                provenance + regeneration instructions
│
├── docs/
│   ├── architecture/  api/  security/  data/  testing/
│
├── docker/                      Dockerfile.frontend, Dockerfile.backend
├── docker-compose.yml
├── .env.example
├── ASSUMPTIONS.md
└── README.md
```

### Deviations from the structure in brief §22, and why

| Change | Reason |
|---|---|
| `app/[locale]/` wraps everything | i18n is a Sprint 3 requirement (C11). Retrofitting a locale segment later means rewriting every route and every internal link. The segment costs nothing now and saves a painful migration. |
| Route groups `(public)/(patient)/(staff)/(admin)` | Each group gets its own layout, its own navigation and its own auth guard. Without groups, the guard logic ends up duplicated in every page. |
| `features/` holds vertical slices, `components/ui/` holds primitives | Brief §22 lists both but not the rule between them. The rule: `ui/` knows nothing about the hospital domain; `features/` knows nothing about CSS internals. Enforced by lint rule — `features/` may not import Tailwind config, `ui/` may not import from `features/`. |
| `types/generated/api.ts` is generated, not written | Prevents the frontend and backend independently inventing different shapes (brief §31). CI regenerates and fails on a diff. |
| Postgres **schemas** rather than separate databases | Analysis Report §8 wants analytics separated from live booking. Schemas give the logical separation and per-schema grants now; splitting to a separate store later is a connection-string change. Two database servers during an 8-week build is cost without benefit. |
| `backend/scripts/` is a first-class directory | Per BLOCKER B1/B2, data generation is not a side task — it is a prerequisite for the core module. |

### Technology choices and the reason for each

Per brief §5, no dependency without a justification.

| Choice | Reason | Rejected alternative |
|---|---|---|
| Next.js 16 App Router | Route groups per portal; native i18n routing; server components shrink dashboard bundles | Vite SPA — would need a separate router, i18n and SSR story |
| TypeScript | Contract safety across a 3-portal surface; generated API types are worthless without it | — |
| Tailwind CSS | Design tokens map directly to NHS Service Manual values; no runtime CSS-in-JS cost | CSS Modules — more boilerplate for a token-driven system |
| TanStack Query | Booking and queue need cache invalidation, retries, and request dedup. Hand-rolling this is where bugs live | SWR — comparable; TanStack has better mutation/rollback ergonomics for booking |
| Recharts | SVG we can annotate for screen readers (C5) | Chart.js — canvas; accessibility is materially harder |
| next-intl | Works with App Router's locale segment; type-safe message keys | i18next — heavier, weaker App Router integration |
| FastAPI | Native OpenAPI generation feeds the frontend type generator; async suits FHIR/LLM I/O | Django REST — heavier, and we do not need the admin or ORM opinions |
| Pydantic v2 | The API contract *is* the schema; validation is not a separate layer | Manual validation — drifts immediately |
| SQLAlchemy 2.0 | Typed queries; and we need raw DDL for the partial unique index and GiST exclusion constraints | Tortoise/Prisma — weaker Postgres DDL control |
| Alembic | Migrations are required by brief §10 | — |
| PostgreSQL 16 | Partial unique indexes and GiST exclusion constraints are what make double-booking structurally impossible | MySQL — no partial indexes, no exclusion constraints; the booking guarantee would have to move into application code |
| Argon2id | Current password-hashing recommendation | bcrypt — acceptable, weaker against GPU attack |
| Playwright | One tool covers the cross-browser matrix required by FS-4.3 | Cypress — weaker WebKit story |
| axe-core | Automates the machine-checkable part of WCAG in CI | — |

**Deliberately not adopted:** Redis (until the outbox proves insufficient), Celery (Python-domain
task, and premature), Kubernetes (Compose is right for staging), a state-management library
(server state is TanStack Query's job; the little client state left does not need Redux), and a
component library like MUI (it would fight the NHS design tokens harder than building 19
primitives costs).
