"""MILESTONE-084 -- the deterministic trade-proposal engine.

WHAT THIS IS. Given one operator configuration, one evaluation instant and one
set of provider-neutral snapshots, this module returns exactly one of two
things: a closed `NO_TRADE` reason, or one immutable `TradeProposal` whose
quantity was derived here rather than supplied by the caller.

DETERMINISTIC. Same inputs, same output, always. No clock read, no randomness,
no I/O. The evaluation instant is a parameter, never `datetime.now()`.

FAIL CLOSED. Every risk check returns PASSED, FAILED or UNKNOWN. A proposal is
produced only when every applicable check is PASS. An UNKNOWN is never treated
as a PASSED -- a check that could not be evaluated is a reason not to trade, and
the engine says which one.

THE CALLER CANNOT SIZE THE TRADE. `evaluate_trade_proposal` accepts no desired
quantity. Quantity is derived from cash, the per-trade capital cap, the
percentage cap and the lot size, then floored. A caller who wants a specific
size must change the configuration, which is versioned and auditable.

THE FINGERPRINT IS A CHANGE DETECTOR. `content_fingerprint` is a SHA-256 over
the exact order terms. It binds an approval to one precise proposal version so
that a changed quantity, price, symbol, order type or expiry cannot inherit an
older approval. It is NOT a cryptographic seal against a determined attacker
with database write access, and this milestone claims no such property.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import ROUND_DOWN, Decimal
from enum import StrEnum
from typing import TypedDict
from zoneinfo import ZoneInfo

from empirical_platform.decision_candidate.operator_trading_configuration import (
    KillSwitchState,
    LimitPricePolicy,
    OperatorTradingConfiguration,
    OrderType,
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

__all__ = [
    "NoTradeReason",
    "ProposalStatus",
    "RiskCheck",
    "RiskCheckOutcome",
    "TradeProposal",
    "TradeProposalOutcome",
    "evaluate_trade_proposal",
]

_MAXIMUM_IDENTIFIER_LENGTH = 64
_CENT = Decimal("0.01")

#: The only side this product represents. Named once so that the default, the
#: refusal in `__post_init__` and the engine all state the same literal.
_BUY_SIDE = "BUY"


class ProposalStatus(StrEnum):
    """Lifecycle state of a proposal.

    The state machine that governs transitions between these is enforced in the
    database; this enum only names the states the domain can represent.
    """

    PREPARED = "PREPARED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    CANCELLED = "CANCELLED"
    INVALIDATED = "INVALIDATED"


class RiskCheckOutcome(StrEnum):
    """Result of one risk check.

    UNKNOWN is a first-class outcome, not an error condition. It means the
    check could not be evaluated from the inputs supplied, and it blocks a
    proposal exactly as firmly as FAILED.
    """

    PASSED = "PASSED"
    FAILED = "FAILED"
    UNKNOWN = "UNKNOWN"


class NoTradeReason(StrEnum):
    """Closed set of reasons the engine declines to propose.

    Ordered by the precedence in `_REASON_PRECEDENCE` below: when several apply,
    the engine reports exactly one, deterministically.
    """

    KILL_SWITCH_ENGAGED = "KILL_SWITCH_ENGAGED"
    MARKET_NOT_OPEN = "MARKET_NOT_OPEN"
    MARKET_STATUS_UNKNOWN = "MARKET_STATUS_UNKNOWN"
    OUTSIDE_ENTRY_WINDOW = "OUTSIDE_ENTRY_WINDOW"
    LIQUIDATION_DEADLINE_UNREACHABLE = "LIQUIDATION_DEADLINE_UNREACHABLE"
    MARKET_DATA_STALE = "MARKET_DATA_STALE"
    MARKET_DATA_NOT_REAL_TIME = "MARKET_DATA_NOT_REAL_TIME"
    EVIDENCE_STALE = "EVIDENCE_STALE"
    INSTRUMENT_NOT_WATCHLISTED = "INSTRUMENT_NOT_WATCHLISTED"
    INSTRUMENT_PROHIBITED = "INSTRUMENT_PROHIBITED"
    MARKET_NOT_PERMITTED = "MARKET_NOT_PERMITTED"
    CURRENCY_MISMATCH = "CURRENCY_MISMATCH"
    PRICE_OUTSIDE_BOUNDS = "PRICE_OUTSIDE_BOUNDS"
    SPREAD_TOO_WIDE = "SPREAD_TOO_WIDE"
    LIQUIDITY_INSUFFICIENT = "LIQUIDITY_INSUFFICIENT"
    SLIPPAGE_TOO_HIGH = "SLIPPAGE_TOO_HIGH"
    COST_ESTIMATE_MISSING = "COST_ESTIMATE_MISSING"
    EXISTING_POSITION_CONFLICT = "EXISTING_POSITION_CONFLICT"
    OPEN_ORDER_CONFLICT = "OPEN_ORDER_CONFLICT"
    POSITION_LIMIT_REACHED = "POSITION_LIMIT_REACHED"
    DAILY_LOSS_LIMIT_REACHED = "DAILY_LOSS_LIMIT_REACHED"
    DAILY_ORDER_LIMIT_REACHED = "DAILY_ORDER_LIMIT_REACHED"
    CASH_INSUFFICIENT = "CASH_INSUFFICIENT"
    CASH_RESERVE_BREACHED = "CASH_RESERVE_BREACHED"
    QUANTITY_ZERO_AFTER_SIZING = "QUANTITY_ZERO_AFTER_SIZING"
    ORDER_TYPE_NOT_PERMITTED = "ORDER_TYPE_NOT_PERMITTED"
    NO_ELIGIBLE_CANDIDATE = "NO_ELIGIBLE_CANDIDATE"


# Precedence is explicit rather than incidental: the engine must report the
# same single reason for the same inputs regardless of check ordering. Earlier
# entries win. Global stops come first, then market state, then data quality,
# then instrument eligibility, then portfolio and capital.
_REASON_PRECEDENCE: tuple[NoTradeReason, ...] = (
    NoTradeReason.KILL_SWITCH_ENGAGED,
    NoTradeReason.MARKET_STATUS_UNKNOWN,
    NoTradeReason.MARKET_NOT_OPEN,
    NoTradeReason.OUTSIDE_ENTRY_WINDOW,
    NoTradeReason.LIQUIDATION_DEADLINE_UNREACHABLE,
    NoTradeReason.MARKET_DATA_NOT_REAL_TIME,
    NoTradeReason.MARKET_DATA_STALE,
    NoTradeReason.EVIDENCE_STALE,
    NoTradeReason.COST_ESTIMATE_MISSING,
    NoTradeReason.INSTRUMENT_PROHIBITED,
    NoTradeReason.INSTRUMENT_NOT_WATCHLISTED,
    NoTradeReason.MARKET_NOT_PERMITTED,
    NoTradeReason.CURRENCY_MISMATCH,
    NoTradeReason.ORDER_TYPE_NOT_PERMITTED,
    NoTradeReason.PRICE_OUTSIDE_BOUNDS,
    NoTradeReason.SPREAD_TOO_WIDE,
    NoTradeReason.LIQUIDITY_INSUFFICIENT,
    NoTradeReason.SLIPPAGE_TOO_HIGH,
    NoTradeReason.EXISTING_POSITION_CONFLICT,
    NoTradeReason.OPEN_ORDER_CONFLICT,
    NoTradeReason.POSITION_LIMIT_REACHED,
    NoTradeReason.DAILY_LOSS_LIMIT_REACHED,
    NoTradeReason.DAILY_ORDER_LIMIT_REACHED,
    NoTradeReason.CASH_RESERVE_BREACHED,
    NoTradeReason.CASH_INSUFFICIENT,
    NoTradeReason.QUANTITY_ZERO_AFTER_SIZING,
    NoTradeReason.NO_ELIGIBLE_CANDIDATE,
)

_PRECEDENCE_INDEX = {reason: index for index, reason in enumerate(_REASON_PRECEDENCE)}


@dataclass(frozen=True, slots=True)
class RiskCheck:
    """One named check and the outcome it produced."""

    check_id: str
    outcome: RiskCheckOutcome
    detail: str

    def __post_init__(self) -> None:
        if not isinstance(self.check_id, str) or not self.check_id.strip():
            raise ValueError("check_id must be a non-empty string")
        if len(self.check_id) > _MAXIMUM_IDENTIFIER_LENGTH:
            raise ValueError("check_id must be at most 64 characters")
        if not isinstance(self.outcome, RiskCheckOutcome):
            raise ValueError("outcome must be a RiskCheckOutcome")
        if not isinstance(self.detail, str):
            raise ValueError("detail must be a string")
        if len(self.detail) > 512:
            raise ValueError("detail must be at most 512 characters")


@dataclass(frozen=True, slots=True)
class TradeProposal:
    """One immutable, versioned, expiring long-only intraday buy proposal.

    `side` is a field only because the fingerprint and the downstream order
    intent must both state it explicitly rather than leave it implied. It is
    fixed: any value but BUY is refused at construction, so this product cannot
    represent a sell even by direct instantiation.
    """

    proposal_governance_id: str
    proposal_version: int
    evaluation_context_id: str
    configuration_governance_id: str
    configuration_version: int

    symbol: str
    quantity: int
    order_type: OrderType
    limit_price: Decimal | None
    currency: str

    estimated_notional: Decimal
    estimated_fees: Decimal
    estimated_slippage_amount: Decimal
    estimated_total_cash_required: Decimal

    stop_loss_price: Decimal
    profit_exit_price: Decimal
    mandatory_liquidation_at: datetime

    created_at: datetime
    expires_at: datetime
    status: ProposalStatus
    risk_checks: tuple[RiskCheck, ...]

    #: SHA-256 over the exact order terms. See the module docstring: a change
    #: detector and approval binding, not a cryptographic seal.
    content_fingerprint: str

    #: Fixed for the lifetime of MILESTONE-084.
    side: str = _BUY_SIDE

    def __post_init__(self) -> None:
        for field_name in (
            "proposal_governance_id",
            "evaluation_context_id",
            "configuration_governance_id",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field_name} must be a non-empty string")
            if len(value) > _MAXIMUM_IDENTIFIER_LENGTH:
                raise ValueError(f"{field_name} must be at most 64 characters")
        for field_name in ("proposal_version", "configuration_version"):
            value = getattr(self, field_name)
            if isinstance(value, bool) or not isinstance(value, int):
                raise ValueError(f"{field_name} must be an int")
            if value < 1:
                raise ValueError(f"{field_name} must start at 1")

        if self.side != _BUY_SIDE:
            raise ValueError(
                "side must be BUY: this product is long-only and does not represent a sell"
            )
        if not isinstance(self.symbol, str) or self.symbol != self.symbol.strip().upper():
            raise ValueError("symbol must be an upper-case, unpadded string")
        if isinstance(self.quantity, bool) or not isinstance(self.quantity, int):
            raise ValueError("quantity must be an int")
        if self.quantity <= 0:
            raise ValueError("quantity must be positive: a zero-quantity proposal is a NO_TRADE")
        if not isinstance(self.order_type, OrderType):
            raise ValueError("order_type must be an OrderType")
        if self.order_type is OrderType.LIMIT and self.limit_price is None:
            raise ValueError("a LIMIT proposal must carry a limit_price")
        if self.order_type is OrderType.MARKET and self.limit_price is not None:
            raise ValueError("a MARKET proposal must not carry a limit_price")
        if self.limit_price is not None and (
            not isinstance(self.limit_price, Decimal)
            or not self.limit_price.is_finite()
            or self.limit_price <= 0
        ):
            raise ValueError("limit_price must be a positive finite Decimal")
        if not isinstance(self.currency, str) or len(self.currency) != 3:
            raise ValueError("currency must be a 3-letter ISO code")

        for field_name in (
            "estimated_notional",
            "estimated_fees",
            "estimated_slippage_amount",
            "estimated_total_cash_required",
            "stop_loss_price",
            "profit_exit_price",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, Decimal) or not value.is_finite() or value < 0:
                raise ValueError(f"{field_name} must be a non-negative finite Decimal")
        if self.stop_loss_price <= 0 or self.profit_exit_price <= 0:
            raise ValueError("stop_loss_price and profit_exit_price must be positive")
        if self.profit_exit_price <= self.stop_loss_price:
            raise ValueError("profit_exit_price must exceed stop_loss_price")

        expected_total = (
            self.estimated_notional + self.estimated_fees + self.estimated_slippage_amount
        )
        if self.estimated_total_cash_required != expected_total:
            raise ValueError("estimated_total_cash_required must equal notional + fees + slippage")

        for field_name in ("created_at", "expires_at", "mandatory_liquidation_at"):
            value = getattr(self, field_name)
            if not isinstance(value, datetime) or value.tzinfo is None:
                raise ValueError(f"{field_name} must be a timezone-aware datetime")
        if self.expires_at <= self.created_at:
            raise ValueError("expires_at must follow created_at")
        if self.mandatory_liquidation_at <= self.created_at:
            raise ValueError("mandatory_liquidation_at must follow created_at")

        if not isinstance(self.status, ProposalStatus):
            raise ValueError("status must be a ProposalStatus")
        if not isinstance(self.risk_checks, tuple) or not self.risk_checks:
            raise ValueError("risk_checks must be a non-empty tuple")
        for check in self.risk_checks:
            if not isinstance(check, RiskCheck):
                raise ValueError("risk_checks must contain RiskCheck values")
        if any(check.outcome is not RiskCheckOutcome.PASSED for check in self.risk_checks):
            raise ValueError(
                "a TradeProposal may only exist when every risk check passed; a FAIL or "
                "UNKNOWN outcome must produce a NO_TRADE instead"
            )
        check_ids = [check.check_id for check in self.risk_checks]
        if len(set(check_ids)) != len(check_ids):
            raise ValueError("risk_checks must not repeat a check_id")

        if not isinstance(self.content_fingerprint, str) or len(self.content_fingerprint) != 64:
            raise ValueError("content_fingerprint must be a 64-character hex digest")
        if self.content_fingerprint != compute_fingerprint(self):
            raise ValueError("content_fingerprint does not match the proposal's own order terms")

    def expired_at(self, instant: datetime) -> bool:
        """Whether this proposal has expired as of a caller-supplied instant."""
        if not isinstance(instant, datetime) or instant.tzinfo is None:
            raise ValueError("instant must be a timezone-aware datetime")
        return instant >= self.expires_at


class _AuthorizedTerms(TypedDict):
    """Exactly the terms an approval authorizes -- the digest's whole input.

    Typed as a mapping rather than a parameter list so that the same object can
    be handed both to the digest and to the constructor, making it structurally
    impossible for a proposal to be fingerprinted over terms other than its own.
    """

    proposal_governance_id: str
    proposal_version: int
    evaluation_context_id: str
    configuration_governance_id: str
    configuration_version: int
    symbol: str
    side: str
    quantity: int
    order_type: OrderType
    limit_price: Decimal | None
    currency: str
    estimated_notional: Decimal
    estimated_fees: Decimal
    estimated_slippage_amount: Decimal
    estimated_total_cash_required: Decimal
    stop_loss_price: Decimal
    profit_exit_price: Decimal
    mandatory_liquidation_at: datetime
    expires_at: datetime


def _money(value: Decimal) -> str:
    """Render one amount for the digest, by value rather than by scale.

    `normalize()` first, deliberately. A price is the same price whether it
    reached here as `200.10` or as the `200.10000000` that a NUMERIC(20,8)
    column returns, and a digest that disagreed with itself across a database
    round trip would report every re-read proposal as tampered with. `"f"`
    formatting then keeps a normalized whole number out of exponent notation,
    so `2000` never renders as `2E+3`.
    """
    return format(value.normalize(), "f")


def _fingerprint_digest(terms: _AuthorizedTerms) -> str:
    """The one definition of the digest, over values rather than an instance.

    Taking values means the digest can be computed before the object exists, so
    a proposal is constructed exactly once, already carrying its real digest --
    no placeholder that `__post_init__` would have to be bypassed to accept.
    """
    limit_price = terms["limit_price"]
    payload = "\n".join(
        (
            terms["proposal_governance_id"],
            str(terms["proposal_version"]),
            terms["evaluation_context_id"],
            terms["configuration_governance_id"],
            str(terms["configuration_version"]),
            terms["symbol"],
            terms["side"],
            str(terms["quantity"]),
            terms["order_type"].value,
            "" if limit_price is None else _money(limit_price),
            terms["currency"],
            _money(terms["estimated_notional"]),
            _money(terms["estimated_fees"]),
            _money(terms["estimated_slippage_amount"]),
            _money(terms["estimated_total_cash_required"]),
            _money(terms["stop_loss_price"]),
            _money(terms["profit_exit_price"]),
            terms["mandatory_liquidation_at"].astimezone(UTC).isoformat(),
            terms["expires_at"].astimezone(UTC).isoformat(),
        )
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def compute_fingerprint(proposal: TradeProposal) -> str:
    """Deterministic SHA-256 over exactly the terms an approval authorizes.

    Deliberately excludes `status` and `risk_checks`: a proposal that moves from
    PREPARED to APPROVED is the same order, and re-recording the checks would
    make the fingerprint depend on diagnostic text. It includes every term whose
    change would mean the operator approved a different order.
    """
    return _fingerprint_digest(
        _AuthorizedTerms(
            proposal_governance_id=proposal.proposal_governance_id,
            proposal_version=proposal.proposal_version,
            evaluation_context_id=proposal.evaluation_context_id,
            configuration_governance_id=proposal.configuration_governance_id,
            configuration_version=proposal.configuration_version,
            symbol=proposal.symbol,
            side=proposal.side,
            quantity=proposal.quantity,
            order_type=proposal.order_type,
            limit_price=proposal.limit_price,
            currency=proposal.currency,
            estimated_notional=proposal.estimated_notional,
            estimated_fees=proposal.estimated_fees,
            estimated_slippage_amount=proposal.estimated_slippage_amount,
            estimated_total_cash_required=proposal.estimated_total_cash_required,
            stop_loss_price=proposal.stop_loss_price,
            profit_exit_price=proposal.profit_exit_price,
            mandatory_liquidation_at=proposal.mandatory_liquidation_at,
            expires_at=proposal.expires_at,
        )
    )


@dataclass(frozen=True, slots=True)
class TradeProposalOutcome:
    """Exactly one of: a proposal, or a single closed NO_TRADE reason."""

    proposal: TradeProposal | None
    no_trade_reason: NoTradeReason | None
    risk_checks: tuple[RiskCheck, ...]

    def __post_init__(self) -> None:
        if (self.proposal is None) == (self.no_trade_reason is None):
            raise ValueError("exactly one of proposal or no_trade_reason must be present")
        if not isinstance(self.risk_checks, tuple) or not self.risk_checks:
            raise ValueError("risk_checks must be a non-empty tuple")

    @property
    def is_trade(self) -> bool:
        return self.proposal is not None


def _first_reason(reasons: set[NoTradeReason]) -> NoTradeReason:
    """The single reason to report, chosen by explicit precedence."""
    return min(reasons, key=lambda reason: _PRECEDENCE_INDEX[reason])


def evaluate_trade_proposal(
    *,
    configuration: OperatorTradingConfiguration,
    evaluation_context_id: str,
    proposal_governance_id: str,
    evaluated_at: datetime,
    symbol: str,
    quote: QuoteSnapshot,
    account: AccountSnapshot,
    session: SessionSnapshot,
    instrument: InstrumentMetadata,
    liquidity: LiquiditySnapshot,
    cost_estimate: TradingCostEstimate | None,
    positions: tuple[PositionSnapshot, ...],
    open_orders: tuple[OpenOrderSnapshot, ...],
    evidence_age_seconds: Decimal,
) -> TradeProposalOutcome:
    """Evaluate one instrument and return a proposal or a closed NO_TRADE reason.

    Note what is absent from this signature: a desired quantity, a desired
    price, and a caller-supplied risk verdict. All three are derived here.
    """
    if not isinstance(evaluated_at, datetime) or evaluated_at.tzinfo is None:
        raise ValueError("evaluated_at must be a timezone-aware datetime")
    if not isinstance(evidence_age_seconds, Decimal) or evidence_age_seconds < 0:
        raise ValueError("evidence_age_seconds must be a non-negative Decimal")
    if symbol != symbol.strip().upper():
        raise ValueError("symbol must be upper-case and unpadded")
    if quote.symbol != symbol or instrument.symbol != symbol or liquidity.symbol != symbol:
        raise ValueError("every snapshot must describe the requested symbol")

    checks: list[RiskCheck] = []
    reasons: set[NoTradeReason] = set()

    def record(
        check_id: str, outcome: RiskCheckOutcome, detail: str, reason: NoTradeReason | None
    ) -> None:
        checks.append(RiskCheck(check_id=check_id, outcome=outcome, detail=detail))
        if outcome is not RiskCheckOutcome.PASSED and reason is not None:
            reasons.add(reason)

    # --- global stop -------------------------------------------------------
    record(
        "kill_switch",
        RiskCheckOutcome.PASSED
        if configuration.kill_switch is KillSwitchState.DISENGAGED
        else RiskCheckOutcome.FAILED,
        f"kill switch {configuration.kill_switch.value}",
        NoTradeReason.KILL_SWITCH_ENGAGED,
    )

    # --- market state ------------------------------------------------------
    if session.status is MarketStatus.UNKNOWN:
        record(
            "market_status",
            RiskCheckOutcome.UNKNOWN,
            "market status unknown",
            NoTradeReason.MARKET_STATUS_UNKNOWN,
        )
    elif not session.is_tradeable:
        record(
            "market_status",
            RiskCheckOutcome.FAILED,
            f"market {session.status.value}",
            NoTradeReason.MARKET_NOT_OPEN,
        )
    else:
        record("market_status", RiskCheckOutcome.PASSED, "market OPEN", None)

    local_now = evaluated_at.astimezone(ZoneInfo(configuration.operator_timezone))
    local_time = local_now.timetz().replace(tzinfo=None)
    within_window = (
        configuration.earliest_entry_time <= local_time <= configuration.latest_entry_time
    )
    record(
        "entry_window",
        RiskCheckOutcome.PASSED if within_window else RiskCheckOutcome.FAILED,
        f"local entry time {local_time.isoformat()}",
        NoTradeReason.OUTSIDE_ENTRY_WINDOW,
    )

    liquidation_at = local_now.replace(
        hour=configuration.mandatory_liquidation_time.hour,
        minute=configuration.mandatory_liquidation_time.minute,
        second=configuration.mandatory_liquidation_time.second,
        microsecond=0,
    )
    # The whole proposal lifetime must fit before the mandatory liquidation, not
    # merely its first instant. A proposal that is still approvable after the
    # deadline authorizes an entry that cannot be closed intraday -- which is an
    # overnight position, the thing this product refuses to hold. Checking only
    # `liquidation_at > local_now` would be vacuous: a valid configuration
    # already requires the deadline to follow the last permitted entry.
    proposal_dies_at = local_now + timedelta(seconds=configuration.proposal_expiry_seconds)
    record(
        "liquidation_reachable",
        RiskCheckOutcome.PASSED if liquidation_at >= proposal_dies_at else RiskCheckOutcome.FAILED,
        f"mandatory liquidation at {liquidation_at.isoformat()}, "
        f"proposal would expire at {proposal_dies_at.isoformat()}",
        NoTradeReason.LIQUIDATION_DEADLINE_UNREACHABLE,
    )

    # --- data quality ------------------------------------------------------
    record(
        "market_data_feed",
        RiskCheckOutcome.PASSED
        if quote.feed_kind is DataFeedKind.REAL_TIME
        else RiskCheckOutcome.FAILED,
        f"quote feed {quote.feed_kind.value}",
        NoTradeReason.MARKET_DATA_NOT_REAL_TIME,
    )
    quote_age = quote.age_seconds(evaluated_at)
    record(
        "market_data_age",
        RiskCheckOutcome.PASSED
        if quote_age <= Decimal(configuration.maximum_market_data_age_seconds)
        else RiskCheckOutcome.FAILED,
        f"quote age {quote_age}s",
        NoTradeReason.MARKET_DATA_STALE,
    )
    record(
        "evidence_age",
        RiskCheckOutcome.PASSED
        if evidence_age_seconds <= Decimal(configuration.maximum_evidence_age_seconds)
        else RiskCheckOutcome.FAILED,
        f"evidence age {evidence_age_seconds}s",
        NoTradeReason.EVIDENCE_STALE,
    )
    if cost_estimate is None:
        record(
            "cost_estimate",
            RiskCheckOutcome.UNKNOWN,
            "no cost estimate supplied",
            NoTradeReason.COST_ESTIMATE_MISSING,
        )
    else:
        record("cost_estimate", RiskCheckOutcome.PASSED, "cost estimate present", None)

    # --- instrument eligibility -------------------------------------------
    record(
        "instrument_not_prohibited",
        RiskCheckOutcome.PASSED
        if symbol not in configuration.prohibited_instruments
        else RiskCheckOutcome.FAILED,
        f"{symbol} prohibited list membership",
        NoTradeReason.INSTRUMENT_PROHIBITED,
    )
    record(
        "instrument_watchlisted",
        RiskCheckOutcome.PASSED if symbol in configuration.watchlist else RiskCheckOutcome.FAILED,
        f"{symbol} watchlist membership",
        NoTradeReason.INSTRUMENT_NOT_WATCHLISTED,
    )
    record(
        "market_permitted",
        RiskCheckOutcome.PASSED
        if instrument.market in configuration.permitted_markets
        else RiskCheckOutcome.FAILED,
        f"market {instrument.market}",
        NoTradeReason.MARKET_NOT_PERMITTED,
    )
    record(
        "currency_match",
        RiskCheckOutcome.PASSED
        if instrument.currency == configuration.base_currency == account.base_currency
        else RiskCheckOutcome.FAILED,
        f"instrument {instrument.currency} / account {account.base_currency}",
        NoTradeReason.CURRENCY_MISMATCH,
    )

    order_type = configuration.default_order_type
    record(
        "order_type_permitted",
        RiskCheckOutcome.PASSED
        if order_type in configuration.permitted_order_types
        else RiskCheckOutcome.FAILED,
        f"order type {order_type.value}",
        NoTradeReason.ORDER_TYPE_NOT_PERMITTED,
    )

    reference_price = quote.last_trade
    price_ok = reference_price >= configuration.minimum_price and (
        configuration.maximum_price is None or reference_price <= configuration.maximum_price
    )
    record(
        "price_bounds",
        RiskCheckOutcome.PASSED if price_ok else RiskCheckOutcome.FAILED,
        f"reference price {reference_price}",
        NoTradeReason.PRICE_OUTSIDE_BOUNDS,
    )
    record(
        "spread",
        RiskCheckOutcome.PASSED
        if quote.spread_percent <= configuration.maximum_spread_percent
        else RiskCheckOutcome.FAILED,
        f"spread {quote.spread_percent}%",
        NoTradeReason.SPREAD_TOO_WIDE,
    )
    record(
        "liquidity",
        RiskCheckOutcome.PASSED
        if liquidity.average_daily_volume_shares >= configuration.minimum_liquidity_shares
        else RiskCheckOutcome.FAILED,
        f"adv {liquidity.average_daily_volume_shares}",
        NoTradeReason.LIQUIDITY_INSUFFICIENT,
    )
    if cost_estimate is not None:
        record(
            "slippage",
            RiskCheckOutcome.PASSED
            if cost_estimate.estimated_slippage_percent
            <= configuration.maximum_estimated_slippage_percent
            else RiskCheckOutcome.FAILED,
            f"slippage {cost_estimate.estimated_slippage_percent}%",
            NoTradeReason.SLIPPAGE_TOO_HIGH,
        )

    # --- portfolio conflicts ------------------------------------------------
    record(
        "no_existing_position",
        RiskCheckOutcome.PASSED
        if all(position.symbol != symbol for position in positions)
        else RiskCheckOutcome.FAILED,
        f"{len(positions)} open positions",
        NoTradeReason.EXISTING_POSITION_CONFLICT,
    )
    record(
        "no_open_order",
        RiskCheckOutcome.PASSED
        if all(order.symbol != symbol for order in open_orders)
        else RiskCheckOutcome.FAILED,
        f"{len(open_orders)} working orders",
        NoTradeReason.OPEN_ORDER_CONFLICT,
    )
    record(
        "position_count",
        RiskCheckOutcome.PASSED
        if len(positions) < configuration.maximum_simultaneous_positions
        else RiskCheckOutcome.FAILED,
        f"{len(positions)}/{configuration.maximum_simultaneous_positions} positions",
        NoTradeReason.POSITION_LIMIT_REACHED,
    )
    record(
        "daily_loss",
        RiskCheckOutcome.PASSED
        if -account.realized_pnl_today < configuration.maximum_daily_loss
        else RiskCheckOutcome.FAILED,
        f"realized pnl today {account.realized_pnl_today}",
        NoTradeReason.DAILY_LOSS_LIMIT_REACHED,
    )
    record(
        "daily_order_count",
        RiskCheckOutcome.PASSED
        if account.orders_submitted_today < configuration.maximum_daily_order_count
        else RiskCheckOutcome.FAILED,
        f"{account.orders_submitted_today} orders today",
        NoTradeReason.DAILY_ORDER_LIMIT_REACHED,
    )

    # --- sizing -------------------------------------------------------------
    deployable = min(
        configuration.maximum_capital_per_trade,
        configuration.maximum_deployable_capital
        * configuration.maximum_percent_per_trade
        / Decimal("100"),
    )
    spendable_cash = account.cash_available - configuration.minimum_cash_reserve
    record(
        "cash_reserve",
        RiskCheckOutcome.PASSED if spendable_cash > 0 else RiskCheckOutcome.FAILED,
        f"cash {account.cash_available} reserve {configuration.minimum_cash_reserve}",
        NoTradeReason.CASH_RESERVE_BREACHED,
    )
    budget = min(deployable, max(spendable_cash, Decimal("0")))

    limit_price = _limit_price(quote, configuration.limit_price_policy)
    entry_price = limit_price if order_type is OrderType.LIMIT else quote.ask
    quantity = 0
    if entry_price > 0 and budget > 0:
        raw = (budget / entry_price).to_integral_value(rounding=ROUND_DOWN)
        lots = (raw / Decimal(instrument.lot_size)).to_integral_value(rounding=ROUND_DOWN)
        quantity = int(lots) * instrument.lot_size
    record(
        "sized_quantity",
        RiskCheckOutcome.PASSED if quantity > 0 else RiskCheckOutcome.FAILED,
        f"derived quantity {quantity} from budget {budget}",
        NoTradeReason.QUANTITY_ZERO_AFTER_SIZING,
    )

    notional = (Decimal(quantity) * entry_price).quantize(_CENT)
    fees = cost_estimate.commission.quantize(_CENT) if cost_estimate else Decimal("0.00")
    slippage_amount = (
        (notional * cost_estimate.estimated_slippage_percent / Decimal("100")).quantize(_CENT)
        if cost_estimate
        else Decimal("0.00")
    )
    total_cash = notional + fees + slippage_amount
    # There is deliberately no `notional_limit` risk check here. `budget` is
    # already `min(maximum_capital_per_trade, ...)` and both roundings above are
    # downward, so `notional <= maximum_capital_per_trade` holds for every input
    # this engine accepts. A recorded check for it could never report FAILED: it
    # would advertise a refusal the engine cannot make, and would be untestable
    # by construction. The cap is enforced where it binds -- in `deployable` --
    # and the resulting invariant is proved by execution in
    # `TestSizingRespectsTheCapitalCap` rather than asserted by a dead branch.
    record(
        "cash_sufficient",
        RiskCheckOutcome.PASSED if total_cash <= spendable_cash else RiskCheckOutcome.FAILED,
        f"total cash required {total_cash}",
        NoTradeReason.CASH_INSUFFICIENT,
    )

    frozen_checks = tuple(checks)
    if reasons:
        return TradeProposalOutcome(
            proposal=None, no_trade_reason=_first_reason(reasons), risk_checks=frozen_checks
        )

    stop_loss = (
        entry_price * (Decimal("100") - configuration.stop_loss_percent) / Decimal("100")
    ).quantize(_CENT)
    profit_exit = (
        entry_price * (Decimal("100") + configuration.profit_exit_percent) / Decimal("100")
    ).quantize(_CENT)

    draft = _assemble(
        proposal_governance_id=proposal_governance_id,
        evaluation_context_id=evaluation_context_id,
        configuration=configuration,
        symbol=symbol,
        quantity=quantity,
        order_type=order_type,
        limit_price=limit_price if order_type is OrderType.LIMIT else None,
        notional=notional,
        fees=fees,
        slippage_amount=slippage_amount,
        total_cash=total_cash,
        stop_loss=stop_loss,
        profit_exit=profit_exit,
        liquidation_at=liquidation_at.astimezone(UTC),
        created_at=evaluated_at.astimezone(UTC),
        checks=frozen_checks,
    )
    return TradeProposalOutcome(proposal=draft, no_trade_reason=None, risk_checks=frozen_checks)


def _assemble(
    *,
    proposal_governance_id: str,
    evaluation_context_id: str,
    configuration: OperatorTradingConfiguration,
    symbol: str,
    quantity: int,
    order_type: OrderType,
    limit_price: Decimal | None,
    notional: Decimal,
    fees: Decimal,
    slippage_amount: Decimal,
    total_cash: Decimal,
    stop_loss: Decimal,
    profit_exit: Decimal,
    liquidation_at: datetime,
    created_at: datetime,
    checks: tuple[RiskCheck, ...],
) -> TradeProposal:
    """Build the one and only proposal object, already carrying its digest.

    Every term below is passed twice on purpose: once to the digest and once to
    the object. They are the same values in the same call, so the digest a
    proposal carries is always the digest of the proposal it is on -- and
    `__post_init__` validates that, on the real object, with no bypass.
    """
    terms = _AuthorizedTerms(
        proposal_governance_id=proposal_governance_id,
        proposal_version=1,
        evaluation_context_id=evaluation_context_id,
        configuration_governance_id=configuration.configuration_governance_id,
        configuration_version=configuration.configuration_version,
        symbol=symbol,
        side=_BUY_SIDE,
        quantity=quantity,
        order_type=order_type,
        limit_price=limit_price,
        currency=configuration.base_currency,
        estimated_notional=notional,
        estimated_fees=fees,
        estimated_slippage_amount=slippage_amount,
        estimated_total_cash_required=total_cash,
        stop_loss_price=stop_loss,
        profit_exit_price=profit_exit,
        mandatory_liquidation_at=liquidation_at,
        expires_at=created_at + timedelta(seconds=configuration.proposal_expiry_seconds),
    )
    return TradeProposal(
        **terms,
        content_fingerprint=_fingerprint_digest(terms),
        created_at=created_at,
        status=ProposalStatus.PREPARED,
        risk_checks=checks,
    )


def _limit_price(quote: QuoteSnapshot, policy: LimitPricePolicy) -> Decimal:
    if policy is LimitPricePolicy.LAST_TRADE:
        return quote.last_trade.quantize(_CENT)
    if policy is LimitPricePolicy.MID_QUOTE:
        return quote.mid.quantize(_CENT)
    return quote.ask.quantize(_CENT)
