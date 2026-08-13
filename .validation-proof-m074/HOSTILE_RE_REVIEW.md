# MILESTONE-074 Focused Hostile Re-Review (Owner Correction Pass)

This document re-attacks the three BLOCKING findings from owner review
plus the new code that addresses them. Every check records its
disposition (PASS / FIXED / N/A_WITH_REASON).

## Re-Attack Vectors

### R1. evaluated vs eligible confusion

- R1.1. `test_u2_regression_eligible_superset_evaluated_subset_still_compatible` — PASS. The new test constructs a study whose EVALUATED union covers M070 requested symbols, but no single window's EVALUATED set is the full superset. It asserts COMPATIBLE. Confirmed: fails on the pre-correction code (`42eafb5`), passes on the correction.
- R1.2. `test_u2_evaluated_subset_only_fails_u2_pass_u1` — PASS. The new negative test confirms that when NO window's ELIGIBLE set is a superset (only the union of EVALUATED covers M070), the rule is INCOMPATIBLE. Pre-correction code was already INCORRECTLY COMPATIBLE in this scenario; the corrected code correctly returns INCOMPATIBLE.
- R1.3. `_evaluate_compatibility` now resolves `eligible_instrument_ids` for U2 and stores the result in `matched_window_resolved_eligible_symbols` — PASS. The pre-correction code stored the EVALUATED set in this field; the corrected code stores the ELIGIBLE set.
- R1.4. Docstring at lines 22-23 of `historical_portfolio_evidence.py` updated to clearly distinguish U1 (evaluated union) from U2 (eligible superset) — PASS.

### R2. Missing InstrumentMaster mappings

- R2.1. `_resolve_symbols` silently drops unknown `InstrumentId`s — PASS (preserved from initial implementation).
- R2.2. With `instrument_master = None`, the resolver returns `()` for every call — PASS (no symbols, so U1 fails with "not represented in any M064 evaluated set" reason).
- R2.3. New `test_u2_regression_*` test would still pass if the `eligible` set partially resolved; uses `_build_instrument_master()` with both AAPL and MSFT, exercising full resolution — PASS.

### R3. Malicious caller-supplied portfolio_lookup

- R3.1. `test_m067_malicious_portfolio_lookup_under_wrong_key_is_dropped` — PASS. A pure-domain test that builds a valid M067 report referencing M064 study B, inserts it under M064 study A's runtime_id key, and asserts the M067 fields on the resulting `HistoricalPortfolioEvidence` are all `None`. Confirmed: fails on pre-correction code (the M067 fields were populated with the bad report's values), passes on the correction.
- R3.2. `test_m067_correct_lineage_is_attached` — PASS. Companion test confirms the corrected rule still attaches an M067 report whose `source_study_runtime_id` DOES match the M064 candidate.
- R3.3. The pre-correction code branched on `governance_id`; both branches were `pass`. The corrected code is a single `if/else` keyed on `source_study_runtime_id` — PASS.

### R4. Wrong M067 source_study_runtime_id

- R4.1. R3.1 covers the keyed-but-wrong case. R3.1 also covers the same study but different runtime case.
- R4.2. Code comment at lines 433-444 explicitly states: "Even if `portfolio_lookup` keys a report under this study's runtime_id, the report's own `source_study_runtime_id` is the truth. If it doesn't match this study's runtime_id, the report belongs to a different M064 study -- it is silently dropped." — PASS.
- R4.3. The M064 evidence itself is still surfaced when an M067 report is dropped — PASS (verified in R3.1: `compatibility_status is COMPATIBLE` AND `portfolio_study_identity_governance is None`).

### R5. Equal coverage ordering

- R5.1. `test_equal_coverage_uses_deterministic_runtime_id_tiebreak` (from the original 23 tests) — PASS.
- R5.2. `matched_window_resolved_eligible_symbols` field is now populated from the ELIGIBLE set, not the EVALUATED set. This does not affect ordering, which is by `coverage_end` then `runtime_id` — PASS.

### R6. Exhaustive SQL discovery wording

- R6.1. PostgresHistoricalPortfolioEvidenceQueryRepository class docstring now explicitly states the EXHAUSTIVE scan semantics — PASS.
- R6.2. KNOWN LIMITATION #2 in `external-review/MILESTONE-074/README.md` is honest about the no-LIMIT design — PASS.
- R6.3. T1 in the original hostile review was rewritten to match reality (no claim of bounded discovery) — PASS.
- R6.4. No silent LIMIT was injected into the adapter — PASS (the SQL remains `SELECT * FROM survivorship_study ORDER BY governance_id`).

## Total: 16 / 16 PASS, 0 FAIL

| Vector | Disposition |
|--------|-------------|
| R1 evaluated vs eligible confusion | PASS (4 checks) |
| R2 missing InstrumentMaster | PASS (3 checks) |
| R3 malicious portfolio_lookup | PASS (3 checks) |
| R4 wrong source_study_runtime_id | PASS (3 checks) |
| R5 equal coverage ordering | PASS (2 checks) |
| R6 exhaustive SQL discovery wording | PASS (4 checks) |
