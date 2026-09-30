"""MILESTONE-092 Phase 18-19 -- `concentration_report_v2` and `classify_v2` correctness,
against hand-built `TradeRecord`s so the expected numbers are checkable by inspection.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from empirical_platform.usecases.opportunity_engine_v2_validation import (
    MAXIMUM_SINGLE_CONTRIBUTOR_SHARE_PERCENT,
    MINIMUM_RESOLVED_TRADES,
    classify_v2,
    concentration_report_v2,
)
from empirical_platform.usecases.opportunity_engine_validation import (
    COST_MODEL_1,
    MetricsSummary,
    TradeRecord,
)


def _record(
    *, symbol: str, session_date: date, pnl_total_1: Decimal, hour: int = 14
) -> TradeRecord:
    return TradeRecord(
        symbol=symbol,
        session_date=session_date,
        decided_hour_utc=hour,
        outcome="TARGET_HIT" if pnl_total_1 > 0 else "STOP_HIT",
        quantity=1,
        maximum_loss=Decimal("10"),
        reward_risk_ratio=Decimal("1.3"),
        holding_seconds=60.0,
        pnl_per_share_0=pnl_total_1,
        pnl_per_share_1=pnl_total_1,
        pnl_per_share_2=pnl_total_1,
        pnl_total_0=pnl_total_1,
        pnl_total_1=pnl_total_1,
        pnl_total_2=pnl_total_1,
    )


def _metrics(
    *,
    net_pnl: Decimal,
    profit_factor: Decimal | None,
    average_trade: Decimal | None,
    trades_resolved: int = 100,
) -> MetricsSummary:
    return MetricsSummary(
        cost_model_name=COST_MODEL_1.name,
        observations=trades_resolved,
        opportunities=trades_resolved,
        rejected_count=0,
        rejection_reasons={},
        trades_resolved=trades_resolved,
        target_hits=trades_resolved // 2,
        stop_hits=trades_resolved // 2,
        mandatory_exits=0,
        unresolved=0,
        gross_pnl=net_pnl,
        net_pnl=net_pnl,
        average_trade=average_trade,
        median_trade=average_trade,
        average_winner=Decimal("5"),
        average_loser=Decimal("-4"),
        payoff_ratio=Decimal("1.25"),
        hit_rate=Decimal("0.5"),
        profit_factor=profit_factor,
        max_drawdown=Decimal("100"),
        longest_losing_streak=3,
        average_holding_seconds=60.0,
        maximum_loss_min=Decimal("10"),
        maximum_loss_median=Decimal("10"),
        maximum_loss_max=Decimal("10"),
        reward_risk_min=Decimal("1.3"),
        reward_risk_median=Decimal("1.3"),
        reward_risk_max=Decimal("1.3"),
    )


# ---------------------------------------------------------------------------
# concentration_report_v2
# ---------------------------------------------------------------------------


def test_gross_profit_share_stays_meaningful_when_total_net_pnl_is_negative() -> None:
    """The exact scenario M091's own concentration formula broke on: total net P&L negative.
    Share-of-GROSS-PROFIT must still be a sensible 0-100% number, not a sign-inverted one."""
    records = (
        _record(symbol="AAA", session_date=date(2026, 1, 1), pnl_total_1=Decimal("10")),
        _record(symbol="AAA", session_date=date(2026, 1, 2), pnl_total_1=Decimal("-50")),
        _record(symbol="BBB", session_date=date(2026, 1, 3), pnl_total_1=Decimal("-50")),
    )
    report = concentration_report_v2(records, cost_model=COST_MODEL_1)
    assert report.total_net_pnl == Decimal("-90")
    assert report.total_gross_profit == Decimal("10")
    assert report.top_symbol_by_gross_profit == "AAA"
    assert report.top_symbol_gross_profit_share_percent == Decimal("100")
    assert 0 <= report.top_symbol_gross_profit_share_percent <= 100


def test_trade_count_concentration_needs_no_pnl_sign() -> None:
    records = (
        _record(symbol="AAA", session_date=date(2026, 1, 1), pnl_total_1=Decimal("1")),
        _record(symbol="AAA", session_date=date(2026, 1, 2), pnl_total_1=Decimal("-1")),
        _record(symbol="BBB", session_date=date(2026, 1, 3), pnl_total_1=Decimal("-1")),
    )
    report = concentration_report_v2(records, cost_model=COST_MODEL_1)
    assert report.top_symbol_by_trade_count == "AAA"
    assert report.top_symbol_trade_count == 2
    assert report.top_symbol_trade_count_share_percent == Decimal("200") / 3


def test_leave_one_out_sensitivity_excludes_exactly_the_top_symbol() -> None:
    records = (
        _record(symbol="AAA", session_date=date(2026, 1, 1), pnl_total_1=Decimal("10")),
        _record(symbol="AAA", session_date=date(2026, 1, 2), pnl_total_1=Decimal("10")),
        _record(symbol="BBB", session_date=date(2026, 1, 3), pnl_total_1=Decimal("-5")),
    )
    report = concentration_report_v2(records, cost_model=COST_MODEL_1)
    assert report.top_symbol_by_trade_count == "AAA"
    assert report.net_pnl_excluding_top_trade_count_symbol == Decimal("-5")


def test_empty_records_do_not_crash() -> None:
    report = concentration_report_v2((), cost_model=COST_MODEL_1)
    assert report.total_net_pnl == Decimal("0")
    assert report.top_symbol_by_trade_count is None
    assert report.top_symbol_trade_count_share_percent is None


# ---------------------------------------------------------------------------
# classify_v2
# ---------------------------------------------------------------------------


def test_validation_failure_is_no_edge_v2_and_never_inconclusive() -> None:
    validation = _metrics(
        net_pnl=Decimal("-100"), profit_factor=Decimal("0.5"), average_trade=Decimal("-1")
    )
    concentration = concentration_report_v2((), cost_model=COST_MODEL_1)
    result = classify_v2(
        validation_metrics=validation,
        validation_concentration=concentration,
        holdout_metrics=None,
        holdout_concentration=None,
    )
    assert result.classification == "NO_EDGE_V2"
    assert result.criteria["validation_net_positive"] is False


def test_validation_pass_with_no_holdout_supplied_is_inconclusive_not_candidate() -> None:
    validation = _metrics(
        net_pnl=Decimal("100"), profit_factor=Decimal("1.5"), average_trade=Decimal("1")
    )
    concentration = concentration_report_v2((), cost_model=COST_MODEL_1)
    result = classify_v2(
        validation_metrics=validation,
        validation_concentration=concentration,
        holdout_metrics=None,
        holdout_concentration=None,
    )
    assert result.classification == "INCONCLUSIVE_V2"


def _diversified_records() -> tuple[TradeRecord, ...]:
    """40 small winners spread evenly across 4 symbols and 40 distinct days -- low
    concentration by construction, for the CANDIDATE_EDGE_V2-shaped tests below."""
    symbols = ["AAA", "BBB", "CCC", "DDD"] * 10
    start = date(2026, 1, 1)
    return tuple(
        _record(symbol=sym, session_date=start + timedelta(days=i), pnl_total_1=Decimal("5"))
        for i, sym in enumerate(symbols)
    )


def test_both_periods_passing_with_low_concentration_is_candidate_edge() -> None:
    records = _diversified_records()
    concentration = concentration_report_v2(records, cost_model=COST_MODEL_1)
    metrics = _metrics(
        net_pnl=Decimal("200"),
        profit_factor=Decimal("2"),
        average_trade=Decimal("5"),
        trades_resolved=40,
    )
    result = classify_v2(
        validation_metrics=metrics,
        validation_concentration=concentration,
        holdout_metrics=metrics,
        holdout_concentration=concentration,
    )
    assert result.classification == "CANDIDATE_EDGE_V2"
    assert all(result.criteria.values())


def test_severe_degradation_from_validation_to_holdout_blocks_candidate_edge() -> None:
    records = _diversified_records()
    concentration = concentration_report_v2(records, cost_model=COST_MODEL_1)
    validation = _metrics(
        net_pnl=Decimal("200"),
        profit_factor=Decimal("2"),
        average_trade=Decimal("5"),
        trades_resolved=40,
    )
    holdout = _metrics(
        net_pnl=Decimal("1"),
        profit_factor=Decimal("1.01"),
        average_trade=Decimal("0.01"),
        trades_resolved=40,
    )
    result = classify_v2(
        validation_metrics=validation,
        validation_concentration=concentration,
        holdout_metrics=holdout,
        holdout_concentration=concentration,
    )
    assert result.classification == "NO_EDGE_V2"
    assert result.criteria["no_severe_degradation"] is False


def test_single_symbol_dependence_blocks_candidate_edge() -> None:
    records = (
        _record(symbol="AAA", session_date=date(2026, 1, 1), pnl_total_1=Decimal("100")),
        _record(symbol="BBB", session_date=date(2026, 1, 2), pnl_total_1=Decimal("1")),
    )
    concentration = concentration_report_v2(records, cost_model=COST_MODEL_1)
    assert concentration.top_symbol_gross_profit_share_percent is not None
    assert (
        concentration.top_symbol_gross_profit_share_percent
        > MAXIMUM_SINGLE_CONTRIBUTOR_SHARE_PERCENT
    )
    metrics = _metrics(
        net_pnl=Decimal("101"),
        profit_factor=Decimal("5"),
        average_trade=Decimal("50"),
        trades_resolved=35,
    )
    result = classify_v2(
        validation_metrics=metrics,
        validation_concentration=concentration,
        holdout_metrics=metrics,
        holdout_concentration=concentration,
    )
    assert result.classification == "NO_EDGE_V2"
    assert result.criteria["validation_not_single_symbol_dependent"] is False


def test_classify_v2_is_pure_same_inputs_same_output() -> None:
    validation = _metrics(
        net_pnl=Decimal("-1"), profit_factor=Decimal("0.9"), average_trade=Decimal("-0.1")
    )
    concentration = concentration_report_v2((), cost_model=COST_MODEL_1)
    a = classify_v2(
        validation_metrics=validation,
        validation_concentration=concentration,
        holdout_metrics=None,
        holdout_concentration=None,
    )
    b = classify_v2(
        validation_metrics=validation,
        validation_concentration=concentration,
        holdout_metrics=None,
        holdout_concentration=None,
    )
    assert a == b


def test_minimum_resolved_trades_constant_is_used() -> None:
    metrics = _metrics(
        net_pnl=Decimal("10"),
        profit_factor=Decimal("2"),
        average_trade=Decimal("1"),
        trades_resolved=MINIMUM_RESOLVED_TRADES - 1,
    )
    concentration = concentration_report_v2((), cost_model=COST_MODEL_1)
    result = classify_v2(
        validation_metrics=metrics,
        validation_concentration=concentration,
        holdout_metrics=metrics,
        holdout_concentration=concentration,
    )
    assert result.criteria["validation_enough_trades"] is False
    assert result.classification == "NO_EDGE_V2"
