# M075 — Claim Honesty

## Classification of every claim M075 makes

| Claim | Class |
|---|---|
| "these N approved plans total X notional" | **FACT** — arithmetic over persisted rows |
| "under policy P with capital base C, K of them fit" | **DIAGNOSTIC** |
| "plan Z does not fit, reason MAX_CAPITAL_UTILIZATION_EXCEEDED" | **DIAGNOSTIC** |
| "the capital base is the equity figure supplied for sizing" | **LIMITATION** — stated in the banner |
| "prior-day positions are not considered" | **LIMITATION** — stated in the banner |

## Forbidden claims — none are made

`PROFITABLE`, `PROVEN_EDGE`, `LIVE_READY`, `BROKER_READY`, `INVESTMENT_ADVICE`,
`SURVIVORSHIP_BIAS_ELIMINATED`, `MARKET_REPRESENTATIVE`, `REALISTIC_EXECUTION`,
`PRODUCTION_TRADING_SYSTEM` — none appear, and the honesty banner explicitly disclaims
the adjacent ones a reader might otherwise infer.

## What M075 is

Research infrastructure. It is a **diagnostic over one recommendation set**. It does not
claim any position was taken, any capital was allocated or reserved, that the operator
holds anything, or that any trade is profitable.

## The outcome vocabulary was chosen for honesty

M067's `PortfolioAllocationOutcome.ALLOCATED` was deliberately **not** reused: that word
asserts capital *was allocated*. M075 allocates nothing, so it owns
`FITS_WITHIN_CAPITAL` / `EXCEEDS_CAPITAL`. Only M067's generic *reason* vocabulary is
reused. A test asserts `ALLOCATED` never appears in M075's outcome enum.
