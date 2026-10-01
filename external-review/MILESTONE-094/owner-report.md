# MILESTONE-094 -- Edge Source Investigation: Owner Report

Research dataset: 100 sessions (2026-05-13 -> 2026-09-29, identical to M093's own research
window), 8-symbol fixed universe, 800 symbol-session pairs fetched (768 non-empty). Locked
FINAL HOLDOUT (2026-03-18 -> 2026-05-12): **never accessed** (see `holdout-confirmation.md`).
This is an information-value survey, not a strategy build -- nothing here has entry/stop/
target geometry or position sizing.

## 1. Why did V1/V2/M093 fail?

Primarily **signal quality**, not merely turnover or cost. Of M093's six signal variants,
four were already net-negative even at COST0 (zero friction): TREND_CONTINUATION,
OPENING_RANGE_5, OPENING_RANGE_15, RELATIVE_STRENGTH. The other two (VWAP_PULLBACK,
MEAN_REVERSION) had a near-zero or small positive COST0 edge (+$0.03 and +$0.17/trade)
that a uniform ~$1.7-1.85/trade cost drag fully erased. See `research-data.md` and Phase 4
below.

## 2. Was excessive trading frequency part of the problem?

Not the primary driver. VWAP_PULLBACK -- the LOWEST-turnover family tested across M091-M093
(1.12 trades per symbol-session, roughly 1 trade/symbol/day) -- still only had a
near-breakeven gross edge before cost. Lower turnover alone did not produce a larger
per-trade gross edge in this dataset. The cost drag (~$1.7-1.85/trade) is roughly UNIFORM
across all six families regardless of how often they traded, which rules out "just trade
less" as a free rescue -- the thing being traded less often also needs a materially larger
gross edge per trade, and none of the six variants had one.

## 3. Which horizons contain the most useful structure?

None, measured unconditionally (Phase 5, own-symbol forward returns pooled across all 6
ranked symbols and the full research window):

| Horizon | n | Mean | Stdev | Sign+ |
|---|---:|---:|---:|---:|
| 5m | 37,925 | +0.00043% | 0.159% | 49.68% |
| 15m | 37,925 | +0.00121% | 0.269% | 49.95% |
| 30m | 37,925 | +0.00259% | 0.376% | 49.96% |
| 60m | 34,507 | +0.00767% | 0.519% | 50.22% |
| 120m | 27,614 | +0.01540% | 0.708% | 50.45% |
| To liquidation | 37,925 | -0.02252% | 0.813% | 49.73% |

Sign persistence sits at ~50% for every horizon -- unconditional forward returns are
indistinguishable from a coin flip at this resolution. Longer horizons show a slightly
positive mean (consistent with a small long-only market drift over 2+ hours), but the
dispersion dwarfs the mean at every horizon; this is not itself a tradeable signal, only
the backdrop the conditioning studies below are measured against.

## 4. Does multi-timeframe context help?

No. Trailing own-symbol momentum (5/15/30/60-minute rolling return) against the 30-minute
forward return:

| Feature | n | Spearman IC |
|---|---:|---:|
| Trailing 5m momentum | 37,925 | -0.0041 |
| Trailing 15m momentum | 37,925 | -0.0000 |
| Trailing 30m momentum | 37,925 | -0.0129 |
| Trailing 60m momentum | 34,469 | -0.0196 |

All four are effectively zero and, where non-zero, weakly NEGATIVE -- i.e. if anything,
recent momentum mean-reverts slightly rather than continuing, and the effect is far too
small to act on. MULTI_TIMEFRAME_TREND is not a promising direction as tested here.

## 5. Do market regimes matter?

Weakly, and not enough to matter economically (Phase 7, SPY-derived labels):

| Regime | n | Mean 30m fwd |
|---|---:|---:|
| SPY above its own VWAP | 20,223 | +0.00646% |
| SPY below its own VWAP | 17,696 | -0.00191% |
| SPY session return positive | 18,553 | +0.00513% |
| SPY session return negative | 19,306 | -0.00018% |
| SPY session flat (n too small to trust) | 60 | +0.08307% |
| Own trailing volatility: LOW | 14,872 | -0.00446% |
| Own trailing volatility: NORMAL | 21,720 | +0.00728% |
| Own trailing volatility: HIGH | 1,327 | +0.00380% |

The VWAP-position and session-return splits each separate the mean by roughly 0.007-0.008
percentage points -- directionally sensible (risk-on SPY tilts individual-name drift
slightly positive) but an order of magnitude below the 0.10% COST1 round-trip cost. The
volatility-bucket split is not monotonic (NORMAL beats both LOW and HIGH) and is not a
usable regime precondition.

## 6. Does relative ranking help?

No, and the sign is wrong. Cross-sectional ranking (each of the 6 non-benchmark symbols'
return-since-open vs SPY's, ranked into STRONGEST/MIDDLE/WEAKEST thirds at every 5-minute
mark):

| Bucket | n | Mean 30m fwd |
|---|---:|---:|
| STRONGEST | 12,490 | +0.0013% |
| MIDDLE | 12,490 | -0.0037% |
| WEAKEST | 12,490 | +0.0101% |

STRONGEST-minus-WEAKEST spread is **-0.0088%** -- the symbol ranked WEAKEST by trailing
relative performance actually shows a slightly HIGHER subsequent 30-minute return than the
symbol ranked STRONGEST, the opposite of a momentum-continuation story and the opposite of
what "buy relative strength" would need. The Spearman IC between the raw relative-return
feature and the 30-minute forward return is **-0.0036** over 37,470 observations --
indistinguishable from zero. This relationship is also unstable across time (see Q8 below):
only 1 of 4 chronological quartiles even has the same sign as the full-sample spread.

## 7. Does stronger selectivity improve forward returns?

Partially monotonic in-sample, but NOT economically usable and NOT stable:

| Bucket | n | Mean 30m fwd | Max symbol share | 1st-half mean | 2nd-half mean |
|---|---:|---:|---:|---:|---:|
| Top 50% | 18,735 | +0.0068% | 18.5% | +0.0005% | +0.0131% |
| Top 25% | 9,368 | +0.0005% | 20.2% | -0.0059% | +0.0068% |
| Top 10% | 3,747 | -0.0017% | 22.5% | +0.0172% | -0.0206% |
| Top 5% | 1,874 | +0.0173% | 24.9% | +0.0620% | -0.0273% |
| Top 1% | 375 | +0.0521% | 54.4% | +0.1205% | -0.0159% |

The top-1% bucket's mean move (+0.052%) is the largest of the five and is the closest any
measured relationship gets to the 0.10% COST1 round-trip cost -- but it is still below it,
it is concentrated in one symbol 54% of the time (the opposite of "broad"), and it **flips
sign between the first and second half of the research window** (+0.12% then -0.016%).
Top-10% is not even monotonically above Top-25% (-0.0017% vs +0.0005%). This is not a
reliable monotonic relationship; it reads as noise concentrated in a few observations, not
a stable selectivity effect.

## 8. Are opening gaps informative?

The most interesting single number in this study, reported honestly alongside its caveats:

| Gap direction | n | Mean 30m fwd (from session open) |
|---|---:|---:|
| Gap down (&lt;-0.1%) | 239 | +0.0072% |
| Flat (within +/-0.1%) | 58 | +0.0104% |
| Gap up (&gt;+0.1%) | 249 | +0.0462% |

Gap-up sessions show a materially larger continuation move than gap-down or flat sessions.
This is the single largest unconditional effect measured in this milestone, and it is still
below the 0.10% COST1 round-trip cost, with a small sample (249 gap-up sessions, one
observation per symbol-session, not independently re-tested across chronological blocks or
broken out per symbol in this fork). It is flagged as the most promising LEAD for future
work, not validated here.

## 9. Which relationships survive COST1 economically?

**None, fully.** COST1 is a 0.10% round-trip (COST0 is 0%, COST2 is 0.30%, unchanged from
M091/M092/M093). Every measured effect is below this bar:

| Relationship | Magnitude | Survives COST1? |
|---|---:|---|
| Cross-sectional STRONGEST-WEAKEST spread | -0.0088% | No (wrong sign too) |
| Selectivity top-1% mean move | +0.0521% | No |
| Selectivity top-5% mean move | +0.0173% | No |
| Regime split (VWAP position) | ~0.0084% | No |
| Opening gap-up vs gap-down | ~0.0390% | No (closest, still short) |

## 10. Which relationships persist across time?

Poorly. The cross-sectional relative-strength spread changes sign in 3 of 4 chronological
quartiles (only quartile 4 is positive):

| Quartile | Dates | n | Spread | Spearman IC |
|---|---|---:|---:|---:|
| Q1 | 2026-05-13 to 2026-06-16 | 9,342 | -0.0128% | -0.0096 |
| Q2 | 2026-06-17 to 2026-07-21 | 9,066 | -0.0242% | -0.0074 |
| Q3 | 2026-07-22 to 2026-08-25 | 9,762 | -0.0077% | +0.0037 |
| Q4 | 2026-08-26 to 2026-09-29 | 9,300 | +0.0090% | -0.0163 |

The IC itself also flips sign across quartiles with no consistent direction. The
selectivity top-1%/5%/10% buckets each flip sign between the first and second
chronological half of the research window (Q7 above). Nothing tested here is temporally
stable.

## 11. Which relationships persist across symbols?

The cross-sectional effect is small and not dominated by one symbol, but it is also small
in every symbol -- there is no symbol where it is large and reliable:

| Symbol | Strongest mean | Weakest mean | Spread |
|---|---:|---:|---:|
| AAPL | +0.0023% | +0.0295% | -0.0273% |
| AMZN | -0.0255% | -0.0020% | -0.0235% |
| GOOGL | +0.0036% | +0.0075% | -0.0039% |
| META | +0.0071% | +0.0085% | -0.0014% |
| MSFT | +0.0109% | +0.0307% | -0.0198% |
| NVDA | -0.0017% | -0.0036% | +0.0019% |

5 of 6 symbols show a NEGATIVE spread (weakest outperforming strongest), consistent across
most of the universe -- so the (wrong-signed, sub-cost) relationship is at least broad
rather than driven by a single name. That consistency does not make it usable; it confirms
the relationship, where it exists at all, point the wrong way for a "buy relative strength"
story, on both ETFs-excluded individual names tested.

## 12. What data is missing?

**EVENT_DATA_NOT_AVAILABLE.** No earnings-calendar or news/sentiment data source exists
anywhere in this repository -- only corporate-action (split/dividend) semantics does. The
opening-gap study (Q8) used only legitimately-available prior-close/today-open displacement,
not fabricated event data. If opening-gap context is pursued further (see Q13), a real
earnings/news data source would likely be the highest-value single addition, since gap-up
sessions plausibly cluster around earnings and macro events this platform cannot currently
distinguish from ordinary gaps.

## 13. Which TWO directions, at most, deserve strategy construction?

**Neither.** The mechanical Phase 17 decision gate was applied to the two candidates with
any real empirical backing in this study:

- **CROSS_SECTIONAL_RELATIVE_STRENGTH**: failed on information coefficient magnitude
  (|IC| 0.0036 &lt; the 0.02 eligibility floor), on cost survivability (spread below COST1,
  wrong sign), and on temporal stability (1 of 4 quartiles same sign).
- **SELECTIVE_MOMENTUM**: failed on cost survivability (even the top-1% bucket's mean move,
  0.052%, is below the 0.10% COST1 round-trip).

Neither direction was forced through to make this milestone look more successful than the
evidence supports. **Classification: `NO_PROMISING_EDGE_SOURCE`.**

## 14. What should we stop researching?

- **Single-symbol multi-timeframe momentum** (MULTI_TIMEFRAME_TREND) as tested: IC is
  effectively zero at every window from 5 to 60 minutes, with the wrong sign where
  non-zero. This specific formulation (trailing rolling return) does not warrant further
  iteration.
- **Cross-sectional relative-strength ranking** as a long-only continuation signal: the
  measured relationship points the wrong way (weakest outperforms strongest) and is
  unstable across time. Re-testing the SAME feature with minor parameter changes is
  unlikely to be informative; a genuinely different cross-sectional construction (e.g.
  volume-based or volatility-adjusted ranking, not re-tested here) would be a new
  hypothesis, not a continuation of this one.
- **Volatility-bucket regime conditioning** as tested: non-monotonic (NORMAL beats both
  LOW and HIGH), no plausible mechanism was found to make it monotonic without more data.

**Worth a follow-up look, NOT selected here:** opening-gap context (Q8/Q12) showed the
single largest unconditional effect in this study, still below COST1, on a small,
single-run sample. A dedicated, properly-stabilized (temporal/cross-symbol split) follow-up
study of gap behavior -- ideally paired with a real event-data source -- is the most
plausible next research direction, but it was not validated well enough in this milestone
to be "selected" under Phase 17's own eligibility bar.
