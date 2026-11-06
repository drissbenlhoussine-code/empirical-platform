"""A LOCAL, SCRIPTED stand-in for the Alpaca PAPER wire, for the M100 acceptance matrix.

Not a test module. The production `AlpacaPaperClient` / `AlpacaPaperMarketDataClient` are used
UNCHANGED: they stay pinned to `paper-api.alpaca.markets` / `data.alpaca.markets` and only the
TRANSPORT is redirected (`http.client.HTTPSConnection.connect` opens a plain socket to this
server on 127.0.0.1) -- exactly the pattern of `test_m085_hostile_http.py` and
`test_m085_send_boundary_transport.py`. No real network, no real credential, no real broker.

WHAT IS FAKED, AND ONLY THAT. The exchange: an in-memory account, positions, an order book of
the orders it was sent, a quote, and a virtual clock. Everything the system under test does
with those answers (parsing, validation, state machines, persistence, reconciliation) is the
REAL production code.

SCRIPTING. `exchange.script_post(...)` queues a behaviour for the next `POST /v2/orders`:
accept (default), a definitive rejection, a delivered-but-answer-lost connection drop, a
never-delivered drop, an HTTP 500 after acceptance, or an acknowledgement that differs from
the order sent. `exchange.fill(...)` moves an order (partially or fully) and updates the
position book the same way a real exchange would.
"""

from __future__ import annotations

import http.client
import json
import socket
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

import pytest

from empirical_platform.shared.brokerage.paper_time import PaperTimeReading


class VirtualClock:
    """Real time plus an adjustable offset. One clock for host, broker wire and `now=` args.

    `advance()` moves every consumer forward together, so a 30-second reprice-spacing rule can
    be exercised without sleeping and without any consumer seeing an inconsistent time.
    """

    def __init__(self) -> None:
        self._offset = timedelta(0)
        self._lock = threading.Lock()

    def now(self) -> datetime:
        with self._lock:
            return datetime.now(UTC) + self._offset

    def advance(self, seconds: float) -> None:
        with self._lock:
            self._offset += timedelta(seconds=seconds)

    def reading(self) -> PaperTimeReading:
        import time as _time

        with self._lock:
            return PaperTimeReading(
                datetime.now(UTC) + self._offset, _time.monotonic() + self._offset.total_seconds()
            )


@dataclass
class FakeOrder:
    id: str
    client_order_id: str
    symbol: str
    side: str
    qty: str
    type: str
    time_in_force: str
    extended_hours: bool
    limit_price: str | None
    status: str = "accepted"
    filled_qty: Decimal = Decimal(0)
    filled_avg_price: Decimal | None = None
    #: Distort the acknowledgement of THIS order (answered-but-wrong scenario).
    ack_overrides: dict[str, Any] = field(default_factory=dict)

    def as_payload(self, *, with_overrides: bool = False) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "id": self.id,
            "client_order_id": self.client_order_id,
            "status": self.status,
            "symbol": self.symbol,
            "side": self.side,
            "qty": self.qty,
            "type": self.type,
            "time_in_force": self.time_in_force,
            "extended_hours": self.extended_hours,
            "limit_price": self.limit_price,
            "filled_qty": str(self.filled_qty),
            "filled_avg_price": (
                None if self.filled_avg_price is None else str(self.filled_avg_price)
            ),
        }
        if with_overrides:
            payload.update(self.ack_overrides)
        return payload

    @property
    def is_open(self) -> bool:
        return self.status in {"new", "accepted", "partially_filled", "pending_new"}


@dataclass
class _Position:
    qty: int
    avg_price: Decimal


@dataclass
class PostScript:
    """What the NEXT `POST /v2/orders` does."""

    action: str = "accept"
    status: int = 422
    body: dict[str, Any] | None = None
    ack_overrides: dict[str, Any] = field(default_factory=dict)


class FakeAlpacaExchange:
    def __init__(self, clock: VirtualClock) -> None:
        self.clock = clock
        self.lock = threading.RLock()
        self.requests: list[tuple[str, str, str]] = []
        #: Distinct values of the key-id header seen on the wire (proves credentials ride the
        #: headers only; tests assert they never appear in a path or a body).
        self.key_ids_seen: set[str] = set()
        self.orders: dict[str, FakeOrder] = {}
        self.positions: dict[str, _Position] = {}
        self.market_open = True
        self.bid = Decimal("99.98")
        self.ask = Decimal("100.00")
        self.equity = Decimal("100000")
        self.last_equity = Decimal("100000")
        self.cash = Decimal("100000")
        self._post_scripts: list[PostScript] = []
        self._cancel_behaviour = "cancel"  # cancel | ignore | refuse
        self._sequence = 0
        self.fail_paths: dict[str, int] = {}  # path prefix -> HTTP status to answer instead
        self.quote_age_seconds = 1.0
        #: Per-tick bids for `/quotes` (the exit-signal corroboration window); None = flat bid.
        self.recent_bids: list[Decimal] | None = None
        #: Minute bars as (minutes_ago, open, high, low, close, volume); None = flat liquid bars.
        self.bars: list[tuple[int, str, str, str, str, int]] | None = None

    # -- scripting --------------------------------------------------------------------

    def script_post(self, action: str = "accept", **kwargs: Any) -> None:
        with self.lock:
            self._post_scripts.append(PostScript(action=action, **kwargs))

    def script_cancel(self, behaviour: str) -> None:
        with self.lock:
            self._cancel_behaviour = behaviour

    def set_quote(self, bid: str, ask: str) -> None:
        with self.lock:
            self.bid, self.ask = Decimal(bid), Decimal(ask)

    def seed_position(self, symbol: str, qty: int, avg_price: str) -> None:
        with self.lock:
            self.positions[symbol] = _Position(qty, Decimal(avg_price))

    def seed_open_order(
        self, *, symbol: str, side: str, qty: int, limit_price: str, client_order_id: str
    ) -> FakeOrder:
        with self.lock:
            order = self._new_order(
                {
                    "symbol": symbol,
                    "side": side,
                    "qty": str(qty),
                    "type": "limit",
                    "time_in_force": "day",
                    "extended_hours": False,
                    "limit_price": limit_price,
                    "client_order_id": client_order_id,
                }
            )
            return order

    # -- queries the tests assert on --------------------------------------------------

    def posts(self) -> list[dict[str, Any]]:
        with self.lock:
            return [json.loads(body) for method, path, body in self.requests if method == "POST"]

    def count(self, method: str, path_prefix: str) -> int:
        with self.lock:
            return sum(1 for m, p, _ in self.requests if m == method and p.startswith(path_prefix))

    def order_by_client_id(self, client_order_id: str) -> FakeOrder | None:
        with self.lock:
            return next(
                (o for o in self.orders.values() if o.client_order_id == client_order_id), None
            )

    def open_orders(self) -> list[FakeOrder]:
        with self.lock:
            return [o for o in self.orders.values() if o.is_open]

    def position_qty(self, symbol: str) -> int:
        with self.lock:
            position = self.positions.get(symbol)
            return 0 if position is None else position.qty

    # -- mutation the "market" performs ----------------------------------------------

    def _new_order(self, sent: dict[str, Any]) -> FakeOrder:
        self._sequence += 1
        order = FakeOrder(
            id=f"b0000000-0000-4000-8000-{self._sequence:012d}",
            client_order_id=sent["client_order_id"],
            symbol=sent["symbol"],
            side=sent["side"],
            qty=str(sent["qty"]),
            type=sent["type"],
            time_in_force=sent["time_in_force"],
            extended_hours=bool(sent["extended_hours"]),
            limit_price=sent.get("limit_price"),
        )
        self.orders[order.id] = order
        return order

    def fill(self, client_order_id: str, qty: int, price: str) -> FakeOrder:
        """Fill `qty` more shares of the order at `price`; partial until the order is whole."""
        with self.lock:
            order = self.order_by_client_id(client_order_id)
            assert order is not None, f"no such order {client_order_id}"
            assert order.is_open, f"order {client_order_id} is {order.status}"
            fill_price = Decimal(price)
            total = Decimal(order.qty)
            new_filled = order.filled_qty + Decimal(qty)
            assert new_filled <= total, "over-fill"
            previous = (order.filled_avg_price or Decimal(0)) * order.filled_qty
            order.filled_avg_price = (previous + fill_price * Decimal(qty)) / new_filled
            order.filled_qty = new_filled
            order.status = "filled" if new_filled == total else "partially_filled"
            position = self.positions.get(order.symbol)
            if order.side == "buy":
                if position is None:
                    self.positions[order.symbol] = _Position(qty, fill_price)
                else:
                    cost = position.avg_price * position.qty + fill_price * qty
                    position.qty += qty
                    position.avg_price = cost / position.qty
            else:
                assert position is not None and position.qty >= qty, "sell of unheld shares"
                position.qty -= qty
                if position.qty == 0:
                    del self.positions[order.symbol]
            return order

    def expire(self, client_order_id: str) -> None:
        with self.lock:
            order = self.order_by_client_id(client_order_id)
            assert order is not None
            order.status = "expired"

    # -- HTTP -------------------------------------------------------------------------

    def handle(self, handler: BaseHTTPRequestHandler, method: str) -> None:
        length = int(handler.headers.get("Content-Length") or 0)
        body = handler.rfile.read(length).decode() if length else ""
        parsed = urlparse(handler.path)
        path = parsed.path
        query = parse_qs(parsed.query)
        with self.lock:
            self.requests.append((method, handler.path, body))
            self.key_ids_seen.add(handler.headers.get("APCA-API-KEY-ID", ""))

        def send(status: int, document: object) -> None:
            payload = b"" if document is None else json.dumps(document).encode()
            handler.send_response(status)
            handler.send_header("Content-Type", "application/json")
            handler.send_header("Content-Length", str(len(payload)))
            handler.end_headers()
            handler.wfile.write(payload)

        def drop() -> None:
            handler.close_connection = True
            try:
                handler.connection.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            handler.connection.close()

        with self.lock:
            for prefix, status in self.fail_paths.items():
                if handler.path.startswith(prefix):
                    send(status, {"message": "scripted outage"})
                    return

        now = self.clock.now()
        if method == "GET" and path == "/v2/account":
            with self.lock:
                send(
                    200,
                    {
                        "id": "acc-m100-paper-0001",
                        "status": "ACTIVE",
                        "currency": "USD",
                        "buying_power": str(self.cash),
                        "cash": str(self.cash),
                        "equity": str(self.equity),
                        "last_equity": str(self.last_equity),
                        "multiplier": "1",
                        "shorting_enabled": False,
                        "trading_blocked": False,
                        "transfers_blocked": False,
                        "account_blocked": False,
                        "trade_suspended_by_user": False,
                    },
                )
        elif method == "GET" and path == "/v2/clock":
            with self.lock:
                send(
                    200,
                    {
                        "is_open": self.market_open,
                        "timestamp": now.isoformat(),
                        "next_open": (now + timedelta(hours=16)).isoformat(),
                        "next_close": (now + timedelta(hours=3)).isoformat(),
                    },
                )
        elif method == "GET" and path.startswith("/v2/assets/"):
            send(
                200,
                {
                    "symbol": path.rsplit("/", 1)[1],
                    "status": "active",
                    "tradable": True,
                    "class": "us_equity",
                    "exchange": "XNAS",
                    "fractionable": True,
                },
            )
        elif method == "GET" and path == "/v2/positions":
            with self.lock:
                send(200, [self._position_payload(s, p) for s, p in self.positions.items()])
        elif method == "GET" and path.startswith("/v2/positions/"):
            symbol = path.rsplit("/", 1)[1]
            with self.lock:
                position = self.positions.get(symbol)
                if position is None:
                    send(404, {"code": 40410000, "message": "position does not exist"})
                else:
                    send(200, self._position_payload(symbol, position))
        elif method == "GET" and path == "/v2/orders":
            with self.lock:
                orders = [o for o in self.orders.values() if o.is_open]
                symbols = query.get("symbols")
                if symbols:
                    orders = [o for o in orders if o.symbol in symbols[0].split(",")]
                send(200, [o.as_payload() for o in orders])
        elif method == "GET" and path == "/v2/orders:by_client_order_id":
            wanted = query.get("client_order_id", [""])[0]
            with self.lock:
                order = self.order_by_client_id(wanted)
                if order is None:
                    send(404, {"code": 40410000, "message": "order not found"})
                else:
                    send(200, order.as_payload())
        elif method == "DELETE" and path.startswith("/v2/orders/"):
            order_id = path.rsplit("/", 1)[1]
            with self.lock:
                order = self.orders.get(order_id)
                if order is None:
                    send(404, {"message": "order not found"})
                elif not order.is_open:
                    send(422, {"message": "order is not cancelable"})
                elif self._cancel_behaviour == "refuse":
                    send(422, {"message": "cancel refused"})
                elif self._cancel_behaviour == "ignore":
                    send(204, None)
                else:
                    order.status = "canceled"
                    send(204, None)
        elif method == "POST" and path == "/v2/orders":
            self._post_order(handler, body, send, drop)
        elif method == "GET" and path.endswith("/quotes/latest"):
            with self.lock:
                send(
                    200,
                    {
                        "symbol": path.split("/")[3],
                        "quote": {
                            "t": (now - timedelta(seconds=self.quote_age_seconds)).isoformat(),
                            "bp": float(self.bid),
                            "ap": float(self.ask),
                        },
                    },
                )
        elif method == "GET" and path.endswith("/quotes"):
            with self.lock:
                bids = self.recent_bids or [self.bid] * 12
                ticks = [
                    {
                        "t": (now - timedelta(seconds=len(bids) - index)).isoformat(),
                        "bp": float(bid),
                        "ap": float(self.ask),
                    }
                    for index, bid in enumerate(bids)
                ]
            send(200, {"symbol": path.split("/")[3], "quotes": ticks})
        elif method == "GET" and path.endswith("/bars"):
            with self.lock:
                scripted = self.bars
            if scripted is not None:
                bars = [
                    {
                        "t": (
                            now.replace(second=0, microsecond=0) - timedelta(minutes=ago)
                        ).isoformat(),
                        "o": float(o),
                        "h": float(h),
                        "l": float(low),
                        "c": float(c),
                        "v": v,
                    }
                    for ago, o, h, low, c, v in scripted
                ]
            else:
                bars = [
                    {
                        "t": (now - timedelta(minutes=minute)).isoformat(),
                        "o": 99.9,
                        "h": 100.1,
                        "l": 99.8,
                        "c": float(self.ask),
                        "v": 400_000,
                    }
                    for minute in range(3, 0, -1)
                ]
            send(200, {"symbol": path.split("/")[3], "bars": bars})
        else:
            send(404, {"code": 40410000, "message": f"unknown path {path}"})

    def _position_payload(self, symbol: str, position: _Position) -> dict[str, Any]:
        return {
            "symbol": symbol,
            "qty": str(position.qty),
            "avg_entry_price": str(position.avg_price),
            "market_value": str(self.bid * position.qty),
            "side": "long",
        }

    def _post_order(
        self,
        handler: BaseHTTPRequestHandler,
        body: str,
        send: Callable[[int, object], None],
        drop: Callable[[], None],
    ) -> None:
        with self.lock:
            script = self._post_scripts.pop(0) if self._post_scripts else PostScript()
        sent = json.loads(body)
        if script.action == "drop_before_record":
            drop()  # delivered to the socket, never processed: no order exists
            return
        if script.action == "reject":
            send(script.status, script.body or {"code": 40310000, "message": "rejected"})
            return
        with self.lock:
            existing = self.order_by_client_id(sent["client_order_id"])
            if existing is not None:
                send(422, {"code": 40010001, "message": "client_order_id must be unique"})
                return
            order = self._new_order(sent)
            order.ack_overrides = script.ack_overrides
        if script.action == "drop_after_record":
            drop()  # the exchange HAS the order but the answer is lost
        elif script.action == "http_500_after_record":
            send(500, {"message": "internal error"})
        else:
            send(200, order.as_payload(with_overrides=True))


def _handler_class(exchange: FakeAlpacaExchange) -> type[BaseHTTPRequestHandler]:
    class _Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            exchange.handle(self, "GET")

        def do_POST(self) -> None:  # noqa: N802
            exchange.handle(self, "POST")

        def do_DELETE(self) -> None:  # noqa: N802
            exchange.handle(self, "DELETE")

        def log_message(self, format: str, *args: object) -> None:  # noqa: A002
            return None

    return _Handler


@contextmanager
def serve_exchange(
    exchange: FakeAlpacaExchange, monkeypatch: pytest.MonkeyPatch
) -> Iterator[FakeAlpacaExchange]:
    """Start the local server and redirect `HTTPSConnection.connect` to it (pin untouched)."""
    server = ThreadingHTTPServer(("127.0.0.1", 0), _handler_class(exchange))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = server.server_address[1]

    def connect(self: http.client.HTTPSConnection) -> None:
        self.sock = socket.create_connection(("127.0.0.1", port), timeout=self.timeout)

    monkeypatch.setattr(http.client.HTTPSConnection, "connect", connect)
    try:
        yield exchange
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
