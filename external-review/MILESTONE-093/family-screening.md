# M093 Phase 11/12 -- Family Screening and Early-Kill Determination

Research dataset: 100 sessions (2026-05-13 -> 2026-09-29, M091 DEVELOPMENT union M092
VALIDATION), 8-symbol fixed universe (AAPL, MSFT, NVDA, AMZN, META, GOOGL, QQQ, SPY).
Bar cache: 800 (symbol, session) pairs, 785 non-empty (15 market-holiday gaps within the
range), all fetched exclusively through `fetch_session_bars_guarded`, which enforces the
M093 holdout guard (2026-03-18 -> 2026-05-12) as its first action before any network call.
No date in the locked holdout range appears anywhere in this cache or in any run reported
below.

Common framework (`m093_research_framework.py`): same session window (09:30-16:00
America/New_York), same stop-first same-bar resolution, same three cost models
(COST_MODEL_0 idealized / COST_MODEL_1 base-conservative 0.05%-per-side / COST_MODEL_2
stress 0.15%-per-side), same position sizing (max $2,000 capital or 50% of $20,000
deployable capital per trade, whichever binds), same mandatory-liquidation time (15:45 ET),
same entry window (10:00-15:30 ET), shared by all five families and both Opening Range
duration variants. Every family/variant below ran against the identical 785-session-symbol
bar set.

## Aggregate results (all 6 signal variants, full research dataset)

| Family / variant | Opportunities | Resolved | COST0 net | COST0 PF | COST1 net | COST1 PF | COST1 avg/trade | COST2 PF |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| TREND_CONTINUATION | 4,045 | 4,031 | -1,327.36 | 0.898 | -8,384.78 | 0.519 | -2.080 | 0.183 |
| VWAP_PULLBACK | 907 | 894 | +26.51 | 1.015 | -1,545.97 | 0.448 | -1.729 | 0.112 |
| OPENING_RANGE_5 | 20,946 | 20,697 | -14,151.48 | 0.836 | -49,739.42 | 0.541 | -2.403 | 0.248 |
| OPENING_RANGE_15 | 18,980 | 18,762 | -12,665.99 | 0.834 | -44,883.69 | 0.532 | -2.392 | 0.237 |
| MEAN_REVERSION | 10,823 | 10,787 | +1,810.20 | 1.157 | -17,775.42 | 0.375 | -1.648 | 0.093 |
| RELATIVE_STRENGTH | 4,296 | 4,287 | -325.71 | 0.988 | -8,225.23 | 0.736 | -1.919 | 0.408 |

Two families show a slightly positive or near-1.0 idealized (COST0, zero-friction) result:
VWAP_PULLBACK (+$26.51 net, PF 1.015 -- statistically indistinguishable from zero over 894
trades) and MEAN_REVERSION (+$1,810.20 net, PF 1.157 -- the only family with a materially
positive idealized edge). RELATIVE_STRENGTH is roughly breakeven idealized (PF 0.988).
TREND_CONTINUATION and both OPENING_RANGE variants are already net-negative even before any
modeled friction.

Every one of the six variants is decisively negative under COST_MODEL_1 (the primary
discovery metric per Phase 4), with profit factor ranging 0.375-0.736 and large,
statistically stable sample sizes (894-20,697 resolved trades). RELATIVE_STRENGTH has the
least-bad COST1 PF (0.736); MEAN_REVERSION has the worst (0.375) despite having the best
COST0 PF, because it also runs the largest position size relative to its (small) per-share
target distance -- see the spot-check below.

## Spot-check: ruling out an implementation defect before concluding fundamental weakness

Before treating the uniform COST1 failure as a genuine finding rather than a bug, individual
resolved trades were inspected directly across MEAN_REVERSION, OPENING_RANGE_5,
VWAP_PULLBACK and RELATIVE_STRENGTH (`spotcheck.py`, scratchpad). In every sampled trade the
realized per-share cost drag (raw COST0 pnl/share minus COST1 pnl/share) matches
`entry_price * 0.05% + outcome_price * 0.05%` to within rounding -- exactly the declared
10bps round-trip friction, applied once, with the correct sign, no double-charging. Example
(MEAN_REVERSION, AAPL 2026-05-14 bar 197): entry 296.91, stop 296.58, raw pnl/share -0.33,
COST1 pnl/share -0.6267, drag 0.2967 = 296.91*0.0005 + 296.58*0.0005 (0.1485 + 0.1483).

The mechanical explanation is straightforward and not a bug: these are tight intraday
setups on $150-500 stocks where the stop/target distance is frequently under $1-2/share.
A fixed 10bps-of-price round-trip cost is therefore a large fraction of the risk unit
itself, not a small tax on a large edge. This is the same structural conclusion M091 and
M092 already reached for V1/V2 -- it recurs here across five genuinely different signal
families, which is itself informative: the result is not an artifact of one particular
entry rule, it is a property of intraday cost economics at this position-sizing scale.

## Phase 12 -- early-kill determination

Rule (Phase 12, verbatim): reject a family if COST1 expectancy is clearly negative AND PF
is materially below 1 AND the weakness is broad (not one isolated implementation defect).

Applying this mechanically to COST_MODEL_1:

- **TREND_CONTINUATION**: REJECTED. Net -8,384.78, PF 0.519, n=4,031. Already negative at
  COST0 (PF 0.898) -- the entry signal itself does not identify a positive-expectancy setup
  even before cost.
- **OPENING_RANGE_5**: REJECTED. Net -49,739.42, PF 0.541, n=20,697. Already negative at
  COST0 (PF 0.836). Largest sample of any family -- the failure is the most statistically
  certain of the six.
- **OPENING_RANGE_15**: REJECTED. Net -44,883.69, PF 0.532, n=18,762. Same pattern as the
  5-minute variant; the longer opening-range window does not change the conclusion.
- **RELATIVE_STRENGTH**: REJECTED. Net -8,225.23, PF 0.736, n=4,287. Best COST1 PF of the
  six, and roughly breakeven at COST0 (0.988), but still clearly fails the COST1 bar.
- **VWAP_PULLBACK**: REJECTED against the strict COST1 rule (net -1,545.97, PF 0.448), but
  flagged as the closest thing to a "near-breakeven" result at COST0 (PF 1.015, essentially
  zero edge on either side) -- carried into Phase 13 for one limited revision rather than
  dropped outright, per the mission's "showing promise or near-breakeven" admission path.
- **MEAN_REVERSION**: REJECTED against the strict COST1 rule (net -17,775.42, PF 0.375 --
  the worst COST1 PF of the six), but it is the only family with a materially positive
  idealized (COST0) result (PF 1.157, +$1,810.20 net over 10,787 trades) -- also carried
  into Phase 13 for one limited revision, to test whether a structural change can improve
  the edge-to-cost ratio enough to matter.

All six variants are formally `FAMILY_REJECTED` at the Phase 12 bar on the unmodified
screening run. Two (VWAP_PULLBACK, MEAN_REVERSION) receive one hypothesis-driven Phase 13
revision each before final disposition, because their COST0 results are qualitatively
different from the other four (near-zero or positive idealized edge, vs. already-negative).
TREND_CONTINUATION, OPENING_RANGE_5, OPENING_RANGE_15 and RELATIVE_STRENGTH receive no
further revision effort -- their weakness is present even before any cost is applied, so no
plausible structural tweak to entry/exit geometry changes the underlying conclusion that the
entry signal itself does not select a positive-expectancy setup.

See `family-revisions.md` for the Phase 13 revision results.
