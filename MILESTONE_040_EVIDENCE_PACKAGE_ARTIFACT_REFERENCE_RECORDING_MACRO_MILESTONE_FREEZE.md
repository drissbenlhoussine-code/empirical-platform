# MILESTONE-040 - EvidencePackage Artifact-Reference Recording Macro Milestone Freeze

## 1. Document Status

**Status: FINAL — OWNER FROZEN**

This document is the Owner Freeze record for MILESTONE-040, the fifth milestone produced under the Macro Milestone Protocol (M035 implementation freeze, Section 49; PROJECT_CHECKPOINT.md Section 31). It is authoritative.

## 2. Milestone Identity

MILESTONE-040 — Concrete Application Command Vertical Slice: EvidencePackage Artifact-Reference Recording.

## 3. Repository Authority

| Field | Value |
| --- | --- |
| Repository | `C:\Users\LuxSy\Documents\trading` |
| Branch | `master` |
| HEAD at freeze | `a0f0f14713c7243911061467cdb25516d4a467f2` |

## 4. Frozen Predecessor Chain

M020-M039 all `APPROVED_AND_FROZEN` at every stage. M039 Owner Freeze: `MILESTONE_039_EVIDENCE_PACKAGE_CRITERION_RESULT_RECORDING_MACRO_MILESTONE_FREEZE.md`, freeze commit `e7c1ae10bea6eada60a6ed4aa39cffa2b902bf6c`, hash-recording commit `0fc2e29b4420ec51b0fcda56d0d3892702d1d8ed`.

## 5. Macro Scope Authority

`MILESTONE_040_CONCRETE_APPLICATION_COMMAND_VERTICAL_SLICE_EVIDENCE_PACKAGE_ARTIFACT_REFERENCE_RECORDING_MACRO_SCOPE.md` — one concrete command recording an `ArtifactReference` on an existing, `COLLECTING` `EvidencePackage`, via `EvidencePackage.add_artifact_reference()`. Selected after a fresh architecture inventory found `add_artifact_reference()` the only remaining `COLLECTING`-reachable capability with zero application-layer proof, and after determining `seal()` was **not independently reachable** this milestone (its own precondition requires a non-empty `artifact_references` collection, which no frozen command could produce before this milestone) and Review creation was, for a third time, deliberately rejected on architectural-leverage grounds rather than merely because its FK exists.

## 6. Macro Design Authority

`MILESTONE_040_CONCRETE_APPLICATION_COMMAND_VERTICAL_SLICE_EVIDENCE_PACKAGE_ARTIFACT_REFERENCE_RECORDING_MACRO_DESIGN.md` — a three-field command (`identity`, `expected_persisted_version`, `value`), the simplest of any milestone to date since `ArtifactReference` carries no `evidence_package_id` field and therefore raises no ownership-derivation question (unlike M039); and, as the central load-bearing decision, a **genuine** deterministic-conflict mechanism (design Section 6) — the exact reverse pairing of M039's own — using the now-frozen `add_criterion_result()` as the interfering write.

## 7. Implementation Commit

`912bfea8179d762281fab5c79aa93975792177d9` (`feat: implement M040 EvidencePackage artifact-reference recording usecase`).

## 8. Finalization Commit

`a0f0f14713c7243911061467cdb25516d4a467f2` (`docs: finalize M040 macro milestone review package`) — narrow, checkpoint-only, recorded the implementation commit's own hash. No production behavior changed.

## 9. Independent Review Authority

The independent hostile review verified: synchronized repository truth; correct M039 freeze ordering; exactly nine authorized M040 tracked changes; one `ArtifactReference`-recording capability only; correct command and handler contracts; one `get()`, one artifact mutation, and one `save()`; exact identity-object pass-through; caller-supplied expected persisted version; exact `SaveResult` propagation; correct duplicate-artifact behavior; criterion-result preservation; genuine live PostgreSQL optimistic-concurrency conflict; a state-preserving interfering `add_criterion_result()` write; absence of any second production capability; zero architecture-checker change; complete tests, regression, typing, build, security, governance, manifest, and ZIP integrity; M020-M039 predecessor preservation; absence of any M041 work.

## 10. Review Decision

**M040 MACRO MILESTONE APPROVED WITH NON-BLOCKING OBSERVATIONS.** No CRITICAL, MAJOR, or blocking MINOR finding remains.

## 11. Owner Approval

The owner formally freezes the M040 macro milestone via this document.

**M040 MACRO MILESTONE APPROVED_AND_FROZEN.**

**M040 APPROVED_AND_FROZEN** — scope, design, and implementation, at every stage, frozen as one consolidated unit per the Macro Milestone Protocol.

## 12. Frozen Production Capability

Exactly one: recording of an `ArtifactReference` on an existing, `COLLECTING` `EvidencePackage`. No `add_criterion_result`, `seal`, `invalidate`, `start_collection`, or any second command/capability.

## 13. Frozen Command Contract

```python
@dataclass(frozen=True, slots=True)
class RecordEvidencePackageArtifactReferenceCommand:
    identity: DomainIdentity[EvidencePackageId]
    expected_persisted_version: AggregateVersion
    value: str
```

Exactly three fields, independently re-verified via `set(RecordEvidencePackageArtifactReferenceCommand.__slots__)`. No `evidence_package_id` field exists — confirmed correct, since `ArtifactReference` itself carries no such field.

## 14. Frozen Handler Contract

```python
class RecordEvidencePackageArtifactReferenceHandler:
    __slots__ = ("_evidence_package_repository",)

    def __init__(self, *, evidence_package_repository: EvidencePackageRepository) -> None:
        self._evidence_package_repository = evidence_package_repository

    def handle(self, command: RecordEvidencePackageArtifactReferenceCommand) -> SaveResult:
        loaded = self._evidence_package_repository.get(command.identity)
        package = loaded.aggregate
        package.add_artifact_reference(ArtifactReference(value=command.value))
        return self._evidence_package_repository.save(
            package, expected_persisted_version=command.expected_persisted_version
        )
```

Sole dependency: `EvidencePackageRepository`. No `RunRepository`, no `CampaignRepository` — independently re-confirmed in this freeze via direct grep (Section 38).

## 15. Frozen Identity Semantics

`command.identity` (a full `DomainIdentity[EvidencePackageId]`) is passed to `EvidencePackageRepository.get()` unchanged — independently re-verified via source inspection.

## 16. Frozen Expected-Version Semantics

`command.expected_persisted_version` — never `loaded.persisted_version` — is passed to `save()`. Independently re-verified via source inspection and via the frozen unit test `test_save_receives_command_version_not_loaded_persisted_version`, which constructs the two values as deliberately different and confirms only the command's own value reaches `save()`.

## 17. Frozen Load–Mutate–Save Sequence

1. Receive `RecordEvidencePackageArtifactReferenceCommand`.
2. Call `evidence_package_repository.get(command.identity)` exactly once.
3. Construct exactly one `ArtifactReference(value=command.value)`.
4. Call `package.add_artifact_reference(reference)` exactly once.
5. Call `evidence_package_repository.save(package, expected_persisted_version=command.expected_persisted_version)` exactly once.
6. Return the exact `SaveResult`, unchanged.

Independently re-verified in this freeze: exactly one `.get(` and exactly one `.save(` in the production module; no `.add(` call; no criterion-result production command; no second artifact mutation; no retry; no Run or Review lookup.

## 18. Frozen Result Contract

`SaveResult` (`operation`, `persisted_version`), returned exactly as received from `EvidencePackageRepository.save()` — no wrapping, no field extraction, no reconstruction.

## 19. ArtifactReference Construction

Exactly one `ArtifactReference` constructed per invocation, from `command.value` alone. `ArtifactReference.__post_init__` (frozen since M020) independently validates that `value` is a non-empty string — the handler duplicates none of this validation. Unlike M039's `CriterionResult`, no ownership-derivation step exists, since `ArtifactReference` has no `evidence_package_id` field.

## 20. Artifact Collection Semantics

A successful `add_artifact_reference()` call appends exactly one `ArtifactReference` to `EvidencePackage._artifact_references`, preserves the current lifecycle state (`COLLECTING`), and advances `version` by exactly one — independently confirmed by the frozen unit test `test_add_artifact_reference_called_with_exact_command_value` and the live PostgreSQL golden-path test.

## 21. Criterion Collection Preservation

The `criterion_results` collection is never modified by this milestone's handler — independently confirmed by the frozen unit test `test_no_criterion_result_seal_or_start_collection_call_occurs` (`package.criterion_results == ()`) and by the live PostgreSQL conflict test, which independently confirms the interfering writer's `CriterionResult` remains durably present and unaffected after the command-under-test's failed attempt.

## 22. Aggregate-Version Semantics

`EvidencePackage.version` is genuine aggregate domain state, advancing when `add_artifact_reference()` is called. It is never exposed on the command or the `SaveResult`; the caller-supplied `expected_persisted_version` is deliberately distinct and independently supplied (Section 16).

## 23. Persisted-Version Semantics

`LoadedAggregate.persisted_version` (the repository-loaded concurrency token at `get()` time) is read but never substituted for `command.expected_persisted_version` when calling `save()` — confirmed by the frozen unit test cited in Section 16.

## 24. Duplicate Artifact Behavior

`EvidencePackage.add_artifact_reference()` raises a domain `ValueError` ("artifact reference already exists") when the supplied `value` already exists in `artifact_references`, propagated transparently with `save()` never reached — proven at unit level and genuinely reproduced against real PostgreSQL (Section 34).

## 25. Not-Found Behavior

`AggregateNotFound` raised by `EvidencePackageRepository.get()` for a `DomainIdentity` with no persisted `EvidencePackage`, propagated transparently — proven at unit level (fake repository) and genuinely reproduced against real PostgreSQL.

## 26. Invalid-State Behavior

`EvidencePackage.add_artifact_reference()` raises a domain `ValueError` ("may be added only while COLLECTING") when the current state is not `COLLECTING`, propagated transparently with `save()` never reached — proven at unit level and genuinely reproduced against real PostgreSQL (Section 33).

## 27. Arbitrary Error Semantics

Transparent, unchanged propagation of `OptimisticConcurrencyConflict` and any arbitrary `get()`/`save()` failure. No handler-level `try`/`except`.

## 28. Validation Ownership

`DomainIdentity`/`EvidencePackageId`/`AggregateVersion` own their own format validation at construction. `ArtifactReference.__post_init__` owns its own field validation. `EvidencePackage.add_artifact_reference()` owns its own state-precondition and duplicate-`value` validation. The handler performs no additional validation and duplicates none of the above.

## 29. Transaction Non-Ownership

No application-level transaction orchestration — one repository-owned `save()` call, already atomic via its own `unit_of_work()`.

## 30. CommandEntryPoint Binding

Test-only direct construction, mirroring every prior command milestone. No production composition root.

## 31. Architecture Preservation

**Zero architecture-checker change.** Independently re-verified in this freeze: `git diff 0fc2e29..a0f0f14 -- tools/check_architecture.py tests/fixtures/` is empty, and `python tools/check_architecture.py .` passes at exit 0.

## 32. PostgreSQL Success Evidence

Independently reproduced against a fresh disposable `postgres:17` container in this freeze session: golden-path recording via `CommandEntryPoint`, `SaveResult.persisted_version == AggregateVersion(2)`, independently reloaded state with exactly one `ArtifactReference` matching the recorded `value`, `state` still `COLLECTING`.

## 33. PostgreSQL Invalid-State Evidence

Independently reproduced against real PostgreSQL in this freeze session: an `EvidencePackage` still `INITIALIZED` rejects `add_artifact_reference()` with a domain `ValueError` before `save()` is ever reached.

## 34. PostgreSQL Duplicate-Artifact Evidence

Independently reproduced against real PostgreSQL in this freeze session: a second command carrying an already-recorded `value` raises a domain `ValueError` before the second `save()` is ever reached.

## 35. PostgreSQL Missing-Aggregate Evidence

Independently reproduced against real PostgreSQL in this freeze session: retrieval of a never-persisted `DomainIdentity` raises `AggregateNotFound`.

## 36. Real Optimistic-Concurrency Evidence

Independently reproduced against real PostgreSQL in this freeze session: `test_stale_expected_version_raises_genuine_optimistic_concurrency_conflict` — a genuine `OptimisticConcurrencyConflict`, not a domain `ValueError`, confirmed by exception type inspection. Post-attempt reload independently confirmed: the interfering writer's `CriterionResult` is durably persisted (the only change beyond the initial `start_collection()` transition), and the losing writer's `ArtifactReference` was never persisted (`artifact_references == ()`).

## 37. Interfering Criterion-Result Evidence

Recorded permanently, the exact real-conflict sequence, independently re-verified against the live integration test in this freeze session:

1. `EvidencePackage` is `COLLECTING`.
2. An independent writer loads a separate aggregate instance for the same identity.
3. The independent writer adds a legitimate `CriterionResult` via `add_criterion_result()`.
4. Lifecycle state remains `COLLECTING` (unchanged by this method).
5. The aggregate's version advances by exactly one.
6. The independent writer saves using the version it loaded with.
7. The durable `persisted_version` advances to reflect the interfering write.
8. The M040 command under test retains the version captured *before* the interference — now stale.
9. The handler reloads the latest, `COLLECTING` aggregate.
10. `add_artifact_reference()` remains domain-valid against this current state.
11. The handler reaches `evidence_package_repository.save()`.
12. The repository's version guard compares the stale `expected_persisted_version` against the actual durable version.
13. `OptimisticConcurrencyConflict` is raised.
14. No retry or second `save()` attempt occurs anywhere in the frozen handler.
15. The criterion result remains persisted and authoritative.
16. The `ArtifactReference` from the losing writer is never persisted.

**Explicitly recorded:** no direct SQL fabrication was used; no aggregate internals were patched; no invalid row was inserted; no second production command was introduced; `add_criterion_result()` was used only as legitimate integration-test interference setup, the exact reverse pairing of M039's own use of `add_artifact_reference()`, and is never invoked as an interfering write by any production code in this milestone.

## 38. Full PostgreSQL Regression

Independently reproduced in this freeze session against a fresh disposable container: `pytest tests/integration/` — 152 passed, 6 skipped; `pytest -q` (PostgreSQL opt-in, full suite) — 851 passed, 6 skipped, 92.92% coverage. Both exactly match the implementation session's own figures — zero drift. Hostile self-audit grep independently re-confirmed: zero genuine prohibited-pattern matches in `record_evidence_package_artifact_reference.py` (one docstring "for" false positive); no `RunRepository`/`CampaignRepository`/`Review` reference; no `add_criterion_result`/`seal`/`invalidate`/`start_collection` call.

An additional targeted regression grouping cited by the independent review — `test_m023_postgres_repositories.py` combined with the full run of vertical-slice suites M030 through M040 — was independently reproduced exactly in this freeze session: **74 passed**, confirming zero regression across every predecessor Campaign/Run/EvidencePackage integration suite plus this milestone's own 6 tests.

## 39. Ruff/Mypy/Build/Security Evidence

Independently re-run in this freeze session under the canonical `.venv` interpreter (Python 3.13.14): `ruff format --check .`/`ruff check .` clean, 240 files formatted; canonical `mypy` clean, 97 source files; `pytest -q -m "not integration"` — 699 passed, 158 deselected, 84.00% coverage; `python -m build --wheel` succeeds; `python -m pip_audit` reports no known vulnerabilities. Secret-scan counts recorded as explicitly time-scoped values: 426 at implementation-evidence-capture time; 427 independently reproduced at final revalidation, exactly matching the independent review's own cited figure; 428 independently reproduced at this freeze document's own creation time (one further file added since).

## 40. External Review Package Verification

`external-review/MILESTONE-040/MILESTONE-040-a0f0f14-external-review.zip` — independently re-verified in this freeze session: SHA-256 `840a7b1fb9e1d2d513ca407b05c739c8f4a41b8c8b2d06d9147d2fd98c3c1b2f`, exact match against the reviewed package. `manifest.sha256`: 27 entries, all 27/27 independently re-verified OK. ZIP: 28 entries (27 manifest entries + the manifest file itself), `testzip()` clean, no stray or debris files. `complete.diff` (regenerated against the frozen M039 baseline `0fc2e29...` through the final pushed HEAD `a0f0f14...`) is byte-identical to a live regeneration performed in this freeze session.

## 41. Changed-File Surface

```
A  MILESTONE_040_CONCRETE_APPLICATION_COMMAND_VERTICAL_SLICE_EVIDENCE_PACKAGE_ARTIFACT_REFERENCE_RECORDING_MACRO_DESIGN.md
A  MILESTONE_040_CONCRETE_APPLICATION_COMMAND_VERTICAL_SLICE_EVIDENCE_PACKAGE_ARTIFACT_REFERENCE_RECORDING_MACRO_IMPLEMENTATION.md
A  MILESTONE_040_CONCRETE_APPLICATION_COMMAND_VERTICAL_SLICE_EVIDENCE_PACKAGE_ARTIFACT_REFERENCE_RECORDING_MACRO_SCOPE.md
M  PROJECT_CHECKPOINT.md
M  src/empirical_platform/usecases/__init__.py
A  src/empirical_platform/usecases/record_evidence_package_artifact_reference.py
A  tests/contract/test_record_evidence_package_artifact_reference_handler_contract.py
A  tests/integration/test_m040_record_evidence_package_artifact_reference_usecase.py
A  tests/unit/test_record_evidence_package_artifact_reference_usecase.py
```

Independently re-confirmed in this freeze session: exactly nine files, matching the implementation commit's own tree exactly.

## 42. Non-Blocking Observation

**M040-OBS-0001 — pre-existing setuptools deprecation warning.** `python -m build` continues to emit the same pre-existing `SetuptoolsDeprecationWarning` about `project.license` as a TOML table, unrelated to this milestone's code, identical to the warning already documented in M034/M036/M037/M038/M039's own freeze records.

## 43. Observation Disposition

**M040-OBS-0001:** `ACCEPTED_PREEXISTING_BUILD_WARNING`. No M040 correction required; not touched unless MILESTONE-041 independently requires a packaging-metadata change for its own reasons.

This observation does not affect production behavior, artifact collection correctness, optimistic concurrency, PostgreSQL correctness, architecture, package integrity, predecessor authority, or freeze eligibility.

## 44. No-Scope-Creep Declaration

No `add_criterion_result`/`seal`/`invalidate`/`start_collection` call; no `Review` work; no retry policy; no composition root, registry, dispatcher, mediator, service locator, or DI framework; no transport/API layer; no schema/migration change; no MILESTONE-041 work exists anywhere in this milestone.

## 45. Preserved M020-M039 Authority

No change to any M020-M039 frozen contract, source file, test, or governance document. All prior authority remains exactly as previously frozen.

## 46. Owner Freeze Declaration

**M040 MACRO MILESTONE APPROVED_AND_FROZEN.** The implementation delivered in commits `912bfea`/`a0f0f14`, exactly as verified in Sections 31-40 above, is the final, frozen implementation of MILESTONE-040.

## 47. Deferred Work

`seal()`; `invalidate()`; `Review` creation and retrieval; retry-on-conflict policy; any composition-root abstraction beyond direct binding; MILESTONE-041 and beyond.

## 48. M041 Boundary

This freeze authorizes work through MILESTONE-040 only. No MILESTONE-041 capability, terminology, sequencing decision, or forward commitment is made anywhere in this document. Section 47's "Deferred Work" is descriptive of currently-visible future candidates, not a binding selection of MILESTONE-041's scope.

## 49. Final Status

**M040 APPROVED_AND_FROZEN** — scope, design, and implementation, at every stage.

M041: NOT_STARTED. M042: NOT_STARTED.

## 50. Next Permitted Action

**MILESTONE-041 COMPLETE MACRO MILESTONE MISSION.**
