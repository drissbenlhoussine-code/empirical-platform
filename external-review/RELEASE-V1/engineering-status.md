# EMPIRICAL PLATFORM v1 -- Personal Paper Release: engineering status

Branch `release/v1-personal-paper`, from the exact latest green stack tip
(`ed9215301f53c3eb9e029caf26be843b57d4f941`, M095/PR #25's head). This is an honest
progress record across two engineering passes, not a "done" claim -- see FINAL STATUS in
the PR/final report.

## What this branch has actually built, and proved with real tests

1. **Kill switch semantics (Release Blocker: "kill switch must not trap an open
   position")**. An engaged kill switch blocks new entries only, never a position-reducing
   exit. `docs/operations/kill-switch.md`. The pre-existing `test_m087_position_exit_
   service.py` kill-switch test rewritten to assert the NEW (correct) behavior.

2. **`ApprovedPlan` domain model** (`decision_candidate/approved_plan.py` +
   `approved_plan_repositories.py`). Pure, frozen, immutable terms, a deterministic
   `system_identity` derivation, and the pure `evaluate_exit_trigger` decision function.
   12 exhaustive unit tests, zero I/O (`tests/unit/test_v1_approved_plan_domain.py`).

3. **`PositionPlanManager`** (`usecases/position_plan_manager.py`) -- Release Blocker 4's
   automatic exit engine. Polls durable `ApprovedPlan`s, evaluates stop/target/mandatory-
   exit against fresh broker/market truth, durably claims the right to act, then dispatches
   through the EXISTING, unmodified `AuthorizePositionExitHandler` ->
   `SubmitAuthorizedPositionExitHandler` chain with `authorized_by` set to the plan's
   system identity. 7 tests over the REAL simulation broker and REAL M087 exit handlers:
   stop trigger, target trigger, mandatory-exit-on-time-alone, two managers racing
   submitting exactly one exit, and simulated restart recovery.

4. **Postgres persistence for `ApprovedPlan`** (added this pass -- was the #1 remaining
   gap after the previous report). Migration `b9f2c4d6a8e1` (additive on M090's head, Store
   A), its own `require_exact_v1_approved_plan_schema_head` guard (this table feeds a real
   unattended-order-submission decision, the same class of danger M085/M087's guards exist
   for -- unlike M090's guard-free research schema), and database-level triggers
   independently enforcing claim-once and immutable-terms, belt-and-suspenders alongside
   the repository's own conditional UPDATE. `PostgresApprovedPlanRepository` follows the
   M085 persistence discipline exactly (literal SQL constants, fail-closed reads). **12
   integration tests against a REAL local PostgreSQL 16 instance**, including the core
   proof: 8 real concurrent connections racing the identical `claim_exit_trigger` UPDATE,
   exactly one wins. A genuine bug (an unescaped colon in a CHECK constraint's SQL text
   being silently parsed as a SQLAlchemy bind parameter, corrupting the stored constraint)
   was caught and fixed by this local-Postgres testing before ever reaching CI.

5. **`approve_full_plan`** (added this pass; `usecases/full_plan_approval.py`) -- Release
   Blocker 2's connector. Calls the existing `OperatorConsoleService.confirm_approval`
   UNCHANGED (full existing safety logic preserved), then creates the durable `ApprovedPlan`
   from the FRESH M085 `TradeProposal`'s own `stop_loss_price`/`profit_exit_price`/
   `quantity` -- never from a Research Candidate's possibly-stale research-time numbers.
   Idempotent: proven to recover and create the plan when called after an EARLIER,
   interrupted call already authorized/submitted the entry (the narrow ordering window the
   module docstring names honestly). 5 tests over the real simulation broker and real
   M084-M086 handler chain.

6. **Entry-governance regression lock** (`tests/unit/test_v1_entry_governance_lock.py`) --
   two tests against the real M089 incident shape, run over the real handler chain.

7. **Architecture boundary tests**
   (`tests/architecture/test_v1_position_plan_manager_boundaries.py`, 4 tests): no
   BUY-capable or Live surface reachable from the manager/plan modules; the manager never
   constructs an order/exit request literal itself; the plan domain module is I/O-free.

8. **Autostart artifacts** (`deploy/windows/run-v1-console.ps1`,
   `deploy/windows/v1-console-task.xml`) -- committed, documented, NOT registered against
   the live machine. Honestly scoped: still point at the EXISTING M088/M089 console, not a
   not-yet-built consolidated v1 console (see Not Done #1 below).

**Full regression proof**: `PYTHONPATH=...\v1-release\src pytest tests/unit
tests/architecture -q` -> **4437 passed, 0 failed** (the coverage-PERCENTAGE gate still
fails at 75.49%, the same pre-existing, documented, non-regression condition noted since
M093). Postgres suites (new `test_v1_approved_plan_postgres.py` plus the full existing
M085-M089/M090-ancestry suites, to confirm zero regression from stacking a new migration
on top) -- **35 passed, 0 failed**, against a real local PostgreSQL 16. `ruff check`,
`ruff format`, `mypy`, `tools/check_architecture.py`, `tools/secret_scan_targets.py` all
clean. Two pre-existing pinned-migration-manifest tests were updated to recognize this
branch's new migration as a third known, accounted-for chain addition (the same way they
were updated when M090's migration first joined M087's) -- not weakened, just extended.

## What remains -- named honestly, not glossed over

1. **Console consolidation (Release Blocker 1)**. TODAY/ACTIVE/HISTORY/SAFETY navigation,
   the "RESEARCH CANDIDATE" banner/labeling and exact candidate fields, and integrating
   M090's opportunity-engine candidates into `operator_console.py`, are NOT built. The
   existing M088/M089 console remains the only running console and does not yet expose a
   "REVIEW PLAN" button wired to `approve_full_plan`, nor start `PlanManagerThread` inside
   its process.
2. **Active Trade UI / History / Safety page content** exactly as specified -- not built;
   the domain model can now supply every field the mission asks for (`ApprovedPlan`,
   `PlanEvaluationOutcome`, the existing History-adjacent repositories), but no HTML/routes
   exist yet to render them.
3. **Retiring the M090-M095 report consoles from "normal navigation"** -- not applicable
   yet, since there is no new consolidated navigation for them to be retired FROM.
4. **Starting `PlanManagerThread` inside the console process** -- the class exists and is
   tested standalone (`tests/unit/test_v1_position_plan_manager.py`), but no composition
   root yet wires it into a running console's startup sequence.
5. **Remaining mission test matrix**: A (full-plan immutable approval, now testable at the
   UI layer once item 1 exists -- the underlying immutability IS proven at the domain/
   connector layer already), D (no automatic entry without approval -- implied by
   `approve_full_plan`'s reuse of `confirm_approval`, not yet a dedicated UI-level test), I
   (partial fills), K (position-zero required for CLOSED -- covered indirectly by reused
   M087 `position_closed` logic, not a dedicated v1 test), Q (no overnight intended
   position), S/T (Simulation/Live-impossible regression -- T is covered by this branch's
   architecture tests; S needs a dedicated run), U (mobile UI -- no UI exists yet), V
   (autostart artifact presence -- the files exist and are documented; no automated test
   asserts their content). B, C, E, F, G, H, J, L, M, N, O, P are directly and freshly
   proven by the test files already in this branch.

## Why engineering stopped here

Two full passes have now delivered, in priority order: the automatic unattended exit
engine with proven collision-safety and crash-recovery (hardest, highest-risk), Postgres
persistence proven under real concurrent-connection racing (the explicitly-named #1 gap),
and the one-click approval connector that ties entry authorization to plan creation with a
proven, tested idempotent-recovery story for its one honestly-disclosed ordering gap. What
remains is real, substantial work (a mobile-first console UI, History/Safety pages, process
composition to start the background manager) but it is UI/wiring/composition work laid
over an already-proven, already-tested safety core -- not open design risk. Building that
UI to the same rigor this pass held itself to (real tests against the real simulation
broker, not a shallow HTML mockup) is a genuinely large unit of work in its own right, and
attempting it in the remaining time of this pass risked exactly the shallow, under-tested
result this project's own discipline exists to avoid.
