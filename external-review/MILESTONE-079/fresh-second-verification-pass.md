# M079 — Fresh Second Verification Pass

Same agent, so **not** an independent review. A genuinely fresh environment and
deliberately different inputs.

- Database `m079_second_pass` **created empty**; the full migration chain
  applied from scratch.
- Different instruments: `SMCI`, `PLTR`, `COIN`, `ARM` — none used in the first
  suite.
- Different governance ids, different position keys, different timestamps
  (day 91–120 rather than day 40–60).
- Prices at both ends of the frozen `NUMERIC(20,6)` domain: `0.000001` and
  `99999999999999.999999`, plus `317.250001` and `401.9`.
- **Reversed insertion order**: the `REDUCED` is written *before* the
  backfilled `OPENED`, so insertion order cannot be what makes the firewall
  work.

## What the second pass attacked, and what held

| Claim | Result |
|---|---|
| Insertion order does not affect eligibility | Held — same answer with the order reversed |
| A reduction visible without its opening is incomplete, not corrupt | Held — `INCOMPLETE_KNOWLEDGE_SEQUENCE`, `position is None` |
| The same key folds once knowledge advances | Held — `KNOWN_OPEN`, quantity 25 after a 19-share reduction from 44 |
| The remaining quantity is valued at the ORIGINAL asserted entry price | Held — `317.250001`, never the reduction's `401.9` |
| The reduction's asserted price never renders | Held — `401.9` absent from the rendered output |
| Raw SQL agrees with the module at three cutoffs | Held — 1, 1, 2 eligible events at `S1`, `S2`, `S3` |
| Determinism on a fresh database | Held — two reads identical |

**3 passed.**
