"""Portfolio capital-allocation historical evidence domain.

MILESTONE-067. A `PortfolioEvidenceReport` is a post-hoc, deterministic
historical replay of shared-capital competition across the trade
opportunities produced by an already-frozen M064
`SurvivorshipAwareRobustnessStudy` and its M061 window
`HistoricalBacktestRun`s. It never re-runs, re-ranks, re-sizes, or
re-optimizes anything upstream -- it only asks: when several genuinely
valid historical trade opportunities compete for one shared pool of
capital, which ones can actually be funded, and what does the resulting
portfolio-level equity/drawdown/exposure evidence look like?

This is historical research only. No broker, no live orders, no real
money, no portfolio optimizer -- see
`MILESTONE_067_PORTFOLIO_CAPITAL_ALLOCATION_CONCURRENT_POSITION_RISK_AND_PORTFOLIO_LEVEL_HISTORICAL_EVIDENCE_SCOPE_AND_DESIGN.md`
for the full design rationale, including the deterministic event-ordering
rule and the choice to model `PortfolioAllocationDecision` as doubling as
the position record for allocated opportunities (a position is simply an
allocation decision that succeeded), rather than introducing a second,
nearly-duplicate structure.

Portfolio equity is realized-PnL-only: it changes only at a position's
own CLOSE event, using the trade's own already-known, already-frozen
`net_pnl`. No mark-to-market price is invented for open positions --
"occupied capital" (the sum of `risk_amount` for currently open
positions) is reported as the exposure figure, never a fabricated
unrealized-PnL estimate the frozen data cannot honestly support.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum

from empirical_platform.decision_candidate.historical_backtest import HistoricalBacktestRun
from empirical_platform.decision_candidate.survivorship_study import (
    SurvivorshipAwareRobustnessStudy,
)
from empirical_platform.identifiers.pairs import DomainIdentity
from empirical_platform.identifiers.types import PortfolioStudyId

_MONEY_QUANT = Decimal("0.000001")
_RATIO_QUANT = Decimal("0.0001")

#: Only these confidence/utilization bounds are meaningful -- an explicit
#: closed set of predeclared capital-sensitivity scenarios, never a
#: search over scenarios to find the most favorable one (mission Phase
#: 15/29).
_REDUCED_CAPITAL_FACTOR = Decimal("0.5")
_TIGHTER_MAX_CONCURRENCY_DIVISOR = 3


class PortfolioAllocationOutcome(StrEnum):
    """Closed vocabulary: whether one candidate opportunity was funded."""

    ALLOCATED = "ALLOCATED"
    REJECTED = "REJECTED"


class PortfolioRejectionReason(StrEnum):
    """Closed vocabulary of reasons a historically-valid opportunity was
    not allocated. Never silently dropped -- every rejected opportunity
    persists exactly one of these."""

    INSUFFICIENT_AVAILABLE_CAPITAL = "INSUFFICIENT_AVAILABLE_CAPITAL"
    MAX_CONCURRENT_POSITIONS = "MAX_CONCURRENT_POSITIONS"
    MAX_CAPITAL_UTILIZATION_EXCEEDED = "MAX_CAPITAL_UTILIZATION_EXCEEDED"


class PortfolioEventKind(StrEnum):
    """Closed vocabulary of portfolio simulation event kinds."""

    OPEN = "OPEN"
    CLOSE = "CLOSE"


class CapitalSensitivityLabel(StrEnum):
    """Closed vocabulary of predeclared capital-sensitivity scenarios
    (mission Phase 15). Never searched for a favorable result -- exactly
    these 3 scenarios are always computed, in this fixed order."""

    CANONICAL = "CANONICAL"
    REDUCED_CAPITAL = "REDUCED_CAPITAL"
    TIGHTER_MAX_CONCURRENCY = "TIGHTER_MAX_CONCURRENCY"


@dataclass(frozen=True, slots=True)
class PortfolioCapitalPolicy:
    """Explicit, versioned, immutable shared-capital authority. No field
    here may ever be silently defaulted at the point of use -- every
    report persists the exact policy that produced it."""

    policy_id: str
    version: str
    initial_capital: Decimal
    currency: str
    max_concurrent_positions: int
    max_capital_utilization_percent: Decimal

    def __post_init__(self) -> None:
        if not self.policy_id.strip():
            raise ValueError("policy_id must be non-empty")
        if not self.version.strip():
            raise ValueError("version must be non-empty")
        if not isinstance(self.initial_capital, Decimal):
            raise TypeError("initial_capital must be a Decimal")
        if self.initial_capital <= 0:
            raise ValueError("initial_capital must be positive")
        if not self.currency.strip() or len(self.currency) != 3 or not self.currency.isupper():
            raise ValueError("currency must be a 3-letter uppercase code")
        if self.max_concurrent_positions < 1:
            raise ValueError("max_concurrent_positions must be at least 1")
        if not isinstance(self.max_capital_utilization_percent, Decimal):
            raise TypeError("max_capital_utilization_percent must be a Decimal")
        if not (Decimal("0") < self.max_capital_utilization_percent <= Decimal("1")):
            raise ValueError("max_capital_utilization_percent must be in (0, 1]")


DEFAULT_PORTFOLIO_CAPITAL_POLICY = PortfolioCapitalPolicy(
    policy_id="PORTFOLIO-CAPITAL-DEFAULT",
    version="1",
    initial_capital=Decimal("100000"),
    currency="USD",
    max_concurrent_positions=10,
    max_capital_utilization_percent=Decimal("1.00"),
)


@dataclass(frozen=True, slots=True)
class PortfolioAllocationDecision:
    """One decision for one candidate historical trade opportunity.
    Doubles as the position record for allocated opportunities --
    `entry_timestamp`/`exit_timestamp`/`risk_amount`/`net_pnl` are always
    the opportunity's own real, already-known historical facts (from the
    frozen M061 trade), regardless of whether it was actually funded;
    `decision`/`rejection_reason` record what the shared-capital policy
    did with it."""

    opportunity_sequence: int
    source_window_id: str
    trade_sequence: int
    instrument_symbol: str
    scan_rank: int
    entry_timestamp: datetime
    exit_timestamp: datetime
    risk_amount: Decimal
    net_pnl: Decimal
    decision: PortfolioAllocationOutcome
    rejection_reason: PortfolioRejectionReason | None

    def __post_init__(self) -> None:
        if self.opportunity_sequence < 1:
            raise ValueError("opportunity_sequence must be at least 1")
        if not self.source_window_id.strip():
            raise ValueError("source_window_id must be non-empty")
        if not self.instrument_symbol.strip():
            raise ValueError("instrument_symbol must be non-empty")
        if self.entry_timestamp.tzinfo is None:
            raise ValueError("entry_timestamp must be timezone-aware")
        if self.exit_timestamp.tzinfo is None:
            raise ValueError("exit_timestamp must be timezone-aware")
        if self.exit_timestamp < self.entry_timestamp:
            raise ValueError("exit_timestamp must not precede entry_timestamp")
        if self.risk_amount <= 0:
            raise ValueError("risk_amount must be positive")
        if self.decision is PortfolioAllocationOutcome.ALLOCATED:
            if self.rejection_reason is not None:
                raise ValueError("an ALLOCATED decision must not carry a rejection_reason")
        elif self.rejection_reason is None:
            raise ValueError("a REJECTED decision must carry a rejection_reason")


@dataclass(frozen=True, slots=True)
class PortfolioEquityObservation:
    """One immutable checkpoint of portfolio state, recorded at every
    OPEN and CLOSE event in canonical event order. `equity` is
    realized-PnL-only (`initial_capital + cumulative realized PnL`);
    `occupied_capital` is the sum of `risk_amount` for currently open
    positions, never a fabricated mark-to-market figure.

    `available_capital` CAN go negative: a closed position's real,
    frozen `net_pnl` (which may include slippage/cost beyond its own
    nominal `risk_amount`, confirmed to occur in real fixture data) is
    credited back in full, not clamped -- a realized loss larger than
    what was nominally reserved for it is honestly reported as reduced
    available capital, never hidden or capped to make the portfolio
    look healthier than it was. `occupied_capital` (a pure sum of
    currently-reserved, always-positive `risk_amount`s) can never be
    negative."""

    sequence_index: int
    event_timestamp: datetime
    event_kind: PortfolioEventKind
    equity: Decimal
    occupied_capital: Decimal
    available_capital: Decimal
    open_position_count: int

    def __post_init__(self) -> None:
        if self.sequence_index < 1:
            raise ValueError("sequence_index must be at least 1")
        if self.event_timestamp.tzinfo is None:
            raise ValueError("event_timestamp must be timezone-aware")
        if self.occupied_capital < 0:
            raise ValueError("occupied_capital must be non-negative")
        if self.open_position_count < 0:
            raise ValueError("open_position_count must be non-negative")


@dataclass(frozen=True, slots=True)
class CapitalSensitivityView:
    """One diagnostic capital-sensitivity scenario result. Descriptive
    only -- never alters the canonical report's own numbers, and never
    used to select a "better" policy (mission Phase 15/29)."""

    label: CapitalSensitivityLabel
    capital_policy_id: str
    initial_capital: Decimal
    max_concurrent_positions: int
    allocated_count: int
    rejected_count: int
    ending_capital: Decimal
    realized_pnl: Decimal
    max_drawdown: Decimal

    def __post_init__(self) -> None:
        if self.allocated_count < 0 or self.rejected_count < 0:
            raise ValueError("allocated_count/rejected_count must be non-negative")
        if self.max_drawdown < 0:
            raise ValueError("max_drawdown must be non-negative")


@dataclass(frozen=True, slots=True)
class PortfolioEvidenceReport:
    """One immutable, persisted, post-hoc portfolio capital-allocation
    evaluation of one already-frozen historical study. A fact computed
    once, never mutated -- mirrors every other M061-M066 study/result
    record in this codebase."""

    identity: DomainIdentity[PortfolioStudyId]

    # Upstream authority lineage -- copied verbatim from the source
    # study, never independently re-derived (mission Phase 18).
    source_study_governance_id: str
    source_study_runtime_id: str
    dataset_bundle_id: str
    dataset_bundle_version: str
    dataset_bundle_sha256: str
    dataset_source_kind: str
    universe_id: str
    universe_version: str
    membership_manifest_hash: str
    strategy_id: str
    strategy_version: str
    ranking_model_id: str
    ranking_model_version: str
    risk_policy_id: str
    risk_policy_version: str
    sizing_policy_id: str
    sizing_policy_version: str

    capital_policy: PortfolioCapitalPolicy

    total_opportunities: int
    allocated_count: int
    rejected_count: int
    rejected_insufficient_capital_count: int
    rejected_max_concurrent_count: int
    rejected_max_utilization_count: int

    initial_capital: Decimal
    ending_capital: Decimal
    realized_pnl: Decimal
    portfolio_return_percent: Decimal
    peak_equity: Decimal
    max_drawdown: Decimal
    max_drawdown_percent: Decimal | None

    max_concurrent_positions_observed: int
    average_concurrent_positions: Decimal | None
    peak_occupied_capital: Decimal
    peak_capital_utilization_percent: Decimal | None

    largest_instrument_positive_contribution_symbol: str | None
    largest_instrument_positive_contribution_amount: Decimal | None
    largest_instrument_negative_contribution_symbol: str | None
    largest_instrument_negative_contribution_amount: Decimal | None
    largest_position_contribution_trade_sequence: int | None
    largest_position_contribution_amount: Decimal | None
    largest_window_contribution_window_id: str | None
    largest_window_contribution_amount: Decimal | None

    allocation_decisions: tuple[PortfolioAllocationDecision, ...]
    equity_curve: tuple[PortfolioEquityObservation, ...]
    capital_sensitivity_views: tuple[CapitalSensitivityView, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.identity, DomainIdentity):
            raise TypeError("identity must be a DomainIdentity[PortfolioStudyId]")
        if not isinstance(self.identity.governance_id, PortfolioStudyId):
            raise TypeError("identity governance_id must be a PortfolioStudyId")
        for field_name in (
            "source_study_governance_id",
            "source_study_runtime_id",
            "dataset_bundle_id",
            "dataset_bundle_version",
            "dataset_bundle_sha256",
            "dataset_source_kind",
            "universe_id",
            "universe_version",
            "membership_manifest_hash",
            "strategy_id",
            "strategy_version",
            "ranking_model_id",
            "ranking_model_version",
            "risk_policy_id",
            "risk_policy_version",
            "sizing_policy_id",
            "sizing_policy_version",
        ):
            if not getattr(self, field_name).strip():
                raise ValueError(f"{field_name} must be non-empty")
        if self.total_opportunities < 0:
            raise ValueError("total_opportunities must be non-negative")
        if self.allocated_count + self.rejected_count != self.total_opportunities:
            raise ValueError("allocated_count + rejected_count must equal total_opportunities")
        if (
            self.rejected_insufficient_capital_count
            + self.rejected_max_concurrent_count
            + self.rejected_max_utilization_count
            != self.rejected_count
        ):
            raise ValueError("rejection-reason breakdown must sum to rejected_count")
        if len(self.allocation_decisions) != self.total_opportunities:
            raise ValueError("allocation_decisions length must equal total_opportunities")
        if len(self.capital_sensitivity_views) != len(CapitalSensitivityLabel):
            raise ValueError("capital_sensitivity_views must cover every predeclared scenario")


def _quantize_money(value: Decimal) -> Decimal:
    return value.quantize(_MONEY_QUANT, rounding=ROUND_HALF_UP)


def _quantize_ratio(value: Decimal) -> Decimal:
    return value.quantize(_RATIO_QUANT, rounding=ROUND_HALF_UP)


@dataclass(frozen=True, slots=True)
class _PooledOpportunity:
    """Internal, pre-decision view of one candidate trade opportunity
    pooled from upstream window backtest runs. Not persisted directly --
    consumed by `_simulate_capital_allocation` to produce
    `PortfolioAllocationDecision` rows."""

    source_window_id: str
    trade_sequence: int
    instrument_symbol: str
    scan_rank: int
    entry_timestamp: datetime
    exit_timestamp: datetime
    risk_amount: Decimal
    net_pnl: Decimal


def _pool_opportunities(
    study: SurvivorshipAwareRobustnessStudy,
    window_runs: tuple[HistoricalBacktestRun, ...],
) -> tuple[_PooledOpportunity, ...]:
    """Pool every executed trade across every window's own backtest run
    into one flat, canonically-ordered opportunity list. Canonical order
    is (entry_timestamp, source_window_id, trade_sequence) -- purely a
    function of authoritative historical data, never caller list order
    (mission Phase 16: order-independence).

    `window_runs` is matched to `study.window_results` by each run's own
    `runtime_id`, never by tuple position -- a caller-supplied
    `window_runs` in any order (or even out of correspondence with
    `study.window_results`'s own iteration order) must still produce the
    identical canonical pooling, since a positional `zip()` would
    silently mispair windows with the wrong run under any reordering."""
    runs_by_runtime_id = {str(run.identity.runtime_id): run for run in window_runs}
    opportunities: list[_PooledOpportunity] = []
    for window in study.window_results:
        if window.backtest_run_runtime_id is None:
            continue
        run = runs_by_runtime_id.get(str(window.backtest_run_runtime_id))
        if run is None:
            continue
        window_id = str(window.backtest_run_id) if window.backtest_run_id is not None else ""
        for trade in run.trades:
            if not trade.executed:
                continue
            assert trade.entry_timestamp is not None
            assert trade.exit_timestamp is not None
            opportunities.append(
                _PooledOpportunity(
                    source_window_id=window_id,
                    trade_sequence=trade.trade_sequence,
                    instrument_symbol=trade.instrument.symbol,
                    scan_rank=trade.scan_rank,
                    entry_timestamp=trade.entry_timestamp,
                    exit_timestamp=trade.exit_timestamp,
                    risk_amount=trade.risk_amount,
                    net_pnl=trade.net_pnl,
                )
            )
    return tuple(
        sorted(
            opportunities,
            key=lambda o: (o.entry_timestamp, o.source_window_id, o.trade_sequence),
        )
    )


@dataclass(frozen=True, slots=True)
class _Event:
    """One global timeline event. `priority` orders events sharing the
    same `timestamp`: 0 = a CLOSE belonging to a *different* opportunity
    than any same-instant OPEN (capital freed by an exit is available to
    a same-instant competing entry -- mission Phase 5), 1 = OPEN, 2 = a
    same-instant *self*-close of a zero-duration opportunity
    (`entry_timestamp == exit_timestamp`), which must always follow that
    same opportunity's own OPEN -- a position cannot close before it
    opens."""

    timestamp: datetime
    priority: int
    scan_rank: int
    instrument_symbol: str
    trade_sequence: int
    opportunity_index: int
    kind: PortfolioEventKind


def _build_event_timeline(opportunities: tuple[_PooledOpportunity, ...]) -> tuple[_Event, ...]:
    events: list[_Event] = []
    for index, opp in enumerate(opportunities):
        events.append(
            _Event(
                timestamp=opp.entry_timestamp,
                priority=1,
                scan_rank=opp.scan_rank,
                instrument_symbol=opp.instrument_symbol,
                trade_sequence=opp.trade_sequence,
                opportunity_index=index,
                kind=PortfolioEventKind.OPEN,
            )
        )
        close_priority = 2 if opp.exit_timestamp == opp.entry_timestamp else 0
        events.append(
            _Event(
                timestamp=opp.exit_timestamp,
                priority=close_priority,
                scan_rank=opp.scan_rank,
                instrument_symbol=opp.instrument_symbol,
                trade_sequence=opp.trade_sequence,
                opportunity_index=index,
                kind=PortfolioEventKind.CLOSE,
            )
        )
    return tuple(
        sorted(
            events,
            key=lambda e: (
                e.timestamp,
                e.priority,
                e.scan_rank,
                e.instrument_symbol,
                e.trade_sequence,
            ),
        )
    )


def _simulate_capital_allocation(
    opportunities: tuple[_PooledOpportunity, ...], policy: PortfolioCapitalPolicy
) -> tuple[tuple[PortfolioAllocationDecision, ...], tuple[PortfolioEquityObservation, ...]]:
    """Deterministic, single-pass, event-ordered capital-allocation
    replay over the true global timeline (mission Phase 5/6/9/16/17):
    every opportunity's OPEN and CLOSE are separate events on one shared
    timeline, so positions genuinely coexist -- an opportunity opened
    but not yet closed continues to occupy capital while later OPEN
    events are evaluated, exactly modeling concurrent positions.

    Event order: (timestamp, priority, scan_rank, instrument_symbol,
    trade_sequence) -- see `_Event` for the priority rule. A REJECTED
    opportunity's own CLOSE event is a no-op when reached (nothing was
    ever allocated, so nothing is released or observed). Future
    opportunities never influence earlier decisions: the full event
    timeline is computed once, up front, purely from immutable
    historical data (never caller input order), then replayed strictly
    in order with no lookahead."""
    timeline = _build_event_timeline(opportunities)

    available_capital = policy.initial_capital
    occupied_capital = Decimal("0")
    open_position_count = 0
    realized_pnl = Decimal("0")
    sequence_index = 0
    open_risk_amounts: dict[int, Decimal] = {}
    outcomes: dict[int, tuple[PortfolioAllocationOutcome, PortfolioRejectionReason | None]] = {}
    equity_points: list[PortfolioEquityObservation] = []

    def _record_observation(timestamp: datetime, kind: PortfolioEventKind) -> None:
        nonlocal sequence_index
        sequence_index += 1
        equity_points.append(
            PortfolioEquityObservation(
                sequence_index=sequence_index,
                event_timestamp=timestamp,
                event_kind=kind,
                equity=_quantize_money(policy.initial_capital + realized_pnl),
                occupied_capital=_quantize_money(occupied_capital),
                available_capital=_quantize_money(available_capital),
                open_position_count=open_position_count,
            )
        )

    for event in timeline:
        opp = opportunities[event.opportunity_index]
        if event.kind is PortfolioEventKind.OPEN:
            can_allocate = True
            reason: PortfolioRejectionReason | None = None
            if available_capital < opp.risk_amount:
                can_allocate = False
                reason = PortfolioRejectionReason.INSUFFICIENT_AVAILABLE_CAPITAL
            elif open_position_count >= policy.max_concurrent_positions:
                can_allocate = False
                reason = PortfolioRejectionReason.MAX_CONCURRENT_POSITIONS
            else:
                prospective_utilization = (
                    occupied_capital + opp.risk_amount
                ) / policy.initial_capital
                if prospective_utilization > policy.max_capital_utilization_percent:
                    can_allocate = False
                    reason = PortfolioRejectionReason.MAX_CAPITAL_UTILIZATION_EXCEEDED

            if can_allocate:
                available_capital -= opp.risk_amount
                occupied_capital += opp.risk_amount
                open_position_count += 1
                open_risk_amounts[event.opportunity_index] = opp.risk_amount
                outcomes[event.opportunity_index] = (PortfolioAllocationOutcome.ALLOCATED, None)
                _record_observation(event.timestamp, PortfolioEventKind.OPEN)
            else:
                outcomes[event.opportunity_index] = (PortfolioAllocationOutcome.REJECTED, reason)
        else:
            reserved = open_risk_amounts.pop(event.opportunity_index, None)
            if reserved is None:
                # This opportunity's own OPEN was rejected -- its CLOSE
                # is inert: nothing was ever allocated, so nothing is
                # released and no observation is recorded.
                continue
            # Release the reserved risk_amount AND apply this position's
            # own realized outcome to available capital in the same
            # step -- a profitable close genuinely makes more capital
            # available for later opportunities, a loss genuinely makes
            # less available (real portfolio cash accounting), not just
            # a return of the original reservation.
            available_capital += reserved + opp.net_pnl
            occupied_capital -= reserved
            open_position_count -= 1
            realized_pnl += opp.net_pnl
            _record_observation(event.timestamp, PortfolioEventKind.CLOSE)

    decisions = [
        PortfolioAllocationDecision(
            opportunity_sequence=index + 1,
            source_window_id=opp.source_window_id,
            trade_sequence=opp.trade_sequence,
            instrument_symbol=opp.instrument_symbol,
            scan_rank=opp.scan_rank,
            entry_timestamp=opp.entry_timestamp,
            exit_timestamp=opp.exit_timestamp,
            risk_amount=opp.risk_amount,
            net_pnl=opp.net_pnl,
            decision=outcomes[index][0],
            rejection_reason=outcomes[index][1],
        )
        for index, opp in enumerate(opportunities)
    ]

    return tuple(decisions), tuple(equity_points)


def _capital_sensitivity_view(
    label: CapitalSensitivityLabel,
    opportunities: tuple[_PooledOpportunity, ...],
    policy: PortfolioCapitalPolicy,
) -> CapitalSensitivityView:
    decisions, equity_points = _simulate_capital_allocation(opportunities, policy)
    allocated = sum(1 for d in decisions if d.decision is PortfolioAllocationOutcome.ALLOCATED)
    rejected = len(decisions) - allocated
    ending_capital = (
        equity_points[-1].equity if equity_points else _quantize_money(policy.initial_capital)
    )
    realized_pnl = _quantize_money(ending_capital - policy.initial_capital)
    max_drawdown = _max_drawdown_from_equity_curve(equity_points, policy.initial_capital)
    return CapitalSensitivityView(
        label=label,
        capital_policy_id=policy.policy_id,
        initial_capital=policy.initial_capital,
        max_concurrent_positions=policy.max_concurrent_positions,
        allocated_count=allocated,
        rejected_count=rejected,
        ending_capital=ending_capital,
        realized_pnl=realized_pnl,
        max_drawdown=max_drawdown,
    )


def _max_drawdown_from_equity_curve(
    equity_points: tuple[PortfolioEquityObservation, ...], initial_capital: Decimal
) -> Decimal:
    """Peak-to-trough drawdown over the authoritative portfolio equity
    sequence -- never derived by summing individual-trade drawdowns
    (mission Phase 14)."""
    peak = initial_capital
    max_dd = Decimal("0")
    for point in equity_points:
        peak = max(peak, point.equity)
        max_dd = max(max_dd, peak - point.equity)
    return _quantize_money(max_dd)


def build_portfolio_evidence_report(
    *,
    identity: DomainIdentity[PortfolioStudyId],
    study: SurvivorshipAwareRobustnessStudy,
    window_runs: tuple[HistoricalBacktestRun, ...],
    capital_policy: PortfolioCapitalPolicy = DEFAULT_PORTFOLIO_CAPITAL_POLICY,
) -> PortfolioEvidenceReport:
    """Build one immutable portfolio capital-allocation evidence report
    from an already-persisted `SurvivorshipAwareRobustnessStudy` and the
    individual `HistoricalBacktestRun`s referenced by its own windows.
    Pure and deterministic. Never mutates, re-ranks, re-sizes, or
    re-runs anything upstream."""
    opportunities = _pool_opportunities(study, window_runs)
    decisions, equity_points = _simulate_capital_allocation(opportunities, capital_policy)

    total = len(decisions)
    allocated = tuple(d for d in decisions if d.decision is PortfolioAllocationOutcome.ALLOCATED)
    rejected = tuple(d for d in decisions if d.decision is PortfolioAllocationOutcome.REJECTED)
    rejected_insufficient = sum(
        1
        for d in rejected
        if d.rejection_reason is PortfolioRejectionReason.INSUFFICIENT_AVAILABLE_CAPITAL
    )
    rejected_max_concurrent = sum(
        1
        for d in rejected
        if d.rejection_reason is PortfolioRejectionReason.MAX_CONCURRENT_POSITIONS
    )
    rejected_max_utilization = sum(
        1
        for d in rejected
        if d.rejection_reason is PortfolioRejectionReason.MAX_CAPITAL_UTILIZATION_EXCEEDED
    )

    ending_capital = (
        equity_points[-1].equity
        if equity_points
        else _quantize_money(capital_policy.initial_capital)
    )
    realized_pnl = _quantize_money(ending_capital - capital_policy.initial_capital)
    portfolio_return_percent = _quantize_ratio(realized_pnl / capital_policy.initial_capital)
    peak_equity = max([capital_policy.initial_capital] + [p.equity for p in equity_points])
    max_drawdown = _max_drawdown_from_equity_curve(equity_points, capital_policy.initial_capital)
    max_drawdown_percent = _quantize_ratio(max_drawdown / peak_equity) if peak_equity > 0 else None

    max_concurrent_observed = max((p.open_position_count for p in equity_points), default=0)
    peak_occupied_capital = max([Decimal("0")] + [p.occupied_capital for p in equity_points])
    peak_utilization_percent = (
        _quantize_ratio(peak_occupied_capital / capital_policy.initial_capital)
        if capital_policy.initial_capital > 0
        else None
    )

    average_concurrent: Decimal | None = None
    if len(equity_points) >= 2:
        weighted_sum = Decimal("0")
        total_seconds = Decimal("0")
        for prev, curr in zip(equity_points, equity_points[1:], strict=False):
            elapsed = Decimal(str((curr.event_timestamp - prev.event_timestamp).total_seconds()))
            weighted_sum += elapsed * prev.open_position_count
            total_seconds += elapsed
        average_concurrent = (
            _quantize_ratio(weighted_sum / total_seconds) if total_seconds > 0 else None
        )

    pnl_by_instrument: dict[str, Decimal] = {}
    pnl_by_window: dict[str, Decimal] = {}
    for d in allocated:
        pnl_by_instrument[d.instrument_symbol] = (
            pnl_by_instrument.get(d.instrument_symbol, Decimal("0")) + d.net_pnl
        )
        pnl_by_window[d.source_window_id] = (
            pnl_by_window.get(d.source_window_id, Decimal("0")) + d.net_pnl
        )

    largest_pos_symbol, largest_pos_amount = (None, None)
    positive_instruments = {k: v for k, v in pnl_by_instrument.items() if v > 0}
    if positive_instruments:
        largest_pos_symbol = max(positive_instruments, key=lambda k: positive_instruments[k])
        largest_pos_amount = _quantize_money(positive_instruments[largest_pos_symbol])

    largest_neg_symbol, largest_neg_amount = (None, None)
    negative_instruments = {k: v for k, v in pnl_by_instrument.items() if v < 0}
    if negative_instruments:
        largest_neg_symbol = min(negative_instruments, key=lambda k: negative_instruments[k])
        largest_neg_amount = _quantize_money(negative_instruments[largest_neg_symbol])

    largest_position_seq, largest_position_amount = (None, None)
    if allocated:
        best = max(allocated, key=lambda d: d.net_pnl)
        largest_position_seq = best.trade_sequence
        largest_position_amount = _quantize_money(best.net_pnl)

    largest_window_id, largest_window_amount = (None, None)
    if pnl_by_window:
        largest_window_id = max(pnl_by_window, key=lambda k: pnl_by_window[k])
        largest_window_amount = _quantize_money(pnl_by_window[largest_window_id])

    reduced_capital_policy = PortfolioCapitalPolicy(
        policy_id=f"{capital_policy.policy_id}-REDUCED-CAPITAL",
        version=capital_policy.version,
        initial_capital=_quantize_money(capital_policy.initial_capital * _REDUCED_CAPITAL_FACTOR),
        currency=capital_policy.currency,
        max_concurrent_positions=capital_policy.max_concurrent_positions,
        max_capital_utilization_percent=capital_policy.max_capital_utilization_percent,
    )
    tighter_concurrency_policy = PortfolioCapitalPolicy(
        policy_id=f"{capital_policy.policy_id}-TIGHTER-MAX-CONCURRENCY",
        version=capital_policy.version,
        initial_capital=capital_policy.initial_capital,
        currency=capital_policy.currency,
        max_concurrent_positions=max(
            1, capital_policy.max_concurrent_positions // _TIGHTER_MAX_CONCURRENCY_DIVISOR
        ),
        max_capital_utilization_percent=capital_policy.max_capital_utilization_percent,
    )
    capital_sensitivity_views = (
        _capital_sensitivity_view(CapitalSensitivityLabel.CANONICAL, opportunities, capital_policy),
        _capital_sensitivity_view(
            CapitalSensitivityLabel.REDUCED_CAPITAL, opportunities, reduced_capital_policy
        ),
        _capital_sensitivity_view(
            CapitalSensitivityLabel.TIGHTER_MAX_CONCURRENCY,
            opportunities,
            tighter_concurrency_policy,
        ),
    )

    return PortfolioEvidenceReport(
        identity=identity,
        source_study_governance_id=str(study.identity.governance_id),
        source_study_runtime_id=str(study.identity.runtime_id),
        dataset_bundle_id=str(study.dataset_bundle_id),
        dataset_bundle_version=study.dataset_bundle_version,
        dataset_bundle_sha256=study.dataset_bundle_sha256,
        dataset_source_kind=study.dataset_source_kind,
        universe_id=study.universe_id,
        universe_version=study.universe_version,
        membership_manifest_hash=study.membership_manifest_hash,
        strategy_id=study.strategy_id,
        strategy_version=study.strategy_version,
        ranking_model_id=study.ranking_model_id,
        ranking_model_version=study.ranking_model_version,
        risk_policy_id=study.risk_policy_id,
        risk_policy_version=study.risk_policy_version,
        sizing_policy_id=study.sizing_policy_id,
        sizing_policy_version=study.sizing_policy_version,
        capital_policy=capital_policy,
        total_opportunities=total,
        allocated_count=len(allocated),
        rejected_count=len(rejected),
        rejected_insufficient_capital_count=rejected_insufficient,
        rejected_max_concurrent_count=rejected_max_concurrent,
        rejected_max_utilization_count=rejected_max_utilization,
        initial_capital=capital_policy.initial_capital,
        ending_capital=ending_capital,
        realized_pnl=realized_pnl,
        portfolio_return_percent=portfolio_return_percent,
        peak_equity=_quantize_money(peak_equity),
        max_drawdown=max_drawdown,
        max_drawdown_percent=max_drawdown_percent,
        max_concurrent_positions_observed=max_concurrent_observed,
        average_concurrent_positions=average_concurrent,
        peak_occupied_capital=_quantize_money(peak_occupied_capital),
        peak_capital_utilization_percent=peak_utilization_percent,
        largest_instrument_positive_contribution_symbol=largest_pos_symbol,
        largest_instrument_positive_contribution_amount=largest_pos_amount,
        largest_instrument_negative_contribution_symbol=largest_neg_symbol,
        largest_instrument_negative_contribution_amount=largest_neg_amount,
        largest_position_contribution_trade_sequence=largest_position_seq,
        largest_position_contribution_amount=largest_position_amount,
        largest_window_contribution_window_id=largest_window_id,
        largest_window_contribution_amount=largest_window_amount,
        allocation_decisions=decisions,
        equity_curve=equity_points,
        capital_sensitivity_views=capital_sensitivity_views,
    )
