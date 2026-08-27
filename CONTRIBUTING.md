# Contributing

Coding standards, branching and commit conventions. Covers the Sprint 1 task
"repo structure, coding standards, and branching strategy".

---

## Branching

A trunk-based model with short-lived branches. With a two-month timeline, long-running
branches would spend more time being merged than being useful.

```
main ──●──────●──────●──────●──────●──────►   always deployable, protected
        \    /        \    /
         ●──●          ●──●                    feature branches, hours to ~2 days
```

| Branch | Purpose | Lifetime |
|---|---|---|
| `main` | Always deployable. Never committed to directly. | Permanent |
| `feat/<scope>-<summary>` | A new capability | Hours to 2 days |
| `fix/<scope>-<summary>` | A defect fix | Hours |
| `docs/<summary>` | Documentation only | Hours |
| `chore/<summary>` | Tooling, dependencies, CI | Hours |

Examples: `feat/booking-slot-holds`, `fix/auth-refresh-rotation`, `chore/ci-axe-step`.

**A branch that has been open more than two days should be split.** The usual cause is a
change that bundled three things together, and the usual fix is to ship the smallest one.

## Merging

Squash-merge into `main`, so `main`'s history is one commit per reviewed change. The
branch's working commits stay in the PR for review and do not pollute the trunk.

`main` requires: CI green (lint, format, types, tests, contract drift, axe) and one review.

---

## Commit messages

Conventional Commits. The type is not decoration — it is what makes
`git log --grep '^fix'` a usable answer to "what broke and when".

```
<type>(<scope>): <imperative summary>
```

| Type | Use for |
|---|---|
| `feat` | New capability |
| `fix` | Defect fix |
| `docs` | Documentation |
| `test` | Tests only |
| `refactor` | Behaviour-preserving change |
| `perf` | Performance, with a before/after figure in the body |
| `chore` | Tooling, dependencies, CI |

Scopes: `api`, `auth`, `booking`, `records`, `triage`, `chat`, `documents`, `admin`,
`ui`, `a11y`, `db`, `docker`, `ci`.

Good:

```
feat(booking): prevent double booking with a partial unique index
fix(auth): revoke the whole token chain on refresh reuse
test(booking): add 20-way concurrent slot booking test
docs: record why admins have no clinical record access
```

Not acceptable: `update`, `fixes`, `wip`, `finished project`.

Write the body when the *why* is not obvious from the diff. A commit that changes a
security or clinical-safety boundary must explain the reasoning, because the next person
to touch it will otherwise assume it was arbitrary.

---

## Before you push

```bash
# backend
cd backend
.venv/Scripts/python -m ruff check . --fix
.venv/Scripts/python -m ruff format .
.venv/Scripts/python -m mypy app
.venv/Scripts/python -m pytest -q
```

CI runs the same commands. Running them locally is faster than waiting for a red build.

---

## Coding standards

### Python

- Type hints everywhere; `mypy` runs in strict mode and the build fails on an error.
- Pydantic schemas define the API contract. All wire schemas inherit `CamelModel`
  (`app/schemas/base.py`) — snake_case in Python, camelCase in JSON. Never spell a
  camelCase attribute name in Python.
- Layering is one-directional: `api → services → repositories → models`. A router must not
  import a model directly, and a service must not import `fastapi`.
- Every error reaching a client is an `AppError` subclass. Raw exceptions are bugs.
- Comment the *why*, never the *what*.

### TypeScript / React

- No `any`. API types are generated from OpenAPI into `types/generated/` and are never
  hand-edited.
- `components/ui/` knows nothing about the hospital domain. `features/` knows nothing
  about CSS internals. Enforced by lint rule.
- Every page implements all six UI states: loading, success, empty, error, unauthorized,
  not found.
- No hard-coded user-facing strings in patient-facing code — translation keys only.

---

## Rules that are not negotiable

These guard properties that cannot be retrofitted. A PR touching one of them needs an
explicit justification in the description.

1. **Never commit a secret.** `.env` is gitignored. If a secret is ever committed, rotate
   it — removing the commit is not sufficient, because it has already been distributed.
2. **Never log a password, token, NHS number or clinical free text.** Redaction is
   enforced by the formatter (`app/core/logging.py`) and tested in
   `tests/security/test_log_redaction.py`.
3. **Never rely on frontend route protection for security.** Every sensitive endpoint
   authorises server-side, independently.
4. **Never let an AI-generated draft become the record without clinician approval.**
   `ai_documents.generated_content` is immutable by database trigger.
5. **Never present synthetic data as real.** Anything derived from generated data carries
   `dataOrigin: "SYNTHETIC"` and renders the notice.
6. **Never claim NHS approval, DTAC/DSPT compliance, or clinical validation.** See the
   non-claims list in `ASSUMPTIONS.md`.
7. **Accessibility is not a Sprint 4 task.** A new component ships keyboard-operable and
   labelled, or it does not ship.

---

## Adding a new endpoint

The order matters — it is what keeps the frontend and backend from inventing different
shapes (brief §31).

1. Write the contract in `docs/api/api-contract-v1.md` first: method, path, auth, roles,
   request, response, errors.
2. Add the Pydantic schemas in `app/schemas/`.
3. Add the service method, with its unit test.
4. Add the router, with the authorisation dependency and its audit event.
5. Add integration and security tests, including the "wrong role" and "other user's
   resource" cases.
6. Regenerate frontend types; CI fails if they are stale.
