"""Pure, offline unit tests for MILESTONE-072's domain-level brief
composition: `classify_attention_level`, `explain_reason_code`,
`BriefInstrumentEntry`/`DailyResearchBrief` validation, and
`build_instrument_entries`/`build_daily_research_brief`.

No I/O, no PostgreSQL, no repository fakes anywhere in this file -- the
usecase-layer fetch/compose orchestration is exercised separately in
tests/unit/test_usecases_daily_research_brief.py.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from empirical_platform.decision_candidate.daily_research_brief import (
    POSITION_SIZING_REASON_UNAVAILABLE,
    AttentionLevel,
    BriefInstrumentEntry,
    BriefRiskEvidence,
    DailyResearchBrief,
    FetchedInstrumentEvidence,
    build_daily_research_brief,
    build_instrument_entries,
    classify_attention_level,
    explain_reason_code,
)
from empirical_platform.decision_candidate.research_session import (
    ResearchDecisionEntry,
    ResearchSessionStatus,
    ResearchSessionSummary,
    SessionComparisonEntry,
    SessionComparisonOutcome,
    StageName,
)
from empirical_platform.identifiers.pairs import DomainIdentity
from empirical_platform.identifiers.types import ResearchSessionId
from empirical_platform.shared.identifiers import RuntimeIdentifier

_T0 = datetime(2026, 1, 10, tzinfo=UTC)


def _identity() -> DomainIdentity[ResearchSessionId]:
    return DomainIdentity(
        governance_id=ResearchSessionId("RESEARCH-1234"),
        runtime_id=RuntimeIdentifier("00000000-0000-4000-8000-000000000001"),
    )


def _summary(
    *, status: ResearchSessionStatus = ResearchSessionStatus.COMPLETED
) -> ResearchSessionSummary:
    return ResearchSessionSummary(
        identity=_identity(),
        as_of=_T0,
        requested_universe=("AAPL", "MSFT"),
        status=status,
        created_at=_T0,
        completed_at=_T0 if status is ResearchSessionStatus.COMPLETED else None,
        candidate_count=2,
        failed_stage=(
            None if status is ResearchSessionStatus.COMPLETED else StageName.CANDIDATE_SCAN
        ),
    )


def _decision(
    symbol: str,
    *,
    scan_decision: str,
    trade_plan_decision: str | None = None,
    position_plan_id: str | None = None,
) -> ResearchDecisionEntry:
    return ResearchDecisionEntry(
        rank=1,
        instrument_symbol=symbol,
        decision_candidate_governance_id=f"DCAND-{symbol}",
        scan_decision=scan_decision,
        trade_plan_governance_id=(f"PLAN-{symbol}" if trade_plan_decision is not None else None),
        trade_plan_decision=trade_plan_decision,
        position_plan_governance_id=position_plan_id,
    )


def _comparison(
    symbol: str, outcome: SessionComparisonOutcome, **overrides: object
) -> SessionComparisonEntry:
    fields: dict[str, object] = {
        "instrument_symbol": symbol,
        "outcome": outcome,
        "target_scan_decision": "NO_TRADE",
        "target_trade_plan_decision": None,
        "baseline_scan_decision": None,
        "baseline_trade_plan_decision": None,
    }
    fields.update(overrides)
    return SessionComparisonEntry(**fields)  # type: ignore[arg-type]


def _risk_evidence() -> BriefRiskEvidence:
    return BriefRiskEvidence(
        entry_price="100",
        stop_price="95",
        target_price="115",
        reward_risk_ratio="3",
        quantity=10,
        position_notional="1000",
        actual_risk="50",
    )


# --------------------------------------------------------------------------
# classify_attention_level
# --------------------------------------------------------------------------


def test_dropped_outranks_everything() -> None:
    assert (
        classify_attention_level(
            comparison_outcome=SessionComparisonOutcome.DROPPED,
            scan_decision=None,
            trade_plan_decision=None,
            position_plan_status=None,
        )
        is AttentionLevel.DROPPED
    )


def test_full_approval_is_action_candidate() -> None:
    assert (
        classify_attention_level(
            comparison_outcome=SessionComparisonOutcome.UNCHANGED,
            scan_decision="LONG_CANDIDATE",
            trade_plan_decision="APPROVED_PLAN",
            position_plan_status="APPROVED_POSITION_PLAN",
        )
        is AttentionLevel.ACTION_CANDIDATE
    )


def test_changed_without_full_approval_is_review() -> None:
    assert (
        classify_attention_level(
            comparison_outcome=SessionComparisonOutcome.CHANGED,
            scan_decision="NO_TRADE",
            trade_plan_decision=None,
            position_plan_status=None,
        )
        is AttentionLevel.REVIEW
    )


def test_long_candidate_with_rejected_plan_is_review_even_when_unchanged() -> None:
    assert (
        classify_attention_level(
            comparison_outcome=SessionComparisonOutcome.UNCHANGED,
            scan_decision="LONG_CANDIDATE",
            trade_plan_decision="REJECTED_PLAN",
            position_plan_status=None,
        )
        is AttentionLevel.REVIEW
    )


def test_steady_no_trade_is_routine() -> None:
    assert (
        classify_attention_level(
            comparison_outcome=SessionComparisonOutcome.UNCHANGED,
            scan_decision="NO_TRADE",
            trade_plan_decision=None,
            position_plan_status=None,
        )
        is AttentionLevel.ROUTINE
    )


def test_new_no_trade_is_routine_not_review() -> None:
    assert (
        classify_attention_level(
            comparison_outcome=SessionComparisonOutcome.NEW,
            scan_decision="NO_TRADE",
            trade_plan_decision=None,
            position_plan_status=None,
        )
        is AttentionLevel.ROUTINE
    )


# --------------------------------------------------------------------------
# explain_reason_code
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "code",
    [
        "PRICE_ABOVE_REFERENCE_HIGH",
        "PRICE_NOT_ABOVE_REFERENCE_HIGH",
        "VOLUME_ABOVE_REFERENCE_AVERAGE",
        "VOLUME_NOT_ABOVE_REFERENCE_AVERAGE",
        "SOURCE_NOT_LONG_CANDIDATE",
        "PROVENANCE_MISMATCH",
        "INVALID_STOP_GEOMETRY",
        "INVALID_TARGET_GEOMETRY",
        "REWARD_RISK_BELOW_MINIMUM",
        "SOURCE_PLAN_NOT_APPROVED",
        "INVALID_EQUITY",
        "INVALID_RISK_BUDGET",
        "POLICY_VIOLATION",
        "ZERO_POSITION_SIZE",
        "CAPITAL_LIMIT_EXCEEDED",
    ],
)
def test_every_frozen_reason_code_has_a_plain_text_explanation(code: str) -> None:
    explanation = explain_reason_code(code)
    assert explanation != code
    assert explanation.islower() or not explanation.isupper()


def test_unknown_reason_code_falls_back_to_the_code_itself() -> None:
    assert explain_reason_code("SOME_FUTURE_CODE") == "SOME_FUTURE_CODE"


# --------------------------------------------------------------------------
# BriefRiskEvidence / BriefInstrumentEntry validation
# --------------------------------------------------------------------------


def test_risk_evidence_rejects_negative_quantity() -> None:
    with pytest.raises(ValueError, match="quantity must not be negative"):
        BriefRiskEvidence(
            entry_price="1",
            stop_price="1",
            target_price="1",
            reward_risk_ratio="1",
            quantity=-1,
            position_notional="1",
            actual_risk="1",
        )


def test_dropped_entry_rejects_current_session_decision() -> None:
    with pytest.raises(ValueError, match="DROPPED entry must carry no current-session decision"):
        BriefInstrumentEntry(
            instrument_symbol="AAPL",
            attention_level=AttentionLevel.DROPPED,
            comparison_outcome=SessionComparisonOutcome.DROPPED,
            scan_decision="LONG_CANDIDATE",
            trade_plan_decision=None,
            position_plan_status=None,
            baseline_scan_decision="LONG_CANDIDATE",
            baseline_trade_plan_decision=None,
            rejection_reasons=(),
            risk_evidence=None,
        )


def test_dropped_entry_rejects_risk_evidence() -> None:
    with pytest.raises(ValueError, match="DROPPED entry must carry no risk_evidence"):
        BriefInstrumentEntry(
            instrument_symbol="AAPL",
            attention_level=AttentionLevel.DROPPED,
            comparison_outcome=SessionComparisonOutcome.DROPPED,
            scan_decision=None,
            trade_plan_decision=None,
            position_plan_status=None,
            baseline_scan_decision="LONG_CANDIDATE",
            baseline_trade_plan_decision=None,
            rejection_reasons=(),
            risk_evidence=_risk_evidence(),
        )


def test_non_dropped_entry_requires_scan_decision() -> None:
    with pytest.raises(ValueError, match="non-DROPPED entry must carry a scan_decision"):
        BriefInstrumentEntry(
            instrument_symbol="AAPL",
            attention_level=AttentionLevel.ROUTINE,
            comparison_outcome=SessionComparisonOutcome.NEW,
            scan_decision=None,
            trade_plan_decision=None,
            position_plan_status=None,
            baseline_scan_decision=None,
            baseline_trade_plan_decision=None,
            rejection_reasons=(),
            risk_evidence=None,
        )


# --------------------------------------------------------------------------
# build_instrument_entries: sorting, tie-break, DROPPED synthesis
# --------------------------------------------------------------------------


def test_entries_are_sorted_by_attention_priority_then_symbol() -> None:
    decisions = (
        _decision("ZZZZ", scan_decision="LONG_CANDIDATE", trade_plan_decision="APPROVED_PLAN"),
        _decision("AAAA", scan_decision="NO_TRADE"),
        _decision("MMMM", scan_decision="LONG_CANDIDATE", trade_plan_decision="REJECTED_PLAN"),
    )
    comparisons = (
        _comparison(
            "ZZZZ",
            SessionComparisonOutcome.NEW,
            target_scan_decision="LONG_CANDIDATE",
            target_trade_plan_decision="APPROVED_PLAN",
        ),
        _comparison(
            "AAAA",
            SessionComparisonOutcome.UNCHANGED,
            target_scan_decision="NO_TRADE",
            baseline_scan_decision="NO_TRADE",
        ),
        _comparison(
            "MMMM",
            SessionComparisonOutcome.NEW,
            target_scan_decision="LONG_CANDIDATE",
            target_trade_plan_decision="REJECTED_PLAN",
        ),
    )
    evidence = {
        "DCAND-ZZZZ": FetchedInstrumentEvidence(
            evaluation_reason_codes=(),
            trade_plan_reason_codes=(),
            position_plan_status="APPROVED_POSITION_PLAN",
            position_plan_reason_codes=(),
            position_plan_reason_unavailable=False,
            risk_evidence=_risk_evidence(),
        ),
    }

    entries = build_instrument_entries(
        target_decisions=decisions,
        comparison_entries=comparisons,
        evidence_by_governance_id=evidence,
    )

    assert [e.instrument_symbol for e in entries] == ["ZZZZ", "MMMM", "AAAA"]
    assert entries[0].attention_level is AttentionLevel.ACTION_CANDIDATE
    assert entries[1].attention_level is AttentionLevel.REVIEW
    assert entries[2].attention_level is AttentionLevel.ROUTINE


def test_dropped_instrument_synthesized_from_comparison_only() -> None:
    comparisons = (
        _comparison(
            "NVDA",
            SessionComparisonOutcome.DROPPED,
            target_scan_decision=None,
            baseline_scan_decision="LONG_CANDIDATE",
            baseline_trade_plan_decision="APPROVED_PLAN",
        ),
    )

    entries = build_instrument_entries(
        target_decisions=(), comparison_entries=comparisons, evidence_by_governance_id={}
    )

    assert len(entries) == 1
    entry = entries[0]
    assert entry.attention_level is AttentionLevel.DROPPED
    assert entry.scan_decision is None
    assert entry.baseline_scan_decision == "LONG_CANDIDATE"
    assert entry.risk_evidence is None


def test_rejection_reasons_only_surfaced_for_the_actual_rejection() -> None:
    """A LONG_CANDIDATE's own price/volume reason codes explain why it
    qualified, not why it was rejected -- they must not leak into
    rejection_reasons."""
    decisions = (
        _decision("AAPL", scan_decision="LONG_CANDIDATE", trade_plan_decision="APPROVED_PLAN"),
    )
    comparisons = (
        _comparison(
            "AAPL",
            SessionComparisonOutcome.NEW,
            target_scan_decision="LONG_CANDIDATE",
            target_trade_plan_decision="APPROVED_PLAN",
        ),
    )
    evidence = {
        "DCAND-AAPL": FetchedInstrumentEvidence(
            evaluation_reason_codes=(
                "PRICE_ABOVE_REFERENCE_HIGH",
                "VOLUME_ABOVE_REFERENCE_AVERAGE",
            ),
            trade_plan_reason_codes=(),
            position_plan_status="APPROVED_POSITION_PLAN",
            position_plan_reason_codes=(),
            position_plan_reason_unavailable=False,
            risk_evidence=_risk_evidence(),
        ),
    }

    entries = build_instrument_entries(
        target_decisions=decisions,
        comparison_entries=comparisons,
        evidence_by_governance_id=evidence,
    )

    assert entries[0].rejection_reasons == ()
    assert entries[0].risk_evidence is not None


def test_unavailable_position_sizing_reason_is_surfaced_honestly() -> None:
    decisions = (
        _decision("AAPL", scan_decision="LONG_CANDIDATE", trade_plan_decision="APPROVED_PLAN"),
    )
    comparisons = (
        _comparison(
            "AAPL",
            SessionComparisonOutcome.NEW,
            target_scan_decision="LONG_CANDIDATE",
            target_trade_plan_decision="APPROVED_PLAN",
        ),
    )
    evidence = {
        "DCAND-AAPL": FetchedInstrumentEvidence(
            evaluation_reason_codes=(),
            trade_plan_reason_codes=(),
            position_plan_status="REJECTED_POSITION_PLAN",
            position_plan_reason_codes=(),
            position_plan_reason_unavailable=True,
            risk_evidence=None,
        ),
    }

    entries = build_instrument_entries(
        target_decisions=decisions,
        comparison_entries=comparisons,
        evidence_by_governance_id=evidence,
    )

    assert entries[0].rejection_reasons == (POSITION_SIZING_REASON_UNAVAILABLE,)
    assert entries[0].risk_evidence is None


# --------------------------------------------------------------------------
# DailyResearchBrief validation
# --------------------------------------------------------------------------


def test_brief_rejects_naive_as_of() -> None:
    with pytest.raises(ValueError, match="as_of must be timezone-aware"):
        DailyResearchBrief(
            session_governance_id="RESEARCH-1234",
            session_runtime_id="rt",
            as_of=datetime(2026, 1, 1),  # noqa: DTZ001
            requested_universe=("AAPL",),
            completion_status="COMPLETED",
            session_warnings=(),
            baseline_session_governance_id=None,
            baseline_as_of=None,
            baseline_note=None,
            entries=(),
            data_source="FAKE",
            dataset_sha256=None,
            backtest_run_governance_id=None,
            backtest_evaluated_opportunity_count=None,
            backtest_executed_trade_count=None,
            backtest_note=None,
            limitations=(),
            campaign_governance_id="CAMP-1",
            run_governance_id="RUN-1",
            evidence_package_governance_id="EVID-1",
            scan_governance_id=None,
            stage_manifest_summary=(),
        )


def test_brief_rejects_empty_universe() -> None:
    with pytest.raises(ValueError, match="requested_universe must contain at least 1"):
        DailyResearchBrief(
            session_governance_id="RESEARCH-1234",
            session_runtime_id="rt",
            as_of=_T0,
            requested_universe=(),
            completion_status="COMPLETED",
            session_warnings=(),
            baseline_session_governance_id=None,
            baseline_as_of=None,
            baseline_note=None,
            entries=(),
            data_source="FAKE",
            dataset_sha256=None,
            backtest_run_governance_id=None,
            backtest_evaluated_opportunity_count=None,
            backtest_executed_trade_count=None,
            backtest_note=None,
            limitations=(),
            campaign_governance_id="CAMP-1",
            run_governance_id="RUN-1",
            evidence_package_governance_id="EVID-1",
            scan_governance_id=None,
            stage_manifest_summary=(),
        )


# --------------------------------------------------------------------------
# build_daily_research_brief end-to-end composition (pure)
# --------------------------------------------------------------------------


def test_build_daily_research_brief_composes_session_and_entries() -> None:
    decisions = (_decision("AAPL", scan_decision="NO_TRADE"),)
    comparisons = (
        _comparison("AAPL", SessionComparisonOutcome.NEW, target_scan_decision="NO_TRADE"),
    )
    evidence = {
        "DCAND-AAPL": FetchedInstrumentEvidence(
            evaluation_reason_codes=("PRICE_NOT_ABOVE_REFERENCE_HIGH",),
            trade_plan_reason_codes=(),
            position_plan_status=None,
            position_plan_reason_codes=(),
            position_plan_reason_unavailable=False,
            risk_evidence=None,
        ),
    }

    brief = build_daily_research_brief(
        session=_summary(),
        session_status="COMPLETED",
        session_warnings=(),
        target_decisions=decisions,
        comparison_entries=comparisons,
        evidence_by_governance_id=evidence,
        baseline_session_governance_id=None,
        baseline_as_of=None,
        baseline_note="no prior session found for this universe -- this is the first session",
        data_source="FakeMarketDataSource",
        dataset_sha256="abc",
        backtest_run_governance_id=None,
        backtest_evaluated_opportunity_count=None,
        backtest_executed_trade_count=None,
        backtest_note=None,
        limitations=("Research output is not a trading instruction.",),
        campaign_governance_id="CAMP-1",
        run_governance_id="RUN-1",
        evidence_package_governance_id="EVID-1",
        scan_governance_id="SCAN-1",
        stage_manifest_summary=("CANDIDATE_SCAN: COMPLETED",),
    )

    assert brief.session_governance_id == "RESEARCH-1234"
    assert len(brief.entries) == 1
    assert brief.entries[0].rejection_reasons == ("closing price did not clear the reference high",)
    assert brief.baseline_note is not None
