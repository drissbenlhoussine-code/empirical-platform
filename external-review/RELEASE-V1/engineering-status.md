# EMPIRICAL PLATFORM v1 -- Personal Paper Release: engineering status

Branch `release/v1-personal-paper`, from the exact latest green stack tip
(`ed9215301f53c3eb9e029caf26be843b57d4f941`, M095/PR #25's head). Three engineering passes
so far. This is an honest progress record, not a "done" claim -- see FINAL STATUS in the
final report.

## What this branch has actually built, and proved with real tests

1. **Kill switch semantics**. An engaged kill switch blocks new entries only, never a
   position-reducing exit. `docs/operations/kill-switch.md`.

2. **`ApprovedPlan` domain model** (`decision_candidate/approved_plan.py` +
   `approved_plan_repositories.py`). Pure, frozen, immutable terms, a deterministic
   `system_identity`, the pure `evaluate_exit_trigger` function. 12 unit tests, zero I/O.

3. **`PositionPlanManager`** (`usecases/position_plan_manager.py`) -- the automatic exit
   engine. Polls durable `ApprovedPlan`s, evaluates stop/target/mandatory-exit, durably
   claims the right to act, dispatches through the EXISTING, unmodified exit-pipeline
   handlers with `authorized_by` set to the plan's system identity. 7 tests over the real
   simulation broker and real M087 exit handlers: stop/target/mandatory triggers, two
   managers racing to exactly one exit, simulated restart recovery.

4. **Postgres persistence for `ApprovedPlan`**. Migration `b9f2c4d6a8e1`, its own
   `require_exact_v1_approved_plan_schema_head` guard, database-level triggers for
   claim-once and immutable-terms. **12 integration tests against real PostgreSQL 16**,
   including 8 real concurrent connections racing the identical claim, exactly one wins. A
   genuine SQL-text-vs-bind-parameter bug was caught and fixed by this local testing before
   reaching CI.

5. **`approve_full_plan`** (`usecases/full_plan_approval.py`) -- one Owner action creates
   the entry authorization AND the durable plan, sourcing stop/target/quantity from the
   FRESH M085 proposal, never stale research numbers. Idempotent/resumable; 5 tests over
   the real simulation broker and real M084-M086 handler chain.

6. **Entry-governance regression lock**, **architecture boundary tests** (no BUY/Live
   surface reachable from the manager/plan modules), **autostart artifacts**.

7. **Console wiring (this pass)** -- Release Blocker 1/2's actual UI integration, built as
   surgical, low-risk extensions of the EXISTING, already-proven M086/M088/M089 console
   rather than a new console:
   - **Research Candidates surface**: the console's existing "opportunity card" (an M085
     `TradeProposal` under review -- the SAME mechanism PAPER's own "Prepare today's Paper
     candidate" button already originates one through, via `prepare_paper_candidate`, a
     real live-evidence-gathering pipeline that already existed) now carries the exact
     mission fields and labeling: a `RESEARCH CANDIDATE` badge, the exact banner text
     ("Research strategy — profitability has not been validated."), Entry/Stop/Target/
     Quantity/Max Loss/Target Gain/R:R/Mandatory Exit, "Why this candidate" (relabeled
     evidence), "Invalid if", and a `REVIEW PLAN` button (renamed from "Approve" -- it
     already led to a review-then-confirm screen, so the behavior was already correct, only
     the label was wrong). A dedicated whole-module test
     (`test_v1_research_candidate_labeling.py`) asserts "recommended"/"best trade"/
     "profitable"/"guaranteed" never appear anywhere in the console's HTML source.
   - **`approve_full_plan` wired to the real route**: `paper_operator_console_app.py`
     overrides `/confirm-approval` (only for the exit-capable composition,
     `backend._plans is not None`) to call `approve_full_plan` instead of
     `service.confirm_approval` directly -- the plain SIMULATION console and M088's own
     plain PAPER composition are completely untouched (verified by the pre-existing
     `test_m088_composition_has_no_source_dependency_on_m089`-style boundary test, which
     still passes).
   - **`PositionPlanManager` now runs inside the console process**: `_serve_with_
     reconciler` starts a `PlanManagerThread` alongside the existing M085 reconciler thread
     (same process, same shutdown-ordering discipline -- stopped and joined before the
     runtime's persistence closes), when `--capability paper-exit` is used. 4 new tests
     (`test_v1_plan_manager_thread.py`) prove the thread starts, polls at least once, a
     failed tick doesn't stop the loop, and stop is idempotent and actually joins.
   - **Safety page**: carries the exact mission statements (Environment/Live/Strategy
     profitability/Automatic authority, the explicit "No:" list) alongside the pre-existing
     kill-switch control. Tested end-to-end over the real router
     (`test_v1_safety_page.py`).
   - **M090-M095 report-console retirement**: verified, not assumed -- grepped the
     console's own HTML module for any port/route reference to those consoles; there was
     never one (they are, and always were, separate processes on separate ports, never
     linked from this console's own navigation). Nothing to remove.

**Full regression proof**: `PYTHONPATH=...\v1-release\src pytest tests/unit
tests/architecture -q` -> **4445 passed, 0 failed** (coverage-PERCENTAGE gate still fails
at 75.36%, the same pre-existing, documented, non-regression condition since M093).
Postgres suites (new + full existing M085-M090) -- **35 passed, 0 failed**. `ruff check`,
`ruff format`, `mypy`, `tools/check_architecture.py`, `tools/secret_scan_targets.py` all
clean.

## What remains -- named honestly

1. **Active Trade UI content** exactly as specified (Symbol/Quantity/Entry avg fill/Current
   price/Unrealized P&L, the APPROVED PLAN block, the MANAGEMENT STATUS enum derived from
   the plan's claim/dispatch state, the "Automatic management is limited to the
   Owner-approved Paper plan" banner, a REVIEW MANUAL EXIT escape hatch) -- NOT built. The
   existing `/active` page shows open positions and the manual exit flow; it does not yet
   render `ApprovedPlan`/`PlanEvaluationOutcome` data, which the domain layer can now fully
   supply.
2. **History page traceability** (Research Candidate ID, exit trigger type
   STOP/TARGET/MANDATORY_EXIT/MANUAL_OWNER_EXIT, full plan lineage) -- NOT built. The
   existing `/history` page shows completed M085 executions; it does not yet join in
   `ApprovedPlan`/claim data.
3. **Remaining test matrix items genuinely untested at the UI layer**: A (full-plan
   immutable approval -- proven at the domain/connector layer already, not yet at the
   `/confirm-approval` route layer with a live `--capability paper-exit` backend, since
   that requires real Alpaca credentials this environment does not have), I (partial fills
   on the ACTIVE page -- blocked on item 1), K (position-zero before HISTORY shows CLOSED --
   blocked on item 2), Q (no overnight intended position as a dedicated assertion over
   `ApprovedPlan`'s own mandatory-exit-before-session-close invariant -- the domain
   construction already structurally prevents a nonsensical deadline via
   `MANDATORY_EXIT_SAFETY_BUFFER_SECONDS`, but no test states this as its own named claim
   yet), U (mobile/responsive check on the specific NEW markup added this pass -- the
   console's existing layout is already mobile-first per M086, not independently
   re-verified for the new Research Candidate card fields).
4. **D and S/T are, on inspection, already covered**: D (no automatic entry without Owner
   approval) is true by construction -- `approve_full_plan` only ever calls the existing,
   human-ticket-gated `confirm_approval`, never originates an entry itself; T (Live
   impossible) is proven by this branch's own architecture tests
   (`test_v1_position_plan_manager_boundaries.py`); S (Simulation regression) is proven by
   the full regression suite passing unchanged for the SIMULATION capability.

## Why engineering stopped here

Three passes have delivered the full safety-critical core (automatic exit engine,
Postgres-durable claim proven under real concurrency, the approval connector) AND wired it
into the real, already-proven console process -- a real Owner can now see a labeled
Research Candidate, click REVIEW PLAN, approve it, and have the automatic manager start
monitoring it inside the same running process, with zero new broker-write surface and zero
regressions anywhere in the existing suite. What remains (Active/History page content,
rounding out the UI-layer test matrix) is presentation work over data the domain layer
already fully supplies -- lower-risk than anything already built, but still real,
un-skipped work that deserves the same rigor (real tests over the real router) rather than
a rushed finish.
