# MILESTONE-085 -- Bounded Alpaca Paper Acceptance Run

Run at `2026-09-09T23:28:06.714186+00:00` (UTC).

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

- **market is_open**: `False`
- **next_open**: `2026-09-10T09:30:00-04:00`
- **asset tradable / status**: `True / active`
- **existing position**: `0`
- **real quote bid / ask**: `299.63 / 0`
- **real quote captured_at**: `2026-09-09T20:00:02.322900+00:00`
- **real quote age**: `12487s`
- **quote source**: `alpaca-iex`
- **limit / bid**: `0.0133`

## RESULT: EXTERNAL PAPER SUBMISSION -- MEASURED BLOCKED

**Reason:** the only available quote is 12487s old, beyond the 60s freshness tolerance. The tolerance is a safety control and is NOT widened to get past this; the market is closed (is_open=False) and IEX publishes no new quotes while it is.

No safety control was relaxed to get past this. The notional ceiling was not raised, the order type was not changed to market, the freshness tolerance was not widened, and no cheaper asset was substituted. All local, database and hostile-adapter validation is unaffected and is reported separately.

## What this run does NOT establish

- that a paper acknowledgement is a real-market execution
- that a paper fill predicts a live fill
- profitability, expected return, fillability or execution quality
- eligibility for, or readiness for, a live Alpaca account
- that the asserted M084 input quote describes what the market showed
- venue truth beyond what the Alpaca paper endpoint returned

