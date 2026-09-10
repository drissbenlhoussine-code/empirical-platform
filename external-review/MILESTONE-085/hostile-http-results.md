# MILESTONE-085 — Hostile HTTP Results

**102 passed.** Executed by `tests/integration/test_m085_hostile_http.py` against a
real local HTTP server, over a real socket, through the real adapter.

## How a host-pinned client is tested against a hostile server

The adapter refuses every endpoint that is not exactly
`https://paper-api.alpaca.markets` — that is the property being protected — so the
attacks cannot simply point it at `http://127.0.0.1:PORT`. Instead the ENDPOINT
stays pinned and only the TRANSPORT is redirected: `HTTPSConnection.connect` is
replaced with one that opens a plain socket to a local server. The adapter still
believes it is speaking to the pinned host, still builds the same request, still
sends the same `Host` header, still reads the response through the same code, and
still applies every refusal.

This is the difference between testing a parser and testing an adapter. A fake object
returning canned dictionaries would exercise none of the framing, the status
handling, the redirect refusal, the body bounding or the phase-by-phase failure
classification — which is where the interesting failures live.

Substituting the connection CLASS instead was tried first and is wrong:
`HTTPSConnection.__init__` calls `super().__init__` and then finds itself in its own
MRO. Only the method is replaced.

## The attacks

### Endpoint substitution — 16 URLs, none of which reaches a socket

`api.alpaca.markets`, `broker-api.alpaca.markets`, an HTTP downgrade, a
suffix attack (`paper-api.alpaca.markets.evil.example`), a bare `evil.example`, two
userinfo forms, an IPv4 literal, an IPv6 literal, ports 8443 and 80, a path, a
fragment, a query string, a missing scheme, an `ftp` scheme, and the empty string.
Each is refused by `PaperEndpoint.from_url` before any connection exists.

A legitimate Alpaca host that is not the trading host — `data.alpaca.markets` — is
also refused by the trading client, so the order path has exactly one reachable
hostname.

**Userinfo needed its own test, and that is a finding.** Both the userinfo rule and
the exact-host rule refuse `https://host@evil.example`, which is the correct amount
of defence but made the userinfo check invisible: with it removed, `partition(":")`
leaves the whole `user@host` in the host slot and the host comparison refuses it
anyway. The mutation campaign SURVIVED that family until a test asserting the
userinfo-SPECIFIC message was added.

### Redirects — 25 combinations, each refused rather than followed

Statuses 301, 302, 303, 307 and 308, each with a `Location` pointing at: the live
host, an unrelated host, the same host, an HTTP downgrade of the same host, and a URL
carrying userinfo. Every one is refused, and each test additionally verifies that
**exactly one request was made** — nothing was re-sent to the target.

A followed cross-host redirect is how a paper-only request would arrive at a live
endpoint carrying these credentials, which is why `http.client` is used: it does not
follow redirects, so a 3xx arrives as a response to be refused rather than as a
silent hop.

### Credentials never come back out

A hostile server that echoes a request header into its response body would otherwise
have the key written verbatim into `sanitized_payload`, which is a durable audit row.
This was a REAL DEFECT found by writing the attack, not by reading the code:
`_scrub_credentials` now removes both the key id and the secret from every response
body at the adapter boundary. Both directions are tested, as are the redacted
`repr`s of the client and the credential type.

### Ambiguity is classified, not collapsed — three outcomes, three exceptions

| Attack | Required classification |
|---|---|
| Connection refused (dead port) | `BrokerNotSentError` — DEFINITELY not sent |
| Server receives the request then hangs up without answering | `BrokerAmbiguousDispatchError` — MAYBE sent |
| Server stalls past the read timeout | `BrokerAmbiguousDispatchError` — MAYBE sent |

Both ambiguous cases additionally verify that the peer DID receive the request, which
is exactly why they must never be retried with a new identity. A test asserts the two
exception types are not subclasses of one another, because collapsing them would
either strand a real order or create a second one.

### An answer about the wrong order is refused — 5 mismatches, each named

`client_order_id`, `symbol`, `side`, `quantity` and `order_type`. A response that
differs from the request that was sent fails closed rather than being persisted, and
several mismatches at once are all named in the message. The reconciliation lookup
refuses an order whose `client_order_id` is not the one asked about, and the asset
endpoint refuses an answer about a different symbol.

### Malformed answers — reported, never coerced

A non-JSON body (an HTML error page), an empty body with a 200, truncated JSON, five
wrong field types, a missing required field, a 200,000-byte body (bounded before
storage, and the truncation is marked), and a non-decimal quantity. None crashes the
adapter and none is coerced into a usable value.

Three type refusals are worth naming because coercion would be actively dangerous:
a naive clock timestamp is refused rather than assumed UTC; the string `"false"` for
`is_open` is refused rather than being read as truthy, because coercing it would turn
a closed market into an open one; and a fractional position quantity is refused
rather than rounded.

### Error statuses — 10, each reported faithfully

400, 401, 403, 404, 409, 422, 429, 500, 502, 503. Each yields no acknowledgement and
keeps its own code.

Two specific cases: Alpaca's documented duplicate-`client_order_id` rejection (422
with code `40010001`, "client_order_id must be unique") is recorded as sent, not
translated into success and not retried with a new identity; and a 429 is reported
rather than retried, because the adapter does not retry at all — a retry decision
needs to know whether the request is safe to repeat, and for an order it is not.

A 404 on reconciliation is returned AS a 404, not as "absence". Deciding what an
absence means is the caller's bounded policy, not the adapter's guess.

### Injection

Path and query injection are refused on the symbol (`../account`,
`AAPL/../../v2/account`, `AAPL?x=1`, lower case), on the broker order id
(`../../v2/account`, `abc?x=1`, `abc/def`) and on the client order id
(`abc&status=all`, `abc?x=1`, empty).

### Cancellation races

A cancel of an already-filled order is reported as the broker sent it (422, "order is
already filled") rather than asserted to have cancelled anything. A successful cancel
returns its status. A replayed identical answer produces an identical view, which the
caller relies on when reconciling.

## What this does not establish

- Not that Alpaca behaves as the local server did. These attacks establish what the
  ADAPTER does when a peer misbehaves; they say nothing about whether Alpaca ever
  would.
- Not TLS certificate validation. The transport is redirected to a plain local
  socket, so the handshake is not exercised; the adapter uses
  `ssl.create_default_context()` and that default is not re-proved here.
- Not rate-limit behaviour under real load. A 429 is exercised as a response shape,
  not as a condition reached by exceeding a real limit.
