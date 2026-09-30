"""MILESTONE-091 -- post-hoc, read-only validation of the FROZEN M090 V1 replay output.

NOT A DOMAIN MODULE. This file never touches `decision_candidate.opportunity_engine` or its
gates; it consumes `usecases.opportunity_engine_replay.ReplayDecision`/`ReplaySessionResult`
objects the frozen replay code already produced, unmodified, and adds three things the
original Phase 19/20 replay did not: (1) a clearly-labeled MODELED cost-adjustment layer,
since the real replay's own zero-spread synthetic quote is documented as idealized, never a
measurement; (2) an aggregation/metrics layer broad enough to answer the M091 mission's exact
questions (per full-sample, per-block, per-symbol, per-hour); (3) a deterministic,
code-driven CANDIDATE_EDGE / NO_EDGE_FOUND / INCONCLUSIVE classification, so the
classification is auditable rather than a judgment call written in prose.

NO BROKER CAPABILITY OF ANY KIND. This module imports no broker client, no order type, no
dispatch handler -- it operates entirely on already-fetched `ReplayDecision` values. See
`tests/architecture/test_m091_validation_boundaries.py`.

THE COST MODELS ARE ASSUMPTIONS, NOT MEASUREMENTS -- STATED ONCE, HERE. Real historical
bid/ask evidence is not available through the existing read-only Alpaca Paper market-data
client without a materially larger architecture change (it exposes current quotes and
historical BARS, not a historical quotes/NBBO endpoint) -- see
`external-review/MILESTONE-091/owner-report.md`'s own note on this. Every cost-model number
below is a documented, conservative assumption applied uniformly to every trade, and every
report this module's output feeds says so.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from statistics import median
from typing import Literal

from empirical_platform.usecases.opportunity_engine_replay import (
    ReplayDecision,
    ReplaySessionResult,
)

__all__ = [
    "COST_MODEL_0",
    "COST_MODEL_1",
    "COST_MODEL_2",
    "ClassificationResult",
    "ConcentrationReport",
    "CostModel",
    "MetricsSummary",
    "TradeRecord",
    "aggregate",
    "classify",
    "concentration_report",
    "cost_adjusted_pnl_per_share",
    "extract_trade_records",
]

_RESOLVED_OUTCOMES = frozenset({"TARGET_HIT", "STOP_HIT", "MANDATORY_EXIT"})


@dataclass(frozen=True, slots=True)
class CostModel:
    """A MODELED, documented assumption -- never a measurement.

    `entry_cost_percent`/`exit_cost_percent` are the fraction of the raw (COST MODEL 0)
    fill price the trader is assumed to give up on entry and on exit respectively, applied
    AGAINST the trader always (a BUY entry costs MORE, a SELL exit yields LESS) -- modeling
    half-spread plus slippage on each side of a round trip.
    """

    name: str
    entry_cost_percent: Decimal
    exit_cost_percent: Decimal
    description: str


#: Idealized / zero friction -- the raw resolution the frozen replay already produces.
COST_MODEL_0 = CostModel(
    name="COST_MODEL_0_IDEALIZED",
    entry_cost_percent=Decimal("0"),
    exit_cost_percent=Decimal("0"),
    description="Zero friction. The raw synthetic-quote resolution, unmodified. Not realistic.",
)

#: Base conservative: ~3 bps modeled half-spread + ~2 bps modeled slippage per side, 10 bps
#: round trip total -- a conservative, not aggressive, estimate for the 8 large-cap/ETF
#: symbols in this validation's frozen universe (all normally tight-spread, highly liquid
#: names). Chosen as a documented, round, defensible assumption -- not fit to any result.
COST_MODEL_1 = CostModel(
    name="COST_MODEL_1_BASE_CONSERVATIVE",
    entry_cost_percent=Decimal("0.05"),
    exit_cost_percent=Decimal("0.05"),
    description=(
        "Modeled 0.05% cost per side (approx. 3 bps half-spread + 2 bps slippage), "
        "0.10% round trip. A documented assumption, not measured historical spread evidence."
    ),
)

#: Stress: 3x COST_MODEL_1, modeling a materially worse execution environment (wider
#: spreads, more slippage, e.g. during volatility) than the base case.
COST_MODEL_2 = CostModel(
    name="COST_MODEL_2_STRESS",
    entry_cost_percent=Decimal("0.15"),
    exit_cost_percent=Decimal("0.15"),
    description=(
        "Modeled 0.15% cost per side (3x COST_MODEL_1), 0.30% round trip. A stress "
        "assumption, not measured historical spread evidence."
    ),
)


def cost_adjusted_pnl_per_share(decision: ReplayDecision, cost_model: CostModel) -> Decimal | None:
    """Net P&L per share for one RESOLVED (non-UNRESOLVED) ACTIONABLE decision, under
    `cost_model`. `None` if the decision never became an ACTIONABLE, resolved trade."""
    if (
        decision.outcome is None
        or decision.outcome.value not in _RESOLVED_OUTCOMES
        or decision.entry_price is None
        or decision.outcome_price is None
    ):
        return None
    entry = decision.entry_price * (Decimal("1") + cost_model.entry_cost_percent / Decimal("100"))
    exit_ = decision.outcome_price * (Decimal("1") - cost_model.exit_cost_percent / Decimal("100"))
    return exit_ - entry


@dataclass(frozen=True, slots=True)
class TradeRecord:
    """One resolved, ACTIONABLE trade, with every field the metrics layer needs, extracted
    once from a `ReplayDecision` so the aggregation code below never re-reads the decision."""

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
    """Every RESOLVED (TARGET_HIT/STOP_HIT/MANDATORY_EXIT) ACTIONABLE decision across
    `results`, as a flat, cost-model-annotated `TradeRecord`. UNRESOLVED_END_OF_DATA
    decisions are real evidence of engine behavior (counted elsewhere) but carry no P&L --
    they are never included here."""
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
    # Chronological order is load-bearing: drawdown and losing-streak below assume it.
    records.sort(key=lambda r: (r.session_date, r.decided_hour_utc, r.symbol))
    return tuple(records)


@dataclass(frozen=True, slots=True)
class MetricsSummary:
    """Every metric the M091 mission's Phase 10 lists, for ONE (results slice, cost model)
    pair. `observations`/`opportunities`/`rejected_count`/`rejection_reasons`/`outcome_counts`
    are cost-model-independent (they come from the raw decisions, not P&L); everything else
    below is computed under the ONE cost model this summary was built for."""

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
    gross_pnl: Decimal  # always COST_MODEL_0, regardless of which model this summary is for
    net_pnl: Decimal  # under THIS summary's cost model
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
    """Every Phase 10 metric for `results` under `cost_model`. Caller supplies whatever
    SLICE of results it wants summarized (full sample, one block, one symbol, ...) -- this
    function does no filtering of its own."""
    all_decisions = [d for r in results for d in r.decisions]
    actionable = [d for d in all_decisions if not d.rejection_reasons]
    rejected = [d for d in all_decisions if d.rejection_reasons]
    reason_counts: Counter[str] = Counter(
        d.rejection_reasons[0].value for d in rejected if d.rejection_reasons
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
    """Phase 11: whether an apparent edge depends on one symbol/day/hour/trade."""

    total_net_pnl: Decimal
    best_symbol: str | None
    best_symbol_pnl: Decimal
    best_symbol_share_percent: Decimal | None
    best_day: date | None
    best_day_pnl: Decimal
    best_day_share_percent: Decimal | None
    best_hour_utc: int | None
    best_hour_pnl: Decimal
    best_hour_share_percent: Decimal | None
    largest_winning_trade_pnl: Decimal
    net_pnl_excluding_largest_winner: Decimal
    block_a_net_pnl: Decimal
    block_b_net_pnl: Decimal


def _share_percent(part: Decimal, total: Decimal) -> Decimal | None:
    if total == 0:
        return None
    return (part / total) * Decimal("100")


def concentration_report(
    records: tuple[TradeRecord, ...],
    *,
    cost_model: CostModel,
    block_a_dates: frozenset[date],
    block_b_dates: frozenset[date],
) -> ConcentrationReport:
    total = sum((_pnl_for_record(r, cost_model) for r in records), Decimal("0"))

    by_symbol: dict[str, Decimal] = {}
    by_day: dict[date, Decimal] = {}
    by_hour: dict[int, Decimal] = {}
    for r in records:
        pnl = _pnl_for_record(r, cost_model)
        by_symbol[r.symbol] = by_symbol.get(r.symbol, Decimal("0")) + pnl
        by_day[r.session_date] = by_day.get(r.session_date, Decimal("0")) + pnl
        by_hour[r.decided_hour_utc] = by_hour.get(r.decided_hour_utc, Decimal("0")) + pnl

    best_symbol = max(by_symbol, key=lambda k: by_symbol[k]) if by_symbol else None
    best_day = max(by_day, key=lambda k: by_day[k]) if by_day else None
    best_hour = max(by_hour, key=lambda k: by_hour[k]) if by_hour else None

    pnls = [_pnl_for_record(r, cost_model) for r in records]
    largest_winner = max(pnls) if pnls else Decimal("0")
    excluding_largest = total - largest_winner if pnls else Decimal("0")

    block_a_total = sum(
        (_pnl_for_record(r, cost_model) for r in records if r.session_date in block_a_dates),
        Decimal("0"),
    )
    block_b_total = sum(
        (_pnl_for_record(r, cost_model) for r in records if r.session_date in block_b_dates),
        Decimal("0"),
    )

    return ConcentrationReport(
        total_net_pnl=total,
        best_symbol=best_symbol,
        best_symbol_pnl=by_symbol.get(best_symbol, Decimal("0")) if best_symbol else Decimal("0"),
        best_symbol_share_percent=(
            _share_percent(by_symbol[best_symbol], total) if best_symbol else None
        ),
        best_day=best_day,
        best_day_pnl=by_day.get(best_day, Decimal("0")) if best_day else Decimal("0"),
        best_day_share_percent=_share_percent(by_day[best_day], total) if best_day else None,
        best_hour_utc=best_hour,
        best_hour_pnl=(
            by_hour.get(best_hour, Decimal("0")) if best_hour is not None else Decimal("0")
        ),
        best_hour_share_percent=(
            _share_percent(by_hour[best_hour], total) if best_hour is not None else None
        ),
        largest_winning_trade_pnl=largest_winner,
        net_pnl_excluding_largest_winner=excluding_largest,
        block_a_net_pnl=block_a_total,
        block_b_net_pnl=block_b_total,
    )


Classification = Literal["CANDIDATE_EDGE", "NO_EDGE_FOUND", "INCONCLUSIVE"]

#: Below this many total resolved trades (full sample, COST_MODEL_1), the sample is too
#: small to conclude anything either way.
MINIMUM_RESOLVED_TRADES = 30
#: Above this fraction of requested (symbol, session) pairs excluded for data-quality
#: reasons, the sample is considered too gappy to trust.
MAXIMUM_EXCLUDED_FRACTION = Decimal("0.20")
#: A single symbol or day owning more than this share of total net P&L is "depends on one".
MAXIMUM_SINGLE_CONTRIBUTOR_SHARE_PERCENT = Decimal("50")


@dataclass(frozen=True, slots=True)
class ClassificationResult:
    classification: Classification
    criteria: dict[str, bool]
    rationale: str


def classify(
    *,
    full_metrics_cost1: MetricsSummary,
    block_a_metrics_cost1: MetricsSummary,
    block_b_metrics_cost1: MetricsSummary,
    concentration: ConcentrationReport,
    excluded_fraction: Decimal,
) -> ClassificationResult:
    """Mechanical, auditable classification. Every criterion below is a plain boolean
    computed from already-computed metrics -- nothing here is a judgment call."""
    criteria: dict[str, bool] = {}

    criteria["enough_trades"] = full_metrics_cost1.trades_resolved >= MINIMUM_RESOLVED_TRADES
    criteria["data_not_too_gappy"] = excluded_fraction <= MAXIMUM_EXCLUDED_FRACTION
    if not criteria["enough_trades"] or not criteria["data_not_too_gappy"]:
        return ClassificationResult(
            classification="INCONCLUSIVE",
            criteria=criteria,
            rationale=(
                f"trades_resolved={full_metrics_cost1.trades_resolved} "
                f"(minimum {MINIMUM_RESOLVED_TRADES}), "
                f"excluded_fraction={excluded_fraction} "
                f"(maximum {MAXIMUM_EXCLUDED_FRACTION}) -- too little data to conclude "
                "either CANDIDATE_EDGE or NO_EDGE_FOUND."
            ),
        )

    a_net = block_a_metrics_cost1.net_pnl
    b_net = block_b_metrics_cost1.net_pnl
    a_pf = block_a_metrics_cost1.profit_factor
    b_pf = block_b_metrics_cost1.profit_factor
    a_avg = block_a_metrics_cost1.average_trade
    b_avg = block_b_metrics_cost1.average_trade

    criteria["block_a_positive"] = a_net > 0
    criteria["block_b_positive"] = b_net > 0
    criteria["block_a_pf_above_1"] = a_pf is not None and a_pf > 1
    criteria["block_b_pf_above_1"] = b_pf is not None and b_pf > 1
    criteria["block_a_avg_trade_positive"] = a_avg is not None and a_avg > 0
    criteria["block_b_avg_trade_positive"] = b_avg is not None and b_avg > 0
    criteria["not_single_symbol_dependent"] = (
        concentration.best_symbol_share_percent is None
        or concentration.best_symbol_share_percent <= MAXIMUM_SINGLE_CONTRIBUTOR_SHARE_PERCENT
    )
    criteria["not_single_day_dependent"] = (
        concentration.best_day_share_percent is None
        or concentration.best_day_share_percent <= MAXIMUM_SINGLE_CONTRIBUTOR_SHARE_PERCENT
    )

    candidate_edge_criteria = (
        "block_a_positive",
        "block_b_positive",
        "block_a_pf_above_1",
        "block_b_pf_above_1",
        "block_a_avg_trade_positive",
        "block_b_avg_trade_positive",
        "not_single_symbol_dependent",
        "not_single_day_dependent",
    )
    if all(criteria[key] for key in candidate_edge_criteria):
        return ClassificationResult(
            classification="CANDIDATE_EDGE",
            criteria=criteria,
            rationale="All CANDIDATE_EDGE criteria satisfied in both Block A and Block B.",
        )

    full_net = full_metrics_cost1.net_pnl
    full_pf = full_metrics_cost1.profit_factor
    hit_rate = full_metrics_cost1.hit_rate
    payoff = full_metrics_cost1.payoff_ratio
    criteria["full_sample_negative_expectancy"] = full_net <= 0
    criteria["full_sample_pf_at_or_below_1"] = full_pf is None or full_pf <= 1
    criteria["either_block_clearly_negative"] = a_net < 0 or b_net < 0
    criteria["stops_dominate_no_payoff"] = (
        hit_rate is not None and hit_rate < Decimal("0.4") and (payoff is None or payoff <= 1)
    )
    no_edge_triggers = (
        criteria["full_sample_negative_expectancy"]
        or criteria["full_sample_pf_at_or_below_1"]
        or criteria["either_block_clearly_negative"]
        or criteria["stops_dominate_no_payoff"]
    )
    if no_edge_triggers:
        return ClassificationResult(
            classification="NO_EDGE_FOUND",
            criteria=criteria,
            rationale=(
                f"full_net_pnl(cost1)={full_net}, full_profit_factor={full_pf}, "
                f"block_a_net={a_net}, block_b_net={b_net}, hit_rate={hit_rate}, "
                f"payoff_ratio={payoff} -- did not meet CANDIDATE_EDGE and shows a clear "
                "negative or unstable signal."
            ),
        )

    return ClassificationResult(
        classification="INCONCLUSIVE",
        criteria=criteria,
        rationale=(
            "Neither the full CANDIDATE_EDGE criteria nor a clear NO_EDGE_FOUND pattern was "
            "met -- the result is borderline/unstable rather than cleanly one or the other."
        ),
    )
