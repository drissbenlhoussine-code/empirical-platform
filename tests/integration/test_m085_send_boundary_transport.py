"""The transport POST count at the send boundary, with the REAL broker adapter.

A path-aware hostile server stands in for Alpaca. The dispatch handler runs with the real
`AlpacaPaperClient` (pinned host, connect() redirected to the local socket), the repository
fakes for persistence, and a fake market-data feed. The identity lookup is served slowly, and
DURING that lookup the kill switch is engaged: the server must see ZERO `POST /v2/orders`.
The positive control sees exactly one.
"""

from __future__ import annotations

import http.client
import json
import socket
import threading
import time
from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import pytest
from freezegun import freeze_time
from tests.integration.test_m085_hostile_http import credentials
from tests.unit import test_m085_corrective_pass_handlers as handlers

from empirical_platform.decision_candidate.paper_execution import (
    PAPER_ENDPOINT_HOST,
    PaperExecutionState,
)
from empirical_platform.shared.brokerage.alpaca_paper import AlpacaPaperClient, PaperEndpoint

pytestmark = pytest.mark.integration


class _Routes:
    def __init__(self) -> None:
        self.requests: list[tuple[str, str]] = []
        self.lock = threading.Lock()
        self.lookup_delay_seconds = 0.0
        self.during_lookup: Callable[[], None] | None = None
        self.orders_posted = 0

    def posts(self) -> int:
        return sum(1 for method, path in self.requests if method == "POST" and path == "/v2/orders")


def _handler_class(routes: _Routes) -> type[BaseHTTPRequestHandler]:
    class _Handler(BaseHTTPRequestHandler):
        def _send(self, status: int, document: object) -> None:
            payload = json.dumps(document).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def _serve(self) -> None:
            length = int(self.headers.get("Content-Length") or 0)
            body = self.rfile.read(length).decode() if length else ""
            with routes.lock:
                routes.requests.append((self.command, self.path))
            path = self.path
            if path == "/v2/account":
                self._send(
                    200,
                    {
                        "id": "real-account-id",
                        "status": "ACTIVE",
                        "currency": "USD",
                        "buying_power": "100000",
                        "cash": "100000",
                        "equity": "100000",
                        "multiplier": "4",
                        "shorting_enabled": True,
                        "trading_blocked": False,
                        "transfers_blocked": False,
                        "account_blocked": False,
                        "trade_suspended_by_user": False,
                    },
                )
            elif path == "/v2/clock":
                now = datetime.now(UTC)
                self._send(
                    200,
                    {
                        "is_open": True,
                        "timestamp": now.isoformat(),
                        "next_open": None,
                        "next_close": now.replace(hour=23, minute=59).isoformat(),
                    },
                )
            elif path.startswith("/v2/assets/"):
                self._send(
                    200,
                    {
                        "symbol": path.rsplit("/", 1)[1],
                        "status": "active",
                        "tradable": True,
                        "class": "us_equity",
                        "exchange": "NASDAQ",
                        "fractionable": True,
                    },
                )
            elif path.startswith("/v2/positions/"):
                self._send(404, {"code": 40410000, "message": "position does not exist"})
            elif path.startswith("/v2/orders:by_client_order_id"):
                if routes.lookup_delay_seconds:
                    time.sleep(routes.lookup_delay_seconds)
                if routes.during_lookup is not None:
                    routes.during_lookup()
                self._send(404, {"code": 40410000, "message": "order not found"})
            elif path == "/v2/orders" and self.command == "POST":
                sent = json.loads(body)
                self._send(
                    200,
                    {
                        "id": "b0000000-0000-4000-8000-000000000001",
                        "client_order_id": sent["client_order_id"],
                        "status": "accepted",
                        "symbol": sent["symbol"],
                        "side": sent["side"],
                        "qty": sent["qty"],
                        "type": sent["type"],
                        "time_in_force": sent["time_in_force"],
                        "extended_hours": sent["extended_hours"],
                        "limit_price": sent.get("limit_price"),
                        "filled_qty": "0",
                        "filled_avg_price": None,
                    },
                )
            else:
                self._send(404, {"code": 40410000, "message": "unknown path"})

        do_GET = _serve  # noqa: N815
        do_POST = _serve  # noqa: N815

        def log_message(self, format: str, *args: object) -> None:  # noqa: A002
            return None

    return _Handler


@pytest.fixture
def routes(monkeypatch: pytest.MonkeyPatch) -> Iterator[_Routes]:
    table = _Routes()
    server = ThreadingHTTPServer(("127.0.0.1", 0), _handler_class(table))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = server.server_address[1]

    def connect(self: http.client.HTTPSConnection) -> None:
        self.sock = socket.create_connection(("127.0.0.1", port), timeout=self.timeout)

    monkeypatch.setattr(http.client.HTTPSConnection, "connect", connect)
    try:
        yield table
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def _real_client() -> AlpacaPaperClient:
    return AlpacaPaperClient(
        endpoint=PaperEndpoint.from_url(f"https://{PAPER_ENDPOINT_HOST}"),
        credentials=credentials(),
        connect_timeout=5.0,
        read_timeout=10.0,
    )


def _world_with_real_broker() -> dict[str, Any]:
    return handlers._world(broker=_real_client())


def test_positive_control_exactly_one_post_reaches_the_server(routes: _Routes) -> None:
    with freeze_time(handlers._NOW, tick=True):
        world = _world_with_real_broker()
        handlers._authorize(world)
        result = handlers._submit(world)
    assert result.dispatched is True
    assert result.attempt.state is PaperExecutionState.PAPER_ACCEPTED
    assert routes.posts() == 1


def test_the_kill_switch_engaged_during_a_slow_lookup_means_zero_posts(routes: _Routes) -> None:
    with freeze_time(handlers._NOW, tick=True):
        world = _world_with_real_broker()
        handlers._authorize(world)
        routes.lookup_delay_seconds = 0.3

        def engage() -> None:
            world["kill_switch"].engaged = True

        routes.during_lookup = engage
        result = handlers._submit(world)
    assert result.dispatched is False
    assert result.attempt.state is PaperExecutionState.REJECTED
    assert routes.posts() == 0, routes.requests
    lookups = [p for m, p in routes.requests if p.startswith("/v2/orders:by_client_order_id")]
    assert len(lookups) == 1
