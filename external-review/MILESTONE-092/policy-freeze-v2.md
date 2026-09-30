# MILESTONE-092 — V2 Policy Freeze (Phase 13) — Candidate V2-C

Written after DEVELOPMENT-only comparison and BEFORE any VALIDATION or FINAL HOLDOUT result exists (see `external-review/MILESTONE-092/candidate-comparison.md` for the selection rationale). No field below may change for any reason, including an unfavorable VALIDATION or FINAL HOLDOUT result.

## FROZEN — OpportunityEnginePolicyV2

| Field | Value |
|---|---|
| `policy_version` | `M092-V2-C` |
| `structure_lookback_bars` | `5` |
| `minimum_recent_share_volume` | `2000` |
| `relative_liquidity_multiple` | `1.5` |
| `minimum_volume_ratio` | `1.5` |
| `minimum_close_location_value` | `0.6` |
| `target_range_multiple` | `2` |
| `minimum_reward_risk_ratio` | `1.3` |
| `time_to_target_feasibility_enabled` | `True` |
| `time_to_target_safety_factor` | `1` |
| `maximum_loss_per_trade` | `100` |
| `top_n` | `5` |
| `entry_tolerance_percent` | `0.5` |
| `opportunity_validity_seconds` | `300` |

## FROZEN — model identities

| Field | Value |
|---|---|
| `structure_model_id` | `BOUNDED_RANGE_BREAKOUT_HIGHER_LOW_VOLUME_V2` |
| `structure_model_version` | `1` |
| `entry_quality_model_id` | `CLOSE_LOCATION_AND_VOLUME_RATIO_CONFIRMATION_V2` |
| `entry_quality_model_version` | `1` |
| `liquidity_model_id` | `ABSOLUTE_FLOOR_PLUS_RELATIVE_VOLUME_RATIO_V2` |
| `liquidity_model_version` | `1` |
| `geometry_model_id` | `STRUCTURAL_STOP_RANGE_AWARE_TARGET_V2` |
| `geometry_model_version` | `1` |

## FROZEN — validation OperatorTradingConfiguration (relevant fields only)

Identical to `external-review/MILESTONE-091/policy-freeze.md`'s own configuration (same universe, price bounds, session window, capital caps) -- V2 changes the POLICY, not the configuration.

## Canonical fingerprint

SHA-256 of the canonical (sorted-key, no-whitespace) JSON object combining the policy, model identities, and configuration exactly as `compute_fingerprint` in this script computes it:

```
2fcd41e03da2a9a20ee5b617bab02f49e97077eb9ed8ff8b59966a7ac3c8e604
```

## Freeze rule

**No field above may change for the duration of this milestone's VALIDATION or FINAL HOLDOUT runs, for any reason, including an unfavorable result.** Any future change to any of these values is a new policy version and a later milestone's decision.
