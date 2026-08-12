# MILESTONE-071 - Daily Research Continuity - Scope and Design

## Repository Truth (Phase 0)

Verified at mission start, not assumed: `git fetch origin`; `HEAD ==
origin/master == 66cd0c945d969a8177e0917fdeda3d557dfbb5fb`; 0 ahead / 0
behind; clean working tree; M070 recorded as `APPROVED_AND_FROZEN`;
`LATEST_FROZEN_MILESTONE = MILESTONE-070`; M071 `NOT_STARTED`.

## Fresh Product-Readiness Gap Analysis

M070 made one command produce one complete, persisted, auditable daily
research session. This analysis asks: what does an operator hit when
they actually try to use it every trading day, starting tomorrow?

| # | Area | Classification | Evidence |
|---|------|----------------|----------|
| 1 | Operator-facing daily report / UX | PARTIAL | `research_session_report_payload()` produces a well-sectioned (FACT/HISTORICAL_EVIDENCE/DIAGNOSTIC/LIMITATION) JSON payload, printed as one line of `json.dumps`. Functional, machine-readable, but requires the operator to already parse JSON by eye every morning -- no rendering, no highlighting of what matters. |
| 2 | Multi-day research continuity | ABSENT | Confirmed by direct code inspection: `ResearchSessionRepository` (`decision_candidate/research_session_repository.py`) has exactly two methods, `get(identity)` and `add(session)`. Nothing links Monday's session to Tuesday's. Each session is a fully isolated island. |
| 3 | Day-over-day change detection | ABSENT | No comparison logic exists anywhere in the codebase (confirmed via `grep -rn "compare\|diff" src/empirical_platform/decision_candidate src/empirical_platform/usecases` -- zero matches for session-level comparison). |
| 4 | Candidate persistence across sessions | PARTIAL | Individual `DecisionCandidate`/`TradePlan`/`PositionPlan` rows ARE durably persisted (frozen M057-M060 schema) and each `research_session_decision` row references them by governance id -- the *data* to support continuity already exists. What is absent is any query that traverses it across sessions. |
| 5 | Research-session comparison | ABSENT | Same as #3 -- no usecase, no CLI, no payload section exists. |
| 6 | Alerting / attention prioritization | ABSENT | No mechanism flags "this session needs a look" vs. "routine, nothing changed." |
| 7 | Session history / navigation | ABSENT | This is the sharpest, most concrete gap found: `get-daily-research` requires the caller to already know BOTH the exact `session_governance_id` AND the exact `session_runtime_id` (a UUID minted by `RunDailyResearchSessionHandler` and never displayed anywhere except the `run` command's own one-time stdout). There is no way to ask "what ran for AAPL/MSFT recently?" or "what is today's session?" without having saved that UUID from the original `run` invocation. Confirmed directly: `entrypoints/get_daily_research_session.py::main()` takes exactly 2 positional args, both required, no lookup-by-criteria path exists. |
| 8 | Report clarity / explainability | PARTIAL | The FACT/HISTORICAL_EVIDENCE/DIAGNOSTIC/LIMITATION sectioning is a genuine, real step toward explainability (confirmed in the M070 hostile review), but nothing in the payload tells an operator *what changed* -- the single most valuable signal for someone using this daily. |
| 9 | Portfolio/risk summary integration | ABSENT (deliberately, per M070's own scope boundary) | M067 (capital accounting) and M068 (cross-instrument dependence) are not wired into the daily session at all -- confirmed unchanged in this inventory. |
| 10 | Correlation/dependence summary integration | ABSENT (same as #9) | Unchanged. |
| 11 | Practical daily workflow friction | Significant, concrete | Directly follows from #7: an operator who runs `run-daily-research` today and comes back tomorrow has no CLI-level way to find yesterday's result. They would have to query PostgreSQL by hand. |
| 12 | Real-data reliability / fallbacks | PARTIAL | M069's own adapter raises `MarketDataAcquisitionError` honestly rather than fabricating data (good), and M070's hostile review already documented a genuine Yahoo settlement-lag edge case being correctly rejected rather than papered over. No retry/secondary-source/degraded-mode logic exists, but this is a deliberate, disclosed limitation (mission Phase 13's own "the data source may have limitations" claim-honesty statement), not a silent gap. |
| 13 | Auditability | PRODUCTION_USABLE | Stage manifest, dataset hash, governance chain, raw-SQL-verifiable -- confirmed extensively in the M070 hostile review (92 cases) and independent second pass. |
| 14 | Reproducibility | PRODUCTION_USABLE | As-of firewall and replay semantics directly attacked and held twice (implementation-time and independent second pass). |
| 15 | Product usability | PARTIAL, bottlenecked by #7 | One command produces one session -- but an operator cannot practically *use* this every day without external record-keeping of UUIDs, and gets no signal about what changed since the last run. |

**The single sharpest, most concrete, most repeatedly-confirmed gap is
#7/#11: an operator cannot find a session without already having saved
its exact runtime UUID, and has no way to see what changed since
yesterday.** Every other PARTIAL/ABSENT area either depends on this
being fixed first (day-over-day comparison needs a way to find "the
prior session" at all) or is a deliberate, already-disclosed M070
boundary (portfolio/dependence integration, data-source fallback).

## Candidate Ranking

Five candidates evaluated against PRODUCT_VALUE, DAILY_OPERATOR_VALUE,
DEPENDENCY_UNLOCK, ARCHITECTURAL_LEVERAGE, IMPLEMENTATION_COST (lower is
better), PREMATURE_COMPLEXITY_RISK (lower is better). Scale: LOW / MED /
HIGH.

| Candidate | PRODUCT_VALUE | DAILY_OPERATOR_VALUE | DEPENDENCY_UNLOCK | ARCHITECTURAL_LEVERAGE | IMPLEMENTATION_COST | PREMATURE_COMPLEXITY_RISK |
|---|---|---|---|---|---|---|
| **A. Session history, retrieval-by-criteria, and day-over-day comparison** | HIGH | HIGH | HIGH -- unlocks #3, #5, #6 as natural follow-ons, and is a prerequisite any future continuity work needs anyway | HIGH -- zero new schema, purely additive read-side query methods on the existing frozen `research_session` tables | MED | LOW |
| B. Human-readable (Markdown/plaintext) report renderer | MED | MED | LOW -- a rendering concern, doesn't unlock anything structural | LOW -- a pure presentation-layer addition with no data-model implications | LOW | LOW |
| C. Portfolio/risk (M067) + dependence (M068) summary integration | MED | LOW-MED -- valuable for larger portfolios, but M070's own canonical runs have used 2-3 instruments; most daily value is currently in candidate/decision visibility, not portfolio aggregation | LOW | MED -- would require synthesizing a portfolio-study "run" from a single day's session, exactly the premature complexity M070's own design doc rejected | HIGH -- both M067/M068 operate on collections of trades/windows across time, not one day's snapshot; wiring them in forces inventing synthetic backtest-run sets | HIGH |
| D. Real-data reliability / fallback (retry, secondary vendor, degraded mode) | LOW-MED | LOW | LOW | LOW | HIGH -- a second real vendor adapter is explicitly out of M070's own boundary and would need its own translation/rate-limit/reliability design | MED -- retry logic without a second source mostly just delays an honest failure |
| E. Candidate watchlist (persistent instrument-level tracking independent of sessions) | MED | MED | MED -- overlaps significantly with A's own decision-level comparison | MED -- would need a new persisted entity/table, unlike A | HIGH -- new schema, new lifecycle semantics for a "watchlist" entity | MED -- risks becoming a second, competing continuity mechanism alongside A |

## Selection

**Selected: Candidate A -- Session history, retrieval-by-criteria, and
day-over-day comparison.**

This is the only candidate that is simultaneously the highest product
value, requires zero new PostgreSQL schema (pure additive read-side
queries against the already-frozen `research_session`/
`research_session_decision` tables), and directly closes the single
gap (#7) every other continuity-oriented improvement depends on. It
also does not touch M067/M068 (still correctly out of scope for a
single day's snapshot) and introduces no new real-vendor integration
risk.

**Rejected, explicitly:**

- **B (human-readable renderer):** genuinely useful, but strictly lower
  leverage than A -- prettifying a JSON blob an operator still cannot
  *find* without a saved UUID solves the wrong problem first. The
  mission's own guidance ("if the selected scope is operator-facing
  reporting, make it genuinely usable, not just prettier JSON")
  confirms this instinct: A's list/compare output remains structured
  JSON, honestly, rather than manufacturing a rendering layer whose
  main effect would be cosmetic.
- **C (portfolio/dependence integration):** HIGH implementation cost,
  HIGH premature-complexity risk, and was already deliberately rejected
  once in M070's own scope-and-design document for the same underlying
  reason (M067/M068 operate on trade/window collections across time,
  not a single day's candidate snapshot). Nothing about this inventory
  changes that reasoning.
- **D (data-source reliability/fallback):** would require a second real
  vendor adapter, explicitly out of M070's boundary; current honest
  -failure behavior (no fabricated data) is itself the correct
  design, not a gap needing a fallback that risks masking real vendor
  issues.
- **E (candidate watchlist):** meaningfully overlaps with A's own
  decision-level day-over-day diff, at higher implementation cost (new
  schema, new entity lifecycle) and a real risk of becoming a second,
  competing continuity mechanism rather than one coherent one.

## Design

**Principle:** extend the read side only. No new PostgreSQL table, no
new domain aggregate, no new business logic beyond structural diffing
of already-computed, already-persisted decisions. Comparisons are
computed on demand from two existing sessions, never persisted as a
new entity -- avoiding both new schema and any question of a
comparison "going stale."

1. **`ResearchSessionSummary`** (new, frozen dataclass in
   `research_session.py`): a lightweight projection -- identity,
   as_of, requested_universe, status, created_at, completed_at,
   candidate_count, failed_stage. Built directly from `research_session`
   table rows, no join to stages/decisions (keeps listing cheap).

2. **`ResearchSessionRepository` Protocol extended** with two new,
   purely additive methods:
   - `list_recent(*, universe: tuple[str, ...] | None, limit: int) -> tuple[ResearchSessionSummary, ...]`
     -- most recent sessions first (`as_of` DESC, `created_at` DESC
     tiebreak), optionally filtered to an exact universe (set-equality,
     order-independent).
   - `find_most_recent_prior(*, universe: tuple[str, ...], before_as_of: datetime, exclude_runtime_id: RuntimeIdentifier) -> ResearchSession | None`
     -- the most recent session (by `as_of`, then `created_at`) with an
     exactly-matching universe and `as_of` strictly before the given
     value, excluding the session itself. Returns the FULL hydrated
     session (including decisions) since the comparison usecase needs
     them. Returns `None` honestly when no prior session exists --
     day-1 usage must not error.

3. **Universe set-equality** is computed in SQL via
   `(SELECT array_agg(x ORDER BY x) FROM unnest(requested_universe) x)`
   compared against the same expression over the query parameter --
   order-independent, duplicate-safe (the domain model already forbids
   duplicate instruments in `requested_universe`).

4. **`ListDailyResearchSessionsQuery`/`Handler`** (new usecase,
   `usecases/list_daily_research_sessions.py`): thin wrapper over
   `list_recent`.

5. **`CompareDailyResearchSessionsQuery`/`Handler`** (new usecase,
   `usecases/compare_daily_research_sessions.py`): loads the target
   session via `get()`, loads the baseline via `find_most_recent_prior`
   using the target's own universe and as_of, then computes a pure,
   deterministic diff over `(instrument_symbol, scan_decision,
   trade_plan_decision)` triples:
   - **NEW**: instrument has a decision in the target but not the
     baseline (or there is no baseline at all).
   - **DROPPED**: instrument has a decision in the baseline but not the
     target.
   - **CHANGED**: instrument present in both, `scan_decision` and/or
     `trade_plan_decision` differs.
   - **UNCHANGED**: present in both, identical on both fields.
   Comparing against a FAILED baseline is deliberately allowed and
   surfaced honestly (baseline status is always reported) rather than
   silently skipped -- a failed prior run is itself valuable diagnostic
   continuity, consistent with M070's own auditability ethos.

6. **Payload sections**: `list` returns `{"FACT": {"sessions": [...]}}`
   (list of summary dicts). `compare` returns FACT (target session
   identity/status), a new **CONTINUITY** section (baseline session
   identity/status/as_of, or `null` with an explicit "no prior session"
   note; the NEW/DROPPED/CHANGED/UNCHANGED lists), and the same
   LIMITATION tuple every M070 payload already carries -- comparison
   output is still research evidence, not a trading instruction.

7. **CLI**: `empirical-platform-list-daily-research <symbol>
   [symbol ...] [--limit N]` and `empirical-platform-compare-daily
   -research <session_governance_id> <session_runtime_id>`. Both
   product-level, no milestone numbers, no new concept an operator must
   learn beyond "list" and "compare."

8. **No new PostgreSQL schema.** Confirmed by design: both new
   repository methods are pure `SELECT` statements against the
   already-frozen `research_session`/`research_session_decision`
   tables. One narrow, justified addition: an index on
   `research_session (as_of DESC)` to support the new query pattern's
   `ORDER BY as_of DESC` efficiently -- the only DDL change in this
   milestone.

## Deferred / M071 Boundary

Explicitly out of scope and not built: any human-readable/Markdown
report renderer (Candidate B), any M067/M068 wiring (Candidate C), any
second real-vendor adapter or retry/fallback logic (Candidate D), any
persisted watchlist entity (Candidate E), any broker/execution code, any
LLM-based decision path. **MILESTONE-072 was explicitly NOT built, per
the mission's own instruction.**
