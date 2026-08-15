# M078 — Owner Review Correction Pass

Owner review of PR #8 at head `2c14d0a9f745980a31c0b0b46a957124b2b4cff3`
returned one blocking authority/identity finding. **It was real.**

## Finding — the join authority was never validated as an identity

M078 joins a session's approved plans to the M076 ledger on
`position_plan_governance_id`. The frozen M070 domain does **not** prove that
every persisted value of that field is non-blank, nor that one id maps to one
immutable plan reference within a session.

`ResearchDecisionEntry.__post_init__` validates `instrument_symbol`,
`decision_candidate_governance_id`, `scan_decision` and `rank` — and **not**
`position_plan_governance_id`.

### Why the first correction was insufficient

Implementation review R02 found that a duplicate plan id silently discarded an
entry, and fixed it by deduplicating deterministically and emitting a
limitation. **Owner review established that this is deterministic but not
semantically safe**, and the owner is right.

When `PLAN-X` names both `AAPL` and `TSLA`, a ledger event citing `PLAN-X`
refers to *neither in particular*. Keeping `AAPL` because it sorts first does
not resolve the ambiguity — **it invents an answer the session data does not
contain**, and then reports statuses, counts and unlinked classifications built
on that invention. A warning beside a fabricated join does not make the join
honest.

**R02's disposition is therefore superseded, not deleted.** It is retracted in
place in `hostile-implementation-review.md`, and the unit test that asserted
the weaker behaviour is corrected in place with the old assertion recorded in
its docstring.

## The identity rule now enforced

Before any lineage is read, the approved plan references must be usable as an
identity. If they are not, **no audit is performed at all**:

`FollowThroughOutcome.NOT_ASSESSABLE` with
`FollowThroughUnassessableReason.SESSION_PLAN_REFERENCES_INCOHERENT`.

Disqualifying conditions, neither resolvable by choosing a winner:

1. **A blank or whitespace-only governance id.** A blank string is not an
   identifier and cannot be joined to a citation.
2. **One non-blank id carrying conflicting authoritative identity** — currently
   a differing `instrument_symbol`.

The withheld result fabricates nothing: `entries`, `unlinked_open_positions`
are empty and every count, including `approved_plan_count`, is zero. The raw
reference count appears only in a limitation, stating explicitly that no plan
count can be given because every one would depend on the ambiguous join.

**The check runs before the ledger checks**, so an incoherent session reports
the same reason whatever the ledger is doing — the diagnosis never depends on
unrelated state. A named test asserts this for all three ledger conditions.

### `rank` — the explicit decision required by the owner

**A rank divergence is presentation metadata, not identity incoherence, and
does not withhold the audit.**

`rank` is the session's operator-facing priority for a decision. It is not part
of what a ledger citation refers to: if the same id carries the same
instrument, the citation is unambiguous regardless of how the session ordered
it. Withholding on rank would refuse to answer an answerable question.

It is still never hidden — the divergence is reported as a limitation naming
both ranks and stating that the deterministically first one orders the report
while the join is unaffected.

### Exact duplicates

An exact duplicate — same id, same instrument, same rank — is semantically
harmless to the join, because both references name the same plan with the same
authoritative identity. It is deduplicated deterministically and the count is
**reported**, never silently dropped.

## What the persistence layer actually does

Proven against real PostgreSQL rather than assumed:

| Malformed form | PostgreSQL | Proof |
|---|---|---|
| blank plan id | **rejected** — the frozen M070 schema declares `position_plan_governance_id` as a FOREIGN KEY to `position_plan`, and `''` matches no row | `test_m078_postgresql_rejects_a_blank_plan_reference_at_the_foreign_key` |
| one plan id across two instruments | **permitted** — the foreign key constrains the id, not the pairing | `test_m078_postgresql_permits_one_plan_id_across_two_instruments` |

The domain guard for the blank case is **retained anyway**. M078's read
boundary must not depend on a constraint owned by another milestone's table,
which could be altered without M078 knowing.

## Required attacks

| # | Attack | Result |
|---|---|---|
| A | blank plan id | `NOT_ASSESSABLE` / `SESSION_PLAN_REFERENCES_INCOHERENT` |
| B | whitespace-only id; and one blank among valid plans | same; a single unusable identity withholds the whole session |
| C | `PLAN-X/AAPL` + `PLAN-X/TSLA` | withheld; no arbitrary first plan; nothing fabricated; detected in either reference order |
| D | conflicting rank | **audited**, with the divergence reported — decision documented above |
| E | exact duplicate | deduplicated deterministically, count reported |
| F | ambiguous `PLAN-X` plus a ledger event citing `PLAN-X` | still withheld; the position does not leak out through the unlinked classification either |
| G | normal unique plans | unchanged |
| H | PostgreSQL | both halves proven above |
| I | text and JSON | both carry the same reason, empty entries, no money, no conduct claim |
| J | M075/M076/M077 | untouched; `git diff` shows no frozen file changed |

## Tests added

Twelve unit tests (attacks A–G, ordering-independence, precedence over the
ledger checks, and a no-money/no-conduct check on the withheld result) and
three PostgreSQL tests (attacks H and I). Two existing tests were corrected in
place rather than deleted.

## A note on one of my own test assertions

The first version of the attack-I test asserted that the string `profit` never
appears in the rendering. It failed — because the banner legitimately contains
*"NOT a profitability claim"*. The check was wrong, not the code: the
meaningful assertion is that the **denial** is present, and that is what it now
asserts.
