"""MILESTONE-090 -- the Opportunity Engine usecases: generate, review, approve, ignore.

Over an in-memory world with fully controllable broker/market-data/bars fakes
(`tests/unit/_m090_fakes.py`) -- no network, no Postgres, no real broker.
"""

from __future__ import annotations

from datetime import UTC, datetime, time, timedelta
from decimal import Decimal

import pytest
from tests.unit._m090_fakes import (
    FakeAssetView,
    FakeBars,
    FakeBarView,
    FakeClockView,
    FakeOpportunities,
    FakeOpportunityBroker,
    FakeOpportunityDecisions,
    FakeOpportunityMarketData,
    FakeQuoteView,
)

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
    OpportunityStatus,
    RejectionReason,
    TradingOpportunity,
)
from empirical_platform.usecases.opportunity_engine import (
    ApproveOpportunityCommand,
    ApproveOpportunityHandler,
    GenerateOpportunitiesCommand,
    GenerateOpportunitiesHandler,
    IgnoreOpportunityCommand,
    IgnoreOpportunityHandler,
    OpportunityEngineRefusedError,
    ReviewOpportunityHandler,
    select_top_actionable,
)

_SYMBOL = "AAPL"
_NOW = datetime(2026, 6, 10, 14, 0, tzinfo=UTC)


def _configuration(**overrides: object) -> OperatorTradingConfiguration:
    defaults: dict[str, object] = {
        "configuration_governance_id": "CFG-090-0001",
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


def _bar(*, minute: int, o: str, h: str, low: str, c: str, v: int) -> FakeBarView:
    return FakeBarView(
        symbol=_SYMBOL,
        timestamp=datetime(2026, 6, 10, 13, minute, tzinfo=UTC),
        open=o,
        high=h,
        low=low,
        close=c,
        volume=v,
    )


def _breakout_bars() -> tuple[FakeBarView, ...]:
    return (
        _bar(minute=54, o="100.00", h="100.50", low="99.00", c="100.00", v=1000),
        _bar(minute=55, o="100.00", h="100.60", low="99.20", c="100.20", v=1000),
        _bar(minute=56, o="100.20", h="100.70", low="99.40", c="100.30", v=1000),
        _bar(minute=57, o="100.30", h="100.80", low="99.60", c="100.40", v=1000),
        _bar(minute=58, o="100.40", h="101.00", low="99.80", c="100.50", v=1000),
        _bar(minute=59, o="100.50", h="101.80", low="100.10", c="101.50", v=2500),
    )


def _world(
    *,
    clock: FakeClockView | None = None,
    quote_ask: str = "101.50",
    quote_bid: str = "101.45",
    quote_captured_at: datetime | None = None,
    bars: tuple[FakeBarView, ...] | None = None,
    asset: FakeAssetView | None = None,
) -> dict[str, object]:
    clock = clock or FakeClockView(is_open=True, timestamp=_NOW)
    broker = FakeOpportunityBroker(
        clock=clock,
        assets={_SYMBOL: asset if asset is not None else FakeAssetView(symbol=_SYMBOL)},
    )
    market_data = FakeOpportunityMarketData(
        quotes={
            _SYMBOL: FakeQuoteView(
                symbol=_SYMBOL,
                bid=quote_bid,
                ask=quote_ask,
                captured_at=quote_captured_at or (clock.timestamp - timedelta(seconds=5)),
            )
        }
    )
    bars_port = FakeBars(bars={_SYMBOL: bars if bars is not None else _breakout_bars()})
    opportunities = FakeOpportunities()
    decisions = FakeOpportunityDecisions()
    return {
        "clock": clock,
        "broker": broker,
        "market_data": market_data,
        "bars": bars_port,
        "opportunities": opportunities,
        "decisions": decisions,
    }


def _generate(
    world: dict[str, object],
    *,
    configuration: OperatorTradingConfiguration | None = None,
    policy: OpportunityEnginePolicy | None = None,
) -> tuple[TradingOpportunity, ...]:
    handler = GenerateOpportunitiesHandler(
        configuration=configuration or _configuration(),
        policy=policy or _policy(),
        broker=world["broker"],  # type: ignore[arg-type]
        market_data=world["market_data"],  # type: ignore[arg-type]
        bars=world["bars"],  # type: ignore[arg-type]
        opportunities=world["opportunities"],  # type: ignore[arg-type]
    )
    return handler.handle(
        GenerateOpportunitiesCommand(session_date="2026-06-10", generated_at=_NOW)
    )


# ---------------------------------------------------------------------------
# Generation: happy path, rejections, resilience
# ---------------------------------------------------------------------------


def test_a_qualifying_symbol_produces_one_actionable_opportunity() -> None:
    world = _world()
    (opportunity,) = _generate(world)
    assert opportunity.status is OpportunityStatus.ACTIONABLE
    assert opportunity.symbol == _SYMBOL
    assert opportunity.entry_price == Decimal("101.50")
    # The reference window's lows rise monotonically (99.00 -> 99.80), so the trough -- and
    # therefore the structural swing low -- is the FIRST reference bar's low, 99.00.
    assert opportunity.stop_price == Decimal("99.00")
    assert opportunity.risk_per_share == Decimal("2.50")
    assert opportunity.target_price == Decimal("106.50")
    assert opportunity.quantity is not None and opportunity.quantity >= 1
    assert opportunity.mandatory_liquidation_at == datetime(2026, 6, 10, 15, 45, tzinfo=UTC)
    assert not opportunity.rejection_reasons
    assert len(opportunity.evidence) >= 3


def test_only_watchlisted_symbols_are_ever_evaluated() -> None:
    """The universe IS the watchlist (Phase 3): the handler iterates it directly, so a symbol
    absent from it is never looked up at all -- `asset_eligibility_refusal`'s own
    NOT_ON_WATCHLIST branch (proven directly in the domain test suite) is a second line of
    defense for a case this handler cannot otherwise reach, precisely because
    OperatorTradingConfiguration's own validation keeps watchlist and prohibited_instruments
    disjoint, and this handler asks about nothing else."""
    world = _world()
    configuration = _configuration(watchlist=(_SYMBOL,))
    _generate(world, configuration=configuration)
    assert world["broker"].asset_lookups == [_SYMBOL]  # type: ignore[attr-defined]


def test_a_non_tradable_asset_is_rejected() -> None:
    world = _world(asset=FakeAssetView(symbol=_SYMBOL, tradable=False))
    (opportunity,) = _generate(world)
    assert opportunity.rejection_reasons == (RejectionReason.NOT_TRADABLE,)


def test_a_stale_quote_is_rejected() -> None:
    world = _world(quote_captured_at=_NOW - timedelta(seconds=120))
    (opportunity,) = _generate(world)
    assert opportunity.rejection_reasons == (RejectionReason.QUOTE_STALE_OR_INVALID,)


def test_a_crossed_quote_is_rejected() -> None:
    world = _world(quote_bid="102.00", quote_ask="101.00")
    (opportunity,) = _generate(world)
    assert opportunity.rejection_reasons == (RejectionReason.QUOTE_STALE_OR_INVALID,)


def test_no_breakout_is_rejected_with_the_right_reason() -> None:
    flat_bars = (
        _bar(minute=54, o="100.00", h="100.50", low="99.00", c="100.00", v=1000),
        _bar(minute=55, o="100.00", h="100.60", low="99.20", c="100.20", v=1000),
        _bar(minute=56, o="100.20", h="100.70", low="99.40", c="100.30", v=1000),
        _bar(minute=57, o="100.30", h="100.80", low="99.60", c="100.40", v=1000),
        _bar(minute=58, o="100.40", h="101.00", low="99.80", c="100.50", v=1000),
        # Volume clears the liquidity floor (1000) so this isolates the BREAKOUT condition --
        # the close (100.60) stays below the reference range high (101.00).
        _bar(minute=59, o="100.50", h="100.90", low="100.10", c="100.60", v=1200),
    )
    world = _world(bars=flat_bars)
    (opportunity,) = _generate(world)
    assert opportunity.rejection_reasons == (RejectionReason.NO_BREAKOUT_STRUCTURE,)


def test_weak_liquidity_is_rejected() -> None:
    world = _world()
    policy = _policy(minimum_recent_share_volume=1_000_000)
    (opportunity,) = _generate(world, policy=policy)
    assert opportunity.rejection_reasons == (RejectionReason.INSUFFICIENT_LIQUIDITY,)


def test_missing_bars_are_insufficient_evidence() -> None:
    world = _world(bars=())
    (opportunity,) = _generate(world)
    assert opportunity.rejection_reasons == (RejectionReason.STALE_OR_MISSING_BARS,)


def test_a_broker_error_on_one_symbol_does_not_crash_the_whole_batch() -> None:
    world = _world()
    configuration = _configuration(watchlist=(_SYMBOL, "MSFT"))
    # MSFT has no configured asset in the fake broker -> raises BrokerResponseInvalidError,
    # which GenerateOpportunitiesHandler must catch per-symbol, not propagate.
    opportunities = _generate(world, configuration=configuration)
    by_symbol = {o.symbol: o for o in opportunities}
    assert by_symbol[_SYMBOL].status is OpportunityStatus.ACTIONABLE
    assert by_symbol["MSFT"].status is OpportunityStatus.REJECTED
    assert by_symbol["MSFT"].rejection_reasons == (RejectionReason.INSUFFICIENT_EVIDENCE,)


def test_quantity_less_than_one_is_rejected_not_silently_rounded_to_one() -> None:
    world = _world()
    policy = _policy(maximum_loss_per_trade=Decimal("0.01"))
    (opportunity,) = _generate(world, policy=policy)
    assert opportunity.rejection_reasons == (RejectionReason.QUANTITY_LESS_THAN_ONE,)


# ---------------------------------------------------------------------------
# E. Session
# ---------------------------------------------------------------------------


def test_outside_the_entry_window_a_qualifying_symbol_is_a_candidate_not_actionable() -> None:
    clock = FakeClockView(is_open=True, timestamp=datetime(2026, 6, 10, 9, 0, tzinfo=UTC))
    world = _world(
        clock=clock,
        quote_captured_at=clock.timestamp - timedelta(seconds=5),
        bars=tuple(
            FakeBarView(
                symbol=_SYMBOL,
                timestamp=b.timestamp - timedelta(hours=5),
                open=b.open,
                high=b.high,
                low=b.low,
                close=b.close,
                volume=b.volume,
            )
            for b in _breakout_bars()
        ),
    )
    (opportunity,) = _generate(world)
    assert opportunity.status is OpportunityStatus.CANDIDATE
    assert opportunity.entry_price is not None  # still fully planned, just not offerable yet


def test_a_closed_market_produces_a_candidate_not_actionable() -> None:
    clock = FakeClockView(is_open=False, timestamp=_NOW)
    world = _world(clock=clock, quote_captured_at=clock.timestamp - timedelta(seconds=5))
    (opportunity,) = _generate(world)
    assert opportunity.status is OpportunityStatus.CANDIDATE


def test_every_actionable_opportunity_carries_a_mandatory_exit() -> None:
    world = _world()
    (opportunity,) = _generate(world)
    assert opportunity.status is OpportunityStatus.ACTIONABLE
    assert opportunity.mandatory_liquidation_at is not None


# ---------------------------------------------------------------------------
# Ranking / top-N
# ---------------------------------------------------------------------------


def test_select_top_actionable_only_returns_actionable_rows_ranked() -> None:
    world = _world()
    configuration = _configuration(watchlist=(_SYMBOL, "MSFT"))
    opportunities = _generate(world, configuration=configuration)
    top = select_top_actionable(opportunities, top_n=5)
    assert all(o.status is OpportunityStatus.ACTIONABLE for o in top)
    assert len(top) == 1  # MSFT was rejected (no configured asset)


def test_top_n_caps_the_returned_count() -> None:
    world = _world()
    (opportunity,) = _generate(world)
    only = (opportunity,)
    assert select_top_actionable(only, top_n=0) == ()


# ---------------------------------------------------------------------------
# Review / Approve / Ignore -- the Owner gate (H), and re-verification (Phase 16)
# ---------------------------------------------------------------------------


def _review_handler(
    world: dict[str, object],
    *,
    configuration: OperatorTradingConfiguration | None = None,
    policy: OpportunityEnginePolicy | None = None,
) -> ReviewOpportunityHandler:
    return ReviewOpportunityHandler(
        configuration=configuration or _configuration(),
        policy=policy or _policy(),
        broker=world["broker"],  # type: ignore[arg-type]
        market_data=world["market_data"],  # type: ignore[arg-type]
        bars=world["bars"],  # type: ignore[arg-type]
        opportunities=world["opportunities"],  # type: ignore[arg-type]
    )


def _approve_handler(
    world: dict[str, object],
    *,
    configuration: OperatorTradingConfiguration | None = None,
    policy: OpportunityEnginePolicy | None = None,
) -> ApproveOpportunityHandler:
    return ApproveOpportunityHandler(
        configuration=configuration or _configuration(),
        policy=policy or _policy(),
        broker=world["broker"],  # type: ignore[arg-type]
        market_data=world["market_data"],  # type: ignore[arg-type]
        bars=world["bars"],  # type: ignore[arg-type]
        opportunities=world["opportunities"],  # type: ignore[arg-type]
        decisions=world["decisions"],  # type: ignore[arg-type]
    )


def test_review_of_an_unchanged_opportunity_returns_it_unchanged() -> None:
    world = _world()
    (opportunity,) = _generate(world)
    reviewed = _review_handler(world).handle(
        opportunity.opportunity_id, at=_NOW + timedelta(seconds=5)
    )
    assert reviewed == opportunity


def test_review_invalidates_when_the_pattern_no_longer_holds() -> None:
    world = _world()
    (opportunity,) = _generate(world)
    # The market moved: the quote's own market data now shows a lower price (structure would
    # no longer confirm a breakout against the SAME stale bars -- simplest deterioration to
    # simulate is to make the quote itself go stale.
    market_data: FakeOpportunityMarketData = world["market_data"]  # type: ignore[assignment]
    market_data.quotes[_SYMBOL] = FakeQuoteView(
        symbol=_SYMBOL,
        bid="101.45",
        ask="101.50",
        captured_at=_NOW - timedelta(seconds=500),
    )
    with pytest.raises(OpportunityEngineRefusedError, match="INVALIDATED"):
        _review_handler(world).handle(opportunity.opportunity_id, at=_NOW + timedelta(seconds=5))
    stored = world["opportunities"].get(opportunity.opportunity_id)  # type: ignore[attr-defined]
    assert stored.status is OpportunityStatus.INVALIDATED


def test_review_invalidates_when_the_entry_moved_outside_tolerance() -> None:
    world = _world()
    policy = _policy(entry_tolerance_percent=Decimal("0.1"))
    (opportunity,) = _generate(world, policy=policy)
    market_data: FakeOpportunityMarketData = world["market_data"]  # type: ignore[assignment]
    # Price rallies well past the reviewed entry -- still a valid breakout, but a DIFFERENT
    # price than the Owner was shown.
    market_data.quotes[_SYMBOL] = FakeQuoteView(
        symbol=_SYMBOL,
        bid="105.00",
        ask="105.05",
        captured_at=_NOW + timedelta(seconds=1),
    )
    with pytest.raises(OpportunityEngineRefusedError, match="INVALIDATED"):
        _review_handler(world, policy=policy).handle(
            opportunity.opportunity_id, at=_NOW + timedelta(seconds=5)
        )


def test_review_refuses_an_expired_opportunity() -> None:
    world = _world()
    policy = _policy(opportunity_validity_seconds=10)
    (opportunity,) = _generate(world, policy=policy)
    with pytest.raises(OpportunityEngineRefusedError, match="expired"):
        _review_handler(world, policy=policy).handle(
            opportunity.opportunity_id, at=_NOW + timedelta(minutes=5)
        )
    stored = world["opportunities"].get(opportunity.opportunity_id)  # type: ignore[attr-defined]
    assert stored.status is OpportunityStatus.EXPIRED


def test_approve_records_a_durable_decision_and_transitions_to_owner_approved() -> None:
    world = _world()
    (opportunity,) = _generate(world)
    approved = _approve_handler(world).handle(
        ApproveOpportunityCommand(
            opportunity_id=opportunity.opportunity_id,
            decision_id="DEC-1",
            approved_by="owner",
            at=_NOW + timedelta(seconds=5),
        )
    )
    assert approved.status is OpportunityStatus.OWNER_APPROVED
    decision = world["decisions"].for_opportunity(opportunity.opportunity_id)  # type: ignore[attr-defined]
    assert decision is not None and decision.action.value == "APPROVE"


def test_approve_refuses_a_second_decision_on_the_same_opportunity() -> None:
    world = _world()
    (opportunity,) = _generate(world)
    handler = _approve_handler(world)
    handler.handle(
        ApproveOpportunityCommand(
            opportunity_id=opportunity.opportunity_id,
            decision_id="DEC-1",
            approved_by="owner",
            at=_NOW + timedelta(seconds=5),
        )
    )
    with pytest.raises(OpportunityEngineRefusedError, match="already has a recorded decision"):
        handler.handle(
            ApproveOpportunityCommand(
                opportunity_id=opportunity.opportunity_id,
                decision_id="DEC-2",
                approved_by="owner",
                at=_NOW + timedelta(seconds=10),
            )
        )


def test_approve_refuses_when_invalidated_by_re_verification() -> None:
    world = _world()
    (opportunity,) = _generate(world)
    market_data: FakeOpportunityMarketData = world["market_data"]  # type: ignore[assignment]
    market_data.quotes[_SYMBOL] = FakeQuoteView(
        symbol=_SYMBOL,
        bid="101.45",
        ask="101.50",
        captured_at=_NOW - timedelta(seconds=500),
    )
    with pytest.raises(OpportunityEngineRefusedError, match="INVALIDATED"):
        _approve_handler(world).handle(
            ApproveOpportunityCommand(
                opportunity_id=opportunity.opportunity_id,
                decision_id="DEC-1",
                approved_by="owner",
                at=_NOW + timedelta(seconds=5),
            )
        )
    assert world["decisions"].for_opportunity(opportunity.opportunity_id) is None  # type: ignore[attr-defined]


def test_ignore_records_a_decision_and_transitions_to_owner_ignored() -> None:
    world = _world()
    (opportunity,) = _generate(world)
    handler = IgnoreOpportunityHandler(
        opportunities=world["opportunities"],
        decisions=world["decisions"],  # type: ignore[arg-type]
    )
    ignored = handler.handle(
        IgnoreOpportunityCommand(
            opportunity_id=opportunity.opportunity_id,
            decision_id="DEC-1",
            ignored_by="owner",
            at=_NOW + timedelta(seconds=5),
        )
    )
    assert ignored.status is OpportunityStatus.OWNER_IGNORED


def test_ignore_refuses_a_candidate_that_never_became_actionable() -> None:
    clock = FakeClockView(is_open=False, timestamp=_NOW)
    world = _world(clock=clock, quote_captured_at=clock.timestamp - timedelta(seconds=5))
    (opportunity,) = _generate(world)
    assert opportunity.status is OpportunityStatus.CANDIDATE
    handler = IgnoreOpportunityHandler(
        opportunities=world["opportunities"],
        decisions=world["decisions"],  # type: ignore[arg-type]
    )
    with pytest.raises(OpportunityEngineRefusedError, match="not\nACTIONABLE|not ACTIONABLE"):
        handler.handle(
            IgnoreOpportunityCommand(
                opportunity_id=opportunity.opportunity_id,
                decision_id="DEC-1",
                ignored_by="owner",
                at=_NOW + timedelta(seconds=5),
            )
        )


# ---------------------------------------------------------------------------
# I. Environment / broker-write safety
# ---------------------------------------------------------------------------


def test_generation_never_calls_submit_order_or_cancel_order() -> None:
    """The fakes raise AssertionError if either is ever reached -- proving zero broker writes."""
    world = _world()
    _generate(world)  # would raise AssertionError from the fake if a write were attempted
    handler = _approve_handler(world)
    (opportunity,) = world["opportunities"].rows.values()  # type: ignore[attr-defined]
    handler.handle(
        ApproveOpportunityCommand(
            opportunity_id=opportunity.opportunity_id,
            decision_id="DEC-1",
            approved_by="owner",
            at=_NOW + timedelta(seconds=5),
        )
    )
    # Reaching here without AssertionError from FakeOpportunityBroker.submit_order/cancel_order
    # is the proof: BUY writes = 0, SELL writes = 0, cancels = 0.
