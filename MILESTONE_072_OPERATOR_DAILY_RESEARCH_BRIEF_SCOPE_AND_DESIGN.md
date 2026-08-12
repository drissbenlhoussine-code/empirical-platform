# MILESTONE-072 - Operator Daily Research Brief - Scope and Design

## Phase 0: Repository Truth

Repository `C:\Users\LuxSy\Documents\trading`, branch `master`. Verified
independently at mission start via `git fetch origin`, `git rev-parse
HEAD`, `git rev-parse origin/master`, `git rev-list --left-right --count
HEAD...origin/master`, `git status --short`: `HEAD ==
origin/master == 7abf090f512a8399f68ac99d712782a222ab35c9`, 0 ahead / 0
behind, working tree clean. `PROJECT_CHECKPOINT.md` confirms
`LATEST_FROZEN_MILESTONE=MILESTONE-071`, `M071_STATUS=APPROVED_AND_FROZEN`,
`M072_STATUS=NOT_STARTED`. Matches the mission's expected lineage exactly.

## Phase 1: Fresh Product-Readiness Inventory (20 Areas)

Every row below was checked directly against the live repository this
session (grep, direct file reads), not recalled from a prior milestone's
own design intent.

| # | Area | State | Evidence |
|---|---|---|---|
| 1 | Operator-facing daily report/UX | PARTIAL | `research_session_report_payload` (M070) is a single-line, unsectioned-visually JSON blob; sectioned internally (FACT/HISTORICAL_EVIDENCE/DIAGNOSTIC/LIMITATION) but never rendered for a human to scan in under a minute |
| 2 | Multi-day research continuity | PRODUCTION_USABLE | M071 `list_recent`/`compare` -- solved |
| 3 | Day-over-day change detection | PARTIAL | M071 `compare_session_decisions` computes NEW/CHANGED/DROPPED/UNCHANGED correctly but only exposed as raw JSON, no narrative, no prioritization |
| 4 | Candidate persistence across sessions | PRODUCTION_USABLE | M070 persists every session; M071 makes it findable |
| 5 | Research-session comparison | PRODUCTION_USABLE | M071 -- solved |
| 6 | Alerting/attention prioritization | ABSENT | No ordering, ranking, or attention concept exists anywhere in M070/M071 output; every instrument is presented in scan-rank order only |
| 7 | Session history/navigation | PRODUCTION_USABLE | M071 `list_recent` -- solved |
| 8 | Report clarity/explainability | ABSENT | `ResearchDecisionEntry` (`research_session.py:139-151`) carries only bare `scan_decision`/`trade_plan_decision` strings -- no reason codes, despite genuine structured reason data already existing one layer down |
| 9 | Portfolio/risk summary integration (M067) | ABSENT, gate fails | Confirmed via grep: zero references to `portfolio`/M067 anywhere in `run_daily_research_session.py`, `research_session.py`, `research_session_io.py`; no governance-id lineage from a `ResearchSession`/`ResearchDecisionEntry` to any M067 `PortfolioStudy` exists to reference honestly |
| 10 | Correlation/dependence summary integration (M068) | ABSENT, gate fails | Same grep, same result -- no M068 lineage exists |
| 11 | Practical daily workflow friction | HIGH | Operator must currently run `get-daily-research`, manually parse nested JSON, cross-reference `compare-daily-research`'s separate JSON output by hand, and has no rejection-reason text at all |
| 12 | Real-data reliability/fallbacks | PRODUCTION_USABLE (M069) | Out of this milestone's scope; already frozen |
| 13 | Auditability | PRODUCTION_USABLE | Every session already carries `stage_manifest`, governance ids, `dataset_sha256` -- fully auditable, just not legible |
| 14 | Reproducibility | PRODUCTION_USABLE | M070's replay guarantees already frozen; unaffected by this milestone |
| 15 | Product usability | ABSENT | Direct consequence of #1 -- the honest answer to the Phase-1 gate question below is NO |
| 16 | Rejection-reason data availability | EXISTS BUT UNSURFACED | `EvaluationReasonCode` (`strategy.py`, always both a price- and volume-condition code, even for `NO_TRADE`), `TradePlanRejectionReason` (`trade_plan.py`, exactly one reason on a `REJECTED_PLAN`), `PositionPlanRejectionReason` (`position_plan.py`) all persisted today, reachable only via `DecisionCandidate.outcome.reasons` / `TradePlan.reasons` / `PositionPlan.reasons`, which requires a full `DomainIdentity` (governance_id **and** runtime_id) to fetch -- `ResearchDecisionEntry` stores only the governance-id string, not the runtime_id, of each referenced record |
| 17 | Position sizing/risk evidence availability | EXISTS BUT UNSURFACED | `TradePlanGeometry` (entry/stop/target/risk-per-unit/reward-per-unit/RR ratio) and `PositionSizing` (quantity, position_notional, actual_risk) both fully computed and persisted per M059/M060, never threaded into the M070 session payload |
| 18 | Data-quality/freshness visibility | PARTIAL | `dataset_sha256`/`data_source`/`as_of` are present in FACT but not framed as a data-quality signal; no explicit "as-of vs today" staleness framing |
| 19 | Machine-readable output for tooling | PRODUCTION_USABLE (raw only) | Already valid JSON via every M070/M071 CLI; not yet paired with a genuinely human-readable counterpart from the same model |
| 20 | Report export/artifact usability | ABSENT | No rendering exists yet to export |

**Phase-1 gate question:** *Can an operator currently open one output
after the daily session and understand within roughly one minute what
deserves attention today, what changed since the previous session, why
it matters, and what the major limitations are?*

**Answer: NO.** The operator has two separate raw, unsectioned-for-humans
JSON payloads (`get-daily-research`, `compare-daily-research`), no
attention ordering, and no narrative rejection reasons, despite the
underlying evidence for most of this already existing in already-frozen,
already-persisted records. This is a genuine, evidence-backed product
gap, not an assumed one.

## Phase 2-3: Candidate Ranking and Selection

Criteria (unchanged from the M071 framework, reused for consistency):
PRODUCT_VALUE, DAILY_OPERATOR_VALUE, DEPENDENCY_UNLOCK,
ARCHITECTURAL_LEVERAGE, IMPLEMENTATION_COST, PREMATURE_COMPLEXITY_RISK.

| Candidate | PRODUCT_VALUE | DAILY_OPERATOR_VALUE | DEPENDENCY_UNLOCK | ARCHITECTURAL_LEVERAGE | IMPLEMENTATION_COST | PREMATURE_COMPLEXITY_RISK | Verdict |
|---|---|---|---|---|---|---|---|
| **Operator Daily Research Brief** (composed, deterministic, human+JSON) | HIGH | HIGH | HIGH -- subsumes #2/#3/#6 below as facets | HIGH -- pure aggregation over already-frozen M057/M059/M060/M070/M071 evidence, zero new business logic | MEDIUM | LOW | **SELECTED** |
| Attention prioritization (standalone) | MEDIUM | HIGH | LOW alone | MEDIUM | LOW | MEDIUM -- an attention flag with nowhere to be displayed is dead weight | Folded into the Brief as one section, not built standalone |
| Richer day-over-day explanation (standalone) | MEDIUM | MEDIUM | LOW alone | MEDIUM | LOW | MEDIUM -- same reasoning | Folded into the Brief |
| Data-quality/freshness visibility (standalone) | LOW-MEDIUM | MEDIUM | LOW alone | LOW | LOW | LOW | Folded into the Brief as one section |
| M067 portfolio summary integration | MEDIUM | MEDIUM | LOW | LOW -- **no genuine lineage exists**; would require fabricating a session-to-portfolio-study association | HIGH (would need real linkage design) | **HIGH -- fabrication risk** | **REJECTED**: gate fails per Phase 1 area #9; no honest evidence path exists yet |
| M068 dependence summary integration | MEDIUM | MEDIUM | LOW | LOW -- same fabrication risk | HIGH | **HIGH** | **REJECTED**: gate fails per Phase 1 area #10, same reason |
| Session navigation/history UX | LOW (already done) | LOW (already done) | NONE | NONE | N/A | N/A | **REJECTED**: already `PRODUCTION_USABLE` via M071; rebuilding it would be pure ceremony |
| Report export/artifact usability | LOW | LOW | NONE | NONE | MEDIUM | **HIGH -- nothing exists yet to export** | **REJECTED**: premature; there is no rendered report to export until the Brief itself exists |

**Selection: Operator Daily Research Brief.** It is the only candidate
that coherently subsumes attention prioritization, richer day-over-day
explanation, and data-quality visibility as facets of one deterministic,
composed view -- exactly the same "one coherent capability, multiple
facets" pattern already used successfully in M070 and M071's own
selections. It wins honestly: the Phase-1 inventory independently
establishes the gap (`ABSENT`/`PARTIAL` across areas #1, #3, #6, #8,
#11, #15, #18, #20) rather than assuming it. M067/M068 integration and
export/artifact usability are explicitly rejected as premature or
fabrication-risk; session navigation is explicitly rejected as
already-solved.

## Phase 4: Design -- No New Business Logic

The Brief performs **zero** new strategy, ranking, risk, sizing,
backtest, statistical, portfolio, or dependence computation. Every
number and decision it displays is read, verbatim, from an
already-persisted M057/M059/M060/M070/M071 record:

- Scan/trade-plan/position-plan decisions and rejection reasons: read
  from `DecisionCandidate.outcome.reasons`, `TradePlan.reasons`,
  `PositionPlan.reasons` (frozen M057/M059/M060 fields, never
  recomputed).
- Trade geometry / position sizing values: read from
  `TradePlan.geometry`, `PositionPlan.sizing` (frozen fields).
- Day-over-day classification: delegated entirely to M071's own
  `compare_session_decisions()` -- called, never reimplemented.
- Historical/backtest evidence: read from the session's own
  `backtest_run_governance_id`/`backtest_evaluated_opportunity_count`/
  `backtest_executed_trade_count` fields (frozen M070 fields).

## Phase 5: The Governance-ID-Only Lookup Gap (and its fix)

`ResearchDecisionEntry` stores only `decision_candidate_governance_id:
str`, `trade_plan_governance_id: str | None`,
`position_plan_governance_id: str | None` -- it does **not** store the
`runtime_id` of any referenced record. But
`DecisionCandidateRepository.get()` / `TradePlanRepository.get()` /
`PositionPlanRepository.get()` all require a full `DomainIdentity`
(governance_id **and** runtime_id). Every one of these three tables
already carries a `governance_id` `UNIQUE` constraint
(`uq_decision_candidate_governance_id`,
`uq_trade_plan_governance_id`, `uq_position_plan_governance_id`), so a
governance-id-only lookup is unambiguous and requires **no schema
change** -- the existing unique constraint already provides an index.

**Decision:** add one new, purely additive read method to each of the
three Protocols and their concrete PostgreSQL implementations:

```python
def get_by_governance_id(self, governance_id: DecisionCandidateId) -> DecisionCandidate: ...
def get_by_governance_id(self, governance_id: TradePlanId) -> TradePlan: ...
def get_by_governance_id(self, governance_id: PositionPlanId) -> PositionPlan: ...
```

Each implemented as `SELECT * FROM <table> WHERE governance_id =
:governance_id`, reusing the existing `_row_to_*` reconstruction helper
unchanged. `get()`/`add()` are untouched. No migration is required. This
mirrors the established M071 precedent (Protocol extended with new
read-only methods, existing methods untouched, zero schema disruption)
at an even smaller footprint than M071's one additive index -- M072
introduces **zero** new PostgreSQL DDL.

## Phase 6: Information Hierarchy

The mission's own proposed hierarchy is adopted as-is (no better
justified alternative was found):

1. **SESSION** -- identity, as_of, universe, completion status; the one
   place an unmistakable session-level `WARNING` banner is raised
   (`FAILED` status, or any diagnostic condition below).
2. **ATTENTION** -- the deterministic attention-priority ordering
   (Phase 7), the only "ranking" this milestone introduces, over
   already-computed decisions.
3. **NEW / CHANGED / DROPPED / UNCHANGED** -- one subsection per M071
   comparison outcome, each entry annotated with its attention level.
4. **REJECTIONS** -- for every `NO_TRADE` scan decision, `REJECTED_PLAN`
   trade decision, or `REJECTED_POSITION_PLAN` sizing decision, the
   genuine reason code(s), read via the new `get_by_governance_id()`
   lookups, in plain text (e.g. `PRICE_NOT_ABOVE_REFERENCE_HIGH` ->
   "price did not close above the reference high").
5. **RISK & EVIDENCE** -- for `LONG_CANDIDATE` + `APPROVED_PLAN` +
   `APPROVED_POSITION_PLAN` entries only: entry/stop/target,
   reward:risk ratio, quantity, position notional, actual risk -- all
   read verbatim from `TradePlanGeometry`/`PositionSizing`, plus the
   session's own historical/backtest evidence with its existing
   "retrospective, not a live claim" note carried forward unchanged.
6. **DATA QUALITY** -- `data_source`, `dataset_sha256`, `as_of`, and an
   explicit framing of any `FAILED`/incomplete stage as a data-quality
   concern, not merely a diagnostic footnote.
7. **LIMITATIONS** -- the existing, unmodified
   `RESEARCH_SESSION_CLAIM_HONESTY_LIMITATIONS` 5-statement tuple,
   reused verbatim, never reworded or supplemented with new claims.
8. **AUDIT** -- governance ids (campaign/run/evidence-package/scan/
   session), full stage manifest -- the existing DIAGNOSTIC content,
   relabeled for operator legibility, not recomputed.

## Phase 7: Deterministic Attention-Priority Vocabulary

A small, closed, explicit vocabulary -- no opaque score, no ML, no LLM:

```python
class AttentionLevel(StrEnum):
    ACTION_CANDIDATE = "ACTION_CANDIDATE"  # NEW or CHANGED-into LONG_CANDIDATE with an APPROVED_PLAN and an APPROVED_POSITION_PLAN
    REVIEW = "REVIEW"                       # any other CHANGED entry, or a NEW LONG_CANDIDATE whose plan/sizing was REJECTED
    ROUTINE = "ROUTINE"                     # UNCHANGED, or NEW/steady-state NO_TRADE
    DROPPED = "DROPPED"                     # instrument present in the prior session, absent from this one
```

Ordering for display is a pure, total, deterministic sort:
`ACTION_CANDIDATE > REVIEW > ROUTINE > DROPPED`, with instrument symbol
as the final alphabetical tiebreaker (mirroring M071's own
tie-handling discipline). Session-level `WARNING` (a `FAILED` session,
or a data-quality concern) always renders above the ATTENTION section
entirely, regardless of any individual instrument's level -- a warning
must outrank an attractive-looking candidate, per the mission's explicit
instruction. This classification is a pure function of already-computed
fields (`scan_decision`, `trade_plan_decision`/status, comparison
outcome) -- no new evaluation, ranking, or sizing math.

## Phase 8: M067/M068 Integration Gate -- Freshly Determined

Freshly re-confirmed this session via direct grep of
`run_daily_research_session.py`, `research_session.py`, and
`research_session_io.py` for `portfolio`/`dependence`/`correlation`:
zero genuine references beyond one unrelated docstring line explicitly
disclaiming any such computation. **No lineage exists** from a
`ResearchSession`/`ResearchDecisionEntry` to any M067 `PortfolioStudy`
or M068 `PortfolioDependenceStudy`. Per the mission's own instruction,
this is documented as **explicitly deferred**, not fabricated: the
Brief's LIMITATIONS section will not claim portfolio- or
dependence-level risk context is present, and no synthetic linkage is
invented. This remains a legitimate candidate for a future milestone
once (and only once) a genuine session-to-study lineage is designed.

## Phase 9: Persistence Decision

**No new tables, no new migration.** The Brief is computed on demand
from already-persisted M057/M059/M060/M070/M071 records, exactly
mirroring M071's "compute on demand, never persist comparisons"
precedent. The only storage-adjacent change is the three additive
`get_by_governance_id()` read methods (Phase 5), which touch zero
schema.

## Phase 10: Rendering Design

One pure, composed data structure -- the "brief model" -- is built once
by the usecase layer from the session, its M071 comparison result (if a
prior session exists), and the referenced M057/M059/M060 records. Two
pure, deterministic renderers consume the same model:

- **Human-readable renderer** (default): fixed-order plain-text
  template sections matching the Phase 6 hierarchy, using only the
  model's own already-formatted strings/values -- no current-time
  insertion, no random ordering, no environment-dependent formatting.
  Same model in -> byte-identical text out, always.
- **JSON renderer** (`--json`): a structured dict mirroring the same
  eight sections, for machine consumption -- semantically identical
  content to the text renderer, verified by a dedicated test.

Neither renderer calls an LLM, a network service, or any
non-deterministic function. Both are pure functions:
`render_brief_text(model) -> str`, `render_brief_json(model) -> dict`.

## Phase 11: CLI Design

New entrypoint `entrypoints/build_daily_research_brief.py`, console
script `empirical-platform-daily-brief`:

```
usage: empirical-platform-daily-brief [--json] [<session_governance_id> <session_runtime_id>]
```

- Zero positional args: default to the single most recent session
  across all universes (`list_recent(universe=None, limit=1)`), then
  `get()` its full record. Raises a clear, explicit error if no session
  has ever been run (empty history) -- never a stack trace.
- Two positional args: explicit session selection, matching the exact
  convention already established by `get-daily-research` and
  `compare-daily-research`.
- `--json` (any position): selects the JSON renderer; its absence
  selects the human-readable renderer. Both read from the same brief
  model, built exactly once per invocation.

## Phase 12: Claim-Honesty Boundary

The renderer templates are grep-tested against a fixed forbidden-term
list (`BUY`, `SELL NOW`, `GUARANTEED`, `WILL`, `PROFIT`, and similar) as
part of the hostile review. `RESEARCH_SESSION_CLAIM_HONESTY_LIMITATIONS`
is reused verbatim in the LIMITATIONS section; no new disclaimer wording
is introduced, avoiding the inconsistent-disclaimer risk the mission
explicitly warns against.

## Deferred / M072 Boundary

Explicitly out of scope, not built: M067 portfolio integration, M068
dependence integration (both gated on lineage that does not yet exist),
any report export/artifact format beyond stdout text/JSON, any new
PostgreSQL schema, any broker/execution code, any LLM-based rendering
or decision path. **MILESTONE-073 is explicitly NOT built as part of
this mission.**
