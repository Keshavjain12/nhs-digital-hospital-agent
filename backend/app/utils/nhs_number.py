"""NHS number validation (Modulus 11).

Required by the project plan (Python S2). The algorithm, per the NHS Data Dictionary:

1. The number is 10 digits. The first nine are the identifier; the tenth is a check digit.
2. Multiply each of the first nine digits by a weight running from 10 down to 2.
3. Sum the products and take the remainder modulo 11.
4. Subtract the remainder from 11 to get the check digit.
5. A result of 11 is treated as 0. A result of 10 means the number is invalid - there is
   no single digit that can represent it, so such identifiers are never issued.

Step 5 is the part usually got wrong. Treating 10 as valid, or mapping it to 0, accepts
numbers the NHS would never issue.
"""

from __future__ import annotations

import re

NHS_NUMBER_LENGTH = 10
_DIGITS_ONLY = re.compile(r"[^0-9]")

# Conventionally reserved for test and synthetic data. Recorded as open action D2 in
# docs/data/dataset-strategy.md: verify against the NHS Data Dictionary before relying on
# this as a guarantee rather than a convention.
TEST_RANGE_PREFIX = "999"


def normalise(value: str) -> str:
    """Strip spaces and dashes. NHS numbers are commonly written as 943 476 5919."""
    return _DIGITS_ONLY.sub("", value or "")


def is_valid(value: str | None) -> bool:
    if not value:
        return False

    digits = normalise(value)
    if len(digits) != NHS_NUMBER_LENGTH:
        return False

    weighted_sum = sum(int(digit) * (10 - index) for index, digit in enumerate(digits[:9]))
    remainder = weighted_sum % 11
    check_digit = 11 - remainder

    if check_digit == 11:
        check_digit = 0
    elif check_digit == 10:
        # No valid NHS number has a check digit of 10.
        return False

    return check_digit == int(digits[9])


def is_test_range(value: str | None) -> bool:
    """Whether the number falls in the range reserved for synthetic data."""
    if not value:
        return False
    return normalise(value).startswith(TEST_RANGE_PREFIX)


def format_display(value: str) -> str:
    """Format as 3-3-4, the grouping used on NHS correspondence.

    Grouping matters for safety: a clinician reading a 10-digit run aloud is far more
    likely to transpose digits than one reading three short groups.
    """
    digits = normalise(value)
    if len(digits) != NHS_NUMBER_LENGTH:
        return value
    return f"{digits[:3]} {digits[3:6]} {digits[6:]}"


def _check_digit(body: str) -> int | None:
    """The check digit for a nine-digit body, or None when the body is unusable.

    A body is unusable when the calculation yields 10, since no single digit can represent
    it. Roughly one body in eleven falls into this case.
    """
    weighted_sum = sum(int(digit) * (10 - index) for index, digit in enumerate(body))
    check = 11 - (weighted_sum % 11)
    if check == 11:
        return 0
    if check == 10:
        return None
    return check


# Valid bodies in the test range, built lazily and extended on demand. Caching keeps the
# indexed lookup amortised O(1); rescanning on every call would make seeding a few
# thousand patients quadratic.
_valid_bodies: list[str] = []
_scan_position = 0


def _ensure_bodies(count: int) -> None:
    global _scan_position

    while len(_valid_bodies) < count:
        if _scan_position >= 1_000_000:
            raise ValueError(
                f"the {TEST_RANGE_PREFIX} test range holds fewer than {count} valid numbers"
            )
        body = f"{TEST_RANGE_PREFIX}{_scan_position:06d}"
        if _check_digit(body) is not None:
            _valid_bodies.append(body)
        _scan_position += 1


def generate_test_number(sequence: int) -> str:
    """The NHS number at position `sequence` in the test range.

    Injective: distinct sequences always yield distinct numbers. An earlier version
    stepped past an unusable body by an offset, which silently landed on the neighbouring
    sequence's number. That is fatal against the unique constraint on
    `patients.nhs_number`, and only shows up once a seed run is large enough to collide.

    Deterministic, so a seeded dataset reproduces exactly for debugging and demos.
    """
    if sequence < 0:
        raise ValueError("sequence must be non-negative")

    _ensure_bodies(sequence + 1)
    body = _valid_bodies[sequence]
    return f"{body}{_check_digit(body)}"


def generate_test_numbers(count: int, *, start: int = 0) -> list[str]:
    """`count` distinct valid test-range numbers, for bulk seeding."""
    _ensure_bodies(start + count)
    return [f"{body}{_check_digit(body)}" for body in _valid_bodies[start : start + count]]
