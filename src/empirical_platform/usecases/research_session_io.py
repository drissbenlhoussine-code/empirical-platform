"""Usecase-layer JSON serialization for MILESTONE-070 daily research
sessions -- the operator-facing final daily report.

The payload is explicitly sectioned into FACT (what genuinely happened
in this session), HISTORICAL_EVIDENCE (the M061 backtest's own
retrospective evidence -- never a claim about live candidates),
DIAGNOSTIC (the stage manifest and per-instrument decision trail, for
operator troubleshooting), and LIMITATION (the fixed claim-honesty
statements, always present, mission Phase 13)."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol, cast

from empirical_platform.decision_candidate.research_session import (
    RESEARCH_SESSION_CLAIM_HONESTY_LIMITATIONS,
    ResearchSessionSummary,
    SessionComparisonEntry,
)
from empirical_platform.usecases.compare_daily_research_sessions import SessionComparisonResult

__all__ = [
    "daily_research_session_comparison_payload",
    "daily_research_session_list_payload",
    "research_session_report_payload",
]


class _StageView(Protocol):
    stage_version: str | None
    started_at: datetime
    completed_at: datetime | None
    input_authority: str
    output_identity: str | None
    error_type: str | None
    error_message: str | None

    @property
    def stage_name(self) -> object: ...

    @property
    def status(self) -> object: ...


class _DecisionView(Protocol):
    rank: int | None
    instrument_symbol: str
    decision_candidate_governance_id: str
    scan_decision: str
    trade_plan_governance_id: str | None
    trade_plan_decision: str | None
    position_plan_governance_id: str | None


class _ValueEnumView(Protocol):
    value: str


class ResearchSessionReportPayloadView(Protocol):
    identity: object
    created_at: datetime
    as_of: datetime
    requested_universe: tuple[str, ...]
    data_source: str
    dataset_id: str | None
    dataset_version: str | None
    dataset_sha256: str | None
    strategy_id: str | None
    strategy_version: str | None
    ranking_model_id: str | None
    ranking_model_version: str | None
    risk_policy_id: str | None
    risk_policy_version: str | None
    sizing_policy_id: str | None
    sizing_policy_version: str | None
    campaign_governance_id: str
    run_governance_id: str
    evidence_package_governance_id: str
    scan_governance_id: str | None
    failed_stage: object | None
    failure_type: str | None
    failure_message: str | None
    completed_at: datetime | None
    stage_manifest: tuple[_StageView, ...]
    decisions: tuple[_DecisionView, ...]
    candidate_count: int
    accepted_trade_plan_count: int
    rejected_trade_plan_count: int
    position_plan_count: int
    backtest_run_governance_id: str | None
    backtest_evaluated_opportunity_count: int | None
    backtest_executed_trade_count: int | None
    limitations: tuple[str, ...]

    @property
    def status(self) -> object: ...


def _stage_payload(stage: _StageView) -> dict[str, object]:
    return {
        "stage_name": cast(_ValueEnumView, stage.stage_name).value,
        "stage_version": stage.stage_version,
        "started_at": stage.started_at.isoformat(),
        "completed_at": stage.completed_at.isoformat() if stage.completed_at else None,
        "status": cast(_ValueEnumView, stage.status).value,
        "input_authority": stage.input_authority,
        "output_identity": stage.output_identity,
        "error_type": stage.error_type,
        "error_message": stage.error_message,
    }


def _decision_payload(decision: _DecisionView) -> dict[str, object]:
    return {
        "rank": decision.rank,
        "instrument_symbol": decision.instrument_symbol,
        "decision_candidate_governance_id": decision.decision_candidate_governance_id,
        "scan_decision": decision.scan_decision,
        "trade_plan_governance_id": decision.trade_plan_governance_id,
        "trade_plan_decision": decision.trade_plan_decision,
        "position_plan_governance_id": decision.position_plan_governance_id,
    }


def research_session_report_payload(session: object) -> dict[str, object]:
    typed = cast(ResearchSessionReportPayloadView, session)
    identity = typed.identity
    is_completed = cast(_ValueEnumView, typed.status).value == "COMPLETED"

    fact = {
        "session_governance_id": str(identity.governance_id),  # type: ignore[attr-defined]
        "session_runtime_id": str(identity.runtime_id),  # type: ignore[attr-defined]
        "created_at": typed.created_at.isoformat(),
        "as_of": typed.as_of.isoformat(),
        "requested_universe": list(typed.requested_universe),
        "data_source": typed.data_source,
        "dataset_id": typed.dataset_id,
        "dataset_version": typed.dataset_version,
        "dataset_sha256": typed.dataset_sha256,
        "strategy_id": typed.strategy_id,
        "strategy_version": typed.strategy_version,
        "ranking_model_id": typed.ranking_model_id,
        "ranking_model_version": typed.ranking_model_version,
        "risk_policy_id": typed.risk_policy_id,
        "risk_policy_version": typed.risk_policy_version,
        "sizing_policy_id": typed.sizing_policy_id,
        "sizing_policy_version": typed.sizing_policy_version,
        "campaign_governance_id": typed.campaign_governance_id,
        "run_governance_id": typed.run_governance_id,
        "evidence_package_governance_id": typed.evidence_package_governance_id,
        "scan_governance_id": typed.scan_governance_id,
        "completion_status": cast(_ValueEnumView, typed.status).value,
        "completed_at": typed.completed_at.isoformat() if typed.completed_at else None,
        "candidate_count": typed.candidate_count,
        "accepted_trade_plan_count": typed.accepted_trade_plan_count,
        "rejected_trade_plan_count": typed.rejected_trade_plan_count,
        "position_plan_count": typed.position_plan_count,
        "decisions": [_decision_payload(d) for d in typed.decisions],
    }

    historical_evidence = {
        "backtest_run_governance_id": typed.backtest_run_governance_id,
        "backtest_evaluated_opportunity_count": typed.backtest_evaluated_opportunity_count,
        "backtest_executed_trade_count": typed.backtest_executed_trade_count,
        "note": (
            "Retrospective evidence over the same acquired historical window -- "
            "not a claim about the live candidates listed under FACT."
            if is_completed and typed.backtest_run_governance_id is not None
            else None
        ),
    }

    diagnostic = {
        "failed_stage": (
            cast(_ValueEnumView, typed.failed_stage).value
            if typed.failed_stage is not None
            else None
        ),
        "failure_type": typed.failure_type,
        "failure_message": typed.failure_message,
        "stage_manifest": [_stage_payload(s) for s in typed.stage_manifest],
    }

    return {
        "FACT": fact,
        "HISTORICAL_EVIDENCE": historical_evidence,
        "DIAGNOSTIC": diagnostic,
        "LIMITATION": list(typed.limitations),
    }


def _session_summary_payload(summary: ResearchSessionSummary) -> dict[str, object]:
    return {
        "session_governance_id": str(summary.identity.governance_id),
        "session_runtime_id": str(summary.identity.runtime_id),
        "as_of": summary.as_of.isoformat(),
        "requested_universe": list(summary.requested_universe),
        "completion_status": summary.status.value,
        "created_at": summary.created_at.isoformat(),
        "completed_at": summary.completed_at.isoformat() if summary.completed_at else None,
        "candidate_count": summary.candidate_count,
        "failed_stage": (summary.failed_stage.value if summary.failed_stage is not None else None),
    }


def daily_research_session_list_payload(
    summaries: tuple[ResearchSessionSummary, ...],
) -> dict[str, object]:
    """MILESTONE-071. Sectioned the same way as every other M070/M071
    daily-research payload: FACT only, since a session listing carries
    no historical-evidence or diagnostic content of its own."""
    return {"FACT": {"sessions": [_session_summary_payload(s) for s in summaries]}}


def _comparison_entry_payload(entry: SessionComparisonEntry) -> dict[str, object]:
    return {
        "instrument_symbol": entry.instrument_symbol,
        "outcome": entry.outcome.value,
        "target_scan_decision": entry.target_scan_decision,
        "target_trade_plan_decision": entry.target_trade_plan_decision,
        "baseline_scan_decision": entry.baseline_scan_decision,
        "baseline_trade_plan_decision": entry.baseline_trade_plan_decision,
    }


def daily_research_session_comparison_payload(
    result: SessionComparisonResult,
) -> dict[str, object]:
    """MILESTONE-071. Sectioned FACT (the target session's own identity)
    / CONTINUITY (the baseline session, or an explicit "no prior
    session" note, plus the per-instrument NEW/DROPPED/CHANGED/UNCHANGED
    diff) / LIMITATION (the same fixed claim-honesty tuple every M070/
    M071 payload carries -- a day-over-day comparison is still research
    evidence, never a trading instruction)."""
    target = result.target
    baseline = result.baseline

    fact = {
        "session_governance_id": str(target.identity.governance_id),
        "session_runtime_id": str(target.identity.runtime_id),
        "as_of": target.as_of.isoformat(),
        "requested_universe": list(target.requested_universe),
        "completion_status": target.status.value,
    }

    continuity: dict[str, object] = {
        "baseline_session_governance_id": (
            str(baseline.identity.governance_id) if baseline is not None else None
        ),
        "baseline_session_runtime_id": (
            str(baseline.identity.runtime_id) if baseline is not None else None
        ),
        "baseline_as_of": baseline.as_of.isoformat() if baseline is not None else None,
        "baseline_completion_status": (baseline.status.value if baseline is not None else None),
        "note": (
            None
            if baseline is not None
            else "no prior session found for this universe -- this is the first session"
        ),
        "new": [_comparison_entry_payload(e) for e in result.entries if e.outcome.value == "NEW"],
        "dropped": [
            _comparison_entry_payload(e) for e in result.entries if e.outcome.value == "DROPPED"
        ],
        "changed": [
            _comparison_entry_payload(e) for e in result.entries if e.outcome.value == "CHANGED"
        ],
        "unchanged": [
            _comparison_entry_payload(e) for e in result.entries if e.outcome.value == "UNCHANGED"
        ],
    }

    return {
        "FACT": fact,
        "CONTINUITY": continuity,
        "LIMITATION": list(RESEARCH_SESSION_CLAIM_HONESTY_LIMITATIONS),
    }
