# M077 — Reality Gate

Questions the platform could not answer before M077, answered from code after.

| Question | Before | After |
|---|---|---|
| How much of my capital is already represented by positions I asserted? | Unanswerable — nothing related the ledger to a capital base | `held_asserted_notional` against an explicit policy |
| Which of today's plans still fit given what I already hold? | Unanswerable — M075 assessed today's plans in isolation | Per-plan verdicts after held exposure is charged |
| Am I already at my concurrent-position limit? | Unanswerable | Held positions seed the cap; plans reject with `MAX_CONCURRENT_POSITIONS` |
| Did I already act on one of today's plans? | Unanswerable | `plans_already_acted_upon`, so one decision is never charged twice |
| Is any of this a broker fact? | — | **No**, and the rendered banner says so |

## What M077 still does not claim

No execution, no fills, no broker verification, no market valuation, no
realized or unrealized P&L, no verified account balance, no allocation or
reservation of capital, no profitability, no advice. Vocabulary is restricted
to `ASSERTED` / `PROPOSED` / `FITS` / `EXCEEDS` / `WITHHELD`, and a
parametrised test asserts `EXECUTED`, `FILLED`, `VERIFIED`, `ALLOCATED` and
`MARKET_VALUE` appear nowhere in the vocabulary.
