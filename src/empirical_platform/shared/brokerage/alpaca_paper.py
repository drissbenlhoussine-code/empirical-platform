"""MILESTONE-085 -- the strict Alpaca PAPER adapter. One host, no redirects.

WHY `http.client` AND NOT AN SDK. Two reasons, and the second is the important
one.

First, MILESTONE-084 installed a package-wide architecture rule forbidding EVERY
module of this package from importing a broker SDK that can place, modify or
cancel an order (`tools/check_architecture.py`, ORDER_SUBMISSION_PREFIXES,
`alpaca` and `alpaca_trade_api` among them). This adapter adds the paper-order
capability WITHOUT weakening that rule by one line, because it imports no broker
SDK at all. The M084 boundary is still exactly where M084 put it.

Second, and more to the point: an SDK decides for you what a base URL means,
whether to follow a redirect, how long to wait, what to retry and what to log. A
milestone whose entire purpose is that an order reaches ONE host, ONCE, and that
an ambiguous answer is never converted into a second order, cannot delegate any
of those four decisions. `http.client` is used rather than `urllib.request`
because it separates connecting, sending and reading into three calls -- which is
what makes the DEFINITELY-NOT-SENT / MAYBE-SENT distinction below observable
rather than guessed.

WHAT THIS ADAPTER CANNOT DO. It has no method taking a URL, a host, a header
mapping, a raw body, or a symbol-and-side pair the caller assembled. It cannot
express a sell, a short, a fractional quantity, an extended-hours order or a
time in force other than DAY, because `PaperOrderRequest` cannot express those
and nothing else is accepted. There is no `--force`, no live mode, and no
argument that changes the endpoint.

REDIRECTS ARE REFUSED, NOT FOLLOWED. `http.client` does not follow redirects, so
a 3xx arrives as a response rather than as a silent hop; it is then refused
explicitly. This matters more than it looks: a followed cross-host redirect is
exactly how a request authorized for a paper endpoint would arrive at a live
one, and it would carry the credentials with it.

CREDENTIALS NEVER APPEAR ANYWHERE. They are held in a type whose `__repr__` and
`__str__` are redacted, they are written only into request headers, and every
diagnostic path in this module passes headers through `redact_headers` first.
Response bodies are bounded and stored sanitized. No exception raised here
carries a credential, because no exception is constructed from a header value.

TRUST NOTHING THE PEER ECHOES. `_validated_order_view` compares the broker's
answer field by field against the request that was sent, and refuses a mismatch
in `client_order_id`, symbol, side, quantity or order type. A peer that returns
somebody else's order, or a different order than the one authorized, is a
failure to fail closed on -- not a result to persist.
"""

from __future__ import annotations

import hashlib
import http.client
import json
import ssl
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from types import MappingProxyType
from typing import Any, Final

from empirical_platform.decision_candidate.operator_trading_configuration import OrderType
from empirical_platform.decision_candidate.paper_execution import (
    PAPER_ENDPOINT_HOST,
    PaperOrderRequest,
)

__all__ = [
    "ALLOWED_PAPER_PORTS",
    "DATA_ENDPOINT_HOST",
    "MAXIMUM_DIAGNOSTIC_BODY_BYTES",
    "REDACTED",
    "AlpacaPaperClient",
    "AlpacaPaperCredentials",
    "AlpacaPaperMarketDataClient",
    "BrokerAmbiguousDispatchError",
    "BrokerNotSentError",
    "BrokerResponseInvalidError",
    "EndpointRefusedError",
    "PaperEndpoint",
    "credentials_from_environment",
    "redact_headers",
]

REDACTED: Final = "<redacted>"

#: Header names whose VALUES must never be rendered. Compared case-folded,
#: because a peer -- or a future edit -- may use any casing.
_SENSITIVE_HEADERS: Final = frozenset(
    {
        "apca-api-key-id",
        "apca-api-secret-key",
        "authorization",
        "proxy-authorization",
        "cookie",
        "set-cookie",
    }
)

#: Only the canonical HTTPS port. `None` means "the scheme's default", which is
#: 443. An explicit non-443 port is refused: no official Alpaca documentation
#: establishes one, and accepting an arbitrary port is how a request reaches a
#: local interceptor.
ALLOWED_PAPER_PORTS: Final = frozenset({None, 443})

#: The market-data host. SEPARATE from the trading host and read-only: this
#: adapter cannot place an order, and the trading adapter cannot fetch a quote.
#: Splitting them means the order path is pinned to exactly one host with no
#: second hostname reachable from it.
DATA_ENDPOINT_HOST: Final = "data.alpaca.markets"

#: A broker response larger than this is truncated for diagnostics and refused
#: as a parse target. An unbounded read is a memory and audit-table hazard, and
#: no legitimate order response approaches this.
MAXIMUM_DIAGNOSTIC_BODY_BYTES: Final = 8192

_MAXIMUM_READ_BYTES: Final = 262_144
_DEFAULT_CONNECT_TIMEOUT_SECONDS: Final = 10.0
_DEFAULT_READ_TIMEOUT_SECONDS: Final = 20.0


class EndpointRefusedError(ValueError):
    """The endpoint is not the exact pinned paper endpoint."""


class BrokerNotSentError(RuntimeError):
    """The request DEFINITELY did not reach the broker.

    Raised only for failures that happen before any byte of the request was
    written: DNS resolution, connection refusal, TLS handshake failure. The
    caller may safely record a refusal without reconciliation, because there is
    nothing at the broker to reconcile against.
    """


class BrokerAmbiguousDispatchError(RuntimeError):
    """The request MAY have reached the broker, and no answer arrived.

    This is the state that must never become a second order. The caller records
    SUBMISSION_UNKNOWN and resolves it by asking the broker about the SAME
    `client_order_id` -- never by sending a new one.
    """


class BrokerResponseInvalidError(RuntimeError):
    """The broker answered, but the answer is not about the order we sent."""


def redact_headers(headers: dict[str, str]) -> dict[str, str]:
    """Replace every sensitive header VALUE with a placeholder.

    Names are kept: knowing that an authentication header was present is useful
    when reading a diagnostic, and the name is not the secret.
    """
    return {
        name: (REDACTED if name.lower() in _SENSITIVE_HEADERS else value)
        for name, value in headers.items()
    }


@dataclass(frozen=True)
class AlpacaPaperCredentials:
    """A paper key pair. Never rendered, never compared, never logged.

    `eq=True` is inherited but the fields are not usable for equality against a
    literal because nothing outside this process holds them. `repr` is
    overridden rather than disabled so that an accidental f-string of this object
    produces a redaction rather than a key.
    """

    key_id: str
    secret_key: str

    def __post_init__(self) -> None:
        for name, value in (("key_id", self.key_id), ("secret_key", self.secret_key)):
            if not isinstance(value, str) or not value:
                raise ValueError(f"{name} must be a non-empty string")
            if value != value.strip():
                raise ValueError(f"{name} must not carry surrounding whitespace")
            if len(value) <= 16:
                raise ValueError(f"{name} is implausibly short for a broker credential")
            if any(ord(character) < 32 or ord(character) == 127 for character in value):
                raise ValueError(f"{name} must not contain control characters")

    def __repr__(self) -> str:
        return "AlpacaPaperCredentials(key_id=<redacted>, secret_key=<redacted>)"

    __str__ = __repr__

    def headers(self) -> dict[str, str]:
        """The only place these values leave this object."""
        return {
            "APCA-API-KEY-ID": self.key_id,
            "APCA-API-SECRET-KEY": self.secret_key,
        }


def credentials_from_environment(environment: dict[str, str]) -> AlpacaPaperCredentials:
    """Read the paper credentials from a caller-supplied environment mapping.

    Takes the mapping rather than reading `os.environ` itself so that the
    composition root decides where credentials come from, and so that no test
    needs a real one to exercise this path.
    """
    key = environment.get("EMPIRICAL_ALPACA_PAPER_API_KEY", "")
    secret = environment.get("EMPIRICAL_ALPACA_PAPER_SECRET_KEY", "")
    missing = [
        name
        for name, value in (
            ("EMPIRICAL_ALPACA_PAPER_API_KEY", key),
            ("EMPIRICAL_ALPACA_PAPER_SECRET_KEY", secret),
        )
        if not value
    ]
    if missing:
        raise ValueError(f"paper credentials are absent from the environment: {sorted(missing)}")
    return AlpacaPaperCredentials(key_id=key, secret_key=secret)


@dataclass(frozen=True)
class PaperEndpoint:
    """A base URL that has been PROVEN to be the paper endpoint.

    Constructing one is the only way to get a host into the client, so every
    refusal below is unavoidable rather than a check a caller might skip.
    """

    host: str
    port: int | None

    @classmethod
    def from_url(cls, url: str, *, expected_host: str = PAPER_ENDPOINT_HOST) -> PaperEndpoint:
        """Parse and pin, refusing everything that is not exactly the paper host.

        Deliberately NOT trusting the variable a URL arrived in. A value whose
        environment variable is named `..._PAPER_BASE_URL` is not thereby a paper
        URL; only this function's refusals establish that.
        """
        if not isinstance(url, str) or not url:
            raise EndpointRefusedError("the endpoint URL must be a non-empty string")
        if url != url.strip():
            raise EndpointRefusedError("the endpoint URL must not carry surrounding whitespace")

        # Parsed by hand rather than with urlsplit: urlsplit accepts several
        # shapes that are not URLs at all and normalizes others, and the point
        # here is to refuse anything that is not the one exact form.
        scheme, separator, remainder = url.partition("://")
        if not separator:
            raise EndpointRefusedError("the endpoint URL must include a scheme")
        if scheme != "https":
            raise EndpointRefusedError(
                f"only https is permitted; {scheme!r} would send credentials in clear text"
            )
        if "#" in remainder:
            raise EndpointRefusedError("the endpoint URL must not carry a fragment")
        if "?" in remainder:
            raise EndpointRefusedError("the endpoint URL must not carry a query string")

        authority, slash, path = remainder.partition("/")
        if slash and path not in {""}:
            raise EndpointRefusedError(
                "the endpoint URL must be a bare origin; a path is added by this adapter"
            )
        if "@" in authority:
            # Userinfo is how `https://paper-api.alpaca.markets@evil.example`
            # reads as the paper host to a human and as `evil.example` to a
            # parser.
            raise EndpointRefusedError("the endpoint URL must not carry userinfo")
        if not authority:
            raise EndpointRefusedError("the endpoint URL must carry a host")

        host, colon, port_text = authority.partition(":")
        port: int | None = None
        if colon:
            if not port_text.isdigit():
                raise EndpointRefusedError(f"the endpoint port {port_text!r} is not a number")
            port = int(port_text)

        host = host.lower()
        if host != expected_host:
            raise EndpointRefusedError(
                f"the endpoint host must be exactly {expected_host!r}, not {host!r}"
            )
        if port not in ALLOWED_PAPER_PORTS:
            raise EndpointRefusedError(
                f"port {port} is outside the canonical HTTPS boundary for {expected_host}"
            )
        return cls(host=host, port=port)

    @property
    def origin(self) -> str:
        suffix = "" if self.port in (None, 443) else f":{self.port}"
        return f"https://{self.host}{suffix}"


@dataclass(frozen=True, slots=True)
class _ClockView:
    is_open: bool
    timestamp: datetime
    next_open: datetime | None
    next_close: datetime | None


@dataclass(frozen=True, slots=True)
class _AssetView:
    symbol: str
    status: str
    tradable: bool
    asset_class: str
    exchange: str
    fractionable: bool


@dataclass(frozen=True, slots=True)
class _PositionView:
    symbol: str
    quantity: int


@dataclass(frozen=True, slots=True)
class _OrderView:
    broker_order_id: str
    client_order_id: str
    status: str
    symbol: str
    side: str
    quantity: str
    order_type: str
    filled_quantity: str
    filled_avg_price: str | None


@dataclass(frozen=True, slots=True)
class _QuoteView:
    symbol: str
    bid: str | None
    ask: str | None
    captured_at: datetime
    source: str


def _sanitize(body: bytes, credentials: AlpacaPaperCredentials | None = None) -> str:
    """A bounded, printable rendering of a response body for the audit trail.

    Truncated rather than dropped, because the first few kilobytes of an HTML
    error page or a rejection message is exactly what a reader needs. Decoded
    with replacement so that a binary or mis-encoded body cannot raise here and
    turn a broker error into an adapter crash.
    """
    text = body[:MAXIMUM_DIAGNOSTIC_BODY_BYTES].decode("utf-8", "replace")
    if len(body) > MAXIMUM_DIAGNOSTIC_BODY_BYTES:
        text += f"...[truncated, {len(body)} bytes total]"
    printable = "".join(
        character if character == "\n" or character.isprintable() else "�" for character in text
    )
    return _scrub_credentials(printable, credentials)


def _scrub_credentials(text: str, credentials: AlpacaPaperCredentials | None) -> str:
    """Remove our own credentials from anything the peer said back to us.

    A peer that echoes a request header into its response body -- a debug endpoint,
    a misconfigured proxy, or a hostile server doing it deliberately -- would
    otherwise have the key written verbatim into `sanitized_payload`, which is a
    durable audit row. The redaction happens at the boundary rather than at the
    point of storage, because there is more than one place a response body is
    handed onward and only one place it is read.
    """
    if credentials is None:
        return text
    scrubbed = text
    for secret in (credentials.secret_key, credentials.key_id):
        if secret and secret in scrubbed:
            scrubbed = scrubbed.replace(secret, REDACTED)
    return scrubbed


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _parse_instant(value: object, *, field: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise BrokerResponseInvalidError(f"{field} is missing or not a string")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as error:
        raise BrokerResponseInvalidError(f"{field} is not an ISO-8601 instant") from error
    if parsed.tzinfo is None:
        raise BrokerResponseInvalidError(f"{field} carries no timezone")
    return parsed


def _optional_instant(value: object, *, field: str) -> datetime | None:
    if value is None:
        return None
    return _parse_instant(value, field=field)


def _require_text(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise BrokerResponseInvalidError(f"the broker response field {key!r} is missing or empty")
    return value


def _require_bool(payload: dict[str, Any], key: str) -> bool:
    value = payload.get(key)
    if not isinstance(value, bool):
        # Deliberately not truthiness. A string "false" is not False, and
        # coercing it would silently turn a blocked account into a permitted one.
        raise BrokerResponseInvalidError(f"the broker response field {key!r} is not a boolean")
    return value


def _decimal_text(value: object, *, field: str) -> str:
    if not isinstance(value, str):
        raise BrokerResponseInvalidError(f"{field} must be a decimal string")
    try:
        Decimal(value)
    except InvalidOperation as error:
        raise BrokerResponseInvalidError(f"{field} is not a valid decimal") from error
    return value


class _StrictConnection:
    """One request, with connecting, sending and reading kept separable.

    The separation is the whole point: it is what lets a failure be classified
    as DEFINITELY-NOT-SENT or MAYBE-SENT instead of being flattened into one
    "network error" that a caller would have to guess about.
    """

    def __init__(
        self,
        endpoint: PaperEndpoint,
        credentials: AlpacaPaperCredentials,
        *,
        connect_timeout: float,
        read_timeout: float,
        context: ssl.SSLContext | None = None,
    ) -> None:
        self._endpoint = endpoint
        self._credentials = credentials
        self._connect_timeout = connect_timeout
        self._read_timeout = read_timeout
        self._context = context if context is not None else ssl.create_default_context()

    def request(
        self,
        method: str,
        path: str,
        *,
        body: str | None = None,
        before_send: Callable[[], None] | None = None,
    ) -> tuple[int, dict[str, str], bytes]:
        if not path.startswith("/"):
            raise EndpointRefusedError("the request path must be absolute")
        headers = self._credentials.headers()
        headers["Accept"] = "application/json"
        if body is not None:
            headers["Content-Type"] = "application/json"

        connection = http.client.HTTPSConnection(
            self._endpoint.host,
            port=self._endpoint.port,
            timeout=self._connect_timeout,
            context=self._context,
        )
        try:
            # PHASE 1 -- connect. A failure here means nothing was sent.
            try:
                connection.connect()
            except (OSError, ssl.SSLError) as error:
                raise BrokerNotSentError(
                    f"could not reach {self._endpoint.host}: {type(error).__name__}"
                ) from error

            # PHASE 2 -- send. A failure here means the request MAY be partly
            # delivered, so it is ambiguous rather than safe to retry.
            if connection.sock is not None:
                connection.sock.settimeout(self._read_timeout)
            if before_send is not None:
                try:
                    before_send()
                except BrokerNotSentError:
                    raise
                except Exception as error:
                    raise BrokerNotSentError(
                        f"pre-send validation failed: {type(error).__name__}"
                    ) from error
            try:
                connection.request(method, path, body=body, headers=headers)
            except (OSError, http.client.HTTPException) as error:
                raise BrokerAmbiguousDispatchError(
                    f"{method} {path} may have been partly delivered: {type(error).__name__}"
                ) from error

            # PHASE 3 -- read. A failure here means the request WAS delivered and
            # the answer is unknown. This is the case that must never produce a
            # second order.
            try:
                response = connection.getresponse()
                raw = response.read(_MAXIMUM_READ_BYTES)
                status = response.status
                response_headers = {name.lower(): value for name, value in response.getheaders()}
            except (TimeoutError, OSError, http.client.HTTPException) as error:
                raise BrokerAmbiguousDispatchError(
                    f"{method} {path} was delivered but no answer arrived: {type(error).__name__}"
                ) from error
        finally:
            connection.close()

        if 300 <= status < 400:
            # Refused, never followed. A followed redirect is how a paper-only
            # request arrives at a live endpoint carrying these credentials.
            location = response_headers.get("location", "<absent>")
            raise EndpointRefusedError(
                f"the broker returned redirect {status} to {location!r}; "
                "redirects are refused because following one could leave the paper endpoint"
            )
        return status, response_headers, raw


class AlpacaPaperClient:
    """The paper trading adapter. Pinned to one host, and only these operations."""

    def __init__(
        self,
        *,
        endpoint: PaperEndpoint,
        credentials: AlpacaPaperCredentials,
        connect_timeout: float = _DEFAULT_CONNECT_TIMEOUT_SECONDS,
        read_timeout: float = _DEFAULT_READ_TIMEOUT_SECONDS,
        ssl_context: ssl.SSLContext | None = None,
    ) -> None:
        if not isinstance(endpoint, PaperEndpoint):
            raise EndpointRefusedError("endpoint must be a proven PaperEndpoint")
        if endpoint.host != PAPER_ENDPOINT_HOST:
            raise EndpointRefusedError(
                f"the trading adapter is pinned to {PAPER_ENDPOINT_HOST}, not {endpoint.host}"
            )
        self._endpoint = endpoint
        # Held ONLY so that a response body echoing them back can be scrubbed
        # before it is stored. Never rendered: this object's `repr` is redacted
        # and the credential type's own `repr` is redacted too.
        self._credentials = credentials
        self._connection = _StrictConnection(
            endpoint,
            credentials,
            connect_timeout=connect_timeout,
            read_timeout=read_timeout,
            context=ssl_context,
        )

    def __repr__(self) -> str:
        # No credential, by construction: this object holds them only inside a
        # type whose own repr is redacted.
        return f"AlpacaPaperClient(endpoint={self._endpoint.origin!r}, credentials=<redacted>)"

    @property
    def endpoint_host(self) -> str:
        return self._endpoint.host

    def _json(
        self,
        method: str,
        path: str,
        *,
        body: str | None = None,
        before_send: Callable[[], None] | None = None,
    ) -> tuple[int, Any, str]:
        if before_send is None:
            status, _, raw = self._connection.request(method, path, body=body)
        else:
            status, _, raw = self._connection.request(
                method, path, body=body, before_send=before_send
            )
        sanitized = _sanitize(raw, self._credentials)
        if not raw:
            return status, None, sanitized
        try:
            return status, json.loads(raw), sanitized
        except json.JSONDecodeError:
            # A non-JSON body is a fact to report, not a crash. An HTML error
            # page from an intermediary is the common case.
            return status, None, sanitized

    def fetch_account(self) -> tuple[int, dict[str, object]]:
        status, payload, sanitized = self._json("GET", "/v2/account")
        if status != 200 or not isinstance(payload, dict):
            raise BrokerResponseInvalidError(
                f"the account endpoint answered HTTP {status} with an unusable body: {sanitized}"
            )
        return status, payload

    def fetch_clock(self) -> _ClockView:
        status, payload, sanitized = self._json("GET", "/v2/clock")
        if status != 200 or not isinstance(payload, dict):
            raise BrokerResponseInvalidError(
                f"the clock endpoint answered HTTP {status}: {sanitized}"
            )
        return _ClockView(
            is_open=_require_bool(payload, "is_open"),
            timestamp=_parse_instant(payload.get("timestamp"), field="timestamp"),
            next_open=_optional_instant(payload.get("next_open"), field="next_open"),
            next_close=_optional_instant(payload.get("next_close"), field="next_close"),
        )

    def fetch_asset(self, symbol: str) -> _AssetView:
        self._require_plain_symbol(symbol)
        status, payload, sanitized = self._json("GET", f"/v2/assets/{symbol}")
        if status != 200 or not isinstance(payload, dict):
            raise BrokerResponseInvalidError(
                f"the asset endpoint answered HTTP {status} for {symbol}: {sanitized}"
            )
        returned = _require_text(payload, "symbol")
        if returned != symbol:
            raise BrokerResponseInvalidError(f"asked about {symbol} and was told about {returned}")
        return _AssetView(
            symbol=returned,
            status=_require_text(payload, "status"),
            tradable=_require_bool(payload, "tradable"),
            asset_class=_require_text(payload, "class"),
            exchange=_require_text(payload, "exchange"),
            fractionable=_require_bool(payload, "fractionable"),
        )

    def fetch_position(self, symbol: str) -> _PositionView | None:
        self._require_plain_symbol(symbol)
        status, payload, sanitized = self._json("GET", f"/v2/positions/{symbol}")
        if status == 404:
            # No position. Alpaca reports this as an error status; it is a
            # legitimate, expected answer and not a failure.
            return None
        if status != 200 or not isinstance(payload, dict):
            raise BrokerResponseInvalidError(
                f"the position endpoint answered HTTP {status} for {symbol}: {sanitized}"
            )
        returned = _require_text(payload, "symbol")
        if returned != symbol:
            raise BrokerResponseInvalidError(
                f"asked about the {symbol} position and was told about {returned}"
            )
        quantity_text = _decimal_text(payload.get("qty"), field="qty")
        quantity = Decimal(quantity_text)
        if quantity != quantity.to_integral_value():
            raise BrokerResponseInvalidError(
                f"the {symbol} position {quantity_text} is fractional; this product "
                "only reasons about whole shares"
            )
        return _PositionView(symbol=returned, quantity=int(quantity))

    def submit_order(
        self, order: PaperOrderRequest, *, before_send: Callable[[], None] | None = None
    ) -> tuple[int, _OrderView | None, str]:
        """Send the one authorized order, exactly as authorized.

        The body is built HERE from the typed request, so there is no path by
        which a caller supplies a field this product does not permit.
        """
        if not isinstance(order, PaperOrderRequest):
            raise ValueError("order must be a PaperOrderRequest")
        payload: dict[str, Any] = {
            "symbol": order.symbol,
            "qty": str(order.quantity),
            "side": order.side.lower(),
            "type": order.order_type.value.lower(),
            "time_in_force": order.time_in_force.lower(),
            "extended_hours": order.extended_hours,
            "client_order_id": order.client_order_id,
        }
        if order.order_type is OrderType.LIMIT and order.limit_price is not None:
            payload["limit_price"] = format(order.limit_price, "f")

        status, body, sanitized = self._json(
            "POST", "/v2/orders", body=json.dumps(payload, sort_keys=True), before_send=before_send
        )
        if status in {200, 201} and isinstance(body, dict):
            return status, self._validated_order_view(body, order=order), sanitized
        # Any other status is the broker declining. Reported with its status and
        # sanitized body so the caller can persist what actually happened.
        return status, None, sanitized

    def fetch_order_by_client_order_id(
        self, client_order_id: str
    ) -> tuple[int, _OrderView | None, str]:
        """The reconciliation path: ask about the identity we derived.

        A 404 is returned as a 404 and NOT converted into "never submitted".
        Deciding what an absence means is a policy question, and it belongs to
        the caller that knows how long ago the dispatch happened.
        """
        if not client_order_id or "&" in client_order_id or "?" in client_order_id:
            raise ValueError("client_order_id is not a safe query value")
        status, body, sanitized = self._json(
            "GET", f"/v2/orders:by_client_order_id?client_order_id={client_order_id}"
        )
        if status == 200 and isinstance(body, dict):
            view = self._order_view(body)
            if view.client_order_id != client_order_id:
                raise BrokerResponseInvalidError(
                    "the broker returned an order whose client_order_id is not the one asked about"
                )
            return status, view, sanitized
        return status, None, sanitized

    def cancel_order(self, broker_order_id: str) -> tuple[int, str]:
        if not broker_order_id or "/" in broker_order_id or "?" in broker_order_id:
            raise ValueError("broker_order_id is not a safe path segment")
        status, _, sanitized = self._json("DELETE", f"/v2/orders/{broker_order_id}")
        return status, sanitized

    @staticmethod
    def _require_plain_symbol(symbol: str) -> None:
        # A symbol goes into a URL path. Anything but upper-case letters and a
        # dot cannot be a US equity symbol, and letting one through would be a
        # path-injection surface.
        if not symbol or not all(character.isalpha() or character == "." for character in symbol):
            raise ValueError(f"{symbol!r} is not a plain equity symbol")
        if symbol != symbol.upper():
            raise ValueError("symbol must be upper-case")

    @staticmethod
    def _order_view(payload: dict[str, Any]) -> _OrderView:
        filled_average = payload.get("filled_avg_price")
        return _OrderView(
            broker_order_id=_require_text(payload, "id"),
            client_order_id=_require_text(payload, "client_order_id"),
            status=_require_text(payload, "status"),
            symbol=_require_text(payload, "symbol"),
            side=_require_text(payload, "side"),
            quantity=_decimal_text(payload.get("qty"), field="qty"),
            order_type=_require_text(payload, "type"),
            filled_quantity=_decimal_text(payload.get("filled_qty"), field="filled_qty"),
            filled_avg_price=(
                None
                if filled_average is None
                else _decimal_text(filled_average, field="filled_avg_price")
            ),
        )

    @classmethod
    def _validated_order_view(
        cls, payload: dict[str, Any], *, order: PaperOrderRequest
    ) -> _OrderView:
        """Refuse an acknowledgement that is not about the order we sent.

        Every one of these mismatches has the same consequence if tolerated: the
        product would persist a broker order identity believing it refers to the
        authorized order when it does not, and would then reconcile and cancel
        the wrong thing.
        """
        view = cls._order_view(payload)
        mismatches: list[str] = []
        if view.client_order_id != order.client_order_id:
            mismatches.append("client_order_id")
        if view.symbol != order.symbol:
            mismatches.append("symbol")
        if view.side.upper() != order.side:
            mismatches.append("side")
        if view.order_type.upper() != order.order_type.value:
            mismatches.append("order_type")
        try:
            if Decimal(view.quantity) != Decimal(order.quantity):
                mismatches.append("quantity")
        except InvalidOperation:
            mismatches.append("quantity")
        if mismatches:
            raise BrokerResponseInvalidError(
                "the broker acknowledged an order that differs from the one authorized: "
                + ", ".join(sorted(mismatches))
            )
        return view


class AlpacaPaperMarketDataClient:
    """Quotes only, pinned to the data host. Cannot place or cancel anything.

    The quote feed available to a paper/basic entitlement is IEX, NOT the
    consolidated SIP tape. A quote from here is therefore evidence about one
    venue's book at one instant and nothing more, and the authority package says
    so rather than letting a reader assume otherwise.
    """

    def __init__(
        self,
        *,
        credentials: AlpacaPaperCredentials,
        endpoint: PaperEndpoint | None = None,
        connect_timeout: float = _DEFAULT_CONNECT_TIMEOUT_SECONDS,
        read_timeout: float = _DEFAULT_READ_TIMEOUT_SECONDS,
        ssl_context: ssl.SSLContext | None = None,
    ) -> None:
        resolved = (
            endpoint
            if endpoint is not None
            else PaperEndpoint.from_url(
                f"https://{DATA_ENDPOINT_HOST}", expected_host=DATA_ENDPOINT_HOST
            )
        )
        if resolved.host != DATA_ENDPOINT_HOST:
            raise EndpointRefusedError(
                f"the market-data adapter is pinned to {DATA_ENDPOINT_HOST}, not {resolved.host}"
            )
        self._endpoint = resolved
        self._credentials = credentials
        self._connection = _StrictConnection(
            resolved,
            credentials,
            connect_timeout=connect_timeout,
            read_timeout=read_timeout,
            context=ssl_context,
        )

    def __repr__(self) -> str:
        return (
            f"AlpacaPaperMarketDataClient(endpoint={self._endpoint.origin!r}, "
            "credentials=<redacted>)"
        )

    @property
    def endpoint_host(self) -> str:
        return self._endpoint.host

    def fetch_quote(self, symbol: str) -> _QuoteView | None:
        AlpacaPaperClient._require_plain_symbol(symbol)
        status, _, raw = self._connection.request(
            "GET", f"/v2/stocks/{symbol}/quotes/latest?feed=iex"
        )
        if status != 200:
            return None
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            return None
        if not isinstance(payload, dict):
            return None
        quote = payload.get("quote")
        if not isinstance(quote, dict):
            return None
        returned = payload.get("symbol")
        if returned is not None and returned != symbol:
            raise BrokerResponseInvalidError(f"asked for a {symbol} quote and was given {returned}")
        bid = quote.get("bp")
        ask = quote.get("ap")
        return _QuoteView(
            symbol=symbol,
            bid=None if bid is None else str(bid),
            ask=None if ask is None else str(ask),
            captured_at=_parse_instant(quote.get("t"), field="quote timestamp"),
            source="alpaca-iex",
        )


#: Everything this module treats as a live endpoint and refuses. Recorded as data
#: so a test can enumerate it rather than trusting that the refusal exists.
LIVE_ENDPOINTS_REFUSED: Final = MappingProxyType(
    {
        "api.alpaca.markets": "the live trading host",
        "broker-api.alpaca.markets": "the broker (live) host",
    }
)
