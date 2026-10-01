# EMPIRICAL PLATFORM v1 -- Personal Paper Release: engineering status

Branch `release/v1-personal-paper`, from the exact latest green stack tip
(`ed9215301f53c3eb9e029caf26be843b57d4f941`, M095/PR #25's head). Five engineering passes.
**Engineering is complete and CI is genuinely green (6/6).** See FINAL STATUS in the final
report.

## What this branch has built, and proved with real tests

1. **Kill switch semantics**, **`ApprovedPlan` domain model** (12 tests), **`PositionPlanManager`**
   automatic exit engine (7 tests over the real simulation broker), **Postgres persistence**
   for `ApprovedPlan` under real concurrent-connection racing (12 integration tests against
   real PostgreSQL 16), **`approve_full_plan`** the one-click entry+plan connector (5 tests),
   entry-governance regression lock, architecture boundary tests, autostart artifacts,
   Research Candidate labeling/fields/banner, `PlanManagerThread` running live inside the
   console process (4 tests), the Safety page's exact statements, Active Trade and History
   page content (`v1_management_status.py`'s pure MANAGEMENT STATUS derivation, 8 tests;
   `approved_plan_block`/`history_page`'s Plan column; 10 more tests on the extracted
   per-row helpers) -- from earlier passes.

2. **This pass: a real bug found and fixed, plus true end-to-end HTTP coverage.** The
   three new route overrides (`/active`, `/history`, `/confirm-approval`) had NO error
   handling -- unlike every other route in this console, a `ConsoleRefusalError` or
   unexpected exception would have propagated as a raw, uncaught exception through the
   WSGI app instead of the graceful error page every other route shows. Fixed: all three
   now wrap their body in try/except and call the SAME `refusal()` helper `paper_health_
   route`/`prepare_candidate_route` already use. The per-row computation was extracted
   into two module-level, directly-testable functions (`active_plan_block_for_row`,
   `history_plan_cell_for_row`). 15 new tests, including ONE full real round trip through
   the actual WSGI router over an in-memory, PAPER-shaped `PaperConsoleBackend`: prepare a
   candidate, review it, POST `/confirm-approval` with a real CSRF token and ticket, and
   verify the `ApprovedPlan` it creates is then rendered on both `/active` and `/history`
   -- the first test in this release to exercise these routes over HTTP rather than only
   at the domain/connector layer. One more edge case closed in `full_plan_approval.py`'s
   own suite: losing a `save()` race against another caller reads back the winner instead
   of erroring.

**Full regression proof**: the exact default `python -m pytest` CI runs (all of `tests/`,
not a scoped subset) -> **5012 passed, 1329 skipped, 0 failed**. `tests/unit
tests/architecture` alone -> **4476 passed, 0 failed**. Postgres suites (new + full
existing M085-M090) -- **35 passed, 0 failed**, against real PostgreSQL 16. `ruff check`,
`ruff format`, `mypy` (scoped to `src/empirical_platform`, matching this project's own
mypy config), `tools/check_architecture.py`, `tools/secret_scan_targets.py` all clean.

## A note on the coverage-percentage line, resolved

CI's `verify` job prints `FAIL Required test coverage of 79.0% not reached. Total
coverage: 78.64%` from `pytest-cov`'s own report step -- but exits 0 and the job passes,
because `coverage.py`'s `fail_under` comparison (`[tool.coverage.report]` in
`pyproject.toml`) is evaluated against the ROUNDED percentage by default: 78.64% rounds to
79, which is not less than `fail_under = 79`, so the gate clears even though the displayed
decimal reads under it. This is standard, documented `coverage.py` behavior, not a
misconfiguration -- confirmed directly from the raw CI job logs (no `##[error]`, exit code
0) and cross-checked against an EARLIER push in this same pass that genuinely DID fail
hard (`total of 78 is less than fail-under=79`, `##[error]Process completed with exit code
1`) when the number was 78.46%, which rounds to 78. The ~15 tests this pass added
(closing real, previously-uncovered route-handler logic -- see above, not padding) moved
the number from 78.46% to 78.64%, crossing the rounding boundary. Two earlier failures in
this pass were a ruff-format drift (a post-edit file never re-formatted) and the
coverage-rounding boundary itself, both now fixed/resolved; neither is a remaining
concern.

## What remains out of scope for this branch

- **Release Blocker 5** (one real, Owner-approved Paper BUY -> automatic exit ->
  SELL_TO_CLOSE round trip against the real Alpaca paper endpoint) and the **5-session
  pilot**: never attempted here, by design -- reserved for the coordinating session to run
  directly with the Owner.
- Live verification against a `--capability paper-exit` backend with REAL Alpaca
  credentials: this environment has none. The equivalent in-memory, fake-broker HTTP round
  trip (prepare -> review -> approve -> plan created -> rendered on Active/History) IS now
  proven end-to-end; what remains unverified is specifically the real-credential
  composition root itself (`_paper_position_exit_composition.py`'s context manager), which
  requires Release Blocker 5's own real round trip to exercise for the first time.

## Engineering is complete

Every named Release Blocker and UI item from the mission has real, working code and real
tests behind it, all changes to the shared, already-proven M086/M088/M089 console were
additive and guarded (verified by the full existing regression suite passing unchanged),
and CI is genuinely green end to end.
