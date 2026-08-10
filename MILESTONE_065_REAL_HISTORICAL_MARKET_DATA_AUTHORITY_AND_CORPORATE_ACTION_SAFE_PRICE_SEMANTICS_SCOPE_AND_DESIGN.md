# MILESTONE-065 - Real Historical Market Data Authority + Corporate-Action-Safe Price Semantics + Historical Import/Validation Pipeline - Scope and Design

## 1. Repository Authority

Repository `C:\Users\LuxSy\Documents\trading`, branch `master`. Starting
baseline independently re-verified from Git (not trusted from the mission
brief): `HEAD == origin/master == cc90d0369a30ace2903a280630a26e3dca644872`
(the M064 hash-recording freeze commit), 0 ahead / 0 behind, clean tree.
M064 was confirmed `APPROVED_AND_FROZEN` from its own freeze document.

## 2. Local Data Discovery (Phase 1)

A dedicated research pass searched the entire repository and local project
directories for real historical market-data artifacts (csv/parquet/json,
`historical_data`/`market_data`/`bars`/`prices`/`ohlcv`/`splits`/
`dividends`/`corporate_actions`/`symbol_changes`/`adjusted_close`/
`vendor`/`dataset_license`/`membership_history` keywords), and for any
vendor/license/API-key reference in source or governance documents.

**Finding: no genuine real historical market data exists anywhere
locally.** Every dataset-shaped file already in the repository (M061's
6-instrument fixture, M062's DEV/HOLDOUT bundles, M063's broad robustness
bundle, M064's survivorship-aware fixture) self-declares synthetic
provenance via its own `source_kind` field, and no vendor, license, or
API-key reference exists anywhere in source or governance docs.

## 3. Real-vs-Synthetic Data Decision (Phase 2)

Per the mission's own explicit instruction: **do not use web/network
data for canonical acceptance, and do not fabricate real provenance.**
M065 therefore proceeds with a `CORPORATE_ACTION_MECHANICS_FIXTURE` --
synthetic, seeded-deterministic, labeled honestly at every layer via its
own `source_kind` field -- plus a production-grade import architecture
that is ready to accept a real vendor snapshot the moment one is licensed
and supplied, without any code change. No field anywhere claims real
market-vendor origin.

## 4. Frozen Stack Reuse (No Mutation)

M065 adds new capability without touching any frozen M020-M064 file.
Concretely reused, unmodified:

- `Bar`/`Instrument`/`BarInterval`/`ObservationWindow` (M057)
- `HistoricalInstrumentSeries`/`HistoricalDataset`/
  `HistoricalDatasetAuthority`/`build_historical_backtest_run()`/
  `dataset_sha256()` (M061) -- the OHLC/chronology/duplicate-bar
  invariants and the entire backtest engine are reused verbatim, never
  reimplemented
- `InstrumentId`/`InstrumentMaster`/`InstrumentMasterEntry`/
  `InstrumentType`/`InstrumentMasterRepository` (M064) -- the same stable
  cross-time instrument identity used for membership continuity
- `PositionSizingContext` (M060)
- `CommandEntryPoint`/`QueryEntryPoint`/`DomainIdentity` (M020)
- `entrypoints._composition.postgres_repository_runtime()` (M053)

`git diff --stat` against the M064 baseline confirms zero deletions in
any of these files.

## 5. Product Objective

Can the platform ingest and preserve historically grounded market data in
a way that makes backtests reproducible and prevents stock splits,
symbol changes, or price-adjustment ambiguity from corrupting historical
results? M065 answers this with real, versioned, hash-verified
provenance and explicit, deterministic corporate-action semantics -- not
by claiming survivorship bias, market representativeness, or
profitability.

## 6. Dataset Snapshot Authority

`DatasetSnapshotAuthority` (`decision_candidate/dataset_snapshot.py`),
keyed by `(dataset_id, dataset_version)` -- an immutable, versioned record
of one local import: `source_kind`/`source_name`/`source_reference`/
`license_note` (provenance), `snapshot_created_at`, `interval`,
`start_timestamp`/`end_timestamp`, `instrument_count`/`total_row_count`/
`file_count`, a `source_file_manifest` (per-file name/instrument/SHA-256
/row-count), `bundle_sha256` (hash of the raw source bytes' own
per-file hashes), `normalized_sha256` (hash of the canonical, order
-independent M061-compatible artifact), `price_semantics`,
`corporate_action_semantics`, an optional `corporate_action_manifest_hash`
(cross-validated against `corporate_action_semantics`), and
`dividend_handling`. Deliberately richer than M061's own
`HistoricalDatasetAuthority` (which only tracks one already-canonical
file's identity) -- `DatasetSnapshotAuthority` tracks *provenance*: what
raw source produced this data and how it was interpreted.

## 7. Price Semantics

Closed vocabulary: `RAW_UNADJUSTED`, `SPLIT_ADJUSTED`,
`TOTAL_RETURN_ADJUSTED` (declared, not yet produced by any pipeline path
-- see dividend boundary below). A single `DatasetSnapshotAuthority` never
mixes raw and adjusted prices; each snapshot declares exactly one
interpretation, enforced structurally (one field, one enum value) rather
than by convention.

## 8. Corporate-Action Domain

`decision_candidate/corporate_actions.py`. Three supported action types:
`SPLIT`, `REVERSE_SPLIT`, `SYMBOL_CHANGE`. `DIVIDEND` is deliberately
absent -- see Section 9.

- `SplitAction`: `instrument_id`, `action_type`, `effective_timestamp`,
  `ratio_new_shares`/`ratio_old_shares` (e.g. a 2-for-1 split is
  `ratio_new_shares=2, ratio_old_shares=1`; a 1-for-5 reverse split is
  `ratio_new_shares=1, ratio_old_shares=5`). `action_type` must agree
  with the ratio's own direction -- validated, not merely labeled.
  `adjustment_factor = ratio_old_shares / ratio_new_shares` (multiply a
  PRE-split raw price by this to express it in post-split-comparable
  terms). `volume_adjustment_factor` is the exact inverse (notional
  value is invariant under a pure split).
- `SymbolChangeAction`: `instrument_id`, `effective_timestamp`,
  `old_symbol`/`new_symbol`. The stable `InstrumentId` is unchanged --
  no new instrument identity is ever created for a rename.
- `CorporateActionManifest`: the immutable, hashable set of every
  declared action for one dataset snapshot. Canonicalizes its own
  `actions` tuple order at construction (sorted by `(instrument_id,
  effective_timestamp, action_type)`) so that a construct-then-persist
  -then-retrieve round trip is exact regardless of input declaration
  order, and rejects duplicate actions and conflicting symbol-change
  chains.
- `symbol_at()` / `split_adjustment_factor_at()` /
  `volume_adjustment_factor_at()`: pure, deterministic boundary
  resolution functions. A bar strictly before `effective_timestamp` is
  pre-action; a bar at or after is post-action.
- `corporate_action_manifest_hash()`: SHA-256 over a canonical,
  order-independent JSON payload -- the same semantic manifest in any
  declaration order produces the same hash.

## 9. Dividend Boundary

Explicitly `NOT_SUPPORTED` / `NOT_EXERCISED`:
`DIVIDEND_TOTAL_RETURN_HANDLING_NOT_EXERCISED` is set unconditionally on
every `DatasetSnapshotAuthority`. No total-return backtesting claim is
made anywhere.

## 10. Symbol-Change Semantics

`symbol_at(manifest, instrument_id, current_symbol, timestamp)` resolves
which ticker was in effect at `timestamp` by walking the manifest's own
symbol-change chain backward from the most recent change. Source CSV
files are keyed by each instrument's CURRENT/FINAL ticker symbol as the
filename -- the historical symbol-in-effect is a pure audit/display
concept resolved via `symbol_at()`, never used for file lookup. Integrates
with M064's stable `InstrumentId` directly: renaming never creates a new
instrument.

## 11. Import Pipeline

`decision_candidate/historical_import.py`. Deterministic, single
direction: parse -> validate (reusing frozen `Bar`/
`HistoricalInstrumentSeries`/`HistoricalDataset` invariants, not
reimplementing them) -> map stable instruments -> optionally apply
corporate-action semantics -> canonicalize -> hash -> persist. No hidden
network fetch; the only input is caller-supplied local bytes.

- `import_raw_historical_dataset_snapshot()`: validates and imports a set
  of local CSV files into one `RAW_UNADJUSTED` snapshot. Deterministic
  and order-independent (files are sorted internally before hashing).
- `derive_split_adjusted_snapshot()`: applies
  `split_adjustment_factor_at()`/`volume_adjustment_factor_at()`
  per-bar to an already-imported raw snapshot, producing a
  `SPLIT_ADJUSTED` snapshot. Prices quantized to `Decimal("0.0001")`;
  volume rounded via `ROUND_HALF_UP`. **Validates every declared
  corporate action's `instrument_id` against the actual imported
  instrument set** -- an action referencing an instrument absent from
  this dataset's own raw import is rejected (added during hostile
  review; see the freeze document's hostile-review section).
- `_canonical_artifact_bytes()`: the single, shared serialization
  function used both to compute `normalized_sha256` and to write the
  on-disk M061-compatible dataset JSON artifact -- guaranteeing the two
  are always identical by construction, eliminating an entire class of
  "hash mismatch from differing serialization" bug.

## 12. Raw vs. Normalized Hash Preservation

`bundle_sha256` (SHA-256 of the sorted, pipe-joined per-source-file
SHA-256 digests) answers "what file was imported?" `normalized_sha256`
(SHA-256 of the canonical, order-independent M061-compatible JSON
artifact) answers "what canonical data did the engine use?" The two are
tracked and reported separately, never conflated. A `SPLIT_ADJUSTED`
snapshot shares its raw predecessor's `bundle_sha256` (same source files)
but has a different `normalized_sha256` (different bar values after
adjustment) -- proving dataset-version coexistence structurally.

## 13. No Parallel Strategy/Backtester

Rather than building a new "run validation against a snapshot" capability,
the import pipeline produces a byte-identical M061-compatible dataset
JSON artifact whose own SHA-256 is guaranteed equal to
`DatasetSnapshotAuthority.normalized_sha256` by construction. The real,
unmodified, frozen M061 CLI (`empirical-platform-run-historical-backtest`)
is then used directly against that artifact -- zero new backtest-running
code was written. The `CORPORATE_ACTION_SEMANTICS_STRESS` diagnostic
(`decision_candidate/corporate_action_stress.py`) calls the real, frozen
M061 `build_historical_backtest_run()` twice (once per dataset
interpretation) and compares -- directly mirroring M064's own
`CURRENT_UNIVERSE_BIAS_STRESS` pattern.

## 14. PostgreSQL Persistence (Additive Only)

Migration `c275f69cee79_create_m065_dataset_snapshot_schema.py`
(`down_revision = d9270168a7c7`, M064's own head). 4 new tables:

- `dataset_snapshot` (PK `(dataset_id, dataset_version)`)
- `dataset_snapshot_source_file` (FK CASCADE to `dataset_snapshot`)
- `corporate_action` (PK `(dataset_id, dataset_version, instrument_id,
  effective_timestamp, action_type)`; a CHECK constraint enforces that
  SPLIT/REVERSE_SPLIT rows carry non-null ratio fields and null symbol
  fields while SYMBOL_CHANGE rows carry the opposite; a `FOREIGN KEY
  (dataset_id, dataset_version) REFERENCES dataset_snapshot` -- added
  during hostile review, see the freeze document)
- `corporate_action_semantics_stress` (standard runtime_id PK /
  governance_id unique pattern, matching every prior milestone's
  diagnostic-result table shape)

No M020-M064 table is dropped, renamed, or altered.

## 15. Application Layer / CLI

Four new usecases (`import_historical_dataset_snapshot`,
`get_historical_dataset_snapshot`, `run_corporate_action_semantics_stress`,
`get_corporate_action_semantics_stress`) and four new CLI entrypoints,
registered as `empirical-platform-import-historical-dataset-snapshot`,
`empirical-platform-get-historical-dataset-snapshot`,
`empirical-platform-run-corporate-action-semantics-stress`,
`empirical-platform-get-corporate-action-semantics-stress`. The import
handler cross-validates that a supplied corporate-action manifest's own
declared `(dataset_id, dataset_version)` matches the dataset actually
being imported -- fails fast, before any persistence, rather than
silently attaching an unrelated manifest.

## 16. Acceptance Fixture

`tests/fixtures/m065_corporate_action_mechanics/`: 4 instruments (`ALFA`,
`BETA`, `GAMA`, `DELT`), 30 one-minute bars each (120 rows total), seeded
deterministic random-walk generation (`SEED=6065001`), one shared
corporate-action boundary at bar index 15
(`2024-03-01T09:45:00+00:00`):

- `BETA`: 2-for-1 `SPLIT`
- `GAMA`: 1-for-5 `REVERSE_SPLIT`
- `DELT`: `SYMBOL_CHANGE` from `OLDD` to `DELT`
- `ALFA`: no declared corporate action (control instrument)

The fixture was generated once, accepted as-is on the first attempt; no
bar or boundary was altered after observing results.

## 17. What M065 PROVES

- Dataset source reality is explicit (`CORPORATE_ACTION_MECHANICS_FIXTURE`,
  declared truthfully, never claimed as real)
- An immutable, versioned, hash-verified dataset snapshot authority exists
  and is enforced at both the application layer and the database layer
- Raw vs. adjusted price semantics are explicit and never silently mixed
- Supported corporate actions (SPLIT, REVERSE_SPLIT, SYMBOL_CHANGE) are
  applied deterministically, independently re-verified bar-for-bar
- Split math is independently re-derivable from raw source bytes without
  calling the production adjustment functions
- Symbol changes preserve stable `InstrumentId` identity
- Source-file and corporate-action-manifest tampering are detected via
  hash mismatch
- Backtests remain linked to the exact dataset version used
  (`HistoricalBacktestRun.dataset_sha256 ==
  DatasetSnapshotAuthority.normalized_sha256`)
- The `CORPORATE_ACTION_SEMANTICS_STRESS` comparator is genuinely capable
  of detecting divergence (independently demonstrated), not a decorative
  always-`IDENTICAL` no-op

## 18. What M065 DOES NOT PROVE

- Survivorship bias is not addressed by this milestone (that is M064's
  own, separate, already-frozen claim)
- No real market vendor data was used; no claim of market
  representativeness is made
- Dividend / total-return handling is not implemented
  (`DIVIDEND_TOTAL_RETURN_HANDLING_NOT_EXERCISED`, unconditional)
- No profitability claim
- No live-trading-readiness claim
- No broker or execution integration exists or is implied

## 19. Out of Scope

Real-vendor data licensing/integration; dividend/total-return accounting;
a generic multi-format ETL platform; a second backtesting engine; strategy,
ranking, risk, or position-sizing changes of any kind; live/broker
execution; network-dependent canonical acceptance; parameter optimization
or fixture cherry-picking.

## 20. Status

Design finalized and implemented in the same mission per the mission's
own reduced-ceremony, single-agent completion model. See the companion
`MACRO_MILESTONE_FREEZE.md` for implementation evidence, hostile review,
canonical validation, and the independent second pass.
