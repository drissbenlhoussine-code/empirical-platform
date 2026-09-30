"""MILESTONE-091 -- cost models, metrics aggregation, concentration, and classification.

Every `ReplayDecision`/`ReplaySessionResult` here is hand-built with literal Decimal prices,
exactly like the M090 replay suite's own arithmetic tests, so every expected metric can be
verified by inspection.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from empirical_platform.decision_candidate.opportunity_engine import RejectionReason
from empirical_platform.usecases.opportunity_engine_replay import (
    ReplayDecision,
    ReplayOutcome,
    ReplaySessionResult,
)
from empirical_platform.usecases.opportunity_engine_validation import (
    COST_MODEL_0,
    COST_MODEL_1,
    COST_MODEL_2,
    ConcentrationReport,
    MetricsSummary,
    aggregate,
    classify,
    concentration_report,
    cost_adjusted_pnl_per_share,
    extract_trade_records,
)

_SYMBOL = "AAPL"


def _decision(
    *,
    bar_index: int = 5,
    decided_at: datetime = datetime(2026, 6, 10, 14, 30, tzinfo=UTC),
    rejection_reasons: tuple[object, ...] = (),
    entry_price: Decimal | None = Decimal("100.00"),
    stop_price: Decimal | None = Decimal("98.00"),
    target_price: Decimal | None = Decimal("104.00"),
    risk_per_share: Decimal | None = Decimal("2.00"),
    quantity: int | None = 10,
    reward_risk_ratio: Decimal | None = Decimal("2.00"),
    outcome: ReplayOutcome | None = None,
    outcome_at: datetime | None = None,
    outcome_price: Decimal | None = None,
    symbol: str = _SYMBOL,
) -> ReplayDecision:
    return ReplayDecision(
        bar_index=bar_index,
        decided_at=decided_at,
        symbol=symbol,
        rejection_reasons=rejection_reasons,  # type: ignore[arg-type]
        entry_price=entry_price,
        stop_price=stop_price,
        target_price=target_price,
        risk_per_share=risk_per_share,
        reward_per_share=Decimal("4.00") if entry_price is not None else None,
        reward_risk_ratio=reward_risk_ratio,
        quantity=quantity,
        quality_score=Decimal("70") if entry_price is not None else None,
        outcome=outcome,
        outcome_at=outcome_at,
        outcome_price=outcome_price,
        realized_pnl_per_share=None,
    )


def _target_hit(
    *,
    entry: Decimal = Decimal("100.00"),
    target: Decimal = Decimal("104.00"),
    quantity: int | None = 10,
    symbol: str = _SYMBOL,
    decided_at: datetime = datetime(2026, 6, 10, 14, 30, tzinfo=UTC),
) -> ReplayDecision:
    return _decision(
        entry_price=entry,
        target_price=target,
        outcome=ReplayOutcome.TARGET_HIT,
        outcome_at=decided_at + timedelta(minutes=10),
        outcome_price=target,
        decided_at=decided_at,
        quantity=quantity,
        symbol=symbol,
    )


def _stop_hit(
    *,
    entry: Decimal = Decimal("100.00"),
    stop: Decimal = Decimal("98.00"),
    quantity: int | None = 10,
    symbol: str = _SYMBOL,
    decided_at: datetime = datetime(2026, 6, 10, 14, 30, tzinfo=UTC),
) -> ReplayDecision:
    return _decision(
        entry_price=entry,
        stop_price=stop,
        outcome=ReplayOutcome.STOP_HIT,
        outcome_at=decided_at + timedelta(minutes=5),
        outcome_price=stop,
        decided_at=decided_at,
        quantity=quantity,
        symbol=symbol,
    )


# ---------------------------------------------------------------------------
# Cost models
# ---------------------------------------------------------------------------


def test_cost_model_0_is_zero_friction_and_matches_raw_pnl() -> None:
    decision = _target_hit(entry=Decimal("100.00"), target=Decimal("104.00"))
    pnl = cost_adjusted_pnl_per_share(decision, COST_MODEL_0)
    assert pnl == Decimal("4.00")


def test_cost_model_1_worsens_both_entry_and_exit() -> None:
    decision = _target_hit(entry=Decimal("100.00"), target=Decimal("104.00"))
    pnl = cost_adjusted_pnl_per_share(decision, COST_MODEL_1)
    # entry: 100 * 1.0005 = 100.05 ; exit: 104 * 0.9995 = 103.948
    expected = Decimal("104") * (Decimal("1") - Decimal("0.05") / 100) - Decimal("100") * (
        Decimal("1") + Decimal("0.05") / 100
    )
    assert pnl == expected
    assert pnl < Decimal("4.00")  # strictly worse than the idealized case


def test_cost_model_2_is_worse_than_cost_model_1() -> None:
    decision = _target_hit(entry=Decimal("100.00"), target=Decimal("104.00"))
    pnl1 = cost_adjusted_pnl_per_share(decision, COST_MODEL_1)
    pnl2 = cost_adjusted_pnl_per_share(decision, COST_MODEL_2)
    assert pnl1 is not None and pnl2 is not None
    assert pnl2 < pnl1


def test_unresolved_decisions_have_no_cost_adjusted_pnl() -> None:
    decision = _decision(outcome=None, outcome_price=None)
    assert cost_adjusted_pnl_per_share(decision, COST_MODEL_1) is None


def test_rejected_decisions_have_no_cost_adjusted_pnl() -> None:
    decision = _decision(
        rejection_reasons=(RejectionReason.NO_BREAKOUT_STRUCTURE,),
        entry_price=None,
        stop_price=None,
        target_price=None,
        risk_per_share=None,
        quantity=None,
        reward_risk_ratio=None,
    )
    assert cost_adjusted_pnl_per_share(decision, COST_MODEL_1) is None


# ---------------------------------------------------------------------------
# extract_trade_records
# ---------------------------------------------------------------------------


def test_extract_trade_records_skips_unresolved_and_rejected() -> None:
    winner = _target_hit()
    unresolved = _decision(outcome=ReplayOutcome.UNRESOLVED_END_OF_DATA)
    result = ReplaySessionResult(
        symbol=_SYMBOL, session_date=date(2026, 6, 10), bar_count=20, decisions=(winner, unresolved)
    )
    records = extract_trade_records([result])
    assert len(records) == 1
    assert records[0].outcome == "TARGET_HIT"


def test_extract_trade_records_computes_all_three_cost_models() -> None:
    winner = _target_hit(entry=Decimal("100.00"), target=Decimal("104.00"), quantity=10)
    result = ReplaySessionResult(
        symbol=_SYMBOL, session_date=date(2026, 6, 10), bar_count=20, decisions=(winner,)
    )
    (record,) = extract_trade_records([result])
    assert record.pnl_per_share_0 == Decimal("4.00")
    assert record.pnl_total_0 == Decimal("40.00")
    assert record.pnl_per_share_1 < record.pnl_per_share_0
    assert record.pnl_per_share_2 < record.pnl_per_share_1
    assert record.pnl_total_1 == record.pnl_per_share_1 * 10


def test_extract_trade_records_is_chronologically_ordered() -> None:
    later = _target_hit(decided_at=datetime(2026, 6, 11, 14, 30, tzinfo=UTC))
    earlier = _target_hit(decided_at=datetime(2026, 6, 10, 14, 30, tzinfo=UTC))
    result_a = ReplaySessionResult(
        symbol=_SYMBOL, session_date=date(2026, 6, 11), bar_count=20, decisions=(later,)
    )
    result_b = ReplaySessionResult(
        symbol=_SYMBOL, session_date=date(2026, 6, 10), bar_count=20, decisions=(earlier,)
    )
    records = extract_trade_records([result_a, result_b])
    assert records[0].session_date == date(2026, 6, 10)
    assert records[1].session_date == date(2026, 6, 11)


# ---------------------------------------------------------------------------
# aggregate
# ---------------------------------------------------------------------------


def test_aggregate_counts_observations_opportunities_and_rejections() -> None:
    winner = _target_hit()
    rejected = _decision(
        rejection_reasons=(RejectionReason.INSUFFICIENT_LIQUIDITY,),
        entry_price=None,
        stop_price=None,
        target_price=None,
        risk_per_share=None,
        quantity=None,
        reward_risk_ratio=None,
    )
    result = ReplaySessionResult(
        symbol=_SYMBOL, session_date=date(2026, 6, 10), bar_count=20, decisions=(winner, rejected)
    )
    summary = aggregate([result], cost_model=COST_MODEL_1)
    assert summary.observations == 2
    assert summary.opportunities == 1
    assert summary.rejected_count == 1
    assert summary.rejection_reasons == {"INSUFFICIENT_LIQUIDITY": 1}
    assert summary.target_hits == 1
    assert summary.trades_resolved == 1


def test_aggregate_profit_factor_hit_rate_and_payoff_ratio() -> None:
    winner = _target_hit(entry=Decimal("100.00"), target=Decimal("104.00"), quantity=10)
    loser = _stop_hit(entry=Decimal("100.00"), stop=Decimal("98.00"), quantity=10)
    result = ReplaySessionResult(
        symbol=_SYMBOL, session_date=date(2026, 6, 10), bar_count=20, decisions=(winner, loser)
    )
    summary = aggregate([result], cost_model=COST_MODEL_0)
    assert summary.trades_resolved == 2
    assert summary.hit_rate == Decimal("0.5")
    # gross win 40, gross loss 20 -> profit factor 2
    assert summary.profit_factor == Decimal("2")
    # avg winner 4/share, avg loser -2/share -> payoff ratio 2
    assert summary.payoff_ratio == Decimal("2")
    assert summary.net_pnl == Decimal("20.00")  # 40 - 20


def test_aggregate_drawdown_and_losing_streak() -> None:
    d1 = datetime(2026, 6, 10, 14, 30, tzinfo=UTC)
    d2 = datetime(2026, 6, 11, 14, 30, tzinfo=UTC)
    d3 = datetime(2026, 6, 12, 14, 30, tzinfo=UTC)
    win = _target_hit(entry=Decimal("100"), target=Decimal("104"), quantity=1, decided_at=d1)
    loss1 = _stop_hit(entry=Decimal("100"), stop=Decimal("98"), quantity=1, decided_at=d2)
    loss2 = _stop_hit(entry=Decimal("100"), stop=Decimal("98"), quantity=1, decided_at=d3)
    results = [
        ReplaySessionResult(
            symbol=_SYMBOL, session_date=date(2026, 6, 10), bar_count=1, decisions=(win,)
        ),
        ReplaySessionResult(
            symbol=_SYMBOL, session_date=date(2026, 6, 11), bar_count=1, decisions=(loss1,)
        ),
        ReplaySessionResult(
            symbol=_SYMBOL, session_date=date(2026, 6, 12), bar_count=1, decisions=(loss2,)
        ),
    ]
    summary = aggregate(results, cost_model=COST_MODEL_0)
    # equity: 0 -> 4 -> 2 -> 0 ; peak 4 ; trough 0 after two losses -> drawdown 4
    assert summary.max_drawdown == Decimal("4")
    assert summary.longest_losing_streak == 2


def test_aggregate_with_no_trades_has_none_metrics_not_a_crash() -> None:
    result = ReplaySessionResult(
        symbol=_SYMBOL, session_date=date(2026, 6, 10), bar_count=1, decisions=()
    )
    summary = aggregate([result], cost_model=COST_MODEL_1)
    assert summary.trades_resolved == 0
    assert summary.average_trade is None
    assert summary.profit_factor is None
    assert summary.hit_rate is None
    assert summary.max_drawdown == Decimal("0")


# ---------------------------------------------------------------------------
# concentration_report
# ---------------------------------------------------------------------------


def test_concentration_report_identifies_the_best_symbol_and_day() -> None:
    big_winner = _target_hit(
        entry=Decimal("100"),
        target=Decimal("110"),
        quantity=100,
        symbol="AAPL",
        decided_at=datetime(2026, 6, 10, 14, 30, tzinfo=UTC),
    )
    small_winner = _target_hit(
        entry=Decimal("100"),
        target=Decimal("101"),
        quantity=1,
        symbol="MSFT",
        decided_at=datetime(2026, 6, 11, 14, 30, tzinfo=UTC),
    )
    results = [
        ReplaySessionResult(
            symbol="AAPL", session_date=date(2026, 6, 10), bar_count=1, decisions=(big_winner,)
        ),
        ReplaySessionResult(
            symbol="MSFT", session_date=date(2026, 6, 11), bar_count=1, decisions=(small_winner,)
        ),
    ]
    records = extract_trade_records(results)
    report = concentration_report(
        records,
        cost_model=COST_MODEL_0,
        block_a_dates=frozenset({date(2026, 6, 10)}),
        block_b_dates=frozenset({date(2026, 6, 11)}),
    )
    assert report.best_symbol == "AAPL"
    assert report.best_day == date(2026, 6, 10)
    assert report.total_net_pnl == Decimal("1001")  # 100*10 + 1*1
    assert report.best_symbol_share_percent is not None
    assert report.best_symbol_share_percent > Decimal("99")
    assert report.block_a_net_pnl == Decimal("1000")
    assert report.block_b_net_pnl == Decimal("1")


# ---------------------------------------------------------------------------
# classify
# ---------------------------------------------------------------------------


def _summary(**overrides: object) -> MetricsSummary:
    defaults: dict[str, object] = {
        "cost_model_name": COST_MODEL_1.name,
        "observations": 1000,
        "opportunities": 100,
        "rejected_count": 900,
        "rejection_reasons": {},
        "trades_resolved": 60,
        "target_hits": 40,
        "stop_hits": 15,
        "mandatory_exits": 5,
        "unresolved": 0,
        "gross_pnl": Decimal("100"),
        "net_pnl": Decimal("80"),
        "average_trade": Decimal("1.5"),
        "median_trade": Decimal("1.0"),
        "average_winner": Decimal("5"),
        "average_loser": Decimal("-2"),
        "payoff_ratio": Decimal("2.5"),
        "hit_rate": Decimal("0.6"),
        "profit_factor": Decimal("2"),
        "max_drawdown": Decimal("10"),
        "longest_losing_streak": 2,
        "average_holding_seconds": 300.0,
        "maximum_loss_min": Decimal("10"),
        "maximum_loss_median": Decimal("50"),
        "maximum_loss_max": Decimal("100"),
        "reward_risk_min": Decimal("2"),
        "reward_risk_median": Decimal("2"),
        "reward_risk_max": Decimal("3"),
    }
    defaults.update(overrides)
    return MetricsSummary(**defaults)  # type: ignore[arg-type]


def _concentration(**overrides: object) -> ConcentrationReport:
    defaults: dict[str, object] = {
        "total_net_pnl": Decimal("80"),
        "best_symbol": "AAPL",
        "best_symbol_pnl": Decimal("30"),
        "best_symbol_share_percent": Decimal("37.5"),
        "best_day": date(2026, 6, 10),
        "best_day_pnl": Decimal("20"),
        "best_day_share_percent": Decimal("25"),
        "best_hour_utc": 14,
        "best_hour_pnl": Decimal("20"),
        "best_hour_share_percent": Decimal("25"),
        "largest_winning_trade_pnl": Decimal("10"),
        "net_pnl_excluding_largest_winner": Decimal("70"),
        "block_a_net_pnl": Decimal("40"),
        "block_b_net_pnl": Decimal("40"),
    }
    defaults.update(overrides)
    return ConcentrationReport(**defaults)  # type: ignore[arg-type]


def test_classify_candidate_edge_when_every_criterion_passes() -> None:
    result = classify(
        full_metrics_cost1=_summary(
            trades_resolved=60, net_pnl=Decimal("80"), profit_factor=Decimal("2")
        ),
        block_a_metrics_cost1=_summary(
            net_pnl=Decimal("40"), profit_factor=Decimal("1.8"), average_trade=Decimal("1.3")
        ),
        block_b_metrics_cost1=_summary(
            net_pnl=Decimal("40"), profit_factor=Decimal("2.2"), average_trade=Decimal("1.7")
        ),
        concentration=_concentration(
            best_symbol_share_percent=Decimal("37.5"), best_day_share_percent=Decimal("25")
        ),
        excluded_fraction=Decimal("0.05"),
    )
    assert result.classification == "CANDIDATE_EDGE"
    assert all(
        result.criteria[k]
        for k in (
            "block_a_positive",
            "block_b_positive",
            "block_a_pf_above_1",
            "block_b_pf_above_1",
            "not_single_symbol_dependent",
            "not_single_day_dependent",
        )
    )


def test_classify_inconclusive_when_too_few_trades() -> None:
    result = classify(
        full_metrics_cost1=_summary(trades_resolved=5),
        block_a_metrics_cost1=_summary(),
        block_b_metrics_cost1=_summary(),
        concentration=_concentration(),
        excluded_fraction=Decimal("0.05"),
    )
    assert result.classification == "INCONCLUSIVE"
    assert result.criteria["enough_trades"] is False


def test_classify_inconclusive_when_data_too_gappy() -> None:
    result = classify(
        full_metrics_cost1=_summary(trades_resolved=60),
        block_a_metrics_cost1=_summary(),
        block_b_metrics_cost1=_summary(),
        concentration=_concentration(),
        excluded_fraction=Decimal("0.5"),
    )
    assert result.classification == "INCONCLUSIVE"
    assert result.criteria["data_not_too_gappy"] is False


def test_classify_no_edge_found_when_full_sample_net_pnl_negative() -> None:
    result = classify(
        full_metrics_cost1=_summary(
            trades_resolved=60, net_pnl=Decimal("-50"), profit_factor=Decimal("0.7")
        ),
        block_a_metrics_cost1=_summary(net_pnl=Decimal("-20")),
        block_b_metrics_cost1=_summary(net_pnl=Decimal("-30")),
        concentration=_concentration(),
        excluded_fraction=Decimal("0.05"),
    )
    assert result.classification == "NO_EDGE_FOUND"
    assert result.criteria["full_sample_negative_expectancy"] is True


def test_classify_no_edge_found_when_one_block_is_negative_even_if_overall_positive() -> None:
    result = classify(
        full_metrics_cost1=_summary(
            trades_resolved=60, net_pnl=Decimal("10"), profit_factor=Decimal("1.1")
        ),
        block_a_metrics_cost1=_summary(net_pnl=Decimal("-40"), profit_factor=Decimal("0.5")),
        block_b_metrics_cost1=_summary(net_pnl=Decimal("50"), profit_factor=Decimal("3")),
        concentration=_concentration(),
        excluded_fraction=Decimal("0.05"),
    )
    # Not CANDIDATE_EDGE (block A not positive) and full-sample profit factor 1.1 > 1, net
    # positive -- but either_block_clearly_negative triggers NO_EDGE_FOUND.
    assert result.classification == "NO_EDGE_FOUND"
    assert result.criteria["either_block_clearly_negative"] is True


def test_classify_no_edge_found_when_single_symbol_dependent_and_full_sample_weak() -> None:
    """A CANDIDATE_EDGE-blocking concentration alone, WITHOUT a clear NO_EDGE signal, lands
    INCONCLUSIVE -- proven separately below. This test keeps a concentration failure paired
    with a genuinely weak full-sample profit factor, which legitimately IS NO_EDGE_FOUND."""
    result = classify(
        full_metrics_cost1=_summary(
            trades_resolved=60, net_pnl=Decimal("5"), profit_factor=Decimal("1.0")
        ),
        block_a_metrics_cost1=_summary(net_pnl=Decimal("2"), profit_factor=Decimal("1.1")),
        block_b_metrics_cost1=_summary(net_pnl=Decimal("3"), profit_factor=Decimal("1.2")),
        concentration=_concentration(best_symbol_share_percent=Decimal("90")),
        excluded_fraction=Decimal("0.05"),
    )
    assert result.criteria["not_single_symbol_dependent"] is False
    assert (
        result.classification == "NO_EDGE_FOUND"
    )  # pf<=1 triggers this independent of concentration


def test_classify_inconclusive_when_borderline_and_not_clearly_either() -> None:
    result = classify(
        full_metrics_cost1=_summary(
            trades_resolved=60,
            net_pnl=Decimal("50"),
            profit_factor=Decimal("1.5"),
            hit_rate=Decimal("0.55"),
            payoff_ratio=Decimal("1.5"),
        ),
        block_a_metrics_cost1=_summary(
            net_pnl=Decimal("30"), profit_factor=Decimal("1.6"), average_trade=Decimal("1")
        ),
        block_b_metrics_cost1=_summary(
            net_pnl=Decimal("20"), profit_factor=Decimal("1.3"), average_trade=Decimal("0.7")
        ),
        concentration=_concentration(
            best_symbol_share_percent=Decimal("90")
        ),  # blocks CANDIDATE_EDGE
        excluded_fraction=Decimal("0.05"),
    )
    assert result.classification == "INCONCLUSIVE"
    assert result.criteria["not_single_symbol_dependent"] is False
    assert result.criteria["full_sample_negative_expectancy"] is False
    assert result.criteria["full_sample_pf_at_or_below_1"] is False
    assert result.criteria["either_block_clearly_negative"] is False
