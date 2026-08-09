"""MILESTONE-062 unit tests for the historical validation study domain:
segment/bundle validation (including hostile segment-boundary cases), and
the full `build_validation_study()` pipeline against the real committed
multi-period fixture. Pure, no PostgreSQL.
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
from empirical_platform.decision_candidate.validation_study import (
    HistoricalValidationStudy,
    HistoricalValidationStudyClassification,
    HistoricalValidationStudyStatus,
    ValidationDatasetBundle,
    ValidationDatasetBundleAuthority,
    ValidationSegment,
    ValidationSegmentResult,
    ValidationSegmentRole,
    ValidationSegmentSpec,
    build_validation_study,
)
from empirical_platform.identifiers.pairs import DomainIdentity
from empirical_platform.identifiers.types import BacktestRunId, DatasetId, ValidationStudyId
from empirical_platform.shared.identifiers import (
    DeterministicRuntimeIdentifierGenerator,
    RuntimeIdentifier,
)

_FIXTURE_PATH = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "m062_validation_study"
    / "synthetic_multi_period_validation_dataset_bundle.json"
)
_EXPECTED_SHA256 = "3289c380b233b06495c865b1645185436318b2394d77faaea97be96bf787c9f3"
_MINUTE_ZERO = datetime(2026, 1, 1, 9, 0, tzinfo=UTC)


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
    """A minimal, always-NO_TRADE bar series (flat price, flat volume) --
    enough for structural segment/bundle validation tests that never need
    a real trading decision."""
    bars = tuple(
        _bar(instrument=instrument, minute=minute, close="100.00") for minute in range(bar_count)
    )
    return HistoricalInstrumentSeries(instrument=Instrument(instrument), bars=bars)


def _bundle_authority(
    *, sha256: str, total_bars: int, instrument_count: int = 1
) -> ValidationDatasetBundleAuthority:
    return ValidationDatasetBundleAuthority(
        dataset_bundle_id=DatasetId("DATASET-9001"),
        dataset_bundle_version="1",
        source_kind="FIXED_VALIDATION_FIXTURE",
        sha256=sha256,
        interval=BarInterval.ONE_MINUTE,
        instrument_count=instrument_count,
        total_bars_per_instrument=total_bars,
    )


_VALID_SPECS = (
    ValidationSegmentSpec(
        segment_id="DEV",
        role=ValidationSegmentRole.DEVELOPMENT_REFERENCE,
        warmup_bar_count=5,
        scoring_bar_count=8,
        buffer_bar_count=3,
    ),
    ValidationSegmentSpec(
        segment_id="HOLDOUT_1",
        role=ValidationSegmentRole.HOLDOUT_1,
        warmup_bar_count=5,
        scoring_bar_count=8,
        buffer_bar_count=3,
    ),
    ValidationSegmentSpec(
        segment_id="HOLDOUT_2",
        role=ValidationSegmentRole.HOLDOUT_2,
        warmup_bar_count=5,
        scoring_bar_count=8,
        buffer_bar_count=3,
    ),
)
_TOTAL_BARS = sum(spec.total_bar_count for spec in _VALID_SPECS)  # 48
_SHA = "a" * 64


# ---------------------------------------------------------------------------
# ValidationSegmentSpec / ValidationDatasetBundleAuthority validation
# ---------------------------------------------------------------------------


def test_segment_spec_rejects_empty_segment_id() -> None:
    with pytest.raises(ValueError, match="segment_id must be non-empty"):
        ValidationSegmentSpec(
            segment_id="  ",
            role=ValidationSegmentRole.DEVELOPMENT_REFERENCE,
            warmup_bar_count=5,
            scoring_bar_count=8,
            buffer_bar_count=3,
        )


def test_segment_spec_rejects_zero_scoring_bar_count() -> None:
    with pytest.raises(ValueError, match="scoring_bar_count must be at least 1"):
        ValidationSegmentSpec(
            segment_id="DEV",
            role=ValidationSegmentRole.DEVELOPMENT_REFERENCE,
            warmup_bar_count=5,
            scoring_bar_count=0,
            buffer_bar_count=3,
        )


def test_segment_spec_rejects_negative_warmup() -> None:
    with pytest.raises(ValueError, match="warmup_bar_count must not be negative"):
        ValidationSegmentSpec(
            segment_id="DEV",
            role=ValidationSegmentRole.DEVELOPMENT_REFERENCE,
            warmup_bar_count=-1,
            scoring_bar_count=8,
            buffer_bar_count=3,
        )


def test_bundle_authority_rejects_short_sha256() -> None:
    with pytest.raises(ValueError, match="sha256 must be a full SHA-256 hex digest"):
        _bundle_authority(sha256="not-a-real-hash", total_bars=48)


# ---------------------------------------------------------------------------
# ValidationDatasetBundle structural validation
# ---------------------------------------------------------------------------


def test_bundle_rejects_instrument_count_mismatch() -> None:
    series = (_flat_series("AAPL", _TOTAL_BARS),)
    authority = _bundle_authority(sha256=_SHA, total_bars=_TOTAL_BARS, instrument_count=2)
    with pytest.raises(ValueError, match="instrument_count does not match"):
        ValidationDatasetBundle(authority=authority, segment_specs=_VALID_SPECS, series=series)


def test_bundle_rejects_duplicate_instrument() -> None:
    series = (_flat_series("AAPL", _TOTAL_BARS), _flat_series("AAPL", _TOTAL_BARS))
    authority = _bundle_authority(sha256=_SHA, total_bars=_TOTAL_BARS, instrument_count=2)
    with pytest.raises(ValueError, match="duplicate instrument"):
        ValidationDatasetBundle(authority=authority, segment_specs=_VALID_SPECS, series=series)


def test_bundle_rejects_mismatched_timestamp_grid() -> None:
    aapl = _flat_series("AAPL", _TOTAL_BARS)
    msft_bars = tuple(
        _bar(instrument="MSFT", minute=minute + 1, close="100.00") for minute in range(_TOTAL_BARS)
    )
    msft = HistoricalInstrumentSeries(instrument=Instrument("MSFT"), bars=msft_bars)
    authority = _bundle_authority(sha256=_SHA, total_bars=_TOTAL_BARS, instrument_count=2)
    with pytest.raises(ValueError, match="canonical timestamp grid"):
        ValidationDatasetBundle(
            authority=authority, segment_specs=_VALID_SPECS, series=(aapl, msft)
        )


def test_bundle_rejects_bar_count_mismatch_with_authority() -> None:
    series = (_flat_series("AAPL", _TOTAL_BARS),)
    authority = _bundle_authority(sha256=_SHA, total_bars=_TOTAL_BARS + 1, instrument_count=1)
    with pytest.raises(ValueError, match="total_bars_per_instrument does not match"):
        ValidationDatasetBundle(authority=authority, segment_specs=_VALID_SPECS, series=series)


def test_bundle_rejects_duplicate_segment_id() -> None:
    duplicate_specs = (
        _VALID_SPECS[0],
        _VALID_SPECS[0],
    )
    series = (_flat_series("AAPL", 32),)
    authority = _bundle_authority(sha256=_SHA, total_bars=32, instrument_count=1)
    with pytest.raises(ValueError, match="segment_id values must be unique"):
        ValidationDatasetBundle(authority=authority, segment_specs=duplicate_specs, series=series)


# ---------------------------------------------------------------------------
# ValidationSegment boundary validation
# ---------------------------------------------------------------------------


def test_validation_segment_rejects_naive_timestamp() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        ValidationSegment(
            segment_id="DEV",
            role=ValidationSegmentRole.DEVELOPMENT_REFERENCE,
            data_start_timestamp=datetime(2026, 1, 1),  # naive
            data_end_timestamp=_MINUTE_ZERO + timedelta(minutes=15),
            scoring_start_timestamp=_MINUTE_ZERO + timedelta(minutes=5),
            scoring_end_timestamp=_MINUTE_ZERO + timedelta(minutes=12),
            warmup_bar_count=5,
            scoring_bar_count=8,
            buffer_bar_count=3,
        )


def test_validation_segment_rejects_inverted_scoring_range() -> None:
    with pytest.raises(ValueError, match="scoring_start_timestamp must not be after scoring_end"):
        ValidationSegment(
            segment_id="DEV",
            role=ValidationSegmentRole.DEVELOPMENT_REFERENCE,
            data_start_timestamp=_MINUTE_ZERO,
            data_end_timestamp=_MINUTE_ZERO + timedelta(minutes=15),
            scoring_start_timestamp=_MINUTE_ZERO + timedelta(minutes=12),
            scoring_end_timestamp=_MINUTE_ZERO + timedelta(minutes=5),  # inverted
            warmup_bar_count=5,
            scoring_bar_count=8,
            buffer_bar_count=3,
        )


def test_validation_segment_rejects_scoring_range_outside_data_range() -> None:
    with pytest.raises(ValueError, match="scoring_end_timestamp must not be after data_end"):
        ValidationSegment(
            segment_id="DEV",
            role=ValidationSegmentRole.DEVELOPMENT_REFERENCE,
            data_start_timestamp=_MINUTE_ZERO,
            data_end_timestamp=_MINUTE_ZERO + timedelta(minutes=10),
            scoring_start_timestamp=_MINUTE_ZERO + timedelta(minutes=5),
            scoring_end_timestamp=_MINUTE_ZERO + timedelta(minutes=15),  # beyond data_end
            warmup_bar_count=5,
            scoring_bar_count=8,
            buffer_bar_count=3,
        )


# ---------------------------------------------------------------------------
# build_validation_study(): hostile segment-declaration cases (Phase 24)
# ---------------------------------------------------------------------------


def _gen() -> DeterministicRuntimeIdentifierGenerator:
    return DeterministicRuntimeIdentifierGenerator(
        [f"{i:08d}-0000-4000-8000-000000000001" for i in range(90000001, 90001000)]
    )


def _backtest_run_identity_for(segment_id: str) -> DomainIdentity[BacktestRunId]:
    n = {"DEV": 1, "HOLDOUT_1": 2, "HOLDOUT_2": 3}.get(segment_id, 9)
    return DomainIdentity(
        governance_id=BacktestRunId(f"BTRUN-900{n}"),
        runtime_id=RuntimeIdentifier(f"9{n}000001-0000-4000-8000-000000000001"),
    )


def _study_identity() -> DomainIdentity[ValidationStudyId]:
    return DomainIdentity(
        governance_id=ValidationStudyId("STUDY-9001"),
        runtime_id=RuntimeIdentifier("91000000-0000-4000-8000-000000000001"),
    )


def _sizing_context() -> PositionSizingContext:
    return PositionSizingContext(account_equity=Decimal("100000"), risk_percent=Decimal("0.01"))


def test_build_validation_study_rejects_missing_development_segment() -> None:
    specs = (_VALID_SPECS[1], _VALID_SPECS[2])  # only the two holdouts
    series = (_flat_series("AAPL", sum(spec.total_bar_count for spec in specs)),)
    authority = _bundle_authority(
        sha256=_SHA, total_bars=sum(spec.total_bar_count for spec in specs), instrument_count=1
    )
    bundle = ValidationDatasetBundle(authority=authority, segment_specs=specs, series=series)
    with pytest.raises(ValueError, match="exactly 3 segments"):
        build_validation_study(
            identity=_study_identity(),
            bundle=bundle,
            sizing_context=_sizing_context(),
            runtime_identifier_generator=_gen(),
            backtest_run_identity_for=_backtest_run_identity_for,
        )


def test_build_validation_study_rejects_only_one_holdout() -> None:
    specs = (_VALID_SPECS[0], _VALID_SPECS[1])  # dev + holdout_1 only
    total = sum(spec.total_bar_count for spec in specs)
    series = (_flat_series("AAPL", total),)
    authority = _bundle_authority(sha256=_SHA, total_bars=total, instrument_count=1)
    bundle = ValidationDatasetBundle(authority=authority, segment_specs=specs, series=series)
    with pytest.raises(ValueError, match="exactly 3 segments"):
        build_validation_study(
            identity=_study_identity(),
            bundle=bundle,
            sizing_context=_sizing_context(),
            runtime_identifier_generator=_gen(),
            backtest_run_identity_for=_backtest_run_identity_for,
        )


def test_build_validation_study_rejects_wrong_segment_order() -> None:
    reordered = (_VALID_SPECS[1], _VALID_SPECS[0], _VALID_SPECS[2])
    series = (_flat_series("AAPL", _TOTAL_BARS),)
    authority = _bundle_authority(sha256=_SHA, total_bars=_TOTAL_BARS, instrument_count=1)
    bundle = ValidationDatasetBundle(authority=authority, segment_specs=reordered, series=series)
    with pytest.raises(ValueError, match="must be declared in order"):
        build_validation_study(
            identity=_study_identity(),
            bundle=bundle,
            sizing_context=_sizing_context(),
            runtime_identifier_generator=_gen(),
            backtest_run_identity_for=_backtest_run_identity_for,
        )


def test_build_validation_study_rejects_warmup_mismatch_with_reference_window_size() -> None:
    series = (_flat_series("AAPL", _TOTAL_BARS),)
    authority = _bundle_authority(sha256=_SHA, total_bars=_TOTAL_BARS, instrument_count=1)
    bundle = ValidationDatasetBundle(authority=authority, segment_specs=_VALID_SPECS, series=series)
    with pytest.raises(ValueError, match="warmup_bar_count .* must equal reference_window_size"):
        build_validation_study(
            identity=_study_identity(),
            bundle=bundle,
            sizing_context=_sizing_context(),
            runtime_identifier_generator=_gen(),
            backtest_run_identity_for=_backtest_run_identity_for,
            reference_window_size=6,  # bundle declares warmup=5
        )


def test_build_validation_study_rejects_buffer_mismatch_with_holding_horizon() -> None:
    from empirical_platform.decision_candidate.historical_backtest import HistoricalOutcomeModel

    series = (_flat_series("AAPL", _TOTAL_BARS),)
    authority = _bundle_authority(sha256=_SHA, total_bars=_TOTAL_BARS, instrument_count=1)
    bundle = ValidationDatasetBundle(authority=authority, segment_specs=_VALID_SPECS, series=series)
    with pytest.raises(ValueError, match="buffer_bar_count .* must equal"):
        build_validation_study(
            identity=_study_identity(),
            bundle=bundle,
            sizing_context=_sizing_context(),
            runtime_identifier_generator=_gen(),
            backtest_run_identity_for=_backtest_run_identity_for,
            outcome_model=HistoricalOutcomeModel(
                holding_horizon_bars=4
            ),  # bundle declares buffer=3
        )


def test_build_validation_study_rejects_segment_range_outside_dataset() -> None:
    # Declare segments whose total bar count exceeds what the series actually has.
    series = (_flat_series("AAPL", _TOTAL_BARS - 1),)  # one bar short
    authority = _bundle_authority(sha256=_SHA, total_bars=_TOTAL_BARS - 1, instrument_count=1)
    bundle = ValidationDatasetBundle(authority=authority, segment_specs=_VALID_SPECS, series=series)
    with pytest.raises(ValueError, match="falls outside the dataset"):
        build_validation_study(
            identity=_study_identity(),
            bundle=bundle,
            sizing_context=_sizing_context(),
            runtime_identifier_generator=_gen(),
            backtest_run_identity_for=_backtest_run_identity_for,
        )


# ---------------------------------------------------------------------------
# build_validation_study(): full pipeline against the real committed fixture
# ---------------------------------------------------------------------------


def _load_real_bundle() -> ValidationDatasetBundle:
    from empirical_platform.usecases.validation_study_io import (
        parse_validation_dataset_bundle_file,
    )

    return parse_validation_dataset_bundle_file(
        str(_FIXTURE_PATH), expected_sha256=_EXPECTED_SHA256
    )


def test_real_fixture_matches_declared_sha256() -> None:
    raw_bytes = _FIXTURE_PATH.read_bytes()
    assert dataset_sha256(raw_bytes) == _EXPECTED_SHA256


def test_build_validation_study_against_real_fixture_matches_hand_verified_results() -> None:
    bundle = _load_real_bundle()
    study, runs = build_validation_study(
        identity=_study_identity(),
        bundle=bundle,
        sizing_context=_sizing_context(),
        runtime_identifier_generator=_gen(),
        backtest_run_identity_for=_backtest_run_identity_for,
    )
    assert study.classification == HistoricalValidationStudyClassification.HOLDOUT_RESULTS_RECORDED
    assert study.development.executed_trade_count == 4
    assert study.development.win_count == 4
    assert study.development.net_pnl == Decimal("933.84935670")
    assert study.holdout_1.executed_trade_count == 3
    assert study.holdout_1.win_count == 1
    assert study.holdout_1.net_pnl == Decimal("64.578130")
    assert study.holdout_2.executed_trade_count == 5
    assert study.holdout_2.win_count == 3
    assert study.holdout_2.net_pnl == Decimal("383.228590")
    assert len(runs) == 3
    assert study.holdout_1_net_pnl_delta == study.holdout_1.net_pnl - study.development.net_pnl
    assert study.holdout_2_net_pnl_delta == study.holdout_2.net_pnl - study.development.net_pnl


def test_segments_never_share_a_bar() -> None:
    """The complete holdout/data-isolation firewall: no bar belongs to more
    than one segment's own HistoricalDataset slice."""
    bundle = _load_real_bundle()
    study, runs = build_validation_study(
        identity=_study_identity(),
        bundle=bundle,
        sizing_context=_sizing_context(),
        runtime_identifier_generator=_gen(),
        backtest_run_identity_for=_backtest_run_identity_for,
    )
    dev_run, holdout1_run, holdout2_run = runs
    assert dev_run.dataset_end_timestamp < holdout1_run.dataset_start_timestamp
    assert holdout1_run.dataset_end_timestamp < holdout2_run.dataset_start_timestamp
    # Each segment's own reported data range covers exactly 16 bars.
    assert dev_run.dataset_total_bars == 16 * len(bundle.series)
    assert holdout1_run.dataset_total_bars == 16 * len(bundle.series)
    assert holdout2_run.dataset_total_bars == 16 * len(bundle.series)


_SEGMENT_INDEX = {"DEV": 1, "HOLDOUT_1": 2, "HOLDOUT_2": 3}


def _replay_backtest_run_identity_for(
    prefix: int,
) -> Callable[[str], DomainIdentity[BacktestRunId]]:
    def _identity_for(segment_id: str) -> DomainIdentity[BacktestRunId]:
        index = _SEGMENT_INDEX[segment_id]
        return DomainIdentity(
            governance_id=BacktestRunId(f"BTRUN-9{prefix}0{index}"),
            runtime_id=RuntimeIdentifier(f"9{prefix}{index}00001-0000-4000-8000-000000000001"),
        )

    return _identity_for


def test_deterministic_replay_produces_identical_semantic_result() -> None:
    bundle = _load_real_bundle()
    study_a, _ = build_validation_study(
        identity=DomainIdentity(
            governance_id=ValidationStudyId("STUDY-9002"),
            runtime_id=RuntimeIdentifier("92000000-0000-4000-8000-000000000001"),
        ),
        bundle=bundle,
        sizing_context=_sizing_context(),
        runtime_identifier_generator=_gen(),
        backtest_run_identity_for=_replay_backtest_run_identity_for(1),
    )
    study_b, _ = build_validation_study(
        identity=DomainIdentity(
            governance_id=ValidationStudyId("STUDY-9003"),  # different identity
            runtime_id=RuntimeIdentifier("93000000-0000-4000-8000-000000000001"),
        ),
        bundle=bundle,
        sizing_context=_sizing_context(),
        runtime_identifier_generator=_gen(),
        backtest_run_identity_for=_replay_backtest_run_identity_for(2),
    )
    assert study_a.classification == study_b.classification
    assert study_a.development.net_pnl == study_b.development.net_pnl
    assert study_a.holdout_1.total_r == study_b.holdout_1.total_r
    assert study_a.holdout_2.win_rate == study_b.holdout_2.win_rate
    assert study_a.holdout_1_net_pnl_delta == study_b.holdout_1_net_pnl_delta


# ---------------------------------------------------------------------------
# Additional hostile-review coverage (Phase 24)
# ---------------------------------------------------------------------------


def _segment_result(
    *, role: ValidationSegmentRole, segment_id: str, start_minute: int, end_minute: int
) -> ValidationSegmentResult:
    segment = ValidationSegment(
        segment_id=segment_id,
        role=role,
        data_start_timestamp=_MINUTE_ZERO + timedelta(minutes=start_minute),
        data_end_timestamp=_MINUTE_ZERO + timedelta(minutes=end_minute),
        scoring_start_timestamp=_MINUTE_ZERO + timedelta(minutes=start_minute),
        scoring_end_timestamp=_MINUTE_ZERO + timedelta(minutes=end_minute),
        warmup_bar_count=0,
        scoring_bar_count=end_minute - start_minute + 1,
        buffer_bar_count=0,
    )
    return ValidationSegmentResult(
        segment=segment,
        backtest_run_id=BacktestRunId("BTRUN-9999"),
        backtest_run_runtime_id=RuntimeIdentifier("99999999-0000-4000-8000-000000000001"),
        evaluated_cutoff_count=1,
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


def _valid_study_kwargs() -> dict[str, object]:
    return {
        "identity": _study_identity(),
        "dataset_bundle_id": DatasetId("DATASET-9001"),
        "dataset_bundle_version": "1",
        "dataset_bundle_sha256": _SHA,
        "dataset_source_kind": "FIXED_VALIDATION_FIXTURE",
        "interval": BarInterval.ONE_MINUTE,
        "instrument_universe": (Instrument("AAPL"),),
        "reference_window_size": 5,
        "strategy_id": "S",
        "strategy_version": "1",
        "ranking_model_id": "R",
        "ranking_model_version": "1",
        "risk_policy_id": "RP",
        "risk_policy_version": "1",
        "sizing_policy_id": "SP",
        "sizing_policy_version": "1",
        "execution_assumption_id": "EA",
        "execution_assumption_version": "1",
        "outcome_model_id": "OM",
        "outcome_model_version": "1",
        "cost_model_id": "CM",
        "cost_model_version": "1",
        "holding_horizon_bars": 3,
        "supplied_account_equity": Decimal("100000"),
        "supplied_risk_percent": Decimal("0.01"),
        "survivorship_bias_disclosure": "SURVIVORSHIP_BIAS_NOT_ADDRESSED",
        "status": HistoricalValidationStudyStatus.STUDY_COMPLETED,
        "classification": HistoricalValidationStudyClassification.INSUFFICIENT_EVIDENCE,
        "holdout_1_net_pnl_delta": Decimal("0"),
        "holdout_1_total_r_delta": Decimal("0"),
        "holdout_2_net_pnl_delta": Decimal("0"),
        "holdout_2_total_r_delta": Decimal("0"),
    }


def test_historical_validation_study_rejects_overlapping_dev_and_holdout1() -> None:
    kwargs = _valid_study_kwargs()
    kwargs["development"] = _segment_result(
        role=ValidationSegmentRole.DEVELOPMENT_REFERENCE,
        segment_id="DEV",
        start_minute=0,
        end_minute=15,
    )
    kwargs["holdout_1"] = _segment_result(
        role=ValidationSegmentRole.HOLDOUT_1, segment_id="HOLDOUT_1", start_minute=10, end_minute=31
    )  # overlaps DEV's own range (10 <= 15)
    kwargs["holdout_2"] = _segment_result(
        role=ValidationSegmentRole.HOLDOUT_2, segment_id="HOLDOUT_2", start_minute=32, end_minute=47
    )
    with pytest.raises(ValueError, match="chronologically disjoint"):
        HistoricalValidationStudy(**kwargs)  # type: ignore[arg-type]


def test_bundle_rejects_interval_mismatch() -> None:
    series = (_flat_series("AAPL", _TOTAL_BARS),)
    authority = ValidationDatasetBundleAuthority(
        dataset_bundle_id=DatasetId("DATASET-9001"),
        dataset_bundle_version="1",
        source_kind="FIXED_VALIDATION_FIXTURE",
        sha256=_SHA,
        interval=BarInterval.FIVE_MINUTE,  # bars are actually ONE_MINUTE
        instrument_count=1,
        total_bars_per_instrument=_TOTAL_BARS,
    )
    with pytest.raises(ValueError, match="own interval"):
        ValidationDatasetBundle(authority=authority, segment_specs=_VALID_SPECS, series=series)


def test_build_validation_study_is_independent_of_instrument_declaration_order() -> None:
    """Reversing the bundle's own instrument order must not change any
    segment's results -- M061's own internal sort already makes this
    order-independent, verified here at the M062 orchestration level."""
    bundle = _load_real_bundle()
    reversed_bundle = ValidationDatasetBundle(
        authority=bundle.authority,
        segment_specs=bundle.segment_specs,
        series=tuple(reversed(bundle.series)),
    )
    study_forward, _ = build_validation_study(
        identity=DomainIdentity(
            governance_id=ValidationStudyId("STUDY-9004"),
            runtime_id=RuntimeIdentifier("94000000-0000-4000-8000-000000000001"),
        ),
        bundle=bundle,
        sizing_context=_sizing_context(),
        runtime_identifier_generator=_gen(),
        backtest_run_identity_for=_replay_backtest_run_identity_for(3),
    )
    study_reversed, _ = build_validation_study(
        identity=DomainIdentity(
            governance_id=ValidationStudyId("STUDY-9005"),
            runtime_id=RuntimeIdentifier("95000000-0000-4000-8000-000000000001"),
        ),
        bundle=reversed_bundle,
        sizing_context=_sizing_context(),
        runtime_identifier_generator=_gen(),
        backtest_run_identity_for=_replay_backtest_run_identity_for(4),
    )
    assert study_forward.development.net_pnl == study_reversed.development.net_pnl
    assert (
        study_forward.holdout_1.executed_trade_count
        == study_reversed.holdout_1.executed_trade_count
    )
    assert study_forward.holdout_2.win_rate == study_reversed.holdout_2.win_rate


def test_zero_trade_segments_produce_insufficient_evidence_with_null_metrics() -> None:
    """An all-flat, always-NO_TRADE dataset must never crash -- every
    nullable metric (win_rate/profit_factor/average_r) is genuinely None,
    not a divide-by-zero, and the study classification honestly reports
    INSUFFICIENT_EVIDENCE rather than fabricating a comparison."""
    series = (_flat_series("AAPL", _TOTAL_BARS),)
    authority = _bundle_authority(sha256=_SHA, total_bars=_TOTAL_BARS, instrument_count=1)
    bundle = ValidationDatasetBundle(authority=authority, segment_specs=_VALID_SPECS, series=series)
    study, runs = build_validation_study(
        identity=_study_identity(),
        bundle=bundle,
        sizing_context=_sizing_context(),
        runtime_identifier_generator=_gen(),
        backtest_run_identity_for=_backtest_run_identity_for,
    )
    assert study.classification == HistoricalValidationStudyClassification.INSUFFICIENT_EVIDENCE
    for segment in (study.development, study.holdout_1, study.holdout_2):
        assert segment.executed_trade_count == 0
        assert segment.win_rate is None
        assert segment.profit_factor is None
        assert segment.average_r is None
        assert segment.net_pnl == Decimal("0")
    assert len(runs) == 3


def test_policy_and_model_identity_are_identical_across_all_three_segments() -> None:
    """No parameter tuning: strategy/ranking/risk/sizing/execution/outcome/
    cost model identity must be byte-identical across DEVELOPMENT_REFERENCE
    and both HOLDOUT segments -- the same frozen configuration is applied
    uniformly, never adjusted based on any segment's own results."""
    bundle = _load_real_bundle()
    study, runs = build_validation_study(
        identity=_study_identity(),
        bundle=bundle,
        sizing_context=_sizing_context(),
        runtime_identifier_generator=_gen(),
        backtest_run_identity_for=_backtest_run_identity_for,
    )
    dev_run, holdout1_run, holdout2_run = runs
    for field_name in (
        "strategy_id",
        "strategy_version",
        "ranking_model_id",
        "ranking_model_version",
        "risk_policy_id",
        "risk_policy_version",
        "sizing_policy_id",
        "sizing_policy_version",
        "execution_assumption_id",
        "execution_assumption_version",
        "outcome_model_id",
        "outcome_model_version",
        "cost_model_id",
        "cost_model_version",
    ):
        dev_value = getattr(dev_run, field_name)
        assert getattr(holdout1_run, field_name) == dev_value
        assert getattr(holdout2_run, field_name) == dev_value
    assert study.risk_policy_id == dev_run.risk_policy_id
    assert study.sizing_policy_id == dev_run.sizing_policy_id
