"""Seed synthetic demo accounts.

Required by brief §39. Creates one account per role so the system can be demonstrated
without anyone inventing credentials and then being unable to sign in.

Everything created here is synthetic:
  - Addresses use the RFC 2606 reserved `.test` domain, which cannot receive mail.
  - NHS numbers come from the 999 test range and are Modulus 11 valid.
  - Every row is marked data_origin = SYNTHETIC.

The password is read from DEMO_PASSWORD. There is deliberately no default: a well-known
default password is the single most common way a demo system becomes a real breach when
someone deploys it somewhere reachable.

Usage:
    docker compose exec api python scripts/seed_demo.py
    docker compose exec api python scripts/seed_demo.py --reset
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.db import get_session_factory
from app.core.security import hash_password
from app.models.base import DataOrigin, UserRole, UserStatus
from app.models.clinical import Patient
from app.models.identity import CareAssignment, Staff, User
from app.models.operational import Department, Site
from app.models.scheduling import Appointment, AppointmentSlot, AppointmentStatus, SlotType
from app.utils import nhs_number as nhs

DEMO_DOMAIN = "example.test"

# Not a password. Argon2 hashes always start with "$argon2", so no input can ever verify
# against this value - these staff records own timetable slots and are not sign-ins.
UNUSABLE_PASSWORD_HASH = "!no-login"  # noqa: S105


@dataclass(frozen=True, slots=True)
class DemoAccount:
    """One synthetic account. A dataclass rather than a dict so the patient-only and
    staff-only fields are typed rather than silently absent."""

    email: str
    role: UserRole
    given_name: str
    family_name: str
    date_of_birth: date | None = None
    job_title: str | None = None


DEMO_ACCOUNTS: tuple[DemoAccount, ...] = (
    DemoAccount(
        email=f"patient@{DEMO_DOMAIN}",
        role=UserRole.PATIENT,
        given_name="Priya",
        family_name="Sharma",
        date_of_birth=date(1986, 3, 14),
    ),
    DemoAccount(
        email=f"doctor@{DEMO_DOMAIN}",
        role=UserRole.DOCTOR,
        given_name="Daniel",
        family_name="Okafor",
        job_title="Consultant, General Medicine",
    ),
    DemoAccount(
        email=f"nurse@{DEMO_DOMAIN}",
        role=UserRole.NURSE,
        given_name="Niamh",
        family_name="Doyle",
        job_title="Senior Staff Nurse",
    ),
    DemoAccount(
        email=f"admin@{DEMO_DOMAIN}",
        role=UserRole.ADMIN,
        given_name="Aisha",
        family_name="Rahman",
        job_title="Operations Manager",
    ),
)

# Synthetic patients for the clinical queue. Names are invented; every one carries a
# reserved-domain address, an Ofcom drama-range number and a 999-range NHS number, so no
# generated contact detail can reach a real person.
QUEUE_PATIENTS = [
    ("Margaret", "Whitfield", date(1948, 2, 11), "Female", True, "cy-GB"),
    ("Tomasz", "Nowak", date(1991, 7, 3), "Male", True, "pl-PL"),
    ("Ade", "Bakare", date(1983, 11, 21), "Male", False, "en-GB"),
    ("Fatima", "Al-Rashid", date(1996, 5, 8), "Female", True, "ar"),
    ("Ellie", "Hargreaves", date(2015, 9, 2), "Female", False, "en-GB"),
    ("Gordon", "MacLeod", date(1957, 12, 30), "Male", False, "en-GB"),
    ("Yusuf", "Demir", date(1974, 4, 17), "Male", False, "tr"),
    ("Bethan", "Price", date(2001, 8, 25), "Female", False, "cy-GB"),
    ("Ivan", "Petrov", date(1966, 1, 9), "Male", False, "en-GB"),
    ("Grace", "Adeyemi", date(1989, 10, 14), "Female", False, "en-GB"),
    ("Harold", "Sims", date(1939, 6, 5), "Male", False, "en-GB"),
    ("Ana", "Silva", date(1993, 3, 27), "Female", True, "pt-PT"),
]

DEPARTMENTS = [
    ("AE", "Accident and Emergency"),
    ("GENMED", "General Medicine"),
    ("CARD", "Cardiology"),
    ("ORTHO", "Orthopaedics"),
    ("PAEDS", "Paediatrics"),
    ("OUTPT", "Outpatients"),
]


async def seed_reference_data(session: AsyncSession) -> Department:
    """Create the site and departments the staff records depend on."""
    site = (await session.execute(select(Site).where(Site.code == "SYN-01"))).scalar_one_or_none()

    if site is None:
        site = Site(
            code="SYN-01",
            name="Example Community Hospital (synthetic)",
            city="Exampleton",
            postcode="EX1 1AA",
            data_origin=DataOrigin.SYNTHETIC.value,
        )
        session.add(site)
        await session.flush()

    departments: list[Department] = []
    for code, name in DEPARTMENTS:
        existing = (
            await session.execute(select(Department).where(Department.code == code))
        ).scalar_one_or_none()
        if existing is None:
            existing = Department(
                site_id=site.id,
                code=code,
                name=name,
                data_origin=DataOrigin.SYNTHETIC.value,
            )
            session.add(existing)
            await session.flush()
        departments.append(existing)

    # General Medicine, used as the default department for demo staff.
    return departments[1]


async def seed_queue_patients(session: AsyncSession, department: Department) -> None:
    """Create the synthetic patients a clinician sees, and assign some to the demo staff.

    Only *some* are assigned on purpose. An unassigned patient is what demonstrates the
    access model: opening that record requires emergency access with a typed
    justification, which is the behaviour the whole audit story rests on.
    """
    doctor = (
        await session.execute(select(Staff).join(User).where(User.email == f"doctor@{DEMO_DOMAIN}"))
    ).scalar_one_or_none()
    nurse = (
        await session.execute(select(Staff).join(User).where(User.email == f"nurse@{DEMO_DOMAIN}"))
    ).scalar_one_or_none()

    for index, (given, family, dob, sex, interpreter, language) in enumerate(QUEUE_PATIENTS):
        existing = (
            await session.execute(
                select(Patient).where(Patient.given_name == given, Patient.family_name == family)
            )
        ).scalar_one_or_none()
        if existing is not None:
            continue

        patient = Patient(
            given_name=given,
            family_name=family,
            date_of_birth=dob,
            sex_at_birth=sex,
            nhs_number=nhs.generate_test_number(100 + index),
            email=f"{given.lower()}.{family.lower().replace(chr(39), '')}@{DEMO_DOMAIN}",
            phone_e164=f"+4477009002{index:02d}",
            address_line1=f"{index + 1} Example Street",
            city="Exampleton",
            postcode="EX1 1AA",
            preferred_language=language,
            interpreter_needed=interpreter,
            data_origin=DataOrigin.SYNTHETIC.value,
        )
        session.add(patient)
        await session.flush()

        # Two thirds assigned; the rest deliberately left unassigned so break-glass has
        # something to demonstrate against.
        if index % 3 != 2:
            staff_member = doctor if index % 2 == 0 else nurse
            if staff_member is not None:
                session.add(
                    CareAssignment(
                        staff_id=staff_member.id,
                        patient_id=patient.id,
                        department_id=department.id,
                        reason="Synthetic demo assignment",
                    )
                )


# Weekday clinic pattern per clinician. Deliberately not 24/7: a timetable with no gaps
# would let the booking screens look plausible while hiding the case that actually matters -
# a patient searching a day with nothing free.
# Additional synthetic clinicians, one per department, so the booking screen's department
# filter is actually exercised. With only the two demo staff every slot is General
# Medicine, and a filter with one option tests nothing.
EXTRA_CLINICIANS = (
    ("Rowan", "Achebe", "Consultant, Cardiology", "CARD"),
    ("Freya", "Lindqvist", "Consultant, Orthopaedics", "ORTHO"),
    ("Marcus", "Bell", "Consultant, Paediatrics", "PAEDS"),
    ("Sofia", "Marchetti", "Consultant, Outpatients", "OUTPT"),
    ("Idris", "Khan", "Emergency Physician", "AE"),
)

CLINIC_WEEKDAYS = (0, 1, 2, 3, 4)  # Monday to Friday
CLINIC_BLOCKS = ((time(9, 0), time(12, 0)), (time(14, 0), time(17, 0)))
SLOT_MINUTES = 20
WEEKS_AHEAD = 6


async def seed_extra_clinicians(session: AsyncSession) -> None:
    """Create one clinician per department, beyond the four demo sign-ins.

    These have no login: they exist to own slots, which is what makes availability spread
    across departments. Staff accounts are provisioned administratively, so a staff record
    without a usable password is the correct shape rather than a gap.
    """
    for index, (given, family, job_title, department_code) in enumerate(EXTRA_CLINICIANS):
        staff_code = f"SYN-2{index:03d}"
        existing = (
            await session.execute(select(Staff).where(Staff.staff_code == staff_code))
        ).scalar_one_or_none()
        if existing is not None:
            continue

        department = (
            await session.execute(select(Department).where(Department.code == department_code))
        ).scalar_one_or_none()
        if department is None:
            continue

        user = User(
            email=f"{given.lower()}.{family.lower()}@{DEMO_DOMAIN}",
            password_hash=UNUSABLE_PASSWORD_HASH,
            role=UserRole.DOCTOR,
            status=UserStatus.DISABLED,
        )
        session.add(user)
        await session.flush()

        session.add(
            Staff(
                user_id=user.id,
                staff_code=staff_code,
                given_name=given,
                family_name=family,
                job_title=job_title,
                department_id=department.id,
                data_origin=DataOrigin.SYNTHETIC.value,
            )
        )
    await session.flush()


async def seed_demo_appointment(session: AsyncSession) -> str | None:
    """Give the demo patient one upcoming appointment.

    Without this a fresh demo opens on an empty appointments screen, so the cancel and
    reschedule flows have nothing to act on and cannot be demonstrated at all. The browser
    test covering the cancel dialog was silently reporting SKIP for exactly this reason - a
    quiet loss of coverage that reads as a pass at a glance.

    Idempotent on *upcoming* rather than on "has any appointment". That distinction is the
    bug being fixed: slots are generated relative to seed time, so a database seeded weeks
    ago has appointments that have all slipped into the past, and a check for mere existence
    declares the job done while the demo shows nothing.
    """
    patient = (
        await session.execute(
            select(Patient).join(User).where(User.email == f"patient@{DEMO_DOMAIN}")
        )
    ).scalar_one_or_none()
    if patient is None:
        return None

    existing = (
        await session.execute(
            select(Appointment.reference)
            .join(AppointmentSlot, AppointmentSlot.id == Appointment.slot_id)
            .where(
                Appointment.patient_id == patient.id,
                Appointment.status == AppointmentStatus.BOOKED,
                AppointmentSlot.starts_at > datetime.now(UTC),
            )
            .limit(1)
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing

    # At least two days out. The first attempt at this took the earliest free slot, which
    # was forty minutes away - the demo appointment aged into the past within the hour and
    # the appointments screen went empty again. Taken slots are excluded by the same rule
    # the booking service uses, so this cannot collide with the partial unique index that
    # enforces one active appointment per slot.
    slot = (
        await session.execute(
            select(AppointmentSlot)
            .where(
                AppointmentSlot.starts_at > datetime.now(UTC) + timedelta(days=2),
                AppointmentSlot.id.not_in(
                    select(Appointment.slot_id).where(
                        Appointment.status.in_(
                            [
                                AppointmentStatus.BOOKED,
                                AppointmentStatus.CHECKED_IN,
                                AppointmentStatus.IN_PROGRESS,
                            ]
                        )
                    )
                ),
            )
            .order_by(AppointmentSlot.starts_at)
            .limit(1)
        )
    ).scalar_one_or_none()
    if slot is None:
        return None

    booked_by = (
        await session.execute(select(User).where(User.email == f"patient@{DEMO_DOMAIN}"))
    ).scalar_one()

    appointment = Appointment(
        patient_id=patient.id,
        slot_id=slot.id,
        department_id=slot.department_id,
        staff_id=slot.staff_id,
        booked_by_user_id=booked_by.id,
        reason_text="Routine review (demonstration data)",
    )
    session.add(appointment)
    await session.flush()
    return appointment.reference


async def seed_slots(session: AsyncSession) -> int:
    """Generate a forward timetable of appointment slots.

    BLOCKER B2 in ASSUMPTIONS.md: no open UK dataset carries clinician availability, so
    this is generated and marked SYNTHETIC like everything else it produces.

    Slots are created per clinician, and the GiST exclusion constraint from migration 002
    means an overlapping pair simply cannot be written - so a bug in this generator fails
    loudly at seed time rather than producing an impossible timetable nobody notices.
    """
    clinicians = (
        (
            await session.execute(
                select(Staff)
                .join(User)
                .where(User.role.in_([UserRole.DOCTOR, UserRole.NURSE]), Staff.active.is_(True))
            )
        )
        .scalars()
        .all()
    )
    if not clinicians:
        return 0

    site = (await session.execute(select(Site).limit(1))).scalar_one_or_none()
    if site is None:
        return 0

    departments = (await session.execute(select(Department))).scalars().all()
    if not departments:
        return 0

    existing = set(
        (
            await session.execute(
                select(AppointmentSlot.staff_id, AppointmentSlot.starts_at).where(
                    AppointmentSlot.starts_at >= datetime.now(UTC)
                )
            )
        ).all()
    )

    # Start tomorrow: a slot earlier today is unbookable the moment it is written, and a
    # demo whose first page is full of dead times is worse than one with fewer slots.
    first_day = (datetime.now(UTC) + timedelta(days=1)).date()
    created = 0

    for clinician in clinicians:
        department = next(
            (d for d in departments if d.id == clinician.department_id), departments[0]
        )
        for day_offset in range(WEEKS_AHEAD * 7):
            day = first_day + timedelta(days=day_offset)
            if day.weekday() not in CLINIC_WEEKDAYS:
                continue

            for block_start, block_end in CLINIC_BLOCKS:
                cursor = datetime.combine(day, block_start, tzinfo=UTC)
                block_finish = datetime.combine(day, block_end, tzinfo=UTC)

                while cursor + timedelta(minutes=SLOT_MINUTES) <= block_finish:
                    if (clinician.id, cursor) not in existing:
                        session.add(
                            AppointmentSlot(
                                department_id=department.id,
                                staff_id=clinician.id,
                                site_id=site.id,
                                starts_at=cursor,
                                ends_at=cursor + timedelta(minutes=SLOT_MINUTES),
                                # The first block of each day is urgent-capacity, so the
                                # triage flow has somewhere to send a same-week case.
                                slot_type=(
                                    SlotType.URGENT
                                    if block_start == CLINIC_BLOCKS[0][0]
                                    else SlotType.ROUTINE
                                ),
                                data_origin=DataOrigin.SYNTHETIC.value,
                            )
                        )
                        created += 1
                    cursor += timedelta(minutes=SLOT_MINUTES)

        # Flushed per clinician so a constraint violation names the clinician it came from.
        await session.flush()

    return created


async def seed(reset: bool) -> int:
    settings = get_settings()

    if not settings.demo_password:
        print(
            "DEMO_PASSWORD is not set.\n"
            "Set it in .env, then re-run. There is no default on purpose:\n"
            "a known default password on a reachable demo is a real breach.",
            file=sys.stderr,
        )
        return 1

    if len(settings.demo_password) < 12:
        print("DEMO_PASSWORD must be at least 12 characters.", file=sys.stderr)
        return 1

    factory = get_session_factory()
    async with factory() as session:
        if reset:
            # Audit rows are intentionally left alone: the table is append-only by
            # trigger, and wiping the trail would defeat the point of having one.
            await session.execute(
                text(
                    "TRUNCATE operational.appointments, operational.slot_holds, "
                    "operational.appointment_slots, identity.staff, clinical.patients, "
                    "identity.refresh_tokens, identity.password_reset_tokens, "
                    "identity.care_assignments, identity.breakglass_grants "
                    "RESTART IDENTITY CASCADE"
                )
            )
            await session.execute(
                text("DELETE FROM identity.users WHERE email LIKE :pattern"),
                {"pattern": f"%@{DEMO_DOMAIN}"},
            )
            await session.commit()
            print("Existing demo data removed.")

        department = await seed_reference_data(session)
        password_hash = hash_password(settings.demo_password)
        created: list[tuple[str, str]] = []

        for index, spec in enumerate(DEMO_ACCOUNTS):
            existing = (
                await session.execute(select(User).where(User.email == spec.email))
            ).scalar_one_or_none()

            if existing is not None:
                # Idempotent: re-running resets the password and clears any lockout, so a
                # demo cannot be blocked by earlier failed attempts.
                existing.password_hash = password_hash
                existing.failed_logins = 0
                existing.locked_until = None
                existing.status = UserStatus.ACTIVE
                created.append((spec.email, "updated"))
                continue

            user = User(
                email=spec.email,
                password_hash=password_hash,
                role=spec.role,
                status=UserStatus.ACTIVE,
            )
            session.add(user)
            await session.flush()

            if spec.role is UserRole.PATIENT and spec.date_of_birth is not None:
                session.add(
                    Patient(
                        user_id=user.id,
                        nhs_number=nhs.generate_test_number(index),
                        given_name=spec.given_name,
                        family_name=spec.family_name,
                        date_of_birth=spec.date_of_birth,
                        email=spec.email,
                        phone_e164=f"+4477009001{index:02d}",  # Ofcom drama range
                        preferred_language="en-GB",
                        data_origin=DataOrigin.SYNTHETIC.value,
                    )
                )
            else:
                session.add(
                    Staff(
                        user_id=user.id,
                        staff_code=f"SYN-{1000 + index}",
                        given_name=spec.given_name,
                        family_name=spec.family_name,
                        job_title=spec.job_title or "Staff",
                        department_id=department.id,
                        data_origin=DataOrigin.SYNTHETIC.value,
                    )
                )

            created.append((spec.email, "created"))

        # Flushed above; staff rows must exist before assignments can reference them.
        await session.flush()
        await seed_queue_patients(session, department)
        await session.flush()
        await seed_extra_clinicians(session)
        slots_created = await seed_slots(session)
        await session.flush()
        demo_reference = await seed_demo_appointment(session)
        await session.commit()

    print("\nDemo accounts ready. All synthetic - no real person is described.\n")
    print(f"  {'Email':<26} {'Role':<9} Status")
    print(f"  {'-' * 26} {'-' * 9} -------")
    for (email, status), spec in zip(created, DEMO_ACCOUNTS, strict=True):
        print(f"  {email:<26} {spec.role.value:<9} {status}")
    print(f"\n  Password for all accounts: {settings.demo_password}")
    print(f"  Appointment slots created: {slots_created}")
    if demo_reference:
        print(f"  Upcoming appointment for the demo patient: {demo_reference}")
    else:
        print("  No upcoming appointment created (no free future slot).")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed synthetic demo accounts.")
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Remove existing demo data before seeding (leaves the audit trail intact).",
    )
    args = parser.parse_args()
    return asyncio.run(seed(args.reset))


if __name__ == "__main__":
    raise SystemExit(main())
