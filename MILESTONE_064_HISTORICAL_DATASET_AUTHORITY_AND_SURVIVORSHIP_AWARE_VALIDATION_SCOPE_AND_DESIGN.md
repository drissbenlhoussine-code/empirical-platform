# MILESTONE-064 - Historical Dataset Authority + Time-Varying Universe Membership + Survivorship-Aware Validation - Scope and Design

**Status: APPROVED_AND_FROZEN**

This document was originally produced as a candidate design (`CANDIDATE_INTERNAL_MACRO_SCOPE_AND_DESIGN`) by an assisting agent, then independently re-verified against live repository source, refined, implemented, hostile-reviewed, and frozen in a single Claude Code mission. Sections 9, 16, 21, and 30 below have been corrected to match the actual, tested, frozen implementation -- see `MILESTONE_064_HISTORICAL_DATASET_AUTHORITY_AND_SURVIVORSHIP_AWARE_VALIDATION_MACRO_MILESTONE_FREEZE.md` for full evidence and results.

This milestone answers the question M063 explicitly left open: after proving broader, windowed historical robustness across a fixed six-instrument synthetic universe, can the platform now make DATA AUTHORITY and HISTORICAL UNIVERSE MEMBERSHIP first-class, so that for every historical scoring cutoff the eligible instrument set is derived from effective-dated membership authority rather than assumed identical to the final surviving universe? The honest answer, confirmed by implementation: mechanics are proven, the bias is not eliminated, and no profitability, live-readiness, or survivorship-elimination claim is made.

## 1. Repository Authority

Repository `C:\Users\LuxSy\Documents\trading`, branch `master`. M064 baseline: `2927c3d24cdf4be2233e01975bc2d4a1de83cf87` (the M063 Owner Freeze hash-recording HEAD; M063 fully `APPROVED_AND_FROZEN`), independently re-verified at mission start. Working tree clean.

## 2. Starting Limitation Acknowledged

M063 explicitly persists the constant:

```
SURVIVORSHIP_BIAS_NOT_ADDRESSED
```

because the M063 robustness study evaluates the same six canonical constituents (`AAPL, AMZN, GOOG, MSFT, NVDA, TSLA`) at every historical cutoff. M064 must replace that constant with something defensible while still refusing to overclaim.

## 3. Fresh Inventory - What Already Exists in the Live Repository

Verified by direct read of source and governance on `master` at mission start.

| Concept | Status | Evidence |
| --- | --- | --- |
| `Instrument` value object | IMPLEMENTED - bare ticker `^[A-Z]{1,5}$` only | `src/empirical_platform/decision_candidate/market_data.py:18-46` |
| `Bar` / `ObservationWindow` | IMPLEMENTED - per-instrument OHLCV | `src/empirical_platform/decision_candidate/market_data.py:48-141` |
| Universe authority as a fixed-synthetic bundle | IMPLEMENTED - M063 first-class | `src/empirical_platform/decision_candidate/robustness_study.py:154-205` |
| `universe_membership_model = "FIXED_SYNTHETIC_UNIVERSE"` | IMPLEMENTED - persisted constant | `src/empirical_platform/decision_candidate/robustness_study.py:328-388` and the M063 schema |
| `survivorship_bias_disclosure` field | IMPLEMENTED - currently `SURVIVORSHIP_BIAS_NOT_ADDRESSED` | `src/empirical_platform/shared/persistence/postgres_repositories/robustness_study_repository.py:109, 292` |
| Instrument Master (stable cross-time identity) | ABSENT | no module |
| Symbol history (ticker rename tracking) | ABSENT | no module |
| Effective-dated universe membership records | ABSENT | no module |
| Universe-at-cutoff derivation | ABSENT | no module |
| Membership manifest / hash | ABSENT | no module |
| Listing / delisting model | ABSENT | no module |
| Survivorship-aware robustness study integration | ABSENT | no module |
| CURRENT_UNIVERSE_BIAS_STRESS diagnostic | ABSENT | no module |
| Real historical membership authority data | ABSENT locally | no committed dataset |
| Corporate action handling (splits, dividends, symbol changes) | PLACEHOLDER only (declared out of scope in M057-M063) | M057 scope and design |

This inventory prevents reinventing infrastructure that already exists. M064 is incremental: it adds the membership and time-varying universe layer on top of the existing fixed-synthetic-universe M063 stack, without modifying the frozen execution path.

## 4. Data-Source Honesty

M064 has no real historical membership authority available locally. The committed M063 fixture is synthetic, deterministic, and vendor-neutral; it carries six canonical constituents with no membership history.

Therefore the canonical M064 fixture must be declared as:

```
source_kind = SURVIVORSHIP_AWARE_MECHANICS_FIXTURE
```

with all membership dates explicitly synthetic and documented as such. M064 does NOT fabricate historical provenance. If a real licensed historical dataset with effective-dated membership metadata becomes locally available later and licensing permits repository use, a future M06x milestone may adopt it and reclassify; M064 does not wait for that and does not require it for acceptance.

## 5. Frozen Stack Reuse (No Mutation)

M064 reuses the M020-M063 frozen stack. No source mutation of:

- `decision_candidate/market_data.py` `Instrument` / `Bar` / `ObservationWindow`
- `decision_candidate/strategy.py`
- `decision_candidate/ranking.py`
- `decision_candidate/trade_plan.py`
- `decision_candidate/position_plan.py`
- `decision_candidate/historical_backtest.py`
- `decision_candidate/robustness_study.py` (only additive extensions; the existing `constituents` / `universe_membership_model` semantics stay)
- Any Campaign/Run/EvidencePackage/Review/DecisionCandidate lifecycle
- Any M020-M063 schema, migration, or repository adapter
- Any M020-M063 frozen command/query handler
- `tools/check_architecture.py`

M064 introduces a new module tree (`decision_candidate/dataset_authority.py`, `decision_candidate/instrument_master.py`, `decision_candidate/universe_authority.py`, `decision_candidate/membership.py`, `decision_candidate/historical_universe.py`, `decision_candidate/survivorship_study.py`) and one new migration, and the M063 robustness-study output is extended ADDITIVELY with per-window universe snapshots and survivorship classification - never by removing or changing the existing M063 fields.

## 6. Product Objective

At every historical scoring cutoff `T`, the platform must answer:

> Which instruments were legitimately eligible for evaluation, according to the dataset/universe authority that existed for that period?

The answer must be derived from immutable effective-dated membership authority, must be deterministic, must be tamper-detectable, and must be persisted per-window in the robustness-study output.

## 7. Capability Selection (Single Selected)

**Selected:**

> Build first-class: (a) Historical Dataset Authority, (b) stable Instrument Identity, (c) Universe Authority, (d) effective-dated Membership Authority, (e) deterministic `universe_at(cutoff)` derivation, (f) per-window universe snapshots in the persisted robustness study, (g) `CURRENT_UNIVERSE_BIAS_STRESS` diagnostic, (h) PostgreSQL persistence of all the above, (i) real CLI acceptance, (j) a fixed synthetic survivorship-aware mechanics fixture.

## 8. Rejected Candidates (Honest Rejection)

| Candidate | Disposition | Reason |
| --- | --- | --- |
| Replace `Instrument` with a global cross-tenant security master | REJECTED | Scope creep; not required for one-platform mechanics proof. |
| Require real licensed historical membership data | REJECTED | Not locally available; would block M064 indefinitely. |
| Eliminate survivorship bias entirely | REJECTED | Not defensible from a synthetic fixture; would overclaim. |
| Refactor M057-M063 frozen strategy/risk/sizing/execution path | REJECTED | Forbidden by scope discipline and by the M020+ freeze contract. |
| Add portfolio / broker / live execution | REJECTED | Out of platform scope; out of M064 scope. |
| Tune parameters against historical fixture to improve PnL | REJECTED | Forbidden by the M020+ optimization prohibition. |
| Add HTTP API | REJECTED | Not required; CLI acceptance is sufficient. |
| Mix adjusted and unadjusted price semantics silently | REJECTED | M064 declares `CORPORATE_ACTION_HANDLING_NOT_EXERCISED` explicitly when fixture does not exercise it. |
| Build a generic data-management platform | REJECTED | Out of scope; M064 ships only the operations M064 consumes. |
| Continue using M063's fixed-constituent semantics without adding the membership layer | REJECTED | Would not address the survivorship limitation. |

## 9. Module Placement (Architecture Compliance) -- AS BUILT

All new modules live under `decision_candidate/`, exactly five (no separate
`dataset_authority.py`: the frozen M063 `RobustnessDatasetBundleAuthority`
and `RobustnessUniverseAuthority` already cover dataset/universe identity
and are reused verbatim -- adding a parallel dataset-authority module would
have duplicated, not extended, frozen M063 concepts):

- `decision_candidate/instrument_master.py` - `InstrumentId`, `InstrumentType`, `InstrumentMasterEntry`, `InstrumentMaster`, `InstrumentMasterRepository` Protocol
- `decision_candidate/universe_authority.py` - `UniverseAuthority` (bare `universe_id`/`universe_version`/`source_kind` identity)
- `decision_candidate/membership.py` - `MembershipStatus`, `MembershipRecord`, `MembershipManifest`, `membership_manifest_hash()`, `UniverseMembershipRepository` Protocol
- `decision_candidate/historical_universe.py` - `universe_at(manifest, cutoff)`, the sole production eligibility-derivation function
- `decision_candidate/survivorship_study.py` - `SurvivorshipAwareRobustnessStudy`, `WindowUniverseSnapshot`, `CurrentUniverseBiasStressResult`, `build_survivorship_aware_robustness_study()`
- `decision_candidate/survivorship_study_repository.py` - `SurvivorshipAwareRobustnessStudyRepository` Protocol

Architecture-checker changes were NOT required and none were made. The
checker continues to forbid `decision_candidate -> sqlalchemy` / `psycopg` /
`boto3` / `shared.persistence` imports (verified: `tools/check_architecture.py`
exits 0 against the final M064 delta); new PostgreSQL persistence lives in
`shared/persistence/postgres_repositories/survivorship_study_repository.py`
only, with the same runtime wiring pattern M020-M063 already use.

## 10. Instrument Identity (Minimum Stable Concept)

A new value object `InstrumentId` will be added with the following invariants:

- `instrument_id: str` - non-empty opaque stable identifier (e.g. `INSTR-AAPL-001`)
- `canonical_symbol: str` - matches M063 `^[A-Z]{1,5}$`
- `instrument_type: str` - currently only `EQUITY` / `ETF` permitted
- `exchange_or_venue: str | None` - optional, never empty when set
- `external_identifier: str | None` - optional

`Instrument` (the existing M063 ticker value object) remains unchanged. `InstrumentId` is an additional stable-identity layer that membership records key on. This satisfies the "stable identity sufficient for historical membership" requirement without overbuilding a global security master.

## 11. Effective-Dated Membership

`MembershipRecord` fields:

- `universe_id: str`
- `universe_version: str`
- `instrument_id: InstrumentId`
- `effective_from: datetime` (timezone-aware)
- `effective_to: datetime | None` (`None` = open-ended)
- `membership_status: str` - only `ACTIVE` / `INACTIVE` / `DELISTED_LIKE` / `INACTIVE_LIKE`
- `source_kind: str` - currently only `SURVIVORSHIP_AWARE_MECHANICS_FIXTURE`

Boundary semantics:

- `effective_from` is **inclusive**
- `effective_to` is **exclusive**
- Eligibility at cutoff `T` requires `effective_from <= T < effective_to` (or `effective_to is None`)

Rejection rules:

- inverted intervals (`effective_to < effective_from`)
- duplicate records with same `(universe_id, universe_version, instrument_id, effective_from)`
- overlapping intervals for the same `(universe_id, universe_version, instrument_id)` unless the second is a status transition
- unknown `InstrumentId` against the master
- empty membership manifest for a non-empty universe
- membership record referring to a `universe_id` that does not exist in the master

## 12. Universe-At-Cutoff Derivation

```
universe_at(universe_authority, membership_authority, cutoff) -> tuple[InstrumentId, ...]
```

Properties:

- deterministic given the same three inputs
- sorted canonically (lexicographic by `instrument_id`)
- input record order must not matter
- rejected inputs produce deterministic `ValueError` with stable messages

A separate, production-isolated `independent_universe_at(...)` verifier module derives the same set without calling `universe_at()`. Both must produce the same canonical ordered set for every test cutoff. This is the **independent membership derivation** the M064 mission calls out.

## 13. Membership Manifest Hash

A canonical JSON representation of all membership records for one `(universe_id, universe_version)` is built by:

1. rejecting duplicates
2. sorting records by `(instrument_id, effective_from)`
3. serializing with stable field order
4. SHA-256 hashing the UTF-8 bytes

Same semantic membership in different input order produces the same hash. Modified membership produces a different hash. Tampered declared hash (recorded hash disagrees with computed hash) fails trusted execution before any persistence or study construction.

## 14. M063 Integration (Additive, No Mutation)

M064 extends the M063 robustness-study persistence with:

- per-window: `universe_authority_id`, `universe_authority_version`, `membership_authority_version`, `membership_manifest_hash`, `eligible_instrument_ids: tuple[InstrumentId, ...]`, `evaluated_instrument_ids: tuple[InstrumentId, ...]`, `missing_data_excluded_instrument_ids: tuple[InstrumentId, ...]`
- study-level: `survivorship_classification: str` (replacing the current constant)
- study-level: `current_universe_bias_stress: StressResult | None` when the diagnostic is run

The existing M063 fields and the M063 dataset bundle / universe authority are never deleted or rewritten. M064 adds new columns, new code paths, and a new fixture.

## 15. Current-Universe Bias Diagnostic

`CURRENT_UNIVERSE_BIAS_STRESS` is a diagnostic-only parallel study. Given the same window manifest and the same dataset bundle, the diagnostic forces the **final** universe (the one declared in the M063 universe authority) across all historical windows, regardless of membership facts at each cutoff. The output reports:

- per-window eligible count (canonical vs stress)
- per-window evaluated count (canonical vs stress)
- total executed trades (canonical vs stress)
- net PnL total (canonical vs stress)
- total R total (canonical vs stress)
- best/worst window by net PnL and total R (canonical vs stress)

The stress result is **not** a canonical alternative result. It is a diagnostic, and its classification vocabulary explicitly forbids `PROFITABLE` / `PROVEN_EDGE` / `LIVE_READY` / `BIAS_ELIMINATED`. If the two results are identical, the report says so honestly. If they differ, the report says so honestly. The data is not altered to force a difference.

**As built**: `CURRENT_UNIVERSE_BIAS_STRESS` is implemented as a direct, unmodified second call to the real, frozen M063 `build_robustness_study()` against the identical dataset bundle -- M063's own function *always* evaluates the bundle's full declared universe every window, which is exactly "force the final/current universe backward across all windows." No second stress engine was written. The resulting `HistoricalRobustnessStudy` is persisted through the unmodified M063 `robustness_study` repository (not duplicated into a new table) and referenced by governance ID from the M064 study record, alongside a small descriptive comparison (`CurrentUniverseBiasStressResult`). On the canonical fixture this produced a genuine, un-massaged difference: 35 canonical executed trades vs. 59 stress-forced executed trades (`CURRENT_UNIVERSE_BIAS_STRESS_DIFFERS`).

## 16. Conservative Classification Vocabulary -- AS BUILT

Allowed (closed, two-value enum; the candidate document's proposed
`HISTORICAL_MEMBERSHIP_EVIDENCE_RECORDED` value was removed since M064 has
no real historical membership authority and would never produce it --
keeping an unreachable classification value would be dead, untested code):

- `INSUFFICIENT_SAMPLE` (mirrors M063's own sample-size floor: `total_executed_trade_count < 15`)
- `SURVIVORSHIP_AWARE_MEMBERSHIP_MECHANICS_PROVEN`

Forbidden (must never appear in any M064 persisted field, CLI output, doc claim, or comment):

- `SURVIVORSHIP_BIAS_ELIMINATED`
- `MARKET_REPRESENTATIVE`
- `REAL_HISTORICAL_UNIVERSE`
- `PROFITABLE`
- `PROVEN_EDGE`
- `LIVE_READY`

The synthetic canonical fixture must produce `SURVIVORSHIP_AWARE_MEMBERSHIP_MECHANICS_PROVEN`.

## 17. Corporate-Action Limitation

The M057-M063 fixture does not exercise stock splits, dividends, or symbol changes. M064 declares:

```
CORPORATE_ACTION_HANDLING_NOT_EXERCISED
```

This is a single persisted constant. If a future M06x adopts a real dataset, the constant becomes a reclassification, not a silent semantic shift. Adjusted-vs-unadjusted price mixing is explicitly forbidden.

## 18. Future-Membership Firewall (Mandatory)

- Modifying a membership record whose `effective_from` is strictly after a window's scoring cutoff MUST NOT change that window's eligible set, decisions, trades, or metrics.
- Removing a future membership record (one whose `effective_from` is after a window's cutoff) MUST NOT retroactively exclude any earlier-window eligibility.
- Modifying a membership record whose `effective_to` is at or before a window's scoring cutoff MUST NOT include that instrument in any window whose cutoff is at or after `effective_to`.

These three rules are formalized as automated tests against `universe_at()` AND against the full persisted study. The mission calls this "later entrant cannot appear early" / "future exit cannot retroactively remove historical eligibility".

**Granularity limitation (documented, not hidden)**: eligibility is derived ONCE per window, at that window's own `scoring_start_timestamp` -- not re-evaluated at every individual decision cutoff inside the window. `build_historical_backtest_run()` (M061, frozen) processes one fixed instrument set across all of its own internal cutoffs; changing the instrument set mid-run would require modifying that frozen function, which is forbidden. This is the finest granularity achievable without touching the frozen M061 engine, and is stated explicitly here and in the final report rather than silently assumed.

## 19. Bar Look-Ahead Firewall (Preserved from M057-M063)

M064 does not weaken M057-M063 temporal protections. Membership authority adds another firewall on top, not a replacement for it. Historical cutoff `T` may use:

- membership facts effective at `T`
- market data available at or before `T` for decision construction

Never future membership, never future market bars. The persisted window result continues to carry `scoring_start_timestamp` / `scoring_end_timestamp` and M063 reference-window semantics are untouched.

## 20. Universe-Exit vs Position-Exit Distinction

Universe membership controls NEW eligibility only. If an instrument leaves the universe after a hypothetical position was already entered:

- the existing frozen execution path continues to behave as it did at entry
- the universe-eligibility derivation no longer returns that instrument for new cutoffs
- no fabricated liquidation event is produced
- no portfolio / broker engine is added

This separation is documented in code comments and is verified by a focused test that constructs a window containing a would-have-been-entered instrument, then mutates the membership so the instrument is no longer eligible for a LATER window, and confirms the earlier window's metrics are unchanged.

## 21. PostgreSQL Persistence (Minimal Migration) -- AS BUILT

One new Alembic migration (`d9270168a7c7_create_m064_survivorship_study_schema.py`, `down_revision = 63e46fdef1c7`) adds five tables:

- `instrument_master` (small reference table, PK `instrument_id`, unique `canonical_symbol`)
- `universe_authority` (PK `(universe_id, universe_version)`)
- `membership_record` (PK `(universe_id, universe_version, instrument_id, effective_from)`, FKs to `universe_authority` and `instrument_master`)
- `survivorship_study` (root: dataset/universe/membership authority, frozen-policy identity fields, cross-window aggregate metrics, and the embedded `CURRENT_UNIVERSE_BIAS_STRESS` comparison summary including a FK to `robustness_study.governance_id`)
- `survivorship_window` (N child rows per study: `eligible_instrument_ids` / `evaluated_instrument_ids` / `missing_data_excluded_instrument_ids` as `TEXT[]`, nullable FK to `historical_backtest_run` since a zero-eligible window has no M061 run to reference)

The migration is additive only -- verified via `git diff --stat` against the M063 freeze baseline (`2927c3d`): zero deletions across every frozen M020-M063 file. Migration upgrade/downgrade/upgrade round-trip verified clean against two independent PostgreSQL containers. The pattern follows the M063 migration shape (`63e46fdef1c7_create_m063_robustness_study_schema.py`), including its shadow-table-declaration convention for cross-migration FK resolution.

## 22. CLI Acceptance (Real Subprocess)

Two production CLI entrypoints:

- `run-survivorship-aware-robustness-study`
- `get-survivorship-aware-robustness-study`

Both register in `pyproject.toml` console scripts. Both are exercised through `subprocess.run([sys.executable, "-m", "empirical_platform.entrypoints.<name>", ...])` in tests, not just in-process. The output is the persisted study plus the bias-stress diagnostic.

## 23. Test Surface

Required:

- `tests/unit/test_instrument_master.py`
- `tests/unit/test_membership.py`
- `tests/unit/test_membership_manifest_hash.py`
- `tests/unit/test_universe_at_cutoff.py`
- `tests/unit/test_independent_universe_derivation.py`
- `tests/unit/test_survivorship_study.py`
- `tests/unit/test_current_universe_bias_stress.py`
- `tests/integration/test_postgres_survivorship_study.py`
- `tests/architecture/test_module_boundaries.py` (additive assertions for new modules)

Required attack tests (50 cases):

- empty instrument master
- duplicate instrument
- unknown instrument
- empty universe
- duplicate universe version
- no membership records
- duplicate membership
- overlapping intervals
- inverted interval
- exact `effective_from` boundary
- exact `effective_to` boundary
- before-join
- after-exit
- membership input order
- membership hash determinism
- membership tamper
- dataset tamper
- dataset/membership mismatch
- bars for unknown instrument
- eligible instrument missing data
- late entrant appearing early
- exited member removed retroactively
- future membership leakage
- future market-data leakage
- all instruments inactive
- one active instrument
- changing universe size
- current-universe stress
- deterministic replay
- multiple universes coexist
- multiple dataset versions coexist
- PostgreSQL round trip
- raw SQL equality
- CLI subprocess
- M063 semantics preserved
- regime semantics preserved
- no strategy mutation
- no parameter optimization
- no cherry-picking
- survivorship overclaim
- market-wide overclaim
- sample-size overclaim
- profitability overclaim
- corporate-action overclaim
- LLM dependency
- network dependency
- broker / live execution
- architecture / frozen predecessor violation
- evidence inconsistency

Each result is recorded as `PASS` / `FIXED` / `N/A WITH REASON`.

## 24. Fixture - Survivorship-Aware Mechanics Fixture

`tests/fixtures/m064_survivorship_aware/`:

- six canonical instruments (reusing the M063 six: `AAPL, AMZN, GOOG, MSFT, NVDA, TSLA`) with stable `InstrumentId`s
- membership manifest with deliberately time-varying eligibility:
  - `INSTR-AAPL-001` present throughout
  - `INSTR-AMZN-001` joins after `T0` (later entrant)
  - `INSTR-GOOG-001` present throughout but exits before the final window (early exit)
  - `INSTR-MSFT-001` joins after `T0`, exits before the final window (middle-period member)
  - `INSTR-NVDA-001` present throughout (surviving final member)
  - `INSTR-TSLA-001` marked `INACTIVE_LIKE` from `T1` onward (inactive / delisted-like historical member)
- 10 windows, reusing the M063 `W01..W10` timing where practical
- declared source kind: `SURVIVORSHIP_AWARE_MECHANICS_FIXTURE`
- declared `CORPORATE_ACTION_HANDLING_NOT_EXERCISED`
- declared `membership_manifest_hash` (computed)
- declared `dataset_bundle_sha256` (computed)

Historical bars for `INSTR-TSLA-001` MUST remain available for any window where it is eligible, even though it is later marked `INACTIVE_LIKE`. This proves the no-bar-deletion-for-inactive-names rule.

## 25. What M064 PROVES

- dataset authority is explicit, hashed, and tamper-detectable
- instrument identity is stable enough to key historical membership
- universe membership is effective-dated
- changing historical membership changes historical eligibility
- later entrants cannot appear early
- exited / inactive historical members remain available historically
- future membership cannot alter earlier windows
- membership authority is hashed and tamper-detectable
- `universe_at(cutoff)` is deterministic
- M063 robustness semantics are reused (not rewritten)
- `CURRENT_UNIVERSE_BIAS_STRESS` can be run and reported honestly
- survivorship claims remain conservative

## 26. What M064 DOES NOT PROVE

- M064 does NOT eliminate survivorship bias.
- M064 does NOT prove profitability.
- M064 does NOT prove live-readiness.
- M064 does NOT prove the synthetic fixture is a real market.
- M064 does NOT prove corporate actions are handled (they are declared NOT_EXERCISED).
- M064 does NOT prove current-universe bias is a major contributor in real markets (it diagnoses mechanics, not magnitude).
- M064 does NOT add a portfolio / broker / live execution engine.
- M064 does NOT tune parameters.
- M064 does NOT use LLM, network, or third-party data sources.

## 27. In Scope (this milestone)

- scope-and-design doc (this file)
- implementation commit
- design freeze doc
- owner-freeze hash-recording commit
- new module tree under `decision_candidate/`
- one new Alembic migration
- one new survivorship-aware-mechanics fixture
- focused unit tests + integration tests + architecture-checker additive assertions
- production CLI registration and CLI acceptance
- per-window universe snapshot persistence
- independent `universe_at()` verifier module
- bias-stress diagnostic
- raw SQL verification
- final review package
- M020-M063 regression remains green

## 28. Out of Scope (this milestone)

- any real historical market data acquisition or licensing
- any HTTP API
- any LLM dependency
- any portfolio / broker / live execution
- any parameter tuning / search / optimization
- any change to the M020-M063 frozen execution path
- any M065 / M06x planning beyond a single recommendation paragraph in the final report

## 29. M065 Boundary

This document does not select any M065 capability, terminology, or sequencing decision. A single recommendation paragraph in the final report is permitted; no M065 implementation begins.

## 30. Resolved Design Decisions

All ten questions the candidate document deferred were resolved before implementation began, using the smallest architecture-consistent choice in each case:

1. **`InstrumentId` format**: `INSTR-{SYMBOL}-{NNN}`, e.g. `INSTR-AAPL-001` -- implemented as its own value object (`instrument_master.py`), not a subclass of the generic `Identifier` base, since that base's pattern (`PREFIX-\d{4}`) cannot embed a ticker symbol.
2. **Instrument master row shape**: one row per `instrument_id` for the lifetime of this milestone's fixture -- no symbol-rename / re-identification history (out of scope; declared via `CORPORATE_ACTION_HANDLING_NOT_EXERCISED`).
3. **`INACTIVE_LIKE` vs `DELISTED_LIKE`**: kept as two separate, honest historical labels in the closed `MembershipStatus` vocabulary. Behaviorally identical for eligibility purposes (only `ACTIVE` records contribute eligibility in `universe_at()`); the distinction is descriptive only.
4. **Bias-stress persistence**: computed and persisted by default on every canonical run, never opt-in -- required for Phase 37 canonical-acceptance evidence.
5. **`universe_at()` return type**: a canonically sorted (lexicographic by `instrument_id` string) tuple of `InstrumentId`.
6. **Migration column shape**: normalized columns throughout (matches every prior M057-M063 migration); `TEXT[]` arrays used only for the three per-window instrument-ID list columns (`eligible_instrument_ids` / `evaluated_instrument_ids` / `missing_data_excluded_instrument_ids`), mirroring M063's own `instrument_universe TEXT[]` precedent -- never `JSONB`.
7. **M063 schema mutation**: none. `survivorship_study` / `survivorship_window` are new, parallel tables, referencing the frozen M061 `historical_backtest_run` table (per canonical window) and the frozen M063 `robustness_study` table (for the bias-stress diagnostic) by governance ID -- zero columns added to any M063 table.
8. **Bias-stress window sharing**: the diagnostic shares the exact same window manifest (`RobustnessDatasetBundle.window_specs`) as the canonical study -- window boundaries are a data/time construct independent of membership, so there was no reason to generate a second manifest.
9. **Fixture bars**: the M064 canonical fixture reuses the M063 fixture's own bar data byte-for-byte (`tests/fixtures/m063_robustness_study/synthetic_broad_robustness_dataset_bundle.json`'s `instruments` array, unmodified) -- only `dataset_bundle_id`, `source_kind`, and `universe_membership_model` were changed, plus the new membership manifest layered on top. This avoids any suspicion of price-behavior tuning to produce a desired result.
10. **CLI output**: JSON only to stdout, matching the M057-M063 CLI convention exactly (`print(json.dumps(payload, sort_keys=True))`); no human-summary mode was added since none of the five prior milestones' CLIs have one either.

An eleventh, unanticipated design question emerged during implementation and is recorded here for completeness: **eligibility granularity**. Since `build_historical_backtest_run()` (M061, frozen) processes one fixed instrument set across all of its own internal per-cutoff decisions, and modifying it is forbidden, eligibility is derived once per window (at that window's own `scoring_start_timestamp`), not once per individual decision cutoff inside the window. This is documented as a limitation in Section 18 and in the final report, not silently assumed.

## 31. Status

**APPROVED_AND_FROZEN.**

Implemented, tested (unit + PostgreSQL integration + real CLI subprocess, two independent PostgreSQL containers), hostile-reviewed, and frozen in one end-to-end Claude Code mission. See `MILESTONE_064_HISTORICAL_DATASET_AUTHORITY_AND_SURVIVORSHIP_AWARE_VALIDATION_MACRO_MILESTONE_FREEZE.md` for the full freeze record, evidence, and commit hashes. M065 not started.
