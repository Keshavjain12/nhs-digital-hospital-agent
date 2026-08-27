"""NHS number Modulus 11 tests.

The check-digit-of-10 case is the one implementations usually get wrong, so it is tested
explicitly rather than left to the round-trip tests to catch by chance.
"""

from __future__ import annotations

import pytest

from app.utils import nhs_number as nhs


@pytest.mark.parametrize(
    "value",
    [
        "9434765919",  # widely published example of a valid NHS number
        "943 476 5919",  # same number, formatted
        "943-476-5919",  # same number, dashed
    ],
)
def test_accepts_valid_numbers(value: str) -> None:
    assert nhs.is_valid(value) is True


@pytest.mark.parametrize(
    ("value", "reason"),
    [
        ("9434765918", "check digit is wrong"),
        ("943476591", "only nine digits"),
        ("94347659190", "eleven digits"),
        ("", "empty"),
        ("abcdefghij", "not numeric"),
        ("943476591a", "trailing non-digit"),
    ],
)
def test_rejects_invalid_numbers(value: str, reason: str) -> None:
    assert nhs.is_valid(value) is False, reason


def test_rejects_none() -> None:
    assert nhs.is_valid(None) is False


def test_generated_test_numbers_are_valid_and_in_range() -> None:
    """Every generated number must pass the same validator the API uses.

    A generator that emits numbers its own validator rejects would fail at seed time and
    take the whole demo dataset with it.
    """
    for sequence in range(0, 5000, 37):
        number = nhs.generate_test_number(sequence)

        assert len(number) == 10
        assert nhs.is_valid(number), f"generated {number} failed validation"
        assert nhs.is_test_range(number)


def test_generation_is_deterministic() -> None:
    """A seeded dataset must reproduce exactly, for debugging and for demos."""
    assert nhs.generate_test_number(42) == nhs.generate_test_number(42)


def test_generated_numbers_are_distinct_across_a_run() -> None:
    numbers = {nhs.generate_test_number(i) for i in range(500)}

    assert len(numbers) == 500


def test_check_digit_of_ten_is_rejected_not_wrapped() -> None:
    """A remainder giving a check digit of 10 makes the number invalid.

    Mapping it to 0 - the common bug - would accept identifiers the NHS never issues.
    This searches for a body that actually produces the case rather than asserting on a
    hard-coded example, so it keeps testing the real branch if the algorithm is touched.
    """
    found = False
    for candidate in range(100_000_000, 100_002_000):
        body = f"{candidate:09d}"
        weighted = sum(int(d) * (10 - i) for i, d in enumerate(body))
        if 11 - (weighted % 11) == 10:
            found = True
            # Every possible final digit must be rejected for this body.
            for final in range(10):
                assert nhs.is_valid(f"{body}{final}") is False
            break

    assert found, "no check-digit-of-10 case found in the search range"


def test_display_format_is_three_three_four() -> None:
    """Grouping reduces transcription errors when a number is read aloud."""
    assert nhs.format_display("9434765919") == "943 476 5919"


def test_display_format_leaves_malformed_input_untouched() -> None:
    assert nhs.format_display("123") == "123"
