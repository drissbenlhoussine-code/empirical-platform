# MILESTONE-060 - Position Sizing + Capital Exposure Gate - Scope and Design

**Status: CANDIDATE_INTERNAL_MACRO_SCOPE_AND_DESIGN**

Combined scope+design, continuing the reduced-ceremony macro-milestone process used by M053-M059. This milestone answers the question M059 deliberately left open: given an already-approved `TradePlan`, how large may the position be without violating explicit risk-budget and capital-exposure rules? The platform must stop treating `APPROVED_PLAN` as equivalent to "size unconstrained."

## 1. Repository Authority

Repository `C:\Users\LuxSy\Documents\trading`, branch `master`. M060 baseline: `5526ee325416d39d3b37dd7d0b51e3f1cd1d05ef` (the final M059 Owner Freeze hash-recording HEAD; M059 fully `APPROVED_AND_FROZEN`), independently re-verified before implementation began.

## 2. Capital / Position Inventory and Prior Authority

An exhaustive fresh search (`position_size`, `quantity`, `shares`, `units`, `risk_budget`, `account_equity`, `capital`, `buying_power`, `exposure`, `notional`, `max_position`, `portfolio`, `cash`, `leverage`, `margin`) found:

- **Implemented**: M059 `TradePlanGeometry` already persists `entry_price`, `stop_price`, `target_price`, and `risk_per_unit`; these are the authoritative sizing inputs M060 must consume.
- **Placeholder / governance-only**: multiple milestone documents mention future position sizing, account state, or capital controls as deferred work, but no frozen runtime contract existed before this milestone.
- **Absent**: no `Account` aggregate, no `Portfolio` aggregate, no mutable cash ledger, no buying-power model, no leverage model, no broker order surface, and no existing persisted position-sizing result.

**No prior frozen sizing-policy authority exists.** M060 therefore originates a minimal, explicit, versioned position-sizing policy as a first product contract, stated plainly as new authority rather than retroactively claimed history.

## 3. Fresh M057-M059 Implementation Inventory

Re-read directly from source, not governance prose:

- M057 `DecisionCandidate` / `EvaluationOutcome` / `EvaluationMeasurements` remain unchanged.
- M058 `TradingOpportunityScan` / ranking remain unchanged.
- M059 `TradePlan` / `TradePlanGeometry` / `TradePlanStatus` / `TradePlanRejectionReason` remain unchanged.
- M060 consumes only the persisted, authoritative `TradePlan` record. It never accepts caller-supplied `entry_price`, `stop_price`, `target_price`, `risk_per_unit`, or `TradePlan` status.

No prior runtime module supplied a position-sizing result or capital gate.

## 4. First Position-Sizing Contract

M060 consumes:

- one authoritative persisted `TradePlan`, loaded by full identity;
- one caller-supplied immutable `PositionSizingContext`;
- one explicit `SizingPolicy`.

The chosen v1 context is deliberately minimal:

- `account_equity: Decimal`
- `risk_percent: Decimal`

No mutable `Account` aggregate is introduced. No portfolio state is loaded. No cash ledger, buying-power ledger, or leverage state exists. The context is a one-shot planning input for a hypothetical position-sizing decision only.

## 5. Versioned Sizing Policy

`SizingPolicy` (`decision_candidate/position_plan.py`) originates M060's first position-sizing authority:

- `policy_id = "EQUITY_PERCENT_RISK_SIZING_GATE"`
- `policy_version = "1"`
- `maximum_risk_percent = Decimal("0.02")`
- `maximum_notional_percent = Decimal("0.25")`
- `allow_fractional_shares = False`

No silent "1% risk per trade" mythology is introduced. The 2% risk cap and 25% notional cap are stated transparently as this milestone's own first explicit policy choices. Every persisted `PositionPlan` stores the policy identity plus the governing parameters so the result remains reproducible even if a future milestone introduces v2.

## 6. Whole vs Fractional Units

**Whole shares only** are selected for v1. Fractional shares were evaluated and rejected because:

- the current domain is US equities / ETFs;
- the platform has no broker integration and therefore no authoritative fractional-capability surface;
- floor-based whole-share sizing is simpler to audit and replay;
- whole shares avoid silently freezing broker-specific fractional behavior before any broker exists.

This decision is explicit and persisted through the policy snapshot (`policy_allow_fractional_shares = False`).

## 7. PositionPlan Domain Model

`PositionPlan` (`decision_candidate/position_plan.py`) is an immutable, append-once record carrying:

- identity
- `source_trade_plan_id`
- `instrument`
- policy identity/version and governing parameters
- supplied sizing context (`supplied_account_equity`, `supplied_risk_percent`)
- `status`
- `reasons`
- optional `PositionSizing`

`PositionSizing` carries the computed quantitative surface:

- `entry_price`
- `stop_price`
- `risk_per_unit`
- `allowed_risk_amount`
- `maximum_notional`
- `risk_based_quantity`
- `capital_based_quantity`
- `quantity`
- `position_notional`
- `actual_risk`

`APPROVED_POSITION_PLAN` requires a populated `PositionSizing`, `quantity > 0`, zero reasons, `actual_risk <= allowed_risk_amount`, and `position_notional <= maximum_notional`. `REJECTED_POSITION_PLAN` carries exactly one real reason and may still preserve computed sizing details when that improves auditability.

## 8. Core Sizing Math

For an authoritative approved `TradePlan`:

- `risk_per_unit = entry_price - stop_price` (already frozen by M059)
- `allowed_risk_amount = account_equity * risk_percent`
- `maximum_notional = account_equity * maximum_notional_percent`
- `risk_based_quantity = floor(allowed_risk_amount / risk_per_unit)`
- `capital_based_quantity = floor(maximum_notional / entry_price)`
- `quantity = min(risk_based_quantity, capital_based_quantity)` when both are positive
- `position_notional = quantity * entry_price`
- `actual_risk = quantity * risk_per_unit`

All computations use `Decimal`. No binary float enters the pipeline.

## 9. Capital Gate Behavior

Two models were evaluated:

1. **Reject whenever risk-derived quantity exceeds the capital-safe quantity.**
2. **Approve the largest capital-safe quantity, capped deterministically downward.**

**Selected: option (2).** If risk sizing says "2 shares" but the capital rule only allows "1 share," the platform approves exactly 1 share, preserving a useful explainable plan instead of rejecting a still-valid smaller size. This makes the first product contract clearer: the platform answers "how many units may I safely take?" rather than only "was my first quantity guess too large?"

Rejection still occurs when capital cannot fund even one whole share (`capital_based_quantity <= 0`).

## 10. Approval / Rejection Vocabulary

`PositionPlanStatus`:

- `APPROVED_POSITION_PLAN`
- `REJECTED_POSITION_PLAN`

`PositionPlanRejectionReason`:

- `SOURCE_PLAN_NOT_APPROVED`
- `INVALID_EQUITY`
- `INVALID_RISK_BUDGET`
- `POLICY_VIOLATION`
- `ZERO_POSITION_SIZE`
- `CAPITAL_LIMIT_EXCEEDED`

No aspirational reason codes were added. Every code is reachable and covered by tests.

## 11. Source Integrity and Provenance

M060 loads the authoritative persisted `TradePlan` through `TradePlanRepository.get()`. The caller never re-supplies:

- entry
- stop
- target
- risk per unit
- approval status
- strategy identity
- ranking identity

The persisted provenance chain becomes:

`TradingOpportunityScan` -> `DecisionCandidate` -> `TradePlan` -> `PositionPlan`

`source_trade_plan_id` is stored on every `PositionPlan`, preserving a direct answer to: "why was this quantity approved or rejected?"

## 12. Rejected-TradePlan Boundary

A `REJECTED_PLAN` from M059 can never become an `APPROVED_POSITION_PLAN`. There is no override flag, no "force" path, and no caller-supplied status. `build_position_plan()` rejects such input as `SOURCE_PLAN_NOT_APPROVED`.

## 13. Edge Conditions

M060 handles deterministically:

- zero equity -> `INVALID_EQUITY`
- negative equity -> `INVALID_EQUITY`
- zero risk budget -> `INVALID_RISK_BUDGET`
- negative risk budget -> `INVALID_RISK_BUDGET`
- risk percent above policy maximum -> `POLICY_VIOLATION`
- risk budget too small for one share -> `ZERO_POSITION_SIZE`
- capital too small for one share -> `CAPITAL_LIMIT_EXCEEDED`
- exact policy boundary -> approval allowed
- exact capital boundary -> approval allowed
- repeating-decimal division -> deterministic floor semantics

Division by zero is structurally unreachable because M059 already guarantees positive `risk_per_unit` for approved plans.

## 14. Persistence Model

New migration `73f4a1d89b22` (`down_revision = "256558a33013"`) creates `position_plan`, an immutable append-once table. No transition child table is introduced. If sizing conditions change, a new `PositionPlan` is created rather than mutating the old one.

Persisted fields include:

- identity
- `source_trade_plan_governance_id`
- `instrument_symbol`
- policy identity/version/parameters
- supplied equity / risk context
- status / reasons
- sizing outputs (`allowed_risk_amount`, both quantity axes, final quantity, notional, actual risk)

Database constraints preserve approved/rejected coherence, complementing the in-memory invariants.

## 15. Evidence Integration

M060 adds one `ArtifactReference` per `PositionPlan`:

`value = f"position-plan:{plan.identity.governance_id}"`

This extends the existing audit chain without duplicating full state into `EvidencePackage`. Preferred lineage becomes:

`EvidencePackage` -> scan artifact -> trade-plan artifact -> position-plan artifact

## 16. Application Layer and CLI

Application layer:

- `BuildPositionPlanCommand` / `BuildPositionPlanHandler`
- `GetPositionPlanQuery` / `GetPositionPlanHandler`

Production entrypoints:

- `empirical-platform-build-position-plan`
- `empirical-platform-get-position-plan`

The command handler:

1. loads the authoritative `TradePlan`;
2. validates source eligibility;
3. applies sizing policy and capital gate;
4. persists exactly one `PositionPlan`;
5. returns the structured result.

No portfolio mutation, no account mutation, no broker mutation, and no direct domain-to-persistence coupling is introduced.

## 17. No-Future-Data Boundary

`build_position_plan()` accepts only:

- `identity`
- authoritative `trade_plan`
- `sizing_context`
- `policy`

It does not accept bars, windows, quotes, or wall-clock inputs. Position sizing depends only on the frozen `TradePlan` geometry plus caller-supplied sizing context. No current-price refresh or live market-data lookup exists anywhere in the M060 path.

## 18. Acceptance Surface

Using real persisted M059 plans, M060 proves at least:

- approved source + sufficient budget -> approved position plan
- approved source + tiny risk budget -> zero-size rejection
- approved source + capital cap tighter than risk sizing -> approved capped quantity
- rejected trade plan source -> rejected position plan
- exact policy / notional boundary -> approved boundary case

All of these are executed against real PostgreSQL through production entrypoints in `tests/integration/test_m060_position_plan_lifecycle.py`.

## 19. Independent Mathematical Verification

M060 includes a separately-authored, non-reused mathematical verifier (`tests/unit/test_decision_candidate_position_plan_independent_verification.py`) that recomputes:

- allowed risk amount
- risk-based quantity
- capital-based quantity
- final quantity
- position notional
- actual risk

without calling the production sizing function.

## 20. Hostile Review Focus

The milestone's hostile review attacks exactly the real risks:

- rejected or missing source plans
- invalid context values
- policy-cap violations
- tiny budgets
- capital boundary behavior
- quantity-rounding behavior
- repeating-decimal behavior
- duplicate identity
- persistence round-trip
- deterministic replay
- no-future-data discipline
- no broker / no portfolio / no leverage scope integrity

Genuine defects discovered during implementation are corrected inline and recorded in the freeze document.

## 21. In-Scope

`PositionPlan` domain + repository contract, one versioned sizing policy, one PostgreSQL migration + adapter, two usecases, two CLI entrypoints, focused unit/integration tests, evidence linkage, this governance document, and the macro-milestone freeze package.

## 22. Out-of-Scope

Any broker connectivity, order placement, fills, execution engine, portfolio/account aggregate, cash ledger, buying-power engine, leverage, margin, live quote refresh, future-data-dependent resizing, profitability claim, or M061 capability.

## 23. M061 Boundary

No MILESTONE-061 capability, terminology, or sequencing decision is frozen here beyond the requirement that it start strictly after M060 is approved and frozen.

## 24. Status

**CANDIDATE_INTERNAL_MACRO_SCOPE_AND_DESIGN.**
