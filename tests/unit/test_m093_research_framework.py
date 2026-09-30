"""MILESTONE-093 Phase 3 -- the common research framework: resolve_outcome's stop-first
rule, position sizing, cost models, and metrics aggregation, all with hand-built bars so the
expected result can be verified by inspection."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from empirical_platform.decision_candidate.market_data import Bar, BarInterval, Instrument
from empirical_platform.usecases.m093_research_framework import (
    COST_MODEL_0,
    COST_MODEL_1,
    ReplayDecision,
    ReplayOutcome,
    ReplaySessionResult,
    aggregate,
    cost_adjusted_pnl_per_share,
    position_size,
    resolve_outcome,
)

_SYMBOL = "AAPL"


def _bar(*, minute: int, o: str, h: str, low: str, c: str, v: int = 1000) -> Bar:
    return Bar(
        instrument=Instrument(_SYMBOL),
        interval=BarInterval.ONE_MINUTE,
        timestamp=datetime(2026, 8, 3, 14, minute, tzinfo=UTC),
        open=Decimal(o),
        high=Decimal(h),
        low=Decimal(low),
        close=Decimal(c),
        volume=v,
    )


def _decision(**overrides: object) -> ReplayDecision:
    defaults: dict[str, object] = dict(
        family="TEST_FAMILY",
        bar_index=0,
        decided_at=datetime(2026, 8, 3, 14, 0, tzinfo=UTC),
        symbol=_SYMBOL,
        rejection_reasons=(),
        entry_price=Decimal("100.00"),
        stop_price=Decimal("98.00"),
        target_price=Decimal("104.00"),
        risk_per_share=Decimal("2.00"),
        reward_per_share=Decimal("4.00"),
        reward_risk_ratio=Decimal("2.00"),
        quantity=10,
        outcome=None,
        outcome_at=None,
        outcome_price=None,
        realized_pnl_per_share=None,
    )
    defaults.update(overrides)
    return ReplayDecision(**defaults)  # type: ignore[arg-type]


def test_resolve_outcome_picks_target_when_only_target_is_touched() -> None:
    bars = [
        _bar(minute=0, o="100", h="100.50", low="99.50", c="100"),
        _bar(minute=1, o="100", h="104.50", low="99.80", c="104.20"),
    ]
    decision = resolve_outcome(
        bars, 0, _decision(), mandatory_liquidation_at=datetime(2026, 8, 3, 20, 0, tzinfo=UTC)
    )
    assert decision.outcome is ReplayOutcome.TARGET_HIT
    assert decision.outcome_price == Decimal("104.00")


def test_resolve_outcome_picks_stop_when_only_stop_is_touched() -> None:
    bars = [
        _bar(minute=0, o="100", h="100.50", low="99.50", c="100"),
        _bar(minute=1, o="100", h="100.20", low="97.50", c="98.50"),
    ]
    decision = resolve_outcome(
        bars, 0, _decision(), mandatory_liquidation_at=datetime(2026, 8, 3, 20, 0, tzinfo=UTC)
    )
    assert decision.outcome is ReplayOutcome.STOP_HIT
    assert decision.outcome_price == Decimal("98.00")


def test_resolve_outcome_same_bar_ambiguity_resolves_stop_first() -> None:
    """Phase 16: when both stop and target are touched in the SAME later bar and intrabar
    ordering is unknowable, the conservative (stop) outcome is chosen, never the favorable
    one."""
    bars = [
        _bar(minute=0, o="100", h="100.50", low="99.50", c="100"),
        _bar(minute=1, o="100", h="105.00", low="96.00", c="100"),
    ]
    decision = resolve_outcome(
        bars, 0, _decision(), mandatory_liquidation_at=datetime(2026, 8, 3, 20, 0, tzinfo=UTC)
    )
    assert decision.outcome is ReplayOutcome.STOP_HIT


def test_resolve_outcome_mandatory_exit_wins_over_a_same_moment_touch() -> None:
    bars = [
        _bar(minute=0, o="100", h="100.50", low="99.50", c="100"),
        _bar(minute=1, o="100", h="105.00", low="96.00", c="100"),
    ]
    decision = resolve_outcome(bars, 0, _decision(), mandatory_liquidation_at=bars[1].timestamp)
    assert decision.outcome is ReplayOutcome.MANDATORY_EXIT


def test_resolve_outcome_unresolved_when_neither_touched_before_data_ends() -> None:
    bars = [
        _bar(minute=0, o="100", h="100.50", low="99.50", c="100"),
        _bar(minute=1, o="100", h="101.00", low="99.00", c="100.50"),
    ]
    decision = resolve_outcome(
        bars, 0, _decision(), mandatory_liquidation_at=datetime(2026, 8, 3, 20, 0, tzinfo=UTC)
    )
    assert decision.outcome is ReplayOutcome.UNRESOLVED_END_OF_DATA
    assert decision.outcome_price is None


def test_position_size_is_the_minimum_of_all_three_caps() -> None:
    quantity = position_size(
        entry_price=Decimal("100"),
        stop_price=Decimal("98"),
        maximum_loss=Decimal("50"),  # -> floor(50/2) = 25 shares
        maximum_capital_per_trade=Decimal("1000"),  # -> floor(1000/100) = 10 shares
        maximum_percent_per_trade=Decimal("50"),
        deployable_capital=Decimal("10000"),  # -> floor(5000/100) = 50 shares
    )
    assert quantity == 10  # the tightest of the three caps


def test_cost_model_0_is_the_raw_unadjusted_fill() -> None:
    decision = _decision(
        entry_price=Decimal("100.00"),
        outcome=ReplayOutcome.TARGET_HIT,
        outcome_price=Decimal("104.00"),
    )
    pnl = cost_adjusted_pnl_per_share(decision, COST_MODEL_0)
    assert pnl == Decimal("4.00")


def test_cost_model_1_charges_a_conservative_round_trip_cost() -> None:
    decision = _decision(
        entry_price=Decimal("100.00"),
        outcome=ReplayOutcome.TARGET_HIT,
        outcome_price=Decimal("104.00"),
    )
    pnl = cost_adjusted_pnl_per_share(decision, COST_MODEL_1)
    # entry paid: 100 * 1.0005 = 100.05; exit received: 104 * 0.9995 = 103.948
    assert pnl is not None
    assert pnl < Decimal("4.00")
    assert pnl > Decimal("3.80")


def test_aggregate_counts_observations_opportunities_and_rejections_correctly() -> None:
    accepted = _decision(
        outcome=ReplayOutcome.TARGET_HIT,
        outcome_price=Decimal("104.00"),
        outcome_at=datetime(2026, 8, 3, 14, 5, tzinfo=UTC),
    )
    rejected = _decision(
        bar_index=1,
        rejection_reasons=("NO_SETUP",),
        entry_price=None,
        stop_price=None,
        target_price=None,
        risk_per_share=None,
        reward_per_share=None,
        reward_risk_ratio=None,
        quantity=None,
    )
    result = ReplaySessionResult(
        family="TEST_FAMILY",
        symbol=_SYMBOL,
        session_date=accepted.decided_at.date(),
        bar_count=2,
        decisions=(accepted, rejected),
    )
    summary = aggregate([result], cost_model=COST_MODEL_0)
    assert summary.observations == 2
    assert summary.opportunities == 1
    assert summary.rejected_count == 1
    assert summary.rejection_reasons == {"NO_SETUP": 1}
    assert summary.trades_resolved == 1
    assert summary.target_hits == 1
    assert summary.net_pnl == Decimal("40.00")  # (104-100) * 10
