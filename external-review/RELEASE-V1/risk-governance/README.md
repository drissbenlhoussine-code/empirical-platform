# V1 risk-governance safety / compatibility correction

Owner authorization: 2026-10-02, continuation of PR #26, no new milestone.

The original M084 baseline remains historical evidence. Its ratified commit,
original digest manifest, authority package, migration, and historical tests are
unchanged. `baseline.json` identifies that commit and every original/corrected
Git blob in eight-character groups. Each `original-*.py.txt` is the exact original
Git blob, independently checked against the original M084 manifest.

A release-blocking defect was discovered later: the original configuration did
not express per-position share and per-trade planned-loss caps, and the approved
intent lacked the immutable stop needed to re-prove risk immediately before send.
The original baseline cannot supply the required current-v1 risk guarantee.

This is a **safety/compatibility correction and superseding operational baseline**,
not a rewrite of historical evidence. Exact affected files and corrections:

- `decision_candidate/operator_trading_configuration.py`: explicit v2 limits,
  validation and deterministic configuration fingerprint; v1 absence stays absent.
- `decision_candidate/trade_proposal.py`: share-cap sizing, exact loss gate,
  immutable risk evidence and fingerprint binding; v1 fingerprint unchanged.
- `decision_candidate/trade_approval.py`: carry approved immutable risk into intent.
- `shared/persistence/postgres_repositories/decision_to_approval_repositories.py`:
  additive risk storage and exact row mappings, with historical-schema reads.
- `usecases/decision_to_approval_io.py`: explicit versioned configuration input and
  exact configuration/proposal/intent risk evidence for the Owner.

The exact five paths are enumerated in `baseline.json`; no path is exempted from
freezing. `tools/check_frozen_paths.py` validates original archived blobs and the
corrected operational blobs. Later edits fail unless separately reviewed and
recorded. The existing destructive-tool safety correction remains independent.
The secret scanner verifies original digest entries against their exact archived
Git blobs, never against a hash-shaped name or blanket exemption.

Tests: `test_v1_entry_risk_contract.py` (boundaries, sizing, exact arithmetic,
serialization, fingerprints, legacy refusal, fake dispatch, late transport
mutation), `test_v1_risk_contract_postgres.py` (old-head upgrade and persistence),
`test_v1_integrated_deployment_shape_postgres.py` (real full-head composition and
corrupted-schema rejection), `test_v1_risk_compatibility_baseline.py` (archives,
exact corrected identities, future mutations and malformed records), plus the
unchanged historical M084 and subsequent regression suites. The final PR CI is
the authoritative verification of the committed correction, not earlier green CI.

No real database migration, configuration, plan, or broker action is authorized
by this engineering correction.
