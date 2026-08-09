"""Historical validation study: does the frozen M057-M061 trading stack
generalize across multiple, temporally-isolated historical periods?

MILESTONE-062. M061 proved the deterministic backtesting *engine* against
one fixed mechanics-validation fixture. It never established anything
about generalization across periods -- M061's own freeze document
explicitly disclaims "the strategy is robust out-of-sample" and
"survivorship bias is absent" as claims it does not make. This module
answers the narrower, honest question those disclaimers leave open: can
the frozen stack be evaluated across a DEVELOPMENT_REFERENCE period and
two independent HOLDOUT periods, with strict temporal/data isolation,
without allowing holdout results to influence anything upstream?

M057-M061 policy stack is frozen. This module performs ZERO parameter
tuning, ZERO search, and selects no "best" configuration from segment
results -- DEVELOPMENT_REFERENCE exists only for descriptive reference,
never as a training signal. Bad holdout performance is a valid, expected,
un-massaged result.

Every segment's backtest is executed by calling the real, unmodified M061
`build_historical_backtest_run()` once per segment -- this module builds
no second backtesting engine, only deterministic dataset slicing and
cross-segment comparison. No live brokerage order is placed. No claim of
profitability or live-trading readiness is made anywhere in this module.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from empirical_platform.decision_candidate.historical_backtest import (
    DEFAULT_COST_MODEL,
    DEFAULT_EXECUTION_ASSUMPTION,
    DEFAULT_OUTCOME_MODEL,
    HistoricalBacktestRun,
    HistoricalCostModel,
    HistoricalDataset,
    HistoricalDatasetAuthority,
    HistoricalExecutionAssumption,
    HistoricalInstrumentSeries,
    HistoricalOutcomeModel,
    build_historical_backtest_run,
    dataset_sha256,
)
from empirical_platform.decision_candidate.market_data import BarInterval, Instrument
from empirical_platform.decision_candidate.position_plan import (
    DEFAULT_SIZING_POLICY,
    PositionSizingContext,
    SizingPolicy,
)
from empirical_platform.decision_candidate.trade_plan import DEFAULT_RISK_POLICY, RiskPolicy
from empirical_platform.identifiers.pairs import DomainIdentity
from empirical_platform.identifiers.types import BacktestRunId, DatasetId, ValidationStudyId
from empirical_platform.shared.identifiers import RuntimeIdentifier, RuntimeIdentifierGenerator

SURVIVORSHIP_BIAS_DISCLOSURE = "SURVIVORSHIP_BIAS_NOT_ADDRESSED"

# Deliberately coarser than the corresponding PostgreSQL NUMERIC column
# precision (`_PRICE`=6dp/`_RATIO`=15dp in the M062 migration) -- used only
# to make post-round-trip comparisons tolerant of the two mathematically
# different rounding paths ("round each operand to column precision, then
# subtract" vs. "subtract at full in-memory precision, then round the
# result"), which can legitimately disagree by one unit in the column's
# own last decimal place. Never used to change any in-memory computation.
_NET_PNL_QUANTUM = Decimal("0.0001")
_RATIO_QUANTUM = Decimal("0.0000000001")


def _quantized_equal(left: Decimal, right: Decimal, quantum: Decimal) -> bool:
    return left.quantize(quantum) == right.quantize(quantum)


class ValidationSegmentRole(StrEnum):
    """Closed segment-role vocabulary. Exactly one DEVELOPMENT_REFERENCE and
    exactly two HOLDOUT segments are required per study -- see
    `_validate_bundle_segments()`."""

    DEVELOPMENT_REFERENCE = "DEVELOPMENT_REFERENCE"
    HOLDOUT_1 = "HOLDOUT_1"
    HOLDOUT_2 = "HOLDOUT_2"


_REQUIRED_SEGMENT_ROLE_ORDER = (
    ValidationSegmentRole.DEVELOPMENT_REFERENCE,
    ValidationSegmentRole.HOLDOUT_1,
    ValidationSegmentRole.HOLDOUT_2,
)


class HistoricalValidationStudyStatus(StrEnum):
    """Closed lifecycle vocabulary for an immutable validation study."""

    STUDY_COMPLETED = "STUDY_COMPLETED"


class HistoricalValidationStudyClassification(StrEnum):
    """Allowed post-study product statements.

    Deliberately excludes any claim of profitability, validation, or
    live-trading readiness (MILESTONE-062 Phase 11) -- this module records
    evidence, it does not certify performance.
    """

    HOLDOUT_RESULTS_RECORDED = "HOLDOUT_RESULTS_RECORDED"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


@dataclass(frozen=True, slots=True)
class ValidationSegmentSpec:
    """One caller-declared segment definition: role plus a private,
    non-overlapping bar-block sizing within the dataset bundle's own
    canonical timestamp grid.

    `warmup_bar_count` bars provide DATA_CONTEXT only (the M057 reference
    window) and are never scored as decision cutoffs. `scoring_bar_count`
    bars each produce exactly one scored decision cutoff -- the
    SCORING_PERIOD. `buffer_bar_count` trailing bars exist only so M061's
    own holding-horizon exit-resolution logic has bars to inspect for
    trades opened near the segment's end, and are likewise never scored.
    See MILESTONE_062 scope Section 6.
    """

    segment_id: str
    role: ValidationSegmentRole
    warmup_bar_count: int
    scoring_bar_count: int
    buffer_bar_count: int

    def __post_init__(self) -> None:
        if not self.segment_id.strip():
            raise ValueError("segment_id must be non-empty")
        if self.warmup_bar_count < 0:
            raise ValueError("warmup_bar_count must not be negative")
        if self.scoring_bar_count < 1:
            raise ValueError("scoring_bar_count must be at least 1 (an empty segment is rejected)")
        if self.buffer_bar_count < 0:
            raise ValueError("buffer_bar_count must not be negative")

    @property
    def total_bar_count(self) -> int:
        return self.warmup_bar_count + self.scoring_bar_count + self.buffer_bar_count


@dataclass(frozen=True, slots=True)
class ValidationDatasetBundleAuthority:
    """Immutable identity and checksum record for a multi-period dataset
    bundle."""

    dataset_bundle_id: DatasetId
    dataset_bundle_version: str
    source_kind: str
    sha256: str
    interval: BarInterval
    instrument_count: int
    total_bars_per_instrument: int

    def __post_init__(self) -> None:
        if not self.dataset_bundle_version.strip():
            raise ValueError("dataset_bundle_version must be non-empty")
        if not self.source_kind.strip():
            raise ValueError("source_kind must be non-empty")
        if len(self.sha256) != 64:
            raise ValueError("sha256 must be a full SHA-256 hex digest")
        if self.instrument_count < 1:
            raise ValueError("instrument_count must be at least 1")
        if self.total_bars_per_instrument < 1:
            raise ValueError("total_bars_per_instrument must be at least 1")


@dataclass(frozen=True, slots=True)
class ValidationDatasetBundle:
    """One fixed, locally reproducible multi-period validation dataset,
    already segmented into caller-declared, ordered `ValidationSegmentSpec`
    blocks over one canonical, continuous per-instrument bar grid.
    """

    authority: ValidationDatasetBundleAuthority
    segment_specs: tuple[ValidationSegmentSpec, ...]
    series: tuple[HistoricalInstrumentSeries, ...]

    def __post_init__(self) -> None:
        if len(self.series) < 1:
            raise ValueError("a dataset bundle must contain at least 1 instrument")
        if len(self.series) != self.authority.instrument_count:
            raise ValueError("authority instrument_count does not match the supplied series")
        seen: set[Instrument] = set()
        canonical_timestamps = tuple(bar.timestamp for bar in self.series[0].bars)
        for series in self.series:
            if series.instrument in seen:
                raise ValueError(f"duplicate instrument in dataset bundle: {series.instrument}")
            seen.add(series.instrument)
            if series.interval != self.authority.interval:
                raise ValueError("all instrument series must share the authority's own interval")
            timestamps = tuple(bar.timestamp for bar in series.bars)
            if timestamps != canonical_timestamps:
                raise ValueError("all instrument series must share one canonical timestamp grid")
        if len(canonical_timestamps) != self.authority.total_bars_per_instrument:
            raise ValueError(
                "authority total_bars_per_instrument does not match the supplied series"
            )
        if len(self.segment_specs) < 1:
            raise ValueError("a dataset bundle must declare at least 1 segment")
        ids = [spec.segment_id for spec in self.segment_specs]
        if len(set(ids)) != len(ids):
            raise ValueError("segment_id values must be unique within a dataset bundle")


@dataclass(frozen=True, slots=True)
class ValidationSegment:
    """One immutable, resolved segment boundary -- both the DATA_CONTEXT
    range actually fed to M061 (`data_start_timestamp`/`data_end_timestamp`)
    and the narrower SCORING_PERIOD range whose decision cutoffs were
    actually scored (`scoring_start_timestamp`/`scoring_end_timestamp`).
    """

    segment_id: str
    role: ValidationSegmentRole
    data_start_timestamp: datetime
    data_end_timestamp: datetime
    scoring_start_timestamp: datetime
    scoring_end_timestamp: datetime
    warmup_bar_count: int
    scoring_bar_count: int
    buffer_bar_count: int

    def __post_init__(self) -> None:
        for field_name in (
            "data_start_timestamp",
            "data_end_timestamp",
            "scoring_start_timestamp",
            "scoring_end_timestamp",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, datetime) or value.tzinfo is None:
                raise ValueError(f"{field_name} must be a timezone-aware datetime")
        if self.data_start_timestamp > self.scoring_start_timestamp:
            raise ValueError("scoring_start_timestamp must not precede data_start_timestamp")
        if self.scoring_start_timestamp > self.scoring_end_timestamp:
            raise ValueError("scoring_start_timestamp must not be after scoring_end_timestamp")
        if self.scoring_end_timestamp > self.data_end_timestamp:
            raise ValueError("scoring_end_timestamp must not be after data_end_timestamp")


@dataclass(frozen=True, slots=True)
class ValidationSegmentResult:
    """One segment's resolved M061 backtest reference plus a copied summary
    of its own metrics, for study-level comparison without a join. Full
    per-trade detail remains independently retrievable through the
    unmodified M061 `get_historical_backtest_run` CLI via
    `backtest_run_id`/`backtest_run_runtime_id`."""

    segment: ValidationSegment
    backtest_run_id: BacktestRunId
    backtest_run_runtime_id: RuntimeIdentifier
    evaluated_cutoff_count: int
    simulated_trade_count: int
    executed_trade_count: int
    win_count: int
    loss_count: int
    time_exit_count: int
    no_entry_count: int
    gross_pnl: Decimal
    net_pnl: Decimal
    average_net_pnl: Decimal | None
    average_r: Decimal | None
    total_r: Decimal
    win_rate: Decimal | None
    profit_factor: Decimal | None
    maximum_realized_pnl_drawdown: Decimal | None


@dataclass(frozen=True, slots=True)
class HistoricalValidationStudy:
    """One immutable, persisted, cross-period validation study: one
    DEVELOPMENT_REFERENCE segment plus two independent HOLDOUT segments,
    each executed through the unmodified M061 engine, compared
    descriptively.

    Deliberately NOT a lifecycle aggregate, mirroring `HistoricalBacktestRun`
    (M061) and every non-lifecycle record since M057: a study is a fact
    computed once from a fixed dataset bundle and never mutated afterward.
    """

    identity: DomainIdentity[ValidationStudyId]
    dataset_bundle_id: DatasetId
    dataset_bundle_version: str
    dataset_bundle_sha256: str
    dataset_source_kind: str
    interval: BarInterval
    instrument_universe: tuple[Instrument, ...]
    reference_window_size: int
    strategy_id: str
    strategy_version: str
    ranking_model_id: str
    ranking_model_version: str
    risk_policy_id: str
    risk_policy_version: str
    sizing_policy_id: str
    sizing_policy_version: str
    execution_assumption_id: str
    execution_assumption_version: str
    outcome_model_id: str
    outcome_model_version: str
    cost_model_id: str
    cost_model_version: str
    holding_horizon_bars: int
    supplied_account_equity: Decimal
    supplied_risk_percent: Decimal
    survivorship_bias_disclosure: str
    status: HistoricalValidationStudyStatus
    classification: HistoricalValidationStudyClassification
    development: ValidationSegmentResult
    holdout_1: ValidationSegmentResult
    holdout_2: ValidationSegmentResult
    holdout_1_net_pnl_delta: Decimal
    holdout_1_total_r_delta: Decimal
    holdout_2_net_pnl_delta: Decimal
    holdout_2_total_r_delta: Decimal

    def __post_init__(self) -> None:
        if not isinstance(self.identity, DomainIdentity):
            raise TypeError("identity must be a DomainIdentity[ValidationStudyId]")
        if not isinstance(self.identity.governance_id, ValidationStudyId):
            raise TypeError("identity governance_id must be a ValidationStudyId")
        for field_name in (
            "dataset_bundle_version",
            "dataset_source_kind",
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
            "survivorship_bias_disclosure",
        ):
            if not getattr(self, field_name).strip():
                raise ValueError(f"{field_name} must be non-empty")
        if len(self.dataset_bundle_sha256) != 64:
            raise ValueError("dataset_bundle_sha256 must be a full SHA-256 hex digest")
        if self.development.segment.role is not ValidationSegmentRole.DEVELOPMENT_REFERENCE:
            raise ValueError("development segment must carry the DEVELOPMENT_REFERENCE role")
        if self.holdout_1.segment.role is not ValidationSegmentRole.HOLDOUT_1:
            raise ValueError("holdout_1 segment must carry the HOLDOUT_1 role")
        if self.holdout_2.segment.role is not ValidationSegmentRole.HOLDOUT_2:
            raise ValueError("holdout_2 segment must carry the HOLDOUT_2 role")
        if (
            self.development.segment.data_end_timestamp
            >= self.holdout_1.segment.data_start_timestamp
        ):
            raise ValueError("development and holdout_1 segments must be chronologically disjoint")
        if self.holdout_1.segment.data_end_timestamp >= self.holdout_2.segment.data_start_timestamp:
            raise ValueError("holdout_1 and holdout_2 segments must be chronologically disjoint")
        # Quantized comparisons, not raw `==`: `net_pnl`/`total_r` and the
        # deltas derived from them are each stored independently in
        # PostgreSQL (NUMERIC(18,6)/NUMERIC(30,15) respectively) and
        # retrieved as separately-rounded Decimals -- the same
        # storage-precision pattern established in M058/M059 (a raw `==`
        # would spuriously fail after a genuine round-trip even though the
        # values were computed correctly at construction time, in-memory,
        # with full precision).
        if not _quantized_equal(
            self.holdout_1_net_pnl_delta,
            self.holdout_1.net_pnl - self.development.net_pnl,
            _NET_PNL_QUANTUM,
        ):
            raise ValueError(
                "holdout_1_net_pnl_delta must equal holdout_1.net_pnl - development.net_pnl"
            )
        if not _quantized_equal(
            self.holdout_1_total_r_delta,
            self.holdout_1.total_r - self.development.total_r,
            _RATIO_QUANTUM,
        ):
            raise ValueError(
                "holdout_1_total_r_delta must equal holdout_1.total_r - development.total_r"
            )
        if not _quantized_equal(
            self.holdout_2_net_pnl_delta,
            self.holdout_2.net_pnl - self.development.net_pnl,
            _NET_PNL_QUANTUM,
        ):
            raise ValueError(
                "holdout_2_net_pnl_delta must equal holdout_2.net_pnl - development.net_pnl"
            )
        if not _quantized_equal(
            self.holdout_2_total_r_delta,
            self.holdout_2.total_r - self.development.total_r,
            _RATIO_QUANTUM,
        ):
            raise ValueError(
                "holdout_2_total_r_delta must equal holdout_2.total_r - development.total_r"
            )


def _segment_bar_ranges(
    segment_specs: tuple[ValidationSegmentSpec, ...],
) -> tuple[tuple[int, int], ...]:
    """Return the [start, end) bar-index range for each segment, in
    declared order, as contiguous, non-overlapping blocks starting at
    index 0 -- no segment's dataset ever shares a bar with another's."""
    ranges = []
    cursor = 0
    for spec in segment_specs:
        start = cursor
        end = cursor + spec.total_bar_count
        ranges.append((start, end))
        cursor = end
    return tuple(ranges)


def _validate_bundle_segments(
    bundle: ValidationDatasetBundle,
    *,
    reference_window_size: int,
    outcome_model: HistoricalOutcomeModel,
) -> None:
    specs = bundle.segment_specs
    if len(specs) != 3:
        raise ValueError(
            "a validation study requires exactly 3 segments: 1 development reference + 2 holdouts"
        )
    roles = tuple(spec.role for spec in specs)
    if roles != _REQUIRED_SEGMENT_ROLE_ORDER:
        raise ValueError(
            "segments must be declared in order DEVELOPMENT_REFERENCE, HOLDOUT_1, HOLDOUT_2"
        )
    for spec in specs:
        if spec.warmup_bar_count != reference_window_size:
            raise ValueError(
                f"segment {spec.segment_id!r} warmup_bar_count ({spec.warmup_bar_count}) must "
                f"equal reference_window_size ({reference_window_size})"
            )
        if spec.buffer_bar_count != outcome_model.holding_horizon_bars:
            raise ValueError(
                f"segment {spec.segment_id!r} buffer_bar_count ({spec.buffer_bar_count}) must "
                f"equal outcome_model.holding_horizon_bars ({outcome_model.holding_horizon_bars})"
            )
    total_declared = sum(spec.total_bar_count for spec in specs)
    bundle_bars = len(bundle.series[0].bars)
    if total_declared != bundle_bars:
        raise ValueError(
            f"sum of segment bar counts ({total_declared}) must equal the bundle's own "
            f"per-instrument bar count ({bundle_bars}) -- a declared segment range falls "
            "outside the dataset"
        )


def _segment_dataset(bundle: ValidationDatasetBundle, *, segment_index: int) -> HistoricalDataset:
    """Slice one segment's own private, non-overlapping bar block out of the
    bundle's full per-instrument series, and wrap it in a standalone
    `HistoricalDataset` for the M061 engine. This is the only place a
    segment's bars are ever read -- no segment's dataset ever includes a
    bar belonging to another segment."""
    start, end = _segment_bar_ranges(bundle.segment_specs)[segment_index]
    sliced_series = tuple(
        HistoricalInstrumentSeries(instrument=series.instrument, bars=series.bars[start:end])
        for series in bundle.series
    )
    first_bars = sliced_series[0].bars
    fingerprint = "|".join(
        f"{series.instrument}:{bar.timestamp.isoformat()}:{bar.open}:{bar.high}:{bar.low}:{bar.close}:{bar.volume}"
        for series in sliced_series
        for bar in series.bars
    ).encode("utf-8")
    authority = HistoricalDatasetAuthority(
        dataset_id=bundle.authority.dataset_bundle_id,
        dataset_version=f"{bundle.authority.dataset_bundle_version}-segment-{segment_index}",
        source_kind=bundle.authority.source_kind,
        interval=bundle.authority.interval,
        start_timestamp=first_bars[0].timestamp,
        end_timestamp=first_bars[-1].timestamp,
        total_bars=sum(len(series.bars) for series in sliced_series),
        instrument_count=len(sliced_series),
        sha256=dataset_sha256(fingerprint),
    )
    return HistoricalDataset(authority=authority, series=sliced_series)


def build_validation_study(
    *,
    identity: DomainIdentity[ValidationStudyId],
    bundle: ValidationDatasetBundle,
    sizing_context: PositionSizingContext,
    runtime_identifier_generator: RuntimeIdentifierGenerator,
    backtest_run_identity_for: Callable[[str], DomainIdentity[BacktestRunId]],
    reference_window_size: int = 5,
    risk_policy: RiskPolicy = DEFAULT_RISK_POLICY,
    sizing_policy: SizingPolicy = DEFAULT_SIZING_POLICY,
    execution_assumption: HistoricalExecutionAssumption = DEFAULT_EXECUTION_ASSUMPTION,
    outcome_model: HistoricalOutcomeModel = DEFAULT_OUTCOME_MODEL,
    cost_model: HistoricalCostModel = DEFAULT_COST_MODEL,
) -> tuple[HistoricalValidationStudy, tuple[HistoricalBacktestRun, ...]]:
    """Build one immutable `HistoricalValidationStudy` by running the real,
    unmodified M061 `build_historical_backtest_run()` once per declared
    segment, over that segment's own private bar slice.

    `backtest_run_identity_for` lets the caller mint each segment's own
    `BacktestRunId`/runtime identity (mirroring M061's own
    identity-injection style) -- this function performs no persistence of
    its own, only pure computation, matching `build_historical_backtest_run`
    (M061) and `build_scan`/`build_trade_plan` (M058/M059) before it.

    Returns both the study and the tuple of per-segment `HistoricalBacktestRun`
    objects (in DEVELOPMENT_REFERENCE, HOLDOUT_1, HOLDOUT_2 order) so a
    caller can persist each one through the unmodified M061 repository,
    preserving full per-trade auditability for every segment.
    """
    _validate_bundle_segments(
        bundle, reference_window_size=reference_window_size, outcome_model=outcome_model
    )

    ranges = _segment_bar_ranges(bundle.segment_specs)
    runs: list[HistoricalBacktestRun] = []
    segment_results: list[ValidationSegmentResult] = []

    for index, spec in enumerate(bundle.segment_specs):
        dataset = _segment_dataset(bundle, segment_index=index)
        run_identity = backtest_run_identity_for(spec.segment_id)
        run = build_historical_backtest_run(
            identity=run_identity,
            dataset=dataset,
            sizing_context=sizing_context,
            runtime_identifier_generator=runtime_identifier_generator,
            reference_window_size=reference_window_size,
            risk_policy=risk_policy,
            sizing_policy=sizing_policy,
            execution_assumption=execution_assumption,
            outcome_model=outcome_model,
            cost_model=cost_model,
        )
        runs.append(run)

        start, end = ranges[index]
        all_bars = bundle.series[0].bars[start:end]
        warmup_end_idx = spec.warmup_bar_count
        scoring_end_idx = spec.warmup_bar_count + spec.scoring_bar_count
        segment = ValidationSegment(
            segment_id=spec.segment_id,
            role=spec.role,
            data_start_timestamp=all_bars[0].timestamp,
            data_end_timestamp=all_bars[-1].timestamp,
            scoring_start_timestamp=all_bars[warmup_end_idx].timestamp,
            scoring_end_timestamp=all_bars[scoring_end_idx - 1].timestamp,
            warmup_bar_count=spec.warmup_bar_count,
            scoring_bar_count=spec.scoring_bar_count,
            buffer_bar_count=spec.buffer_bar_count,
        )
        segment_results.append(
            ValidationSegmentResult(
                segment=segment,
                backtest_run_id=run.identity.governance_id,
                backtest_run_runtime_id=run.identity.runtime_id,
                evaluated_cutoff_count=run.evaluated_cutoff_count,
                simulated_trade_count=run.simulated_trade_count,
                executed_trade_count=run.executed_trade_count,
                win_count=run.win_count,
                loss_count=run.loss_count,
                time_exit_count=run.time_exit_count,
                no_entry_count=run.no_entry_count,
                gross_pnl=run.gross_pnl,
                net_pnl=run.net_pnl,
                average_net_pnl=run.average_net_pnl,
                average_r=run.average_r,
                total_r=run.total_r,
                win_rate=run.win_rate,
                profit_factor=run.profit_factor,
                maximum_realized_pnl_drawdown=run.maximum_realized_pnl_drawdown,
            )
        )

    development, holdout_1, holdout_2 = segment_results
    classification = (
        HistoricalValidationStudyClassification.HOLDOUT_RESULTS_RECORDED
        if holdout_1.executed_trade_count > 0 and holdout_2.executed_trade_count > 0
        else HistoricalValidationStudyClassification.INSUFFICIENT_EVIDENCE
    )
    reference_run = runs[0]
    study = HistoricalValidationStudy(
        identity=identity,
        dataset_bundle_id=bundle.authority.dataset_bundle_id,
        dataset_bundle_version=bundle.authority.dataset_bundle_version,
        dataset_bundle_sha256=bundle.authority.sha256,
        dataset_source_kind=bundle.authority.source_kind,
        interval=bundle.authority.interval,
        instrument_universe=tuple(sorted((series.instrument for series in bundle.series), key=str)),
        reference_window_size=reference_window_size,
        strategy_id=reference_run.strategy_id,
        strategy_version=reference_run.strategy_version,
        ranking_model_id=reference_run.ranking_model_id,
        ranking_model_version=reference_run.ranking_model_version,
        risk_policy_id=reference_run.risk_policy_id,
        risk_policy_version=reference_run.risk_policy_version,
        sizing_policy_id=reference_run.sizing_policy_id,
        sizing_policy_version=reference_run.sizing_policy_version,
        execution_assumption_id=reference_run.execution_assumption_id,
        execution_assumption_version=reference_run.execution_assumption_version,
        outcome_model_id=reference_run.outcome_model_id,
        outcome_model_version=reference_run.outcome_model_version,
        cost_model_id=reference_run.cost_model_id,
        cost_model_version=reference_run.cost_model_version,
        holding_horizon_bars=reference_run.holding_horizon_bars,
        supplied_account_equity=sizing_context.account_equity,
        supplied_risk_percent=sizing_context.risk_percent,
        survivorship_bias_disclosure=SURVIVORSHIP_BIAS_DISCLOSURE,
        status=HistoricalValidationStudyStatus.STUDY_COMPLETED,
        classification=classification,
        development=development,
        holdout_1=holdout_1,
        holdout_2=holdout_2,
        holdout_1_net_pnl_delta=holdout_1.net_pnl - development.net_pnl,
        holdout_1_total_r_delta=holdout_1.total_r - development.total_r,
        holdout_2_net_pnl_delta=holdout_2.net_pnl - development.net_pnl,
        holdout_2_total_r_delta=holdout_2.total_r - development.total_r,
    )
    return study, tuple(runs)
