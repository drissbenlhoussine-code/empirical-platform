# MILESTONE-059 trade-plan fixture

**Synthetic, hand-authored. Not live or historical market data.**

`synthetic_boundary_ratio_universe.json` -- a 2-instrument universe (BNDA,
BNDB), each sharing the identical five-bar reference set used throughout
the M058 fixture (`reference_high = 100.50`), differing only in their
evaluation bar's close, purpose-built to land exactly at and just below
the M059 default risk policy's minimum reward/risk ratio (2.0).

## Expected results (computed by hand, verified against `evaluate()`/`build_trade_plan()` before use)

Both use `stop_price = reference_high = 100.50` and
`target_price = reference_high * 1.02 = 102.51`.

| Instrument | entry (close) | risk_per_unit | reward_per_unit | reward_risk_ratio | plan status |
| --- | --- | --- | --- | --- | --- |
| BNDA | 101.17 | 0.67 | 1.34 | **2.00** (exactly the minimum) | APPROVED_PLAN (inclusive `>=`) |
| BNDB | 101.18 | 0.68 | 1.33 | 1.955882... (just below 2.00) | REJECTED_PLAN (REWARD_RISK_BELOW_MINIMUM) |

Both instruments independently satisfy the M057 `LONG_CANDIDATE` price
(close > 100.50) and volume (1100 > 1012) conditions, so both produce a
genuine `LONG_CANDIDATE` `DecisionCandidate` before the M059 risk gate is
ever applied -- the boundary is purely in the trade-plan geometry, not in
the underlying strategy decision.

`synthetic_6instrument_scan_universe_second_scan.json` -- byte-for-byte
identical bars to `tests/fixtures/m058_market_scan/synthetic_6instrument_
scan_universe.json`, but with a distinct `decision_candidate_governance_id`
namespace (`DCAND-8201`..`DCAND-8206` instead of `DCAND-8101`..`DCAND-8106`).
Used only by the hostile provenance test (`test_hostile_mismatched_scan_and_
candidate_is_rejected`) to produce a second, genuinely independent scan over
the same instrument set, so a candidate from scan B can be presented,
adversarially, as if it belonged to scan A.
