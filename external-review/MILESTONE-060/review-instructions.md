# MILESTONE-060 External Review Instructions

## Baseline

- Repository: `C:\Users\LuxSy\Documents\trading`, branch `master`.
- M060's own frozen baseline: `5526ee325416d39d3b37dd7d0b51e3f1cd1d05ef` (M059 fully `APPROVED_AND_FROZEN`).
- M060 implementation commit: `89592838d76f13eedbd22305b45627356766f58b`.
- M060 owner-freeze commit: `06cdd26622c6fe700c32de3d66139056098088e8`.
- `complete.diff` spans `5526ee325416d39d3b37dd7d0b51e3f1cd1d05ef..06cdd26622c6fe700c32de3d66139056098088e8` -- the full substantive M060 milestone delta.

## Mission Type

Continues the reduced-ceremony Macro Milestone Protocol used by M053-M059. Two governance documents carry milestone authority: `MILESTONE_060_POSITION_SIZING_CAPITAL_EXPOSURE_GATE_SCOPE_AND_DESIGN.md` and `MILESTONE_060_POSITION_SIZING_CAPITAL_EXPOSURE_GATE_MACRO_MILESTONE_FREEZE.md`.

## Commit Lineage

| Commit | Message | Role |
| --- | --- | --- |
| `5526ee325416d39d3b37dd7d0b51e3f1cd1d05ef` | `docs: record M059 owner freeze commit hash` | M060 frozen baseline |
| `89592838d76f13eedbd22305b45627356766f58b` | `feat: implement M060 position sizing and capital exposure gate` | Implementation |
| `06cdd26622c6fe700c32de3d66139056098088e8` | `docs: record M060 owner macro milestone freeze` | Owner freeze |

## Review Priorities

1. **Source integrity is preserved.** Confirm `build_position_plan` loads the authoritative persisted M059 `TradePlan` and never accepts caller-supplied entry/stop/target/risk-per-unit values.
2. **The sizing contract is explicit and versioned.** Read `src/empirical_platform/decision_candidate/position_plan.py` and confirm the persisted policy snapshot is `EQUITY_PERCENT_RISK_SIZING_GATE` v1 with `maximum_risk_percent = 0.02`, `maximum_notional_percent = 0.25`, and whole shares only.
3. **Capital gating is deterministic and explainable.** Confirm final approved quantity is `min(risk_based_quantity, capital_based_quantity)` when both are positive, and that the code rejects only when risk or capital cannot fund even one whole share.
4. **Rejected M059 trade plans cannot become approved position plans.** Confirm `SOURCE_PLAN_NOT_APPROVED` is the outcome for a rejected source plan and that no override path exists.
5. **No future-market-data surface exists.** `build_position_plan()` must accept only `identity`, authoritative `trade_plan`, caller-supplied `sizing_context`, and `policy`; no bars, quotes, windows, or clock inputs may appear.
6. **No broker, portfolio, leverage, or mutable account state exists.** Confirm the M060 delta introduces planning only, not execution or mutable capital-state behavior.
7. **Hostile-review corrections are real and narrow.** Inspect `scripts/security.ps1`, `tools/secret_scan_targets.py`, and `tests/unit/test_secret_scan_targets.py`; confirm they address Windows command-length and benign migration false positives without disabling real secret scanning.
8. **Independent math agrees without calling production sizing.** Review `tests/unit/test_decision_candidate_position_plan_independent_verification.py` and the raw-subprocess `evidence/independent-second-pass.txt`.
9. **PostgreSQL truth matches the application claims.** Review `tests/integration/test_m060_position_plan_lifecycle.py` and `evidence/independent-second-pass.txt`; confirm approved, small-budget rejection, capital-capped approval, and rejected-source rejection all survive persistence and raw-SQL inspection.
10. **Canonical validation remained green after the hostile-review corrections.** Use `evidence/security-output.txt`, `evidence/verify-output.txt`, `evidence/focused-m060-tests.txt`, and `evidence/build-output.txt`.

## Expected Validation Facts

- Python `3.13.14`
- full canonical verify: `1522 collected`, `1516 passed`, `6 skipped`, `0 failed`
- focused M060 suite: `26 passed`, `4 skipped`
- mypy clean across `180` source files
- secret scan target count: `655`
- wheel/sdist build succeeded
- independent second pass: all checks passed

## Scope Integrity

M060 must not introduce:

- broker connectivity
- order placement or fills
- mutable portfolio or cash ledgers
- leverage or margin
- live quote refresh
- future-data-dependent resizing
- profitability claims
- M061 behavior
