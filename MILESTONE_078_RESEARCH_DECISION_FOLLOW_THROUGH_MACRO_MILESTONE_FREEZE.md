# MILESTONE-078 - Research Decision Follow-Through Audit - Macro Milestone Freeze

## Status: FINAL - OWNER FROZEN

## Repository Authority

Repository `C:\Users\LuxSy\Documents\trading`, branch `master`. M078 baseline
`183401efae221ecfea4cbb3837e79d045721f174` (the M077 Owner Freeze
hash-recording HEAD; M077 fully `APPROVED_AND_FROZEN`), independently
re-verified from git at mission start rather than taken from the mission
text. Delivered through pull request #8, owner-approved at head
`fc7ac90802c5dda35f1a3fe357da71a3bd6ebac3` with the `foundation` workflow
green on that exact SHA, and merged into `master` as
`565b7ebf072d821e4b5d375a9de28c4b246bdc4e`.

The pull request was merged with a true merge commit. **All three commits are
preserved and none was squashed away:** the implementation
`2c14d0a9f745980a31c0b0b46a957124b2b4cff3`, the owner correction
`110fc3b43bad1b997e59511f9cfe50ec8b059768`, and the evidence reconciliation
`fc7ac90802c5dda35f1a3fe357da71a3bd6ebac3`.

Scope, the proved gap, five ranked candidates, semantics, non-goals and the
pre-implementation adversarial design review are recorded in
`MILESTONE_078_RESEARCH_DECISION_FOLLOW_THROUGH_SCOPE_AND_DESIGN.md`.

## Why M078 Exists

M076 records what the operator asserts they hold. M077 charges that exposure
against today's proposals. **Neither closes the loop back to the research.**

Plan lineage already existed: an `OPENED` event may cite the position plan the
operator says it came from. A repository-wide search showed it was consumed in
exactly **two** ways -- M077's double-counting suppression, over positions open
at `as_of`, for the session being briefed today only; and display of a single
held position's cited plan. **Nothing joined a session's approved plans to the
ledger.**

So no one could ask what became of what the research recommended, or what is
held that the research never proposed. An asserted position citing no plan is
the platform's only detectable signal of an unplanned, undocumented position,
and nothing surfaced it.

## A Contradiction in the Frozen Record, Documented Rather Than Reconciled

M077's freeze record states that decision-versus-outcome evaluation was
deferred because it "requires an outcome, which requires either market
revaluation or realized proceeds, and **M076 asserts neither**."

**The second half is inaccurate, and the code is the authority.** M076
validates and persists an `asserted_price` on *every* event kind, including
`CLOSED` and `REDUCED` (`operator_position_ledger.py:136,160-186`), so operator-
asserted exit prices already exist. What is true is that nothing reads them:
the fold returns `(quantity, is_open, opening_event)` and the notional uses
`opening.asserted_price` alone (`:340,:422`).

M077's frozen document is **not edited**. The correction is recorded here and
in M078's design document, because it changes what M078 could have been.

## Why This Capability and Not the Outcome One

Round-trip outcome evaluation is therefore **technically available** and was
still rejected -- **on honesty rather than feasibility.** Subtracting an
asserted entry from an asserted exit produces a number that is substantively
**realized P&L**, and renaming it would be the exact failure the reality gate
forbids: no disclaimer may rescue misleading semantics. It would also be the
first profit-shaped number the platform has ever emitted, which is a decision
for the owner to authorize explicitly rather than for a mission to take
unilaterally. **It remains unblocked and is the owner's next explicit choice.**

## Delivered Capability

A read-only follow-through audit for one research session, as of an explicit
timestamp. For every approved position plan, whether an operator-asserted
position citing it is open, is closed, or **was never recorded**; and
separately, the operator's open asserted positions that this session's plans do
not account for.

## The Strongest Property: M078 Computes No Money

**M078 emits no monetary value of any kind** -- no price, notional, valuation,
proceeds or difference. It reports statuses, counts, quantities and identifiers
only.

This is structural, not conventional: accidental P&L, accidental valuation and
accidental profitability claims are **impossible** when no arithmetic over
prices is performed. A test walks every field of every returned dataclass and
rejects any `Decimal` or money-named field, and the integration suites persist
asserted prices of `110`, `123.456789`, `291.6375`, `415.999999`, `150.125` and
`99.999999` and prove that **none of them reaches any rendering**.

## The Most Important Word

`NO_ASSERTED_POSITION_RECORDED` means **nothing was written down** citing that
plan. It does **not** mean the operator ignored it, rejected it, or failed to
act. The ledger records assertions, not conduct, and its silence is not
evidence about what a human did.

The first draft called this `NOT_ACTED_UPON`, which asserts conduct the data
cannot support. There is deliberately no `FOLLOWED` / `ADHERENCE` /
`COMPLIANCE` vocabulary anywhere, enforced by test, and the caveat is emitted
unconditionally in both renderings.

## Owner Review Correction: the Join Authority Must Be an Identity

Owner review of `2c14d0a` returned one blocking authority/identity finding.
**It was real, and it superseded my own earlier fix.** The detailed record is
`external-review/MILESTONE-078/owner-correction-pass.md`.

M078 joins on `position_plan_governance_id`, but the frozen M070 domain does
not prove that field is non-blank or uniquely mapped:
`ResearchDecisionEntry.__post_init__` validates `instrument_symbol`,
`decision_candidate_governance_id`, `scan_decision` and `rank` -- and **not**
the plan id.

### Why the first correction was insufficient

Implementation review R02 found that a duplicate plan id silently discarded an
entry, and fixed it by deduplicating deterministically and emitting a
limitation. **That is deterministic but not semantically safe.** When `PLAN-X`
names both `AAPL` and `TSLA`, a ledger event citing `PLAN-X` refers to *neither
in particular*, and keeping `AAPL` because it sorts first **invents an answer
the session data does not contain** -- then reports statuses, counts and
unlinked classifications built on that invention. A warning beside a fabricated
join does not make the join honest.

**R02's disposition is retracted in place, not deleted**, as is design attack
D03, which asked only whether duplicates produce duplicate entries and never
whether the id is a usable *identity* -- which is exactly why it missed the
defect. The unit test that asserted the weaker behaviour is corrected in place
with its old assertion preserved in the docstring.

### The rule now enforced

Plan references are validated **before any lineage is read** and **before the
ledger checks**, so an incoherent session reports the same reason whatever the
ledger is doing. Disqualifying, and neither resolvable by choosing a winner:

- a **blank or whitespace-only** governance id -- not an identifier at all;
- **one non-blank id carrying conflicting instrument identity**.

Either yields `NOT_ASSESSABLE` with
`SESSION_PLAN_REFERENCES_INCOHERENT`. The withheld result fabricates nothing:
`entries` and `unlinked_open_positions` are empty and every count, including
`approved_plan_count`, is zero.

- A **`rank` divergence is presentation metadata, not identity ambiguity.**
  With the same id and the same instrument the join is unambiguous, so the
  audit proceeds and the divergence is reported. Withholding on rank would
  refuse an answerable question.
- **Exact identical duplicates** (same id, instrument and rank) are
  deterministically deduplicated and the count is **reported**, never hidden.

### What the persistence layer actually does

Proven against real PostgreSQL rather than assumed:

| Malformed form | PostgreSQL | Proof |
|---|---|---|
| blank plan id | **rejected** -- the frozen M070 schema declares the column a FOREIGN KEY to `position_plan`, and `''` matches no row | `test_m078_postgresql_rejects_a_blank_plan_reference_at_the_foreign_key` |
| one plan id across two instruments | **permitted** -- the foreign key constrains the id, not the pairing | `test_m078_postgresql_permits_one_plan_id_across_two_instruments` |

The domain guard for the blank case is **retained anyway**: M078's read
boundary must not depend on a constraint owned by another milestone's table.

## Temporal Semantics, and the Limitation That Must Not Be Strengthened

M078 introduces `FOLLOW_THROUGH_OBSERVED_AT(t)`: a pure function of this
session's approved plans and the ledger folded at `t`. `as_of` is **required**
and inclusive -- there is deliberately no default, because the answer depends
entirely on the window and the obvious default, the session's own `as_of`, is
the one window guaranteed to show nothing.

**M078 is an EFFECTIVE-TIME audit, not a point-in-time one.** M076 defines
`event_timestamp` as when the operator says the event happened and
`recorded_at` as when the assertion was written down, and **only
`event_timestamp` drives the fold**. M078 inherits that unchanged.

The consequence, stated plainly and **not strengthened by this freeze**:

- a later **backfilled** assertion can change the answer for an earlier
  `as_of`;
- **M078 does NOT prove what information or evidence was available to the
  system at historical time `t`** -- it reports what the ledger *now* says
  about `t`;
- it **must NOT be treated as historical evidence-availability or
  forward-evaluation proof without a future `recorded_at` firewall**, because
  doing so is a look-ahead leak that would credit the system with knowledge it
  did not have.

This documents existing frozen M076 semantics. **No M076 or M078 code was
changed to address it**, and doing so would be a separate, explicitly
authorized milestone.

Distinct from `STATE_AT(t)`, `EVENT_AFTER(t)`, M074's
`HISTORICAL_EVIDENCE_AVAILABLE_AT(t)`, M075's
`RECOMMENDATION_SET_FEASIBILITY_AT(t)`, M076's
`OPERATOR_ASSERTED_POSITION_STATE_AT(t)` and M077's
`PORTFOLIO_AWARE_FEASIBILITY_AT(t)`.

## Implementation Evidence

- **Source:** one new pure, I/O-free module,
  `decision_candidate/research_decision_follow_through.py`; one usecase; one
  renderer; one CLI entrypoint and its registered console script.
- **Zero new PostgreSQL table, zero new migration, zero new repository.**
- **Read-only** with respect to M070 and M076, through their frozen public
  contracts. M076 is **not modified** to expose lineage: it is projected from
  the same event tuple already read, and M076's fold remains the sole authority
  on open versus closed.
- The M072 daily brief is **untouched** -- follow-through is a question about
  the past, not about today.

## Canonical Results

| Environment | Result |
|---|---|
| M078 unit | 54 passed |
| M078 PostgreSQL integration | 15 passed |
| M078 focused total | 69 passed |
| M078 PostgreSQL, fresh second pass, new database | 3 passed |
| M070-M078 focused integration | 77 passed, 5 skipped, 6 pre-existing M074 seal-debt failures |

**Regression measured against an identical baseline** -- same working tree,
same PostgreSQL instance, integration enabled:

| Head | PostgreSQL off | PostgreSQL on |
|---|---|---|
| `master` `183401e` | 8 failed, 1975 passed, 12 errors | 24 failed, 2311 passed, 44 errors |
| M078 branch | 8 failed, **2029** passed, 12 errors | 24 failed, **2383** passed, 44 errors |

Identical failure and error counts, and **zero regressions**. The claim does
not rest on the counts: the sorted failing-test-id lists were **diffed and are
identical**, so no test that passed on the baseline fails here and no failure
was swapped for another. No M075, M076, M077 or M078 test appears in the
failing set. The 8/24 failures and 12/44 errors are the pre-existing
M062/M064/M065 CRLF seal debt.

**No gate was suppressed to go green.** The module carries zero `type: ignore`
and zero `noqa`. Two drafts required suppressions -- a `**dict` splat in the
usecase and a complexity `noqa` -- and both were removed by restructuring the
code rather than by silencing the checker.

## Adversarial Review

A pre-implementation hostile design review of **79 attacks** corrected **22
defects** before a line of code was written, including a draft that would have
added a section to the frozen M072 brief and a draft whose vocabulary judged
the operator.

The implementation pass catalogued **104 attacks** and found **three genuine
defects, every one by executing the code rather than reading it**. The unit
suite passed 38/38 on its first run; that was evidence the tests were not yet
pointed at the right places, not evidence of correctness.

1. A position recorded on `TSLA` citing an `AAPL` plan was silently counted as
   follow-through, asserting a position against an instrument the operator
   never recorded one on.
2. One plan id naming two instruments silently discarded an entry.
3. A naive `as_of` was reported as `LEDGER_INCOHERENT` -- telling the operator
   their persisted data is corrupt when their *request* was malformed. **A
   false diagnosis is worse than a crash.**

Each is fixed with a regression test that fails against the pre-fix code. Two
review verdicts -- implementation R02 and design D03 -- are **retracted in
place** following owner review, with the reason each was too narrow recorded
beside them.

## Fresh Second Verification Pass

Same agent, so not an independent review. A brand-new database created empty,
the full migration chain applied from scratch, and deliberately different
inputs throughout -- different session ids, different symbols, a shifted
breakout fixture placing the event on day 13, a different `as_of`, different
quantities, prices carrying six decimal places and a different capital base:
3/3.

## Concurrency

M078 reads while M076 may be writing. `list_all()` is a single `SELECT` inside
one transaction, so under `READ COMMITTED` it observes one consistent snapshot;
M076 commits each position's event atomically under a per-position advisory
lock. No additional locking is required, proven by a barrier-synchronised
writer/reader race rather than asserted. A further named test proves **M077 and
M078 do not contradict each other** over the same ledger.

## Frozen Preservation

No M057-M077 source file's semantics change. M070's `ResearchSession` is **not
modified** -- M078 defends its own read boundary against malformed persisted
session data rather than tightening a frozen aggregate. MILESTONE-075,
MILESTONE-076 and MILESTONE-077 are neither modified nor re-interpreted.
MILESTONE-074 and the M063 exceptional byte-seal reconciliation record are
untouched. No migration is added or changed.

## M062 / M064 / M065 Seal Debt - Not Repaired

M078 introduces no fixture, no dataset bundle and no byte seal; its tests
construct typed domain objects in memory and it reads no file whose bytes are
hashed. The debt therefore does not block M078's capability, tests, CI, or
reproducibility, and was deliberately left alone. It continues to warrant its
own authorization.

## Claim Honesty

M078 makes no claim of profitability, live-trading readiness, broker readiness,
order execution, fills, market valuation, realized or unrealized P&L, or
investment advice. It proves what the operator's ledger **records** against a
session's plans -- a statement about records, not about markets, money or
conduct. A parametrised test asserts that `EXECUTED`, `FILLED`, `VERIFIED`,
`REALIZED`, `PROFIT`, `PNL`, `FOLLOWED` and `ADHERENCE` appear nowhere in any
closed vocabulary.

## Owner Approval

All phases of the M078 mission specification are complete: repository truth
independently verified; a contradiction in M077's frozen record found and
documented rather than silently reconciled; the gap proved structurally; five
candidates ranked, with the highest-value one rejected on honesty and named as
the owner's next explicit choice; a design that survived 79 attacks with 22
pre-implementation corrections; a minimal additive implementation with zero new
schema; 69 focused tests including real-PostgreSQL evidence cross-checked
against raw SQL; a 104-attack implementation review that found three real
defects by execution; a fresh second pass on a new database; a full regression
proving zero new failures against a measured baseline; **one owner review pass
that found a real join-authority defect, corrected architecturally**; and an
evidence reconciliation pass that retracted the superseded conclusions in place.

**Freeze declaration:** `M078 MACRO MILESTONE APPROVED_AND_FROZEN`.
`M078 APPROVED_AND_FROZEN`.

## Deferred / M078 Boundary

Explicitly out of scope and not built: monetary values of any kind; realized or
unrealized P&L; round-trip outcome evaluation; profitability; valuation; market
prices; broker integration, confirmation or reconciliation; execution or fills;
judgement of operator conduct; causal claims; predictive or calibration claims;
a `recorded_at` evidence-availability firewall; modification of M070, M075,
M076 or M077; any new PostgreSQL table or migration; any repair of the
M062/M064/M065 seal debt. **MILESTONE-079 was explicitly NOT built.**

## Next Permitted Action

MILESTONE-079 -- recommendation only; not started as part of M078.
