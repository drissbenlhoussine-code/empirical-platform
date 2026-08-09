# MILESTONE-061 External Review Instructions

## Baseline

- Repository: `C:\Users\LuxSy\Documents\trading`, branch `master`.
- M061's own frozen baseline: `a544be6ee073456d0360108e87105d4f3ab1be59` (M060 fully `APPROVED_AND_FROZEN`).
- M061 implementation commit: `3b6ea1d4d81e7ad379ceb04d73a5336c66f7009d`.
- M061 owner-freeze commit: `c5ce6f64bc030ebf7c144ddcacc4119fc3b64b9c`.
- `complete.diff` spans `a544be6ee073456d0360108e87105d4f3ab1be59..c5ce6f64bc030ebf7c144ddcacc4119fc3b64b9c` -- the full substantive M061 milestone delta.

## Mission Type

Continues the reduced-ceremony Macro Milestone Protocol used by M053-M060. Two governance documents carry milestone authority: `MILESTONE_061_HISTORICAL_STRATEGY_VALIDATION_AND_BACKTESTING_V1_SCOPE_AND_DESIGN.md` and `MILESTONE_061_HISTORICAL_STRATEGY_VALIDATION_AND_BACKTESTING_V1_MACRO_MILESTONE_FREEZE.md`.

## Commit Lineage

| Commit | Message | Role |
| --- | --- | --- |
| `a544be6ee073456d0360108e87105d4f3ab1be59` | `docs: record M060 owner freeze commit hash` | M061 frozen baseline |
| `3b6ea1d4d81e7ad379ceb04d73a5336c66f7009d` | `feat: implement M061 historical strategy validation and backtesting V1` | Implementation |
| `c5ce6f64bc030ebf7c144ddcacc4119fc3b64b9c` | `docs: record M061 owner macro milestone freeze` | Owner freeze |

## Review Priorities

1. **Frozen M057-M060 decision semantics are reused rather than duplicated.** Confirm `historical_backtest.py` orchestrates the existing trading-evaluation, ranking, trade-plan, and position-plan rules instead of introducing backtest-only strategy copies.
2. **Historical dataset authority is explicit and immutable.** Review `tests/fixtures/m061_historical_backtest/README.md`, the JSON fixture, and the persisted `dataset_id`, `dataset_version`, `dataset_source_kind`, and SHA-256 evidence.
3. **Decision-time semantics are non-look-ahead.** Confirm decisions use bars through cutoff `T` only and hypothetical entry occurs at next-bar open `T+1`.
4. **Same-bar ambiguity is conservative.** Review `SameBarAmbiguityPolicy.STOP_FIRST`, the NVDA fixture path, and persisted `ambiguity_triggered = true` raw-SQL evidence.
5. **Costs and PnL use explicit Decimal-safe formulas.** Review `historical_backtest.py`, the independent verification suite, and the second-pass recomputation output.
6. **Persistence truth is auditable.** Validate `historical_backtest_run` and `historical_backtest_trade` rows using `evidence/independent-second-pass.txt` and `tests/integration/test_m061_historical_backtest_lifecycle.py`.
7. **Replay is deterministic and future-bar mutation does not change earlier trades.** Review the replay and look-ahead evidence in `evidence/independent-second-pass.txt` plus the focused unit suites.
8. **The package makes no profitability or live-readiness claim.** The only allowed product classification is a validation-engine statement about the fixture.
9. **Toolchain/security remained green after the narrow scanner hardening.** Use `evidence/security-output.txt`, `evidence/verify-output.txt`, `tools/secret_scan_targets.py`, and `tests/unit/test_secret_scan_targets.py`.
10. **Scope remains bounded.** M061 must not introduce broker execution, mutable portfolio accounting, optimization loops, live data, or M062 behavior.

## Expected Validation Facts

- Python `3.13.14`
- full canonical verify: `1536 collected`, `1272 passed`, `264 skipped`, `0 failed`
- coverage: `81.80%`
- focused M061 unit suites: `9 passed`
- M057-M061 PostgreSQL regression: `22 passed`
- full PostgreSQL integration suite: `258 passed`, `6 skipped`
- secret scan target count: `711`
- build succeeded
- independent second pass: `PASS`

## Scope Integrity

M061 must not introduce:

- broker connectivity
- live market-data downloads
- optimization/parameter search
- mutable portfolio ledgering
- leverage or margin engines
- profitability claims
- live-trading-readiness claims
- M062 behavior
