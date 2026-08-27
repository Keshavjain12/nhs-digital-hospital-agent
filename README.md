# NHS Digital Hospital Agent

An end-to-end digital hospital platform connecting patient self-service, clinical workflow and
hospital operations, with AI used as an assistant at four specific points — never as the final
medical decision-maker.

> ## ⚠ This is a student / portfolio project
>
> It is **not** an NHS service. It is not approved, assessed or certified by any NHS body, and it
> must not be used for real patient care.
>
> It is **not**: NHS-approved · DTAC-assessed · DSPT-certified · DCB0129/0160-compliant ·
> FHIR UK Core conformance-tested · clinically validated.
>
> All data in this repository is **synthetic**. No record describes a real person.

---

## Current status

**Sprint 0 — architecture and planning complete. No code written yet.**

The analysis requested in the project brief §41 is complete and lives in `docs/`. Implementation
begins once the two open decisions in `ASSUMPTIONS.md` (B1, B6) are resolved.

| Deliverable | Status |
|---|---|
| Project analysis, scope, risks, MVP | ✅ `docs/architecture/01-analysis-and-scope.md` |
| System architecture and repo structure | ✅ `docs/architecture/02-system-architecture.md` |
| Database schema | ✅ `docs/architecture/03-data-model.md` |
| Frontend specification | ✅ `docs/architecture/04-frontend-spec.md` |
| Full Stack sprint plan | ✅ `docs/architecture/05-fullstack-sprint-plan.md` |
| API contract v1 | ✅ `docs/api/api-contract-v1.md` |
| RBAC, authorisation and audit | ✅ `docs/security/rbac-and-audit.md` |
| Dataset strategy and gap analysis | ✅ `docs/data/dataset-strategy.md` |
| Assumption register | ✅ `ASSUMPTIONS.md` |
| Backend implementation | ⬜ Sprint 1 |
| Frontend implementation | ⬜ Sprint 1 |

---

## Where to start reading

1. **`ASSUMPTIONS.md`** — what is confirmed, what is inferred, what is proposed, and what is
   blocked. Read this first; everything else depends on it.
2. **`docs/data/dataset-strategy.md`** — explains why there is no dataset and what we do about it.
3. **`docs/architecture/01-analysis-and-scope.md`** — the project, the 19 Full Stack tasks, risks,
   and the MVP definition.
4. **`docs/api/api-contract-v1.md`** — the frontend/backend seam.

---

## Architecture at a glance

```
Next.js 16 (App Router, TS, Tailwind)
   patient portal · staff portal · admin portal
            │  typed client generated from OpenAPI
            ▼
FastAPI  routers → services → repositories
            │            └── integrations: FHIR · triage engine · LLM · notifications · identity
            ▼
PostgreSQL 16
   identity · clinical · operational · ai · audit · analytics
```

Full detail in `docs/architecture/02-system-architecture.md`.

### Three design decisions worth knowing up front

1. **Double booking is prevented by the database, not by application code.** A partial unique index
   on `appointments(slot_id)` filtered to active statuses makes two simultaneous bookings of one
   slot impossible at the storage layer.

2. **AI drafts are immutable.** `ai_documents.generated_content` is protected by a trigger.
   Clinician edits create revisions; approval is a separate row. What the model produced, what the
   human changed, and who accepted it stay three distinct, recoverable facts.

3. **Admins cannot read clinical records.** Operational and clinical authority are separated
   deliberately. An operations manager does not need a diagnosis to manage bed capacity, and
   granting the access anyway creates risk with no benefit.

---

## Technology

| Layer | Choice | Why |
|---|---|---|
| Frontend | Next.js 16, TypeScript, Tailwind | Route groups per portal; native i18n routing; server components for dashboards |
| API state | TanStack Query | Cache invalidation and mutation rollback for booking |
| Charts | Recharts | SVG we can annotate for screen readers |
| Backend | FastAPI, Pydantic v2 | OpenAPI generation feeds the frontend type generator |
| ORM | SQLAlchemy 2.0 + Alembic | Typed queries; raw DDL control for partial indexes and exclusion constraints |
| Database | PostgreSQL 16 | Partial unique indexes and GiST exclusion constraints underpin the booking guarantee |
| Auth | OAuth2 password flow, JWT + rotating refresh, argon2id | Real revocation; CIS2-ready via an `IdentityProvider` port |
| Testing | pytest, vitest, Playwright, axe-core | Covers the cross-browser and accessibility requirements |

Rationale for every choice, and for what was rejected, in
`docs/architecture/02-system-architecture.md` §D.

---

## Getting started

> Not yet runnable. This section describes the Sprint 1 target so the setup contract is agreed
> before the code exists.

```bash
git clone <repo> && cd nhs-digital-hospital-agent
cp .env.example .env          # fill in local values; never commit .env
docker compose up -d          # postgres, api, web, worker

docker compose exec api alembic upgrade head
docker compose exec api python scripts/import_synthea.py --count 200
docker compose exec api python scripts/generate_operational_data.py --weeks 12
docker compose exec api python scripts/seed_demo.py
```

| Service | URL |
|---|---|
| Frontend | http://localhost:3000 |
| API | http://localhost:8000 |
| API docs | http://localhost:8000/docs |
| Health | http://localhost:8000/health |

### Demo accounts

Synthetic only, per brief §39. Passwords come from `.env`; there are no default credentials in
source.

| Role | Email |
|---|---|
| Patient | `patient@example.test` |
| Nurse | `nurse@example.test` |
| Doctor | `doctor@example.test` |
| Admin | `admin@example.test` |

All demo contact details use RFC 2606 reserved domains and the Ofcom drama phone range
(`+44 7700 900xxx`), so a bug in the notification service cannot reach a real person.

---

## Environment variables

See `.env.example`. No secret is ever committed.

```
DATABASE_URL=
JWT_SECRET=
JWT_ACCESS_TTL_SECONDS=900
REFRESH_TOKEN_TTL_DAYS=14
FHIR_BASE_URL=
FHIR_MODE=local|sandbox
LLM_API_KEY=
LLM_MODEL=
TRIAGE_ENGINE=rules|ml
NOTIFICATION_SINK=console|smtp
REDIS_URL=
CORS_ORIGINS=
LOG_LEVEL=
ENVIRONMENT=development|testing|staging|production
```

---

## Testing

```bash
docker compose exec api  pytest                      # unit, integration, security, contract
docker compose exec web  npm run test                # vitest
docker compose exec web  npm run test:e2e            # playwright, 3 browsers
docker compose exec web  npm run test:a11y           # axe-core
```

Test strategy in `docs/architecture/05-fullstack-sprint-plan.md`. The two suites that matter most:

- **B1–B10** — booking concurrency, run against real Postgres. B2 fires 20 simultaneous bookings at
  one slot and asserts exactly one succeeds. Run 50× in CI.
- **S1–S20** — security, in `docs/security/rbac-and-audit.md` §6. Covers IDOR, privilege
  escalation, token replay, audit immutability and log leakage.

---

## Known limitations

Stated plainly, per brief §34.

| Limitation | Detail |
|---|---|
| No real dataset exists | The supplied "dataset guide" lists sources; it is not data. See `docs/data/dataset-strategy.md`. |
| Operational data is entirely invented | No open UK source provides slots, rosters or live occupancy. Generated and labelled `SYNTHETIC` everywhere. |
| FHIR is shaped, not conformant | Tables mirror FHIR resource boundaries; no UK Core conformance testing has been done. |
| SNOMED CT is a demo subset | The full UK release requires a TRUD licence this project may not qualify for. |
| No Clinical Safety Officer | DCB0129/0160 cannot be validly satisfied. We build the technical substrate a safety case would need, and claim nothing more. |
| CIS2 is a stub | The `IdentityProvider` port exists; no NHS identity integration is available to us. |
| Models are not owned by Full Stack | Triage, no-show, readmission and forecasting belong to the AI/ML and Data Science domains. Full Stack builds against the contract. |
| Model metrics come from synthetic data | They say nothing about real-world performance and must never be quoted as if they did. |

---

## Documentation map

```
ASSUMPTIONS.md                              CONFIRMED / INFERRED / PROPOSED / BLOCKED register
docs/
├── architecture/
│   ├── 01-analysis-and-scope.md            understanding · 19 tasks · risks · MVP
│   ├── 02-system-architecture.md           layers · data flows · repo structure · tech choices
│   ├── 03-data-model.md                    full schema with constraints and rationale
│   ├── 04-frontend-spec.md                 routes · design system · states · copy rules · i18n
│   └── 05-fullstack-sprint-plan.md         week-by-week plan for all four sprints
├── api/api-contract-v1.md                  the frontend/backend seam
├── security/rbac-and-audit.md              roles · permission matrix · audit · 20 security tests
├── data/dataset-strategy.md                the missing dataset, and what we do instead
└── testing/                                UAT scenarios · defect register · performance baseline
```

---

## Licence and data provenance

Code: to be decided. Data: synthetic, generated by Synthea (Apache 2.0) plus this project's own
operational generator. No real patient data is present in this repository, and none may be added
without formal Information Governance approval — per the golden rule in the supplied Dataset Guide.
