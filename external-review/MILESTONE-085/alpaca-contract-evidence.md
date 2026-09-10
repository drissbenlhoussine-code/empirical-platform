# MILESTONE-085 — Alpaca Contract Evidence

Every fact this milestone relies on about Alpaca, with how it was established.
Four classifications, and nothing is recorded under a stronger one than it earned:

| Class | Meaning |
|---|---|
| `VERIFIED_PRIMARY` | Read from current official Alpaca documentation |
| `VERIFIED_EXECUTABLE` | Observed by making the request against the real paper endpoint |
| `UNVERIFIED` | Not established here. Recorded so it is not mistaken for known |
| `NOT_APPLICABLE` | Real, and deliberately outside this milestone's reachable surface |

**A note on the environment, because it differs from M084's.** MILESTONE-084 recorded
its broker research as `CONDITIONAL_AND_UNRESOLVED` because all three vendors'
documentation domains were blocked in that environment, and its
`operator-verification-checklist.md` has no completed row. In THIS environment
`docs.alpaca.markets` is reachable, so most of the table below is
`VERIFIED_PRIMARY` rather than resting on a search summary. That is a difference in
what could be read, not a difference in standards — and where a page could not be
retrieved the row still says `UNVERIFIED`.

## The endpoint and authentication

| Fact | Value | Class | Source |
|---|---|---|---|
| Paper trading base URL | `https://paper-api.alpaca.markets` | `VERIFIED_PRIMARY` | docs.alpaca.markets/docs/paper-trading |
| Live trading host (refused here) | `api.alpaca.markets` | `VERIFIED_PRIMARY` | docs.alpaca.markets/docs/authentication |
| Authentication headers | `APCA-API-KEY-ID`, `APCA-API-SECRET-KEY` | `VERIFIED_PRIMARY` | docs.alpaca.markets/docs/authentication |
| The paper endpoint accepts those headers | HTTP 200 from `GET /v2/account` | `VERIFIED_EXECUTABLE` | `paper-acceptance-results.md` |
| Non-canonical ports | No documented paper port other than the HTTPS default | `UNVERIFIED` | Nothing found establishing one, so any explicit non-443 port is refused |

## The account

| Fact | Value | Class | Source |
|---|---|---|---|
| Account endpoint | `GET /v2/account` | `VERIFIED_PRIMARY` | reference/getaccount-1 |
| Fields consumed | `id`, `status`, `currency`, `buying_power`, `cash`, `equity`, `multiplier`, `shorting_enabled`, `trading_blocked`, `transfers_blocked`, `account_blocked`, `trade_suspended_by_user` | `VERIFIED_PRIMARY` | reference/getaccount-1 |
| All twelve are present on a real paper account | Observed | `VERIFIED_EXECUTABLE` | acceptance run |
| Account status enum | `INACTIVE`, `PAPER_ONLY`, `ONBOARDING`, `SUBMISSION_FAILED`, `SUBMITTED`, `ACCOUNT_UPDATED`, `APPROVAL_PENDING`, `ACTIVE`, `REJECTED`, `ACCOUNT_CLOSED`, `APPROVED`, `ACCOUNT_CLOSED_PENDING`, `ACTION_REQUIRED`, `LIMITED` | `VERIFIED_PRIMARY` | reference/getaccount-1 |
| This paper account | `status=ACTIVE`, `multiplier=4`, `shorting_enabled=true` | `VERIFIED_EXECUTABLE` | acceptance run |
| Response carries 37 keys | Only the twelve above are stored; the rest is dropped | `VERIFIED_EXECUTABLE` | read-only probe |

**Why `multiplier=4` and `shorting_enabled=true` matter.** The paper account PERMITS
leverage and short selling. Long-only and unleveraged are therefore properties of
THIS PRODUCT, not of the account, and they have to be enforced here — which is why
`PaperOrderRequest` cannot express a sell and the migration carries a
`side = 'BUY'` CHECK. An account-level assumption would have been wrong.

## Orders

| Fact | Value | Class | Source |
|---|---|---|---|
| Order endpoint | `POST /v2/orders` | `VERIFIED_PRIMARY` | reference/postorder |
| Required fields | `type`, `time_in_force` | `VERIFIED_PRIMARY` | reference/postorder |
| Order types | `market`, `limit`, `stop`, `stop_limit`, `trailing_stop` | `VERIFIED_PRIMARY` | reference/postorder |
| Time in force | `day`, `gtc`, `opg`, `cls`, `ioc`, `fok` | `VERIFIED_PRIMARY` | reference/postorder |
| `client_order_id` | Optional, max 128 characters, auto-generated if absent | `VERIFIED_PRIMARY` | reference/postorder |
| Duplicate `client_order_id` | HTTP 422, body code `40010001`, "client_order_id must be unique" | `VERIFIED_PRIMARY` | alpaca.markets/learn — Alpaca-published, though absent from the API reference |
| Duplicate scope | Applies while the first order is still ACTIVE | `VERIFIED_PRIMARY` | same |
| Duplicate behaviour against the real endpoint | Not executed | `UNVERIFIED` | Only one submission was authorized, and it was blocked. The 422 shape is exercised against the hostile local server instead |
| `notional` | Works only for market orders and `day` | `VERIFIED_PRIMARY` | reference/postorder |
| Fractional `qty` | Market and day only per the reference; limit also permitted per orders-at-alpaca | `NOT_APPLICABLE` | The two official pages DISAGREE. Rather than pick one, `quantity` is an `int` and fractional orders are unreachable |
| Order status values | `new`, `accepted`, `pending_new`, `accepted_for_bidding`, `partially_filled`, `filled`, `done_for_day`, `canceled`, `pending_cancel`, `expired`, `replaced`, `pending_replace`, `stopped`, `rejected`, `suspended`, `calculated`, `held` | `VERIFIED_PRIMARY` | reference/postorder |
| Terminal statuses | `filled`, `canceled`, `expired`, `replaced`, `rejected` | `VERIFIED_PRIMARY` | docs/orders-at-alpaca |
| Statuses mapped here | 12 of the 17 | — | The other five have no obviously correct destination and are left unmapped on purpose |
| Extended hours | Limit orders only, `day` or `gtc`; market orders never | `VERIFIED_PRIMARY` | docs/orders-at-alpaca |
| Extended hours here | Always `false` | `NOT_APPLICABLE` | No milestone has authorized it |
| Cancellation | Possible until `filled`, `canceled` or `expired`; a partial fill can occur before a cancel is processed | `VERIFIED_PRIMARY` | docs/orders-at-alpaca |

**The duplicate-`client_order_id` row is the single most important fact in this
table.** Because Alpaca's uniqueness applies only while the first order is ACTIVE,
the broker is NOT a durable exactly-once authority: once an order reaches a terminal
state its id could be reused. That is why exactly-once here is a PostgreSQL unique
constraint and a conditional UPDATE, and why the design does not lean on the
broker's rejection.

## Order lookup and reconciliation

| Fact | Value | Class | Source |
|---|---|---|---|
| Lookup by client id | `GET /v2/orders:by_client_order_id?client_order_id=...` | `VERIFIED_PRIMARY` | reference/getorderbyclientorderid |
| Response on a match | HTTP 200 with the Order object | `VERIFIED_PRIMARY` | same |
| Response on NO match | Undocumented in the reference | `UNVERIFIED` → then | — |
| Response on no match, measured | **HTTP 404, body code `40410000`, "order not found for ..."** | `VERIFIED_EXECUTABLE` | read-only probe against the real paper endpoint |

**And what that 404 is not allowed to mean.** A request that timed out may still be
in flight, so a 404 immediately afterwards is not proof the order was never
accepted. `RECONCILIATION_UNKNOWN_POLICY` therefore requires at least two
consecutive not-found observations AND at least 60 seconds since dispatch before an
unknown outcome is resolved, and the resolution writes an operator-visible event.
The policy is a stated choice, not a proof.

## Market data

| Fact | Value | Class | Source |
|---|---|---|---|
| Data host | `https://data.alpaca.markets` | `VERIFIED_PRIMARY` | docs/about-market-data-api |
| Paper/Basic entitlement | IEX only, 15-minute historical limitation | `VERIFIED_PRIMARY` | same |
| Data rate limit | 200 requests/minute on Basic | `VERIFIED_PRIMARY` | same |
| Latest quote endpoint | `GET /v2/stocks/{symbol}/quotes/latest?feed=iex` | `VERIFIED_EXECUTABLE` | read-only probe |
| Quote shape | `quote.bp` bid, `quote.ap` ask, `quote.t` timestamp | `VERIFIED_EXECUTABLE` | read-only probe |
| Quote while the market is closed | Last session's quote, hours old; AAPL returned `ask = 0` | `VERIFIED_EXECUTABLE` | acceptance run: age 12461s, bid 299.63, ask 0 |

**`ask = 0` is why freshness is a gate and not a nicety.** A closed-market quote can
carry a degenerate value that no sanity check on the number alone would catch. The
age check catches it.

## Rate limits and retries

| Fact | Value | Class | Source |
|---|---|---|---|
| Trading API rate limit | 200 requests/minute per account | `VERIFIED_PRIMARY` | alpaca.markets/support/usage-limit-api-calls |
| Over-limit response | HTTP 429 | `VERIFIED_PRIMARY` | same |
| Rate-limit headers | `x-ratelimit-limit: 200`, `x-ratelimit-remaining`, `x-ratelimit-reset` | `VERIFIED_EXECUTABLE` | read-only probe |
| Retry guidance for orders | None adopted | `NOT_APPLICABLE` | The adapter does not retry. A retry decision needs to know whether the request is safe to repeat, and for an order it is not |

## Paper-specific limitations, from Alpaca

`VERIFIED_PRIMARY`, docs.alpaca.markets/docs/paper-trading. Paper trading does not
account for market impact, information leakage, price slippage due to latency, order
queue position for non-marketable limit orders, price improvement, regulatory fees
or dividends. Fills are simulated from real-time quotes, and eligible orders
"receive partial fills for a random size 10% of the time". Paper accounts do not
send order-fill emails.

This list is the evidentiary basis for the non-claim
`that_paper_behaviour_equals_live_behaviour`. It is Alpaca's own statement, not an
inference.

## Redirects

| Fact | Value | Class | Source |
|---|---|---|---|
| Whether the paper endpoint redirects | Not established | `UNVERIFIED` | No page found stating a redirect policy |
| What this adapter does with one | Refuses it, at every 3xx status, without following | `VERIFIED_EXECUTABLE` | 25 redirect combinations in `test_m085_hostile_http.py`, each verified to have issued exactly one request |

Not knowing whether Alpaca redirects is precisely why the adapter refuses rather
than follows. A followed cross-host redirect is how a paper-only request would
arrive at a live endpoint carrying these credentials.

## What was NOT researched, and is therefore not relied on

- Options, crypto, multi-leg and bracket/OCO/OTO order semantics — `NOT_APPLICABLE`;
  the request type cannot express them.
- Corporate-action handling, dividends, margin interest — `NOT_APPLICABLE`; this
  milestone places one order and cancels it.
- Websocket streaming — `NOT_APPLICABLE`; nothing here subscribes to a stream.
- Live account opening, funding or agreements — deliberately untouched. No broker was
  contacted, no account opened, no agreement accepted.
