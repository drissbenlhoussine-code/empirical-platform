# MILESTONE-073 - One-Command Daily Research Workflow - Macro Milestone Freeze

## Status: FINAL - OWNER FROZEN

## Repository Authority

Repository `C:\Users\LuxSy\Documents\trading`, branch `master`. M073
baseline `f935913157a8fb8a50e01706f178f1c11b929426` (the M072 Owner
Freeze hash-recording HEAD; M072 fully `APPROVED_AND_FROZEN`),
independently re-verified at mission start and again during the
logically independent second pass (`git fetch`, `git status`,
`git rev-list --left-right --count HEAD...origin/master` agreed both
times: 0 ahead / 0 behind). Full governance and design decisions,
including the mandatory fresh 40-area product-reality audit, the live
daily-use simulation, the friction map, and the 9-candidate ranking,
are recorded in
`MILESTONE_073_ONE_COMMAND_DAILY_WORKFLOW_SCOPE_AND_DESIGN.md`.

## Delivered Capability

An operator can now run one real installed command,
`empirical-platform-daily-workflow`, and go from nothing to a
complete, real-data, legible daily research brief in a single step --
no hand-invented session identifier, no retyped universe/equity/
risk-percent defaults, no separate "now go run the brief command"
step. The command composes the frozen M070 `RunDailyResearchSessionHandler`
and the frozen M072 `BuildDailyResearchBriefHandler` directly, sharing
one PostgreSQL runtime so the just-created session's own identity
flows straight into the brief. Sensible, documented, overridable
defaults (today's date, a 20-day lookback, $100,000 equity, 1% risk)
remove the need to retype anything not genuinely operator-necessary.
Both text (default) and `--json` output derive from the same
authoritative brief model M072 already built.

## Implementation Evidence

- **Source:** one new file,
  `entrypoints/run_daily_research_workflow.py` -- pure composition
  -root orchestration, zero new domain model, zero new usecase module,
  zero new persistence. Plus one `pyproject.toml` console-script
  registration (`empirical-platform-daily-workflow`).
- **Tests:** 17 new pure unit tests (random session-id generation and
  its `RESEARCH-\d{4}` format, default artifact-path derivation, full
  argv parsing including all defaults/overrides/error paths, `main()`
  argv handling with the real network/DB function monkeypatched out,
  and the duplicate-symbol regression) + 4 real-network/PostgreSQL
  integration tests (one-command session-to-brief lifecycle with raw
  -SQL cross-verification, day-over-day comparison across two real
  invocations, an honest FAILED-session/WARNING path via a genuine
  invalid real ticker, and the real installed CLI subprocess with
  `--json`). Full default regression: `1833 passed, 351 skipped`,
  zero failures, **80.24% coverage -- met without any threshold
  adjustment**.

## Canonical Results

A live, real, two-day daily-use simulation (executed on a genuinely
fresh PostgreSQL environment, real Yahoo Finance data, real installed
CLI, before any implementation code was chosen) established the
friction this milestone closes: two separate commands, a hand-invented
session identifier, and fully retyped defaults every day. After
implementation, the same two-day scenario collapses to one command per
day, real data, real day-over-day comparison, confirmed twice more --
once during hostile review and once independently on a second, fresh
container with a different instrument pair (TSLA/NVDA) and different
dates.

## Hostile Review

82 explicit attack/verification cases were catalogued in
`external-review/MILESTONE-073/hostile-review-matrix.md`. One genuine
defect was found and fixed inline: a duplicate symbol in the requested
universe (e.g. `AAPL AAPL`) previously produced an uncaught Python
traceback, reproduced identically via the pre-existing, frozen
`run-daily-research` entrypoint -- confirming this was a genuine,
pre-existing M070 defect, not something M073 introduced. M070 was not
reopened; instead, the new entrypoint now rejects a duplicate symbol
with a clear error before the database or network are ever touched,
with two dedicated regression tests. A second, deliberately
non-obvious finding was documented rather than "fixed": two
back-to-back real-network invocations with identical inputs produce
identical semantic research decisions (genuine deterministic replay)
but a different `dataset_sha256`, because the underlying, unmodified
M065/M069 dataset artifact embeds acquisition-time provenance metadata
in the hashed bytes -- exactly the mission's own instruction that "if
external data changed... the hash must make the difference explicit,"
working as intended, not a defect.

## Canonical Validation

`ruff format --check .` clean on every M073-owned file (the same 4
pre-existing, unrelated M067 files remain flagged, confirmed to
predate M070, not touched). `ruff check .` clean. `mypy` (strict)
clean, 276 source files. `tools/check_architecture.py .` exit 0; the
negative fixture still correctly reports 31 violations. Full default
`pytest`: `1833 passed, 351 skipped`, 80.24% coverage. `pip_audit`: no
known vulnerabilities. Secret scan: 0 findings. Wheel build succeeded
with the new module present, including the
`empirical-platform-daily-workflow` console-script entry point;
package smoke-imports cleanly post-build.

## Logically Independent Second Pass

Full record: `external-review/MILESTONE-073/independent-second-pass.md`.
Summary: a genuinely fresh PostgreSQL container
(`m073-second-pass-pg`, port 32783, removed after use), Git truth
re-established independently, all 16 migrations applied cleanly from
empty, the real installed CLI driven against a deliberately different
instrument pair (TSLA/NVDA) and dates than every prior run this
session, every persisted value independently cross-checked via raw
`psql` queries, the duplicate-symbol fix re-attacked and re-confirmed
fixed, a claim-honesty grep run against the real rendered CLI output,
and the full M073 test suite re-run against this second, independent
container. The central claim was directly attacked from five angles
and held under every attempt.

## No Duplicated Business Logic / No New Schema / No Broker / No LLM

`grep -rniE "def evaluate|def rank_candidates|def build_trade_plan|def size_position|def run_backtest"`
across the new M073 file matches nothing. `grep -rniE
"place_order|submit_order|broker|live.?trade"` and `grep -rniE
"openai|anthropic|llm|gpt|chat_completion"` return nothing. `git diff
--stat` confirms zero new migration files.

## Product Reality Gate

1. **What exactly was the largest real product gap?** The daily
   morning routine required two separate commands, a hand-invented
   session identifier, and fully retyped universe/equity/risk-percent
   inputs every day -- confirmed by actually running the product
   end-to-end on a fresh environment before any implementation
   decision was made.
2. **Why did it outrank the alternatives?** It was the only candidate
   directly supported by friction observed while genuinely using the
   product, required zero new business logic and zero new schema, and
   satisfied the Product Value Rule on multiple axes (manual work
   removed, faster to know, more reliable to run) at the lowest
   implementation cost and premature-complexity risk of any candidate
   evaluated.
3. **What manual work disappeared?** Inventing a session governance
   id; retyping universe/equity/risk-percent every day; running a
   second, separate command to see the result.
4. **What can the operator now do that they could not do before?**
   Run one real command each morning and receive a complete,
   attention-prioritized, evidence-rich brief -- nothing else to run,
   nothing else to remember.
5. **Does the product become meaningfully more useful tomorrow?**
   Yes -- proven via a real, live before/after simulation with real
   market data, not asserted abstractly.
6. **What remains manual?** Choosing which symbols to research each
   day (no watchlist/auto-selection); remembering to actually run the
   command (no scheduling); reading and interpreting the brief.
7. **What remains research-only?** M062/M063 (holdout/robustness
   validation), M066 (statistical evidence), M067 (portfolio
   accounting), M068 (dependence evidence) -- all standalone CLIs,
   none wired into the daily workflow.
8. **Does M073 submit real trades?** No.
9. **Does M073 claim profitability?** No -- every brief still carries
   the same fixed, unconditional 5-statement claim-honesty tuple.
10. **Is the product ready for paper-trading evaluation?** Not yet.
    Per the mission's own Phase 7 gate, portfolio/risk evidence must
    be sufficiently integrated into daily research first; this audit
    freshly re-confirmed that integration remains `ABSENT`.
11. **Is it ready for live trading?** No, and by design never will be
    without a separate, explicit, human-gated broker-integration
    milestone that does not exist anywhere in this codebase.
12. **What is the single biggest blocker after M073?** The missing
    "concurrent-position handling" / portfolio-integration bridge --
    there is still no way for the daily workflow to know about
    already-open positions or connect to genuine M067/M068 evidence,
    which blocks both richer daily risk evidence and any legitimate
    future paper-trading milestone.

**No claim of profitability, live-trading readiness, or investment
advice is made anywhere in this milestone.** M073 makes the existing
daily research product runnable as one coherent, low-friction habit
for the first time; it does not certify any strategy as profitable or
ready for real capital.

## Owner Approval

All phases of the M073 mission specification are complete: repository
truth verified; a fresh 40-area product-reality inventory; a real,
live two-day daily-use simulation executed before any implementation
decision; an honest friction map derived from that live run; a
9-candidate ranking against 8 required criteria with each rejected
candidate given a specific, falsifiable reason (M067/M068 integration
correctly gated on a missing prerequisite, not merely deferred by
habit; paper trading correctly rejected per the mission's own Phase 7
precondition); a concise design; immediate implementation with zero
new business logic and zero new schema; 17 pure unit tests plus 4 real
PostgreSQL/network/CLI integration tests, including a mandatory
deterministic-replay proof and a genuine failure-scenario
demonstration; an 82-case hostile review with one genuine defect found
and fixed inline (with regression protection) and one genuine, honest
observation documented rather than silently accepted; full canonical
validation with coverage met without adjustment; a logically
independent second pass on a genuinely fresh container with a
deliberately different universe that directly attempted and failed to
disprove the central claim; and the 12-question product reality gate
above. Zero blockers remain for this milestone's own scope.

**Freeze declaration:** `M073 MACRO MILESTONE APPROVED_AND_FROZEN`.
`M073 APPROVED_AND_FROZEN`.

## Deferred / M073 Boundary

Explicitly out of scope and not built: M067 portfolio integration and
M068 dependence integration (both gated on a "concurrent-position
handling" concept that does not yet exist, freshly re-confirmed
absent), persistent operator configuration/profile beyond the new
command's own CLI-level defaults, data-source fallback/reliability,
automatic universe selection, alert delivery channels beyond the
brief's own existing attention surface, session-trend summaries beyond
M071, report export, paper trading (explicitly gated on the missing
portfolio/risk integration precondition), live trading, any
LLM-based decision or rendering path. **MILESTONE-074 was explicitly
NOT built, per the mission's own instruction.**

## Next Permitted Action

MILESTONE-074 -- recommendation only; not started as part of M073.
