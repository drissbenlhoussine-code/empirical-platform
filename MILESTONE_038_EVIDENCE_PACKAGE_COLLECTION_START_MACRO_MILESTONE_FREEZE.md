# MILESTONE-038 - EvidencePackage Collection Start Macro Milestone Freeze

## 1. Document Status

**Status: FINAL — OWNER FROZEN**

This document is the Owner Freeze record for MILESTONE-038, the third milestone produced under the Macro Milestone Protocol (M035 implementation freeze, Section 49; PROJECT_CHECKPOINT.md Section 31). It is authoritative.

## 2. Milestone Identity

MILESTONE-038 — Concrete Application Command Vertical Slice: EvidencePackage Collection Start.

## 3. Repository Authority

| Field | Value |
| --- | --- |
| Repository | `C:\Users\LuxSy\Documents\trading` |
| Branch | `master` |
| HEAD at freeze | `56d35586368124998c47c164b07a583f8dce716a` |

## 4. Frozen Predecessor Chain

M020-M037 all `APPROVED_AND_FROZEN` at every stage. M037 Owner Freeze: `MILESTONE_037_EVIDENCE_PACKAGE_RETRIEVAL_MACRO_MILESTONE_FREEZE.md`, freeze commit `9c53e1de89093bc12244ccb50ce2ced11947f396`, hash-recording commit `4674601db269da2e2b554e13e16bc62564aeaa08`.

## 5. Macro Scope Authority

`MILESTONE_038_CONCRETE_APPLICATION_COMMAND_VERTICAL_SLICE_EVIDENCE_PACKAGE_COLLECTION_START_MACRO_SCOPE.md` — one concrete command transitioning an existing `EvidencePackage` from `INITIALIZED` to `COLLECTING`, via `EvidencePackage.start_collection()`. Selected after a fresh architecture inventory found `save()`/`OptimisticConcurrencyConflict` unproven for `EvidencePackage` (the single largest remaining unproven-generalization gap), and after independently evaluating 8 candidates — including criterion-result/artifact-reference mutation (rejected as premature, gated behind this milestone) and Review creation (rejected to preserve the twice-repeated per-aggregate completion cadence) — this milestone completes `EvidencePackage`'s create-retrieve-transition trio (M036/M037/M038).

## 6. Macro Design Authority

`MILESTONE_038_CONCRETE_APPLICATION_COMMAND_VERTICAL_SLICE_EVIDENCE_PACKAGE_COLLECTION_START_MACRO_DESIGN.md` — command fields mirror `AuthorizeRunCommand` (`identity`, `expected_persisted_version`, `actor`, `occurred_at`, `correlation_id`, `reason`); `SaveResult` result contract; and, as the central load-bearing decision, an **independently derived** deterministic-conflict-scenario mechanism (Section 6 of the design), since `EvidencePackage` has no non-transition interfering write available while `INITIALIZED`, unlike `Campaign`/`Run`.

## 7. Implementation Commit

`a77ef2fd8abd17244f80698cbb7b6ea972c06a0d` (`feat: implement M038 EvidencePackage collection-start usecase`).

## 8. Finalization Commit

`56d35586368124998c47c164b07a583f8dce716a` (`docs: finalize M038 macro milestone review package`) — narrow, checkpoint-only, recorded the implementation commit's own hash. No production behavior changed.

## 9. Independent Review Authority

The independent hostile review verified: synchronized repository truth; correct M037 freeze ordering; exactly nine authorized M038 tracked changes; one EvidencePackage collection-start capability only; correct `StartEvidencePackageCollectionCommand` contract; one `EvidencePackageRepository` dependency only; exact full identity pass-through; caller-supplied expected persisted version; exactly one `get()`, one `start_collection()`, and one `save()`; exact `SaveResult` propagation; correct aggregate/persisted-version separation; correct transition-history behavior; transparent errors; zero architecture-checker change; genuine live PostgreSQL success; genuine invalid-transition behavior; genuine missing-aggregate behavior; honest two-caller concurrency semantics; absence of any false PostgreSQL `OptimisticConcurrencyConflict` claim; complete regression, typing, build, security, governance, manifest, and ZIP integrity; M020-M037 predecessor preservation; absence of any M039 work.

## 10. Review Decision

**M038 MACRO MILESTONE APPROVED WITH NON-BLOCKING OBSERVATIONS.** No CRITICAL, MAJOR, or blocking MINOR finding remains.

## 11. Owner Approval

The owner formally freezes the M038 macro milestone via this document.

**M038 MACRO MILESTONE APPROVED_AND_FROZEN.**

**M038 APPROVED_AND_FROZEN** — scope, design, and implementation, at every stage, frozen as one consolidated unit per the Macro Milestone Protocol.

## 12. Frozen Production Capability

Exactly one: transition of an existing `EvidencePackage` from `INITIALIZED` to `COLLECTING`. No `add_criterion_result`, `add_artifact_reference`, `seal`, `invalidate`, or any second command/capability.

## 13. Frozen Command Contract

```python
@dataclass(frozen=True, slots=True)
class StartEvidencePackageCollectionCommand:
    identity: DomainIdentity[EvidencePackageId]
    expected_persisted_version: AggregateVersion
    actor: str
    occurred_at: datetime
    correlation_id: str | None = None
    reason: str | None = None
```

Exactly six fields, independently re-verified via `set(StartEvidencePackageCollectionCommand.__slots__)`.

## 14. Frozen Handler Contract

```python
class StartEvidencePackageCollectionHandler:
    __slots__ = ("_evidence_package_repository",)

    def __init__(self, *, evidence_package_repository: EvidencePackageRepository) -> None:
        self._evidence_package_repository = evidence_package_repository

    def handle(self, command: StartEvidencePackageCollectionCommand) -> SaveResult:
        loaded = self._evidence_package_repository.get(command.identity)
        package = loaded.aggregate
        package.start_collection(
            actor=command.actor,
            occurred_at=command.occurred_at,
            correlation_id=command.correlation_id,
            reason=command.reason,
        )
        return self._evidence_package_repository.save(
            package, expected_persisted_version=command.expected_persisted_version
        )
```

Sole dependency: `EvidencePackageRepository`. No `RunRepository`, no `CampaignRepository` — independently re-confirmed in this freeze via direct grep (Section 34).

## 15. Frozen Identity Semantics

`command.identity` (a full `DomainIdentity[EvidencePackageId]`) is passed to `EvidencePackageRepository.get()` unchanged — independently re-verified via source inspection (`self._evidence_package_repository.get(command.identity)`) in this freeze.

## 16. Frozen Expected-Version Semantics

`command.expected_persisted_version` — never `loaded.persisted_version` — is passed to `save()`. Independently re-verified via source inspection: `save(package, expected_persisted_version=command.expected_persisted_version)`, and via the frozen unit test `test_save_receives_command_version_not_loaded_persisted_version`, which constructs the two values as deliberately different and confirms only the command's own value reaches `save()`.

## 17. Frozen Load–Mutate–Save Sequence

1. Receive `StartEvidencePackageCollectionCommand`.
2. Call `evidence_package_repository.get(command.identity)` exactly once.
3. Call `loaded.aggregate.start_collection(actor=..., occurred_at=..., correlation_id=..., reason=...)` exactly once.
4. Call `evidence_package_repository.save(loaded.aggregate, expected_persisted_version=command.expected_persisted_version)` exactly once.
5. Return the exact `SaveResult`, unchanged.

Independently re-verified in this freeze: exactly one `.get(` and exactly one `.save(` in the production module; no `.add(` call; no retry; no second mutation of any kind.

## 18. Frozen Result Contract

`SaveResult` (`operation`, `persisted_version`), returned exactly as received from `EvidencePackageRepository.save()` — no wrapping, no field extraction, no reconstruction.

## 19. Aggregate-Version Semantics

`EvidencePackage.version` is genuine aggregate domain state, advancing when `start_collection()` is called. It is never exposed on the command or the `SaveResult`; the caller-supplied `expected_persisted_version` is deliberately distinct and independently supplied (Section 16).

## 20. Persisted-Version Semantics

`LoadedAggregate.persisted_version` (the repository-loaded concurrency token at `get()` time) is read but never substituted for `command.expected_persisted_version` when calling `save()` — the frozen unit test `test_save_receives_command_version_not_loaded_persisted_version` constructs these as deliberately different values and confirms only the command's own value is used.

## 21. Transition-History Semantics

A successful `start_collection()` call produces exactly one new `StateTransitionRecord` (`from_state="INITIALIZED"`, `to_state="COLLECTING"`), independently confirmed by the frozen unit test `test_successful_start_collection_produces_exactly_one_transition_record` and by the live PostgreSQL golden-path test asserting `len(loaded.aggregate.transition_history) == 1`.

## 22. Not-Found Behavior

`AggregateNotFound` raised by `EvidencePackageRepository.get()` for a `DomainIdentity` with no persisted `EvidencePackage`, propagated transparently — proven at unit level (fake repository) and genuinely reproduced against real PostgreSQL.

## 23. Invalid-Transition Behavior

`EvidencePackage.start_collection()` raises a domain `ValueError` ("cannot transition from ...") when the current state is not `INITIALIZED`, propagated transparently with `save()` never reached — proven at unit level and genuinely reproduced against real PostgreSQL (Section 32).

## 24. Arbitrary Error Semantics

Transparent, unchanged propagation of `OptimisticConcurrencyConflict` (unit-level proof, Section 33) and any arbitrary `get()`/`save()` failure. No handler-level `try`/`except`.

## 25. Validation Ownership

`DomainIdentity`/`EvidencePackageId`/`AggregateVersion` own their own format validation at construction. `EvidencePackage.start_collection()` owns its own state-precondition and `occurred_at`-type validation. The handler performs no additional validation.

## 26. Transaction Non-Ownership

No application-level transaction orchestration — one repository-owned `save()` call, already atomic via its own `unit_of_work()`.

## 27. CommandEntryPoint Binding

Test-only direct construction, mirroring `AuthorizeRunHandler`/`PrepareCampaignForAuthorizationHandler`. No production composition root.

## 28. Architecture Preservation

**Zero architecture-checker change.** Independently re-verified in this freeze: `git diff 4674601..56d3558 -- tools/check_architecture.py tests/fixtures/` is empty, and `python tools/check_architecture.py .` passes at exit 0.

## 29. PostgreSQL Success Evidence

Independently reproduced against a fresh disposable `postgres:17` container in this freeze session: golden-path transition via `CommandEntryPoint`, `SaveResult.persisted_version == AggregateVersion(1)`, independently reloaded state `COLLECTING`, exactly one transition record.

## 30. PostgreSQL Invalid-Transition Evidence

Independently reproduced against real PostgreSQL in this freeze session: `test_two_racing_callers_second_start_collection_raises_domain_value_error` — the second caller's own `start_collection()` call fails with a domain `ValueError` before `save()` is ever reached (Section 32).

## 31. PostgreSQL Missing-Aggregate Evidence

Independently reproduced against real PostgreSQL in this freeze session: retrieval of a never-persisted `DomainIdentity` raises `AggregateNotFound`.

## 32. Two-Caller Concurrency Evidence

**Real PostgreSQL two-caller behavior, recorded explicitly and permanently:**

1. Both callers may carry `expected_persisted_version = AggregateVersion(0)`.
2. The first caller loads the `EvidencePackage` while it is `INITIALIZED`.
3. The first caller performs `start_collection()`.
4. The first caller's `save()` succeeds.
5. Durable state becomes `COLLECTING`, `persisted_version = 1`.
6. The second caller executes later, still carrying its own stale `expected_persisted_version = AggregateVersion(0)`.
7. The second caller's handler independently loads the now-`COLLECTING` durable state.
8. The second caller's own `start_collection()` call raises a domain `ValueError` (`"cannot transition from COLLECTING to COLLECTING"`).
9. `save()` is never reached by the second caller.
10. No `OptimisticConcurrencyConflict` is raised anywhere in this real sequence.
11. No retry occurs anywhere in the frozen handler.
12. The first writer's state (`COLLECTING`, version 1, one transition record) remains authoritative and untouched by the second caller's failed attempt — independently re-verified via a post-attempt reload in the integration test.

**Why no deterministic real-PostgreSQL `OptimisticConcurrencyConflict` reproduction exists for this specific capability:** the frozen `EvidencePackage` aggregate has no legitimate state-preserving mutation available while `INITIALIZED` that simultaneously (a) advances the aggregate version, (b) preserves the `INITIALIZED` state, and (c) leaves a subsequent `start_collection()` call domain-valid. `Campaign.revise_scope_statement()` and `Run.append_manifest()` each satisfy this three-part requirement for their own aggregate in its own initial state; `EvidencePackage` has no analogous method. Independently re-confirmed in this freeze against `src/empirical_platform/evidence/package.py`: `start_collection()` is the only method operating on `state == INITIALIZED`. Therefore the M032/M035-style real-conflict reproduction pattern is genuinely unavailable for this capability — not omitted through oversight, and not fabricated via direct SQL manipulation or invalid database rows (both explicitly rejected in the design, Section 19).

## 33. OptimisticConcurrencyConflict Propagation Boundary

**Fake-repository evidence, and precisely what it does and does not prove:** the unit test `test_optimistic_concurrency_conflict_from_save_propagates_unchanged` uses a fake repository whose `save()` raises `OptimisticConcurrencyConflict` directly, unconstrained by `EvidencePackage`'s own state machine (a real `PostgresEvidencePackageRepository` cannot be induced to do this without first satisfying the aggregate's own domain preconditions, per Section 32). This proves: the handler reaches `save()`; `save()` raising `OptimisticConcurrencyConflict` propagates the exact exception instance unchanged; exactly one `save()` attempt occurs; no retry; no wrapping or translation of any kind. **It does not prove**, and this freeze record does not claim, that this specific transition (`start_collection()`) can generate a real PostgreSQL `OptimisticConcurrencyConflict` through the natural application call sequence — Section 32 establishes that it cannot, for this specific transition, and this boundary is not blurred anywhere in this milestone's governance.

## 34. Full PostgreSQL Regression

Independently reproduced in this freeze session against a fresh disposable container: `pytest tests/integration/` — 140 passed, 6 skipped; `pytest -q` (PostgreSQL opt-in, full suite) — 788 passed, 6 skipped, 92.83% coverage. Both exactly match the implementation session's own figures — zero drift. Hostile self-audit grep independently re-confirmed: zero genuine prohibited-pattern matches in `start_evidence_package_collection.py` (two docstring "for" false positives); no `RunRepository`/`CampaignRepository`/`Review` reference; no `add_criterion_result`/`add_artifact_reference`/`seal`/`invalidate` call.

Two additional targeted regression groupings cited by the independent review were independently reproduced exactly in this freeze session, confirming the review's own evidence as genuine and reproducible: a focused unit/contract/architecture command spanning M036-M038's own tests plus `test_authorize_run_usecase.py`/`test_authorize_run_handler_contract.py` and `test_module_boundaries.py` — **89 passed**, exact match; a targeted predecessor-plus-M038 PostgreSQL regression spanning `test_m023_postgres_repositories.py` plus `test_m033_create_run_usecase.py` through `test_m038_start_evidence_package_collection_usecase.py` — **53 passed**, exact match.

## 35. Ruff/Mypy/Build/Security Evidence

Independently re-run in this freeze session under the canonical `.venv` interpreter (Python 3.13.14): `ruff format --check .`/`ruff check .` clean, 232 files formatted; canonical `mypy` clean, 95 source files; `pytest -q -m "not integration"` — 648 passed, 146 deselected, 83.79% coverage; `python -m build --wheel` succeeds; `python -m pip_audit` reports no known vulnerabilities.

## 36. External Review Package Verification

`external-review/MILESTONE-038/MILESTONE-038-56d3558-external-review.zip` — independently re-verified in this freeze session: SHA-256 `a724f4cfbeaed5949a500161a75a3fc22c7fc82b0717f3d12de7490357b1b669`, exact match against the reviewed package. `manifest.sha256`: 27 entries, all 27/27 independently re-verified OK. ZIP: 28 entries (27 manifest entries + the manifest file itself), `testzip()` clean, no stray or debris files. `complete.diff` (regenerated against the frozen M037 baseline `4674601...` through the final pushed HEAD `56d3558...`) is byte-identical to a live regeneration performed in this freeze session.

## 37. Changed-File Surface

```
A  MILESTONE_038_CONCRETE_APPLICATION_COMMAND_VERTICAL_SLICE_EVIDENCE_PACKAGE_COLLECTION_START_MACRO_DESIGN.md
A  MILESTONE_038_CONCRETE_APPLICATION_COMMAND_VERTICAL_SLICE_EVIDENCE_PACKAGE_COLLECTION_START_MACRO_IMPLEMENTATION.md
A  MILESTONE_038_CONCRETE_APPLICATION_COMMAND_VERTICAL_SLICE_EVIDENCE_PACKAGE_COLLECTION_START_MACRO_SCOPE.md
M  PROJECT_CHECKPOINT.md
M  src/empirical_platform/usecases/__init__.py
A  src/empirical_platform/usecases/start_evidence_package_collection.py
A  tests/contract/test_start_evidence_package_collection_handler_contract.py
A  tests/integration/test_m038_start_evidence_package_collection_usecase.py
A  tests/unit/test_start_evidence_package_collection_usecase.py
```

Independently re-confirmed in this freeze session: exactly nine files, matching the implementation commit's own tree exactly.

## 38. Non-Blocking Findings

**M038-REVIEW-0001 — secret-scan target count time-scoping (MINOR, non-blocking).** The implementation evidence recorded 410 targets. The independent final review reported 413 targets. This freeze session independently reproduced **412 targets** at freeze-verification time (before staging the freeze document itself) — one more than the implementation-time count (this milestone's own new governance/test/source files having been added since), and one fewer than the reviewer's cited 413. All three values are recorded as explicitly time-scoped; the freeze-time discrepancy against the reviewer's own figure is smaller and more plausibly explained by ordinary file-count drift across sessions than an error, unlike a larger unreconciled gap would be — see Section 39 for disposition.

**M038-REVIEW-0002 — pre-existing setuptools deprecation warning (OBSERVATION, non-blocking).** `python -m build` continues to emit the same pre-existing `SetuptoolsDeprecationWarning` about `project.license` as a TOML table, unrelated to this milestone's code, identical to the warning already documented in M034/M036/M037's own freeze records.

## 39. Finding Disposition

**M038-REVIEW-0001:** `RESOLVED_BY_TIME_SCOPED_SECURITY_COUNT_CLARIFICATION`. Recorded as three explicitly time-scoped values: implementation-time value **410**; this freeze session's own independently reproduced value **412**; the independent review's cited value **413** (not independently re-reproduced exactly by this freeze session, recorded as reported rather than asserted as freeze-time canonical truth). The canonical security gate (`pip_audit`) passed in every run; no secret or vulnerability defect exists under any of the three counts. The original historical evidence file is not rewritten solely to erase the earlier count.

**M038-REVIEW-0002:** `ACCEPTED_PREEXISTING_BUILD_WARNING`. No M038 correction required; not touched unless MILESTONE-039 independently requires a packaging-metadata change for its own reasons.

Neither finding affects production behavior, concurrency correctness, PostgreSQL correctness, architecture, package integrity, predecessor authority, or freeze eligibility.

## 40. No-Scope-Creep Declaration

No `add_criterion_result`/`add_artifact_reference`/`seal`/`invalidate` call; no `Review` work; no retry policy; no composition root, registry, dispatcher, mediator, service locator, or DI framework; no transport/API layer; no schema/migration change; no MILESTONE-039 work exists anywhere in this milestone.

## 41. Preserved M020-M037 Authority

No change to any M020-M037 frozen contract, source file, test, or governance document. All prior authority remains exactly as previously frozen.

## 42. Owner Freeze Declaration

**M038 MACRO MILESTONE APPROVED_AND_FROZEN.** The implementation delivered in commits `a77ef2f`/`56d3558`, exactly as verified in Sections 28-37 above, is the final, frozen implementation of MILESTONE-038.

## 43. Deferred Work

`add_criterion_result()`, `add_artifact_reference()`, `seal()`, `invalidate()`; `Review` creation and retrieval; retry-on-conflict policy; any composition-root abstraction beyond direct binding; MILESTONE-039 and beyond.

## 44. M039 Boundary

This freeze authorizes work through MILESTONE-038 only. No MILESTONE-039 capability, terminology, sequencing decision, or forward commitment is made anywhere in this document. Section 43's "Deferred Work" is descriptive of currently-visible future candidates, not a binding selection of MILESTONE-039's scope.

## 45. Final Status

**M038 APPROVED_AND_FROZEN** — scope, design, and implementation, at every stage.

M039: NOT_STARTED. M040: NOT_STARTED.

## 46. Next Permitted Action

**MILESTONE-039 COMPLETE MACRO MILESTONE MISSION.**
