# MILESTONE-059 - Risk-Gated Trade Plan - Macro Milestone Freeze

## Status: FINAL — OWNER FROZEN

## Repository Authority

Repository `C:\Users\LuxSy\Documents\trading`, branch `master`. M059 baseline `05e0480595ded146d388cc794c2592e5e242be04` (the M058 Owner Freeze hash-recording HEAD; M058 fully `APPROVED_AND_FROZEN`). Implementation commit `8a18999260c978e30f0dc7fc0c436d2d8fdc9a6e`.

## Delivered Capability

The first deterministic risk-gated trade plan. Before this milestone, the platform could rank opportunities (M058) but could not distinguish a candidate worth ranking from a trade worth taking. After this milestone, a real caller can present an already-persisted, already-ranked M058 opportunity (identified by scan and decision-candidate identity alone) to the `build_trade_plan` CLI entrypoint and receive a structured, persisted, explainable `APPROVED_PLAN` or `REJECTED_PLAN`, gated by one explicit, versioned risk policy (`REFERENCE_HIGH_BREAKOUT_RISK_GATE` v1). See `MILESTONE_059_RISK_GATED_TRADE_PLAN_SCOPE_AND_DESIGN.md` for the full inventory, stop/target-model rationale, and risk-policy authority.

## Implementation Evidence

New risk-policy and trade-plan domain (`trade_plan.py`: `RiskPolicy`, `TradePlanGeometry`, `TradePlanStatus`, `TradePlanRejectionReason`, `TradePlan`, `compute_stop_price()`, `compute_target_price()`, `build_geometry()`, `build_trade_plan()`), `TradePlanRepository` Protocol, migration `256558a33013` (upgrade/downgrade round-trip verified against a real disposable container), `PostgresTradePlanRepository` (nullable geometry columns, a database-level `CHECK` constraint tying `status` to reasons-count and geometry-nullability), two usecases (`BuildTradePlanCommand`/`Handler`, `GetTradePlanQuery`/`Handler`), two production CLI entrypoints (registered in `pyproject.toml`, reusing the unmodified M053 `_composition.py` helper), two new labeled synthetic fixtures (`tests/fixtures/m059_trade_plan/`, expected results hand-computed and recorded before any code ran against them, then confirmed to match exactly), one PostgreSQL acceptance suite (7 tests: full approved/rejected lifecycle with raw-SQL cross-check, boundary-exact and just-below reward/risk cases, hostile mismatched-scan/candidate rejection, duplicate-identity `AggregateAlreadyExists`, missing-source `AggregateNotFound` for both scan and candidate, ratio-precision storage round-trip), one independently-authored math-verification suite (6 tests, a separately-authored single-expression-chain reimplementation, never calling production trade-plan code), and one look-ahead audit suite (3 tests, structural signature inspection plus a cross-milestone regression trap reusing M057's own look-ahead probe fixture).

Full canonical validation: `ruff check`/`ruff format --check` clean (the only flagged files were 8 pre-existing, untouched files with empty `git diff`, the same known `core.autocrlf` cosmetic artifact seen every prior milestone), `mypy` (172 source files) clean, `tools/check_architecture.py` clean (zero changes required -- every new module lives inside already-wired packages), full non-integration regression 1231 passed (up from 1195, exactly the +36 new M059 unit tests), full PostgreSQL integration regression 250 passed / 6 skipped / 0 failed (up from 243 passed, exactly the +7 new M059 acceptance tests), build (wheel, both new console scripts registered and present) clean, `pip-audit` clean, `detect-secrets` scan of every new/modified file (1 expected false positive: the migration's own `revision`/`down_revision` alembic hex identifiers, the same pattern every other migration file in the repository triggers). Zero regressions across every prior milestone's own suite (M020-M058).

## Look-Ahead / Data-Time Audit

`build_trade_plan()`'s own signature (`identity`, `scan`, `candidate`, `target_evidence_package_id`, `policy`) carries no `Bar`, `ObservationWindow`, or wall-clock parameter -- confirmed by direct `inspect.signature()` assertion. Both stop and target derive solely from `candidate.outcome.measurements.reference_high`, a value M057's own `evaluate()` already computed using only data available at or before the evaluation cutoff. Proven empirically by reusing M057's own look-ahead regression-trap fixture (an evaluation bar whose own extreme high/volume would corrupt `reference_high` to 200.00 if M057's defense were ever broken) as a cross-milestone test: with the correct, uncorrupted `reference_high` (100.50), the resulting plan is `REJECTED_PLAN`/`INVALID_TARGET_GEOMETRY` (an already-extended breakout overshooting even a generous target); if `reference_high` were ever corrupted to 200.00, the plan would instead fail with the different, diagnostically distinguishable `INVALID_STOP_GEOMETRY`. A positive control (M057's ordinary long-candidate fixture) confirms a normal `APPROVED_PLAN` with `stop_price == 100.50`, isolating the rejection above to the probe's own extreme geometry rather than a general defect.

## Hostile Risk Review

All 28 questions from this mission's own checklist were attacked against the implementation. Findings, all addressed inline (no correction milestone):

1. **Missing-source-scan / missing-source-candidate propagation** -- no test previously confirmed that a `source_scan_identity` or `source_decision_candidate_identity` referencing a never-persisted governance_id propagates `AggregateNotFound` untouched, rather than being silently swallowed. Closed via `test_missing_source_scan_raises_aggregate_not_found` and `test_missing_source_decision_candidate_raises_aggregate_not_found`.
2. **Reward/risk-ratio storage-precision survival** -- no test previously confirmed a genuinely repeating-decimal ratio (BNDB's 1.9558823529411764...) survives `NUMERIC(30,15)` storage and retrieval without corrupting the REJECTED decision. Closed via `test_reward_risk_ratio_precision_survives_storage_rounding`.

Every other question (stop==entry, stop>entry, target==entry, target<entry, zero/negative risk, huge Decimal values, boundary R:R threshold both exact and just-below, NO_TRADE source, mismatched candidate/scan, duplicate plan identity, strategy-version/ranking-version mismatch -- structurally impossible by construction, future-data leakage, random behavior, input-order dependence, persistence round-trip, approved/rejected semantic equality, hidden mutable constants, LLM dependency, profitability language, scope creep, accidental order execution, accidental account/portfolio abstraction) was already covered by an existing test or a structural invariant, confirmed by direct source inspection. **Findings: two, both closed. Zero remaining.**

## Independent Second Review

A completely fresh, disposable PostgreSQL 16 container was migrated from empty (all four migrations, M022 through M059, applied cleanly), then driven entirely through real subprocess CLI invocations (`python -m empirical_platform.entrypoints.<name>`) -- never direct Python function calls: seeded three separate real Campaign -> Run -> EvidencePackage chains; ran the M058 six-instrument scan and independently confirmed the exact expected ranking (AMZN #1, NVDA #2, TSLA #3, AAPL #4); built four trade plans via the real `build_trade_plan` CLI and confirmed AAPL (rank #4, the worst-ranked LONG_CANDIDATE) was `APPROVED_PLAN` while AMZN (rank #1, the best-ranked) was `REJECTED_PLAN`/`INVALID_TARGET_GEOMETRY`, NVDA `REJECTED_PLAN`/`REWARD_RISK_BELOW_MINIMUM`, and MSFT (a `NO_TRADE` source) `REJECTED_PLAN`/`SOURCE_NOT_LONG_CANDIDATE`; independently retrieved all four plans via the real `get_trade_plan` CLI, confirming an exact match; ran the M059 boundary fixture and confirmed BNDA (ratio exactly 2.00) `APPROVED_PLAN` and BNDB (ratio ~1.9559) `REJECTED_PLAN`; ran a second, independent scan over the second-scan fixture and confirmed a hostile attempt to claim the first scan's identity with the second scan's candidate produced `REJECTED_PLAN`/`PROVENANCE_MISMATCH`; started `EvidencePackage` collection and recorded all four trade plans as four independent `ArtifactReference`s. All results were independently cross-checked via raw SQL, bypassing all repository and application code. A separately-authored, single-expression-chain reimplementation of the entire risk-gate pipeline (re-deriving `reference_high`/`current_close` directly from the raw fixture bars, independently recomputing stop/target/risk/reward/ratio) was run against the same four M058 instruments and matched the production CLI output exactly on approval status, rejection reason, and reward/risk ratio in every case.

**Findings: none. Zero CRITICAL, MAJOR, or MINOR findings. No further correction required.**

**Answer to the mission's own Phase 27 question -- "did the platform genuinely learn to distinguish a good market candidate from a trade plan that passes explicit risk rules?"** Yes, demonstrated concretely: the M058 universe's #1-ranked candidate (AMZN, by momentum) is rejected by the M059 risk gate, while its #4-ranked candidate (AAPL, the most modest) is approved. Rank order and trade-plan approval are provably independent.

## No-Broker-Execution Boundary

Confirmed by direct inspection: zero broker/order/fill/exchange/execution terminology and zero external network-library imports anywhere in the M059 changeset. `build_trade_plan()` produces a structured, persisted decision describing a *hypothetical* trade; nothing in this milestone places, submits, or simulates submission of a live or paper order.

## Owner Approval

**M059 MACRO MILESTONE APPROVED_AND_FROZEN.**

Scope, design, implementation, hostile risk review, independent second review, and look-ahead/data-time audit frozen as one consolidated unit. No architecture broadening beyond the already-justified M053 composition helper's continued reuse; zero `tools/check_architecture.py` change was required. No scope creep, no framework creep, no policy bypass, no position-sizing or account/portfolio abstraction introduced. Predecessor authority (M020-M058) fully preserved; no M020-M058 entrypoint, usecase, aggregate, strategy, or ranking function was modified. **M059 does not claim approved plans are profitable** -- it proves only that a specific, explicit, versioned risk policy's geometry conditions are satisfied.

## Deferred / M060 Boundary

No MILESTONE-060 capability, terminology, or sequencing decision is made in this document.

## Next Permitted Action

MILESTONE-060 — not yet selected or started. See this milestone's own final report for a non-binding recommended direction. **M060 has not been built or started as part of this mission.**
