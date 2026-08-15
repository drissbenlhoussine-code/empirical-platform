# MILESTONE-076 - Operator-Asserted Position Ledger - Macro Milestone Freeze

## Status: FINAL - OWNER FROZEN

## Repository Authority

Repository `C:\Users\LuxSy\Documents\trading`, branch `master`. M076 baseline
`92ff47217716aebba7b88633afed40b5265c68b2` (the M075 Owner Freeze
hash-recording HEAD; M075 fully `APPROVED_AND_FROZEN`), independently
re-verified from git at mission start rather than taken from the mission
text. Delivered through pull request #6, owner-approved at head
`f41c35efd41cfc16a5b923898154f82b725bf588` with the `foundation` workflow
green on that exact SHA, and merged into `master` as
`635a2f6219ec685e6a4e1c2b1d86dc2917ac84e7`.

The pull request was merged with a true merge commit. **All three commits are
preserved and none was squashed away:** the initial implementation
`14e8bd29132b73d4e2db6de477c0c48307d0741b`, owner correction pass 1
`f1b4340b907237bee16e7877066d943e29ab0ab3`, and owner correction pass 2
`f41c35efd41cfc16a5b923898154f82b725bf588`. The correction history is part of
the frozen record, not an embarrassment to be tidied out of it.

Scope, capability matrix, eight-candidate ranking, architecture, domain and
persistence semantics, temporal semantics, and the pre-implementation
adversarial design review are recorded in
`MILESTONE_076_OPERATOR_ASSERTED_POSITION_LEDGER_SCOPE_AND_DESIGN.md`.

## Why M076 Exists

The mission required attacking, not assuming, the claim that durable
cross-day position state was the highest-leverage missing primitive. It was
attacked and it survived, on evidence rather than on assertion.

**Forty-three tables existed and not one modelled an operational position.**
`position_plan` is a terminal sizing verdict with no lifecycle and no
open/closed state. M071 carries decisions but never exposure. The only
`OPEN`/`CLOSED` vocabulary anywhere in the repository belonged to M067/M068
*historical simulation*, which replays a hypothetical portfolio over past
data and holds nothing. All seven questions of the mission's special gate --
what is held right now, at what size, entered when, at what asserted price,
what was closed and when, what changed since yesterday, and what is the
current exposure -- were **unanswerable from the repository**, not merely
unanswered.

The primitive's absence was cited by name in M073's, M074's *and* M075's own
frozen text. M075's own docstring states it plainly: *"this repository has no
durable position state."*

Eight candidates were ranked against six weighted criteria. Durable
cross-day position state scored 25; portfolio-aware daily capital awareness
19; explainability 21; data-quality fallback 18; scheduling 17; alerting 16;
P&L state 16; paper trading and execution simulation 12. The ranking is not
merely arithmetic: portfolio-aware daily capital **cannot be built without**
durable state, because it is M075 plus prior exposure and prior exposure is
exactly what did not exist; and P&L, paper trading and execution simulation
all sit downstream of it and score badly on honesty risk precisely because,
without a recorded operator action, any fill or P&L claim would be
fabricated.

## The Central Boundary

**An approved `PositionPlan` is a recommendation, not an action.** Deriving
positions from plans would fabricate holdings the operator never took. This
is the single honesty constraint the whole milestone is built around. Only an
explicit operator assertion creates a position; a cited plan is
informational, optional, and never changes the fold.

## Delivered Capability

An operator-asserted, event-sourced position ledger. The operator explicitly
records what they did; the platform derives what is held as of any timestamp
by folding those events in a total order. Nothing is ever inferred from a
recommendation.

`OPENED`, `REDUCED` and `CLOSED` events append to `operator_position_event`.
`derive_position_state(as_of)` folds the events whose `event_timestamp` is at
or before an inclusive `as_of` and reports quantity, asserted entry price and
`asserted_open_notional`. A `CLOSED` event's quantity is **derived from the
open quantity, never supplied**, so it cannot disagree with the ledger.

## Implementation Evidence

- **Source:** one new pure module,
  `decision_candidate/operator_position_ledger.py`; a repository protocol;
  one PostgreSQL adapter; one usecase; two CLI entrypoints.
- **Schema:** one additive table, `operator_position_event`, created by
  migration `b7e1c4a95d38` on the verified head `31365632c016`, with
  `asserted_price NUMERIC(20, 6)`, `TIMESTAMPTZ` columns, a UNIQUE constraint
  on `governance_id`, four CHECK constraints and two indexes. `downgrade()`
  is real and up -> down -> up is a named test. The table is **append-only in
  practice**: the adapter issues only `INSERT` and `SELECT`, never `UPDATE`
  or `DELETE`.
- **Additive only:** two pre-existing files were touched and both diffs are
  **provably additive with zero deleted lines**. `PositionPlan` is untouched
  and never read.
- **Tests:** 53 pure unit tests and 16 real-PostgreSQL integration tests,
  including four genuine concurrency attacks.

## Owner Review Correction Passes

Two owner review passes returned **four blocking correctness findings. All
four were real, and all four are recorded here rather than quietly fixed.**
The detailed record is `external-review/MILESTONE-076/owner-correction-pass.md`.

### Finding 1 - validation/append concurrency race

**Found by my own hostile review, and then argued away by it.** Attack 48 of
the implementation review, and design-review item D11 before it,
dispositioned this race as `ACCEPTED AND DOCUMENTED` on the reasoning that
this is a single-operator CLI primitive. **That reasoning was wrong.** A
ledger whose invariant two ordinary writers can break does not have that
invariant, and documenting a race is not a fix for a durable ledger.

`handle()` performed `list_all` -> `validate` -> `append` across separate
transactions, so two writers could read the same open quantity, both
validate, and both persist a sequence the canonical fold rejects.

**Corrected architecturally, not by documentation.** The repository contract
no longer exposes an unvalidated `append`. `append_validated` is one
transaction: `pg_advisory_xact_lock(hashtext(...))` keyed on the *position
governance id*, then re-read that key's committed events, then pure domain
validation, then insert. The lock is transaction-scoped, so it releases on
commit or rollback, and it is keyed per position, so writers to different
positions never contend.

Four real concurrency attacks prove it, each with its own runtime and
connection and a `threading.Barrier` so the writes genuinely collide:

| Attack | Result |
|---|---|
| open 10, two concurrent `REDUCED(6)` | exactly one wins; the other is rejected `REDUCTION_EXCEEDS_OPEN_QUANTITY` after seeing committed state; 2 rows; final fold = 4 |
| two concurrent `OPENED` on one position | one wins; the other `POSITION_ALREADY_OPEN`; 1 row |
| two concurrent identical event ids | exactly one row persists |
| concurrent writes to **different** positions | **both succeed** -- the fix did not serialise the ledger |

### Finding 2 - timezone invariant missing

`event_timestamp`, `recorded_at` and `as_of` were not required to be
timezone-aware, so a naive datetime could reach a `TIMESTAMPTZ` column with
an assumed zone. They are now rejected as `NAIVE_TIMESTAMP` at the domain
boundary. Inclusive `as_of` semantics are unchanged. Verified at the domain
boundary, through PostgreSQL, and with two offsets representing one instant
folding identically at the exact boundary and one microsecond before it.

### Finding 3 - Decimal / NUMERIC(20,6) scale mismatch

`Decimal("1.1234567")` would have been accepted, silently rounded on write,
and reloaded as a *different* value. `ASSERTED_PRICE_MAX_DECIMAL_PLACES = 6`
is now a domain invariant and the domain **rejects** beyond it rather than
quantizing, because silently altering a number the operator asserted is
itself a small dishonesty. Positivity became a domain invariant rather than
only a database CHECK.

### Finding 4 - total precision unbounded

Finding 3 bounded the **scale** and never the **total precision**.
`NUMERIC(20, 6)` bounds both: twenty total digits, hence at most **fourteen
digits left of the point**. `Decimal("100000000000000")` therefore passed
every domain check and was refused by PostgreSQL with `numeric field
overflow`. That broke M076's own claim that an accepted asserted price
round-trips deterministically, because a value that cannot be stored cannot
round-trip at all.

**The earlier "maximum precision" test used only eleven integer digits, so it
never probed the real ceiling. The test was weaker than the claim it was
written to defend** -- which is why the gap survived a 49-attack review.

`ASSERTED_PRICE_MAX_INTEGER_DIGITS = 14` is now enforced in the domain.
`ASSERTED_PRICE_PRECISION_EXCEEDED` covers both halves of one invariant --
*exactly representable by the persisted column* -- with a detail message
naming which bound was crossed; one reason rather than two, because the rule
is single. **Nothing is clamped and nothing is rounded: the value is
refused.**

| Attack | Result |
|---|---|
| `99999999999999.999999`, the column's exact ceiling | accepted |
| `99999999999999`, `0.000001` | accepted |
| `100000000000000` | rejected in-domain; row count proven to stay at 0 |
| `100000000000000.5`, `999999999999999`, `1E+15` | rejected in-domain |
| `1.1234567` | still rejected |
| zero, negative | still rejected |
| PostgreSQL round-trip of the ceiling value | exact -- `Decimal` equality, full object equality and raw-SQL equality |
| in-memory versus reloaded rendering | identical |

The honesty banner is **byte-identical** across both correction passes,
verified by diff, and the ledger module diff is **purely additive with zero
deleted lines**.

## Canonical Results

| Environment | Result |
|---|---|
| M076 unit | 53 passed |
| M076 PostgreSQL integration | 16 passed |
| M070-M076 focused integration | 38 passed, 5 skipped, 6 pre-existing M074 failures |
| M076 PostgreSQL integration, pass 2, new database | 16 passed |

**Regression measured against an identical baseline** -- same clone
semantics, same PostgreSQL instance, integration enabled:

| Head | PostgreSQL off | PostgreSQL on |
|---|---|---|
| `master` `92ff472` | 8 failed, 1869 passed, 12 errors | 24 failed, 2168 passed, 44 errors |
| M076 branch | 8 failed, **1922** passed, 12 errors | 24 failed, **2237** passed, 44 errors |

Identical failure and error counts, **+53 and +69 passing tests, and zero
regressions.** The regression claim does not rest on counts matching: the
sorted lists of failing test ids were diffed and are **identical**, so no test
that passed on the baseline fails here and no failure was swapped for another.
No M075 or M076 test appears in the failing set at all.

The 8/24 failures and 12/44 errors are the pre-existing M062/M064/M065 CRLF
seal debt, untouched here and invisible on the `windows-latest` CI runner. The
six M074 failures inside the M070-M076 focused set belong to that same debt --
M074's fixtures depend on the M064 seals -- and each one is present, identically,
on the `92ff472` baseline.

**Measurement provenance.** Both rows were re-measured at freeze time in one
environment against one PostgreSQL instance, the baseline by checking `92ff472`
out in the same working tree rather than by quoting an earlier run. An initial
freeze-time measurement read 26 failures; the cause was traced to this
environment's database password having been set to a string that is also a
substring of the database user and database name, which made
`test_repr_does_not_expose_real_credentials` report a leak that does not exist.
That was a defect in the measurement environment, not in the repository. The
password was changed and both rows above were then measured cleanly.

## Genuine Defects Found and Fixed

Beyond the four owner findings, four defects were found and fixed during
construction. Two are worth recording because of what they say about the
tests:

1. **I broke 74 passing tests.** `OperatorPositionEventId` was appended
   between `ResearchSessionId`'s docstring and its `prefix = "RESEARCH"`, so
   `ResearchSessionId` silently inherited the empty base prefix and the new
   class took `RESEARCH` for itself. The full regression caught it -- 82
   failures against a measured baseline of 8. Fixed by restoring from
   `master` and appending at end of file, plus a registry-wide regression
   test so the whole identifier registry is now asserted rather than assumed.
2. **`LedgerRejectionError` was unraisable.** `@dataclass(frozen=True,
   slots=True)` over `Exception` rebuilds the class and breaks `super()`
   resolution, so raising it produced a `TypeError`. **The unit tests missed
   it and the integration tests exposed it** -- a direct argument for the
   integration layer existing at all. Fixed to a plain exception.
3. **Money strings depended on the database scale**, rendering `750.000000`
   after reload against `750` in memory. Fixed with canonical `_money()`
   formatting so rendering is scale-independent.
4. **The CLI violated the architecture boundary** by importing
   `decision_candidate` from `entrypoints`. The architecture checker caught
   it; construction and rendering moved into the usecase layer.

## Adversarial Review

A pre-implementation hostile design review of **23 attacks** (D01-D23)
corrected five defects before a line of code was written, including the
sharpest one: **a back-dated event inserted after later events would corrupt
history.** Validation therefore does not check "state at this event's
timestamp"; it **re-folds the entire resulting sequence for that position key
in timestamp order and rejects if any transition becomes invalid.**

`external-review/MILESTONE-076/hostile-implementation-review.md` records the
implementation pass: **49 attacks** across architecture, frozen-contract
preservation, determinism, ledger arithmetic, temporal semantics, absence and
malformed states, CLI, claim honesty, security and packaging.

**That review's verdict on attack 48 was wrong, and it is retracted in place
in the matrix rather than quietly edited away**, so the record shows both the
mistaken disposition and its retraction. A review that accepts a real defect
is itself evidence about the review.

## Fresh Second Verification Pass

Same agent, so not an independent review. A brand-new database created empty,
the full migration chain applied from scratch, and the M076 integration suite
reproduced 16/16.

## Temporal and State Semantics

M076 introduces `OPERATOR_ASSERTED_POSITION_STATE_AT(t)`: a deterministic
fold over an append-only event ledger, filtered to `event_timestamp <= as_of`
and ordered totally by `(event_timestamp, governance_id)`. `recorded_at` is
audit metadata and never enters the fold, so when an event was *typed* cannot
change what was *held*. There is no future-data channel: a query about the
past cannot see later rows, and the CLI states how many events were excluded.

This is distinct from `STATE_AT(t)` over campaign aggregates, from
`EVENT_AFTER(t)`, from M074's `HISTORICAL_EVIDENCE_AVAILABLE_AT(t)`, and from
M075's `RECOMMENDATION_SET_FEASIBILITY_AT(t)`. It is emphatically **not**
M067/M068 historical portfolio replay: different module, different table,
different vocabulary, and a banner that names the distinction.

## Frozen Preservation

No M057-M075 source file's semantics change. The two pre-existing files
touched are provably additive with zero deleted lines. M075 is entirely
untouched -- neither read nor modified -- and wiring the ledger into M075's
same-day capital feasibility is a deliberate non-goal, because it would
change M075's frozen meaning. That is M077's job. M074 and the M063
exceptional byte-seal reconciliation record are unchanged.

## M062 / M064 / M065 Seal Debt - Not Repaired

M076 introduces no fixture, no dataset bundle and no byte seal; its tests
construct typed domain objects in memory and it reads no file whose bytes are
hashed. The debt therefore does not block M076's capability, tests, CI, or
reproducibility, and was deliberately left alone. It continues to warrant its
own authorization.

## Claim Honesty

M076 makes no claim of profitability, live-trading readiness, broker
readiness, order execution, fills, realistic execution, or investment advice.
Every value in the ledger is **what the operator said**, not what a broker
confirmed: there is no broker, no confirmation and no reconciliation. The
vocabulary is deliberately `operator-asserted`, never `executed`, `filled` or
`live`, and a forbidden-vocabulary test enforces that over both the module
and the rendered output. `asserted_open_notional` is quantity times the
asserted entry price and nothing revalues it; it is explicitly neither a
market value nor a P&L.

## Owner Approval

All phases of the M076 mission specification are complete: repository truth
independently verified; the premise that durable position state was the
highest-leverage gap attacked rather than assumed, and proven against
forty-three tables and seven unanswerable questions; eight candidates ranked;
a design that survived a 23-attack review with five pre-implementation
corrections; implementation on one additive table with a reversible
migration; 69 tests including four real concurrency attacks; a 49-attack
implementation review; a fresh second pass on a new database; a full
regression proving zero new failures against a measured baseline; and **two
owner review passes that found four real correctness defects, all corrected
architecturally and all recorded rather than tidied away.**

**Freeze declaration:** `M076 MACRO MILESTONE APPROVED_AND_FROZEN`.
`M076 APPROVED_AND_FROZEN`.

## Deferred / M076 Boundary

Explicitly out of scope and not built: consumption of the ledger by M075's
same-day capital feasibility; cross-day exposure reporting in the daily
brief; P&L; market valuation; cash ledger; margin; leverage; fills;
execution simulation; paper trading; live trading; broker integration;
reconciliation; symbol validation against `instrument_master`; scheduling;
any repair of the M062/M064/M065 seal debt. **MILESTONE-077 was explicitly
NOT built.**

## Next Permitted Action

MILESTONE-077 -- recommendation only; not started as part of M076.
