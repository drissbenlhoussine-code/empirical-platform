# MILESTONE-058 - Trading Opportunity Scanner & Ranking - Scope and Design

**Status: CANDIDATE_INTERNAL_MACRO_SCOPE_AND_DESIGN**

Combined scope+design, continuing the reduced-ceremony process established in M053-M057. This milestone extends the M057 trading-evaluation vertical slice from a single instrument to a bounded multi-instrument universe, adding the first deterministic ranking model.

## 1. Repository Authority

Repository `C:\Users\LuxSy\Documents\trading`, branch `master`. M058 frozen baseline: `23712e7dabd76e962960d9d8ab0d6982379c1fde` (the final M057 Owner Freeze hash-recording HEAD; M057 fully `APPROVED_AND_FROZEN`), independently re-verified via `git fetch` immediately before this document was written.

## 2. Fresh M057 Implementation Inventory (Phase 1)

Re-read directly from source, not governance prose: `Bar`/`BarInterval`/`Instrument`/`ObservationWindow` (`decision_candidate/market_data.py`) -- reused entirely unchanged. `STRATEGY_ID`/`STRATEGY_VERSION`/`TradingDecision`/`EvaluationReasonCode`/`StrategyParameters`/`EvaluationMeasurements`/`EvaluationOutcome`/`evaluate()` (`decision_candidate/strategy.py`) -- `evaluate()` is called verbatim, once per instrument, with zero modification. `DecisionCandidate`/`DecisionCandidateRepository`/`PostgresDecisionCandidateRepository` -- reused unchanged; every instrument in a scan still produces its own persisted `DecisionCandidate` exactly as M057 defined it. `EvaluateTradingObservationCommand`/`Handler` (`usecases/evaluate_trading_observation.py`) -- not composed directly (see Section 9); its `DecisionCandidate`-construction field mapping is mirrored, not imported, since this codebase has no precedent for one usecase module importing another. `record_evidence_package_artifact_reference` (M040, frozen) -- reused unchanged for the scan-to-evidence link.

## 3. Scan Domain Model (Phase 2)

`TradingOpportunityScan` (`decision_candidate/scan.py`): identity, target `EvidencePackageId`, `strategy_id`/`strategy_version`, `ranking_model_id`/`ranking_model_version`, `evaluation_cutoff`, and `evaluations: tuple[ScanEvaluationEntry, ...]` in caller-supplied universe order. `total_instruments`/`candidate_count`/`no_trade_count`/`ranked_opportunities` are **derived properties**, not stored fields -- a single source of truth (the `evaluations` tuple) that cannot silently disagree with itself. `ScanEvaluationEntry` carries `instrument`, `decision_candidate_id`, `decision`, `measurements`, `reasons`, and `rank`/`score` (both `None` for `NO_TRADE`, both required for `LONG_CANDIDATE` -- enforced by `__post_init__`). Deliberately minimal: no giant market-scanner framework, no configurable scan-type registry, no plugin system.

## 4. Universe Contract (Phase 3)

`validate_scan_universe()` (`decision_candidate/scan.py`) enforces: at least 1 instrument; every window shares one `BarInterval`; every window shares one evaluation cutoff (the evaluation bar's own timestamp -- see Section 10 for why this single check is also the scan-level look-ahead defense); no duplicate instrument. No live market API; input is a deterministic, caller-supplied set of `ObservationWindow`s (via a JSON universe-fixture file at the CLI boundary, see Section 12).

## 5. Ranking Model (Phase 5)

Three candidate signals were evaluated: breakout magnitude alone (ignores volume confirmation, which the M057 strategy already treats as equally load-bearing to price); volume confirmation ratio alone (same objection, inverted); and the selected **explicit, equal-weighted sum of both**, since the M057 strategy's own two conditions (price above reference high, volume above reference average) are already the two signals that matter for a `LONG_CANDIDATE` -- ranking should measure *how strongly* each was cleared, not introduce a third, unrelated signal.

## 6. Ranking Formula and Version (Phase 5/13)

`RANKING_MODEL_ID = "BREAKOUT_VOLUME_STRENGTH_SUM"`, `RANKING_MODEL_VERSION = "1"` (`decision_candidate/ranking.py`), versioned identically to `STRATEGY_ID`/`STRATEGY_VERSION` for the same reproducibility reason.

```
breakout_strength = (current_close - reference_high) / reference_high
volume_strength    = current_volume / reference_average_volume
ranking_score       = breakout_strength + volume_strength
```

Both terms are dimensionless ratios already implied by the strategy's own two conditions (each is `> 0`/`> 1` respectively for any genuine `LONG_CANDIDATE`, by construction of the M057 decision rule). No historical calibration, no hidden weights, no randomness, no LLM scoring -- `compute_ranking_score()` is a pure function of `EvaluationMeasurements` alone.

## 7. Tie-Breaking (Phase 6)

`rank_sort_key()` (`ranking.py`): score descending, then instrument symbol ascending. Proven with a deliberate, hand-verified tie (NVDA/TSLA, identical measurements, resolved as NVDA before TSLA) in both the acceptance suite and the independent verification suite.

## 8. NO_TRADE Handling (Phase 6/9)

`NO_TRADE` evaluations are persisted as full `DecisionCandidate` rows exactly like `LONG_CANDIDATE` ones (M057 behavior, unchanged), remain present in `scan.evaluations` with `rank=None`/`score=None`, and are excluded from `scan.ranked_opportunities` by construction, not by a runtime filter a future bug could bypass -- `TradingOpportunityScan.__post_init__` additionally verifies ranked entries form a contiguous `1..N` sequence with no gaps, so a `NO_TRADE` entry accidentally carrying a rank would be structurally impossible without also breaking that invariant.

## 9. Core Integration Decision (Phase 9)

Considered two models: (A) each `DecisionCandidate` keeps its own individual `ArtifactReference` on the target `EvidencePackage` (as M057 did for its single-instrument case), or (B) the scan itself becomes the one `ArtifactReference`, with each `DecisionCandidate` reachable through the scan's own `evaluations`. **Selected (B)**: recording N individual `ArtifactReference`s (one per instrument, every scan) would duplicate exactly what `trading_opportunity_scan_evaluation` already encodes relationally, and would not answer "why was X ranked #1 in *this* scan" any better than the scan record itself already does. One `ArtifactReference` per scan (`value = f"trading-opportunity-scan:{scan.identity.governance_id}"`) is the complete, non-duplicated link; the audit chain is: `EvidencePackage` -> `ArtifactReference` -> `TradingOpportunityScan` -> `ScanEvaluationEntry.decision_candidate_id` -> `DecisionCandidate` (real, unmodified `get_decision_candidate` retrieval).

## 10. Persistence Model and Atomicity Boundary (Phase 8)

New migration `8e6693903b41` (`down_revision = "a1c93f7e2b04"`): `trading_opportunity_scan` (scan-level fields) and `trading_opportunity_scan_evaluation` (one child row per instrument, `position`-ordered, foreign-keying to both its own scan and `decision_candidate.governance_id`). The child table deliberately does **not** duplicate `decision_candidate`'s own measurements/reasons columns -- `PostgresTradingOpportunityScanRepository.get()` reconstructs each `ScanEvaluationEntry` by joining back to `decision_candidate` at read time. `add()` persists the scan row and every evaluation row within one `unit_of_work()` -- genuinely atomic for the scan and its full evaluation set.

**Disclosed limitation, not a hidden one**: `RunTradingOpportunityScanHandler.handle()` performs N `DecisionCandidateRepository.add()` calls (one per instrument, each its own transaction) followed by one `TradingOpportunityScanRepository.add()` (its own further transaction) -- this is a deliberate exception to the one-aggregate-mutation-per-command discipline used everywhere else in this project, justified because a scan and its per-instrument evaluations are one atomic *business* fact ("this scan happened, producing exactly these N evaluations"), not N+1 independently meaningful business events with separate actors or timing, unlike Campaign/Run/EvidencePackage/Review. It is **not** wrapped in a single database transaction across all N+1 writes, consistent with how M056's own cross-aggregate chain is not atomic across separate command invocations either: a crash mid-scan leaves any already-persisted `DecisionCandidate`s as individually valid, auditable records, but with no scan yet referencing them.

## 11. Application Layer and Production Boundary (Phase 10/11)

`RunTradingOpportunityScanCommand`/`Handler` (`usecases/run_trading_opportunity_scan.py`): validates the universe, evaluates every instrument through the unmodified M057 `evaluate()`, persists each `DecisionCandidate`, ranks the `LONG_CANDIDATE` subset via `build_scan()`, persists the scan. `GetTradingOpportunityScanQuery`/`Handler` mirrors the established Query pattern. Exposed via two new CLI entrypoints (`run_trading_opportunity_scan`, `get_trading_opportunity_scan`), reusing the unmodified M053 `_composition.py` helper, registered in `pyproject.toml`. No HTTP/UI layer was built.

**Predecessor boundary correction, applied inline** (no correction milestone): `entrypoints` cannot import `decision_candidate` directly (unchanged architecture rule). `usecases/run_trading_opportunity_scan.py` and `usecases/get_trading_opportunity_scan.py` explicitly re-export (`import X as X`) the domain types their entrypoints construct -- the same idiom used in M054/M057. Zero `tools/check_architecture.py` change was required: every new module lives inside `decision_candidate` (already wired to `usecases`/`shared` since M057) or `shared/persistence/postgres_repositories` (already wired).

## 12. Market-Scan Fixture (Phase 12)

`tests/fixtures/m058_market_scan/synthetic_6instrument_scan_universe.json`: six instruments (AAPL, MSFT, GOOG, AMZN, NVDA, TSLA), one JSON object with an `instruments` array, each entry carrying a caller-supplied `decision_candidate_governance_id` and a `bars` array in the M057 per-bar fixture shape. All six share an identical five-bar reference set and evaluation cutoff (`2026-08-10T13:45:00+00:00`). Expected results (4 `LONG_CANDIDATE`, 2 `NO_TRADE`, a non-trivial AMZN-leads comparison, and a deliberate NVDA/TSLA tie) were hand-computed and recorded in the fixture's own `README.md` **before** any code was run against it, then independently confirmed to match the real `evaluate()`/`build_scan()` output exactly.

## 13. Acceptance, Independent Verification, and Look-Ahead Audit (Phases 15/13/14)

PostgreSQL acceptance suite (`tests/integration/test_m058_trading_opportunity_scan_lifecycle.py`, 3 tests): full scan persistence/ranking/evidence-linkage with raw-SQL cross-check; deterministic replay under independent identities; hand-verified score-precision cross-check. Independent, non-reused ranking verification (`tests/unit/test_decision_candidate_scan_independent_ranking_verification.py`, 3 tests): a separately-authored score formula and hand-rolled insertion sort, never calling `ranking.py`/`scan.py`'s own scoring or sorting code, matching production exactly on both score and complete order. Scan-level look-ahead audit (`tests/unit/test_decision_candidate_scan_lookahead_audit.py`, 3 tests): `validate_scan_universe()`'s cutoff-matching check is the complete defense against one instrument "running ahead" of its peers, since a window's evaluation bar is structurally its own last bar -- proven by constructing an instrument with an extra, extreme-valued bar dated after the common cutoff and confirming the whole universe is rejected before any evaluation or ranking occurs, plus a positive control confirming that bar really would have dominated the ranking if it had been allowed through.

## 14. Hostile Review Summary (Phase 16)

All 26 questions from the mission's own checklist were attacked; two genuine gaps were found and closed inline (no correction milestone): ranking-order independence from universe input order (added `test_build_scan_ranking_is_independent_of_universe_input_order`) and explicit ranking-model identity preservation independent of strategy identity (added `test_build_scan_preserves_strategy_and_ranking_model_identity`). Every other question was already covered by existing tests or structural invariants; see the Owner Freeze document for the full per-question disposition.

## 15. Product-Value Review (Phase 19)

**Before M058**, the platform could evaluate exactly one instrument at a time and produce one `LONG_CANDIDATE`/`NO_TRADE` decision. **After M058**, a real caller can submit a bounded universe of multiple instruments observed at the same decision point, have every one of them evaluated through the unchanged M057 strategy, have the illegitimate (`NO_TRADE`) candidates rejected from consideration while remaining fully persisted and auditable, and receive a deterministic, explainable, reproducible ranking of the surviving `LONG_CANDIDATE` opportunities -- answering, for the first time, "which of several observed opportunities deserves attention." This is a genuine, substantive product-capability delta, not a cosmetic wrapper around M057.

## 16. In-Scope

Ranking domain (`ranking.py`), scan domain (`scan.py`, `scan_repository.py`), migration `8e6693903b41`, `PostgresTradingOpportunityScanRepository`, two usecases, two CLI entrypoints and their `pyproject.toml` registration, one multi-instrument synthetic fixture, unit tests (ranking, scan domain, independent verification, look-ahead audit), one PostgreSQL acceptance suite, and this governance document.

## 17. Out-of-Scope

Any transport/HTTP/UI layer; live market-data ingestion; a second ranking model; portfolio construction or order execution; any change to Campaign/Run/EvidencePackage/Review or their entrypoints; any claim, backtest, or benchmark asserting the ranking model identifies profitable opportunities.

## 18. M059 Boundary

This scope selects exactly one MILESTONE-058 capability. No MILESTONE-059 capability, terminology, or sequencing decision is made anywhere in this document. **M058 does not claim the ranking identifies profitable opportunities** -- it orders already-legitimate candidates by the strength of the same two signals the frozen M057 strategy already uses to decide `LONG_CANDIDATE` in the first place.

## 19. Status

**CANDIDATE_INTERNAL_MACRO_SCOPE_AND_DESIGN.**
