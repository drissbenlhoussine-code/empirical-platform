# MILESTONE-084 — Validation Results

Every figure below was executed and observed. Where something was **not** done,
it is listed in Section 7 rather than omitted.

Environment: Python 3.13.12, ruff 0.16.6, mypy 1.20.2, pytest 9.1.1,
PostgreSQL 16.13 (local, database `empirical_m084`).

---

## 1. Test suites, each run individually

| Suite | Result |
|---|---|
| `tests/unit/test_m084_domain_core.py` | **134 passed** |
| `tests/unit/test_m084_cli_and_io.py` | **46 passed** |
| `tests/unit/test_m084_repositories_and_handlers.py` | **71 passed** |
| `tests/integration/test_m084_decision_to_approval_postgres_attacks.py` | **213 passed, 2 skipped** |
| `tests/integration/test_m084_decision_to_approval_lifecycle.py` | **18 passed** |
| `tests/integration/test_m084_authority_contract.py` | **31 passed** |
| `tests/architecture/test_module_boundaries.py` | **7 passed** (3 new) |

**Total: 520 passed, 2 skipped.** The two skips are deliberate: the
terminal-state attack matrix skips the cases where start and target statuses
are equal, because a no-op update is not a transition.

## 2. Static gates

| Gate | Result |
|---|---|
| `ruff format --check .` (whole tree, as CI runs it) | **664 files already formatted** |
| `ruff check .` (whole tree, as CI runs it) | **All checks passed!** |
| `mypy --strict` (336 source files) | **Success: no issues found** |
| Coverage floor (79%) | **pass at 79%** |
| Architecture boundaries (`tools/check_architecture.py`) | pass, zero violations |
| `python tools/render_m084_authority.py --check` | matches |

**No `noqa`, no `type: ignore` outside test-only fixture typing, and no
suppression was added to any production module.** Two ruff findings were
resolved by restructuring rather than silencing:

- `S105` on a `PASS = "PASS"` enum member (flagged as a hardcoded password) →
  members renamed to `PASSED`/`FAILED`/`UNKNOWN`.
- `S608` on f-string SQL in the repositories and attack suite → the SQL is now
  fully literal, and the attack suite composes statements with SQLAlchemy Core
  rather than string formatting.

`ANN401` on `Any`-typed parameters was likewise fixed by giving real types
(`object`, PEP 695 type parameters), not by exemption.

## 3. The PostgreSQL attack campaign

215 attacks, each asserting the specific rule that refused it rather than
merely that something failed. Grouped by what they attack:

| Group | Attacks | What they establish |
|---|---|---|
| `TestProposalStateMachine` | 45 | Every edge out of PREPARED permitted; every terminal status refuses further change; no order term editable, alone or hidden inside a legal status change; delete refused |
| `TestDecisionAdmission` | 27 | PREPARED-only, version and fingerprint match, one per proposal, action/status pairing, expiry only for approvals, append-only |
| `TestProposalTermConstraints` | 22 | Long-only, positive quantity, order-type/limit-price pairing, closed status set, digest shape, exit ordering, foreign keys |
| `TestConfigurationOrderingAndUniverse` | 21 | Expiry, entry-window and capital orderings; watchlist/prohibited overlap; blank identity; version uniqueness |
| `TestIntentCannotBecomeASubmission` | 20 | No submission state but NOT_SUBMITTED storable; no update; no delete; PREPARATION and DAY only; long-only; positive quantity |
| `TestIntentAdmission` | 19 | APPROVE-only, correct proposal, all three fingerprints agree, terms match, lapse and expiry, one per proposal, idempotency key |
| `TestRiskCheckEvidence` | 13 | Only PASSED storable; one row per check; ordinal uniqueness; foreign key; append-only |
| `TestEvaluationContextBinding` | 13 | A context requires an existing M083 watermark row; digest shape and width; non-negative count; zero is an honest state |
| `TestConfigurationClosedEnumerations` | 13 | Session, kill switch, order type and limit-price policy are closed sets |
| `TestConfigurationHardInvariantsInTheDatabase` | 12 | A leveraged, short-selling, overnight or PAPER/LIVE configuration is not storable — and the legal one is |
| `TestBypassAttempts` | 7 | Multi-row INSERT, INSERT…SELECT, CTE UPDATE, ON CONFLICT DO UPDATE, upsert resurrection, `pg_temp` shadowing, COPY |
| `TestFrozenMilestonesArePreserved` | 3 | M083's table still behaves as M083 specified and gained no columns |

### 3.1 The bypass attempts are the interesting ones

Each of these is a way a caller might reasonably expect to get around a
BEFORE ROW trigger, and each was executed against the live database:

- a **multi-row INSERT** with one good row and one bad — refused per row;
- an **INSERT … SELECT** cloning a stored proposal into a forbidden state;
- a **CTE-wrapped UPDATE** (`WITH bump AS (UPDATE …)`) — still an update;
- **ON CONFLICT DO UPDATE** attempting to edit terms, and a second attempting
  to resurrect a terminal proposal;
- a **`pg_temp` shadowing** attack: a same-named temp table holding a forged
  APPROVED row, which the intent trigger does not see because it reads
  `public.trade_proposal` under a pinned `search_path`;
- the **COPY path**, which refuses at the constraint like any other insert.

## 4. Anti-vacuity: the tests were verified to fail when the rules are weakened

A test that passes against a weakened implementation proves nothing. Two schema
mutations were applied, run, and reverted:

| Mutation | Expected | Observed |
|---|---|---|
| Widen `submission_state` CHECK to admit `'SUBMITTED'` | the SUBMITTED attack fails | **1 failed** — exactly `test_no_submission_state_but_not_submitted_can_be_stored[SUBMITTED]`. The other parametrized states are still refused, which is correct. |
| Remove the terminal-state guard from `trade_proposal_guard_update` | the terminal-transition matrix fails | **15 failed**, including the named revival case and the upsert-resurrection bypass |
| Restore both | all pass | **200 passed, 2 skipped** (count at the time of the campaign; 213/2 after the risk-check attacks were added) |

One architecture mutation was applied the same way:

| Mutation | Observed |
|---|---|
| Remove `"alpaca"` from `ORDER_SUBMISSION_PREFIXES` | **2 failed** — exactly the two alpaca fixture assertions. Restoring it: **7 passed**. |

## 5. End-to-end evidence

### 5.1 Against a live database, through the repositories

`test_m084_decision_to_approval_lifecycle.py` runs the whole flow —
configuration, context bound to a **real captured M083 watermark**, proposal,
decision, intent — and reads each back. The strongest single assertion in the
file: after a full round trip through PostgreSQL, the fingerprint recomputed
from the **read-back** terms still equals the one stored with them. If any
conversion had reshaped a price or a timestamp, that would not hold.

### 5.2 Through the CLI, against the live database

All eight commands were executed end to end. Observed output, unedited:

```
=== 1. save configuration ===
stored configuration CFG-CLI-0001 v1 [PREPARATION, kill switch DISENGAGED]
=== 2. open evaluation context ===
evaluation context ECX-CLI-0001
  configuration CFG-CLI-0001 v1
  watermark WM-CLI-0001 (0 receipts)
  receipt set digest 42775710256c74735a3d4c8fd7227b336ffb9d5cebc0a2f9a83024e85a5b3421
=== 3. prepare proposal ===
proposal PRP-CLI-0001 v1 [PREPARED]
  BUY 9 AAPL @ limit 200.10 (LIMIT)
  notional 1800.90 USD  fees 1.00  slippage 1.80
  total cash required 1803.70 USD
  stop 196.10  target 208.10
  fingerprint 8d45b76f1dfbefb0d1d54d05df66a7740b4d86db7e1a8ca5bcfdf9db81eab97e
  risk checks passed: 26
=== 5. approve ===
decision DEC-CLI-0001: APPROVE -> APPROVED
  by alice at 2026-06-10T12:00:30+00:00
=== 6. issue intent ===
order intent INT-CLI-0001 [NOT_SUBMITTED]
  BUY 9 AAPL @ limit 200.10 (LIMIT, DAY)
  requires account mode PREPARATION
  NOT SUBMITTED. MILESTONE-084 provides no way to send this to a broker.
```

The sizing is checked arithmetic, not a coincidence: budget = min(2000
per-trade cap, 20% of 10000) = 2000; floor(2000 / 200.10) = 9 shares;
9 × 200.10 = 1800.90; + 1.00 commission + 0.1% slippage (1.80) = 1803.70.

### 5.3 Migration

`alembic upgrade head` applies cleanly from an empty schema through all 21
migrations. A `downgrade -1` / `upgrade head` cycle was executed and the M083
watermark table and M082 receipt table survive it unchanged.

## 6. Regression against the baseline

Baseline, captured before any M084 work: **8 failed / 2497 passed / 718 skipped
/ 12 errors** with PostgreSQL disabled.

| Configuration | Result | Assessment |
|---|---|---|
| PostgreSQL **off** (the CI configuration) | 2753 passed, 8 failed, 12 errors | **Same 20 pre-existing failures**, in survivorship-study, validation-study and historical-import suites this milestone does not touch. Coverage gate passes. |
| PostgreSQL **on** | 3596 passed, 25 failed, 87 errors | See below. |

The PostgreSQL-on failures were investigated rather than assumed. Re-running
the identical command with this milestone's two integration files **excluded**
gives **the identical 25 failed and 87 errors** (3365 passed). The interference
is therefore pre-existing and not caused by this work: several integration
suites each `DROP SCHEMA public CASCADE` and re-migrate, and collide when run
together in one database. Run individually, all 264 M084 integration tests
pass.

### 6.1 Coverage

Adding this much code dropped the total to **78%**, below the 79% floor. The
floor was **not** lowered. Instead the repositories' row mapping and control
flow and the handlers' branching were unit-tested offline — following the
MILESTONE-083 REV-004 precedent that code reachable only through a live
database is untested wherever that database is absent, as it is in CI. The
total is back to **79%**.

## 7. What was not done

Stated so no reader over-reads this package.

- **The five formal hostile-review passes were not performed as separate,
  separately-documented passes.** Adversarial testing was done continuously and
  is what produced the three defects in Section 5 of `scope-and-design.md`, but
  it was not structured as the numbered passes the mission describes, and this
  document does not claim it was.
- **The 27-item mutation campaign was not completed.** Three mutations were
  executed (Section 4), chosen as the highest-value ones: the submission-state
  constraint, the terminal-state guard, and the order-submission deny-list. The
  remaining items were not run.
- **No concurrency campaign was run** against the M084 tables. The
  one-decision-per-proposal and one-intent-per-proposal rules are unique
  constraints, so concurrent writers race on the constraint and exactly one
  wins — but that has not been *measured* here, and it should be before the
  milestone is frozen.
- **No performance characterization was run.** No timing at any row count.
- **The four-mode regression was run in two modes** (PostgreSQL on and off),
  not four.
- **Phase C research could not read its primary sources.** The execution
  environment's egress proxy blocks the vendor domains; every claim in
  `broker-and-market-data-research.md` comes from search summaries and is
  labelled as such in that document's Section 0.
- **`PROJECT_CHECKPOINT.md` was not modified**, no merge was performed, and no
  freeze was performed. This is a candidate awaiting Owner review.
