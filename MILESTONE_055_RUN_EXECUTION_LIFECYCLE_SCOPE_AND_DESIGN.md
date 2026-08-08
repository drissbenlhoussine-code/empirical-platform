# MILESTONE-055 - Run Execution Lifecycle End-to-End - Scope and Design

**Status: CANDIDATE_INTERNAL_MACRO_SCOPE_AND_DESIGN**

Combined scope+design, continuing the reduced-ceremony process established in M053/M054.

## 1. Repository Authority

Repository `C:\Users\LuxSy\Documents\trading`, branch `master`. M055 frozen baseline: `853a74931340fd34b0dec78d5ff65939a2d16271` (the final M054 Owner Freeze hash-recording HEAD; M054 fully `APPROVED_AND_FROZEN`), independently re-verified via `git fetch` before any work began.

## 2. Fresh Run Architecture Inventory

Independently re-derived from source (`src/empirical_platform/run/aggregate.py`, `run/repository.py`, `usecases/*run*.py`), not from prior governance prose or from this mission's own speculative naming:

- **Lifecycle states** (`campaign.lifecycle.RunLifecycleState`, frozen M012): `CREATED`, `AUTHORIZED`, `ACQUIRING`, `NORMALIZING`, `VALIDATING`, `EXECUTION_COMPLETED`, `FAILED`, `CANCELLED` — 8 states.
- **All transition domain methods already exist on the frozen `Run` aggregate**, unmodified, requiring zero new domain design: `authorize()` (CREATED→AUTHORIZED), `start_acquisition()` (AUTHORIZED→ACQUIRING), `start_normalization()` (ACQUIRING→NORMALIZING), `start_validation()` (NORMALIZING→VALIDATING), `complete_execution()` (VALIDATING→EXECUTION_COMPLETED), `cancel()` (AUTHORIZED→CANCELLED), `fail()` (ACQUIRING/NORMALIZING/VALIDATING→FAILED), and `append_manifest()` (appends an immutable `DatasetManifest` while in any of CREATED/AUTHORIZED/ACQUIRING/NORMALIZING/VALIDATING).
- **`complete_execution()` has no manifest precondition** — unlike `EvidencePackage.seal()`, recording a manifest is not a hard gate to progress. Manifests are genuine, real, persisted execution data, not a fabricated requirement.
- **Existing usecases** (all frozen, unmodified): `create_run` (M033), `get_run` (M034), `authorize_run` (M035), `fail_run` (M048). **Existing usecases with zero production entrypoints**: `authorize_run`, `fail_run` — both already frozen, both already exercised by their own integration test suites at the repository level, neither ever composed into a real CLI command.
- **Missing usecases** (confirmed absent from `src/empirical_platform/usecases/`): none exist yet for `start_acquisition`, `start_normalization`, `start_validation`, `complete_execution`, or `append_manifest`.
- **Repository/persistence**: `PostgresRunRepository.save()`/`.add()` already fully persist `run_manifest` rows (delete-then-reinsert-all on save, identical pattern to `evidence_package_criterion_result`) — already frozen, already exercised by the repository's own test suite, but never exercised end-to-end through any usecase or entrypoint.
- **Existing production entrypoints**: `create_run`, `get_run` (both M053, unmodified). Zero entrypoints exist for authorize, execution-stage transitions, manifest recording, or failure.
- **Out of scope, explicitly**: `cancel()` (AUTHORIZED→CANCELLED) has no usecase and is a *different* terminal path than `fail()`, not requested by this mission's own scope instruction, and adding it would be a second, unrelated capability bolted onto this milestone. Not built here.

## 3. BEFORE/AFTER Statement

**Before M055**, a caller can create a Run, but the Run cannot genuinely progress through its execution lifecycle via production composition — every execution-stage transition, and manifest recording, exists only inside the frozen aggregate and its own unit tests. **After M055**, a caller can drive a persisted Run through its complete legitimate execution lifecycle — authorize, start acquisition, record acquisition data, start normalization, record further data, start validation, complete execution — or fail it from any active execution stage — using real production entrypoints against real PostgreSQL, and retrieve the final persisted state, with PostgreSQL-backed end-to-end evidence including genuine data preservation across transitions.

## 4. Selected Scope

**Five new application-layer usecases** (zero new domain design; each composes an already-frozen `Run` aggregate method):

1. `usecases.start_run_acquisition` — `StartRunAcquisitionCommand`/`StartRunAcquisitionHandler`, composes `Run.start_acquisition()`.
2. `usecases.append_run_manifest` — `AppendRunManifestCommand`/`AppendRunManifestHandler`, composes `Run.append_manifest()`.
3. `usecases.start_run_normalization` — `StartRunNormalizationCommand`/`StartRunNormalizationHandler`, composes `Run.start_normalization()`.
4. `usecases.start_run_validation` — `StartRunValidationCommand`/`StartRunValidationHandler`, composes `Run.start_validation()`.
5. `usecases.complete_run_execution` — `CompleteRunExecutionCommand`/`CompleteRunExecutionHandler`, composes `Run.complete_execution()`.

**Seven new production entrypoints**, all reusing the unmodified M053 `entrypoints._composition.postgres_repository_runtime()` helper: `authorize_run`, `start_run_acquisition`, `append_run_manifest`, `start_run_normalization`, `start_run_validation`, `complete_run_execution`, `fail_run`. The first and last compose the already-frozen M035/M048 usecases (no new application code); the middle five compose the five new usecases above.

## 5. Legal Lifecycle Sequence (What This Milestone Proves End-to-End)

```
Campaign exists (M052)
  -> Run created (M053, existing)
  -> authorize_run          CREATED -> AUTHORIZED
  -> start_run_acquisition  AUTHORIZED -> ACQUIRING
  -> append_run_manifest    (records acquisition data; version bump, no transition)
  -> start_run_normalization ACQUIRING -> NORMALIZING
  -> append_run_manifest    (records normalization data; second manifest)
  -> start_run_validation   NORMALIZING -> VALIDATING
  -> complete_run_execution VALIDATING -> EXECUTION_COMPLETED
  -> get_run (M053, existing) -> final state verified, both manifests preserved
```

Negative path, proven on a separate Run from a legitimate active state:

```
Run created -> authorize_run -> start_run_acquisition -> append_run_manifest
  -> fail_run   ACQUIRING -> FAILED (manifest data preserved across the failure transition)
```

## 6. Architecture Decisions

**Reuse, no new abstraction.** The M053 `_composition.py` helper is reused unchanged for all seven entrypoints. M050-M054's own entrypoints remain untouched.

**No exception translation, no dispatcher, no registry.** Identical discipline to M050-M054: `AggregateNotFound`, domain `ValueError` (invalid transition, invalid manifest), and `OptimisticConcurrencyConflict` all propagate to the caller unchanged.

**One coherent aggregate mutation per command.** Every new command is a single-aggregate `get()`→mutate→`save()` sequence, matching every prior usecase in this project.

## 7. Concurrency

Every new write command reuses the identical, already-proven `expected_persisted_version`-guarded optimistic-concurrency mechanism, already independently proven at the usecase/repository level by M035 (`authorize_run`) and M048 (`fail_run`) integration tests. Rather than duplicate that exact boundary ceremonially, this milestone proves OCC once through the genuinely new thing it adds — real entrypoint composition — via the natural two-sequential-manifest-append point in the main acceptance test: the second `append_run_manifest` call is first attempted with a deliberately stale `expected_persisted_version` (a genuine conflict against real PostgreSQL), then correctly retried. No additional ceremonial OCC test is added beyond this.

## 8. Failure Semantics

No exception translation anywhere. `AggregateNotFound` (missing Run), domain `ValueError` (invalid lifecycle transition; invalid manifest — e.g. duplicate `manifest_id`, or appending outside the allowed states), and `OptimisticConcurrencyConflict` all propagate to the caller unchanged.

## 9. In-Scope

Five usecase modules, seven production entrypoint modules, seven matching `[project.scripts]` entries, focused unit/contract tests for the five new usecases (command shape, get/save wiring, exact version passthrough, domain-effect proof, domain-failure propagation, OCC propagation — reusing the established `authorize_run`/`fail_run` fake-repository test pattern, not reproducing its full ~30-test breadth per usecase), focused CLI unit tests for the seven new entrypoints, and one comprehensive PostgreSQL end-to-end acceptance test proving the complete legal forward lifecycle plus the negative `fail_run` path — verified via direct SQL against `run`, `run_manifest`, and `run_transition`.

## 10. Out-of-Scope

`cancel_run` (different terminal path, no usecase, not requested); any transport/HTTP layer; any transaction orchestration beyond single-aggregate `save()`; any change to `tools/check_architecture.py`; any change to M050-M054's own entrypoints; any change to `create_run.py`/`get_run.py`; MILESTONE-056 work of any kind.

## 11. M056 Boundary

This scope selects exactly one MILESTONE-055 capability. No MILESTONE-056 capability, terminology, or sequencing decision is made anywhere in this document.

## 12. Status

**CANDIDATE_INTERNAL_MACRO_SCOPE_AND_DESIGN.**
