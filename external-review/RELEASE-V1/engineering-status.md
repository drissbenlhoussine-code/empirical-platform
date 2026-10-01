# EMPIRICAL PLATFORM v1 -- Personal Paper Release: engineering status

Branch `release/v1-personal-paper`, from the exact latest green stack tip
(`ed9215301f53c3eb9e029caf26be843b57d4f941`, M095/PR #25's head). This is an honest
progress record, not a "done" claim -- see FINAL STATUS at the end.

## What this pass actually built, and proved with real tests

1. **Kill switch semantics (Release Blocker: "kill switch must not trap an open
   position")**. Removed the three exit-side kill-switch refusals in
   `usecases/position_exit.py` (`AuthorizePositionExitHandler.handle`,
   `SubmitAuthorizedPositionExitHandler.handle`, and its pre-send-boundary check) and the
   console-level check in `usecases/operator_console_exits.py::confirm`. Entry-side
   blocking is UNCHANGED. Documented in `docs/operations/kill-switch.md`. The pre-existing
   `test_m087_position_exit_service.py` kill-switch test was rewritten to assert the NEW
   (correct) behavior rather than deleted.

2. **`ApprovedPlan` domain model**
   (`decision_candidate/approved_plan.py` + `approved_plan_repositories.py`). Pure,
   frozen, immutable terms (stop/target/mandatory-liquidation/owner-approval identity),
   a deterministic `system_identity` derivation that traces every automatic action back
   to the one Owner approval that created it, and the pure `evaluate_exit_trigger`
   decision function. 12 exhaustive unit tests, zero I/O
   (`tests/unit/test_v1_approved_plan_domain.py`).

3. **`PositionPlanManager`** (`usecases/position_plan_manager.py`) -- Release Blocker 4's
   core: polls durable `ApprovedPlan`s, evaluates stop/target/mandatory-exit against fresh
   broker/market truth, and on a trigger, durably claims the right to act
   (`ApprovedPlanRepository.claim_exit_trigger`, same atomic-UPDATE discipline as the
   existing `claim_dispatch`), then dispatches through the EXISTING, unmodified
   `AuthorizePositionExitHandler` -> `SubmitAuthorizedPositionExitHandler` chain with
   `authorized_by` set to the plan's own system identity -- never a fabricated human
   identity, never a new broker-submission code path. 7 tests
   (`tests/unit/test_v1_position_plan_manager.py`) run over the REAL simulation broker and
   the REAL M087 exit handlers (not mocks), covering: monitoring (no trigger), a stop
   trigger submitting a real SELL_TO_CLOSE, a target trigger, the mandatory-exit deadline
   firing on time alone, two managers racing on the identical tick submitting exactly one
   exit, and a simulated restart (a claim recorded with nothing yet dispatched, picked up
   and completed by a fresh manager instance over a rebuilt broker connection).

4. **Entry-governance regression lock** (`tests/unit/test_v1_entry_governance_lock.py`) --
   two tests, explicitly labeled against the real M089 incident shape (an expired
   approval; a regenerated proposal at different terms), run over the real handler chain.
   This formalizes coverage that already existed in `test_m085_paper_execution_handlers.py`
   and `test_m086_operator_console_service.py` as its own dedicated v1 proof.

5. **Architecture boundary tests**
   (`tests/architecture/test_v1_position_plan_manager_boundaries.py`, 4 tests): the
   manager and the plan domain/repository modules cannot import or name a BUY-capable
   surface, a Live client, or `paper_execution`'s own handlers; the manager never
   constructs an order/exit request literal itself (quantity/price always come from the
   existing, broker-verified construction inside `PreviewPositionExitHandler`); the plan
   domain module is proven I/O-free.

6. **Autostart artifacts** (`deploy/windows/run-v1-console.ps1`,
   `deploy/windows/v1-console-task.xml`) -- committed, documented, explicitly NOT
   registered against the live machine (that is an Owner action). Honestly scoped: they
   currently autostart the EXISTING M088/M089 console (`operator_console.py --capability
   paper-exit`), not a not-yet-built consolidated v1 console -- see item 7.

**Full regression proof**: `PYTHONPATH=...\v1-release\src pytest tests/unit
tests/architecture -q` -> **4432 passed, 0 failed** (the coverage-PERCENTAGE gate still
fails at 75.49%, the same pre-existing, documented, non-regression condition noted in
M093-M095's own reports -- not a test failure). `ruff check`, `ruff format`, `mypy` on
every new/changed file, `tools/check_architecture.py`, and `tools/secret_scan_targets.py`
all clean.

## What this pass did NOT complete -- named honestly, not glossed over

1. **Console consolidation (Release Blocker 1)**. The TODAY/ACTIVE/HISTORY/SAFETY
   navigation, the "RESEARCH CANDIDATE" banner/labeling and exact candidate fields, and
   integrating the M090 opportunity-engine's candidates into the existing
   `operator_console.py` are NOT built. The existing M088/M089 console (candidate review +
   approval + active positions + kill switch, one process, port 8086) remains the only
   running console; it does not yet present the ONE full-plan approval UI, does not yet
   create an `ApprovedPlan` row when the Owner approves, and does not yet start
   `PlanManagerThread` inside its process.
2. **The one-click full-plan approval endpoint (Release Blocker 2)**. The domain pieces
   (`ApprovedPlan`, system identity, `PositionPlanManager`) exist and are tested in
   isolation; the console ROUTE that lets the Owner approve a candidate once and have it
   create both the entry authorization AND the `ApprovedPlan` row in one action does not
   exist yet. This is the critical remaining wiring step -- the hard part (the automatic
   manager itself) is built and tested; the UI/endpoint that produces its input is not.
3. **Postgres persistence for `ApprovedPlan`**. Only the Protocol
   (`ApprovedPlanRepository`) and an in-memory fake exist. No Alembic migration, no
   `PostgresApprovedPlanRepository`, and therefore no PostgreSQL integration test exists
   yet -- `claim_exit_trigger`'s atomicity is proven against the in-memory fake's own lock,
   not against a real `UPDATE ... WHERE ... IS NULL RETURNING` under concurrent Postgres
   connections. This is the single highest-priority remaining item before any real
   deployment: the exactly-once claim is architecturally sound and unit-tested, but not
   yet proven under real Postgres concurrency the way `claim_dispatch` was for M085.
4. **Active Trade UI / History / Safety page content** exactly as specified (symbol,
   quantity, unrealized P&L, management status enum, "Automatic management is limited to
   the Owner-approved Paper plan" banner, manual-exit escape hatch, full History
   traceability fields) -- not built; these render data this pass's domain model can now
   supply, but the HTML/routes do not exist.
5. **Retiring the M090-M095 report consoles from "normal navigation"** -- not applicable
   yet, since there is no new consolidated navigation for them to be retired FROM. Their
   evidence files are untouched.
6. **Full mission test matrix A-V** -- tests A (full-plan immutable approval), D (no
   automatic entry without approval), I (partial fills), K (position-zero required for
   CLOSED), Q (no overnight intended position), S/T (Simulation/Live-impossible
   regression), U (mobile UI), V (autostart/bootstrap artifact presence) are either
   covered indirectly by existing M085-M089 tests reused unchanged, or not yet written as
   dedicated v1 tests, because the UI/endpoint they'd test (item 2 above) does not exist
   yet. B, C, E, F, G, H, J, L, M, N, O, P are directly and freshly proven by the test
   files listed above.
7. **CI / PR**. Not yet opened -- see GIT section of the final report.

## Why engineering stopped here rather than pushing further

This is an honest timeboxing decision, not a discovered blocker: Release Blockers 1 and 2
(console UI + the approval endpoint that creates an `ApprovedPlan`) and Blocker 4's
Postgres persistence are each a substantial, separate unit of real work, and the highest-
risk, hardest-to-get-right piece of the whole release -- the automatic unattended
position-reducing exit logic itself, including its collision-safety and crash-recovery
behavior -- is the piece this pass prioritized getting genuinely right and genuinely
tested against the real simulation broker, rather than spreading effort thin across every
blocker and risking a shallow, under-tested implementation of the part that submits real
orders without a human in the loop. The remaining work is substantial but is UI/wiring/
persistence work over an already-proven core, not open design risk.
