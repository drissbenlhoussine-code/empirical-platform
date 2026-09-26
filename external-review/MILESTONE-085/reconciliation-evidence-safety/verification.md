# Exact-SHA verification — reconciliation evidence safety (REV-R1) and strict boundary parsing (REV-R2)

Reviewed baseline: **`e7a089a06c518800682b232b8719d6f05e4224a2`** (published; L1 code `806896b`, V1
renderer `05eec31`). Preserved local parent: **`94ffe908067e3b5bf10753352afe0abeaf258b24`** (the
24 → 21 count correction; rides with this candidate).

CODE_CANDIDATE_SHA: **`e010075a6e63c990c45174425b4d03e4fb0459b9`** (`e010075`). Executable delta
`806896b..e010075`: `src/empirical_platform/decision_candidate/paper_execution.py`,
`src/empirical_platform/usecases/paper_execution.py`, `tools/m085_mutation_campaign.py`,
`tools/render_m085_exhaustion_table.py` (the V1 correction, `05eec31`), `.github/workflows/m085-temporal.yml`,
and tests (`tests/unit/test_m085_absence_policy.py`, `tests/unit/test_m085_boundary_binding_parser.py`,
`tests/integration/test_m085_absence_policy_postgres.py` new; `tests/unit/test_m085_paper_execution_handlers.py`
modified). Commits after `e010075` are evidence-only, verified per commit.

All commands ran in the foreground, one at a time, on a clean tree at `e010075` (`dirty=0` in every
log under `runs-e010075/`). Mutation chunks never overlapped another test run. No Alpaca endpoint was
called; PostgreSQL tests used the disposable database `m085_pgon_b24c471`.

## 1. Environment (printed)

Windows 11 Pro 10.0.26200; Python 3.13.14; pytest 9.1.1; psycopg 3.3.4 pinned `PSYCOPG_IMPL=python`
over libpq 16.0.13 (`impl python libpq 160013` printed in R2/R3); SQLAlchemy 2.0.51; alembic 1.18.5;
PostgreSQL 16.13 (trust auth for the disposable role; the password variable is the literal
placeholder `trust-auth-placeholder-not-a-credential`); detect-secrets 1.5.0; ruff 0.16.3;
mypy 1.20.2. No CI has run on `e010075` (not pushed).

## 2. Reproduction (before any edit; executable content of `e7a089a`)

| Path | Result | Log |
|---|---|---|
| unit, production handlers over fakes (`tests/unit/test_m085_absence_policy.py`) | 4 failed (A, A′, B, C) / 2 passed (positive controls) | `rev/unit-reproduction-on-e7a089a.txt` |
| per-step facts (state, code, broker id, terminal, POSTs, acknowledgement sequence, events, reconcilability) | A/A′/B/C all end `REJECTED` / `NOT_FOUND_AT_BROKER`, terminal, no later reconciliation; POSTs A/A′/B = 1, C = 0 | `rev/facts-on-e7a089a.txt` |
| PostgreSQL, fresh persistence service per process (`tests/integration/test_m085_absence_policy_postgres.py`) | A, B, C all `REJECTED NOT_FOUND_AT_BROKER` after restart | `rev/postgres-reproduction-on-e7a089a.txt` |

**REV-R1: REPRODUCED** through production paths and across restarts (details: README §1). REV-R2 was
reproduced by the parser's own negative tests (all failing on the old `_binding_fields`: duplicates
overwrote, malformed tokens were skipped, unknown fields ignored); see README §2.

## 3. Results on `e010075`

| Stage | Scope | Result | Log |
|---|---|---|---|
| R1 focused | absence policy (6), binding parser (40), pre-send crash (21), send boundary (19), identity lineage (67), identity collision, handlers (incl. the rewritten reconcile tests), corrective pass (domain + handlers), domain, entrypoints, exhaustion-table rows (20), hostile HTTP (125), acknowledgement terms (15), send-boundary transport (2) | **887 passed** | `runs-e010075/R1-focused.txt` |
| R2 PostgreSQL | **absence policy restarts (3)**, pre-send crash (3, real child death), temporal 7, time-basis 48, lifecycle 57, concurrency 49, corrective pass 62, identity collision 7, authority contract 71, M084 file audit 23 | **330 passed** | `runs-e010075/R2-postgres.txt` |
| R3 non-PostgreSQL full suite | `pytest tests`, PostgreSQL opt-in unset | **4122 passed, 0 failed, 1239 skipped** (all opt-in gates; +3 = the new PostgreSQL absence tests); **coverage 80.45 % ≥ 79 %** (20 474 statements / 3 483 missed) | `runs-e010075/R3-full-non-pg.txt` |
| R4 mutations | **110** families: 109 whose target file changed `806896b..e010075` (domain, usecases — incl. the 7 new) + `claim_time_after_lock` (target unchanged, detecting test file changed); five sequential chunks, whole-tree SHA-256 before/after | **110 / 110 detected**; digest `cbb5318236d04147…` identical before and after every chunk; tree clean after each | `runs-e010075/mutation-chunk-0{0..4}.md`, `R4-chunk-0{0..4}.txt`, `affected-families.txt` |
| R5 static | compileall; ruff format `--check` (754 files); ruff check; mypy (368); architecture + negative fixture; frozen-path guard (M083 27 + M084 69 = 96); architecture/frozen/base-pin tests (54); authority renderers M082–M085 `--check`; M084 file audit (75); `scripts/security.ps1` (venv interpreter; pip-audit clean; secret scan 1441 targets, none); build | **green** | `runs-e010075/R5-static.txt` |

Pre-commit on the same content (uncommitted tree): PostgreSQL suites 329 passed + 1 failure that
was a **real defect in the correction** — the `RECONCILE_NOT_FOUND_INSUFFICIENT` event id was keyed on
the observation count, which repeats once a run is broken (`EVT-…-RECON-404-1` twice → primary-key
violation in PostgreSQL; the fakes cannot see it). Fixed by keying absence-event ids on the
acknowledgement sequence (`rev/pg-suites-on-corrected-worktree.txt`). Pre-commit mutation passes:
16/18 then, after two detecting-test ids containing spaces were slugged (pytest cannot resolve such
node ids from the command line — a fixture error, not an invariant result), 2/2
(`rev/precommit-mutations.md`, `rev/precommit-mutations-parser.md`).

The 50 families not rerun target files byte-identical between `806896b` and `e010075` (adapter 11,
paper_time 6, persistence 4, migrations 23, composition 1, frozen guard 2, authority 3) and their
detecting test files are unchanged. Historical results (`134/134` on `2726f6f`, `109/109` on
`00716e4`, `102/102` on `806896b`) are not claimed for this head.

## 4. Corrected behaviour — the four cases on `e010075`

| Case | State after the sequence | broker_order_id | Events added | POSTs | Reconcilable |
|---|---|---|---|---|---|
| A. 404 → 500 → 404 | `SUBMISSION_UNKNOWN` (cause unchanged) | None | `RECONCILE_NOT_FOUND_INSUFFICIENT` ×2, `RECONCILE_UNUSABLE_ANSWER` | 1 | yes; a consecutive second 404 then resolves it (`REJECTED` / `NOT_FOUND_AT_BROKER`) |
| A′. 404 → raise → 404 | `SUBMISSION_UNKNOWN` | None | `RECONCILE_LOOKUP_FAILED` (exception re-raised), run restarts at 1 | 1 | yes |
| B. accepted, 404 → 404 | `PAPER_ACCEPTED` | `broker-1` retained | `RECONCILE_NOT_FOUND_KNOWN_ORDER` ×2 | 1 | yes; a later found `filled` → `FILLED` |
| C. unresolved identity, 404 → 200 observed → 404 | `SUBMISSION_UNKNOWN` | None (never attributed) | `IDENTITY_OBSERVED_NOT_ATTRIBUTED`, `RECONCILE_NOT_FOUND_AFTER_OBSERVATION` | 0 | yes; a new dispatch is refused |
| never-observed UNKNOWN, 404 → 404 (≥ 60 s) | `REJECTED` / `NOT_FOUND_AT_BROKER` | None | `RECONCILE_RESOLVED_NOT_FOUND` | 1 | — (positive control) |
| `SUBMISSION_IN_PROGRESS`, 404 ×3 | unchanged | None | `RECONCILE_NOT_FOUND_DISPATCH_MAY_BE_LIVE` ×3 | 1 | yes (unchanged rule) |

## 5. Self-review findings and remaining limitations

- **Q-1 (found and fixed this round).** Absence-event ids were keyed on the observation count; with a
  consecutive-suffix count that repeats after a broken run and collides on the event primary key.
  Only PostgreSQL could show it; keyed on the acknowledgement sequence now (§3).
- **Q-2.** A `RECONCILE_LOOKUP_FAILED` event is recorded *before* the exception is re-raised. If the
  event write itself fails, nothing is recorded and the original exception is lost behind the
  persistence error; the 404 run would then not be broken by that failed round. Bounded: it needs a
  broker failure and a database failure in the same round; the policy still needs ≥ 2 consecutive
  404s afterwards. Recorded, not fixed (no retry, no second write).
- **Q-3.** The "positively observed" rule treats an acknowledgement's `client_order_id_echo` or
  `broker_order_id` as a positive observation. A 200 whose view described a different order under
  our identity (a collision) is a positive observation of *an* order under the identity, which is
  the intended reading: absence after a collision is still an anomaly, not a resolution.
- **Q-4.** The consecutive run is computed from acknowledgements in `sequence` order and the failure
  events by timestamp (`command.at`, the reconciler's clock). Two reconcilers on hosts with skewed
  clocks could order a failure relative to a 404 differently than it happened; the effect is at most
  one extra or one fewer counted 404, and the ≥ 60 s / ≥ 2 rule still applies.
- **Q-5.** Legacy `SUBMISSION_UNKNOWN` rows: none exist in any acceptance database (Paper acceptance
  NOT_STARTED); disposable databases are rebuilt per run. No backfill of boundary records or
  observations.
- **REV-R2.** The binding stays a `key=value` token string; the strict parser removes the demonstrated
  ambiguity, so no typed-column migration was introduced. A value-truncated record that remains
  well-formed (`identity_lookup=4`) is refused at the binding step, not the parse step (tested).
- Unchanged from earlier rounds: S-1 possible-send window; S-2 the boundary write inside
  `before_send`; the historical full-PostgreSQL baseline (3 failed / 43 errors) remains non-green and
  was not rerun; V1 remains pending Owner ratification (its narrow correction is intact — this round
  regenerates only the changed-file inventory and re-renders the table, per the documented process).

## 6. Commits after the code candidate

| Commit | Content | Executable change |
|---|---|---|
| (docs commit following `e010075`) | this record, `runs-e010075/` logs, README pointer, `changed-files.txt` regenerated at that head | none |
| (docs commit following that) | `exhaustion-table.md` rendered against the regenerated inventory | none |

## 7. Outcome

REV-R1: **REPRODUCED_AND_FIXED**. REV-R2: **REPRODUCED_AND_FIXED**. Recommendation:
READY_FOR_OWNER_PUBLICATION_APPROVAL — local commits only; not pushed; not merged; not frozen; not
OWNER_ACCEPTED; not READY_FOR_PAPER; Paper acceptance NOT_STARTED; M086 NOT_STARTED; V1 pending Owner
ratification; the `94ffe90` count correction rides with this candidate.
