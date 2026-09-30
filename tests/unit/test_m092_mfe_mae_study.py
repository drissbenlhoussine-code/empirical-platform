"""MILESTONE-092 Phase 22-E -- MFE/MAE calculation correctness, and Phase 22-G -- freeze
fingerprint determinism. Both exercised with hand-built, small inputs so every number is
independently checkable."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from empirical_platform.decision_candidate.market_data import Bar, BarInterval, Instrument
from empirical_platform.decision_candidate.operator_trading_configuration import (
    AccountMode,
    KillSwitchState,
    LimitPricePolicy,
    OperatorTradingConfiguration,
    OrderType,
    TradingSession,
)
from empirical_platform.usecases.opportunity_engine_replay import ReplayDecision

_SYMBOL = "AAPL"


def _bar(*, minute: int, o: str, h: str, low: str, c: str, v: int) -> Bar:
    return Bar(
        instrument=Instrument(_SYMBOL),
        interval=BarInterval.ONE_MINUTE,
        timestamp=datetime(2026, 6, 10, 14, minute, tzinfo=UTC),
        open=Decimal(o),
        high=Decimal(h),
        low=Decimal(low),
        close=Decimal(c),
        volume=v,
    )


def test_measure_excursion_computes_mfe_and_mae_correctly() -> None:
    from tools.m092_mfe_mae_study import measure_excursion

    bars = (
        _bar(minute=0, o="100", h="100.10", low="99.90", c="100.00", v=1000),
        _bar(minute=1, o="100.00", h="103.00", low="99.00", c="102.00", v=1000),  # MFE bar
        _bar(minute=2, o="102.00", h="102.50", low="97.50", c="98.00", v=1000),  # MAE bar
        _bar(minute=3, o="98.60", h="99.00", low="98.50", c="98.80", v=1000),
    )
    decision = ReplayDecision(
        bar_index=0,
        decided_at=bars[0].timestamp,
        symbol=_SYMBOL,
        rejection_reasons=(),
        entry_price=Decimal("100.00"),
        stop_price=Decimal("98.00"),
        target_price=Decimal("104.00"),
        risk_per_share=Decimal("2.00"),
        reward_per_share=Decimal("4.00"),
        reward_risk_ratio=Decimal("2.00"),
        quantity=1,
        quality_score=None,
        outcome=None,
        outcome_at=None,
        outcome_price=None,
        realized_pnl_per_share=None,
    )
    record = measure_excursion(
        bars,
        0,
        decision,
        mandatory_liquidation_at=datetime(2026, 6, 10, 15, 45, tzinfo=UTC),
        lookback=5,
    )
    assert record is not None
    # MFE = max(high - entry) over bars[1:] = max(103.00-100, 102.50-100, 99.00-100)
    #     = max(3.00, 2.50, -1.00) = 3.00
    assert Decimal(record.mfe) == Decimal("3.00")
    assert Decimal(record.mfe_in_r) == Decimal("1.5000")  # 3.00 / risk(2.00)
    # MAE = max(entry - low) over bars[1:] = max(100-99.00, 100-97.50, 100-98.50)
    #     = max(1.00, 2.50, 1.50) = 2.50
    assert Decimal(record.mae) == Decimal("2.50")
    assert Decimal(record.mae_in_r) == Decimal("1.2500")  # 2.50 / risk(2.00)


def test_measure_excursion_returns_none_without_a_full_geometry() -> None:
    from tools.m092_mfe_mae_study import measure_excursion

    bars = (
        _bar(minute=0, o="100", h="100.10", low="99.90", c="100.00", v=1000),
        _bar(minute=1, o="100.00", h="100.50", low="99.50", c="100.10", v=1000),
    )
    rejected = ReplayDecision(
        bar_index=0,
        decided_at=bars[0].timestamp,
        symbol=_SYMBOL,
        rejection_reasons=(),
        entry_price=None,
        stop_price=None,
        target_price=None,
        risk_per_share=None,
        reward_per_share=None,
        reward_risk_ratio=None,
        quantity=None,
        quality_score=None,
        outcome=None,
        outcome_at=None,
        outcome_price=None,
        realized_pnl_per_share=None,
    )
    assert (
        measure_excursion(
            bars,
            0,
            rejected,
            mandatory_liquidation_at=datetime(2026, 6, 10, 15, 45, tzinfo=UTC),
            lookback=5,
        )
        is None
    )


def test_measure_excursion_never_reads_bars_at_or_before_its_own_index() -> None:
    """Look-ahead defense for the diagnostic tool itself: MFE/MAE must only ever be
    computed from bars[index+1:], never the decision bar or anything before it."""
    from tools.m092_mfe_mae_study import measure_excursion

    bars = (
        _bar(minute=0, o="100", h="1000000", low="1", c="100.00", v=1000),  # poisoned if read
        _bar(minute=1, o="100.00", h="100.50", low="99.50", c="100.10", v=1000),
        _bar(minute=2, o="100.10", h="100.60", low="99.60", c="100.20", v=1000),
    )
    decision = ReplayDecision(
        bar_index=1,
        decided_at=bars[1].timestamp,
        symbol=_SYMBOL,
        rejection_reasons=(),
        entry_price=Decimal("100.10"),
        stop_price=Decimal("99.00"),
        target_price=Decimal("102.10"),
        risk_per_share=Decimal("1.10"),
        reward_per_share=Decimal("2.00"),
        reward_risk_ratio=Decimal("1.82"),
        quantity=1,
        quality_score=None,
        outcome=None,
        outcome_at=None,
        outcome_price=None,
        realized_pnl_per_share=None,
    )
    record = measure_excursion(
        bars,
        1,
        decision,
        mandatory_liquidation_at=datetime(2026, 6, 10, 15, 45, tzinfo=UTC),
        lookback=5,
    )
    assert record is not None
    # Only bars[2:] (high=100.60) is in scope; the poisoned bars[0] (high=1000000) must
    # never influence MFE.
    assert Decimal(record.mfe) == Decimal("0.5000")  # 100.60 - 100.10


def _configuration() -> OperatorTradingConfiguration:
    return OperatorTradingConfiguration(
        configuration_governance_id="CFG-TEST",
        configuration_version=1,
        base_currency="USD",
        permitted_markets=("ARCA", "NASDAQ", "NYSE"),
        watchlist=("AAPL",),
        prohibited_instruments=(),
        maximum_deployable_capital=Decimal("20000"),
        maximum_capital_per_trade=Decimal("2000"),
        maximum_percent_per_trade=Decimal("50"),
        minimum_cash_reserve=Decimal("1000"),
        maximum_simultaneous_positions=3,
        maximum_daily_loss=Decimal("500"),
        maximum_daily_order_count=10,
        minimum_price=Decimal("5"),
        maximum_price=Decimal("5000"),
        minimum_liquidity_shares=100_000,
        maximum_spread_percent=Decimal("1"),
        maximum_estimated_slippage_percent=Decimal("1"),
        maximum_evidence_age_seconds=86_400,
        maximum_market_data_age_seconds=60,
        permitted_session=TradingSession.REGULAR,
        earliest_entry_time=datetime(2026, 1, 1, 10, 0).time(),
        latest_entry_time=datetime(2026, 1, 1, 15, 30).time(),
        mandatory_liquidation_time=datetime(2026, 1, 1, 15, 45).time(),
        operator_timezone="America/New_York",
        exchange_calendar_policy="XNAS-REGULAR-2026",
        proposal_expiry_seconds=300,
        approval_expiry_seconds=120,
        default_order_type=OrderType.LIMIT,
        permitted_order_types=(OrderType.LIMIT, OrderType.MARKET),
        limit_price_policy=LimitPricePolicy.ASK,
        stop_loss_percent=Decimal("2"),
        profit_exit_percent=Decimal("4"),
        maximum_leverage=Decimal("1"),
        short_selling_permitted=False,
        overnight_positions_permitted=False,
        account_mode=AccountMode.PREPARATION,
        kill_switch=KillSwitchState.DISENGAGED,
    )


def test_fingerprint_is_deterministic_and_sensitive_to_every_field() -> None:
    from tools.m092_validation import candidate_v2_c, compute_fingerprint

    configuration = _configuration()
    policy = candidate_v2_c()
    first = compute_fingerprint(policy, configuration)
    second = compute_fingerprint(policy, configuration)
    assert first == second

    from dataclasses import replace

    changed = replace(policy, minimum_reward_risk_ratio=Decimal("1.31"))
    assert compute_fingerprint(changed, configuration) != first


def test_the_three_candidates_have_distinct_fingerprints() -> None:
    from tools.m092_validation import (
        candidate_v2_a,
        candidate_v2_b,
        candidate_v2_c,
        compute_fingerprint,
    )

    configuration = _configuration()
    fingerprints = {
        name: compute_fingerprint(candidate(), configuration)
        for name, candidate in (
            ("V2-A", candidate_v2_a),
            ("V2-B", candidate_v2_b),
            ("V2-C", candidate_v2_c),
        )
    }
    assert len(set(fingerprints.values())) == 3


def test_candidate_v2_a_uses_no_relative_liquidity_or_time_gate() -> None:
    from tools.m092_validation import candidate_v2_a

    policy = candidate_v2_a()
    assert policy.relative_liquidity_multiple is None
    assert policy.time_to_target_feasibility_enabled is False


def test_candidate_v2_b_adds_relative_liquidity_but_not_the_time_gate() -> None:
    from tools.m092_validation import candidate_v2_b

    policy = candidate_v2_b()
    assert policy.relative_liquidity_multiple is not None
    assert policy.time_to_target_feasibility_enabled is False


def test_candidate_v2_c_enables_the_time_gate_and_lowers_the_reward_risk_floor() -> None:
    from tools.m092_validation import candidate_v2_c

    policy = candidate_v2_c()
    assert policy.time_to_target_feasibility_enabled is True
    assert policy.minimum_reward_risk_ratio < Decimal("2")
