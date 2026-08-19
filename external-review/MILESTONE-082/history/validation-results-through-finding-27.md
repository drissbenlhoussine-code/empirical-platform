> **HISTORICAL RECORD — NOT CURRENT M082 AUTHORITY**
>
> Accumulated validation evidence for candidates up to and including finding
> 27. Superseded by the closure mission's `validation-results.md`.
>
> The single active statement of M082 authority is
> [`current-authority.md`](../current-authority.md).

# M082 - Validation Results

> **⚠ SUPERSEDED — this file describes an EARLIER candidate.**
> The authoritative latest correction is
> **`owner-correction-mission-findings-12-15.md`**. Where this file conflicts
> with it, that file wins. Nothing here is deleted: it is the record of what was
> believed at the time, including the parts that were wrong.


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

## Full regression, CORRECTION-PASS candidate vs master baseline `28a1053`

> These are the **correction-pass** figures (head `5be05bd`), retained as
> history. The figures for the final head `8415939` are in the fail-closed
> section at the end of this file.

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

> **⚠ THESE FIGURES WERE RE-MEASURED AT THE FINAL HEAD `8415939`.**
>
> An earlier version of this section reported the same numbers, but they had
> been measured **before** the `secrets` edit that introduced the `CREATE ROLE`
> defect — so they described neither the broken intermediate `6337ba4` nor the
> repaired final `8415939`. Reporting them as final was an evidence-consistency
> error, and it is corrected here rather than quietly overwritten. See
> `owner-review-fail-closed-pass.md` for the full causal sequence.
>
> Every figure below was taken with the working tree clean and identical to
> `841593946353f43cb3b75e5983b6f81e707a910a`.

| Suite | Hardening pass | **Fail-closed pass, measured at `8415939`** |
|---|---|---|
| M082 unit | 40 | **40 passed** |
| M082 PostgreSQL integration | 40 | **44 passed** |
| M082 fresh second pass | 4 | **4 passed** |
| M076-M082 compatibility chain | 532 | **536 passed** |

## Full regression at `8415939`, candidate vs master baseline `28a1053`

Same working tree, same PostgreSQL instance, sorted failing-test-id lists diffed.

| Mode | Baseline `28a1053` | Candidate `8415939` | Failing-ID diff |
|---|---|---|---|
| PostgreSQL **on** | 24 failed, 2704 passed, 14 skipped, 44 errors | 24 failed, **2792** passed, 14 skipped, 44 errors | **empty** - 68 ids each side |
| PostgreSQL **off** | 8 failed, 2285 passed, 481 skipped, 12 errors | 8 failed, **2327** passed, 527 skipped, 12 errors | **empty** - 20 ids each side |

> **The regression run that mattered most is the one that FAILED.** Against the
> broken intermediate `6337ba4` the PostgreSQL-on run returned **25 failed** and
> a diff of **69 vs 68 ids**, with exactly one extra entry:
>
> ```
> > FAILED tests/integration/test_m082_operator_event_receipt_lifecycle.py::test_an_unexpected_checker_error_fails_closed
> ```
>
> That single line is what exposed the `CREATE ROLE` defect after it had already
> been misdiagnosed as a database-suite collision. The empty diff above is from
> the re-run at `8415939`.

## CI

| Head | Run | Result |
|---|---|---|
| `8415939` | `32013982326` | **success**, 14/14 steps green |

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
> for the throwaway probe role.
>
> **⚠ SUPERSEDED — this described the BROKEN INTERMEDIATE `6337ba4`.** That fix
> used `secrets.token_urlsafe(18)` passed as a **bound parameter**, and a bound
> parameter is exactly what `CREATE ROLE` cannot take. The final implementation
> at `8415939` uses **`secrets.token_hex(24)` interpolated directly** — hex
> cannot contain a quote, so interpolation is safe by construction. `S106`
> remains clean and **no `# noqa` was added** in either version.

> **A sequencing error of my own:** I ran the focused M082 suite while the full
> regression was still using the same database, and got 11 spurious failures.
>
> **⚠ That explanation was INCOMPLETE, and the incompleteness mattered.** The
> collision was real, but it was masking a defect I had introduced in the same
> edit — see the causal sequence in `owner-review-fail-closed-pass.md`. The full
> regression caught it as one extra failing ID.

---

# AUTHORITATIVE FINAL SECTION — Owner correction mission, findings 12–15

**Everything above this line describes an EARLIER candidate.** These are the
figures for the current head. Measured with the working tree clean.

| | |
|---|---|
| HEAD | **the commit containing this file** — see below |
| base master | `28a10530dbc295fedacfa89c8aef246b35a0b86e` |
| PostgreSQL | **16.13** |
| console command | **`empirical-platform-receipt-label-cutoff-view`** |

> **On naming the head.** An earlier draft of this section hard-coded a commit
> hash, which went stale the moment the commit was amended — the same
> evidence-drift class as Owner finding 15, reproduced by me one paragraph after
> writing the fix for it. A commit cannot contain its own hash, so this section
> identifies the head as "the commit containing this file" and the exact SHA is
> reported in the delivery report and on PR #12. The figures below were measured
> with the working tree clean and identical to that commit's tree.
>
> **RETRACTED / SUPERSEDED above:** `8415939` is **not** the final head; the old
> console entry point `empirical-platform-attested-evidence-snapshot` and the old
> flag `--attested-as-of` are **withdrawn**; the "true receipt-cutoff snapshot"
> framing is **withdrawn** (owner findings 5 and 11).

## Focused suites

| Suite | Result |
|---|---|
| M082 unit | **40 passed** |
| M082 PostgreSQL lifecycle | **91 passed** |
| M082 fresh second pass | **4 passed** |
| M076–M082 compatibility chain | **583 passed** |

## Migration up / down / up

| Check | Result |
|---|---|
| `upgrade head` | table present, **0 rows**, triggers **2**, functions **2**, CHECK constraints **4** |
| `downgrade -1` | table gone, triggers 0, functions 0, checks 0 |
| `upgrade head` again | table present, **0 rows**, triggers 2, functions 2, checks 4 |

## M076 isolation

| Check | Result |
|---|---|
| M082 migration removed → `alembic heads` | `b7e1c4a95d38 (head)` |
| M076 reversibility test in isolation | **1 passed** |
| full M076 suite with M082 present | **16 passed** |

## Full regression vs master `28a1053`

| Mode | Baseline | Candidate | Failing-ID diff |
|---|---|---|---|
| PostgreSQL **on** | 24 failed, 2704 passed, 14 skipped, 44 errors | 24 failed, **2839** passed, 14 skipped, 44 errors | **EMPTY** — 68 ids each side |
| PostgreSQL **off** | 8 failed, 2285 passed, 481 skipped, 12 errors | 8 failed, **2327** passed, 574 skipped, 12 errors | **EMPTY** — 20 ids each side |

**+135 passing with PostgreSQL on, +42 with it off. Zero new failures.**

## Static, security and build

| Gate | Result |
|---|---|
| `compileall src tests tools migrations` | clean |
| `ruff check .` | All checks passed |
| `ruff format --check .` | 613 files already formatted |
| `python -m mypy` | Success, 312 source files |
| architecture checker | exit 0 |
| negative architecture fixture | exit 1 |
| `pip-audit` | ran, no known vulnerabilities |
| secret scan | **0 findings** |
| `python -m build` | sdist + wheel |
| clean-venv wheel import | OK |
| console entry point in wheel | **`empirical-platform-receipt-label-cutoff-view`** |

**No suppressions anywhere.**

## CI

| Head | Run | Result |
|---|---|---|
| the commit containing this file | reported in the delivery report and on PR #12 | reported there |

> A CI run id cannot exist before the commit that triggers it, so it cannot be
> written into that same commit. It is reported alongside the head SHA rather
> than fabricated here.
>
> **Recorded, not hidden:** an earlier version of this row carried a stale hash
> and two unfilled `<CI_RUN>` / `<CI_RESULT>` placeholders, because my token
> substitution ran before the edit that was meant to replace them. Two separate
> self-referential-stamp mistakes in one file, immediately after correcting
> Owner finding 15 about exactly this drift.


---

# AUTHORITATIVE FINAL SECTION — Owner correction mission, findings 16–18

**Everything above this line, including the previous "authoritative final
section", describes an EARLIER candidate.** Measured with the working tree clean.

| | |
|---|---|
| HEAD | the commit containing this file — SHA reported in the delivery report and on PR #12 |
| base master | `28a10530dbc295fedacfa89c8aef246b35a0b86e` |
| PostgreSQL | **16.13** |
| console command | **`empirical-platform-receipt-label-cutoff-view`** |

## Focused suites

| Suite | Result |
|---|---|
| M082 unit | **40 passed** |
| M082 PostgreSQL lifecycle | **181 passed** |
| M082 fresh second pass | **4 passed** |
| M076–M082 compatibility chain | **673 passed** |

The lifecycle suite grew from 91 to 181 because the blank attack is now
parametrised over **30 cases × 4 persisted columns = 120 executed CHECK
attacks**, plus the sanctioned command/domain rejection and provenance sweeps.

## Migration up / down / up

```
after up     table=yes rows=0 triggers=2 functions=2 checks=4
after down   table=NO  rows=None triggers=0 functions=0 checks=0
after up#2   table=yes rows=0 triggers=2 functions=2 checks=4
```

## Full regression vs master `28a1053`

| Mode | Baseline | Candidate | Failing-ID diff |
|---|---|---|---|
| PostgreSQL **on** | 24 failed, 2704 passed, 14 skipped, 44 errors | 24 failed, **2929** passed, 14 skipped, 44 errors | **EMPTY** — 68 ids each side |
| PostgreSQL **off** | 8 failed, 2285 passed, 481 skipped, 12 errors | 8 failed, **2327** passed, 664 skipped, 12 errors | **EMPTY** — 20 ids each side |

**+225 passing with PostgreSQL on, +42 with it off. Zero new failures.**

## Static, security and build

`compileall` clean · `ruff check` passed · `ruff format --check` 613 files ·
`mypy` 312 source files · architecture exit 0 · negative fixture exit 1 ·
secret scan **0 findings**. **No suppressions.**

## CI

Reported in the delivery report and on PR #12. A commit cannot contain the id of
the run it triggers.


---

# AUTHORITATIVE FINAL SECTION — Owner residual correction, findings 17–19

**Supersedes every section above, including the previous "authoritative final
section".** Measured with the working tree clean.

| Suite | Result |
|---|---|
| M082 unit | **40 passed** |
| M082 PostgreSQL lifecycle | **182 passed** |
| M082 fresh second pass | **4 passed** |
| M076–M082 compatibility chain | **674 passed** |

| Mode | Baseline `28a1053` | Candidate | Failing-ID diff |
|---|---|---|---|
| PostgreSQL **on** | 24 failed, 2704 passed, 44 errors | 24 failed, **2930** passed, 44 errors | **EMPTY** — 68 ids each side |
| PostgreSQL **off** | 8 failed, 2285 passed, 12 errors | 8 failed, **2327** passed, 12 errors | **EMPTY** — 20 ids each side |

**Gates:** `compileall` clean · `ruff check` passed · `ruff format --check` 613
files · `mypy` 312 source files · architecture exit 0 · negative fixture exit 1 ·
secret scan **0 findings**. No suppressions.

## Installed-constraint proof, strengthened

Containment was not enough — a trim set with an **extra** character still
contains all 29, so "contains" would have passed even with the `\v`-escape bug
that once produced the letter `v`. Each installed CHECK's trim set is now
extracted, resolved **by PostgreSQL itself**, and compared for **exact
equality** with the frozen 29.

**Negative control, executed:** injecting `\x76` (`v`) into the migration's set
makes **both** the equality test and the `v`/`valve`/padded control test **fail**.
The migration was restored immediately afterwards.

## CI

Reported in the delivery report. A commit cannot contain the id of the run it
triggers, and the PR body is updated separately after the push and after CI.

---

## Owner final micro-correction mission — findings 20–21

Executed on the corrected working tree, starting head `2ce4135`, base `master`
`28a1053`. Full detail in `owner-correction-mission-findings-20-21.md`.

| Gate | Result |
|---|---|
| M082 unit suite | 40 collected, **40 passed** |
| M082 PostgreSQL lifecycle | 187 collected, **187 passed** (was 182: −1 replaced, +4 parametrised, +2 source sweeps) |
| Fresh second pass, schema dropped and re-upgraded | **187 passed** |
| `test_m082_operator_event_receipt_second_pass.py` | **4 passed** |
| M076–M082 chain, 13 integration files | **311 passed** |
| M076–M082 chain, unit surface | **357 passed** |
| Migration up → down → up | clean |
| Installed trim set per CHECK | `receipt_id`, `event_id`, `attested_by`, `attester_version` — **29 characters each** |
| `git diff --check` | clean |
| `compileall` | clean |
| `ruff format --check` | 613 files formatted |
| `ruff check` | all checks passed |
| `mypy src` | no issues, 311 source files |
| `tools/check_architecture.py .` | exit 0 |
| Negative architecture fixture | exit 1, as required |
| Secret scan | 1135 targets, **0 findings** |
| Suppressions introduced | **none** |

### Negative controls, both executed

* **Source provenance sweep.** Pre-correction domain module restored from
  `2ce4135` → `test_no_m082_source_file_asserts_generic_metadata_origin` FAILS
  and names all four defects. Corrected module restored → passes.
* **Installed trim set.** `r"\x76"` (letter `v`) appended to the migration's
  frozen set → exact-set equality FAILS with `extra=['v']`, and **all four**
  parametrised per-column control cases FAIL, each refused by its own named
  CHECK constraint. Migration restored immediately; `grep -c x76` returns `0`.

### Regression comparison, baseline re-derived in the same working tree

| Run | Result | Failing ids |
|---|---|---|
| Baseline `2ce4135`, PG-ON | 24 failed, 2930 passed, 14 skipped, 44 errors | 68 |
| Corrected, PG-ON | 24 failed, 2935 passed, 14 skipped, 44 errors | 68 |
| Baseline `2ce4135`, PG-OFF | 8 failed, 2327 passed, 665 skipped, 12 errors | 20 |
| Corrected, PG-OFF | 8 failed, 2329 passed, 668 skipped, 12 errors | 20 |

**Both sorted failing-ID diffs are EMPTY.**

### Production behaviour diff

Every changed production and migration file compared against `2ce4135` as a
docstring-stripped AST: **IDENTICAL** in all five.
`NON-STRING/NON-COMMENT PRODUCTION BEHAVIOUR DIFF: EMPTY`.

## CI

Reported in the delivery report. A commit cannot contain the id of the run it
triggers, and the PR body is updated separately after the push and after CI.

---

## Owner residual claim-surface correction — findings 22–23

Executed on the corrected working tree, starting head `9b487d1`, base `master`
`28a1053`. Full detail in `owner-correction-mission-findings-22-23.md`.

| Gate | Result |
|---|---|
| M082 unit suite | 40 collected, **40 passed** |
| M082 PostgreSQL lifecycle | 188 collected, **188 passed** (was 187: −1 replaced sweep, +2 new) |
| Fresh second pass, schema dropped and re-upgraded | **188 passed** |
| `test_m082_operator_event_receipt_second_pass.py` | **4 passed** |
| M076–M082 chain, 13 integration files | **312 passed** |
| M076–M082 chain, unit surface | **357 passed** |
| Migration up → down → up | clean |
| Installed trim set per CHECK | 29 characters each, all four |
| `git diff --check` | clean |
| `compileall` | clean |
| `ruff format --check` | 613 files formatted |
| `ruff check` | all checks passed |
| `mypy src` | no issues, 311 source files |
| `tools/check_architecture.py .` | exit 0 |
| Negative architecture fixture | exit 1, as required |
| Secret scan | **1140 targets** at the new head (1139 at `7ed953a`, 1138 at `b879147`, 1137 at `fc550f7`), **0 findings** |

### Suppressions — the exact delta-scoped claim

**"No suppressions anywhere" is RETRACTED as false.** Measured as
`git diff master` restricted to `src`, `migrations`, `tests`, `tools`:

| Scope | Count |
|---|---|
| Production + migration | **2** (one `pragma: no cover` on an unreachable defensive branch; one `noqa: E501` on a long import) |
| Tests | **16** (11 `noqa` — 7 `ANN202`, 2 `BLE001`, 1 `E501`, 1 `ANN001` — and 5 `type: ignore`) |
| **M082 delta total** | **18** |
| Introduced by findings 22–23 | **0** |
| Repository-wide pre-existing baseline | 872 occurrences, untouched |

> **⚠ RETRACTED (owner finding 25).** The sentence that stood here read: *"No
> suppression silences a failing gate, and no test is skipped or xfailed."* The
> second half is **FALSE**. CI reports skipped tests, and both M082 PostgreSQL
> fixtures call `pytest.skip()` when the explicit opt-in is absent — measured
> PG-off, the two M082 PostgreSQL suites report **5 passed, 187 skipped**.

No suppression silences a failing gate. **No M082 test is xfailed or
unconditionally skipped** (measured: zero `xfail`, zero `skipif`, zero
`@pytest.mark.skip` across the three M082 test files). PostgreSQL-dependent
fixtures **conditionally skip** when explicit PostgreSQL opt-in is absent. **No
failing finding is concealed by skip or xfail.** This statement is scoped to
M082's own tests and does **not** deny that the repository at large, or any
PG-off run, reports skips — both do.

### Negative controls, both executed

* **Claim sweep, paragraph-locality.** The exact phrase finding 22 removed from
  §23 — `The system_received_at column records the attestation instant.` — is
  appended to the real design file in its own paragraph. The sweep catches it and
  the file is restored in a `finally` block.
* **The control discriminates.** With the exemption temporarily made
  **file-scoped**, the same control reports
  `AssertionError: the sweep did NOT catch an injected unscoped claim / assert []`
  — the weakness the Owner named, demonstrated rather than asserted. Restored,
  both sweep tests pass.

### Regression comparison, baseline re-derived in the same working tree

| Run | Result | Failing ids |
|---|---|---|
| Baseline `9b487d1`, PG-ON | 24 failed, 2935 passed, 14 skipped, 44 errors | 68 |
| Corrected, PG-ON | 24 failed, 2936 passed, 14 skipped, 44 errors | 68 |
| Baseline `9b487d1`, PG-OFF | 8 failed, 2329 passed, 668 skipped, 12 errors | 20 |
| Corrected, PG-OFF | 8 failed, 2330 passed, 668 skipped, 12 errors | 20 |

**Both sorted failing-ID diffs are EMPTY.**

### Production behaviour diff

Only one production file changed (`usecases/attest_operator_event_receipt.py`,
docstring only) and `migrations/` is **byte-identical** to `9b487d1`.
Docstring-stripped AST comparison: **IDENTICAL**.
`PRODUCTION BEHAVIOUR DIFF: EMPTY`. The Finding-21 per-column control tests are
untouched.

## CI

Reported in the delivery report. A commit cannot contain the id of the run it
triggers, and the PR body is updated separately after the push and after CI.

---

## Owner findings 24–25 correction

Full detail: `owner-correction-mission-findings-24-25.md` (authoritative latest).

**Scope:** documentation and tests only. `migrations/` byte-identical to
`fc550f7`; the two changed production files have an **empty behavior delta**,
proven by comparing their docstring-stripped ASTs against `fc550f7` (both
IDENTICAL).

| Gate | Result |
|---|---|
| M082 unit | 40 collected, **40 passed** |
| M082 PostgreSQL lifecycle | 189 collected, **189 passed** |
| M082 fresh second pass | 4 collected, **4 passed** |
| M076–M082 compatibility chain | **471 passed** |
| Claim sweep + paragraph-locality + 3 new class controls | **4 passed** |
| Migration up / down / up | `d9a2f5c81b73` → `b7e1c4a95d38` → `d9a2f5c81b73`, clean |
| `compileall` / `ruff format --check` / `ruff check` | OK / 613 formatted / all passed |
| `mypy src` | no issues in 311 source files |
| architecture checker / `git diff --check` | clean / clean |
| Secret scan | **1138 targets**, **0 findings** |

**Sweep strengthened** from one banned family to five: origin/label-as-instant,
upper-bound/commit-by-label, historical/knowledge snapshot, removed status
names, removed API/CLI names. The two assertive families accept an honest
negation; the two removed-name families do not.

**Three executed negative controls**, each injected independently into the real
active design in its own unmarked paragraph, each caught, each restored:
`upper bound witness`, `NO_SYSTEM_RECEIPT_EVIDENCE`, `--attested-as-of`.
An anti-vacuity probe blinded one family and confirmed the matching control
**fails** when the sweep cannot see the phrase.

---

## Owner finding 26 correction

Full detail: `owner-correction-mission-finding-26.md` (authoritative latest).

**Scope:** documentation and tests only. `migrations/` byte-identical to
`b879147` — no migration edit was required. Production changes are comment- and
docstring-only, with the **emitted artifact text proven identical by evaluating
`ATTESTED_EVIDENCE_BANNER`, `_LIMITATIONS` and `BLANK_CHARACTERS` in both
versions and comparing values**, not merely by reading the diff.

Six laundering bypasses were reproduced against `b879147` and the exemption
model was rebuilt on structural rules: banner-governed blockquote runs,
banner-governed fenced blocks, paragraphs whose **first** line is a banner,
banner lines themselves, explicit **line-local** annotations, and negation that
**grammatically governs** the phrase it exempts. The paragraph-wide
`recorded_at` / `operator-supplied` exception is deleted.

| Gate | Result |
|---|---|
| M082 unit | 40 collected, **40 passed** |
| M082 PostgreSQL lifecycle | 192 collected, **192 passed** |
| M082 fresh second pass | 4 collected, **4 passed** |
| Complete claim-sweep suite | 7 collected, **7 passed** |
| M076–M082 compatibility chain | **474 passed** |
| `compileall` / `ruff format --check` / `ruff check` | OK / 613 files / all passed |
| `mypy src` | no issues in 311 source files |
| architecture / negative fixture | exit 0 / exit 1 |
| `python -m build` | wheel built |
| `git diff --check` | clean |

**Six negative controls**, all caught independently. **Five positive controls**,
all accepted. **Anti-vacuity probe on both new rules**: weakening negation to
"any negator on the line" launders attack 2; weakening the banner to "any
substring" launders attack 4; restoring each rule catches each again.

---

## Owner finding 27 correction

Full detail: `owner-correction-mission-finding-27.md` (authoritative latest).

**SUPERSEDED — the finding-26 green sweep result.** Five exemption-grammar
bypasses were executed against `7ed953a` and **all five returned zero
offenders**. A sweep reporting zero proves only that its grammar accepted the
surface. That has now been true three reviews running and is recorded, not
smoothed over.

The exemption grammar was tightened to match its documented contract: a
blockquote is governed only when its **first** content line is a banner; the two
annotation forms are exact (`# BANNED-TERM` as a real Python COMMENT token,
`<!-- QUOTED-DEFECT -->` complete), and the undocumented `(QUOTED-DEFECT)`
parenthetical is abolished as a marker — **17 occurrences across 5 files**, all
re-scoped structurally; banner tokens must end on a boundary, so `REMOVEDLY` is
prose; and negators are lexical tokens, so `not` inside `knot` governs nothing.

| Gate | Result |
|---|---|
| M082 unit | 40 collected, **40 passed** |
| M082 PostgreSQL lifecycle | 195 collected, **195 passed** |
| M082 fresh second pass | 4 collected, **4 passed** |
| Complete claim-sweep suite | 10 collected, **10 passed** |
| M076–M082 compatibility chain | **477 passed** |
| Migration up / down / up | clean (migrations byte-identical) |
| `compileall` / `ruff format --check` / `ruff check` | OK / 613 files / all passed |
| `mypy src` | no issues in 311 source files |
| architecture / negative fixture | exit 0 / exit 1 |
| dependency audit / build | no actionable finding / wheel built |

**Five negative controls**, all caught independently. **Five positive controls**,
all accepted, including the contrast that the same Python line *without* its
comment token is caught. **Four anti-vacuity mutations — one per structural rule
— each laundering its own attack when the rule is reverted.**
