# M081 - Fresh Second Verification Pass

Same agent, so **not** an independent review. A genuinely fresh database and
deliberately different inputs.

- Database `m081_second_pass`, **dropped and created empty**, full migration
  chain applied from scratch.
- Different instruments: `PLTR`, `COIN`, `ARM`, `SMCI` - none used in the first
  suite.
- Different position keys, different timestamps (day 91-180 rather than day 1-90).
- **Three exits on one position** rather than the first suite's one or two.
- Prices at both ends of the frozen `NUMERIC(20, 6)` domain **within a single
  position**: entry `0.000002`, exits at `0.000001` and `99999999999999.999999`.
- **Reversed knowledge order**: the opening carries a later `recorded_at` than the
  reduction.

## What the second pass attacked, and what held

| Claim | Result |
|---|---|
| Three exits each contribute their own asserted price | Held - `5/9`, exact |
| The approximation of `5/9` truncates rather than rounds up | Held - `~0.555555`, strictly below `5/9` |
| Both ends of the numeric domain in one position | Held - denominator positive, ratio `> -1`, numerator positive |
| A reduction visible before its opening yields no ratio | Held - `UNRESOLVED_KNOWLEDGE_SEQUENCE` |
| The same position resolves once the opening is known | Held - `2/5` on 5 of 8 units |
| A post-cutoff row appended between two reads moves the answer | Did **not** - reports identical |
| Those rows become visible once the cutoff advances | Held - the ratio changes |

**4 passed.**

## One correction to the pass itself, recorded

My first version tried to append the `REDUCED` event *before* its `OPENED` to
achieve "reversed recording order". Frozen M076 rejected it - `POSITION_NOT_OPEN`
- because M076 validates every append against the derived state. The reversal
that actually matters here is in **knowledge time**, not append order: the
opening is written first but carries a later `recorded_at`. The test was wrong
about the mechanism; frozen M076 was right, and the corrected test exercises the
property that was actually intended.
