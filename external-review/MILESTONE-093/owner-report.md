# MILESTONE-093 — Intraday Strategy Discovery — Owner Report

**Headline: `NO_CANDIDATE_EDGE`.** Five genuinely different long-only intraday strategy
families (six signal variants, counting Opening Range's two duration options separately)
were researched, screened, revised where justified, and stress-tested for regime- and
symbol-dependence over a 100-session research dataset. None showed a defensible edge after
realistic modeled costs. No candidate was selected or frozen. The locked M092 FINAL
HOLDOUT (2026-03-18 → 2026-05-12) was never touched — it remains fully reserved for a
future, separate M094.

## 1. Which strategy families were tested?

Five, matching the mission's own hypothesis-driven brief — each genuinely different in its
entry logic, not a retuned breakout:
- **A — Trend Continuation**: established trend → pullback that preserves structure →
  resumption.
- **B — VWAP Pullback/Reclaim**: constructive context → pullback to a look-ahead-safe
  intraday VWAP → confirmed reclaim.
- **C — Opening Range** (two variants, 5-minute and 15-minute): breakout/reclaim only after
  the opening range has structurally completed.
- **D — Conditional Mean Reversion**: deviation from VWAP + absence of adverse trend +
  stabilization evidence, targeting VWAP (never a fixed multiple).
- **E — Relative Strength**: outperformance vs. SPY/QQQ over a bounded prior interval
  (SPY/QQQ themselves excluded from this family — never compared against their own future
  bars).

## 2. Which failed immediately?

All six variants failed the Phase 12 early-kill bar on the full research sample: COST1
profit factor ranged from **0.375** (Mean Reversion) to **0.736** (Relative Strength) — every
one clearly below 1.0, and every one's idealized (zero-cost) result was also flat-to-negative
except two. A manual spot-check of 12 real trades across 4 families confirmed the cost drag
exactly matches the declared 10bps round-trip cost model — this is a real signal-quality
finding, not an implementation bug charging costs twice.

## 3. Which improved after limited hypothesis-driven revision?

Two families (VWAP Pullback and Mean Reversion) had a positive or near-zero *idealized*
(COST0) result, so each received its one allowed hypothesis-driven revision (Phase 13 caps
this at 2 per family). **Neither revision closed the gap to COST1 profitability** — VWAP
Pullback's revision (raising the volume-ratio confirmation threshold) actually made the
idealized result worse (PF 1.015 → 0.932). Both revisions and their stated before/after
hypotheses are recorded in full, including the negative ones, in
`external-review/MILESTONE-093/family-revisions.md`.

## 4. Which family performed best after costs?

**Relative Strength**, with the least-bad COST1 profit factor (0.736 full-sample) and the
smallest degradation across the walk-forward split (0.747 design → 0.695 observe). This is
reported as the most *structurally consistent* of six failing families, explicitly **not**
as a reason to select it — a strategy that reliably loses money at a stable PF of ~0.7 is a
measured non-edge, not "almost an edge."

## 5. How many trades?

| Family | Trades (COST1) |
|---|---:|
| Trend Continuation | 4,031 |
| VWAP Pullback | 894 |
| Opening Range (5-min) | 20,697 |
| Opening Range (15-min) | 18,762 |
| Mean Reversion | 10,787 |
| Relative Strength | 4,287 |

## 6. PF?

| Family | COST1 PF |
|---|---:|
| Trend Continuation | 0.519 |
| VWAP Pullback | 0.448 |
| Opening Range (5-min) | 0.541 |
| Opening Range (15-min) | 0.532 |
| Mean Reversion | 0.375 |
| Relative Strength | 0.736 |

No family clears 1.0 anywhere: not the full sample, not any of 3 time-of-day buckets, not
any of 6–8 symbols, not either half of a chronological walk-forward split (144 cells
checked total).

## 7. Average trade?

Ranges from −$1.65 (Mean Reversion) to −$2.40 (Opening Range 5-min), all negative, all
consistent with each family's own profit factor.

## 8. Drawdown?

| Family | Max drawdown (COST1) |
|---|---:|
| Trend Continuation | $8,519.78 |
| VWAP Pullback | $1,546.57 |
| Opening Range (5-min) | $49,764.38 |
| Opening Range (15-min) | $44,904.15 |
| Mean Reversion | $17,792.22 |
| Relative Strength | $8,435.27 |

## 9. Losing streak?

Longest observed: 237 consecutive losing trades (Opening Range 5-min, the highest-volume
variant). Every family showed long losing streaks consistent with a genuine negative
expectancy, not an unlucky run inside an otherwise-profitable system.

## 10. Symbol concentration?

No family depended on one symbol — the opposite problem was found: performance was
*uniformly poor* across 6–8 symbols per family, with at most one (symbol, family) cell out
of the entire study (Opening Range 15-min on META, PF 1.040 on 1,620 trades) clearing
breakeven, and that one cell does not repeat for the same symbol under any other family or
even the sibling 5-minute Opening Range variant — consistent with noise, not a genuine
symbol-specific edge.

## 11. Regime dependence?

None found. Every family is below PF 1.0 in every time-of-day bucket (morning is
consistently *least bad*, afternoon consistently *worst*, plausibly reflecting tighter
ranges approaching the mandatory 15:45 ET liquidation) — but no bucket for any family
clears breakeven, so no regime precondition would rescue any family.

## 12. Walk-forward stability?

Checked via a chronological design/observe split within the 100-session research dataset
(never the locked holdout). Every family's PF was WORSE in the later "observe" half than
in the earlier "design" half (e.g. Trend Continuation 0.572 → 0.394) except Relative
Strength, which degraded the least (0.747 → 0.695) — still clearly unprofitable in both
halves. No family showed stability at a profitable level; none is a case of "narrow but
real" performance that a stricter design/observe split would need to re-confirm.

## 13. Was a candidate selected?

**No.** Classification: `NO_CANDIDATE_EDGE`. Phase 18 (freeze) does not apply — there is no
candidate to freeze.

## 14. Why?

Every one of five genuinely different strategy families (six signal variants) failed to
show a positive COST1 expectancy anywhere in 100 real research sessions — not in aggregate,
not in any time bucket, not in any symbol, not in either half of a walk-forward split. The
two families with any positive idealized signal were each given their one allowed
hypothesis-driven revision, and neither revision closed the gap to profitability. A manual
spot-check confirmed the cost drag is exactly the declared cost model, not a bug inflating
losses. This is a broad, consistent, structural pattern across independently-designed
signal logic — not the failure of one implementation detail that a different threshold
could fix.

## 15. What remains genuinely unseen?

The M092 FINAL HOLDOUT, **2026-03-18 through 2026-05-12**, was never fetched, inspected, or
evaluated by any M093 code path — confirmed by the machine-enforced holdout guard (which
would raise immediately on any attempt), by a functional test proving the guard refuses
before any network call, and by a static/AST check over this milestone's own screening
tool. It remains fully reserved, exactly as before M093 began.

## What this report does NOT establish

- That no long-only intraday edge could ever exist on this platform — five families is a
  meaningful but bounded search, not an exhaustive one.
- Real historical spread/slippage evidence — COST MODEL 1/2 remain the same modeled
  assumptions as M091/M092, unchanged, never adjusted to rescue a result.
- Live-market fillability, live costs, or live execution quality.
- Guaranteed or expected future profitability of any kind, under any classification.
