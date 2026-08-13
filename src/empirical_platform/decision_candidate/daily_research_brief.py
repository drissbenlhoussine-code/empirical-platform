"""MILESTONE-072. Deterministic composition of an operator-facing daily
research brief.

This module performs zero new strategy, ranking, risk, sizing,
backtest, statistical, portfolio, or dependence computation. Every
value it carries is read verbatim from already-persisted M057
(`EvaluationReasonCode`)/M059 (`TradePlanGeometry`,
`TradePlanRejectionReason`)/M060 (`PositionSizing`,
`PositionPlanRejectionReason`)/M070 (`ResearchSession`)/M071
(`compare_session_decisions`) evidence. The only genuinely new logic
here is `classify_attention_level` -- a small, closed, deterministic
classification of already-computed decision fields, not a score, not
a model, not an LLM.

The fetching of `DecisionCandidate`/`TradePlan`/`PositionPlan` records
(real I/O) happens one layer up, in
`usecases/build_daily_research_brief.py`; this module only ever
consumes already-fetched values, so every function here is pure and
independently unit-testable without a database.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from empirical_platform.decision_candidate.historical_portfolio_evidence import (
    HistoricalPortfolioEvidence,
)
from empirical_platform.decision_candidate.research_session import (
    ResearchDecisionEntry,
    ResearchSessionSummary,
    SessionComparisonEntry,
    SessionComparisonOutcome,
)

__all__ = [
    "AttentionLevel",
    "BriefInstrumentEntry",
    "BriefRiskEvidence",
    "DailyResearchBrief",
    "FetchedInstrumentEvidence",
    "HistoricalPortfolioEvidence",
    "build_daily_research_brief",
    "classify_attention_level",
    "explain_reason_code",
]


class AttentionLevel(StrEnum):
    """Closed, deterministic attention vocabulary -- no opaque score,
    no ML, no LLM. A session-level `WARNING` (see
    `DailyResearchBrief.session_warnings`) always renders above every
    instrument-level attention level, regardless of how the instrument
    itself is classified."""

    ACTION_CANDIDATE = "ACTION_CANDIDATE"
    REVIEW = "REVIEW"
    ROUTINE = "ROUTINE"
    DROPPED = "DROPPED"


_ATTENTION_PRIORITY: dict[AttentionLevel, int] = {
    AttentionLevel.ACTION_CANDIDATE: 0,
    AttentionLevel.REVIEW: 1,
    AttentionLevel.ROUTINE: 2,
    AttentionLevel.DROPPED: 3,
}

#: Plain-text explanations for the frozen M057 `EvaluationReasonCode`
#: vocabulary. Display-only -- never reinterprets or recomputes the
#: underlying evaluation.
_EVALUATION_REASON_TEXT: dict[str, str] = {
    "PRICE_ABOVE_REFERENCE_HIGH": "closing price cleared the reference high",
    "PRICE_NOT_ABOVE_REFERENCE_HIGH": "closing price did not clear the reference high",
    "VOLUME_ABOVE_REFERENCE_AVERAGE": "volume exceeded the reference average",
    "VOLUME_NOT_ABOVE_REFERENCE_AVERAGE": "volume did not exceed the reference average",
}

#: Plain-text explanations for the frozen M059 `TradePlanRejectionReason`
#: vocabulary.
_TRADE_PLAN_REASON_TEXT: dict[str, str] = {
    "SOURCE_NOT_LONG_CANDIDATE": "the source scan was not a LONG_CANDIDATE",
    "PROVENANCE_MISMATCH": "the source evidence provenance did not match",
    "INVALID_STOP_GEOMETRY": "the computed stop geometry was invalid",
    "INVALID_TARGET_GEOMETRY": "the computed target geometry was invalid",
    "REWARD_RISK_BELOW_MINIMUM": "the reward:risk ratio was below the policy minimum",
}

#: Plain-text explanations for the frozen M060 `PositionPlanRejectionReason`
#: vocabulary.
_POSITION_PLAN_REASON_TEXT: dict[str, str] = {
    "SOURCE_PLAN_NOT_APPROVED": "the source trade plan was not approved",
    "INVALID_EQUITY": "the supplied account equity was invalid",
    "INVALID_RISK_BUDGET": "the supplied risk percent was invalid",
    "POLICY_VIOLATION": "the sizing policy was violated",
    "ZERO_POSITION_SIZE": "the computed position size was zero",
    "CAPITAL_LIMIT_EXCEEDED": "the position exceeded the capital/notional limit",
}

#: Shown for a REJECTED_POSITION_PLAN whose governance id was never
#: persisted on `ResearchDecisionEntry` -- MILESTONE-070's own
#: orchestrator (`run_daily_research_session.py`) only records
#: `position_plan_governance_id` on the APPROVED branch, so a rejected
#: position plan's own reason codes are genuinely unavailable from this
#: session's own record. Stated honestly rather than fabricated;
#: MILESTONE-070 is frozen and not reopened to backfill this.
POSITION_SIZING_REASON_UNAVAILABLE = (
    "position-sizing rejection reason unavailable -- this session's own "
    "record does not retain a rejected position plan's governance id"
)


def explain_reason_code(code: str) -> str:
    """Translate one frozen M057/M059/M060 machine-readable reason code
    into a plain-text explanation, for display only."""
    for table in (_EVALUATION_REASON_TEXT, _TRADE_PLAN_REASON_TEXT, _POSITION_PLAN_REASON_TEXT):
        if code in table:
            return table[code]
    return code


def classify_attention_level(
    *,
    comparison_outcome: SessionComparisonOutcome,
    scan_decision: str | None,
    trade_plan_decision: str | None,
    position_plan_status: str | None,
) -> AttentionLevel:
    """Pure, deterministic classification of already-computed decision
    fields. Never inspects price, volume, or any other market value
    directly -- only the closed-vocabulary decision strings a session
    already carries."""
    if comparison_outcome is SessionComparisonOutcome.DROPPED:
        return AttentionLevel.DROPPED
    if (
        scan_decision == "LONG_CANDIDATE"
        and trade_plan_decision == "APPROVED_PLAN"
        and position_plan_status == "APPROVED_POSITION_PLAN"
    ):
        return AttentionLevel.ACTION_CANDIDATE
    if comparison_outcome is SessionComparisonOutcome.CHANGED:
        return AttentionLevel.REVIEW
    if scan_decision == "LONG_CANDIDATE":
        return AttentionLevel.REVIEW
    return AttentionLevel.ROUTINE


@dataclass(frozen=True, slots=True)
class BriefRiskEvidence:
    """Read verbatim from an already-persisted `TradePlanGeometry` +
    `PositionSizing` pair -- never recomputed. Decimal values are
    carried as their exact `str()` form so no float/Decimal rendering
    ambiguity can creep into either the text or JSON renderer."""

    entry_price: str
    stop_price: str
    target_price: str
    reward_risk_ratio: str
    quantity: int
    position_notional: str
    actual_risk: str

    def __post_init__(self) -> None:
        if self.quantity < 0:
            raise ValueError("quantity must not be negative")


@dataclass(frozen=True, slots=True)
class FetchedInstrumentEvidence:
    """Evidence fetched by the usecase layer via the MILESTONE-072
    `get_by_governance_id` repository lookups -- read verbatim, never
    recomputed. Passed into `build_daily_research_brief` so the
    domain-level composition itself stays a pure function with no I/O."""

    evaluation_reason_codes: tuple[str, ...]
    trade_plan_reason_codes: tuple[str, ...]
    position_plan_status: str | None
    position_plan_reason_codes: tuple[str, ...]
    position_plan_reason_unavailable: bool
    risk_evidence: BriefRiskEvidence | None


@dataclass(frozen=True, slots=True)
class BriefInstrumentEntry:
    """One instrument's fully-explained entry in the brief."""

    instrument_symbol: str
    attention_level: AttentionLevel
    comparison_outcome: SessionComparisonOutcome
    scan_decision: str | None
    trade_plan_decision: str | None
    position_plan_status: str | None
    baseline_scan_decision: str | None
    baseline_trade_plan_decision: str | None
    rejection_reasons: tuple[str, ...]
    risk_evidence: BriefRiskEvidence | None

    def __post_init__(self) -> None:
        if not self.instrument_symbol.strip():
            raise ValueError("instrument_symbol must be non-empty")
        if self.comparison_outcome is SessionComparisonOutcome.DROPPED:
            if self.scan_decision is not None or self.trade_plan_decision is not None:
                raise ValueError("a DROPPED entry must carry no current-session decision")
            if self.risk_evidence is not None:
                raise ValueError("a DROPPED entry must carry no risk_evidence")
        else:
            if self.scan_decision is None:
                raise ValueError("a non-DROPPED entry must carry a scan_decision")


def _classify_and_build_entry(
    *,
    decision: ResearchDecisionEntry,
    comparison_by_symbol: Mapping[str, SessionComparisonEntry],
    evidence_by_governance_id: Mapping[str, FetchedInstrumentEvidence],
) -> BriefInstrumentEntry:
    comparison = comparison_by_symbol[decision.instrument_symbol]
    evidence = evidence_by_governance_id.get(decision.decision_candidate_governance_id)

    attention_level = classify_attention_level(
        comparison_outcome=comparison.outcome,
        scan_decision=decision.scan_decision,
        trade_plan_decision=decision.trade_plan_decision,
        position_plan_status=evidence.position_plan_status if evidence else None,
    )

    rejection_reasons: tuple[str, ...] = ()
    risk_evidence: BriefRiskEvidence | None = None
    if evidence is not None:
        reasons: list[str] = []
        if decision.scan_decision == "NO_TRADE":
            reasons.extend(explain_reason_code(c) for c in evidence.evaluation_reason_codes)
        if decision.trade_plan_decision == "REJECTED_PLAN":
            reasons.extend(explain_reason_code(c) for c in evidence.trade_plan_reason_codes)
        if evidence.position_plan_status == "REJECTED_POSITION_PLAN":
            if evidence.position_plan_reason_unavailable:
                reasons.append(POSITION_SIZING_REASON_UNAVAILABLE)
            else:
                reasons.extend(explain_reason_code(c) for c in evidence.position_plan_reason_codes)
        rejection_reasons = tuple(reasons)
        risk_evidence = evidence.risk_evidence

    return BriefInstrumentEntry(
        instrument_symbol=decision.instrument_symbol,
        attention_level=attention_level,
        comparison_outcome=comparison.outcome,
        scan_decision=decision.scan_decision,
        trade_plan_decision=decision.trade_plan_decision,
        position_plan_status=evidence.position_plan_status if evidence else None,
        baseline_scan_decision=comparison.baseline_scan_decision,
        baseline_trade_plan_decision=comparison.baseline_trade_plan_decision,
        rejection_reasons=rejection_reasons,
        risk_evidence=risk_evidence,
    )


def _build_dropped_entry(comparison: SessionComparisonEntry) -> BriefInstrumentEntry:
    return BriefInstrumentEntry(
        instrument_symbol=comparison.instrument_symbol,
        attention_level=AttentionLevel.DROPPED,
        comparison_outcome=SessionComparisonOutcome.DROPPED,
        scan_decision=None,
        trade_plan_decision=None,
        position_plan_status=None,
        baseline_scan_decision=comparison.baseline_scan_decision,
        baseline_trade_plan_decision=comparison.baseline_trade_plan_decision,
        rejection_reasons=(),
        risk_evidence=None,
    )


def _sort_key(entry: BriefInstrumentEntry) -> tuple[int, str]:
    return (_ATTENTION_PRIORITY[entry.attention_level], entry.instrument_symbol)


def build_instrument_entries(
    *,
    target_decisions: tuple[ResearchDecisionEntry, ...],
    comparison_entries: tuple[SessionComparisonEntry, ...],
    evidence_by_governance_id: Mapping[str, FetchedInstrumentEvidence],
) -> tuple[BriefInstrumentEntry, ...]:
    """Pure composition: combines the current session's own decisions,
    M071's own `compare_session_decisions` output, and pre-fetched
    M057/M059/M060 evidence into one attention-sorted entry list. No
    new evaluation, ranking, risk, or sizing math."""
    comparison_by_symbol = {c.instrument_symbol: c for c in comparison_entries}
    entries = [
        _classify_and_build_entry(
            decision=decision,
            comparison_by_symbol=comparison_by_symbol,
            evidence_by_governance_id=evidence_by_governance_id,
        )
        for decision in target_decisions
    ]
    entries.extend(
        _build_dropped_entry(c)
        for c in comparison_entries
        if c.outcome is SessionComparisonOutcome.DROPPED
    )
    return tuple(sorted(entries, key=_sort_key))


@dataclass(frozen=True, slots=True)
class DailyResearchBrief:
    """The single, authoritative, composed brief model. Both the
    human-readable and JSON renderers consume this same structure, so
    they can never semantically diverge."""

    session_governance_id: str
    session_runtime_id: str
    as_of: datetime
    requested_universe: tuple[str, ...]
    completion_status: str
    session_warnings: tuple[str, ...]

    baseline_session_governance_id: str | None
    baseline_as_of: datetime | None
    baseline_note: str | None

    entries: tuple[BriefInstrumentEntry, ...]

    data_source: str
    dataset_sha256: str | None

    backtest_run_governance_id: str | None
    backtest_evaluated_opportunity_count: int | None
    backtest_executed_trade_count: int | None
    backtest_note: str | None

    limitations: tuple[str, ...]

    campaign_governance_id: str
    run_governance_id: str
    evidence_package_governance_id: str
    scan_governance_id: str | None
    stage_manifest_summary: tuple[str, ...]

    historical_portfolio_evidence: tuple[HistoricalPortfolioEvidence, ...] = ()

    def __post_init__(self) -> None:
        if not self.session_governance_id.strip():
            raise ValueError("session_governance_id must be non-empty")
        if not self.session_runtime_id.strip():
            raise ValueError("session_runtime_id must be non-empty")
        if self.as_of.tzinfo is None:
            raise ValueError("as_of must be timezone-aware")
        if self.baseline_as_of is not None and self.baseline_as_of.tzinfo is None:
            raise ValueError("baseline_as_of must be timezone-aware when present")
        if not self.requested_universe:
            raise ValueError("requested_universe must contain at least 1 instrument")
        sort_keys = [_sort_key(e) for e in self.entries]
        if sort_keys != sorted(sort_keys):
            raise ValueError("entries must be sorted by attention priority, then symbol")


def build_daily_research_brief(
    *,
    session: ResearchSessionSummary,
    session_status: str,
    session_warnings: tuple[str, ...],
    target_decisions: tuple[ResearchDecisionEntry, ...],
    comparison_entries: tuple[SessionComparisonEntry, ...],
    evidence_by_governance_id: Mapping[str, FetchedInstrumentEvidence],
    baseline_session_governance_id: str | None,
    baseline_as_of: datetime | None,
    baseline_note: str | None,
    data_source: str,
    dataset_sha256: str | None,
    backtest_run_governance_id: str | None,
    backtest_evaluated_opportunity_count: int | None,
    backtest_executed_trade_count: int | None,
    backtest_note: str | None,
    limitations: tuple[str, ...],
    campaign_governance_id: str,
    run_governance_id: str,
    evidence_package_governance_id: str,
    scan_governance_id: str | None,
    stage_manifest_summary: tuple[str, ...],
    historical_portfolio_evidence: tuple[HistoricalPortfolioEvidence, ...] = (),
) -> DailyResearchBrief:
    """Compose the authoritative brief model. Pure: every argument is
    already-fetched/already-computed data; this function performs no
    I/O and no new evaluation/ranking/risk/sizing/backtest math."""
    entries = build_instrument_entries(
        target_decisions=target_decisions,
        comparison_entries=comparison_entries,
        evidence_by_governance_id=evidence_by_governance_id,
    )
    return DailyResearchBrief(
        session_governance_id=str(session.identity.governance_id),
        session_runtime_id=str(session.identity.runtime_id),
        as_of=session.as_of,
        requested_universe=session.requested_universe,
        completion_status=session_status,
        session_warnings=session_warnings,
        baseline_session_governance_id=baseline_session_governance_id,
        baseline_as_of=baseline_as_of,
        baseline_note=baseline_note,
        entries=entries,
        data_source=data_source,
        dataset_sha256=dataset_sha256,
        backtest_run_governance_id=backtest_run_governance_id,
        backtest_evaluated_opportunity_count=backtest_evaluated_opportunity_count,
        backtest_executed_trade_count=backtest_executed_trade_count,
        backtest_note=backtest_note,
        limitations=limitations,
        campaign_governance_id=campaign_governance_id,
        run_governance_id=run_governance_id,
        evidence_package_governance_id=evidence_package_governance_id,
        scan_governance_id=scan_governance_id,
        stage_manifest_summary=stage_manifest_summary,
        historical_portfolio_evidence=historical_portfolio_evidence,
    )
