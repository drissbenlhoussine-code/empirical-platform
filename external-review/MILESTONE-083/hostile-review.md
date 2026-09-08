# MILESTONE-083 — Hostile Design and Implementation Review

Single-pass hostile review performed against the actual executable design (a
real PostgreSQL 16.13 instance), not a description of it. Findings below are
preserved as found, then corrected; none is deleted.

## Pre-implementation (design) findings

**D01 — statement-snapshot visibility needed an explicit, executed
definition.** The initial design sentence said only "visible to the capture
query." That is ambiguous between "visible under the transaction's snapshot"
and "already committed." Correction: Section 5.12 of the scope document and
attack 20 measure the SAME-transaction case directly against a live
database — a receipt inserted earlier in the same transaction as the capture
*is* included, which is ordinary PostgreSQL own-transaction-write visibility,
not a prior-commit guarantee. The migration docstring and domain module now
state this precisely and warn against renaming it "prior-committed."

**D02 — a digest was briefly considered as the stored authority.** Rejected
before implementation per the mission's Section 5.10: a digest is validation
evidence at best, not a substitute for the identities themselves.

**D03 — whether `array_agg` needs an explicit `COLLATE` was not obvious.**
The cluster's default collation (`C.UTF-8`) happens to already agree with
byte-order comparison, so an unqualified `ORDER BY receipt_governance_id`
would have looked correct in this environment while leaving canonical order
dependent on a database-level setting the migration does not control.
Correction: `ORDER BY receipt_governance_id COLLATE "C"` is explicit in the
capture query.

## Implementation-phase findings (found by executing the code)

**I01 — the M082 prior-committed-event trigger initially broke three of my
own test helpers.** `_seed_receipt` originally inserted the M076 event and
the M082 receipt inside one transaction. M082's own
`operator_event_receipt_requires_prior_commit` trigger correctly refused
that (`... EV-SLOW was written by a transaction whose status is in
progress`) — this is M082's guarantee working as designed, not an M083 defect,
but it meant three tests (`test_2` through `test_20`, and the second-pass
file) failed on first execution. Corrected by splitting event and receipt
insertion into two committed transactions, matching how `attest()` itself
requires the event to be already committed.

**I02 — a session-scoped TEMP TABLE leaked across the connection pool.**
`test_13_pg_temp_relation_shadowing_cannot_alter_the_result` created a TEMP
TABLE named `operator_event_receipt` on a pooled connection and returned that
connection to the pool without discarding it. PostgreSQL temp tables are
session-scoped, not transaction-scoped, so a later test reusing the same
physical connection intermittently saw its own queries against
`operator_event_receipt` silently shadowed by the leftover decoy table,
surfacing as an unrelated `relation "evaluation_evidence_watermark" does not
exist` error several tests later — a genuinely confusing failure mode,
reproduced and root-caused rather than worked around. Corrected by calling
`conn.invalidate()` after the temp-table test so the pool discards that
physical connection instead of reusing a tainted one.

**I03 — a lexical-order assertion was simply wrong.** The original
`test_18_and_19` asserted `("RC-PRE", "RC-POST")` in that order; `'RC-POST' <
'RC-PRE'` under byte-order comparison (`'O' < 'R'`), so the trigger's
canonical output was correct and the test's expectation was not. Corrected
the test's fixture identities (`RC-A-PRE`, `RC-Z-POST`) rather than the
production query.

**I04 — a hardcoded revision-id literal tripped the secret scanner and
would have drifted from the actual migration graph.** A `_M082_HEAD`
constant holding the M082 migration's own revision id as a literal string
matched detect-secrets' "Hex High Entropy String" heuristic (the same
false-positive class M082's own `12c3b84` commit corrected for its archive
checksum -- restating that literal value here would retrigger the identical
finding in this very document) and duplicated a fact the migration graph
already states. Corrected by reading `down_revision` from `ScriptDirectory`
at test time instead of hardcoding it — this removed the finding AND the
duplication, not
just the scanner trigger.

**I05 — `mypy --strict` run in isolation against a `tools/` script produces
errors identical in shape to the pre-existing ones in
`tools/render_m082_authority.py`.** Confirmed this is not an M083 regression:
`pyproject.toml`'s `[tool.mypy]` scopes `packages = ["empirical_platform"]`,
so the CI `python -m mypy` gate never checks `tools/` for either milestone.
No production code is affected; noted here rather than silently left
unexplained.

**I06 — the first CI push failed a coverage gate that local `--no-cov`
validation runs never exercised.** `python -m pytest` in CI (no PostgreSQL
service) applies `pyproject.toml`'s `--cov=empirical_platform` `addopts` and
its `fail_under = 79` floor; every local validation run in this mission had
used `--no-cov`, so this was never checked before the first push. Verified
it was a genuine regression, not a pre-existing base-branch failure, by
checking the last "push" workflow run on `master` at the exact base SHA
(`32266710533`, `conclusion: success`) on GitHub Actions before writing a
single line of fix code. Closed most of the gap with real, precedented unit
tests (see `validation-results.md`'s "Coverage gate" section for the full
account) and lowered the floor by exactly one point for the small,
genuinely PostgreSQL-only residual, mirroring M070's own documented
precedent in both reasoning and magnitude.

**I07 — closing I06 introduced a real architecture-boundary violation.**
Splitting `run_capture_evaluation_evidence_watermark`/`run_get_evaluation_
evidence_watermark` out of each CLI's `main()` (to make them
monkeypatchable, closing part of the I06 gap) required an explicit
`-> EvaluationEvidenceWatermark` return-type annotation, and
`EvaluationEvidenceWatermark` lives in `decision_candidate`, which
`ALLOWED["entrypoints"]` did not include. `tests/architecture/
test_module_boundaries.py::test_current_source_tree_respects_boundaries`
caught this immediately on the next full-suite run. Corrected with one
narrow, documented addition to `tools/check_architecture.py`'s
`ALLOWED["entrypoints"]` set, re-verified against both the positive checker
and the negative fixture.

**I08 — `ruff format` silently corrupted both authority JSON files into
invalid JSON.** An early `ruff format tools/render_m083_authority.py
external-review/MILESTONE-083/current-authority.json external-review/
MILESTONE-083/current-authority.schema.json` call was intended to format
only the Python file; ruff accepted the `.json` paths too and rewrote both
into JSON5-like syntax with trailing commas before closing brackets --
invalid strict JSON, and neither `python -m json` nor `python tools/
render_m083_authority.py --check` was re-run against them until this
coverage-fix pass, so the corruption went undetected through the entire
first push and its CI run (nothing else in the validated gate set parses
these two files). Found by re-running `render_m083_authority.py --check`
as part of re-validating this fix; both files were repaired by removing the
trailing commas and re-serialized with the standard library `json` module.
`ruff format`/`ruff check` are now invoked on `.py` targets only, never on
`.json` paths.

## Owner deep-closure review findings (REV-001 through REV-005)

Reproduced and closed against the actual executable candidate at `c75c14d`,
in the order the owner mission specified.

**REV-001 — authority schema left `structural_limitations`/
`intended_future_use` open to any regex-valid identifier.** Reproduced
first: `renderer.validate()` accepted an invented identifier appended to
`structural_limitations` (schema only enforced `pattern: "^[a-z0-9_]+$"`),
and only `renderer.render()` then crashed with a bare `KeyError` -- an
incidental failure, not a schema rejection, exactly as the finding states.
Corrected by converting both arrays to closed `enum` lists with exact
`minItems`/`maxItems` (6 and 2, matching the renderer's own `_LIMITATIONS`/
`_FUTURE` dictionaries) -- the identical enum-closure technique already used
for `proves`/`does_not_prove`. Re-verified with an isolated same-length swap
(not merely an over-length append, which the `maxItems` check alone would
have caught) to prove the enum closure itself, not just cardinality, is
doing the rejecting. New dedicated suite:
`tests/integration/test_m083_authority_contract.py` (57 tests, closing
REV-002 in the same change).

**REV-002 — no dedicated authority-contract attack suite existed.** Added
`tests/integration/test_m083_authority_contract.py`, executing the real
`validate()`/`render()`/`main()` against the real committed contract and
schema. Covers all 36 items the mission specified (numbered `test_1_...`
through `test_36_...` plus named coverage tests) and a four-part anti-vacuity
campaign (`test_each_structural_rule_is_anti_vacuous`): closed-schema,
enum-closure, byte-exact-rendering, and `authority_version`-const, each
weakened, shown to pass the attack, then restored and shown to fail it
again. All 57 tests pass.

**REV-003 — `immutable_after_persistence` overclaimed absolute database
immutability.** The rendered text read "immutability -- the stored set
never changes once persisted, regardless of later receipt activity" as one
of the four `proves` claims -- broader-sounding than the actual boundary
(row-level UPDATE/DELETE refusal only; TRUNCATE/DROP/disable-trigger/
superuser remain outside it, already correctly stated elsewhere in the same
document's `does_not_prove`/`structural_limitations`, but the `proves` claim
itself did not carry that qualifier inline). Corrected by retiring the
identifier entirely and replacing it with two bounded claims exactly as
named in the mission: `stored_set_stable_against_later_receipt_activity` and
`row_level_update_delete_refused_while_installed_trigger_is_active`, each
with its own precise, separately-qualified rendered sentence. `proves` grew
from 4 to 5 items; schema, JSON, and renderer all updated together and
re-verified with `--check`. The same bounded language was then applied
consistently to `decision_candidate/evaluation_evidence_watermark.py`'s
module and class docstrings (replacing a bare "IMMUTABILITY" section and a
bare "One immutable, database-computed..." class summary) and to
`evaluation_evidence_watermark_repository.py`'s protocol docstring
("is immutable" -> "has a stable stored set", with an explicit pointer to
the bounded-guarantee module docstring). The migration file's own docstring
was already precisely bounded ("ROW-LEVEL UPDATE/DELETE IMMUTABILITY UNDER
THE INSTALLED TRIGGER ONLY") and needed no correction.

**REV-004 — coverage floor lowered to 78 rather than closing the real
gap.** Measured the actual gap directly: `PostgresEvaluationEvidenceWatermark
Repository.capture`/`.get` carried 21 uncovered statements (branches: the
existing-row fast path, the INSERT happy path and its exact SQL shape, the
conflict-and-read-back path, the no-readable-winner defensive branch, and
unrelated-error propagation). Added `tests/unit/
test_postgres_evaluation_evidence_watermark_repository.py`'s 8 new tests
against a hand-written fake that duck-types the narrow `unit_of_work()`/
`execute()` surface -- scripted rows only, never a simulation of what the
BEFORE INSERT trigger computes (that remains exclusively PostgreSQL-tested).
This raised measured offline coverage from 78.95% to 79.18%, clearing the
original 79% floor with real margin, not by construction. `pyproject.toml`'s
`fail_under` is restored to 79 (from 78). The two CLI `run_capture_.../
run_get_...` composition bodies remain offline-uncovered by deliberate,
precedented choice, matching `entrypoints.create_run`'s own `run_create_run`
(no existing entrypoint in this ~80-entrypoint codebase unit-tests its own
composition body by monkeypatching `postgres_repository_runtime`); they
are exhaustively covered by the PostgreSQL integration suite instead.

**REV-005 — `entrypoints -> decision_candidate` architecture widening was
unnecessary.** The only reason for the widening was a return-type annotation
on `run_capture_evaluation_evidence_watermark`/`run_get_evaluation_evidence_
watermark`. `EvaluationEvidenceWatermark` was already imported into
`usecases/capture_evaluation_evidence_watermark.py` for its own handler
signatures; adding it to that module's `__all__` and having both entrypoints
import the type from there instead of directly from `decision_candidate`
resolves the annotation through an edge (`entrypoints -> usecases`) already
present in the pre-M083 allowlist -- mirroring exactly how `entrypoints.
create_run` already gets `RunId` through the pre-existing `identifiers`
edge. `ALLOWED["entrypoints"]` is restored to its exact pre-M083 set
(`{"shared", "application", "identifiers", "usecases"}`); both the positive
checker and the negative fixture were re-verified.

## What the review looked for and did not find a defect in

- Exact-set completeness against a direct SQL caller who supplies an omitted
  subset, an extra nonexistent id, duplicates, or no membership column at
  all (attacks 9-12) — the trigger's unconditional overwrite handles all four
  uniformly, by construction, and this was confirmed rather than assumed.
- Idempotency and immutability under concurrent capture of the same identity
  (attack 22) and under retry after receipts changed in between (attack 27).
- Rollback leaving no partial row (attack 23) and TRUNCATE/DROP/trigger-
  disable/superuser remaining outside the enforcement boundary, executed and
  rolled back rather than merely asserted (attack 32).
- M082 surviving an M083 downgrade byte-for-byte, including its own
  immutability trigger still refusing a DELETE afterward (attack 29).

## Anti-vacuity check on the two governing negative controls

Both checks were run directly against the live database with raw SQL and
SQLAlchemy, outside pytest — the pytest module fixture rebuilds the schema
(and therefore the trigger functions) from the migration on every run, which
would silently undo any in-place weakening before a test ever executed, and
the first attempt at this check did exactly that and produced a false
"no difference" result. The check below replaces that failed attempt.

- **Weakened the capture trigger** to `NEW.receipt_governance_ids :=
  COALESCE(NEW.receipt_governance_ids, <the same subquery>)` — i.e. respect a
  caller-supplied array when present, matching what an omitted-subset /
  extra-id / duplicate attack (9-12) would need to succeed. Under the
  weakened trigger, `INSERT ... (watermark_governance_id,
  receipt_governance_ids) VALUES ('WM-ANTIVAC', ARRAY['RC-FORGED'])`
  persisted `{RC-FORGED}` verbatim, even though `RC-FORGED` names no real
  receipt — the forgery succeeded. Restored the unconditional overwrite; the
  identical INSERT shape then persisted the real computed set
  (`{RC-AV-REAL}`), ignoring the supplied array entirely.
- **Disabled the UPDATE/DELETE immutability trigger**
  (`ALTER TABLE evaluation_evidence_watermark DISABLE TRIGGER
  evaluation_evidence_watermark_immutable_trigger`, inside a transaction
  rolled back afterward — DDL is transactional in PostgreSQL). Under the
  disabled trigger, `DELETE FROM evaluation_evidence_watermark WHERE
  watermark_governance_id='WM-IMMUT-AV'` succeeded and removed the row.
  After the rollback restored the trigger, the identical DELETE against the
  same still-present row raised `evaluation_evidence_watermark is
  append-only: DELETE is not permitted`.

Both checks match the required shape exactly: weaken the rule, show the
attack passes; restore the rule, show the attack is rejected. The full
33-test hostile suite was re-run after both checks and passed unchanged
(the raw-SQL checks above ran against isolated, freshly truncated rows and
left the schema in its correct, restored state).

## Owner deep-closure review: extended attack campaign (E1-E10)

Ten additional attacks, committed as `tests/integration/
test_m083_evaluation_evidence_watermark_extended_attacks.py`, target SQL
surfaces and isolation levels the original 33 did not exercise. All pass,
repeated across five separate full runs of the combined M083 PostgreSQL
suite (43 tests: 33 original + 10 extended) with no flake.

| # | Attack | Result |
|---|---|---|
| E1 | Multi-row single-statement `INSERT ... VALUES (a),(b)` | Both rows independently receive the identical, complete set (row trigger, not statement-level) |
| E2 | `INSERT ... SELECT 'id'` (derived source, not a literal VALUES list) | Fires identically; full set captured |
| E3 | Caller supplies `ARRAY[]::text[]` while real receipts exist | Overwritten to the real, non-empty set |
| E4 | Caller supplies explicit `NULL` for a `NOT NULL` column | Overwritten before NOT NULL is even checked (BEFORE ROW fires first) — real PostgreSQL semantics, not an M083-specific mechanism |
| E5 | `COPY evaluation_evidence_watermark (watermark_governance_id) FROM STDIN` | Fires the identical row trigger |
| E6 | Exactly 64 vs. 65-character identity | 64 succeeds; 65 rejected by the column type itself (`value too long`), independent of any Python-layer check |
| E7 | REPEATABLE READ, snapshot pinned at first statement, a receipt committed mid-transaction from another connection | The pinned snapshot excludes it — genuinely different from the default per-statement READ COMMITTED behaviour attacks 18-19 measure |
| E8 | SERIALIZABLE write-skew (two transactions each read `count(*)`, then each insert a different row) | A real serialization failure (SQLSTATE `40001`, "could not serialize access due to read/write dependencies") aborts exactly one side at commit; its retry then succeeds |
| E9 | Named hostile schema (`hostile_evil_schema`, holding a shadow `operator_event_receipt` table) explicitly prepended to `search_path` | The trigger's own `SET search_path = pg_catalog, public` pins resolution; the forged receipt never appears |
| E10 | Direct repository call with a blank identity, bypassing Python-layer command validation, reaching the real CHECK constraint (SQLSTATE `23514`) | `unique_violation_constraint_name` correctly returns `None`; the repository re-raises rather than misclassifying it as a PK conflict |

**Independent database-design review (Phase D), findings that did NOT
require any code change:** own-transaction-write visibility, later-commit
exclusion, and same-transaction inclusion were re-derived from first
principles against the live database rather than trusted from the existing
33-attack report, and matched exactly. `array_agg(...COLLATE "C")` was
confirmed stable across ASCII and a mixed-case sample. Receipt-identity
`NULL`/duplicate prevention is M082's own primary-key/NOT NULL boundary,
read-only from M083's side and unchanged. No rule, default, or second
BEFORE INSERT trigger exists on this table to race with or bypass the
capture trigger (confirmed by inspecting `pg_trigger`/`pg_rewrite` for this
relation: exactly the two triggers the M083 migration installs, in the
expected firing order).

**Performance and scale characterization (Phase I), measured, not
estimated.** Against the same local PostgreSQL 16.13 instance, single
connection, no concurrent load:

| Receipt-table size at capture | `capture()` latency | Stored array size (`pg_column_size`) | `get()` latency |
|---|---|---|---|
| 0 | 5.85 ms | 13 bytes | 1.17 ms |
| 100 | 3.89 ms | 1,624 bytes | 1.37 ms |
| 1,000 | 5.46 ms | 3,280 bytes | 1.87 ms |
| 10,000 | 17.24 ms | 33,542 bytes | 4.87 ms |

Both `capture()` and `get()` scale sub-linearly to linearly and stay in
single-digit-to-low-double-digit milliseconds through 10,000 receipts on
this hardware; `get()` is a primary-key lookup and is not expected to
degrade with table growth. No scalability defect was found at this scale.
This is measured local-hardware evidence, not a portable performance
guarantee, and is NOT converted into M083 authority (the schema's `proves`/
`does_not_prove` sets are unchanged by this measurement). The capture
trigger's `array_agg` over the entire `operator_event_receipt` table has no
row-count cap; this remains a recorded structural characteristic (see
`validation-results.md`'s "Remaining limitations"), not a defect requiring
a fix within M083 -- a future evaluation-context milestone should re-measure
at its own expected receipt-table size before relying on these numbers.

**Environment-only limitation, separated from the above (operating
principle #14):** the true non-superuser/table-owner permission boundary
(mission Phase D/E) could not be independently re-measured in this sandbox
beyond what M082's own two pre-existing probe tests already attempt --
those two tests themselves fail in this sandbox for a database-role-
privilege reason unrelated to any M083 or M082 code (see
`validation-results.md`'s "Probe/environment errors" section). This is
recorded as an environment gap, not a product finding.

---

# Quantified exhaustion campaign — three formally separate hostile passes

Everything above this line is the earlier deep-closure review. This section is
a later, separate campaign run against commit `2cadb91827ff679e4bb4ca3bc03c6d18e2ae42e5`
(tree `2dfd62b1`) to complete the Owner exhaustion criteria the preceding
independent audit explicitly reported as NOT completed.

**Status of the preceding audit's conclusion:
`SUPERSEDED IN PART — INDEPENDENT AUDIT DID NOT COMPLETE ALL OWNER EXHAUSTION
CRITERIA`.** Its findings stand and are not rewritten; what is superseded is
only its terminal claim of completeness. It disclosed five omissions — three
formally separate hostile passes, three clean concurrency repetitions, the
10,000-receipt measurement, the complete 27-mutation matrix, and full
exhaustion — and this campaign executes all five.

Each pass below began from the recorded commit identity above, used its own
checklist, inspected executable code rather than reports, and was followed by
a fresh re-review after every correction.

## Pass A — database adversary

Files inspected (blob identity at the time of the pass):

| File | git blob |
|---|---|
| `migrations/versions/9e4e647347ad_...py` | `255ce7b4` |
| `shared/persistence/postgres_repositories/evaluation_evidence_watermark_repository.py` | `434b390b` |
| `decision_candidate/evaluation_evidence_watermark.py` | `780dac5f` |
| `decision_candidate/evaluation_evidence_watermark_repository.py` | `b4e7c4c6` |
| `shared/persistence/postgres_repositories/runtime.py` | `096a1c36` |

### Executed attacks (28 total; 18 alternative-SQL-path attacks written for this pass)

All run against a real PostgreSQL 16.13 cluster, in an isolated database, with
a committed seed of three receipts `RC-1..RC-3`. **Every sanctioned path stored
exactly `{RC-1,RC-2,RC-3}`.**

| # | Attack | Result |
|---|---|---|
| P1 | INSERT omitting the membership column | exact set |
| P2 | INSERT with explicit `NULL` membership | overwritten to exact set |
| P3 | INSERT with empty array while receipts exist | overwritten to exact set |
| P4 | INSERT with forged **subset** `{RC-1}` | overwritten to exact set |
| P5 | INSERT with forged **superset** incl. `RC-FAKE` | overwritten to exact set |
| P6 | INSERT with duplicated membership | overwritten to exact set |
| P7 | INSERT with reverse-ordered membership | overwritten, canonical order |
| P8 | `INSERT ... SELECT` (derived source) | overwritten to exact set |
| P9 | multi-row single-statement INSERT (3 rows, 3 different forged shapes) | **all three rows identical**, exact set |
| P10 | `PREPARE`/`EXECUTE` prepared statement | overwritten to exact set |
| P11 | application repository path (composition root) | exact set; `get` == `capture`; re-capture idempotent |
| P12 | raw SQL capture | exact set, **byte-identical to P11** |
| P13 | `COPY ... FROM STDIN` | capture trigger fires; exact set |
| P14 | `ON CONFLICT DO NOTHING` on a duplicate identity | 0 rows, no mutation |
| P14b | `ON CONFLICT DO UPDATE` | refused by the immutability trigger |
| P15 | hostile `search_path = pg_temp, public` | exact set (schema qualification holds) |
| P16 | `pg_temp` **table** shadowing `operator_event_receipt` | exact set — shadow ignored |
| P17 | `pg_temp` **function** shadowing `array_agg` | exact set — shadow ignored |
| P18a | competing BEFORE INSERT trigger named *earlier* (`aaa_…`) | exact set — capture runs after and overwrites |
| P18b | competing BEFORE INSERT trigger named *later* (`zzz_…`) | **captured set overridden** — see finding A-01 |
| A-N1 | `TRUNCATE` | rows removed — row trigger does not intercept (as documented) |
| A-N2 | `DROP TRIGGER` then `UPDATE` | mutation succeeds (as documented); rollback restored the trigger |
| A-N3 | `SET session_replication_role = replica` then forged INSERT | **forged array persisted** — see finding A-02 |
| A-N4 | non-owner attempts `SET session_replication_role` | `permission denied to set parameter` |
| A-N5 | non-owner attempts `CREATE TRIGGER` on the table | `permission denied for table` |
| A-N6 | non-owner attempts `ALTER TABLE ... DISABLE TRIGGER` | `must be owner of table` |
| A-N7 | non-owner ordinary INSERT | still receives the exact set |
| A-N8 | duplicate identity in one transaction | `duplicate key value violates unique constraint` , exactly one row |

### Pass A findings

**A-01 — BEFORE-row trigger *name* ordering decides whose write survives.**
PostgreSQL fires BEFORE ROW triggers in trigger-name order. The capture trigger
is `evaluation_evidence_watermark_capture_receipt_set_trigger` (`e…`), so a
competing trigger named alphabetically *after* it runs later and can overwrite
`NEW.receipt_governance_ids` (`{ZZZ-HOSTILE}` in P18b), while one named earlier
is simply overwritten by capture (P18a).

*Adjudication: not a new defect, and NOT an authority change.* Creating a
trigger on this table requires table ownership or superuser — measured in A-N5,
where a non-owner is refused outright. That is precisely the DDL authority
already disclaimed by `does_not_prove.protection_against_ddl_trigger_disable_
truncate_drop_or_superuser` and by `database_enforcement.ddl_authority_trigger_
disable_truncate_drop_superuser: false`. Recorded here as validation evidence
that sharpens the *mechanism* of an existing non-claim, per the mission's rule
that observations may not silently expand authority.

**A-02 — the replication path bypasses both triggers, executed rather than
asserted.** Under `session_replication_role = replica`, the capture trigger does
not fire and a caller-supplied forged array (`{FORGED-VIA-REPLICA}`) is stored
verbatim. The migration docstring already names "a replication path that
bypasses these triggers" as outside the boundary; this is the first time it has
been *executed* rather than stated. A-N4 bounds it: a non-owner cannot set that
parameter at all.

*Adjudication: documented limitation, verified, correctly disclaimed.*

**A-03 — see AUD-001 in the audit findings section below.** Pass A's read-path
review is what surfaced the fail-open row mapping, the one blocker-class defect
of this campaign.

### Pass A fresh re-review after correction

After the AUD-001 fix, the whole Pass A attack set was re-executed against the
corrected head: all 28 attacks behave identically, and the two new regression
tests (E11/E12) additionally prove a corrupted stored row is now refused rather
than fabricated.

## Pass B — scientific-authority adversary

20 executed authority mutations. Each attempts to make the contract assert a
forbidden class; each must be rejected **structurally by the schema validator,
before the renderer is reached**. The renderer was replaced with a tripwire for
the duration so "render was never reached" is measured, not assumed.

| # | Forbidden class attempted | Result |
|---|---|---|
| B01 | receipt commit order | rejected structurally, render never reached |
| B02 | capture-time / wall-clock chronology | rejected structurally, render never reached |
| B03 | availability at an arbitrary cutoff | rejected structurally, render never reached |
| B04 | receipt sequence / committed prefix | rejected structurally, render never reached |
| B05 | event payload | rejected structurally, render never reached |
| B06 | receipt metadata provenance | rejected structurally, render never reached |
| B07 | completeness of all operator evidence | rejected structurally, render never reached |
| B08 | excluded / future-tail count | rejected structurally, render never reached |
| B09 | existing-evaluation consumption | rejected structurally, render never reached |
| B10 | absolute immutability | rejected structurally, render never reached |
| B11 | cryptographic sealing | rejected structurally, render never reached |
| B12 | profitability | rejected structurally, render never reached |
| B13 | performance | rejected structurally, render never reached |
| B14 | investment advice | rejected structurally, render never reached |
| B15 | live-trading readiness | rejected structurally, render never reached |
| B16 | smuggling a claim in via `structural_limitations` | rejected |
| B17 | smuggling a claim in via `intended_future_use` | rejected |
| B18 | inventing a new `does_not_prove` identifier | rejected |
| B19 | flipping `ddl_authority_…` to `true` (overclaiming DDL protection) | rejected |
| B20 | silently DROPPING a non-claim | rejected (exact cardinality) |

Bijection verified in both directions across all 15 required points — exact
top-level keys; contract set == schema enum for all four lists; enforcement
keys and const values; exact domain dataclass fields; exact runtime JSON keys;
runtime text/JSON semantic agreement; `captured_receipt_count` derived, never
stored; byte-identical 3,601-byte Markdown; JSON-reorder and Markdown-only
drift both detectable; determinism across calls; unknown identifiers rejected
before rendering; and no committed M083 runtime fixture that could act as an
alternate authority source.

### Pass B finding

**AUD-002 — the schema's own enum membership was pinned by nothing** (details
in the audit findings section below). Found because a mutation adding an
*eighth* identifier to the `proves` enum was not detected by any test.

## Pass C — software-governance adversary

| # | Attack | Result |
|---|---|---|
| C01 | schema openness (5 enum/cardinality/additionalProperties mutations) | all detected — mutations 1-7 |
| C02 | incidental exception masquerading as rejection | **found**: the pre-fix NULL-element rejection was an ordering complaint, not a type check (AUD-001) |
| C03 | test vacuity across every governing rule | 27-mutation matrix; 3 real gaps found |
| C04 | coverage manipulation | gate is live: floor→80 produces `FAIL Required test coverage of 80.0% not reached. Total coverage: 79.19%` |
| C05 | architecture-rule weakening | **found**: re-adding the REV-005 edge was undetectable (AUD-003) |
| C06 | suppression-count accuracy | recomputed mechanically base→HEAD: 31 added suppressions with exact file:line |
| C07 | skips / xfails | 0 added by the whole PR, mechanically verified |
| C08 | changed-files accuracy | exact match, 29 files; omitting one entry is detected by the comparison |
| C09 | frozen-path preservation | no frozen path touched; temporary frozen mutation detected by two independent detectors and restored byte-exactly |
| C10 | build/wheel mismatch | sdist+wheel build; clean-venv import; both console scripts execute a live round trip |
| C11 | CLI/runtime mismatch | runtime JSON keys closed; text and JSON semantically agree |
| C12 | PR-body drift | PR body rewritten from measured numbers at the final head |
| C13 | documentation claims unsupported by commands | every claim in this section carries its command and totals |
| C14 | renderer drift | byte-exact `--check`; both drift directions detected |
| C15 | alternate authority source | none exists (verified against `git ls-files`) |

### Pass C findings

**AUD-003** and **AUD-004** (below) were both found here: two governing rules
whose weakening no test detected.

## Audit findings AUD-001 – AUD-004 (this campaign)

**AUD-001 — BLOCKER CLASS — the repository's row mapping was fail-open.**

`_row_to_watermark` read `str(value)`. That does not narrow a type; it
CONVERTS whatever the driver returned into a governance identity. Measured,
pre-fix, against the real function:

| stored/driver value | pre-fix result |
|---|---|
| `None` array element | receipt identity `'None'`, counted in `captured_receipt_count` |
| `memoryview(b'abc')` | receipt identity `'<memory at 0x…>'` |
| `1` | receipt identity `'1'` |
| `b'WM-1'` identity | watermark identity `"b'WM-1'"` |
| `['a']` nested | receipt identity `"['a']"` |
| `None` identity | watermark identity `'None'` |

The exposure is real, not theoretical. PostgreSQL's `NOT NULL` binds the array
value, not its members: `ARRAY['real-id', NULL]::varchar(64)[]` is a legal
value for this column (executed), and SQLAlchemy/psycopg returns Python `None`
for that member (executed). The capture trigger cannot produce one — it
aggregates a primary-key column — but the trigger is not the only writer the
schema admits, and `DISABLE TRIGGER`, DDL authority, the replication path
(A-02) and a superuser are all explicitly outside the enforcement boundary.
Reading a row back is exactly where that boundary should be noticed.

The domain type's duplicate/canonical-order checks were **not** a substitute.
They caught a stringified NULL only *incidentally*, and only when `'None'`
sorted out of position. `['A-real-id', NULL]` stringifies to an ascending pair
(`'A' < 'N'`) and was **accepted**, reporting `('A-real-id', 'None')` as the
stored receipt set with `captured_receipt_count == 2`. That is a fabricated
receipt identity presented as authoritative evidence — a direct contradiction
of the milestone's one claim.

*Correction:* fail-closed. Both the identity and every array member must
really be `str`, and the receipt column must really be an array, or the read
raises a PERSISTENCE `FoundationError` naming the offending position and the
actual type. No coercion is needed for a well-formed row: SQLAlchemy's
`result.mappings()` returns `str` and `list[str]` for these column types,
measured against this schema including the empty-array case. **M082's own
mapping is deliberately unchanged** — it is frozen, and its columns are scalar
`NOT NULL` varchars with no comparable element-level hole.

*Retraction:* the unit test `test_row_to_watermark_coerces_non_string_column_
values` asserted the OPPOSITE contract — it called the coercion "defensive" and
asserted an object's `__str__` became the identity. It enshrined the defect
rather than catching it. Retracted and replaced by tests that assert the
REASON for each refusal (a type check, not an ordering complaint), plus
real-database E11 (a corrupted row is refused end to end) and E12 (a
well-formed round trip, including the empty set, is unaffected).

**AUD-002 — the authority SCHEMA's enum membership was pinned by nothing.**
The contract was pinned to the approved sets, and seven forbidden literals were
pinned, but adding any *eighth* identifier to the schema's `proves` enum passed
undetected. The schema is the gate every other attack test relies on: it could
be widened in one commit and used in the next, with contract-side tests only
noticing at the second step. Closed by
`test_the_schema_admits_exactly_the_approved_identifier_universe`, which makes
schema and contract pin each other (enum membership, exact cardinality,
uniqueness, enforcement consts, `additionalProperties`, `authority_version`).

**AUD-003 — REV-005's architecture correction was unprotected.** Re-adding the
`entrypoints → decision_candidate` edge was undetectable *by construction*:
granting a permission never produces a violation, so the checker still exits 0
and the negative fixture still fails as designed. Closed by
`test_rev_005_entrypoints_may_not_regain_a_direct_decision_candidate_edge`,
which pins **only that one edge** — deliberately not the whole project-wide
`ALLOWED` table, which other milestones must stay free to evolve.

**AUD-004 — the explicit `COLLATE "C"` was pinned by nothing.** Deleting it
was undetected, because this cluster's default collation (`C.UTF-8`) agrees
with byte order — exactly what design finding D03 predicted. The guarantee is
that canonical order does *not* depend on that coincidence. A behavioural test
cannot discriminate portably (CI runs on `windows-latest`), so E13 pins the
property against the function definition PostgreSQL actually installed, and
proves the pin is not cosmetic by showing a real ICU collation in this same
cluster orders the same identifiers differently (`B-1,_z,a-1` vs `_z,a-1,B-1`).

## Mutation / anti-vacuity matrix — 27 of 27 executed

Each mutation was applied in isolation to a clean tree, the detecting test was
run, the failure was captured, the file was restored via `git checkout --`, and
restoration was proven by `git diff --quiet` before the unmutated test was
re-run and confirmed passing. **No mutation is present in the candidate; no
mutation was ever committed.**

| # | Invariant | Detecting test | Detected |
|---|---|---|---|
| 1 | `authority_version` const 1 | `test_3_authority_version_two_is_rejected` | yes |
| 2 | positive-claim enum closed | `test_6_unknown_positive_claim_rejected` | yes |
| 3 | non-claim enum closed | `test_9_unknown_non_claim_rejected` | yes |
| 4 | structural-limitations enum closed | `test_15_unknown_structural_limitation_rejected` | yes |
| 5 | intended-future-use enum closed | `test_18_unknown_future_use_identifier_rejected` | yes |
| 6 | exact list cardinality | `test_7_missing_positive_claim_rejected` | yes |
| 7 | top-level `additionalProperties:false` | `test_4_unknown_top_level_key_rejected` | yes |
| 8 | absolute immutability cannot enter `proves` | `test_21_to_27[26-absolute-immutability-retired-identifier]` | yes |
| 9 | evaluation-consumption cannot enter `proves` | **initially NONE → AUD-002** → `test_the_schema_admits_exactly_the_approved_identifier_universe` | yes (after fix) |
| 10 | capture overwrites caller membership | `test_e3_caller_supplied_empty_array_is_overwritten_when_receipts_exist` | yes |
| 11 | capture query is schema-qualified | `test_13_pg_temp_relation_shadowing_cannot_alter_the_result` | yes |
| 12 | canonical order pinned by `COLLATE "C"` | **initially NONE → AUD-004** → `test_e13_the_installed_capture_function_pins_collate_c_explicitly` | yes (after fix) |
| 13 | empty set explicit, never NULL | `test_1_empty_receipt_table_produces_an_explicit_empty_set` | yes |
| 14 | row-level UPDATE/DELETE refused | `test_25_update_is_refused` | yes |
| 15 | `get()` reads the stored set only | `test_5_later_receipt_insertion_does_not_change_an_existing_watermark` | yes |
| 16 | domain refuses duplicates | `test_duplicate_receipt_ids_are_refused` | yes |
| 17 | domain refuses non-canonical order | `test_out_of_order_receipt_ids_are_refused` | yes |
| 18 | unrelated DB error propagates | `test_capture_propagates_an_unrelated_foundation_error_unmodified` | yes |
| 19 | unrelated unique constraint not misclassified | `test_capture_propagates_an_unrelated_foundation_error_unmodified` | yes |
| 20 | winner read-back on conflict | `test_capture_conflict_reads_back_and_returns_the_winner` | yes |
| 21 | runtime JSON key set closed | `test_json_rendering_exposes_exactly_four_keys` | yes |
| 22 | no appended runtime claim | `test_31_runtime_json_exposes_no_key_beyond_the_canonical_contract` | yes |
| 23 | Markdown byte-exactness | `test_2_the_generated_document_is_byte_identical_to_the_rendering` | yes |
| 24 | coverage gate live | the gate itself: `FAIL Required test coverage of 80.0% not reached. Total coverage: 79.19%` | yes |
| 25 | REV-005 edge stays removed | **initially NONE → AUD-003** → `test_rev_005_entrypoints_may_not_regain_a_direct_decision_candidate_edge` | yes (after fix) |
| 26 | `changed-files.txt` exact | exact comparison command (see note) | yes |
| 27 | frozen M082 file unmodified | frozen-path diff **and** M082's own suite (3 failures) | yes |

Three mutations initially detected nothing. Each produced a real finding
(AUD-002, AUD-004, AUD-003), each was closed with a permanent test, and each
mutation was then **re-run and confirmed detected**.

*Note on #26:* the detector is a command, not a committed test, and
deliberately so — a committed test would have to encode the review base SHA,
which becomes meaningless the moment this branch merges. `changed-files.txt` is
a review-package artifact whose correctness is a review-time gate; it is
verified in the quality-gate list and regenerated from `git diff --name-only`.

*Note on #24:* the discriminator is the coverage line, not the process exit
code — this environment has 8 pre-existing, M083-unrelated test failures (see
`validation-results.md`), so pytest exits non-zero either way. Stating the exit
code alone would have been a false signal.
