"""Historical strategy validation and deterministic backtesting.

MILESTONE-061. This module introduces a first-class, immutable historical
validation record layered directly on top of the frozen M057-M060 decision
stack. It reuses:

- M057 strategy evaluation (`evaluate`)
- M058 opportunity scan / ranking (`build_scan`)
- M059 risk-gated trade planning (`build_trade_plan`)
- M060 position sizing (`build_position_plan`)

The backtest itself adds only deterministic orchestration plus an explicit
outcome and cost model. It is not broker execution, not a live portfolio
engine, and not a claim of profitability.
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from empirical_platform.decision_candidate.candidate import DecisionCandidate
from empirical_platform.decision_candidate.market_data import (
    Bar,
    BarInterval,
    Instrument,
    ObservationWindow,
)
from empirical_platform.decision_candidate.position_plan import (
    DEFAULT_SIZING_POLICY,
    PositionPlan,
    PositionPlanStatus,
    PositionSizingContext,
    SizingPolicy,
    build_position_plan,
)
from empirical_platform.decision_candidate.ranking import RANKING_MODEL_ID, RANKING_MODEL_VERSION
from empirical_platform.decision_candidate.scan import (
    TradingOpportunityScan,
    build_scan,
    validate_scan_universe,
)
from empirical_platform.decision_candidate.strategy import (
    STRATEGY_ID,
    STRATEGY_VERSION,
    EvaluationOutcome,
    StrategyParameters,
    evaluate,
)
from empirical_platform.decision_candidate.trade_plan import (
    DEFAULT_RISK_POLICY,
    RiskPolicy,
    TradePlan,
    TradePlanStatus,
    build_trade_plan,
)
from empirical_platform.identifiers.pairs import DomainIdentity
from empirical_platform.identifiers.types import (
    BacktestRunId,
    DatasetId,
    DecisionCandidateId,
    EvidencePackageId,
    PositionPlanId,
    TradePlanId,
    TradingOpportunityScanId,
)
from empirical_platform.shared.identifiers import RuntimeIdentifierGenerator

DECISION_CADENCE = "BAR_CLOSE"
EXECUTION_ASSUMPTION_ID = "NEXT_BAR_OPEN_ENTRY"
EXECUTION_ASSUMPTION_VERSION = "1"
OUTCOME_MODEL_ID = "STOP_TARGET_TIME_EXIT"
OUTCOME_MODEL_VERSION = "1"
COST_MODEL_ID = "BPS_SLIPPAGE_WITH_OPTIONAL_FIXED_COMMISSION"
COST_MODEL_VERSION = "1"
FIXED_TEST_UNIVERSE = "FIXED_TEST_UNIVERSE"
_LOCAL_EVIDENCE_PACKAGE_ID = EvidencePackageId("EVID-9999")


class HistoricalBacktestRunStatus(StrEnum):
    """Closed lifecycle vocabulary for an immutable historical validation run."""

    COMPLETED = "COMPLETED"


class HistoricalValidationClassification(StrEnum):
    """Allowed post-run product statements for M061."""

    VALIDATION_ENGINE_PROVEN_STRATEGY_UNASSESSED = "VALIDATION_ENGINE_PROVEN_STRATEGY_UNASSESSED"
    VALIDATION_ENGINE_PROVEN_FIXTURE_RESULTS_RECORDED = (
        "VALIDATION_ENGINE_PROVEN_FIXTURE_RESULTS_RECORDED"
    )


class SameBarAmbiguityPolicy(StrEnum):
    """How M061 resolves bars that hit both stop and target."""

    STOP_FIRST = "STOP_FIRST"


class HistoricalTradeOutcome(StrEnum):
    """Supported deterministic historical outcomes for one approved position."""

    TARGET_HIT = "TARGET_HIT"
    STOP_HIT = "STOP_HIT"
    TIME_EXIT = "TIME_EXIT"
    NO_ENTRY = "NO_ENTRY"


@dataclass(frozen=True, slots=True)
class HistoricalExecutionAssumption:
    """Explicit, versioned historical execution timing assumption."""

    assumption_id: str = EXECUTION_ASSUMPTION_ID
    assumption_version: str = EXECUTION_ASSUMPTION_VERSION
    description: str = "Decision at bar close T, hypothetical entry at next bar open T+1"


DEFAULT_EXECUTION_ASSUMPTION = HistoricalExecutionAssumption()


@dataclass(frozen=True, slots=True)
class HistoricalOutcomeModel:
    """Explicit, versioned historical outcome model."""

    model_id: str = OUTCOME_MODEL_ID
    model_version: str = OUTCOME_MODEL_VERSION
    holding_horizon_bars: int = 3
    ambiguity_policy: SameBarAmbiguityPolicy = SameBarAmbiguityPolicy.STOP_FIRST
    no_overnight: bool = True

    def __post_init__(self) -> None:
        if not self.model_id.strip():
            raise ValueError("model_id must be non-empty")
        if not self.model_version.strip():
            raise ValueError("model_version must be non-empty")
        if self.holding_horizon_bars < 1:
            raise ValueError("holding_horizon_bars must be at least 1")


DEFAULT_OUTCOME_MODEL = HistoricalOutcomeModel()


@dataclass(frozen=True, slots=True)
class HistoricalCostModel:
    """Explicit, versioned deterministic transaction-cost model."""

    model_id: str = COST_MODEL_ID
    model_version: str = COST_MODEL_VERSION
    entry_slippage_bps: Decimal = Decimal("5")
    exit_slippage_bps: Decimal = Decimal("5")
    fixed_commission_per_side: Decimal = Decimal("0")

    def __post_init__(self) -> None:
        for field_name in ("entry_slippage_bps", "exit_slippage_bps", "fixed_commission_per_side"):
            value = getattr(self, field_name)
            if not isinstance(value, Decimal):
                raise TypeError(f"{field_name} must be a Decimal")
            if value < 0:
                raise ValueError(f"{field_name} must be non-negative")
        if not self.model_id.strip():
            raise ValueError("model_id must be non-empty")
        if not self.model_version.strip():
            raise ValueError("model_version must be non-empty")


DEFAULT_COST_MODEL = HistoricalCostModel()


@dataclass(frozen=True, slots=True)
class HistoricalInstrumentSeries:
    """One instrument's immutable historical bar series."""

    instrument: Instrument
    bars: tuple[Bar, ...]

    def __post_init__(self) -> None:
        if len(self.bars) < 2:
            raise ValueError("a historical instrument series requires at least 2 bars")
        if any(bar.instrument != self.instrument for bar in self.bars):
            raise ValueError("all bars in a historical instrument series must match the instrument")
        for previous, current in zip(self.bars, self.bars[1:], strict=False):
            if current.timestamp <= previous.timestamp:
                raise ValueError(
                    "historical bars must be strictly chronological with no duplicates"
                )
            if current.interval != previous.interval:
                raise ValueError("historical instrument series must share one bar interval")

    @property
    def interval(self) -> BarInterval:
        return self.bars[0].interval


@dataclass(frozen=True, slots=True)
class HistoricalDatasetAuthority:
    """Immutable identity and checksum record for a historical dataset."""

    dataset_id: DatasetId
    dataset_version: str
    source_kind: str
    interval: BarInterval
    start_timestamp: datetime
    end_timestamp: datetime
    total_bars: int
    instrument_count: int
    sha256: str

    def __post_init__(self) -> None:
        if not self.dataset_version.strip():
            raise ValueError("dataset_version must be non-empty")
        if not self.source_kind.strip():
            raise ValueError("source_kind must be non-empty")
        if self.start_timestamp.tzinfo is None or self.end_timestamp.tzinfo is None:
            raise ValueError("dataset timestamps must be timezone-aware")
        if self.start_timestamp >= self.end_timestamp:
            raise ValueError("dataset start_timestamp must be before end_timestamp")
        if self.total_bars < 1:
            raise ValueError("total_bars must be at least 1")
        if self.instrument_count < 1:
            raise ValueError("instrument_count must be at least 1")
        if len(self.sha256) != 64:
            raise ValueError("sha256 must be a full SHA-256 hex digest")


@dataclass(frozen=True, slots=True)
class HistoricalDataset:
    """One fixed, locally reproducible historical backtest dataset."""

    authority: HistoricalDatasetAuthority
    series: tuple[HistoricalInstrumentSeries, ...]

    def __post_init__(self) -> None:
        if len(self.series) < 1:
            raise ValueError("a historical dataset must contain at least 1 instrument")
        seen: set[Instrument] = set()
        first = self.series[0]
        canonical_timestamps = tuple(bar.timestamp for bar in first.bars)
        if first.interval != self.authority.interval:
            raise ValueError("dataset authority interval must match the bar series interval")
        total_bars = 0
        for series in self.series:
            if series.instrument in seen:
                raise ValueError(f"duplicate instrument in historical dataset: {series.instrument}")
            seen.add(series.instrument)
            if series.interval != self.authority.interval:
                raise ValueError("all historical instrument series must share one interval")
            timestamps = tuple(bar.timestamp for bar in series.bars)
            if timestamps != canonical_timestamps:
                raise ValueError(
                    "all historical instrument series must share one canonical timestamp grid"
                )
            total_bars += len(series.bars)
        if total_bars != self.authority.total_bars:
            raise ValueError("dataset authority total_bars does not match the supplied series")
        if len(self.series) != self.authority.instrument_count:
            raise ValueError(
                "dataset authority instrument_count does not match the supplied series"
            )
        if canonical_timestamps[0] != self.authority.start_timestamp:
            raise ValueError("dataset authority start_timestamp does not match the series")
        if canonical_timestamps[-1] != self.authority.end_timestamp:
            raise ValueError("dataset authority end_timestamp does not match the series")

    @property
    def instruments(self) -> tuple[Instrument, ...]:
        return tuple(sorted((series.instrument for series in self.series), key=str))

    @property
    def bars_per_instrument(self) -> int:
        return len(self.series[0].bars)


@dataclass(frozen=True, slots=True)
class HistoricalBacktestTrade:
    """One persisted, immutable historical trade outcome."""

    trade_sequence: int
    instrument: Instrument
    evaluation_cutoff: datetime
    source_scan_reference: str
    source_decision_candidate_reference: str
    source_trade_plan_reference: str
    source_position_plan_reference: str
    scan_rank: int
    ranking_score: Decimal
    entry_timestamp: datetime | None
    planned_entry_price: Decimal
    simulated_entry_price: Decimal | None
    planned_stop_price: Decimal
    planned_target_price: Decimal
    exit_timestamp: datetime | None
    exit_price: Decimal | None
    outcome: HistoricalTradeOutcome
    ambiguity_policy: SameBarAmbiguityPolicy
    ambiguity_triggered: bool
    quantity: int
    gross_pnl: Decimal
    transaction_costs: Decimal
    net_pnl: Decimal
    risk_amount: Decimal
    r_multiple: Decimal | None
    holding_bars: int | None

    def __post_init__(self) -> None:
        if self.trade_sequence < 1:
            raise ValueError("trade_sequence must be at least 1")
        if self.evaluation_cutoff.tzinfo is None:
            raise ValueError("evaluation_cutoff must be timezone-aware")
        if self.entry_timestamp is not None and self.entry_timestamp.tzinfo is None:
            raise ValueError("entry_timestamp must be timezone-aware when present")
        if self.exit_timestamp is not None and self.exit_timestamp.tzinfo is None:
            raise ValueError("exit_timestamp must be timezone-aware when present")
        if self.quantity < 1:
            raise ValueError("quantity must be at least 1")
        if self.scan_rank < 1:
            raise ValueError("scan_rank must be at least 1")
        if self.risk_amount <= 0:
            raise ValueError("risk_amount must be positive")
        if self.outcome is HistoricalTradeOutcome.NO_ENTRY:
            if self.entry_timestamp is not None or self.exit_timestamp is not None:
                raise ValueError("NO_ENTRY trades must not carry entry or exit timestamps")
            if self.simulated_entry_price is not None or self.exit_price is not None:
                raise ValueError("NO_ENTRY trades must not carry entry or exit prices")
            if self.gross_pnl != Decimal("0") or self.transaction_costs != Decimal("0"):
                raise ValueError("NO_ENTRY trades must carry zero gross pnl and transaction costs")
            if self.net_pnl != Decimal("0") or self.r_multiple is not None:
                raise ValueError("NO_ENTRY trades must carry zero net pnl and no R multiple")
        else:
            if self.entry_timestamp is None or self.exit_timestamp is None:
                raise ValueError("executed trades must carry entry and exit timestamps")
            if self.simulated_entry_price is None or self.exit_price is None:
                raise ValueError("executed trades must carry entry and exit prices")
            if self.holding_bars is None or self.holding_bars < 1:
                raise ValueError("executed trades must carry a positive holding_bars count")

    @property
    def executed(self) -> bool:
        return self.outcome is not HistoricalTradeOutcome.NO_ENTRY


@dataclass(frozen=True, slots=True)
class HistoricalBacktestRun:
    """One immutable historical validation run plus per-trade evidence."""

    identity: DomainIdentity[BacktestRunId]
    dataset_id: DatasetId
    dataset_version: str
    dataset_source_kind: str
    dataset_sha256: str
    interval: BarInterval
    universe: tuple[Instrument, ...]
    dataset_start_timestamp: datetime
    dataset_end_timestamp: datetime
    dataset_total_bars: int
    reference_window_size: int
    decision_cadence: str
    strategy_id: str
    strategy_version: str
    ranking_model_id: str
    ranking_model_version: str
    risk_policy_id: str
    risk_policy_version: str
    risk_policy_target_projection_percent: Decimal
    risk_policy_minimum_reward_risk_ratio: Decimal
    sizing_policy_id: str
    sizing_policy_version: str
    sizing_policy_maximum_risk_percent: Decimal
    sizing_policy_maximum_notional_percent: Decimal
    sizing_policy_allow_fractional_shares: bool
    supplied_account_equity: Decimal
    supplied_risk_percent: Decimal
    execution_assumption_id: str
    execution_assumption_version: str
    outcome_model_id: str
    outcome_model_version: str
    outcome_model_no_overnight: bool
    cost_model_id: str
    cost_model_version: str
    cost_model_entry_slippage_bps: Decimal
    cost_model_exit_slippage_bps: Decimal
    cost_model_fixed_commission_per_side: Decimal
    ambiguity_policy: SameBarAmbiguityPolicy
    holding_horizon_bars: int
    status: HistoricalBacktestRunStatus
    product_classification: HistoricalValidationClassification
    evaluated_cutoff_count: int
    evaluated_opportunity_count: int
    approved_trade_plan_count: int
    approved_position_plan_count: int
    simulated_trade_count: int
    executed_trade_count: int
    win_count: int
    loss_count: int
    flat_count: int
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
    trades: tuple[HistoricalBacktestTrade, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.identity.governance_id, BacktestRunId):
            raise TypeError("identity governance_id must be a BacktestRunId")
        if self.dataset_start_timestamp.tzinfo is None or self.dataset_end_timestamp.tzinfo is None:
            raise ValueError("dataset timestamps must be timezone-aware")
        if self.evaluated_cutoff_count < 1:
            raise ValueError("evaluated_cutoff_count must be at least 1")
        if self.evaluated_opportunity_count < 1:
            raise ValueError("evaluated_opportunity_count must be at least 1")
        if len(self.trades) != self.simulated_trade_count:
            raise ValueError("simulated_trade_count must match the persisted trade count")


def dataset_sha256(raw_bytes: bytes) -> str:
    """Return the SHA-256 digest of a dataset's raw byte content."""
    return hashlib.sha256(raw_bytes).hexdigest()


def _validated_sequence(sequence: int) -> int:
    if sequence < 1 or sequence > 9999:
        raise ValueError("M061 local provenance identifiers support only sequence values 0001-9999")
    return sequence


def _local_candidate_id(sequence: int) -> DecisionCandidateId:
    return DecisionCandidateId(f"DCAND-{_validated_sequence(sequence):04d}")


def _local_scan_id(sequence: int) -> TradingOpportunityScanId:
    return TradingOpportunityScanId(f"SCAN-{_validated_sequence(sequence):04d}")


def _local_trade_plan_id(sequence: int) -> TradePlanId:
    return TradePlanId(f"PLAN-{_validated_sequence(sequence):04d}")


def _local_position_plan_id(sequence: int) -> PositionPlanId:
    return PositionPlanId(f"POS-{_validated_sequence(sequence):04d}")


def _ranked_entry(
    scan: TradingOpportunityScan,
    instrument: Instrument,
) -> tuple[int, Decimal]:
    for entry in scan.ranked_opportunities:
        if entry.instrument == instrument and entry.rank is not None and entry.score is not None:
            return entry.rank, entry.score
    raise ValueError(f"ranked entry missing for instrument {instrument}")


def _net_costs(
    *,
    quantity: int,
    entry_price: Decimal,
    exit_price: Decimal,
    cost_model: HistoricalCostModel,
) -> Decimal:
    entry_slippage = entry_price * (cost_model.entry_slippage_bps / Decimal("10000"))
    exit_slippage = exit_price * (cost_model.exit_slippage_bps / Decimal("10000"))
    return (
        (entry_slippage * quantity)
        + (exit_slippage * quantity)
        + (cost_model.fixed_commission_per_side * 2)
    )


def _simulate_trade(
    *,
    trade_sequence: int,
    position_plan: PositionPlan,
    scan: TradingOpportunityScan,
    trade_plan: TradePlan,
    entry_bars: Sequence[Bar],
    cost_model: HistoricalCostModel,
    outcome_model: HistoricalOutcomeModel,
) -> HistoricalBacktestTrade:
    sizing = position_plan.sizing
    geometry = trade_plan.geometry
    if sizing is None or geometry is None:
        raise ValueError("approved position plans must carry sizing")
    first_bar = entry_bars[0]
    entry_price = first_bar.open
    scan_rank, ranking_score = _ranked_entry(scan, position_plan.instrument)
    if entry_price <= sizing.stop_price or entry_price >= geometry.target_price:
        return HistoricalBacktestTrade(
            trade_sequence=trade_sequence,
            instrument=position_plan.instrument,
            evaluation_cutoff=trade_plan.evaluation_cutoff,
            source_scan_reference=str(scan.identity.governance_id),
            source_decision_candidate_reference=str(trade_plan.source_decision_candidate_id),
            source_trade_plan_reference=str(trade_plan.identity.governance_id),
            source_position_plan_reference=str(position_plan.identity.governance_id),
            scan_rank=scan_rank,
            ranking_score=ranking_score,
            entry_timestamp=None,
            planned_entry_price=sizing.entry_price,
            simulated_entry_price=None,
            planned_stop_price=sizing.stop_price,
            planned_target_price=geometry.target_price,
            exit_timestamp=None,
            exit_price=None,
            outcome=HistoricalTradeOutcome.NO_ENTRY,
            ambiguity_policy=outcome_model.ambiguity_policy,
            ambiguity_triggered=False,
            quantity=sizing.quantity,
            gross_pnl=Decimal("0"),
            transaction_costs=Decimal("0"),
            net_pnl=Decimal("0"),
            risk_amount=sizing.actual_risk,
            r_multiple=None,
            holding_bars=None,
        )

    ambiguity_triggered = False
    raw_exit_price: Decimal | None = None
    exit_timestamp: datetime | None = None
    outcome: HistoricalTradeOutcome | None = None
    holding_bars: int | None = None
    for index, bar in enumerate(entry_bars[: outcome_model.holding_horizon_bars], start=1):
        stop_hit = bar.low <= sizing.stop_price
        target_hit = bar.high >= geometry.target_price
        if stop_hit and target_hit:
            ambiguity_triggered = True
            raw_exit_price = sizing.stop_price
            exit_timestamp = bar.timestamp
            outcome = HistoricalTradeOutcome.STOP_HIT
            holding_bars = index
            break
        if stop_hit:
            raw_exit_price = sizing.stop_price
            exit_timestamp = bar.timestamp
            outcome = HistoricalTradeOutcome.STOP_HIT
            holding_bars = index
            break
        if target_hit:
            raw_exit_price = geometry.target_price
            exit_timestamp = bar.timestamp
            outcome = HistoricalTradeOutcome.TARGET_HIT
            holding_bars = index
            break
    if outcome is None:
        last_bar = entry_bars[outcome_model.holding_horizon_bars - 1]
        raw_exit_price = last_bar.close
        exit_timestamp = last_bar.timestamp
        outcome = HistoricalTradeOutcome.TIME_EXIT
        holding_bars = outcome_model.holding_horizon_bars

    quantity = sizing.quantity
    if raw_exit_price is None or exit_timestamp is None or holding_bars is None:
        raise ValueError("executed trades must resolve a concrete exit")
    gross_pnl = (raw_exit_price - entry_price) * quantity
    transaction_costs = _net_costs(
        quantity=quantity,
        entry_price=entry_price,
        exit_price=raw_exit_price,
        cost_model=cost_model,
    )
    net_pnl = gross_pnl - transaction_costs
    return HistoricalBacktestTrade(
        trade_sequence=trade_sequence,
        instrument=position_plan.instrument,
        evaluation_cutoff=trade_plan.evaluation_cutoff,
        source_scan_reference=str(scan.identity.governance_id),
        source_decision_candidate_reference=str(trade_plan.source_decision_candidate_id),
        source_trade_plan_reference=str(trade_plan.identity.governance_id),
        source_position_plan_reference=str(position_plan.identity.governance_id),
        scan_rank=scan_rank,
        ranking_score=ranking_score,
        entry_timestamp=first_bar.timestamp,
        planned_entry_price=sizing.entry_price,
        simulated_entry_price=entry_price,
        planned_stop_price=sizing.stop_price,
        planned_target_price=geometry.target_price,
        exit_timestamp=exit_timestamp,
        exit_price=raw_exit_price,
        outcome=outcome,
        ambiguity_policy=outcome_model.ambiguity_policy,
        ambiguity_triggered=ambiguity_triggered,
        quantity=quantity,
        gross_pnl=gross_pnl,
        transaction_costs=transaction_costs,
        net_pnl=net_pnl,
        risk_amount=sizing.actual_risk,
        r_multiple=net_pnl / sizing.actual_risk,
        holding_bars=holding_bars,
    )


def _drawdown(trades: Sequence[HistoricalBacktestTrade]) -> Decimal | None:
    executed = sorted(
        (trade for trade in trades if trade.executed),
        key=lambda trade: (trade.exit_timestamp, trade.trade_sequence),
    )
    if not executed:
        return None
    running = Decimal("0")
    peak = Decimal("0")
    max_drawdown = Decimal("0")
    for trade in executed:
        running += trade.net_pnl
        if running > peak:
            peak = running
        drawdown = peak - running
        if drawdown > max_drawdown:
            max_drawdown = drawdown
    return max_drawdown


def build_historical_backtest_run(
    *,
    identity: DomainIdentity[BacktestRunId],
    dataset: HistoricalDataset,
    sizing_context: PositionSizingContext,
    runtime_identifier_generator: RuntimeIdentifierGenerator,
    reference_window_size: int = 5,
    strategy_parameters: StrategyParameters | None = None,
    risk_policy: RiskPolicy = DEFAULT_RISK_POLICY,
    sizing_policy: SizingPolicy = DEFAULT_SIZING_POLICY,
    execution_assumption: HistoricalExecutionAssumption = DEFAULT_EXECUTION_ASSUMPTION,
    outcome_model: HistoricalOutcomeModel = DEFAULT_OUTCOME_MODEL,
    cost_model: HistoricalCostModel = DEFAULT_COST_MODEL,
) -> HistoricalBacktestRun:
    """Build one immutable historical backtest run from a fixed dataset."""
    if reference_window_size < 1:
        raise ValueError("reference_window_size must be at least 1")
    if dataset.bars_per_instrument <= reference_window_size + outcome_model.holding_horizon_bars:
        raise ValueError("dataset does not contain enough bars for the requested horizon")

    ordered_series = tuple(sorted(dataset.series, key=lambda series: str(series.instrument)))
    evaluated_cutoffs = range(
        reference_window_size,
        dataset.bars_per_instrument - outcome_model.holding_horizon_bars,
    )
    parameters = strategy_parameters or StrategyParameters(
        reference_window_size=reference_window_size
    )
    cutoff_count = len(evaluated_cutoffs)
    local_candidate_sequence = 0
    local_scan_sequence = 0
    local_trade_plan_sequence = 0
    local_position_plan_sequence = 0
    trade_sequence = 0
    approved_trade_plan_count = 0
    approved_position_plan_count = 0
    trades: list[HistoricalBacktestTrade] = []

    for cutoff_index in evaluated_cutoffs:
        windows = tuple(
            ObservationWindow(tuple(series.bars[: cutoff_index + 1])) for series in ordered_series
        )
        validate_scan_universe(windows)
        universe: list[tuple[Instrument, DecisionCandidateId, EvaluationOutcome]] = []
        candidates_by_id: dict[DecisionCandidateId, DecisionCandidate] = {}
        for window in windows:
            local_candidate_sequence += 1
            candidate_identity = DomainIdentity(
                governance_id=_local_candidate_id(local_candidate_sequence),
                runtime_id=runtime_identifier_generator.generate(),
            )
            outcome = evaluate(window, parameters)
            candidate = DecisionCandidate(
                identity=candidate_identity,
                target_evidence_package_id=_LOCAL_EVIDENCE_PACKAGE_ID,
                instrument=window.instrument,
                interval=window.interval,
                evaluation_timestamp=window.evaluation_bar.timestamp,
                strategy_id=STRATEGY_ID,
                strategy_version=STRATEGY_VERSION,
                reference_window_size=reference_window_size,
                outcome=outcome,
            )
            universe.append((window.instrument, candidate.identity.governance_id, outcome))
            candidates_by_id[candidate.identity.governance_id] = candidate

        local_scan_sequence += 1
        scan = build_scan(
            identity=DomainIdentity(
                governance_id=_local_scan_id(local_scan_sequence),
                runtime_id=runtime_identifier_generator.generate(),
            ),
            target_evidence_package_id=_LOCAL_EVIDENCE_PACKAGE_ID,
            strategy_id=STRATEGY_ID,
            strategy_version=STRATEGY_VERSION,
            evaluation_cutoff=windows[0].evaluation_bar.timestamp,
            universe=universe,
        )

        for ranked in scan.ranked_opportunities:
            candidate = candidates_by_id[ranked.decision_candidate_id]
            local_trade_plan_sequence += 1
            trade_plan = build_trade_plan(
                identity=DomainIdentity(
                    governance_id=_local_trade_plan_id(local_trade_plan_sequence),
                    runtime_id=runtime_identifier_generator.generate(),
                ),
                scan=scan,
                candidate=candidate,
                target_evidence_package_id=_LOCAL_EVIDENCE_PACKAGE_ID,
                policy=risk_policy,
            )
            if trade_plan.status is not TradePlanStatus.APPROVED_PLAN:
                continue
            approved_trade_plan_count += 1

            local_position_plan_sequence += 1
            position_plan = build_position_plan(
                identity=DomainIdentity(
                    governance_id=_local_position_plan_id(local_position_plan_sequence),
                    runtime_id=runtime_identifier_generator.generate(),
                ),
                trade_plan=trade_plan,
                sizing_context=sizing_context,
                policy=sizing_policy,
            )
            if position_plan.status is not PositionPlanStatus.APPROVED_POSITION_PLAN:
                continue
            approved_position_plan_count += 1
            trade_sequence += 1
            matching_series = next(
                series for series in ordered_series if series.instrument == position_plan.instrument
            )
            entry_bars = tuple(
                matching_series.bars[
                    cutoff_index + 1 : cutoff_index + 1 + outcome_model.holding_horizon_bars
                ]
            )
            trades.append(
                _simulate_trade(
                    trade_sequence=trade_sequence,
                    position_plan=position_plan,
                    scan=scan,
                    trade_plan=trade_plan,
                    entry_bars=entry_bars,
                    cost_model=cost_model,
                    outcome_model=outcome_model,
                )
            )

    executed_trades = [trade for trade in trades if trade.executed]
    wins = sum(1 for trade in executed_trades if trade.net_pnl > 0)
    losses = sum(1 for trade in executed_trades if trade.net_pnl < 0)
    flat = sum(1 for trade in executed_trades if trade.net_pnl == 0)
    time_exits = sum(1 for trade in trades if trade.outcome is HistoricalTradeOutcome.TIME_EXIT)
    no_entries = sum(1 for trade in trades if trade.outcome is HistoricalTradeOutcome.NO_ENTRY)
    gross_pnl = sum((trade.gross_pnl for trade in trades), Decimal("0"))
    net_pnl = sum((trade.net_pnl for trade in trades), Decimal("0"))
    total_r = sum(
        (trade.r_multiple for trade in executed_trades if trade.r_multiple is not None),
        Decimal("0"),
    )
    positive_net = sum(
        (trade.net_pnl for trade in executed_trades if trade.net_pnl > 0),
        Decimal("0"),
    )
    negative_net = sum(
        (trade.net_pnl for trade in executed_trades if trade.net_pnl < 0),
        Decimal("0"),
    )
    executed_count = len(executed_trades)

    return HistoricalBacktestRun(
        identity=identity,
        dataset_id=dataset.authority.dataset_id,
        dataset_version=dataset.authority.dataset_version,
        dataset_source_kind=dataset.authority.source_kind,
        dataset_sha256=dataset.authority.sha256,
        interval=dataset.authority.interval,
        universe=dataset.instruments,
        dataset_start_timestamp=dataset.authority.start_timestamp,
        dataset_end_timestamp=dataset.authority.end_timestamp,
        dataset_total_bars=dataset.authority.total_bars,
        reference_window_size=reference_window_size,
        decision_cadence=DECISION_CADENCE,
        strategy_id=STRATEGY_ID,
        strategy_version=STRATEGY_VERSION,
        ranking_model_id=RANKING_MODEL_ID,
        ranking_model_version=RANKING_MODEL_VERSION,
        risk_policy_id=risk_policy.policy_id,
        risk_policy_version=risk_policy.policy_version,
        risk_policy_target_projection_percent=risk_policy.target_projection_percent,
        risk_policy_minimum_reward_risk_ratio=risk_policy.minimum_reward_risk_ratio,
        sizing_policy_id=sizing_policy.policy_id,
        sizing_policy_version=sizing_policy.policy_version,
        sizing_policy_maximum_risk_percent=sizing_policy.maximum_risk_percent,
        sizing_policy_maximum_notional_percent=sizing_policy.maximum_notional_percent,
        sizing_policy_allow_fractional_shares=sizing_policy.allow_fractional_shares,
        supplied_account_equity=sizing_context.account_equity,
        supplied_risk_percent=sizing_context.risk_percent,
        execution_assumption_id=execution_assumption.assumption_id,
        execution_assumption_version=execution_assumption.assumption_version,
        outcome_model_id=outcome_model.model_id,
        outcome_model_version=outcome_model.model_version,
        outcome_model_no_overnight=outcome_model.no_overnight,
        cost_model_id=cost_model.model_id,
        cost_model_version=cost_model.model_version,
        cost_model_entry_slippage_bps=cost_model.entry_slippage_bps,
        cost_model_exit_slippage_bps=cost_model.exit_slippage_bps,
        cost_model_fixed_commission_per_side=cost_model.fixed_commission_per_side,
        ambiguity_policy=outcome_model.ambiguity_policy,
        holding_horizon_bars=outcome_model.holding_horizon_bars,
        status=HistoricalBacktestRunStatus.COMPLETED,
        product_classification=HistoricalValidationClassification.VALIDATION_ENGINE_PROVEN_FIXTURE_RESULTS_RECORDED,
        evaluated_cutoff_count=cutoff_count,
        evaluated_opportunity_count=cutoff_count * len(ordered_series),
        approved_trade_plan_count=approved_trade_plan_count,
        approved_position_plan_count=approved_position_plan_count,
        simulated_trade_count=len(trades),
        executed_trade_count=executed_count,
        win_count=wins,
        loss_count=losses,
        flat_count=flat,
        time_exit_count=time_exits,
        no_entry_count=no_entries,
        gross_pnl=gross_pnl,
        net_pnl=net_pnl,
        average_net_pnl=(net_pnl / executed_count) if executed_count else None,
        average_r=(total_r / executed_count) if executed_count else None,
        total_r=total_r,
        win_rate=(Decimal(wins) / Decimal(executed_count)) if executed_count else None,
        profit_factor=(positive_net / abs(negative_net) if negative_net != 0 else None),
        maximum_realized_pnl_drawdown=_drawdown(trades),
        trades=tuple(trades),
    )
