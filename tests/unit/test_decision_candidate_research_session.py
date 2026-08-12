"""Pure, offline unit tests for MILESTONE-070's `ResearchSession` domain
model and its own as-of temporal firewall helpers
(`derive_shared_evaluation_timestamp`/`derive_observation_window`).

No network, no PostgreSQL anywhere in this file.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from empirical_platform.decision_candidate.historical_backtest import HistoricalInstrumentSeries
from empirical_platform.decision_candidate.market_data import Bar, BarInterval, Instrument
from empirical_platform.decision_candidate.research_session import (
    RESEARCH_SESSION_CLAIM_HONESTY_LIMITATIONS,
    ResearchDecisionEntry,
    ResearchSession,
    ResearchSessionStatus,
    StageName,
    StageRecord,
    StageStatus,
    derive_observation_window,
    derive_shared_evaluation_timestamp,
)
from empirical_platform.identifiers.pairs import DomainIdentity
from empirical_platform.identifiers.types import ResearchSessionId
from empirical_platform.shared.identifiers import RuntimeIdentifier

_T0 = datetime(2026, 1, 1, tzinfo=UTC)


def _bar(symbol: str, minute_offset: int, close: str = "100") -> Bar:
    price = Decimal(close)
    return Bar(
        instrument=Instrument(symbol),
        interval=BarInterval.ONE_DAY,
        timestamp=_T0 + timedelta(days=minute_offset),
        open=price,
        high=price,
        low=price,
        close=price,
        volume=1000,
    )


def _series(symbol: str, n: int, skip: int | None = None) -> HistoricalInstrumentSeries:
    bars = tuple(_bar(symbol, i) for i in range(n) if i != skip)
    return HistoricalInstrumentSeries(instrument=Instrument(symbol), bars=bars)


def _identity() -> DomainIdentity[ResearchSessionId]:
    return DomainIdentity(
        governance_id=ResearchSessionId("RESEARCH-0001"),
        runtime_id=RuntimeIdentifier("00000000-0000-4000-8000-000000000001"),
    )


def _stage(
    name: StageName, status: StageStatus, *, started_at: datetime = _T0, failed: bool = False
) -> StageRecord:
    return StageRecord(
        stage_name=name,
        stage_version=None,
        started_at=started_at,
        completed_at=started_at if status is not StageStatus.PENDING else None,
        status=status,
        input_authority="test",
        output_identity=None if failed else "OUT-0001",
        error_type="ValueError" if failed else None,
        error_message="boom" if failed else None,
    )


def _completed_session(**overrides: object) -> ResearchSession:
    defaults: dict[str, object] = dict(
        identity=_identity(),
        created_at=_T0,
        as_of=_T0,
        requested_universe=("AAPL",),
        data_source="FAKE_OFFLINE_FIXTURE",
        dataset_id="DATASET-0001",
        dataset_version="1",
        dataset_sha256="0" * 64,
        strategy_id="STRAT",
        strategy_version="1",
        ranking_model_id="RANK",
        ranking_model_version="1",
        risk_policy_id="RISK",
        risk_policy_version="1",
        sizing_policy_id="SIZE",
        sizing_policy_version="1",
        campaign_governance_id="CAMP-0001",
        run_governance_id="RUN-0001",
        evidence_package_governance_id="EVID-0001",
        scan_governance_id="SCAN-0001",
        status=ResearchSessionStatus.COMPLETED,
        failed_stage=None,
        failure_type=None,
        failure_message=None,
        completed_at=_T0,
        stage_manifest=(_stage(StageName.GOVERNANCE_SETUP, StageStatus.COMPLETED),),
        decisions=(),
        candidate_count=0,
        accepted_trade_plan_count=0,
        rejected_trade_plan_count=0,
        position_plan_count=0,
        backtest_run_governance_id="BTRUN-0001",
        backtest_evaluated_opportunity_count=0,
        backtest_executed_trade_count=0,
        limitations=RESEARCH_SESSION_CLAIM_HONESTY_LIMITATIONS,
    )
    defaults.update(overrides)
    return ResearchSession(**defaults)  # type: ignore[arg-type]


# --------------------------------------------------------------------------
# StageRecord validation
# --------------------------------------------------------------------------


def test_stage_record_completed_requires_completed_at() -> None:
    with pytest.raises(ValueError, match="COMPLETED stage must carry completed_at"):
        StageRecord(
            stage_name=StageName.DATA_ACQUISITION,
            stage_version=None,
            started_at=_T0,
            completed_at=None,
            status=StageStatus.COMPLETED,
            input_authority="x",
            output_identity="y",
            error_type=None,
            error_message=None,
        )


def test_stage_record_failed_requires_error_metadata() -> None:
    with pytest.raises(ValueError, match="FAILED stage must carry a non-empty error_type"):
        StageRecord(
            stage_name=StageName.DATA_ACQUISITION,
            stage_version=None,
            started_at=_T0,
            completed_at=_T0,
            status=StageStatus.FAILED,
            input_authority="x",
            output_identity=None,
            error_type=None,
            error_message=None,
        )


def test_stage_record_completed_forbids_error_metadata() -> None:
    with pytest.raises(ValueError, match="COMPLETED stage must carry no error metadata"):
        StageRecord(
            stage_name=StageName.DATA_ACQUISITION,
            stage_version=None,
            started_at=_T0,
            completed_at=_T0,
            status=StageStatus.COMPLETED,
            input_authority="x",
            output_identity="y",
            error_type="ValueError",
            error_message="boom",
        )


def test_stage_record_completed_at_before_started_at_rejected() -> None:
    with pytest.raises(ValueError, match="completed_at must not precede started_at"):
        StageRecord(
            stage_name=StageName.DATA_ACQUISITION,
            stage_version=None,
            started_at=_T0,
            completed_at=_T0 - timedelta(seconds=1),
            status=StageStatus.COMPLETED,
            input_authority="x",
            output_identity="y",
            error_type=None,
            error_message=None,
        )


def test_stage_record_rejects_naive_started_at() -> None:
    with pytest.raises(ValueError, match="started_at must be timezone-aware"):
        StageRecord(
            stage_name=StageName.DATA_ACQUISITION,
            stage_version=None,
            started_at=datetime(2026, 1, 1),  # noqa: DTZ001
            completed_at=None,
            status=StageStatus.PENDING,
            input_authority="x",
            output_identity=None,
            error_type=None,
            error_message=None,
        )


def test_stage_record_rejects_naive_completed_at() -> None:
    with pytest.raises(ValueError, match="completed_at must be timezone-aware"):
        StageRecord(
            stage_name=StageName.DATA_ACQUISITION,
            stage_version=None,
            started_at=_T0,
            completed_at=datetime(2026, 1, 1),  # noqa: DTZ001
            status=StageStatus.COMPLETED,
            input_authority="x",
            output_identity="y",
            error_type=None,
            error_message=None,
        )


def test_stage_record_rejects_empty_input_authority() -> None:
    with pytest.raises(ValueError, match="input_authority must be non-empty"):
        StageRecord(
            stage_name=StageName.DATA_ACQUISITION,
            stage_version=None,
            started_at=_T0,
            completed_at=None,
            status=StageStatus.PENDING,
            input_authority="   ",
            output_identity=None,
            error_type=None,
            error_message=None,
        )


def test_stage_record_failed_requires_non_empty_error_message() -> None:
    with pytest.raises(ValueError, match="FAILED stage must carry a non-empty error_message"):
        StageRecord(
            stage_name=StageName.DATA_ACQUISITION,
            stage_version=None,
            started_at=_T0,
            completed_at=_T0,
            status=StageStatus.FAILED,
            input_authority="x",
            output_identity=None,
            error_type="ValueError",
            error_message="   ",
        )


def test_stage_record_failed_requires_completed_at() -> None:
    with pytest.raises(ValueError, match="FAILED stage must carry completed_at"):
        StageRecord(
            stage_name=StageName.DATA_ACQUISITION,
            stage_version=None,
            started_at=_T0,
            completed_at=None,
            status=StageStatus.FAILED,
            input_authority="x",
            output_identity=None,
            error_type="ValueError",
            error_message="boom",
        )


def test_stage_record_pending_forbids_error_metadata() -> None:
    with pytest.raises(ValueError, match="PENDING/SKIPPED stage must carry no error metadata"):
        StageRecord(
            stage_name=StageName.DATA_ACQUISITION,
            stage_version=None,
            started_at=_T0,
            completed_at=None,
            status=StageStatus.PENDING,
            input_authority="x",
            output_identity=None,
            error_type="ValueError",
            error_message=None,
        )


def test_stage_record_pending_without_error_metadata_builds_successfully() -> None:
    stage = StageRecord(
        stage_name=StageName.DATA_ACQUISITION,
        stage_version=None,
        started_at=_T0,
        completed_at=None,
        status=StageStatus.PENDING,
        input_authority="x",
        output_identity=None,
        error_type=None,
        error_message=None,
    )
    assert stage.status is StageStatus.PENDING


def test_stage_record_running_status_carries_no_extra_validation() -> None:
    stage = StageRecord(
        stage_name=StageName.DATA_ACQUISITION,
        stage_version=None,
        started_at=_T0,
        completed_at=None,
        status=StageStatus.RUNNING,
        input_authority="x",
        output_identity=None,
        error_type=None,
        error_message=None,
    )
    assert stage.status is StageStatus.RUNNING


# --------------------------------------------------------------------------
# ResearchDecisionEntry validation
# --------------------------------------------------------------------------


def test_decision_entry_rejects_rank_below_one() -> None:
    with pytest.raises(ValueError, match="rank must be at least 1"):
        ResearchDecisionEntry(
            rank=0,
            instrument_symbol="AAPL",
            decision_candidate_governance_id="DCAND-0001",
            scan_decision="LONG_CANDIDATE",
            trade_plan_governance_id=None,
            trade_plan_decision=None,
            position_plan_governance_id=None,
        )


def test_decision_entry_rejects_empty_instrument_symbol() -> None:
    with pytest.raises(ValueError, match="instrument_symbol must be non-empty"):
        ResearchDecisionEntry(
            rank=None,
            instrument_symbol="",
            decision_candidate_governance_id="DCAND-0001",
            scan_decision="LONG_CANDIDATE",
            trade_plan_governance_id=None,
            trade_plan_decision=None,
            position_plan_governance_id=None,
        )


def test_decision_entry_rejects_empty_decision_candidate_governance_id() -> None:
    with pytest.raises(ValueError, match="decision_candidate_governance_id must be non-empty"):
        ResearchDecisionEntry(
            rank=None,
            instrument_symbol="AAPL",
            decision_candidate_governance_id="",
            scan_decision="LONG_CANDIDATE",
            trade_plan_governance_id=None,
            trade_plan_decision=None,
            position_plan_governance_id=None,
        )


def test_decision_entry_rejects_empty_scan_decision() -> None:
    with pytest.raises(ValueError, match="scan_decision must be non-empty"):
        ResearchDecisionEntry(
            rank=None,
            instrument_symbol="AAPL",
            decision_candidate_governance_id="DCAND-0001",
            scan_decision="",
            trade_plan_governance_id=None,
            trade_plan_decision=None,
            position_plan_governance_id=None,
        )


# --------------------------------------------------------------------------
# ResearchSession validation
# --------------------------------------------------------------------------


def test_completed_session_builds_successfully() -> None:
    session = _completed_session()
    assert session.is_completed
    assert session.status is ResearchSessionStatus.COMPLETED


def test_completed_session_rejects_failure_metadata() -> None:
    with pytest.raises(ValueError, match="COMPLETED session must carry no failure metadata"):
        _completed_session(failed_stage=StageName.DATA_ACQUISITION)


def test_completed_session_requires_completed_at() -> None:
    with pytest.raises(ValueError, match="COMPLETED session must carry completed_at"):
        _completed_session(completed_at=None)


def test_completed_session_rejects_failed_stage_in_manifest() -> None:
    with pytest.raises(ValueError, match="COMPLETED session must have no FAILED stage"):
        _completed_session(
            stage_manifest=(
                _stage(StageName.GOVERNANCE_SETUP, StageStatus.COMPLETED),
                _stage(StageName.DATA_ACQUISITION, StageStatus.FAILED, failed=True),
            )
        )


def test_failed_session_requires_failed_stage_and_message() -> None:
    with pytest.raises(ValueError, match="FAILED session must carry failed_stage"):
        _completed_session(
            status=ResearchSessionStatus.FAILED,
            stage_manifest=(_stage(StageName.DATA_ACQUISITION, StageStatus.FAILED, failed=True),),
        )


def test_failed_session_stage_manifest_must_record_failure() -> None:
    with pytest.raises(ValueError, match="own stage_manifest must record which stage failed"):
        _completed_session(
            status=ResearchSessionStatus.FAILED,
            failed_stage=StageName.DATA_ACQUISITION,
            failure_type="ValueError",
            failure_message="boom",
            stage_manifest=(_stage(StageName.GOVERNANCE_SETUP, StageStatus.COMPLETED),),
        )


def test_failed_session_with_consistent_metadata_builds_successfully() -> None:
    session = _completed_session(
        status=ResearchSessionStatus.FAILED,
        failed_stage=StageName.DATA_ACQUISITION,
        failure_type="ValueError",
        failure_message="boom",
        stage_manifest=(
            _stage(StageName.GOVERNANCE_SETUP, StageStatus.COMPLETED),
            _stage(StageName.DATA_ACQUISITION, StageStatus.FAILED, failed=True),
        ),
    )
    assert not session.is_completed
    assert session.status is ResearchSessionStatus.FAILED


def test_failed_session_rejects_empty_failure_type() -> None:
    with pytest.raises(ValueError, match="FAILED session must carry a non-empty failure_type"):
        _completed_session(
            status=ResearchSessionStatus.FAILED,
            failed_stage=StageName.DATA_ACQUISITION,
            failure_type="   ",
            failure_message="boom",
            stage_manifest=(
                _stage(StageName.GOVERNANCE_SETUP, StageStatus.COMPLETED),
                _stage(StageName.DATA_ACQUISITION, StageStatus.FAILED, failed=True),
            ),
        )


def test_failed_session_rejects_empty_failure_message() -> None:
    with pytest.raises(ValueError, match="FAILED session must carry a non-empty failure_message"):
        _completed_session(
            status=ResearchSessionStatus.FAILED,
            failed_stage=StageName.DATA_ACQUISITION,
            failure_type="ValueError",
            failure_message="   ",
            stage_manifest=(
                _stage(StageName.GOVERNANCE_SETUP, StageStatus.COMPLETED),
                _stage(StageName.DATA_ACQUISITION, StageStatus.FAILED, failed=True),
            ),
        )


def test_completed_session_rejects_failure_message_alone() -> None:
    with pytest.raises(ValueError, match="COMPLETED session must carry no failure_message"):
        _completed_session(failure_message="boom")


def test_session_rejects_non_terminal_status() -> None:
    with pytest.raises(ValueError, match="terminal status must be COMPLETED or FAILED"):
        _completed_session(status=ResearchSessionStatus.RUNNING_RESEARCH)


def test_session_rejects_identity_of_wrong_type() -> None:
    with pytest.raises(TypeError, match="identity must be a DomainIdentity"):
        _completed_session(identity="not-a-domain-identity")


def test_session_rejects_identity_with_wrong_governance_id_type() -> None:
    from empirical_platform.identifiers.types import CampaignId

    with pytest.raises(TypeError, match="identity governance_id must be a ResearchSessionId"):
        _completed_session(
            identity=DomainIdentity(
                governance_id=CampaignId("CAMP-0001"),
                runtime_id=RuntimeIdentifier("00000000-0000-4000-8000-000000000001"),
            )
        )


def test_session_rejects_naive_created_at() -> None:
    with pytest.raises(ValueError, match="created_at must be timezone-aware"):
        _completed_session(created_at=datetime(2026, 1, 1))  # noqa: DTZ001


def test_session_rejects_naive_as_of() -> None:
    with pytest.raises(ValueError, match="as_of must be timezone-aware"):
        _completed_session(as_of=datetime(2026, 1, 1))  # noqa: DTZ001


def test_session_rejects_empty_data_source() -> None:
    with pytest.raises(ValueError, match="data_source must be non-empty"):
        _completed_session(data_source="   ")


def test_session_rejects_empty_campaign_governance_id() -> None:
    with pytest.raises(ValueError, match="campaign_governance_id must be non-empty"):
        _completed_session(campaign_governance_id="   ")


def test_session_rejects_negative_candidate_count() -> None:
    with pytest.raises(ValueError, match="candidate_count must be non-negative"):
        _completed_session(candidate_count=-1)


def test_session_rejects_negative_trade_plan_counts() -> None:
    with pytest.raises(ValueError, match="trade plan counts must be non-negative"):
        _completed_session(accepted_trade_plan_count=-1)


def test_session_rejects_negative_position_plan_count() -> None:
    with pytest.raises(ValueError, match="position_plan_count must be non-negative"):
        _completed_session(position_plan_count=-1)


def test_session_rejects_wrong_limitations_tuple() -> None:
    with pytest.raises(ValueError, match="limitations must be exactly"):
        _completed_session(limitations=("wrong",))


def test_session_rejects_empty_stage_manifest() -> None:
    with pytest.raises(ValueError, match="stage_manifest must contain at least 1 stage"):
        _completed_session(stage_manifest=())


def test_session_rejects_duplicate_universe_instruments() -> None:
    with pytest.raises(ValueError, match="must not contain duplicate instruments"):
        _completed_session(requested_universe=("AAPL", "AAPL"))


def test_session_rejects_empty_universe() -> None:
    with pytest.raises(ValueError, match="requested_universe must contain at least 1"):
        _completed_session(requested_universe=())


def test_session_rejects_position_plan_count_exceeding_accepted() -> None:
    with pytest.raises(ValueError, match="position_plan_count must not exceed"):
        _completed_session(accepted_trade_plan_count=1, position_plan_count=2)


def test_session_rejects_out_of_order_stage_manifest() -> None:
    with pytest.raises(ValueError, match="non-decreasing started_at"):
        _completed_session(
            stage_manifest=(
                _stage(StageName.DATA_ACQUISITION, StageStatus.COMPLETED, started_at=_T0),
                _stage(
                    StageName.GOVERNANCE_SETUP,
                    StageStatus.COMPLETED,
                    started_at=_T0 - timedelta(seconds=1),
                ),
            )
        )


def test_ranked_decisions_property_sorts_ascending_and_excludes_unranked() -> None:
    session = _completed_session(
        decisions=(
            ResearchDecisionEntry(
                rank=2,
                instrument_symbol="MSFT",
                decision_candidate_governance_id="DCAND-0002",
                scan_decision="LONG_CANDIDATE",
                trade_plan_governance_id=None,
                trade_plan_decision=None,
                position_plan_governance_id=None,
            ),
            ResearchDecisionEntry(
                rank=None,
                instrument_symbol="GOOG",
                decision_candidate_governance_id="DCAND-0003",
                scan_decision="NO_TRADE",
                trade_plan_governance_id=None,
                trade_plan_decision=None,
                position_plan_governance_id=None,
            ),
            ResearchDecisionEntry(
                rank=1,
                instrument_symbol="AAPL",
                decision_candidate_governance_id="DCAND-0001",
                scan_decision="LONG_CANDIDATE",
                trade_plan_governance_id=None,
                trade_plan_decision=None,
                position_plan_governance_id=None,
            ),
        )
    )
    ranked = session.ranked_decisions
    assert [d.instrument_symbol for d in ranked] == ["AAPL", "MSFT"]


# --------------------------------------------------------------------------
# As-of temporal firewall: derive_shared_evaluation_timestamp
# --------------------------------------------------------------------------


def test_shared_evaluation_timestamp_aligned_instruments() -> None:
    series = {"AAPL": _series("AAPL", 10), "MSFT": _series("MSFT", 10)}
    result = derive_shared_evaluation_timestamp(series, as_of=_T0 + timedelta(days=6))
    assert result == _T0 + timedelta(days=6)


def test_shared_evaluation_timestamp_falls_back_on_gap() -> None:
    series = {"AAPL": _series("AAPL", 10), "MSFT": _series("MSFT", 10, skip=6)}
    result = derive_shared_evaluation_timestamp(series, as_of=_T0 + timedelta(days=6))
    assert result == _T0 + timedelta(days=5)


def test_shared_evaluation_timestamp_none_when_no_overlap() -> None:
    series = {
        "AAPL": _series("AAPL", 3),
        "MSFT": HistoricalInstrumentSeries(
            instrument=Instrument("MSFT"), bars=(_bar("MSFT", 100), _bar("MSFT", 101))
        ),
    }
    result = derive_shared_evaluation_timestamp(series, as_of=_T0 + timedelta(days=6))
    assert result is None


def test_shared_evaluation_timestamp_empty_universe_returns_none() -> None:
    assert derive_shared_evaluation_timestamp({}, as_of=_T0) is None


def test_shared_evaluation_timestamp_never_uses_future_bars() -> None:
    """The as-of firewall itself: mutating bars strictly after as_of must
    never change the derived cutoff."""
    original = {"AAPL": _series("AAPL", 10), "MSFT": _series("MSFT", 10)}
    as_of = _T0 + timedelta(days=5)
    before = derive_shared_evaluation_timestamp(original, as_of=as_of)

    mutated_aapl_bars = original["AAPL"].bars[:6] + tuple(
        _bar("AAPL", i, close="99999") for i in range(6, 10)
    )
    mutated = {
        "AAPL": HistoricalInstrumentSeries(instrument=Instrument("AAPL"), bars=mutated_aapl_bars),
        "MSFT": original["MSFT"],
    }
    after = derive_shared_evaluation_timestamp(mutated, as_of=as_of)
    assert before == after == as_of


# --------------------------------------------------------------------------
# As-of temporal firewall: derive_observation_window
# --------------------------------------------------------------------------


def test_observation_window_builds_at_exact_evaluation_timestamp() -> None:
    series = _series("AAPL", 10)
    window = derive_observation_window(
        series, evaluation_timestamp=_T0 + timedelta(days=6), reference_window_size=5
    )
    assert window is not None
    assert window.evaluation_bar.timestamp == _T0 + timedelta(days=6)
    assert len(window.reference_bars) == 5


def test_observation_window_none_when_evaluation_bar_missing() -> None:
    series = _series("AAPL", 5)
    window = derive_observation_window(
        series, evaluation_timestamp=_T0 + timedelta(days=6), reference_window_size=5
    )
    assert window is None


def test_observation_window_none_when_insufficient_reference_bars() -> None:
    series = _series("AAPL", 3)
    window = derive_observation_window(
        series, evaluation_timestamp=_T0 + timedelta(days=2), reference_window_size=5
    )
    assert window is None


def test_observation_window_never_includes_bars_after_evaluation_timestamp() -> None:
    series = _series("AAPL", 10)
    window = derive_observation_window(
        series, evaluation_timestamp=_T0 + timedelta(days=5), reference_window_size=5
    )
    assert window is not None
    assert all(bar.timestamp <= _T0 + timedelta(days=5) for bar in window.bars)
