# M082 - Validation Results

> **⚠ Superseded numbers below are from the previous pass.** The final authority
> hardening pass re-ran everything; its figures are in the "Hardening pass"
> section at the end of this file.

All measured after the Owner review correction pass. None quoted from a previous
run.

## Focused suites

| Suite | Before correction | **After correction** |
|---|---|---|
| M082 unit | 30 passed | **40 passed** |
| M082 PostgreSQL integration | 23 passed | **30 passed** |
| M082 fresh second pass | 4 passed | **4 passed** (dropped-and-recreated database) |
| M076-M082 compatibility chain | 435 passed | **522 passed** |

New tests added by this pass, all against real PostgreSQL unless noted:

| Test | Owner requirement |
|---|---|
| `test_a_receipt_created_after_the_cutoff_changes_nothing` | 1 — identical pre-W receipts, different post-W receipt tails |
| `test_an_event_created_after_the_cutoff_changes_nothing` | 2 — identical pre-W receipts, different future event tails |
| `test_no_count_in_the_artifact_is_aware_of_anything_after_the_cutoff` | 3 — no future receipt count leaks |
| `test_an_event_created_after_the_cutoff_changes_nothing` | 4 — no future event identity leaks |
| `test_a_backward_clock_breaks_the_wall_clock_implication` | 5 — application clock deliberately moves backward |
| `test_the_causal_claim_survives_the_backward_clock` | 6 — exact claim level remains true under that attack |
| `test_a_clock_returning_a_naive_datetime_is_refused` | 6 — a label with no offset names no instant |
| `test_production_wiring_uses_the_host_clock_and_takes_no_caller_instant` | 6 — the injection is not reachable from production |
| second pass, five-years-early lie | 7 — an old `recorded_at` lie creates no M082 authority |
| scenario E | 8 — legacy event remains unattested |
| scenario J | 9 — direct M076 bypass remains unattested |
| scenario I + second pass | 10 — concurrent receipt idempotency |
| scenario H, rollback tests | 11 — rollback/crash absence remains honest |
| `test_text_and_json_agree_and_json_is_deterministic` | 12 — text/JSON parity |
| frozen-preservation checks below | 13 — M079/M080/M081 unchanged |
| R02 table below | 14 — M076 test-only migration fix remains non-semantic |
| `test_a_receipt_labelled_after_the_cutoff_is_wholly_unreachable` (unit) | 1, structural |
| `test_the_report_carries_no_future_tail_count` (unit) | 3, structural |
| `test_no_artifact_surface_claims_an_upper_bound_or_a_knowledge_time` (unit) | claim-surface honesty |
| `test_the_old_overclaiming_names_are_gone` (unit) | the renames are load-bearing |
| `test_a_receipt_for_an_unsupplied_event_is_refused_not_skipped` (unit) | a missing referent is a fault, not an absence |

## Full regression, candidate vs master baseline `28a1053`

Measured by checking out the baseline SHA in the **same working tree** against
the **same PostgreSQL instance**, then diffing sorted failing-test-id lists.

| Mode | Baseline `28a1053` | Candidate | Failing-ID diff |
|---|---|---|---|
| PostgreSQL **on** | 24 failed, 2704 passed, 14 skipped, 44 errors | 24 failed, **2778** passed, 14 skipped, 44 errors | **empty** — 68 ids each side |
| PostgreSQL **off** | 8 failed, 2285 passed, 481 skipped, 12 errors | 8 failed, **2327** passed, 513 skipped, 12 errors | **empty** — 20 ids each side |

**+74 passing with PostgreSQL on, +42 with it off, zero new failures in either
mode.**

The pre-existing M062/M064/M065 seal debt remains, unrepaired and identical on
both sides of both diffs.

## Static gates

| Gate | Result |
|---|---|
| `compileall src tests tools migrations` | clean |
| `ruff check .` | All checks passed |
| `ruff format --check .` | 613 files already formatted |
| `python -m mypy` | Success, **312** source files |
| `tools/check_architecture.py .` | exit 0 |
| negative architecture fixture | exit **1** on seeded violations |

**No `# type: ignore`, no concealing `# noqa`, no gate suppression** in any M082
module.

> One lint finding in this pass, fixed rather than silenced: `N806`, an
> upper-case `W` local in the backward-clock test. Renamed to `cutoff`.

## Security and build

| Gate | Result |
|---|---|
| `pip-audit` | no known vulnerabilities |
| secret scan | **0 findings** |
| `python -m build` | sdist + wheel |
| wheel import | M082 imports from the built wheel in a clean Python 3.13 venv |
| console entry point | `empirical-platform-attested-evidence-snapshot` present |

## Migration verification

| Check | Result |
|---|---|
| `upgrade head` | table present, **0 rows**, trigger 1, function 1 |
| `downgrade -1` | table gone, trigger 0, function 0 |
| `upgrade head` again | table present, **0 rows**, trigger 1, function 1 |
| existing tables altered | **zero** |
| rows written by the migration | **zero** |

## End-to-end CLI

Run against a real seeded database with two events, **one** attested. The
snapshot lists exactly the attested event; the unattested one is **absent**, not
listed as unattested. The banner carries the retraction and the causal claim.
This is the check that caught M081's duplicated-denial defect, and it is why it
is run every milestone.

## Frozen preservation

Byte-identical to `28a1053`: `operator_position_ledger.py`,
`operator_evidence_availability.py`, `operator_asserted_round_trip.py`,
`operator_asserted_round_trip_ratio.py`, `same_day_capital_feasibility.py`,
`portfolio_aware_capital_feasibility.py`,
`research_decision_follow_through.py`.

None of M079, M080 or M081 references `operator_event_receipt`,
`events_with_receipt_labelled_by` or `system_received_at` — **no silent
adoption**, and after the correction that matters more, not less: this authority
is now explicitly weaker than a knowledge-time filter.

Non-M082 files changed: `pyproject.toml` (entry point), `runtime.py` (nine added
lines, no line removed), and the M076 reversibility test per R02.

## R02, re-verified this pass

| Requirement | Result |
|---|---|
| no M076 behavioural assertion changed | **confirmed** — the diff's only `assert` line is docstring prose |
| no test weakened | **confirmed** |
| only migration-target addressing changed | **confirmed** — `"-1"` → `"31365632c016"` |
| target is M076's own predecessor | **confirmed** — the literal `down_revision`; M076's own `revision` is `b7e1c4a95d38` |
| passes against M076 in isolation | **confirmed** — M082 migration removed, `alembic heads` = `b7e1c4a95d38 (head)`, test passes |
| passes with M082's migration present | **confirmed** — 16 passed |
| no production M076 code changed | **confirmed** |

## Evidence reconciliation sweep

Every phrase the Owner listed was searched across the whole branch — source,
tests, migrations, the root design document, the evidence package and the PR
body.

| Location | Action |
|---|---|
| M082 source, tests, design doc, evidence package | corrected, with the retracted claims **quoted** rather than deleted |
| `MILESTONE_005`, `MILESTONE_006` | **no change** — their "one-directional" is about Health/Logging dependency, unrelated |
| `external-review/MILESTONE-079/reality-gate.md` | **no change** — M079's own frozen snapshot claim, over `recorded_at`, still stands on its own terms |
| `tests/unit/test_decision_candidate_operator_asserted_round_trip.py` | **no change** — "upper bound" there is M080's forbidden-token list |

None of those four is touched by this branch.


---

# Hardening pass - final measured figures

## Focused suites

| Suite | Correction pass | **Hardening pass** |
|---|---|---|
| M082 unit | 40 | **40** |
| M082 PostgreSQL integration | 30 | **40** |
| M082 fresh second pass | 4 | **4** |
| M076-M082 compatibility chain | 522 | **532** |

Ten new PostgreSQL tests, one per Owner requirement:

| Test | Owner requirement |
|---|---|
| `test_a_same_transaction_event_and_receipt_is_refused_by_the_database` | 1 — same-transaction direct SQL attack |
| `test_a_savepoint_wrapped_same_transaction_insert_is_also_refused` (×2 depths) | 1 — subtransaction and nested-subtransaction variants |
| `test_rollback_to_savepoint_then_reinsert_is_still_refused` | 1 — retry variant |
| `test_a_direct_insert_for_an_already_committed_event_is_still_accepted` | 2, 3, 4 — direct INSERT, forged label, forged version |
| `test_a_concurrent_committed_writer_with_a_higher_xid_is_not_falsely_refused` | same-xid vs prior-xid, the false-rejection attack on the trigger |
| `test_the_repository_attest_path_still_works_under_the_trigger` | 5 — repository attest path causal guarantee |
| `test_immutability_is_row_level_update_delete_only` | immutability wording |
| `test_a_later_backdated_receipt_changes_the_same_cutoff` | 10 — same cutoff before/after a BACKDATED receipt |
| `test_a_later_forward_labelled_receipt_does_not_change_the_same_cutoff` | 11 — same cutoff before/after a forward-labelled receipt |

Requirements 6–9 and 12–15 are covered by the suites carried forward unchanged
(concurrency, rollback, legacy event, direct M076 bypass, text/JSON parity,
frozen-module preservation, migration up/down/up, M076 migration isolation).

## Migration verification, with two triggers

| Check | Result |
|---|---|
| `upgrade head` | table present, **0 rows**, **triggers 2**, **functions 2** |
| `downgrade -1` | table gone, triggers 0, functions 0 |
| `upgrade head` again | table present, **0 rows**, triggers 2, functions 2 |
| existing tables altered | **zero** |
| rows written by the migration | **zero** |

## Static gates

| Gate | Result |
|---|---|
| `compileall src tests tools migrations` | clean |
| `ruff check .` | All checks passed |
| `ruff format --check .` | 613 files already formatted |
| `python -m mypy` | Success, **312** source files |
| `tools/check_architecture.py .` | exit 0 |
| negative architecture fixture | exit **1** |
| secret scan | **0 findings** |

> One lint finding, fixed rather than suppressed: `S608`, SQL built by string
> interpolation in the new raw-SQL attack helpers. Rewritten to use bound
> parameters. **No `# noqa` was added.**

## Evidence reconciliation sweep, now a script over the whole tree

| | |
|---|---|
| RETRACTION-MARKED occurrences | **87** |
| ACTIVE occurrences | **8** — every one a denial or a heading naming the defect |

The sweep tool's own first run was wrong: it scanned `.venv` and reported 91
"active" hits, 83 of them `mypy`, `sqlalchemy` and `psycopg` discussing
type-variable and range upper bounds. Recorded rather than quietly fixed.


---

# Fail-closed pass - final measured figures

| Suite | Hardening pass | **Fail-closed pass** |
|---|---|---|
| M082 unit | 40 | **40** |
| M082 PostgreSQL integration | 40 | **44** |
| M082 fresh second pass | 4 | **4** |
| M076-M082 compatibility chain | 532 | **536** |

Four new PostgreSQL tests:

| Test | Owner attack |
|---|---|
| `test_an_unexpected_checker_error_fails_closed` | **8** — forced error in the status-check path, with a control proving the cause |
| `test_the_trigger_body_contains_no_broad_exception_handler` | 8, secondary — reads the INSTALLED `pg_proc` body |
| `test_a_frozen_event_row_is_still_accepted` | 6 — `VACUUM FREEZE`d event |
| `test_an_aborted_writers_event_is_never_visible_so_cannot_be_attested` | 7 — aborted writer semantics defined by measurement |

## Migration verification

| Check | Result |
|---|---|
| `upgrade head` | table present, **0 rows**, triggers 2, functions 2 |
| `downgrade -1` | table gone, triggers 0, functions 0 |
| `upgrade head` again | table present, **0 rows**, triggers 2, functions 2 |

## Static gates

`compileall` clean · `ruff check` passed · `ruff format --check` 613 files ·
`mypy` 312 source files · architecture exit 0 · negative fixture exit 1 ·
secret scan **0 findings**.

> One lint finding, fixed rather than suppressed: `S106`, a hardcoded password
> for the throwaway probe role. Replaced with `secrets.token_urlsafe(18)`
> generated per run and passed as a bound parameter. **No `# noqa` added.**

> **A sequencing error of my own:** I ran the focused M082 suite while the full
> regression was still using the same database, and got 11 spurious failures.
> Re-run after the regression completed. The collision was mine, not the code's.
