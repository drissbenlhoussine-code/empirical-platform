"""Portfolio-level entry limits, judged at the PAPER submission boundary (fix D1).

`maximum_daily_loss`, `maximum_daily_order_count`, `maximum_simultaneous_positions` and
the total-exposure ceiling (`maximum_deployable_capital`) used to be judged only in the
Prepare path, against an account snapshot whose `realized_pnl_today` and
`orders_submitted_today` were hardcoded zeros, and a position list that only saw the one
target symbol. They therefore always passed. This module is the pure decision those
numbers feed, evaluated at the LAST controllable boundary before an ENTRY order leaves
(`usecases.paper_execution`, inside `before_send`), on FRESH broker reads and durable
local order history. Nothing here performs I/O.

FAIL CLOSED, EVERYWHERE. Evidence that is missing, unparseable or odd is a refusal, never
a zero: a missing `last_equity` is not "no loss today", an order without a limit price is
not "no exposure". These limits apply to ENTRY orders only; risk-reducing exits
(`usecases.position_exit`) never pass through this module and are never blocked by it.

DAILY P&L PROXY. The broker reports `equity` (now) and `last_equity` (equity at the
previous session close). `equity - last_equity` therefore includes UNREALIZED gains and
losses. That is deliberately conservative for a loss limit (an open position that is deep
under water blocks further entries) and is the only P&L figure the broker states
authoritatively; the product does not re-derive realized P&L from fills.

DAILY ORDER COUNT. Durable local truth: entry attempts claimed in the market's trading day
(America/New_York calendar day) that were actually sent or may have been sent, counted
INCLUDING the order being sent. An attempt counts once it has been admitted by the atomic
ledger (`ExecutionAttemptRepository.admit_entry`), or -- for attempts that predate the
ledger -- once it reached a post-send state. An attempt that was closed REJECTED/NOT_SENT
(nothing left the process) does not count.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo

from empirical_platform.decision_candidate.operator_trading_configuration import (
    OperatorTradingConfiguration,
)

__all__ = [
    "ENTRY_ADMITTED_EVENT_TYPE",
    "MARKET_TIMEZONE",
    "EntryLedgerRow",
    "PortfolioEvidence",
    "PortfolioEvidenceError",
    "PortfolioLimits",
    "PortfolioPosition",
    "PortfolioWorkingBuy",
    "admission_event_id",
    "decode_admission_detail",
    "encode_admission_detail",
    "ledger_counts_order",
    "ledger_order_in_flight",
    "portfolio_limit_refusal",
    "portfolio_limits_from_configuration",
    "read_portfolio_evidence",
    "trading_day_bounds",
]

#: The market's calendar. The daily limits reset at midnight here, not in UTC and not in
#: the operator's timezone.
MARKET_TIMEZONE = "America/New_York"

#: The durable "this entry attempt passed the limits and was admitted to send" marker,
#: stored as an append-only `paper_execution_event` row written under the day lock.
ENTRY_ADMITTED_EVENT_TYPE = "ENTRY_ADMITTED"

_NOT_SENT_FAILURE_CODE = "NOT_SENT"
#: States in which the broker has certainly (or possibly) received the order.
_POST_SEND_STATES = frozenset(
    {
        "PAPER_SUBMITTED",
        "PAPER_ACCEPTED",
        "PARTIALLY_FILLED",
        "FILLED",
        "CANCEL_REQUESTED",
        "CANCELED",
        "EXPIRED",
        "SUBMISSION_UNKNOWN",
    }
)
#: States in which an admitted order may not yet be visible in the broker's position or
#: working-order lists.
_IN_FLIGHT_STATES = frozenset({"DISPATCH_CLAIMED", "SUBMISSION_IN_PROGRESS", "SUBMISSION_UNKNOWN"})


class PortfolioEvidenceError(ValueError):
    """Broker portfolio evidence that is missing, malformed or odd. Always a refusal."""


def _finite_decimal(value: object, *, field: str) -> Decimal:
    # The broker states every amount as a decimal STRING. A number, a bool or None is odd.
    if not isinstance(value, str):
        raise PortfolioEvidenceError(f"{field} is missing or not a decimal string")
    try:
        parsed = Decimal(value)
    except InvalidOperation as error:
        raise PortfolioEvidenceError(f"{field} is not a valid decimal") from error
    if not parsed.is_finite():
        raise PortfolioEvidenceError(f"{field} is not finite")
    return parsed


@dataclass(frozen=True, slots=True)
class PortfolioLimits:
    """The four portfolio ceilings of ONE immutable configuration version."""

    maximum_daily_loss: Decimal
    maximum_daily_order_count: int
    maximum_simultaneous_positions: int
    maximum_deployable_capital: Decimal

    def __post_init__(self) -> None:
        for name in ("maximum_daily_loss", "maximum_deployable_capital"):
            value = getattr(self, name)
            if not isinstance(value, Decimal) or not value.is_finite() or value <= 0:
                raise ValueError(f"{name} must be a positive finite Decimal")
        for name in ("maximum_daily_order_count", "maximum_simultaneous_positions"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ValueError(f"{name} must be a positive int")


def portfolio_limits_from_configuration(
    configuration: OperatorTradingConfiguration,
) -> PortfolioLimits:
    return PortfolioLimits(
        maximum_daily_loss=configuration.maximum_daily_loss,
        maximum_daily_order_count=configuration.maximum_daily_order_count,
        maximum_simultaneous_positions=configuration.maximum_simultaneous_positions,
        maximum_deployable_capital=configuration.maximum_deployable_capital,
    )


@dataclass(frozen=True, slots=True)
class PortfolioPosition:
    symbol: str
    quantity: Decimal
    market_value: Decimal


@dataclass(frozen=True, slots=True)
class PortfolioWorkingBuy:
    client_order_id: str
    symbol: str
    #: Remaining quantity times the limit price: the most this order can still add.
    notional: Decimal


@dataclass(frozen=True, slots=True)
class PortfolioEvidence:
    """Everything the broker said about the whole account, read fresh."""

    equity: Decimal
    last_equity: Decimal
    positions: tuple[PortfolioPosition, ...]
    working_buys: tuple[PortfolioWorkingBuy, ...]

    @property
    def daily_pnl(self) -> Decimal:
        """`equity - last_equity`; includes unrealized P&L (conservative for a loss cap)."""
        return self.equity - self.last_equity


def read_portfolio_evidence(
    *,
    account_payload: object,
    positions: Iterable[object],
    open_orders: Iterable[object],
) -> PortfolioEvidence:
    """Strictly parse the three broker reads. Raises `PortfolioEvidenceError` on anything odd."""
    if not isinstance(account_payload, dict):
        raise PortfolioEvidenceError("the account payload is not an object")
    equity = _finite_decimal(account_payload.get("equity"), field="account equity")
    last_equity = _finite_decimal(account_payload.get("last_equity"), field="account last_equity")
    if equity < 0 or last_equity < 0:
        raise PortfolioEvidenceError("account equity or last_equity is negative")

    parsed_positions: list[PortfolioPosition] = []
    seen: set[str] = set()
    for view in positions:
        symbol = getattr(view, "symbol", None)
        if not isinstance(symbol, str) or not symbol.strip():
            raise PortfolioEvidenceError("a broker position has no symbol")
        if symbol in seen:
            raise PortfolioEvidenceError(f"the broker listed {symbol} twice")
        seen.add(symbol)
        parsed_positions.append(
            PortfolioPosition(
                symbol=symbol,
                quantity=_finite_decimal(getattr(view, "quantity", None), field=f"{symbol} qty"),
                market_value=_finite_decimal(
                    getattr(view, "market_value", None), field=f"{symbol} market_value"
                ),
            )
        )

    working: list[PortfolioWorkingBuy] = []
    for order in open_orders:
        symbol = getattr(order, "symbol", None)
        side = getattr(order, "side", None)
        client_order_id = getattr(order, "client_order_id", None)
        if not isinstance(symbol, str) or not symbol.strip():
            raise PortfolioEvidenceError("a working order has no symbol")
        if not isinstance(client_order_id, str) or not client_order_id:
            raise PortfolioEvidenceError(f"a working {symbol} order has no client_order_id")
        if not isinstance(side, str) or side.lower() not in {"buy", "sell"}:
            raise PortfolioEvidenceError(f"a working {symbol} order has an unreadable side")
        if side.lower() == "sell":
            continue  # risk-reducing; adds neither a position nor exposure
        quantity = _finite_decimal(getattr(order, "quantity", None), field=f"{symbol} order qty")
        filled = _finite_decimal(
            getattr(order, "filled_quantity", None), field=f"{symbol} order filled_qty"
        )
        limit_price = getattr(order, "limit_price", None)
        if limit_price is None:
            raise PortfolioEvidenceError(
                f"a working BUY order for {symbol} has no limit price; "
                "its exposure cannot be bounded"
            )
        price = _finite_decimal(limit_price, field=f"{symbol} order limit_price")
        if quantity <= 0 or price <= 0 or filled < 0 or filled > quantity:
            raise PortfolioEvidenceError(f"a working BUY order for {symbol} has odd quantities")
        working.append(
            PortfolioWorkingBuy(
                client_order_id=client_order_id,
                symbol=symbol,
                notional=(quantity - filled) * price,
            )
        )
    return PortfolioEvidence(
        equity=equity,
        last_equity=last_equity,
        positions=tuple(parsed_positions),
        working_buys=tuple(working),
    )


@dataclass(frozen=True, slots=True)
class EntryLedgerRow:
    """One entry attempt claimed in a trading day, as durable local truth records it."""

    attempt_id: str
    client_order_id: str
    state: str
    failure_code: str | None
    #: True when the atomic ledger admitted this attempt (it carries a marker).
    admitted: bool
    symbol: str | None
    notional: Decimal | None


def ledger_counts_order(row: EntryLedgerRow) -> bool:
    """Does this attempt count against the daily order cap?"""
    if row.state == "REJECTED" and row.failure_code == _NOT_SENT_FAILURE_CODE:
        return False  # closed before the request left: nothing was sent
    if row.admitted:
        return True
    # Predates the ledger (or was never admitted). Count it only when it demonstrably
    # reached the broker; a claimed-but-not-yet-admitted concurrent attempt must not.
    return row.state in _POST_SEND_STATES or (
        row.state == "REJECTED" and row.failure_code != _NOT_SENT_FAILURE_CODE
    )


def ledger_order_in_flight(row: EntryLedgerRow) -> bool:
    """Admitted, and possibly not yet visible in the broker's positions / working orders."""
    return row.admitted and ledger_counts_order(row) and row.state in _IN_FLIGHT_STATES


def admission_event_id(attempt_id: str) -> str:
    """The deterministic event id of an attempt's admission marker (one per attempt, ever)."""
    import hashlib

    return "EVT-ADM-" + hashlib.sha256(attempt_id.encode("utf-8")).hexdigest()[:40]


def encode_admission_detail(*, symbol: str, notional: Decimal, client_order_id: str) -> str:
    return f"symbol={symbol};notional={notional};client_order_id={client_order_id}"


def decode_admission_detail(detail: str) -> tuple[str, Decimal, str]:
    """Strict inverse of `encode_admission_detail`. Raises `PortfolioEvidenceError`."""
    fields: dict[str, str] = {}
    for part in detail.split(";"):
        key, separator, value = part.partition("=")
        if not separator or key in fields:
            raise PortfolioEvidenceError("an entry-admission record is unreadable")
        fields[key] = value
    if set(fields) != {"symbol", "notional", "client_order_id"} or not fields["symbol"]:
        raise PortfolioEvidenceError("an entry-admission record is unreadable")
    notional = _finite_decimal(fields["notional"], field="admission notional")
    if notional < 0:
        raise PortfolioEvidenceError("an entry-admission record is unreadable")
    return fields["symbol"], notional, fields["client_order_id"]


def trading_day_bounds(instant: datetime) -> tuple[datetime, datetime]:
    """The UTC `[start, end)` of the America/New_York calendar day containing `instant`."""
    if instant.tzinfo is None:
        raise ValueError("instant must be timezone-aware")
    zone = ZoneInfo(MARKET_TIMEZONE)
    local_day = instant.astimezone(zone).date()
    start = datetime.combine(local_day, time.min, tzinfo=zone)
    end = datetime.combine(local_day + timedelta(days=1), time.min, tzinfo=zone)
    return start.astimezone(UTC), end.astimezone(UTC)


def portfolio_limit_refusal(
    *,
    limits: PortfolioLimits | None,
    portfolio: PortfolioEvidence | None,
    ledger: Sequence[EntryLedgerRow] | None,
    attempt_id: str,
    client_order_id: str,
    symbol: str,
    order_notional: Decimal,
) -> str | None:
    """The first portfolio limit this ENTRY order would breach, or None if none is.

    `ledger` is the trading day's entry attempts; the row of `attempt_id` itself is
    ignored and the order being sent is added to every count and to the exposure.
    """
    if limits is None or portfolio is None or ledger is None:
        return (
            "portfolio risk evidence (limits, broker portfolio, order history) is missing; "
            "entry refused"
        )
    if not isinstance(order_notional, Decimal) or not order_notional.is_finite():
        return "the order's notional is not a finite Decimal; entry refused"

    # 1. Daily loss (equity - last_equity; includes unrealized).
    loss = -portfolio.daily_pnl
    if loss >= limits.maximum_daily_loss:
        return (
            f"daily loss limit reached: equity-based loss today {loss} >= "
            f"maximum_daily_loss {limits.maximum_daily_loss}"
        )

    others = [row for row in ledger if row.attempt_id != attempt_id]

    # 2. Daily order count, INCLUDING this order.
    orders_today = sum(1 for row in others if ledger_counts_order(row)) + 1
    if orders_today > limits.maximum_daily_order_count:
        return (
            f"daily order count limit reached: {orders_today} orders today including this "
            f"one > maximum_daily_order_count {limits.maximum_daily_order_count}"
        )

    working = [w for w in portfolio.working_buys if w.client_order_id != client_order_id]
    visible_ids = {w.client_order_id for w in portfolio.working_buys}
    in_flight = [
        row
        for row in others
        if ledger_order_in_flight(row) and row.client_order_id not in visible_ids
    ]

    # 3. Simultaneous positions: held + working BUY + in-flight admitted, plus this symbol.
    symbols = {p.symbol for p in portfolio.positions if p.quantity != 0}
    symbols.update(w.symbol for w in working)
    symbols.update(row.symbol for row in in_flight if row.symbol is not None)
    symbols.add(symbol)
    if len(symbols) > limits.maximum_simultaneous_positions:
        return (
            f"simultaneous position limit reached: {len(symbols)} symbols held or working "
            f"including {symbol} > maximum_simultaneous_positions "
            f"{limits.maximum_simultaneous_positions}"
        )

    # 4. Total exposure: |held market value| + working BUY notional + in-flight + this order.
    exposure = (
        sum((abs(p.market_value) for p in portfolio.positions), Decimal(0))
        + sum((w.notional for w in working), Decimal(0))
        + sum((row.notional or Decimal(0) for row in in_flight), Decimal(0))
        + order_notional
    )
    if exposure > limits.maximum_deployable_capital:
        return (
            f"total exposure limit reached: {exposure} including this order > "
            f"maximum_deployable_capital {limits.maximum_deployable_capital}"
        )
    return None
