"""Survivorship-aware historical robustness study: time-varying universe
membership on top of the unmodified M057-M063 execution stack.

MILESTONE-064. M063 proved broad, windowed historical robustness assuming
one fixed surviving universe across every window. This module answers the
question M063 explicitly left open: at each historical window's own
scoring cutoff, derive the eligible instrument set from immutable,
effective-dated membership authority (`membership.py` /
`historical_universe.universe_at`) instead of assuming the final universe
always applied. Later entrants cannot appear early; exited/inactive
historical members remain historically queryable but not eligible; future
membership changes cannot alter an earlier window.

Every window's canonical backtest is still executed by the real, unmodified
M061 `build_historical_backtest_run()` -- this module builds no second
backtesting engine, only membership-gated dataset slicing on top of the
identical M063 window/regime mechanics.

The `CURRENT_UNIVERSE_BIAS_STRESS` diagnostic literally reuses the real,
unmodified M063 `build_robustness_study()` (which always evaluates the
bundle's full fixed universe every window) against the exact same dataset
bundle -- no second "stress engine" is written; the diagnostic result IS a
genuine `HistoricalRobustnessStudy`, persisted through the unmodified M063
repository, and only *referenced* (by its own `RobustnessStudyId`) from the
survivorship-aware study, alongside a small descriptive comparison. It is
never a canonical alternative result.

Eligibility is derived once per window, at that window's own
`scoring_start_timestamp` -- not re-evaluated at every individual decision
cutoff within the window, since `build_historical_backtest_run()` is frozen
and processes one fixed instrument set across all of its own internal
cutoffs. This is a documented limitation (see governance), not a hidden
one.

No claim of profitability, live-trading readiness, resolved survivorship
bias, or real-market representativeness is made anywhere in this module.
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
from empirical_platform.decision_candidate.historical_universe import universe_at
from empirical_platform.decision_candidate.instrument_master import InstrumentId, InstrumentMaster
from empirical_platform.decision_candidate.membership import (
    MembershipManifest,
    membership_manifest_hash,
)
from empirical_platform.decision_candidate.position_plan import (
    DEFAULT_SIZING_POLICY,
    PositionSizingContext,
    SizingPolicy,
)
from empirical_platform.decision_candidate.robustness_study import (
    REGIME_POLICY_ID,
    REGIME_POLICY_VERSION,
    HistoricalRobustnessStudy,
    RegimeLabel,
    RobustnessDatasetBundle,
    WindowExtreme,
    build_robustness_study,
)
from empirical_platform.decision_candidate.trade_plan import DEFAULT_RISK_POLICY, RiskPolicy
from empirical_platform.identifiers.pairs import DomainIdentity
from empirical_platform.identifiers.types import (
    BacktestRunId,
    DatasetId,
    RobustnessStudyId,
    SurvivorshipStudyId,
)
from empirical_platform.shared.identifiers import RuntimeIdentifier, RuntimeIdentifierGenerator

CORPORATE_ACTION_HANDLING_NOT_EXERCISED = "CORPORATE_ACTION_HANDLING_NOT_EXERCISED"
HISTORICAL_MEMBERSHIP_MODEL = "HISTORICAL_MEMBERSHIP"
MINIMUM_SAMPLE_EXECUTED_TRADES = 15


class SurvivorshipStudyStatus(StrEnum):
    STUDY_COMPLETED = "STUDY_COMPLETED"


class SurvivorshipClassification(StrEnum):
    """Closed, conservative product-statement vocabulary. Deliberately
    excludes any bias-elimination, market-representativeness,
    profitability, or live-readiness claim (see governance forbidden-terms
    list)."""

    INSUFFICIENT_SAMPLE = "INSUFFICIENT_SAMPLE"
    SURVIVORSHIP_AWARE_MEMBERSHIP_MECHANICS_PROVEN = (
        "SURVIVORSHIP_AWARE_MEMBERSHIP_MECHANICS_PROVEN"
    )


class BiasStressComparison(StrEnum):
    """Whether the diagnostic current-universe-forced result matches the
    canonical membership-gated result -- reported honestly either way,
    never forced."""

    CURRENT_UNIVERSE_BIAS_STRESS_IDENTICAL = "CURRENT_UNIVERSE_BIAS_STRESS_IDENTICAL"
    CURRENT_UNIVERSE_BIAS_STRESS_DIFFERS = "CURRENT_UNIVERSE_BIAS_STRESS_DIFFERS"


@dataclass(frozen=True, slots=True)
class WindowUniverseSnapshot:
    """Audit trail answering "why was instrument X evaluated in window
    W07?" for one window: the membership authority used, the full eligible
    set, the subset actually evaluated (eligible AND has bar data in this
    dataset bundle), and any eligible-but-missing-data exclusions."""

    window_id: str
    sequence_index: int
    universe_id: str
    universe_version: str
    membership_manifest_hash: str
    eligible_instrument_ids: tuple[InstrumentId, ...]
    evaluated_instrument_ids: tuple[InstrumentId, ...]
    missing_data_excluded_instrument_ids: tuple[InstrumentId, ...]

    def __post_init__(self) -> None:
        if not self.window_id.strip():
            raise ValueError("window_id must be non-empty")
        for field_name in ("universe_id", "universe_version", "membership_manifest_hash"):
            if not getattr(self, field_name).strip():
                raise ValueError(f"{field_name} must be non-empty")
        evaluated = set(self.evaluated_instrument_ids)
        missing = set(self.missing_data_excluded_instrument_ids)
        eligible = set(self.eligible_instrument_ids)
        if evaluated | missing != eligible or evaluated & missing:
            raise ValueError(
                "evaluated_instrument_ids and missing_data_excluded_instrument_ids must "
                "exactly partition eligible_instrument_ids"
            )

    @property
    def eligible_count(self) -> int:
        return len(self.eligible_instrument_ids)

    @property
    def evaluated_count(self) -> int:
        return len(self.evaluated_instrument_ids)


@dataclass(frozen=True, slots=True)
class SurvivorshipWindowResult:
    """One window's membership-gated canonical result: the universe
    snapshot used, its post-hoc regime label, and the same M061 metric
    shape M063 already reports. `backtest_run_id` /
    `backtest_run_runtime_id` are `None` only when zero instruments were
    evaluated in this window (nothing to persist through M061) -- this is a
    predeclared, honestly-recorded zero-trade window, never a silently
    dropped one."""

    snapshot: WindowUniverseSnapshot
    data_start_timestamp: datetime
    data_end_timestamp: datetime
    scoring_start_timestamp: datetime
    scoring_end_timestamp: datetime
    backtest_run_id: BacktestRunId | None
    backtest_run_runtime_id: RuntimeIdentifier | None
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
class StressWindowComparison:
    """One window's canonical-vs-stress eligible/evaluated instrument
    counts."""

    window_id: str
    canonical_eligible_count: int
    canonical_evaluated_count: int
    stress_eligible_count: int
    stress_evaluated_count: int


@dataclass(frozen=True, slots=True)
class CurrentUniverseBiasStressResult:
    """Diagnostic-only comparison between the canonical (membership-gated)
    study and `stress_study_id` -- a genuine, separately persisted
    `HistoricalRobustnessStudy` (M063, unmodified) built by forcing the
    dataset bundle's declared final/current universe across every window
    regardless of historical membership facts. Never a canonical
    alternative result; the vocabulary here structurally cannot say
    `PROFITABLE`/`PROVEN_EDGE`/`LIVE_READY`/`BIAS_ELIMINATED`.

    `window_comparisons` is NOT stored here -- since the stress side always
    applies the same `full_universe_size` to every window, per-window
    comparisons are a pure, derived view (`stress_window_comparisons()`)
    over `window_results` + `full_universe_size`, computed identically at
    construction time and at repository retrieval time (the same pattern
    M063's own `regime_breakdown()` already established)."""

    stress_study_id: RobustnessStudyId
    comparison: BiasStressComparison
    full_universe_size: int
    canonical_total_executed_trade_count: int
    stress_total_executed_trade_count: int
    canonical_net_pnl_total: Decimal
    stress_net_pnl_total: Decimal
    canonical_total_r_total: Decimal
    stress_total_r_total: Decimal
    canonical_best_window_by_net_pnl: WindowExtreme
    stress_best_window_by_net_pnl: WindowExtreme
    canonical_worst_window_by_net_pnl: WindowExtreme
    stress_worst_window_by_net_pnl: WindowExtreme


@dataclass(frozen=True, slots=True)
class SurvivorshipAwareRobustnessStudy:
    """One immutable, persisted survivorship-aware robustness study --
    additive to, never a replacement for, the frozen M063
    `HistoricalRobustnessStudy`."""

    identity: DomainIdentity[SurvivorshipStudyId]
    dataset_bundle_id: DatasetId
    dataset_bundle_version: str
    dataset_bundle_sha256: str
    dataset_source_kind: str
    universe_id: str
    universe_version: str
    universe_membership_model: str
    membership_manifest_hash: str
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
    corporate_action_handling: str
    status: SurvivorshipStudyStatus
    classification: SurvivorshipClassification
    window_results: tuple[SurvivorshipWindowResult, ...]
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
    current_universe_bias_stress: CurrentUniverseBiasStressResult

    def stress_window_comparisons(self) -> tuple[StressWindowComparison, ...]:
        """Pure, derived per-window canonical-vs-stress eligible/evaluated
        instrument counts -- never separately persisted (see
        `CurrentUniverseBiasStressResult` docstring)."""
        full_size = self.current_universe_bias_stress.full_universe_size
        return tuple(
            StressWindowComparison(
                window_id=result.snapshot.window_id,
                canonical_eligible_count=result.snapshot.eligible_count,
                canonical_evaluated_count=result.snapshot.evaluated_count,
                stress_eligible_count=full_size,
                stress_evaluated_count=full_size,
            )
            for result in self.window_results
        )

    def __post_init__(self) -> None:
        if not isinstance(self.identity, DomainIdentity):
            raise TypeError("identity must be a DomainIdentity[SurvivorshipStudyId]")
        if not isinstance(self.identity.governance_id, SurvivorshipStudyId):
            raise TypeError("identity governance_id must be a SurvivorshipStudyId")
        for field_name in (
            "dataset_bundle_version",
            "dataset_source_kind",
            "universe_id",
            "universe_version",
            "universe_membership_model",
            "membership_manifest_hash",
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
            "corporate_action_handling",
        ):
            if not getattr(self, field_name).strip():
                raise ValueError(f"{field_name} must be non-empty")
        if len(self.dataset_bundle_sha256) != 64:
            raise ValueError("dataset_bundle_sha256 must be a full SHA-256 hex digest")
        if len(self.membership_manifest_hash) != 64:
            raise ValueError("membership_manifest_hash must be a full SHA-256 hex digest")
        if self.window_count < 1:
            raise ValueError("window_count must be at least 1")
        if len(self.window_results) != self.window_count:
            raise ValueError("window_count must match the persisted window_results count")
        sequence_indexes = [result.snapshot.sequence_index for result in self.window_results]
        if sequence_indexes != sorted(sequence_indexes):
            raise ValueError("window_results must be ordered by sequence_index")
        if sequence_indexes != list(range(self.window_count)):
            raise ValueError("window sequence_index values must be a contiguous 0..N-1 sequence")
        for previous, current in zip(self.window_results, self.window_results[1:], strict=False):
            if previous.data_end_timestamp >= current.data_start_timestamp:
                raise ValueError("windows must be chronologically disjoint and strictly ordered")


def _median(values: tuple[Decimal, ...]) -> Decimal:
    ordered = sorted(values)
    count = len(ordered)
    midpoint = count // 2
    if count % 2 == 1:
        return ordered[midpoint]
    return (ordered[midpoint - 1] + ordered[midpoint]) / 2


def _window_bar_ranges(bundle: RobustnessDatasetBundle) -> tuple[tuple[int, int], ...]:
    ranges = []
    cursor = 0
    for spec in bundle.ordered_window_specs:
        start = cursor
        end = cursor + spec.total_bar_count
        ranges.append((start, end))
        cursor = end
    return tuple(ranges)


def _realized_volatility(series: tuple[HistoricalInstrumentSeries, ...]) -> Decimal:
    """Same formula M063's `REGIME_POLICY_ID` uses: mean (high-low)/close
    across every supplied bar. Applied here to only the window's own
    evaluated-instrument bars (already sliced to the scoring range by the
    caller)."""
    ranges: list[Decimal] = []
    for one_series in series:
        for bar in one_series.bars:
            if bar.close > 0:
                ranges.append((bar.high - bar.low) / bar.close)
    if not ranges:
        return Decimal("0")
    return sum(ranges, Decimal("0")) / Decimal(len(ranges))


def _classify_regimes(
    volatilities: tuple[Decimal, ...], window_ids: tuple[str, ...]
) -> dict[str, RegimeLabel]:
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


def _validate_bundle_windows(
    bundle: RobustnessDatasetBundle,
    *,
    reference_window_size: int,
    outcome_model: HistoricalOutcomeModel,
) -> None:
    for spec in bundle.ordered_window_specs:
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
    total_declared = sum(spec.total_bar_count for spec in bundle.ordered_window_specs)
    bundle_bars = len(bundle.series[0].bars)
    if total_declared != bundle_bars:
        raise ValueError(
            f"sum of window bar counts ({total_declared}) must equal the bundle's own "
            f"per-instrument bar count ({bundle_bars})"
        )


def build_survivorship_aware_robustness_study(
    *,
    identity: DomainIdentity[SurvivorshipStudyId],
    stress_study_identity: DomainIdentity[RobustnessStudyId],
    bundle: RobustnessDatasetBundle,
    instrument_master: InstrumentMaster,
    membership_manifest: MembershipManifest,
    sizing_context: PositionSizingContext,
    runtime_identifier_generator: RuntimeIdentifierGenerator,
    backtest_run_identity_for: Callable[[str], DomainIdentity[BacktestRunId]],
    stress_backtest_run_identity_for: Callable[[str], DomainIdentity[BacktestRunId]],
    reference_window_size: int = 5,
    risk_policy: RiskPolicy = DEFAULT_RISK_POLICY,
    sizing_policy: SizingPolicy = DEFAULT_SIZING_POLICY,
    execution_assumption: HistoricalExecutionAssumption = DEFAULT_EXECUTION_ASSUMPTION,
    outcome_model: HistoricalOutcomeModel = DEFAULT_OUTCOME_MODEL,
    cost_model: HistoricalCostModel = DEFAULT_COST_MODEL,
) -> tuple[
    SurvivorshipAwareRobustnessStudy,
    tuple[HistoricalBacktestRun, ...],
    HistoricalRobustnessStudy,
    tuple[HistoricalBacktestRun, ...],
]:
    """Build one immutable `SurvivorshipAwareRobustnessStudy`, its own
    canonical-window `HistoricalBacktestRun`s, plus the diagnostic
    `CURRENT_UNIVERSE_BIAS_STRESS` `HistoricalRobustnessStudy` (a genuine
    M063 study, unmodified) and its own `HistoricalBacktestRun`s, so a
    caller can persist all of them through the unmodified M061/M063
    repositories.
    """
    membership_manifest.validate_against_master(instrument_master)
    if membership_manifest.universe_id != bundle.universe_authority.universe_id:
        raise ValueError(
            "membership manifest universe_id "
            f"({membership_manifest.universe_id!r}) does not match the dataset bundle's own "
            f"declared universe_id ({bundle.universe_authority.universe_id!r})"
        )
    if membership_manifest.universe_version != bundle.universe_authority.universe_version:
        raise ValueError(
            "membership manifest universe_version "
            f"({membership_manifest.universe_version!r}) does not match the dataset bundle's "
            f"own declared universe_version ({bundle.universe_authority.universe_version!r})"
        )
    _validate_bundle_windows(
        bundle, reference_window_size=reference_window_size, outcome_model=outcome_model
    )

    symbol_by_instrument_id = instrument_master.symbol_by_instrument_id
    instrument_id_by_symbol = {symbol: iid for iid, symbol in symbol_by_instrument_id.items()}
    for series in bundle.series:
        if series.instrument not in instrument_id_by_symbol:
            raise ValueError(
                f"dataset bundle contains bars for unknown instrument: {series.instrument}"
            )
    symbol_to_series = {series.instrument: series for series in bundle.series}

    manifest_hash = membership_manifest_hash(membership_manifest)
    ordered_specs = bundle.ordered_window_specs
    ranges = _window_bar_ranges(bundle)

    canonical_runs: list[HistoricalBacktestRun] = []
    window_results: list[SurvivorshipWindowResult] = []
    raw_volatilities: list[Decimal] = []
    reference_run: HistoricalBacktestRun | None = None

    for index, spec in enumerate(ordered_specs):
        start, end = ranges[index]
        all_bars = bundle.series[0].bars[start:end]
        warmup_end_idx = spec.warmup_bar_count
        scoring_end_idx = spec.warmup_bar_count + spec.scoring_bar_count
        data_start_timestamp = all_bars[0].timestamp
        data_end_timestamp = all_bars[-1].timestamp
        scoring_start_timestamp = all_bars[warmup_end_idx].timestamp
        scoring_end_timestamp = all_bars[scoring_end_idx - 1].timestamp

        eligible_instrument_ids = universe_at(membership_manifest, scoring_start_timestamp)
        eligible_symbols = tuple(
            sorted((symbol_by_instrument_id[iid] for iid in eligible_instrument_ids), key=str)
        )
        evaluated_symbols = tuple(sym for sym in eligible_symbols if sym in symbol_to_series)
        missing_symbols = tuple(sym for sym in eligible_symbols if sym not in symbol_to_series)
        snapshot = WindowUniverseSnapshot(
            window_id=spec.window_id,
            sequence_index=spec.sequence_index,
            universe_id=membership_manifest.universe_id,
            universe_version=membership_manifest.universe_version,
            membership_manifest_hash=manifest_hash,
            eligible_instrument_ids=eligible_instrument_ids,
            evaluated_instrument_ids=tuple(
                sorted((instrument_id_by_symbol[sym] for sym in evaluated_symbols), key=str)
            ),
            missing_data_excluded_instrument_ids=tuple(
                sorted((instrument_id_by_symbol[sym] for sym in missing_symbols), key=str)
            ),
        )

        if not evaluated_symbols:
            raw_volatilities.append(Decimal("0"))
            window_results.append(
                SurvivorshipWindowResult(
                    snapshot=snapshot,
                    data_start_timestamp=data_start_timestamp,
                    data_end_timestamp=data_end_timestamp,
                    scoring_start_timestamp=scoring_start_timestamp,
                    scoring_end_timestamp=scoring_end_timestamp,
                    backtest_run_id=None,
                    backtest_run_runtime_id=None,
                    regime_label=RegimeLabel.LOW_VOLATILITY,  # placeholder, overwritten below
                    realized_volatility=Decimal("0"),
                    evaluated_cutoff_count=0,
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
            )
            continue

        sliced_series = tuple(
            HistoricalInstrumentSeries(
                instrument=symbol_to_series[symbol].instrument,
                bars=symbol_to_series[symbol].bars[start:end],
            )
            for symbol in evaluated_symbols
        )
        fingerprint = "|".join(
            f"{series.instrument}:{bar.timestamp.isoformat()}:{bar.open}:{bar.high}:"
            f"{bar.low}:{bar.close}:{bar.volume}"
            for series in sliced_series
            for bar in series.bars
        ).encode("utf-8")
        authority = HistoricalDatasetAuthority(
            dataset_id=bundle.authority.dataset_bundle_id,
            dataset_version=f"{bundle.authority.dataset_bundle_version}-survivorship-window-{index}",
            source_kind=bundle.authority.source_kind,
            interval=bundle.authority.interval,
            start_timestamp=sliced_series[0].bars[0].timestamp,
            end_timestamp=sliced_series[0].bars[-1].timestamp,
            total_bars=sum(len(series.bars) for series in sliced_series),
            instrument_count=len(sliced_series),
            sha256=dataset_sha256(fingerprint),
        )
        window_dataset = HistoricalDataset(authority=authority, series=sliced_series)
        run_identity = backtest_run_identity_for(spec.window_id)
        run = build_historical_backtest_run(
            identity=run_identity,
            dataset=window_dataset,
            sizing_context=sizing_context,
            runtime_identifier_generator=runtime_identifier_generator,
            reference_window_size=reference_window_size,
            risk_policy=risk_policy,
            sizing_policy=sizing_policy,
            execution_assumption=execution_assumption,
            outcome_model=outcome_model,
            cost_model=cost_model,
        )
        canonical_runs.append(run)
        reference_run = reference_run or run

        scoring_series = tuple(
            HistoricalInstrumentSeries(
                instrument=series.instrument,
                bars=series.bars[warmup_end_idx:scoring_end_idx],
            )
            for series in sliced_series
        )
        raw_volatilities.append(_realized_volatility(scoring_series))
        window_results.append(
            SurvivorshipWindowResult(
                snapshot=snapshot,
                data_start_timestamp=data_start_timestamp,
                data_end_timestamp=data_end_timestamp,
                scoring_start_timestamp=scoring_start_timestamp,
                scoring_end_timestamp=scoring_end_timestamp,
                backtest_run_id=run.identity.governance_id,
                backtest_run_runtime_id=run.identity.runtime_id,
                regime_label=RegimeLabel.LOW_VOLATILITY,  # placeholder, overwritten below
                realized_volatility=raw_volatilities[-1],
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

    if reference_run is None:
        raise ValueError(
            "every window had zero evaluated instruments -- a survivorship-aware study "
            "requires at least one window with at least one eligible, data-available "
            "instrument to derive its policy-identity fields"
        )

    regime_by_window = _classify_regimes(
        tuple(raw_volatilities), tuple(spec.window_id for spec in ordered_specs)
    )
    window_results = [
        SurvivorshipWindowResult(
            snapshot=result.snapshot,
            data_start_timestamp=result.data_start_timestamp,
            data_end_timestamp=result.data_end_timestamp,
            scoring_start_timestamp=result.scoring_start_timestamp,
            scoring_end_timestamp=result.scoring_end_timestamp,
            backtest_run_id=result.backtest_run_id,
            backtest_run_runtime_id=result.backtest_run_runtime_id,
            regime_label=regime_by_window[result.snapshot.window_id],
            realized_volatility=result.realized_volatility,
            evaluated_cutoff_count=result.evaluated_cutoff_count,
            simulated_trade_count=result.simulated_trade_count,
            executed_trade_count=result.executed_trade_count,
            win_count=result.win_count,
            loss_count=result.loss_count,
            time_exit_count=result.time_exit_count,
            no_entry_count=result.no_entry_count,
            gross_pnl=result.gross_pnl,
            net_pnl=result.net_pnl,
            average_net_pnl=result.average_net_pnl,
            average_r=result.average_r,
            total_r=result.total_r,
            win_rate=result.win_rate,
            profit_factor=result.profit_factor,
            maximum_realized_pnl_drawdown=result.maximum_realized_pnl_drawdown,
        )
        for result in window_results
    ]
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
        classification = SurvivorshipClassification.INSUFFICIENT_SAMPLE
    else:
        classification = SurvivorshipClassification.SURVIVORSHIP_AWARE_MEMBERSHIP_MECHANICS_PROVEN

    # CURRENT_UNIVERSE_BIAS_STRESS: literally the real, unmodified M063
    # build_robustness_study() over the identical bundle -- it always
    # evaluates the bundle's full declared universe every window, which IS
    # "force the final/current universe backward across all windows".
    stress_study, stress_runs = build_robustness_study(
        identity=stress_study_identity,
        bundle=bundle,
        sizing_context=sizing_context,
        runtime_identifier_generator=runtime_identifier_generator,
        backtest_run_identity_for=stress_backtest_run_identity_for,
        reference_window_size=reference_window_size,
        risk_policy=risk_policy,
        sizing_policy=sizing_policy,
        execution_assumption=execution_assumption,
        outcome_model=outcome_model,
        cost_model=cost_model,
    )

    comparison = (
        BiasStressComparison.CURRENT_UNIVERSE_BIAS_STRESS_IDENTICAL
        if (
            total_executed == stress_study.total_executed_trade_count
            and all_net_pnl_total == stress_study.all_window_net_pnl_total
            and all_total_r_total == stress_study.all_window_total_r_total
        )
        else BiasStressComparison.CURRENT_UNIVERSE_BIAS_STRESS_DIFFERS
    )
    bias_stress = CurrentUniverseBiasStressResult(
        stress_study_id=stress_study.identity.governance_id,
        comparison=comparison,
        full_universe_size=len(bundle.universe_authority.constituents),
        canonical_total_executed_trade_count=total_executed,
        stress_total_executed_trade_count=stress_study.total_executed_trade_count,
        canonical_net_pnl_total=all_net_pnl_total,
        stress_net_pnl_total=stress_study.all_window_net_pnl_total,
        canonical_total_r_total=all_total_r_total,
        stress_total_r_total=stress_study.all_window_total_r_total,
        canonical_best_window_by_net_pnl=WindowExtreme(
            window_id=best_net_pnl_result.snapshot.window_id, value=best_net_pnl_result.net_pnl
        ),
        stress_best_window_by_net_pnl=stress_study.best_window_by_net_pnl,
        canonical_worst_window_by_net_pnl=WindowExtreme(
            window_id=worst_net_pnl_result.snapshot.window_id, value=worst_net_pnl_result.net_pnl
        ),
        stress_worst_window_by_net_pnl=stress_study.worst_window_by_net_pnl,
    )

    study = SurvivorshipAwareRobustnessStudy(
        identity=identity,
        dataset_bundle_id=bundle.authority.dataset_bundle_id,
        dataset_bundle_version=bundle.authority.dataset_bundle_version,
        dataset_bundle_sha256=bundle.authority.sha256,
        dataset_source_kind=bundle.authority.source_kind,
        universe_id=membership_manifest.universe_id,
        universe_version=membership_manifest.universe_version,
        universe_membership_model=HISTORICAL_MEMBERSHIP_MODEL,
        membership_manifest_hash=manifest_hash,
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
        corporate_action_handling=CORPORATE_ACTION_HANDLING_NOT_EXERCISED,
        status=SurvivorshipStudyStatus.STUDY_COMPLETED,
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
            window_id=best_net_pnl_result.snapshot.window_id, value=best_net_pnl_result.net_pnl
        ),
        worst_window_by_net_pnl=WindowExtreme(
            window_id=worst_net_pnl_result.snapshot.window_id, value=worst_net_pnl_result.net_pnl
        ),
        best_window_by_total_r=WindowExtreme(
            window_id=best_total_r_result.snapshot.window_id, value=best_total_r_result.total_r
        ),
        worst_window_by_total_r=WindowExtreme(
            window_id=worst_total_r_result.snapshot.window_id, value=worst_total_r_result.total_r
        ),
        all_window_net_pnl_total=all_net_pnl_total,
        all_window_total_r_total=all_total_r_total,
        excluding_best_window_net_pnl_total=excluding_best_net_pnl_total,
        excluding_best_window_total_r_total=excluding_best_total_r_total,
        largest_positive_window_share_of_positive_pnl=largest_positive_share,
        largest_negative_window_share_of_absolute_negative_pnl=largest_negative_share,
        current_universe_bias_stress=bias_stress,
    )
    return study, tuple(canonical_runs), stress_study, tuple(stress_runs)
