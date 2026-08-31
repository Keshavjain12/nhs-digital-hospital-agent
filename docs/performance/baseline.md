# Performance baseline

**Status:** measured, 28 August 2026. Sprint 3, task 4.

The brief's instruction was to establish a working baseline and measure before optimising.
This records what was measured, what was changed as a result, and — equally important —
what was left alone because the measurement said it was already fine.

Nothing in this document is a claim about production performance. Every figure is from a
single developer machine running Docker Desktop on Windows, over loopback, with one
concurrent user. They are useful for comparing one build of this service against another.
They are not a capacity plan and they do not predict what a patient on mobile data
experiences.

---

## 1. Why the first attempt measured nothing

The seeded demo database holds 17 patients, 4 appointments and 3,780 slots. Every query
against it is fast, because every table fits in a handful of pages and the planner can scan
the lot without noticing. A missing index is invisible at that size.

`backend/scripts/load_volume.py` inflates the tables to roughly a district general
hospital's working set:

| Table | Rows |
| --- | --- |
| `operational.appointment_slots` | 82,172 |
| `clinical.patients` | 26,669 |
| `operational.appointments` | 15,004 |
| `audit.audit_logs` | 221 |

Generated rows carry `data_origin = 'loadtest'` so `--clear` removes exactly those and
nothing else. The script runs `ANALYZE` afterwards, without which the planner works from
stale row estimates and the first measurements describe a database that no longer exists.

---

## 2. API latency

`backend/scripts/benchmark.py`, 30 runs per endpoint after one untimed warm-up request, so
connection setup and first-plan cost do not land entirely in the p95.

Milliseconds, after the changes in §3:

| Endpoint | p50 | p95 | max |
| --- | ---: | ---: | ---: |
| patient: available slots | 9.1 | 21.7 | 34.8 |
| patient: slots, one department | 9.4 | 17.8 | 21.9 |
| patient: my appointments | 5.4 | 7.0 | 7.1 |
| clinician: patient list | 10.7 | 13.3 | 14.3 |
| clinician: patient search | 16.0 | 22.4 | 23.9 |
| clinician: triage queue | 5.6 | 6.6 | 6.9 |
| admin: overview | 10.2 | 11.5 | 11.6 |
| admin: audit trail | 6.5 | 8.8 | 9.2 |
| admin: model monitoring | 5.3 | 7.0 | 9.1 |

Nothing is above 300 ms at p95, and nothing was above it before the changes either. **The
API did not need optimising for present-day speed.** The value of §3 is entirely in how
these numbers behave as the tables grow.

---

## 3. What was changed, and why

Migration `0004_performance_indexes`. Two query plans showed a sequential scan on a table
with no natural ceiling; both are now indexed. That is the whole of the change.

### 3.1 Patient search — trigram index

Clinicians search on what the patient said, not on how the record was filed: "the O'Neill
admitted yesterday" gets typed as `neill`. The service therefore matches a fragment
anywhere in the name (`app/services/patients.py`), which means `LIKE '%neill%'` — and a
leading wildcard makes a btree index unusable. `ix_patients_name_dob` already existed; the
planner correctly ignored it.

```
Before:  Seq Scan on patients  (rows=11111)   8.8 ms
After:   Bitmap Index Scan on ix_patients_given_name_trgm
       + Bitmap Index Scan on ix_patients_family_name_trgm   1.3 ms
```

`pg_trgm` indexes the three-character substrings of a value, which is what makes an
unanchored `LIKE` indexable. Both indexes are built on `lower(...)` to match what the query
actually asks for; an index on the raw column would not be used.

Two honest caveats:

- **The planner still chooses a sequential scan for an unselective term.** Searching
  `tester1` against the load data matches 11,111 of 26,669 rows, and scanning is genuinely
  the cheaper plan for a 42% match. That is the planner being right, not the index failing.
  Real name searches are selective; the synthetic data is not.
- **Terms shorter than three characters cannot use a trigram index at all.** A clinician
  typing `li` gets a sequential scan. This is inherent to the approach and acceptable: a
  two-letter search returns too many patients to be clinically useful anyway.

The gain is not the 7 ms. It is that search cost stops being proportional to the size of
the patient register — the old plan degraded precisely as the service succeeded.

### 3.2 Audit trail — index on `occurred_at`

The audit log is append-only and every access to patient data writes to it, so it is the
fastest-growing table in the system and the only one with no natural ceiling. It carried
indexes on `actor`, `action` and `resource` — the columns an investigation filters by — but
none on `occurred_at`, which is what the default view sorts by.

```
Before:  Seq Scan -> top-N heapsort   0.16 ms   (at 221 rows)
After:   Index Scan using ix_audit_occurred_at, no sort node   0.09 ms
```

At 221 rows this is a difference nobody could notice. The reason to do it now is that a
year of real traffic turns "sort the entire table to return twenty-five rows" into the
slowest page an administrator uses, and the fix is one index either way.

---

## 4. What was measured and deliberately left alone

Recording these matters as much as §3: each was a candidate for optimisation that the
evidence did not support.

**Slot availability** — already an `Index Scan using ix_slots_starts_at`, with the
exclusion of booked slots served by an `Index Only Scan` on the partial unique index
`uq_appointment_active_slot`. 2.9 ms. The indexes from migration 0002 are doing their job.
One thing to watch: that index-only scan reads all 15,002 active appointments to build the
anti-join, so it is proportional to the booked-appointment count rather than to the page
size. It is cheap now and there is no measurement justifying a change, but it is the next
thing that would show up.

**Frontend bundle** — 1,121 KB raw across all routes, **303 KB gzipped**, 22 KB of CSS.
That is the whole application; any single page loads a subset. For React plus TanStack
Query this is unremarkable, and no single chunk dominates in a way that would justify a
split. Left alone.

**Query caching** — `lib/query.tsx` already sets a 30-second `staleTime`, refetch on window
focus (deliberate: clinical data going stale in a background tab is a real risk), and a
retry predicate that never retries an authorisation failure. Nothing to add.

**Everything else in §2** — seven of the nine endpoints were already under 15 ms at p95.
Changing them would have been motion, not improvement.

---

## 5. Reproducing this

```bash
docker compose exec api python scripts/load_volume.py     # generate volume
docker compose exec api python scripts/benchmark.py       # measure
docker compose exec api python scripts/load_volume.py --clear   # remove it again
```

The load-test rows are removed after measuring so the demo database stays small and
legible. Regenerate them before any future performance work — comparing a new measurement
against §2 is only meaningful at the same volume.

---

## 6. Not covered

Stated so the gaps are not mistaken for clean results:

- **Concurrency.** Every figure is single-user. The booking path has a 20-way concurrency
  test for *correctness* (exactly one success, nineteen clean 409s), but throughput under
  concurrent load has not been measured.
- **Lighthouse / Core Web Vitals.** Not run. Bundle size is a proxy for it, not a
  substitute.
- **Real network conditions.** Loopback only. No latency, packet loss, or TLS handshake.
- **Sustained write load.** The audit log grows on every request; its write cost over
  months has not been modelled.
