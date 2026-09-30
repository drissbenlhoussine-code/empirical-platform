"""MILESTONE-090 Phase 19 -- the replay harness: deterministic outcomes and a look-ahead audit.

Every bar sequence here is hand-built with literal Decimal prices so the expected outcome can
be verified by inspection, exactly like `test_decision_candidate_opportunity_engine.py`'s own
arithmetic tests.
"""

from __future__ import annotations

from datetime import UTC, datetime, time
from decimal import Decimal

from tests.unit._m090_fakes import FakeBars, FakeBarView

from empirical_platform.decision_candidate.market_data import Bar, BarInterval, Instrument
from empirical_platform.decision_candidate.operator_trading_configuration import (
    AccountMode,
    KillSwitchState,
    LimitPricePolicy,
    OperatorTradingConfiguration,
    OrderType,
    TradingSession,
)
from empirical_platform.decision_candidate.opportunity_engine import (
    OpportunityEnginePolicy,
    RejectionReason,
)
from empirical_platform.usecases.opportunity_engine_replay import (
    ReplayDecision,
    ReplayOutcome,
    fetch_session_bars,
    replay_session,
)

_SYMBOL = "AAPL"


def _configuration(**overrides: object) -> OperatorTradingConfiguration:
    defaults: dict[str, object] = {
        "configuration_governance_id": "CFG-090-REPLAY-0001",
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


def _policy(**overrides: object) -> OpportunityEnginePolicy:
    defaults: dict[str, object] = {
        "policy_version": "M090-V1",
        "structure_lookback_bars": 5,
        "minimum_recent_share_volume": 1000,
        "minimum_reward_risk_ratio": Decimal("2"),
        "maximum_loss_per_trade": Decimal("100"),
        "top_n": 5,
        "entry_tolerance_percent": Decimal("0.5"),
        "opportunity_validity_seconds": 300,
    }
    defaults.update(overrides)
    return OpportunityEnginePolicy(**defaults)  # type: ignore[arg-type]


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
    """5 reference bars + 1 breakout bar, identical to the domain suite's own fixture: entry
    101.50, stop 99.00 (the trough of the monotonically rising reference lows), risk 2.50,
    target 106.50 at a 2:1 floor."""
    return [
        _bar(minute=0, o="100.00", h="100.50", low="99.00", c="100.00", v=1000),
        _bar(minute=1, o="100.00", h="100.60", low="99.20", c="100.20", v=1000),
        _bar(minute=2, o="100.20", h="100.70", low="99.40", c="100.30", v=1000),
        _bar(minute=3, o="100.30", h="100.80", low="99.60", c="100.40", v=1000),
        _bar(minute=4, o="100.40", h="101.00", low="99.80", c="100.50", v=1000),
        _bar(minute=5, o="100.50", h="101.80", low="100.10", c="101.50", v=2500),
    ]


def _flat_bar(minute: int) -> Bar:
    # Volume above the policy's liquidity floor (1000) so a flat/no-breakout fixture is
    # rejected for the reason under test, not masked by INSUFFICIENT_LIQUIDITY first -- the
    # same ordering pitfall the domain test suite already documents.
    return _bar(minute=minute, o="101.50", h="101.55", low="101.45", c="101.50", v=1200)


def test_a_target_hit_resolves_correctly() -> None:
    bars = _breakout_prefix()
    # Bar 6: high reaches 106.50 (the target) without the low touching 99.00 (the stop) first.
    bars.append(_bar(minute=6, o="101.50", h="106.60", low="101.00", c="106.00", v=2000))
    liquidation_at = datetime(2026, 6, 10, 15, 45, tzinfo=UTC)
    result = replay_session(
        symbol=_SYMBOL,
        session_date=bars[0].timestamp.date(),
        bars=tuple(bars),
        policy=_policy(),
        configuration=_configuration(),
        deployable_capital=Decimal("10000"),
        mandatory_liquidation_at=liquidation_at,
    )
    # The walk evaluates EVERY bar with enough reference history, not just the intended one --
    # bar 6 (itself still rising) may seed a SECOND, later breakout decision. Select the one
    # this test is actually about by its bar index, not by assumed uniqueness.
    (decision,) = [d for d in result.decisions if d.bar_index == 5]
    assert decision.entry_price == Decimal("101.50")
    assert decision.stop_price == Decimal("99.00")
    assert decision.target_price == Decimal("106.50")
    assert decision.outcome is ReplayOutcome.TARGET_HIT
    assert decision.outcome_price == Decimal("106.50")
    assert decision.realized_pnl_per_share == Decimal("5.00")


def test_a_stop_hit_resolves_correctly() -> None:
    bars = _breakout_prefix()
    bars.append(_bar(minute=6, o="101.50", h="102.00", low="98.50", c="99.50", v=2000))
    liquidation_at = datetime(2026, 6, 10, 15, 45, tzinfo=UTC)
    result = replay_session(
        symbol=_SYMBOL,
        session_date=bars[0].timestamp.date(),
        bars=tuple(bars),
        policy=_policy(),
        configuration=_configuration(),
        deployable_capital=Decimal("10000"),
        mandatory_liquidation_at=liquidation_at,
    )
    (decision,) = [d for d in result.decisions if d.bar_index == 5]
    assert decision.outcome is ReplayOutcome.STOP_HIT
    assert decision.outcome_price == Decimal("99.00")
    assert decision.realized_pnl_per_share == Decimal("-2.50")


def test_same_bar_stop_and_target_resolves_stop_first() -> None:
    bars = _breakout_prefix()
    # Bar 6's range spans BOTH the stop (99.00) and the target (106.50) -- an impossible-but-
    # illustrative worst case, resolved conservatively.
    bars.append(_bar(minute=6, o="101.50", h="107.00", low="98.00", c="100.00", v=2000))
    liquidation_at = datetime(2026, 6, 10, 15, 45, tzinfo=UTC)
    result = replay_session(
        symbol=_SYMBOL,
        session_date=bars[0].timestamp.date(),
        bars=tuple(bars),
        policy=_policy(),
        configuration=_configuration(),
        deployable_capital=Decimal("10000"),
        mandatory_liquidation_at=liquidation_at,
    )
    (decision,) = [d for d in result.decisions if d.bar_index == 5]
    assert decision.outcome is ReplayOutcome.STOP_HIT


def test_reaching_mandatory_liquidation_with_neither_stop_nor_target_hit() -> None:
    bars = _breakout_prefix()
    # Flat bars all the way to and past the mandatory liquidation instant.
    for minute in range(6, 20):
        bars.append(_flat_bar(minute))
    liquidation_at = datetime(2026, 6, 10, 14, 15, tzinfo=UTC)  # inside the flat run
    result = replay_session(
        symbol=_SYMBOL,
        session_date=bars[0].timestamp.date(),
        bars=tuple(bars),
        policy=_policy(),
        configuration=_configuration(),
        deployable_capital=Decimal("10000"),
        mandatory_liquidation_at=liquidation_at,
    )
    (decision,) = [d for d in result.decisions if d.bar_index == 5]
    assert decision.outcome is ReplayOutcome.MANDATORY_EXIT
    assert decision.outcome_at is not None and decision.outcome_at >= liquidation_at


def test_running_out_of_bars_before_any_resolution_is_unresolved_not_a_win_or_a_loss() -> None:
    bars = _breakout_prefix()
    bars.append(_flat_bar(6))  # neither stop nor target nor the (far-future) liquidation instant
    liquidation_at = datetime(2026, 6, 10, 20, 0, tzinfo=UTC)  # never reached by this short feed
    result = replay_session(
        symbol=_SYMBOL,
        session_date=bars[0].timestamp.date(),
        bars=tuple(bars),
        policy=_policy(),
        configuration=_configuration(),
        deployable_capital=Decimal("10000"),
        mandatory_liquidation_at=liquidation_at,
    )
    (decision,) = [d for d in result.decisions if d.bar_index == 5]
    assert decision.outcome is ReplayOutcome.UNRESOLVED_END_OF_DATA
    assert decision.outcome_at is None and decision.outcome_price is None
    assert decision.realized_pnl_per_share is None


def test_a_flat_session_produces_zero_actionable_decisions_with_the_correct_reason() -> None:
    bars = [_flat_bar(minute) for minute in range(0, 10)]
    liquidation_at = datetime(2026, 6, 10, 15, 45, tzinfo=UTC)
    result = replay_session(
        symbol=_SYMBOL,
        session_date=bars[0].timestamp.date(),
        bars=tuple(bars),
        policy=_policy(),
        configuration=_configuration(),
        deployable_capital=Decimal("10000"),
        mandatory_liquidation_at=liquidation_at,
    )
    assert all(d.rejection_reasons for d in result.decisions)
    assert all(
        d.rejection_reasons == (RejectionReason.NO_BREAKOUT_STRUCTURE,) for d in result.decisions
    )


def test_too_few_reference_bars_are_never_evaluated_at_all() -> None:
    bars = [_flat_bar(minute) for minute in range(0, 3)]
    result = replay_session(
        symbol=_SYMBOL,
        session_date=bars[0].timestamp.date(),
        bars=tuple(bars),
        policy=_policy(structure_lookback_bars=5),
        configuration=_configuration(),
        deployable_capital=Decimal("10000"),
        mandatory_liquidation_at=datetime(2026, 6, 10, 15, 45, tzinfo=UTC),
    )
    assert result.decisions == ()  # nothing reaches index >= lookback


def test_replay_is_deterministic() -> None:
    bars = tuple(
        _breakout_prefix()
        + [_bar(minute=6, o="101.50", h="106.60", low="101.00", c="106.00", v=2000)]
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
    first = replay_session(**kwargs)  # type: ignore[arg-type]
    second = replay_session(**kwargs)  # type: ignore[arg-type]
    assert first == second


# ---------------------------------------------------------------------------
# fetch_session_bars
# ---------------------------------------------------------------------------


def test_fetch_session_bars_sorts_and_deduplicates() -> None:
    unordered = (
        FakeBarView(
            symbol=_SYMBOL,
            timestamp=datetime(2026, 6, 10, 14, 1, tzinfo=UTC),
            open="100",
            high="101",
            low="99",
            close="100.5",
            volume=100,
        ),
        FakeBarView(
            symbol=_SYMBOL,
            timestamp=datetime(2026, 6, 10, 14, 0, tzinfo=UTC),
            open="99",
            high="100",
            low="98",
            close="99.5",
            volume=100,
        ),
        # A duplicate timestamp of the second bar above.
        FakeBarView(
            symbol=_SYMBOL,
            timestamp=datetime(2026, 6, 10, 14, 0, tzinfo=UTC),
            open="99",
            high="100",
            low="98",
            close="99.5",
            volume=100,
        ),
    )
    bars_port = FakeBars(bars={_SYMBOL: unordered})
    bars = fetch_session_bars(
        bars_port,
        _SYMBOL,
        date_arg := datetime(2026, 6, 10).date(),
        session_start=time(9, 30),
        session_end=time(16, 0),
        operator_timezone="UTC",
    )
    del date_arg
    assert [b.timestamp for b in bars] == [
        datetime(2026, 6, 10, 14, 0, tzinfo=UTC),
        datetime(2026, 6, 10, 14, 1, tzinfo=UTC),
    ]


def test_fetch_session_bars_returns_empty_for_a_symbol_with_no_data() -> None:
    bars_port = FakeBars(bars={})
    bars = fetch_session_bars(
        bars_port,
        _SYMBOL,
        datetime(2026, 6, 10).date(),
        session_start=time(9, 30),
        session_end=time(16, 0),
        operator_timezone="UTC",
    )
    assert bars == ()


# ---------------------------------------------------------------------------
# G. Look-ahead audit
# ---------------------------------------------------------------------------


def test_no_decision_is_affected_by_any_bar_that_occurs_after_it() -> None:
    """The rigorous, whole-walk version: an impossible, extreme bar appended at the END of the
    sequence must not change ANY earlier decision's TERMS (entry/stop/target/quantity/
    rejection reasons) -- proving the walk-forward DECISION loop as a whole, not just one
    window in isolation.

    OUTCOME RESOLUTION is deliberately excluded from this comparison: `_resolve_outcome` reads
    `bars[index + 1 :]` ON PURPOSE (that is how a backtest learns what happened afterward), so
    appending a bar can legitimately turn an UNRESOLVED_END_OF_DATA outcome into a resolved
    one. That is not a look-ahead leak in the DECISION -- it is exactly what resolution is for.
    """
    baseline_bars = tuple(
        _breakout_prefix()
        + [_bar(minute=6, o="101.50", h="106.60", low="101.00", c="106.00", v=2000)]
        + [_flat_bar(minute) for minute in range(7, 12)]
    )
    kwargs = dict(
        symbol=_SYMBOL,
        session_date=baseline_bars[0].timestamp.date(),
        policy=_policy(),
        configuration=_configuration(),
        deployable_capital=Decimal("10000"),
        mandatory_liquidation_at=datetime(2026, 6, 10, 15, 45, tzinfo=UTC),
    )
    baseline = replay_session(bars=baseline_bars, **kwargs)  # type: ignore[arg-type]

    # An impossible future bar (price 1,000,000, volume 999,999,999) appended at the very end.
    poisoned_bars = baseline_bars + (
        _bar(minute=12, o="1000000", h="1000000", low="1000000", c="1000000", v=999_999_999),
    )
    poisoned = replay_session(bars=poisoned_bars, **kwargs)  # type: ignore[arg-type]

    def _decision_terms(d: ReplayDecision) -> tuple[object, ...]:
        return (
            d.bar_index,
            d.decided_at,
            d.rejection_reasons,
            d.entry_price,
            d.stop_price,
            d.target_price,
            d.risk_per_share,
            d.reward_per_share,
            d.reward_risk_ratio,
            d.quantity,
            d.quality_score,
        )

    baseline_terms = [_decision_terms(d) for d in baseline.decisions]
    poisoned_terms = [_decision_terms(d) for d in poisoned.decisions[: len(baseline.decisions)]]
    assert poisoned_terms == baseline_terms


def test_the_decision_function_never_receives_bars_after_its_own_index() -> None:
    """A structural proof, not just an outcome comparison: instrument the bar sequence itself
    so any read past the decision index raises immediately."""
    from empirical_platform.usecases.opportunity_engine_replay import _decide_at

    class _TripwireSequence(tuple[Bar, ...]):
        """A tuple subclass that raises if sliced/indexed past `allowed_upper`."""

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
    # Must not raise: _decide_at(bars, 5, ...) may read up to and including index 5.
    decision = _decide_at(
        bars,
        5,
        symbol=_SYMBOL,
        policy=_policy(),
        configuration=_configuration(),
        deployable_capital=Decimal("10000"),
    )
    assert not decision.rejection_reasons
