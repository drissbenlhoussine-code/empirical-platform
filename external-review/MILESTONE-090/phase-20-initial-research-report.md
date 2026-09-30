# MILESTONE-090 Phase 20 -- Initial Research Report

Generated 2026-09-30T09:08:23.031786+00:00. Produced by `tools/m090_replay.py`, a read-only
historical replay -- no broker write of any kind was made to generate this report.

## Sample

- Symbols requested: AAPL, MSFT, QQQ, SPY
- Session dates requested: 2026-09-23, 2026-09-24, 2026-09-25, 2026-09-28, 2026-09-29
- Session dates with at least one observed bar: 2026-09-23, 2026-09-24, 2026-09-25, 2026-09-28, 2026-09-29
- Policy version: M090-V1

This is a SMALL, BOUNDED sample. No claim of expected profitability is made or implied by
anything below -- that would require a far larger, statistically meaningful sample this run
does not attempt.

## ENGINE SIGNAL QUALITY

Whether the deterministic, look-ahead-safe rules behaved as designed over this sample --
NOT a claim about future returns.

- Total observations (bar-evaluations with enough reference history): 7651
- ACTIONABLE (opportunities generated): 472
- REJECTED: 7179

### Rejection reasons
- NO_BREAKOUT_STRUCTURE: 4465
- INSUFFICIENT_LIQUIDITY: 2714

### Reward/risk ratio distribution (ACTIONABLE only)
min=2.00, median=2.00, max=2.00, n=472

### Maximum-loss distribution (ACTIONABLE only, risk_per_share * quantity)
min=0.32, median=2.20, max=39.72, n=472

### Time-of-day distribution of ACTIONABLE decisions (decision hour, UTC)
13:00 UTC x29, 14:00 UTC x59, 15:00 UTC x79, 16:00 UTC x87, 17:00 UTC x62, 18:00 UTC x81, 19:00 UTC x75

## HYPOTHETICAL HISTORICAL OUTCOME

What the replay's stop/target/mandatory-exit resolution says WOULD have happened to each
ACTIONABLE decision, under the replay harness's ONE documented simplification: each bar's own
close stands in for BOTH the synthetic bid and ask (zero spread), never a real fill price or a
real market spread. This section is a hypothetical, not a real trading result.

- STOP_HIT: 271
- TARGET_HIT: 102
- MANDATORY_EXIT: 97
- UNRESOLVED_END_OF_DATA: 2

No expected-value, win-rate or profitability claim is made from this sample. A handful of
sessions cannot separate genuine edge from noise.
