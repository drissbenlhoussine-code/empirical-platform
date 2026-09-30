# M093 Phase 17 -- Candidate Selection

## Rule (Phase 17, verbatim)

Select at most ONE family as the M093 candidate. Selection is NOT automatically the
highest-P&L family -- it must be genuinely credible: positive COST1 expectancy, a
believable causal story for why the edge should exist, and survival of the cross-symbol /
regime / walk-forward checks above. If no family is credible, the classification is
`NO_CANDIDATE_EDGE`, and that is an acceptable result.

## Evidence summary across Phases 11-16

| Family | COST1 PF (full) | COST1 PF (best time bucket) | COST1 PF (best symbol) | Design PF | Observe PF |
|---|---:|---:|---:|---:|---:|
| TREND_CONTINUATION | 0.519 | 0.674 | 0.730 (META) | 0.572 | 0.394 |
| VWAP_PULLBACK | 0.448 | 0.571 | 0.929 (META) | 0.494 | 0.320 |
| OPENING_RANGE_5 | 0.541 | 0.841 | 0.859 (META) | 0.554 | 0.493 |
| OPENING_RANGE_15 | 0.532 | 0.805 | 1.040 (META) | 0.544 | 0.490 |
| MEAN_REVERSION | 0.375 | 0.452 | 0.431 (META) | 0.379 | 0.359 |
| RELATIVE_STRENGTH | 0.736 | 0.793 | 0.868 (AAPL/MSFT) | 0.747 | 0.695 |

No family clears profit factor 1.0 in its full-sample COST1 result. No family clears it in
either half of the within-research walk-forward split. Across all 6 families x 8 symbols x
3 time-of-day buckets (144 cells total), exactly one cell -- OPENING_RANGE_15 on META,
PF 1.040 on 1,620 trades -- clears breakeven, and it is a single cell out of 144 with a
small margin, not a repeatable pattern (the same family on the same symbol's sibling
variant, OPENING_RANGE_5, is at PF 0.859 on META; the same symbol under
TREND_CONTINUATION/VWAP_PULLBACK/MEAN_REVERSION/RELATIVE_STRENGTH is also below 1.0). This
is consistent with a single favorable-noise cell among 144, not a structural regime.

Two families (VWAP_PULLBACK, MEAN_REVERSION) received one hypothesis-driven Phase 13
revision each on the strength of a positive or near-zero idealized (COST0) result; neither
revision improved the COST1 outcome (`family-revisions.md`).

RELATIVE_STRENGTH has the best COST1 profit factor of the six variants (0.736 full-sample,
0.695 in the walk-forward observe half) and the smallest full-to-observe PF degradation of
any family (0.747 -> 0.695, versus e.g. TREND_CONTINUATION's 0.572 -> 0.394), which speaks
to some structural consistency in the signal even though it never reaches profitability.
That consistency is noted as the most credible-looking of a set of six families that all
fail, not as grounds for selection -- a family with a repeatably-measured PF of ~0.7-0.8
loses money in a stable, unsurprising way; it is not "almost an edge," it is a
non-edge measured with low variance.

## Decision

**No family is selected.** None of the six screened signal variants (5 families, with
Opening Range's two duration variants counted separately) shows a positive COST1
expectancy anywhere in the research dataset: not in the full sample, not in any of 3
time-of-day buckets, not in any of 6-8 symbols, not in either half of a chronological
walk-forward split. The two families with the most promising idealized (COST0) results
were given a limited, hypothesis-driven revision per Phase 13 and neither revision closed
the gap to COST1 profitability. The uniform failure pattern, combined with the Phase 11
spot-check confirming the cost drag matches the declared cost model exactly (not a
double-charge or other implementation defect), supports a structural conclusion rather
than a screening artifact: at this position-sizing scale and this cost assumption, none of
the five genuinely different strategy families tested produces a defensible intraday
long-only edge on this 100-session research dataset.

**Classification: `NO_CANDIDATE_EDGE`.**

Per Phase 17's own framing, this is an acceptable and informative result. It does not mean
"try harder" -- Phase 13's revision budget (at most 2 per promising family) was already
spent on the two candidates with any positive idealized signal, and Phase 12's screening
already showed the other four failing even before cost. Phase 18 (candidate freeze) is
therefore not applicable -- there is no candidate to freeze. Phase 19's confirmation that
the locked final holdout (2026-03-18 through 2026-05-12) was never touched is recorded
separately (`holdout-confirmation.md` and the accompanying test/static-check evidence);
it applies regardless of this outcome, since M093 never reaches the holdout under any
classification.
