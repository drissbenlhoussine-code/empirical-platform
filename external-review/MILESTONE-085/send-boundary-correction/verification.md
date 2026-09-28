# Exact-SHA verification — send-boundary and identity-recovery correction

CODE_CANDIDATE_SHA: **`00716e460ffdb7de99f554d443e05c3ddf9003a9`** (`00716e4`), on
`feature/m085-alpaca-paper-human-approved-execution`, two commits above the published `38dc069`:

| Commit | Content |
|---|---|
| `80d1faa9643ac0bb50fe5da618932a399f6d7cf7` | the correction proper: send boundary, canonical terms, lineage, inconclusive lookup, documented refusal codes, four new suites, 14 new families, CI workflow, evidence README + defect log |
| `00716e460ffdb7de99f554d443e05c3ddf9003a9` | found by this verification (§2.5): the refusal-status rule stated once, in the code table; two equivalent mutants retargeted |
| `37a2d5573e4aac10928b7722a87aacd6158169b7` | docs-only: first version of this record + 35 run logs |
| (the commit containing this version) | docs-only: scope map, two scope-closing runs (§2.2), publication checks (§6), language corrections (§7) |

The executable content of every commit after `00716e4` is byte-identical to `00716e4`: each is
verified below with `git diff --name-status` restricted to nothing outside `external-review/`.

Every command ran in the foreground, one at a time, on a clean working tree (`dirty=0` at the head
of every log in `runs-00716e4/`). Mutation runs never overlapped any other test run. No Alpaca
endpoint was called; every HTTP test targets a local hostile server on 127.0.0.1; every PostgreSQL
test targets the disposable database `m085_pgon_b24c471`; `m085_acceptance_2e5c38c` was not touched.

## 1. Environment (printed, not assumed)

| Component | Value |
|---|---|
| Host | Windows 11 Pro 10.0.26200, Git Bash (MINGW64) |
| Python | 3.13.14 (`.venv`) |
| pytest 9.1.1, pytest-cov 6.3.0, coverage 7.15.1, freezegun 1.5.5, hypothesis 6.156.6, ruff 0.16.3, mypy 1.20.2, build 1.5.1, detect-secrets 1.5.0 | |
| psycopg 3.3.4 (psycopg-binary 3.3.4 also installed) | pinned `PSYCOPG_IMPL=python`, libpq 16.0.13 (`PostgreSQL/16/bin` on PATH); the loaded implementation is printed at the head of every PostgreSQL log (`impl python libpq 160013`) |
| SQLAlchemy 2.0.51, alembic 1.18.5 | |
| PostgreSQL | 16.13 on 127.0.0.1:5432, `pg_hba` trust for the disposable role; no password exists or is recorded (the `EMPIRICAL_PLATFORM_POSTGRES_PASSWORD` variable carries the literal placeholder `trust-auth-placeholder-not-a-credential`) |

CI resolves its own versions; they are recorded in the PR description from the actual run logs, or
stated as UNKNOWN where a run does not print them.

## 2. Results on `00716e4`

### 2.1 Stage table

| Stage | Scope | Result | Log |
|---|---|---|---|
| R1 focused regressions | `tests/unit/test_m085_send_boundary.py` (19 ids), `test_m085_identity_lineage.py` (67), `test_m085_identity_collision.py`, `test_m085_paper_execution_handlers.py`, `test_m085_corrective_pass_handlers.py`, `test_m085_corrective_pass_domain.py`, `test_m085_paper_execution_domain.py`; `tests/integration/test_m085_hostile_http.py` (125), `test_m085_acknowledgement_terms_http.py` (15), `test_m085_send_boundary_transport.py` (2) | **661 passed** | `runs-00716e4/R1-focused.txt` |
| R2 PostgreSQL | `test_m085_temporal_postgres.py` (7), `test_m085_time_basis_postgres.py` (48), `test_m085_paper_execution_postgres.py` (57), `test_m085_concurrency.py` (49), `test_m085_corrective_pass_postgres.py` (62), `test_m085_identity_collision_postgres.py` (7), `test_m084_file_audit.py` (23) | **253 passed** | `runs-00716e4/R2-postgres.txt` |
| R2b PostgreSQL, scope closure (§2.2) | `test_m085_authority_contract.py` (71) — run together with the lifecycle and time-basis files (105 ids re-executed, not counted again) | **176 passed**, of which 71 are the authority-contract ids | `runs-00716e4/R2b-authority-contract-and-R4b.txt` |
| R3 non-PostgreSQL full suite + coverage | `pytest tests`, PostgreSQL opt-in unset | **4034 passed, 0 failed, 1233 skipped**; **coverage 80.37 % ≥ 79 %** (20 380 statements, 3 480 missed; 4 708 branches, 786 partial); every skip is an opt-in gate (PostgreSQL 831 ids, object storage 4, real network 2, unified runtime 2) | `runs-00716e4/R3-full-non-pg.txt` |
| R4 mutation campaign | the **108** families whose target file changed between `2726f6f` and `00716e4` (§3), five sequential chunks, whole-tree SHA-256 before/after each | **108 / 108 detected**, digest `b484179c…8da973e` identical before and after every chunk, tree clean after each | `runs-00716e4/mutation-chunk-0{0..4}.md`, `R4-chunk-0{0..4}.txt`, `affected-families.txt` |
| R4b mutation, scope closure (§2.2) | `legacy_dry_run_refused` (target `tools/m085_paper_acceptance.py`, one changed line) | **detected**, digest identical | `runs-00716e4/R2b-authority-contract-and-R4b.txt`, `mutation-legacy_dry_run_refused.md` |
| R5 static gates | compileall; ruff format `--check` (747 files); ruff check; mypy (368 files); architecture positive + negative fixture; frozen-path guard (M083 27 since `707161a1`, M084 69 since `1127134`; 96 by blob id and by diff); architecture/frozen tests (41); authority renderers M082–M085 `--check`; M084 file audit (75 paths); `scripts/security.ps1` (pip-audit: no known vulnerabilities; secret scan: 1365 targets, none); `python -m build` | **all green** | `runs-00716e4/R5-static.txt` |

Counts in different rows overlap (R2b re-executes 105 R2 ids; R1's domain files overlap R3). They
are not summed anywhere in this record.

### 2.2 Scope relative to the earlier 446-test PostgreSQL run on `2726f6f`

`final-candidate-2726f6f` R1a (180) = temporal 7 + time-basis 48 + lifecycle 57 + corrective pass
62 + identity collision 6 (the file then held 6 ids). R1b (266) = concurrency 49 + authority
contract 71 + hostile HTTP 123 + M084 file audit 23. This round:

| 446-run component | This round | Where |
|---|---|---|
| temporal, time-basis, lifecycle, corrective pass, concurrency, M084 file audit | re-executed unchanged | R2 |
| identity collision PostgreSQL | re-executed, **rewritten**: removed `test_a_duplicate_answer_after_the_send_is_stored_as_unknown_then_reconciled`, `test_a_rebuilt_database_adopts_the_brokers_exact_order_and_sends_nothing` (they asserted the adoption behaviour this correction removes); added `test_a_duplicate_answer_after_the_send_is_observed_and_not_attributed`, `test_a_rebuilt_database_observes_the_brokers_order_without_attributing_or_sending`, `test_an_inconclusive_lookup_then_a_restart_surfaces_the_order_without_attribution` | R2 |
| authority contract (71) | **initially omitted from R2 — a scope gap found in the publication check** and closed by R2b on the same executable content (HEAD `37a2d55`, docs-only above `00716e4`) | R2b |
| hostile HTTP (123 → 125 ids: `an_order_payload` carries `limit_price`/`time_in_force`/`extended_hours`; definitive test parametrised by (status, code); new `test_a_code_that_does_not_belong_to_its_status_is_uncertain[401|403]`) | re-executed; it needs no database | R1 |

### 2.3 Where each safety concern is exercised (test and family identities)

| Concern | Tests | Families (R4 unless noted) |
|---|---|---|
| Temporal provenance (per-act time bases, broker-bounded instants) | `test_m085_temporal_postgres.py`, `test_m085_time_basis_postgres.py`, `test_m085_paper_time.py` (R3) | `authorization_basis_interval_required`, `broker_basis_required`, `broker_basis_authorization_expiry`, `authorization_not_future_dated_against_its_basis`, `m084_deadline_on_proposal_time_basis`, `m084_deadline_never_through_a_later_basis`, `proposal_basis_*`, `decision_basis_*`, `approval_*`, `*_uses_the_measured_host_reading`, `intent_basis_*`, `post_fetch_time`; `paper_time.py` families not rerun (file unchanged, §3) |
| Policy binding (send-time policy from stored configuration) | `test_m085_corrective_pass_postgres.py`, `test_m085_corrective_pass_domain.py`, `test_m085_corrective_pass_handlers.py` | `policy_derived_from_the_configuration`, `policy_fingerprint_covers_every_limit`, `final_guard_policy_fingerprint`, `final_guard_reads_the_configuration_again`, `dispatch_checks_the_binding`; DB guards `database_preview_carries_the_configuration_policy`, `database_authorization_equals_its_preview` not rerun (migration unchanged) |
| Schema guards / authority contract | `test_m085_paper_execution_postgres.py`, `test_m085_authority_contract.py` (R2b), `test_m085_time_basis_postgres.py` | 23 migration families and `schema_head_exact`, `schema_head_checked_by_the_composition`, `authority_contract_reads_the_sql_installed_at_head` not rerun (files unchanged) |
| Lifecycle (states, terminality, single dispatch) | `test_m085_paper_execution_postgres.py`, `test_m085_paper_execution_handlers.py` | `unknown_outcome_state`, `terminal_states_are_terminal`, `dispatch_*_is_unknown`, `reconcile_*`; `repository_refuses_a_terminal_transition`, `dispatch_claim_lease`, `claim_time_after_lock` not rerun (persistence file unchanged) |
| Concurrency | `test_m085_concurrency.py` (49) | `claim_time_after_lock`, `dispatch_claim_lease` (not rerun, unchanged) |
| Send boundary (this correction) | `test_m085_send_boundary.py` (19: positive control, ordering, expiry/kill-switch/stale-quote × {lookup, configuration, clock, quote}, intent expiry, liquidation deadline, market close, stale-when-read, refused repeat), `test_m085_send_boundary_transport.py` (2) | `send_boundary_no_read_after_the_decision`, `send_boundary_kill_switch_read_after_the_slow_reads`, `send_boundary_time_sampled_after_the_reads`, `final_guard_reads_the_*_again`, `final_authorization_expiry`, `final_intent_expiry`, `final_session_close`, `final_quote_freshness`, `kill_switch` |
| Acknowledgement terms | `test_m085_acknowledgement_terms_http.py` (15), `test_m085_hostile_http.py::TestAnAnswerAboutTheWrongOrderIsRefused`, `test_m085_identity_lineage.py::TestTheCanonicalTermsComparison` | `acknowledgement_terms_compared_canonically`, `response_identity_validation`, `response_quantity_validation`, `terms_compare_{limit_price,time_in_force,extended_hours,bound_broker_order_id}`, `identity_match_checks_the_{symbol,quantity,side}` |
| Identity recovery, lineage, no blind resend | `test_m085_identity_lineage.py` (67), `test_m085_identity_collision.py`, `test_m085_identity_collision_postgres.py` (7) | `identity_collision_looks_the_identity_up`, `pre_send_lookup_uses_the_derived_identity`, `no_resend_after_a_collision`, `reconcile_requires_lineage_before_adoption`, `reconcile_verifies_the_account`, `lineage_unsent_never_attributed`, `reconcile_refuses_a_mismatching_order`, `database_rebuilt_meets_existing_identity` |
| Crash / restart | `test_m085_identity_collision_postgres.py::test_an_inconclusive_lookup_then_a_restart_surfaces_the_order_without_attribution`, `test_m085_identity_lineage.py::TestAnInconclusiveLookupBeforeTheSendStaysRecoverable::test_after_a_restart_a_successful_lookup_surfaces_the_order_without_attributing_it`, `test_m085_paper_execution_handlers.py::TestReconcilePaperOrder` | `inconclusive_lookup_is_not_a_rejection`, `unresolved_identity_recovered_after_restart`, `reconcile_a_stale_in_progress_attempt`, `reconcile_recovers_unknown_after_restart`, `reconcile_leaves_a_live_dispatch_alone`, `reconcile_absence_never_rejects_a_live_dispatch` |
| Refusal semantics | `test_m085_corrective_pass_domain.py::TestOnlyADefinitiveRefusalIsARefusal`, `test_m085_identity_lineage.py::TestRefusalsAreClassifiedByDocumentedSemantics`, hostile HTTP definitive/uncertain tests | `definitive_refusal_statuses`, `definitive_refusal_requires_the_brokers_document`, `unknown_error_code_is_uncertain`, `duplicate_identity_422_is_not_a_refusal`, `unknown_422_shape_fails_closed`, `adapter_uncertain_status_is_ambiguous` |

No changed safety invariant is without a collected test and a detected family; the 39 families not
rerun all target files that are byte-identical between `2726f6f` and `00716e4` (§3).

### 2.4 Coverage — what is and is not established

- **80.37 %** is the reported measurement for the current candidate (R3).
- The **83.31 %** recorded for `2726f6f` in `final-candidate-2726f6f/R2-full-non-pg.summary.txt`
  was **not reproduced** in this session. An export of `2726f6f` (`git archive`, no `.git`)
  measured in this session's environment reported 80.29 %, but 21 git-dependent tests failed in
  that export (`tests/architecture/test_frozen_milestones.py` 12, `test_frozen_paths.py` 8,
  `tests/unit/test_m085_base_pin.py` 1), so it is **not a controlled baseline** and no cause for
  the difference is asserted here. Log: `runs-00716e4/coverage-2726f6f-export.txt`. The commit
  message of `37a2d55` calls the earlier figure an "environment artefact"; that wording is
  superseded by this paragraph. Per changed module (statements / missed) in R3: domain 879 / 66,
  usecases 678 / 27, adapter 395 / 42.

### 2.5 What the first candidate `80d1faa` showed (kept in `runs-80d1faa/`)

R1 661 passed; R2 253 passed; R3 4034 passed / 1233 skipped, 80.37 % (that run left
`PSYCOPG_IMPL` unpinned — the binary implementation loaded; recorded as such); R5 all green.
**R4: 106 / 108** — chunk 03 left two survivors, `definitive_refusal_statuses` and
`definitive_refusal_requires_the_brokers_document`, both in `classify_broker_refusal`. Analysis
(README §3.1): equivalent mutants — the new per-status code table already refused what each removed
rule refused, so each had become a masking duplicate. `00716e4` derives
`DEFINITIVE_BROKER_REFUSAL_STATUSES` from the table, removes the early exit, and retargets both
families at the table (a `500` entry; a fabricated *documented* code); both are detected in
`runs-00716e4/mutation-chunk-03.md`. Also there: the first pass of the 20 directly affected/new
families before the first commit, in which `pre_send_lookup_uses_the_derived_identity` and
`lineage_unsent_never_attributed` survived and were fixed by strengthening the tests (README §3).

### 2.6 One environment slip, recorded rather than hidden

The first R3 attempt on `00716e4` pinned `PSYCOPG_IMPL=python` without libpq on PATH in that shell:
two M084 modules that import psycopg at module level failed to collect (`ImportError: libpq library
not found`), pytest exit 2. Operator error, not a product finding; kept as
`runs-00716e4/R3-attempt1-env-error-libpq-not-on-path.txt`; R3 was rerun with libpq on PATH.

### 2.7 Historical baseline (unchanged, not re-run, not green)

The combined full PostgreSQL run of the base (5104 passed / **3 failed / 43 errors** / 16 skipped —
43 M083 `TRUNCATE`-under-FK setup errors, `test_28_migration_up_down_up_is_clean`, two M082
privilege tests; documented non-M085, frozen tests unmodified) was **not** re-run in this round and
remains **non-green**. Nothing here changes those results.

## 3. Mutation-family accounting (`2726f6f`: 134 → `00716e4`: 148; removed: none)

| Class | Count | Families |
|---|---|---|
| New, executed on `00716e4` | 14 | `send_boundary_no_read_after_the_decision`, `send_boundary_kill_switch_read_after_the_slow_reads`, `send_boundary_time_sampled_after_the_reads`, `inconclusive_lookup_is_not_a_rejection`, `unresolved_identity_recovered_after_restart`, `reconcile_requires_lineage_before_adoption`, `reconcile_verifies_the_account`, `lineage_unsent_never_attributed`, `unknown_error_code_is_uncertain`, `acknowledgement_terms_compared_canonically`, `terms_compare_limit_price`, `terms_compare_time_in_force`, `terms_compare_extended_hours`, `terms_compare_bound_broker_order_id` |
| Retargeted (mutation and/or target changed because the governing line moved), executed | 6 | `response_identity_validation`, `response_quantity_validation` (adapter → domain: the rule now lives in `order_terms_mismatches`), `duplicate_identity_422_is_not_a_refusal`, `reconcile_refuses_a_mismatching_order`, `definitive_refusal_statuses`, `definitive_refusal_requires_the_brokers_document` |
| Detecting test renamed (the old test asserted adoption and was removed), mutation unchanged, executed | 3 | `identity_collision_looks_the_identity_up`, `pre_send_lookup_uses_the_derived_identity`, `database_rebuilt_meets_existing_identity` |
| Unchanged, executed (target file changed) | 85 | the remainder of the 108 in `runs-00716e4/affected-families.txt` |
| Unchanged, executed for scope closure | 1 | `legacy_dry_run_refused` (R4b) |
| Unchanged, **not rerun** — target byte-identical between `2726f6f` and `00716e4` | 39 | `migrations/versions/9c4b2e7d5a18_*` (11), `b1e9d47c30a5_*` (2), `d4f18a6c2e97_*` (6), `e61b3f9a4c27_*` (4); `shared/brokerage/paper_time.py` (6); `postgres_repositories/paper_execution_repositories.py` (4); `entrypoints/_paper_composition.py` (1); `tools/check_frozen_paths.py` (2); `current-authority.json` (1), `current-authority.schema.json` (2) |
| Removed | 0 | — |

The historical "134/134" result belongs to `2726f6f` and is **not** claimed for `00716e4`; on
`00716e4` the executed set is 109 (108 + `legacy_dry_run_refused`), all detected.

## 4. Invariant → family mapping

Recorded in [README.md](README.md) §3 and §2.3 above.

## 5. Findings outside the code (Owner-visible; nothing changed here)

### V1 — stale exhaustion table (acceptance-evidence issue; not a publication blocker; **open**)

`tools/render_m085_exhaustion_table.py --check` reports `exhaustion-table.md` "is not the current
rendering". The committed table was rendered at `754ceda` (67 families, 31/31). The renderer's base
is `a224076754fb38909ee04c2464e50e51df12d7ad` (`master`). Rendering at `37a2d55` derives:

| Row | Requirement | Derived status | Conflicting expectation |
|---|---|---|---|
| 21 | No unauthorized M084 file changed | FAIL: `external-review/MILESTONE-085/m084-frozen-path-digests.json` | `_m084_production_untouched` flags any path matching `m084|MILESTONE-084` outside a six-file allow-list. The flagged file is the **M085-owned** blob-id manifest introduced by the Owner-ratified freeze extension (`5ae236c`, PROJECT_CHECKPOINT §119); blob `394a8687e84017d54579b4b46c4efbf838e4d1f0`, unchanged since `5ae236c`. |
| 28 | The changed-files list is exact | FAIL: 78 recorded, 163 actual; 0 recorded-but-absent, **85 present-but-unrecorded** | `changed-files.txt` was last regenerated at `754ceda`. Unrecorded: `migrations/versions/9c4b2e7d5a18_bind_m085_send_policy_and_terminal_attempts.py`; `tests/architecture/test_frozen_milestones.py`; `tests/integration/test_m085_{acknowledgement_terms_http,corrective_pass_postgres,identity_collision_postgres,send_boundary_transport}.py`; `tests/unit/test_m085_{corrective_pass_domain,corrective_pass_handlers,identity_collision,identity_lineage,paper_acceptance_dry_run,send_boundary}.py`. Modified `PROJECT_CHECKPOINT.md`, `tests/architecture/test_frozen_paths.py`, `tests/unit/test_secret_scan_targets.py`, `tools/check_frozen_paths.py`, `tools/secret_scan_targets.py`. Also 68 evidence files under `external-review/MILESTONE-085/` (`corrective-pass*.md` 4, `identity-collision-correction.md`, `m084-frozen-path-digests.json`, `mutation-matrix-*` 4, `final-candidate-2726f6f/` 20, `send-boundary-correction/` 38). |
| 29 | PROJECT_CHECKPOINT.md untouched | FAIL: modified | `_checkpoint_untouched` requires the file absent from the diff. It differs from the base by **+61 lines in two hunks** (M084 pointer block near line 812; new §119 "MILESTONE-084 Post-Freeze Owner Ratification and Mechanical Freeze Extension"), blob `ba9f8439394355ad582b1e9b5e44cc54d8f0cc89`, identical from `5ae236c` to `37a2d55`; base blob `f577d887190f75b737d0c7810b1d09c746addf20`. |

Row 15 would also change ("67 of 67" → "121 of 121", read from `mutation-matrix.md`), which is
a passing row and not a conflict. The staleness predates this round (present at `38dc069`).

**Narrow proposed correction (for a future, separately authorized round; not done here):**
- Row 21: keep the pattern rule; add exactly one allow-list entry,
  `external-review/MILESTONE-085/m084-frozen-path-digests.json`, and require its blob id to equal
  the id the frozen-path guard itself pins (`394a8687…`), so any later edit to the manifest is again
  a breach. Do **not** widen the M084 pattern or exempt `MILESTONE-084` paths in general.
- Row 29: replace "absent from the diff" with "either absent, or its blob equals the Owner-ratified
  checkpoint blob `ba9f8439…` (§119 record)". Any other checkpoint content fails as before.
- Row 28: regenerate `changed-files.txt` from `git diff --name-status a224076...HEAD` at the
  candidate being tabled, and re-render.
The overall acceptance table is **not** green and is not reported as such anywhere in this round.

### V2 — coverage record

See §2.4. The 83.31 % figure is recorded as not reproduced; no environmental cause is asserted.

### V3 — security launcher invocation

`scripts/security.ps1` invokes bare `python`, which on this host resolved to a system Python 3.14
without `pip-audit`, so the script aborted at its own audit step. Tested, passing invocation from
the repository root, no policy or file change:

    PATH="<repo>/.venv/Scripts:$PATH" powershell -ExecutionPolicy Bypass -File ./scripts/security.ps1

CI is unaffected (`setup-python` owns PATH). Nothing in `scripts/`, the scanner, or any frozen file
was altered.

## 6. Publication checks (performed before the push; all on a clean tree)

| Check | Result |
|---|---|
| Remote | `origin` = `https://github.com/drissbenlhoussine-code/empirical-platform.git`; `git fetch --prune` |
| Published head before publication | `origin/feature/m085-alpaca-paper-human-approved-execution` = `2726f6f53f74a0f6d0c63198d0970d3bce822efe`; PR #15 `headRefOid` identical; base `master`; state OPEN |
| Unpublished chain (oldest first) | `38dc069525cef0cc6cc9208ed33f704f365a474d` (docs) → `80d1faa9643ac0bb50fe5da618932a399f6d7cf7` → `00716e460ffdb7de99f554d443e05c3ddf9003a9` → `37a2d5573e4aac10928b7722a87aacd6158169b7` (docs) → this docs commit |
| Ancestry / fast-forward | `00716e4` is an ancestor of `37a2d55`; `2726f6f` is an ancestor of HEAD; `origin/...` is an ancestor of HEAD; `HEAD..origin` is empty — a plain fast-forward |
| Docs-only deltas | `2726f6f..38dc069`: 22 paths, all `external-review/MILESTONE-085/`. `00716e4..37a2d55`: 38 paths, all `external-review/MILESTONE-085/`. `37a2d55..this`: verified in its own commit's check (external-review only). |
| Surfaces touched by the whole range `2726f6f..HEAD` | `.github/workflows/m085-temporal.yml` (1), `src/empirical_platform` (5), `tests/integration` (5), `tests/unit` (7), `tools/` (2), `external-review/MILESTONE-085` (60+). **No** change to `pyproject.toml`, `alembic.ini`, `migrations/`, `scripts/`, `infra/`, `docs/`. |
| CI workflow diff | adds 4 test files to the PostgreSQL step and 16 family names to the mutation step; actions remain `actions/checkout@v4` and `actions/setup-python@v5`; no secrets, network fetches, deploys or pushes |
| Frozen guards | `check_frozen_paths.py`: 96 paths unmodified; `tests/architecture/test_frozen_paths.py` + `test_frozen_milestones.py`: 34 passed |
| Secret scan of every published file (80 paths in `2726f6f..37a2d55`, including the 60 force-added evidence files hidden by `.git/info/exclude`) | detect-secrets 1.5.0: **0 findings**. Credential-shape sweep (Alpaca header/key shapes, AWS, GitHub, Slack, private-key blocks, connection strings with passwords, `password=`): five lines, all present verbatim at `2726f6f` — the two Alpaca **header names** in the adapter's credential-header builder and the `PKTEST…` fake key fixture of the hostile-HTTP test. The placeholder string `trust-auth-placeholder-not-a-credential` appears once (this file) and is not a credential. |
| Secret scan of this record itself | The version of this file committed in `ca9dd02` was flagged by detect-secrets' keyword detector (and therefore by the repository scanner CI runs) on one prose line: a backtick-quoted list of file names following `test_secret_scan_targets.py` was read as a keyword/value pair. No credential was involved. The line was reworded in the next docs-only commit; afterwards detect-secrets, `tools/secret_scan_targets.py --scan-json` and `scripts/security.ps1` all report 0 findings (1403 targets). |

## 7. Adversarial self-review (item 9 of the correction round)

**What is proven.** The in-connection guard's order — lookup first, configuration/clock/quote
next, kill switch after them, host and broker-bounded time sampled after them, `final_send_refusal`
on that evidence, nothing after — is pinned by a trace test (`boundary[0]=="lookup"`,
`boundary[-2]=="kill_switch"`, `boundary[-1]=="POST"`), by scenario tests that flip each hazard
*during* each slow read and count POSTs (positive control: exactly one POST while permitted), by a
transport-level test through the real `AlpacaPaperClient` and real HTTP framing, and by three
mutation families that respectively insert a read after the decision, reuse the pre-claim
kill-switch snapshot, and judge deadlines on the pre-read time. In the adapter, the statement after
`before_send()` returns is `connection.request(...)`; headers and body are built before the guard.

**What is not claimed.** Control over the broker's receipt time, over the TCP write once
`connection.request` is invoked, or over anything after the request leaves.

**Residual observations.**
- R-1 (transport). The POST's TLS connection is opened *before* the guard runs, so a slow lookup
  leaves that socket idle. Two outcomes must be kept apart: a **proven pre-send refusal**
  (`BrokerNotSentError` → terminal `NOT_SENT`, nothing left the process) and an **attempted send
  with uncertain outcome** — if the idle socket has been closed by the peer, `connection.request`
  raises `BrokerAmbiguousDispatchError` and the attempt becomes `SUBMISSION_UNKNOWN`. The second is
  not a refusal and **does not permit a retry**: no code path resends; reconciliation against the
  same `client_order_id` is the only resolution (404 twice over ≥ 60 s → `NOT_SENT`; found → the
  lineage rules apply). Opening the connection after the guard would put the connect phase between
  the decision and the send; left as is and recorded.
- R-2 Lineage admits a `SUBMISSION_IN_PROGRESS` attempt with no unsent event as "may have
  transmitted" (a dispatcher that died after claiming). Reconciliation adopts a found order only if
  every term matches *and* the broker account is the authorized one. Accepted as the intended
  crash-recovery path.
- R-3 An order observed without lineage rests in `SUBMISSION_UNKNOWN` with `IDENTITY_EXISTS_*`
  indefinitely; there is deliberately no automatic path from "observed" to "attributed", and no
  command resends, replaces, cancels or liquidates on its behalf.
- R-4 `_observe_identity` performs one further lookup *after* the decision not to send, to record
  the broker's order. It is a network operation after the decision, but there is no POST after it.

## 8. Outcome

Local verification of `00716e4` complete as above. Publication of the docs-only head that contains
this file is authorized by the Owner for the existing review branch only (fast-forward). Not merged;
not frozen; not OWNER_ACCEPTED; not READY_FOR_PAPER; Paper acceptance NOT_STARTED; M086
NOT_STARTED. Exact-head CI results are recorded in the PR #15 description, not here.

## 9. Exact-head CI on the published head `6b6518c29550292a713c069b462e577485845584` (2026-09-26)

Published by fast-forward push from `2726f6f`; remote ref and PR #15 head read back identical.
All four runs **success**. `push` runs test the branch head; `pull_request` runs test GitHub's
synthetic merge with `master`.

| Workflow | Event | Run | Executed |
|---|---|---|---|
| foundation (windows-2025, CPython 3.13.15, PostgreSQL off) | push | 36240162010 | 4012 passed / 0 failed / 1255 skipped; coverage 80.37 % (TOTAL 20 380 / 3 480 — identical to local R3); all 14 steps incl. pip-audit, secret scan, build |
| foundation | pull_request (synthetic merge) | 36240163397 | 4012 passed / 1255 skipped; 80.37 % |
| M085 temporal PostgreSQL (ubuntu-latest, CPython 3.13.15, PostgreSQL 16.15 service, full history) | push | 36240161916 | 356 passed with `--no-cov` (= 253 PostgreSQL ids + 19 + 67 + 15 + 2 of the four new suites, exact); 52/52 mutation families detected incl. the 16 added here, tree digest `5576bb5ccdb407c2` identical before/after |
| M085 temporal PostgreSQL | pull_request (synthetic merge) | 36240163431 | 356 passed; 52/52; digest identical |

CI versions from the logs: Python 3.13.15; psycopg 3.3.6 + psycopg-binary 3.3.6 (implementation not
printed — presumed binary; **libpq version UNKNOWN**); SQLAlchemy 2.1.1; alembic 1.20.0; pytest 9.1.1;
PostgreSQL 16.15. The 22 extra foundation skips versus local are the git-history-dependent checks
that a shallow checkout cannot run (as on `2726f6f`). CI does not run the full PostgreSQL suite of
every milestone, the 39 not-rerun families, the R2b authority-contract file, or anything external.

This section is recorded in a docs-only commit that is **not pushed** (publishing it would start
another CI round on a new head that would in turn need recording); the same content is in the PR #15
description for the published head. Outcome of the publication round: READY_FOR_INDEPENDENT_CODE_REVIEW.
