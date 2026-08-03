# MILESTONE-037 - EvidencePackage Retrieval Macro Milestone Freeze

## 1. Document Status

**Status: FINAL — OWNER FROZEN**

This document is the Owner Freeze record for MILESTONE-037, the second milestone produced under the Macro Milestone Protocol (M035 implementation freeze, Section 49; PROJECT_CHECKPOINT.md Section 31). It is authoritative.

## 2. Milestone Identity

MILESTONE-037 — Concrete Application Query Vertical Slice: EvidencePackage Retrieval.

## 3. Repository Authority

| Field | Value |
| --- | --- |
| Repository | `C:\Users\LuxSy\Documents\trading` |
| Branch | `master` |
| HEAD at freeze | `10ea710f9c010e093774d02e6c05717cf3a873e2` |

## 4. Frozen Predecessor Chain

M020-M036 all `APPROVED_AND_FROZEN` at every stage. M036 Owner Freeze: `MILESTONE_036_EVIDENCE_PACKAGE_CREATION_MACRO_MILESTONE_FREEZE.md`, freeze commit `8c5f04cb2e4b32749fc6ba04806b33ac38c0216f`, hash-recording commit `ce65d890404c975a10821224c501cd386fd63e6f`.

## 5. Macro Scope Authority

`MILESTONE_037_CONCRETE_APPLICATION_QUERY_VERTICAL_SLICE_EVIDENCE_PACKAGE_RETRIEVAL_MACRO_SCOPE.md` — one concrete query retrieving an existing `EvidencePackage` by full identity, via `EvidencePackageRepository.get()`. Selected after a fresh architecture inventory found `EvidencePackage`'s `get()`/`save()` verbs both still unproven at the application layer, and after independently evaluating 8 candidates — including the genuinely FK-viable Review creation — rejecting the latter to preserve the project's own twice-repeated per-aggregate create-retrieve-transition completion cadence (Campaign M030-M032; Run M033-M035).

## 6. Macro Design Authority

`MILESTONE_037_CONCRETE_APPLICATION_QUERY_VERTICAL_SLICE_EVIDENCE_PACKAGE_RETRIEVAL_MACRO_DESIGN.md` — caller-supplied full `DomainIdentity[EvidencePackageId]` query identity (mirrors `GetRunQuery`); bounded `EvidencePackageSnapshot(identity, run_id, state)` result contract, deliberately excluding `version`/`persisted_version`/`criterion_results`/`artifact_references`/`transition_history`, mirroring `RunSnapshot`'s own established exclusions.

## 7. Implementation Commit

`d041d94492f678f049ae48dfb5edd4ded1f76c39` (`feat: implement M037 EvidencePackage retrieval usecase`).

## 8. Finalization Commit

`10ea710f9c010e093774d02e6c05717cf3a873e2` (`docs: finalize M037 macro milestone review package`) — narrow, checkpoint-only, recorded the implementation commit's own hash. No production behavior changed.

## 9. Independent Review Authority

The independent hostile review verified: synchronized repository truth; proper M036 freeze ordering; exactly nine M037 tracked changes; one EvidencePackage retrieval capability only; full `DomainIdentity[EvidencePackageId]` query model; exactly one `EvidencePackageRepository.get()`; bounded immutable `EvidencePackageSnapshot`; transparent `AggregateNotFound`/error propagation; absence of mutation, save, second lookup, cache, or retry; zero architecture-checker change; live PostgreSQL retrieval and missing-identity behavior; current-HEAD `EvidencePackage` repository reconstruction regression; complete regression, typing, build, security, governance, manifest, and ZIP integrity; M020-M036 preservation; absence of any M038 work.

## 10. Review Decision

**M037 MACRO MILESTONE APPROVED WITH NON-BLOCKING OBSERVATIONS.** No CRITICAL, MAJOR, or blocking MINOR finding remains.

## 11. Owner Approval

The owner formally freezes the M037 macro milestone via this document.

**M037 MACRO MILESTONE APPROVED_AND_FROZEN.**

**M037 APPROVED_AND_FROZEN** — scope, design, and implementation, at every stage, frozen as one consolidated unit per the Macro Milestone Protocol.

## 12. Frozen Production Capability

Exactly one: retrieval of an existing `EvidencePackage` by full identity. No creation, mutation, `save()`, listing, filtering, or pagination.

## 13. Frozen Query Contract

```python
@dataclass(frozen=True, slots=True)
class GetEvidencePackageQuery:
    identity: DomainIdentity[EvidencePackageId]
```

## 14. Frozen Handler Contract

```python
class GetEvidencePackageHandler:
    __slots__ = ("_evidence_package_repository",)

    def __init__(self, *, evidence_package_repository: EvidencePackageRepository) -> None:
        self._evidence_package_repository = evidence_package_repository

    def handle(self, query: GetEvidencePackageQuery) -> EvidencePackageSnapshot:
        loaded = self._evidence_package_repository.get(query.identity)
        return EvidencePackageSnapshot(
            identity=loaded.aggregate.identity,
            run_id=loaded.aggregate.run_id,
            state=loaded.aggregate.state,
        )
```

Sole dependency: `EvidencePackageRepository`. No `RunRepository`, no `CampaignRepository` — independently re-confirmed in this freeze via direct grep (Section 31).

## 15. Frozen Identity Semantics

Caller-supplied full `DomainIdentity[EvidencePackageId]` (governance ID and runtime ID both required), passed unchanged to `EvidencePackageRepository.get()`. No partial-identity lookup exists. Mirrors `GetRunQuery`/`GetCampaignQuery` exactly.

## 16. Frozen Retrieval Sequence

1. Receive `GetEvidencePackageQuery`.
2. Call `evidence_package_repository.get(query.identity)` exactly once, with the exact identity object unchanged.
3. Construct exactly one `EvidencePackageSnapshot` from `loaded.aggregate`.
4. Return the snapshot.

No `add()`/`save()` call of any kind. No second `get()` call. No Run or Review lookup.

## 17. Frozen Snapshot Contract

`EvidencePackageSnapshot(identity: DomainIdentity[EvidencePackageId], run_id: RunId, state: EvidencePackageLifecycleState)` — exactly three fields, verified via `set(EvidencePackageSnapshot.__slots__) == {"identity", "run_id", "state"}`.

## 18. Snapshot Exclusions

`EvidencePackageSnapshot` is a bounded application read result. It does not expose: the mutable `EvidencePackage` aggregate itself; `LoadedAggregate`; `persisted_version`; `EvidencePackage.version`; `transition_history`; `criterion_results`; `artifact_references`; or any other owned collection. This holds even when the source aggregate has non-empty values for all of the above — independently proven by `tests/unit/test_get_evidence_package_usecase.py::test_criterion_results_artifact_references_and_transition_history_are_not_exposed` and `::test_aggregate_version_and_persisted_version_are_distinct_and_neither_leaks`.

## 19. Aggregate-Version Semantics

`EvidencePackage.version` is genuine aggregate domain state, advancing via lifecycle transitions (`start_collection`, `add_criterion_result`, `add_artifact_reference`, `seal`, `invalidate`). It is never exposed on `EvidencePackageSnapshot`.

## 20. Persisted-Version Semantics

`LoadedAggregate.persisted_version` is separate repository-loaded concurrency metadata, distinct from `EvidencePackage.version`. The frozen unit test constructs the two as deliberately different values and confirms neither appears on the snapshot. Not exposed, and not needed by this milestone's read-only capability.

## 21. Owned-Collection Evidence Boundary

**Precise scope, not overstated:** the M037-specific PostgreSQL integration test (`test_criterion_result_and_artifact_reference_tables_load_without_error`) proves that `PostgresEvidencePackageRepository.get()` loads the `evidence_package_criterion_result`/`evidence_package_artifact_reference`/`evidence_package_transition` tables without error for a **freshly created EvidencePackage, which has none of any** — an empty-collection regression only. It does not, by itself, prove non-empty owned-collection reconstruction. That broader guarantee is independently and separately proven by the pre-existing, current-HEAD `tests/integration/test_m023_postgres_repositories.py` regression suite (frozen since M023), re-run in this freeze session (30 passed, combined with the 4 M037 tests, against a fresh disposable container). M037 correctly relies on that pre-existing M023 proof rather than re-proving it, and correctly does not expose those collections in the snapshot regardless (Section 18).

## 22. Not-Found Behavior

`AggregateNotFound` raised by `EvidencePackageRepository.get()` for a `DomainIdentity` with no persisted `EvidencePackage`, propagated transparently — proven at unit level (fake repository) and genuinely reproduced against real PostgreSQL (no seeded row for the queried identity).

## 23. Arbitrary Error Semantics

Transparent, unchanged propagation of `InvalidPersistedAggregateState` and any arbitrary repository exception. No handler-level `try`/`except`.

## 24. Validation Ownership

`DomainIdentity`/`EvidencePackageId` own identity-shape validation at construction (already frozen since M020). The handler performs no additional validation.

## 25. Transaction Non-Ownership

No application-level transaction orchestration — one repository-owned `get()` call.

## 26. QueryEntryPoint Binding

Test-only direct construction, mirroring every prior query milestone. No production composition root.

## 27. Architecture Preservation

**Zero architecture-checker change.** `usecases` already had `evidence` in `ALLOWED["usecases"]` since M036; this read-only query uses an already-permitted import edge. Independently re-verified in this freeze: `git diff` against `tools/check_architecture.py` for the M037 commit range is empty, and `python tools/check_architecture.py .` passes at exit 0.

## 28. Unit and Contract Evidence

Independently re-collected in this freeze session: `tests/unit/test_get_evidence_package_usecase.py` — 18 tests; `tests/contract/test_get_evidence_package_handler_contract.py` — 3 tests; `tests/integration/test_m037_get_evidence_package_usecase.py` — 4 tests. **Total: 25 M037-specific tests.** (See Section 36 for correction of a miscounted "24" total in the implementation document's own summary line.)

## 29. PostgreSQL Success Evidence

Independently reproduced against a fresh disposable `postgres:17` container in this freeze session: golden-path retrieval via `QueryEntryPoint`, matching `identity`/`run_id`/`state == INITIALIZED`, exact three-field snapshot shape.

## 30. PostgreSQL Not-Found Evidence

Independently reproduced against real PostgreSQL in this freeze session: retrieval of a never-persisted `DomainIdentity` raises `AggregateNotFound`.

## 31. Repository Reconstruction Regression

Independently re-run in this freeze session against a fresh disposable container: `tests/integration/test_m023_postgres_repositories.py` combined with `tests/integration/test_m037_get_evidence_package_usecase.py` — **30 passed**, confirming zero regression in the frozen M023 `PostgresEvidencePackageRepository` reconstruction path. Hostile self-audit grep independently re-confirmed in this freeze: zero genuine prohibited-pattern matches in `get_evidence_package.py` (one docstring "for one" false positive); exactly one `.get(` call; no `RunRepository`/`CampaignRepository` reference.

## 32. Full PostgreSQL Regression

Independently reproduced in this freeze session against a fresh disposable container: `pytest tests/integration/` — 136 passed, 6 skipped; `pytest -q` (PostgreSQL opt-in, full suite) — 760 passed, 6 skipped, 92.78% coverage. Both exactly match the implementation session's own figures — zero drift.

## 33. Ruff/Mypy/Build/Security Evidence

Independently re-run in this freeze session under the canonical `.venv` interpreter (Python 3.13.14): `ruff format --check .`/`ruff check .` clean, 228 files formatted; canonical `mypy` clean, 94 source files; `pytest -q -m "not integration"` — 624 passed, 142 deselected, 83.68% coverage; `python -m build --wheel` succeeds; `python -m pip_audit` reports no known vulnerabilities.

**Disclosed tooling artifact (non-blocking, see Section 34):** one non-canonical invocation under system Python 3.14 produced a spurious `ruff format --check` finding ("8 files would be reformatted") not reproducible under the canonical `.venv`; the canonical rerun is clean.

## 34. External Review Package Verification

`external-review/MILESTONE-037/MILESTONE-037-10ea710-external-review.zip` — independently re-verified in this freeze session: SHA-256 `a696c80e927bc391d7cee9cf558a0be7a8ac1d11e7323adffe0cd8e6169f92d9`, exact match against the reviewed package. `manifest.sha256`: 27 entries, all 27/27 independently re-verified OK. ZIP: 28 entries (27 manifest entries + the manifest file itself), `testzip()` clean, no stray or debris files. `complete.diff` (regenerated against the frozen M036 baseline `ce65d890...` through the final pushed HEAD `10ea710...`) is byte-identical to a live regeneration performed in this freeze session.

## 35. Changed-File Surface

```
A  MILESTONE_037_CONCRETE_APPLICATION_QUERY_VERTICAL_SLICE_EVIDENCE_PACKAGE_RETRIEVAL_MACRO_DESIGN.md
A  MILESTONE_037_CONCRETE_APPLICATION_QUERY_VERTICAL_SLICE_EVIDENCE_PACKAGE_RETRIEVAL_MACRO_IMPLEMENTATION.md
A  MILESTONE_037_CONCRETE_APPLICATION_QUERY_VERTICAL_SLICE_EVIDENCE_PACKAGE_RETRIEVAL_MACRO_SCOPE.md
M  PROJECT_CHECKPOINT.md
M  src/empirical_platform/usecases/__init__.py
A  src/empirical_platform/usecases/get_evidence_package.py
A  tests/contract/test_get_evidence_package_handler_contract.py
A  tests/integration/test_m037_get_evidence_package_usecase.py
A  tests/unit/test_get_evidence_package_usecase.py
```

Independently re-confirmed in this freeze session: exactly nine files, matching the implementation commit's own tree exactly.

## 36. Non-Blocking Findings

**M037-OBS-0001 — miscounted test total in the implementation document.** `MILESTONE_037_..._MACRO_IMPLEMENTATION.md` Section 10 states "**Added** (24 tests, all passing)" as its summary line, but the three itemized sub-counts immediately below it (18 unit + 3 contract + 4 integration) sum to **25**, not 24 — a genuine arithmetic slip in the summary line, independently confirmed by fresh collection in this freeze session (18/3/4/25 exactly).

**M037-OBS-0002 — PostgreSQL eager-load evidence-boundary precision.** The implementation document's phrase "eager-load regression" for the M037-specific integration test could be read as proving non-empty owned-collection reconstruction; in fact that test only exercises the empty-collection case for a freshly created `EvidencePackage`. Non-empty owned-collection reconstruction is proven separately by the pre-existing, current-HEAD M023 repository regression suite (Section 21/31), not by M037's own test.

**M037-OBS-0003 — secret-scan target count time-scoping.** Recorded values across three distinct points in time: 402 targets at implementation-evidence-capture time (before the implementation governance document existed on disk); 403 targets independently reproduced twice in this freeze session (after that document was added and committed); a cited final-review figure of 411 targets that this freeze session was **unable to independently reproduce** with any tested command grouping against the current pushed HEAD. Recorded as an unreconciled, non-blocking documentation discrepancy — security itself passed in every run (`pip_audit`: no known vulnerabilities; no secret defect of any kind in any run), so this does not affect freeze eligibility.

**M037-OBS-0004 — pre-existing setuptools deprecation warning.** `python -m build` continues to emit the same pre-existing `SetuptoolsDeprecationWarning` about `project.license` as a TOML table, unrelated to this milestone's code, identical to the warning already documented in M034's and M036's own freeze records.

## 37. Finding Disposition

**M037-OBS-0001:** `RESOLVED_BY_FREEZE_RECORD_COUNT_CLARIFICATION`. The correct, independently-verified total is **25 M037-specific tests** (18 unit, 3 contract, 4 integration), as recorded in Section 28 of this freeze. The implementation document's own text is not rewritten (matching this project's standing no-history-rewrite discipline for already-committed governance text); this freeze record is the authoritative corrected figure going forward.

**M037-OBS-0002:** `RESOLVED_BY_PRECISE_EVIDENCE_BOUNDARY`. Section 21 of this freeze records the exact, non-overstated evidence boundary. No test or code change required.

**M037-OBS-0003:** `RESOLVED_BY_TIME_SCOPED_SECURITY_COUNTS`. Section 36 records all three counts as explicitly time-scoped values. The 411 figure is recorded as reported-but-not-independently-reproduced in this freeze session, rather than asserted as freeze-time canonical truth; the independently-reproduced freeze-time value is 403. No security defect exists under any of the three counts.

**M037-OBS-0004:** `ACCEPTED_PREEXISTING_BUILD_WARNING`. No M037 correction required; not touched unless MILESTONE-038 independently requires a packaging-metadata change for its own reasons.

None of the four affects behavior, identity semantics, repository retrieval, PostgreSQL correctness, architecture, package integrity, or freeze eligibility.

## 38. No-Scope-Creep Declaration

No `EvidencePackage` mutation, `save()`, or second command/query; no `Review` work; no retry policy; no composition root, registry, dispatcher, mediator, service locator, or DI framework; no transport/API layer; no schema/migration change; no MILESTONE-038 work exists anywhere in this milestone.

## 39. Preserved M020-M036 Authority

No change to any M020-M036 frozen contract, source file, test, or governance document. All prior authority remains exactly as previously frozen.

## 40. Owner Freeze Declaration

**M037 MACRO MILESTONE APPROVED_AND_FROZEN.** The implementation delivered in commits `d041d94`/`10ea710`, exactly as verified in Sections 27-35 above, is the final, frozen implementation of MILESTONE-037.

## 41. Deferred Work

`EvidencePackage` mutation and `save()` (`start_collection`, `add_criterion_result`, `add_artifact_reference`, `seal`, `invalidate`, guarded by `OptimisticConcurrencyConflict`); `Review` creation and retrieval (still gated behind completing `EvidencePackage`'s own create-retrieve-transition trio, per the project's own established cadence); retry-on-conflict policy; any composition-root abstraction beyond direct binding; MILESTONE-038 and beyond.

## 42. M038 Boundary

This freeze authorizes work through MILESTONE-037 only. No MILESTONE-038 capability, terminology, sequencing decision, or forward commitment is made anywhere in this document. Section 41's "Deferred Work" is descriptive of currently-visible future candidates, not a binding selection of MILESTONE-038's scope.

## 43. Final Status

**M037 APPROVED_AND_FROZEN** — scope, design, and implementation, at every stage.

M038: NOT_STARTED. M039: NOT_STARTED.

## 44. Next Permitted Action

**MILESTONE-038 COMPLETE MACRO MILESTONE MISSION.**
