# MILESTONE-079 - Operator Evidence Availability Snapshot - Macro Milestone Freeze

## Status: FINAL - OWNER FROZEN

## Repository Authority

Repository `C:\Users\LuxSy\Documents\trading`, branch `master`. M079 baseline
`5945e4effd48dfa97939bbd9448fa600503d4f89` (the M078 Owner Freeze
hash-recording HEAD; M078 fully `APPROVED_AND_FROZEN`), independently
re-verified from git and from `PROJECT_CHECKPOINT.md` at mission start rather
than taken from the mission text. Delivered through pull request #9,
owner-approved at head `007df59948401b29f1330614a8da2dd99f0f42ed` with the
`foundation` workflow green on that exact SHA, and merged into `master` as
`ac5de9404326c7920b7917cecdd574d219b9f7d4`.

The pull request was merged with a true merge commit. **All three commits are
preserved and none was squashed away:** the implementation
`2996730`, the external review evidence package
`21ed5ad693aa5d412d287bb7e38cced426616fab`, and the owner review correction
`007df59948401b29f1330614a8da2dd99f0f42ed`.

Scope, the proved gap, six ranked candidates, semantics, non-goals and the
pre-implementation adversarial design review are recorded in
`MILESTONE_079_OPERATOR_EVIDENCE_AVAILABILITY_SNAPSHOT_SCOPE_AND_DESIGN.md`.

## Why M079 Exists

M078's own frozen record named the missing piece. M078 is an EFFECTIVE-TIME
audit and "must NOT be treated as historical evidence-availability or
forward-evaluation proof without a future `recorded_at` firewall". **That
firewall did not exist.**

M076 persists two timestamps on every operator assertion: `event_timestamp`,
when the operator says the event happened, and `recorded_at`, when the
assertion says it was written down. Both are `TIMESTAMPTZ NOT NULL` and both
are validated timezone-aware (`operator_position_ledger.py:149`), and both are
`SELECT`ed and `INSERT`ed by the repository.

**`recorded_at` was never filtered on, never ordered on, and never read by any
derivation anywhere in the repository.** The fold's only temporal filter was
`event_timestamp <= as_of` (`:413`). So the platform already stored
knowledge-time and had no way to use it, and nothing could answer *"what did
the operator ledger actually record as of historical time t?"*

The consequence is a look-ahead leak. A position opened effective Aug 10 and
written into the ledger on Aug 12 was fully visible to an audit asking "as
known at Aug 10 16:00". Every forward-evaluation, calibration or
decision-versus-outcome analysis built on that would silently include
assertions recorded after the moment being evaluated - the hardest kind of
error to detect later, because the numbers look plausible.

## Why This Capability and Not the Outcome One

Six candidates were ranked across ten criteria. The evidence-availability
firewall won at 45, ahead of cross-session exposure evolution at 40 and
decision-versus-asserted-outcome evaluation at 37.

It is the **only candidate that is a strict prerequisite for three of the
others.** Outcome evaluation, forward observation and calibration all evaluate
a decision against later information, and each is unsafe until knowledge-time
filtering exists. Building any of them first would have baked the look-ahead
leak into the platform's first evaluation artifact.

Round-trip outcome evaluation remains rejected on **honesty rather than
feasibility**, exactly as M078 froze it: subtracting an asserted entry from an
asserted exit is substantively realized P&L, and it is the owner's call to
authorize. M079 makes it *technically safe* for the first time without making
it any more *authorized*.

## Delivered Capability

`OPERATOR_EVIDENCE_AVAILABLE_AT(E, K)`: a read-only, additive, point-in-time
snapshot reporting what the operator's ledger **records as having been recorded
by** knowledge cutoff `K`, about what it says happened by effective cutoff `E`.

Both cutoffs are required, inclusive, and must be timezone-aware. Neither has a
default, in the domain or in the CLI, because a default on either dimension
would silently choose an epistemic stance on the caller's behalf.

## Separation of Duties

M079 applies **exactly one filter**, `recorded_at <= K`, and hands the
survivors to M076's own `derive_position_state`, which applies the effective
filter and folds. M079 adds one dimension and delegates the other: **M076's
fold remains the sole authority on open versus closed, is not modified, and is
not re-implemented.** Setting `K` to the present reproduces M076's answer
exactly, and a named test asserts it.

## The Corrected Temporal Claim - Preserved Exactly

**M079 reports what the ledger RECORDS as having been recorded by knowledge
cutoff `K`. It does NOT prove what evidence was actually available at `K`,
because `recorded_at` is operator-supplied** and is not a system-assigned,
independently attested, immutable receipt time. An operator who back-dates
`recorded_at` defeats the firewall, and M079 cannot detect that.

**No assertion with `recorded_at > K` may influence:**

- state
- status
- reason
- counts
- limitations
- ordering
- classification

`UNRESOLVED_KNOWLEDGE_SEQUENCE` is the honest point-in-time refusal and must
remain so. **The retracted future discriminator must not be silently restored.**

## Owner Review Correction: the Classification Leaked Even Though No Value Did

Owner review of `21ed5ad` returned one blocking temporal-leak finding. **It was
real, and the leak was wider than the finding named.** The detailed record is
the "Owner review correction" section of
`external-review/MILESTONE-079/hostile-implementation-review.md`.

### The defect

Candidate evidence was filtered correctly with `recorded_at <= K`. But when the
knowledge-filtered sequence failed to fold, the implementation **re-folded the
same key against the UNFILTERED event set** to choose between
`INCOMPLETE_KNOWLEDGE_SEQUENCE` and `LEDGER_INCOHERENT_FOR_POSITION`. That set
can contain assertions with `recorded_at > K`, so **future knowledge decided
the status emitted at historical `K`**.

No position quantity was ever copied from that second fold. The design review
verified exactly that, and a test asserted it. **Verifying only that no VALUE
leaked is what made the defect invisible: nobody asked whether the
CLASSIFICATION leaked.** It did.

At `K` the system cannot know whether a sequence is merely truncated - a
`CLOSED` whose `OPENED` is recorded later - or genuinely incoherent. Claiming
to know it is a look-ahead leak regardless of how carefully the derived
quantity is withheld.

### Two further leaks the same rule exposes

Once the rule is stated properly, two fields fail it that **neither the design
review nor the implementation review had questioned at all**:

| Field | Why it leaked |
|---|---|
| `total_event_count` | `len(events)` over the whole ledger; grows with rows recorded after `K` |
| `excluded_by_knowledge_cutoff` | literally counts the rows the firewall hid - a direct readout of post-cutoff data |

The limitation string carrying that second count leaked with it.

### What replaced them

| Retracted | Frozen |
|---|---|
| `INCOMPLETE_KNOWLEDGE_SEQUENCE` + `LEDGER_INCOHERENT_FOR_POSITION` | one `UNRESOLVED_KNOWLEDGE_SEQUENCE` |
| `incomplete_knowledge_count`, `incoherent_position_count` | `unresolved_position_count` |
| `total_event_count` | `known_event_count` - assertions recorded **by** `K` |
| `excluded_by_knowledge_cutoff` | removed; a static limitation states why no such count can exist |
| `excluded_by_effective_cutoff` | **kept** - computed only from evidence recorded by `K`, so it does not leak |

`UNRESOLVED_KNOWLEDGE_SEQUENCE` means exactly: *the evidence recorded by this
cutoff does not form a coherent fold, and from that evidence alone it cannot be
known whether this is temporary incompleteness or underlying ledger
incoherence.* M076's own rejection reason for the **filtered** fold is still
reported, because it is derived from visible evidence and is leak-free - so two
differently-broken keys share the status while keeping distinct reasons.

Temporal evolution stays legitimate. A query at a later `K2` may fold
successfully, or may remain unresolved. **Neither reaches back and strengthens
the answer at `K`**, and a test asserts it.

### The guarantee is structural, not disciplinary

The first candidate **stated** this guarantee and then broke it three fields
later, so restating it would not have been a fix.

All snapshot logic now lives in
`_snapshot_from_known_evidence(known, effective_as_of, knowledge_as_of)`, which
is **never given the unfiltered events**. A post-cutoff row is not merely
unused there - it is unreachable. `build_operator_evidence_snapshot` reads
`events` exactly once, through `events_known_by`, and passes on only the
survivors. A test asserts this against the function's own signature and source,
so a future refactor that reintroduces the unfiltered set fails loudly rather
than silently.

### Retractions preserved, not erased

The superseded conclusions are marked **RETRACTED in place** with their
originals preserved verbatim: design review T07 (the discriminator), C05
(partially - the knowledge-cutoff count only) and K03, the reality gate's
safeguard paragraph, the original validation results, and the mission report's
own claim that the discriminator was "load-bearing", which was exactly
backwards. **This freeze does not rewrite the original incorrect decision out
of history.**

## A Cost Worth Recording

M079 makes the platform's answers **less** convenient on purpose, and the owner
correction made them less convenient still:

1. An operator can no longer be told whether an unresolved gap is likely to
   close.
2. The snapshot can no longer report how many assertions it hid, because
   counting them requires reading them. The limitation says so explicitly
   rather than omitting the number silently.

Both are removals of information the system could not honestly have at `K`.

## The Honesty Boundary

M079 emits **no monetary value, no valuation, no P&L and no verification
claim**. `KNOWN` means known **to the ledger** by `K` - not known to be true.
Asserted prices and notionals are M076's own figures carried through unchanged
and never revalued. The banner states what the snapshot is not: not
broker-verified, not execution, not fills, not actual holdings, not a market
valuation, not realized or unrealized P&L, not a profitability claim, not a
causal claim, not advice.

`NO_EVIDENCE_RECORDED_BY_KNOWLEDGE_CUTOFF` means the ledger was silent at that
moment. It does **not** mean nothing happened.

## Implementation Evidence

- **Source:** one new pure, I/O-free module,
  `decision_candidate/operator_evidence_availability.py`; one usecase; one
  renderer producing text and JSON from one object; one CLI entrypoint and its
  registered console script
  `empirical-platform-operator-evidence-snapshot`.
- **Zero new PostgreSQL table, zero new column, zero new migration, zero new
  repository.** The capability runs entirely on data M076 already persists.
- **Read-only.** No append path is reachable from the entrypoint.
- A database-level failure **propagates** rather than being disguised as a soft
  `LEDGER_UNAVAILABLE` verdict. Bad *data* is withheld honestly; a broken
  *database* is not.

## Temporal Vocabulary

`OPERATOR_EVIDENCE_AVAILABLE_AT(E, K)` is distinct from `STATE_AT(t)`,
`EVENT_AFTER(t)`, M074's `HISTORICAL_EVIDENCE_AVAILABLE_AT(t)`, M075's
`RECOMMENDATION_SET_FEASIBILITY_AT(t)`, M076's
`OPERATOR_ASSERTED_POSITION_STATE_AT(t)`, M077's
`PORTFOLIO_AWARE_FEASIBILITY_AT(t)` and M078's
`FOLLOW_THROUGH_OBSERVED_AT(t)`. It is the first two-dimensional temporal
predicate in the platform.

## Canonical Results

| Environment | Result |
|---|---|
| M079 unit | 57 passed |
| M079 PostgreSQL integration | 14 passed |
| M079 PostgreSQL, fresh second pass, new database | 4 passed |
| M076-M079 focused compatibility chain | 290 passed |

**Regression measured against an identical baseline** - same working tree, same
PostgreSQL instance:

| Head | PostgreSQL off | PostgreSQL on |
|---|---|---|
| `master` `5945e4e` | 8 failed, 1975 passed, 12 errors | 24 failed, 2383 passed, 44 errors |
| M079 first candidate `21ed5ad` | 8 failed, 2070 passed, 12 errors | 24 failed, 2438 passed, 44 errors |
| M079 corrected `007df59` | 8 failed, **2086** passed, 12 errors | 24 failed, **2458** passed, 44 errors |

Identical failure and error counts, and **zero regressions**. The claim does
not rest on the counts: the sorted failing-test-id lists were **diffed against
the baseline and are identical**, so no test that passed on the baseline fails
here and no failure was swapped for another. No M076, M077, M078 or M079 test
appears in the failing set. The 8/24 failures and 12/44 errors are the
pre-existing M062/M064/M065 CRLF seal debt.

**No gate was suppressed to go green.** The module carries zero `type: ignore`
and zero concealing `noqa`. A `**dict` splat in the usecase that would have
required a suppression was removed by restructuring into explicit typed
parameters.

## Adversarial Review

A pre-implementation hostile design review of **81 attacks** corrected **25
defects** before a line of code was written - including a first draft with a
single `as_of` serving both dimensions, a draft defaulting `knowledge_as_of` to
now, and a draft that re-implemented M076's fold instead of delegating to it.
**Two of its conclusions, T07 and C05, are retracted following owner review and
are recorded as retracted rather than removed.**

The implementation pass catalogued **126 attacks** and found **two genuine
defects, both by executing the code rather than reading it.** The unit suite
passed 37/37 on its first run; as in M078, that was evidence the tests were not
yet pointed at the right places.

1. **R01** - the `position is None` branch was unreachable dead code whose body
   was `continue`. Had a refactor ever broken the invariant, a position would
   have vanished from the snapshot with no entry, no count and no limitation
   recording the omission. `_fold_one_key` now returns non-optional and raises
   naming the invariant.
2. **R02** - the design review's own header overstated its attack count. Counts
   are now computed programmatically from the file.

The owner review correction pass added **20 further attacks**, catalogued
O01-O20, and found **three defects**: the discriminator and the two leaking
counts.

## The Two-Database Proof

The strongest evidence for the corrected claim, over real PostgreSQL rather
than in memory. A second physical database is **created empty and migrated from
scratch inside the test**; both ledgers are written through the **real M076
repository** and read through the real query handler.

| | DB-A | DB-B |
|---|---|---|
| Rows with `recorded_at <= K` | the `CLOSED`, identical in every column | the `CLOSED`, identical in every column |
| Rows after `K` | `OPENED` id `OPEV-7951`, price `100`, recorded `T3`, **plus an entire extra position** | `OPENED` id `OPEV-7999`, price `555`, recorded `T0+90d` |
| Total rows | 3 | 2 |

Raw SQL confirms the shared prefix is byte-identical and that the totals
differ. At `K = T2` the snapshots are equal as objects, their JSON is equal,
their text is equal, and both report `UNRESOLVED_KNOWLEDGE_SEQUENCE` with no
position state.

A companion test advances the cutoff to prove the two databases were genuinely
different all along: DB-A resolves to `KNOWN_CLOSED`, DB-B legitimately stays
unresolved, and re-querying at the original `K` still yields identical answers.

**One frozen M076 behaviour shaped this test and is recorded here rather than
worked around:** M076 *derives* a `CLOSED` event's quantity from the open
position rather than taking it as supplied
(`operator_position_ledger.py:126`), so both ledgers' openings must carry the
same quantity for the visible prefix to match. The post-cutoff tails differ by
governance id, asserted price and `recorded_at`. **M076 was not modified.**

## The Original Adversarial Timeline

The mandated `T1 < T2 < T3` case, with the `OPENED` **recorded last** and
inserted `CLOSED`-first so insertion order cannot be what makes it work:

| Knowledge cutoff | Result |
|---|---|
| `T1` | `NO_EVIDENCE_RECORDED_BY_KNOWLEDGE_CUTOFF` - the firewall holds |
| `T2` | the `CLOSED` is visible, its `OPENED` is not, so `UNRESOLVED_KNOWLEDGE_SEQUENCE` with no state invented |
| `T3` | `KNOWN_CLOSED` - the same key folds normally once knowledge advances |

Raw SQL independent of every repository helper confirms both timestamps read
back exactly and that
`WHERE event_timestamp <= :e AND recorded_at <= :k` agrees with the module's
`visible_event_count` at each cutoff.

## Fresh Second Verification Pass

Same agent, so not an independent review. A brand-new database created empty,
the full migration chain applied from scratch, and deliberately different
inputs throughout: different instruments (`SMCI`, `PLTR`, `COIN`, `ARM`),
different governance ids, different timestamps, prices at both ends of the
frozen `NUMERIC(20,6)` domain (`0.000001` and `99999999999999.999999`), and
**reversed insertion order** so ordering cannot be what makes the firewall
work. A further test appends post-cutoff assertions between two reads of the
same cutoff and proves the answer does not move: 4/4.

## Concurrency

M079 reads while M076 may be writing. `list_all()` is a single `SELECT` inside
one transaction, so under `READ COMMITTED` it observes one consistent snapshot.
No additional locking is required, proven by a barrier-synchronised
writer/reader race rather than asserted. A named test proves **M076 still sees
the backfill that M079 hides**, and that M076 is unchanged by having been
called through M079.

## Frozen Preservation

No M057-M078 source file's semantics change. `operator_position_ledger.py`
(M076), `same_day_capital_feasibility.py` (M075),
`portfolio_aware_capital_feasibility.py` (M077) and
`research_decision_follow_through.py` (M078) are **byte-identical across this
merge**, verified by diff rather than asserted. MILESTONE-075, MILESTONE-076,
MILESTONE-077 and MILESTONE-078 freeze records are neither modified nor
re-interpreted. MILESTONE-074 and the M063 exceptional byte-seal reconciliation
record are untouched. No migration is added or changed.

M078's frozen effective-time limitation is **not edited and not weakened**.
M079 supplies the firewall that limitation named as missing; it does not
retroactively change what M078 proves. M078 remains an effective-time audit.

## M062 / M064 / M065 Seal Debt - Not Repaired

M079 introduces no fixture, no dataset bundle and no byte seal; its tests
construct typed domain objects in memory and persist rows through the real M076
repository, and it reads no file whose bytes are hashed. The debt therefore
does not block M079's capability, tests, CI, or reproducibility, and was
deliberately left alone. It continues to warrant its own authorization.

## Known Limitations

Recorded in full in `external-review/MILESTONE-079/known-limitations.md`.
Fourteen items, of which the load-bearing ones are: `KNOWN` means known to the
ledger and not known to be true; a snapshot can be superseded by an assertion
recorded later, which is the reason the milestone exists; unfoldable evidence
is reported without diagnosis and nothing is inferred; `recorded_at` is
operator-supplied and back-dating defeats the firewall undetectably; no money
is derived; the snapshot cannot say how much it hid; and there is no index on
`recorded_at`, M079 filtering in memory through the existing `list_all()`
exactly as M077 and M078 do - a deliberate deferral, not an oversight.

## Claim Honesty

M079 makes no claim of profitability, live-trading readiness, broker readiness,
order execution, fills, market valuation, realized or unrealized P&L, or
investment advice. It proves what the operator's ledger **records as having
been recorded** by a knowledge cutoff - a statement about records of records,
not about markets, money or conduct.

## Owner Approval

All phases of the M079 mission specification are complete: repository truth
independently verified from git and the checkpoint rather than trusted from the
mission text; a fresh post-M078 gap analysis proving `recorded_at` was stored
and never read by any derivation; six candidates ranked, with the
highest-honesty-risk one again rejected and named as the owner's explicit
choice; a design that survived 81 attacks with 25 pre-implementation
corrections; a minimal additive implementation with zero new schema; focused
tests including real-PostgreSQL evidence cross-checked against raw SQL over the
mandated adversarial timeline; a 126-attack implementation review that found
two real defects by execution; a fresh second pass on a new database with
reversed insertion order; a full regression proving zero new failures against a
measured baseline by diffing failing-test-id lists; **one owner review pass
that found a real temporal leak in the milestone's own central safeguard,
corrected structurally rather than textually, together with two further leaking
fields neither review had questioned**; and a 20-attack correction pass
including a two-database PostgreSQL proof.

**Freeze declaration:** `M079 MACRO MILESTONE APPROVED_AND_FROZEN`.
`M079 APPROVED_AND_FROZEN`.

## Deferred / M079 Boundary

Explicitly out of scope and not built: monetary values of any kind; realized or
unrealized P&L; round-trip outcome evaluation; profitability; valuation; market
prices; broker integration, confirmation or reconciliation; execution or fills;
calibration or decision-effectiveness scoring; forward observation primitives;
cross-session exposure evolution; per-instrument concentration policy;
judgement of operator conduct; causal claims; predictive claims; any
system-assigned or independently attested receipt time; an index on
`recorded_at` or a query-side knowledge filter; modification of M070, M075,
M076, M077 or M078; any new PostgreSQL table, column or migration; any repair
of the M062/M064/M065 seal debt. **MILESTONE-080 was explicitly NOT built.**

## Next Permitted Action

MILESTONE-080 -- recommendation only; not started as part of M079.
