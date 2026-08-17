# MILESTONE-082 - Operator Event Receipt Attestation - Scope and Design

> **⚠ CORRECTED AFTER OWNER REVIEW — READ THIS FIRST.**
>
> Two conclusions recorded below are **RETRACTED**. They are left in place, not
> deleted, so the original reasoning stays readable and the correction stays
> visible.
>
> **RETRACTION 1 (Owner finding 1) — "point-in-time historical snapshot".**
> The artifact was built from the CURRENT ledger, so a receipt created after the
> cutoff and an event created after the cutoff both changed the historical
> output. Executed: two databases with identical evidence at W produced
> `ATTESTED_AFTER_CUTOFF` vs `NO_SYSTEM_RECEIPT_EVIDENCE`, differing counts, and
> a leak of a future event's id, position and instrument symbol. Any sentence
> below claiming the artifact is a point-in-time snapshot, or that "nothing
> attested after the cutoff influences any figure", is **SUPERSEDED** by
> `reality-gate.md`. The snapshot is now built FROM RECEIPTS labelled at or
> before the cutoff; `ATTESTED_AFTER_CUTOFF`, `NO_SYSTEM_RECEIPT_EVIDENCE`,
> `attested_after_cutoff_count` and `unattested_count` no longer exist.
>
> **RETRACTION 2 (Owner finding 2) — the wall-clock upper bound.**
> Any sentence below asserting `commit_time(event) < system_received_at`, that
> `system_received_at <= W` implies durable commit by W, that the guarantee is
> "one-directional", or that M082 "can never overstate", is **RETRACTED**. A
> backward host clock breaks it, and the attack is executed in
> `test_a_backward_clock_breaks_the_wall_clock_implication`. What survives is
> the CAUSAL claim: the read-back preceded the receipt. **M082 therefore does
> NOT replace M079's `recorded_at` firewall.**
>
> Renames that followed: `attested_known_by` → `events_with_receipt_labelled_by`,
> `attested_as_of` → `receipt_label_cutoff`, `--attested-as-of` →
> `--receipt-label-cutoff`.


## Status: ACTIVE DESIGN OF THE IMPLEMENTED CANDIDATE - NOT OWNER FROZEN

*(Corrected by Owner finding 11: this said "NOT IMPLEMENTED" while serving as the
active design of an implemented candidate under review.)*

---

## 1. Repository Truth

Verified from git and `PROJECT_CHECKPOINT.md` at mission start, not taken from
the mission text.

```
branch                    master
HEAD                      28a10530dbc295fedacfa89c8aef246b35a0b86e
origin/master             28a10530dbc295fedacfa89c8aef246b35a0b86e
ahead/behind              0 / 0
working tree              clean
LATEST_FROZEN_MILESTONE   MILESTONE-081
M081_STATUS               APPROVED_AND_FROZEN
M082_STATUS               NOT_STARTED
NEXT_PERMITTED_ACTION     MILESTONE-082 -- recommendation only
```

Repository truth agrees with the expected starting state in every field.

## 2. M081 Starting State - The Chain, Read From Code

| # | Question | Answer, from source |
|---|---|---|
| A | who creates `event_timestamp` | **the caller**; a plain dataclass field |
| B | who creates `recorded_at` | **the caller**; a plain dataclass field |
| C | either caller-supplied? | **both are** |
| D | does the CLI generate one? | the shipped CLI stamps `datetime.now(UTC)`, but that is a *convention of one entry point*, not an enforced authority |
| E | can domain callers pass arbitrary `recorded_at`? | **yes** - proved below |
| F | does PostgreSQL generate any timestamp? | **no.** `information_schema` reports **zero** columns with a `DEFAULT` or `GENERATED` on `operator_position_event` |
| G | does PostgreSQL attest receipt time? | **no** |
| H | is `recorded_at` mutable after insert? | not through any application path; **not database-enforced** |
| I | is M076 persistence append-only? | at the application layer yes - the repository exposes `append_validated`, `list_all`, `list_for_position` and contains **no `UPDATE` and no `DELETE`**. Not enforced by the database |
| J | what does M079 filter? | exactly one predicate, `recorded_at <= K`, in `events_known_by` |
| K | what do M080/M081 inherit? | M080 calls `events_known_by`; M081 composes M080. Both inherit the filter and add none |
| L | what depends on `recorded_at`? | every historical knowledge claim M079, M080 and M081 make |
| M | any system receipt identity or sequence? | **none** - no `receipt`, `watermark`, `bigserial`, `IDENTITY` or `nextval` in any migration |
| N | any knowledge watermark on decisions/sessions? | **none** |

M079's own frozen docstring already says `recorded_at` "is an operator-supplied
field, not a system-assigned immutable" one. M082 is the milestone that supplies
what that sentence admits is missing.

## 3. Exact Pre-M082 Gap Proof

**Executed against real PostgreSQL, each attempt on its own position key so that
ledger-state rules cannot mask the result.**

| Attempt | Outcome |
|---|---|
| `recorded_at` = 365 days ago | **PERSISTED** |
| `recorded_at` = 365 days in the future | **PERSISTED** |
| `recorded_at` = year 1999 | **PERSISTED** |
| `recorded_at` = year 2999 | **PERSISTED** |
| `recorded_at` **before** `event_timestamp` | **PERSISTED** |

Read back by raw SQL, independent of the repository, the database holds exactly
those values. Nothing rejects any of them, and the table carries **no**
database-generated column.

> **A correction worth recording.** My first run of this probe reused one
> position key, so three of the five attempts were rejected - and I briefly read
> that as evidence of a `recorded_at` bound. It was not: they were rejected by
> the ledger's own open/closed state rules. Re-run with distinct keys, **all
> five persist.** The gap is wider than the first probe suggested, and I nearly
> recorded a false statement in the other direction.

**Therefore:** M079 cannot distinguish an event persisted today claiming
`recorded_at` of last week from an event genuinely present last week. The
firewall is sound *given* `recorded_at`; `recorded_at` is not an independent
authority.

## 4. Received Time Versus Durable Time - Proved, Not Assumed

Measured on this PostgreSQL 16.13:

| Function | Behaviour inside one transaction |
|---|---|
| `transaction_timestamp()` | frozen at transaction start; does **not** advance |
| `statement_timestamp()` | advances per statement |
| `clock_timestamp()` | advances continuously |

**All three are assigned before `COMMIT`. None is a commit time.**

### The mandatory commit-gap attack, executed

A transaction assigned its timestamp, then paused before committing. `K` was
chosen during the pause.

```
T1 timestamp ASSIGNED : 13:44:14.924211
K chosen DURING pause : 13:44:16.424349
rows VISIBLE at K     : 0          <- genuinely not yet durable
T2 COMMIT             : 13:44:17.926

AFTER commit, historical query "assigned_at <= K"  ->  returns the row
```

**Leak proven.** The row was invisible to every reader at `K`, yet a later
historical query at `K` reports it as available. An in-transaction timestamp
**cannot** support a durable-availability claim, and the size of the window is
irrelevant to whether the claim is true.

## 5. Commit-Time Authority - Investigated And Rejected

```
track_commit_timestamp = off
SELECT pg_xact_commit_timestamp(xmin) -> ObjectNotInPrerequisiteState:
                                          could not get commit timestamp data
```

`track_commit_timestamp` is off by default, requires a **server restart** to
enable, is not retroactive for already-committed transactions, and is a
deployment-wide setting the platform does not control.

**M082 therefore does not use commit timestamps and does not claim commit time.**
Recorded rather than faked.

## 6. Sequence Semantics - Investigated And Rejected As An Ordering Authority

Executed with two connections:

```
A assigned seq=1 ... commits LAST
B assigned seq=2 ... commits FIRST

sequence order : [A, B]
COMMIT order   : [B, A]      ->  sequence order != commit order
```

And with a deliberate rollback:

```
surviving sequence values: 1, 2, 3, 5      (4 consumed by the rolled-back txn)
```

So a `bigserial` is **assignment order, not commit order**, and its gaps do not
mean missing receipts. It could be carried while labelled precisely - but a
field whose name invites "commit order" and whose gaps invite "missing data" is
a misreading hazard for no capability gain: deterministic ordering is already
achievable from `(system_received_at, event_governance_id)`, both persisted.

**M082 emits no sequence.** The proof above is why.

## 7. Candidate Ranking

Scored 1-5. For risk rows, **5 = low risk**.

| Criterion | A in-txn receipt | **A' post-commit receipt** | B sequence | C watermark | D combined | E system recorded_at in M076 | F cross-session exposure | G calibration |
|---|---|---|---|---|---|---|---|---|
| scientific value | 3 | **5** | 2 | 4 | 4 | 4 | 3 | 2 |
| product value | 3 | **4** | 2 | 3 | 3 | 4 | 3 | 4 |
| knowledge-authority strength | 2 | **5** | 2 | 4 | 4 | 4 | 1 | 1 |
| temporal-leakage resistance | **1** | **5** | 2 | 3 | 2 | 2 | 3 | 2 |
| concurrency correctness | 2 | **5** | 2 | 2 | 2 | 2 | 4 | 3 |
| frozen-contract risk | 4 | **5** | 4 | 3 | 4 | **1** | 4 | 4 |
| schema complexity | 4 | **4** | 4 | 2 | 3 | 3 | 4 | 4 |
| operational complexity | 4 | **4** | 4 | 2 | 3 | 3 | 4 | 4 |
| backward compatibility | 4 | **5** | 4 | 3 | 4 | 1 | 5 | 5 |
| testability | 4 | **5** | 4 | 3 | 4 | 3 | 4 | 4 |
| downstream calibration unlock | 3 | **4** | 2 | 4 | 4 | 4 | 2 | 2 |
| operator usability | 3 | **4** | 3 | 2 | 3 | 4 | 3 | 3 |
| failure-mode honesty | 2 | **5** | 3 | 2 | 3 | 2 | 4 | 2 |
| **total** | **39** | **60** | **38** | **37** | **43** | **37** | **44** | **40** |

## 8. Selected Capability

**MILESTONE-082 - Operator Event Receipt Attestation.**

An **additive, append-only sidecar** that records, for an M076 event, that the
platform's persistence boundary **observed the event already durably committed**
at a system-assigned instant.

The receipt is written in a **second transaction, after the event's transaction
has committed**, and only after the receipt writer has **read the event back**.

### Why this is sound where the in-transaction model leaks

Because the receipt instant is taken strictly **after** the event is durably
committed:

```
RETRACTED (owner review finding 2) - the inequality below is NOT proved and is
false under a backward host clock. Kept verbatim as the original reasoning.

commit_time(event)  <  system_received_at(receipt)
```

Therefore:

```
system_received_at <= K   IMPLIES   the event was durably committed by K
```

**Proved by execution**, using the same pause that broke the in-transaction
model: with `K` chosen during the uncommitted window, the post-commit receipt
query at `K` correctly returns **nothing**.

The converse does **not** hold, and that asymmetry is the design: an event
committed just before `K` but receipted just after `K` is **excluded**. The
error direction is **conservative** - M082 may *understate* what was known, and
can never *overstate* it. A false negative is a safe direction for a knowledge
claim; a false positive is exactly the M079-style leak.

## 9. Rejected Alternatives

**A - in-transaction receipt timestamp. REJECTED, with the leak proved** in §4.

**B - database monotonic sequence. REJECTED as an ordering authority**, with
assignment-order-is-not-commit-order and rollback gaps both proved in §6.

**C - knowledge watermark. REJECTED for M082.** A watermark must denote a stable
committed prefix. Under out-of-order commits (proved in §6) no prefix over
assignment order is stable, and a watermark over *post-commit receipts* is
buildable only once post-commit receipts exist - which is this milestone. It is
the natural M083, not M082.

**D - combined receipt + sequence. REJECTED**: the sequence adds a misreading
hazard and no capability, per §6.

**E - system-assigned `recorded_at` inside M076. REJECTED.** It would mutate a
frozen dataclass, a frozen table and a frozen repository contract, and would
silently change the meaning of every historical M079/M080/M081 statement. The
mission's own instruction is that this needs extraordinary justification;
an additive sidecar supplies the authority without any of that risk.

**F - cross-session exposure evolution. REJECTED**: real, but it does not close
the authority gap the whole M079-M081 stack rests on.

**G - decision calibration / aggregation. REJECTED as premature**: calibration
built on operator-supplied `recorded_at` would inherit exactly the weakness this
milestone exists to fix.

## 10. Authority Model

M082 introduces **one** new authority and is precise about its level:

> The platform's persistence boundary **observed** that this M076 event was
> **already durably committed** at `system_received_at`, measured by the
> **application host clock** of the process performing the attestation.

## 11. Clock Authority

The clock is the **application host clock** (`datetime.now(UTC)` in the
attesting process), not the database server clock and not an external time
service.

Chosen over the database clock deliberately: the receipt must be taken *after*
the read-back that proves durability, and a value taken in the attesting process
after that read is unambiguous about ordering, whereas a database-side `now()`
in the receipt transaction would re-open a "which clock, relative to what"
question for no benefit.

**Honest limits, stated rather than narrated away:** the host clock can be
wrong, can be adjusted, can move backward under NTP correction, and a
sufficiently privileged operator or administrator could influence it. M082 says
**system-assigned**, never *true time* or *actual time*. It is not a trusted
timestamping service and makes no cryptographic claim.

## 12. Receipt Semantics

A receipt asserts, and asserts only:

- an M076 event with this `event_governance_id` was **read back as committed**
  by the attesting process;
- at `system_received_at`, taken from the application host clock **after** that
  read;
- through the attesting pathway named in `attested_by`.

It does **not** assert that the operator's claim is true, that a trade occurred,
that `recorded_at` is honest, or that the event was durably visible at any
instant *earlier* than `system_received_at`.

## 13. Receipt Versus Commit Semantics

> **⚠ RETRACTED (owner review finding 2).** The sentence below is withdrawn.
> `system_received_at` bounds nothing; it is a system-assigned label. Kept
> verbatim as the original reasoning.

`system_received_at` is an **upper bound witness** on the event's commit time,
never the commit time itself:

```
commit_time(event) < system_received_at    [known]
commit_time(event) = ?                     [NOT known, and not claimed]
```

M082 does not know when the event committed. It knows the event **had already
committed** by `system_received_at`.

## 14. Concurrency Model

Receipts are independent per event. Two concurrent attesters for the **same**
event race, and the database resolves it: a `UNIQUE` constraint on
`event_governance_id` means exactly one receipt survives and the loser sees an
integrity error, which the repository surfaces as "already attested" rather than
as a fault.

Because §6 proved assignment order is not commit order, M082 emits **no
ordering authority** beyond the receipt instants themselves, and its
deterministic ordering is `(system_received_at, event_governance_id)`.

## 15. Transaction Model

**Two transactions, deliberately.** §9 of the mission asks both to be analysed:

| Model | Benefit | Cost |
|---|---|---|
| one transaction | no event-without-receipt partial commit | **receipt instant precedes commit - the proved leak** |
| **two transactions** | receipt is taken only after durable commit; the leak is structurally impossible | a crash between phases leaves an event permanently unreceipted |

The two-transaction cost is **accepted deliberately**, because an unreceipted
event is an *honest absence*, whereas a pre-commit receipt is a *false
presence*. Absence is recoverable later by an honest, clearly-later receipt;
a fabricated historical instant is not recoverable at all.

## 16. Crash And Failure Model

| Failure | Outcome |
|---|---|
| crash after event commit, before receipt | event exists, **no receipt**. Honest state, never fabricated |
| crash during receipt transaction | receipt transaction rolls back; event still unreceipted |
| receipt attempted for a missing event | **refused** - the read-back finds nothing, and the FK would refuse anyway |
| attestation retried later | permitted; the receipt records the **later, true** instant |

**A later reconciliation may assign a later receipt instant. It may never assign
a guessed historical one.**

## 17. Legacy-Event Semantics

M076 already holds events created before M082. M082 **must not** manufacture a
receipt for them from `recorded_at`, `event_timestamp`, a migration time, or any
other guess.

The migration creates the receipt table **empty**. It backfills nothing.

An event with no receipt reports `NO_SYSTEM_RECEIPT_EVIDENCE`. It remains a
perfectly valid M076 operator assertion; it simply carries no M082 authority.
**Absence remains absence.**

## 18. Bypass Semantics

The M076 writer still exists and is unchanged, so events can still be appended
without a receipt. M082 therefore does **not** claim that all future M076 events
carry receipt authority, and says so:

> Only events possessing a valid M082 receipt are eligible for
> M082-authoritative knowledge analysis. Unreceipted events remain valid M076
> operator assertions and lack M082 receipt authority.

Disabling the old writer would alter frozen behaviour and is not done.

## 19. Immutability Semantics

Enforced in **two** layers, and reported as exactly what each is:

- **API append-only:** the repository exposes `attest` and read methods only.
  There is no `UPDATE` and no `DELETE` code path.
- **Database-enforced:** a `BEFORE UPDATE OR DELETE` trigger on the receipt
  table raises an exception, so even direct SQL cannot mutate a receipt.

The distinction the mission asks for is kept: without the trigger this would be
*API append-only*; with it, receipts are *database-enforced immutable* against
`UPDATE` and `DELETE`. A superuser can still drop the trigger; that is stated,
not hidden.

## 20. Temporal Query Semantics

> **⚠ RETRACTED AND SUPERSEDED (owner review findings 2 and 5).** The whole of
> this section as originally written is withdrawn. It is kept verbatim below so
> the original reasoning stays readable.
>
> **What is true instead.** M082 exposes a **RECEIPT-LABEL-CUTOFF VIEW**:
>
> ```
> events_with_receipt_labelled_by(events, receipts, receipt_label_cutoff)
>   = events whose receipt exists and whose system_received_at <= the cutoff
> ```
>
> The only property this has is **label selection**: no entry can be derived
> from a receipt whose system-assigned label is after the cutoff. It is **NOT**
> a claim that the cutoff establishes real wall-clock knowledge time, and **NOT**
> a claim that the selected events were durably committed or available by that
> instant. A label can be backdated, so a receipt created later can still
> qualify, and repeated evaluation at the same cutoff can return more.
>
> `attested_known_by` was renamed `events_with_receipt_labelled_by` precisely
> because "known by" asserted what the label cannot support.

**RETAINED VERBATIM AS THE ORIGINAL, WITHDRAWN REASONING:**

M082 exposes an attested knowledge snapshot at a cutoff `W`:

```
attested_known_by(events, receipts, W)
  = events whose receipt exists and whose system_received_at <= W
```

Sound direction: every event returned **was durably committed by `W`**.
Conservative direction: an event may be omitted although it had committed by `W`,
if its receipt came later. Both are stated on every report.

## 21. Interaction With M079

**None. M079 is frozen and untouched.**

> **⚠ SUPERSEDED (owner review findings 2 and 5).** M082 does not add a second
> "snapshot", and its field is no longer called `attested_as_of`. M079 keeps its
> own frozen vocabulary; M082 emits a **receipt-label-cutoff view** whose field
> is `receipt_label_cutoff`. The two authorities are still separate, and M082
> is the **weaker** of the two in what it establishes about time — it does not
> replace M079's `recorded_at` firewall. Original text kept verbatim below.

M079 remains the *operator-recorded* knowledge snapshot, filtering
`recorded_at <= K`. M082 adds a distinct *system-receipt-attested* snapshot,
filtering `system_received_at <= W`. These are two different products with two
different authorities, and the vocabulary keeps them apart: M079 says
`knowledge_as_of`, M082 says `attested_as_of`.

M082 does **not** reinterpret, wrap or silently strengthen any M079 output.

## 22. Interaction With M080 And M081

**None.** Neither is modified, and neither begins consuming receipt authority.
M080 and M081 continue to inherit M079's `recorded_at` filter exactly as frozen.

Making them attested-aware would change the meaning of every figure they emit
and is a **future authorized milestone**, not a side effect of this one.

## 23. Schema And Persistence

**One** minimal additive migration creating **one** table:

| Column | Type | Why |
|---|---|---|
| `receipt_governance_id` | `String(64)` PK | receipt identity |
| `event_governance_id` | `String(64)` **UNIQUE**, FK -> `operator_position_event.governance_id` **ON DELETE RESTRICT** | exactly one receipt per event; the FK refuses a receipt for a missing event |
| `system_received_at` | `TIMESTAMPTZ NOT NULL` | the attestation instant |
| `attested_by` | `String(64) NOT NULL` | the pathway that attested |
| `attester_version` | `String(32) NOT NULL` | which writer produced it |

`ON DELETE RESTRICT`, never `CASCADE`: M076 is append-only, but if a row were
ever removed, the receipt evidence must **not** silently vanish with it.

Plus the immutability trigger of §19. No change to any existing table.

## 24. CLI And Usecase

One additive query entry point,
`empirical-platform-attested-evidence-snapshot`, requiring `--attested-as-of`
with **no default**, plus `--json`.

Attestation itself is a usecase (`AttestOperatorEventReceiptHandler`) rather
than a second copy of the M076 recording CLI, so the existing recording path is
not duplicated and not disturbed.

## 25. Deterministic Ordering

`(system_received_at, event_governance_id)` - both persisted, both stable. Never
by receipt insertion order, and never by a sequence, per §6.

## 26. Duplicate And Retry Semantics

Attestation is **idempotent by event**. A retry after a successful attestation
returns the existing receipt unchanged and creates no second authority; the
`UNIQUE` constraint makes that structural rather than advisory.

A retry after a *failed* attestation creates the receipt with the **later** true
instant.

## 27. Failure And Absence Vocabulary

| State | Meaning |
|---|---|
| `ATTESTED` | a receipt exists and `system_received_at <= W` |
| `NO_SYSTEM_RECEIPT_EVIDENCE` | the event exists and has no receipt |
| `ATTESTED_AFTER_CUTOFF` | a receipt exists but is later than `W` |

No state is ever inferred from `recorded_at`.

## 28. Frozen-Contract Preservation

M070 and M075-M081 read-only and byte-unmodified. No existing table altered. No
existing repository method changed. The M062/M064/M065 seal debt untouched.

## 29. Security

The attestation pathway performs no privilege escalation, adds no dependency,
and stores no secret. `attested_by` and `attester_version` are recorded strings,
not authorities in themselves.

## 30. What M082 Proves, And What It Does Not

**Proves:** that the platform's persistence boundary observed the event already
durably committed at a system-assigned instant, so `system_received_at <= W`
implies durable commit by `W`.

**Does NOT prove:** the event's commit time; wall-clock truth; that
`recorded_at` is honest; that the operator's assertion is true; that any trade
occurred; anything at all about a legacy unreceipted event; and it does **not**
retroactively attest anything.

## 31. M083 Boundary

Explicitly not built: any knowledge watermark; any change to M079, M080 or M081;
any attested recomputation of the round-trip result or ratio; any calibration;
any commit-timestamp dependency; any sequence authority; any backfill.

**Recommended M083, recommendation only:** an attested knowledge watermark, now
buildable *because* post-commit receipts exist - the stable committed prefix §9
showed was impossible without them.

---

## Amended by the final Owner authority hardening pass

Three further findings changed the design after the correction pass. The
sections above are preserved verbatim; where they conflict with what follows,
**this section wins**.

### Finding 3 — the migration still carried the retracted upper-bound claim

The previous reconciliation sweep covered `src`, `tests`, this document and
`external-review`, and **did not search `migrations/`** — the one file defining
the persisted schema. Corrected in place. The sweep is now a script over the
whole tree that classifies each hit as ACTIVE or RETRACTION-MARKED.

### Finding 4 — a persisted row now proves the causal claim

`BEFORE INSERT ON operator_event_receipt` refuses a receipt whose referenced
event was written by the current transaction. Before it, a direct SQL caller
could insert an event and a matching receipt in one transaction — the foreign
key was satisfied because the event was visible to that transaction — and the
report listed the result as authoritative with a forged label and attester.

The mechanism was chosen by measurement on PostgreSQL 16.13, not by reading
documentation. `xmin = pg_current_xact_id()::xid` **misses savepoints**: a
subtransaction gets its own, higher xid (`equal=false` while the attack
succeeds). An xid ordering comparison **falsely refuses** a concurrent committed
writer holding a higher xid (measured: reader 140579, row xmin 140580,
`committed`). The trigger therefore tests whether the writing transaction is
still `in progress`, which is correct across same-transaction, one savepoint,
nested savepoints, rollback-to-savepoint, concurrent-higher-xid, frozen rows and
aborted transactions.

**Still not enforced:** `system_received_at`, `attested_by` and
`attester_version` are unauthenticated labels, forgeable by direct SQL for an
already-committed event. A test asserts that forgery succeeds so the limitation
cannot drift.

### Finding 5 — this is a RECEIPT-LABEL-CUTOFF VIEW, not a snapshot

Because a label can be backdated, a receipt created later can carry a qualifying
label, so **repeated evaluation at the same cutoff can return more**. Executed
through the real attestation path. `HISTORICAL_OUTPUT_POST_W_INDEPENDENT=YES` is
**SUPERSEDED**: the view is independent of receipts whose persisted *label*
exceeds the cutoff and of events lacking a qualifying receipt — not of receipts
created later with a backdated label. No hidden creation timestamp was added;
that would reopen finding 4 one layer down.

### Immutability wording

Narrowed everywhere to **row-level UPDATE/DELETE under the installed trigger**.
`TRUNCATE` succeeds, and a test proves it.


---

## Amended by the Owner correction mission (findings 7-11)

Five further findings were reproduced by execution against `699d7f9` before any
change. Where earlier sections conflict with this one, **this section wins**.

### Finding 7 - the receipt did not bind the event payload

A receipt was created for `EV-MUTATE`; the M076 row was then changed by direct
SQL from `POS-ORIGINAL`/`AAPL` to `POS-MUTATED`/`ZZZZ`. The receipt identity and
label were unchanged, **and the report changed** - it resolved position and
instrument from the *current* M076 row. M076 carries **zero** user-defined
triggers, so nothing made that row immutable, and this milestone's own source
nevertheless called it immutable.

**Candidates ranked.**

| | Candidate | Authority gained | Cost | Verdict |
|---|---|---|---|---|
| **A** | **receipt-only: attest the event IDENTITY, drop payload enrichment** | none beyond what is already proved | the artifact stops showing instrument/position | **SELECTED** |
| B | capture the payload into the receipt row by trigger | a NEW claim: "payload as of receipt time" | new columns, more trigger surface, and it *strengthens* M082 - which this mission forbids | rejected |
| C | make M076 rows immutable once a receipt exists | payload stability | alters a **frozen** milestone's table behaviour and its downgrade path | rejected |

A is the smallest honest design, and it is the only one that does not add a
claim. It also **collapses findings 9 and 10**: with no ledger read there is no
malformed-row exposure and no split-read race.

M082 therefore states plainly: **it does not attest the payload of the M076
event, current or historical.**

### Finding 8 - `pg_temp` shadowing bypassed the prior-commit trigger

A role with `rolsuper`, `rolcreatedb` and `rolcreaterole` all false created a
TEMP relation named `operator_position_event`, committed a decoy row into it,
and then in a second transaction inserted the real event and its receipt. The
trigger's **unqualified** read resolved `pg_temp` ahead of `public`; the receipt
inserted, and afterwards `event xmin = receipt xmin` - one transaction.

Every relation and function in the trigger is now schema-qualified, the function
carries `SET search_path = pg_catalog, public`, and all four repository
statements are qualified as well.

### Finding 9 - malformed future tails reached the report

A 2099 receipt with a database-accepted blank `attested_by` made a 2027 report
raise `ValueError`; an unreceipted 2099 event with a `NUMERIC NaN` price made it
raise `InvalidOperation`. The cutoff is now applied **in SQL**, four `CHECK`
constraints enforce non-empty receipt identity and metadata at the write
boundary, and the ledger is not read at all.

### Finding 10 - two non-atomic reads

`ledger.list_all()` then `receipts.list_all()`, with an event and receipt
committing between them, produced `MissingAttestedEventError`. One store, one
cutoff-narrowed query. `MissingAttestedEventError` no longer exists.

### Fail-closed hardening - explicit allowlist

`committed` and a documented `NULL` accept; **everything else refuses**,
including `in progress` and `aborted`. The previous denylist would have accepted
any future status value.

### The claim M082 now makes

> A persisted M082 receipt binds a stable receipt identity to an exact M076
> event governance identity whose real public-table row was visible as coming
> from a prior committed transaction at receipt insertion. The receipt label is
> not commit time, trusted wall-clock truth, historical knowledge time, or proof
> of availability at an arbitrary cutoff.
>
> **M082 does not attest the current or historical payload of that M076 event.**
