# MILESTONE-092 — Research Hypotheses (written before any V2 code)

M091 classified the frozen M090 V1 policy (fingerprint
`6ed540efd2b2638bf5a3a9aae290874bad6c5fdad54c604325c86ce4fd2c49da`) as `NO_EDGE_FOUND` over
60 DEVELOPMENT sessions (2026-07-08 → 2026-09-29, 484 resolved trades). This document states
five hypotheses derived directly from that evidence, what each predicts, and how it will be
tested — before any V2 signal/geometry code is written. V1 itself is not touched anywhere in
this milestone.

## H1 — Payoff geometry

**Claim:** the fixed 2.0 reward/risk target (`minimum_reward_risk_ratio = 2`, always used as
the target's exact multiple, never exceeded — `reward_risk_min`/`median`/`max` in M091's
`results.json` are all exactly `2.00`) is too rigid relative to the observed 28–40% hit rate
and the 37.8% mandatory-exit rate. A fixed 2R target set far from where price actually tends
to travel intraday either overshoots (rarely reached, driving the high mandatory-exit rate)
or is arbitrary relative to the realized range.

**Test:** the Phase 6 MFE/MAE study measures, for every V1 entry, how far price actually
moved favorably (MFE) before mandatory liquidation, in risk-multiples (MFE / risk_per_share).
If the MFE distribution's median/75th-percentile sits well below 2.0R, the target is
structurally too far for most trades to reach — confirming H1. If MFE regularly clears 2.0R
but STOP_HIT still dominates, the problem is more about stop placement (H1 disconfirmed in
favor of a stop-geometry explanation).

**Confirming result:** MFE median « 2.0R, explaining both the 20% target-hit rate and much
of the 37.8% mandatory-exit rate. **Disconfirming result:** MFE regularly exceeds 2.0R — the
target itself is not the bottleneck.

## H2 — Entry quality

**Claim:** the breakout condition (`evaluate_structure`: close > prior range high, low ≥
prior swing low, volume > reference average) admits weak or late breakouts — a close that
just barely clears the range high, or a breakout bar far from the range edge, is treated
identically to a strong, decisive breakout.

**Test:** for each V1 entry, measure breakout distance relative to the prior bounded range
(`(close - range_high) / (range_high - range_low)`) and close-location-within-bar
(`(close - low) / (high - low)`), then compare the MFE/MAE outcome distribution for
"weak" (bottom tercile of breakout distance) vs "strong" (top tercile) entries.

**Confirming result:** strong entries show a materially better MFE/MAE ratio or hit rate than
weak ones — evidence that a stronger confirmation filter would improve entry quality.
**Disconfirming result:** no meaningful difference — breakout strength is not the
discriminating factor.

## H3 — Liquidity concentration

**Claim:** the absolute `minimum_recent_share_volume = 20,000` per-bar floor is not itself
concentrating trades in NVDA (NVDA's own typical per-minute volume is simply far higher than
every other symbol in the universe in absolute terms) — an ABSOLUTE floor structurally favors
whichever symbol trades the most shares per minute in absolute terms, regardless of whether
that symbol is proportionally more or less liquid RELATIVE TO ITSELF.

**Test:** compare, for each symbol, the fraction of its own bars that clear the 20,000-share
floor. If NVDA clears it far more often (in relative terms) than e.g. AAPL or MSFT simply
because NVDA's baseline volume is higher, an absolute floor is confirmed to structurally favor
high-share-count names over high-dollar-volume or high-relative-activity names.

**Confirming result:** NVDA's bar-pass-rate is a clear outlier vs. the other 7 symbols.
**Disconfirming result:** pass rates are roughly uniform — the floor is not the concentration
driver (something else, e.g. the breakout condition itself, is).

## H4 — Time-of-day

**Claim:** some entry periods systematically underperform — e.g. entries very late in the
regular session structurally cannot reach a 2R target before mandatory liquidation, inflating
the mandatory-exit rate for that bucket specifically.

**Test:** M091's own `results.json` already has a `per_hour_utc_cost_model_1` breakdown —
extend the Phase 6 MFE/MAE study with a per-hour remaining-session-duration measurement:
does the mandatory-exit rate rise as the decision hour approaches the session's own
mandatory-liquidation time?

**Confirming result:** mandatory-exit rate increases monotonically (or near-monotonically)
with decision hour. **Disconfirming result:** no clear time-of-day pattern — mandatory exits
are evenly distributed.

## H5 — Mandatory exit rate

**Claim:** 37.8% of V1's resolved trades hit mandatory liquidation before the stop or target,
which — combined with H1 and H4 — suggests many entries are structurally issued without
enough remaining session time for the proposed target to be realistically reachable, given
the symbol's own recent volatility/range.

**Test:** for every V1 entry, compute remaining-session-duration (minutes from decision to
mandatory liquidation) and a bounded historical volatility/range measure (e.g. average
true-range-like measure over the reference window), then check whether entries that later
hit MANDATORY_EXIT had systematically LESS remaining time and/or LOWER recent volatility
relative to the required target distance than entries that resolved via STOP_HIT/TARGET_HIT.

**Confirming result:** MANDATORY_EXIT trades show a statistically distinguishable
(shorter remaining-time / lower-volatility-relative-to-target-distance) profile from
resolved trades — directly motivating Phase 8's time-to-target feasibility gate.
**Disconfirming result:** no distinguishable profile — mandatory exits are not explained by
time/volatility feasibility alone.

## What this document does NOT do

It does not add an indicator because it is popular, does not propose parameter values yet
(those come from the Phase 6 MFE/MAE study's actual numbers, Phase 7-10's research, and
Phase 11's candidate definitions), and does not touch any M090 V1 file or constant.
