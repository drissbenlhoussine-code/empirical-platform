"""Pure, offline unit tests for MILESTONE-071's session-continuity
domain model: `ResearchSessionSummary`, `SessionComparisonEntry`, and
the pure `compare_session_decisions` diff function.

No network, no PostgreSQL anywhere in this file.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from empirical_platform.decision_candidate.research_session import (
    ResearchDecisionEntry,
    ResearchSessionStatus,
    ResearchSessionSummary,
    SessionComparisonEntry,
    SessionComparisonOutcome,
    StageName,
    compare_session_decisions,
)
from empirical_platform.identifiers.pairs import DomainIdentity
from empirical_platform.identifiers.types import CampaignId, ResearchSessionId
from empirical_platform.shared.identifiers import RuntimeIdentifier

_T0 = datetime(2026, 1, 1, tzinfo=UTC)


def _identity() -> DomainIdentity[ResearchSessionId]:
    return DomainIdentity(
        governance_id=ResearchSessionId("RESEARCH-0001"),
        runtime_id=RuntimeIdentifier("00000000-0000-4000-8000-000000000001"),
    )


def _summary(**overrides: object) -> ResearchSessionSummary:
    defaults: dict[str, object] = dict(
        identity=_identity(),
        as_of=_T0,
        requested_universe=("AAPL",),
        status=ResearchSessionStatus.COMPLETED,
        created_at=_T0,
        completed_at=_T0,
        candidate_count=0,
        failed_stage=None,
    )
    defaults.update(overrides)
    return ResearchSessionSummary(**defaults)  # type: ignore[arg-type]


def _decision(
    symbol: str, scan_decision: str, trade_plan_decision: str | None = None
) -> ResearchDecisionEntry:
    return ResearchDecisionEntry(
        rank=None,
        instrument_symbol=symbol,
        decision_candidate_governance_id=f"DCAND-{symbol}",
        scan_decision=scan_decision,
        trade_plan_governance_id=None,
        trade_plan_decision=trade_plan_decision,
        position_plan_governance_id=None,
    )


# --------------------------------------------------------------------------
# ResearchSessionSummary validation
# --------------------------------------------------------------------------


def test_summary_builds_successfully() -> None:
    summary = _summary()
    assert summary.status is ResearchSessionStatus.COMPLETED


def test_summary_rejects_identity_of_wrong_type() -> None:
    with pytest.raises(TypeError, match="identity must be a DomainIdentity"):
        _summary(identity="not-a-domain-identity")


def test_summary_rejects_identity_with_wrong_governance_id_type() -> None:
    with pytest.raises(TypeError, match="identity governance_id must be a ResearchSessionId"):
        _summary(
            identity=DomainIdentity(
                governance_id=CampaignId("CAMP-0001"),
                runtime_id=RuntimeIdentifier("00000000-0000-4000-8000-000000000001"),
            )
        )


def test_summary_rejects_naive_as_of() -> None:
    with pytest.raises(ValueError, match="as_of must be timezone-aware"):
        _summary(as_of=datetime(2026, 1, 1))  # noqa: DTZ001


def test_summary_rejects_naive_created_at() -> None:
    with pytest.raises(ValueError, match="created_at must be timezone-aware"):
        _summary(created_at=datetime(2026, 1, 1))  # noqa: DTZ001


def test_summary_rejects_naive_completed_at() -> None:
    with pytest.raises(ValueError, match="completed_at must be timezone-aware"):
        _summary(completed_at=datetime(2026, 1, 1))  # noqa: DTZ001


def test_summary_accepts_none_completed_at() -> None:
    summary = _summary(
        completed_at=None,
        status=ResearchSessionStatus.FAILED,
        failed_stage=StageName.DATA_ACQUISITION,
    )
    assert summary.completed_at is None


def test_summary_rejects_empty_universe() -> None:
    with pytest.raises(ValueError, match="requested_universe must contain at least 1"):
        _summary(requested_universe=())


def test_summary_rejects_negative_candidate_count() -> None:
    with pytest.raises(ValueError, match="candidate_count must be non-negative"):
        _summary(candidate_count=-1)


def test_summary_failed_requires_failed_stage() -> None:
    with pytest.raises(ValueError, match="a FAILED summary must carry failed_stage"):
        _summary(status=ResearchSessionStatus.FAILED, failed_stage=None)


def test_summary_completed_forbids_failed_stage() -> None:
    with pytest.raises(ValueError, match="a COMPLETED summary must carry no failed_stage"):
        _summary(status=ResearchSessionStatus.COMPLETED, failed_stage=StageName.DATA_ACQUISITION)


def test_summary_failed_with_failed_stage_builds_successfully() -> None:
    summary = _summary(
        status=ResearchSessionStatus.FAILED,
        failed_stage=StageName.DATA_ACQUISITION,
        completed_at=None,
    )
    assert summary.failed_stage is StageName.DATA_ACQUISITION


# --------------------------------------------------------------------------
# SessionComparisonEntry validation
# --------------------------------------------------------------------------


def test_comparison_entry_rejects_empty_instrument_symbol() -> None:
    with pytest.raises(ValueError, match="instrument_symbol must be non-empty"):
        SessionComparisonEntry(
            instrument_symbol="",
            outcome=SessionComparisonOutcome.NEW,
            target_scan_decision="NO_TRADE",
            target_trade_plan_decision=None,
            baseline_scan_decision=None,
            baseline_trade_plan_decision=None,
        )


def test_comparison_entry_new_requires_target_scan_decision() -> None:
    with pytest.raises(ValueError, match="NEW entries must carry a target_scan_decision"):
        SessionComparisonEntry(
            instrument_symbol="AAPL",
            outcome=SessionComparisonOutcome.NEW,
            target_scan_decision=None,
            target_trade_plan_decision=None,
            baseline_scan_decision=None,
            baseline_trade_plan_decision=None,
        )


def test_comparison_entry_new_forbids_baseline_scan_decision() -> None:
    with pytest.raises(ValueError, match="NEW entries must carry no baseline_scan_decision"):
        SessionComparisonEntry(
            instrument_symbol="AAPL",
            outcome=SessionComparisonOutcome.NEW,
            target_scan_decision="NO_TRADE",
            target_trade_plan_decision=None,
            baseline_scan_decision="NO_TRADE",
            baseline_trade_plan_decision=None,
        )


def test_comparison_entry_dropped_requires_baseline_scan_decision() -> None:
    with pytest.raises(ValueError, match="DROPPED entries must carry a baseline_scan_decision"):
        SessionComparisonEntry(
            instrument_symbol="AAPL",
            outcome=SessionComparisonOutcome.DROPPED,
            target_scan_decision=None,
            target_trade_plan_decision=None,
            baseline_scan_decision=None,
            baseline_trade_plan_decision=None,
        )


def test_comparison_entry_dropped_forbids_target_scan_decision() -> None:
    with pytest.raises(ValueError, match="DROPPED entries must carry no target_scan_decision"):
        SessionComparisonEntry(
            instrument_symbol="AAPL",
            outcome=SessionComparisonOutcome.DROPPED,
            target_scan_decision="NO_TRADE",
            target_trade_plan_decision=None,
            baseline_scan_decision="NO_TRADE",
            baseline_trade_plan_decision=None,
        )


def test_comparison_entry_changed_requires_both_sides() -> None:
    with pytest.raises(ValueError, match="CHANGED/UNCHANGED entries must carry both"):
        SessionComparisonEntry(
            instrument_symbol="AAPL",
            outcome=SessionComparisonOutcome.CHANGED,
            target_scan_decision="LONG_CANDIDATE",
            target_trade_plan_decision=None,
            baseline_scan_decision=None,
            baseline_trade_plan_decision=None,
        )


def test_comparison_entry_unchanged_builds_successfully() -> None:
    entry = SessionComparisonEntry(
        instrument_symbol="AAPL",
        outcome=SessionComparisonOutcome.UNCHANGED,
        target_scan_decision="NO_TRADE",
        target_trade_plan_decision=None,
        baseline_scan_decision="NO_TRADE",
        baseline_trade_plan_decision=None,
    )
    assert entry.outcome is SessionComparisonOutcome.UNCHANGED


# --------------------------------------------------------------------------
# compare_session_decisions -- the pure day-over-day diff
# --------------------------------------------------------------------------


def test_compare_no_baseline_marks_everything_new() -> None:
    target = (_decision("AAPL", "NO_TRADE"), _decision("MSFT", "LONG_CANDIDATE"))
    entries = compare_session_decisions(target_decisions=target, baseline_decisions=None)
    assert len(entries) == 2
    assert all(e.outcome is SessionComparisonOutcome.NEW for e in entries)
    assert [e.instrument_symbol for e in entries] == ["AAPL", "MSFT"]


def test_compare_identical_decisions_are_unchanged() -> None:
    target = (_decision("AAPL", "NO_TRADE"),)
    baseline = (_decision("AAPL", "NO_TRADE"),)
    entries = compare_session_decisions(target_decisions=target, baseline_decisions=baseline)
    assert len(entries) == 1
    assert entries[0].outcome is SessionComparisonOutcome.UNCHANGED
    assert entries[0].target_scan_decision == "NO_TRADE"
    assert entries[0].baseline_scan_decision == "NO_TRADE"


def test_compare_different_scan_decision_is_changed() -> None:
    target = (_decision("AAPL", "LONG_CANDIDATE"),)
    baseline = (_decision("AAPL", "NO_TRADE"),)
    entries = compare_session_decisions(target_decisions=target, baseline_decisions=baseline)
    assert entries[0].outcome is SessionComparisonOutcome.CHANGED


def test_compare_different_trade_plan_decision_is_changed() -> None:
    target = (_decision("AAPL", "LONG_CANDIDATE", "APPROVED_PLAN"),)
    baseline = (_decision("AAPL", "LONG_CANDIDATE", "REJECTED_PLAN"),)
    entries = compare_session_decisions(target_decisions=target, baseline_decisions=baseline)
    assert entries[0].outcome is SessionComparisonOutcome.CHANGED


def test_compare_instrument_only_in_target_is_new() -> None:
    target = (_decision("AAPL", "NO_TRADE"), _decision("MSFT", "NO_TRADE"))
    baseline = (_decision("AAPL", "NO_TRADE"),)
    entries = compare_session_decisions(target_decisions=target, baseline_decisions=baseline)
    by_symbol = {e.instrument_symbol: e.outcome for e in entries}
    assert by_symbol["AAPL"] is SessionComparisonOutcome.UNCHANGED
    assert by_symbol["MSFT"] is SessionComparisonOutcome.NEW


def test_compare_instrument_only_in_baseline_is_dropped() -> None:
    target = (_decision("AAPL", "NO_TRADE"),)
    baseline = (_decision("AAPL", "NO_TRADE"), _decision("MSFT", "NO_TRADE"))
    entries = compare_session_decisions(target_decisions=target, baseline_decisions=baseline)
    by_symbol = {e.instrument_symbol: e.outcome for e in entries}
    assert by_symbol["AAPL"] is SessionComparisonOutcome.UNCHANGED
    assert by_symbol["MSFT"] is SessionComparisonOutcome.DROPPED


def test_compare_empty_target_and_baseline_produces_no_entries() -> None:
    entries = compare_session_decisions(target_decisions=(), baseline_decisions=())
    assert entries == ()


def test_compare_empty_target_with_populated_baseline_drops_everything() -> None:
    baseline = (_decision("AAPL", "NO_TRADE"), _decision("MSFT", "NO_TRADE"))
    entries = compare_session_decisions(target_decisions=(), baseline_decisions=baseline)
    assert len(entries) == 2
    assert all(e.outcome is SessionComparisonOutcome.DROPPED for e in entries)


def test_compare_results_are_sorted_by_instrument_symbol() -> None:
    target = (_decision("MSFT", "NO_TRADE"), _decision("AAPL", "NO_TRADE"))
    entries = compare_session_decisions(target_decisions=target, baseline_decisions=None)
    assert [e.instrument_symbol for e in entries] == ["AAPL", "MSFT"]


def test_compare_preserves_trade_plan_decision_on_new_entries() -> None:
    target = (_decision("AAPL", "LONG_CANDIDATE", "APPROVED_PLAN"),)
    entries = compare_session_decisions(target_decisions=target, baseline_decisions=None)
    assert entries[0].target_trade_plan_decision == "APPROVED_PLAN"
    assert entries[0].baseline_trade_plan_decision is None
