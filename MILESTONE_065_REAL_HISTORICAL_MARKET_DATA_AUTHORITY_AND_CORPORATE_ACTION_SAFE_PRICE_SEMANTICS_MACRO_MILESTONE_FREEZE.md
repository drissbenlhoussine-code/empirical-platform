# MILESTONE-065 - Real Historical Market Data Authority + Corporate-Action-Safe Price Semantics + Historical Import/Validation Pipeline - Macro Milestone Freeze

## Status: FINAL - OWNER FROZEN

## Repository Authority

Repository `C:\Users\LuxSy\Documents\trading`, branch `master`. M065
baseline `cc90d0369a30ace2903a280630a26e3dca644872` (the M064 Owner
Freeze hash-recording HEAD; M064 fully `APPROVED_AND_FROZEN`),
independently re-verified at mission start and again during the
logically independent second pass (`git fetch`, `git status`,
`git rev-parse HEAD`/`origin/master` agreed both times: 0 ahead / 0
behind, clean tree except the M065 working-tree changes themselves).
Implementation commit `58d9296`.

## Delivered Capability

Before this milestone, every backtest in this platform ran against a
dataset whose historical price authority was a single opaque, already
-canonical JSON file (M061's `HistoricalDatasetAuthority`) -- there was
no first-class record of where that data came from, no explicit
declaration of whether its prices were raw or split-adjusted, and no
mechanism to apply or verify corporate-action semantics (stock splits,
reverse splits, symbol changes) at all. After this milestone, a caller
can present a local directory of raw CSV source files, an instrument
master, and an optional corporate-action manifest to
`import_historical_dataset_snapshot`, and receive one immutable,
versioned `DatasetSnapshotAuthority` recording exactly which files were
imported (with their own raw-byte SHA-256s), the resulting
canonical-content SHA-256, and an explicit price-semantics declaration
-- plus, when a manifest is supplied, a second, derived `SPLIT_ADJUSTED`
snapshot with deterministic, independently-reproducible split/reverse
-split/symbol-change math applied bar-by-bar. The import pipeline
produces a byte-identical M061-compatible dataset artifact, so the real,
unmodified, frozen M061 `run-historical-backtest` CLI is reused verbatim
-- no parallel backtesting engine was written. A
`CORPORATE_ACTION_SEMANTICS_STRESS` diagnostic (the real M061
`build_historical_backtest_run()`, called a second time against the raw
-naive interpretation) reports honestly whether split-mishandling would
have changed the backtest's own trade outcomes on this dataset. No real
historical market data was used or claimed; no profitability or
live-readiness claim is made.

## Local Data Discovery Disposition

A dedicated Explore-agent research pass, run before any implementation
began, searched the entire repository and local project directories for
real historical market-data artifacts and any vendor/license/API-key
reference. **Finding: no genuine real historical market data exists
anywhere locally** -- every dataset-shaped file already in the repository
(M061-M064's own fixtures) self-declares synthetic provenance via its
own `source_kind` field, and no vendor, license, or API-key reference
exists anywhere in source or governance docs. Per the mission's own
explicit instruction ("do not use web/network data for canonical
acceptance," "do not fabricate real provenance"), M065 proceeds with a
`CORPORATE_ACTION_MECHANICS_FIXTURE`, honestly labeled at every layer,
plus a production-grade import architecture ready to accept a real
vendor snapshot the moment one is licensed, without any code change.

## Implementation Evidence

New domain and repository surface (5 new `decision_candidate/` modules,
1 new migration, 1 new concrete Postgres repository module, 4 new
usecases, 4 new CLI entrypoints, 1 new identifier type):

- `decision_candidate/corporate_actions.py`, `dataset_snapshot.py`,
  `historical_import.py`, `corporate_action_stress.py`,
  `dataset_snapshot_repository.py` (Protocol contracts)
- migration `c275f69cee79_create_m065_dataset_snapshot_schema.py`
  (`down_revision = d9270168a7c7`, M064's own head) -- 4 tables:
  `dataset_snapshot`, `dataset_snapshot_source_file`, `corporate_action`,
  `corporate_action_semantics_stress`
- `PostgresDatasetSnapshotRepository`, `PostgresCorporateActionRepository`,
  `PostgresCorporateActionSemanticsStressRepository`
- runtime wiring in `postgres_repositories/runtime.py` (`.dataset_snapshots`
  / `.corporate_actions` / `.corporate_action_semantics_stresses`
  properties)
- `usecases/import_historical_dataset_snapshot.py`,
  `get_historical_dataset_snapshot.py`,
  `run_corporate_action_semantics_stress.py`,
  `get_corporate_action_semantics_stress.py`, `historical_import_io.py`
- `entrypoints/import_historical_dataset_snapshot.py`,
  `get_historical_dataset_snapshot.py`,
  `run_corporate_action_semantics_stress.py`,
  `get_corporate_action_semantics_stress.py`
- new `CorporateActionStressId` identifier (prefix `CASTR`)
- CLI registration in `pyproject.toml` (4 new console scripts)

Purely additive: `git diff --stat HEAD` on the implementation commit's
own 4 modified shared files (`pyproject.toml`,
`decision_candidate/__init__.py`, `identifiers/types.py`,
`postgres_repositories/runtime.py`) shows 99 insertions, 0 deletions.
Every other file in the delta is new. No M020-M064 file was deleted,
renamed, or had content removed.

The canonical fixture (`tests/fixtures/m065_corporate_action_mechanics/`):
4 instruments (`ALFA`, `BETA`, `GAMA`, `DELT`), 30 one-minute bars each
(120 rows total), seeded deterministic generation (`SEED=6065001`), one
shared corporate-action boundary at bar index 15
(`2024-03-01T09:45:00+00:00`): `BETA` 2-for-1 `SPLIT`, `GAMA` 1-for-5
`REVERSE_SPLIT`, `DELT` `SYMBOL_CHANGE` (`OLDD` -> `DELT`), `ALFA` as an
undisturbed control instrument. Generated once, accepted as-is on the
first attempt.

## Canonical Results

Reproduced identically via real installed-CLI subprocess against **three**
independent PostgreSQL containers across this mission (`m063-dev-pg`
port 55466 used for the main acceptance evidence, plus a fresh
`m065-second-pass-pg` port 55480 built and torn down for the independent
second pass):

- raw snapshot: `dataset_version="1"`, `price_semantics=RAW_UNADJUSTED`,
  `bundle_sha256 = 7fe5bd4b64573e08d5adfc38fa691211c6ffa72c8301037b16d745846d7948fe`,
  `normalized_sha256 = 5d06e0e057c0e01ba1ac04b9ac1731895f785372a65f4c5468f74e53fee38664`
- adjusted snapshot: `dataset_version="2-split-adjusted"`,
  `price_semantics=SPLIT_ADJUSTED`,
  `corporate_action_semantics=SPLIT_AND_SYMBOL_CHANGE_AWARE`,
  same `bundle_sha256` as raw (same source files), different
  `normalized_sha256 = 77390f379ed05b9a80f60f99f59b47ddc562d4f9e2cc9bd21fc5f1f4832b2a76`
- BETA 2-for-1 split boundary: raw pre-split close `203.6577` ->
  adjusted `101.8288` (exactly half); post-split raw and adjusted bars
  are byte-identical at/after the boundary
- GAMA 1-for-5 reverse split boundary: raw pre-split close `19.0970` ->
  adjusted `95.4850` (exactly 5x)
- real, unmodified, frozen M061 `run-historical-backtest` CLI against the
  adjusted artifact: `executed_trade_count=2`,
  `net_pnl=136.5861192780`, and critically `dataset_sha256` in the M061
  run's own output exactly matches
  `DatasetSnapshotAuthority.normalized_sha256`
- `CORPORATE_ACTION_SEMANTICS_STRESS`: `CORPORATE_ACTION_SEMANTICS_STRESS_IDENTICAL`
  -- correct (adjusted) and naive (raw) interpretations produced the same
  2 executed trades, same `net_pnl_total=136.5861192780`, same
  `total_r_total=1.339761890331594634873323398`

This `IDENTICAL` result was accepted honestly, not regenerated to force
`DIFFERS` -- see "Attempting to Disprove the Central Claim" below for the
direct proof that the comparator is genuinely capable of detecting
divergence and that this specific `IDENTICAL` outcome is a real,
fixture-specific property, not evidence of a broken diagnostic.

## Hostile Review

All mission-specified hostile-review categories (54 explicit cases,
recorded in full in `external-review/MILESTONE-065/hostile-review-matrix.md`)
were attacked; two genuine findings were fixed inline before freeze:

- **FIXED**: `derive_split_adjusted_snapshot()` silently accepted a
  corporate action referencing an instrument entirely absent from the
  dataset's own raw import, with no error and no effect -- a governance
  typo (wrong `instrument_id`) would silently produce zero adjustment
  with no warning. Added explicit validation: every declared action's
  `instrument_id` is now checked against the actual imported instrument
  set, raising `ValueError` before deriving anything.
- **FIXED**: `ImportHistoricalDatasetSnapshotHandler.handle()` never
  cross-checked a corporate-action manifest's own self-declared
  `(dataset_id, dataset_version)` against the dataset actually being
  imported, and the `corporate_action` table had no foreign key to
  `dataset_snapshot` -- a caller-supplied manifest could silently attach
  to the wrong (or a nonexistent) dataset with no referential-integrity
  backstop. Fixed with an explicit application-layer `ValueError` check
  (fails before any persistence) plus a new `ForeignKeyConstraint` on
  `corporate_action(dataset_id, dataset_version) -> dataset_snapshot` in
  the migration, re-verified via a full upgrade/downgrade/upgrade
  round trip.
- **PASS** (verified via dedicated tests, not merely asserted): empty
  source file; malformed CSV (missing column, zero data rows); duplicate
  bars; out-of-order bars; timezone-naive timestamp; invalid OHLC;
  negative volume; unsupported bar interval; unknown instrument; duplicate
  dataset version (real `AggregateAlreadyExists` on PostgreSQL); dataset
  source tamper (bundle/normalized hash both change); normalized-artifact
  tamper after persistence (rejected before any backtest runs, zero
  stress rows persisted); mixed price semantics (structurally impossible
  -- one enum field per snapshot); duplicate corporate action; invalid /
  zero / negative / 1-for-1 split ratio; split and reverse-split boundary
  math (independently re-verified without calling the production
  adjustment functions); volume adjustment (exact inverse of price
  factor); symbol-change boundary (before/at/after, independently
  re-verified); conflicting symbol-change chain; stable `InstrumentId`
  preserved across rename; corporate-action-manifest tamper (hash
  changes on ratio or timestamp edit); future action semantics (correct
  by design -- documented explicitly so it is never mistaken for a bug);
  deterministic replay; file-order independence; manifest declaration
  -order independence; multiple dataset versions coexisting (real
  PostgreSQL); PostgreSQL round trip; raw SQL agreement including
  CHECK-constraint payload coherence; real CLI subprocess (5 CLIs, exit 0
  throughout); M064/M063/M061 semantics preserved (`git diff --stat`
  zero deletions); strategy/ranking/risk/sizing logic unchanged; no
  optimization/cherry-picking/fake-provenance/broker/network/LLM (grep
  -clean); architecture boundary respected; frozen predecessor
  preservation; evidence consistency.
- **N/A** (out of this milestone's own scope, with rationale): membership
  /data mismatch against the M064 eligible universe, inactive historical
  member inclusion, and changing universe membership -- M065 does not
  itself re-run M064 universe/membership evaluation over the imported
  price data; it only reuses the same stable `InstrumentId` type,
  unmodified. No integration claim beyond that is made.

No CRITICAL or MAJOR finding remains open.

## Canonical Validation

Run from the repository `.venv` (`Python 3.13.14`); full detail in
`external-review/MILESTONE-065/canonical-validation.md`:

- Ruff format/check (whole repository): PASS, all checks passed
- mypy (`packages = ["empirical_platform"]`): `Success: no issues found
  in 230 source files`
- architecture checker (`tools/check_architecture.py`): PASS (exit 0)
- full non-integration suite: `1484 passed`, coverage `77.40%` (below
  the 80% gate -- expected, since M065's new PostgreSQL repository code
  is only exercised by the PostgreSQL-gated integration tests, the same
  pattern M064's own repository code follows)
- full suite, real PostgreSQL opt-in: `1766 passed, 6 skipped, 1 failed`,
  coverage `91.60%` (>= 80% gate, PASS). The single failure
  (`test_repr_does_not_expose_real_credentials`, M026, untouched by
  M065) is a pre-existing false positive triggered only because this
  session's local test password happens to be the literal string
  `"postgres"`, a substring of the field name
  `PostgreSQLConfigSnapshot`/`postgresql=` in the printed `repr()` --
  no actual credential value leaks.
- build (`python -m build --wheel`): PASS; all 15 new M065 source files
  and all 4 new console-script entry points confirmed present in the
  built wheel by direct zip inspection
- `pip-audit`: no known vulnerabilities (the local `empirical-platform`
  package itself is correctly skipped as not-on-PyPI, the same benign
  skip every prior milestone's evidence records)
- secret scan: 3 findings, all pre-existing M064 dataset-hash constants;
  **zero new findings introduced by M065**

## Attempting to Disprove the Central Claim

The real M065 acceptance fixture's own `CORPORATE_ACTION_SEMANTICS_STRESS`
diagnostic reports `IDENTICAL`. To rule out the possibility that this is
a symptom of a comparator that can never report `DIFFERS`,
`build_corporate_action_semantics_stress()` was called directly with the
real M065 adjusted dataset as `correct_dataset` and the unrelated,
larger M061 6-instrument fixture dataset as `naive_dataset` -- a
deliberately, obviously different pair. Result:
`CORPORATE_ACTION_SEMANTICS_STRESS_DIFFERS`, with `correct trades=2` vs.
`naive trades=4` and clearly different net PnL. **The comparator
correctly detected and reported the divergence.** This confirms the
`IDENTICAL` result on the real fixture is a genuine, fixture-specific
property -- no trade decision in that particular 30-bar/4-instrument
fixture happens to straddle the split boundary in a way that changes the
outcome -- not evidence of a broken or decorative diagnostic.

## Logically Independent Second Pass

Genuinely distinct from every earlier step in this mission (full detail
in `external-review/MILESTONE-065/independent-second-pass.md`):

- a different, freshly created PostgreSQL container
  (`m065-second-pass-pg`, port 55480), never reused from any earlier
  step, built from an empty schema via `alembic upgrade head`, torn down
  after use
- Git truth independently re-established from scratch
  (`HEAD == origin/master == cc90d0369a30ace2903a280630a26e3dca644872`
  before this milestone's own commits, 0/0, clean except M065's own
  working-tree changes)
- a standalone, stdlib-only script (zero imports from
  `empirical_platform.decision_candidate.*`) independently recomputed
  every raw source-file SHA-256, the `bundle_sha256` formula, the
  BETA/GAMA split boundary math, and the DELT symbol boundary --
  matching production exactly, with the independently-computed
  `bundle_sha256` matching the real-CLI-reported value byte-for-byte
- driven entirely through the real installed CLI executables
  (`.venv/Scripts/empirical-platform-*.exe`), not `python -m` and not
  in-process calls, except for the two deliberate adversarial checks
  below and the disproof-attempt check above
- both hostile-review-fixed defects were independently re-attacked from
  scratch via the real CLI on the fresh container and confirmed still
  properly rejected
- a source-file tamper attack via the real CLI confirmed the resulting
  `bundle_sha256` differs from the untampered original
- raw SQL inspection on the fresh container agreed exactly with the
  CLI-reported values
- a fresh grep/source/governance disproof attempt against the entire
  M065 delta found nothing

Result: **no defect, inconsistency, or unsupported claim found beyond
what the hostile review already identified and fixed.**

## No Optimization / No Cherry-Picking / No Broker / No Network / No LLM

Every M065 source file was searched directly (not sampled) for
optimization/tuning/grid-search/hyperparameter, broker/order-execution
/live-trading, network/HTTP-client, and LLM-provider terms. No matches
anywhere. The canonical fixture's bar data and corporate-action manifest
were both generated once, in a single deterministic pass, and accepted
as-is; no bar, boundary, or ratio was altered after observing results.

## Product Honesty Gate

M065 makes historical dataset provenance explicit and demonstrates, with
real evidence, that raw and adjusted price interpretations are never
silently mixed, that split/reverse-split/symbol-change math is
deterministic and independently re-derivable, and that source and
manifest tampering are detected via hash mismatch. It does **not**
prove:

- that any real historical market data was used (the canonical fixture
  remains synthetic; `source_kind = CORPORATE_ACTION_MECHANICS_FIXTURE`
  throughout)
- that survivorship bias is addressed (that is M064's own, separate,
  already-frozen claim -- M065 does not re-run M064's own membership
  evaluation)
- dividend or total-return accounting
  (`DIVIDEND_TOTAL_RETURN_HANDLING_NOT_EXERCISED`, unconditional)
- profitability
- live-trading readiness
- that current-universe or corporate-action mishandling is a major
  contributor in real markets (the stress diagnostic measures this
  fixture's own mechanics, not real-world magnitude)

## Owner Approval

**M065 MACRO MILESTONE APPROVED_AND_FROZEN.**

Scope, design, implementation, hostile review, independent second
review, and product-honesty gate are frozen as one consolidated unit.
M065 makes historical dataset provenance and corporate-action semantics
first-class and proves the mechanics honestly. It does not certify real
-data usage, survivorship-bias resolution, profitability, or live
readiness.

## Deferred / M066 Boundary

No MILESTONE-066 capability is built here. M066 remains a recommendation
only (see the external-review final report).

## Next Permitted Action

MILESTONE-066 - recommendation only; not started as part of M065.
