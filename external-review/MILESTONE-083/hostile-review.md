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
would have drifted from the actual migration graph.** `_M082_HEAD =
"d9a2f5c81b73"` matched detect-secrets' "Hex High Entropy String" heuristic
(the same false-positive class M082's own `12c3b84` commit corrected for its
archive checksum) and duplicated a fact the migration graph already states.
Corrected by reading `down_revision` from `ScriptDirectory` at test time
instead of hardcoding it — this removed the finding AND the duplication, not
just the scanner trigger.

**I05 — `mypy --strict` run in isolation against a `tools/` script produces
errors identical in shape to the pre-existing ones in
`tools/render_m082_authority.py`.** Confirmed this is not an M083 regression:
`pyproject.toml`'s `[tool.mypy]` scopes `packages = ["empirical_platform"]`,
so the CI `python -m mypy` gate never checks `tools/` for either milestone.
No production code is affected; noted here rather than silently left
unexplained.

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
