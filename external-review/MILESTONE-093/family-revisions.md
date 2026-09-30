# M093 Phase 13 -- Hypothesis-Driven Revisions

Per Phase 13, only families showing promise or near-breakeven behavior at the Phase 12
screening (not the four already negative even at COST0) are eligible for limited revision:
VWAP_PULLBACK (COST0 PF 1.015, essentially zero idealized edge) and MEAN_REVERSION (COST0
PF 1.157, the only family with a materially positive idealized edge). One revision each was
run (of the at-most-two allowed), since the quantitative gap between COST0 and COST1 for
both families (roughly a 10x ratio of cost drag to average idealized edge per trade) made a
second iteration unlikely to be informative once the first confirmed the hypothesis did not
close that gap; both revisions are reported in full, including the one that made results
worse.

## Revision D1 -- MEAN_REVERSION, minimum_deviation_percent 0.3% -> 0.6%

**Hypothesis (stated before running):** the original 0.3% deviation floor admits shallow,
low-conviction dips whose reversion move is too small relative to the fixed round-trip cost
drag (COST1 average -$1.648/trade vs. COST0 average +$0.168/trade, roughly a 10x gap).
Requiring a deeper deviation before considering a reversion should select fewer, higher-
conviction setups with a larger expected move, improving the edge-to-cost ratio.

**Change:** `minimum_deviation_percent` 0.3 -> 0.6, all other policy fields unchanged
(regime_lookback_bars=20, maximum_adverse_trend_percent=2, minimum_liquidity_shares=2000,
minimum_reward_risk_ratio=1.2).

**Result:**

| | Resolved | COST0 net | COST0 PF | COST1 net | COST1 PF | COST1 avg/trade |
|---|---:|---:|---:|---:|---:|---:|
| Original (0.3%) | 10,787 | +1,810.20 | 1.157 | -17,775.42 | 0.375 | -1.648 |
| Revision D1 (0.6%) | 5,264 | +480.68 | 1.076 | -9,136.33 | 0.389 | -1.736 |

**Outcome: hypothesis not confirmed.** Trade count halved as expected, but both the COST0
net and COST0 PF *fell* (1.157 -> 1.076) rather than improving -- deeper dips did not carry
a proportionally larger reversion move in this dataset. COST1 PF moved from 0.375 to 0.389,
a change within noise given the reduced sample, not a material improvement, and the average
per-trade loss under COST1 actually got slightly worse (-1.648 -> -1.736). The deeper-
deviation filter does not rescue this family.

## Revision B1 -- VWAP_PULLBACK, minimum_volume_ratio 1.1x -> 1.6x

**Hypothesis (stated before running):** the original 1.1x volume-ratio confirmation is
barely above average volume, admitting low-conviction reclaims (COST0 average
+$0.030/trade -- already essentially zero edge). A materially stronger volume confirmation
should select fewer, higher-conviction reclaims with better follow-through.

**Change:** `minimum_volume_ratio` 1.1 -> 1.6, all other policy fields unchanged
(constructive_lookback_bars=20, pullback_bars=10, minimum_liquidity_shares=2000,
target_range_multiple=2, minimum_reward_risk_ratio=1.5).

**Result:**

| | Resolved | COST0 net | COST0 PF | COST1 net | COST1 PF | COST1 avg/trade |
|---|---:|---:|---:|---:|---:|---:|
| Original (1.1x) | 894 | +26.51 | 1.015 | -1,545.97 | 0.448 | -1.729 |
| Revision B1 (1.6x) | 488 | -63.45 | 0.932 | -911.07 | 0.389 | -1.867 |

**Outcome: hypothesis not confirmed, result is worse.** Requiring stronger volume
confirmation cut the trade count (894 -> 488) but the COST0 result flipped from marginally
positive to negative (PF 1.015 -> 0.932), and COST1 PF also declined (0.448 -> 0.389). A
higher volume-ratio bar in this dataset does not select better-quality reclaims; if
anything it removes some of the profitable low-volume trades along with the unprofitable
ones.

## Conclusion

Neither revision closed the COST0-to-COST1 gap, and in both cases the revision moved the
idealized (COST0) result in the wrong direction rather than improving it. This is consistent
with the Phase 11 spot-check finding: the cost drag is a fixed ~10bps-of-price round-trip
tax that is large relative to the tight stop/target geometry these intraday setups use, and
no tested structural change to entry selectivity closed that gap. Per Phase 4, the cost
model itself was not altered to rescue either family.

Both VWAP_PULLBACK and MEAN_REVERSION remain `FAMILY_REJECTED` after their one allowed
revision. No family or variant under any tested configuration in M093 survives COST1. This
carries forward into Phase 17 (candidate selection).
