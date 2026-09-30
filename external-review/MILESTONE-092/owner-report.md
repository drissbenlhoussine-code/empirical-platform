# MILESTONE-092 — V2 Strategy Rework — Owner Report

**Headline: NO_EDGE_V2.** VALIDATION did not clear the required bar, so FINAL HOLDOUT was
never fetched or evaluated — it remains genuinely unseen. This is a research finding about
one specific frozen V2-C policy over one specific unseen 40-session sample, not a permanent
verdict on whether ANY rework of this engine could ever work.

## 1. What changed from V1?

Three research-grade changes, all frozen as candidate **V2-C** before any VALIDATION data
was touched:

- **Lowered, range-aware reward/risk floor** (1.3, down from V1's fixed 2.0) with the target
  scaling above that floor by the symbol's own recent range, instead of a single fixed
  multiple for every trade.
- **Normalized liquidity gate**: an absolute floor (2,000 shares/bar, down from 20,000) PLUS
  a requirement that recent volume be at least 1.5x the symbol's own rolling median — instead
  of one absolute floor that happened to structurally favor whichever symbol trades the most
  shares in absolute terms.
- **Time-to-target feasibility gate**: a new rule that refuses a plan outright if the required
  price move is not realistically reachable in the session time remaining, using only
  already-observed volatility/range evidence.

## 2. Why did we change it?

M091 measured M090 V1 as `NO_EDGE_FOUND` (COST 1 net **−$886.29**, profit factor **0.67**,
negative in both halves of a 60-session sample, max drawdown **$1,183.74**, 37.8% of trades
ending in a forced mandatory exit, NVDA alone producing 68% of all trades). A dedicated
MFE/MAE diagnostic study (361 real V1 entries, DEVELOPMENT sessions only) confirmed 4 of 5
hypotheses about WHY: the fixed 2.0R target sat well above the median favorable move actually
observed (1.37R); the absolute liquidity floor structurally favored NVDA (76.7% of entries);
later-session entries had a much higher forced-exit rate; and forced-exit trades had
systematically less remaining time than resolved ones. V2-C directly targets all four.

## 3. How many unseen trades were tested?

**2,218 resolved trades** on VALIDATION (40 sessions, 2026-05-13 → 2026-07-07, 296 of 320
requested symbol/session pairs returned bars — the rest were likely non-trading days).
**Zero** on FINAL HOLDOUT — it was never fetched, because VALIDATION did not clear the bar
required to proceed (see Q4).

## 4. Validation result?

**Failed.** COST_MODEL_1 (base conservative costs): net P&L **−$3,691.49**, profit factor
**0.53**, average trade **−$1.66**. The idealized (zero-friction) result was a razor-thin
**+$0.07/trade average** (profit factor 1.03) — essentially breakeven before any cost is
applied, and clearly negative once even a conservative cost assumption is applied. Per the
mission's own rule, VALIDATION failing this bar means FINAL HOLDOUT is never run and the
result is classified `NO_EDGE_V2` immediately.

## 5. Final holdout result?

**Not run.** The 40-session FINAL HOLDOUT block (2026-03-18 → 2026-05-12) was never fetched
or evaluated by any V2 candidate — this is by design (Phase 14's own rule), not an omission.

## 6. COST 1 result?

Net P&L **−$3,691.49** over 2,218 resolved trades on VALIDATION (average trade −$1.66,
median −$2.76). Under COST_MODEL_2 (stress), it worsens to **−$11,405** (average trade
−$5.14). Under the idealized COST_MODEL_0, it is roughly breakeven (+$159.66 total,
+$0.07/trade).

## 7. Profit factor?

**0.53** on VALIDATION (base cost) — meaning for every $1 the strategy made on winning
trades, it lost about $1.89 on losing trades. Idealized (zero-friction): 1.03, essentially
breakeven. Stress: 0.14.

## 8. Average trade?

**−$1.66** per trade (base cost), **+$0.07** idealized, **−$5.14** under stress.

## 9. Max drawdown?

**$3,808.44** (base cost, VALIDATION, 2,218 trades) — substantially larger in absolute terms
than V1's own $1,183.74 on DEVELOPMENT, though VALIDATION also had roughly 4.6x as many
resolved trades (2,218 vs 484), so this is not a direct apples-to-apples comparison of
per-trade risk.

## 10. Stop/Target/Mandatory Exit rates?

VALIDATION (2,218 resolved trades): **Stop hit 1,107 (49.9%)**, **Target hit 823 (37.1%)**,
**Mandatory exit 288 (13.0%)**, **Unresolved 0 (0%)**. The mandatory-exit rate dropped
sharply from V1's 37.8% to V2-C's 13.0% — the time-to-target feasibility gate (Q1) worked
exactly as designed on this dimension. It did not, on its own, fix the underlying
profitability problem.

## 11. Symbol concentration?

Much better distributed than V1: top symbol by trade count is **SPY** (336 trades, 15.15% of
all VALIDATION trades — nowhere near V1's 68% NVDA concentration). Top symbol by gross
profit is **AMZN** (20.46% of gross profit, well under any reasonable single-symbol-dependency
threshold). The normalized liquidity gate (Q1) also worked as designed on this dimension.

## 12. Biggest weakness?

The core economic edge itself. Even the IDEALIZED, zero-friction version of V2-C is only
barely breakeven (profit factor 1.03, average trade +$0.07) on unseen VALIDATION data — there
is essentially no margin to absorb any real-world execution cost, and a conservative
(not aggressive) cost assumption is enough to turn it clearly negative. The structural fixes
(payoff geometry, liquidity normalization, time-feasibility) each measurably improved their
OWN targeted symptom (mandatory-exit rate, symbol concentration) without producing a
underlying profitable signal. This matches exactly what the DEVELOPMENT-phase comparison
already found and explicitly predicted: none of V2-A/B/C showed a DEVELOPMENT edge, and
V2-C's own selection rationale stated plainly that VALIDATION success was "honestly
unlikely."

## 13. Is V2 ready for Paper automation?

**No.** Classification is `NO_EDGE_V2`. The mission's own release-gate rule requires
`CANDIDATE_EDGE_V2` (positive, profit-factor->1, positive-average-trade results in BOTH
VALIDATION and FINAL HOLDOUT, with adequate trade count and no severe degradation between
them) before any automation discussion is appropriate — this milestone does not clear even
the first of those two required passes.

## 14. What happens next?

Per the mission's own decision tree, this result maps to **`STRATEGY_REWORK_REQUIRED`** —
NOT more data collection against the same frozen V2-C rules (that is what `MORE_DATA_REQUIRED`
would mean, and does not apply here: this is a clear, decisive negative result, not an
inconclusive one). Candidate directions for a future, later-milestone V3 (none of this is
done here — V2-C remains frozen and untouched by this finding):

- The structural fixes each worked on their OWN targeted symptom (mandatory-exit rate cut
  from 37.8% to 13.0%; symbol concentration cut from 68% in one name to 15% in the top name)
  without fixing the underlying signal quality — suggesting the core breakout/entry signal
  itself, not just its surrounding risk/liquidity/timing rules, may need to change next.
- The idealized (zero-cost) result being only barely breakeven across three different
  candidate designs (V1, and now V2-A/B/C) across two independent historical samples
  (DEVELOPMENT and VALIDATION) is a consistent enough pattern to treat seriously before
  investing further engineering in geometry/liquidity/timing variations of the SAME core
  signal.

## Appendix — the three DEVELOPMENT candidates (none selected for their numbers)

All three failed to show a DEVELOPMENT edge; full detail in
`external-review/MILESTONE-092/candidate-comparison.md`.

| | Trades | Net P&L (COST 1) | Profit factor | Avg trade | Unresolved |
|---|---|---|---|---|---|
| V2-A (entry quality only) | 285 | −$519.34 | 0.63 | −$1.82 | 28 |
| V2-B (+normalized liquidity) | 4,085 | −$6,298.56 | 0.56 | −$1.54 | 33 |
| **V2-C (selected, +time-feasibility)** | 3,337 | −$5,090.61 | 0.54 (worst of the three) | −$1.53 | **0** |

V2-C was selected for structural robustness (zero unresolved trades, highest hit rate, acts
on all four confirmed hypotheses) — explicitly NOT because its DEVELOPMENT numbers were
best. They were not; its profit factor was the worst of the three. This was stated plainly
in the selection rationale before VALIDATION was ever run.

## What this report does NOT establish

- That a differently-designed V3 would perform any differently.
- Real historical spread/slippage evidence — COST_MODEL_1/2 remain documented modeled
  assumptions, not measurements (identical assumptions to M091, unchanged, per the mission's
  own instruction not to alter cost assumptions because a result looks bad).
- Live-market fillability, live costs, or live execution quality.
- Guaranteed or expected future profitability of any kind, under any classification.
