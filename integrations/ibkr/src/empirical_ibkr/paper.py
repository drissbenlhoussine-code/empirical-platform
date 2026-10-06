# The optional official SDK has dynamic payloads and mandated callback names.
# ruff: noqa: ANN401
"""Direct-route Helsinki adapter using the official TWS API, disabled for writes by default."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from empirical_ibkr.session import (
    IBKROwnerSetupRequiredError,
    IBKRSession,
)
from empirical_platform.decision_candidate.market_access_ports import (
    AccountTruth,
    DispatchRecord,
    PositionsSnapshot,
    PositionTruth,
    ResolvedContract,
)
from empirical_platform.decision_candidate.market_identity import (
    BrokerIdentity,
    Currency,
    InstrumentIdentity,
    MarketQuote,
    PaperAccountIdentity,
)
from empirical_platform.decision_candidate.market_plan import MarketPlan, OrderPurpose, OrderTruth


def _contract(instrument: InstrumentIdentity | None = None, *, symbol: str = "") -> Any:
    try:
        from ibapi.contract import Contract  # type: ignore[import-not-found]
    except ImportError as error:
        raise IBKROwnerSetupRequiredError("official TWS API SDK required") from error
    contract = Contract()
    contract.symbol = instrument.symbol if instrument else symbol
    contract.secType = "STK"
    contract.currency = "EUR"
    contract.exchange = "HEX"
    contract.primaryExchange = "HEX"
    if instrument:
        if instrument.broker is not BrokerIdentity.IBKR_PAPER:
            raise ValueError("cross-broker contract refused")
        contract.conId = int(instrument.contract_id)
    return contract


def liquid_interval(
    value: str, timezone: str, now: datetime
) -> tuple[datetime | None, datetime | None]:
    if timezone not in ("Europe/Helsinki", "EET"):
        raise ValueError("unexpected Helsinki contract timezone")
    zone = ZoneInfo("Europe/Helsinki")
    intervals = []
    for day in value.split(";"):
        if day.endswith(":CLOSED"):
            continue
        for interval in day.split(","):
            pieces = interval.split("-")
            if len(pieces) != 2:
                raise ValueError("unrecognized liquid-hours format")
            start, end = (datetime.strptime(p, "%Y%m%d:%H%M").replace(tzinfo=zone) for p in pieces)
            if start.date() == now.astimezone(zone).date():
                intervals.append((start, end))
    if not intervals:
        return None, None  # Contract discovery remains possible while entry stays closed.
    if len(intervals) != 1:
        raise ValueError("contract liquid hours do not prove one session for this date")
    return intervals[0]


class IBKRPaperAdapter:
    def __init__(self, session: IBKRSession, *, allow_approved_writes: bool = False) -> None:
        self._session = session
        self._identity = PaperAccountIdentity(
            BrokerIdentity.IBKR_PAPER, session.account_id, Currency.EUR, session.client_id
        )
        self._allow_writes = allow_approved_writes
        self._resolved: dict[str, ResolvedContract] = {}

    @property
    def identity(self) -> PaperAccountIdentity:
        return self._identity

    def now(self) -> datetime:
        rows = self._session.request("clock")
        if len(rows) != 1:
            raise ValueError("ambiguous broker clock")
        return datetime.fromtimestamp(rows[0], UTC)

    def resolve(self, symbol: str) -> ResolvedContract:
        rows = self._session.request("contract", _contract(symbol=symbol))
        if len(rows) != 1:
            raise ValueError("symbol is missing or ambiguous; contract resolution required")
        details = rows[0]
        contract = details.contract
        instrument = InstrumentIdentity(
            BrokerIdentity.IBKR_PAPER,
            str(contract.conId),
            contract.symbol,
            "XHEL",
            contract.exchange,
            contract.primaryExchange,
            Currency(contract.currency),
            contract.secType,
        )
        if instrument.symbol != symbol:
            raise ValueError("resolved symbol differs from requested symbol")
        now = self.now()
        opens, closes = liquid_interval(details.liquidHours, details.timeZoneId, now)
        tick = Decimal(str(details.minTick))
        if not tick.is_finite() or tick <= 0:
            raise ValueError("contract tick missing")
        result = ResolvedContract(instrument, tick, opens, closes, now)
        self._resolved[instrument.contract_id] = result
        return result

    def _known(self, contract: Any) -> InstrumentIdentity:
        known = self._resolved.get(str(contract.conId))
        if known is None:
            raise ValueError("unresolved contract in broker state; refuse rather than guess")
        item = known.instrument
        if (contract.symbol, contract.currency, contract.secType) != (
            item.symbol,
            item.currency,
            item.security_type,
        ):
            raise ValueError("broker contract identity mismatch")
        for value in (contract.exchange, contract.primaryExchange):
            if value and value != "HEX":
                raise ValueError("wrong exchange in broker state")
        return item

    def quote(self, instrument: InstrumentIdentity) -> MarketQuote:
        if (
            instrument.contract_id not in self._resolved
            or self._resolved[instrument.contract_id].instrument != instrument
        ):
            raise ValueError("quote requires exact resolved contract")
        rows = self._session.request("quote", _contract(instrument))
        if not rows:
            raise ValueError("no live bid/ask")
        timestamp, bid, ask, received_at = rows[-1]
        # Tick-by-tick has exchange timestamps and does not support delayed data.
        return MarketQuote(
            instrument,
            Decimal(bid),
            Decimal(ask),
            datetime.fromtimestamp(timestamp, UTC),
            received_at,
            True,
        )

    def account(self) -> AccountTruth:
        rows = self._session.request("account")
        values: dict[str, str] = {}
        readiness: set[str] = set()
        for account, tag, value, currency in rows:
            if account != self.identity.account:
                raise ValueError("account identity mismatch")
            if tag.lower() == "accountready":
                readiness.add(value.lower())
            if currency == "EUR":
                if tag in values and values[tag] != value:
                    raise ValueError("conflicting account evidence")
                values[tag] = value
        # Never interpret BASE or another currency as EUR, even for an EUR trade.
        required = ("CashBalance", "NetLiquidationByCurrency", "RealizedPnL")
        if any(key not in values for key in required):
            raise IBKROwnerSetupRequiredError(
                "explicit EUR cash, equity and realized P&L evidence required"
            )
        cash, equity, pnl = (Decimal(values[key]) for key in required)
        if any(not v.is_finite() for v in (cash, equity, pnl)) or cash < 0 or equity < 0:
            raise ValueError("invalid account balances")
        if readiness != {"true"}:
            raise IBKROwnerSetupRequiredError("explicit ready account evidence required")
        return AccountTruth(self.identity, cash, equity, pnl, datetime.now(UTC), True)

    def positions(self) -> tuple[PositionTruth, ...]:
        result = []
        for account, contract, quantity in self._session.request("positions"):
            if account != self.identity.account:
                raise ValueError("position account mismatch")
            amount = Decimal(quantity)
            if not amount.is_finite() or amount < 0:
                raise ValueError("short or invalid position refused")
            if amount:
                result.append(
                    PositionTruth(self.identity, self._known(contract), amount, datetime.now(UTC))
                )
        return tuple(result)

    def last_trade(self, instrument: InstrumentIdentity) -> tuple[Decimal, datetime]:
        if (
            self._resolved.get(instrument.contract_id) is None
            or self._resolved[instrument.contract_id].instrument != instrument
        ):
            raise ValueError("resolved instrument required")
        rows = self._session.request("last", _contract(instrument))
        if len(rows) != 1:
            raise ValueError("one live last-trade observation required")
        timestamp, price, exchange, conditions = rows[0]
        amount = Decimal(price)
        if exchange != "HEX" or conditions or not amount.is_finite() or amount <= 0:
            raise ValueError("unverified last trade")
        return amount, datetime.fromtimestamp(timestamp, UTC)

    def positions_snapshot(self) -> PositionsSnapshot:
        positions = self.positions()
        return PositionsSnapshot(self.identity, positions, datetime.now(UTC))

    def average_daily_volume(self, instrument: InstrumentIdentity) -> tuple[int, datetime]:
        if (
            self._resolved.get(instrument.contract_id) is None
            or self._resolved[instrument.contract_id].instrument != instrument
        ):
            raise ValueError("exact resolved instrument required for bars")
        rows = self._session.request("bars", _contract(instrument))
        now = datetime.now(UTC)
        today = now.astimezone(ZoneInfo("Europe/Helsinki")).date()
        completed: dict[str, Decimal] = {}
        for day, raw in rows:
            parsed = datetime.strptime(day, "%Y%m%d").date()
            volume = Decimal(raw)
            if not volume.is_finite() or volume < 0 or day in completed:
                raise ValueError("invalid or duplicate volume evidence")
            if parsed < today:
                completed[day] = volume
        recent = sorted(completed)[-20:]
        if len(recent) != 20 or (today - datetime.strptime(recent[-1], "%Y%m%d").date()).days > 7:
            raise ValueError("twenty recent completed daily bars required")
        return int(sum((completed[d] for d in recent), Decimal("0")) / 20), now

    def _order(self, row: Any, executions: list[Any]) -> OrderTruth:
        order_id, contract, order, state = row
        if order.clientId != self.identity.client_id:
            raise ValueError("order belongs to another API client; refuse attribution")
        if order.account != self.identity.account or order.action not in ("BUY", "SELL"):
            raise ValueError("order account/side mismatch")
        instrument = self._known(contract)
        filled = Decimal("0")
        average = None
        seen: dict[str, tuple[str, str]] = {}
        notional = Decimal("0")
        for execution_contract, execution in executions:
            if execution.permId != order.permId:
                continue
            if (
                execution.acctNumber != self.identity.account
                or self._known(execution_contract) != instrument
                or execution.orderRef != order.orderRef
                or execution.side != ("BOT" if order.action == "BUY" else "SLD")
            ):
                raise ValueError("execution identity mismatch")
            if execution.execId not in seen:
                shares = Decimal(str(execution.shares))
                price = Decimal(str(execution.price))
                if not shares.is_finite() or not price.is_finite() or shares <= 0 or price <= 0:
                    raise ValueError("invalid execution")
                filled += shares
                notional += shares * price
                seen[execution.execId] = (str(execution.shares), str(execution.price))
            elif seen[execution.execId] != (str(execution.shares), str(execution.price)):
                raise ValueError("conflicting execution correction requires reconciliation")
        if filled:
            average = notional / filled
        quantity = Decimal(str(order.totalQuantity))
        statuses = {
            "PendingSubmit": "WORKING",
            "PreSubmitted": "WORKING",
            "Submitted": "WORKING",
            "PendingCancel": "WORKING",
            "Filled": "FILLED",
            "Cancelled": "CANCELED",
            "ApiCancelled": "CANCELED",
            "Inactive": "UNKNOWN",
        }
        status = statuses.get(state.status, "UNKNOWN")
        if filled and filled < quantity and status == "WORKING":
            status = "PARTIAL"
        return OrderTruth(
            instrument,
            self.identity,
            order.orderRef,
            order_id,
            order.permId,
            OrderPurpose.ENTRY if order.action == "BUY" else OrderPurpose.CLOSE,
            quantity,
            filled,
            average,
            status,
            datetime.now(UTC),
        )

    def _executions(self) -> list[Any]:
        from ibapi.execution import ExecutionFilter  # type: ignore[import-not-found]

        query = ExecutionFilter()
        query.acctCode = self.identity.account
        return self._session.request("executions", query)

    def open_orders(self) -> tuple[OrderTruth, ...]:
        rows = self._session.request("orders")
        executions = self._executions()
        return tuple(self._order(row, executions) for row in rows)

    def reconcile(self, plan: MarketPlan, record: DispatchRecord) -> OrderTruth | None:
        rows = self._session.request("orders") + self._session.request("completed")
        matches = [row for row in rows if row[2].orderRef == record.reference]
        by_permanent = {row[2].permId: row for row in matches}
        if len(by_permanent) > 1:
            raise ValueError("duplicate broker orders require Owner reconciliation")
        if not matches:
            return None  # missing history is UNKNOWN, never permission to retry
        truth = self._order(next(iter(by_permanent.values())), self._executions())
        truth.require_matches(plan, record.purpose, record.order_id)
        return truth

    def next_order_id(self) -> int:
        return self._session.next_order_id()

    def send_bound(
        self, plan: MarketPlan, record: DispatchRecord, *, before_send: Callable[[], None]
    ) -> None:
        self._session.require_connected()
        if not self._allow_writes:
            raise ValueError("IBKR adapter is read-only until Owner deployment approval")
        if plan.account != self.identity or record.reference != plan.order_reference(
            record.purpose
        ):
            raise ValueError("dispatch route mismatch")
        if record.plan_id != plan.plan_id or record.state != "CLAIMED":
            raise ValueError("durable dispatch claim required")
        if not 0 < record.quantity <= plan.risk.quantity:
            raise ValueError("quantity bound violated")
        if record.purpose is OrderPurpose.ENTRY:
            if (
                record.quantity != plan.risk.quantity
                or record.limit_price != plan.risk.entry_ceiling
            ):
                raise ValueError("approved entry terms changed")
            plan.risk.__post_init__()
        elif record.purpose is OrderPurpose.CLOSE:
            positions = self.positions()
            if (
                len(positions) != 1
                or positions[0].instrument != plan.instrument
                or positions[0].quantity != record.quantity
            ):
                raise ValueError("full attributable long position must still exist before close")
        else:
            raise ValueError("unsupported side")
        from ibapi.order import Order  # type: ignore[import-not-found]

        order = Order()
        order.account = self.identity.account
        order.action = "BUY" if record.purpose is OrderPurpose.ENTRY else "SELL"
        order.orderType = "LMT"
        order.totalQuantity = record.quantity
        order.lmtPrice = float(record.limit_price)
        if Decimal(str(order.lmtPrice)) != record.limit_price:
            raise ValueError("SDK price conversion would change immutable terms")
        order.tif = "DAY"
        order.outsideRth = False
        order.orderRef = record.reference
        order.transmit = True
        contract = _contract(plan.instrument)
        before_send()
        self._session.require_connected()
        self._session._client.placeOrder(record.order_id, contract, order)

    def cancel_bound(self, plan: MarketPlan, record: DispatchRecord) -> None:
        # No generic cancellation surface: uncertain/foreign orders are never canceled.
        if not self._allow_writes or plan.account != self.identity:
            raise ValueError("cancellation not permitted")
        truth = self.reconcile(plan, record)
        if truth is None or truth.status not in ("WORKING", "PARTIAL"):
            raise ValueError("only positively identified working order can be canceled")
        self._session.require_connected()
        from ibapi.order_cancel import OrderCancel  # type: ignore[import-not-found]

        self._session._client.cancelOrder(record.order_id, OrderCancel())
