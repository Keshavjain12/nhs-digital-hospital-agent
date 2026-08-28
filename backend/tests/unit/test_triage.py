"""Triage engine tests.

These are the safety tests. Everything else in this repository can be wrong in ways that
cost time; this can be wrong in a way that costs a life, so the assertions are about the
*direction* of failure, not just correctness on happy paths.

The engine is a deterministic rule matcher, not a model, and not a diagnosis. It decides
only how urgently someone should be seen.
"""

from __future__ import annotations

import pytest

from app.services.triage import (
    RED_FLAG_RULES,
    SEVERITY_ORDER,
    RuleBasedTriageEngine,
    Severity,
    UnavailableTriageEngine,
)

engine = RuleBasedTriageEngine()


# --- Red flags ----------------------------------------------------------------


@pytest.mark.parametrize(
    "message",
    [
        "I have chest pain that spreads to my left arm",
        "my chest feels tight and heavy",
        "there is pressure in my chest",
        "my face has dropped on one side",
        "his speech is slurred and his arm went weak",
        "I cannot breathe properly",
        "she is gasping for air",
        "my throat is closing up",
        "the cut will not stop bleeding",
        "I am coughing up blood",
        "there is a rash that does not fade when pressed",
        "he passed out and collapsed",
        "I have been having a seizure",
        "I want to kill myself",
        "I have taken an overdose",
    ],
)
def test_emergency_presentations_are_flagged(message: str) -> None:
    result = engine.assess(message)

    assert result.severity is Severity.EMERGENCY, message
    assert result.is_emergency
    assert result.red_flags


def test_every_red_flag_rule_actually_fires() -> None:
    """A rule that never matches is dead code wearing the shape of a safety control."""
    for rule in RED_FLAG_RULES:
        for phrase in rule.phrases:
            result = engine.assess(f"I think {phrase} is happening")

            assert result.severity is Severity.EMERGENCY, f"{rule.flag}: {phrase!r}"
            assert rule.flag in result.red_flags

        for qualifier in rule.qualifiers:
            result = engine.assess(f"my {rule.anchor} feels {qualifier}")

            assert result.severity is Severity.EMERGENCY, f"{rule.flag}: {qualifier!r}"
            assert rule.flag in result.red_flags


@pytest.mark.parametrize(
    "message",
    [
        "my chest feels tight and heavy",
        "there is a heaviness across my chest",
        "my chest has been aching since this morning",
        "burning in the chest",
        "squeezing feeling in my chest",
    ],
)
def test_natural_phrasings_of_chest_symptoms_are_caught(message: str) -> None:
    """Regression: exact-phrase matching missed ordinary speech.

    "my chest feels tight and heavy" matched none of the original phrases, so someone
    describing a possible heart attack in their own words was banded SOON.
    """
    assert engine.assess(message).severity is Severity.EMERGENCY


def test_an_emergency_never_recommends_waiting_for_an_appointment() -> None:
    result = engine.assess("I have crushing chest pain")

    assert "999" in result.recommended_action
    for wrong in ("within 24 hours", "within a week", "routine appointment"):
        assert wrong not in result.recommended_action


# --- Direction of failure ------------------------------------------------------


def test_negated_red_flags_still_escalate() -> None:
    """Deliberate over-triage.

    "no chest pain" matches and escalates. Handling negation correctly is hard, and every
    error in that direction is *under*-triage. Over-triage costs a wasted reassurance;
    under-triage can cost a life, so the asymmetry decides it. If this test is ever
    "fixed", the reasoning above has to be revisited first.
    """
    result = engine.assess("I have no chest pain at all")

    assert result.severity is Severity.EMERGENCY


def test_unrecognised_text_does_not_become_routine() -> None:
    """ "We did not understand" must never be rendered as "you are fine"."""
    result = engine.assess("qwertyuiop zxcvbnm asdfgh")

    assert result.severity is Severity.SOON
    assert result.needs_human_review is True
    assert result.matched_rules == ()


def test_empty_input_does_not_become_routine() -> None:
    result = engine.assess("")

    assert result.severity is not Severity.ROUTINE
    assert result.needs_human_review is True


def test_the_most_urgent_match_wins() -> None:
    """A minor symptom mentioned alongside a red flag must not dilute it."""
    result = engine.assess("I have a bit of a cough and also crushing chest pain")

    assert result.severity is Severity.EMERGENCY


def test_a_red_flag_from_earlier_in_the_conversation_is_not_forgotten() -> None:
    """The patient mentions chest pain, then answers a follow-up with "three days".

    Assessing only the latest message would downgrade them to routine.
    """
    result = engine.assess("about three days", history=["I have had chest pain since this morning"])

    assert result.severity is Severity.EMERGENCY
    assert "cardiac_chest_pain" in result.red_flags


# --- Ordinary bands ------------------------------------------------------------


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("I cannot keep anything down", Severity.URGENT),
        ("I am short of breath when walking", Severity.URGENT),
        ("I have had a sore knee for weeks", Severity.SOON),
        ("I need a repeat prescription", Severity.ROUTINE),
        ("I have an itchy rash on my arm", Severity.ROUTINE),
    ],
)
def test_non_emergency_bands(message: str, expected: Severity) -> None:
    assert engine.assess(message).severity is expected


def test_word_boundaries_are_respected() -> None:
    """'cold' must not fire inside 'shoulder'; a substring match would mis-band everything."""
    result = engine.assess("my shoulder is stiff")

    assert "minor_complaint" not in result.matched_rules


# --- Determinism and shape -----------------------------------------------------


def test_the_engine_is_deterministic() -> None:
    """A triage band that varies between identical inputs cannot be reviewed."""
    message = "I have had a headache and a fever for two days"

    assert engine.assess(message) == engine.assess(message)


def test_no_confidence_is_reported() -> None:
    """A rule matcher has no calibrated probability.

    Inventing one would hand a clinician a number that looks like evidence and is not.
    """
    assert engine.assess("I have chest pain").confidence is None


def test_the_engine_identifies_itself() -> None:
    """A stored severity is not reviewable without knowing what produced it."""
    result = engine.assess("I have a cough")

    assert result.engine == "rules"
    assert result.engine_version


def test_explanations_are_present_and_plain() -> None:
    result = engine.assess("I have chest pain")

    assert result.explanations
    for explanation in result.explanations:
        assert explanation[0].isupper()
        assert len(explanation) > 20


@pytest.mark.parametrize("severity", list(Severity))
def test_every_severity_has_a_recommended_action(severity: Severity) -> None:
    from app.services.triage import RECOMMENDED_ACTION

    assert RECOMMENDED_ACTION[severity]


def test_severity_order_covers_every_band() -> None:
    """The 'most urgent wins' comparison indexes into this; a missing band would raise."""
    assert set(SEVERITY_ORDER) == set(Severity)


# --- Failure mode ---------------------------------------------------------------


def test_an_unavailable_engine_escalates_rather_than_going_quiet() -> None:
    """ASSUMPTIONS P9: a safe failure state cannot be 'assume the patient is fine'."""
    result = UnavailableTriageEngine().assess("I have a mild headache")

    assert result.severity is Severity.URGENT
    assert result.needs_human_review is True
    assert result.engine == "unavailable"


def test_emergency_is_never_offered_an_appointment_window() -> None:
    from app.services.triage import BOOKABLE_WITHIN_DAYS

    assert Severity.EMERGENCY not in BOOKABLE_WITHIN_DAYS
