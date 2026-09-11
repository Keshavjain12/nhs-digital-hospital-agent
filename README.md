# NHS Digital Hospital Agent

[![CI](https://github.com/Keshavjain12/nhs-digital-hospital-agent/actions/workflows/ci.yml/badge.svg)](https://github.com/Keshavjain12/nhs-digital-hospital-agent/actions/workflows/ci.yml)

An end-to-end digital hospital platform connecting patient self-service, clinical workflow and
hospital operations. AI is used as an assistant — never as the final medical decision-maker:
every automated suggestion is labelled as such, and a clinician's decision is recorded alongside
it.

> ## ⚠ This is a student / portfolio project
>
> It is **not** an NHS service. It is not approved, assessed or certified by any NHS body, and it
> must not be used for real patient care.
>
> It is **not**: NHS-approved · DTAC-assessed · DSPT-certified · DCB0129/0160-compliant ·
> FHIR UK Core conformance-tested · clinically validated · production-ready.
>
> All data in this repository is **synthetic**. No record describes a real person.

---

## Status

All four sprints of the Full Stack plan are complete and merged to `main`.

| Sprint | What it delivered |
|---|---|
| 1 — Foundation | Docker stack, FastAPI, PostgreSQL schema, authentication (argon2id, JWT with rotating refresh tokens, lockout, password reset), Next.js portals, NHS-styled design system, wireframes |
| 2 — Core slice | Appointment slots and booking with a database-level double-booking guarantee, patient portal, clinical working list, patient records restricted to the care team with audited emergency access |
| 3 — AI surfaced | Symptom-check conversation, rule-based triage, clinician review and override, model monitoring, Welsh (draft) translation, performance baseline |
| 4 — Validation | Acceptance scenarios, WCAG 2.1 AA audit and cross-browser testing in three engines, rescheduling, a production-shaped deployment with a nonce-based Content-Security-Policy |

Blockers that engineering cannot resolve — no clinician-availability or triage ground-truth
dataset, and no named Clinical Safety Officer — are recorded in [`ASSUMPTIONS.md`](ASSUMPTIONS.md),
along with the defects found and closed.

---

## Running it

You need Docker Desktop and Node.js 22 or later.

```bash
cp .env.example .env
# In .env, set POSTGRES_PASSWORD, JWT_SECRET and DEMO_PASSWORD. Generate a secret with:
#   python -c "import secrets; print(secrets.token_urlsafe(48))"

docker compose up -d                                   # PostgreSQL, Redis and the API
docker compose exec api alembic upgrade head          # create the schema
docker compose exec api python scripts/seed_demo.py   # synthetic demonstration data

cd frontend
cp .env.example .env.local
npm ci
npm run dev                                            # add  -- -p 3001  if port 3000 is taken
```

| | URL |
|---|---|
| App | http://localhost:3000 (or 3001) |
| API | http://localhost:8000 |
| API reference | http://localhost:8000/docs |
| Health | http://localhost:8000/health |

The browser only ever talks to the app. `/api/v1` is proxied to the API by
`frontend/next.config.ts`, so the session cookie is first-party and no cross-origin request is
made.

### Demo accounts

| Role | Email |
|---|---|
| Patient | `patient@example.test` |
| Nurse | `nurse@example.test` |
| Doctor | `doctor@example.test` |
| Administrator | `admin@example.test` |

The password is the `DEMO_PASSWORD` you set before seeding. The sign-in page lists
`demo-hospital-2026`, so use that value unless you change the page too.

Demo contact details use RFC 2606 reserved domains and the Ofcom drama phone range, so a bug in
notifications cannot reach a real person.

- **Demo data ages.** Slots are generated forward from the day you seed. If the appointments
  screen looks empty, re-run `seed_demo.py` — it is safe to run repeatedly.
- **Locked out?** Sign-in allows 15 attempts per 15 minutes and keeps the count in Redis:
  `docker compose exec redis redis-cli FLUSHDB` clears it.
- **All times are UK times**, whatever time zone your device is set to.

### Production-shaped deployment

`docker-compose.prod.yml` runs built images, applies migrations before the API starts, and
publishes only the web service. It is not production-ready — see
[`docs/deployment.md`](docs/deployment.md), including the list of what is missing.

---

## Testing

| What | Command |
|---|---|
| Backend lint, format and types | `cd backend && ruff check . && ruff format --check . && mypy app scripts` |
| Backend tests, against real PostgreSQL | `docker compose exec api pytest` |
| Frontend lint, types and unit tests | `cd frontend && npm run lint && npm run typecheck && npm test` |
| Browser suites: WCAG audit and cross-browser | `cd frontend && npx playwright test --project=chromium` (then `firefox`, `webkit`) |
| Acceptance scenarios against the running service | `docker compose exec api python scripts/uat_run.py` |
| API latency baseline | `docker compose exec api python scripts/benchmark.py` |

**Continuous integration** (`.github/workflows/ci.yml`) runs on every push to `main` and every
pull request: backend lint, format, types and tests against a real PostgreSQL; frontend lint,
types, unit tests and a production build; and an API contract check that fails if
`frontend/types/generated/api.d.ts` no longer matches the backend.

The browser suites are not in CI: they need the whole stack running with seeded data and three
browser engines, so they run against a live stack. They run serially on purpose — see
`frontend/playwright.config.ts` for why.

---

## Design decisions worth knowing

1. **Double booking is prevented by the database.** A partial unique index on
   `appointments(slot_id)`, limited to active statuses, makes two bookings of one slot
   impossible at the storage layer. A test fires 20 simultaneous bookings at one slot and
   asserts exactly one succeeds.
2. **Automated output cannot be quietly rewritten.** Triage results are append-only, enforced
   by a database trigger. A clinician's review is stored alongside the original, so what the
   engine said and what the clinician decided remain two separate, recoverable facts.
3. **Records follow the care relationship.** A clinician can open a record only for patients
   they are assigned to. Emergency access exists, requires a written reason, and is recorded in
   an append-only audit trail.
4. **Administrators cannot read clinical records.** Operational authority is not clinical
   authority: the admin views show that records were accessed, never whose.
5. **Every time is UK time.** Clinic hours are defined in Europe/London, and every screen
   formats times in that zone rather than the viewer's.

---

## Architecture

```
Next.js 16 (App Router, TypeScript, Tailwind)     patient · clinical · operations portals
       │  /api/v1 proxied on the app's own origin; types generated from OpenAPI
       ▼
FastAPI   routers → services → repositories        rule-based triage engine
       │
       ├── PostgreSQL 16   schemas per domain; audit trail append-only by trigger
       └── Redis 7         rate-limit counters shared by every API worker
```

[`docs/architecture/02-system-architecture.md`](docs/architecture/02-system-architecture.md) is
the design written before implementation. Where it and the code differ, the code and this
README are current.

| Layer | Choice | Why |
|---|---|---|
| Frontend | Next.js 16, TypeScript, Tailwind CSS 4, TanStack Query | Route groups per portal; mutations with rollback for booking |
| Backend | FastAPI, Pydantic v2, SQLAlchemy 2.0 (async), Alembic | OpenAPI feeds the frontend's generated types |
| Database | PostgreSQL 16 | Partial unique indexes and GiST exclusion constraints underpin the booking guarantee |
| Cache | Redis 7 | One rate-limit window shared by every API worker |
| Auth | Access token in memory, rotating refresh token in an httpOnly cookie, argon2id | Real revocation; replaying a spent refresh token ends every session |
| Testing | pytest, Vitest, Playwright, axe-core | Integration tests on real PostgreSQL; browser suites in three engines |

---

## Known limitations

| Limitation | Detail |
|---|---|
| No real dataset | The supplied dataset guide lists sources; it is not data. See [`docs/data/dataset-strategy.md`](docs/data/dataset-strategy.md). |
| Operational data is invented | No open UK source provides slots, rosters or live occupancy. Generated, and labelled synthetic everywhere. |
| No Clinical Safety Officer | DCB0129/0160 cannot be validly satisfied. |
| Triage is a rule-based stand-in | Not clinically reviewed. The real model belongs to the AI/ML workstream. |
| Welsh is machine-drafted | Unreviewed. Anything that affects care is shown in English alongside. |
| No email or SMS delivery | Notifications go to the console. Nothing is sent to anyone. |
| Not tested with real people | No patients, clinicians or assistive-technology users; no screen-reader testing. |
| Not production-ready | No TLS, secrets management, tested backups or monitoring — [`docs/deployment.md`](docs/deployment.md) §7. |
| Model metrics are from synthetic data | They say nothing about real-world performance. |

---

## Documentation map

```
ASSUMPTIONS.md                          confirmed · inferred · proposed · blocked; defects closed
CONTRIBUTING.md                         branching, commits, non-negotiable rules
docs/
├── architecture/01 … 05                analysis, architecture, data model, frontend spec, sprint plan
├── api/api-contract-v1.md              the frontend/backend seam
├── security/rbac-and-audit.md          roles, permissions, audit, security tests
├── data/dataset-strategy.md            the missing dataset, and what is done instead
├── design/wireframes/                  wireframe canvas
├── performance/baseline.md             measured latency, and the indexes it justified
├── testing/uat-scenarios.md            acceptance scenarios and their results
├── testing/accessibility-audit.md      WCAG 2.1 AA audit, and what automation cannot cover
├── testing/cross-browser.md            three-engine results, including a misdiagnosis corrected
└── deployment.md                       the production-shaped stack, and what is still missing
```

---

## Licence and data provenance

Code: to be decided. Data: synthetic, generated by this project's own scripts
(`backend/scripts/seed_demo.py`). No real patient data is present in this repository, and none
may be added without formal Information Governance approval — per the golden rule in the
supplied Dataset Guide.
