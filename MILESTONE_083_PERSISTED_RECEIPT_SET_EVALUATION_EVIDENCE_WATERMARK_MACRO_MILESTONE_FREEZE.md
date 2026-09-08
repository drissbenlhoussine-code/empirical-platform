# MILESTONE-083 - Persisted Receipt-Set Evaluation Evidence Watermark - Macro Milestone Freeze

## Status: FINAL - OWNER FROZEN

## Repository Authority

Branch `master`. M083 baseline `45016d7cb79381d9ff8f90a410f57d5a22473269` (the
M082 Owner Freeze hash-recording HEAD; M082 fully `APPROVED_AND_FROZEN`),
re-resolved from git and from `PROJECT_CHECKPOINT.md` immediately before the
merge rather than taken from the mission text. Delivered through pull request
#13, owner-conditionally-accepted at engineering head
`7291962054c27760dc69b35142371b8765d4cca2`, closed at documentation head
`49a7c9ff8860b9bbaa175431ecf604841d7a3b5b` with both `verify` runs green on that exact SHA
(`34220758592`, `34220761589`), and merged into `master` as
`3b841af8b1591ce274442c011f2590c19676e8a2`.

The pull request was merged with a **true merge commit** carrying two parents,
`45016d7` and `49a7c9f`. **All eight branch commits are preserved and none was
squashed away.** The sequence, from first implementation to owner closure:

| Commit | What it is |
|---|---|
| `a767370` | the primitive: migration, domain type, repository, usecases, entrypoints, first tests |
| `c75c14d` | CI coverage gate, an architecture-boundary violation, repaired authority JSON |
| `e53275e` | owner deep-closure review: REV-001 through REV-005 closed, extended attack campaigns |
| `a288352` | independent audit: corrected M083's own suppression-count claim |
| `2cadb91` | independent audit: stale status label in `scope-and-design.md` |
| `4a05e41` | quantified exhaustion campaign: four audit findings closed (AUD-001 through AUD-004) |
| `7291962` | quantified exhaustion campaign: three hostile passes and all measured results recorded |
| `49a7c9f` | owner-required evidence matrices: completion table and 29-file audit |

The active design is `external-review/MILESTONE-083/scope-and-design.md`. The
external review package is under `external-review/MILESTONE-083/`.

All evidence in this record - including every PostgreSQL result - was executed in
a Linux container against a real PostgreSQL 16.13 server, not simulated.

## The Authority Is Not Stated In Prose

M083's authority is stated **once**, machine-readably, in
`external-review/MILESTONE-083/current-authority.json`, validated against the
committed closed schema `current-authority.schema.json`, and rendered
deterministically to `current-authority.md` by `tools/render_m083_authority.py`.
The renderer maps closed identifiers to fixed sentences and interprets no prose.
`--check` fails if the committed document is not the byte-exact rendering.

The schema uses `const`, closed `enum`, exact item counts and
`additionalProperties: false` at every object boundary. An unknown claim
identifier is therefore **unrepresentable**, not merely discouraged. The
quantified exhaustion campaign additionally closed the reverse direction: the
schema's own enum membership is now pinned to the approved sets, so neither the
contract nor the schema can be widened alone (audit finding AUD-002).

This freeze record is prose. Where this document and
`current-authority.json` could ever be read as differing, **the JSON governs.**

## A. What A Persisted Watermark Proves - Five Bounded Claims

1. `stable_watermark_governance_identity` - the row binds one stable,
   caller-supplied watermark governance identity.
2. `exact_receipt_governance_id_set_visible_to_capture_statement_snapshot` -
   the stored set is EXACTLY the `receipt_governance_id` values that were
   visible to the schema-qualified capture query executed by the INSERT
   statement that created the row, under **that statement's own transaction
   snapshot**.
3. `canonical_deterministic_storage_order` - stored once in ascending
   `COLLATE "C"` byte order, deterministic and independent of the database's
   default collation.
4. `stored_set_stable_against_later_receipt_activity` - a later receipt
   insertion, including a backdated one, does not recalculate an existing
   watermark, and a read returns the STORED set, never a re-derivation from
   the current receipt inventory.
5. `row_level_update_delete_refused_while_installed_trigger_is_active` -
   ordinary row-level UPDATE and DELETE against the row are refused by the
   installed trigger.

**Statement-snapshot, not prior-commit.** Unlike M082's prior-commit
attestation, M083 does NOT require the referenced receipts to have committed in
an earlier transaction. A receipt INSERTed earlier in the SAME transaction as
the capture IS visible and IS included, even though it has not committed. A
receipt committed by another transaction after the capture statement's snapshot
was taken is excluded. Both directions are measured against a live database.

## B. What It Does NOT Prove - Fifteen Explicit Non-Claims

Reproduced from `does_not_prove`, which is the governing list:

1. no ResearchSession, DecisionCandidate, brief or evaluation consumption;
2. no evaluation time, capture time or wall-clock chronology;
3. no receipt or event commit time;
4. no historical availability at an arbitrary cutoff;
5. no receipt ordering, committed-prefix or sequence authority;
6. no event payload, current or historical;
7. no receipt metadata provenance;
8. no operator or broker truth, fills or trades;
9. not that every M076 event has a receipt;
10. not that an absent receipt did not exist at another time;
11. not that the set represents all operator evidence;
12. no future-tail or excluded-receipt count;
13. no cryptographic sealing;
14. no protection against DDL, trigger disable, TRUNCATE, DROP or superuser;
15. no profitability, performance, advice or live-trading readiness.

## C. What The Database Enforces, And What It Does Not

Enforced (`database_enforcement`, all measured against a live server):

- `capture_query_overwrites_caller_supplied_membership: true` - the BEFORE
  INSERT trigger never reads `NEW.receipt_governance_ids` before overwriting
  it. Eighteen alternative SQL paths were executed - omitted, NULL, empty,
  forged subset, forged superset, duplicated, reverse-ordered, `INSERT ...
  SELECT`, multi-row, prepared statement, application repository, raw SQL,
  `COPY FROM STDIN`, both `ON CONFLICT` forms, hostile `search_path`, pg_temp
  table shadow, pg_temp function shadow - and every sanctioned path stored the
  identical exact set.
- `canonical_deterministic_order: true`
- `empty_set_explicit_not_null: true` - an empty receipt table yields `{}`,
  never NULL.
- `row_level_update_delete_refused: true`
- `identity_uniqueness_idempotency: true` - the primary key is the ONLY
  idempotency mechanism; a concurrent duplicate loses on the constraint and the
  repository returns the winner.
- `ddl_authority_trigger_disable_truncate_drop_superuser: false` - stated as
  **false**, i.e. explicitly NOT enforced.

## D. Known Limitations - Executed, Not Merely Asserted

The six `structural_limitations` stand as written. The quantified exhaustion
campaign executed each boundary rather than asserting it:

- **TRUNCATE** removes rows; a row trigger does not intercept it.
- **DROP TRIGGER** then UPDATE succeeds.
- **A competing BEFORE INSERT trigger named alphabetically after the capture
  trigger** overwrites the captured set, because PostgreSQL fires BEFORE ROW
  triggers in trigger-name order.
- **`session_replication_role = replica`** bypasses both triggers, and a
  caller-supplied forged array is stored verbatim.

Each requires table ownership or superuser: a non-owner is refused
`CREATE TRIGGER`, `ALTER TABLE ... DISABLE TRIGGER` and
`SET session_replication_role`, and a non-owner's ordinary INSERT still
receives the exact set. These four are demonstrations of the already-stated
non-claim 14 and the DDL enforcement value of `false`. **They did not widen,
narrow or otherwise change the authority**, in keeping with the rule that an
observation may not silently become a claim.

Also unchanged: no cryptographic signature, no monotonicity enforcement; the
watermark cannot report how much evidence it excluded; the identity is
caller-supplied and carries no chronology of its own; a crash between capture
statement start and commit leaves no partial row.

**Unbounded array aggregation.** The capture trigger's `array_agg` over the
whole receipt table has no row-count cap. This remains a stated structural
characteristic and is NOT repaired in M083: capping it would change stored
behaviour with no consumer requiring it.

## E. Measured Performance Is Validation Evidence Only

Capture and read latency, stored row size and query plans were measured at 0,
1, 100, 1,000, **10,000** and 25,000 receipts through the real repository path,
with a discarded warm-up and five measured samples per size. Sort spill was
forced and observed rather than assumed absent. The explicit `COLLATE "C"` was
measured to prevent an index-only scan - the price of the determinism
guarantee, recorded rather than optimised away.

**None of this is M083 authority.** It is validation evidence about one machine
under one configuration. A future consumer must re-measure at its own scale
rather than extrapolate these numbers, and no scalability claim enters the
contract.

## F. Owner Findings And Audit Findings - Every One Removed Or Bounded A Claim

Five Owner findings (REV-001 through REV-005) were closed with real code and
test changes: the authority schema was fully closed by enum; a 36-attack
authority contract suite was written; the absolute-immutability claim
`immutable_after_persistence` was **retired**, not reworded, and replaced by
two bounded claims; the coverage floor was **restored** to 79 by writing tests
rather than left lowered; and the architecture allowlist widening was
**removed** entirely.

Four further findings came from an independent audit and a quantified
exhaustion campaign:

- **AUD-001 (blocker class)** - the repository's row mapping was fail-open.
  `str(value)` converted a stored NULL array element into the receipt identity
  `'None'`, a `memoryview` into `'<memory at 0x...>'` and an integer into
  `'1'`, each then counted as a real receipt. PostgreSQL's `NOT NULL` binds the
  array value, not its members, so the corrupt input is genuinely storable, and
  the domain type's order check caught it only incidentally. Now fail-closed.
- **AUD-002** - the authority schema's own enum membership was pinned by
  nothing; schema and contract now pin each other.
- **AUD-003** - REV-005's architecture correction was unprotected, because
  granting an allowlist permission never produces a violation. That one edge is
  now pinned.
- **AUD-004** - the explicit `COLLATE "C"` was pinned by nothing, because this
  cluster's default collation happens to agree with byte order.

## G. Validation Evidence

172 M083 tests, all passing. Full regression against baseline
`45016d7cb79381d9ff8f90a410f57d5a22473269` shows an **empty failing/error ID
diff in both PostgreSQL-off and PostgreSQL-on modes** (20 identical off, 68
identical on), with every count delta reconciled exactly to the 172 tests and
no remainder. Twenty-seven mutation experiments each had their detecting test
named, executed and restored byte-identically; three initially detected nothing
and became AUD-002, AUD-003 and AUD-004. The concurrency suite ran three times
with full database resets between runs, producing identical result checksums.

Offline coverage 79.19% against the restored floor of 79, with the gate proven
live by a negative control.

## H. Frozen Preservation

No M057/M070/M076/M077/M078/M079/M080/M081/M082 path appears in the M083 diff.
`operator_event_receipt` is READ by exactly one statement - the capture query -
and never written. A live upgrade/downgrade/upgrade cycle confirmed M082's
rows, triggers and **enforced behaviour** all survive the M083 downgrade, and
that only M083's own objects are removed.

## I. Claim Honesty

M083 makes no profitability claim, no performance claim, no investment-advice
claim and no live-trading-readiness claim. It does not claim any evaluation
consumed a watermark; that binding belongs to a future evaluation-context
milestone which is **not started**. M083 does not replace or strengthen M082's
receipt identity attestation.

## J. Owner Approval

The Owner conditionally accepted the engineering content at `7291962`,
requiring only that two evidence matrices asserted in the final report be added
to the committed package. That correction is `49a7c9f`, documentation
only, touching `external-review/MILESTONE-083/validation-results.md` and nothing
else.

**MILESTONE-083 is APPROVED_AND_FROZEN.**

## K. Next Permitted Action

`MILESTONE-084` - **recommendation only.** M084 is `NOT_STARTED`. No M084 file,
design, scope or consumption claim exists, and nothing in M083 asserts that any
future milestone will consume this primitive.
