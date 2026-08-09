"""Broader historical robustness study: when the frozen M057-M062 trading
stack is evaluated across substantially more historical observations, more
instruments, and more chronological windows, what remains stable, what
degrades, and where does it fail?

MILESTONE-063. M062 proved strict temporal isolation across exactly three
segments, over a deliberately small canonical fixture (4 instruments, 48
bars). This module generalizes that same isolation model to an arbitrary,
caller-declared sequence of N chronological windows -- a genuine
walk-forward *evaluation* sequence, never a walk-forward *optimization*
loop: the identical frozen M057-M062 policy stack runs, unmodified, across
every window. No parameter is ever fitted, tuned, or adjusted between
windows, and no window is ever discarded because it lost money.

Every window's backtest is executed by calling the real, unmodified M061
`build_historical_backtest_run()` once per window -- this module builds no
second backtesting engine, only deterministic dataset slicing,
post-hoc-only regime labeling, and transparent cross-window descriptive
statistics (never an opaque "robustness score"). No live brokerage order
is placed. No claim of profitability, live-trading readiness, or resolved
survivorship bias is made anywhere in this module.
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
from empirical_platform.identifiers.types import BacktestRunId, DatasetId, RobustnessStudyId
from empirical_platform.shared.identifiers import RuntimeIdentifier, RuntimeIdentifierGenerator

SURVIVORSHIP_BIAS_DISCLOSURE = "SURVIVORSHIP_BIAS_NOT_ADDRESSED"
REGIME_POLICY_ID = "POST_HOC_REALIZED_VOLATILITY_TERTILE"
REGIME_POLICY_VERSION = "1"
MINIMUM_SAMPLE_EXECUTED_TRADES = 15


class RegimeLabel(StrEnum):
    """Closed, post-hoc-only vocabulary. Computed exclusively from each
    window's own already-completed scoring bars, entirely after every
    window's trading decisions and outcomes are already final -- never fed
    back into any decision. See `_classify_regimes()`."""

    LOW_VOLATILITY = "LOW_VOLATILITY"
    NORMAL_VOLATILITY = "NORMAL_VOLATILITY"
    HIGH_VOLATILITY = "HIGH_VOLATILITY"


class RobustnessStudyStatus(StrEnum):
    """Closed lifecycle vocabulary for an immutable robustness study."""

    STUDY_COMPLETED = "STUDY_COMPLETED"


class RobustnessStudyClassification(StrEnum):
    """Allowed post-study product statements, chosen by an explicit,
    deterministic rule (`_classify_study()`) -- never a subjective
    judgment. Deliberately excludes any claim of profitability, a proven
    edge, or live-trading readiness."""

    INSUFFICIENT_SAMPLE = "INSUFFICIENT_SAMPLE"
    ROBUSTNESS_EVIDENCE_RECORDED = "ROBUSTNESS_EVIDENCE_RECORDED"
    ROBUSTNESS_EVIDENCE_MIXED = "ROBUSTNESS_EVIDENCE_MIXED"
    ROBUSTNESS_EVIDENCE_WEAK = "ROBUSTNESS_EVIDENCE_WEAK"


@dataclass(frozen=True, slots=True)
class RobustnessWindowSpec:
    """One caller-declared window definition: a private, non-overlapping
    bar-block sizing, identical in shape to M062's own per-segment model
    (warmup/scoring/buffer), positioned by `sequence_index` rather than a
    fixed role. `sequence_index` is the sole ordering authority -- window
    declaration (list) order is never trusted (Phase 25: no caller
    window-order dependence)."""

    window_id: str
    sequence_index: int
    warmup_bar_count: int
    scoring_bar_count: int
    buffer_bar_count: int

    def __post_init__(self) -> None:
        if not self.window_id.strip():
            raise ValueError("window_id must be non-empty")
        if self.sequence_index < 0:
            raise ValueError("sequence_index must not be negative")
        if self.warmup_bar_count < 0:
            raise ValueError("warmup_bar_count must not be negative")
        if self.scoring_bar_count < 1:
            raise ValueError("scoring_bar_count must be at least 1 (an empty window is rejected)")
        if self.buffer_bar_count < 0:
            raise ValueError("buffer_bar_count must not be negative")

    @property
    def total_bar_count(self) -> int:
        return self.warmup_bar_count + self.scoring_bar_count + self.buffer_bar_count


@dataclass(frozen=True, slots=True)
class RobustnessDatasetBundleAuthority:
    """Immutable identity and checksum record for a broad, multi-window
    robustness dataset bundle."""

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
class RobustnessUniverseAuthority:
    """Immutable authority record for the study's declared instrument universe."""

    universe_id: str
    universe_version: str
    membership_model: str
    constituents: tuple[Instrument, ...]

    def __post_init__(self) -> None:
        for field_name in ("universe_id", "universe_version", "membership_model"):
            if not getattr(self, field_name).strip():
                raise ValueError(f"{field_name} must be non-empty")
        if len(self.constituents) < 1:
            raise ValueError("constituents must contain at least 1 instrument")
        if len(set(self.constituents)) != len(self.constituents):
            raise ValueError("constituents must not contain duplicates")
        if tuple(sorted(self.constituents, key=str)) != self.constituents:
            raise ValueError("constituents must be sorted canonically")


@dataclass(frozen=True, slots=True)
class RobustnessDatasetBundle:
    """One fixed, locally reproducible, broad multi-window robustness
    dataset, already segmented into caller-declared `RobustnessWindowSpec`
    blocks over one canonical, continuous per-instrument bar grid."""

    authority: RobustnessDatasetBundleAuthority
    universe_authority: RobustnessUniverseAuthority
    window_specs: tuple[RobustnessWindowSpec, ...]
    series: tuple[HistoricalInstrumentSeries, ...]

    def __post_init__(self) -> None:
        if len(self.series) < 1:
            raise ValueError("a dataset bundle must contain at least 1 instrument")
        if len(self.series) != self.authority.instrument_count:
            raise ValueError("authority instrument_count does not match the supplied series")
        seen_instruments: set[Instrument] = set()
        canonical_timestamps = tuple(bar.timestamp for bar in self.series[0].bars)
        for series in self.series:
            if series.instrument in seen_instruments:
                raise ValueError(f"duplicate instrument in dataset bundle: {series.instrument}")
            seen_instruments.add(series.instrument)
            if series.interval != self.authority.interval:
                raise ValueError("all instrument series must share the authority's own interval")
            timestamps = tuple(bar.timestamp for bar in series.bars)
            if timestamps != canonical_timestamps:
                raise ValueError("all instrument series must share one canonical timestamp grid")
        if len(canonical_timestamps) != self.authority.total_bars_per_instrument:
            raise ValueError(
                "authority total_bars_per_instrument does not match the supplied series"
            )
        canonical_constituents = tuple(sorted(seen_instruments, key=str))
        if self.universe_authority.constituents != canonical_constituents:
            raise ValueError(
                "universe authority constituents must match the supplied instrument series"
            )
        if len(self.window_specs) < 1:
            raise ValueError("a dataset bundle must declare at least 1 window")
        ids = [spec.window_id for spec in self.window_specs]
        if len(set(ids)) != len(ids):
            raise ValueError("window_id values must be unique within a dataset bundle")
        sequence_indexes = [spec.sequence_index for spec in self.window_specs]
        if len(set(sequence_indexes)) != len(sequence_indexes):
            raise ValueError("sequence_index values must be unique within a dataset bundle")
        if sorted(sequence_indexes) != list(range(len(self.window_specs))):
            raise ValueError("sequence_index values must form a contiguous 0..N-1 sequence")

    @property
    def ordered_window_specs(self) -> tuple[RobustnessWindowSpec, ...]:
        """Windows sorted by `sequence_index` -- the sole ordering
        authority, independent of this tuple's own declaration order."""
        return tuple(sorted(self.window_specs, key=lambda spec: spec.sequence_index))


@dataclass(frozen=True, slots=True)
class RobustnessWindow:
    """One immutable, resolved window boundary -- both the DATA_CONTEXT
    range actually fed to M061 and the narrower SCORING_PERIOD range whose
    decision cutoffs were actually scored."""

    window_id: str
    sequence_index: int
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
class RobustnessWindowResult:
    """One window's resolved M061 backtest reference plus a copied summary
    of its own metrics and its post-hoc regime label. Full per-trade detail
    remains independently retrievable through the unmodified M061
    `get_historical_backtest_run` CLI."""

    window: RobustnessWindow
    backtest_run_id: BacktestRunId
    backtest_run_runtime_id: RuntimeIdentifier
    regime_label: RegimeLabel
    realized_volatility: Decimal
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
class WindowExtreme:
    """A window identity plus one of its own scalar metric values --
    used for best/worst-window reporting (Phase 28: outlier-window
    analysis)."""

    window_id: str
    value: Decimal


@dataclass(frozen=True, slots=True)
class RegimeBreakdownEntry:
    """One post-hoc regime's aggregate evidence -- computed identically at
    study-construction time and at retrieval time from the same
    `window_results`, never independently persisted (Phase 18: regime
    breakdown)."""

    regime_label: RegimeLabel
    window_count: int
    executed_trade_count: int
    net_pnl_total: Decimal
    total_r_total: Decimal
    positive_window_count: int
    negative_window_count: int


@dataclass(frozen=True, slots=True)
class HistoricalRobustnessStudy:
    """One immutable, persisted, broad multi-window robustness study.

    Deliberately NOT a lifecycle aggregate, mirroring `HistoricalBacktestRun`
    (M061) and `HistoricalValidationStudy` (M062): a study is a fact
    computed once from a fixed dataset bundle and never mutated afterward.
    """

    identity: DomainIdentity[RobustnessStudyId]
    dataset_bundle_id: DatasetId
    dataset_bundle_version: str
    dataset_bundle_sha256: str
    dataset_source_kind: str
    universe_id: str
    universe_version: str
    universe_membership_model: str
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
    regime_policy_id: str
    regime_policy_version: str
    survivorship_bias_disclosure: str
    status: RobustnessStudyStatus
    classification: RobustnessStudyClassification
    window_results: tuple[RobustnessWindowResult, ...]
    window_count: int
    total_evaluated_cutoff_count: int
    total_simulated_trade_count: int
    total_executed_trade_count: int
    positive_net_pnl_window_count: int
    negative_net_pnl_window_count: int
    positive_total_r_window_count: int
    negative_total_r_window_count: int
    median_window_net_pnl: Decimal
    median_window_total_r: Decimal
    best_window_by_net_pnl: WindowExtreme
    worst_window_by_net_pnl: WindowExtreme
    best_window_by_total_r: WindowExtreme
    worst_window_by_total_r: WindowExtreme
    all_window_net_pnl_total: Decimal
    all_window_total_r_total: Decimal
    excluding_best_window_net_pnl_total: Decimal
    excluding_best_window_total_r_total: Decimal
    largest_positive_window_share_of_positive_pnl: Decimal | None
    largest_negative_window_share_of_absolute_negative_pnl: Decimal | None

    def __post_init__(self) -> None:
        if not isinstance(self.identity, DomainIdentity):
            raise TypeError("identity must be a DomainIdentity[RobustnessStudyId]")
        if not isinstance(self.identity.governance_id, RobustnessStudyId):
            raise TypeError("identity governance_id must be a RobustnessStudyId")
        for field_name in (
            "dataset_bundle_version",
            "dataset_source_kind",
            "universe_id",
            "universe_version",
            "universe_membership_model",
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
            "regime_policy_id",
            "regime_policy_version",
            "survivorship_bias_disclosure",
        ):
            if not getattr(self, field_name).strip():
                raise ValueError(f"{field_name} must be non-empty")
        if len(self.dataset_bundle_sha256) != 64:
            raise ValueError("dataset_bundle_sha256 must be a full SHA-256 hex digest")
        if self.window_count < 1:
            raise ValueError("window_count must be at least 1")
        if len(self.window_results) != self.window_count:
            raise ValueError("window_count must match the persisted window_results count")
        sequence_indexes = [result.window.sequence_index for result in self.window_results]
        if sequence_indexes != sorted(sequence_indexes):
            raise ValueError("window_results must be ordered by sequence_index")
        if sequence_indexes != list(range(self.window_count)):
            raise ValueError("window sequence_index values must be a contiguous 0..N-1 sequence")
        for previous, current in zip(self.window_results, self.window_results[1:], strict=False):
            if previous.window.data_end_timestamp >= current.window.data_start_timestamp:
                raise ValueError("windows must be chronologically disjoint and strictly ordered")


def regime_breakdown(
    window_results: tuple[RobustnessWindowResult, ...],
) -> tuple[RegimeBreakdownEntry, ...]:
    """Group already-computed window results by their own post-hoc regime
    label -- a pure, derived view, never separately persisted. Called
    identically at study-construction time and at repository retrieval
    time, so the two can never drift."""
    labels_seen: list[RegimeLabel] = []
    for result in window_results:
        if result.regime_label not in labels_seen:
            labels_seen.append(result.regime_label)
    entries = []
    for label in labels_seen:
        matching = [result for result in window_results if result.regime_label is label]
        entries.append(
            RegimeBreakdownEntry(
                regime_label=label,
                window_count=len(matching),
                executed_trade_count=sum(result.executed_trade_count for result in matching),
                net_pnl_total=sum((result.net_pnl for result in matching), Decimal("0")),
                total_r_total=sum((result.total_r for result in matching), Decimal("0")),
                positive_window_count=sum(1 for result in matching if result.net_pnl > 0),
                negative_window_count=sum(1 for result in matching if result.net_pnl < 0),
            )
        )
    return tuple(entries)


def _median(values: tuple[Decimal, ...]) -> Decimal:
    ordered = sorted(values)
    count = len(ordered)
    midpoint = count // 2
    if count % 2 == 1:
        return ordered[midpoint]
    return (ordered[midpoint - 1] + ordered[midpoint]) / 2


def _window_bar_ranges(specs: tuple[RobustnessWindowSpec, ...]) -> tuple[tuple[int, int], ...]:
    """Return the [start, end) bar-index range for each window, in
    `sequence_index` order (never caller-declaration order), as
    contiguous, non-overlapping blocks starting at index 0 -- no window's
    dataset ever shares a bar with another's."""
    ranges = []
    cursor = 0
    for spec in sorted(specs, key=lambda spec: spec.sequence_index):
        start = cursor
        end = cursor + spec.total_bar_count
        ranges.append((start, end))
        cursor = end
    return tuple(ranges)


def _validate_bundle_windows(
    bundle: RobustnessDatasetBundle,
    *,
    reference_window_size: int,
    outcome_model: HistoricalOutcomeModel,
) -> None:
    specs = bundle.ordered_window_specs
    for spec in specs:
        if spec.warmup_bar_count != reference_window_size:
            raise ValueError(
                f"window {spec.window_id!r} warmup_bar_count ({spec.warmup_bar_count}) must "
                f"equal reference_window_size ({reference_window_size})"
            )
        if spec.buffer_bar_count != outcome_model.holding_horizon_bars:
            raise ValueError(
                f"window {spec.window_id!r} buffer_bar_count ({spec.buffer_bar_count}) must "
                f"equal outcome_model.holding_horizon_bars ({outcome_model.holding_horizon_bars})"
            )
    total_declared = sum(spec.total_bar_count for spec in specs)
    bundle_bars = len(bundle.series[0].bars)
    if total_declared != bundle_bars:
        raise ValueError(
            f"sum of window bar counts ({total_declared}) must equal the bundle's own "
            f"per-instrument bar count ({bundle_bars}) -- a declared window range falls "
            "outside the dataset"
        )


def _window_dataset(bundle: RobustnessDatasetBundle, *, window_index: int) -> HistoricalDataset:
    """Slice one window's own private, non-overlapping bar block out of the
    bundle's full per-instrument series, and wrap it in a standalone
    `HistoricalDataset` for the M061 engine. Window order is always
    resolved via `sequence_index`, never the caller's own declaration
    order."""
    start, end = _window_bar_ranges(bundle.window_specs)[window_index]
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
        dataset_version=f"{bundle.authority.dataset_bundle_version}-window-{window_index}",
        source_kind=bundle.authority.source_kind,
        interval=bundle.authority.interval,
        start_timestamp=first_bars[0].timestamp,
        end_timestamp=first_bars[-1].timestamp,
        total_bars=sum(len(series.bars) for series in sliced_series),
        instrument_count=len(sliced_series),
        sha256=dataset_sha256(fingerprint),
    )
    return HistoricalDataset(authority=authority, series=sliced_series)


def _realized_volatility(dataset: HistoricalDataset, *, spec: RobustnessWindowSpec) -> Decimal:
    """POST_HOC_REGIME_LABEL input only: the mean (high-low)/close across
    every instrument's own SCORING-range bars (excluding warmup/buffer) in
    this already-completed window. Computed strictly after the window's
    own trading decisions/outcomes are already final; never consumed by
    `evaluate()`, `build_scan()`, `build_trade_plan()`,
    `build_position_plan()`, or `build_historical_backtest_run()`."""
    ranges: list[Decimal] = []
    warmup = spec.warmup_bar_count
    scoring_end = spec.warmup_bar_count + spec.scoring_bar_count
    for series in dataset.series:
        for bar in series.bars[warmup:scoring_end]:
            if bar.close > 0:
                ranges.append((bar.high - bar.low) / bar.close)
    if not ranges:
        return Decimal("0")
    return sum(ranges, Decimal("0")) / Decimal(len(ranges))


def _classify_regimes(
    volatilities: tuple[Decimal, ...], window_ids: tuple[str, ...]
) -> dict[str, RegimeLabel]:
    """Deterministic tertile split of realized volatility across every
    window in the study -- study-relative, computed only once every
    window's own result is already final, and used solely to group
    already-completed windows for post-hoc analysis. Ties are broken by
    `window_id` (stable, deterministic, independent of dict/sort
    implementation details)."""
    ordered = sorted(
        zip(volatilities, window_ids, strict=True), key=lambda pair: (pair[0], pair[1])
    )
    count = len(ordered)
    labels: dict[str, RegimeLabel] = {}
    for rank, (_volatility, window_id) in enumerate(ordered):
        fraction = (rank + 1) / count
        if fraction <= 1 / 3:
            labels[window_id] = RegimeLabel.LOW_VOLATILITY
        elif fraction <= 2 / 3:
            labels[window_id] = RegimeLabel.NORMAL_VOLATILITY
        else:
            labels[window_id] = RegimeLabel.HIGH_VOLATILITY
    return labels


def build_robustness_study(
    *,
    identity: DomainIdentity[RobustnessStudyId],
    bundle: RobustnessDatasetBundle,
    sizing_context: PositionSizingContext,
    runtime_identifier_generator: RuntimeIdentifierGenerator,
    backtest_run_identity_for: Callable[[str], DomainIdentity[BacktestRunId]],
    reference_window_size: int = 5,
    risk_policy: RiskPolicy = DEFAULT_RISK_POLICY,
    sizing_policy: SizingPolicy = DEFAULT_SIZING_POLICY,
    execution_assumption: HistoricalExecutionAssumption = DEFAULT_EXECUTION_ASSUMPTION,
    outcome_model: HistoricalOutcomeModel = DEFAULT_OUTCOME_MODEL,
    cost_model: HistoricalCostModel = DEFAULT_COST_MODEL,
) -> tuple[HistoricalRobustnessStudy, tuple[HistoricalBacktestRun, ...]]:
    """Build one immutable `HistoricalRobustnessStudy` by running the real,
    unmodified M061 `build_historical_backtest_run()` once per declared
    window, over that window's own private bar slice, in `sequence_index`
    order.

    Applies the identical frozen policy stack to every window -- no
    parameter is ever read from one window's own result and fed into
    another window's inputs. Returns both the study and the tuple of
    per-window `HistoricalBacktestRun` objects (in sequence order) so a
    caller can persist each one through the unmodified M061 repository.
    """
    _validate_bundle_windows(
        bundle, reference_window_size=reference_window_size, outcome_model=outcome_model
    )

    ordered_specs = bundle.ordered_window_specs
    ranges = _window_bar_ranges(bundle.window_specs)
    runs: list[HistoricalBacktestRun] = []
    window_datasets: list[HistoricalDataset] = []
    windows: list[RobustnessWindow] = []
    raw_volatilities: list[Decimal] = []

    for index, spec in enumerate(ordered_specs):
        dataset = _window_dataset(bundle, window_index=index)
        window_datasets.append(dataset)
        run_identity = backtest_run_identity_for(spec.window_id)
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
        window = RobustnessWindow(
            window_id=spec.window_id,
            sequence_index=spec.sequence_index,
            data_start_timestamp=all_bars[0].timestamp,
            data_end_timestamp=all_bars[-1].timestamp,
            scoring_start_timestamp=all_bars[warmup_end_idx].timestamp,
            scoring_end_timestamp=all_bars[scoring_end_idx - 1].timestamp,
            warmup_bar_count=spec.warmup_bar_count,
            scoring_bar_count=spec.scoring_bar_count,
            buffer_bar_count=spec.buffer_bar_count,
        )
        windows.append(window)
        raw_volatilities.append(_realized_volatility(dataset, spec=spec))

    regime_by_window = _classify_regimes(
        tuple(raw_volatilities), tuple(spec.window_id for spec in ordered_specs)
    )

    window_results: list[RobustnessWindowResult] = []
    for window, run, volatility in zip(windows, runs, raw_volatilities, strict=True):
        window_results.append(
            RobustnessWindowResult(
                window=window,
                backtest_run_id=run.identity.governance_id,
                backtest_run_runtime_id=run.identity.runtime_id,
                regime_label=regime_by_window[window.window_id],
                realized_volatility=volatility,
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
    window_results_tuple = tuple(window_results)

    total_executed = sum(result.executed_trade_count for result in window_results_tuple)
    positive_net_pnl_windows = [result for result in window_results_tuple if result.net_pnl > 0]
    negative_net_pnl_windows = [result for result in window_results_tuple if result.net_pnl < 0]
    positive_total_r_windows = [result for result in window_results_tuple if result.total_r > 0]
    negative_total_r_windows = [result for result in window_results_tuple if result.total_r < 0]

    best_net_pnl_result = max(window_results_tuple, key=lambda result: result.net_pnl)
    worst_net_pnl_result = min(window_results_tuple, key=lambda result: result.net_pnl)
    best_total_r_result = max(window_results_tuple, key=lambda result: result.total_r)
    worst_total_r_result = min(window_results_tuple, key=lambda result: result.total_r)

    all_net_pnl_total = sum((result.net_pnl for result in window_results_tuple), Decimal("0"))
    all_total_r_total = sum((result.total_r for result in window_results_tuple), Decimal("0"))
    excluding_best_net_pnl_total = all_net_pnl_total - best_net_pnl_result.net_pnl
    excluding_best_total_r_total = all_total_r_total - best_total_r_result.total_r

    positive_pnl_sum = sum((result.net_pnl for result in positive_net_pnl_windows), Decimal("0"))
    largest_positive_share = (
        (max(result.net_pnl for result in positive_net_pnl_windows) / positive_pnl_sum)
        if positive_net_pnl_windows and positive_pnl_sum > 0
        else None
    )
    negative_pnl_abs_sum = sum(
        (abs(result.net_pnl) for result in negative_net_pnl_windows), Decimal("0")
    )
    largest_negative_share = (
        (max(abs(result.net_pnl) for result in negative_net_pnl_windows) / negative_pnl_abs_sum)
        if negative_net_pnl_windows and negative_pnl_abs_sum > 0
        else None
    )

    if total_executed < MINIMUM_SAMPLE_EXECUTED_TRADES:
        classification = RobustnessStudyClassification.INSUFFICIENT_SAMPLE
    elif positive_net_pnl_windows and negative_net_pnl_windows:
        classification = RobustnessStudyClassification.ROBUSTNESS_EVIDENCE_MIXED
    elif positive_net_pnl_windows and not negative_net_pnl_windows:
        classification = RobustnessStudyClassification.ROBUSTNESS_EVIDENCE_RECORDED
    else:
        classification = RobustnessStudyClassification.ROBUSTNESS_EVIDENCE_WEAK

    reference_run = runs[0]
    study = HistoricalRobustnessStudy(
        identity=identity,
        dataset_bundle_id=bundle.authority.dataset_bundle_id,
        dataset_bundle_version=bundle.authority.dataset_bundle_version,
        dataset_bundle_sha256=bundle.authority.sha256,
        dataset_source_kind=bundle.authority.source_kind,
        universe_id=bundle.universe_authority.universe_id,
        universe_version=bundle.universe_authority.universe_version,
        universe_membership_model=bundle.universe_authority.membership_model,
        interval=bundle.authority.interval,
        instrument_universe=bundle.universe_authority.constituents,
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
        regime_policy_id=REGIME_POLICY_ID,
        regime_policy_version=REGIME_POLICY_VERSION,
        survivorship_bias_disclosure=SURVIVORSHIP_BIAS_DISCLOSURE,
        status=RobustnessStudyStatus.STUDY_COMPLETED,
        classification=classification,
        window_results=window_results_tuple,
        window_count=len(window_results_tuple),
        total_evaluated_cutoff_count=sum(
            result.evaluated_cutoff_count for result in window_results_tuple
        ),
        total_simulated_trade_count=sum(
            result.simulated_trade_count for result in window_results_tuple
        ),
        total_executed_trade_count=total_executed,
        positive_net_pnl_window_count=len(positive_net_pnl_windows),
        negative_net_pnl_window_count=len(negative_net_pnl_windows),
        positive_total_r_window_count=len(positive_total_r_windows),
        negative_total_r_window_count=len(negative_total_r_windows),
        median_window_net_pnl=_median(tuple(result.net_pnl for result in window_results_tuple)),
        median_window_total_r=_median(tuple(result.total_r for result in window_results_tuple)),
        best_window_by_net_pnl=WindowExtreme(
            window_id=best_net_pnl_result.window.window_id, value=best_net_pnl_result.net_pnl
        ),
        worst_window_by_net_pnl=WindowExtreme(
            window_id=worst_net_pnl_result.window.window_id, value=worst_net_pnl_result.net_pnl
        ),
        best_window_by_total_r=WindowExtreme(
            window_id=best_total_r_result.window.window_id, value=best_total_r_result.total_r
        ),
        worst_window_by_total_r=WindowExtreme(
            window_id=worst_total_r_result.window.window_id, value=worst_total_r_result.total_r
        ),
        all_window_net_pnl_total=all_net_pnl_total,
        all_window_total_r_total=all_total_r_total,
        excluding_best_window_net_pnl_total=excluding_best_net_pnl_total,
        excluding_best_window_total_r_total=excluding_best_total_r_total,
        largest_positive_window_share_of_positive_pnl=largest_positive_share,
        largest_negative_window_share_of_absolute_negative_pnl=largest_negative_share,
    )
    return study, tuple(runs)
