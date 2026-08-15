# M080 — Fresh Second Verification Pass

Same agent, so **not** an independent review. A genuinely fresh database and
deliberately different inputs.

- Database `m080_second_pass`, **created empty**, full migration chain applied
  from scratch.
- Different instruments: `PLTR`, `COIN`, `ARM`, `SMCI` — none used in the first
  suite.
- Different governance ids, different position keys, different timestamps (day
  91–130 rather than day 1–60).
- **Three exits on one position** rather than the first suite's two.
- Prices at both ends of the frozen `NUMERIC(20, 6)` domain **in a single
  position**: entry `0.000002`, exits at `0.000001` and
  `99999999999999.999999`.
- **Reversed recording order**: the opening is recorded *after* the reduction,
  so recording order cannot be what makes the arithmetic work.

## What the second pass attacked, and what held

| Claim | Result |
|---|---|
| Multiple exits each contribute their own asserted price | Held — `299999999999999.999989`, exact |
| A partial exit reports the still-open quantity separately | Held — 5 exited, 4 still open |
| Boundary decimals survive multiplication and summation together | Held |
| A reduction visible before its opening is unresolved, not arithmetic | Held — `UNRESOLVED_KNOWLEDGE_SEQUENCE`, no result |
| The same position resolves once the opening is recorded | Held — `423.249995` on 5 of 8 units |
| Post-cutoff rows appended between two reads move the answer | Did not — object and text byte-identical |
| Those rows become visible once the cutoff advances | Held — `4677.740736` |
| Raw SQL confirms the extreme price round-trips | Held — `99999999999999.999999` |

**4 passed.**
