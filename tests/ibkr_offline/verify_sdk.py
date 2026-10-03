"""Explicit CI-only real SDK serialization: synthetic inputs, sockets forbidden.

Run explicitly after installing the hash-verified official SDK. This file is not
part of default discovery and never reports an authenticated broker session.
"""

# Official SDK method names and dynamic error callback payloads.
# ruff: noqa: N802, ANN401
import socket
from decimal import Decimal
from typing import Any

import pytest
from empirical_ibkr.paper import IBKRPaperAdapter
from empirical_ibkr.session import IBKRSession, _require_safe_protobuf_runtime
from ibapi.client import EClient
from ibapi.protobuf.PlaceOrderRequest_pb2 import PlaceOrderRequest
from ibapi.wrapper import EWrapper
from tests.unit.test_ibkr_market_access import NOW, plan

from empirical_platform.decision_candidate.market_access_ports import DispatchRecord, PositionTruth
from empirical_platform.decision_candidate.market_plan import OrderPurpose


class WireCapture:
    def __init__(self) -> None:
        self.messages: list[bytes] = []

    def isConnected(self) -> bool:
        return True  # Synthetic transport only; no socket exists.

    def sendMsg(self, message: bytes) -> None:
        self.messages.append(message)


class RejectErrors(EWrapper):
    def error(self, *args: Any, **kwargs: Any) -> None:
        raise AssertionError("official SDK rejected offline serialization")


@pytest.mark.parametrize(
    ("purpose", "quantity"),
    [(OrderPurpose.ENTRY, "1"), (OrderPurpose.CLOSE, "1"), (OrderPurpose.CLOSE, "0.4")],
)
def test_actual_adapter_serializes_exact_terms_with_real_sdk_and_no_network(
    monkeypatch: pytest.MonkeyPatch,
    purpose: OrderPurpose,
    quantity: str,
) -> None:
    def deny_socket(*args: Any, **kwargs: Any) -> None:
        pytest.fail("offline SDK verification attempted a socket")

    monkeypatch.setattr(socket, "socket", deny_socket)
    monkeypatch.setattr(socket, "create_connection", deny_socket)
    _require_safe_protobuf_runtime()  # Actual imported runtime, not metadata or a double.
    wire = WireCapture()
    client = EClient(RejectErrors())
    client.conn = wire
    client.connState = EClient.CONNECTED
    client.serverVersion_ = 213
    session = IBKRSession(account="DU12345", client_id=71)
    session._client = client
    session._accounts = (session.account_id,)
    session._connected = True  # Explicit synthetic setup, not a handshake claim.
    candidate = plan()
    record = DispatchRecord(
        candidate.plan_id,
        purpose,
        7,
        candidate.order_reference(purpose),
        Decimal(quantity),
        Decimal("100"),
        "CLAIMED",
    )
    checks: list[bool] = []
    readonly = IBKRPaperAdapter(session)
    with pytest.raises(ValueError, match="read-only"):
        readonly.send_bound(candidate, record, before_send=lambda: checks.append(True))
    assert not wire.messages and not checks
    adapter = IBKRPaperAdapter(session, allow_approved_writes=True)
    monkeypatch.setattr(
        adapter,
        "positions",
        lambda: (PositionTruth(candidate.account, candidate.instrument, Decimal(quantity), NOW),),
    )

    def refused_final_gate() -> None:
        raise ValueError("offline final gate refusal")

    with pytest.raises(ValueError, match="final gate refusal"):
        adapter.send_bound(candidate, record, before_send=refused_final_gate)
    assert not wire.messages
    adapter.send_bound(candidate, record, before_send=lambda: checks.append(True))
    assert checks == [True] and len(wire.messages) == 1
    frame = wire.messages[0]
    assert int.from_bytes(frame[:4], "big") == len(frame) - 4
    request = PlaceOrderRequest()
    request.ParseFromString(frame[8:])
    assert request.orderId == 7
    assert request.contract.conId == 123
    assert request.contract.exchange == "HEX" and request.contract.primaryExch == "HEX"
    assert request.contract.currency == "EUR" and request.contract.secType == "STK"
    assert request.order.account == "DU12345"
    assert request.order.action == ("BUY" if purpose is OrderPurpose.ENTRY else "SELL")
    assert request.order.totalQuantity == quantity
    assert request.order.orderType == "LMT" and request.order.lmtPrice == 100
    assert request.order.tif == "DAY" and not request.order.outsideRth
    assert request.order.orderRef == record.reference and request.order.transmit
