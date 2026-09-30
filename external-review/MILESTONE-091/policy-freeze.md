# MILESTONE-091 — M090 V1 Policy Freeze (Phase 3)

Written BEFORE any validation result exists. Nothing below is chosen or adjusted after
seeing outcomes; the fingerprint below exists precisely so that claim is checkable — any
later change to any frozen field produces a different fingerprint, visibly.

## Which policy this freezes

The **production** `OpportunityEnginePolicy` as reviewed and accepted for the real M090
console (`entrypoints._opportunity_engine_composition.DEFAULT_OPPORTUNITY_ENGINE_POLICY`),
**not** `tools/m090_replay.py`'s own separate, more lenient CLI-testing defaults (that
script's `default_policy()` uses `minimum_recent_share_volume=1000`, a research-CLI
convenience value never reviewed for the real console, which used `20_000`). Validating
"whether M090 V1 has evidence of a usable intraday edge" means validating the policy the
Owner would actually run, not a laxer stand-in — so this freeze uses the production
console's own `20_000` share floor, and this discrepancy between the two existing defaults
is noted here rather than silently inherited.

A canonical `OperatorTradingConfiguration` for this validation is ALSO frozen here, since
none existed as a single reviewed artifact before now (the real console reads whatever
configuration happens to be staged under `CFG-090-PAPER` at runtime, which is fixture-only
so far) — its thresholds are taken from `tools/m090_replay.py`'s own already-reviewed
defaults (spread/liquidity/price bounds/entry window), since those values WERE already
exercised in the Phase 20 initial research report.

## FROZEN — OpportunityEnginePolicy

| Field | Value |
|---|---|
| `policy_version` | `M090-V1` |
| `structure_lookback_bars` | `5` |
| `minimum_recent_share_volume` | `20000` |
| `minimum_reward_risk_ratio` | `2` |
| `maximum_loss_per_trade` | `100` |
| `top_n` | `5` |
| `entry_tolerance_percent` | `0.5` |
| `opportunity_validity_seconds` | `300` |

## FROZEN — signal / ranking model identities

| Field | Value |
|---|---|
| `structure_model_id` | `BOUNDED_RANGE_BREAKOUT_HIGHER_LOW_VOLUME` |
| `structure_model_version` | `1` |
| `quality_model_id` | `SPREAD_LIQUIDITY_TREND_REWARD_RISK_FRESHNESS_WEIGHTED_SUM` |
| `quality_model_version` | `1` |

## FROZEN — validation OperatorTradingConfiguration (relevant fields only)

| Field | Value |
|---|---|
| `watchlist` | `AAPL, AMZN, GOOGL, META, MSFT, NVDA, QQQ, SPY` (canonical ascending) |
| `permitted_markets` | `ARCA, NASDAQ, NYSE` |
| `maximum_spread_percent` | `1` |
| `minimum_liquidity_shares` | `100000` |
| `minimum_price` / `maximum_price` | `5` / `5000` |
| `permitted_session` | `REGULAR` |
| `earliest_entry_time` / `latest_entry_time` | `10:00:00` / `15:30:00` (operator tz) |
| `mandatory_liquidation_time` | `15:45:00` (operator tz) |
| `operator_timezone` | `America/New_York` |
| `maximum_capital_per_trade` | `2000` |
| `maximum_percent_per_trade` | `50` |
| `maximum_deployable_capital` | `20000` |
| `default_order_type` / `limit_price_policy` | `LIMIT` / `ASK` |
| `maximum_leverage` | `1` |
| `short_selling_permitted` | `false` |
| `overnight_positions_permitted` | `false` |

## Canonical fingerprint

SHA-256 of the canonical (sorted-key, no-whitespace) JSON object combining the three tables
above exactly:

```
6ed540efd2b2638bf5a3a9aae290874bad6c5fdad54c604325c86ce4fd2c49da
```

## Freeze rule

**No field above may change for the duration of this milestone's validation study, for any
reason, including an unfavorable result.** Any future change to any of these values is a
new policy version and a later milestone's decision, never a same-milestone reaction to
this study's own output.
