"""MILESTONE-084 -- provider-neutral market and portfolio input contracts.

WHAT THIS IS. The immutable snapshots the proposal engine is allowed to reason
from, and nothing else. Every snapshot carries its own identity, the provider
that produced it, when it was observed, and an explicit freshness computation
against a caller-supplied evaluation instant.

WHY PROVIDER-NEUTRAL. M085 will introduce a real broker and a real market-data
vendor. If the domain depended on a vendor SDK type, swapping or adding a
provider would mean rewriting the decision logic. These types name only what a
long-only intraday decision genuinely needs, so a vendor adapter can be written
later without the domain learning anything about it.

FAIL CLOSED, NEVER COERCE. A missing fee is not zero. A stale quote is not a
current quote. An unknown market status is not "open". A delayed feed is not
real-time. Each of those is a construction-time refusal here, because the only
place a silent coercion can be caught cheaply is at the boundary where the data
enters.

FRESHNESS IS COMPUTED, NEVER ASSERTED. `age_seconds` is derived from
`observed_at` and the evaluation instant the caller supplies from an authorized
time source. No snapshot may declare itself fresh.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum

__all__ = [
    "AccountSnapshot",
    "DataFeedKind",
    "InstrumentMetadata",
    "LiquiditySnapshot",
    "MarketStatus",
    "OpenOrderSnapshot",
    "PositionSnapshot",
    "QuoteSnapshot",
    "SessionSnapshot",
    "TradingCostEstimate",
]

_MAXIMUM_IDENTIFIER_LENGTH = 64
_MAXIMUM_SYMBOL_LENGTH = 32


class MarketStatus(StrEnum):
    """Exchange session status as reported by a calendar provider.

    `UNKNOWN` exists so a provider that cannot answer says so. It is never
    treated as OPEN: the proposal engine refuses to trade an unknown market.
    """

    OPEN = "OPEN"
    CLOSED = "CLOSED"
    HALTED = "HALTED"
    EARLY_CLOSE = "EARLY_CLOSE"
    UNKNOWN = "UNKNOWN"


class DataFeedKind(StrEnum):
    """How a quote was sourced.

    Recorded because a delayed or fixture feed must never be presented as
    real-time. `FIXTURE` is what M084's own deterministic tests and demos use.
    """

    REAL_TIME = "REAL_TIME"
    DELAYED = "DELAYED"
    FIXTURE = "FIXTURE"


def _require_identifier(value: str, *, field: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    if len(value) > _MAXIMUM_IDENTIFIER_LENGTH:
        raise ValueError(f"{field} must be at most {_MAXIMUM_IDENTIFIER_LENGTH} characters")


def _require_symbol(value: str, *, field: str = "symbol") -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    if len(value) > _MAXIMUM_SYMBOL_LENGTH:
        raise ValueError(f"{field} must be at most {_MAXIMUM_SYMBOL_LENGTH} characters")
    if value != value.strip().upper():
        raise ValueError(f"{field} must be upper-case and unpadded: {value!r}")


def _require_aware_instant(value: datetime, *, field: str) -> None:
    if not isinstance(value, datetime):
        raise ValueError(f"{field} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware: a naive instant carries no chronology")


def _require_price(value: Decimal, *, field: str) -> None:
    if not isinstance(value, Decimal):
        raise ValueError(f"{field} must be a Decimal, never a float or a string")
    if not value.is_finite():
        raise ValueError(f"{field} must be finite: NaN and infinity are not prices")
    if value <= 0:
        raise ValueError(f"{field} must be positive")


def _require_non_negative_amount(value: Decimal, *, field: str) -> None:
    if not isinstance(value, Decimal):
        raise ValueError(f"{field} must be a Decimal, never a float or a string")
    if not value.is_finite():
        raise ValueError(f"{field} must be finite")
    if value < 0:
        raise ValueError(f"{field} must not be negative")


def _require_non_negative_int(value: int, *, field: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{field} must be an int")
    if value < 0:
        raise ValueError(f"{field} must not be negative")


def _age_seconds(observed_at: datetime, evaluated_at: datetime, *, label: str) -> Decimal:
    """Seconds between an observation and the evaluation instant.

    A negative age means the snapshot claims to have been observed after the
    evaluation instant. That is refused rather than clamped to zero: it means
    the caller's time source and the provider's disagree, and silently treating
    a future observation as maximally fresh is exactly the coercion this module
    exists to prevent.
    """
    _require_aware_instant(observed_at, field=f"{label}.observed_at")
    _require_aware_instant(evaluated_at, field="evaluated_at")
    delta = (evaluated_at.astimezone(UTC) - observed_at.astimezone(UTC)).total_seconds()
    if delta < 0:
        raise ValueError(
            f"{label} was observed after the evaluation instant; refusing to treat a "
            "future observation as fresh"
        )
    return Decimal(str(delta))


@dataclass(frozen=True, slots=True)
class QuoteSnapshot:
    """One observed top-of-book quote for one instrument."""

    quote_id: str
    provider_id: str
    symbol: str
    bid: Decimal
    ask: Decimal
    last_trade: Decimal
    observed_at: datetime
    feed_kind: DataFeedKind

    def __post_init__(self) -> None:
        _require_identifier(self.quote_id, field="quote_id")
        _require_identifier(self.provider_id, field="provider_id")
        _require_symbol(self.symbol)
        _require_price(self.bid, field="bid")
        _require_price(self.ask, field="ask")
        _require_price(self.last_trade, field="last_trade")
        if self.ask < self.bid:
            raise ValueError("ask must not be below bid: the book is crossed or malformed")
        _require_aware_instant(self.observed_at, field="observed_at")
        if not isinstance(self.feed_kind, DataFeedKind):
            raise ValueError("feed_kind must be a DataFeedKind")

    @property
    def mid(self) -> Decimal:
        return (self.bid + self.ask) / Decimal("2")

    @property
    def spread(self) -> Decimal:
        return self.ask - self.bid

    @property
    def spread_percent(self) -> Decimal:
        """Spread as a percentage of the mid price."""
        return (self.spread / self.mid) * Decimal("100")

    def age_seconds(self, evaluated_at: datetime) -> Decimal:
        return _age_seconds(self.observed_at, evaluated_at, label="quote")


@dataclass(frozen=True, slots=True)
class AccountSnapshot:
    """Cash and equity as reported by the account provider."""

    account_snapshot_id: str
    provider_id: str
    account_reference: str
    base_currency: str
    cash_available: Decimal
    equity_total: Decimal
    realized_pnl_today: Decimal
    orders_submitted_today: int
    observed_at: datetime

    def __post_init__(self) -> None:
        _require_identifier(self.account_snapshot_id, field="account_snapshot_id")
        _require_identifier(self.provider_id, field="provider_id")
        _require_identifier(self.account_reference, field="account_reference")
        if not isinstance(self.base_currency, str) or len(self.base_currency) != 3:
            raise ValueError("base_currency must be a 3-letter ISO code")
        if self.base_currency != self.base_currency.upper():
            raise ValueError("base_currency must be upper-case")
        _require_non_negative_amount(self.cash_available, field="cash_available")
        _require_non_negative_amount(self.equity_total, field="equity_total")
        if not isinstance(self.realized_pnl_today, Decimal):
            raise ValueError("realized_pnl_today must be a Decimal")
        if not self.realized_pnl_today.is_finite():
            raise ValueError("realized_pnl_today must be finite")
        _require_non_negative_int(self.orders_submitted_today, field="orders_submitted_today")
        _require_aware_instant(self.observed_at, field="observed_at")

    def age_seconds(self, evaluated_at: datetime) -> Decimal:
        return _age_seconds(self.observed_at, evaluated_at, label="account")


@dataclass(frozen=True, slots=True)
class PositionSnapshot:
    """One currently held position.

    Quantity is non-negative by construction: a negative quantity would be a
    short position, which this product does not permit and will not silently
    normalize into a long one.
    """

    symbol: str
    quantity: int
    average_price: Decimal

    def __post_init__(self) -> None:
        _require_symbol(self.symbol)
        if isinstance(self.quantity, bool) or not isinstance(self.quantity, int):
            raise ValueError("quantity must be an int")
        if self.quantity < 0:
            raise ValueError(
                "quantity must not be negative: a short position cannot be represented, "
                "and must not be coerced into a long one"
            )
        _require_price(self.average_price, field="average_price")


@dataclass(frozen=True, slots=True)
class OpenOrderSnapshot:
    """One order already working at the broker."""

    order_reference: str
    symbol: str
    side: str
    quantity: int

    def __post_init__(self) -> None:
        _require_identifier(self.order_reference, field="order_reference")
        _require_symbol(self.symbol)
        if self.side not in {"BUY", "SELL"}:
            raise ValueError("side must be BUY or SELL")
        if isinstance(self.quantity, bool) or not isinstance(self.quantity, int):
            raise ValueError("quantity must be an int")
        if self.quantity <= 0:
            raise ValueError("quantity must be positive")


@dataclass(frozen=True, slots=True)
class SessionSnapshot:
    """Exchange calendar status for one market."""

    session_id: str
    provider_id: str
    market: str
    status: MarketStatus
    observed_at: datetime

    def __post_init__(self) -> None:
        _require_identifier(self.session_id, field="session_id")
        _require_identifier(self.provider_id, field="provider_id")
        _require_symbol(self.market, field="market")
        if not isinstance(self.status, MarketStatus):
            raise ValueError("status must be a MarketStatus")
        _require_aware_instant(self.observed_at, field="observed_at")

    @property
    def is_tradeable(self) -> bool:
        """Only an explicitly OPEN market is tradeable.

        EARLY_CLOSE is excluded deliberately: an early close shortens the window
        in which a mandatory intraday liquidation must still be achievable, and
        this milestone does not model that shortened window.
        """
        return self.status is MarketStatus.OPEN

    def age_seconds(self, evaluated_at: datetime) -> Decimal:
        return _age_seconds(self.observed_at, evaluated_at, label="session")


@dataclass(frozen=True, slots=True)
class InstrumentMetadata:
    """Static-ish facts about a tradeable instrument."""

    symbol: str
    market: str
    currency: str
    is_fractionable: bool
    lot_size: int

    def __post_init__(self) -> None:
        _require_symbol(self.symbol)
        _require_symbol(self.market, field="market")
        if not isinstance(self.currency, str) or len(self.currency) != 3:
            raise ValueError("currency must be a 3-letter ISO code")
        if self.currency != self.currency.upper():
            raise ValueError("currency must be upper-case")
        if not isinstance(self.is_fractionable, bool):
            raise ValueError("is_fractionable must be a bool")
        if isinstance(self.lot_size, bool) or not isinstance(self.lot_size, int):
            raise ValueError("lot_size must be an int")
        if self.lot_size < 1:
            raise ValueError("lot_size must be at least 1")


@dataclass(frozen=True, slots=True)
class LiquiditySnapshot:
    """Observed liquidity for one instrument."""

    symbol: str
    average_daily_volume_shares: int
    observed_at: datetime

    def __post_init__(self) -> None:
        _require_symbol(self.symbol)
        _require_non_negative_int(
            self.average_daily_volume_shares, field="average_daily_volume_shares"
        )
        _require_aware_instant(self.observed_at, field="observed_at")

    def age_seconds(self, evaluated_at: datetime) -> Decimal:
        return _age_seconds(self.observed_at, evaluated_at, label="liquidity")


@dataclass(frozen=True, slots=True)
class TradingCostEstimate:
    """Estimated cost of one trade.

    Every component is required. A missing fee estimate is not zero: it is a
    reason to refuse to propose, and the proposal engine treats the absence of
    this snapshot exactly that way.
    """

    estimate_id: str
    provider_id: str
    symbol: str
    commission: Decimal
    estimated_slippage_percent: Decimal
    observed_at: datetime

    def __post_init__(self) -> None:
        _require_identifier(self.estimate_id, field="estimate_id")
        _require_identifier(self.provider_id, field="provider_id")
        _require_symbol(self.symbol)
        _require_non_negative_amount(self.commission, field="commission")
        _require_non_negative_amount(
            self.estimated_slippage_percent, field="estimated_slippage_percent"
        )
        if self.estimated_slippage_percent > Decimal("100"):
            raise ValueError("estimated_slippage_percent must not exceed 100")
        _require_aware_instant(self.observed_at, field="observed_at")

    def age_seconds(self, evaluated_at: datetime) -> Decimal:
        return _age_seconds(self.observed_at, evaluated_at, label="cost estimate")
