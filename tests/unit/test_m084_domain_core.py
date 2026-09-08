"""MILESTONE-084 -- unit tests for the decision-to-approval domain core.

These tests are written to fail if a safety rule is weakened. Where a rule says
"refuse", the test asserts the refusal rather than asserting the happy path and
trusting the refusal to still be there.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, time, timedelta
from decimal import Decimal

import pytest

from empirical_platform.decision_candidate.evaluation_context import (
    EvaluationContext,
    build_evaluation_context,
    recompute_consumed_receipt_digest,
)
from empirical_platform.decision_candidate.evaluation_evidence_watermark import (
    EvaluationEvidenceWatermark,
)
from empirical_platform.decision_candidate.operator_trading_configuration import (
    AccountMode,
    KillSwitchState,
    LimitPricePolicy,
    OperatorTradingConfiguration,
    OrderType,
    TradingSession,
)
from empirical_platform.decision_candidate.product_market_inputs import (
    AccountSnapshot,
    DataFeedKind,
    InstrumentMetadata,
    LiquiditySnapshot,
    MarketStatus,
    OpenOrderSnapshot,
    PositionSnapshot,
    QuoteSnapshot,
    SessionSnapshot,
    TradingCostEstimate,
)
from empirical_platform.decision_candidate.trade_approval import (
    ALLOWED_TRANSITIONS,
    ApprovalDecision,
    ApprovedOrderIntent,
    OperatorAction,
    SubmissionState,
    build_approved_order_intent,
    is_transition_allowed,
    record_operator_decision,
)
from empirical_platform.decision_candidate.trade_proposal import (
    NoTradeReason,
    ProposalStatus,
    RiskCheckOutcome,
    TradeProposal,
    TradeProposalOutcome,
    compute_fingerprint,
    evaluate_trade_proposal,
)

# 2026-06-10 12:00Z is 15:00 in Europe/Helsinki: inside the entry window below,
# and before the 15:45 liquidation deadline. Every temporal test is anchored to
# this instant so that none of them depends on when the suite is run.
EVALUATED_AT = datetime(2026, 6, 10, 12, 0, tzinfo=UTC)


def a_configuration(**overrides: object) -> OperatorTradingConfiguration:
    defaults: dict[str, object] = {
        "configuration_governance_id": "CFG-084-0001",
        "configuration_version": 1,
        "base_currency": "USD",
        "permitted_markets": ("XNAS",),
        "watchlist": ("AAPL", "MSFT"),
        "prohibited_instruments": ("PENNY",),
        "maximum_deployable_capital": Decimal("10000"),
        "maximum_capital_per_trade": Decimal("2000"),
        "maximum_percent_per_trade": Decimal("20"),
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
        "operator_timezone": "Europe/Helsinki",
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


def a_quote(**overrides: object) -> QuoteSnapshot:
    defaults: dict[str, object] = {
        "quote_id": "QTE-0001",
        "provider_id": "PROVIDER-A",
        "symbol": "AAPL",
        "bid": Decimal("199.95"),
        "ask": Decimal("200.10"),
        "last_trade": Decimal("200.00"),
        "observed_at": EVALUATED_AT - timedelta(seconds=5),
        "feed_kind": DataFeedKind.REAL_TIME,
    }
    defaults.update(overrides)
    return QuoteSnapshot(**defaults)  # type: ignore[arg-type]


def an_account(**overrides: object) -> AccountSnapshot:
    defaults: dict[str, object] = {
        "account_snapshot_id": "ACC-0001",
        "provider_id": "PROVIDER-A",
        "account_reference": "PREP-ACCOUNT-1",
        "base_currency": "USD",
        "cash_available": Decimal("5000"),
        "equity_total": Decimal("10000"),
        "realized_pnl_today": Decimal("0"),
        "orders_submitted_today": 0,
        "observed_at": EVALUATED_AT - timedelta(seconds=5),
    }
    defaults.update(overrides)
    return AccountSnapshot(**defaults)  # type: ignore[arg-type]


def a_session(**overrides: object) -> SessionSnapshot:
    defaults: dict[str, object] = {
        "session_id": "SES-0001",
        "provider_id": "PROVIDER-A",
        "market": "XNAS",
        "status": MarketStatus.OPEN,
        "observed_at": EVALUATED_AT - timedelta(seconds=5),
    }
    defaults.update(overrides)
    return SessionSnapshot(**defaults)  # type: ignore[arg-type]


def an_instrument(**overrides: object) -> InstrumentMetadata:
    defaults: dict[str, object] = {
        "symbol": "AAPL",
        "market": "XNAS",
        "currency": "USD",
        "is_fractionable": False,
        "lot_size": 1,
    }
    defaults.update(overrides)
    return InstrumentMetadata(**defaults)  # type: ignore[arg-type]


def a_liquidity(**overrides: object) -> LiquiditySnapshot:
    defaults: dict[str, object] = {
        "symbol": "AAPL",
        "average_daily_volume_shares": 50_000_000,
        "observed_at": EVALUATED_AT - timedelta(seconds=5),
    }
    defaults.update(overrides)
    return LiquiditySnapshot(**defaults)  # type: ignore[arg-type]


def a_cost_estimate(**overrides: object) -> TradingCostEstimate:
    defaults: dict[str, object] = {
        "estimate_id": "CST-0001",
        "provider_id": "PROVIDER-A",
        "symbol": "AAPL",
        "commission": Decimal("1.00"),
        "estimated_slippage_percent": Decimal("0.1"),
        "observed_at": EVALUATED_AT - timedelta(seconds=5),
    }
    defaults.update(overrides)
    return TradingCostEstimate(**defaults)  # type: ignore[arg-type]


def evaluate(**overrides: object) -> TradeProposalOutcome:
    defaults: dict[str, object] = {
        "configuration": a_configuration(),
        "evaluation_context_id": "ECX-0001",
        "proposal_governance_id": "PRP-0001",
        "evaluated_at": EVALUATED_AT,
        "symbol": "AAPL",
        "quote": a_quote(),
        "account": an_account(),
        "session": a_session(),
        "instrument": an_instrument(),
        "liquidity": a_liquidity(),
        "cost_estimate": a_cost_estimate(),
        "positions": (),
        "open_orders": (),
        "evidence_age_seconds": Decimal("60"),
    }
    defaults.update(overrides)
    return evaluate_trade_proposal(**defaults)  # type: ignore[arg-type]


def evaluate_for(symbol: str, **overrides: object) -> TradeProposalOutcome:
    """Evaluate a symbol with every snapshot describing that same symbol.

    The engine refuses a snapshot set that describes a different instrument than
    the one requested, so a symbol-driven test must move all of them together.
    """
    defaults: dict[str, object] = {
        "symbol": symbol,
        "quote": a_quote(symbol=symbol),
        "instrument": an_instrument(symbol=symbol),
        "liquidity": a_liquidity(symbol=symbol),
        "cost_estimate": a_cost_estimate(symbol=symbol),
    }
    defaults.update(overrides)
    return evaluate(**defaults)


def evaluate_at(instant: datetime, **overrides: object) -> TradeProposalOutcome:
    """Evaluate at a different instant, with every observation moved with it.

    Snapshots keep their five-second age; leaving them behind would make an
    observation dated after the evaluation instant, which the inputs refuse.
    """
    observed_at = instant - timedelta(seconds=5)
    defaults: dict[str, object] = {
        "evaluated_at": instant,
        "quote": a_quote(observed_at=observed_at),
        "account": an_account(observed_at=observed_at),
        "session": a_session(observed_at=observed_at),
        "liquidity": a_liquidity(observed_at=observed_at),
        "cost_estimate": a_cost_estimate(observed_at=observed_at),
    }
    defaults.update(overrides)
    return evaluate(**defaults)


def a_proposal(**overrides: object) -> TradeProposal:
    outcome = evaluate(**overrides)
    assert outcome.proposal is not None, f"expected a proposal, got {outcome.no_trade_reason}"
    return outcome.proposal


def a_variant(proposal: TradeProposal, **changes: object) -> TradeProposal:
    """A proposal object with altered terms and no re-validation.

    `dataclasses.replace` cannot express this: `__post_init__` refuses any
    proposal whose digest does not match its terms, which is exactly the state
    these tests need in order to check that the digest notices the difference.
    """
    variant = TradeProposal.__new__(TradeProposal)
    for field_name in TradeProposal.__slots__:
        object.__setattr__(variant, field_name, getattr(proposal, field_name))
    for field_name, value in changes.items():
        object.__setattr__(variant, field_name, value)
    return variant


def a_watermark(count: int = 3) -> EvaluationEvidenceWatermark:
    return EvaluationEvidenceWatermark(
        watermark_governance_id="WM-0001",
        receipt_governance_ids=tuple(f"RCPT-{index:04d}" for index in range(count)),
    )


# =====================================================================
# OperatorTradingConfiguration -- the four hard product invariants
# =====================================================================


class TestConfigurationHardInvariants:
    """Long-only, intraday-only, unleveraged, preparation-mode are not dials."""

    def test_leverage_above_one_is_refused(self) -> None:
        with pytest.raises(ValueError, match="maximum_leverage must be exactly 1"):
            a_configuration(maximum_leverage=Decimal("1.5"))

    def test_leverage_below_one_is_refused_as_well(self) -> None:
        # Not merely "no more than 1": the value must be exactly 1, so that a
        # configuration cannot quietly express a different capital model at all.
        with pytest.raises(ValueError, match="maximum_leverage must be exactly 1"):
            a_configuration(maximum_leverage=Decimal("0.5"))

    def test_short_selling_cannot_be_permitted(self) -> None:
        with pytest.raises(ValueError, match="long-only"):
            a_configuration(short_selling_permitted=True)

    def test_overnight_positions_cannot_be_permitted(self) -> None:
        with pytest.raises(ValueError, match="intraday-only"):
            a_configuration(overnight_positions_permitted=True)

    @pytest.mark.parametrize("mode", [AccountMode.PAPER, AccountMode.LIVE])
    def test_only_preparation_mode_is_accepted(self, mode: AccountMode) -> None:
        with pytest.raises(ValueError, match="account_mode must be PREPARATION"):
            a_configuration(account_mode=mode)

    def test_preparation_mode_is_accepted(self) -> None:
        assert a_configuration().account_mode is AccountMode.PREPARATION


class TestConfigurationOrderingInvariants:
    def test_an_approval_may_not_outlive_the_proposal_it_authorizes(self) -> None:
        with pytest.raises(ValueError, match="approval_expiry_seconds must not exceed"):
            a_configuration(proposal_expiry_seconds=60, approval_expiry_seconds=61)

    def test_an_equal_approval_and_proposal_expiry_is_accepted(self) -> None:
        configuration = a_configuration(proposal_expiry_seconds=60, approval_expiry_seconds=60)
        assert configuration.approval_expiry_seconds == 60

    def test_liquidation_at_or_before_the_last_entry_is_an_overnight_position(self) -> None:
        with pytest.raises(ValueError, match="mandatory_liquidation_time must follow"):
            a_configuration(latest_entry_time=time(15, 30), mandatory_liquidation_time=time(15, 30))

    def test_the_entry_window_must_be_ordered(self) -> None:
        with pytest.raises(ValueError, match="earliest_entry_time must precede"):
            a_configuration(earliest_entry_time=time(15, 0), latest_entry_time=time(10, 0))

    def test_entry_times_must_be_naive_local_times(self) -> None:
        with pytest.raises(ValueError, match="must be a naive local time"):
            a_configuration(earliest_entry_time=time(10, 0, tzinfo=UTC))


class TestConfigurationUniverseInvariants:
    def test_an_instrument_may_not_be_both_watchlisted_and_prohibited(self) -> None:
        with pytest.raises(ValueError, match="both watchlisted and prohibited"):
            a_configuration(watchlist=("AAPL",), prohibited_instruments=("AAPL",))

    def test_an_unknown_timezone_is_refused(self) -> None:
        with pytest.raises(ValueError, match="must be a known IANA zone"):
            a_configuration(operator_timezone="Mars/Olympus_Mons")

    def test_the_watchlist_must_be_in_canonical_order(self) -> None:
        with pytest.raises(ValueError, match="canonical ascending order"):
            a_configuration(watchlist=("MSFT", "AAPL"))

    def test_a_lower_case_symbol_is_refused_rather_than_normalised(self) -> None:
        # Silent normalisation would make two different configurations compare
        # equal on the wire while reading differently in the operator's file.
        with pytest.raises(ValueError, match="upper-case and unpadded"):
            a_configuration(watchlist=("aapl",))

    @pytest.mark.parametrize("session", [TradingSession.PRE_MARKET, TradingSession.POST_MARKET])
    def test_only_the_regular_session_is_permitted(self, session: TradingSession) -> None:
        with pytest.raises(ValueError, match="only the REGULAR session"):
            a_configuration(permitted_session=session)

    def test_the_kill_switch_governs_the_trading_permission_property(self) -> None:
        assert a_configuration().is_trading_permitted is True
        assert a_configuration(kill_switch=KillSwitchState.ENGAGED).is_trading_permitted is False


# =====================================================================
# Market input snapshots
# =====================================================================


class TestMarketInputSnapshots:
    def test_an_observation_from_the_future_is_refused_rather_than_aged_negatively(self) -> None:
        quote = a_quote(observed_at=EVALUATED_AT + timedelta(seconds=1))
        with pytest.raises(ValueError, match="observed after"):
            quote.age_seconds(EVALUATED_AT)

    def test_quote_age_is_measured_against_the_supplied_instant(self) -> None:
        assert a_quote().age_seconds(EVALUATED_AT) == Decimal("5")

    def test_a_crossed_quote_is_refused(self) -> None:
        with pytest.raises(ValueError):
            a_quote(bid=Decimal("201.00"), ask=Decimal("200.00"))

    def test_spread_percent_is_computed_from_the_mid(self) -> None:
        quote = a_quote(bid=Decimal("99.00"), ask=Decimal("101.00"))
        assert quote.mid == Decimal("100.00")
        assert quote.spread == Decimal("2.00")
        assert quote.spread_percent == Decimal("2")

    @pytest.mark.parametrize(
        "status",
        [MarketStatus.CLOSED, MarketStatus.HALTED, MarketStatus.EARLY_CLOSE, MarketStatus.UNKNOWN],
    )
    def test_only_an_open_market_is_tradeable(self, status: MarketStatus) -> None:
        # EARLY_CLOSE is deliberately not tradeable: this milestone has no model
        # of a shortened session's liquidation deadline.
        assert a_session(status=status).is_tradeable is False

    def test_an_open_market_is_tradeable(self) -> None:
        assert a_session().is_tradeable is True


# =====================================================================
# The proposal engine -- happy path and derivation
# =====================================================================


class TestProposalHappyPath:
    def test_a_complete_and_clean_input_set_produces_one_proposal(self) -> None:
        outcome = evaluate()
        assert outcome.no_trade_reason is None
        assert outcome.proposal is not None
        assert outcome.proposal.status is ProposalStatus.PREPARED

    def test_the_quantity_is_derived_from_the_budget_and_not_supplied(self) -> None:
        # budget = min(2000 per-trade cap, 20% of 10000) = 2000, against a 200.10
        # ask: floor(2000 / 200.10) = 9.
        assert a_proposal().quantity == 9

    def test_the_derived_money_terms_are_exact(self) -> None:
        proposal = a_proposal()
        assert proposal.estimated_notional == Decimal("1800.90")
        assert proposal.estimated_fees == Decimal("1.00")
        assert proposal.estimated_slippage_amount == Decimal("1.80")
        assert proposal.estimated_total_cash_required == Decimal("1803.70")

    def test_the_exit_prices_bracket_the_entry_price(self) -> None:
        proposal = a_proposal()
        assert proposal.stop_loss_price == Decimal("196.10")
        assert proposal.profit_exit_price == Decimal("208.10")
        assert proposal.stop_loss_price < proposal.limit_price  # type: ignore[operator]
        assert proposal.profit_exit_price > proposal.limit_price  # type: ignore[operator]

    def test_the_lot_size_floors_the_quantity(self) -> None:
        proposal = a_proposal(instrument=an_instrument(lot_size=5))
        assert proposal.quantity == 5  # floor(9 / 5) * 5

    def test_the_limit_price_follows_the_configured_policy(self) -> None:
        ask = a_proposal().limit_price
        mid = a_proposal(
            configuration=a_configuration(limit_price_policy=LimitPricePolicy.MID_QUOTE)
        ).limit_price
        last = a_proposal(
            configuration=a_configuration(limit_price_policy=LimitPricePolicy.LAST_TRADE)
        ).limit_price
        assert (ask, mid, last) == (Decimal("200.10"), Decimal("200.02"), Decimal("200.00"))

    def test_a_market_proposal_carries_no_limit_price(self) -> None:
        proposal = a_proposal(
            configuration=a_configuration(
                default_order_type=OrderType.MARKET,
                permitted_order_types=(OrderType.MARKET,),
            )
        )
        assert proposal.order_type is OrderType.MARKET
        assert proposal.limit_price is None

    def test_the_engine_is_deterministic(self) -> None:
        first, second = a_proposal(), a_proposal()
        assert first == second
        assert first.content_fingerprint == second.content_fingerprint

    def test_every_recorded_check_passed_when_a_proposal_is_produced(self) -> None:
        outcome = evaluate()
        assert outcome.risk_checks
        assert all(check.outcome is RiskCheckOutcome.PASSED for check in outcome.risk_checks)

    def test_the_expiry_follows_the_configured_proposal_lifetime(self) -> None:
        proposal = a_proposal()
        assert proposal.expires_at == proposal.created_at + timedelta(seconds=300)


class TestProposalFingerprint:
    def test_a_proposal_carries_the_digest_of_its_own_terms(self) -> None:
        proposal = a_proposal()
        assert proposal.content_fingerprint == compute_fingerprint(proposal)

    @pytest.mark.parametrize(
        ("field", "value"),
        [
            ("symbol", "MSFT"),
            ("quantity", 8),
            ("limit_price", Decimal("200.11")),
            ("order_type", OrderType.MARKET),
            ("proposal_version", 2),
            ("expires_at", EVALUATED_AT + timedelta(seconds=600)),
            ("estimated_total_cash_required", Decimal("1803.71")),
            ("stop_loss_price", Decimal("196.11")),
            ("profit_exit_price", Decimal("208.11")),
            ("mandatory_liquidation_at", EVALUATED_AT + timedelta(hours=2)),
        ],
    )
    def test_changing_any_authorized_term_changes_the_digest(
        self, field: str, value: object
    ) -> None:
        proposal = a_proposal()
        assert compute_fingerprint(a_variant(proposal, **{field: value})) != (
            proposal.content_fingerprint
        )

    @pytest.mark.parametrize(
        ("field", "value"),
        [("status", ProposalStatus.APPROVED), ("created_at", EVALUATED_AT + timedelta(seconds=1))],
    )
    def test_the_digest_ignores_terms_an_approval_does_not_authorize(
        self, field: str, value: object
    ) -> None:
        # A PREPARED proposal and the same proposal APPROVED are the same order.
        proposal = a_proposal()
        altered = replace(proposal, **{field: value})
        assert compute_fingerprint(altered) == proposal.content_fingerprint

    def test_a_proposal_whose_digest_does_not_match_its_terms_is_refused(self) -> None:
        proposal = a_proposal()
        with pytest.raises(ValueError):
            replace(proposal, content_fingerprint="a" * 64)


class TestProposalConstructionInvariants:
    def test_a_sell_proposal_cannot_be_constructed(self) -> None:
        variant = a_variant(a_proposal(), side="SELL")
        with pytest.raises(ValueError, match="side must be BUY"):
            replace(variant, content_fingerprint=compute_fingerprint(variant))

    def test_a_zero_quantity_proposal_cannot_be_constructed(self) -> None:
        variant = a_variant(a_proposal(), quantity=0)
        with pytest.raises(ValueError):
            replace(variant, content_fingerprint=compute_fingerprint(variant))


# =====================================================================
# The proposal engine -- every NO_TRADE reason it can reach
# =====================================================================


class TestNoTradeReasons:
    """Each case drives exactly one rule and asserts the reason it produces."""

    def test_an_engaged_kill_switch_stops_everything(self) -> None:
        outcome = evaluate(configuration=a_configuration(kill_switch=KillSwitchState.ENGAGED))
        assert outcome.proposal is None
        assert outcome.no_trade_reason is NoTradeReason.KILL_SWITCH_ENGAGED

    def test_an_engaged_kill_switch_wins_over_every_other_reason(self) -> None:
        # Several rules fail at once; the kill switch is the reason reported.
        outcome = evaluate_for(
            "TSLA",
            configuration=a_configuration(kill_switch=KillSwitchState.ENGAGED),
            session=a_session(status=MarketStatus.CLOSED),
            cost_estimate=None,
        )
        assert outcome.no_trade_reason is NoTradeReason.KILL_SWITCH_ENGAGED

    @pytest.mark.parametrize(
        ("status", "reason"),
        [
            (MarketStatus.CLOSED, NoTradeReason.MARKET_NOT_OPEN),
            (MarketStatus.HALTED, NoTradeReason.MARKET_NOT_OPEN),
            (MarketStatus.EARLY_CLOSE, NoTradeReason.MARKET_NOT_OPEN),
            (MarketStatus.UNKNOWN, NoTradeReason.MARKET_STATUS_UNKNOWN),
        ],
    )
    def test_a_market_that_is_not_open_produces_no_trade(
        self, status: MarketStatus, reason: NoTradeReason
    ) -> None:
        outcome = evaluate(session=a_session(status=status))
        assert outcome.no_trade_reason is reason

    def test_an_unknown_market_status_is_never_treated_as_open(self) -> None:
        outcome = evaluate(session=a_session(status=MarketStatus.UNKNOWN))
        unknown = [
            check for check in outcome.risk_checks if check.outcome is RiskCheckOutcome.UNKNOWN
        ]
        assert unknown, "an unevaluable check must be recorded as UNKNOWN, not silently passed"
        assert outcome.proposal is None

    def test_an_evaluation_before_the_entry_window_produces_no_trade(self) -> None:
        # 06:00Z is 09:00 in Helsinki, before the 10:00 earliest entry.
        outcome = evaluate_at(EVALUATED_AT.replace(hour=6))
        assert outcome.no_trade_reason is NoTradeReason.OUTSIDE_ENTRY_WINDOW

    def test_an_evaluation_after_the_entry_window_produces_no_trade(self) -> None:
        # 13:00Z is 16:00 in Helsinki, after the 15:30 latest entry.
        outcome = evaluate_at(EVALUATED_AT.replace(hour=13))
        assert outcome.no_trade_reason is NoTradeReason.OUTSIDE_ENTRY_WINDOW

    def test_a_proposal_that_would_outlive_the_liquidation_deadline_is_refused(self) -> None:
        # 12:29Z is 15:29 in Helsinki: inside the entry window, but a 300-second
        # proposal would still be approvable at 15:34, four minutes after the
        # 15:31 mandatory liquidation.
        outcome = evaluate_at(
            EVALUATED_AT.replace(hour=12, minute=29),
            configuration=a_configuration(
                earliest_entry_time=time(10, 0),
                latest_entry_time=time(15, 30),
                mandatory_liquidation_time=time(15, 31),
            ),
        )
        assert outcome.no_trade_reason is NoTradeReason.LIQUIDATION_DEADLINE_UNREACHABLE

    def test_a_proposal_that_expires_before_the_deadline_is_allowed(self) -> None:
        outcome = evaluate_at(
            EVALUATED_AT.replace(hour=12, minute=25),
            configuration=a_configuration(
                earliest_entry_time=time(10, 0),
                latest_entry_time=time(15, 30),
                mandatory_liquidation_time=time(15, 31),
            ),
        )
        assert outcome.proposal is not None

    def test_a_stale_quote_produces_no_trade(self) -> None:
        outcome = evaluate(quote=a_quote(observed_at=EVALUATED_AT - timedelta(seconds=61)))
        assert outcome.no_trade_reason is NoTradeReason.MARKET_DATA_STALE

    @pytest.mark.parametrize("feed", [DataFeedKind.DELAYED, DataFeedKind.FIXTURE])
    def test_a_feed_that_is_not_real_time_produces_no_trade(self, feed: DataFeedKind) -> None:
        outcome = evaluate(quote=a_quote(feed_kind=feed))
        assert outcome.no_trade_reason is NoTradeReason.MARKET_DATA_NOT_REAL_TIME

    def test_stale_evidence_produces_no_trade(self) -> None:
        outcome = evaluate(evidence_age_seconds=Decimal("86401"))
        assert outcome.no_trade_reason is NoTradeReason.EVIDENCE_STALE

    def test_a_missing_cost_estimate_produces_no_trade_rather_than_a_zero_cost(self) -> None:
        outcome = evaluate(cost_estimate=None)
        assert outcome.no_trade_reason is NoTradeReason.COST_ESTIMATE_MISSING

    def test_a_prohibited_instrument_produces_no_trade(self) -> None:
        # PENNY is on the prohibited list and, necessarily, off the watchlist:
        # the two lists may not overlap. Prohibition is the stronger statement,
        # so it is the reason reported.
        outcome = evaluate_for("PENNY")
        assert outcome.no_trade_reason is NoTradeReason.INSTRUMENT_PROHIBITED

    def test_an_instrument_off_the_watchlist_produces_no_trade(self) -> None:
        outcome = evaluate_for("TSLA")
        assert outcome.no_trade_reason is NoTradeReason.INSTRUMENT_NOT_WATCHLISTED

    def test_an_unpermitted_market_produces_no_trade(self) -> None:
        outcome = evaluate(instrument=an_instrument(market="XHEL"))
        assert outcome.no_trade_reason is NoTradeReason.MARKET_NOT_PERMITTED

    def test_a_currency_mismatch_produces_no_trade(self) -> None:
        outcome = evaluate(instrument=an_instrument(currency="EUR"))
        assert outcome.no_trade_reason is NoTradeReason.CURRENCY_MISMATCH

    def test_a_price_below_the_minimum_produces_no_trade(self) -> None:
        outcome = evaluate(
            quote=a_quote(bid=Decimal("1.00"), ask=Decimal("1.01"), last_trade=Decimal("1.00"))
        )
        assert outcome.no_trade_reason is NoTradeReason.PRICE_OUTSIDE_BOUNDS

    def test_a_price_above_the_maximum_produces_no_trade(self) -> None:
        outcome = evaluate(
            quote=a_quote(
                bid=Decimal("1999.00"), ask=Decimal("1999.10"), last_trade=Decimal("1999.00")
            )
        )
        assert outcome.no_trade_reason is NoTradeReason.PRICE_OUTSIDE_BOUNDS

    def test_a_wide_spread_produces_no_trade(self) -> None:
        outcome = evaluate(
            quote=a_quote(bid=Decimal("190.00"), ask=Decimal("210.00"), last_trade=Decimal("200"))
        )
        assert outcome.no_trade_reason is NoTradeReason.SPREAD_TOO_WIDE

    def test_thin_liquidity_produces_no_trade(self) -> None:
        outcome = evaluate(liquidity=a_liquidity(average_daily_volume_shares=1_000))
        assert outcome.no_trade_reason is NoTradeReason.LIQUIDITY_INSUFFICIENT

    def test_excessive_estimated_slippage_produces_no_trade(self) -> None:
        outcome = evaluate(cost_estimate=a_cost_estimate(estimated_slippage_percent=Decimal("5")))
        assert outcome.no_trade_reason is NoTradeReason.SLIPPAGE_TOO_HIGH

    def test_an_existing_position_in_the_same_symbol_produces_no_trade(self) -> None:
        outcome = evaluate(
            positions=(PositionSnapshot(symbol="AAPL", quantity=1, average_price=Decimal("190")),)
        )
        assert outcome.no_trade_reason is NoTradeReason.EXISTING_POSITION_CONFLICT

    def test_a_working_order_in_the_same_symbol_produces_no_trade(self) -> None:
        outcome = evaluate(
            open_orders=(
                OpenOrderSnapshot(order_reference="O-1", symbol="AAPL", side="BUY", quantity=1),
            )
        )
        assert outcome.no_trade_reason is NoTradeReason.OPEN_ORDER_CONFLICT

    def test_the_position_count_limit_produces_no_trade(self) -> None:
        outcome = evaluate(
            configuration=a_configuration(maximum_simultaneous_positions=1),
            positions=(PositionSnapshot(symbol="MSFT", quantity=1, average_price=Decimal("400")),),
        )
        assert outcome.no_trade_reason is NoTradeReason.POSITION_LIMIT_REACHED

    def test_the_daily_loss_limit_produces_no_trade(self) -> None:
        outcome = evaluate(account=an_account(realized_pnl_today=Decimal("-500")))
        assert outcome.no_trade_reason is NoTradeReason.DAILY_LOSS_LIMIT_REACHED

    def test_a_profitable_day_does_not_trip_the_loss_limit(self) -> None:
        outcome = evaluate(account=an_account(realized_pnl_today=Decimal("500")))
        assert outcome.proposal is not None

    def test_the_daily_order_count_limit_produces_no_trade(self) -> None:
        outcome = evaluate(account=an_account(orders_submitted_today=10))
        assert outcome.no_trade_reason is NoTradeReason.DAILY_ORDER_LIMIT_REACHED

    def test_cash_at_or_below_the_reserve_produces_no_trade(self) -> None:
        outcome = evaluate(account=an_account(cash_available=Decimal("1000")))
        assert outcome.no_trade_reason is NoTradeReason.CASH_RESERVE_BREACHED

    def test_a_budget_too_small_for_one_share_produces_no_trade(self) -> None:
        outcome = evaluate(account=an_account(cash_available=Decimal("1100")))
        assert outcome.no_trade_reason is NoTradeReason.QUANTITY_ZERO_AFTER_SIZING

    def test_an_unpermitted_default_order_type_produces_no_trade(self) -> None:
        # The configuration refuses this pairing, so the rule is driven through
        # the one path that can still reach the engine: a permitted-set that no
        # longer contains the default after the object was built.
        configuration = a_configuration()
        object.__setattr__(configuration, "permitted_order_types", (OrderType.MARKET,))
        outcome = evaluate(configuration=configuration)
        assert outcome.no_trade_reason is NoTradeReason.ORDER_TYPE_NOT_PERMITTED

    def test_a_lot_size_larger_than_the_budget_produces_no_trade(self) -> None:
        outcome = evaluate(instrument=an_instrument(lot_size=100))
        assert outcome.no_trade_reason is NoTradeReason.QUANTITY_ZERO_AFTER_SIZING


class TestNoTradeReporting:
    def test_exactly_one_reason_is_reported_even_when_many_rules_fail(self) -> None:
        outcome = evaluate(
            session=a_session(status=MarketStatus.CLOSED),
            cost_estimate=None,
            liquidity=a_liquidity(average_daily_volume_shares=1),
        )
        assert outcome.proposal is None
        assert outcome.no_trade_reason is not None

    def test_the_reported_reason_is_stable_across_repeated_evaluations(self) -> None:
        reasons = {
            evaluate(
                session=a_session(status=MarketStatus.CLOSED),
                cost_estimate=None,
                liquidity=a_liquidity(average_daily_volume_shares=1),
            ).no_trade_reason
            for _ in range(25)
        }
        assert len(reasons) == 1, "reason selection must not depend on set iteration order"

    def test_an_outcome_cannot_carry_both_a_proposal_and_a_reason(self) -> None:
        proposal = a_proposal()
        with pytest.raises(ValueError, match="exactly one"):
            TradeProposalOutcome(
                proposal=proposal,
                no_trade_reason=NoTradeReason.MARKET_NOT_OPEN,
                risk_checks=(),
            )

    def test_an_outcome_cannot_carry_neither(self) -> None:
        with pytest.raises(ValueError, match="exactly one"):
            TradeProposalOutcome(proposal=None, no_trade_reason=None, risk_checks=())

    def test_the_checks_are_reported_on_the_no_trade_path_too(self) -> None:
        outcome = evaluate(session=a_session(status=MarketStatus.CLOSED))
        assert outcome.risk_checks, "a refusal must still say what was evaluated"


# =====================================================================
# Approval
# =====================================================================


class TestTransitionTable:
    def test_only_prepared_has_outgoing_transitions(self) -> None:
        for status, targets in ALLOWED_TRANSITIONS.items():
            if status is ProposalStatus.PREPARED:
                assert targets
            else:
                assert targets == frozenset(), f"{status.value} must be terminal"

    def test_every_status_appears_in_the_table(self) -> None:
        assert set(ALLOWED_TRANSITIONS) == set(ProposalStatus)

    def test_an_approved_proposal_cannot_transition_again(self) -> None:
        for target in ProposalStatus:
            assert is_transition_allowed(ProposalStatus.APPROVED, target) is False

    def test_the_table_cannot_be_mutated(self) -> None:
        with pytest.raises(TypeError):
            ALLOWED_TRANSITIONS[ProposalStatus.APPROVED] = frozenset({ProposalStatus.PREPARED})  # type: ignore[index]


class TestOperatorDecision:
    def test_an_approval_records_the_exact_proposal_fingerprint(self) -> None:
        proposal = a_proposal()
        decision = record_operator_decision(
            proposal=proposal,
            decision_governance_id="DEC-0001",
            action=OperatorAction.APPROVE,
            operator_identity="operator-1",
            decided_at=EVALUATED_AT + timedelta(seconds=30),
            approval_expiry_seconds=120,
        )
        assert decision.approved_fingerprint == proposal.content_fingerprint
        assert decision.resulting_status is ProposalStatus.APPROVED
        assert decision.expires_at == EVALUATED_AT + timedelta(seconds=150)

    @pytest.mark.parametrize(
        ("action", "status"),
        [
            (OperatorAction.REJECT, ProposalStatus.REJECTED),
            (OperatorAction.CANCEL, ProposalStatus.CANCELLED),
        ],
    )
    def test_a_refusal_produces_its_own_status_and_never_lapses(
        self, action: OperatorAction, status: ProposalStatus
    ) -> None:
        decision = record_operator_decision(
            proposal=a_proposal(),
            decision_governance_id="DEC-0002",
            action=action,
            operator_identity="operator-1",
            decided_at=EVALUATED_AT + timedelta(seconds=30),
            approval_expiry_seconds=120,
        )
        assert decision.resulting_status is status
        assert decision.expires_at is None

    def test_an_expired_proposal_cannot_be_approved(self) -> None:
        with pytest.raises(ValueError, match="expired before this decision"):
            record_operator_decision(
                proposal=a_proposal(),
                decision_governance_id="DEC-0003",
                action=OperatorAction.APPROVE,
                operator_identity="operator-1",
                decided_at=EVALUATED_AT + timedelta(seconds=301),
                approval_expiry_seconds=120,
            )

    def test_a_proposal_that_is_not_prepared_cannot_be_decided_on(self) -> None:
        approved = replace(a_proposal(), status=ProposalStatus.APPROVED)
        with pytest.raises(ValueError, match="not an allowed transition"):
            record_operator_decision(
                proposal=approved,
                decision_governance_id="DEC-0004",
                action=OperatorAction.APPROVE,
                operator_identity="operator-1",
                decided_at=EVALUATED_AT + timedelta(seconds=30),
                approval_expiry_seconds=120,
            )

    def test_an_approval_expiry_must_be_positive(self) -> None:
        with pytest.raises(ValueError, match="must be positive"):
            record_operator_decision(
                proposal=a_proposal(),
                decision_governance_id="DEC-0005",
                action=OperatorAction.APPROVE,
                operator_identity="operator-1",
                decided_at=EVALUATED_AT + timedelta(seconds=30),
                approval_expiry_seconds=0,
            )

    def test_a_naive_decision_instant_is_refused(self) -> None:
        with pytest.raises(ValueError, match="timezone-aware"):
            record_operator_decision(
                proposal=a_proposal(),
                decision_governance_id="DEC-0006",
                action=OperatorAction.APPROVE,
                operator_identity="operator-1",
                decided_at=datetime(2026, 6, 10, 12, 0),  # noqa: DTZ001 -- the point of the test
                approval_expiry_seconds=120,
            )

    def test_a_rejection_may_not_be_recorded_as_an_approval(self) -> None:
        with pytest.raises(ValueError, match="must produce"):
            ApprovalDecision(
                decision_governance_id="DEC-0007",
                proposal_governance_id="PRP-0001",
                proposal_version=1,
                approved_fingerprint="a" * 64,
                action=OperatorAction.REJECT,
                operator_identity="operator-1",
                decided_at=EVALUATED_AT,
                expires_at=None,
                resulting_status=ProposalStatus.APPROVED,
            )

    def test_an_approval_lapses_at_its_expiry(self) -> None:
        decision = record_operator_decision(
            proposal=a_proposal(),
            decision_governance_id="DEC-0008",
            action=OperatorAction.APPROVE,
            operator_identity="operator-1",
            decided_at=EVALUATED_AT,
            approval_expiry_seconds=120,
        )
        assert decision.is_expired_at(EVALUATED_AT + timedelta(seconds=119)) is False
        assert decision.is_expired_at(EVALUATED_AT + timedelta(seconds=120)) is True


# =====================================================================
# The approved order intent -- the hand-off that cannot submit anything
# =====================================================================


def an_approved_pair(
    **proposal_overrides: object,
) -> tuple[TradeProposal, ApprovalDecision]:
    prepared = a_proposal(**proposal_overrides)
    decision = record_operator_decision(
        proposal=prepared,
        decision_governance_id="DEC-INTENT",
        action=OperatorAction.APPROVE,
        operator_identity="operator-1",
        decided_at=EVALUATED_AT + timedelta(seconds=10),
        approval_expiry_seconds=120,
    )
    return replace(prepared, status=ProposalStatus.APPROVED), decision


class TestApprovedOrderIntent:
    def test_an_approved_proposal_yields_one_intent(self) -> None:
        proposal, decision = an_approved_pair()
        intent = build_approved_order_intent(
            intent_governance_id="INT-0001",
            proposal=proposal,
            decision=decision,
            created_at=EVALUATED_AT + timedelta(seconds=20),
            idempotency_key="IDEM-0001",
        )
        assert intent.quantity == proposal.quantity
        assert intent.approved_fingerprint == proposal.content_fingerprint

    def test_the_intent_is_never_submitted_and_has_no_way_to_become_submitted(self) -> None:
        proposal, decision = an_approved_pair()
        intent = build_approved_order_intent(
            intent_governance_id="INT-0002",
            proposal=proposal,
            decision=decision,
            created_at=EVALUATED_AT + timedelta(seconds=20),
            idempotency_key="IDEM-0002",
        )
        assert intent.submission_state is SubmissionState.NOT_SUBMITTED
        assert list(SubmissionState) == [SubmissionState.NOT_SUBMITTED], (
            "MILESTONE-084 must not declare a submitted state it cannot reach"
        )

    def test_the_intent_declares_preparation_and_day_only(self) -> None:
        proposal, decision = an_approved_pair()
        intent = build_approved_order_intent(
            intent_governance_id="INT-0003",
            proposal=proposal,
            decision=decision,
            created_at=EVALUATED_AT + timedelta(seconds=20),
            idempotency_key="IDEM-0003",
        )
        assert intent.account_mode_required == "PREPARATION"
        assert intent.time_in_force == "DAY"
        assert intent.side == "BUY"

    def test_a_rejection_cannot_produce_an_intent(self) -> None:
        proposal = a_proposal()
        rejection = record_operator_decision(
            proposal=proposal,
            decision_governance_id="DEC-REJ",
            action=OperatorAction.REJECT,
            operator_identity="operator-1",
            decided_at=EVALUATED_AT + timedelta(seconds=10),
            approval_expiry_seconds=120,
        )
        with pytest.raises(ValueError, match="requires an APPROVE decision"):
            build_approved_order_intent(
                intent_governance_id="INT-0004",
                proposal=replace(proposal, status=ProposalStatus.REJECTED),
                decision=rejection,
                created_at=EVALUATED_AT + timedelta(seconds=20),
                idempotency_key="IDEM-0004",
            )

    def test_an_approval_cannot_be_carried_to_a_different_proposal(self) -> None:
        _, decision = an_approved_pair()
        other = replace(
            a_proposal(proposal_governance_id="PRP-OTHER"), status=ProposalStatus.APPROVED
        )
        with pytest.raises(ValueError, match="does not belong to this proposal"):
            build_approved_order_intent(
                intent_governance_id="INT-0005",
                proposal=other,
                decision=decision,
                created_at=EVALUATED_AT + timedelta(seconds=20),
                idempotency_key="IDEM-0005",
            )

    def test_a_proposal_changed_after_approval_cannot_reuse_the_approval(self) -> None:
        proposal, decision = an_approved_pair()
        # Re-fingerprint the mutated proposal so that only the *decision's*
        # recorded digest is stale: exactly the attack the binding exists for.
        changed = evaluate(account=an_account(cash_available=Decimal("1500"))).proposal
        assert changed is not None
        changed = replace(changed, status=ProposalStatus.APPROVED)
        assert changed.quantity != proposal.quantity
        with pytest.raises(ValueError, match="approved fingerprint does not match"):
            build_approved_order_intent(
                intent_governance_id="INT-0006",
                proposal=changed,
                decision=decision,
                created_at=EVALUATED_AT + timedelta(seconds=20),
                idempotency_key="IDEM-0006",
            )

    def test_an_intent_cannot_be_built_after_the_approval_lapsed(self) -> None:
        proposal, decision = an_approved_pair()
        with pytest.raises(ValueError, match="approval expired"):
            build_approved_order_intent(
                intent_governance_id="INT-0007",
                proposal=proposal,
                decision=decision,
                created_at=EVALUATED_AT + timedelta(seconds=131),
                idempotency_key="IDEM-0007",
            )

    def test_an_intent_cannot_be_built_from_a_proposal_that_is_not_approved(self) -> None:
        proposal = a_proposal()
        decision = record_operator_decision(
            proposal=proposal,
            decision_governance_id="DEC-PREP",
            action=OperatorAction.APPROVE,
            operator_identity="operator-1",
            decided_at=EVALUATED_AT + timedelta(seconds=10),
            approval_expiry_seconds=120,
        )
        with pytest.raises(ValueError, match="not APPROVED"):
            build_approved_order_intent(
                intent_governance_id="INT-0008",
                proposal=proposal,
                decision=decision,
                created_at=EVALUATED_AT + timedelta(seconds=20),
                idempotency_key="IDEM-0008",
            )

    def test_an_intent_declaring_a_live_account_is_refused(self) -> None:
        proposal, decision = an_approved_pair()
        intent = build_approved_order_intent(
            intent_governance_id="INT-0009",
            proposal=proposal,
            decision=decision,
            created_at=EVALUATED_AT + timedelta(seconds=20),
            idempotency_key="IDEM-0009",
        )
        with pytest.raises(ValueError, match="account_mode_required must be PREPARATION"):
            replace(intent, account_mode_required="LIVE")

    def test_an_intent_that_survives_the_session_is_refused(self) -> None:
        proposal, decision = an_approved_pair()
        intent = build_approved_order_intent(
            intent_governance_id="INT-0010",
            proposal=proposal,
            decision=decision,
            created_at=EVALUATED_AT + timedelta(seconds=20),
            idempotency_key="IDEM-0010",
        )
        with pytest.raises(ValueError, match="time_in_force must be DAY"):
            replace(intent, time_in_force="GTC")

    def test_a_sell_intent_is_refused(self) -> None:
        proposal, decision = an_approved_pair()
        intent = build_approved_order_intent(
            intent_governance_id="INT-0011",
            proposal=proposal,
            decision=decision,
            created_at=EVALUATED_AT + timedelta(seconds=20),
            idempotency_key="IDEM-0011",
        )
        with pytest.raises(ValueError, match="side must be BUY"):
            replace(intent, side="SELL")

    def test_the_intent_carries_no_broker_endpoint_or_credential_field(self) -> None:
        # A field list is the cheapest place for a submission capability to
        # reappear, so it is asserted rather than assumed.
        forbidden = ("broker", "credential", "token", "endpoint", "api", "secret", "submitted_at")
        for field_name in ApprovedOrderIntent.__slots__:
            assert not any(word in field_name.lower() for word in forbidden), field_name


# =====================================================================
# Evaluation context -- the M083 watermark is consumed, not attached
# =====================================================================


class TestEvaluationContext:
    def build(self, **overrides: object) -> EvaluationContext:
        defaults: dict[str, object] = {
            "evaluation_context_id": "ECX-0001",
            "configuration": a_configuration(),
            "watermark": a_watermark(),
            "quote_id": "QTE-0001",
            "account_snapshot_id": "ACC-0001",
            "session_id": "SES-0001",
            "cost_estimate_id": "CST-0001",
            "instrument_universe_version": "UNIVERSE-2026-06",
            "strategy_version": "STRATEGY-0001",
            "created_at": EVALUATED_AT,
        }
        defaults.update(overrides)
        return build_evaluation_context(**defaults)  # type: ignore[arg-type]

    def test_the_receipt_count_is_read_from_the_loaded_watermark(self) -> None:
        context = self.build(watermark=a_watermark(count=7))
        assert context.consumed_receipt_count == 7

    def test_the_count_cannot_be_supplied_by_the_caller(self) -> None:
        with pytest.raises(TypeError):
            self.build(consumed_receipt_count=9999)

    def test_a_context_cannot_be_built_from_a_watermark_identity_alone(self) -> None:
        with pytest.raises(ValueError, match="must be a loaded EvaluationEvidenceWatermark"):
            self.build(watermark="WM-0001")

    def test_the_digest_binds_the_exact_receipt_set(self) -> None:
        watermark = a_watermark(count=4)
        context = self.build(watermark=watermark)
        assert context.consumed_receipt_digest == recompute_consumed_receipt_digest(watermark)

    def test_a_different_receipt_set_produces_a_different_digest(self) -> None:
        assert recompute_consumed_receipt_digest(
            a_watermark(count=3)
        ) != recompute_consumed_receipt_digest(a_watermark(count=4))

    def test_an_empty_watermark_is_representable_and_says_so(self) -> None:
        # Zero receipts is a real, honest state: it means no evidence was
        # captured, not that the binding may be skipped.
        context = self.build(watermark=a_watermark(count=0))
        assert context.consumed_receipt_count == 0

    def test_the_configuration_identity_and_version_are_taken_from_the_configuration(self) -> None:
        context = self.build(
            configuration=a_configuration(
                configuration_governance_id="CFG-084-0002", configuration_version=4
            )
        )
        assert context.configuration_governance_id == "CFG-084-0002"
        assert context.configuration_version == 4

    def test_a_naive_creation_instant_is_refused(self) -> None:
        with pytest.raises(ValueError, match="timezone-aware"):
            self.build(created_at=datetime(2026, 6, 10, 12, 0))  # noqa: DTZ001

    def test_a_blank_input_identity_is_refused(self) -> None:
        with pytest.raises(ValueError, match="quote_id must be a non-empty string"):
            self.build(quote_id="   ")

    def test_a_fabricated_digest_is_refused_at_construction(self) -> None:
        context = self.build()
        with pytest.raises(ValueError, match="64 lowercase hexadecimal"):
            replace(context, consumed_receipt_digest="not-a-digest")

    def test_an_optional_identity_may_be_absent(self) -> None:
        context = self.build(cost_estimate_id=None)
        assert context.cost_estimate_id is None
