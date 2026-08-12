# MILESTONE-071 - Daily Research Continuity - Macro Milestone Freeze

## Status: FINAL - OWNER FROZEN

## Repository Authority

Repository `C:\Users\LuxSy\Documents\trading`, branch `master`. M071
baseline `66cd0c945d969a8177e0917fdeda3d557dfbb5fb` (the M070 Owner
Freeze hash-recording HEAD; M070 fully `APPROVED_AND_FROZEN`),
independently re-verified at mission start and again during the
logically independent second pass (`git fetch`, `git status`,
`git rev-list --left-right --count HEAD...origin/master` agreed both
times: 0 ahead / 0 behind). Full governance and design decisions,
including the mandatory fresh gap analysis across 15 named areas and a
5-candidate ranking, are recorded in
`MILESTONE_071_DAILY_RESEARCH_CONTINUITY_SCOPE_AND_DESIGN.md`.

## Delivered Capability

An operator can now find a daily research session without already
knowing its exact runtime id, and see exactly what changed since the
last research session for the same instruments. Two new, purely
additive query capabilities extend the existing `ResearchSessionRepository`
Protocol: `list_recent()` (session history, optionally filtered to an
exact universe) and `find_most_recent_prior()` (the basis for day-over
-day comparison). A new, pure `compare_session_decisions()` diff
function classifies each instrument as NEW / DROPPED / CHANGED /
UNCHANGED between a target session and its own most recent prior
session sharing the same universe -- computed on demand from two
already-persisted sessions, never itself persisted as a new entity. Two
new real installed CLI commands
(`empirical-platform-list-daily-research`,
`empirical-platform-compare-daily-research`) expose both capabilities.
Zero new PostgreSQL tables; one purely additive index.

## Implementation Evidence

- **Source:** `decision_candidate/research_session.py` (extended with
  `ResearchSessionSummary`, `SessionComparisonEntry`,
  `SessionComparisonOutcome`, `compare_session_decisions`),
  `decision_candidate/research_session_repository.py` (Protocol
  extended with `list_recent`/`find_most_recent_prior`),
  `shared/persistence/postgres_repositories/research_session_repository.py`
  (concrete implementation), `usecases/list_daily_research_sessions.py`,
  `usecases/compare_daily_research_sessions.py`,
  `usecases/research_session_io.py` (extended with the list/comparison
  payload serializers), `entrypoints/list_daily_research_sessions.py`,
  `entrypoints/compare_daily_research_sessions.py`, one new additive
  migration (`31365632c016`, an index on `research_session(as_of)`),
  and `pyproject.toml` console-script registration.
- **Tests:** 45 new pure unit tests (29 for the domain-level
  `ResearchSessionSummary`/`SessionComparisonEntry`/
  `compare_session_decisions` diff function; 16 for the usecase-layer
  handlers against a fake repository, both payload serializers, and
  both CLI entrypoints' argv handling) + 6 PostgreSQL integration tests
  (full lifecycle with genuine day-over-day list+compare+raw-SQL
  verification, universe-filter correctness, day-1 no-prior-session
  semantics, cross-universe non-comparison, comparison against a FAILED
  baseline, and a real installed CLI subprocess run). Full default
  regression: `1767 passed, 342 skipped`, zero failures, **80.05%
  coverage -- met without any threshold adjustment**, unlike M070's
  after-the-fact scramble, because these ~45 tests were written
  proactively alongside the implementation.

## Canonical Results

The same `FakeMarketDataSource` fixture bytes, evaluated at two
different `as_of` dates (day 5, flat; day 10, the first genuine
breakout bar), produced a real, unforced day-over-day state transition:
`NO_TRADE -> LONG_CANDIDATE` for both AAPL and MSFT. `list_recent`
correctly ordered both sessions most-recent-first; `compare` correctly
identified the baseline and classified both instruments `CHANGED`,
independently confirmed via raw SQL. The independent second pass
repeated this against a genuinely fresh container with a deliberately
different instrument pair (NVDA/AMD) and a different calendar month,
additionally surfacing that the comparison correctly threads trade-plan
-level state (`REJECTED_PLAN`, from the frozen M059 risk gate
independently rejecting both breakout candidates), not just scan-level
state.

## Hostile Review

63 explicit attack/verification cases were catalogued in
`external-review/MILESTONE-071/hostile-review-matrix.md`. Five genuine
findings were made and fixed inline during this pass:

1. **`unnest(unknown)` ambiguity** -- PostgreSQL could not resolve which
   `unnest` overload to use for an untyped bind parameter; fixed with
   an explicit `CAST(:universe AS text[])`.
2. **`:param::type` SQLAlchemy tokenizer conflict** -- the `::` cast
   operator directly touching a named bind parameter caused SQLAlchemy
   to silently fail to bind the parameter at all (a genuinely dangerous
   silent-failure shape, not an immediate error); fixed by using
   `CAST(...)` instead.
3. **Non-deterministic `ORDER BY` under a tied `(as_of, created_at)`**
   -- reproduced directly with a genuine 3-way tie; fixed by adding
   `runtime_id DESC` as a final, always-unique tiebreaker to both new
   query methods.
4. **An entrypoint importing `decision_candidate` directly**, violating
   the established architecture boundary -- fixed by re-exporting
   through the usecase layer's own `__all__`, matching the M070
   precedent exactly.
5. **A test-fixture design flaw**: the intended "breakout" as_of date
   initially fell one day too late, where the reference window itself
   had already absorbed the prior day's own elevated high/volume,
   silently masking the breakout signal -- found via direct
   smoke-testing, root-caused by reading the frozen M057 `evaluate()`
   function directly, and fixed by moving the as_of date to the exact
   first breakout day.

No genuine defect was found in the day-1 semantics, the cross-universe
non-comparison guarantee, the FAILED-baseline handling, the payload
sectioning, or the no-new-business-logic boundary.

## Canonical Validation

`ruff check .` clean. `ruff format --check .` clean on every M071
-owned file (the same 4 pre-existing, unrelated M067 files remain
flagged, confirmed to predate even M070, not touched). `mypy` (strict)
clean, 271 source files. `tools/check_architecture.py .` exit 0; the
negative fixture still correctly reports 31 violations. Full default
`pytest`: `1767 passed, 342 skipped`, 80.05% coverage. `pip_audit`: no
known vulnerabilities. Secret scan: zero genuine findings across 920
tracked/relevant files. Wheel build succeeded with every new M071
module present; package smoke-imports cleanly post-build.

## Logically Independent Second Pass

Full record: `external-review/MILESTONE-071/independent-second-pass.md`.
Summary: a genuinely fresh PostgreSQL container
(`m071-second-pass-pg`, port 32781, removed after use), Git truth
re-established independently, all 16 migrations applied cleanly from
empty, the real installed CLIs driven against a deliberately different
instrument pair and calendar month than every prior run this session,
every persisted value independently cross-checked via raw `psql`
queries, and the full offline/Postgres test suite re-run against this
second, independent container. The central claim was directly attacked
from four angles and held under every attempt.

## No Duplicated Business Logic / No New Schema Beyond One Index / No Broker / No LLM

`grep -rniE "def evaluate|def rank_candidates|def build_trade_plan|def size_position|def run_backtest"`
across every new M071 file matches only frozen imports, never a new
definition. `grep -rniE "place_order|submit_order|broker|live.?trade"`
and `grep -rniE "openai|anthropic|llm|gpt|chat_completion"` across all
new M071 source return nothing. `git diff --stat` confirms exactly one
new migration, an index, with zero `CREATE TABLE`.

## Product Honesty Gate (Reality Gate)

1. **Can an operator now find a session without already knowing its
   exact runtime id?** **YES.** `list_recent`/`empirical-platform-list
   -daily-research`, proven on two independent PostgreSQL environments.
2. **Does day-over-day comparison reflect genuine, meaningful state
   changes, not merely a trivial day-1 NEW-everything result?** **YES.**
   A real `NO_TRADE -> LONG_CANDIDATE` transition was proven twice,
   independently, with two different instrument pairs.
3. **Is any new strategy/ranking/risk/sizing/backtest math introduced?**
   **NO.** `compare_session_decisions` is a pure structural diff over
   already-computed decision fields.
4. **Is any new PostgreSQL schema introduced beyond one additive
   index?** **NO.** Confirmed by `git diff --stat` and direct migration
   inspection.
5. **Was any broker integration, live order placement, or LLM-based
   decision path added?** **NO.** Confirmed by grep, twice,
   independently.
6. **Is any profitability or investment-advice claim made?** **NO.**
   Every comparison payload carries the same fixed 5-statement
   claim-honesty tuple every M070 payload already carries,
   unconditionally.
7. **Does the real installed CLI genuinely work end-to-end against real
   PostgreSQL?** **YES.** Proven twice, on two independent
   environments, via genuine subprocess invocation.
8. **Is offline, deterministic testing still possible without any
   network dependency?** **YES.** All 6 integration tests and all 45
   unit tests run and pass with zero network access; M071 never touches
   market-data acquisition at all.

**No claim of profitability, live-trading readiness, or investment
advice is made anywhere in this milestone.** M071 makes the existing
daily research product usable across multiple days for the first time;
it does not certify any strategy as profitable or ready for real
capital.

## Owner Approval

All phases of the M071 mission specification are complete: a fresh
15-area gap analysis explicitly classifying each area
PRODUCTION_USABLE/PARTIAL/ABSENT; a 5-candidate ranking against all 6
required criteria with the 4 losing candidates each rejected for a
specific, falsifiable reason; the `ResearchSessionSummary`/
`SessionComparisonEntry`/`compare_session_decisions` domain model; two
new, purely additive repository query methods; two real installed CLI
commands; one purely additive PostgreSQL index (zero new tables); 45
pure unit tests plus 6 real PostgreSQL/CLI integration tests, including
a mandatory proof of genuine day-over-day state transition; a 63-case
hostile review with five genuine findings fixed inline; full canonical
validation with coverage met on the first attempt; a logically
independent second pass on a genuinely fresh container with a
deliberately different universe that directly attempted and failed to
disprove the central claim; and the 8-question reality gate above. Zero
blockers remain.

**Freeze declaration:** `M071 MACRO MILESTONE APPROVED_AND_FROZEN`.
`M071 APPROVED_AND_FROZEN`.

## Deferred / M071 Boundary

Explicitly out of scope and not built: any human-readable/Markdown
report renderer, any M067/M068 portfolio/dependence wiring into the
daily session, any second real-vendor adapter or data-source
fallback/retry logic, any persisted watchlist entity, any broker/
execution code, any LLM-based decision path. **MILESTONE-072 was
explicitly NOT built, per the mission's own instruction.**

## Next Permitted Action

MILESTONE-072 -- recommendation only; not started as part of M071.
