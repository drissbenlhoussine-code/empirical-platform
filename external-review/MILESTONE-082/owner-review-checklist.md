# M082 - Owner Review Checklist

## The judgment calls, stated so you can overrule them

| # | Call | Why |
|---|---|---|
| 1 | **Two transactions, not one** | One transaction guarantees the proved commit-gap leak. Two admit a crash window where an event has no receipt. An honest absence beats a false presence. |
| 2 | **Claim an upper bound, not a commit time** | `track_commit_timestamp` is off and `pg_xact_commit_timestamp` errors here. Claiming commit time would be faking it. |
| 3 | **Emit no sequence** | Proved: assignment order is not commit order, and gaps are not missing data. Two standing misreadings for no capability. |
| 4 | **Application host clock, not the database clock** | The instant must follow the read-back that proves durability; taking it in-process makes that ordering unambiguous. |
| 5 | **Never backfill legacy events** | The table is created empty. Absence stays absence. |
| 6 | **Do not disable the old M076 writer** | That would alter frozen behaviour. The cost is that coverage is not universal, and the artifact says so. |
| 7 | **Do not make M079/M080/M081 consume this** | It would change the meaning of every figure they emit. That is a future authorized milestone. |
| 8 | **⚠ Touch one frozen milestone's TEST file** | `test_m076_migration_is_reversible` downgraded by a relative step and assumed M076 was at head; any new migration breaks it. The fix targets M076's own predecessor revision. **No M076 semantics, source or schema changed.** This is the one place M082 touches a frozen milestone, and it is the decision most worth your scrutiny. |

## What to check

| # | Check | Where |
|---|---|---|
| 1 | The `recorded_at` gap is real | `scope-and-design-snapshot.md` §3 - five values persist, including year 2999 |
| 2 | The commit-gap leak is proved, not argued | `transaction-timing-evidence.md` §2 |
| 3 | The post-commit model closes it | §3 of the same file, same pause, opposite result |
| 4 | Commit-time authority is genuinely unavailable | §4 - `pg_xact_commit_timestamp` errors |
| 5 | Sequence rejection is proved | `concurrency-evidence.md` §1-2 |
| 6 | Legacy events are never backfilled | `test_no_receipt_instant_is_ever_manufactured_from_a_frozen_field` |
| 7 | The migration creates the table empty | migration source, and the up-down-up check |
| 8 | Immutability is database-enforced | direct `UPDATE`/`DELETE` both blocked by trigger |
| 9 | Concurrency yields exactly one receipt | six threads, zero errors, one row |
| 10 | M079/M080/M081 are byte-identical and do not reference receipts | `validation-results.md` |
| 11 | R01 and R02 are recorded, not hidden | `hostile-implementation-review.md` |
| 12 | No suppressions anywhere | grep over all M082 modules |

## What I would push back on

- **Calling `system_received_at` a commit time.** It is an upper bound.
- **Adding a receipt sequence.** Proved misleading.
- **Backfilling legacy events to make coverage look complete.** That fabricates
  knowledge history.
- **Having M079/M080/M081 silently adopt receipt authority.** That would rewrite
  the meaning of every frozen figure.
