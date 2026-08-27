"""Concurrency tests for booking.

These do NOT use the shared rollback fixture. That fixture puts every request inside one
transaction on one connection, which serialises everything and would make a race
impossible to observe - the test would pass while proving nothing.

Instead each attempt gets its own engine, connection and transaction, and commits for
real, which is what the production path does. The rows are cleaned up afterwards.

This is the test the partial unique index exists for. If someone later "simplifies"
booking to an application-level check, this is what fails.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.errors import AppointmentConflict
from app.models.base import UserRole
from app.services.auth import RequestContext
from app.services.booking import BookingService

pytestmark = pytest.mark.integration

CONCURRENT_ATTEMPTS = 20


@pytest.fixture
async def scenario(database_url: str) -> Any:
    """Create one slot and N patients, committed so other connections can see them."""
    engine = create_async_engine(database_url)
    factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    marker = uuid.uuid4().hex[:8]

    async with factory() as session:
        site_id = await session.scalar(
            text(
                "INSERT INTO operational.sites (code, name) VALUES (:c, 'Race Test Site') "
                "RETURNING id"
            ),
            {"c": f"RACE-{marker}"},
        )
        department_id = await session.scalar(
            text(
                "INSERT INTO operational.departments (site_id, code, name) "
                "VALUES (:s, :c, 'Race Test Dept') RETURNING id"
            ),
            {"s": site_id, "c": f"RD-{marker}"},
        )
        slot_id = await session.scalar(
            text(
                "INSERT INTO operational.appointment_slots "
                "(department_id, site_id, starts_at, ends_at) "
                "VALUES (:d, :s, now() + interval '3 days', now() + interval '3 days 20 minutes') "
                "RETURNING id"
            ),
            {"d": department_id, "s": site_id},
        )

        patients: list[tuple[uuid.UUID, uuid.UUID]] = []
        for index in range(CONCURRENT_ATTEMPTS):
            user_id = await session.scalar(
                text(
                    "INSERT INTO identity.users (email, password_hash, role) "
                    "VALUES (:e, 'x', 'PATIENT') RETURNING id"
                ),
                {"e": f"race-{marker}-{index}@example.test"},
            )
            patient_id = await session.scalar(
                text(
                    "INSERT INTO clinical.patients "
                    "(user_id, given_name, family_name, date_of_birth) "
                    "VALUES (:u, 'Race', :f, '1990-01-01') RETURNING id"
                ),
                {"u": user_id, "f": f"Tester{index}"},
            )
            patients.append((user_id, patient_id))

        await session.commit()

    yield {"slot_id": slot_id, "patients": patients, "factory": factory}

    async with factory() as session:
        await session.execute(
            text("DELETE FROM operational.appointments WHERE slot_id = :s"), {"s": slot_id}
        )
        await session.execute(
            text("DELETE FROM operational.slot_holds WHERE slot_id = :s"), {"s": slot_id}
        )
        await session.execute(
            text("DELETE FROM operational.appointment_slots WHERE id = :s"), {"s": slot_id}
        )
        for user_id, patient_id in patients:
            await session.execute(
                text("DELETE FROM clinical.patients WHERE id = :p"), {"p": patient_id}
            )
            await session.execute(text("DELETE FROM identity.users WHERE id = :u"), {"u": user_id})
        await session.execute(
            text("DELETE FROM operational.departments WHERE id = :d"), {"d": department_id}
        )
        await session.execute(text("DELETE FROM operational.sites WHERE id = :s"), {"s": site_id})
        await session.commit()

    await engine.dispose()


async def _attempt(factory: Any, slot_id: uuid.UUID, user_id: uuid.UUID, patient_id: uuid.UUID):
    """One independent booking attempt, on its own connection, committing for real."""
    session: AsyncSession
    async with factory() as session:
        try:
            await BookingService(session).book(
                slot_id,
                patient_id=patient_id,
                actor_user_id=user_id,
                actor_role=UserRole.PATIENT,
                reason=None,
                priority=None,
                previous_appointment_id=None,
                context=RequestContext(request_id="race"),
            )
            await session.commit()
            return "booked"
        except AppointmentConflict:
            await session.rollback()
            return "conflict"
        except Exception as exc:
            await session.rollback()
            return f"unexpected:{type(exc).__name__}"


async def test_only_one_of_twenty_concurrent_bookings_wins(scenario: Any) -> None:
    """The headline guarantee: one slot, twenty simultaneous patients, one appointment."""
    slot_id = scenario["slot_id"]
    factory = scenario["factory"]

    results = await asyncio.gather(
        *(
            _attempt(factory, slot_id, user_id, patient_id)
            for user_id, patient_id in scenario["patients"]
        )
    )

    booked = [r for r in results if r == "booked"]
    conflicts = [r for r in results if r == "conflict"]
    unexpected = [r for r in results if r.startswith("unexpected")]

    assert not unexpected, f"every loser must get a clean conflict, got: {set(unexpected)}"
    assert len(booked) == 1, f"exactly one booking must succeed, got {len(booked)}"
    assert len(conflicts) == CONCURRENT_ATTEMPTS - 1

    async with factory() as session:
        live = await session.scalar(
            text(
                "SELECT count(*) FROM operational.appointments "
                "WHERE slot_id = :s AND status IN ('BOOKED','CHECKED_IN','IN_PROGRESS')"
            ),
            {"s": slot_id},
        )

    # The database is the source of truth, not the tally of return values.
    assert live == 1


async def test_the_database_refuses_a_second_booking_even_without_the_service(
    scenario: Any,
) -> None:
    """The guarantee must not depend on the service layer being involved.

    A future admin tool, a data migration or a fix-up script writing straight to the table
    is still bound by the index.
    """
    slot_id = scenario["slot_id"]
    factory = scenario["factory"]
    (user_a, patient_a), (user_b, patient_b) = scenario["patients"][:2]

    async with factory() as session:
        department_id = await session.scalar(
            text("SELECT department_id FROM operational.appointment_slots WHERE id = :s"),
            {"s": slot_id},
        )
        insert = text(
            "INSERT INTO operational.appointments "
            "(patient_id, slot_id, department_id, booked_by_user_id) "
            "VALUES (:p, :s, :d, :u)"
        )
        await session.execute(
            insert, {"p": patient_a, "s": slot_id, "d": department_id, "u": user_a}
        )
        await session.commit()

    async with factory() as session:
        with pytest.raises(Exception, match="uq_appointment_active_slot"):
            await session.execute(
                insert, {"p": patient_b, "s": slot_id, "d": department_id, "u": user_b}
            )
            await session.commit()


async def test_a_cancelled_appointment_frees_the_slot(scenario: Any) -> None:
    """Cancelling must release the slot without erasing the history.

    The index is scoped to live states precisely so a cancellation stays on the record
    while the time becomes bookable again.
    """
    slot_id = scenario["slot_id"]
    factory = scenario["factory"]
    (user_a, patient_a), (user_b, patient_b) = scenario["patients"][:2]

    assert await _attempt(factory, slot_id, user_a, patient_a) == "booked"
    assert await _attempt(factory, slot_id, user_b, patient_b) == "conflict"

    async with factory() as session:
        await session.execute(
            text(
                "UPDATE operational.appointments SET status = 'CANCELLED', cancelled_at = now() "
                "WHERE slot_id = :s"
            ),
            {"s": slot_id},
        )
        await session.commit()

    assert await _attempt(factory, slot_id, user_b, patient_b) == "booked"

    async with factory() as session:
        total = await session.scalar(
            text("SELECT count(*) FROM operational.appointments WHERE slot_id = :s"),
            {"s": slot_id},
        )
        cancelled = await session.scalar(
            text(
                "SELECT count(*) FROM operational.appointments "
                "WHERE slot_id = :s AND status = 'CANCELLED'"
            ),
            {"s": slot_id},
        )

    assert total == 2, "the cancelled appointment must still exist"
    assert cancelled == 1


async def test_concurrent_holds_leave_only_one_holder(scenario: Any) -> None:
    """Two patients must not both be told a slot is reserved for them."""
    slot_id = scenario["slot_id"]
    factory = scenario["factory"]

    async def hold(user_id: uuid.UUID, patient_id: uuid.UUID) -> str:
        async with factory() as session:
            try:
                await BookingService(session).hold_slot(
                    slot_id, patient_id=patient_id, context=RequestContext(request_id="race")
                )
                await session.commit()
                return "held"
            except AppointmentConflict:
                await session.rollback()
                return "conflict"
            except Exception:
                await session.rollback()
                return "unexpected"

    results = await asyncio.gather(
        *(hold(user_id, patient_id) for user_id, patient_id in scenario["patients"][:8])
    )

    assert results.count("held") == 1, f"exactly one hold should be granted, got {results}"
    assert "unexpected" not in results

    async with factory() as session:
        holds = await session.scalar(
            text("SELECT count(*) FROM operational.slot_holds WHERE slot_id = :s"), {"s": slot_id}
        )
    assert holds == 1


async def test_an_expired_hold_does_not_block_a_later_booking(scenario: Any) -> None:
    """A patient who walks away must not lock the slot for everyone else."""
    slot_id = scenario["slot_id"]
    factory = scenario["factory"]
    (_, patient_a), (user_b, patient_b) = scenario["patients"][:2]

    async with factory() as session:
        await BookingService(session).hold_slot(
            slot_id, patient_id=patient_a, context=RequestContext(request_id="race")
        )
        await session.commit()

    # Someone else cannot take it while the hold is live.
    assert await _attempt(factory, slot_id, user_b, patient_b) == "conflict"

    async with factory() as session:
        await session.execute(
            text("UPDATE operational.slot_holds SET expires_at = :past WHERE slot_id = :s"),
            {"past": datetime.now(UTC) - timedelta(minutes=1), "s": slot_id},
        )
        await session.commit()

    assert await _attempt(factory, slot_id, user_b, patient_b) == "booked"
