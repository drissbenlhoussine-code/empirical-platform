# MILESTONE-085 -- Bounded Alpaca Paper Acceptance Run

Run at `2026-09-28T16:05:00.753613+00:00` (UTC).

Every number below was measured against the real Alpaca **paper** endpoint.
Balances are simulated. A paper acknowledgement is not a real-market execution.

## Authorized bounds, none of them relaxed by this run

- **symbol**: `AAPL`
- **side**: `BUY only (the request type cannot express a sell)`
- **maximum notional**: `5`
- **limit price**: `4.00`
- **quote freshness tolerance**: `60s`
- **limit must be at most this fraction of the bid**: `0.5`
- **extended hours**: `False`

### Step 1 -- Environment verification (read-only)

*Expected:* the pinned paper host answers

- **trading endpoint**: `paper-api.alpaca.markets`
- **is the pinned paper host**: `True`
- **market data endpoint**: `data.alpaca.markets`
- **account reachable**: `True`
- **account status**: `ACTIVE`
- **account reference (redacted digest)**: `ref:341c858b31beccb4dfbff79a79a8a105`

### Step 2 -- Real market evidence

*Expected:* measured, and reported whatever it says

- **market is_open**: `True`
- **next_open**: `2026-09-29T09:30:00-04:00`
- **asset tradable / status**: `True / active`
- **existing position**: `0`
- **real quote bid / ask**: `340.69 / 340.74`
- **real quote captured_at**: `2026-09-28T16:05:02.307080+00:00`
- **real quote age**: `1s`
- **quote source**: `alpaca-iex`
- **limit / bid**: `0.0117`

### Step 3 -- MILESTONE-084 chain

*Expected:* a real approved intent, derived not fabricated

- **proposal-time basis host reading**: `2026-09-28 19:05:03.919504+03:00`
- **M084 derived quantity**: `1`
- **M084 derived limit price**: `4.00000000`
- **M084 proposal fingerprint**: `e326975afae0d3a28ff1b35823ef135248323cf07706c980bce744d706414b57`
- **intent-time basis host reading**: `2026-09-28T19:05:04.830488+03:00`
- **M084 intent**: `INT-085-ACCEPT`
- **M084 submission_state**: `NOT_SUBMITTED`

### Step 4 -- Submission preview

*Expected:* the exact order, and every refusal


```
=== PAPER SUBMISSION PREVIEW -- NOTHING HAS BEEN SENT ===

intent              : INT-085-ACCEPT
preview             : PVW-085-ACCEPT v1
paper account       : ref:341c858b31beccb4dfbff79a79a8a105

THE EXACT ORDER THAT WOULD BE SENT:
  symbol            : AAPL
  side              : BUY
  quantity          : 1 (whole shares; never fractional)
  order type        : LIMIT
  limit price       : 4.00
  time in force     : DAY
  extended hours    : False
  client order id   : m085-113dd0e32c4d03438f7619afb3eac3d96e651ef8
  cost ceiling      : 4.00

MARKET AND ASSET EVIDENCE:
  market open       : True
  quote bid/ask     : 340.66 / 340.74
  quote source      : alpaca-iex (IEX only, NOT the consolidated tape)
  quote captured at : 2026-09-28T19:05:06.953430+03:00
  asset tradable    : True (active, us_equity, NASDAQ)

SEND-TIME LIMITS (from the configuration; no command can change them):
  configuration     : CFG-085-ACCEPT v1
  notional cap      : 5.00
  quote max age     : 60s
  max spread        : 5.00%
  watchlist         : AAPL
  entry window      : 00:01:00-23:58:00 (UTC)
  policy fingerprint: 82714781cfc5094cf1c8a5bf2510d30acb26f024a177c415347510027c3277dd
  intent expires at : 2026-09-28T20:05:03.919504+03:00

REQUEST FINGERPRINT : e1cfe51e0aeefa94a84dcd6a382d3ab3100344828e547f0f07b4177d4064cd69

AUTHORIZABLE. To authorize, pass the fingerprint above back explicitly.
An authorization is single-use, expires, and covers this order only.

This is the ALPACA PAPER environment. An acknowledgement here is not a
real-market execution, does not predict a live fill, and says nothing
about profitability or execution quality.

```
- **authorizable**: `True`
- **cost ceiling**: `4.00000000`
- **client_order_id**: `m085-113dd0e32c4d03438f7619afb3eac3d96e651ef8`
- **request fingerprint**: `e1cfe51e0aeefa94a84dcd6a382d3ab3100344828e547f0f07b4177d4064cd69`

### Step 5 -- Human authorization

*Expected:* single-use, expiring, bound to this fingerprint

- **authorization**: `AUT-085-ACCEPT`
- **expires at**: `2026-09-28T19:10:07.344262+03:00`

### Step 6 -- Dispatch

*Expected:* exactly one order, one client_order_id

- **dispatched**: `True`
- **http status**: `200`
- **broker status**: `pending_new`
- **state**: `PAPER_ACCEPTED`
- **broker order id**: `9e9a3a5d-cfd6-44f3-a6fd-88475c4cee08`
- **note**: `the paper broker acknowledged the order`

### Step 7 -- Cancellation

*Expected:* requested immediately; a request is not a cancellation

- **state after cancel request**: `CANCEL_REQUESTED`

### Step 8 -- Reconciliation

*Expected:* the broker decides the terminal state, not us

- **final state**: `CANCELED`
- **final broker status**: `canceled`
- **filled quantity**: `0E-8`

## RESULT: EXTERNAL PAPER SUBMISSION COMPLETED

One bounded paper order was dispatched through the real human-approval flow, cancelled, and reconciled to an honestly observed terminal state.

## What this run does NOT establish

- that a paper acknowledgement is a real-market execution
- that a paper fill predicts a live fill
- profitability, expected return, fillability or execution quality
- eligibility for, or readiness for, a live Alpaca account
- that the asserted M084 input quote describes what the market showed
- venue truth beyond what the Alpaca paper endpoint returned

