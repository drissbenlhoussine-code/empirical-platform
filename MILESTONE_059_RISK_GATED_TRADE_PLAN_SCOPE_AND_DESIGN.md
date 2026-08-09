# MILESTONE-059 - Risk-Gated Trade Plan - Scope and Design

**Status: CANDIDATE_INTERNAL_MACRO_SCOPE_AND_DESIGN**

Combined scope+design, continuing the reduced-ceremony process established in M053-M058. This milestone answers the question M058 deliberately left open: given a ranked LONG_CANDIDATE opportunity, is there a valid, explicit, risk-constrained trade plan worth acting on? The platform must stop treating "good candidate" as equivalent to "take the trade."

## 1. Repository Authority

Repository `C:\Users\LuxSy\Documents\trading`, branch `master`. M059 baseline: `05e0480595ded146d388cc794c2592e5e242be04` (the final M058 Owner Freeze hash-recording HEAD; M058 fully `APPROVED_AND_FROZEN`), independently re-verified via `git fetch` immediately before implementation began and again at the start of the independent second pass.

## 2. Risk-Domain Inventory and Policy Authority (Phases 1-2)

An exhaustive fresh search (`risk`, `trade_plan`, `position`, `entry`, `stop`, `invalidation`, `target`, `reward`, `position_size`, `account`, `capital`, `equity`, `exposure`, `order`, `execution`, `fill`, `slippage`, `commission`, `spread`) found zero pre-existing risk or trade-plan domain code -- only unrelated false-positive matches (e.g. `EvaluationReasonCode`, `RISK` never appearing as a real term). M057's own scope document explicitly classified stop/target/risk modeling as "useful later, deliberately deferred." **No prior frozen risk-policy authority exists.** M059 therefore originates a minimal, explicit, versioned policy (Section 8) -- stated here plainly as a first product contract, not as historical or objectively-correct authority.

## 3. Fresh M057/M058 Implementation Inventory (Phase 1)

Re-read directly from source, not governance prose: `DecisionCandidate`/`EvaluationOutcome`/`EvaluationMeasurements`/`TradingDecision` (`decision_candidate/candidate.py`, `strategy.py`) -- reused unchanged; `build_trade_plan()` reads only `outcome.decision` and `outcome.measurements` from an already-persisted candidate, never raw bars. `TradingOpportunityScan`/`ScanEvaluationEntry`/`build_scan()` (`decision_candidate/scan.py`) -- reused unchanged; `build_trade_plan()` accepts the full `scan` object so its own provenance check (Section 11) can inspect `scan.evaluations` directly. Neither M057's `evaluate()` nor M058's `build_scan()`/ranking logic is reimplemented anywhere in M059.

## 4. TradePlan Domain Model (Phase 3)

`TradePlan` (`decision_candidate/trade_plan.py`): identity, `source_scan_id`, `source_decision_candidate_id`, `target_evidence_package_id`, `instrument`, `evaluation_cutoff`, `strategy_id`/`strategy_version`/`ranking_model_id`/`ranking_model_version` (always read from the authoritative scan/candidate, never caller-supplied), `policy_id`/`policy_version`, `status` (`APPROVED_PLAN`/`REJECTED_PLAN`), `geometry: TradePlanGeometry | None`, and `reasons: tuple[TradePlanRejectionReason, ...]`. A structured result, not a naked boolean: an `APPROVED_PLAN` must carry geometry and zero reasons; a `REJECTED_PLAN` must carry exactly one reason and may or may not carry geometry (geometry is preserved for audit when the rejection is purely a policy-threshold failure, `REWARD_RISK_BELOW_MINIMUM`; it is `None` when no valid geometry could be computed at all).

## 5. Stop / Invalidation Model (Phase 6)

Five candidate models were considered: (a) a strategy-defined invalidation level -- rejected, since M057's `evaluate()` does not currently emit one and inventing one would silently expand M057's own frozen contract; (b) a fixed percentage below entry -- rejected as arbitrary and disconnected from the actual breakout structure that produced the candidate; (c) an ATR-like volatility rule -- rejected as requiring additional historical bars beyond the reference window M057 already computes, and as carrying an implicit, unstated claim of statistical validity this milestone is not prepared to defend; (d) the most recent swing low -- rejected as under-specified without a swing-detection algorithm that would itself need independent design and verification; (e) **selected: the breakout reference level itself** (`reference_high`, the same value M057's own strategy already computed and used to decide `LONG_CANDIDATE`). This is deterministic, reproducible from data already available at the evaluation cutoff, financially coherent (a breakout that falls back below the level it broke out from has invalidated the setup that justified the trade), and requires no new data, no new parameters, and no new claim of technical validity beyond what M057 already asserts.

## 6. Target Model (Phase 7)

Two models were considered: (a) a fixed multiple of `risk_per_unit` (e.g. target = entry + 2 x risk) -- rejected **deliberately and specifically**, because this would make `reward_risk_ratio` a tautological constant (always exactly the configured multiple), turning the risk gate into a vacuous check that could never actually reject a candidate on ratio grounds; (b) **selected: a fixed percentage projection above `reference_high`** (`target = reference_high * (1 + target_projection_percent)`, `target_projection_percent = 0.02`). This makes the reward/risk ratio a genuine function of *where the candidate's own entry price already sits relative to the breakout level* -- data-dependent, not a constant -- which is what makes the risk gate meaningful rather than decorative. No claim is made that this target is profitable or that price will reach it; its sole purpose is to give the risk/reward contract a well-defined, non-tautological reward side.

## 7. Numeric Semantics (Phase 9)

`risk_per_unit = entry_price - stop_price`, `reward_per_unit = target_price - entry_price`, `reward_risk_ratio = reward_per_unit / risk_per_unit` (long-only; `build_geometry()` rejects `stop_price >= entry_price` as `INVALID_STOP_GEOMETRY` and `target_price <= entry_price` as `INVALID_TARGET_GEOMETRY` before any division is attempted, so division-by-zero is structurally unreachable). All values are `Decimal`. Storage precision: `NUMERIC(18,6)` for price/risk/reward columns, `NUMERIC(30,15)` for the ratio (mirroring M058's own ranking-score precision choice) -- in-memory `Decimal` division can carry more significant digits than the column supports, so retrieved-vs-in-memory ratio comparisons must `.quantize()` to the column's own precision rather than compare with raw `==`.

## 8. Risk Policy (Phase 8)

`RiskPolicy` (`decision_candidate/trade_plan.py`): `policy_id = "REFERENCE_HIGH_BREAKOUT_RISK_GATE"`, `policy_version = "1"`, `target_projection_percent = Decimal("0.02")`, `minimum_reward_risk_ratio = Decimal("2.0")`. No hidden mutable constants -- every parameter lives on the frozen `RiskPolicy` dataclass, and every persisted `TradePlan` carries its own `policy_id`/`policy_version`, so historical plan decisions remain reproducible even if a future milestone introduces `RISK_POLICY_VERSION = "2"` with different parameters. The 2.0 minimum reward/risk ratio is stated plainly as this policy's own first choice, not as an externally-validated or historically-derived threshold.

## 9. Approval / Rejection Vocabulary (Phase 10)

`TradePlanStatus`: `APPROVED_PLAN`, `REJECTED_PLAN`. `TradePlanRejectionReason`: `SOURCE_NOT_LONG_CANDIDATE` (the source `DecisionCandidate` was `NO_TRADE`), `PROVENANCE_MISMATCH` (the candidate does not belong to the claimed scan), `INVALID_STOP_GEOMETRY`, `INVALID_TARGET_GEOMETRY`, `REWARD_RISK_BELOW_MINIMUM`. Every reason is actually reachable and tested; none is aspirational.

## 10. Position-Sizing Decision (Phase 11)

**Option A selected: trade geometry only.** M059 proves entry/stop/target/risk/reward/ratio and the resulting APPROVED/REJECTED decision; it does not introduce account balance, portfolio state, or a caller-supplied risk budget to compute a position size. This is a deliberate, narrow boundary, not an oversight: introducing account/portfolio abstractions before any capability consumes them would be speculative scope, and M059 can prove the full risk/reward contract without them. Position sizing is explicitly deferred to a future milestone, to be built only once a genuine consuming capability exists.

## 11. Provenance and Source-Integrity Model (Phase 12/20)

`build_trade_plan()` accepts the full, already-persisted `scan: TradingOpportunityScan` and `candidate: DecisionCandidate` objects (loaded by the usecase handler from their respective repositories by identity, never accepted as loose caller-supplied fields). `strategy_id`/`strategy_version`/`ranking_model_id`/`ranking_model_version` are always read from these authoritative objects, making a strategy-version or ranking-version mismatch structurally impossible by construction -- there is no caller-supplied field for either to diverge from. The one remaining, genuinely adversarially-possible mismatch -- a candidate that exists but was never actually evaluated as part of the claimed scan -- is caught by `_candidate_belongs_to_scan()`, which checks the candidate's governance_id against the scan's own `evaluations` tuple; a mismatch produces `PROVENANCE_MISMATCH`, never a silent approval. Full chain: `TradingOpportunityScan` -> `ScanEvaluationEntry.decision_candidate_id` -> `DecisionCandidate` -> `TradePlan`, answering "why did this TradePlan exist" by construction.

## 12. Evidence Integration (Phase 13)

**One `ArtifactReference` per `TradePlan`** (`value = f"trade-plan:{plan.identity.governance_id}"`), in deliberate contrast to M058's own "one per scan" choice: each `BuildTradePlanCommand` invocation is its own independent business/audit event (a distinct risk-gate decision, approved or rejected), unlike a scan's per-instrument detail, which is already fully encoded relationally within the scan's own child rows. A rejected plan is exactly as auditable as an approved one -- both receive their own `ArtifactReference`. Full audit chain: `EvidencePackage` -> `ArtifactReference` -> `TradePlan` -> `source_scan_id`/`source_decision_candidate_id` -> `TradingOpportunityScan`/`DecisionCandidate`.

## 13. Persistence Model (Phase 14)

New migration `256558a33013` (`down_revision = "8e6693903b41"`): single `trade_plan` table, immutable/single-insert (no `*_transition` child table, mirroring `DecisionCandidate`/`TradingOpportunityScan`'s own non-lifecycle shape). Geometry columns are nullable: `NULL` for `SOURCE_NOT_LONG_CANDIDATE`/`PROVENANCE_MISMATCH`/`INVALID_STOP_GEOMETRY`/`INVALID_TARGET_GEOMETRY` (no valid geometry existed), populated for `REWARD_RISK_BELOW_MINIMUM` (valid geometry, preserved for audit) and every `APPROVED_PLAN`. `reasons` is a `TEXT[]` column. A database-level `CHECK` constraint ties `status` to reasons-count and geometry-nullability, so the invariant enforced in Python (`TradePlan.__post_init__`) is also enforced at the storage layer. Foreign keys to `trading_opportunity_scan`, `decision_candidate`, and `evidence_package` by governance_id, mirroring the M057/M058 convention exactly.

## 14. Application Layer and Production Boundary (Phase 15/16)

`BuildTradePlanCommand`/`Handler` (`usecases/build_trade_plan.py`): loads the authoritative scan and candidate via their repositories (never trusting caller-supplied duplicated measurements), calls the pure `build_trade_plan()` function, persists the result. `GetTradePlanQuery`/`Handler` mirrors the established Query pattern. Exposed via two new CLI entrypoints (`build_trade_plan`, `get_trade_plan`), reusing the unmodified M053 `_composition.py` helper, registered in `pyproject.toml`. No HTTP/UI layer was built. Zero `tools/check_architecture.py` change was required -- every new module lives inside already-wired `decision_candidate`/`usecases`/`shared`/`entrypoints` packages.

## 15. Look-Ahead / Data-Time Protection (Phase 19)

`build_trade_plan()`'s own signature (`identity`, `scan`, `candidate`, `target_evidence_package_id`, `policy`) contains no `Bar`, `ObservationWindow`, or wall-clock parameter -- there is no surface for future data to enter through. Both stop and target are derived solely from `candidate.outcome.measurements.reference_high`, a value M057's own `evaluate()` already computed, at candidate-build time, using only data available at or before the evaluation cutoff. M059 introduces no new market-data access. Proven both structurally (signature inspection) and empirically, by reusing M057's own look-ahead regression-trap fixture as a cross-milestone test: if M057's protection were ever broken, the resulting plan would flip from `INVALID_TARGET_GEOMETRY` to the different, diagnostically distinguishable `INVALID_STOP_GEOMETRY`.

## 16. Fixtures (Phase 17)

`tests/fixtures/m059_trade_plan/synthetic_boundary_ratio_universe.json`: a purpose-built two-instrument universe (BNDA/BNDB) landing exactly at and just below the policy's minimum reward/risk ratio (2.0), sharing the M058 fixture's own five-bar reference set. `synthetic_6instrument_scan_universe_second_scan.json`: bars byte-for-byte identical to the M058 six-instrument fixture, under a distinct `DCAND-8201`..`8206` governance-id namespace, used only to produce a second, genuinely independent scan for the hostile provenance test. Expected results for both were hand-computed and recorded in the fixtures' own `README.md` before any code was run against them, then confirmed to match the real `evaluate()`/`build_scan()`/`build_trade_plan()` output exactly.

## 17. Acceptance, Independent Verification, and Hostile Review Summary (Phases 17/18/20/23)

PostgreSQL acceptance suite (`tests/integration/test_m059_trade_plan_lifecycle.py`, 7 tests): full lifecycle proving one real APPROVED_PLAN (AAPL -- the *worst-ranked*, #4, of the four M058 LONG_CANDIDATEs) and three REJECTED_PLANs, including the single clearest proof of the milestone's own thesis -- AMZN, the *highest-ranked* (#1) M058 candidate, rejected for `INVALID_TARGET_GEOMETRY`; a boundary-exact APPROVED_PLAN and a just-below REJECTED_PLAN; hostile mismatched-scan/candidate rejection; duplicate-identity and missing-source `AggregateNotFound`/`AggregateAlreadyExists` propagation; reward/risk-ratio storage-precision round-trip. Independent, non-reused math verification (`tests/unit/test_decision_candidate_trade_plan_independent_verification.py`, 6 tests): a separately-authored, single-expression-chain reimplementation of the entire risk-gate pipeline, never calling `trade_plan.py`'s own functions, matching production exactly on all four M058 instruments plus both boundary cases. Look-ahead audit (`tests/unit/test_decision_candidate_trade_plan_lookahead_audit.py`, 3 tests) as described in Section 15. All 28 hostile-review questions from the mission's own checklist were attacked; findings and dispositions are recorded in the Owner Freeze document.

## 18. No-Broker-Execution Boundary (Phase 24)

Confirmed by direct inspection: zero broker/order/fill/exchange/execution terminology and zero external network-library imports anywhere in the M059 changeset. `build_trade_plan()` produces a structured, persisted decision describing a *hypothetical* trade; nothing in this milestone places, submits, or simulates submission of a live or paper order.

## 19. Product-Value Review (Phase 25)

**Before M059**, the platform could rank opportunities but could not distinguish "worth ranking" from "worth taking." **After M059**, a real caller can present a specific, already-ranked M058 opportunity and receive a deterministic, explainable, versioned, persisted decision on whether its actual trade geometry satisfies an explicit risk policy -- and the milestone's own acceptance evidence demonstrates this is not decorative: the highest-ranked candidate in the M058 six-instrument universe (AMZN) is rejected, while a lower-ranked candidate (AAPL) is approved. This is a genuine, substantive product-capability delta.

## 20. In-Scope

Risk policy + trade-plan domain (`trade_plan.py`), `TradePlanRepository` Protocol, migration `256558a33013`, `PostgresTradePlanRepository`, two usecases, two CLI entrypoints and their `pyproject.toml` registration, two new synthetic fixtures, unit tests (risk-policy/geometry/domain invariants, independent verification, look-ahead audit), one PostgreSQL acceptance suite, and this governance document.

## 21. Out-of-Scope

Any transport/HTTP/UI layer; live market-data ingestion or live brokerage connectivity of any kind; position sizing or account/portfolio state; a second stop or target model; any change to Campaign/Run/EvidencePackage/Review/DecisionCandidate/TradingOpportunityScan or their entrypoints; any claim, backtest, or benchmark asserting an `APPROVED_PLAN` is profitable.

## 22. M060 Boundary

This scope selects exactly one MILESTONE-059 capability. No MILESTONE-060 capability, terminology, or sequencing decision is made anywhere in this document. **M059 does not claim approved plans are profitable** -- it proves only that a specific, explicit, versioned risk policy's geometry conditions are satisfied.

## 23. Status

**CANDIDATE_INTERNAL_MACRO_SCOPE_AND_DESIGN.**
