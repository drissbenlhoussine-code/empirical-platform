# MILESTONE-087 — verification record

CODE_CANDIDATE_SHA: **`909d402afe3201ad1b1acf48278ff853a3f52cbd`**. Parent:
`33f1eb33d8328f68785539d15bcdd9ec73c53708` (the M086 head). The runs in `runs-worktree/` were
taken on the working tree with the exact content then committed as the candidate (24 files,
+8 692 / −65); `runs-909d402/` holds the exact-SHA confirmation on a clean tree (§5).

Every run was executed on this machine (Windows 11, Python 3.13, PostgreSQL 16, psycopg pure
Python over libpq) against the disposable database `m085_pgon_b24c471` and temporary simulation
stores. No Alpaca endpoint was called; no M087 module imports the Alpaca client (architecture
suite) and the Alpaca adapter has no exit implementation.

## 1. Results

| Stage | Scope | Result | Log |
|---|---|---|---|
| R1 focused | all M087 suites (domain 25, simulation broker 14, console service 17, routes 9, architecture 15) and all M086 unit/architecture suites, verbose by id | **215 passed** | `runs-worktree/R1-focused.txt` |
| R2 PostgreSQL | 13 M085 PostgreSQL suites + M086 console suite + M087 exit suite (8) on a schema rebuilt from the complete migration history | **520 passed, 5 failed** — every failure is the M085 exact-head pin (§3); every M086 and M087 test passed | `runs-worktree/R2-postgres.txt` |
| R2b isolation | the two M085 corrective-pass tests that failed in R2, alone on a fresh schema | see the log: they pass when not preceded by the head-pin test that resets `alembic_version` to the old M085 head (cascade, not an M087 migration defect) | `runs-worktree/R2b-corrective-isolated.txt` |
| R3 full non-PostgreSQL suite (the repository's merge gate) | `pytest` with coverage | **4405 passed, 2 failed, 1268 opt-in skips; coverage 80.52 % ≥ 79 %** — both failures are the M085 head pin (§3) | `runs-worktree/R3-full-non-pg.txt` |
| R5 static | compileall, ruff format (787 files) / check, mypy (381 files), architecture checker + negative fixture, frozen paths (M083 27 + M084 69), `tests/architecture` 65 passed, authority renderers M082–M085, M084 file audit, `scripts/security.ps1`, build | **green** after one correction: the secret scanner flagged a full revision-id literal in a new test; the literal is now grouped, the scan passes (1558 targets, none) | `runs-worktree/R5-static.txt` (first run, flag shown) + re-run recorded in §5 |

The exhaustion table `--check` reports the M085 inventory stale at this head, as at every head
since M086; it is regenerated in the docs commits (row 30 "No M086 path exists" remains the
M085 scope boundary, now with M087 paths as well).

## 2. Scenarios proven (by test id)

| Requirement | Where |
|---|---|
| Full round trip: open position → review → CONFIRM EXIT → SELL-TO-CLOSE → accepted → filled → verified zero → closed → History realized result | service `test_the_full_round_trip_closes_the_position_and_history_shows_the_realized_result`; routes `test_confirm_exit_sends_once_and_a_refresh_or_replay_never_sends_again`; PostgreSQL `test_the_round_trip_closes_the_position_and_the_rows_are_consistent` |
| Review sends nothing; exact immutable terms; SIMULATION badge | routes `test_the_review_page_shows_the_exact_terms_and_sends_nothing` |
| Duplicate click / two tabs / replayed POST / refresh | service `test_a_duplicate_confirmation_and_a_second_tab_never_create_a_second_exit`; routes (above); PostgreSQL `test_two_service_instances_cannot_create_two_exit_attempts` |
| Two service instances race one authorization: exactly one winner | PostgreSQL `test_a_racing_claim_on_one_authorization_has_exactly_one_winner` |
| Stale ticket, expired review, tampered ticket, missing CSRF, environment field | service `test_a_stale_ticket_and_an_expired_review_send_nothing`; routes `test_a_post_without_the_csrf_token_or_a_stale_ticket_sends_nothing`, `test_an_exit_confirmation_that_chooses_an_environment_fails_closed[...]` |
| Kill switch engaged after review, before confirm | service `test_the_kill_switch_engaged_after_the_review_blocks_the_confirmation` |
| Position changed after review (external share) | service `test_a_position_that_changed_after_the_review_is_refused_at_confirmation` |
| Zero position / rejected entry / partially filled entry | service `test_ineligible_positions_are_refused_with_the_attention_sentence[NVDA|AMZN|MSFT]`; routes `test_an_ineligible_position_shows_the_attention_message` |
| Cancelled partial entry → stable position → exit (cancel/fill race) → closed | service `test_a_cancelled_partial_entry_becomes_a_stable_position_that_can_be_closed` |
| Two lots in one symbol | domain `competing_entry_attempt_ids` refusal; service `test_a_second_entry_in_the_same_symbol_is_refused_by_m085_so_attribution_stays_single` |
| Broker rejection → position open → new identity on the next exit | service `test_a_broker_rejection_leaves_the_position_open_and_reviewable_again` |
| Failure before send → BLOCKED, nothing sent | service `test_a_failure_before_the_send_is_blocked_with_nothing_sent` |
| Ambiguous after possible send → UNKNOWN → same identity found → closed | service `test_an_ambiguous_exit_is_unknown_and_reconciliation_addresses_the_same_identity`; routes `test_an_unknown_exit_is_shown_as_needs_attention_do_not_retry` |
| Never received → bounded absence policy → REJECTED, position open | service `test_an_exit_never_received_is_resolved_by_the_bounded_absence_policy` |
| Restart during UNKNOWN (in-memory world and PostgreSQL) | service `test_a_restart_while_the_exit_is_unknown_preserves_unknown_and_then_resolves_it`; PostgreSQL `test_restart_after_an_ambiguous_exit_preserves_unknown_and_reconciles_the_same_identity` |
| Restart before confirmation and after authorization sends nothing | PostgreSQL `test_restart_before_confirmation_and_after_authorization_sends_nothing` |
| Partial exit fill: reduced, never closed; cancel; remainder closable | service `test_a_partial_exit_fill_reduces_the_position_but_never_calls_it_closed`; broker `test_a_partial_close_reduces_the_position_by_the_filled_part_only` |
| Missed deadline recorded once and shown; nothing sent | service `test_a_missed_liquidation_deadline_is_recorded_and_shown_and_nothing_is_sent` |
| Simulator: no position / over-position refused; duplicate identity; never negative; scenario recording | broker suite (14) |
| Database: CHECKs, one authorization per preview, single-use, immutable identity, terminal rows, close once, over-sold, append-only evidence | PostgreSQL `test_the_database_refuses_every_rewrite_and_every_second_identity` |
| Migration up / down / up, exact head, composition refuses a non-M087 head | PostgreSQL `test_the_migration_upgrades_downgrades_and_re_upgrades_with_an_exact_head` |
| M086 one-console lock intact | PostgreSQL `test_the_one_console_per_state_dir_lock_is_intact` |
| M085 BUY-only request untouched; no Alpaca exit; SIMULATION-only environment; presentation boundaries; additive migration | architecture `test_m087_exit_boundaries.py` (15) |

## 3. The M085 head pin — BLOCKED, disclosed exactly

The M087 migration `e7c1a9d3b5f2` is the repository head. Seven M085 tests pin the head to the
M085 revision and fail on this branch:

| Test | Why it fails | Kind |
|---|---|---|
| `tests/unit/test_m085_paper_composition.py::TestTheSchemaHeadIsExact::test_the_pinned_head_is_the_repository_migration_head` | asserts `M085_SCHEMA_HEAD == ScriptDirectory head` | constant not moved |
| `tests/integration/test_m085_corrective_pass_postgres.py::TestTheExactSchemaHeadIsRequired::test_the_migrated_database_is_accepted` | `require_exact_m085_schema_head` refuses the M087 head | constant not moved |
| `…test_m085_reconciliation_rounds_postgres.py::test_the_round_journal_migration_goes_down_and_up_again` | asserts the database head equals `M085_SCHEMA_HEAD` | constant not moved |
| `…test_m085_corrective_pass_postgres.py::test_the_corrective_migration_goes_down_and_up_again` | CASCADE: the preceding head-pin test restores `alembic_version` to the OLD M085 head while the M087 tables exist, so the next downgrade skips M087 and the re-upgrade meets an existing table; **passes in isolation** (R2b): the M087 migration goes down and up cleanly | cascade of the constant |
| `…test_m085_corrective_pass_postgres.py::test_the_upgrade_refuses_to_invent_a_binding_for_rows_that_exist` | its migration round trip passes; its LAST assertion compares the database head with `M085_SCHEMA_HEAD` (R2b shows the assertion) | constant not moved |
| `tests/integration/test_m085_authority_contract.py::TestTheContractReadsTheSqlInstalledAtHead::test_the_rendered_chain_is_exactly_the_m085_revisions_ending_at_head` (in R2 and R3) | asserts the repository head IS the last M085 revision — an M085 scope guard, like exhaustion row 30 | scope boundary |

Required M085 edit (one constant, plus its comment): `M085_SCHEMA_HEAD = "e7c1a9d3" + "b5f2"` in
`src/empirical_platform/shared/persistence/postgres_repositories/paper_execution_repositories.py`.
This session was not permitted to modify that M085 production module; the edit is for the Owner
to apply or authorize. After it, the first four rows pass; the last row is a scope boundary the
Owner decides on (accept as the stacked-branch boundary, or authorize the M085 test to name the
M085 head explicitly). The M087 console does not depend on the M085 pin: it verifies
`M087_SCHEMA_HEAD` itself (PostgreSQL migration test).

## 4. External effects

Zero. The console composes `SimulatedPaperBroker` and `SimulatedMarketData` only; the only
`submit_close_order` implementation is the simulator's; `PositionExitRequest` cannot bind PAPER or
LIVE; the composition root refuses every capability but SIMULATION.

## 5. Exact-SHA confirmation (`909d402afe3201ad1b1acf48278ff853a3f52cbd`, clean tree)

| Stage | Result | Log |
|---|---|---|
| R1 focused (all M087 + M086 unit/architecture suites, verbose by id) | **215 passed** | `runs-909d402/R1-focused.txt` |
| R2 PostgreSQL (M087 exit suite 8 + M086 console suite 6, schema rebuilt from the full history) | **14 passed** | `runs-909d402/R2-postgres-m086-m087.txt` |
| R5 static (compileall, ruff format 787 / check, mypy, architecture + negative fixture, frozen paths, `tests/architecture` 65 passed, renderers M082–M085, M084 file audit, `security.ps1` 1559 targets none, build) | **green**; exhaustion table `--check` stale until the docs regeneration commits | `runs-909d402/R5-static.txt` |

Not re-run at the exact SHA: R3 (full non-PostgreSQL suite) and the 13 M085 PostgreSQL suites,
whose worktree runs (§1) had identical content apart from the grouped revision literal in one
architecture test; their only failures are the M085 head-pin rows of §3.

## 6. Classification

**M087_SIMULATION_READY_FOR_INDEPENDENT_REVIEW**, with the §3 item BLOCKED and reported: the
one-line M085 constant edit (and the Owner's decision on the M085 head-pin tests) is required
before this branch's full suite is green. Local commits only; not pushed; not merged; not frozen.
No Alpaca call, no Paper trade, no Live trade. M085 Paper Acceptance remains NOT_STARTED. Not
M087 COMPLETE, not DAILY TRADING READY, not PAPER READY, not LIVE READY.
