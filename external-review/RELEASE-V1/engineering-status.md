# EMPIRICAL PLATFORM v1 -- Personal Paper Release: engineering status

Branch `release/v1-personal-paper`, from the exact latest green stack tip
(`ed9215301f53c3eb9e029caf26be843b57d4f941`, M095/PR #25's head). Five engineering passes.
All FEATURE work is complete and tested; CI is red for exactly one reason, named precisely
below -- see FINAL STATUS in the final report.

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
   per-row helpers) -- all from earlier passes, unchanged this pass.

2. **This pass: a real bug found and fixed, plus the first true end-to-end HTTP coverage
   of the v1 routes.** The three new route overrides (`/active`, `/history`,
   `/confirm-approval`) had NO error handling -- unlike every other route in this console,
   a `ConsoleRefusalError` or unexpected exception would have propagated as a raw,
   uncaught exception through the WSGI app instead of the graceful error page every other
   route shows. Fixed: all three now wrap their body in try/except and call the SAME
   `refusal()` helper `paper_health_route`/`prepare_candidate_route` already use. The
   per-row computation was also extracted into two module-level, directly-testable
   functions (`active_plan_block_for_row`, `history_plan_cell_for_row`). 15 new tests,
   including ONE full real round trip through the actual WSGI router over an in-memory,
   PAPER-shaped `PaperConsoleBackend`: prepare a candidate, review it, POST
   `/confirm-approval` with a real CSRF token and ticket, and verify the `ApprovedPlan` it
   creates is then rendered on both `/active` and `/history` -- the first test in this
   release to exercise these routes over HTTP rather than only at the domain/connector
   layer.

**Full regression proof**: `PYTHONPATH=...\v1-release\src pytest tests/unit
tests/architecture -q` -> **4476 passed, 0 failed**. Postgres suites (new + full existing
M085-M090) -- **35 passed, 0 failed**, against real PostgreSQL 16. `ruff check`, `ruff
format`, `mypy` (scoped to `src/empirical_platform`, matching this project's own mypy
config), `tools/check_architecture.py`, `tools/secret_scan_targets.py` all clean.

## The one remaining item: CI's coverage-percentage gate, named precisely

`pyproject.toml` enforces `fail_under = 79` over the FULL default `pytest` run (all of
`tests/`, not just `tests/unit`+`tests/architecture` -- this is a materially different,
LARGER scope than every coverage number quoted in this document's earlier passes, which
were always scoped to `tests/unit tests/architecture` and never actually matched what CI
enforces). Running the exact default `python -m pytest` locally: **5034 passed, 1307
skipped, 0 failed -- but total coverage 78.64%, 0.36 points under the 79% gate.**

This is NOT a test failure, NOT a logic bug, and NOT something more unit tests can close
within reasonable effort. The shortfall is concentrated in composition-root code that
requires real Alpaca and Postgres credentials to execute even once:
- `_paper_position_exit_composition.py` (53% -- the `paper_operator_console_with_exit_
  runtime()` context manager body, lines 106-198, is one continuous block that opens a
  REAL `PostgresPersistenceService` against Store A/B/C and a REAL `AlpacaPaperClient`;
  it cannot be partially executed).
- `_paper_operator_console_composition.py` (80%, the plain-PAPER equivalent).
- `shared/persistence/postgres_repositories/approved_plan_repositories.py` (33% --
  matches, almost exactly, the ALREADY-ESTABLISHED, ALREADY-ACCEPTED baseline of its
  sibling Postgres repositories in this same codebase: `position_exit_repositories.py`
  and `paper_execution_repositories.py` are BOTH at 36% in this same default run, and
  have been since M087/M085 -- this is not a new problem this branch introduced, it is
  the same, pre-existing shape of problem, just one more file.

This is the EXACT class of exception `pyproject.toml`'s own `[tool.coverage.report]`
section already documents and accepts for M070's `RunDailyResearchSessionHandler`: a
large, real, DB/credential-orchestrating method "exhaustively covered by real PostgreSQL/
CLI/network integration tests, just not by this default (non-Postgres) coverage run,"
where "building a full in-memory fake [...] stack solely to force offline coverage of
already-[integration]-tested orchestration code would be new, unprecedented test
infrastructure disproportionate to the fractional gap it would close." That comment also
records the ONE time this floor was deliberately, explicitly lowered (from 80 to 79) to
accommodate exactly this class of file -- a conscious, documented, one-time decision, not
something made routinely or unilaterally by whoever's branch happens to tip the balance.

**I have not touched `fail_under`, and will not** -- lowering a project-wide quality gate
to force a specific branch green is exactly the kind of gate-weakening this project's own
discipline forbids, and the decision about whether THIS gap warrants the same one-time
treatment M070 received is the Owner's/coordinating session's to make, not mine. What I
have done instead, across the last two passes, is add real, substantial, legitimate
coverage wherever it was actually achievable without disproportionate new infrastructure
(adding ~0.2 points back from this pass's 15 tests alone), while being honest that the
remaining ~0.36-point gap sits in exactly the kind of credential-requiring composition
code this codebase has already, once, formally decided not to chase.

## Options for closing this, for the coordinator to choose from (not decided here)

1. A documented, one-time `fail_under` adjustment (the M070 precedent), with a comment of
   the same shape explaining why.
2. Building real Postgres+Alpaca-credentialed integration tests for the two composition
   functions (a genuinely new, non-trivial piece of test infrastructure -- most similar to
   what `tests/integration/test_m089_paper_exit_postgres.py` already does for the
   sibling exit composition, extended to also open Store A's plan connection).
3. Accept CI as-is and merge with an explicit, recorded exception (outside my authority to
   decide).

I have not picked one -- this is a project-quality-gate decision, not an engineering
judgment call I'm positioned to make alone.
