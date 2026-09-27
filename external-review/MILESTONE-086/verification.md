# MILESTONE-086 — verification record

CODE_CANDIDATE_SHA: **`513d4ea55c007349633664d4a5c587059890ff1d`**. Parent: `54ae23c7f22c4544b3dc3b06761adc3a25f5ced4`
(the published M085 head). Executable delta: nine new modules (listed in README §3), one new
console script in `pyproject.toml` plus a per-file lint exemption for the HTML module (E501
only), eight new test files and the runbook. **No file under M083, M084 or M085 is modified.**

Every run below was executed on this machine (Windows 11, Python 3.13.14, PostgreSQL 16.13,
psycopg 3.3.4 pure-Python over libpq 16.0.13) against the disposable database
`m085_pgon_b24c471` and a temporary simulation store. No Alpaca endpoint was called; the console
process imports no Alpaca client (architecture test).

## 1. Results

| Stage | Scope | Result | Log |
|---|---|---|---|
| R1 focused | all `tests/unit/test_m086_*.py` (service 54, routes 12, launcher 8, simulation broker 13, domain 16), `tests/architecture/test_m086_console_boundaries.py` (7), `tests/integration/test_m086_operator_console_postgres.py` (4), and every `tests/unit/test_m085_*.py` (unchanged M085 invariants) | **1004 passed** | `runs-worktree/R1-focused.txt` |
| R2 PostgreSQL | all 13 M085 PostgreSQL suites + the M086 console suite | **515 passed** (464 M085 + 4 M086 + 47 authority) in 6 min 14 s | `runs-worktree/R2-postgres.txt` |
| R3 full non-PostgreSQL suite (the repository's merge gate) | `pytest` with coverage | **4307 passed, 0 failed, 1258 opt-in skips; coverage 80.98 % ≥ 79 %** (22 252 statements / 3 679 missed; new modules: services 90 %+, routes 96 %, pages 99 %, web 88 %, simulation 95 %, launcher covered by its own tests) | `runs-worktree/R3-full-non-pg.txt` |
| R5 static | compileall, ruff format/check, mypy (strict), architecture checker + negative fixture, frozen-path guard (M083 27 + M084 69), `tests/architecture`, authority renderers M082–M085, M084 file audit, exhaustion table, `scripts/security.ps1` (pip-audit, secret scan), build | **green** (773 files formatted; mypy 376 files; frozen paths 96; architecture tests 50; renderers M082–M085 current; secret scan 1517 targets, none; build ok) | `runs-worktree/R5-static.txt` |
| Exact-SHA confirmation | R1 + R5 rerun on the committed candidate | **R1 1004 passed; R5 green** on `513d4ea` with a clean tree | `runs-513d4ea/` |

The mutation campaign was not rerun: no mutation target (M084/M085 production files) changed.
The `runs-worktree/` logs were taken on the working tree with the exact content later committed
as the candidate (the `dirty` count in each header is the number of not-yet-committed new files).

## 2. Scenarios proven (by test id)

| Requirement | Where |
|---|---|
| Today card states, every human word | `test_m086_operator_console_domain.py::test_every_engine_state_has_exactly_one_human_word`, routes `test_today_shows_every_card_state_word_from_the_closed_vocabulary` |
| Two-stage approval; stage 1 executes nothing | routes `test_the_two_stage_approval_over_http`; service `test_confirm_approval_runs_the_whole_chain_and_the_order_fills` |
| Stale proposal refusal (version/fingerprint) | service `test_a_stale_tab_with_an_older_proposal_version_is_refused` |
| Duplicate confirmation, two tabs | service `test_a_duplicated_confirmation_creates_no_second_action`, `test_two_tabs_cannot_approve_twice`; routes replay in `test_the_two_stage_approval_over_http` |
| Expired confirmation / proposal expires while open | service `test_a_proposal_that_expires_while_the_page_is_open_is_refused`, ticket age tests |
| Kill switch race | service `test_the_kill_switch_engaged_just_before_confirmation_blocks_it`; PostgreSQL `test_the_absence_policy_and_the_kill_switch_hold_on_postgres`; routes kill-switch test |
| Malformed request | routes `test_malformed_requests_are_refused_without_a_traceback`, `test_a_direct_post_cannot_bypass_confirmation`, `test_a_post_without_the_browsers_csrf_token_is_refused` |
| Direct Paper/Live environment request | routes `test_a_request_that_chooses_an_environment_fails_closed[...]`; service `test_the_service_cannot_be_composed_for_paper_or_live`; PostgreSQL `test_paper_and_live_cannot_be_composed`; architecture `test_the_composition_root_refuses_every_capability_but_simulation` |
| Unauthorized state transition | none exists in the console: no route writes an execution table (architecture tests); M085 repositories/triggers hold |
| Restart reconstruction | service `test_restart_reconstructs_state_from_durable_records_and_creates_nothing`, `test_a_ticket_from_a_previous_process_is_refused_after_restart`; PostgreSQL `test_restart_after_an_ambiguous_execution_reconstructs_and_resolves` |
| Responsive page rendering contract | routes `test_every_page_renders_with_the_simulation_badge_and_the_contract` (viewport meta, no script, no inline style, same-origin stylesheet, CSP, media query present) |
| Twelve simulation scenarios | `test_m086_simulation_broker.py` (adapter) and service `test_each_staged_broker_behaviour_shows_the_honest_state`, `test_an_ambiguous_submission_is_reported_unknown_and_never_resent`, `test_a_lost_request_resolves_rejected_only_through_the_bounded_absence_policy`, `test_cancel_success_and_the_cancel_fill_race_are_both_honest` |
| No direct DB imports from presentation | architecture `test_presentation_imports_no_persistence_broker_or_domain` |
| Loopback binding, security headers, live server | launcher tests |
| End-to-end daily scenario on PostgreSQL | `test_the_daily_scenario_end_to_end_on_postgres` |
| Owner rejects | service `test_rejection_needs_one_confirmation_and_sends_nothing`; routes rejection test |
| Real browser run | `screens/01…09` — approval confirmed in Chrome, background reconciler moved the order to Filled, History and the execution timeline captured |

## 3. External effects

Zero. The console composes `SimulatedPaperBroker` and `SimulatedMarketData` only; the
architecture tests prove no console module imports the Alpaca client or reads credentials; the
simulation module opens no socket. The browser run used `http://127.0.0.1:8086` only.

## 4. Outcome

M086 works end to end in SIMULATION: the day loads through the real M084 handler, the Owner's two-stage confirmation runs the real M085 chain, the background reconciler moves executions to their honest final state, and every safety attack in README §6 is refused by a test. External effects: none. M085 unchanged (13 PostgreSQL suites and every unit suite pass; frozen paths untouched).

Owner decision carried forward: the M085 exhaustion table's row 30 ("No M086 path exists") now derives a blocker (30/31) because M086 paths exist — see README §7; the M085 renderer was not modified.

Open finding carried: **M086-REV-EXIT-01 — OPEN** (no exit/close path; README §6a).

Publication status: **M086_SIMULATION_CANDIDATE_FOR_INDEPENDENT_REVIEW** — local commits only; not pushed; not merged; not frozen. No Paper order, no Alpaca call, no live trading. M085 Paper Acceptance remains NOT_STARTED and Paper composition in the console is a separate, Owner-gated change that this milestone does not pre-authorize.
