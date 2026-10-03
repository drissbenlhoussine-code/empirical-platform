# The optional official SDK has dynamic payloads and mandated callback names.
# ruff: noqa: ANN401, N802, N803
"""Official TWS API callback bridge. No credentials, login automation or Live endpoints.

Install the Python SDK from IBKR's official TWS API download. The SDK is optional
until this adapter is selected; Alpaca imports and installations remain unchanged.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict
from datetime import UTC, datetime
from importlib import import_module
from typing import Any


class IBKROwnerSetupRequiredError(RuntimeError):
    """Paper session, official SDK or API permission is unavailable."""


def _require_safe_protobuf_runtime() -> None:
    """Refuse the upstream SDK's vulnerable dependency pin before any socket opens."""
    try:
        version = getattr(import_module("google.protobuf"), "__version__", None)
    except ImportError as error:
        raise IBKROwnerSetupRequiredError("reviewed protobuf 5.29.6 runtime required") from error
    if version != "5.29.6":
        raise IBKROwnerSetupRequiredError("reviewed protobuf 5.29.6 runtime required")


class IBKRSession:
    def __init__(
        self, *, account: str, port: int = 7497, client_id: int = 71, timeout: float = 10
    ) -> None:
        if port not in (7497, 4002) or client_id <= 0 or timeout <= 0:
            raise ValueError("explicit Paper socket and positive dedicated client ID required")
        if not account.startswith("DU") or not account[2:].isdigit():
            raise ValueError("explicit Paper DU account required")
        self.account_id = account
        self.port = port
        self.client_id = client_id
        self.timeout = timeout
        self._condition = threading.Condition()
        self._serial = threading.Lock()
        self._rows: dict[object, list[Any]] = defaultdict(list)
        self._done: set[object] = set()
        self._errors: dict[object, int] = {}
        self._request_id = 1000
        self._next_id: int | None = None
        self._accounts: tuple[str, ...] = ()
        self._connected = False
        self._thread: threading.Thread | None = None
        self._client: Any = None
        self._active: set[object] = {"accounts", "next_id"}
        self._streams: dict[tuple[int, str], int] = {}

    def _append(self, key: object, value: Any, *, done: bool = False) -> None:
        with self._condition:
            if key not in self._active:
                return
            if key in self._streams.values():
                self._rows[key] = [value]
            else:
                self._rows[key].append(value)
            if done:
                self._done.add(key)
            self._condition.notify_all()

    def _finish(self, key: object) -> None:
        with self._condition:
            if key not in self._active:
                return
            self._done.add(key)
            self._condition.notify_all()

    def _wait(self, key: object) -> list[Any]:
        deadline = time.monotonic() + self.timeout
        with self._condition:
            while key not in self._done and key not in self._errors:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise IBKROwnerSetupRequiredError(
                        "IBKR request timed out; verify Paper login/API/data permissions"
                    )
                self._condition.wait(remaining)
            if key in self._errors:
                # Never echo raw IBKR errors: they can contain account/user data.
                raise IBKROwnerSetupRequiredError(
                    f"IBKR request refused (code {self._errors[key]})"
                )
            return list(self._rows[key])

    def connect(self) -> None:
        _require_safe_protobuf_runtime()
        if self._client is not None:
            raise IBKROwnerSetupRequiredError("create a fresh verified session after disconnect")
        try:
            from ibapi.client import EClient  # type: ignore[import-not-found]
            from ibapi.wrapper import EWrapper  # type: ignore[import-not-found]
        except ImportError as error:
            raise IBKROwnerSetupRequiredError(
                "install the official IBKR TWS API Python SDK"
            ) from error
        parent = self

        class Callbacks(EWrapper, EClient):  # type: ignore[misc]
            def __init__(self) -> None:
                EWrapper.__init__(self)
                EClient.__init__(self, self)

            def nextValidId(self, orderId: int) -> None:
                with parent._condition:
                    parent._next_id = max(parent._next_id or 0, orderId)
                parent._finish("next_id")

            def managedAccounts(self, accountsList: str) -> None:
                parent._accounts = tuple(x for x in accountsList.split(",") if x)
                parent._finish("accounts")

            def currentTime(self, timestamp: int) -> None:
                parent._append("clock", timestamp, done=True)

            def error(self, reqId: int, *args: Any) -> None:
                # Both legacy (code,message) and current (time,code,message) SDKs.
                code = args[1] if len(args) >= 3 and isinstance(args[1], int) else args[0]
                if code in (2104, 2106, 2107, 2108, 2158):
                    return
                with parent._condition:
                    parent._errors[reqId] = int(code)
                    if code in (1100, 1101, 1102, 1300, 502, 504):
                        parent._connected = False
                    parent._condition.notify_all()

            def connectionClosed(self) -> None:
                parent._connected = False

            def contractDetails(self, reqId: int, details: Any) -> None:
                parent._append(reqId, details)

            def contractDetailsEnd(self, reqId: int) -> None:
                parent._finish(reqId)

            def tickByTickBidAsk(
                self,
                reqId: int,
                timestamp: int,
                bidPrice: float,
                askPrice: float,
                bidSize: Any,
                askSize: Any,
                tickAttribBidAsk: Any,
            ) -> None:
                parent._append(
                    reqId, (timestamp, str(bidPrice), str(askPrice), datetime.now(UTC)), done=True
                )

            def accountSummary(
                self, reqId: int, account: str, tag: str, value: str, currency: str
            ) -> None:
                parent._append(reqId, (account, tag, value, currency))

            def accountSummaryEnd(self, reqId: int) -> None:
                parent._finish(reqId)

            def tickByTickAllLast(
                self,
                reqId: int,
                tickType: int,
                timestamp: int,
                price: float,
                size: Any,
                tickAttribLast: Any,
                exchange: str,
                specialConditions: str,
            ) -> None:
                parent._append(
                    reqId, (timestamp, str(price), exchange, specialConditions), done=True
                )

            def historicalData(self, reqId: int, bar: Any) -> None:
                parent._append(reqId, (bar.date, str(bar.volume)))

            def historicalDataEnd(self, reqId: int, start: str, end: str) -> None:
                parent._finish(reqId)

            def accountUpdateMulti(
                self, reqId: int, account: str, modelCode: str, key: str, value: str, currency: str
            ) -> None:
                if modelCode:
                    with parent._condition:
                        parent._errors[reqId] = -1
                parent._append(reqId, (account, key, value, currency))

            def accountUpdateMultiEnd(self, reqId: int) -> None:
                parent._finish(reqId)

            def position(self, account: str, contract: Any, position: Any, avgCost: float) -> None:
                parent._append("positions", (account, contract, str(position)))

            def positionEnd(self) -> None:
                parent._finish("positions")

            def openOrder(self, orderId: int, contract: Any, order: Any, orderState: Any) -> None:
                parent._append("orders", (orderId, contract, order, orderState))
                with parent._condition:
                    parent._next_id = max(parent._next_id or 0, orderId + 1)

            def openOrderEnd(self) -> None:
                parent._finish("orders")

            def completedOrder(self, contract: Any, order: Any, orderState: Any) -> None:
                parent._append(
                    "completed", (getattr(order, "orderId", -1), contract, order, orderState)
                )

            def completedOrdersEnd(self) -> None:
                parent._finish("completed")

            def execDetails(self, reqId: int, contract: Any, execution: Any) -> None:
                parent._append(reqId, (contract, execution))

            def execDetailsEnd(self, reqId: int) -> None:
                parent._finish(reqId)

        self._client = Callbacks()
        self._client.connect("127.0.0.1", self.port, self.client_id)
        self._thread = threading.Thread(
            target=self._client.run, name="ibkr-paper-reader", daemon=True
        )
        self._thread.start()
        try:
            self._wait("accounts")
            self._wait("next_id")
            if self._accounts != (self.account_id,):
                raise IBKROwnerSetupRequiredError(
                    "managed account differs from the explicit Paper account"
                )
            self._connected = True
        except Exception:
            self.close()
            raise

    def require_connected(self) -> None:
        if (
            not self._connected
            or self._accounts != (self.account_id,)
            or not self._client.isConnected()
        ):
            raise IBKROwnerSetupRequiredError("verified Paper connection is unavailable")

    def request(self, kind: str, argument: Any = None) -> list[Any]:
        self.require_connected()
        with self._serial:
            stream = (int(argument.conId), kind) if kind in ("quote", "last") else None
            if stream is not None and stream in self._streams:
                return self._wait(self._streams[stream])
            self._request_id += 1
            key: Any = (
                self._request_id
                if kind in ("contract", "quote", "last", "bars", "account", "executions")
                else kind
            )
            with self._condition:
                self._rows[key] = []
                self._done.discard(key)
                self._errors.pop(key, None)
                self._active.add(key)
                if stream is not None:
                    self._streams[stream] = key
            if kind == "contract":
                self._client.reqContractDetails(key, argument)
            elif kind == "quote":
                self._client.reqTickByTickData(key, argument, "BidAsk", 0, False)
            elif kind == "last":
                self._client.reqTickByTickData(key, argument, "Last", 0, False)
            elif kind == "bars":
                self._client.reqHistoricalData(
                    key, argument, "", "2 M", "1 day", "TRADES", 1, 1, False, []
                )
            elif kind == "account":
                self._client.reqAccountUpdatesMulti(key, self.account_id, "", True)
            elif kind == "executions":
                self._client.reqExecutions(key, argument)
            elif kind == "positions":
                self._client.reqPositions()
            elif kind == "orders":
                self._client.reqAllOpenOrders()
            elif kind == "completed":
                self._client.reqCompletedOrders(False)
            elif kind == "clock":
                self._client.reqCurrentTime()
            else:
                raise ValueError("unsupported read operation")
            try:
                return self._wait(key)
            except Exception:
                # Id-less callbacks cannot distinguish old and new subscriptions.
                # A timeout invalidates this session; never treat a late end marker
                # as proof that a new positions request returned zero.
                self.close()
                raise
            finally:
                if kind == "bars":
                    self._client.cancelHistoricalData(key)
                elif kind == "account":
                    self._client.cancelAccountUpdatesMulti(key)
                elif kind == "positions":
                    self._client.cancelPositions()
                if stream is None or not self._connected:
                    with self._condition:
                        self._active.discard(key)
                        self._rows.pop(key, None)
                        self._done.discard(key)
                        self._errors.pop(key, None)

    def next_order_id(self) -> int:
        self.require_connected()
        with self._condition:
            if self._next_id is None:
                raise IBKROwnerSetupRequiredError("nextValidId missing")
            value = self._next_id
            self._next_id += 1
            return value

    def close(self) -> None:
        self._connected = False
        if self._client is not None:
            self._client.disconnect()
        if self._thread is not None:
            self._thread.join(timeout=5)
