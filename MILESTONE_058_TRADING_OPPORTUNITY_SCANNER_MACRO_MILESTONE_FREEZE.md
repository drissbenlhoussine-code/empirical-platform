# MILESTONE-058 - Trading Opportunity Scanner & Ranking - Macro Milestone Freeze

## Status: FINAL — OWNER FROZEN

## Repository Authority

Repository `C:\Users\LuxSy\Documents\trading`, branch `master`. M058 baseline `23712e7dabd76e962960d9d8ab0d6982379c1fde` (the M057 Owner Freeze hash-recording HEAD; M057 fully `APPROVED_AND_FROZEN`). Implementation commit `858045c7f027038352f214bf253db48395e01a91`.

## Delivered Capability

The first deterministic trading opportunity scanner and ranker. Before this milestone, the platform could evaluate exactly one instrument at a time. After this milestone, a real caller can submit a bounded, deterministic universe of multiple instruments observed at the same decision cutoff through the `run_trading_opportunity_scan` CLI entrypoint, have every instrument evaluated through the unmodified M057 strategy, have `NO_TRADE` evaluations excluded from ranking while remaining fully persisted and auditable, and receive a persisted, retrievable, deterministically-ranked `TradingOpportunityScan` linked to a target `EvidencePackage` via a single `ArtifactReference`. See `MILESTONE_058_TRADING_OPPORTUNITY_SCANNER_SCOPE_AND_DESIGN.md` for the full inventory, ranking-model rationale, and core-integration decision.

## Implementation Evidence

New ranking domain (`ranking.py`: `compute_ranking_score()`, `rank_sort_key()`, 6 unit tests) and scan domain (`scan.py`: `validate_scan_universe()`, `ScanEvaluationEntry`, `TradingOpportunityScan`, `build_scan()`, 20 unit tests including tie-breaking, all-`NO_TRADE`/all-`LONG_CANDIDATE`/single-instrument universes, input-order independence, and strategy/ranking-model identity preservation), `TradingOpportunityScanRepository` Protocol, migration `8e6693903b41` (upgrade/downgrade round-trip verified against a real disposable container; a genuine naming-collision bug in the two `UniqueConstraint`s -- both defaulting to the same auto-generated name since they shared a first column -- was found and fixed before the round-trip passed), `PostgresTradingOpportunityScanRepository` (atomic scan+evaluations insert within one `unit_of_work()`, smoke-tested end-to-end including duplicate/not-found error paths), two usecases, two production CLI entrypoints (registered in `pyproject.toml`, reusing the unmodified M053 `_composition.py` helper), one labeled synthetic six-instrument fixture (`tests/fixtures/m058_market_scan/`, expected results hand-computed and recorded before any code ran against it, then confirmed to match exactly), one PostgreSQL acceptance suite (3 tests: full scan persistence/ranking/evidence-linkage with raw-SQL cross-check; deterministic replay under independent identities; hand-verified score-precision cross-check), one independently-authored ranking-verification suite (3 tests, a separately-authored formula and hand-rolled sort, never calling production ranking code), and one scan-level look-ahead audit suite (3 tests). Full canonical validation: `ruff check`/`ruff format --check` clean (the only flagged files were 8 pre-existing, untouched files with empty `git diff`, the same known `core.autocrlf` cosmetic artifact seen every prior milestone), `mypy` (165 source files) clean, `tools/check_architecture.py` clean (zero changes required -- every new module lives inside already-wired packages), build (wheel, both new console scripts registered and present) clean, `pip-audit` clean, `detect-secrets` scan of every new/modified file (2 expected false positives: the migration's own `revision`/`down_revision` alembic hex identifiers, the same pattern every other migration file in the repository triggers). Full regression: 1195 non-integration tests passed, 243 PostgreSQL integration tests passed (6 pre-existing, unrelated skips) -- zero regressions across every prior milestone's own suite (M020-M057).

## Scan-Level Look-Ahead Audit

M057's structural look-ahead defense (`ObservationWindow` cannot contain a bar dated after its own evaluation bar) is inherited unchanged. The one new risk a multi-instrument scan introduces -- one instrument's window running "ahead" of its peers, carrying a later evaluation cutoff -- is fully closed by `validate_scan_universe()`'s single cutoff-matching check: since a window's evaluation bar is structurally its own last bar, "one instrument sees data after the common cutoff" and "one instrument's cutoff differs from its peers'" are the same condition. Proven by constructing a universe where one instrument carries an extra bar dated after the common cutoff with an extreme close/volume that would have won the entire ranking outright (confirmed via a positive-control test evaluating that bar in isolation), and confirming the whole universe is rejected with `ValueError` before any evaluation or ranking is attempted.

## Hostile Review

All 26 questions from this mission's own checklist were attacked. Two genuine gaps were found and closed inline (no correction milestone):

1. **Ranking-order input-order dependence** -- no test previously confirmed that `ranked_opportunities` order depends only on scores/symbols, not on the order instruments were supplied in the universe. Closed via `test_build_scan_ranking_is_independent_of_universe_input_order` (forward vs. reversed universe input, identical ranked output).
2. **Ranking-model identity preservation** -- no test previously asserted `ranking_model_id`/`ranking_model_version` explicitly equal their expected constant values (only implicit round-trip equality was checked). Closed via `test_build_scan_preserves_strategy_and_ranking_model_identity`.

Every other question (mixed intervals, mismatched cutoff, duplicate instrument/observation, malformed OHLC, negative volume, unsupported instrument form, all-`NO_TRADE`/all-`LONG_CANDIDATE`/single-candidate universes, deterministic ties, ranking-score precision, strategy-version preservation, `NO_TRADE`-accidentally-ranked, candidate-accidentally-omitted, future-data leakage, persistence-ordering corruption, retrieval round-trip, evidence linkage, exception transparency, no randomness, no LLM dependency, no profitability claims, no scope creep) was already covered by an existing test or a structural invariant, confirmed by direct source inspection. **Findings: two, both closed. Zero remaining.**

## Independent Second Review

A completely fresh, disposable PostgreSQL 16 container was migrated from empty, then driven entirely through real subprocess CLI invocations (`python -m empirical_platform.entrypoints.<name>`) -- never direct Python function calls: seeded a real Campaign -> Run -> EvidencePackage chain; ran the six-instrument scan (matching the hand-verified expected ranking exactly: AMZN/NVDA/TSLA/AAPL with the NVDA=TSLA tie); independently retrieved the persisted scan, confirming an exact match (with the expected `NUMERIC(30,15)` precision rounding); started `EvidencePackage` collection and recorded the scan's governance_id as a single real `ArtifactReference`. Final state was then independently verified via raw `psql`, bypassing all repository and application code -- the scan-level counts, the full per-instrument ranked/`NO_TRADE` rows (including the NVDA/TSLA score tie), all six `decision_candidate` rows, and the one `evidence_package_artifact_reference` row all matched every subprocess-reported result exactly.

**Findings: none. Zero CRITICAL, MAJOR, or MINOR findings. No further correction required.**

## Owner Approval

**M058 MACRO MILESTONE APPROVED_AND_FROZEN.**

Scope, design, implementation, hostile review, independent second review, and scan-level look-ahead audit frozen as one consolidated unit. No architecture broadening beyond the already-justified M053 composition helper's continued reuse; zero `tools/check_architecture.py` change was required. No scope creep, no framework creep, no policy bypass. Predecessor authority (M020-M057) fully preserved; no M050-M057 entrypoint, usecase, aggregate, or strategy function was modified. **M058 does not claim the ranking model identifies profitable opportunities** -- it orders already-legitimate candidates by the strength of the same two signals the frozen M057 strategy already uses to decide `LONG_CANDIDATE`.

## Deferred / M059 Boundary

No MILESTONE-059 capability, terminology, or sequencing decision is made in this document.

## Next Permitted Action

MILESTONE-059 — not yet selected or started. See this milestone's own final report for a non-binding recommended direction.
