# MILESTONE-092 Phase 14 -- VALIDATION Result (frozen V2-C, run exactly once)

Sessions: 40 (2026-05-13 -> 2026-07-07). Fingerprint verified: `2fcd41e03da2a9a20ee5b617bab02f49e97077eb9ed8ff8b59966a7ac3c8e604`.

## COST_MODEL_0 (idealized)

| Metric | Value |
|---|---|
| Observations | 113816 |
| Opportunities (ACTIONABLE) | 2218 |
| Rejected | 111598 |
| Trades resolved | 2218 |
| Target hits | 823 |
| Stop hits | 1107 |
| Mandatory exits | 288 |
| Unresolved | 0 |
| Gross P&L (COST 0) | 159.66 |
| Average trade | 0.07 |
| Median trade | -1.21 |
| Hit rate | 0.44 |
| Average winner | 5.90 |
| Average loser | -4.58 |
| Payoff ratio | 1.29 |
| Profit factor | 1.03 |
| Max drawdown | 661.22 |
| Longest losing streak | 18 |
| Average holding (s) | 1920.3 |
| Rejection reasons | {'INSUFFICIENT_LIQUIDITY_RELATIVE': 45350, 'NO_BREAKOUT_STRUCTURE': 17499, 'INSUFFICIENT_LIQUIDITY_ABSOLUTE': 46993, 'WEAK_BREAKOUT_VOLUME_RATIO': 815, 'WEAK_CLOSE_LOCATION': 536, 'REWARD_RISK_TOO_LOW': 324, 'TARGET_NOT_FEASIBLE_IN_REMAINING_TIME': 81} |

## COST_MODEL_1 (base conservative) -- primary viability judgment

| Metric | Value |
|---|---|
| Observations | 113816 |
| Opportunities (ACTIONABLE) | 2218 |
| Rejected | 111598 |
| Trades resolved | 2218 |
| Target hits | 823 |
| Stop hits | 1107 |
| Mandatory exits | 288 |
| Unresolved | 0 |
| Gross P&L (COST 0) | 159.66 |
| Average trade | -1.66 |
| Median trade | -2.76 |
| Hit rate | 0.38 |
| Average winner | 4.98 |
| Average loser | -5.73 |
| Payoff ratio | 0.87 |
| Profit factor | 0.53 |
| Max drawdown | 3808.44 |
| Longest losing streak | 31 |
| Average holding (s) | 1920.3 |
| Rejection reasons | {'INSUFFICIENT_LIQUIDITY_RELATIVE': 45350, 'NO_BREAKOUT_STRUCTURE': 17499, 'INSUFFICIENT_LIQUIDITY_ABSOLUTE': 46993, 'WEAK_BREAKOUT_VOLUME_RATIO': 815, 'WEAK_CLOSE_LOCATION': 536, 'REWARD_RISK_TOO_LOW': 324, 'TARGET_NOT_FEASIBLE_IN_REMAINING_TIME': 81} |

## COST_MODEL_2 (stress)

| Metric | Value |
|---|---|
| Observations | 113816 |
| Opportunities (ACTIONABLE) | 2218 |
| Rejected | 111598 |
| Trades resolved | 2218 |
| Target hits | 823 |
| Stop hits | 1107 |
| Mandatory exits | 288 |
| Unresolved | 0 |
| Gross P&L (COST 0) | 159.66 |
| Average trade | -5.14 |
| Median trade | -5.83 |
| Hit rate | 0.21 |
| Average winner | 4.18 |
| Average loser | -7.56 |
| Payoff ratio | 0.55 |
| Profit factor | 0.14 |
| Max drawdown | 11430.47 |
| Longest losing streak | 55 |
| Average holding (s) | 1920.3 |
| Rejection reasons | {'INSUFFICIENT_LIQUIDITY_RELATIVE': 45350, 'NO_BREAKOUT_STRUCTURE': 17499, 'INSUFFICIENT_LIQUIDITY_ABSOLUTE': 46993, 'WEAK_BREAKOUT_VOLUME_RATIO': 815, 'WEAK_CLOSE_LOCATION': 536, 'REWARD_RISK_TOO_LOW': 324, 'TARGET_NOT_FEASIBLE_IN_REMAINING_TIME': 81} |

## Concentration (COST_MODEL_1, share-of-gross-profit formula)

- Total net P&L: -3691.49
- Total gross profit: 4196.95
- Top symbol by trade count: SPY (336 trades, 15.15% of all trades)
- Top symbol by gross profit: AMZN (20.46% of gross profit)
- Top day by gross profit: 2026-06-11 (7.47% of gross profit)
- Net P&L excluding top-trade-count symbol: -3180.94
- Net P&L excluding top-gross-profit day: -3686.55

## Holdout trigger: NOT TRIGGERED

VALIDATION did NOT clear the required bar -- per Phase 14's own instruction, classified NO_EDGE_V2 and FINAL HOLDOUT was never fetched or evaluated. The 40-session FINAL HOLDOUT block (2026-03-18 -> 2026-05-12) remains genuinely unseen by any V2 candidate evaluation.
