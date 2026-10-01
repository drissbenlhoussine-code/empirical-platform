# M095 Phases 8-18 -- Event + Gap Study Findings

Research dataset: 100 sessions (2026-05-13 -> 2026-09-29, the SAME M091/M092-derived
window M093/M094 used), 6 ranked symbols (AAPL, AMZN, GOOGL, META, MSFT, NVDA), SPY/QQQ as
benchmark-only. Observation point: session open (see `data-source-qualification.md` for why
this milestone studies the open rather than the mission's full open+5/15/30m sweep).
Horizons: 15m/30m/60m/120m/session, from `open+0` via `forward_return_to_horizon`/
`forward_return_to_liquidation` (M094's own, already-proven look-ahead-safe primitives,
reused unchanged). All numbers below are from `event-study-results.json`.

## Phase 10 -- gap buckets (predeclared thresholds, |gap| <= 0.1% FLAT, 0.1%-1.0% SMALL,
## beyond 1.0% LARGE)

| Bucket | n (30m) | Mean 30m | Mean 60m | Mean session | Positive % (30m) |
|---|---:|---:|---:|---:|---:|
| GAP_DOWN_LARGE | 93 | +0.068% | -0.007% | +0.001% | 58.1% |
| GAP_DOWN_SMALL | 159 | -0.034% | -0.054% | -0.124% | 48.4% |
| FLAT | 60 | +0.026% | +0.031% | -0.014% | 43.3% |
| GAP_UP_SMALL | 158 | -0.148% | -0.124% | -0.026% | 45.6% |
| GAP_UP_LARGE | 100 | +0.294% | +0.272% | +0.359% | 58.0% |

570 of 600 symbol-sessions resolved (30 missing bars/prior-close, consistent with the
15-32-empty pattern M093/M094 already documented for this same provider/window).

**Observation, flagged but NOT selected (Phase 17 discipline):** `GAP_UP_LARGE` alone
shows a materially larger mean move (+0.294% at 30m, +0.359% at session) than
`GAP_UP_SMALL` (-0.148%) or the combined event+gap-up group this milestone's predeclared
cost/temporal/cross-symbol checks actually ran against. This asymmetry was only visible
AFTER looking at the gap-bucket table -- isolating `GAP_UP_LARGE` now as a new candidate
direction would be exactly the "select the best historical cutoff after seeing outcomes"
practice Phase 10/17 explicitly forbid. It is recorded here as a lead for a future,
properly pre-registered study (its own thresholds, fixed before looking at THAT study's
own outcome data), not adopted as a selected direction in M095.

## Phase 9 -- event vs. control

**Could not be meaningfully executed as originally envisioned**: the `without_event`
group for both gap-up buckets is empty (n=0) -- every gap-up session in this dataset had
at least one qualifying company-specific article published before the open. See
`event-taxonomy.md`'s "honest, discovered limitation" section. `EARNINGS_KEYWORD_NEWS`
(n=15 at 30m) vs. `OTHER_NEWS` (n=559 at 30m) is the working substitute:

| Group | n (30m) | Mean 30m | Positive % |
|---|---:|---:|---:|
| EARNINGS_KEYWORD_NEWS | 15 | +0.146% | 40.0% |
| OTHER_NEWS | 559 | +0.014% | 50.8% |

The earnings-keyword group's mean is numerically larger but the sample (n=15) is far too
small to draw a stable conclusion, and its own positive-fraction (40%) is actually BELOW
the other-news group's (50.8%) -- consistent with noise, not a signal, over this sample
size.

## Phase 11 -- relative early volume

Among event-present gap-up observations with volume data (n=258), split at the median
relative-volume ratio (1.05x the trailing-20-session median first-30-minute volume):

| Group | n | Mean 30m | Positive % |
|---|---:|---:|---:|
| High relative volume (>= median) | 129 | +0.244% | 58.9% |
| Low relative volume (< median) | 129 | -0.197% | 41.9% |

This is the single most separated split measured in this milestone -- high-relative-
-volume event+gap-up sessions show a materially larger and more often positive 30-minute
move than low-relative-volume ones. It was NOT included in the Phase 19 decision gate
(which evaluated the single predeclared `EVENT_KNOWN_BEFORE_OPEN_PLUS_GAP_UP` direction
only) because the volume split, like the gap-magnitude split above, was identified by
looking at this study's own output rather than predeclared before running it. Recorded
here as the second most promising lead for a future, properly pre-registered follow-up.

## Phase 12 -- market context (SPY's own opening-gap sign)

| SPY gap sign | n (30m) | Mean 30m | Positive % |
|---|---:|---:|---:|
| Positive | 179 | +0.009% | 50.3% |
| Negative | 79 | +0.055% | 50.6% |

No material separation -- market-wide gap direction does not meaningfully condition the
event+gap-up effect in this sample.

## Phase 13 -- forward-return information value

Reported per group above (n, mean, median, dispersion via p10/p90, positive-fraction) --
see `event-study-results.json` for the full per-horizon breakdown (15m/30m/60m/120m/
session) of every group. No bootstrap confidence intervals were computed (the mission
allows this "where useful"; given the uniformly weak/unstable effects found, a confidence
interval would not change the Phase 19 classification).

## Phase 14 -- cost survivability

Combined event+gap-up group (`GAP_UP_SMALL` + `GAP_UP_LARGE`, n=258, the SAME predeclared
group the Phase 19 gate evaluates): mean 30m move +0.023%. COST1 round trip is 0.10%,
COST2 is 0.30% (unchanged from M091-M094). **Does not survive COST1 or COST2.**

## Phase 15 -- temporal stability

Chronological halves of the 100-session research window (first 50 vs. last 50 sessions,
by calendar date -- never the locked holdout):

| Half | n | Mean 30m (event+gap-up) |
|---|---:|---:|
| First half (2026-05-13 to ~2026-07-21) | 282 | -0.065% |
| Second half (~2026-07-22 to 2026-09-29) | 294 | +0.091% |

**Sign flips between halves.** Not temporally stable.

## Phase 16 -- cross-symbol stability

| Symbol | n | Mean 30m |
|---|---:|---:|
| AAPL | 44 | -0.092% |
| AMZN | 43 | -0.054% |
| GOOGL | 38 | -0.072% |
| META | 42 | +0.263% |
| MSFT | 38 | +0.162% |
| NVDA | 53 | -0.037% |

No symbol dominates the total (max share NVDA/META each under 21% of the 258-observation
total, well under the 60% concentration threshold), but the sign is NOT consistent: 4 of
6 symbols are negative, 2 (META, MSFT) are positive. This is broad disagreement, not a
single-symbol artifact -- the effect simply isn't there across the universe as a whole.

## Phase 17 -- selectivity

Spearman rank correlation between gap magnitude (among event-present gap-up
observations, n=287) and 30-minute forward return: **IC = +0.1525**. This is the largest
single rank-correlation measured across M093-M095's research so far (compare M094's
near-zero ICs, -0.004 to -0.02) -- a genuinely non-trivial, positive, monotonic-leaning
relationship between gap size and subsequent move among event-present gap-ups. It is
consistent with, and likely the same underlying effect as, the `GAP_UP_LARGE`-vs-
`GAP_UP_SMALL` asymmetry flagged in Phase 10 above. It did NOT, by itself, change the
Phase 19 classification, because the predeclared direction it would support
(`EVENT_KNOWN_BEFORE_OPEN_PLUS_GAP_UP`, evaluated as a single combined group) still
fails cost survivability and temporal stability on its own predeclared terms. A
genuinely new, gap-magnitude-weighted or GAP_UP_LARGE-scoped direction is a candidate
for a future, separately pre-registered study -- not retrofitted here.

## Phase 18 -- frequency economics

- Earnings-keyword or other qualifying articles: ~20.1 events/symbol/month.
- Event + gap-up (either bucket) qualifying observations: ~54.2/month across all 6
  symbols combined (~12.5/week). This sits in the mission's "moderate" (~3-8/day
  cross-symbol, roughly matching 54/month / ~21 sessions ≈ 2.6/day) to "high" frequency
  band -- frequent enough to be practically tradeable IF the effect were real, which
  Phases 14-16 show it is not, on the predeclared `EVENT_KNOWN_BEFORE_OPEN_PLUS_GAP_UP`
  direction specifically.
