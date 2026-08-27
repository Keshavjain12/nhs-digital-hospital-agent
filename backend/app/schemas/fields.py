"""Reusable validated field types.

`EmailAddress` exists instead of pydantic's `EmailStr` for one specific reason, recorded
here because it looks like a weakening of validation and is the opposite.

`email_validator` rejects RFC 2606 special-use domains (`.test`, `.invalid`, `.example`)
on the grounds that mail to them cannot be delivered. That is exactly why this project
uses them: every synthetic patient gets an `@example.test` address so that a bug in the
notification service physically cannot send a real message to a real person
(docs/data/dataset-strategy.md §4.1).

With `EmailStr`, the safety property and the validator are in direct conflict - the seed
data will not load. Enabling `test_environment` resolves it in the right direction:
syntax is still fully validated, and the reserved domains stay usable.

Deliverability is never checked. It performs a DNS lookup, which would make request
latency depend on an external resolver and make the test suite fail offline.
"""

from __future__ import annotations

from typing import Annotated, Any

from email_validator import EmailNotValidError, validate_email
from pydantic import AfterValidator, Field


def _normalise_email(value: str) -> str:
    try:
        result = validate_email(
            value,
            check_deliverability=False,
            # Permits .test / .invalid / .example, used throughout the synthetic dataset.
            test_environment=True,
        )
    except EmailNotValidError as exc:
        raise ValueError("email_invalid") from exc

    # Lower-cased to match the functional unique index on identity.users, so the same
    # address cannot produce two accounts.
    return result.normalized.lower()


EmailAddress = Annotated[str, Field(max_length=320), AfterValidator(_normalise_email)]


def is_reserved_domain(email: str) -> bool:
    """Whether an address is in a domain reserved for documentation and testing.

    Used by the seeder to assert that no generated contact detail could reach a real
    person, and available to any check that wants the same guarantee.
    """
    domain = email.rsplit("@", 1)[-1].lower()
    return domain.endswith((".test", ".invalid", ".example", ".localhost")) or domain in {
        "example.com",
        "example.net",
        "example.org",
    }


def describe_email_policy() -> dict[str, Any]:
    """Surfaced in the OpenAPI description so the rule is discoverable, not folklore."""
    return {
        "syntaxChecked": True,
        "deliverabilityChecked": False,
        "reservedDomainsAllowed": True,
    }
