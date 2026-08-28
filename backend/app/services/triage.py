"""Rule-based triage engine.

**This is not a diagnosis and not a model.** It is a deterministic keyword matcher whose
only job is to decide how urgently someone should be seen, and to recognise the small set
of presentations where the correct answer is "call 999 now, do not wait for us".

Ownership: the ML triage classifier belongs to the AI/ML domain (Task Plan, AI/ML S2).
This exists so the Full Stack booking journey has a working, inspectable priority signal,
and so the API contract the frontend depends on is settled before a model arrives. The
`TriageEngine` protocol is the seam: swapping in a model changes what implements it, not
the routes, the storage or the UI.

Three design decisions worth stating, because each looks like a flaw until the reasoning
is visible:

1. **No negation handling.** "no chest pain" matches the chest-pain rule and escalates.
   Handling negation correctly is hard, and every mistake in that direction produces
   *under*-triage - telling someone with chest pain to wait. Over-triage costs an
   unnecessary reassurance; under-triage can cost a life. The asymmetry decides it.

2. **Red flags short-circuit.** Once one matches, no further questions are asked and no
   appointment is offered. A system that keeps asking about duration while someone
   describes stroke symptoms is actively harmful.

3. **Unknown input escalates.** Text matching nothing does not become ROUTINE; it becomes
   SOON with a human-review flag. "We did not understand" must never be rendered as
   "you are fine".
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol

ENGINE_NAME = "rules"
ENGINE_VERSION = "0.3.0"


class Severity(StrEnum):
    EMERGENCY = "EMERGENCY"
    URGENT = "URGENT"
    SOON = "SOON"
    ROUTINE = "ROUTINE"
    SELF_CARE = "SELF_CARE"


#: Ordered most to least urgent, so the worst match always wins.
SEVERITY_ORDER: tuple[Severity, ...] = (
    Severity.EMERGENCY,
    Severity.URGENT,
    Severity.SOON,
    Severity.ROUTINE,
    Severity.SELF_CARE,
)


@dataclass(frozen=True, slots=True)
class Rule:
    """One matcher, with two complementary strategies.

    `phrases` match exact wording on word boundaries. `anchor` + `qualifiers` match when a
    body part and any concerning descriptor both appear anywhere in the text, in any order.

    The second exists because exact phrases miss natural speech. "my chest feels tight and
    heavy" matched none of "chest pain", "tight chest" or "chest tightness" - a real gap in
    a red-flag rule, found by test. Enumerating every phrasing people use is a losing game;
    co-occurrence covers the space far better and errs toward matching, which is the safe
    direction here.
    """

    flag: str
    phrases: tuple[str, ...]
    severity: Severity
    #: Shown to the patient. Plain English, no jargon, never a diagnosis.
    explanation: str
    #: A body part or subject, e.g. "chest".
    anchor: str | None = None
    #: Descriptors that make the anchor concerning, e.g. "tight", "heavy".
    qualifiers: tuple[str, ...] = ()


# --- Red flags ----------------------------------------------------------------
# Emergency presentations. Each ends the conversation and directs to 999.
RED_FLAG_RULES: tuple[Rule, ...] = (
    Rule(
        flag="cardiac_chest_pain",
        phrases=("angina",),
        # Any mention of the chest together with any of these descriptors. Covers "chest
        # pain", "my chest feels tight and heavy", "pressure across the chest" and the many
        # phrasings in between, without listing each one.
        anchor="chest",
        qualifiers=(
            "pain",
            "painful",
            "tight",
            "tightness",
            "heavy",
            "heaviness",
            "pressure",
            "crushing",
            "squeezing",
            "ache",
            "aching",
            "discomfort",
            "burning",
        ),
        severity=Severity.EMERGENCY,
        explanation="Chest pain or tightness can be a sign of a heart attack.",
    ),
    Rule(
        flag="stroke_symptoms",
        phrases=(
            "face has dropped",
            "face drooping",
            "one side of my face",
            "slurred speech",
            "cannot speak",
            "can't speak properly",
            "arm went weak",
            "weakness on one side",
            "numb on one side",
        ),
        severity=Severity.EMERGENCY,
        explanation="These can be signs of a stroke, where every minute matters.",
    ),
    Rule(
        flag="breathing_difficulty",
        phrases=(
            "cannot breathe",
            "can't breathe",
            "struggling to breathe",
            "gasping",
            "fighting for breath",
            "turning blue",
            "lips are blue",
        ),
        severity=Severity.EMERGENCY,
        explanation="Severe difficulty breathing needs emergency help.",
    ),
    Rule(
        flag="anaphylaxis",
        phrases=(
            "throat is closing",
            "throat closing",
            "tongue is swelling",
            "cannot swallow",
            "can't swallow",
            "anaphylaxis",
            "anaphylactic",
        ),
        severity=Severity.EMERGENCY,
        explanation="Swelling of the throat or tongue can be a severe allergic reaction.",
    ),
    Rule(
        flag="severe_bleeding",
        phrases=(
            "bleeding heavily",
            "will not stop bleeding",
            "won't stop bleeding",
            "losing a lot of blood",
            "coughing up blood",
            "vomiting blood",
        ),
        severity=Severity.EMERGENCY,
        explanation="Heavy or uncontrolled bleeding needs emergency help.",
    ),
    Rule(
        flag="sepsis_or_meningitis",
        phrases=(
            "rash that does not fade",
            "rash doesn't fade",
            "non blanching",
            "stiff neck and fever",
            "cannot stay awake",
            "can't stay awake",
            "confused and feverish",
        ),
        severity=Severity.EMERGENCY,
        explanation="These can be signs of a serious infection such as sepsis or meningitis.",
    ),
    Rule(
        flag="loss_of_consciousness",
        phrases=(
            "passed out",
            "blacked out",
            "unconscious",
            "having a seizure",
            "fitting",
            "collapsed",
        ),
        severity=Severity.EMERGENCY,
        explanation="Loss of consciousness or a seizure needs to be assessed immediately.",
    ),
    Rule(
        flag="self_harm_risk",
        phrases=(
            "kill myself",
            "end my life",
            "suicidal",
            "want to die",
            "harm myself",
            "hurt myself",
            "taken an overdose",
            "overdosed",
        ),
        severity=Severity.EMERGENCY,
        explanation="You deserve help right now, and it is available immediately.",
    ),
)

# --- Non-emergency rules ------------------------------------------------------
URGENT_RULES: tuple[Rule, ...] = (
    Rule(
        flag="high_fever_infant",
        phrases=("baby has a fever", "newborn fever", "baby is burning up"),
        severity=Severity.URGENT,
        explanation="A fever in a very young baby needs to be checked the same day.",
    ),
    Rule(
        flag="persistent_vomiting",
        phrases=("cannot keep anything down", "can't keep anything down", "vomiting for days"),
        severity=Severity.URGENT,
        explanation="Not being able to keep fluids down can lead to dehydration.",
    ),
    Rule(
        flag="severe_pain",
        phrases=("worst pain", "unbearable pain", "severe pain", "agony"),
        severity=Severity.URGENT,
        explanation="Severe pain should be assessed quickly.",
    ),
    Rule(
        flag="breathing_worse",
        phrases=("wheezing", "short of breath", "breathless"),
        severity=Severity.URGENT,
        explanation="Breathing problems should be assessed quickly.",
    ),
)

SOON_RULES: tuple[Rule, ...] = (
    Rule(
        flag="persistent_symptom",
        phrases=("for weeks", "for a month", "keeps coming back", "not getting better"),
        severity=Severity.SOON,
        explanation="Symptoms that persist should be looked at.",
    ),
    Rule(
        flag="infection_signs",
        phrases=("fever", "temperature", "infection", "swollen"),
        severity=Severity.SOON,
        explanation="Possible infection should be assessed.",
    ),
    Rule(
        flag="general_pain",
        phrases=("pain", "ache", "aching", "sore", "hurts"),
        severity=Severity.SOON,
        explanation="Pain should be assessed by a clinician.",
    ),
)

ROUTINE_RULES: tuple[Rule, ...] = (
    Rule(
        flag="minor_complaint",
        phrases=("rash", "cough", "cold", "blocked nose", "tired", "sleep", "itchy"),
        severity=Severity.ROUTINE,
        explanation="This can usually wait for a routine appointment.",
    ),
    Rule(
        flag="administrative",
        phrases=("repeat prescription", "sick note", "fit note", "test results", "referral"),
        severity=Severity.ROUTINE,
        explanation="This can be handled at a routine appointment.",
    ),
)

ALL_RULES: tuple[Rule, ...] = RED_FLAG_RULES + URGENT_RULES + SOON_RULES + ROUTINE_RULES

RECOMMENDED_ACTION: dict[Severity, str] = {
    Severity.EMERGENCY: (
        "Call 999 now, or go to your nearest A&E. Do not wait for an appointment and do "
        "not drive yourself."
    ),
    Severity.URGENT: "You should be seen within 24 hours.",
    Severity.SOON: "You should be seen within a week.",
    Severity.ROUTINE: "A routine appointment is suitable.",
    Severity.SELF_CARE: "This can usually be managed at home.",
}

#: Slot types offered for each band, used to filter availability in the booking flow.
#: EMERGENCY is absent on purpose: no appointment is ever offered for an emergency.
BOOKABLE_WITHIN_DAYS: dict[Severity, int] = {
    Severity.URGENT: 1,
    Severity.SOON: 7,
    Severity.ROUTINE: 84,
    Severity.SELF_CARE: 84,
}


@dataclass(frozen=True, slots=True)
class TriageAssessment:
    severity: Severity
    red_flags: tuple[str, ...]
    matched_rules: tuple[str, ...]
    explanations: tuple[str, ...]
    recommended_action: str
    #: True when nothing matched, so a human should look at it.
    needs_human_review: bool
    engine: str = ENGINE_NAME
    engine_version: str = ENGINE_VERSION
    #: Deliberately None. A rule matcher has no calibrated probability, and inventing one
    #: would give a clinician a number that looks like evidence and is not.
    confidence: float | None = None
    contributing_factors: dict[str, object] = field(default_factory=dict)

    @property
    def is_emergency(self) -> bool:
        return self.severity is Severity.EMERGENCY


class TriageEngine(Protocol):
    """The seam an ML classifier will implement in place of the rules."""

    def assess(self, text: str, *, history: list[str] | None = None) -> TriageAssessment: ...


def _matches(text: str, phrase: str) -> bool:
    """Word-boundary match, so 'cold' does not fire inside 'shoulder'."""
    return re.search(rf"(?<!\w){re.escape(phrase)}(?!\w)", text) is not None


def _rule_matches(text: str, rule: Rule) -> bool:
    if any(_matches(text, phrase) for phrase in rule.phrases):
        return True
    if rule.anchor and _matches(text, rule.anchor):
        return any(_matches(text, qualifier) for qualifier in rule.qualifiers)
    return False


class RuleBasedTriageEngine:
    """Deterministic matcher. Same input always gives the same output."""

    name = ENGINE_NAME
    version = ENGINE_VERSION

    def assess(self, text: str, *, history: list[str] | None = None) -> TriageAssessment:
        # History is folded in so a red flag mentioned earlier is not forgotten when the
        # patient's latest message is something innocuous like "about three days".
        corpus = " ".join([*(history or []), text]).lower()

        matched: list[Rule] = [rule for rule in ALL_RULES if _rule_matches(corpus, rule)]

        red_flags = tuple(rule.flag for rule in matched if rule.severity is Severity.EMERGENCY)

        if not matched:
            # Nothing recognised. This is the case most likely to be got wrong by
            # defaulting to ROUTINE, so it deliberately does not.
            return TriageAssessment(
                severity=Severity.SOON,
                red_flags=(),
                matched_rules=(),
                explanations=(
                    "We could not tell how urgent this is from what you told us, so we have "
                    "asked for it to be looked at by a person.",
                ),
                recommended_action=RECOMMENDED_ACTION[Severity.SOON],
                needs_human_review=True,
                contributing_factors={"reason": "no_rule_matched"},
            )

        # The most urgent match wins, always.
        severity = min((rule.severity for rule in matched), key=lambda s: SEVERITY_ORDER.index(s))
        relevant = [rule for rule in matched if rule.severity is severity]

        return TriageAssessment(
            severity=severity,
            red_flags=red_flags,
            matched_rules=tuple(rule.flag for rule in matched),
            explanations=tuple(rule.explanation for rule in relevant),
            recommended_action=RECOMMENDED_ACTION[severity],
            needs_human_review=severity in {Severity.EMERGENCY, Severity.URGENT},
            contributing_factors={
                "matchedRuleCount": len(matched),
                "usedConversationHistory": bool(history),
            },
        )


class UnavailableTriageEngine:
    """Stand-in for when the real engine cannot be reached.

    It does not return "unknown" or raise into the caller: it returns URGENT with a
    human-review flag. A triage system whose failure mode is silence would let a patient
    conclude nothing is wrong. Failing toward escalation is the only safe direction
    (ASSUMPTIONS P9).
    """

    name = "unavailable"
    version = "0"

    def assess(self, text: str, *, history: list[str] | None = None) -> TriageAssessment:
        return TriageAssessment(
            severity=Severity.URGENT,
            red_flags=(),
            matched_rules=(),
            explanations=(
                "We could not check your symptoms automatically, so we have asked for a "
                "person to look at this.",
            ),
            recommended_action=RECOMMENDED_ACTION[Severity.URGENT],
            needs_human_review=True,
            engine="unavailable",
            engine_version="0",
            contributing_factors={"reason": "engine_unavailable"},
        )


def get_triage_engine() -> TriageEngine:
    from app.core.config import get_settings

    if get_settings().triage_engine == "rules":
        return RuleBasedTriageEngine()
    # The ML engine is owned by the AI/ML domain and is not part of this build. Rather than
    # silently falling back to the rules - which would misreport which engine ran - this
    # returns the fail-safe engine, so the mismatch is visible in the stored result.
    return UnavailableTriageEngine()
