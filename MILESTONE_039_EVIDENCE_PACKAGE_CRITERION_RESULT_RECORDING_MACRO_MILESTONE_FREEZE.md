# MILESTONE-039 - EvidencePackage Criterion-Result Recording Macro Milestone Freeze

## 1. Document Status

**Status: FINAL — OWNER FROZEN**

This document is the Owner Freeze record for MILESTONE-039, the fourth milestone produced under the Macro Milestone Protocol (M035 implementation freeze, Section 49; PROJECT_CHECKPOINT.md Section 31). It is authoritative.

## 2. Milestone Identity

MILESTONE-039 — Concrete Application Command Vertical Slice: EvidencePackage Criterion-Result Recording.

## 3. Repository Authority

| Field | Value |
| --- | --- |
| Repository | `C:\Users\LuxSy\Documents\trading` |
| Branch | `master` |
| HEAD at freeze | `adf0ec7a26b3aeda5e7f98d1e4ecdb2deed0405e` |

## 4. Frozen Predecessor Chain

M020-M038 all `APPROVED_AND_FROZEN` at every stage. M038 Owner Freeze: `MILESTONE_038_EVIDENCE_PACKAGE_COLLECTION_START_MACRO_MILESTONE_FREEZE.md`, freeze commit `cf3907a30ddbea6609be8ba322ff3f3c7cfb6bd7`, hash-recording commit `35cbdd09792abedb41382098241f1c39eb889f25`.

## 5. Macro Scope Authority

`MILESTONE_039_CONCRETE_APPLICATION_COMMAND_VERTICAL_SLICE_EVIDENCE_PACKAGE_CRITERION_RESULT_RECORDING_MACRO_SCOPE.md` — one concrete command recording a `CriterionResult` on an existing, `COLLECTING` `EvidencePackage`, via `EvidencePackage.add_criterion_result()`. Selected after a fresh architecture inventory found the owned-collection-append write pattern completely unproven anywhere in this project, and after seriously evaluating and independently rejecting Review creation (now FK-viable, but would repeat an already-three-times-proven CQRS pattern rather than close the still-open gap, and semantically mismatches reviewing an un-sealable package).

## 6. Macro Design Authority

`MILESTONE_039_CONCRETE_APPLICATION_COMMAND_VERTICAL_SLICE_EVIDENCE_PACKAGE_CRITERION_RESULT_RECORDING_MACRO_DESIGN.md` — seven-field command (`identity`, `expected_persisted_version`, `criterion_id`, `recorded_at`, `result_label`, `summary`, `evidence_references`) with `evidence_package_id` derived from the loaded aggregate's own identity rather than separately supplied; `SaveResult` result contract; and, as the central load-bearing decision, a **genuine** deterministic-conflict mechanism (design Section 6) closing the boundary M038's own freeze record explicitly disclosed as unavailable.

## 7. Implementation Commit

`9ec849a04bb76d11f391988979c4d9fce54e3beb` (`feat: implement M039 EvidencePackage criterion-result recording usecase`).

## 8. Finalization Commit

`adf0ec7a26b3aeda5e7f98d1e4ecdb2deed0405e` (`docs: finalize M039 macro milestone review package`) — narrow, checkpoint-only, recorded the implementation commit's own hash. No production behavior changed.

## 9. Independent Review Authority

The independent hostile review verified: synchronized repository truth; correct M038 freeze ordering; exactly nine authorized M039 tracked changes; one `CriterionResult`-recording capability only; correct command and handler contracts; `EvidencePackage` ownership derived from the loaded aggregate; exact identity-object pass-through; caller-supplied expected persisted version; exactly one `get()`, one criterion mutation, and one `save()`; exact `SaveResult` propagation; correct duplicate-criterion behavior; genuine live PostgreSQL optimistic-concurrency conflict; a state-preserving interfering `add_artifact_reference()` write; absence of any second production capability; zero architecture-checker change; complete tests, regression, typing, build, security, governance, manifest, and ZIP integrity; M020-M038 predecessor preservation; absence of any M040 work.

## 10. Review Decision

**M039 MACRO MILESTONE APPROVED WITH NON-BLOCKING OBSERVATIONS.** No CRITICAL, MAJOR, or blocking MINOR finding remains.

## 11. Owner Approval

The owner formally freezes the M039 macro milestone via this document.

**M039 MACRO MILESTONE APPROVED_AND_FROZEN.**

**M039 APPROVED_AND_FROZEN** — scope, design, and implementation, at every stage, frozen as one consolidated unit per the Macro Milestone Protocol.

## 12. Frozen Production Capability

Exactly one: recording of a `CriterionResult` on an existing, `COLLECTING` `EvidencePackage`. No `add_artifact_reference`, `seal`, `invalidate`, `start_collection`, or any second command/capability.

## 13. Frozen Command Contract

```python
@dataclass(frozen=True, slots=True)
class RecordEvidencePackageCriterionResultCommand:
    identity: DomainIdentity[EvidencePackageId]
    expected_persisted_version: AggregateVersion
    criterion_id: str
    recorded_at: datetime
    result_label: str
    summary: str | None = None
    evidence_references: tuple[str, ...] = ()
```

Exactly seven fields, independently re-verified via `set(RecordEvidencePackageCriterionResultCommand.__slots__)`. No `evidence_package_id` field exists.

## 14. Frozen Handler Contract

```python
class RecordEvidencePackageCriterionResultHandler:
    __slots__ = ("_evidence_package_repository",)

    def __init__(self, *, evidence_package_repository: EvidencePackageRepository) -> None:
        self._evidence_package_repository = evidence_package_repository

    def handle(self, command: RecordEvidencePackageCriterionResultCommand) -> SaveResult:
        loaded = self._evidence_package_repository.get(command.identity)
        package = loaded.aggregate
        result = CriterionResult(
            evidence_package_id=package.identity.governance_id,
            criterion_id=command.criterion_id,
            recorded_at=command.recorded_at,
            result_label=command.result_label,
            summary=command.summary,
            evidence_references=command.evidence_references,
        )
        package.add_criterion_result(result)
        return self._evidence_package_repository.save(
            package, expected_persisted_version=command.expected_persisted_version
        )
```

Sole dependency: `EvidencePackageRepository`. No `RunRepository`, no `CampaignRepository` — independently re-confirmed in this freeze via direct grep (Section 38).

## 15. Frozen Identity Semantics

`command.identity` (a full `DomainIdentity[EvidencePackageId]`) is passed to `EvidencePackageRepository.get()` unchanged — independently re-verified via source inspection.

## 16. Frozen Ownership Derivation

`evidence_package_id` on the constructed `CriterionResult` is derived from `package.identity.governance_id` — the loaded aggregate's own identity — never from a separately supplied command field. There is no such field on the command at all, independently re-confirmed via `set(RecordEvidencePackageCriterionResultCommand.__slots__)`. This eliminates any possible mismatch failure mode between a caller-supplied ownership value and the aggregate actually loaded.

## 17. Frozen Expected-Version Semantics

`command.expected_persisted_version` — never `loaded.persisted_version` — is passed to `save()`. Independently re-verified via source inspection and via the frozen unit test `test_save_receives_command_version_not_loaded_persisted_version`, which constructs the two values as deliberately different and confirms only the command's own value reaches `save()`.

## 18. Frozen Load–Mutate–Save Sequence

1. Receive `RecordEvidencePackageCriterionResultCommand`.
2. Call `evidence_package_repository.get(command.identity)` exactly once.
3. Derive `evidence_package_id` from `package.identity.governance_id`.
4. Construct exactly one `CriterionResult`.
5. Call `package.add_criterion_result(result)` exactly once.
6. Call `evidence_package_repository.save(package, expected_persisted_version=command.expected_persisted_version)` exactly once.
7. Return the exact `SaveResult`, unchanged.

Independently re-verified in this freeze: exactly one `.get(` and exactly one `.save(` in the production module; no `.add(` call; no artifact-reference production command; no second criterion mutation; no retry; no Run or Review lookup.

## 19. Frozen Result Contract

`SaveResult` (`operation`, `persisted_version`), returned exactly as received from `EvidencePackageRepository.save()` — no wrapping, no field extraction, no reconstruction.

## 20. CriterionResult Construction

Exactly one `CriterionResult` constructed per invocation, with all fields sourced from the command except `evidence_package_id` (Section 16). `CriterionResult.__post_init__` (frozen since M020) independently validates `criterion_id`/`result_label`/`summary`/`evidence_references` — the handler duplicates none of this validation.

## 21. Criterion Collection Semantics

A successful `add_criterion_result()` call appends exactly one `CriterionResult` to `EvidencePackage._criterion_results`, preserves the current lifecycle state (`COLLECTING`), and advances `version` by exactly one — independently confirmed by the frozen unit test `test_add_criterion_result_called_with_exact_command_arguments` and the live PostgreSQL golden-path test.

## 22. Aggregate-Version Semantics

`EvidencePackage.version` is genuine aggregate domain state, advancing when `add_criterion_result()` is called. It is never exposed on the command or the `SaveResult`; the caller-supplied `expected_persisted_version` is deliberately distinct and independently supplied (Section 17).

## 23. Persisted-Version Semantics

`LoadedAggregate.persisted_version` (the repository-loaded concurrency token at `get()` time) is read but never substituted for `command.expected_persisted_version` when calling `save()` — confirmed by the frozen unit test cited in Section 17.

## 24. Duplicate Criterion Behavior

`EvidencePackage.add_criterion_result()` raises a domain `ValueError` ("criterion_id already exists") when the supplied `criterion_id` already exists in `criterion_results`, propagated transparently with `save()` never reached — proven at unit level and genuinely reproduced against real PostgreSQL (Section 34).

## 25. Not-Found Behavior

`AggregateNotFound` raised by `EvidencePackageRepository.get()` for a `DomainIdentity` with no persisted `EvidencePackage`, propagated transparently — proven at unit level (fake repository) and genuinely reproduced against real PostgreSQL.

## 26. Invalid-State Behavior

`EvidencePackage.add_criterion_result()` raises a domain `ValueError` ("may be added only while COLLECTING") when the current state is not `COLLECTING`, propagated transparently with `save()` never reached — proven at unit level and genuinely reproduced against real PostgreSQL (Section 33).

## 27. Arbitrary Error Semantics

Transparent, unchanged propagation of `OptimisticConcurrencyConflict` and any arbitrary `get()`/`save()` failure. No handler-level `try`/`except`.

## 28. Validation Ownership

`DomainIdentity`/`EvidencePackageId`/`AggregateVersion` own their own format validation at construction. `CriterionResult.__post_init__` owns its own field validation. `EvidencePackage.add_criterion_result()` owns its own state-precondition and duplicate-`criterion_id` validation. The handler performs no additional validation and duplicates none of the above.

## 29. Transaction Non-Ownership

No application-level transaction orchestration — one repository-owned `save()` call, already atomic via its own `unit_of_work()`.

## 30. CommandEntryPoint Binding

Test-only direct construction, mirroring every prior command milestone. No production composition root.

## 31. Architecture Preservation

**Zero architecture-checker change.** Independently re-verified in this freeze: `git diff 35cbdd0..adf0ec7 -- tools/check_architecture.py tests/fixtures/` is empty, and `python tools/check_architecture.py .` passes at exit 0.

## 32. PostgreSQL Success Evidence

Independently reproduced against a fresh disposable `postgres:17` container in this freeze session: golden-path recording via `CommandEntryPoint`, `SaveResult.persisted_version == AggregateVersion(2)`, independently reloaded state with exactly one `CriterionResult` matching every recorded field, `state` still `COLLECTING`.

## 33. PostgreSQL Invalid-State Evidence

Independently reproduced against real PostgreSQL in this freeze session: an `EvidencePackage` still `INITIALIZED` rejects `add_criterion_result()` with a domain `ValueError` before `save()` is ever reached.

## 34. PostgreSQL Duplicate-Criterion Evidence

Independently reproduced against real PostgreSQL in this freeze session: a second command carrying an already-recorded `criterion_id` raises a domain `ValueError` before the second `save()` is ever reached.

## 35. PostgreSQL Missing-Aggregate Evidence

Independently reproduced against real PostgreSQL in this freeze session: retrieval of a never-persisted `DomainIdentity` raises `AggregateNotFound`.

## 36. Real Optimistic-Concurrency Evidence

Independently reproduced against real PostgreSQL in this freeze session: `test_stale_expected_version_raises_genuine_optimistic_concurrency_conflict` — a genuine `OptimisticConcurrencyConflict`, not a domain `ValueError`, confirmed by exception type inspection. Post-attempt reload independently confirmed: the interfering writer's `ArtifactReference` is durably persisted (the only change beyond the initial `start_collection()` transition), and the losing writer's `CriterionResult` was never persisted (`criterion_results == ()`).

## 37. Interfering Artifact-Reference Evidence

Recorded permanently, the exact real-conflict sequence, independently re-verified against the live integration test in this freeze session:

1. `EvidencePackage` is already `COLLECTING` (via the frozen M038 `start_collection()`).
2. An independent writer loads a separate `LoadedAggregate` instance for the same identity.
3. The independent writer calls `add_artifact_reference(ArtifactReference(value="interfering-writer"))` — a legitimate domain method.
4. Lifecycle state remains `COLLECTING` (unchanged by this method).
5. The aggregate's in-memory `version` advances by exactly one.
6. The independent writer calls `save()` using the version it loaded with.
7. The durable `persisted_version` advances to reflect the interfering write.
8. The M039 command under test retains the version captured *before* the interference — now stale.
9. The handler independently reloads the identity, observing the current, `COLLECTING` state.
10. `add_criterion_result()` remains domain-valid against this current state (state unchanged by the interference).
11. The handler reaches `evidence_package_repository.save()`.
12. The repository's version guard compares the stale `expected_persisted_version` against the actual durable version.
13. `OptimisticConcurrencyConflict` is raised.
14. No retry or second `save()` attempt occurs anywhere in the frozen handler.
15. The interfering writer's `ArtifactReference` remains persisted and authoritative.
16. The losing writer's `CriterionResult` is never persisted.

**Explicitly recorded:** no direct SQL fabrication was used; no aggregate internals were patched; no invalid row was inserted; no second production command was introduced; `add_artifact_reference()` was used only as legitimate integration-test interference setup, identical in spirit to M032's `revise_scope_statement()` and M035's `append_manifest()` test-scaffolding precedent, and is never invoked by any production code in this milestone.

## 38. Full PostgreSQL Regression

Independently reproduced in this freeze session against a fresh disposable container: `pytest tests/integration/` — 146 passed, 6 skipped; `pytest -q` (PostgreSQL opt-in, full suite) — 820 passed, 6 skipped, 92.88% coverage. Both exactly match the implementation session's own figures — zero drift. Hostile self-audit grep independently re-confirmed: zero genuine prohibited-pattern matches in `record_evidence_package_criterion_result.py` (one docstring "for" false positive); no `RunRepository`/`CampaignRepository`/`Review` reference; no `add_artifact_reference`/`seal`/`invalidate`/`start_collection` call.

An additional targeted PostgreSQL regression grouping was independently reproduced in this freeze session (`test_m023_postgres_repositories.py` combined with `test_m033_create_run_usecase.py` through `test_m039_record_evidence_package_criterion_result_usecase.py`): **59 passed**, confirming zero regression across every predecessor Run/EvidencePackage integration suite plus this milestone's own 6 tests. A wider grouping additionally including the Campaign vertical-slice suites (`test_m030_create_campaign_usecase.py` through `test_m032_prepare_campaign_for_authorization_usecase.py`) independently reproduced **68 passed**. The independent review's own cited figure of 65 was not exactly reproduced with either tested grouping in this freeze session; recorded as an unreconciled, non-blocking documentation discrepancy — both independently reproduced groupings show zero regression regardless, and the full integration suite (Section 38's own 146-passed figure, encompassing every integration test in the repository) is the authoritative, unambiguous regression signal.

## 39. Ruff/Mypy/Build/Security Evidence

Independently re-run in this freeze session under the canonical `.venv` interpreter (Python 3.13.14): `ruff format --check .`/`ruff check .` clean, 236 files formatted; canonical `mypy` clean, 96 source files; `pytest -q -m "not integration"` — 674 passed, 152 deselected, 83.91% coverage; `python -m build --wheel` succeeds; `python -m pip_audit` reports no known vulnerabilities. Secret-scan counts recorded as explicitly time-scoped values: 418 at implementation-evidence-capture time; 419 independently reproduced at final revalidation before this freeze document itself existed on disk, exactly matching the independent review's own cited figure; 420 independently reproduced at this freeze document's own creation time (one further file added since). No secret or vulnerability defect exists under any of the three counts.

## 40. External Review Package Verification

`external-review/MILESTONE-039/MILESTONE-039-adf0ec7-external-review.zip` — independently re-verified in this freeze session: SHA-256 `b4f61cfaec8db3f229f38f29929127673ac6f73c35c564bf5a8e2ad94a1ae9e0`, exact match against the reviewed package. `manifest.sha256`: 27 entries, all 27/27 independently re-verified OK. ZIP: 28 entries (27 manifest entries + the manifest file itself), `testzip()` clean, no stray or debris files. `complete.diff` (regenerated against the frozen M038 baseline `35cbdd0...` through the final pushed HEAD `adf0ec7...`) is byte-identical to a live regeneration performed in this freeze session.

## 41. Changed-File Surface

```
A  MILESTONE_039_CONCRETE_APPLICATION_COMMAND_VERTICAL_SLICE_EVIDENCE_PACKAGE_CRITERION_RESULT_RECORDING_MACRO_DESIGN.md
A  MILESTONE_039_CONCRETE_APPLICATION_COMMAND_VERTICAL_SLICE_EVIDENCE_PACKAGE_CRITERION_RESULT_RECORDING_MACRO_IMPLEMENTATION.md
A  MILESTONE_039_CONCRETE_APPLICATION_COMMAND_VERTICAL_SLICE_EVIDENCE_PACKAGE_CRITERION_RESULT_RECORDING_MACRO_SCOPE.md
M  PROJECT_CHECKPOINT.md
M  src/empirical_platform/usecases/__init__.py
A  src/empirical_platform/usecases/record_evidence_package_criterion_result.py
A  tests/contract/test_record_evidence_package_criterion_result_handler_contract.py
A  tests/integration/test_m039_record_evidence_package_criterion_result_usecase.py
A  tests/unit/test_record_evidence_package_criterion_result_usecase.py
```

Independently re-confirmed in this freeze session: exactly nine files, matching the implementation commit's own tree exactly.

## 42. Non-Blocking Observations

**M039-OBS-0001 — pre-existing setuptools deprecation warning.** `python -m build` continues to emit the same pre-existing `SetuptoolsDeprecationWarning` about `project.license` as a TOML table, unrelated to this milestone's code, identical to the warning already documented in M034/M036/M037/M038's own freeze records.

**M039-OBS-0002 — transient tooling friction during initial reviewer setup.** An initial default Docker Compose run encountered a stale local PostgreSQL volume password from a prior, unrelated local setup. Isolated clean PostgreSQL verification (a fresh, disposable container with an explicit, correct password, exactly as this project's own established convention requires) passed, and reviewer cleanup completed.

## 43. Observation Disposition

**M039-OBS-0001:** `ACCEPTED_PREEXISTING_BUILD_WARNING`. No M039 correction required; not touched unless MILESTONE-040 independently requires a packaging-metadata change for its own reasons.

**M039-OBS-0002:** `RESOLVED_BY_ISOLATED_CLEAN_POSTGRESQL_VERIFICATION`. No source, test, package, architecture, or configuration correction required — the canonical, isolated-container evidence path (Sections 32-38) is unaffected and independently re-verified in this freeze session.

Neither observation affects production behavior, owned-collection correctness, optimistic concurrency, PostgreSQL correctness, architecture, package integrity, or freeze eligibility.

## 44. No-Scope-Creep Declaration

No `add_artifact_reference`/`seal`/`invalidate`/`start_collection` call; no `Review` work; no retry policy; no composition root, registry, dispatcher, mediator, service locator, or DI framework; no transport/API layer; no schema/migration change; no MILESTONE-040 work exists anywhere in this milestone.

## 45. Preserved M020-M038 Authority

No change to any M020-M038 frozen contract, source file, test, or governance document. All prior authority remains exactly as previously frozen.

## 46. Owner Freeze Declaration

**M039 MACRO MILESTONE APPROVED_AND_FROZEN.** The implementation delivered in commits `9ec849a`/`adf0ec7`, exactly as verified in Sections 31-40 above, is the final, frozen implementation of MILESTONE-039.

## 47. Deferred Work

`add_artifact_reference()`; `seal()`; `invalidate()`; `Review` creation and retrieval; retry-on-conflict policy; any composition-root abstraction beyond direct binding; MILESTONE-040 and beyond.

## 48. M040 Boundary

This freeze authorizes work through MILESTONE-039 only. No MILESTONE-040 capability, terminology, sequencing decision, or forward commitment is made anywhere in this document. Section 47's "Deferred Work" is descriptive of currently-visible future candidates, not a binding selection of MILESTONE-040's scope.

## 49. Final Status

**M039 APPROVED_AND_FROZEN** — scope, design, and implementation, at every stage.

M040: NOT_STARTED. M041: NOT_STARTED.

## 50. Next Permitted Action

**MILESTONE-040 COMPLETE MACRO MILESTONE MISSION.**
