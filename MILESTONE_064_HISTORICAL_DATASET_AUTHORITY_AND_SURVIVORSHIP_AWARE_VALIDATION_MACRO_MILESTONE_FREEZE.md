# MILESTONE-064 - Historical Dataset Authority + Time-Varying Universe Membership + Survivorship-Aware Validation - Macro Milestone Freeze

## Status: FINAL - OWNER FROZEN

## Repository Authority

Repository `C:\Users\LuxSy\Documents\trading`, branch `master`. M064 baseline `2927c3d24cdf4be2233e01975bc2d4a1de83cf87` (the M063 Owner Freeze hash-recording HEAD; M063 fully `APPROVED_AND_FROZEN`), independently re-verified at mission start (`git fetch`, `git status`, `git rev-parse HEAD`/`origin/master` all agreed, working tree clean except one untracked MiniMax design candidate document). Implementation commit `12a77a2`.

## Delivered Capability

Before this milestone, the M063 broad historical robustness study assumed one fixed surviving universe (all six canonical constituents) applied identically to every historical window -- `universe_membership_model = FIXED_SYNTHETIC_UNIVERSE`. After this milestone, a real caller can present a fixed instrument-master, a fixed effective-dated membership manifest (with SHA-256 tamper detection), and the same M063-shaped dataset bundle to `run_survivorship_aware_robustness_study`, and receive a persisted `SurvivorshipAwareRobustnessStudy` in which each window's evaluated instrument set is derived deterministically from historical membership authority as it existed at that window's own cutoff -- never from the final/current universe. A `CURRENT_UNIVERSE_BIAS_STRESS` diagnostic (the real, unmodified M063 `build_robustness_study()`, called a second time against the identical bundle) is computed and persisted alongside every canonical run, so the platform can honestly report how much the membership-gating changed the result. No profitability, live-readiness, or survivorship-bias-elimination claim is made; the persisted `survivorship_aware_membership_mechanics_proven` classification says exactly what was proven and nothing more.

## MiniMax Design-Candidate Disposition

The untracked candidate document (`MILESTONE_064_..._SCOPE_AND_DESIGN.md`) was read in full and independently re-verified against live source before any implementation began. Disposition of its major claims:

- **ACCEPT**: repository-truth baseline hash; the "ABSENT" inventory (instrument master, membership records, `universe_at()`, membership hash, `CURRENT_UNIVERSE_BIAS_STRESS` -- confirmed genuinely absent via grep); frozen-stack reuse constraints; module placement under `decision_candidate/`; effective-dated `[effective_from, effective_to)` half-open interval semantics; the future-membership firewall requirement; the universe-exit-vs-position-exit distinction; the conservative classification vocabulary (minus one unreachable value, see below); `CORPORATE_ACTION_HANDLING_NOT_EXERCISED`; the survivorship-aware mechanics fixture design (six instruments, later entrant, early exit, middle-period member, always-present survivor, inactive/delisted-like historical member).
- **CORRECT**: the "Universe authority as a fixed-synthetic bundle" inventory row understated what M063 actually already ships -- live source showed `RobustnessUniverseAuthority` (with `universe_id`/`universe_version`/`membership_model`/`constituents`) already exists as first-class M063 output, not merely "a bundle." M064 reuses this type directly rather than reinventing it. The proposed sixth module `dataset_authority.py` was removed (Section 9 above) since M063's own `RobustnessDatasetBundleAuthority` already covers dataset identity/hash/coverage and a parallel module would have duplicated it. The proposed `HISTORICAL_MEMBERSHIP_EVIDENCE_RECORDED` classification value was removed as unreachable dead code (M064 has no real historical authority and would never produce it).
- **REMOVE**: none of the candidate's REJECTED-candidates table required revision; all ten rejections (global security master, real licensed data requirement, bias-elimination claim, frozen-stack refactor, broker/live execution, parameter tuning, HTTP API, adjusted/unadjusted price mixing, generic data-management platform, fixed-constituent status quo) were independently re-confirmed as correctly out of scope.

No M064 work was restarted merely because a different agent authored the initial design; the candidate was refined and implemented in place.

## Resolved Design Decisions

All ten questions the candidate document deferred were resolved before implementation began (recorded in full in the finalized `SCOPE_AND_DESIGN.md` Section 30): `InstrumentId` format `INSTR-{SYMBOL}-{NNN}`; one instrument-master row per `instrument_id`; `INACTIVE_LIKE`/`DELISTED_LIKE` kept separate as descriptive-only labels; bias-stress persisted by default; `universe_at()` returns a canonically sorted `InstrumentId` tuple; normalized migration columns (`TEXT[]` only for the three per-window instrument-ID list columns, mirroring M063's own `instrument_universe TEXT[]` precedent); zero M063 schema mutation (parallel tables only); bias-stress shares the canonical window manifest; the canonical fixture reuses M063's own bar data byte-for-byte; CLI output is JSON-only, matching every prior milestone. An eleventh, unanticipated question (eligibility granularity: once per window, not once per decision cutoff, since the frozen M061 engine processes one fixed instrument set per run) was identified during implementation and is documented as an explicit, honest limitation rather than a silent assumption.

## Implementation Evidence

New domain and repository surface (5 new `decision_candidate/` modules, 1 new migration, 1 new concrete Postgres repository module, 2 new usecases, 2 new CLI entrypoints, 1 new identifier type):

- `decision_candidate/instrument_master.py`, `universe_authority.py`, `membership.py`, `historical_universe.py`, `survivorship_study.py`, `survivorship_study_repository.py`
- migration `d9270168a7c7_create_m064_survivorship_study_schema.py` (`down_revision = 63e46fdef1c7`) -- 5 tables: `instrument_master`, `universe_authority`, `membership_record`, `survivorship_study`, `survivorship_window`
- `PostgresSurvivorshipAwareRobustnessStudyRepository`, `PostgresInstrumentMasterRepository`, `PostgresUniverseMembershipRepository`
- runtime wiring in `postgres_repositories/runtime.py` (`.survivorship_studies` / `.instrument_masters` / `.universe_memberships` properties)
- `usecases/run_survivorship_aware_robustness_study.py`, `get_survivorship_aware_robustness_study.py`, `survivorship_study_io.py`
- `entrypoints/run_survivorship_aware_robustness_study.py`, `get_survivorship_aware_robustness_study.py`
- new `SurvivorshipStudyId` identifier (prefix `SURV`)
- CLI registration in `pyproject.toml` (`empirical-platform-run-survivorship-aware-robustness-study`, `empirical-platform-get-survivorship-aware-robustness-study`)

Purely additive: `git diff --stat 2927c3d -- <every frozen M057-M063 decision_candidate/usecases/entrypoints file + tools/check_architecture.py>` returned zero output. Only 4 tracked files were modified (`pyproject.toml`, `decision_candidate/__init__.py`, `identifiers/types.py`, `postgres_repositories/runtime.py`), and each of those 4 diffs is 0 deletions / N insertions only.

The canonical fixture (`tests/fixtures/m064_survivorship_aware/`) reuses the M063 fixture's own bar data byte-for-byte, relabeled with `source_kind = SURVIVORSHIP_AWARE_MECHANICS_FIXTURE` and `universe_membership_model = HISTORICAL_MEMBERSHIP`:

- dataset bundle `DATASET-6401` version `1`, SHA-256 `af996c094538abcc34356357db1ea74ad675b3bcff10a7ea759ae86a4ee073ff`
- universe `UNIVERSE-6401` version `1`
- membership manifest hash `caa9fa899ea26816101a0a494c4977fed75849d4ac19b65ac6410e561f232fda`
- 6 instruments (`AAPL, AMZN, GOOG, MSFT, NVDA, TSLA`), 10 windows, 7 membership records

Designed membership timeline: `AAPL`/`NVDA` present throughout (always-present + surviving final member); `AMZN` joins exactly at W03's own scoring-cutoff (later entrant); `GOOG` present from inception, exits exactly at W06's own cutoff (early exit); `MSFT` joins at W02's cutoff, exits at W08's cutoff (middle-period member); `TSLA` present from inception, becomes `INACTIVE_LIKE` exactly at W05's cutoff (inactive/delisted-like historical member -- bars remain in the dataset for every window, proven by direct test assertion).

## Canonical Results

Canonical study result over the committed fixture (`account_equity = 100000`, `risk_percent = 0.01`), reproduced identically via real installed-CLI subprocess against two independent PostgreSQL containers:

- classification `SURVIVORSHIP_AWARE_MEMBERSHIP_MECHANICS_PROVEN`
- `window_count = 10`
- `total_evaluated_cutoff_count = 80`
- `total_executed_trade_count = 35`
- `positive_net_pnl_window_count = 6`, `negative_net_pnl_window_count = 4`
- `median_window_net_pnl = 214.631855`
- `median_window_total_r = 2.206382809025329073444550589`
- best net-PnL window `W02 / 527.43199400`; worst net-PnL window `W07 / -416.895490`
- best total-R window `W02 / 6.557392735176808210516075685`; worst total-R window `W06 / -5.641665453527435610302351623`
- all-window net PnL `1516.02221780`; all-window total R `15.60916029901257197054340861`
- excluding-best-window net PnL `988.59022380`; excluding-best-window total R `9.051767563835763760027332925`
- largest positive-window share of positive PnL `0.2413221378477775484469920661`
- largest negative-window share of absolute negative PnL `0.6226308743483848744552592985`

Eligible-instrument count per window, in `sequence_index` order: `4, 5, 6, 6, 5, 4, 4, 3, 3, 3` -- a genuine, honest, monotonic-leaning decline driven entirely by the designed membership timeline, not by any tuning of trade outcomes.

## CURRENT_UNIVERSE_BIAS_STRESS Diagnostic

- `stress_study_id = ROBUST-6402` (a genuine, separately persisted M063 `HistoricalRobustnessStudy`, retrievable through the unmodified M063 `get-historical-robustness-study` CLI)
- `comparison = CURRENT_UNIVERSE_BIAS_STRESS_DIFFERS`
- canonical vs. stress `total_executed_trade_count`: `35` vs. `59`
- canonical vs. stress `all_window_net_pnl_total`: `1516.02221780` vs. `3159.55176410`
- canonical vs. stress `all_window_total_r_total`: `15.60916029901257197054340861` vs. `33.84096575766330478385285292`

The stress diagnostic is literally the real, frozen M063 `build_robustness_study()`, called a second time against the identical dataset bundle -- no second "stress engine" was written. Membership-gating a materially smaller instrument set into most windows genuinely reduced the trade count and total PnL on this fixture; this is reported honestly and is not evidence of a "better" or "worse" strategy, only evidence that the choice of eligible universe materially affects the result on this dataset.

## Future-Membership Firewall Evidence

Two independent forms of attack evidence:

1. **Formal test suite** (`tests/unit/test_decision_candidate_survivorship_study.py::TestFutureMembershipFirewall`, `tests/integration/test_m064_survivorship_study_lifecycle.py::test_future_membership_edit_does_not_change_earlier_windows`): mutating `INSTR-AAPL-001`'s own `effective_to` to exactly W10's own scoring cutoff leaves windows W01-W09 byte-identical on eligible set, executed-trade count, net PnL, and total R; W10 changes as expected. A companion test proves the reverse direction: *removing* a future exit record restores eligibility retroactively removed by nothing -- earlier windows remain unchanged either way.
2. **Independent second pass**, using a *different* instrument (`INSTR-NVDA-001`, not `AAPL`) and a genuinely fresh, independently built PostgreSQL container, driven entirely through the real installed CLI subprocess (`empirical-platform-run-survivorship-aware-robustness-study.exe`, not `python -m`): windows W01-W09 confirmed byte-identical across the baseline and mutated runs; W10 changed exactly as expected (NVDA dropped from the eligible set).

## Independent Membership Derivation

A separately-authored verifier (`tests/unit/test_decision_candidate_historical_universe.py::TestIndependentUniverseDerivation`, plus a standalone scratch script used in the second pass) derives eligible sets from raw membership records using its own loop/comparison logic, never calling `historical_universe.universe_at()`. Exact agreement was confirmed at 9 boundary cutoffs (before-join, exact join instant, 1 day after join, exact exit-boundary-minus-1-microsecond, exact exit instant, and others) and, in the independent second pass, across all 10 real fixture windows plus an exact join-instant/pre-instant boundary spot check. The independent script also recomputed both the membership-manifest SHA-256 and the dataset-bundle SHA-256 from raw file bytes and matched the declared/production values exactly.

## PostgreSQL Acceptance

Three PostgreSQL containers were used across this mission:

1. **`m063-dev-pg` (port 55466, reused from the prior session, migrated fresh via `alembic downgrade base` + `upgrade head` after discovering pre-existing schema drift from an earlier M063 domain amendment)**: canonical CLI run/get smoke tests, full unit + PostgreSQL integration test suite (4/4 M064 integration tests passed, including the real CLI subprocess test and the membership-tamper/future-membership-firewall attacks), full repository-wide PostgreSQL regression (278 passed, 6 skipped, 0 failed, using a distinct `empirical`/`m064secretpw` role to avoid the known M026 credential-substring coincidence unrelated to M064).
2. **`m064-second-pass-pg` (port 55480, freshly created for this mission, torn down after use)**: independent second-pass verification only -- fresh `alembic upgrade head` from empty, real installed-CLI-subprocess canonical run, real installed-CLI-subprocess mutation-attack run (different instrument than the formal test), raw SQL inspection of both persisted studies plus `instrument_master`/`membership_record`/`universe_authority` row counts (confirming idempotent `ON CONFLICT DO NOTHING` inserts).

## Hostile Review

All mission-specified hostile-review categories were attacked; genuine findings were fixed inline before freeze:

- **FIXED**: `build_survivorship_aware_robustness_study()` did not validate that the membership manifest's own `(universe_id, universe_version)` matched the dataset bundle's own declared universe authority -- a caller could silently persist a study whose reported universe identity did not match the data it was actually built from. Added an explicit `ValueError` check (`TestDatasetMembershipUniverseMismatch::test_mismatched_universe_id_rejected`).
- **FIXED**: an integration-test assertion compared a bare Python string against a tuple of `InstrumentId` value objects (`"INSTR-AAPL-001" in eligible_instrument_ids`), which is always `False` regardless of actual eligibility since the types never compare equal -- caught when the test failed for the wrong reason during the formal PostgreSQL acceptance run; corrected to compare `InstrumentId` instances.
- **PASS** (verified via dedicated tests, not merely asserted): empty instrument master; duplicate instrument ID / duplicate canonical symbol; unknown instrument referenced by membership or by dataset bars; empty membership manifest; duplicate membership record; overlapping intervals; inverted interval; exact `effective_from` boundary (inclusive); exact `effective_to` boundary (exclusive); before-join; after-exit; membership record input-order independence (hash and `universe_at()` both); membership-hash determinism; membership tamper (PostgreSQL-integration-level, real CLI); dataset tamper (reuses the already-tested frozen M063 tamper check, and was empirically re-triggered by the author's own fixture-generation bug during this mission, then fixed); dataset/membership universe mismatch (see FIXED above); eligible instrument with missing bar data (excluded, not evaluated, recorded in `missing_data_excluded_instrument_ids`); later entrant appearing early (rejected); retroactive removal of a future exit (does not affect earlier windows); future membership leakage (firewall tests, twice); future bar leakage (inherited unchanged from frozen M061/M063 per-window private-bar-block slicing); all instruments inactive (returns an empty eligible set, no crash); one active instrument; changing universe size across windows (4→6→3, genuinely observed); `CURRENT_UNIVERSE_BIAS_STRESS` (extensively tested); deterministic replay; multiple universe versions coexisting (structurally proven: distinct `(universe_id, universe_version)` primary key, plus a dedicated construction test); PostgreSQL round trip; raw SQL equality; real CLI subprocess (twice, two different containers); M063 semantics preserved (`isinstance` check against the real `HistoricalRobustnessStudy`/`RobustnessStudyClassification` types); regime semantics preserved (same `REGIME_POLICY_ID`/`VERSION` constants, same tertile formula); no strategy/ranking/risk/sizing/execution/backtest/robustness mutation (`git diff --stat` against the M063 freeze baseline: zero deletions in every frozen file); no parameter optimization or cherry-picking (grep-clean; the fixture's first and only generation attempt was accepted as-is); survivorship/market-wide/profitability/live-readiness overclaim (grep-clean across the entire M064 code delta; the only matches anywhere in the delta are inside the design document's own explicit forbidden-terms and rejected-candidates lists); corporate-action overclaim (the `CORPORATE_ACTION_HANDLING_NOT_EXERCISED` constant is always set, unconditionally); LLM/network/broker/live-execution dependency (grep-clean); architecture/frozen-predecessor violation (`tools/check_architecture.py` exits 0; zero deletions in frozen files); evidence inconsistency (this report's own figures were cross-checked against the actual JSON CLI output and raw SQL captured during the mission, not written from memory).
- **N/A_WITH_JUSTIFICATION**: duplicate universe-version insert -- `add_universe`/`add_membership`/`add_all` all use `ON CONFLICT DO NOTHING` by design (idempotent write-once reference data, matching the small-reference-table pattern this repository already uses elsewhere); not an error case. Multiple dataset-bundle versions coexisting -- no unique constraint prevents it and no dedicated test was added given the schema already demonstrably supports arbitrary `dataset_bundle_id`/`version` text values with no cross-study uniqueness constraint.

No CRITICAL or MAJOR finding remains open.

## Canonical Validation

Run from the repository `.venv` (`Python 3.13.14`):

- Ruff format/check (whole repository): PASS, 450 files formatted, all checks passed
- mypy (`packages = ["empirical_platform"]`, the canonical scope): `Success: no issues found in 216 source files`
- architecture checker (`tools/check_architecture.py`): PASS (exit 0)
- full non-integration suite: `1396 passed`, coverage `81.86%` (>= 80% gate)
- full PostgreSQL integration suite: `278 passed, 6 skipped`, 0 failed
- build (`python -m build --wheel`): PASS; wheel contents verified to include all 6 new `decision_candidate` modules, the new concrete repository module, both new usecases, both new CLI entrypoints, and both new console-script entry points; smoke-imported cleanly from the extracted wheel
- `pip-audit`: no known vulnerabilities (the local `empirical-platform` package itself is correctly skipped as not-on-PyPI, the same benign skip every prior milestone's evidence records)
- secret scan: 3 files flagged, all "Hex High Entropy String" false positives on the committed SHA-256 dataset/membership hash constants (matches the documented, accepted pattern from M062/M063)

## No Optimization / No Cherry-Picking / No Broker / No Network / No LLM

Every file in the M064 delta was searched directly (not sampled) for optimization/tuning/grid-search/hyperparameter/genetic/bayesian, broker/network/socket/HTTP-client/LLM-provider, and forbidden overclaim terms. The only matches anywhere in the entire delta are inside `MILESTONE_064_..._SCOPE_AND_DESIGN.md`'s own explicit "REJECTED" and "Forbidden" lists -- i.e., the document naming what must never appear, not an instance of it appearing. The canonical fixture's membership timeline and bar data were both generated once, in a single deterministic pass, and accepted as-is; no window, instrument, or membership boundary was altered after observing results.

## Product Honesty Gate

M064 makes historical universe membership explicit and demonstrates, with real evidence, that later entrants cannot appear early, that future membership changes cannot alter earlier windows, and that inactive/exited historical members remain historically queryable. It does **not** prove:

- that survivorship bias is eliminated (the canonical fixture remains synthetic; `source_kind = SURVIVORSHIP_AWARE_MECHANICS_FIXTURE` throughout)
- market representativeness
- that the synthetic membership timeline reflects any real historical market
- profitability
- live-trading readiness
- that corporate actions (splits, dividends, symbol changes) are handled (`CORPORATE_ACTION_HANDLING_NOT_EXERCISED`, unconditionally)
- that current-universe bias is a major contributor in real markets (the stress diagnostic measures this fixture's own mechanics, not real-world magnitude)

## Independent Second Review

Genuinely distinct from the implementation-validation pass:

- a different, freshly created PostgreSQL container (`m064-second-pass-pg`, port 55480), never reused from any earlier step, built from an empty schema via `alembic upgrade head`
- driven entirely through the real installed CLI executable (`empirical-platform-run-survivorship-aware-robustness-study.exe`), not `python -m` and not in-process function calls
- independent membership-manifest-hash and dataset-hash recomputation from raw file bytes, in a standalone script that imports neither `membership.py` nor `historical_universe.py`
- independent eligible-set derivation for all 10 real windows plus an exact join-instant boundary check, matching production exactly
- a future-membership mutation attack using a *different* instrument (`NVDA`) than the formal test suite used (`AAPL`), proving the firewall generalizes rather than happening to pass for one specific case
- raw SQL inspection of both the baseline and mutated studies coexisting in the same container, plus idempotency verification of the small reference tables
- a fresh grep/source/governance disproof attempt against the entire M064 delta

Result: **no blocking defect found beyond the one dataset/membership-universe-mismatch gap (fixed inline before freeze), no contradiction found, no false survivorship-mechanics claim found.**

## Owner Approval

**M064 MACRO MILESTONE APPROVED_AND_FROZEN.**

Scope, design, implementation, hostile review, independent second review, and product-honesty gate are frozen as one consolidated unit. M064 makes historical universe membership first-class and proves the mechanics honestly. It does not certify survivorship-bias elimination, profitability, or live readiness.

## Deferred / M065 Boundary

No MILESTONE-065 capability is built here. M065 remains a recommendation only (see the external-review final report, Section AU).

## Next Permitted Action

MILESTONE-065 - recommendation only; not started as part of M064.
