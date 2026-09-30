"""MILESTONE-093 Phase 3 -- ONE common, look-ahead-safe, cost-aware research framework
every strategy family shares.

WHY THIS EXISTS. Phase 3's own instruction: "This prevents one strategy from receiving more
favorable simulation assumptions." Every family built in this milestone plugs into this
module for bar fetching (holdout-guarded), the same-bar stop-first ambiguity rule, position
sizing, the three cost models, and the full metrics/concentration layer. The ONLY thing that
differs between families is their own entry/stop/target/regime signal logic -- never the
bars they see, the costs they pay, or the metrics computed over their results.

NOT A COPY-PASTE OF V1/V2'S OWN MODULES, BUT THE SAME NUMBERS AND RULES. Mirrors
`usecases.opportunity_engine_replay`/`opportunity_engine_v2_replay`/`opportunity_engine_validation`'s
own discipline exactly (same stop-first rule, same cost-model percentages, same metrics
formulas) without importing them -- M093 is architecturally independent of V1/V2, matching
the established parallel-module pattern V2 already set for V1. Every family family-specific
module in this milestone imports FROM HERE, never from V1/V2's own files.

HOLDOUT-GUARDED AT THE ONE FETCH POINT. `fetch_session_bars_guarded` is the SINGLE place any
M093 code fetches real market data; it calls `m093_holdout_guard.assert_not_holdout` before
ever calling the broker's read-only bars endpoint.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime, time
from decimal import ROUND_DOWN, Decimal
from enum import StrEnum
from statistics import median
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

from empirical_platform.decision_candidate.m093_holdout_guard import assert_not_holdout
from empirical_platform.decision_candidate.market_data import Bar, BarInterval, Instrument

if TYPE_CHECKING:
    from empirical_platform.decision_candidate.opportunity_engine_repositories import (
        IntradayBarsPort,
    )

__all__ = [
    "COST_MODEL_0",
    "COST_MODEL_1",
    "COST_MODEL_2",
    "ConcentrationReport",
    "CostModel",
    "MetricsSummary",
    "ReplayDecision",
    "ReplayOutcome",
    "ReplaySessionResult",
    "TradeRecord",
    "aggregate",
    "concentration_report",
    "cost_adjusted_pnl_per_share",
    "extract_trade_records",
    "fetch_session_bars_guarded",
    "position_size",
    "resolve_outcome",
]

_HUNDRED = Decimal("100")
_RESOLVED_OUTCOMES = frozenset({"TARGET_HIT", "STOP_HIT", "MANDATORY_EXIT"})


# ---------------------------------------------------------------------------
# Bar fetching -- the ONE holdout-guarded entry point
# ---------------------------------------------------------------------------


def fetch_session_bars_guarded(
    bars_port: IntradayBarsPort,
    symbol: str,
    session_date: date,
    *,
    session_start: time,
    session_end: time,
    operator_timezone: str,
) -> tuple[Bar, ...]:
    """Identical fetch/sort/dedupe behavior to V1's/V2's own `fetch_session_bars`, with ONE
    addition: `assert_not_holdout(session_date)` is called FIRST, before any network call.
    This is the single fetch point every M093 family and tool must use."""
    assert_not_holdout(session_date)
    zone = ZoneInfo(operator_timezone)
    start = datetime.combine(session_date, session_start, tzinfo=zone).astimezone(ZoneInfo("UTC"))
    end = datetime.combine(session_date, session_end, tzinfo=zone).astimezone(ZoneInfo("UTC"))
    raw = bars_port.fetch_minute_bars(symbol, start=start, end=end, limit=1000)
    instrument = Instrument(symbol)
    bars = [
        Bar(
            instrument=instrument,
            interval=BarInterval.ONE_MINUTE,
            timestamp=view.timestamp,
            open=Decimal(view.open),
            high=Decimal(view.high),
            low=Decimal(view.low),
            close=Decimal(view.close),
            volume=view.volume,
        )
        for view in raw
    ]
    bars.sort(key=lambda bar: bar.timestamp)
    deduped: list[Bar] = []
    for bar in bars:
        if deduped and deduped[-1].timestamp == bar.timestamp:
            continue
        deduped.append(bar)
    return tuple(deduped)


# ---------------------------------------------------------------------------
# Shared decision/outcome shape -- every family produces THESE types
# ---------------------------------------------------------------------------


class ReplayOutcome(StrEnum):
    TARGET_HIT = "TARGET_HIT"
    STOP_HIT = "STOP_HIT"
    MANDATORY_EXIT = "MANDATORY_EXIT"
    UNRESOLVED_END_OF_DATA = "UNRESOLVED_END_OF_DATA"


@dataclass(frozen=True, slots=True)
class ReplayDecision:
    """One bar's evaluation for ONE family. `family` names which strategy family produced
    this decision, so results from different families can be freely mixed in one report
    without losing provenance. `rejection_reasons` is a tuple of plain strings rather than a
    per-family StrEnum -- five families sharing one StrEnum would force every family to know
    about every other family's rejection vocabulary; plain strings keep each family's own
    vocabulary independent while still being fully reportable."""

    family: str
    bar_index: int
    decided_at: datetime
    symbol: str
    rejection_reasons: tuple[str, ...]
    entry_price: Decimal | None
    stop_price: Decimal | None
    target_price: Decimal | None
    risk_per_share: Decimal | None
    reward_per_share: Decimal | None
    reward_risk_ratio: Decimal | None
    quantity: int | None
    outcome: ReplayOutcome | None
    outcome_at: datetime | None
    outcome_price: Decimal | None
    realized_pnl_per_share: Decimal | None


@dataclass(frozen=True, slots=True)
class ReplaySessionResult:
    family: str
    symbol: str
    session_date: date
    bar_count: int
    decisions: tuple[ReplayDecision, ...]


def resolve_outcome(
    bars: Sequence[Bar],
    index: int,
    decision: ReplayDecision,
    *,
    mandatory_liquidation_at: datetime,
) -> ReplayDecision:
    """Resolve `decision` using ONLY `bars[index+1:]`. Same-bar stop/target ambiguity
    resolves STOP FIRST -- the conservative assumption, identical to V1/V2's own rule
    (Phase 16: "Do not select the favorable outcome when intrabar ordering is unknowable")."""
    if decision.stop_price is None or decision.target_price is None:
        return decision
    for later in bars[index + 1 :]:
        if later.timestamp >= mandatory_liquidation_at:
            return _with_outcome(
                decision, ReplayOutcome.MANDATORY_EXIT, later.timestamp, later.close
            )
        stop_touched = later.low <= decision.stop_price
        target_touched = later.high >= decision.target_price
        if stop_touched:
            return _with_outcome(
                decision, ReplayOutcome.STOP_HIT, later.timestamp, decision.stop_price
            )
        if target_touched:
            return _with_outcome(
                decision, ReplayOutcome.TARGET_HIT, later.timestamp, decision.target_price
            )
    return _with_outcome(decision, ReplayOutcome.UNRESOLVED_END_OF_DATA, None, None)


def _with_outcome(
    decision: ReplayDecision,
    outcome: ReplayOutcome,
    at: datetime | None,
    price: Decimal | None,
) -> ReplayDecision:
    from dataclasses import replace

    pnl = None if price is None or decision.entry_price is None else (price - decision.entry_price)
    return replace(
        decision, outcome=outcome, outcome_at=at, outcome_price=price, realized_pnl_per_share=pnl
    )


# ---------------------------------------------------------------------------
# Position sizing -- identical formula to V1/V2 (capital/risk math is not family-specific)
# ---------------------------------------------------------------------------


def position_size(
    *,
    entry_price: Decimal,
    stop_price: Decimal,
    maximum_loss: Decimal,
    maximum_capital_per_trade: Decimal,
    maximum_percent_per_trade: Decimal,
    deployable_capital: Decimal,
) -> int:
    risk_per_share = entry_price - stop_price
    if risk_per_share <= 0:
        raise ValueError("risk_per_share must be positive; check stop < entry first")
    by_risk = (maximum_loss / risk_per_share).to_integral_value(rounding=ROUND_DOWN)
    by_trade_cap = (maximum_capital_per_trade / entry_price).to_integral_value(rounding=ROUND_DOWN)
    by_percent_cap = (
        (deployable_capital * maximum_percent_per_trade / _HUNDRED) / entry_price
    ).to_integral_value(rounding=ROUND_DOWN)
    return int(min(by_risk, by_trade_cap, by_percent_cap))


# ---------------------------------------------------------------------------
# Cost models -- byte-identical assumptions to M091/M092 (Phase 4: "keep cost assumptions
# unchanged"). Ported, not imported, matching the established parallel-module pattern.
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class CostModel:
    name: str
    entry_cost_percent: Decimal
    exit_cost_percent: Decimal
    description: str


COST_MODEL_0 = CostModel(
    name="COST_MODEL_0_IDEALIZED",
    entry_cost_percent=Decimal("0"),
    exit_cost_percent=Decimal("0"),
    description="Zero friction. The raw synthetic-quote resolution, unmodified. Not realistic.",
)

COST_MODEL_1 = CostModel(
    name="COST_MODEL_1_BASE_CONSERVATIVE",
    entry_cost_percent=Decimal("0.05"),
    exit_cost_percent=Decimal("0.05"),
    description=(
        "Modeled 0.05% cost per side (approx. 3 bps half-spread + 2 bps slippage), "
        "0.10% round trip. A documented assumption, identical to M091/M092, not measured "
        "historical spread evidence."
    ),
)

COST_MODEL_2 = CostModel(
    name="COST_MODEL_2_STRESS",
    entry_cost_percent=Decimal("0.15"),
    exit_cost_percent=Decimal("0.15"),
    description=(
        "Modeled 0.15% cost per side (3x COST_MODEL_1), 0.30% round trip. A stress "
        "assumption, identical to M091/M092, not measured historical spread evidence."
    ),
)


def cost_adjusted_pnl_per_share(decision: ReplayDecision, cost_model: CostModel) -> Decimal | None:
    if (
        decision.outcome is None
        or decision.outcome.value not in _RESOLVED_OUTCOMES
        or decision.entry_price is None
        or decision.outcome_price is None
    ):
        return None
    entry = decision.entry_price * (Decimal("1") + cost_model.entry_cost_percent / _HUNDRED)
    exit_ = decision.outcome_price * (Decimal("1") - cost_model.exit_cost_percent / _HUNDRED)
    return exit_ - entry


# ---------------------------------------------------------------------------
# Metrics -- same formulas as M091/M092's own MetricsSummary/aggregate
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class TradeRecord:
    family: str
    symbol: str
    session_date: date
    decided_hour_utc: int
    outcome: str
    quantity: int
    maximum_loss: Decimal
    reward_risk_ratio: Decimal | None
    holding_seconds: float | None
    pnl_per_share_0: Decimal
    pnl_per_share_1: Decimal
    pnl_per_share_2: Decimal
    pnl_total_0: Decimal
    pnl_total_1: Decimal
    pnl_total_2: Decimal


def extract_trade_records(results: list[ReplaySessionResult]) -> tuple[TradeRecord, ...]:
    records: list[TradeRecord] = []
    for result in results:
        for decision in result.decisions:
            if decision.outcome is None or decision.outcome.value not in _RESOLVED_OUTCOMES:
                continue
            assert decision.quantity is not None and decision.risk_per_share is not None
            pnl0 = cost_adjusted_pnl_per_share(decision, COST_MODEL_0)
            pnl1 = cost_adjusted_pnl_per_share(decision, COST_MODEL_1)
            pnl2 = cost_adjusted_pnl_per_share(decision, COST_MODEL_2)
            assert pnl0 is not None and pnl1 is not None and pnl2 is not None
            holding_seconds = (
                (decision.outcome_at - decision.decided_at).total_seconds()
                if decision.outcome_at is not None
                else None
            )
            records.append(
                TradeRecord(
                    family=decision.family,
                    symbol=decision.symbol,
                    session_date=result.session_date,
                    decided_hour_utc=decision.decided_at.hour,
                    outcome=decision.outcome.value,
                    quantity=decision.quantity,
                    maximum_loss=decision.risk_per_share * Decimal(decision.quantity),
                    reward_risk_ratio=decision.reward_risk_ratio,
                    holding_seconds=holding_seconds,
                    pnl_per_share_0=pnl0,
                    pnl_per_share_1=pnl1,
                    pnl_per_share_2=pnl2,
                    pnl_total_0=pnl0 * Decimal(decision.quantity),
                    pnl_total_1=pnl1 * Decimal(decision.quantity),
                    pnl_total_2=pnl2 * Decimal(decision.quantity),
                )
            )
    records.sort(key=lambda r: (r.session_date, r.decided_hour_utc, r.symbol))
    return tuple(records)


@dataclass(frozen=True, slots=True)
class MetricsSummary:
    cost_model_name: str
    observations: int
    opportunities: int
    rejected_count: int
    rejection_reasons: dict[str, int]
    trades_resolved: int
    target_hits: int
    stop_hits: int
    mandatory_exits: int
    unresolved: int
    gross_pnl: Decimal
    net_pnl: Decimal
    average_trade: Decimal | None
    median_trade: Decimal | None
    average_winner: Decimal | None
    average_loser: Decimal | None
    payoff_ratio: Decimal | None
    hit_rate: Decimal | None
    profit_factor: Decimal | None
    max_drawdown: Decimal
    longest_losing_streak: int
    average_holding_seconds: float | None
    maximum_loss_min: Decimal | None
    maximum_loss_median: Decimal | None
    maximum_loss_max: Decimal | None
    reward_risk_min: Decimal | None
    reward_risk_median: Decimal | None
    reward_risk_max: Decimal | None


def _pnl_for_record(record: TradeRecord, cost_model: CostModel) -> Decimal:
    if cost_model.name == COST_MODEL_0.name:
        return record.pnl_total_0
    if cost_model.name == COST_MODEL_1.name:
        return record.pnl_total_1
    if cost_model.name == COST_MODEL_2.name:
        return record.pnl_total_2
    raise ValueError(f"unknown cost model {cost_model.name!r}")


def _drawdown_and_streak(pnls_in_order: list[Decimal]) -> tuple[Decimal, int]:
    equity = Decimal("0")
    peak = Decimal("0")
    max_dd = Decimal("0")
    streak = 0
    longest_streak = 0
    for pnl in pnls_in_order:
        equity += pnl
        if equity > peak:
            peak = equity
        drawdown = peak - equity
        if drawdown > max_dd:
            max_dd = drawdown
        if pnl < 0:
            streak += 1
            longest_streak = max(longest_streak, streak)
        else:
            streak = 0
    return max_dd, longest_streak


def _decimal_stats(values: list[Decimal]) -> tuple[Decimal | None, Decimal | None, Decimal | None]:
    if not values:
        return None, None, None
    ordered = sorted(values)
    return ordered[0], median(ordered), ordered[-1]


def aggregate(results: list[ReplaySessionResult], *, cost_model: CostModel) -> MetricsSummary:
    all_decisions = [d for r in results for d in r.decisions]
    actionable = [d for d in all_decisions if not d.rejection_reasons]
    rejected = [d for d in all_decisions if d.rejection_reasons]
    reason_counts: Counter[str] = Counter(
        d.rejection_reasons[0] for d in rejected if d.rejection_reasons
    )
    outcome_counts: Counter[str] = Counter(
        d.outcome.value for d in actionable if d.outcome is not None
    )

    records = extract_trade_records(results)
    pnls = [_pnl_for_record(r, cost_model) for r in records]
    gross_pnl = sum((r.pnl_total_0 for r in records), Decimal("0"))
    net_pnl = sum(pnls, Decimal("0"))
    winners = [p for p in pnls if p > 0]
    losers = [p for p in pnls if p <= 0]
    average_trade = (net_pnl / len(pnls)) if pnls else None
    median_trade = median(pnls) if pnls else None
    average_winner = (sum(winners, Decimal("0")) / len(winners)) if winners else None
    average_loser = (sum(losers, Decimal("0")) / len(losers)) if losers else None
    payoff_ratio = (
        (average_winner / abs(average_loser))
        if average_winner is not None and average_loser is not None and average_loser != 0
        else None
    )
    hit_rate = (Decimal(len(winners)) / Decimal(len(pnls))) if pnls else None
    gross_profit = sum(winners, Decimal("0"))
    gross_loss = abs(sum(losers, Decimal("0")))
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else None
    max_dd, streak = _drawdown_and_streak(pnls)
    holding = [r.holding_seconds for r in records if r.holding_seconds is not None]
    avg_holding = (sum(holding) / len(holding)) if holding else None
    ml_min, ml_med, ml_max = _decimal_stats([r.maximum_loss for r in records])
    rr_values = [r.reward_risk_ratio for r in records if r.reward_risk_ratio is not None]
    rr_min, rr_med, rr_max = _decimal_stats(rr_values)

    return MetricsSummary(
        cost_model_name=cost_model.name,
        observations=len(all_decisions),
        opportunities=len(actionable),
        rejected_count=len(rejected),
        rejection_reasons=dict(reason_counts),
        trades_resolved=len(records),
        target_hits=outcome_counts.get("TARGET_HIT", 0),
        stop_hits=outcome_counts.get("STOP_HIT", 0),
        mandatory_exits=outcome_counts.get("MANDATORY_EXIT", 0),
        unresolved=outcome_counts.get("UNRESOLVED_END_OF_DATA", 0),
        gross_pnl=gross_pnl,
        net_pnl=net_pnl,
        average_trade=average_trade,
        median_trade=median_trade,
        average_winner=average_winner,
        average_loser=average_loser,
        payoff_ratio=payoff_ratio,
        hit_rate=hit_rate,
        profit_factor=profit_factor,
        max_drawdown=max_dd,
        longest_losing_streak=streak,
        average_holding_seconds=avg_holding,
        maximum_loss_min=ml_min,
        maximum_loss_median=ml_med,
        maximum_loss_max=ml_max,
        reward_risk_min=rr_min,
        reward_risk_median=rr_med,
        reward_risk_max=rr_max,
    )


@dataclass(frozen=True, slots=True)
class ConcentrationReport:
    """Share-of-GROSS-PROFIT concentration (stays meaningful with a negative total, unlike a
    share-of-net-P&L formula -- the same fix M092's own `concentration_report_v2` made)."""

    total_net_pnl: Decimal
    total_gross_profit: Decimal
    trade_count: int
    per_symbol_trade_counts: dict[str, int]
    top_symbol_by_trade_count: str | None
    top_symbol_trade_count_share_percent: Decimal | None
    top_symbol_by_gross_profit: str | None
    top_symbol_gross_profit_share_percent: Decimal | None
    top_day_by_gross_profit: str | None
    top_day_gross_profit_share_percent: Decimal | None
    net_pnl_excluding_top_trade_count_symbol: Decimal
    net_pnl_excluding_top_gross_profit_day: Decimal


def concentration_report(
    records: tuple[TradeRecord, ...], *, cost_model: CostModel
) -> ConcentrationReport:
    pnls: list[Decimal] = [_pnl_for_record(r, cost_model) for r in records]
    total_net = sum(pnls, Decimal("0"))
    total_gross_profit = sum((p for p in pnls if p > 0), Decimal("0"))

    by_symbol_count: dict[str, int] = {}
    by_symbol_profit: dict[str, Decimal] = {}
    by_day_profit: dict[date, Decimal] = {}
    for record, pnl in zip(records, pnls, strict=True):
        by_symbol_count[record.symbol] = by_symbol_count.get(record.symbol, 0) + 1
        if pnl > 0:
            by_symbol_profit[record.symbol] = (
                by_symbol_profit.get(record.symbol, Decimal("0")) + pnl
            )
            by_day_profit[record.session_date] = (
                by_day_profit.get(record.session_date, Decimal("0")) + pnl
            )

    top_count_symbol = max(by_symbol_count, key=lambda k: by_symbol_count[k]) if records else None
    top_count_share = (
        (Decimal(by_symbol_count[top_count_symbol]) / Decimal(len(records)) * _HUNDRED)
        if top_count_symbol
        else None
    )
    top_profit_symbol = (
        max(by_symbol_profit, key=lambda k: by_symbol_profit[k]) if by_symbol_profit else None
    )
    top_profit_symbol_share = (
        (by_symbol_profit[top_profit_symbol] / total_gross_profit * _HUNDRED)
        if top_profit_symbol is not None and total_gross_profit > 0
        else None
    )
    top_day = max(by_day_profit, key=lambda k: by_day_profit[k]) if by_day_profit else None
    top_day_share = (
        (by_day_profit[top_day] / total_gross_profit * _HUNDRED)
        if top_day is not None and total_gross_profit > 0
        else None
    )

    paired = tuple(zip(records, pnls, strict=True))
    net_excl_symbol = (
        sum((pnl for record, pnl in paired if record.symbol != top_count_symbol), Decimal("0"))
        if top_count_symbol is not None
        else total_net
    )
    net_excl_day = (
        sum((pnl for record, pnl in paired if record.session_date != top_day), Decimal("0"))
        if top_day is not None
        else total_net
    )

    return ConcentrationReport(
        total_net_pnl=total_net,
        total_gross_profit=total_gross_profit,
        trade_count=len(records),
        per_symbol_trade_counts=by_symbol_count,
        top_symbol_by_trade_count=top_count_symbol,
        top_symbol_trade_count_share_percent=top_count_share,
        top_symbol_by_gross_profit=top_profit_symbol,
        top_symbol_gross_profit_share_percent=top_profit_symbol_share,
        top_day_by_gross_profit=top_day.isoformat() if top_day is not None else None,
        top_day_gross_profit_share_percent=top_day_share,
        net_pnl_excluding_top_trade_count_symbol=net_excl_symbol,
        net_pnl_excluding_top_gross_profit_day=net_excl_day,
    )
