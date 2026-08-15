"""MILESTONE-063 unit tests for broad historical robustness studies.

Pure, no PostgreSQL: window/bundle validation, deterministic walk-forward
ordering, temporal isolation, replay stability, and the real committed
fixture's canonical study metrics.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from empirical_platform.decision_candidate.historical_backtest import (
    HistoricalInstrumentSeries,
    dataset_sha256,
)
from empirical_platform.decision_candidate.market_data import Bar, BarInterval, Instrument
from empirical_platform.decision_candidate.position_plan import PositionSizingContext
from empirical_platform.decision_candidate.robustness_study import (
    HistoricalRobustnessStudy,
    RegimeLabel,
    RobustnessDatasetBundle,
    RobustnessDatasetBundleAuthority,
    RobustnessStudyClassification,
    RobustnessStudyStatus,
    RobustnessUniverseAuthority,
    RobustnessWindow,
    RobustnessWindowResult,
    RobustnessWindowSpec,
    WindowExtreme,
    build_robustness_study,
)
from empirical_platform.identifiers.pairs import DomainIdentity
from empirical_platform.identifiers.types import BacktestRunId, DatasetId, RobustnessStudyId
from empirical_platform.shared.identifiers import (
    DeterministicRuntimeIdentifierGenerator,
    RuntimeIdentifier,
)

_FIXTURE_PATH = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "m063_robustness_study"
    / "synthetic_broad_robustness_dataset_bundle.json"
)
_EXPECTED_SHA256 = "765601962773a215aa483538f467632de6780c8510b4a82b823f77bd132db2dd"
_MINUTE_ZERO = datetime(2026, 1, 1, 9, 0, tzinfo=UTC)
_WINDOW_TOTAL_BARS = 16
_REFERENCE_WINDOW = 5
_HOLDING_HORIZON = 3


def _bar(*, instrument: str, minute: int, close: str, volume: int = 1000) -> Bar:
    price = Decimal(close)
    return Bar(
        instrument=Instrument(instrument),
        interval=BarInterval.ONE_MINUTE,
        timestamp=_MINUTE_ZERO + timedelta(minutes=minute),
        open=price,
        high=price + Decimal("0.10"),
        low=price - Decimal("0.10"),
        close=price,
        volume=volume,
    )


def _flat_series(instrument: str, bar_count: int) -> HistoricalInstrumentSeries:
    bars = tuple(
        _bar(instrument=instrument, minute=minute, close="100.00") for minute in range(bar_count)
    )
    return HistoricalInstrumentSeries(instrument=Instrument(instrument), bars=bars)


def _bundle_authority(
    *, sha256: str, total_bars: int, instrument_count: int
) -> RobustnessDatasetBundleAuthority:
    return RobustnessDatasetBundleAuthority(
        dataset_bundle_id=DatasetId("DATASET-9001"),
        dataset_bundle_version="1",
        source_kind="FIXED_ROBUSTNESS_FIXTURE",
        sha256=sha256,
        interval=BarInterval.ONE_MINUTE,
        instrument_count=instrument_count,
        total_bars_per_instrument=total_bars,
    )


def _universe_authority(*, constituents: tuple[Instrument, ...]) -> RobustnessUniverseAuthority:
    return RobustnessUniverseAuthority(
        universe_id="UNIVERSE-9001",
        universe_version="1",
        membership_model="FIXED_SYNTHETIC_UNIVERSE",
        constituents=tuple(sorted(constituents, key=str)),
    )


_VALID_SPECS = tuple(
    RobustnessWindowSpec(
        window_id=f"W{index:02d}",
        sequence_index=index - 1,
        warmup_bar_count=5,
        scoring_bar_count=8,
        buffer_bar_count=3,
    )
    for index in range(1, 4)
)
_TOTAL_BARS = sum(spec.total_bar_count for spec in _VALID_SPECS)
_SHA = "a" * 64


def _gen() -> DeterministicRuntimeIdentifierGenerator:
    return DeterministicRuntimeIdentifierGenerator(
        [f"{i:08d}-0000-4000-8000-000000000001" for i in range(93000001, 93001000)]
    )


def _study_identity() -> DomainIdentity[RobustnessStudyId]:
    return DomainIdentity(
        governance_id=RobustnessStudyId("ROBUST-9001"),
        runtime_id=RuntimeIdentifier("93000000-0000-4000-8000-000000000001"),
    )


def _sizing_context() -> PositionSizingContext:
    return PositionSizingContext(account_equity=Decimal("100000"), risk_percent=Decimal("0.01"))


def _backtest_run_identity_for(window_id: str) -> DomainIdentity[BacktestRunId]:
    sequence = int(window_id[1:])
    return DomainIdentity(
        governance_id=BacktestRunId(f"BTRUN-9{sequence:03d}"),
        runtime_id=RuntimeIdentifier(f"93{sequence:06d}-0000-4000-8000-000000000001"),
    )


def _load_real_bundle() -> RobustnessDatasetBundle:
    from empirical_platform.usecases.robustness_study_io import (
        parse_robustness_dataset_bundle_file,
    )

    return parse_robustness_dataset_bundle_file(
        str(_FIXTURE_PATH), expected_sha256=_EXPECTED_SHA256
    )


def _replay_backtest_run_identity_for(
    prefix: int,
) -> Callable[[str], DomainIdentity[BacktestRunId]]:
    def _identity_for(window_id: str) -> DomainIdentity[BacktestRunId]:
        sequence = int(window_id[1:])
        governance_number = 3000 + (prefix * 10) + sequence
        return DomainIdentity(
            governance_id=BacktestRunId(f"BTRUN-{governance_number:04d}"),
            runtime_id=RuntimeIdentifier(f"{prefix:02d}{sequence:06d}-0000-4000-8000-000000000001"),
        )

    return _identity_for


def _study_with_flat_windows() -> tuple[HistoricalRobustnessStudy, tuple[object, ...]]:
    series = (_flat_series("AAPL", _TOTAL_BARS),)
    bundle = RobustnessDatasetBundle(
        authority=_bundle_authority(sha256=_SHA, total_bars=_TOTAL_BARS, instrument_count=1),
        universe_authority=_universe_authority(constituents=(Instrument("AAPL"),)),
        window_specs=_VALID_SPECS,
        series=series,
    )
    return build_robustness_study(
        identity=_study_identity(),
        bundle=bundle,
        sizing_context=_sizing_context(),
        runtime_identifier_generator=_gen(),
        backtest_run_identity_for=_backtest_run_identity_for,
    )


def test_window_spec_rejects_empty_window_id() -> None:
    with pytest.raises(ValueError, match="window_id must be non-empty"):
        RobustnessWindowSpec(
            window_id=" ",
            sequence_index=0,
            warmup_bar_count=5,
            scoring_bar_count=8,
            buffer_bar_count=3,
        )


def test_window_spec_rejects_zero_scoring_bar_count() -> None:
    with pytest.raises(ValueError, match="scoring_bar_count must be at least 1"):
        RobustnessWindowSpec(
            window_id="W01",
            sequence_index=0,
            warmup_bar_count=5,
            scoring_bar_count=0,
            buffer_bar_count=3,
        )


def test_universe_authority_rejects_unsorted_constituents() -> None:
    with pytest.raises(ValueError, match="sorted canonically"):
        RobustnessUniverseAuthority(
            universe_id="UNIVERSE-1",
            universe_version="1",
            membership_model="FIXED_SYNTHETIC_UNIVERSE",
            constituents=(Instrument("MSFT"), Instrument("AAPL")),
        )


def test_bundle_rejects_universe_constituent_mismatch() -> None:
    series = (_flat_series("AAPL", _TOTAL_BARS),)
    with pytest.raises(ValueError, match="constituents must match"):
        RobustnessDatasetBundle(
            authority=_bundle_authority(sha256=_SHA, total_bars=_TOTAL_BARS, instrument_count=1),
            universe_authority=_universe_authority(constituents=(Instrument("MSFT"),)),
            window_specs=_VALID_SPECS,
            series=series,
        )


def test_bundle_rejects_duplicate_sequence_index() -> None:
    duplicate_specs = (
        _VALID_SPECS[0],
        RobustnessWindowSpec(
            window_id="W99",
            sequence_index=_VALID_SPECS[0].sequence_index,
            warmup_bar_count=5,
            scoring_bar_count=8,
            buffer_bar_count=3,
        ),
    )
    series = (_flat_series("AAPL", 32),)
    with pytest.raises(ValueError, match="sequence_index values must be unique"):
        RobustnessDatasetBundle(
            authority=_bundle_authority(sha256=_SHA, total_bars=32, instrument_count=1),
            universe_authority=_universe_authority(constituents=(Instrument("AAPL"),)),
            window_specs=duplicate_specs,
            series=series,
        )


def test_real_fixture_matches_declared_sha256() -> None:
    assert dataset_sha256(_FIXTURE_PATH.read_bytes()) == _EXPECTED_SHA256


def test_build_robustness_study_against_real_fixture_matches_hand_verified_results() -> None:
    bundle = _load_real_bundle()
    study, runs = build_robustness_study(
        identity=_study_identity(),
        bundle=bundle,
        sizing_context=_sizing_context(),
        runtime_identifier_generator=_gen(),
        backtest_run_identity_for=_backtest_run_identity_for,
    )

    assert study.classification == RobustnessStudyClassification.ROBUSTNESS_EVIDENCE_MIXED
    assert study.dataset_bundle_id == DatasetId("DATASET-6301")
    assert study.universe_id == "UNIVERSE-6301"
    assert study.universe_version == "1"
    assert study.universe_membership_model == "FIXED_SYNTHETIC_UNIVERSE"
    assert study.instrument_universe == (
        Instrument("AAPL"),
        Instrument("AMZN"),
        Instrument("GOOG"),
        Instrument("MSFT"),
        Instrument("NVDA"),
        Instrument("TSLA"),
    )
    assert study.window_count == 10
    assert study.total_evaluated_cutoff_count == 80
    assert study.total_simulated_trade_count == 59
    assert study.total_executed_trade_count == 59
    assert study.positive_net_pnl_window_count == 7
    assert study.negative_net_pnl_window_count == 3
    assert study.positive_total_r_window_count == 7
    assert study.negative_total_r_window_count == 3
    assert study.median_window_net_pnl == Decimal("183.944565")
    assert study.median_window_total_r == Decimal("1.634932038356822214357869934")
    assert study.best_window_by_net_pnl == WindowExtreme(
        window_id="W08", value=Decimal("1245.30999130")
    )
    assert study.worst_window_by_net_pnl == WindowExtreme(
        window_id="W07", value=Decimal("-293.055420")
    )
    assert study.best_window_by_total_r == WindowExtreme(
        window_id="W05", value=Decimal("18.24646990892242838850180340")
    )
    assert study.worst_window_by_total_r == WindowExtreme(
        window_id="W06", value=Decimal("-7.737888034172596900624932265")
    )
    assert study.all_window_net_pnl_total == Decimal("3159.55176410")
    assert study.all_window_total_r_total == Decimal("33.84096575766330478385285292")
    assert study.excluding_best_window_net_pnl_total == Decimal("1914.24177280")
    assert study.excluding_best_window_total_r_total == Decimal("15.59449584874087639535104952")
    assert study.largest_positive_window_share_of_positive_pnl == Decimal(
        "0.3481136196652371557486284593"
    )
    assert study.largest_negative_window_share_of_absolute_negative_pnl == Decimal(
        "0.7014969015918107753748046817"
    )
    assert len(runs) == 10
    assert study.window_results[7].window.window_id == "W08"
    assert study.window_results[7].net_pnl == Decimal("1245.30999130")
    assert study.window_results[6].window.window_id == "W07"
    assert study.window_results[6].net_pnl == Decimal("-293.055420")


def test_windows_never_share_a_bar_and_are_ordered_by_sequence_index() -> None:
    bundle = _load_real_bundle()
    study, runs = build_robustness_study(
        identity=_study_identity(),
        bundle=bundle,
        sizing_context=_sizing_context(),
        runtime_identifier_generator=_gen(),
        backtest_run_identity_for=_backtest_run_identity_for,
    )
    for previous, current in zip(study.window_results, study.window_results[1:], strict=False):
        assert previous.window.data_end_timestamp < current.window.data_start_timestamp
    for run in runs:
        assert run.dataset_total_bars == _WINDOW_TOTAL_BARS * len(bundle.series)


def test_build_robustness_study_is_independent_of_window_declaration_order() -> None:
    bundle = _load_real_bundle()
    reversed_bundle = RobustnessDatasetBundle(
        authority=bundle.authority,
        universe_authority=bundle.universe_authority,
        window_specs=tuple(reversed(bundle.window_specs)),
        series=bundle.series,
    )
    study_forward, _ = build_robustness_study(
        identity=DomainIdentity(
            governance_id=RobustnessStudyId("ROBUST-9002"),
            runtime_id=RuntimeIdentifier("93000002-0000-4000-8000-000000000001"),
        ),
        bundle=bundle,
        sizing_context=_sizing_context(),
        runtime_identifier_generator=_gen(),
        backtest_run_identity_for=_replay_backtest_run_identity_for(81),
    )
    study_reversed, _ = build_robustness_study(
        identity=DomainIdentity(
            governance_id=RobustnessStudyId("ROBUST-9003"),
            runtime_id=RuntimeIdentifier("93000003-0000-4000-8000-000000000001"),
        ),
        bundle=reversed_bundle,
        sizing_context=_sizing_context(),
        runtime_identifier_generator=_gen(),
        backtest_run_identity_for=_replay_backtest_run_identity_for(82),
    )

    assert study_forward.all_window_net_pnl_total == study_reversed.all_window_net_pnl_total
    assert study_forward.best_window_by_net_pnl == study_reversed.best_window_by_net_pnl
    assert tuple(result.window.window_id for result in study_forward.window_results) == tuple(
        result.window.window_id for result in study_reversed.window_results
    )


def test_zero_trade_windows_remain_evidence_and_classify_as_insufficient_sample() -> None:
    study, runs = _study_with_flat_windows()
    assert study.classification == RobustnessStudyClassification.INSUFFICIENT_SAMPLE
    assert study.window_count == 3
    for result in study.window_results:
        assert result.executed_trade_count == 0
        assert result.win_rate is None
        assert result.profit_factor is None
        assert result.average_r is None
        assert result.net_pnl == Decimal("0")
    assert len(runs) == 3


def test_late_window_mutation_preserves_earlier_window_semantics() -> None:
    bundle = _load_real_bundle()
    baseline, _ = build_robustness_study(
        identity=DomainIdentity(
            governance_id=RobustnessStudyId("ROBUST-9004"),
            runtime_id=RuntimeIdentifier("93000004-0000-4000-8000-000000000001"),
        ),
        bundle=bundle,
        sizing_context=_sizing_context(),
        runtime_identifier_generator=_gen(),
        backtest_run_identity_for=_replay_backtest_run_identity_for(83),
    )

    mutated_series = []
    for series in bundle.series:
        bars = list(series.bars)
        for index in range(144, 160):
            bar = bars[index]
            bars[index] = Bar(
                instrument=bar.instrument,
                interval=bar.interval,
                timestamp=bar.timestamp,
                open=Decimal("1.00"),
                high=Decimal("1.00"),
                low=Decimal("1.00"),
                close=Decimal("1.00"),
                volume=1,
            )
        mutated_series.append(
            HistoricalInstrumentSeries(instrument=series.instrument, bars=tuple(bars))
        )
    mutated_bundle = RobustnessDatasetBundle(
        authority=bundle.authority,
        universe_authority=bundle.universe_authority,
        window_specs=bundle.window_specs,
        series=tuple(mutated_series),
    )
    mutated, _ = build_robustness_study(
        identity=DomainIdentity(
            governance_id=RobustnessStudyId("ROBUST-9005"),
            runtime_id=RuntimeIdentifier("93000005-0000-4000-8000-000000000001"),
        ),
        bundle=mutated_bundle,
        sizing_context=_sizing_context(),
        runtime_identifier_generator=_gen(),
        backtest_run_identity_for=_replay_backtest_run_identity_for(84),
    )

    for baseline_result, mutated_result in zip(
        baseline.window_results[:9], mutated.window_results[:9], strict=True
    ):
        assert mutated_result.net_pnl == baseline_result.net_pnl
        assert mutated_result.total_r == baseline_result.total_r
        assert mutated_result.executed_trade_count == baseline_result.executed_trade_count
    assert mutated.window_results[9].net_pnl != baseline.window_results[9].net_pnl


def test_deterministic_replay_produces_identical_semantic_result() -> None:
    bundle = _load_real_bundle()
    study_a, _ = build_robustness_study(
        identity=DomainIdentity(
            governance_id=RobustnessStudyId("ROBUST-9006"),
            runtime_id=RuntimeIdentifier("93000006-0000-4000-8000-000000000001"),
        ),
        bundle=bundle,
        sizing_context=_sizing_context(),
        runtime_identifier_generator=_gen(),
        backtest_run_identity_for=_replay_backtest_run_identity_for(85),
    )
    study_b, _ = build_robustness_study(
        identity=DomainIdentity(
            governance_id=RobustnessStudyId("ROBUST-9007"),
            runtime_id=RuntimeIdentifier("93000007-0000-4000-8000-000000000001"),
        ),
        bundle=bundle,
        sizing_context=_sizing_context(),
        runtime_identifier_generator=_gen(),
        backtest_run_identity_for=_replay_backtest_run_identity_for(86),
    )
    assert study_a.classification == study_b.classification
    assert study_a.all_window_net_pnl_total == study_b.all_window_net_pnl_total
    assert study_a.best_window_by_total_r == study_b.best_window_by_total_r
    assert study_a.largest_positive_window_share_of_positive_pnl == (
        study_b.largest_positive_window_share_of_positive_pnl
    )


def test_historical_robustness_study_rejects_overlapping_windows() -> None:
    window_one = RobustnessWindow(
        window_id="W01",
        sequence_index=0,
        data_start_timestamp=_MINUTE_ZERO,
        data_end_timestamp=_MINUTE_ZERO + timedelta(minutes=15),
        scoring_start_timestamp=_MINUTE_ZERO + timedelta(minutes=5),
        scoring_end_timestamp=_MINUTE_ZERO + timedelta(minutes=12),
        warmup_bar_count=5,
        scoring_bar_count=8,
        buffer_bar_count=3,
    )
    window_two = RobustnessWindow(
        window_id="W02",
        sequence_index=1,
        data_start_timestamp=_MINUTE_ZERO + timedelta(minutes=12),
        data_end_timestamp=_MINUTE_ZERO + timedelta(minutes=27),
        scoring_start_timestamp=_MINUTE_ZERO + timedelta(minutes=17),
        scoring_end_timestamp=_MINUTE_ZERO + timedelta(minutes=24),
        warmup_bar_count=5,
        scoring_bar_count=8,
        buffer_bar_count=3,
    )
    result_one = RobustnessWindowResult(
        window=window_one,
        backtest_run_id=BacktestRunId("BTRUN-9001"),
        backtest_run_runtime_id=RuntimeIdentifier("93001001-0000-4000-8000-000000000001"),
        regime_label=RegimeLabel.NORMAL_VOLATILITY,
        realized_volatility=Decimal("0.01"),
        evaluated_cutoff_count=8,
        simulated_trade_count=0,
        executed_trade_count=0,
        win_count=0,
        loss_count=0,
        time_exit_count=0,
        no_entry_count=0,
        gross_pnl=Decimal("0"),
        net_pnl=Decimal("0"),
        average_net_pnl=None,
        average_r=None,
        total_r=Decimal("0"),
        win_rate=None,
        profit_factor=None,
        maximum_realized_pnl_drawdown=None,
    )
    result_two = RobustnessWindowResult(
        window=window_two,
        backtest_run_id=BacktestRunId("BTRUN-9002"),
        backtest_run_runtime_id=RuntimeIdentifier("93001002-0000-4000-8000-000000000001"),
        regime_label=RegimeLabel.HIGH_VOLATILITY,
        realized_volatility=Decimal("0.02"),
        evaluated_cutoff_count=8,
        simulated_trade_count=0,
        executed_trade_count=0,
        win_count=0,
        loss_count=0,
        time_exit_count=0,
        no_entry_count=0,
        gross_pnl=Decimal("0"),
        net_pnl=Decimal("0"),
        average_net_pnl=None,
        average_r=None,
        total_r=Decimal("0"),
        win_rate=None,
        profit_factor=None,
        maximum_realized_pnl_drawdown=None,
    )
    with pytest.raises(ValueError, match="chronologically disjoint and strictly ordered"):
        HistoricalRobustnessStudy(
            identity=_study_identity(),
            dataset_bundle_id=DatasetId("DATASET-9001"),
            dataset_bundle_version="1",
            dataset_bundle_sha256=_SHA,
            dataset_source_kind="FIXED_ROBUSTNESS_FIXTURE",
            universe_id="UNIVERSE-9001",
            universe_version="1",
            universe_membership_model="FIXED_SYNTHETIC_UNIVERSE",
            interval=BarInterval.ONE_MINUTE,
            instrument_universe=(Instrument("AAPL"),),
            reference_window_size=5,
            strategy_id="S",
            strategy_version="1",
            ranking_model_id="R",
            ranking_model_version="1",
            risk_policy_id="RP",
            risk_policy_version="1",
            sizing_policy_id="SP",
            sizing_policy_version="1",
            execution_assumption_id="EA",
            execution_assumption_version="1",
            outcome_model_id="OM",
            outcome_model_version="1",
            cost_model_id="CM",
            cost_model_version="1",
            holding_horizon_bars=3,
            supplied_account_equity=Decimal("100000"),
            supplied_risk_percent=Decimal("0.01"),
            regime_policy_id="POST_HOC_REALIZED_VOLATILITY_TERTILE",
            regime_policy_version="1",
            survivorship_bias_disclosure="SURVIVORSHIP_BIAS_NOT_ADDRESSED",
            status=RobustnessStudyStatus.STUDY_COMPLETED,
            classification=RobustnessStudyClassification.INSUFFICIENT_SAMPLE,
            window_results=(result_one, result_two),
            window_count=2,
            total_evaluated_cutoff_count=16,
            total_simulated_trade_count=0,
            total_executed_trade_count=0,
            positive_net_pnl_window_count=0,
            negative_net_pnl_window_count=0,
            positive_total_r_window_count=0,
            negative_total_r_window_count=0,
            median_window_net_pnl=Decimal("0"),
            median_window_total_r=Decimal("0"),
            best_window_by_net_pnl=WindowExtreme(window_id="W01", value=Decimal("0")),
            worst_window_by_net_pnl=WindowExtreme(window_id="W01", value=Decimal("0")),
            best_window_by_total_r=WindowExtreme(window_id="W01", value=Decimal("0")),
            worst_window_by_total_r=WindowExtreme(window_id="W01", value=Decimal("0")),
            all_window_net_pnl_total=Decimal("0"),
            all_window_total_r_total=Decimal("0"),
            excluding_best_window_net_pnl_total=Decimal("0"),
            excluding_best_window_total_r_total=Decimal("0"),
            largest_positive_window_share_of_positive_pnl=None,
            largest_negative_window_share_of_absolute_negative_pnl=None,
        )
