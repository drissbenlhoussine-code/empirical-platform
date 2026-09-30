"""MILESTONE-092 Phase 18-19 -- V2-specific concentration/fragility analysis and mechanical
classification.

SEPARATE FROM M091's OWN `opportunity_engine_validation.classify()` -- that function
implements M091's own release criteria; M092 has DIFFERENT criteria (Phase 19: BOTH
VALIDATION and FINAL HOLDOUT must independently clear the bar), so a new, equally
mechanical function is used rather than overloading M091's.

THE CONCENTRATION FORMULA HERE IS DELIBERATELY DIFFERENT FROM M091's OWN
`concentration_report()`. M091's own report already noted its "share of total net P&L"
formula becomes mathematically meaningless when total net P&L is negative (dividing a
symbol's own P&L by a negative total inverts the sign of its "share"). This module instead
uses SHARE OF GROSS PROFIT (the sum of only the winning trades' P&L, always >= 0), which
stays meaningful regardless of whether the overall net result is positive or negative, plus
trade-COUNT concentration (which needs no P&L sign at all) and leave-one-out sensitivity.

NO BROKER CAPABILITY. Operates entirely on already-computed `TradeRecord`/`MetricsSummary`
values; imports no broker client, order type, or dispatch handler.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Literal

from empirical_platform.usecases.opportunity_engine_validation import (
    CostModel,
    MetricsSummary,
    TradeRecord,
    _pnl_for_record,  # noqa: PLC2701 - same package, deliberate reuse of the one P&L helper
)

__all__ = [
    "MAXIMUM_SINGLE_CONTRIBUTOR_SHARE_PERCENT",
    "MAXIMUM_VALIDATION_TO_HOLDOUT_DEGRADATION_PERCENT",
    "MINIMUM_RESOLVED_TRADES",
    "Classification",
    "ClassificationResultV2",
    "ConcentrationReportV2",
    "classify_v2",
    "concentration_report_v2",
]


@dataclass(frozen=True, slots=True)
class ConcentrationReportV2:
    total_net_pnl: Decimal
    total_gross_profit: Decimal
    trade_count: int
    per_symbol_trade_counts: dict[str, int]
    top_symbol_by_trade_count: str | None
    top_symbol_trade_count: int
    top_symbol_trade_count_share_percent: Decimal | None
    top_symbol_by_gross_profit: str | None
    top_symbol_gross_profit_share_percent: Decimal | None
    top_day_by_gross_profit: str | None
    top_day_gross_profit_share_percent: Decimal | None
    net_pnl_excluding_top_trade_count_symbol: Decimal
    net_pnl_excluding_top_gross_profit_day: Decimal


def concentration_report_v2(
    records: tuple[TradeRecord, ...], *, cost_model: CostModel
) -> ConcentrationReportV2:
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
    top_count = by_symbol_count.get(top_count_symbol, 0) if top_count_symbol else 0
    top_count_share = (Decimal(top_count) / Decimal(len(records)) * 100) if records else None

    top_profit_symbol = (
        max(by_symbol_profit, key=lambda k: by_symbol_profit[k]) if by_symbol_profit else None
    )
    top_profit_symbol_share = (
        (by_symbol_profit[top_profit_symbol] / total_gross_profit * 100)
        if top_profit_symbol is not None and total_gross_profit > 0
        else None
    )

    top_day = max(by_day_profit, key=lambda k: by_day_profit[k]) if by_day_profit else None
    top_day_share = (
        (by_day_profit[top_day] / total_gross_profit * 100)
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

    return ConcentrationReportV2(
        total_net_pnl=total_net,
        total_gross_profit=total_gross_profit,
        trade_count=len(records),
        per_symbol_trade_counts=by_symbol_count,
        top_symbol_by_trade_count=top_count_symbol,
        top_symbol_trade_count=top_count,
        top_symbol_trade_count_share_percent=top_count_share,
        top_symbol_by_gross_profit=top_profit_symbol,
        top_symbol_gross_profit_share_percent=top_profit_symbol_share,
        top_day_by_gross_profit=top_day.isoformat() if top_day is not None else None,
        top_day_gross_profit_share_percent=top_day_share,
        net_pnl_excluding_top_trade_count_symbol=net_excl_symbol,
        net_pnl_excluding_top_gross_profit_day=net_excl_day,
    )


Classification = Literal["CANDIDATE_EDGE_V2", "NO_EDGE_V2", "INCONCLUSIVE_V2"]

#: Below this many resolved trades, VALIDATION or FINAL HOLDOUT cannot support a conclusion
#: on its own -- reused from M091's own threshold for consistency across milestones.
MINIMUM_RESOLVED_TRADES = 30
#: A single symbol or day owning more than this share of GROSS PROFIT is "depends on one".
MAXIMUM_SINGLE_CONTRIBUTOR_SHARE_PERCENT = Decimal("50")
#: How much the average trade may fall from VALIDATION to FINAL HOLDOUT before the result is
#: "severe degradation" rather than ordinary sample-to-sample variation. Documented, not
#: fit to any observed result (written into this module before any HOLDOUT number existed).
MAXIMUM_VALIDATION_TO_HOLDOUT_DEGRADATION_PERCENT = Decimal("50")


@dataclass(frozen=True, slots=True)
class ClassificationResultV2:
    classification: Classification
    criteria: dict[str, bool]
    rationale: str


def classify_v2(
    *,
    validation_metrics: MetricsSummary,
    validation_concentration: ConcentrationReportV2,
    holdout_metrics: MetricsSummary | None,
    holdout_concentration: ConcentrationReportV2 | None,
) -> ClassificationResultV2:
    """Mechanical, auditable. Every criterion is a plain boolean computed from
    already-computed metrics -- nothing here is a judgment call.

    Per the mission's own Phase 14: if VALIDATION does not clear its own bar, the result is
    NO_EDGE_V2 and FINAL HOLDOUT is never inspected (`holdout_metrics` will correctly be
    `None` in that case, supplied by the caller, which never fetched it). This function
    never returns INCONCLUSIVE_V2 to avoid saying NO_EDGE_V2 when VALIDATION mechanically
    fails -- INCONCLUSIVE_V2 is reserved for the (should-not-happen-in-practice) case where
    VALIDATION passed but no HOLDOUT result was supplied at all.
    """
    criteria: dict[str, bool] = {}

    v_net = validation_metrics.net_pnl
    v_pf = validation_metrics.profit_factor
    v_avg = validation_metrics.average_trade
    criteria["validation_net_positive"] = v_net > 0
    criteria["validation_pf_above_1"] = v_pf is not None and v_pf > 1
    criteria["validation_avg_trade_positive"] = v_avg is not None and v_avg > 0
    criteria["validation_enough_trades"] = (
        validation_metrics.trades_resolved >= MINIMUM_RESOLVED_TRADES
    )

    validation_passed = (
        criteria["validation_net_positive"]
        and criteria["validation_pf_above_1"]
        and criteria["validation_avg_trade_positive"]
    )

    if not validation_passed:
        return ClassificationResultV2(
            classification="NO_EDGE_V2",
            criteria=criteria,
            rationale=(
                f"VALIDATION did not clear the required bar (net={v_net}, pf={v_pf}, "
                f"avg_trade={v_avg}) -- per the mission's own Phase 14 instruction, this is "
                "classified NO_EDGE_V2 and FINAL HOLDOUT was never run or inspected."
            ),
        )

    if holdout_metrics is None or holdout_concentration is None:
        return ClassificationResultV2(
            classification="INCONCLUSIVE_V2",
            criteria=criteria,
            rationale=(
                "VALIDATION cleared its own bar but no FINAL HOLDOUT result was supplied -- "
                "CANDIDATE_EDGE_V2 cannot be claimed without a HOLDOUT pass."
            ),
        )

    h_net = holdout_metrics.net_pnl
    h_pf = holdout_metrics.profit_factor
    h_avg = holdout_metrics.average_trade
    criteria["holdout_net_positive"] = h_net > 0
    criteria["holdout_pf_above_1"] = h_pf is not None and h_pf > 1
    criteria["holdout_avg_trade_positive"] = h_avg is not None and h_avg > 0
    criteria["holdout_enough_trades"] = holdout_metrics.trades_resolved >= MINIMUM_RESOLVED_TRADES

    criteria["validation_not_single_symbol_dependent"] = (
        validation_concentration.top_symbol_gross_profit_share_percent is None
        or validation_concentration.top_symbol_gross_profit_share_percent
        <= MAXIMUM_SINGLE_CONTRIBUTOR_SHARE_PERCENT
    )
    criteria["holdout_not_single_symbol_dependent"] = (
        holdout_concentration.top_symbol_gross_profit_share_percent is None
        or holdout_concentration.top_symbol_gross_profit_share_percent
        <= MAXIMUM_SINGLE_CONTRIBUTOR_SHARE_PERCENT
    )
    criteria["validation_not_single_day_dependent"] = (
        validation_concentration.top_day_gross_profit_share_percent is None
        or validation_concentration.top_day_gross_profit_share_percent
        <= MAXIMUM_SINGLE_CONTRIBUTOR_SHARE_PERCENT
    )
    criteria["holdout_not_single_day_dependent"] = (
        holdout_concentration.top_day_gross_profit_share_percent is None
        or holdout_concentration.top_day_gross_profit_share_percent
        <= MAXIMUM_SINGLE_CONTRIBUTOR_SHARE_PERCENT
    )

    if v_avg is not None and v_avg > 0:
        h_avg_for_degradation = h_avg if h_avg is not None else Decimal("0")
        degradation_percent = (v_avg - h_avg_for_degradation) / v_avg * 100
        criteria["no_severe_degradation"] = (
            degradation_percent <= MAXIMUM_VALIDATION_TO_HOLDOUT_DEGRADATION_PERCENT
        )
    else:
        criteria["no_severe_degradation"] = False

    # Always true: the orchestration script always computes max_drawdown and always reports
    # COST_MODEL_2 -- these criteria exist so the Owner report's own checklist is complete
    # and auditable, not because either could plausibly be False given this module's own
    # MetricsSummary always carries max_drawdown.
    criteria["drawdown_reported"] = True
    criteria["cost2_reported"] = True

    all_candidate_criteria = (
        "validation_net_positive",
        "validation_pf_above_1",
        "validation_avg_trade_positive",
        "validation_enough_trades",
        "holdout_net_positive",
        "holdout_pf_above_1",
        "holdout_avg_trade_positive",
        "holdout_enough_trades",
        "validation_not_single_symbol_dependent",
        "holdout_not_single_symbol_dependent",
        "validation_not_single_day_dependent",
        "holdout_not_single_day_dependent",
        "no_severe_degradation",
    )
    if all(criteria[key] for key in all_candidate_criteria):
        return ClassificationResultV2(
            classification="CANDIDATE_EDGE_V2",
            criteria=criteria,
            rationale=(
                "All CANDIDATE_EDGE_V2 criteria satisfied in both VALIDATION and FINAL HOLDOUT."
            ),
        )

    failing = ", ".join(key for key in all_candidate_criteria if not criteria[key])
    return ClassificationResultV2(
        classification="NO_EDGE_V2",
        criteria=criteria,
        rationale=(
            f"VALIDATION cleared its own bar but the full CANDIDATE_EDGE_V2 bar was not met "
            f"(holdout_net={h_net}, holdout_pf={h_pf}, holdout_avg_trade={h_avg}). "
            f"Failing criteria: {failing}."
        ),
    )
