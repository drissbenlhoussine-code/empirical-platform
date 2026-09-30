# MILESTONE-091 — M090 V1 Strategy Validation — Owner Report

Generated from a real, out-of-sample, 60-session historical replay of the FROZEN M090 V1
policy (fingerprint `6ed540efd2b2638bf5a3a9aae290874bad6c5fdad54c604325c86ce4fd2c49da`,
verified by the run itself before any data was fetched — see
`external-review/MILESTONE-091/policy-freeze.md`). Full machine-readable results:
`external-review/MILESTONE-091/results.json`.

**Headline: NO_EDGE_FOUND.** After realistic modeled trading costs, this sample shows a
negative result, consistently in both halves of the sample. This is a research finding
about a specific frozen rule set over a specific historical sample — not a permanent
verdict on intraday trading, and not a claim that a differently-tuned version of this
engine would perform the same way.

## 1. Does M090 V1 show evidence of an edge?

**No — NO_EDGE_FOUND.** Under idealized, zero-friction execution (COST MODEL 0), the
result was roughly breakeven: net P&L of **+$3.31** across 484 resolved trades, a profit
factor of essentially exactly 1.00. Once a conservative, realistic cost assumption (COST
MODEL 1 — see Q3) is applied, the result becomes clearly negative: **−$886.29**, profit
factor **0.67**. A strategy that is only breakeven before costs is not survivable after
costs, and this one was not.

## 2. How many trades were tested?

**484 resolved trades** (TARGET_HIT, STOP_HIT, or MANDATORY_EXIT) out of 516 ACTIONABLE
opportunities generated (32 were still open, unresolved, at the end of their session's
fetched data — never counted as a win or a loss). This came from **181,031 total
bar-by-bar observations** across 472 of 480 requested (symbol, session) pairs — 8 pairs
(all 8 symbols on 2026-09-07, a U.S. market holiday) were excluded honestly with that exact
reason; nothing was fabricated in their place. 180,515 observations were REJECTED before
ever becoming an opportunity — the overwhelming majority (177,847) for
`INSUFFICIENT_LIQUIDITY` (the frozen policy's 20,000-share-per-bar floor), the rest
(2,668) for `NO_BREAKOUT_STRUCTURE`.

## 3. What happens after realistic costs?

Real historical bid/ask spread evidence is **not available** through the existing
read-only Alpaca Paper market-data client without a materially larger architecture change
(it exposes current quotes and historical bars, not a historical NBBO/quotes endpoint) — so
this validation uses three explicitly labeled **modeled assumptions**, never measurements:

| Model | Assumption | Full-sample net P&L | Profit factor |
|---|---|---|---|
| COST MODEL 0 | Idealized, zero friction | **+$3.31** | 1.00 |
| COST MODEL 1 | Base conservative: 0.05% modeled cost per side (~3bps spread + ~2bps slippage), 0.10% round trip | **−$886.29** | 0.67 |
| COST MODEL 2 | Stress: 3x COST MODEL 1, 0.30% round trip | **−$2,665.48** | 0.33 |

The gap between COST MODEL 0 and COST MODEL 1 (roughly $890 swinging on a 0.10% round-trip
assumption, over 484 trades averaging a few hundred dollars of notional each) shows this
result is **fragile to cost assumptions** — a marginal idealized edge does not survive even
a conservative, realistic friction estimate.

## 4. Is performance stable across both 30-session blocks?

**Yes — consistently negative in both.** This is the one place the sample is "stable": it
did not accidentally look good in one half and bad in the other.

| | Trades | Net P&L (base cost) | Profit factor | Average trade |
|---|---|---|---|---|
| Block A (2026-07-08 → 2026-08-18, oldest 30 sessions) | 338 | **−$617.12** | 0.69 | −$1.83 |
| Block B (2026-08-19 → 2026-09-29, most recent 30 sessions) | 146 | **−$269.17** | 0.62 | −$1.84 |

Note Block B has far fewer trades (146 vs 338) despite the same 30-session length —
opportunity generation was not stable in *volume* across the sample even though it was
stable in *direction* (negative).

## 5. Which symbols help/hurt?

| Symbol | Trades | Net P&L (base cost) | Profit factor | Hit rate |
|---|---|---|---|---|
| NVDA | 328 | −$325.12 | 0.83 | 32.9% |
| AMZN | 42 | −$197.66 | 0.29 | 14.3% |
| MSFT | 14 | −$144.46 | 0.05 | 14.3% |
| AAPL | 45 | −$122.95 | 0.44 | 31.1% |
| SPY | 31 | −$60.73 | 0.03 | 6.5% |
| GOOGL | 5 | −$35.69 | 0.00 | 20.0% |
| QQQ | 13 | −$4.99 | 0.66 | 15.4% |
| META | 6 | **+$5.31** | 1.18 | 33.3% |

Only META was net positive, and marginally (6 trades — far too few to mean anything on its
own). Every other symbol lost money. **NVDA alone produced 328 of the 484 resolved trades
(68%)** — the engine's opportunity generation on this frozen policy is heavily
concentrated in one symbol by trade *count*, even though NVDA is not the single largest
*dollar* contributor. This is a real fragility signal worth naming plainly, even though the
mechanical Phase 12 classification criteria (which check P&L-share concentration, not
trade-count concentration) did not flag it — see the note under Q8.

## 6. What is the worst drawdown?

**$1,183.74** (full sample, base cost, COST MODEL 1) — the largest peak-to-trough decline
in the running P&L curve, computed over all 484 resolved trades in chronological order.
Under the idealized COST MODEL 0 the full-sample drawdown was much smaller ($489.79); the
gap between the two again shows how much the realistic cost assumption changes the picture.
At the block level, Block A's own drawdown was $909.56 and Block B's was $307.29 — under
realistic costs the equity curve is in a near-continuous decline rather than one sharp
event, so the drawdown figure largely tracks the same trend as the headline net loss. The
longest losing streak observed was **32 consecutive losing trades**, occurring within Block
B.

## 7. How often does Stop vs Target vs Mandatory Exit occur?

Full sample, 484 resolved trades:

| Outcome | Count | Share |
|---|---|---|
| STOP_HIT | 204 | 42.1% |
| MANDATORY_EXIT | 183 | 37.8% |
| TARGET_HIT | 97 | 20.0% |

Only 1 in 5 resolved trades actually reached the target. Over a third of the time, the
session simply ran out (mandatory liquidation) before either the stop or the target was
touched — the engine's stop/target geometry is frequently not resolving within the same
session at all.

## 8. What is the biggest weakness?

Three, in order of how directly they explain the negative result:

1. **The idealized edge is too thin to survive any realistic cost.** +$3.31 gross over 484
   trades is not a margin of safety against even a conservative 10bps round-trip
   assumption, let alone real-world spread and slippage.
2. **Low hit rate (28–40% depending on cost model) not fully compensated by payoff.** The
   payoff ratio (~1.5–1.8, average winner vs. average loser) is positive but not large
   enough to offset a hit rate well under 50%.
3. **Heavy trade-count concentration in one symbol (NVDA, 68% of trades)** and a very low
   trade count for several others (GOOGL: 5, META: 6) — most of the 8-symbol universe
   barely generated enough opportunities to say anything about it individually. A caveat on
   the mechanical classification itself: when total net P&L is negative, the "share of
   total P&L" concentration formula this milestone's `classify()` function uses becomes
   mathematically degenerate (dividing a symbol's own P&L by a negative total inverts the
   sign of its "share"), so the `not_single_symbol_dependent`/`not_single_day_dependent`
   criteria reported `True` here in a way that should NOT be read as "diversified" — they
   simply did not drive this NO_EDGE_FOUND result, which was independently and clearly
   triggered by negative expectancy and sub-1 profit factor in both blocks.

## 9. Is M090 V1 ready to automate on Paper?

**No.** The classification is NO_EDGE_FOUND, and the mission's own release-gate rule is
explicit: automating an already-approved trade plan (a future M092) requires
`READY_FOR_M092`, which in turn requires `CANDIDATE_EDGE`. This sample does not show that.

## 10. What should be built next?

Per the mission's own decision tree, this result maps to **STRATEGY_REWORK_REQUIRED** —
the FROZEN M090 V1 policy itself needs rework (a new, later-milestone policy version), not
more data collection against the same frozen rules. Concretely, worth investigating in a
future milestone (none of this is done here — the frozen policy is not touched by this
milestone):

- The reward/risk floor is a constant 2.00 for every single trade (see
  `reward_risk_min`/`median`/`max` in `results.json`, always exactly `2.00`) — the target
  is always placed at exactly the policy's own floor, never higher, which may be
  structurally capping the payoff ratio below what the hit rate needs.
- Whether the `INSUFFICIENT_LIQUIDITY` gate (98.5% of all rejections) is filtering out the
  bulk of the universe so aggressively that only a handful of genuinely tradable setups
  remain, concentrated in the most liquid name (NVDA).
- Whether the 37.8% MANDATORY_EXIT rate indicates the stop/target geometry is too wide
  relative to the entry window, session length, or `structure_lookback_bars`.

## Appendix — data quality

- Symbol-session pairs requested: 480 (8 symbols × 60 sessions)
- Excluded: 8 (all 8 symbols, 2026-09-07 — U.S. market holiday, "no bars returned")
- Excluded fraction: 1.67% (well under this milestone's own 20% data-gap tolerance)
- Session dates: 2026-07-08 through 2026-09-29 (Block A: 2026-07-08 → 2026-08-18; Block B:
  2026-08-19 → 2026-09-29)
- Look-ahead protection: re-proven against a real fetched bar sequence in
  `tests/unit/test_m091_validation_look_ahead.py`, in addition to the original M090 unit
  suite's own hand-built-bar audit — a poisoned future bar provably cannot alter any
  earlier decision.

## What this study does NOT establish

- That a differently-tuned version of the Opportunity Engine would perform the same way.
- Real historical spread/slippage evidence — COST MODEL 1/2 are documented assumptions.
- Live-market fillability, live costs, or live execution quality.
- Guaranteed or expected future profitability of any kind, under any classification.
