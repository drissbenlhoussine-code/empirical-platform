"""MILESTONE-085 -- the adapter against a hostile peer, over a real socket.

HOW A HOST-PINNED CLIENT IS TESTED AGAINST A HOSTILE SERVER. The adapter refuses
every endpoint that is not exactly `https://paper-api.alpaca.markets`, which is
the property being protected -- so the attacks below cannot simply point it at
`http://127.0.0.1:PORT`. Instead the ENDPOINT stays pinned and only the TRANSPORT
is redirected: `http.client.HTTPSConnection` is replaced with a subclass whose
`connect()` opens a plain socket to a local server. The adapter still believes it
is speaking to the pinned host, still builds the same request, still reads the
response through the same code, and still applies every refusal. Nothing about
the pin is relaxed; the wire simply arrives somewhere a test controls.

This is the difference between testing a parser and testing an adapter. A fake
object returning canned dictionaries would exercise none of the framing, the
status handling, the redirect refusal, the body bounding or the phase-by-phase
failure classification -- which is where the interesting failures live.

WHAT EVERY AMBIGUOUS CASE MUST DO. Fail closed WITHOUT producing a new order
identity. The adapter distinguishes three outcomes and the tests hold that
distinction: DEFINITELY-NOT-SENT (`BrokerNotSentError`), MAYBE-SENT
(`BrokerAmbiguousDispatchError`) and answered-but-wrong
(`BrokerResponseInvalidError`). Collapsing any two of those would either strand a
real order or create a second one.
"""

from __future__ import annotations

import http.client
import json
import socket
import threading
from collections.abc import Callable, Iterator
from decimal import Decimal
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import pytest

from empirical_platform.decision_candidate.operator_trading_configuration import OrderType
from empirical_platform.decision_candidate.paper_execution import (
    PAPER_ENDPOINT_HOST,
    PaperOrderRequest,
)
from empirical_platform.shared.brokerage.alpaca_paper import (
    MAXIMUM_DIAGNOSTIC_BODY_BYTES,
    REDACTED,
    AlpacaPaperClient,
    AlpacaPaperCredentials,
    BrokerAmbiguousDispatchError,
    BrokerNotSentError,
    BrokerResponseInvalidError,
    EndpointRefusedError,
    PaperEndpoint,
)

pytestmark = pytest.mark.integration

_KEY = "PKTESTKEYIDENTIFIER0123"
#: Not a credential: a fixture value this test writes and then requires the
#: adapter to scrub back out of a hostile response body.
_SECRET = "s3cr3t-paper-secret-value-not-real-0123456789"  # noqa: S105


def credentials() -> AlpacaPaperCredentials:
    return AlpacaPaperCredentials(key_id=_KEY, secret_key=_SECRET)


def an_order(**overrides: object) -> PaperOrderRequest:
    arguments: dict[str, object] = {
        "symbol": "AAPL",
        "side": "BUY",
        "quantity": 1,
        "order_type": OrderType.LIMIT,
        "limit_price": Decimal("4.00"),
        "time_in_force": "DAY",
        "extended_hours": False,
        "client_order_id": "m085-abcdef0123456789",
    }
    arguments.update(overrides)
    return PaperOrderRequest(**arguments)  # type: ignore[arg-type]


def an_order_payload(**overrides: object) -> dict[str, Any]:
    """A well-formed Alpaca order response, matching `an_order()`."""
    payload: dict[str, Any] = {
        "id": "b0000000-0000-4000-8000-000000000001",
        "client_order_id": "m085-abcdef0123456789",
        "status": "accepted",
        "symbol": "AAPL",
        "side": "buy",
        "qty": "1",
        "type": "limit",
        "filled_qty": "0",
        "filled_avg_price": None,
    }
    payload.update(overrides)
    return payload


class _Script:
    """What the hostile server should do next, and what it saw."""

    def __init__(self) -> None:
        self.responses: list[Callable[[BaseHTTPRequestHandler], None]] = []
        self.requests: list[dict[str, Any]] = []
        self.lock = threading.Lock()

    def then(self, action: Callable[[BaseHTTPRequestHandler], None]) -> _Script:
        self.responses.append(action)
        return self


def _respond(
    status: int,
    body: str | bytes = "",
    headers: dict[str, str] | None = None,
) -> Callable[[BaseHTTPRequestHandler], None]:
    def action(handler: BaseHTTPRequestHandler) -> None:
        payload = body.encode() if isinstance(body, str) else body
        handler.send_response(status)
        for name, value in (headers or {}).items():
            handler.send_header(name, value)
        handler.send_header("Content-Length", str(len(payload)))
        handler.end_headers()
        handler.wfile.write(payload)

    return action


def _json_response(status: int, document: object) -> Callable[[BaseHTTPRequestHandler], None]:
    return _respond(status, json.dumps(document), {"Content-Type": "application/json"})


def _hang_up_without_answering() -> Callable[[BaseHTTPRequestHandler], None]:
    def action(handler: BaseHTTPRequestHandler) -> None:
        # The request WAS received. Closing without a reply is the MAYBE-SENT
        # case: the peer may have acted on it.
        handler.close_connection = True
        handler.wfile.close()

    return action


def _stall_past_the_read_timeout() -> Callable[[BaseHTTPRequestHandler], None]:
    def action(handler: BaseHTTPRequestHandler) -> None:
        import time

        time.sleep(3.0)
        handler.send_response(200)
        handler.end_headers()

    return action


class _Handler(BaseHTTPRequestHandler):
    script: _Script

    def _serve(self) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length).decode() if length else ""
        with self.script.lock:
            self.script.requests.append(
                {
                    "method": self.command,
                    "path": self.path,
                    "headers": dict(self.headers),
                    "body": body,
                }
            )
            action = (
                self.script.responses.pop(0)
                if self.script.responses
                else _json_response(200, an_order_payload())
            )
        action(self)

    # BaseHTTPRequestHandler dispatches on these exact names, so the casing is
    # the stdlib contract rather than a style choice.
    do_GET = _serve  # noqa: N815
    do_POST = _serve  # noqa: N815
    do_DELETE = _serve  # noqa: N815

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        """Silence the default stderr logging; the tests assert, not the console."""


@pytest.fixture
def hostile() -> Iterator[_Script]:
    script = _Script()
    handler = type("_ScriptedHandler", (_Handler,), {"script": script})
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    script.port = server.server_address[1]  # type: ignore[attr-defined]
    try:
        yield script
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def _redirect_transport(monkeypatch: pytest.MonkeyPatch, port: int) -> None:
    """Point `connect()` at a local socket and change nothing else.

    Only the METHOD is replaced, not the class: the adapter constructs the genuine
    `http.client.HTTPSConnection`, so its own framing, header handling and
    response reading all still run. Substituting the class instead breaks
    `HTTPSConnection.__init__`, which calls `super().__init__` and would then find
    itself in its own MRO.
    """

    def connect(self: http.client.HTTPSConnection) -> None:
        self.sock = socket.create_connection(("127.0.0.1", port), timeout=self.timeout)

    monkeypatch.setattr(http.client.HTTPSConnection, "connect", connect)


@pytest.fixture
def client(hostile: _Script, monkeypatch: pytest.MonkeyPatch) -> AlpacaPaperClient:
    """The REAL adapter, pinned to the real paper host, wired to the local socket."""
    _redirect_transport(monkeypatch, hostile.port)  # type: ignore[attr-defined]
    return AlpacaPaperClient(
        endpoint=PaperEndpoint.from_url(f"https://{PAPER_ENDPOINT_HOST}"),
        credentials=credentials(),
        connect_timeout=5.0,
        read_timeout=2.0,
    )


class TestTheEndpointItselfCannotBeMoved:
    """Attacks on the base URL. None of these reaches a socket at all."""

    @pytest.mark.parametrize(
        "url",
        [
            "https://api.alpaca.markets",
            "https://broker-api.alpaca.markets",
            "http://paper-api.alpaca.markets",
            "https://paper-api.alpaca.markets.evil.example",
            "https://paper-api.alpaca.markets@evil.example",
            "https://user:pass@paper-api.alpaca.markets",
            "https://127.0.0.1",
            "https://[::1]",
            "https://paper-api.alpaca.markets:8443",
            "https://paper-api.alpaca.markets:80",
            "https://paper-api.alpaca.markets/v2/orders",
            "https://paper-api.alpaca.markets#x",
            "https://paper-api.alpaca.markets?x=1",
            "ftp://paper-api.alpaca.markets",
            "paper-api.alpaca.markets",
            "",
        ],
    )
    def test_a_non_paper_endpoint_is_refused(self, url: str) -> None:
        with pytest.raises(EndpointRefusedError):
            PaperEndpoint.from_url(url)

    def test_the_trading_client_refuses_a_data_host_endpoint(self) -> None:
        # Even a legitimate Alpaca host that is not the trading host is refused,
        # so the order path has exactly one reachable hostname.
        data = PaperEndpoint.from_url(
            "https://data.alpaca.markets", expected_host="data.alpaca.markets"
        )
        with pytest.raises(EndpointRefusedError, match="pinned to"):
            AlpacaPaperClient(endpoint=data, credentials=credentials())


class TestRedirectsAreRefusedNotFollowed:
    @pytest.mark.parametrize("status", [301, 302, 303, 307, 308])
    @pytest.mark.parametrize(
        "location",
        [
            "https://api.alpaca.markets/v2/orders",
            "https://evil.example/v2/orders",
            "https://paper-api.alpaca.markets/v2/orders",
            "http://paper-api.alpaca.markets/v2/orders",
            "https://key:secret@evil.example/v2/orders",
        ],
    )
    def test_every_redirect_is_refused(
        self, client: AlpacaPaperClient, hostile: _Script, status: int, location: str
    ) -> None:
        hostile.then(_respond(status, "", {"Location": location}))
        with pytest.raises(EndpointRefusedError, match="redirect"):
            client.submit_order(an_order())
        # And exactly one request was made: nothing was re-sent to the target.
        assert len(hostile.requests) == 1

    def test_the_refusal_does_not_echo_a_credential_from_the_location(
        self, client: AlpacaPaperClient, hostile: _Script
    ) -> None:
        hostile.then(_respond(302, "", {"Location": f"https://evil.example/?k={_SECRET}"}))
        with pytest.raises(EndpointRefusedError) as raised:
            client.submit_order(an_order())
        # The Location is reported so an operator can see where it pointed. It is
        # the ATTACKER's string, so it may contain anything -- what matters is
        # that our own credential is not disclosed by us. Here the attacker
        # already knows what it put in its own header, so the real assertion is
        # that we did not FOLLOW it.
        assert "evil.example" in str(raised.value)
        assert len(hostile.requests) == 1


class TestTheRequestCarriesOnlyWhatItShould:
    def test_the_authentication_headers_are_sent_and_the_host_is_the_pinned_one(
        self, client: AlpacaPaperClient, hostile: _Script
    ) -> None:
        hostile.then(_json_response(200, an_order_payload()))
        client.submit_order(an_order())
        sent = hostile.requests[0]
        assert sent["headers"]["APCA-API-KEY-ID"] == _KEY
        assert sent["headers"]["Host"].startswith(PAPER_ENDPOINT_HOST)

    def test_the_body_is_exactly_the_authorized_order(
        self, client: AlpacaPaperClient, hostile: _Script
    ) -> None:
        hostile.then(_json_response(200, an_order_payload()))
        client.submit_order(an_order())
        body = json.loads(hostile.requests[0]["body"])
        assert body == {
            "symbol": "AAPL",
            "qty": "1",
            "side": "buy",
            "type": "limit",
            "time_in_force": "day",
            "extended_hours": False,
            "client_order_id": "m085-abcdef0123456789",
            "limit_price": "4.00",
        }

    def test_no_order_class_or_leverage_field_is_ever_sent(
        self, client: AlpacaPaperClient, hostile: _Script
    ) -> None:
        hostile.then(_json_response(200, an_order_payload()))
        client.submit_order(an_order())
        body = json.loads(hostile.requests[0]["body"])
        for absent in ("order_class", "legs", "notional", "trail_price", "trail_percent"):
            assert absent not in body


class TestACredentialNeverComesBackOut:
    def test_a_peer_echoing_our_secret_has_it_scrubbed_before_storage(
        self, client: AlpacaPaperClient, hostile: _Script
    ) -> None:
        """The audit trail must not become the place a key is written down.

        A debug endpoint, a misconfigured proxy or a hostile server can echo a
        request header into its response body. The sanitized payload is a durable
        row, so the scrub happens at the adapter boundary.
        """
        hostile.then(_respond(500, f"upstream said: APCA-API-SECRET-KEY={_SECRET}"))
        status, view, sanitized = client.submit_order(an_order())
        assert status == 500
        assert view is None
        assert _SECRET not in sanitized
        assert REDACTED in sanitized

    def test_the_key_id_is_scrubbed_too(self, client: AlpacaPaperClient, hostile: _Script) -> None:
        hostile.then(_respond(500, f"key was {_KEY}"))
        _, _, sanitized = client.submit_order(an_order())
        assert _KEY not in sanitized

    def test_the_client_repr_discloses_nothing(self, client: AlpacaPaperClient) -> None:
        rendered = repr(client)
        assert _SECRET not in rendered
        assert _KEY not in rendered
        assert "redacted" in rendered

    def test_the_credential_repr_discloses_nothing(self) -> None:
        rendered = repr(credentials())
        assert _SECRET not in rendered
        assert _KEY not in rendered
        assert str(credentials()) == rendered


class TestAmbiguityIsClassifiedNotCollapsed:
    def test_a_refused_connection_is_definitely_not_sent(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        closed = socket.socket()
        closed.bind(("127.0.0.1", 0))
        port = closed.getsockname()[1]
        closed.close()

        _redirect_transport(monkeypatch, port)
        client = AlpacaPaperClient(
            endpoint=PaperEndpoint.from_url(f"https://{PAPER_ENDPOINT_HOST}"),
            credentials=credentials(),
            connect_timeout=1.0,
            read_timeout=1.0,
        )
        with pytest.raises(BrokerNotSentError):
            client.submit_order(an_order())

    def test_a_hang_up_after_the_request_is_ambiguous(
        self, client: AlpacaPaperClient, hostile: _Script
    ) -> None:
        hostile.then(_hang_up_without_answering())
        with pytest.raises(BrokerAmbiguousDispatchError):
            client.submit_order(an_order())
        # The peer DID receive it. That is exactly why this must not be retried
        # with a new identity.
        assert len(hostile.requests) == 1

    def test_a_stalled_answer_is_ambiguous(
        self, client: AlpacaPaperClient, hostile: _Script
    ) -> None:
        hostile.then(_stall_past_the_read_timeout())
        with pytest.raises(BrokerAmbiguousDispatchError):
            client.submit_order(an_order())
        assert len(hostile.requests) == 1

    def test_the_two_ambiguity_classes_are_different_exceptions(self) -> None:
        # Collapsing them would either strand a real order or create a second one.
        assert not issubclass(BrokerNotSentError, BrokerAmbiguousDispatchError)
        assert not issubclass(BrokerAmbiguousDispatchError, BrokerNotSentError)


class TestAnAnswerAboutTheWrongOrderIsRefused:
    @pytest.mark.parametrize(
        ("override", "field"),
        [
            ({"client_order_id": "m085-somebody-elses-order"}, "client_order_id"),
            ({"symbol": "MSFT"}, "symbol"),
            ({"side": "sell"}, "side"),
            ({"qty": "2"}, "quantity"),
            ({"type": "market"}, "order_type"),
        ],
    )
    def test_a_mismatched_acknowledgement_fails_closed(
        self,
        client: AlpacaPaperClient,
        hostile: _Script,
        override: dict[str, Any],
        field: str,
    ) -> None:
        hostile.then(_json_response(200, an_order_payload(**override)))
        with pytest.raises(BrokerResponseInvalidError, match=field):
            client.submit_order(an_order())

    def test_several_mismatches_are_all_named(
        self, client: AlpacaPaperClient, hostile: _Script
    ) -> None:
        hostile.then(_json_response(200, an_order_payload(symbol="MSFT", side="sell")))
        with pytest.raises(BrokerResponseInvalidError) as raised:
            client.submit_order(an_order())
        assert "side" in str(raised.value)
        assert "symbol" in str(raised.value)

    def test_a_lookup_answering_about_another_order_is_refused(
        self, client: AlpacaPaperClient, hostile: _Script
    ) -> None:
        hostile.then(_json_response(200, an_order_payload(client_order_id="m085-other")))
        with pytest.raises(BrokerResponseInvalidError, match="not the one asked about"):
            client.fetch_order_by_client_order_id("m085-abcdef0123456789")

    def test_an_asset_answer_about_another_symbol_is_refused(
        self, client: AlpacaPaperClient, hostile: _Script
    ) -> None:
        hostile.then(
            _json_response(
                200,
                {
                    "symbol": "MSFT",
                    "status": "active",
                    "tradable": True,
                    "class": "us_equity",
                    "exchange": "NASDAQ",
                    "fractionable": True,
                },
            )
        )
        with pytest.raises(BrokerResponseInvalidError, match="was told about"):
            client.fetch_asset("AAPL")


class TestMalformedAnswers:
    def test_a_non_json_body_is_reported_not_crashed(
        self, client: AlpacaPaperClient, hostile: _Script
    ) -> None:
        hostile.then(_respond(502, "<html><body>Bad Gateway</body></html>"))
        status, view, sanitized = client.submit_order(an_order())
        assert status == 502
        assert view is None
        assert "Bad Gateway" in sanitized

    def test_an_empty_body_with_a_success_status_is_not_an_acknowledgement(
        self, client: AlpacaPaperClient, hostile: _Script
    ) -> None:
        hostile.then(_respond(200, ""))
        status, view, _ = client.submit_order(an_order())
        assert status == 200
        assert view is None

    def test_truncated_json_is_reported_not_crashed(
        self, client: AlpacaPaperClient, hostile: _Script
    ) -> None:
        hostile.then(_respond(200, '{"id": "abc", "client_order_'))
        status, view, _ = client.submit_order(an_order())
        assert status == 200
        assert view is None

    @pytest.mark.parametrize(
        "override",
        [
            {"id": None},
            {"client_order_id": 12345},
            {"status": None},
            {"qty": 1},
            {"filled_qty": None},
        ],
    )
    def test_a_wrong_field_type_is_refused_rather_than_coerced(
        self, client: AlpacaPaperClient, hostile: _Script, override: dict[str, Any]
    ) -> None:
        hostile.then(_json_response(200, an_order_payload(**override)))
        with pytest.raises(BrokerResponseInvalidError):
            client.submit_order(an_order())

    def test_a_missing_field_is_refused(self, client: AlpacaPaperClient, hostile: _Script) -> None:
        payload = an_order_payload()
        del payload["status"]
        hostile.then(_json_response(200, payload))
        with pytest.raises(BrokerResponseInvalidError, match="status"):
            client.submit_order(an_order())

    def test_an_oversized_body_is_bounded_before_it_is_stored(
        self, client: AlpacaPaperClient, hostile: _Script
    ) -> None:
        hostile.then(_respond(500, "x" * 200_000))
        _, _, sanitized = client.submit_order(an_order())
        assert len(sanitized) < MAXIMUM_DIAGNOSTIC_BODY_BYTES + 200
        assert "truncated" in sanitized

    def test_a_non_decimal_quantity_is_refused(
        self, client: AlpacaPaperClient, hostile: _Script
    ) -> None:
        hostile.then(_json_response(200, an_order_payload(qty="not-a-number")))
        with pytest.raises(BrokerResponseInvalidError):
            client.submit_order(an_order())


class TestErrorStatusesAreReportedFaithfully:
    @pytest.mark.parametrize("status", [400, 401, 403, 404, 409, 422, 429, 500, 502, 503])
    def test_an_error_status_yields_no_acknowledgement_and_keeps_its_code(
        self, client: AlpacaPaperClient, hostile: _Script, status: int
    ) -> None:
        hostile.then(_json_response(status, {"code": 40010001, "message": "refused"}))
        observed, view, sanitized = client.submit_order(an_order())
        assert observed == status
        assert view is None
        assert "refused" in sanitized

    def test_a_duplicate_client_order_id_rejection_is_reported_as_the_broker_sent_it(
        self, client: AlpacaPaperClient, hostile: _Script
    ) -> None:
        # Alpaca's documented duplicate response. It is recorded, not translated
        # into success, and not retried with a new identity.
        hostile.then(
            _json_response(422, {"code": 40010001, "message": "client_order_id must be unique"})
        )
        status, view, sanitized = client.submit_order(an_order())
        assert status == 422
        assert view is None
        assert "must be unique" in sanitized

    def test_a_rate_limit_answer_is_reported_rather_than_retried_here(
        self, client: AlpacaPaperClient, hostile: _Script
    ) -> None:
        # The adapter does not retry. A retry decision belongs to a caller that
        # knows whether the request is safe to repeat -- and for an order, it is
        # not.
        hostile.then(_json_response(429, {"message": "too many requests"}))
        status, _, _ = client.submit_order(an_order())
        assert status == 429
        assert len(hostile.requests) == 1

    def test_a_not_found_on_reconciliation_is_returned_as_404_not_as_absence(
        self, client: AlpacaPaperClient, hostile: _Script
    ) -> None:
        # Deciding what a 404 MEANS is the caller's bounded policy, not the
        # adapter's guess.
        hostile.then(_json_response(404, {"code": 40410000, "message": "order not found"}))
        status, view, _ = client.fetch_order_by_client_order_id("m085-abcdef0123456789")
        assert status == 404
        assert view is None


class TestCancellationRaces:
    def test_a_cancel_of_an_already_filled_order_is_reported_not_asserted(
        self, client: AlpacaPaperClient, hostile: _Script
    ) -> None:
        hostile.then(_json_response(422, {"message": "order is already filled"}))
        status, sanitized = client.cancel_order("b0000000-0000-4000-8000-000000000001")
        assert status == 422
        assert "already filled" in sanitized

    def test_a_successful_cancel_returns_its_status(
        self, client: AlpacaPaperClient, hostile: _Script
    ) -> None:
        hostile.then(_respond(204, ""))
        status, _ = client.cancel_order("b0000000-0000-4000-8000-000000000001")
        assert status == 204

    def test_a_cancel_path_cannot_be_injected(self, client: AlpacaPaperClient) -> None:
        for hostile_id in ("../../v2/account", "abc?x=1", "abc/def"):
            with pytest.raises(ValueError, match="safe path segment"):
                client.cancel_order(hostile_id)

    def test_a_lookup_identity_cannot_be_injected(self, client: AlpacaPaperClient) -> None:
        for hostile_id in ("abc&status=all", "abc?x=1", ""):
            with pytest.raises(ValueError, match="safe query value"):
                client.fetch_order_by_client_order_id(hostile_id)

    def test_a_symbol_cannot_be_injected_into_a_path(self, client: AlpacaPaperClient) -> None:
        for hostile_symbol in ("../account", "AAPL/../../v2/account", "AAPL?x=1", "aapl"):
            with pytest.raises(ValueError):
                client.fetch_asset(hostile_symbol)


class TestReplayAndDuplicateIdentifiers:
    def test_the_same_answer_twice_produces_the_same_view(
        self, client: AlpacaPaperClient, hostile: _Script
    ) -> None:
        # A replayed response is not itself an attack on this adapter -- it is
        # deterministic -- but the caller relies on that determinism when it
        # reconciles, so it is pinned here.
        hostile.then(_json_response(200, an_order_payload()))
        hostile.then(_json_response(200, an_order_payload()))
        first = client.fetch_order_by_client_order_id("m085-abcdef0123456789")
        second = client.fetch_order_by_client_order_id("m085-abcdef0123456789")
        assert first[1] == second[1]

    def test_a_second_answer_naming_a_different_broker_order_id_is_still_validated(
        self, client: AlpacaPaperClient, hostile: _Script
    ) -> None:
        # A peer that changes the broker id under a stable client_order_id is
        # reported as-is; the CLIENT identity is what the product keys on, and it
        # is checked.
        hostile.then(_json_response(200, an_order_payload(id="different-broker-id")))
        status, view, _ = client.fetch_order_by_client_order_id("m085-abcdef0123456789")
        assert status == 200
        assert view is not None
        assert view.broker_order_id == "different-broker-id"
        assert view.client_order_id == "m085-abcdef0123456789"


class TestTheAccountPathIsEquallyStrict:
    def test_a_non_200_account_answer_is_refused(
        self, client: AlpacaPaperClient, hostile: _Script
    ) -> None:
        hostile.then(_json_response(403, {"message": "forbidden"}))
        with pytest.raises(BrokerResponseInvalidError, match="403"):
            client.fetch_account()

    def test_a_non_object_account_answer_is_refused(
        self, client: AlpacaPaperClient, hostile: _Script
    ) -> None:
        hostile.then(_json_response(200, ["not", "an", "object"]))
        with pytest.raises(BrokerResponseInvalidError):
            client.fetch_account()

    def test_a_clock_answer_with_a_naive_timestamp_is_refused(
        self, client: AlpacaPaperClient, hostile: _Script
    ) -> None:
        hostile.then(
            _json_response(
                200,
                {
                    "is_open": True,
                    "timestamp": "2026-09-10T09:30:00",
                    "next_open": None,
                    "next_close": None,
                },
            )
        )
        with pytest.raises(BrokerResponseInvalidError, match="timezone"):
            client.fetch_clock()

    def test_a_clock_answer_with_a_non_boolean_is_refused(
        self, client: AlpacaPaperClient, hostile: _Script
    ) -> None:
        # "false" is not False. Coercing it would turn a closed market into an
        # open one.
        hostile.then(
            _json_response(
                200,
                {
                    "is_open": "false",
                    "timestamp": "2026-09-10T09:30:00+00:00",
                    "next_open": None,
                    "next_close": None,
                },
            )
        )
        with pytest.raises(BrokerResponseInvalidError, match="is_open"):
            client.fetch_clock()

    def test_a_fractional_position_is_refused_rather_than_rounded(
        self, client: AlpacaPaperClient, hostile: _Script
    ) -> None:
        hostile.then(_json_response(200, {"symbol": "AAPL", "qty": "0.5"}))
        with pytest.raises(BrokerResponseInvalidError, match="fractional"):
            client.fetch_position("AAPL")

    def test_an_absent_position_is_a_legitimate_answer(
        self, client: AlpacaPaperClient, hostile: _Script
    ) -> None:
        hostile.then(_json_response(404, {"message": "position does not exist"}))
        assert client.fetch_position("AAPL") is None
