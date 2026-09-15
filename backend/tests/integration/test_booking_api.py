"""Booking API tests.

The concurrency suite drives BookingService directly. These go through HTTP, so they also
cover authorisation, the request/response contract and the status codes a client branches
on - none of which the service-level tests touch.

Brief §28 lists the booking cases these mirror: success, conflict, cancellation,
reschedule, invalid input, expired hold, and one patient reaching another's appointment.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.integration

AUTH = "/api/v1/auth"
PASSWORD = "correct-horse-battery-staple"


async def register_and_login(api: AsyncClient, email: str, family: str) -> tuple[str, str]:
    created = await api.post(
        f"{AUTH}/register",
        json={
            "email": email,
            "password": PASSWORD,
            "givenName": "Test",
            "familyName": family,
            "dateOfBirth": "1990-01-01",
        },
    )
    assert created.status_code == 201, created.text

    signed_in = await api.post(f"{AUTH}/login", json={"email": email, "password": PASSWORD})
    assert signed_in.status_code == 200, signed_in.text
    return str(signed_in.json()["accessToken"]), str(created.json()["patientId"])


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def slot(db_session: AsyncSession) -> Any:
    """One bookable slot, visible inside the test transaction."""
    marker = uuid.uuid4().hex[:8]
    site_id = await db_session.scalar(
        text("INSERT INTO operational.sites (code, name) VALUES (:c, 'API Test') RETURNING id"),
        {"c": f"API-{marker}"},
    )
    department_id = await db_session.scalar(
        text(
            "INSERT INTO operational.departments (site_id, code, name) "
            "VALUES (:s, :c, 'API Test Dept') RETURNING id"
        ),
        {"s": site_id, "c": f"AD-{marker}"},
    )
    slot_id = await db_session.scalar(
        text(
            "INSERT INTO operational.appointment_slots "
            "(department_id, site_id, starts_at, ends_at) "
            "VALUES (:d, :s, now() + interval '2 days', now() + interval '2 days 20 minutes') "
            "RETURNING id"
        ),
        {"d": department_id, "s": site_id},
    )
    await db_session.flush()
    return {"id": str(slot_id), "department_id": str(department_id), "site_id": str(site_id)}


# --- Availability -------------------------------------------------------------


async def test_slots_require_authentication(api: AsyncClient) -> None:
    assert (await api.get("/api/v1/slots")).status_code == 401


async def test_a_patient_can_see_open_slots(api: AsyncClient, slot: Any) -> None:
    token, _ = await register_and_login(api, "slots@example.test", "Slots")

    response = await api.get("/api/v1/slots?limit=100", headers=auth(token))

    assert response.status_code == 200
    assert slot["id"] in {item["id"] for item in response.json()["items"]}


async def test_a_booked_slot_disappears_from_availability(api: AsyncClient, slot: Any) -> None:
    token, _ = await register_and_login(api, "gone@example.test", "Gone")
    await api.post("/api/v1/appointments", json={"slotId": slot["id"]}, headers=auth(token))

    response = await api.get("/api/v1/slots?limit=100", headers=auth(token))

    assert slot["id"] not in {item["id"] for item in response.json()["items"]}


async def test_a_held_slot_disappears_from_availability(api: AsyncClient, slot: Any) -> None:
    """Otherwise two patients are shown a time only one of them can have."""
    token, _ = await register_and_login(api, "held@example.test", "Held")
    await api.post(f"/api/v1/slots/{slot['id']}/hold", headers=auth(token))

    response = await api.get("/api/v1/slots?limit=100", headers=auth(token))

    assert slot["id"] not in {item["id"] for item in response.json()["items"]}


# --- Booking ------------------------------------------------------------------


async def test_booking_succeeds_and_returns_a_reference(api: AsyncClient, slot: Any) -> None:
    token, _ = await register_and_login(api, "book@example.test", "Book")

    response = await api.post(
        "/api/v1/appointments",
        json={"slotId": slot["id"], "reason": "Ongoing headaches"},
        headers=auth(token),
    )

    assert response.status_code == 201, response.text
    appointment = response.json()["appointment"]
    assert appointment["status"] == "BOOKED"
    assert appointment["reference"].startswith("APT-")
    assert appointment["reasonText"] == "Ongoing headaches"
    assert appointment["isCancellable"] is True


async def test_booking_the_same_slot_twice_returns_409(api: AsyncClient, slot: Any) -> None:
    token, _ = await register_and_login(api, "twice@example.test", "Twice")
    first = await api.post("/api/v1/appointments", json={"slotId": slot["id"]}, headers=auth(token))
    assert first.status_code == 201

    second = await api.post(
        "/api/v1/appointments", json={"slotId": slot["id"]}, headers=auth(token)
    )

    assert second.status_code == 409
    assert second.json()["error"]["code"] == "APPOINTMENT_CONFLICT"


async def test_booking_an_unknown_slot_returns_404(api: AsyncClient) -> None:
    token, _ = await register_and_login(api, "missing@example.test", "Missing")

    response = await api.post(
        "/api/v1/appointments",
        json={"slotId": str(uuid.uuid4())},
        headers=auth(token),
    )

    assert response.status_code == 404


async def test_booking_a_past_slot_is_rejected(api: AsyncClient, db_session: AsyncSession) -> None:
    token, _ = await register_and_login(api, "past@example.test", "Past")
    marker = uuid.uuid4().hex[:8]
    site_id = await db_session.scalar(
        text("INSERT INTO operational.sites (code, name) VALUES (:c, 'Past') RETURNING id"),
        {"c": f"PAST-{marker}"},
    )
    department_id = await db_session.scalar(
        text(
            "INSERT INTO operational.departments (site_id, code, name) "
            "VALUES (:s, :c, 'Past Dept') RETURNING id"
        ),
        {"s": site_id, "c": f"PD-{marker}"},
    )
    past_slot = await db_session.scalar(
        text(
            "INSERT INTO operational.appointment_slots "
            "(department_id, site_id, starts_at, ends_at) "
            "VALUES (:d, :s, now() - interval '2 days', now() - interval '2 days' "
            "+ interval '20 minutes') RETURNING id"
        ),
        {"d": department_id, "s": site_id},
    )
    await db_session.flush()

    response = await api.post(
        "/api/v1/appointments", json={"slotId": str(past_slot)}, headers=auth(token)
    )

    assert response.status_code == 400
    assert "past" in response.json()["error"]["message"].lower()


async def test_booking_rejects_a_malformed_slot_id(api: AsyncClient) -> None:
    token, _ = await register_and_login(api, "malformed@example.test", "Malformed")

    response = await api.post(
        "/api/v1/appointments", json={"slotId": "not-a-uuid"}, headers=auth(token)
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


async def test_a_patient_cannot_book_in_someone_elses_name(api: AsyncClient, slot: Any) -> None:
    """The patient identity comes from the token, never the body.

    A `patientId` in the payload must be ignored rather than honoured.
    """
    token, own_patient_id = await register_and_login(api, "self@example.test", "Self")
    _, other_patient_id = await register_and_login(api, "other@example.test", "Other")

    response = await api.post(
        "/api/v1/appointments",
        json={"slotId": slot["id"], "patientId": other_patient_id},
        headers=auth(token),
    )

    assert response.status_code == 201
    booked_for = await api.get(
        f"/api/v1/appointments/{response.json()['appointment']['id']}", headers=auth(token)
    )
    # It belongs to the caller, not to the id they tried to inject.
    assert booked_for.status_code == 200
    assert own_patient_id != other_patient_id


# --- Holds --------------------------------------------------------------------


async def test_holding_a_slot_returns_a_countdown(api: AsyncClient, slot: Any) -> None:
    token, _ = await register_and_login(api, "hold@example.test", "Hold")

    response = await api.post(f"/api/v1/slots/{slot['id']}/hold", headers=auth(token))

    assert response.status_code == 200
    body = response.json()
    assert body["slotId"] == slot["id"]
    assert 0 < body["expiresInSeconds"] <= 300


async def test_a_second_patient_cannot_hold_a_held_slot(api: AsyncClient, slot: Any) -> None:
    first, _ = await register_and_login(api, "first@example.test", "First")
    second, _ = await register_and_login(api, "second@example.test", "Second")
    await api.post(f"/api/v1/slots/{slot['id']}/hold", headers=auth(first))

    response = await api.post(f"/api/v1/slots/{slot['id']}/hold", headers=auth(second))

    assert response.status_code == 409


async def test_the_holder_can_book_their_own_held_slot(api: AsyncClient, slot: Any) -> None:
    token, _ = await register_and_login(api, "holder@example.test", "Holder")
    await api.post(f"/api/v1/slots/{slot['id']}/hold", headers=auth(token))

    response = await api.post(
        "/api/v1/appointments", json={"slotId": slot["id"]}, headers=auth(token)
    )

    assert response.status_code == 201


async def test_an_expired_hold_is_reported_distinctly(
    api: AsyncClient, slot: Any, db_session: AsyncSession
) -> None:
    """ "Your time expired" is not the same as "someone took it".

    Collapsing the two would tell a patient the slot is gone when it may still be free.
    """
    token, _ = await register_and_login(api, "expired@example.test", "Expired")
    await api.post(f"/api/v1/slots/{slot['id']}/hold", headers=auth(token))

    await db_session.execute(
        text("UPDATE operational.slot_holds SET expires_at = :past WHERE slot_id = :s"),
        {"past": datetime.now(UTC) - timedelta(minutes=1), "s": slot["id"]},
    )
    await db_session.flush()

    response = await api.post(
        "/api/v1/appointments", json={"slotId": slot["id"]}, headers=auth(token)
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "SLOT_HOLD_EXPIRED"


# --- Reading, cancelling, rescheduling ----------------------------------------


async def test_a_patient_sees_only_their_own_appointments(api: AsyncClient, slot: Any) -> None:
    mine, _ = await register_and_login(api, "mine@example.test", "Mine")
    theirs, _ = await register_and_login(api, "theirs@example.test", "Theirs")
    await api.post("/api/v1/appointments", json={"slotId": slot["id"]}, headers=auth(mine))

    response = await api.get("/api/v1/appointments", headers=auth(theirs))

    assert response.status_code == 200
    assert response.json()["items"] == []


async def test_a_patient_cannot_open_another_patients_appointment(
    api: AsyncClient, slot: Any
) -> None:
    """404 rather than 403: a 403 confirms the appointment exists."""
    owner, _ = await register_and_login(api, "owner@example.test", "Owner")
    intruder, _ = await register_and_login(api, "intruder@example.test", "Intruder")
    created = await api.post(
        "/api/v1/appointments", json={"slotId": slot["id"]}, headers=auth(owner)
    )
    appointment_id = created.json()["appointment"]["id"]

    response = await api.get(f"/api/v1/appointments/{appointment_id}", headers=auth(intruder))

    assert response.status_code == 404


async def test_a_patient_cannot_cancel_another_patients_appointment(
    api: AsyncClient, slot: Any
) -> None:
    owner, _ = await register_and_login(api, "owner2@example.test", "Owner2")
    intruder, _ = await register_and_login(api, "intruder2@example.test", "Intruder2")
    created = await api.post(
        "/api/v1/appointments", json={"slotId": slot["id"]}, headers=auth(owner)
    )
    appointment_id = created.json()["appointment"]["id"]

    response = await api.post(
        f"/api/v1/appointments/{appointment_id}/cancel", json={}, headers=auth(intruder)
    )

    assert response.status_code == 404

    still_booked = await api.get(f"/api/v1/appointments/{appointment_id}", headers=auth(owner))
    assert still_booked.json()["appointment"]["status"] == "BOOKED"


async def test_cancelling_keeps_the_record_and_frees_the_slot(api: AsyncClient, slot: Any) -> None:
    token, _ = await register_and_login(api, "cancel@example.test", "Cancel")
    created = await api.post(
        "/api/v1/appointments", json={"slotId": slot["id"]}, headers=auth(token)
    )
    appointment_id = created.json()["appointment"]["id"]

    cancelled = await api.post(
        f"/api/v1/appointments/{appointment_id}/cancel",
        json={"reason": "No longer needed"},
        headers=auth(token),
    )

    assert cancelled.status_code == 200
    assert cancelled.json()["appointment"]["status"] == "CANCELLED"
    assert cancelled.json()["appointment"]["isCancellable"] is False

    # The slot is bookable again...
    rebooked = await api.post(
        "/api/v1/appointments", json={"slotId": slot["id"]}, headers=auth(token)
    )
    assert rebooked.status_code == 201

    # ...and the cancellation is still on the record.
    history = await api.get("/api/v1/appointments?includePast=true", headers=auth(token))
    statuses = [item["status"] for item in history.json()["items"]]
    assert "CANCELLED" in statuses


async def test_cancelling_twice_is_reported_as_a_state_error(api: AsyncClient, slot: Any) -> None:
    token, _ = await register_and_login(api, "twicecancel@example.test", "TwiceCancel")
    created = await api.post(
        "/api/v1/appointments", json={"slotId": slot["id"]}, headers=auth(token)
    )
    appointment_id = created.json()["appointment"]["id"]
    await api.post(f"/api/v1/appointments/{appointment_id}/cancel", json={}, headers=auth(token))

    response = await api.post(
        f"/api/v1/appointments/{appointment_id}/cancel", json={}, headers=auth(token)
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "INVALID_STATE_TRANSITION"


async def test_rescheduling_moves_the_appointment_and_links_the_chain(
    api: AsyncClient, slot: Any, db_session: AsyncSession
) -> None:
    token, _ = await register_and_login(api, "move@example.test", "Move")
    created = await api.post(
        "/api/v1/appointments", json={"slotId": slot["id"]}, headers=auth(token)
    )
    original_id = created.json()["appointment"]["id"]

    later_slot = await db_session.scalar(
        text(
            "INSERT INTO operational.appointment_slots "
            "(department_id, site_id, starts_at, ends_at) "
            "VALUES (:d, :s, now() + interval '5 days', now() + interval '5 days 20 minutes') "
            "RETURNING id"
        ),
        {"d": slot["department_id"], "s": slot["site_id"]},
    )
    await db_session.flush()

    response = await api.post(
        f"/api/v1/appointments/{original_id}/reschedule",
        json={"newSlotId": str(later_slot)},
        headers=auth(token),
    )

    assert response.status_code == 201, response.text
    assert response.json()["kind"] == "rescheduled"
    new_id = response.json()["appointment"]["id"]

    original = await api.get(f"/api/v1/appointments/{original_id}", headers=auth(token))
    assert original.json()["appointment"]["status"] == "CANCELLED"
    assert original.json()["appointment"]["cancellationReason"] == "Rescheduled"

    linked = await db_session.scalar(
        text("SELECT previous_appointment_id FROM operational.appointments WHERE id = :i"),
        {"i": new_id},
    )
    assert str(linked) == original_id


async def test_rescheduling_onto_a_taken_slot_keeps_the_original(
    api: AsyncClient, slot: Any, db_session: AsyncSession
) -> None:
    """The new booking is taken before the old one is released.

    Cancelling first would risk leaving the patient with no appointment at all when the
    target slot turns out to be gone.
    """
    mover, _ = await register_and_login(api, "mover@example.test", "Mover")
    blocker, _ = await register_and_login(api, "blocker@example.test", "Blocker")

    created = await api.post(
        "/api/v1/appointments", json={"slotId": slot["id"]}, headers=auth(mover)
    )
    original_id = created.json()["appointment"]["id"]

    contested = await db_session.scalar(
        text(
            "INSERT INTO operational.appointment_slots "
            "(department_id, site_id, starts_at, ends_at) "
            "VALUES (:d, :s, now() + interval '6 days', now() + interval '6 days 20 minutes') "
            "RETURNING id"
        ),
        {"d": slot["department_id"], "s": slot["site_id"]},
    )
    await db_session.flush()
    await api.post("/api/v1/appointments", json={"slotId": str(contested)}, headers=auth(blocker))

    response = await api.post(
        f"/api/v1/appointments/{original_id}/reschedule",
        json={"newSlotId": str(contested)},
        headers=auth(mover),
    )

    assert response.status_code == 409

    # The patient still has their original appointment.
    original = await api.get(f"/api/v1/appointments/{original_id}", headers=auth(mover))
    assert original.json()["appointment"]["status"] == "BOOKED"


# --- Audit --------------------------------------------------------------------


async def test_booking_and_cancelling_are_audited(
    api: AsyncClient, slot: Any, db_session: AsyncSession
) -> None:
    token, _ = await register_and_login(api, "audited@example.test", "Audited")
    created = await api.post(
        "/api/v1/appointments", json={"slotId": slot["id"]}, headers=auth(token)
    )
    await api.post(
        f"/api/v1/appointments/{created.json()['appointment']['id']}/cancel",
        json={},
        headers=auth(token),
    )

    actions = {
        row[0]
        for row in (await db_session.execute(text("SELECT action FROM audit.audit_logs"))).all()
    }

    assert "APPOINTMENT_CREATED" in actions
    assert "APPOINTMENT_CANCELLED" in actions


async def test_a_cancellation_reason_stays_out_of_the_audit_metadata(
    api: AsyncClient, slot: Any, db_session: AsyncSession
) -> None:
    """The reason is free text a patient typed; it belongs on the appointment, not the log."""
    token, _ = await register_and_login(api, "reason@example.test", "Reason")
    created = await api.post(
        "/api/v1/appointments", json={"slotId": slot["id"]}, headers=auth(token)
    )
    await api.post(
        f"/api/v1/appointments/{created.json()['appointment']['id']}/cancel",
        json={"reason": "Distinctive personal circumstance"},
        headers=auth(token),
    )

    blob = await db_session.scalar(
        text("SELECT string_agg(metadata::text, ' ') FROM audit.audit_logs")
    )

    assert blob is not None
    assert "Distinctive personal circumstance" not in blob


async def test_departments_are_listed_for_a_signed_in_patient(api: AsyncClient, slot: Any) -> None:
    """The booking picker needs every department, independent of which slots are loaded."""
    token, _ = await register_and_login(api, "departments.viewer@example.test", "Viewer")

    response = await api.get("/api/v1/departments", headers=auth(token))

    assert response.status_code == 200, response.text
    items = response.json()["items"]
    assert any(item["id"] == slot["department_id"] for item in items)
    # Organisational data only: nothing beyond identity, code and name leaves this route.
    assert all(set(item) == {"id", "code", "name"} for item in items)


async def test_departments_require_sign_in(api: AsyncClient) -> None:
    assert (await api.get("/api/v1/departments")).status_code == 401
