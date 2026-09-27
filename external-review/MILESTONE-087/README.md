# MILESTONE-087 — Human-approved position exit (SIMULATION only)

Status: **M087_SCHEMA_BOUNDARY_CLOSED_READY_FOR_INDEPENDENT_REVIEW** (verification.md §6; the
exact-SHA PostgreSQL and static re-runs at `58a7eaf` were interrupted by the host and are owed).
Branch
`feature/m087-human-approved-position-exit`, started from the M086 head
`33f1eb33d8328f68785539d15bcdd9ec73c53708`; first code candidate `909d402…`, schema-boundary
correction `58a7eaf6e84765c5abe0dfa804b79aac41ced2fc` on top (verification.md §5–§6); not
pushed, not merged, not frozen. NOT M087
COMPLETE, NOT DAILY TRADING READY, NOT PAPER READY, NOT LIVE READY. **No Alpaca order or cancel
call of any kind, no Paper trade, no Live trade.** M085 Paper Acceptance remains NOT_STARTED.

## 1. What M087 adds

The intraday lifecycle closes. Before M087 the platform could do
proposal → Owner approval → BUY → fill → open position. M087 adds, from the Operator Console
and with no shell command:

open position → Owner reviews the exact exit → **CONFIRM EXIT** → SELL-TO-CLOSE → reconciliation
→ **position verified at zero** → closed trade → History round trip with the realized result.

## 2. Architecture (layers, all new modules are additive)

| Layer | Module | Role |
|---|---|---|
| Domain | `decision_candidate/position_exit.py` | `PositionExitRequest` (side literal `SELL_TO_CLOSE`, whole positive quantity, environment ∈ {SIMULATION}), `PositionSnapshot` + `exit_eligibility` (the conservative rule), `PositionExitPreview`, `PositionExitAuthorization` (single-use, broker time basis), `PositionExitAttempt` (closed transition table, `closed_position_verified_at`), `PositionExitEvent`, `derive_exit_client_order_id` (`m087-…`, derived from entry intent + account + preview), `exit_request_fingerprint`, `realized_result` (only when proven), `exit_absence_evaluation` (M085's bounded not-found rule over M085's own round type) |
| Ports | `decision_candidate/position_exit_repositories.py` | Six repository protocols and `ExitBrokerPort.submit_close_order` — no method mints an identity or takes a free sell quantity |
| Usecases | `usecases/position_exit.py` | Assess, Preview, Authorize, Submit (claim → send boundary → kill switch last → send), Reconcile (rounds, same identity, position-zero verification), Cancel |
| Console | `usecases/operator_console_exits.py`; `usecases/operator_console.py` (extended) | Review (ticket bound to preview version + fingerprint), Confirm (re-read everything; derived ids `XPV-/XAU-/XAT-<intent>-<version>`), categories (Working entry order / Open position / Exit in progress / Needs attention / Position closed), deadline truth, exit timeline, History result |
| Presentation | `entrypoints/_operator_console_html.py`, `operator_console_app.py` | `/exit/review`, POST `/exit/confirm`, `/exit/cancel`, POST `/exit/confirm-cancel`; grouped Active trades; SIMULATION badge; CSRF; 303 after POST |
| Persistence | `migrations/versions/e7c1a9d3b5f2_…`, `shared/persistence/postgres_repositories/position_exit_repositories.py` | Six `position_exit_*` tables with CHECKs, guards and append-only triggers; `M087_SCHEMA_HEAD` + `require_exact_m087_schema_head` (M087's own schema authority) |
| Composition | `entrypoints/_operator_console_composition.py` (M086, unchanged meaning), `entrypoints/_position_exit_composition.py` (M087) | Two public compositions, two exact-head guards: M086 `compose_operator_console` → `require_exact_m085_schema_head` → private `_compose_verified_console`; M087 `compose_operator_console_with_exits` → `require_exact_m087_schema_head` → the same private helper + exit runtime. No verifier parameter exists; the launcher composes the M087 runtime |
| Simulation | `shared/brokerage/simulation_paper.py` (extended) | `submit_close_order` (refuses no position / over-position, definitive 403), `reduce_position` (never below zero), ten exit scenarios, side-aware progression |

**M085 is consumed, not rewritten.** `PaperOrderRequest` still refuses any side but BUY (asserted
by `tests/architecture/test_m087_exit_boundaries.py`). No M085 handler, repository, migration,
trigger, state machine, authority file or constant is modified: `M085_SCHEMA_HEAD` remains the
M085 revision `a7d3c9e14f26`, permanently. **Schema authority (two heads, kept apart):**

| Milestone | Pin | Guard | Accepts | Refuses |
|---|---|---|---|---|
| M085 | `M085_SCHEMA_HEAD = a7d3c9e14f26` (unchanged) | `require_exact_m085_schema_head` | exactly the M085 revision | the M087 revision, older revisions, unknown newer, multiple heads, missing version |
| M087 | `M087_SCHEMA_HEAD = e7c1a9d3b5f2` | `require_exact_m087_schema_head` | exactly the M087 revision | the M085 head, older revisions, unknown newer, multiple heads, missing version |

**Migration ancestry, machine-checkable** (`tests/unit/test_m087_schema_head.py`,
`tests/integration/test_m087_schema_ancestry_postgres.py`, `m085-migration-manifest.json`):
`e7c1a9d3b5f2.down_revision == a7d3c9e14f26`; it is the only head and the only revision above
M085; the 26 migration files at the published M085 head `54ae23c` are byte-identical on this
branch (sha256 manifest) and exactly one file was added. **M085 catalog preservation:** every
M085-owned table, column, constraint, index, trigger and trigger-function definition (including
the closed transition table) is byte-identical at the M085 head, after upgrading to M087 and after
downgrading back; M087 adds six tables and eight functions and holds no foreign key into an M085
table (its link to the entry is a BEFORE INSERT guard that reads `paper_execution_attempt`).

## 3. The non-negotiable invariants, and where each one lives

| # | Invariant | Enforcement |
|---|---|---|
| 1 | M085 stays structurally BUY-only | `PaperOrderRequest` untouched; architecture test asserts the literal refusal |
| 2 | Own exit model and authority | Separate domain, tables, handlers, authorization and identity prefix `m087-` |
| 3 | Only REDUCE an attributable long; no short | Eligibility requires broker position = attributable entry quantity > 0; simulator refuses no-position / over-position; `reduce_position` refuses crossing zero; `filled_quantity ≤ quantity` CHECK |
| 4 | Full close only | `PositionExitPreview` refuses `quantity ≠ attributable ≠ broker position`; CHECKs `quantity = broker_position_quantity` and `quantity = entry_filled − exits_filled` |
| 5 | Disagreement → refuse, Needs attention | `exit_eligibility`; the review page shows "Position requires operator attention before it can be closed safely" with reasons |
| 6 | Partially filled entry cannot be exited while the remainder can fill; a cancelled entry with a proven filled part can | `_STABLE_ENTRY_STATES = {FILLED, CANCELED}`; PARTIALLY_FILLED refused; preview insert guard reads the M085 entry state |
| 7 | Position never negative in the simulator | `SimulationStore.reduce_position` (under the store lock) |
| 8 | Every exit needs a fresh explicit confirmation | Review → signed ticket → CONFIRM EXIT; no timer, no scheduled liquidation; deadline passing only records the truth |
| 9 | Duplicates, retries, restart, two tabs → no second exit | Derived ids; `active_for_entry`; partial UNIQUE index `one_active_per_entry`; UNIQUE `client_order_id`; single-use authorization; "Already confirmed" |
| 10 | Ambiguous exit = UNKNOWN, do not retry, same identity reconciled | `SUBMISSION_UNKNOWN`; rounds bound to `client_order_id`; no edge back to `SUBMISSION_IN_PROGRESS` |
| 11 | No automatic Paper/Live capability | `ALLOWED_EXIT_ENVIRONMENTS = {SIMULATION}`; CHECK `environment = 'SIMULATION'`; composition root refuses PAPER/LIVE; no Alpaca `submit_close_order` exists |
| 12 | Kill switch explicit and consistent | The M085 execution stop is READ, not reinterpreted: engaged → authorization and submission refused with "release it on the Safety page first"; review page shows the banner |

## 4. Position eligibility (first version, conservative)

Eligible only when: one entry attempt on record in state FILLED (or CANCELED with a filled part),
whole filled quantity > 0, attributable = filled − already exited > 0, broker position == attributable,
no other entry attempt in the symbol still holding shares, no exit open or filled for this entry.
Every other case refuses. Note: M085 itself refuses a second BUY in a symbol with an existing
position, so two lots never arise through the engine; the domain rule still guards it.

## 5. Exactly-once exit

Preview (append-only) → single-use authorization bound to preview fingerprint, binding
fingerprint, account and derived `client_order_id` → `claim_dispatch` consumes the authorization
and inserts the attempt in ONE transaction (conditional UPDATE decides the race) → durable
`EXIT_SEND_BOUNDARY_ENTERED` event → kill switch read last → transport sends. Ambiguous answers
are `SUBMISSION_UNKNOWN`; reconciliation rounds are begun before the network and completed once;
absence resolves only under the M085 bounded rule (3 consecutive completed NOT_FOUND rounds, ≥ 60 s
on the broker clock), re-validated under a row lock.

## 6. Position closed, History and P&L

"Position closed" = exit FILLED for its whole quantity **and** `closed_position_verified_at` set by
a reconciliation that saw the broker position at zero (event `POSITION_CLOSED_VERIFIED`). History
shows the round trip and `realized P&L = (exit avg fill − entry avg fill) × closed quantity` only
when the exit is verified closed and both actual fill prices are recorded; otherwise the result is
"Not available". Results are labelled *simulation*.

## 7. Adversarial review — IMPLEMENTED / PROVEN / CLAIMED / BLOCKED

Legend: **PROVEN** = an executed test at the candidate asserts it; **IMPLEMENTED** = code exists,
covered indirectly; **CLAIMED** = stated, not executed here; **BLOCKED** = could not be completed.

| Attack | Result | Evidence |
|---|---|---|
| Zero position | PROVEN | domain `test_every_uncertainty_refuses_rather_than_guesses[broker_position_quantity=0]`; service `test_ineligible_positions…[NVDA]`; broker `test_a_close_with_no_position_is_definitively_refused…` |
| Quantity mismatch / position larger or smaller than entry evidence | PROVEN | domain (9 and 7 vs 8); service `test_a_position_that_changed_after_the_review_is_refused_at_confirmation`; broker over-position refusal |
| Two entries in one symbol | PROVEN (domain) / PROVEN (engine refuses the second BUY) | domain `competing_entry_attempt_ids`; service `test_a_second_entry_in_the_same_symbol_is_refused_by_m085…` |
| Partially filled entry, remainder working | PROVEN | service `test_ineligible_positions…[MSFT]`, `test_a_cancelled_partial_entry_becomes_a_stable_position…` |
| Cancelled entry with stable partial position | PROVEN | same test: exit of 2 of 4, closed and verified |
| Stale exit confirmation | PROVEN | service `test_a_stale_ticket_and_an_expired_review_send_nothing`; routes `test_a_post_without_the_csrf_token_or_a_stale_ticket_sends_nothing` |
| Expired authorization | PROVEN (domain `refusal_against`, ticket expiry) / IMPLEMENTED (authorization expiry on both clocks at claim; DB `consumed_at >= expires_at` refused) | domain + service; PG guard tests cover consumption rules |
| Kill switch engaged after review, before confirm | PROVEN | service `test_the_kill_switch_engaged_after_the_review_blocks_the_confirmation` |
| Double click | PROVEN | service `test_a_duplicate_confirmation_and_a_second_tab…`; routes `test_confirm_exit_sends_once…` |
| Two tabs | PROVEN | same; PG `test_two_service_instances_cannot_create_two_exit_attempts` |
| Crash before send | PROVEN (restart before confirmation / after authorization sends nothing) | PG `test_restart_before_confirmation_and_after_authorization_sends_nothing`; service `test_a_failure_before_the_send_is_blocked_with_nothing_sent` |
| Crash after possible send | PROVEN | service `test_an_ambiguous_exit_is_unknown…`; PG `test_restart_after_an_ambiguous_exit_preserves_unknown…` |
| Duplicate broker identity | PROVEN | broker `test_a_duplicate_exit_identity_is_refused_by_the_broker`; DB UNIQUE `client_order_id`; two-console test |
| Broker returns mismatched exit terms | PROVEN (domain `exit_order_terms_mismatches`) / IMPLEMENTED (submit and reconcile record `EXIT_IDENTITY_COLLISION_MISMATCH`, never adopt) | domain test; handler code paths not driven by the simulator (it always echoes the sent terms) |
| Partial exit fill | PROVEN | service `test_a_partial_exit_fill_reduces_the_position_but_never_calls_it_closed`; broker partial test |
| Restart during UNKNOWN | PROVEN | service and PG restart tests (KO) |
| Reconciliation finds the exit | PROVEN | ambiguous scenarios resolve to FILLED and verified closed |
| Reconciliation does not find it | PROVEN | service `test_an_exit_never_received_is_resolved_by_the_bounded_absence_policy` |
| Exit fill produces zero position | PROVEN | round-trip tests: `store.position == 0`, `closed_position_verified_at` set, event recorded |
| Simulator attempts to cross below zero | PROVEN | broker `test_the_position_can_never_go_negative_even_under_a_racing_fill`; service `test_the_simulator_refuses_to_cross_below_zero` |
| Racing claims on one authorization | PROVEN | PG `test_a_racing_claim_on_one_authorization_has_exactly_one_winner` (two connections, one winner) |
| Database rewrites (identity, terminal rows, close twice, over-sold, second authorization per preview, append-only evidence) | PROVEN | PG `test_the_database_refuses_every_rewrite_and_every_second_identity` |
| Migration fresh up / down / up + exact head | PROVEN | PG `test_the_migration_upgrades_downgrades_and_re_upgrades_with_an_exact_head` |
| Browser refresh cannot send again; environment field refused | PROVEN | routes tests |
| Missed liquidation deadline recorded and shown, nothing sent | PROVEN | service `test_a_missed_liquidation_deadline_is_recorded_and_shown_and_nothing_is_sent` |
| Real mobile-browser rendering | CLAIMED | CSS media query only (as in M086) |
| Manual browser walkthrough with screenshots | CLAIMED | not performed in this session; the routes suite renders every page |
| M086 public composition refuses the M087 schema; M087 composition refuses the M085 schema; each accepts its own | PROVEN | PG `test_the_migration_upgrades_downgrades_and_re_upgrades_with_an_exact_head`; unit `test_m087_schema_head.py` (guard matrix, both guards) |
| M087 is an additive descendant; M085 catalog byte-identical before/after/down; migration files byte-identical to the M085 head | PROVEN | PG `test_m087_schema_ancestry_postgres.py`; `m085-migration-manifest.json` |
| A caller-supplied verifier can bypass a schema guard | PROVEN impossible | architecture `test_each_milestone_composition_verifies_its_own_exact_schema_head` (no such parameter; private helper not exported) |

## 8. Known limitations and the blocked item

- **Stacked-milestone test evolution (M085 tests, each named).** `M085_SCHEMA_HEAD` was NOT
  moved. Instead the M085 tests whose purpose is the M085 exact-head guard migrate their disposable
  database explicitly to `M085_SCHEMA_HEAD` (`_m085_support.build_engine(revision)`), and the two
  assertions that said "the repository-global head IS the M085 head" were evolved into the
  invariant they protected (pin unchanged; head descends from it in one line; nothing inserted or
  replaced; the M085 branch still ends at M085). Full list in verification.md §3. The M085 paper
  CLI composition (`_paper_composition.py`) is unchanged and therefore refuses a database at the
  M087 head, exactly as it refuses any non-M085 revision: on this branch the M085 CLI is not
  runnable against the console's database, by design, and that is disclosed rather than hidden.
- Exit orders are LIMIT at the current bid; MARKET exits are not offered.
- A partial exit fill followed by a cancel leaves a smaller position; the next exit is a full
  close of the remainder (a new preview, a new identity).
- `PositionExitConsole.summary` computes `Position closed` from the durable attempt only; it does
  not re-query the broker on every page render (the reconciler does).
- The two-console PostgreSQL test releases the state-directory lock deliberately; in production a
  second console is refused before it can read state (M086 lock, re-asserted here).
