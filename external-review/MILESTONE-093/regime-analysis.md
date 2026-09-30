# M093 Phase 14 -- Regime Analysis

Method: each resolved trade is bucketed by contemporaneously-measurable evidence only --
the Eastern-time-of-day of the entry bar (known at decision time from the bar timestamp
itself, no future information). No trade is labeled by its own outcome or by any
information not available at the moment the entry decision was made. Buckets: MORNING
(10:00-12:00 ET), MIDDAY (12:00-14:00 ET), AFTERNOON (14:00-15:30 ET) -- matching the
shared framework's entry window (10:00-15:30 ET). All numbers are COST_MODEL_1.

(Note: the bar timestamps in the cache are UTC; an earlier pass of this analysis bucketed
by the raw UTC time and produced an obviously wrong result -- zero trades in two of three
buckets. That was caught before being reported and fixed by converting to
`America/New_York` before bucketing; the numbers below are post-fix.)

## Results by time-of-day bucket (COST1 profit factor)

| Family | MORNING (10-12) | MIDDAY (12-14) | AFTERNOON (14-15:30) |
|---|---:|---:|---:|
| TREND_CONTINUATION | 0.674 (n=1304) | 0.527 (n=1181) | 0.402 (n=918) |
| VWAP_PULLBACK | 0.571 (n=325) | 0.539 (n=206) | 0.251 (n=164) |
| OPENING_RANGE_5 | 0.841 (n=5256) | 0.491 (n=4252) | 0.344 (n=4938) |
| OPENING_RANGE_15 | 0.805 (n=4895) | 0.547 (n=4158) | 0.341 (n=4628) |
| MEAN_REVERSION | 0.452 (n=3664) | 0.385 (n=2982) | 0.295 (n=2411) |
| RELATIVE_STRENGTH | 0.793 (n=2184) | 0.790 (n=1023) | 0.489 (n=491) |

## Finding: no regime-narrow edge exists

Every family is below PF 1.0 in every time-of-day bucket, with no exception. The pattern is
consistent and directionally uniform across all six variants: the morning bucket is
consistently the *least bad* (still clearly losing) and the afternoon bucket is
consistently the *worst* -- plausible given tighter spreads/larger ranges shortly after the
open versus more compressed ranges into the mandatory 15:45 liquidation, but this does not
rise to a tradeable regime precondition since no bucket for any family clears breakeven.

Cross-referencing against the Phase 15 per-symbol breakdown (below), the same conclusion
holds: across 6-8 symbols per family, at most one (symbol, family) cell across the entire
study clears PF 1.0 -- OPENING_RANGE_15 on META, PF 1.039, net +$421.47 on 1,620 trades,
essentially a noise-level result in one symbol out of eight for one of six variants, not a
broad or repeatable regime.

**Conclusion:** no family's weakness is regime-narrow in a way that could be captured as a
hard precondition (e.g. "only trade in the morning," "only trade META"). The weakness is
broad across time-of-day, broad across symbols (Phase 15), and broad across the
chronological design/observe split (Phase 16). There is no regime-gating revision to
propose here; encoding a precondition would not change the fundamental conclusion of
Phase 11/12/13.
