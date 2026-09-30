"""MILESTONE-092 -- the V2 replay harness: deterministic outcomes and a look-ahead audit.
Mirrors `test_usecases_opportunity_engine_replay.py`'s (V1's) own discipline exactly."""

from __future__ import annotations

from datetime import UTC, datetime, time
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
from empirical_platform.decision_candidate.opportunity_engine_v2 import (
    OpportunityEnginePolicyV2,
)
from empirical_platform.usecases.opportunity_engine_v2_replay import (
    ReplayOutcomeV2,
    replay_session_v2,
)

_SYMBOL = "AAPL"


def _configuration(**overrides: object) -> OperatorTradingConfiguration:
    defaults: dict[str, object] = {
        "configuration_governance_id": "CFG-092-REPLAY-TEST",
        "configuration_version": 1,
        "base_currency": "USD",
        "permitted_markets": ("NASDAQ",),
        "watchlist": (_SYMBOL,),
        "prohibited_instruments": ("PENNY",),
        "maximum_deployable_capital": Decimal("10000"),
        "maximum_capital_per_trade": Decimal("2000"),
        "maximum_percent_per_trade": Decimal("50"),
        "minimum_cash_reserve": Decimal("1000"),
        "maximum_simultaneous_positions": 3,
        "maximum_daily_loss": Decimal("500"),
        "maximum_daily_order_count": 10,
        "minimum_price": Decimal("5"),
        "maximum_price": Decimal("1000"),
        "minimum_liquidity_shares": 100_000,
        "maximum_spread_percent": Decimal("1"),
        "maximum_estimated_slippage_percent": Decimal("1"),
        "maximum_evidence_age_seconds": 86_400,
        "maximum_market_data_age_seconds": 60,
        "permitted_session": TradingSession.REGULAR,
        "earliest_entry_time": time(10, 0),
        "latest_entry_time": time(15, 30),
        "mandatory_liquidation_time": time(15, 45),
        "operator_timezone": "UTC",
        "exchange_calendar_policy": "XNAS-REGULAR-2026",
        "proposal_expiry_seconds": 300,
        "approval_expiry_seconds": 120,
        "default_order_type": OrderType.LIMIT,
        "permitted_order_types": (OrderType.LIMIT, OrderType.MARKET),
        "limit_price_policy": LimitPricePolicy.ASK,
        "stop_loss_percent": Decimal("2"),
        "profit_exit_percent": Decimal("4"),
        "maximum_leverage": Decimal("1"),
        "short_selling_permitted": False,
        "overnight_positions_permitted": False,
        "account_mode": AccountMode.PREPARATION,
        "kill_switch": KillSwitchState.DISENGAGED,
    }
    defaults.update(overrides)
    return OperatorTradingConfiguration(**defaults)  # type: ignore[arg-type]


def _policy(**overrides: object) -> OpportunityEnginePolicyV2:
    defaults: dict[str, object] = {
        "policy_version": "M092-V2-TEST",
        "structure_lookback_bars": 5,
        "minimum_recent_share_volume": 1000,
        "relative_liquidity_multiple": None,
        "minimum_volume_ratio": Decimal("1.2"),
        "minimum_close_location_value": Decimal("0.5"),
        "target_range_multiple": Decimal("2"),
        "minimum_reward_risk_ratio": Decimal("1"),
        "time_to_target_feasibility_enabled": False,
        "time_to_target_safety_factor": Decimal("1"),
        "maximum_loss_per_trade": Decimal("100"),
        "top_n": 5,
        "entry_tolerance_percent": Decimal("0.5"),
        "opportunity_validity_seconds": 300,
    }
    defaults.update(overrides)
    return OpportunityEnginePolicyV2(**defaults)  # type: ignore[arg-type]


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


def _breakout_prefix() -> list[Bar]:
    return [
        _bar(minute=0, o="100.00", h="100.50", low="99.00", c="100.00", v=1000),
        _bar(minute=1, o="100.00", h="100.40", low="99.20", c="100.20", v=1000),
        _bar(minute=2, o="100.20", h="100.30", low="99.40", c="100.30", v=1000),
        _bar(minute=3, o="100.30", h="100.45", low="99.60", c="100.40", v=1000),
        _bar(minute=4, o="100.40", h="100.50", low="99.80", c="100.50", v=1000),
        _bar(minute=5, o="101.45", h="101.60", low="101.40", c="101.55", v=2500),
    ]


def test_replay_is_deterministic() -> None:
    bars = tuple(
        _breakout_prefix()
        + [_bar(minute=6, o="101.50", h="110.00", low="101.00", c="106.00", v=2000)]
    )
    kwargs = dict(
        symbol=_SYMBOL,
        session_date=bars[0].timestamp.date(),
        bars=bars,
        policy=_policy(),
        configuration=_configuration(),
        deployable_capital=Decimal("10000"),
        mandatory_liquidation_at=datetime(2026, 6, 10, 15, 45, tzinfo=UTC),
    )
    first = replay_session_v2(**kwargs)  # type: ignore[arg-type]
    second = replay_session_v2(**kwargs)  # type: ignore[arg-type]
    assert first == second


def test_a_target_hit_resolves_correctly() -> None:
    bars = _breakout_prefix()
    bars.append(_bar(minute=6, o="101.50", h="110.00", low="101.00", c="106.00", v=2000))
    result = replay_session_v2(
        symbol=_SYMBOL,
        session_date=bars[0].timestamp.date(),
        bars=tuple(bars),
        policy=_policy(),
        configuration=_configuration(),
        deployable_capital=Decimal("10000"),
        mandatory_liquidation_at=datetime(2026, 6, 10, 15, 45, tzinfo=UTC),
    )
    (decision,) = [d for d in result.decisions if d.bar_index == 5]
    assert not decision.rejection_reasons
    assert decision.outcome is ReplayOutcomeV2.TARGET_HIT


def test_no_decision_is_affected_by_any_bar_that_occurs_after_it() -> None:
    """The whole-walk look-ahead proof: an impossible extreme bar appended at the END of the
    sequence must not change ANY earlier decision's TERMS."""
    baseline_bars = tuple(
        _breakout_prefix()
        + [_bar(minute=6, o="101.50", h="110.00", low="101.00", c="106.00", v=2000)]
        + [
            _bar(minute=m, o="101.50", h="101.55", low="101.45", c="101.50", v=1200)
            for m in range(7, 12)
        ]
    )
    kwargs = dict(
        symbol=_SYMBOL,
        session_date=baseline_bars[0].timestamp.date(),
        policy=_policy(),
        configuration=_configuration(),
        deployable_capital=Decimal("10000"),
        mandatory_liquidation_at=datetime(2026, 6, 10, 15, 45, tzinfo=UTC),
    )
    baseline = replay_session_v2(bars=baseline_bars, **kwargs)  # type: ignore[arg-type]

    poisoned_bars = baseline_bars + (
        _bar(minute=12, o="1000000", h="1000000", low="1000000", c="1000000", v=999_999_999),
    )
    poisoned = replay_session_v2(bars=poisoned_bars, **kwargs)  # type: ignore[arg-type]

    def _terms(d: object) -> tuple[object, ...]:
        return (
            d.bar_index,  # type: ignore[attr-defined]
            d.decided_at,  # type: ignore[attr-defined]
            d.rejection_reasons,  # type: ignore[attr-defined]
            d.entry_price,  # type: ignore[attr-defined]
            d.stop_price,  # type: ignore[attr-defined]
            d.target_price,  # type: ignore[attr-defined]
            d.quantity,  # type: ignore[attr-defined]
        )

    baseline_terms = [_terms(d) for d in baseline.decisions]
    poisoned_terms = [_terms(d) for d in poisoned.decisions[: len(baseline.decisions)]]
    assert poisoned_terms == baseline_terms


def test_the_decide_function_never_reads_bars_after_its_own_index() -> None:
    """A structural proof, not just an outcome comparison: instrument the bar sequence so
    any read past the decision index raises immediately."""
    from empirical_platform.usecases.opportunity_engine_v2_replay import _decide_at

    class _TripwireSequence(tuple[Bar, ...]):
        allowed_upper: int = 0

        def __getitem__(self, item: int | slice) -> object:  # type: ignore[override]
            if isinstance(item, slice):
                stop = item.stop
                if stop is not None and stop > self.allowed_upper + 1:
                    raise AssertionError(
                        f"look-ahead: sliced up to {stop}, only {self.allowed_upper + 1} allowed"
                    )
            elif isinstance(item, int) and item > self.allowed_upper:
                raise AssertionError(f"look-ahead: indexed {item} > {self.allowed_upper}")
            return super().__getitem__(item)

    bars = _TripwireSequence(_breakout_prefix())
    bars.allowed_upper = 5
    decision = _decide_at(
        bars,
        5,
        symbol=_SYMBOL,
        policy=_policy(),
        configuration=_configuration(),
        deployable_capital=Decimal("10000"),
        mandatory_liquidation_at=datetime(2026, 6, 10, 15, 45, tzinfo=UTC),
    )
    assert not decision.rejection_reasons
