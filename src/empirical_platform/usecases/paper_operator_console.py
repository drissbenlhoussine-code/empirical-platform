"""MILESTONE-088 -- preparing ONE bounded PAPER candidate, and read-only PAPER health.

WHY THIS MODULE EXISTS SEPARATELY FROM `operator_console.py`. `OperatorConsoleService`
already carries the entire staged review -> two-stage confirm -> dispatch pipeline, reused
UNCHANGED for PAPER (see `entrypoints._paper_operator_console_composition`): `today()`,
`opportunity()`, `prepare_approval()`/`confirm_approval()`, `active_trades()`, `history()`
and `safety()` all work over Store B exactly as they do over Store A, because they were
already written against the `PaperBrokerPort`/`PaperMarketDataPort` protocols rather than
against a concrete simulated adapter. What that service does NOT do is originate a NEW
candidate: MILESTONE-086's `today()` reads proposals that already exist, and the M086
console composes its own scenario-staged day (`ConsoleRuntime.load_day`) to put them there.
PAPER has no opportunity-scanning engine yet (mission scope), so this module supplies the
one thing the console still needs: an explicit, Owner-triggered action that prepares
exactly one bounded MILESTONE-084 proposal. Preparing a candidate writes ONLY a PREPARED
proposal; nothing is decided, issued, previewed, authorized or dispatched here. From there
the Owner uses the EXISTING Today -> Review -> Approve -> Confirm pipeline, unchanged.

WHY THE SAME BOUNDS AS THE ACCEPTANCE RUN, DUPLICATED RATHER THAN IMPORTED. AAPL, a limit
price derived to sit at most half of the real bid, a $5 notional ceiling, a 60-second
quote-freshness tolerance -- the exact values `tools/m085_paper_acceptance.py` used. They
are copied here, not imported from it: this package (`src/empirical_platform`) does not
import from `tools/`, the direction the architecture guard enforces is the other way, and
the canonical M085 Paper CLI is not touched to make this module possible. If the reviewed
acceptance bounds ever change, both places change together by the same review, not by one
silently drifting from the other.

READ-ONLY PAPER HEALTH (Phase 7). `paper_health()` calls only `fetch_account`,
`fetch_clock`, `fetch_asset`, `fetch_position` and `fetch_quote` -- the read methods on
`AlpacaPaperClient`/`AlpacaPaperMarketDataClient` -- and returns a view with no field that
could hold a credential. It never calls `submit_order` or `cancel_order`.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timedelta
from datetime import time as clock_time
from decimal import Decimal

from empirical_platform.decision_candidate.evaluation_context import build_evaluation_context
from empirical_platform.decision_candidate.evaluation_evidence_watermark_repository import (
    EvaluationEvidenceWatermarkRepository,
)
from empirical_platform.decision_candidate.operator_trading_configuration import (
    AccountMode,
    KillSwitchState,
    LimitPricePolicy,
    OperatorTradingConfiguration,
    OrderType,
    TradingSession,
)
from empirical_platform.decision_candidate.paper_execution_repositories import (
    PaperBrokerPort,
    PaperMarketDataPort,
    TimeBasisRepository,
)
from empirical_platform.decision_candidate.product_market_inputs import (
    AccountSnapshot,
    DataFeedKind,
    InstrumentMetadata,
    LiquiditySnapshot,
    MarketStatus,
    QuoteSnapshot,
    SessionSnapshot,
    TradingCostEstimate,
)
from empirical_platform.decision_candidate.product_repositories import (
    EvaluationContextRepository,
    OperatorTradingConfigurationRepository,
    TradeProposalRepository,
)
from empirical_platform.decision_candidate.trade_proposal import TradeProposal
from empirical_platform.shared.brokerage.paper_time import PaperTimeSource
from empirical_platform.usecases.operator_console_fixtures import simulation_timezone_for
from empirical_platform.usecases.paper_execution import (
    PreparePaperBoundTradeProposalCommand,
    PreparePaperBoundTradeProposalHandler,
)

__all__ = [
    "APPROVED_SYMBOL",
    "PaperCandidateBlockedError",
    "PaperHealthView",
    "paper_health",
    "prepare_paper_candidate",
]

#: MILESTONE-088's own configuration identity: same bounds as M085's acceptance contract
#: (watchlist AAPL only, $5 per-trade cap), so a candidate prepared here is authorized
#: under the SAME already-reviewed envelope -- not a wider one, not a new one.
_CONFIGURATION_ID = "CFG-088-PAPER"
_CONFIGURATION_VERSION = 1

#: Mirrors `tools/m085_paper_acceptance.py`'s safety constants exactly (see module
#: docstring for why they are copied here rather than imported).
APPROVED_SYMBOL = "AAPL"
MAXIMUM_NOTIONAL = Decimal("5")
ACCEPTANCE_LIMIT_PRICE = Decimal("4.00")
QUOTE_MAXIMUM_AGE_SECONDS = 60
MAXIMUM_LIMIT_FRACTION_OF_BID = Decimal("0.5")


class PaperCandidateBlockedError(RuntimeError):
    """A safety gate refused before any proposal was written. Recorded, not worked around."""


def _account_reference(account_id: str) -> str:
    """Same stable, non-reversible digest convention as `usecases.paper_execution`."""
    return "ref:" + hashlib.sha256(f"m085/{account_id}".encode()).hexdigest()[:32]


@dataclass(frozen=True, slots=True)
class PaperHealthView:
    """Read-only PAPER health. No field here can hold a credential."""

    trading_endpoint: str
    is_pinned_paper_host: bool
    market_data_endpoint: str
    account_reachable: bool
    account_status: str
    account_reference: str
    trading_blocked: bool
    account_blocked: bool
    trade_suspended_by_user: bool
    market_is_open: bool
    next_open: datetime | None
    next_close: datetime | None
    symbol: str
    asset_tradable: bool
    asset_status: str
    position_quantity: str
    quote_bid: str
    quote_ask: str
    quote_captured_at: datetime | None
    quote_age_seconds: str
    quote_source: str


def paper_health(
    *, broker: PaperBrokerPort, market_data: PaperMarketDataPort, now: datetime
) -> PaperHealthView:
    """Phase 7: read-only. Every call below is a GET; none can place or cancel an order."""
    _status, payload = broker.fetch_account()
    clock = broker.fetch_clock()
    asset = broker.fetch_asset(APPROVED_SYMBOL)
    position = broker.fetch_position(APPROVED_SYMBOL)
    quote = market_data.fetch_quote(APPROVED_SYMBOL)
    age = "" if quote is None else f"{(now - quote.captured_at).total_seconds():.1f}"
    account_id = payload.get("id")
    return PaperHealthView(
        trading_endpoint=broker.endpoint_host,
        is_pinned_paper_host=broker.endpoint_host == "paper-api.alpaca.markets",
        market_data_endpoint=market_data.endpoint_host,
        account_reachable=True,
        account_status=str(payload.get("status", "unknown")),
        account_reference=(
            _account_reference(account_id) if isinstance(account_id, str) else "unknown"
        ),
        trading_blocked=bool(payload.get("trading_blocked", True)),
        account_blocked=bool(payload.get("account_blocked", True)),
        trade_suspended_by_user=bool(payload.get("trade_suspended_by_user", True)),
        market_is_open=clock.is_open,
        next_open=clock.next_open,
        next_close=clock.next_close,
        symbol=APPROVED_SYMBOL,
        asset_tradable=asset.tradable,
        asset_status=asset.status,
        position_quantity=("0" if position is None else str(position.quantity)),
        quote_bid=("" if quote is None else str(quote.bid)),
        quote_ask=("" if quote is None else str(quote.ask)),
        quote_captured_at=None if quote is None else quote.captured_at,
        quote_age_seconds=age,
        quote_source="" if quote is None else quote.source,
    )


def _default_configuration(*, now: datetime) -> OperatorTradingConfiguration:
    """`mandatory_liquidation_time=23:59` combined with a 1-hour proposal expiry leaves a
    ~61-minute-per-UTC-day window where `liquidation_reachable` genuinely (and correctly)
    refuses -- a real gap near UTC midnight, not a bug in that safety check. Rather than
    weaken it, `operator_timezone` is chosen (via `simulation_timezone_for`) so `now` always
    reads mid-morning in it, the same established pattern `operator_console_fixtures.py`
    already uses for this exact problem."""
    return OperatorTradingConfiguration(
        configuration_governance_id=_CONFIGURATION_ID,
        configuration_version=_CONFIGURATION_VERSION,
        base_currency="USD",
        permitted_markets=("XNAS",),
        watchlist=(APPROVED_SYMBOL,),
        prohibited_instruments=("PENNY",),
        maximum_deployable_capital=Decimal("10000"),
        maximum_capital_per_trade=MAXIMUM_NOTIONAL,
        maximum_percent_per_trade=Decimal("20"),
        minimum_cash_reserve=Decimal("1000"),
        maximum_simultaneous_positions=3,
        maximum_daily_loss=Decimal("500"),
        maximum_daily_order_count=10,
        minimum_price=Decimal("1"),
        maximum_price=Decimal("1000"),
        minimum_liquidity_shares=100_000,
        maximum_spread_percent=Decimal("5"),
        maximum_estimated_slippage_percent=Decimal("1"),
        maximum_evidence_age_seconds=86_400,
        maximum_market_data_age_seconds=QUOTE_MAXIMUM_AGE_SECONDS,
        permitted_session=TradingSession.REGULAR,
        earliest_entry_time=clock_time(0, 1),
        latest_entry_time=clock_time(23, 58),
        mandatory_liquidation_time=clock_time(23, 59),
        operator_timezone=simulation_timezone_for(now),
        exchange_calendar_policy="XNAS-REGULAR-2026",
        proposal_expiry_seconds=3600,
        approval_expiry_seconds=1800,
        default_order_type=OrderType.LIMIT,
        permitted_order_types=(OrderType.LIMIT,),
        limit_price_policy=LimitPricePolicy.ASK,
        stop_loss_percent=Decimal("2"),
        profit_exit_percent=Decimal("4"),
        maximum_leverage=Decimal("1"),
        short_selling_permitted=False,
        overnight_positions_permitted=False,
        account_mode=AccountMode.PREPARATION,
        kill_switch=KillSwitchState.DISENGAGED,
    )


def prepare_paper_candidate(
    *,
    configurations: OperatorTradingConfigurationRepository,
    contexts: EvaluationContextRepository,
    proposals: TradeProposalRepository,
    watermarks: EvaluationEvidenceWatermarkRepository,
    time_bases: TimeBasisRepository,
    broker: PaperBrokerPort,
    market_data: PaperMarketDataPort,
    time_source: PaperTimeSource,
    now: datetime,
) -> TradeProposal:
    """Prepare (not decide, not issue) ONE bounded PAPER candidate for today.

    Idempotent by date: `PRP-088-PAPER-<date>` is DERIVED, never generated, so calling this
    twice on the same day returns the existing proposal rather than writing a second one.
    Raises `PaperCandidateBlockedError` -- never relaxes a bound -- exactly as the acceptance
    script does, when the market is shut, the quote is stale, or the limit cannot be shown
    to sit safely below the real bid.
    """
    today = now.date().isoformat()
    proposal_id = f"PRP-088-PAPER-{today}"
    existing = proposals.get(proposal_id)
    if existing is not None:
        return existing

    configuration = configurations.get(_CONFIGURATION_ID, _CONFIGURATION_VERSION)
    if configuration is None:
        configuration = _default_configuration(now=now)
        configurations.save(configuration)

    clock = broker.fetch_clock()
    if not clock.is_open:
        raise PaperCandidateBlockedError(
            f"the market is closed (next open {clock.next_open}); no candidate was prepared"
        )
    quote = market_data.fetch_quote(APPROVED_SYMBOL)
    if quote is None:
        raise PaperCandidateBlockedError(
            "no quote is available, so no limit price can be shown to be safe"
        )
    age = (now - quote.captured_at).total_seconds()
    if age > QUOTE_MAXIMUM_AGE_SECONDS:
        raise PaperCandidateBlockedError(
            f"the only available quote is {age:.0f}s old, beyond the "
            f"{QUOTE_MAXIMUM_AGE_SECONDS}s freshness tolerance; not widened to get past it"
        )
    if quote.bid is None or Decimal(quote.bid) <= 0:
        raise PaperCandidateBlockedError(
            f"the real bid is {quote.bid!r}, so a safe limit cannot be shown"
        )
    bid = Decimal(quote.bid)
    fraction = (ACCEPTANCE_LIMIT_PRICE / bid).quantize(Decimal("0.0001"))
    if fraction > MAXIMUM_LIMIT_FRACTION_OF_BID:
        raise PaperCandidateBlockedError(
            f"the bounded limit is {fraction} of the real bid, above the "
            f"{MAXIMUM_LIMIT_FRACTION_OF_BID} ceiling; not raised to get past it"
        )

    watermark = watermarks.capture(watermark_governance_id=f"WM-088-PAPER-{today}")
    context = build_evaluation_context(
        evaluation_context_id=f"ECX-088-PAPER-{today}",
        configuration=configuration,
        watermark=watermark,
        quote_id=f"QTE-088-PAPER-{today}",
        account_snapshot_id=f"ACC-088-PAPER-{today}",
        session_id=f"SES-088-PAPER-{today}",
        cost_estimate_id=f"CST-088-PAPER-{today}",
        instrument_universe_version="UNIVERSE-2026-09",
        strategy_version="M088-PAPER-BOUNDED-CANDIDATE",
        created_at=now,
    )
    contexts.save(context)

    prepared = PreparePaperBoundTradeProposalHandler(
        configurations=configurations,
        contexts=contexts,
        proposals=proposals,
        time_bases=time_bases,
        broker=broker,
        time_source=time_source,
    ).handle(
        PreparePaperBoundTradeProposalCommand(
            proposal_governance_id=proposal_id,
            evaluation_context_id=context.evaluation_context_id,
            symbol=APPROVED_SYMBOL,
            # THE SAFETY INPUT, not a market observation -- same discipline as the acceptance
            # script: derives a limit far below the real market, which is what the real-quote
            # check above already proved is safe.
            quote=QuoteSnapshot(
                quote_id=f"QTE-088-PAPER-{today}",
                provider_id="OPERATOR-ASSERTED-SAFETY-INPUT",
                symbol=APPROVED_SYMBOL,
                bid=ACCEPTANCE_LIMIT_PRICE - Decimal("0.05"),
                ask=ACCEPTANCE_LIMIT_PRICE,
                last_trade=ACCEPTANCE_LIMIT_PRICE,
                observed_at=now - timedelta(seconds=5),
                feed_kind=DataFeedKind.REAL_TIME,
            ),
            account=AccountSnapshot(
                account_snapshot_id=f"ACC-088-PAPER-{today}",
                provider_id="OPERATOR-ASSERTED-SAFETY-INPUT",
                account_reference="PAPER-CONSOLE",
                base_currency="USD",
                cash_available=Decimal("5000"),
                equity_total=Decimal("10000"),
                realized_pnl_today=Decimal("0"),
                orders_submitted_today=0,
                observed_at=now - timedelta(seconds=5),
            ),
            session=SessionSnapshot(
                session_id=f"SES-088-PAPER-{today}",
                provider_id="OPERATOR-ASSERTED-SAFETY-INPUT",
                market="XNAS",
                status=MarketStatus.OPEN,
                observed_at=now - timedelta(seconds=5),
            ),
            instrument=InstrumentMetadata(
                symbol=APPROVED_SYMBOL,
                market="XNAS",
                currency="USD",
                is_fractionable=False,
                lot_size=1,
            ),
            liquidity=LiquiditySnapshot(
                symbol=APPROVED_SYMBOL,
                average_daily_volume_shares=50_000_000,
                observed_at=now - timedelta(seconds=5),
            ),
            cost_estimate=TradingCostEstimate(
                estimate_id=f"CST-088-PAPER-{today}",
                provider_id="OPERATOR-ASSERTED-SAFETY-INPUT",
                symbol=APPROVED_SYMBOL,
                commission=Decimal("0.00"),
                estimated_slippage_percent=Decimal("0.1"),
                observed_at=now - timedelta(seconds=5),
            ),
            positions=(),
            open_orders=(),
            evidence_age_seconds=Decimal("60"),
        )
    )
    outcome = prepared.outcome
    if outcome.proposal is None or prepared.time_basis is None:
        raise PaperCandidateBlockedError(
            f"MILESTONE-084 refused to propose: {outcome.no_trade_reason}"
        )
    return outcome.proposal
