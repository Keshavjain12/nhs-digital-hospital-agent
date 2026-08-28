"""Model monitoring.

Every figure here is computed from `ai.triage_results`. Nothing is estimated, and models
that do not exist report no metrics at all rather than plausible-looking zeros - a
dashboard that shows 0% drift for a model nobody has built is worse than an empty row,
because it reads as a healthy model.

The metric that matters is not the override rate but its *direction*:

- A clinician choosing a LESS urgent band than the engine means the engine over-triaged.
  Costly, annoying, and safe.
- A clinician choosing a MORE urgent band means the engine UNDER-triaged. That is the
  failure that harms people, and it is tracked separately and never averaged away into a
  single "accuracy" number.

Everything returned is aggregate. Administrators see that overrides are happening and in
which direction; they never see whose record it was (rbac-and-audit.md §3).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Literal

from sqlalchemy import Integer, Text, case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chat import TriageResult, TriageReviewStatus
from app.services.triage import ENGINE_NAME, ENGINE_VERSION

#: Clinical ordering, lower is more urgent. Shared with the review service's sort.
SEVERITY_RANK: dict[str, int] = {
    "EMERGENCY": 0,
    "URGENT": 1,
    "SOON": 2,
    "ROUTINE": 3,
    "SELF_CARE": 4,
}

ModelStatus = Literal["LIVE", "SHADOW", "NOT_BUILT", "ROLLED_BACK"]


@dataclass(frozen=True, slots=True)
class Metric:
    """One reported number, with the wording needed to read it correctly."""

    key: str
    label: str
    value: str
    caption: str
    tone: Literal["neutral", "attention"] = "neutral"


@dataclass(frozen=True, slots=True)
class ModelCard:
    key: str
    name: str
    purpose: str
    owner: str
    status: ModelStatus
    version: str | None
    #: Empty for a model that does not exist. The UI must render that as "no data",
    #: never as zeroes.
    metrics: list[Metric] = field(default_factory=list)
    last_output_at: datetime | None = None
    #: Plain-English notes a reader needs in order not to over-interpret the numbers.
    caveats: list[str] = field(default_factory=list)


#: Models named in the project plan. Those the Full Stack domain has not built are listed
#: honestly rather than omitted - an absent row looks like an oversight, a NOT_BUILT row
#: is a statement.
PLANNED_MODELS: tuple[dict[str, str], ...] = (
    {
        "key": "no_show",
        "name": "Did-not-attend risk",
        "purpose": "Predicts which appointments are likely to be missed.",
        "owner": "Data Science",
    },
    {
        "key": "readmission",
        "name": "Readmission risk",
        "purpose": "Flags patients at higher risk of readmission after discharge.",
        "owner": "Data Science",
    },
    {
        "key": "demand_forecast",
        "name": "Bed and staff demand forecast",
        "purpose": "Projects demand so capacity can be planned rather than guessed.",
        "owner": "Data Science",
    },
    {
        "key": "note_summariser",
        "name": "Clinical note summariser",
        "purpose": "Drafts summaries and discharge letters for clinician approval.",
        "owner": "Gen AI",
    },
)


class ModelMonitoringService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def model_cards(self, *, window_days: int) -> list[ModelCard]:
        return [await self._triage_card(window_days), *self._planned_cards()]

    # --- The one model that exists --------------------------------------------

    async def _triage_card(self, window_days: int) -> ModelCard:
        since = datetime.now(UTC) - timedelta(days=window_days)

        rank = case(dict(SEVERITY_RANK), value=func.cast(TriageResult.severity, Text), else_=99)
        clinician_rank = case(
            dict(SEVERITY_RANK),
            value=func.cast(TriageResult.clinician_severity, Text),
            else_=99,
        )

        row = (
            await self._session.execute(
                select(
                    func.count().label("total"),
                    func.count()
                    .filter(TriageResult.review_status != TriageReviewStatus.PENDING_REVIEW)
                    .label("reviewed"),
                    func.count()
                    .filter(TriageResult.review_status == TriageReviewStatus.CLINICIAN_OVERRIDDEN)
                    .label("overridden"),
                    # Clinician picked a MORE urgent band: the engine missed something.
                    func.coalesce(
                        func.sum(
                            case(
                                (
                                    (TriageResult.clinician_severity.isnot(None))
                                    & (clinician_rank < rank),
                                    1,
                                ),
                                else_=0,
                            ).cast(Integer)
                        ),
                        0,
                    ).label("under_triaged"),
                    # Clinician picked a LESS urgent band: the engine over-triaged.
                    func.coalesce(
                        func.sum(
                            case(
                                (
                                    (TriageResult.clinician_severity.isnot(None))
                                    & (clinician_rank > rank),
                                    1,
                                ),
                                else_=0,
                            ).cast(Integer)
                        ),
                        0,
                    ).label("over_triaged"),
                    func.max(TriageResult.created_at).label("last_output"),
                ).where(TriageResult.created_at >= since)
            )
        ).one()

        total, reviewed, overridden, under, over, last_output = row

        metrics = [
            Metric(
                key="total",
                label="Results produced",
                value=str(total),
                caption=f"In the last {window_days} days",
            ),
            Metric(
                key="reviewed",
                label="Reviewed by a clinician",
                value=_ratio(reviewed, total),
                caption=f"{reviewed} of {total}",
                # Unreviewed output is not a model problem, but it is the reason the other
                # numbers are provisional, so it is flagged rather than buried.
                tone="attention" if total and reviewed < total else "neutral",
            ),
            Metric(
                key="agreement",
                label="Clinician agreed",
                value=_ratio(reviewed - overridden, reviewed),
                caption=f"{reviewed - overridden} of {reviewed} reviewed",
            ),
            Metric(
                key="under_triage",
                label="Made more urgent by a clinician",
                value=str(under),
                caption="The engine judged these less urgent than the clinician did",
                # The safety-critical direction. Any occurrence deserves a look.
                tone="attention" if under else "neutral",
            ),
            Metric(
                key="over_triage",
                label="Made less urgent by a clinician",
                value=str(over),
                caption="The engine judged these more urgent than the clinician did",
            ),
        ]

        return ModelCard(
            key="triage",
            name="Triage severity check",
            purpose="Suggests how urgently a patient should be seen.",
            owner="AI/ML (rule-based stand-in built by Full Stack)",
            status="LIVE",
            version=f"{ENGINE_NAME} {ENGINE_VERSION}",
            metrics=metrics,
            last_output_at=last_output,
            caveats=[
                "This is a deterministic rule matcher, not a trained model. It reports no "
                "confidence score because it has none.",
                "It deliberately over-triages: ambiguous input is escalated rather than "
                "downgraded, so a high 'made less urgent' count is expected behaviour.",
                "These figures come from synthetic demonstration data and say nothing about "
                "how the engine would perform on real patients.",
                "Monitoring is not clinical governance. It does not replace a safety case, "
                "a Clinical Safety Officer, or clinician review of every output.",
            ],
        )

    # --- Models that do not exist ----------------------------------------------

    @staticmethod
    def _planned_cards() -> list[ModelCard]:
        return [
            ModelCard(
                key=spec["key"],
                name=spec["name"],
                purpose=spec["purpose"],
                owner=spec["owner"],
                status="NOT_BUILT",
                version=None,
                metrics=[],
                caveats=[
                    "Not built. No output has ever been produced, so there is nothing to "
                    "monitor and no figures are shown."
                ],
            )
            for spec in PLANNED_MODELS
        ]


def _ratio(part: int, whole: int) -> str:
    """A percentage, or an em dash when the denominator is zero.

    Rendering 0/0 as "0%" would report a failure where there is simply no data.
    """
    if not whole:
        return "—"
    return f"{round(part / whole * 100)}%"
