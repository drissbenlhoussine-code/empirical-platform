# M082 - Fresh Second Verification Pass

Same agent, so **not** an independent review. A genuinely new database, created
empty and migrated from scratch, with deliberately different inputs.

- Database `m082_second_pass`, **dropped and created empty**, full migration
  chain applied from scratch.
- Different instruments: `PLTR`, `COIN`, `ARM`, `SMCI`.
- Different event ids, positions, quantities and prices.
- Different effective timestamps (2027, not 2026).
- **Deliberately false `recorded_at`** values: five years early, and 900 days
  early.
- Concurrent attestation, retry, and a bypassed legacy event never attested.

## What the second pass attacked, and what held

| Claim | Result |
|---|---|
| A five-year-early `recorded_at` reaches the receipt | **Did not** - the instant is system-assigned and matches neither the lie nor the event timestamp |
| A bypassed legacy event gets attested | **Did not** - `NO_SYSTEM_RECEIPT_EVIDENCE`, instant `None` |
| Five concurrent attesters create multiple authorities | **Did not** - one instant, one row, and a later retry returns the same |
| The cutoff boundary drifts on a fresh database | **Did not** - excluded one microsecond before, included exactly at |

**4 passed.**

The env-var override used to point alembic at the fresh database is scoped to
the alembic call **only**; leaving it set across the yield would make later
comparisons compare a database with itself.
