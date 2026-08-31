# User acceptance scenarios

**Status:** 19 automated scenarios executed and passing, 31 August 2026. 12 manual
scenarios defined and **not yet run**.

Acceptance testing asks a different question from the unit suite. The 249 backend tests ask
whether each function is correct against a throwaway database; these ask whether a person in
one of the three user groups can actually do the thing they came to do, driving the real
service over HTTP as a signed-in user against seeded data.

`backend/scripts/uat_run.py` executes every scenario in §2–§5 and exits non-zero if any
fails, so it can gate a release. The scenarios in §6 need eyes on a screen and are recorded
as NOT RUN rather than assumed.

> This is a coursework build on synthetic data. Passing these scenarios does not make the
> service clinically approved, DTAC-compliant, DSPT-certified or fit for patient use. See
> `ASSUMPTIONS.md`.

---

## 1. How to run it

```bash
docker compose exec api python scripts/uat_run.py            # PASS/FAIL per scenario
docker compose exec api python scripts/uat_run.py --verbose  # with the evidence behind each
```

The run is non-destructive: anything it books it also cancels, so the seeded data is the
same afterwards as before. An earlier version did not release the slot contended in P3, and
the demo patient accumulated an extra appointment on every run — worth stating because a
test that quietly changes the data it measures stops being repeatable.

A scenario that cannot run reports **SKIP**, listed separately and never counted as a pass.
An absent precondition is not evidence of correctness.

---

## 2. Patient scenarios

| Ref | Scenario | Expected | Result | Evidence from the run |
| --- | --- | --- | --- | --- |
| P1 | Patient views their appointments | Their own bookings, nobody else's | **PASS** | 200, 11 own bookings |
| P2 | Patient books an available slot | Confirmed with a reference | **PASS** | `APT-2026-016014` issued |
| P3 | The same slot cannot be booked twice | Second attempt refused | **PASS** | 201 then 409 |
| P4 | Patient cancels a booking | Moves to cancelled | **PASS** | status `CANCELLED` |
| P5 | Red-flag symptoms escalate | Emergency advice, not a booking | **PASS** | band `EMERGENCY`, session escalated, 999 shown |
| P6 | Meaningless input does not advance the intake | Re-asks the question | **PASS** | `.` did not advance the stage |

**P5 is the most important scenario in this document.** It is asserted on the session's own
escalation state and the triage band, not on a substring: a page that merely contains the
word "emergency" in a footer would satisfy a text search while doing nothing. The check is
`escalatedAt` set **and** band returned **and** 999 present in the reply.

**P6** is regression cover for a defect found in Sprint 3, where typing `.` was answered
with "Thank you. How long has this been going on?" — the intake treated input it had not
understood as an answer.

---

## 3. Clinical scenarios

| Ref | Scenario | Expected | Result | Evidence from the run |
| --- | --- | --- | --- | --- |
| C1 | Clinician sees a working list | Patients listed | **PASS** | 17 listed |
| C2 | Record access follows the care relationship | Assigned open, others refused | **PASS** | 3 open, 9 refused |
| C3 | Break-glass refuses a thin reason | Rejected | **PASS** | one word → 400 |
| C4 | Break-glass opens the record | Access granted | **PASS** | record 200 after grant |
| C5 | Clinician cannot reach admin functions | Refused | **PASS** | `/admin/overview` → 403 |

**C2 is the scenario that would matter most in a real deployment.** The brief's rule is that
a patient's record is not readable by any clinician who happens to be logged in. The run
shows the split directly: of twelve records attempted, three opened on the strength of a
care assignment and nine were refused. A result where *all* twelve opened would pass a
naive "clinician can view records" test while proving the control absent — so the scenario
fails if nothing is refused, not only if nothing is allowed.

---

## 4. Administrative scenarios

| Ref | Scenario | Expected | Result | Evidence from the run |
| --- | --- | --- | --- | --- |
| A1 | Administrator sees the service overview | KPIs returned | **PASS** | cards, departments, meta |
| A2 | Break-glass appears in the audit trail | Recorded permanently | **PASS** | 2 `BREAKGLASS_INVOKED` entries |
| A3 | Monitoring separates under- and over-triage | Two distinct measures | **PASS** | `under_triage`, `over_triage` present |

**A2 is the control, not C3.** Asking a clinician for a justification is a prompt, and a
prompt alone stops nobody. What makes emergency access safe is that it is permanently
recorded and visible to an administrator afterwards. A2 asserts the record exists; the
append-only trigger from migration 0001 is what stops it being edited away.

**A3** exists because a single "accuracy" figure would hide the distinction that matters
clinically. Under-triage — telling someone their symptoms are less urgent than they are —
is the dangerous direction. Over-triage wastes clinical time. Averaging them into one
number would let a rise in the dangerous one be masked by a fall in the harmless one.

---

## 5. Cross-cutting scenarios

| Ref | Scenario | Expected | Result | Evidence from the run |
| --- | --- | --- | --- | --- |
| X1 | Unauthenticated access refused | 401 | **PASS** | 401 |
| X2 | Forged token refused | 401 | **PASS** | 401 |
| X3 | Errors do not leak internals | No stack trace or SQL | **PASS** | clean 404, no leaked markers |
| X4 | Every response is traceable | `X-Request-ID` present | **PASS** | present on success and error |
| X5 | Security headers applied | CSP, nosniff, referrer policy | **PASS** | all present |

X3 scans the error body for `traceback`, `sqlalchemy`, `psycopg`, `asyncpg`, `file "/` and
`select ` — the markers that would indicate an internal detail reaching a user. X4 checks
both the success and the error path, because the error path is the one that previously
bypassed the middleware stack and returned no request id at all.

---

## 6. Manual scenarios — DEFINED, NOT RUN

These cannot be asserted over HTTP. They are listed so that the 19 passes above are not
mistaken for full coverage, and they feed directly into the accessibility audit and
cross-browser tasks that follow.

| Ref | Scenario | What to check |
| --- | --- | --- |
| M1 | Symptom check, keyboard only | Every step reachable and completable without a mouse |
| M2 | Symptom check with a screen reader | Questions and the emergency banner announced; the banner is not skipped |
| M3 | Emergency advice is unmissable | Escalation is visually dominant, stated once, not repeated into noise |
| M4 | Booking flow, keyboard only | Slot selection and confirmation reachable; focus visible throughout |
| M5 | Cancel confirmation dialog | Focus trapped, Escape closes, focus returns to the trigger, safe action first |
| M6 | Welsh with a draft translation | Safety-critical strings show English alongside; `lang` set so the voice switches |
| M7 | Clinical queue at 200% zoom | No horizontal scrolling; priority flags still distinguishable |
| M8 | Priority flags without colour | Urgency conveyed by more than hue alone |
| M9 | Service unavailable | The UI fails into a safe, explained state rather than a blank screen |
| M10 | Session expiry mid-form | The patient is told, and does not silently lose what they typed |
| M11 | Cross-browser: Chrome, Firefox, Safari, Edge | Layout and the `<dialog>` behave consistently |
| M12 | Mobile viewport, 360 px | Patient screens usable; tap targets large enough |

---

## 7. What these scenarios do not cover

- **Concurrency.** Every scenario is a single user acting alone. Booking has a separate
  20-way concurrency test for correctness, but no acceptance scenario covers contention.
- **Clinical validity.** Whether the triage bands are *clinically right* is not a question
  automated acceptance testing can answer. It needs clinical review, which is blocker B3 in
  `ASSUMPTIONS.md` and has not happened.
- **Real users.** No patient or clinician has used this. "User acceptance" here means the
  scenarios a user would perform, executed by a script — not observed sessions with real
  people, which is what the term means in a real NHS procurement.
- **Data quality.** Everything runs against synthetic seeded data. See
  `docs/data/dataset-strategy.md`.
