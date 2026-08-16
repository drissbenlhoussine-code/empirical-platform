# M082 - Concurrency Evidence

All executed against real PostgreSQL.

## 1. A sequence is assignment order, not commit order

Two connections:

```
A assigned seq=1 ... committed LAST
B assigned seq=2 ... committed FIRST

sequence order : [A, B]
COMMIT order   : [B, A]        ->  they disagree
```

## 2. Sequence gaps do not mean missing receipts

With a deliberate rollback between two inserts, the surviving values were
`1, 2, 3, 5`. The `4` was consumed by the rolled-back transaction. **A gap is
not lost data.**

**Consequence:** M082 emits **no sequence**. It would carry two standing
misreadings for no capability, since deterministic ordering is already available
from `(system_received_at, event_governance_id)`.

## 3. Receipt order is attestation order

Two events, the second appended later but attested **first**:

```
EV-ORD-B attested at .314
EV-ORD-A attested at .818
list_all() -> [EV-ORD-B, EV-ORD-A]
```

M082 claims exactly this and nothing more: the receipts order by when
attestation ran. No commit-order authority is claimed.

## 4. Concurrent attesters for one event

Six threads attesting the same event simultaneously:

- **no errors**
- **exactly one receipt row**
- **every caller observed the same instant**

The `UNIQUE` constraint decides; the losers report the winner's receipt rather
than failing.

> **This is where implementation defect R01 was found.** The first version read
> the winner back *while still inside the losing transaction*, which raised
> "Nested persistence units of work are not supported" — so the losers crashed
> instead of reporting the winner, which is precisely the case the branch exists
> to handle. The conflict is now only *detected* inside the transaction and the
> winner is read after it closes.

## 5. Rollback and recovery

- a rolled-back receipt leaves **no row**;
- the event correctly remains `NO_SYSTEM_RECEIPT_EVIDENCE`;
- re-attestation afterwards succeeds and records a **later, true** instant,
  never a historical one.
