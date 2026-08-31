"""Generate realistic data volume for performance measurement.

A performance pass against seventeen patients measures nothing: every query is fast when
the table fits in a single page. This inflates the tables to roughly the size of a district
general hospital's working set so that a missing index actually shows up.

Everything created is marked SYNTHETIC like the rest of the generated data, and uses the
same reserved contact ranges (see docs/data/dataset-strategy.md §4.1).

Bulk-inserted with generate_series rather than through the API: the point is to have the
rows, not to exercise the write path.

    docker compose exec api python scripts/load_volume.py --patients 20000 --slots 60000
    docker compose exec api python scripts/load_volume.py --clear
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time

from sqlalchemy import text

from app.core.db import get_session_factory

#: Marks rows this script created, so --clear removes exactly them and nothing else.
LOAD_MARKER = "loadtest"


async def clear() -> None:
    factory = get_session_factory()
    async with factory() as session:
        await session.execute(
            text("DELETE FROM operational.appointments WHERE reason_text = :m"),
            {"m": LOAD_MARKER},
        )
        await session.execute(
            text("DELETE FROM operational.appointment_slots WHERE data_origin = :m"),
            {"m": LOAD_MARKER},
        )
        await session.execute(
            text("DELETE FROM clinical.patients WHERE data_origin = :m"), {"m": LOAD_MARKER}
        )
        await session.commit()
    print("load-test rows removed")


async def generate(patients: int, slots: int, appointments: int) -> None:
    factory = get_session_factory()

    async with factory() as session:
        department_ids = (
            (await session.execute(text("SELECT id FROM operational.departments"))).scalars().all()
        )
        site_id = (
            await session.execute(text("SELECT id FROM operational.sites LIMIT 1"))
        ).scalar_one()

        if not department_ids:
            print("Seed the demo data first: python scripts/seed_demo.py", file=sys.stderr)
            return

        started = time.perf_counter()

        # Patients. NHS numbers are left null here: the unique constraint would force a
        # per-row checksum calculation, which is the seeder's job and not what this
        # measures.
        await session.execute(
            text(
                """
                INSERT INTO clinical.patients
                    (given_name, family_name, date_of_birth, sex_at_birth, email,
                     phone_e164, city, postcode, preferred_language, data_origin)
                SELECT
                    'Load' || i,
                    'Tester' || i,
                    DATE '1940-01-01' + (random() * 30000)::int,
                    CASE WHEN i % 2 = 0 THEN 'Female' ELSE 'Male' END,
                    'load' || i || '@example.test',
                    '+44770090' || lpad((i % 10000)::text, 4, '0'),
                    'Exampleton',
                    'EX1 1AA',
                    'en-GB',
                    :marker
                FROM generate_series(1, :n) AS i
                """
            ),
            {"n": patients, "marker": LOAD_MARKER},
        )
        print(f"  patients:     {patients:>7,}  ({time.perf_counter() - started:.1f}s)")

        # Slots. staff_id is left null so the GiST no-overlap exclusion constraint does
        # not apply - this is bulk volume, not a realistic timetable, and generating
        # non-overlapping per-clinician rows would cost more than the measurement is worth.
        #
        # Departments are rotated with a join rather than interpolated into the SQL: it
        # keeps the statement parameterised and avoids the printf-escaping tangle that
        # building an array literal in Python produced.
        step = time.perf_counter()
        await session.execute(
            text(
                """
                WITH numbered AS (
                    SELECT id, (row_number() OVER (ORDER BY code) - 1) AS rn,
                           count(*) OVER () AS total
                    FROM operational.departments
                )
                INSERT INTO operational.appointment_slots
                    (department_id, site_id, starts_at, ends_at, slot_type, data_origin)
                SELECT
                    numbered.id,
                    :site,
                    now() + (i % 4000) * interval '20 minutes',
                    now() + (i % 4000) * interval '20 minutes' + interval '20 minutes',
                    'ROUTINE',
                    :marker
                FROM generate_series(1, :n) AS i
                JOIN numbered ON numbered.rn = i % numbered.total
                """
            ),
            {"site": site_id, "n": slots, "marker": LOAD_MARKER},
        )
        print(f"  slots:        {slots:>7,}  ({time.perf_counter() - step:.1f}s)")

        # Appointments against a distinct slot each, so the partial unique index holds.
        step = time.perf_counter()
        await session.execute(
            text(
                """
                INSERT INTO operational.appointments
                    (patient_id, slot_id, department_id, booked_by_user_id, status, reason_text)
                SELECT
                    p.id, s.id, s.department_id,
                    (SELECT id FROM identity.users LIMIT 1),
                    'BOOKED',
                    :marker
                FROM (
                    SELECT id, department_id, row_number() OVER (ORDER BY id) AS rn
                    FROM operational.appointment_slots
                    WHERE data_origin = :marker LIMIT :n
                ) s
                JOIN (
                    SELECT id, row_number() OVER (ORDER BY id) AS rn
                    FROM clinical.patients WHERE data_origin = :marker
                ) p ON p.rn = s.rn
                """
            ),
            {"n": appointments, "marker": LOAD_MARKER},
        )
        print(f"  appointments: {appointments:>7,}  ({time.perf_counter() - step:.1f}s)")

        await session.commit()

    async with factory() as session:
        # ANALYZE so the planner has current statistics. Without it the first measurements
        # reflect a planner working from stale row estimates, not the real query cost.
        await session.execute(text("ANALYZE clinical.patients"))
        await session.execute(text("ANALYZE operational.appointment_slots"))
        await session.execute(text("ANALYZE operational.appointments"))
        await session.commit()

    print(f"\ntotal {time.perf_counter() - started:.1f}s; statistics refreshed")


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate volume for performance testing.")
    parser.add_argument("--patients", type=int, default=20000)
    parser.add_argument("--slots", type=int, default=60000)
    parser.add_argument("--appointments", type=int, default=15000)
    parser.add_argument("--clear", action="store_true", help="Remove load-test rows only.")
    args = parser.parse_args()

    if args.clear:
        asyncio.run(clear())
    else:
        asyncio.run(generate(args.patients, args.slots, args.appointments))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
