"""Redaction tests.

Brief §17 forbids logging passwords, tokens and unnecessary clinical content. Security
test S18. These tests exist because a redaction convention that nobody verifies is a
convention that quietly stops holding the first time someone is in a hurry.
"""

from __future__ import annotations

import json
import logging

import pytest

from app.core.logging import REDACTED_KEYS, JsonFormatter, redact

SENSITIVE_SAMPLE = {
    "password": "hunter2",
    "refresh_token": "eyJhbGciOiJIUzI1NiJ9.secret",
    "authorization": "Bearer eyJhbGciOi",
    "nhs_number": "9990000018",
    "date_of_birth": "1988-04-12",
    "email": "alex.morgan@example.test",
    "generated_content": "Mr Morgan was admitted on 24 August with chest discomfort.",
    "symptoms": "crushing central chest pain radiating to the left arm",
    "given_name": "Alex",
    "family_name": "Morgan",
    "postcode": "SW1A 1AA",
}


@pytest.mark.security
@pytest.mark.parametrize("key", sorted(SENSITIVE_SAMPLE))
def test_each_sensitive_key_is_redacted(key: str) -> None:
    result = redact({key: SENSITIVE_SAMPLE[key]})

    assert result[key] == "[redacted]"
    assert SENSITIVE_SAMPLE[key] not in json.dumps(result)


@pytest.mark.security
def test_redaction_reaches_nested_structures() -> None:
    """Sensitive data is usually nested, not top-level."""
    payload = {
        "event": "booking_created",
        "patient": {
            "id": "abc-123",
            "nhs_number": "9990000018",
            "contact": {"email": "alex@example.test", "phone": "+447700900123"},
        },
        "messages": [
            {"role": "PATIENT", "content": "I have been having chest pain"},
            {"role": "ASSISTANT", "content": "Please call 999"},
        ],
    }

    serialised = json.dumps(redact(payload))

    assert "9990000018" not in serialised
    assert "alex@example.test" not in serialised
    assert "chest pain" not in serialised
    # Non-sensitive identifiers survive - the log is still useful.
    assert "abc-123" in serialised
    assert "booking_created" in serialised


@pytest.mark.security
def test_redaction_is_case_insensitive() -> None:
    assert redact({"PASSWORD": "hunter2"})["PASSWORD"] == "[redacted]"
    assert redact({"NHS_Number": "9990000018"})["NHS_Number"] == "[redacted]"


@pytest.mark.security
def test_redaction_survives_cyclic_structures() -> None:
    """The logging path must never be able to hang or crash the application."""
    node: dict[str, object] = {"name": "ward"}
    node["self"] = node

    result = redact(node)

    assert json.dumps(result, default=str)  # terminates, and remains serialisable


@pytest.mark.security
def test_formatter_redacts_even_when_caller_did_not() -> None:
    """The formatter is the backstop.

    Calling code should not log a password. This test asserts that when it does anyway,
    the value still does not reach the output stream.
    """
    record = logging.LogRecord(
        name="app.api.v1.auth",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="login_attempt",
        args=(),
        exc_info=None,
    )
    record.email = "alex@example.test"
    record.password = "hunter2"
    record.request_id = "8f2c-4a1b"

    output = JsonFormatter().format(record)
    parsed = json.loads(output)

    assert parsed["password"] == "[redacted]"
    assert parsed["email"] == "[redacted]"
    assert parsed["request_id"] == "8f2c-4a1b"
    assert "hunter2" not in output


@pytest.mark.security
def test_formatter_emits_valid_single_line_json() -> None:
    record = logging.LogRecord(
        name="app",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="request_completed",
        args=(),
        exc_info=None,
    )
    record.status_code = 200

    output = JsonFormatter().format(record)

    assert "\n" not in output
    assert json.loads(output)["status_code"] == 200


@pytest.mark.security
def test_authentication_and_clinical_keys_are_all_covered() -> None:
    """Guards against a key being dropped from the redaction list during a refactor."""
    must_cover = {
        "password",
        "token",
        "refresh_token",
        "access_token",
        "authorization",
        "jwt_secret",
        "nhs_number",
        "date_of_birth",
        "email",
        "content",
        "generated_content",
        "symptoms",
        "diagnosis",
        "notes",
    }

    assert must_cover <= REDACTED_KEYS
