# MILESTONE-084 — Executed Concurrency Campaign

**36 races, executed against real PostgreSQL 16.13, three times against three
freshly created databases.** `tests/integration/test_m084_concurrency.py`.

A unique constraint is a *claim* about what a database will do. Nothing below
argues from that claim: every race opens two real connections in two real
transactions, makes them contend, and records which one won and what the loser
was told.

## 0. Method, and why no result here rests on a timer

**No `sleep` is used as proof anywhere in this suite.** Each race sequences its
two connections with `threading.Barrier`, so neither can reach the contended
statement before the other has started. Where a race needs one transaction to
be *inside* an uncommitted write while the other runs, it is held there by a
`threading.Event` released by the other connection — not by hoping a timer
lines up.

The one timeout in the file is a **failure bound**: `Barrier(2, timeout=30)`.
If the two connections do not meet, the test fails. It never passes slowly.

Each race reports, from the harness rather than from narration:

| Field | Meaning |
|---|---|
| `outcomes` | what each connection returned: `COMMITTED`, or the exception type and message |
| `winners` / `losers` | how many committed, how many were refused |
| `final_rows` | what the table actually holds afterwards, read on a third connection |
| `loser_errors` | the losing exception text — checked, not just counted |

## 1. Three clean repetitions, with reset proof

Each repetition ran against a database **created fresh for that repetition**.
The proof is `pg_database.oid`: PostgreSQL assigns a new OID on every CREATE
DATABASE, so three distinct OIDs mean three genuinely distinct databases and
not a reused one that a TRUNCATE happened to empty.

| Repetition | Database | `pg_database.oid` | Result | Test-id set sha256[0:16] |
|---|---|---|---|---|
| 1 | `empirical_conc_r1` | 1174427 | **36 passed** in 1.83s | `0dbbdc6fd184f7bf` |
| 2 | `empirical_conc_r2` | 1176417 | **36 passed** in 1.66s | `0dbbdc6fd184f7bf` |
| 3 | `empirical_conc_r3` | 1178404 | **36 passed** in 1.72s | `0dbbdc6fd184f7bf` |

Three distinct OIDs. Identical test-id checksums, so the three runs executed
the same set of races and not a silently reduced one.

## 2. Anti-vacuity: the races detect a weakened schema

A concurrency suite that passes against a database with no unique constraint
proves nothing. Verified directly:

| Mutation | Expected | Observed |
|---|---|---|
| Drop `uq_trade_approval_decision_one_per_proposal` from the migration | the one-decision races fail | **2 failed** — `d24_two_different_operators_leave_exactly_one_named` (both `alice` and `bob` committed) and `d28_an_approval_retry_after_uncertainty_reads_the_winner` (the retry landed instead of conflicting). The other 34 still passed, which is correct: they do not depend on that constraint. |
| Restore the migration byte-for-byte | all pass | **36 passed**; `git diff --stat` on the migration is empty |

## 3. The races

### A. Configuration (4)

| # | Race | Isolation | Mechanism | Outcome |
|---|---|---|---|---|
| A1 | two *different* versions for one identity | READ COMMITTED | barrier | **both commit** — versions 1 and 2 both stored. Recorded because a "race" here would mean the schema was refusing a legal write. |
| A2 | two *identical* version creations | READ COMMITTED | barrier | 1 winner, 1 loser on `pk_operator_trading_configuration`; exactly 1 row |
| A3 | one version, two **different policies** | READ COMMITTED | barrier | 1 winner; the stored `maximum_daily_loss` is one of the two, never a blend. The dangerous case: a proposal citing that version must be governed by a policy someone can name. |
| A4 | reader during an uncommitted version | READ COMMITTED | event-gated | reader sees **0 rows**, is not blocked, and the writer's rollback leaves 0 |

### B. Evaluation context (6)

| # | Race | Mechanism | Outcome |
|---|---|---|---|
| B5 | identical identity, identical inputs | barrier | 1 winner, 1 row |
| B6 | identical identity, **conflicting** inputs (different `quote_id`) | barrier | 1 winner; exactly one quote id stored. Both cannot be true and the database holds only one. |
| B7 | context commits while its configuration is uncommitted, then rolled back | event-gated | context **refused** (`IntegrityError`); 0 rows. The FK cannot see an uncommitted parent, so a context can never bind to a configuration that never existed. |
| B8 | context commits while its **watermark** is uncommitted, then rolled back | event-gated | context **refused** (`IntegrityError`) |
| B9 | winner rolls back | sequential | the identity is free again; a later insert with different inputs succeeds |
| B10 | retry after commit uncertainty | sequential | the retry conflicts and the read-back returns the **winner's** row, which is the pattern a repository must use |

### C. Proposals (9, of which 3 are the isolation matrix)

| # | Race | Outcome |
|---|---|---|
| C11 | identical proposal construction | 1 winner, 1 row |
| C12 | one identity, **quantity 9 vs 99** | 1 winner; exactly one quantity stored. The most dangerous proposal race: an operator must never be shown one quantity and have another persisted under that identity. |
| C13 | one identity, two fingerprints | 1 winner; one fingerprint |
| C14 | invalidation vs expiry on one row | 1 winner, 1 loser; the row is `INVALIDATED` **or** `EXPIRED`, never half-transitioned. The loser met the terminal-state guard after waiting on the row lock. |
| C15 | proposal insert vs kill-switch version | **both commit.** Engaging the switch writes a new configuration version; it does not retract an already-prepared proposal. Recorded because a reader might assume otherwise. |
| C16 | two different proposals for one symbol | **both commit.** The schema does not enforce one-proposal-per-symbol, and the authority contract does not claim it. |
| C17 | quantity race under **READ COMMITTED** | 1 winner, 1 row, loser told |
| C18 | quantity race under **REPEATABLE READ** | 1 winner, 1 row, loser told |
| C19 | quantity race under **SERIALIZABLE** | 1 winner, 1 row, loser told |

C17–C19 run the identical contention at each level an operator might set. The
winner count holds at all three. The loser's *error* legitimately differs — a
unique violation under READ COMMITTED, possibly a serialization failure under
SERIALIZABLE — and both are honest outcomes a caller must retry rather than
ignore. The suite asserts the loser was told, not which words it was told in.

### D. Approval decisions (9)

| # | Race | Outcome |
|---|---|---|
| D20 | **APPROVE vs REJECT** | 1 winner, 1 loser. The proposal's status and the surviving decision **agree** — asserted jointly, because an APPROVED proposal with a REJECT on file, or with no decision at all, is the unsafe outcome this milestone exists to prevent. |
| D21 | **APPROVE vs CANCEL** | as D20 |
| D22 | approve vs invalidate | `(APPROVED, 1 decision)` or `(INVALIDATED, 0 decisions)`. An INVALIDATED proposal carrying an approval never occurred. |
| D23 | two identical approvals | 1 winner, 1 decision |
| D24 | **two different operators** (`alice` vs `bob`) | 1 winner; exactly one operator on the record. Whose approval it is is never ambiguous. |
| D25 | approval vs expiry | `(APPROVED, 1)` or `(EXPIRED, 0)` |
| D26 | approval vs kill-switch version | both commit; 1 decision, 2 configuration versions |
| D27 | approval vs a **superseded proposal version** | the version-2 decision is refused by the admission trigger; the stored decision cites version 1 |
| D28 | approval retry after uncertainty | the retry conflicts; the read-back returns `DEC-0001` |

### E. Approved intents (8)

| # | Race | Outcome |
|---|---|---|
| E29 | two identical issuances | 1 winner, 1 intent |
| E30 | two intents with **conflicting quantities** | at most 1 intent; if one is stored its quantity is the approved proposal's `9`. Two intents authorizing different orders from one human approval never occurred. |
| E31 | intent vs proposal invalidation | never `(INVALIDATED, 1 intent)`. APPROVED is terminal, so the invalidation loses outright. |
| E32 | two intents created **after the approval lapsed** | **0 winners.** Both refused, both errors contain `lapsed`. |
| E33 | intent vs kill-switch version | **both commit.** Recorded honestly: engaging the switch does not block an intent for an already-approved proposal. The switch stops new evaluations. The authority contract claims nothing more. |
| E34 | rolled-back intent | the proposal is free for a retry, which succeeds |
| E35 | **direct-SQL competitor** (`INSERT … SELECT`, never through the repository) | at most 1 intent. It meets the same unique constraint, which is the entire reason the rule lives in the database. |
| E36 | unique collision vs **unrelated** integrity error | 1 winner; the loser failed on `never_submitted` (a CHECK) and **not** on a `uq_` index. A repository that retried on every `IntegrityError` would retry a CHECK violation forever, so the two must be distinguishable — and they are. |

## 4. Blockers

**None.** Every race resolved to a safe, single, consistent winner, and every
loser was told. No inconsistent or unsafe winner was observed in any of the
three repetitions.

## 5. What this campaign does not establish

- It does not prove the absence of every possible interleaving. No finite set
  of executed races could, and this document does not claim otherwise.
- Three of the races (A1, C15, C16, D26, E33) end with **both** connections
  committing. Those are recorded because they document behaviour a reader
  might wrongly assume is prevented — distinct configuration versions, distinct
  proposals for one symbol, and the kill switch not retracting existing work.
- The campaign ran on a single host with a local PostgreSQL. It says nothing
  about behaviour across a replicated or failing-over cluster.
