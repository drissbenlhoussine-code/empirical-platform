# MILESTONE-055 - Run Execution Lifecycle End-to-End - Macro Milestone Freeze

## Status: FINAL — OWNER FROZEN

## Repository Authority

Repository `C:\Users\LuxSy\Documents\trading`, branch `master`. M055 baseline `853a74931340fd34b0dec78d5ff65939a2d16271` (the M054 Owner Freeze hash-recording HEAD; M054 fully `APPROVED_AND_FROZEN`). Implementation commit `6da49c3d694da28405977f59f8d52e2899b2fdc8`.

## Delivered Capability

Seven new production entrypoints (`authorize_run`, `start_run_acquisition`, `append_run_manifest`, `start_run_normalization`, `start_run_validation`, `complete_run_execution`, `fail_run`) composing five new usecases plus the two already-frozen M035/M048 usecases (`authorize_run`, `fail_run` — composed into production for the first time). Before this milestone a caller could create a Run, but it could not genuinely progress through its execution lifecycle via production composition. After this milestone, a caller can drive a persisted Run through its complete legal execution lifecycle — authorize, start acquisition, record dataset manifests, start normalization, start validation, complete execution — or fail it from any active execution stage, entirely through real CLI commands against real PostgreSQL, with genuine data preservation across every transition. See `MILESTONE_055_RUN_EXECUTION_LIFECYCLE_SCOPE_AND_DESIGN.md` for the full architecture inventory and selection rationale.

## Implementation Evidence

54 new focused tests: 18 usecase unit/contract tests (command shape, get/save wiring, exact version passthrough, domain-effect proof, domain-failure propagation, OCC propagation — reusing the established `authorize_run`/`fail_run` fake-repository pattern) and 36 entrypoint CLI tests, plus one comprehensive PostgreSQL end-to-end acceptance test (5 tests: the complete legal forward lifecycle with a genuine optimistic-concurrency conflict during manifest recording and a corrected retry; the negative `fail_run` path with manifest data preservation; an out-of-order transition failure; a post-completion manifest-append failure; environment-default-config path) run against a real, freshly-migrated, disposable Docker PostgreSQL container. Full canonical validation after implementation stabilized: `ruff check`/`ruff format --check` clean, canonical `mypy` (136 source files) clean, `tools/check_architecture.py` clean, build (wheel, all 7 new console scripts registered) clean, `pip-audit` clean, secret scan (565 tracked targets) zero findings. Full regression: 1080 non-integration tests passed (84.29% coverage, ≥80% gate), 231 PostgreSQL integration tests passed (6 pre-existing, unrelated skips) — zero regressions across every prior milestone's own suite.

## A Genuine, Minimal Correction Made Inside This Milestone

`Run.append_manifest()` (frozen, unmodified) requires a `DatasetManifest` value object, which lives in the separate top-level `datasets` package rather than inside `run` itself — unlike `EvidencePackage`'s `CriterionResult`/`ArtifactReference` or `Review`'s `ReviewFinding`, which are defined inside their own aggregate packages. Since `entrypoints`/`usecases` architecture rules do not permit importing `datasets` directly, and this is the first usecase to ever need this value object, `run/__init__.py` was given one additive, zero-behavior-change line re-exporting `DatasetManifest` (mirroring how `run/aggregate.py` itself already imports it) — making it reachable through the already-permitted `run` import boundary. Verified zero semantic diff (`git diff` shows exactly two lines added) and zero regression (36 pre-existing Run-related contract/mapper/reconstruction tests all pass unchanged).

## Hostile Self-Review

Attacked all 13 questions from this mission's own checklist. Confirmed: the complete claimed lifecycle is genuinely reachable (proven twice — automated test and real subprocess); no domain precondition was bypassed anywhere (zero direct SQL fabrication of state); `expected_persisted_version` is genuinely caller-controlled (unit-tested: `saved_version is command.expected_persisted_version`, never `loaded.persisted_version`); manifests survive every transition including failure (independently verified via direct SQL); transition history is exactly correct (verified against `run_transition` row-by-row); `fail_run` works from a legitimate active state (ACQUIRING) with data preserved; resources are always closed (zero `try:`/`except` in any of the 7 new entrypoints — fully delegated to the M053 helper); zero business logic in entrypoints (zero direct `.get()`/`.add()`/`.save()` calls, confirmed via grep); no frozen predecessor was altered beyond the one justified, additive `run/__init__.py` line and the purely additive `pyproject.toml` diff; no second unrelated capability was introduced (`cancel_run` was explicitly identified and left out of scope). **Findings: none requiring correction** beyond the explicit re-export addition described above.

## Independent Second Review

Re-derived repository truth fresh from live Git history (working tree exactly the 17 intended files at the pre-implementation baseline). Directly challenged "can a real caller now drive a Run through its genuine execution lifecycle without test-only or SQL bypasses?" using a second, independent technique beyond the automated suite: invoked every entrypoint as a real subprocess (`python -m empirical_platform.entrypoints.<name>`) against a second, fresh, disposable PostgreSQL container, driving two Runs through the complete chain — one to `EXECUTION_COMPLETED` (including a genuine `OptimisticConcurrencyConflict` on a stale manifest append, a corrected retry, and a genuine post-completion manifest-append `ValueError`), one to `FAILED` from `ACQUIRING` with manifest data intact — then independently verified final state via raw `psql`, bypassing all application code, confirming exact agreement with every subprocess-reported result across both Runs' final states, manifests, and complete transition histories.

**Findings: none. Zero CRITICAL, MAJOR, or MINOR findings. No further correction required.**

## Owner Approval

**M055 MACRO MILESTONE APPROVED_AND_FROZEN.**

Scope, design, implementation, hostile self-review, and independent second review frozen as one consolidated unit. No architecture broadening beyond the one justified `run/__init__.py` re-export. No scope creep (`cancel_run` explicitly excluded), no framework creep, no policy bypass. Predecessor authority (M020-M054) fully preserved; M050-M054's own entrypoints are unmodified.

## Deferred / M056 Boundary

No MILESTONE-056 capability, terminology, or sequencing decision is made in this document.

## Next Permitted Action

MILESTONE-056 (large, product-oriented capability — see `PROJECT_CHECKPOINT.md`).
