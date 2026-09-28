# Exact-SHA verification — durable reconciliation rounds and clock-safe waiting (Q-2 / Q-4)

Reviewed baseline: **`832b20b340f758726876fcd3181cd05d16e41de9`** (published; REV-R1/REV-R2 code
`e010075`).

CODE_CANDIDATE_SHA: **`093baf76773f3b2f6a24127e832a786371fa76a7`** (`093baf7`). Executable delta
`832b20b..093baf7` (25 files): `migrations/versions/a7d3c9e14f26_add_m085_reconciliation_round_journal.py`
(new), `src/empirical_platform/decision_candidate/paper_execution.py`,
`src/empirical_platform/decision_candidate/paper_execution_repositories.py`,
`src/empirical_platform/shared/persistence/postgres_repositories/paper_execution_repositories.py`,
`src/empirical_platform/usecases/paper_execution.py`, `src/empirical_platform/entrypoints/reconcile_paper_order.py`,
`tools/m085_paper_acceptance.py`, `tools/m085_mutation_campaign.py`, `tools/render_m085_authority.py`,
`.github/workflows/m085-temporal.yml`, the regenerated `current-authority.md`, and tests
(`tests/unit/test_m085_reconciliation_rounds.py`, `tests/integration/test_m085_reconciliation_rounds_postgres.py`
new; `_m085_fakes.py`, `_m085_support.py`, `_m085_crash_child.py` and eight existing M085 suites adapted
to the round semantics). One executable commit follows: **`c4cc3d05e36bee0c106f3cadf79a486d386558ac`**
(`c4cc3d0`; `tests/unit/test_m085_corrective_pass_handlers.py`, `tools/m085_mutation_campaign.py` —
a detecting test strengthened after R4 found one survivor, §3.1; no production code). Commits after
`c4cc3d0` are evidence-only.

Every run below executed on the exact commit `093baf7` with no executable file modified (`dirty` in
each log counts only the two documentation files edited under `external-review/` while the runs
proceeded). **Two early logs are invalid and are kept, labelled, for the record:** the first R1 and
the first R2 ran concurrently against the same disposable database, and every PostgreSQL module
rebuilds `public` from the full migration history, so they corrupted each other
(`R1-focused-INVALID-overlapped-with-R2.txt`: 10 failed / 1 error; `R2-postgres-INVALID-overlapped-with-R1.txt`:
7 failed / 5 errors). Both were rerun **alone**; the valid runs are `R1-focused.txt` and
`R2-postgres.txt`. Mutation chunks never overlapped another test run. No Alpaca endpoint was called;
PostgreSQL tests used the disposable database `m085_pgon_b24c471` (trust auth; the password variable
is the literal placeholder `trust-auth-placeholder-not-a-credential`).

## 1. Environment (printed)

Windows 11 Pro 10.0.26200; Python 3.13.14; pytest 9.1.1; psycopg 3.3.4 pinned `PSYCOPG_IMPL=python`
over libpq 16.0.13 (`impl python libpq 160013` printed in R3); SQLAlchemy 2.0.51; alembic 1.18.5;
PostgreSQL 16.13; detect-secrets 1.5.0; ruff 0.16.3; mypy 1.20.2. No CI has run on `093baf7` (not
pushed). The workflow `m085-temporal.yml` now lists both new suites and the fifteen new families.

## 2. Before — Q-2 / Q-4 on `832b20b` (published reproductions)

Reproduced in the PR #15 verification comment before this round, through the production handlers
and on PostgreSQL:

| Case | `832b20b` behaviour | `093baf7` behaviour (this round's tests) |
|---|---|---|
| Q-2. 404 → lookup raises **and** the failure-event write raises → restart → 404 | no durable trace of the failed round; the second 404 completed a "consecutive" pair → `REJECTED` | round 2 stays `STARTED`/incomplete; the third round records `RECONCILE_ROUND_INCOMPLETE`; `SUBMISSION_UNKNOWN` after 3, 300 and 400 s; 1 POST (unit `test_q2_a_failed_round_whose_outcome_write_fails…`; PostgreSQL across a fresh service `test_q2_double_failure_across_a_restart…`) |
| Q-2′. real child death inside the lookup after the round began | no record at all | the parent finds `[(1, None)]`, `died-at = during-reconciliation-lookup-after-round-begun`; a later 404 never resolves (`test_q2_a_real_child_death_after_the_round_began_leaves_it_incomplete`) |
| Q-2″. beginning the round fails | n/a (no round) | zero lookups, zero rounds, exception propagated (`test_q2_when_beginning_the_round_fails_no_lookup_is_made`) |
| Q-4a. 404 → failure by a reconciler lagging 120 s → 404 | the failure event sorted before the run by timestamp and was ignored → `REJECTED` | rounds `[(1, NOT_FOUND), (2, FAILED), (3, NOT_FOUND)]` by sequence; run = 1; `SUBMISSION_UNKNOWN` (unit both skews; PostgreSQL `test_q4_failure_by_a_skewed_reconciler_breaks_the_run_by_sequence`) |
| Q-4b. two 404s 10 broker-seconds apart, round 2 by a host whose clock leads by 120 s | `command.at − dispatched_at` = 130 s ≥ 60 → `REJECTED` | waiting lower bound = 10.0 s on the broker clock → `RECONCILE_NOT_FOUND_INSUFFICIENT`; resolves only 60 broker-seconds after the anchor (unit; PostgreSQL with a second `Clock` for process B) |
| Q-4c. 404 → 200 observed by a skewed reconciler → 404 | (REV-R1 already protected) | `PAPER_ACCEPTED`/bound with `broker-1` retained, `RECONCILE_NOT_FOUND_KNOWN_ORDER`, rounds `[NOT_FOUND, FOUND, NOT_FOUND]`, no resend (both skews, unit and PostgreSQL) |
| interval uncertainty straddling the threshold (anchor round trip 10 s) | not modelled | anchor `[t, t+10]`; at t+65 the bound is 55 s → refused; at t+70 the bound is 60 s → resolves |
| broker clock reading earlier than the anchor | not modelled | no interval (`None`), `RECONCILE_TIME_EVIDENCE_INSUFFICIENT`, unresolved |
| completed rounds without any broker interval (legacy-shaped rows) | n/a | `resolvable=False`, reason "no compatible broker-time evidence"; the same rows with intervals 60 s apart resolve |
| positive control: two clean 404 rounds 60 broker-seconds apart | `REJECTED / NOT_FOUND_AT_BROKER` | unchanged: `REJECTED / NOT_FOUND_AT_BROKER`, `RECONCILE_RESOLVED_NOT_FOUND`, 1 POST, 0 cancels (unit; PostgreSQL fresh service; after a `FAILED` clock-fetch round) |

## 3. Results on `093baf7`

| Stage | Scope | Result | Log |
|---|---|---|---|
| R1 focused (solo) | all `tests/unit/test_m085_*.py` (incl. reconciliation rounds 22, handlers 114, corrective-pass handlers 38, identity lineage 67, absence policy 6, domain 116) + PostgreSQL reconciliation rounds (15) + authority contract (71) | **971 passed** | `runs-093baf7/R1-focused.txt` |
| R2 PostgreSQL (solo) | all 13 `tests/integration/test_m085_*.py`: lifecycle, temporal, time basis, identity collision, pre-send crash (real child deaths), authority contract, **reconciliation rounds (15: guards, thread race, deterministic lock race, restart double-failure, child death R, skews, leading clock, interlopers ×3, migration down/up/up)**, absence policy restarts, corrective pass, concurrency, acknowledgement terms, hostile HTTP, send-boundary transport | **464 passed** in 5 min 54 s | `runs-093baf7/R2-postgres.txt` |
| R3 non-PostgreSQL full suite | `pytest` (root config, coverage on), PostgreSQL opt-in unset, libpq on PATH | **4145 passed, 0 failed, 1254 skipped** (all explicit opt-in gates: 779+27+20+9+9 PostgreSQL, 4 object storage); **coverage 80.35 % ≥ 79 %** (20 667 statements / 3 535 missed) | `runs-093baf7/R3-full-non-pg.txt` (+ `.raw`) |
| R4 mutations | **138 of 175** families: every family whose mutation target changed `832b20b..093baf7` (129: domain, usecases, repository, campaign-listed migration) or whose detecting-test file changed (9 more); five sequential chunks of ≤ 28, whole-tree SHA-256 before/after each | **137 / 138 detected; 1 SURVIVED** (`reconcile_absence_never_rejects_a_live_dispatch`, chunk 02 — see §3.1); digest `b96e298a8b997dd7…` identical before and after every chunk; tree clean after each | `runs-093baf7/mutation-chunk-0{0..4}.md`, `R4-chunk-0{0..4}.txt`, `affected-families.txt` |
| R5 static | compileall; ruff format `--check` (757 files); ruff check; mypy (368 files); architecture + negative fixture; frozen-path guard (M083 27 + M084 69 = 96, by blob id and diff); `tests/architecture` (41); authority renderers M082–M085 `--check`; M084 file audit (75); M085 exhaustion table `--check` (stale inventory as expected before regeneration); `scripts/security.ps1` (pip-audit clean; secret scan 1460 targets, none); `python -m build` | **green** | `runs-093baf7/R5-static.txt` |

### 3.1 The survivor on `093baf7`, and the follow-up commit `c4cc3d0`

`reconcile_absence_never_rejects_a_live_dispatch` replaces the handler's `if dispatch_may_be_live:`
with `if False:`. On `832b20b` that removal recorded `REJECTED` for a `SUBMISSION_IN_PROGRESS`
attempt, the order was then sent, and the acknowledgement write hit the immutable terminal row —
the family's expected fragment was `terminal and is immutable`. On `093baf7` the pure
`absence_evaluation` **also** refuses every state other than `SUBMISSION_UNKNOWN`, so the removed
branch no longer changes the decision: the attempt stays `SUBMISSION_IN_PROGRESS` and the order is
sent normally — **the rule the family names still holds**; what the branch alone provides is the
operator's reason, `RECONCILE_NOT_FOUND_DISPATCH_MAY_BE_LIVE`. The detecting test did not assert
that event, so the mutation survived. Not a surviving safety defect (the same test's state and
POST assertions passed with the rule removed *because* the second enforcement point held) but a
detection gap the campaign correctly refuses to call a pass.

Follow-up commit **`c4cc3d05e36bee0c106f3cadf79a486d386558ac`** (`c4cc3d0`), test and campaign
definition only (no production code): the detecting test asserts the event is recorded for both
not-found answers and that no `RECONCILE_NOT_FOUND_INSUFFICIENT` replaced it; the family's expected
fragment names that assertion. Pre-commit: 1/1 detected. Because seven other test modules import
helpers from the changed test file (one of them collected by R2), the re-verification on `c4cc3d0`
reran R1, R2, R3 and R5 in full and R4 for the **12 families whose detecting test lives in that
file**, strictly sequentially (`runs-c4cc3d0/`):

| Stage | Result on `c4cc3d0` | Log |
|---|---|---|
| R1 focused (solo) | **971 passed** | `runs-c4cc3d0/R1-focused.txt` |
| R2 PostgreSQL (solo) | **464 passed** (4 min 59 s) | `runs-c4cc3d0/R2-postgres.txt` |
| R3 non-PostgreSQL full suite | **4145 passed, 0 failed, 1254 skipped; coverage 80.35 % ≥ 79 %** | `runs-c4cc3d0/R3-full-non-pg.txt` |
| R4 the 12 families detected through `test_m085_corrective_pass_handlers.py` | **12 / 12 detected** (incl. `reconcile_absence_never_rejects_a_live_dispatch`); digest `a5c387a39f23ad22…` identical before and after; tree clean | `runs-c4cc3d0/mutation-chunk-00.md`, `R4-chunk-00.txt`, `affected-families.txt` |
| R5 static | **green** (same gates as on `093baf7`; the log's `dirty=2` counts the two documentation files under `external-review/` being edited during the run, nothing executable) | `runs-c4cc3d0/R5-static.txt` |

The other 126 families rerun on `093baf7` target production files that are byte-identical between
`093baf7` and `c4cc3d0` and detect through unchanged test files; their `093baf7` results stand for
`c4cc3d0` (same executable content).

Pre-commit mutation passes on the same content (uncommitted tree): the ten unit-targeted round
families plus the five REV-R1 families (two retargeted) → 13/15, then, after two test-side fixes
(a distinct event name for the `FOUND`-round anomaly so the positive-observation family detects the
lost event; assertion order in the pure missing-evidence test), 7/7 including the five
PostgreSQL-targeted families (`precommit-mutations-unit-targets.md`, `precommit-mutations-pg-targets.md`).
Both blockers were **test-design** findings, not surviving defects; they are recorded in README §6.

The 37 families not rerun target files byte-identical between `832b20b` and `093baf7` (adapter 11,
corrective-pass migration `9c4b2e7d5a18` 10, `paper_time.py` 5, basis migrations `d4f18a6c2e97` 4 and
`e61b3f9a4c27` 4, frozen-path guard 2, composition 1) **and** whose detecting-test file is unchanged
(corrective-pass PostgreSQL 10, hostile HTTP 9, time-basis PostgreSQL 8, paper-time unit 6, frozen
milestones 2, composition 1, acknowledgement terms 1). Their most recent results are historical (`e010075` round) and are
not claimed for this head.

## 4. Round ordering and crash outcomes (from the PostgreSQL logs)

- Sequence allocation: 8 concurrent services → sequences 1–8, no errors; deterministic pause race →
  `{slow: 1, fast: 2}`, journal `[(1, None), (2, None)]`.
- Real child death (`os._exit(3)`) after `begin` committed and inside the lookup: parent reads
  `[(1, None)]`; later 404 from a fresh service → `RECONCILE_ROUND_INCOMPLETE`, state unchanged.
- Completion twice → `ValueError("… already complete …")`, row unchanged; SQL `UPDATE` of outcome or
  sequence → trigger `… is immutable`; `DELETE` → `append-only`; insert already complete → `must begin
  incomplete`; foreign authorization → `does not describe attempt`; duplicate `(attempt_id, 1)` →
  `uq_paper_reconciliation_round_attempt_sequence`.
- Migration: at head, table + 3 triggers + 2 functions present and `alembic_version = a7d3c9e14f26`;
  downgrade to `9c4b2e7d5a18` removes all of them; upgrade restores them; a second upgrade is a no-op.

## 5. Elapsed-time derivation, assumptions, legacy behaviour

Stated in README §3 and in `RECONCILIATION_UNKNOWN_POLICY` (asserted by
`test_the_policy_states_its_round_and_time_semantics`). In one line: the bound is
`current_round.broker_earliest_at − anchor_round.broker_latest_at` where the anchor is the first
completed round carrying a broker interval; nothing is measured from the dispatch; nothing crosses
hosts; missing or contradictory evidence leaves the outcome unresolved; legacy acknowledgements
without rounds never count. The thresholds 2 / 60 s are unchanged **and the contract is not called
unchanged**: the authority rendering's claim sentences now name the round journal, the broker-clock
anchor and the assumptions (`tools/render_m085_authority.py`, `current-authority.md` regenerated,
`--check` green in R5).

## 6. Commits after the code candidate

| Commit | Content | Executable change |
|---|---|---|
| `c4cc3d0` | detecting test asserts the live-dispatch operator event; family fragment updated (§3.1) | tests + campaign definition only |
| (docs commit following `c4cc3d0`) | this record, `runs-093baf7/` and `runs-c4cc3d0/` logs, folder README, README pointer, superseding notes in `reconciliation-evidence-safety/verification.md` §5 | none |
| (docs commit following that) | `changed-files.txt` regenerated from `git diff --name-status <base>...HEAD` at that head; `exhaustion-table.md` rendered against it (V1 rows unchanged) | none |

## 7. Outcome

Q-2: **CLOSED AT THE ROOT** (durable STARTED round before any network work; FAILED completion; an
incomplete round blocks resolution; real child death and double-failure-across-restart tested on
PostgreSQL). Q-4: **CLOSED AT THE ROOT** (sequence-only ordering; broker-clock interval between two
rounds; atomic revalidation before the terminal write; both skew directions, both answer orders,
leading and lagging hosts tested on fakes and PostgreSQL). The withdrawn "one observation bound"
claim is superseded in `reconciliation-evidence-safety/verification.md` §5.

On the exact SHAs: `093baf7` — R1 971, R2 464, R3 4145 / 80.35 %, R5 green, R4 137/138 with one
survivor that was a detection gap (§3.1); `c4cc3d0` — R1 971, R2 464, R3 4145 / 80.35 %, R5 green,
R4 12/12 including the former survivor. Every affected family (138) is now detected on the
executable content of `c4cc3d0`.

Recommendation: **READY_FOR_OWNER_PUBLICATION_APPROVAL** — local commits only; not pushed; not
merged; not frozen; not OWNER_ACCEPTED; not READY_FOR_PAPER; Paper acceptance NOT_STARTED; M086
NOT_STARTED; V1 pending Owner ratification (its narrow correction is intact; this round regenerates
only the changed-file inventory and re-renders the table). No CI has run on either SHA. The
historical full-PostgreSQL baseline (3 failed / 43 errors) remains non-green and was not rerun.
