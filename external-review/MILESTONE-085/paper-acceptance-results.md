# MILESTONE-085 -- Bounded Alpaca Paper Acceptance Run

Run at `2026-09-10T13:35:55.226896+00:00` (UTC).

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
- **next_open**: `2026-09-11T09:30:00-04:00`
- **asset tradable / status**: `True / active`
- **existing position**: `0`
- **real quote bid / ask**: `315.04 / 320`
- **real quote captured_at**: `2026-09-10T13:35:58.839102+00:00`
- **real quote age**: `-1s`
- **quote source**: `alpaca-iex`
- **limit / bid**: `0.0127`

### Step 3 -- MILESTONE-084 chain

*Expected:* a real approved intent, derived not fabricated

- **M084 derived quantity**: `1`
- **M084 derived limit price**: `4.00000000`
- **M084 proposal fingerprint**: `fa5db6c743f0a98d9326aa4c1a6951ebfb82a8b60cbd0def27ae734768f58309`
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
  client order id   : m085-524e58d5d797656019277f4176290c19c3fb9646
  cost ceiling      : 4.00

MARKET AND ASSET EVIDENCE:
  market open       : True
  quote bid/ask     : 319.83 / 320.17
  quote source      : alpaca-iex (IEX only, NOT the consolidated tape)
  quote captured at : 2026-09-10T16:36:02.362000+03:00
  asset tradable    : True (active, us_equity, NASDAQ)

REQUEST FINGERPRINT : 233f9ba081fa0edeaa4a50a7277cb6be8b6234e74628dfdc365b06dcbd3b41ab

REFUSED -- this preview CANNOT be authorized:
  - the captured quote is dated after this preview

This is the ALPACA PAPER environment. An acknowledgement here is not a
real-market execution, does not predict a live fill, and says nothing
about profitability or execution quality.

```
- **authorizable**: `False`
- **cost ceiling**: `4.00000000`
- **client_order_id**: `m085-524e58d5d797656019277f4176290c19c3fb9646`
- **request fingerprint**: `233f9ba081fa0edeaa4a50a7277cb6be8b6234e74628dfdc365b06dcbd3b41ab`

## RESULT: EXTERNAL PAPER SUBMISSION -- MEASURED BLOCKED

**Reason:** the preview refuses authorization: the captured quote is dated after this preview

No safety control was relaxed to get past this. The notional ceiling was not raised, the order type was not changed to market, the freshness tolerance was not widened, and no cheaper asset was substituted. All local, database and hostile-adapter validation is unaffected and is reported separately.

## What this run does NOT establish

- that a paper acknowledgement is a real-market execution
- that a paper fill predicts a live fill
- profitability, expected return, fillability or execution quality
- eligibility for, or readiness for, a live Alpaca account
- that the asserted M084 input quote describes what the market showed
- venue truth beyond what the Alpaca paper endpoint returned

