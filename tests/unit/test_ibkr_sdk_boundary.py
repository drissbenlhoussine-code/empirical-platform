"""Deterministic SDK callback doubles: no socket, account or broker is contacted."""

# SDK callback signatures and intentionally dynamic test payloads.
# ruff: noqa: ANN401, N802, N803
from __future__ import annotations

import sys
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest
from empirical_ibkr.paper import IBKRPaperAdapter, _contract
from empirical_ibkr.session import (
    IBKROwnerSetupRequiredError,
    IBKRSession,
    _require_safe_protobuf_runtime,
)
from tests.unit.test_ibkr_market_access import NOW, instrument, plan

from empirical_platform.decision_candidate.market_access_ports import DispatchRecord
from empirical_platform.decision_candidate.market_plan import OrderPurpose


class Client:
    def __init__(self, wrapper: Any) -> None:
        self.wrapper = wrapper
        self.connected = False
        self.submitted: list[Any] = []
        self.orders: list[Any] = []
        self.completed: list[Any] = []
        self.executions: list[Any] = []
        self.holdings: list[Any] = []
        self.contract = SimpleNamespace(
            conId=123,
            symbol="NOKIA",
            exchange="HEX",
            primaryExchange="HEX",
            currency="EUR",
            secType="STK",
        )
        self.ready = "true"
        self.stream_requests = 0

    def connect(self, host: str, port: int, client_id: int) -> None:
        assert host == "127.0.0.1" and port == 7497 and client_id == 71
        self.connected = True
        self.wrapper.managedAccounts("DU12345")
        self.wrapper.nextValidId(10)

    def run(self) -> None:
        pass

    def disconnect(self) -> None:
        self.connected = False

    def isConnected(self) -> bool:
        return self.connected

    def reqCurrentTime(self) -> None:
        self.wrapper.currentTime(int(NOW.timestamp()))

    def reqContractDetails(self, key: int, contract: Any) -> None:
        self.wrapper.contractDetails(
            key,
            SimpleNamespace(
                contract=self.contract,
                minTick=0.01,
                liquidHours="20261002:1000-20261002:1830",
                timeZoneId="Europe/Helsinki",
            ),
        )
        self.wrapper.contractDetailsEnd(key)

    def reqTickByTickData(
        self, key: int, contract: Any, kind: str, count: int, ignore: bool
    ) -> None:
        self.stream_requests += 1
        if kind == "Last":
            self.wrapper.tickByTickAllLast(
                key, 1, int(datetime.now(UTC).timestamp()), 100.0, 1, None, "HEX", ""
            )
        else:
            self.wrapper.tickByTickBidAsk(
                key, int(datetime.now(UTC).timestamp()), 99.0, 100.0, 1, 1, None
            )

    def reqHistoricalData(self, key: int, *args: Any) -> None:
        for offset in range(1, 21):
            day = (datetime.now(UTC) - timedelta(days=offset)).strftime("%Y%m%d")
            self.wrapper.historicalData(key, SimpleNamespace(date=day, volume=200000))
        self.wrapper.historicalDataEnd(key, "", "")

    def cancelHistoricalData(self, key: int) -> None:
        pass

    def cancelTickByTickData(self, key: int) -> None:
        pass

    def reqAccountUpdatesMulti(self, key: int, account: str, model: str, ledger: bool) -> None:
        for tag, value, currency in (
            ("CashBalance", "5000", "EUR"),
            ("NetLiquidationByCurrency", "6000", "EUR"),
            ("RealizedPnL", "0", "EUR"),
            ("accountReady", self.ready, ""),
        ):
            self.wrapper.accountUpdateMulti(key, account, model, tag, value, currency)
        self.wrapper.accountUpdateMultiEnd(key)

    def cancelAccountUpdatesMulti(self, key: int) -> None:
        pass

    def reqPositions(self) -> None:
        for row in self.holdings:
            self.wrapper.position(*row, 100.0)
        self.wrapper.positionEnd()

    def cancelPositions(self) -> None:
        pass

    def reqExecutions(self, key: int, query: Any) -> None:
        for row in self.executions:
            self.wrapper.execDetails(key, *row)
        self.wrapper.execDetailsEnd(key)

    def reqAllOpenOrders(self) -> None:
        for row in self.orders:
            self.wrapper.openOrder(*row)
        self.wrapper.openOrderEnd()

    def reqCompletedOrders(self, api_only: bool) -> None:
        for row in self.completed:
            self.wrapper.completedOrder(*row)
        self.wrapper.completedOrdersEnd()

    def placeOrder(self, order_id: int, contract: Any, order: Any) -> None:
        self.submitted.append((order_id, contract, order))

    def cancelOrder(self, order_id: int, cancel: Any) -> None:
        self.submitted.append((order_id, cancel))


@pytest.fixture
def session(monkeypatch: pytest.MonkeyPatch) -> Any:
    # This fixture replaces the entire SDK. The real runtime guard is tested below.
    monkeypatch.setattr("empirical_ibkr.session._require_safe_protobuf_runtime", lambda: None)
    for name, clsname, cls in (
        ("client", "EClient", Client),
        ("wrapper", "EWrapper", type("Wrapper", (), {})),
        ("contract", "Contract", SimpleNamespace),
        ("order", "Order", SimpleNamespace),
        ("execution", "ExecutionFilter", SimpleNamespace),
        ("order_cancel", "OrderCancel", SimpleNamespace),
    ):
        module = ModuleType("ibapi." + name)
        setattr(module, clsname, cls)
        monkeypatch.setitem(sys.modules, "ibapi." + name, module)
    value = IBKRSession(account="DU12345", timeout=0.01)
    value.connect()
    yield value
    value.close()


@pytest.mark.parametrize("version", ["5.29.5", "6.33.5", None])
def test_unreviewed_protobuf_refused_before_sdk_or_socket(
    monkeypatch: pytest.MonkeyPatch, version: str | None
) -> None:
    monkeypatch.setattr(
        "empirical_ibkr.session.import_module", lambda name: SimpleNamespace(__version__=version)
    )
    value = IBKRSession(account="DU12345")
    with pytest.raises(IBKROwnerSetupRequiredError, match="protobuf"):
        value.connect()
    assert value._client is None


def test_missing_protobuf_refused_and_reviewed_patch_accepted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def missing(name: str) -> None:
        raise ImportError("unavailable")

    monkeypatch.setattr("empirical_ibkr.session.import_module", missing)
    with pytest.raises(IBKROwnerSetupRequiredError, match="protobuf"):
        _require_safe_protobuf_runtime()
    monkeypatch.setattr(
        "empirical_ibkr.session.import_module", lambda name: SimpleNamespace(__version__="5.29.6")
    )
    _require_safe_protobuf_runtime()


def record() -> DispatchRecord:
    p = plan()
    return DispatchRecord(
        p.plan_id,
        OrderPurpose.ENTRY,
        10,
        p.order_reference(OrderPurpose.ENTRY),
        Decimal("1"),
        Decimal("100"),
        "CLAIMED",
    )


def test_all_read_requests_are_bound_and_bounded(session: IBKRSession) -> None:
    adapter = IBKRPaperAdapter(session)
    assert adapter.resolve("NOKIA").instrument == instrument()
    quote = adapter.quote(instrument())
    quote.validate(instrument(), datetime.now(UTC), 60)
    assert adapter.account().ready
    assert adapter.positions() == () and adapter.open_orders() == ()
    assert adapter.reconcile(plan(), record()) is None
    assert session.next_order_id() == 10
    assert len(session._rows) <= 3
    session._client.ready = "false"
    with pytest.raises(IBKROwnerSetupRequiredError, match="ready"):
        adapter.account()
    with pytest.raises(IBKROwnerSetupRequiredError):
        session.connect()


def test_exact_order_construction_default_refusal_and_final_gate(session: IBKRSession) -> None:
    with pytest.raises(ValueError, match="read-only"):
        IBKRPaperAdapter(session).send_bound(plan(), record(), before_send=lambda: None)
    adapter = IBKRPaperAdapter(session, allow_approved_writes=True)
    adapter.resolve("NOKIA")

    def expired() -> None:
        raise ValueError("expired")

    with pytest.raises(ValueError, match="expired"):
        adapter.send_bound(plan(), record(), before_send=expired)
    assert session._client.submitted == []
    adapter.send_bound(plan(), record(), before_send=lambda: None)
    _, contract, order = session._client.submitted[0]
    assert contract.conId == 123 and contract.exchange == "HEX" and contract.currency == "EUR"
    assert order.action == "BUY" and order.totalQuantity == 1 and order.tif == "DAY"
    assert order.outsideRth is False and order.lmtPrice == 100.0


def test_order_fill_truth_and_exact_cancellation(session: IBKRSession) -> None:
    adapter = IBKRPaperAdapter(session, allow_approved_writes=True)
    adapter.resolve("NOKIA")
    order = SimpleNamespace(
        account="DU12345",
        clientId=71,
        action="BUY",
        permId=777,
        orderId=10,
        totalQuantity=1,
        orderRef=record().reference,
    )
    state = SimpleNamespace(status="Submitted")
    session._client.orders = [(10, session._client.contract, order, state)]
    assert adapter.open_orders()[0].status == "WORKING"
    adapter.cancel_bound(plan(), record())
    assert len(session._client.submitted) == 1
    session._client.orders = []
    state.status = "Filled"
    session._client.completed = [(session._client.contract, order, state)]
    execution = SimpleNamespace(
        permId=777,
        acctNumber="DU12345",
        orderRef=order.orderRef,
        side="BOT",
        execId="e1",
        shares=1,
        price=100,
    )
    session._client.executions = [(session._client.contract, execution)]
    truth = adapter.reconcile(plan(), record())
    assert truth is not None and truth.status == "FILLED" and truth.average_price == 100
    with pytest.raises(ValueError, match="working"):
        adapter.cancel_bound(plan(), record())
    session._client.holdings = [("DU12345", session._client.contract, "1")]
    assert adapter.positions()[0].quantity == 1
    session._client.holdings = [("DU12345", session._client.contract, "-1")]
    with pytest.raises(ValueError, match="short"):
        adapter.positions()


def test_timeout_invalidates_session_and_ignores_late_callbacks(session: IBKRSession) -> None:
    session._client.reqPositions = lambda: None
    with pytest.raises(IBKROwnerSetupRequiredError, match="timed out"):
        session.request("positions")
    session._client.positionEnd()
    with pytest.raises(IBKROwnerSetupRequiredError, match="unavailable"):
        session.request("positions")
    assert "positions" not in session._done


def test_live_streams_are_reused_and_bars_are_real_callback_values(session: IBKRSession) -> None:
    adapter = IBKRPaperAdapter(session)
    adapter.resolve("NOKIA")
    first = adapter.quote(instrument())
    assert adapter.quote(instrument()) == first
    assert session._client.stream_requests == 1
    assert adapter.last_trade(instrument())[0] == Decimal("100")
    assert adapter.average_daily_volume(instrument())[0] == 200000
    key = session._streams[(123, "quote")]
    session._client.tickByTickBidAsk(
        key, int(datetime.now(UTC).timestamp()), 100.0, 101.0, 1, 1, None
    )
    assert adapter.quote(instrument()).ask == Decimal("101")
    assert session._client.stream_requests == 2
    assert adapter.positions_snapshot().positions == ()


@pytest.mark.parametrize(
    "field,value",
    [
        ("exchange", "NYSE"),
        ("currency", "USD"),
        ("symbol", "OTHER"),
        ("secType", "CFD"),
        ("primaryExchange", "NYSE"),
        ("conId", 0),
    ],
)
def test_sdk_contract_mismatches_refuse(session: IBKRSession, field: str, value: Any) -> None:
    setattr(session._client.contract, field, value)
    with pytest.raises(ValueError):
        IBKRPaperAdapter(session).resolve("NOKIA")
    assert not session._client.submitted


def test_reducing_close_requires_exact_position_and_has_no_short_surface(
    session: IBKRSession,
) -> None:
    adapter = IBKRPaperAdapter(session, allow_approved_writes=True)
    adapter.resolve("NOKIA")
    p = plan()
    close = DispatchRecord(
        p.plan_id,
        OrderPurpose.CLOSE,
        11,
        p.order_reference(OrderPurpose.CLOSE),
        Decimal("1"),
        Decimal("99"),
        "CLAIMED",
    )
    with pytest.raises(ValueError, match="position"):
        adapter.send_bound(p, close, before_send=lambda: None)
    session._client.holdings = [("DU12345", session._client.contract, "1")]
    adapter.send_bound(p, close, before_send=lambda: None)
    assert session._client.submitted[-1][2].action == "SELL"
    assert session._client.submitted[-1][2].totalQuantity == 1


def test_callback_error_is_sanitized_and_disconnect_blocks_next_write(session: IBKRSession) -> None:
    key = 3000
    session._active.add(key)
    session._client.error(key, 123456789, 354, "test message must never be echoed")
    with pytest.raises(IBKROwnerSetupRequiredError, match=r"code 354") as caught:
        session._wait(key)
    assert "message" not in str(caught.value)
    session._client.error(-1, 123456789, 1100, "connection reset")
    with pytest.raises(IBKROwnerSetupRequiredError):
        session.next_order_id()


def test_foreign_broker_contract_cannot_be_constructed() -> None:
    from empirical_platform.decision_candidate.market_identity import (
        BrokerIdentity,
        Currency,
        InstrumentIdentity,
    )

    foreign = InstrumentIdentity(
        BrokerIdentity.ALPACA_PAPER, "123", "AAPL", "XNAS", "NASDAQ", "NASDAQ", Currency.USD, "STK"
    )
    # Missing SDK is also a safe refusal; this unit installs none globally.
    with pytest.raises((ValueError, IBKROwnerSetupRequiredError)):
        _contract(foreign)
