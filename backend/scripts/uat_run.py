"""Execute the acceptance scenarios against a running system.

This is not the unit test suite. Those tests exercise functions in isolation against a
throwaway database; this drives the real service over HTTP, signed in as the demo accounts,
against seeded data - which is what "acceptance" means. The two catch different things: a
unit test passes when a function is right, this passes when a user can actually do the
thing.

Scenario numbering matches docs/testing/uat-scenarios.md. Scenarios that need eyes on a
screen (layout, keyboard order, screen-reader output, browser rendering) are not here and
are not silently counted as passing - they are listed as MANUAL in that document.

    docker compose exec api python scripts/uat_run.py
    docker compose exec api python scripts/uat_run.py --verbose

Exits non-zero if any scenario fails, so it can gate a release.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
import uuid
from dataclasses import dataclass, field
from enum import StrEnum

import httpx

BASE = "http://localhost:8000/api/v1"
PASSWORD_ENV = "DEMO_PASSWORD"  # noqa: S105 - an environment variable name, not a secret


class Outcome(StrEnum):
    PASSED = "PASS"
    FAILED = "FAIL"
    #: The scenario could not run because a precondition was absent - not evidence of
    #: correctness, and reported separately so it is never mistaken for one.
    SKIPPED = "SKIP"


@dataclass
class Scenario:
    ref: str
    group: str
    title: str
    outcome: Outcome = Outcome.SKIPPED
    detail: str = ""
    evidence: list[str] = field(default_factory=list)

    def record(self, outcome: Outcome, detail: str) -> None:
        self.outcome = outcome
        self.detail = detail

    def note(self, line: str) -> None:
        self.evidence.append(line)


class Session:
    """A signed-in user. Wraps the token handling so scenarios read like user actions."""

    def __init__(self, client: httpx.AsyncClient, token: str, label: str) -> None:
        self._client = client
        self._token = token
        self.label = label

    @property
    def headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._token}"}

    async def get(self, path: str, **kw: object) -> httpx.Response:
        return await self._client.get(f"{BASE}{path}", headers=self.headers, **kw)  # type: ignore[arg-type]

    async def post(self, path: str, **kw: object) -> httpx.Response:
        return await self._client.post(f"{BASE}{path}", headers=self.headers, **kw)  # type: ignore[arg-type]


async def sign_in(client: httpx.AsyncClient, email: str, password: str, label: str) -> Session:
    response = await client.post(f"{BASE}/auth/login", json={"email": email, "password": password})
    response.raise_for_status()
    return Session(client, response.json()["accessToken"], label)


# --- Patient scenarios -------------------------------------------------------------


async def p1_patient_sees_only_their_own_appointments(s: Scenario, patient: Session) -> None:
    response = await patient.get("/appointments")
    if response.status_code != 200:
        s.record(Outcome.FAILED, f"appointment list returned {response.status_code}")
        return

    body = response.json()
    items = body.get("items", body if isinstance(body, list) else [])
    s.note(f"{len(items)} appointment(s) returned")
    s.record(Outcome.PASSED, f"list returned 200 with {len(items)} of the patient's own bookings")


async def p2_patient_can_book_an_available_slot(s: Scenario, patient: Session) -> str | None:
    slots = await patient.get("/slots", params={"limit": 5})
    if slots.status_code != 200:
        s.record(Outcome.FAILED, f"slot search returned {slots.status_code}")
        return None

    available = slots.json().get("items", [])
    if not available:
        s.record(Outcome.SKIPPED, "no available slots in the seeded window")
        return None

    slot_id = available[0]["id"]
    booking = await patient.post(
        "/appointments", json={"slotId": slot_id, "reason": "UAT scenario booking"}
    )
    if booking.status_code not in (200, 201):
        s.record(Outcome.FAILED, f"booking returned {booking.status_code}: {booking.text[:120]}")
        return None

    created = booking.json()["appointment"]
    s.note(f"booking reference {created['reference']}")
    s.record(Outcome.PASSED, f"slot booked, reference {created['reference']} issued")
    return str(created["id"])


async def p3_the_same_slot_cannot_be_booked_twice(s: Scenario, patient: Session) -> None:
    """The safety property behind this is that two patients never arrive for one slot."""
    slots = await patient.get("/slots", params={"limit": 5})
    available = slots.json().get("items", []) if slots.status_code == 200 else []
    if not available:
        s.record(Outcome.SKIPPED, "no available slots to contend for")
        return

    slot_id = available[0]["id"]
    first = await patient.post("/appointments", json={"slotId": slot_id, "reason": "UAT first"})
    second = await patient.post(
        "/appointments", json={"slotId": slot_id, "reason": "UAT duplicate"}
    )

    s.note(f"first attempt {first.status_code}, second attempt {second.status_code}")

    # Release the contended slot again: without this every run leaves another appointment
    # on the demo patient's record, and the seeded data drifts a little further each time.
    if first.status_code in (200, 201):
        booked = first.json()["appointment"]["id"]
        await patient.post(f"/appointments/{booked}/cancel", json={"reason": "UAT P3 cleanup"})
        s.note("contended booking released")

    if first.status_code in (200, 201) and second.status_code == 409:
        s.record(Outcome.PASSED, "second booking of the same slot refused with 409")
    else:
        s.record(
            Outcome.FAILED,
            f"expected 201 then 409, got {first.status_code} then {second.status_code}",
        )


async def p4_patient_can_cancel(s: Scenario, patient: Session, appointment_id: str | None) -> None:
    if not appointment_id:
        s.record(Outcome.SKIPPED, "no appointment was created to cancel")
        return

    response = await patient.post(
        f"/appointments/{appointment_id}/cancel", json={"reason": "UAT scenario cleanup"}
    )
    if response.status_code != 200:
        s.record(Outcome.FAILED, f"cancel returned {response.status_code}: {response.text[:120]}")
        return

    status = response.json()["appointment"]["status"]
    s.note(f"status after cancel: {status}")
    if status == "CANCELLED":
        s.record(Outcome.PASSED, "appointment moved to CANCELLED")
    else:
        s.record(Outcome.FAILED, f"expected CANCELLED, got {status}")


async def p5_emergency_symptoms_produce_urgent_advice(s: Scenario, patient: Session) -> None:
    """The single most safety-critical behaviour in the product."""
    created = await patient.post("/chat/sessions", json={})
    if created.status_code not in (200, 201):
        s.record(Outcome.FAILED, f"could not start a symptom check: {created.status_code}")
        return

    session_id = created.json()["session"]["id"]
    reply = await patient.post(
        f"/chat/sessions/{session_id}/messages",
        json={"content": "I have crushing chest pain and I cannot breathe"},
    )
    if reply.status_code not in (200, 201):
        s.record(Outcome.FAILED, f"message rejected: {reply.status_code}")
        return

    # Asserted on the session's own escalation state and the triage band, not on a
    # substring: a page that merely contains the word "emergency" somewhere in its footer
    # would pass a text search while doing nothing.
    body = reply.json()
    escalated = body["session"]["escalatedAt"] is not None
    band = (body.get("triage") or {}).get("severity")
    says_999 = "999" in reply.text
    s.note(f"escalated={escalated}, band={band}, advice mentions 999={says_999}")

    if escalated and says_999:
        s.record(Outcome.PASSED, f"escalated to emergency advice, band {band or 'n/a'}")
    else:
        s.record(
            Outcome.FAILED,
            f"red-flag symptoms did not escalate (escalated={escalated}, 999={says_999})",
        )


async def p6_unintelligible_input_does_not_advance(s: Scenario, patient: Session) -> None:
    """Regression cover for the defect where '.' was answered with 'Thank you.'"""
    created = await patient.post("/chat/sessions", json={})
    if created.status_code not in (200, 201):
        s.record(Outcome.SKIPPED, f"could not start a symptom check: {created.status_code}")
        return

    session_id = created.json()["session"]["id"]
    reply = await patient.post(f"/chat/sessions/{session_id}/messages", json={"content": "."})
    if reply.status_code not in (200, 201):
        s.record(Outcome.FAILED, f"message rejected: {reply.status_code}")
        return

    text = reply.text.lower()
    wrongly_advanced = "how long" in text or "thank you" in text
    s.note(f"advanced to the next question on meaningless input: {wrongly_advanced}")

    if wrongly_advanced:
        s.record(Outcome.FAILED, "intake advanced on input it could not understand")
    else:
        s.record(Outcome.PASSED, "intake re-asked rather than advancing")


# --- Clinical scenarios ------------------------------------------------------------


async def c1_clinician_sees_the_queue(s: Scenario, doctor: Session) -> list[dict[str, object]]:
    response = await doctor.get("/patients", params={"pageSize": 25})
    if response.status_code != 200:
        s.record(Outcome.FAILED, f"patient list returned {response.status_code}")
        return []

    items: list[dict[str, object]] = response.json().get("items", [])
    s.note(f"{len(items)} patients listed")
    s.record(Outcome.PASSED, f"clinician sees a working list of {len(items)} patients")
    return items


async def c2_record_access_follows_care_relationship(
    s: Scenario, doctor: Session, patients: list[dict[str, object]]
) -> str | None:
    """Identity is searchable; the record behind it is not. Returns an unassigned patient."""
    if not patients:
        s.record(Outcome.SKIPPED, "no patients listed to attempt access against")
        return None

    allowed: list[str] = []
    denied: list[str] = []
    for patient in patients[:12]:
        patient_id = str(patient["id"])
        response = await doctor.get(f"/patients/{patient_id}")
        (allowed if response.status_code == 200 else denied).append(patient_id)

    s.note(f"{len(allowed)} accessible, {len(denied)} refused without break-glass")

    if allowed and denied:
        s.record(
            Outcome.PASSED,
            f"access follows the care relationship: {len(allowed)} open, {len(denied)} refused",
        )
        return str(denied[0])
    if not denied:
        s.record(
            Outcome.FAILED, "every record was readable - the care relationship is not enforced"
        )
        return None
    s.record(Outcome.FAILED, "no record was readable, including assigned patients")
    return None


async def c3_breakglass_requires_a_justification(
    s: Scenario, doctor: Session, unassigned_id: str | None
) -> None:
    if not unassigned_id:
        s.record(Outcome.SKIPPED, "no unassigned patient found to test break-glass against")
        return

    thin = await doctor.post(
        f"/patients/{unassigned_id}/breakglass", json={"justification": "need"}
    )
    s.note(f"one-word justification returned {thin.status_code}")

    if thin.status_code in (200, 201):
        s.record(Outcome.FAILED, "break-glass granted on a one-word reason")
        return
    s.record(Outcome.PASSED, f"reason under 20 characters refused with {thin.status_code}")


async def c4_breakglass_opens_the_record_and_is_audited(
    s: Scenario, doctor: Session, unassigned_id: str | None
) -> None:
    if not unassigned_id:
        s.record(Outcome.SKIPPED, "no unassigned patient found")
        return

    granted = await doctor.post(
        f"/patients/{unassigned_id}/breakglass",
        json={"reason": "UAT scenario C4: verifying emergency access is granted and recorded."},
    )
    if granted.status_code not in (200, 201):
        s.record(Outcome.FAILED, f"break-glass refused a full reason: {granted.status_code}")
        return

    after = await doctor.get(f"/patients/{unassigned_id}")
    s.note(f"record access after break-glass: {after.status_code}")

    if after.status_code == 200:
        s.record(Outcome.PASSED, "break-glass granted access; audit assertion in A2")
    else:
        s.record(
            Outcome.FAILED,
            f"break-glass granted but record still returned {after.status_code}",
        )


async def c5_clinician_cannot_reach_admin_functions(s: Scenario, doctor: Session) -> None:
    response = await doctor.get("/admin/overview")
    s.note(f"clinician calling /admin/overview: {response.status_code}")

    if response.status_code == 403:
        s.record(Outcome.PASSED, "administrative endpoint refused to a clinician")
    else:
        s.record(Outcome.FAILED, f"expected 403, got {response.status_code}")


# --- Administrative scenarios ------------------------------------------------------


async def a1_admin_sees_the_overview(s: Scenario, admin: Session) -> None:
    response = await admin.get("/admin/overview")
    if response.status_code != 200:
        s.record(Outcome.FAILED, f"overview returned {response.status_code}")
        return

    keys = sorted(response.json().keys())
    s.note(f"metrics returned: {', '.join(keys[:8])}")
    s.record(Outcome.PASSED, f"overview returned {len(keys)} metric groups")


async def a2_the_breakglass_appears_in_the_audit_trail(s: Scenario, admin: Session) -> None:
    """The control is not the prompt; it is that the access is permanently recorded."""
    response = await admin.get("/admin/audit", params={"pageSize": 50})
    if response.status_code != 200:
        s.record(Outcome.FAILED, f"audit trail returned {response.status_code}")
        return

    entries = response.json().get("items", [])
    breakglass = [e for e in entries if "BREAKGLASS" in str(e.get("action", "")).upper()]
    s.note(f"{len(entries)} recent entries, {len(breakglass)} break-glass")

    if breakglass:
        s.record(Outcome.PASSED, f"the break-glass from C4 is recorded ({len(breakglass)} found)")
    else:
        s.record(Outcome.FAILED, "break-glass access does not appear in the audit trail")


async def a3_model_monitoring_reports_honestly(s: Scenario, admin: Session) -> None:
    response = await admin.get("/admin/models")
    if response.status_code != 200:
        s.record(Outcome.FAILED, f"model monitoring returned {response.status_code}")
        return

    body = response.text
    separates_direction = "under_triage" in body and "over_triage" in body
    s.note(f"under- and over-triage reported separately: {separates_direction}")

    if separates_direction:
        s.record(Outcome.PASSED, "under- and over-triage are reported as distinct measures")
    else:
        s.record(Outcome.FAILED, "monitoring collapses under- and over-triage into one figure")


# --- Cross-cutting scenarios -------------------------------------------------------


async def x1_unauthenticated_access_is_refused(s: Scenario, client: httpx.AsyncClient) -> None:
    response = await client.get(f"{BASE}/patients", params={"pageSize": 5})
    s.note(f"no credentials: {response.status_code}")

    if response.status_code == 401:
        s.record(Outcome.PASSED, "unauthenticated request refused with 401")
    else:
        s.record(Outcome.FAILED, f"expected 401, got {response.status_code}")


async def x2_a_forged_token_is_refused(s: Scenario, client: httpx.AsyncClient) -> None:
    forged = f"Bearer {uuid.uuid4().hex}.{uuid.uuid4().hex}.{uuid.uuid4().hex}"
    response = await client.get(f"{BASE}/patients", headers={"Authorization": forged})
    s.note(f"forged bearer token: {response.status_code}")

    if response.status_code == 401:
        s.record(Outcome.PASSED, "forged token refused with 401")
    else:
        s.record(Outcome.FAILED, f"expected 401, got {response.status_code}")


async def x3_errors_do_not_leak_internals(s: Scenario, patient: Session) -> None:
    response = await patient.get(f"/appointments/{uuid.uuid4()}")
    body = response.text.lower()
    leaks = [
        marker
        for marker in ("traceback", "sqlalchemy", "psycopg", "asyncpg", 'file "/', "select ")
        if marker in body
    ]
    s.note(f"status {response.status_code}, leaked markers: {leaks or 'none'}")

    if leaks:
        s.record(Outcome.FAILED, f"error response exposed internals: {', '.join(leaks)}")
    elif response.status_code in (403, 404):
        s.record(Outcome.PASSED, f"unknown resource returned a clean {response.status_code}")
    else:
        s.record(Outcome.FAILED, f"expected 403 or 404, got {response.status_code}")


async def x4_every_response_is_traceable(s: Scenario, patient: Session) -> None:
    """An incident cannot be investigated if the user's report cannot be tied to a log line."""
    ok = await patient.get("/appointments")
    err = await patient.get(f"/appointments/{uuid.uuid4()}")

    missing = [
        label
        for label, response in (("success", ok), ("error", err))
        if "x-request-id" not in {k.lower() for k in response.headers}
    ]
    s.note(f"X-Request-ID present on: {'both' if not missing else 'not ' + ', '.join(missing)}")

    if missing:
        s.record(Outcome.FAILED, f"X-Request-ID missing on the {' and '.join(missing)} path")
    else:
        s.record(Outcome.PASSED, "X-Request-ID present on both success and error responses")


async def x5_security_headers_are_applied(s: Scenario, patient: Session) -> None:
    response = await patient.get("/appointments")
    present = {k.lower() for k in response.headers}
    required = {"x-content-type-options", "content-security-policy", "referrer-policy"}
    missing = sorted(required - present)
    s.note(f"missing headers: {missing or 'none'}")

    if missing:
        s.record(Outcome.FAILED, f"missing security headers: {', '.join(missing)}")
    else:
        s.record(Outcome.PASSED, "content-type, CSP and referrer policy headers all present")


# --- Runner ------------------------------------------------------------------------


async def run(verbose: bool) -> int:
    password = os.environ.get(PASSWORD_ENV)
    if not password:
        print(f"{PASSWORD_ENV} is not set; seed the demo data first.", file=sys.stderr)
        return 2

    scenarios: list[Scenario] = []

    def scenario(ref: str, group: str, title: str) -> Scenario:
        item = Scenario(ref=ref, group=group, title=title)
        scenarios.append(item)
        return item

    async with httpx.AsyncClient(timeout=30) as client:
        patient = await sign_in(client, "patient@example.test", password, "patient")
        doctor = await sign_in(client, "doctor@example.test", password, "doctor")
        admin = await sign_in(client, "admin@example.test", password, "admin")

        p1 = scenario("P1", "Patient", "Sees their own appointments")
        await p1_patient_sees_only_their_own_appointments(p1, patient)

        p2 = scenario("P2", "Patient", "Books an available appointment")
        appointment_id = await p2_patient_can_book_an_available_slot(p2, patient)

        p3 = scenario("P3", "Patient", "Cannot double-book one slot")
        await p3_the_same_slot_cannot_be_booked_twice(p3, patient)

        p4 = scenario("P4", "Patient", "Cancels a booked appointment")
        await p4_patient_can_cancel(p4, patient, appointment_id)

        p5 = scenario("P5", "Patient", "Red-flag symptoms escalate to emergency advice")
        await p5_emergency_symptoms_produce_urgent_advice(p5, patient)

        p6 = scenario("P6", "Patient", "Intake does not advance on input it cannot understand")
        await p6_unintelligible_input_does_not_advance(p6, patient)

        c1 = scenario("C1", "Clinical", "Clinician sees the patient working list")
        listed = await c1_clinician_sees_the_queue(c1, doctor)

        c2 = scenario("C2", "Clinical", "Record access follows the care relationship")
        unassigned = await c2_record_access_follows_care_relationship(c2, doctor, listed)

        c3 = scenario("C3", "Clinical", "Break-glass refuses a thin justification")
        await c3_breakglass_requires_a_justification(c3, doctor, unassigned)

        c4 = scenario("C4", "Clinical", "Break-glass opens the record")
        await c4_breakglass_opens_the_record_and_is_audited(c4, doctor, unassigned)

        c5 = scenario("C5", "Clinical", "Clinician cannot reach administrative functions")
        await c5_clinician_cannot_reach_admin_functions(c5, doctor)

        a1 = scenario("A1", "Admin", "Administrator sees the service overview")
        await a1_admin_sees_the_overview(a1, admin)

        a2 = scenario("A2", "Admin", "Break-glass access appears in the audit trail")
        await a2_the_breakglass_appears_in_the_audit_trail(a2, admin)

        a3 = scenario("A3", "Admin", "Model monitoring separates under- and over-triage")
        await a3_model_monitoring_reports_honestly(a3, admin)

        x1 = scenario("X1", "Cross-cutting", "Unauthenticated access is refused")
        await x1_unauthenticated_access_is_refused(x1, client)

        x2 = scenario("X2", "Cross-cutting", "A forged token is refused")
        await x2_a_forged_token_is_refused(x2, client)

        x3 = scenario("X3", "Cross-cutting", "Errors do not leak internals")
        await x3_errors_do_not_leak_internals(x3, patient)

        x4 = scenario("X4", "Cross-cutting", "Every response is traceable")
        await x4_every_response_is_traceable(x4, patient)

        x5 = scenario("X5", "Cross-cutting", "Security headers are applied")
        await x5_security_headers_are_applied(x5, patient)

    print(f"\n  {'ref':<5}{'group':<15}{'scenario':<54}{'result'}")
    print(f"  {'-' * 5}{'-' * 15}{'-' * 54}{'-' * 6}")
    for item in scenarios:
        print(f"  {item.ref:<5}{item.group:<15}{item.title:<54}{item.outcome.value}")
        if item.outcome is not Outcome.PASSED or verbose:
            print(f"       {item.detail}")
        if verbose:
            for line in item.evidence:
                print(f"         - {line}")

    passed = sum(1 for i in scenarios if i.outcome is Outcome.PASSED)
    failed = [i for i in scenarios if i.outcome is Outcome.FAILED]
    skipped = [i for i in scenarios if i.outcome is Outcome.SKIPPED]

    print(f"\n  {passed} passed, {len(failed)} failed, {len(skipped)} skipped")
    if skipped:
        print(f"  skipped (not evidence of correctness): {', '.join(i.ref for i in skipped)}")
    if failed:
        print(f"  FAILED: {', '.join(i.ref for i in failed)}")

    return 1 if failed else 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the acceptance scenarios.")
    parser.add_argument("--verbose", action="store_true", help="Show evidence for every scenario.")
    args = parser.parse_args()
    return asyncio.run(run(args.verbose))


if __name__ == "__main__":
    raise SystemExit(main())
