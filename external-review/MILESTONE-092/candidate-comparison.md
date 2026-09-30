# MILESTONE-092 Phase 12 -- Development Comparison

(DEVELOPMENT only, never VALIDATION/HOLDOUT)

All three candidates run over the SAME 60 DEVELOPMENT sessions, COST_MODEL_1 (base conservative) used for selection, per the mission's own instruction ("Primary viability judgment = COST 1").

## V2-A (`M092-V2-A`)

| Metric | Value |
|---|---|
| Observations | 181031 |
| Opportunities (ACTIONABLE) | 313 |
| Rejected | 180718 |
| Trades resolved | 285 |
| Target hits | 58 |
| Stop hits | 115 |
| Mandatory exits | 112 |
| Unresolved | 28 |
| Gross P&L (COST 0) | 0.04 |
| Net P&L (COST 1) | -519.34 |
| Average trade | -1.82 |
| Profit factor | 0.63 |
| Hit rate | 0.27 |
| Payoff ratio | 1.73 |
| Max drawdown | 661.91 |
| Longest losing streak | 21 |
| Rejection reasons | {'INSUFFICIENT_LIQUIDITY_ABSOLUTE': 177847, 'NO_BREAKOUT_STRUCTURE': 2615, 'WEAK_BREAKOUT_VOLUME_RATIO': 196, 'WEAK_CLOSE_LOCATION': 60} |

## V2-B (`M092-V2-B`)

| Metric | Value |
|---|---|
| Observations | 181031 |
| Opportunities (ACTIONABLE) | 4118 |
| Rejected | 176913 |
| Trades resolved | 4085 |
| Target hits | 1087 |
| Stop hits | 2203 |
| Mandatory exits | 795 |
| Unresolved | 33 |
| Gross P&L (COST 0) | 818.92 |
| Net P&L (COST 1) | -6298.56 |
| Average trade | -1.54 |
| Profit factor | 0.56 |
| Hit rate | 0.31 |
| Payoff ratio | 1.27 |
| Max drawdown | 6742.29 |
| Longest losing streak | 31 |
| Rejection reasons | {'INSUFFICIENT_LIQUIDITY_RELATIVE': 56009, 'INSUFFICIENT_LIQUIDITY_ABSOLUTE': 93431, 'NO_BREAKOUT_STRUCTURE': 25488, 'WEAK_CLOSE_LOCATION': 835, 'WEAK_BREAKOUT_VOLUME_RATIO': 1150} |

## V2-C (`M092-V2-C`)

| Metric | Value |
|---|---|
| Observations | 181031 |
| Opportunities (ACTIONABLE) | 3337 |
| Rejected | 177694 |
| Trades resolved | 3337 |
| Target hits | 1302 |
| Stop hits | 1597 |
| Mandatory exits | 438 |
| Unresolved | 0 |
| Gross P&L (COST 0) | 720.24 |
| Net P&L (COST 1) | -5090.61 |
| Average trade | -1.53 |
| Profit factor | 0.54 |
| Hit rate | 0.38 |
| Payoff ratio | 0.88 |
| Max drawdown | 5303.37 |
| Longest losing streak | 31 |
| Rejection reasons | {'INSUFFICIENT_LIQUIDITY_RELATIVE': 56009, 'INSUFFICIENT_LIQUIDITY_ABSOLUTE': 93431, 'NO_BREAKOUT_STRUCTURE': 25488, 'WEAK_CLOSE_LOCATION': 835, 'WEAK_BREAKOUT_VOLUME_RATIO': 1150, 'REWARD_RISK_TOO_LOW': 643, 'TARGET_NOT_FEASIBLE_IN_REMAINING_TIME': 138} |

## Honest reading of the actual numbers

None of the three candidates show anything resembling a positive edge on DEVELOPMENT at
COST_MODEL_1 -- all three have profit factor well below 1 and negative average trade. This
is stated plainly before the selection below, which is a choice among three still-unpromising
candidates, not a claim that any of them "worked."

A few things the raw numbers show that are worth naming directly, including where they cut
AGAINST the eventual selection:

- **By net P&L and profit factor alone, V2-A looks "best"** (net -519.34, PF 0.63) -- but
  this is substantially a sample-size artifact: V2-A traded only 285 times (closest to V1's
  own absolute-liquidity-gated behavior) versus V2-B/V2-C's 3,300-4,100+ trades. A smaller
  sample naturally has a smaller absolute loss. V2-A's PF (0.63) is also WORSE than V1's own
  measured PF (0.67, per M091's `owner-report.md`) -- entry-quality confirmation ALONE (the
  untested-by-MFE-study volume-ratio/close-location-value features) did not improve on V1 in
  this development sample; if anything it was marginally worse.
- **V2-C's profit factor (0.54) is the WORST of the three**, and its payoff ratio (0.88, the
  only one of the three below 1.0) shows the lowered reward/risk floor (1.3 vs V1/V2-A/V2-B's
  2.0) traded win RATE for win SIZE in a way that did not pay off in aggregate -- this is an
  honest, negative finding about the specific H1-motivated geometry change, not hidden.
- **By average trade (the fairest sample-size-normalized comparison), V2-B (-1.54) and V2-C
  (-1.53) are statistically indistinguishable** and both less negative than V2-A (-1.82).

## Selection rationale

**Selected: V2-C**, on ROBUSTNESS/EXPLAINABILITY grounds (the mission's own Phase 12
instruction: "Do NOT simply select the highest net P&L"), not because its raw numbers are
best -- they are not; its profit factor is the worst of the three. The specific robustness
argument:

1. **Zero unresolved trades** (vs. 28 for V2-A, 33 for V2-B). Every plan V2-C proposes
   resolves to a definite TARGET_HIT/STOP_HIT/MANDATORY_EXIT within the fetched session --
   a direct, measurable, structural consequence of the time-to-target feasibility gate doing
   exactly what Phase 8 asked it to do, and a genuine improvement in what the engine's own
   evidence can honestly claim (V2-A/B leave 28-33 trades with literally no verdict, which
   means their true P&L is not fully known even in-sample).
2. **Highest hit rate (38% vs 27%/31%)**, directly addressing the MFE study's own confirmed
   H1 finding (median MFE 1.37R, well under V1's fixed 2.0R) -- more entries now resolve
   favorably before running out of session, exactly as intended.
3. V2-C is the only candidate that acts on ALL FOUR of the MFE study's CONFIRMED hypotheses
   (H1 payoff geometry, H3 liquidity concentration via the same normalized-liquidity model
   V2-B introduced, H4/H5 time-of-day and remaining-time feasibility) rather than only the
   liquidity piece (V2-B) or neither (V2-A).

**This selection is NOT a prediction that V2-C will show a positive edge on VALIDATION or
FINAL HOLDOUT.** On the numbers above, that is honestly unlikely. It is the most
structurally sound and explainable of three candidates that all failed to show a
DEVELOPMENT edge, selected before VALIDATION is ever inspected, exactly as the mission
requires -- the FROZEN result is reported honestly in Phase 14 regardless of what it shows.
