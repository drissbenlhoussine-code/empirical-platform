# EMPIRICAL PLATFORM v1 -- Personal Paper Release: engineering status

Branch `release/v1-personal-paper`, from the exact latest green stack tip
(`ed9215301f53c3eb9e029caf26be843b57d4f941`, M095/PR #25's head). Four engineering passes.
Engineering is now complete -- see FINAL STATUS in the final report. Release Blocker 5 (the
real governance acceptance) and the 5-session pilot remain entirely out of scope for this
branch, reserved for direct Owner interaction.

## What this branch has built, and proved with real tests

1. **Kill switch semantics**. An engaged kill switch blocks new entries only, never a
   position-reducing exit. `docs/operations/kill-switch.md`.

2. **`ApprovedPlan` domain model** -- pure, frozen, immutable terms, a deterministic
   `system_identity`, the pure `evaluate_exit_trigger` function. 12 unit tests, zero I/O.

3. **`PositionPlanManager`** -- the automatic exit engine. Polls durable `ApprovedPlan`s,
   evaluates stop/target/mandatory-exit, durably claims the right to act, dispatches
   through the EXISTING, unmodified exit-pipeline handlers. 7 tests over the real
   simulation broker and real M087 exit handlers.

4. **Postgres persistence for `ApprovedPlan`** -- migration `b9f2c4d6a8e1`, its own schema-
   head guard, database-level triggers for claim-once/immutable-terms. 12 integration
   tests against real PostgreSQL 16, including 8 real concurrent connections racing the
   identical claim, exactly one wins.

5. **`approve_full_plan`** -- one Owner action creates the entry authorization AND the
   durable plan, sourcing stop/target/quantity from the FRESH M085 proposal. Idempotent/
   resumable; 5 tests over the real simulation broker and real M084-M086 handler chain.

6. **Entry-governance regression lock**, **architecture boundary tests** (no BUY/Live
   surface reachable), **autostart artifacts**.

7. **Console wiring**: Research Candidate labeling/fields/banner on the existing
   opportunity card (with a whole-module no-superlative-language test), `approve_full_plan`
   wired to the real `/confirm-approval` route (exit-capable composition only), the
   automatic manager running live inside the console process via `PlanManagerThread`
   (4 tests: starts, polls, survives a bad tick, stops cleanly), and the Safety page's
   exact mission statements (tested end-to-end over the real router). Verified, not
   assumed, that nothing ever linked to the M090-M095 report consoles from this console's
   own navigation -- there was nothing to retire.

8. **Active and History page content (this pass)** -- the final two UI items:
   - **`usecases/v1_management_status.py`**: a pure function deriving the mission's exact
     MANAGEMENT STATUS word (Monitoring / Stop triggered / Target triggered / Mandatory
     exit triggered / Exit submitted / Needs attention / Closed) from an `ApprovedPlan`'s
     durable claim state and its exit attempt's state -- an ambiguous outcome
     (`SUBMISSION_UNKNOWN`) or a terminal-but-unverified attempt both read as "Needs
     attention," never guessed into a falsely reassuring status. 8 pure unit tests cover
     every transition, including the ambiguous-outcome case explicitly.
   - **`_operator_console_html.py::approved_plan_block`**: a new, self-contained renderer
     for the APPROVED PLAN block on an Active Trade card -- Quantity, Entry avg fill,
     Current price, Unrealized P&L, Stop, Target, Mandatory Exit, Max Loss, the
     MANAGEMENT STATUS chip, the fixed "Automatic management is limited to the
     Owner-approved Paper plan" banner, and a REVIEW MANUAL EXIT link (reusing the
     EXISTING human-authorized `/exit/review` route -- a pure escape hatch, never a
     dependency of the automatic manager, which has never read this link). `active_page`
     gained an optional `plan_blocks` mapping (keyed by intent id, defaulted to empty) so
     SIMULATION and plain PAPER render byte-identically to before.
   - **`history_page`**: gained an optional `plan_cells` mapping (keyed by intent/proposal
     id, defaulted to empty) adding a "Plan" column ONLY when given one -- Research
     Candidate ID, Owner approval reference, exit trigger type, exit broker order + fill,
     position-zero verification, and gross realized P&L (computed only from real
     attempt/proposal fields already on record -- no invented fees, no new parallel data
     model; sourced from the SAME `ApprovedPlan`/exit-attempt repositories the automatic
     manager and the manual exit flow already read).
   - **Route wiring**: `paper_operator_console_app.py` overrides `/active` and `/history`
     (exit-capable composition only, same `backend._plans is not None` guard as
     `/confirm-approval`) to build these mappings from `backend._plans` and the newly
     exposed `backend._exits`, and pass them through. SIMULATION and plain PAPER are
     unaffected -- neither route is overridden for them.
   - **11 new tests** (`test_v1_management_status.py` x8, `test_v1_active_history_plan.py`
     x7 -- overlap is the shared pure function under both direct and page-rendering
     tests): the APPROVED PLAN block renders every required field; the manual-exit link is
     present only when offered; a "Needs attention" status is visible on a rendered Active
     page; a plan block appears only for its own matching row, never leaking onto another
     position's card; the History "Plan" column is absent by default and present with
     every required fact when given; a no-superlative-language check on the plan-rendering
     source, the same discipline the Candidates page already proves.

**Full regression proof**: `PYTHONPATH=...\v1-release\src pytest tests/unit
tests/architecture -q` -> **4460 passed, 0 failed** (coverage-PERCENTAGE gate still fails
at 75.26%, the same pre-existing, documented, non-regression condition since M093).
Postgres suites (new + full existing M085-M090) -- **35 passed, 0 failed**. `ruff check`,
`ruff format`, `mypy`, `tools/check_architecture.py`, `tools/secret_scan_targets.py` all
clean.

## What remains genuinely out of scope for this branch

- **Release Blocker 5** (one real, Owner-approved Paper BUY -> automatic exit ->
  SELL_TO_CLOSE round trip against the real Alpaca paper endpoint) and the **5-session
  pilot**: never attempted here, by design -- these require live credentials and a human
  in the loop, reserved for the coordinating session to run directly with the Owner.
- End-to-end verification of `/active` and `/history` against a LIVE `--capability
  paper-exit` backend (real Alpaca credentials) was not possible in this environment; the
  rendering itself is tested directly and thoroughly (11 tests), and the route-override
  wiring follows the identical, already-proven pattern used for `/confirm-approval` (same
  guard, same backend fields), but the full HTTP round trip through a live backend has not
  been separately exercised.
- Items from the mission's full test-matrix letters that are either covered indirectly by
  existing M085-M089 tests reused unchanged, or are true by construction rather than by a
  dedicated new test (D: `approve_full_plan` only ever calls the existing human-ticket-
  gated `confirm_approval`, never originates an entry itself; T: proven by this branch's
  own architecture tests; S: proven by the unchanged SIMULATION regression suite) were
  already covered as of the previous pass's report.

## Engineering is complete

Every named Release Blocker and UI item from the mission has real, working code and real
tests behind it: the automatic exit engine (collision-safe, crash-recoverable, Postgres-
durable under proven real concurrency), the one-click approval connector, the Research
Candidates surface, the Safety page, and now the Active Trade and History pages. All
changes to the shared, already-proven M086/M088/M089 console were additive and guarded
(new optional parameters defaulting to today's exact behavior, route overrides gated on
`backend._plans is not None`), so SIMULATION and plain PAPER are provably unaffected --
verified by the full existing regression suite passing unchanged, not just argued.
