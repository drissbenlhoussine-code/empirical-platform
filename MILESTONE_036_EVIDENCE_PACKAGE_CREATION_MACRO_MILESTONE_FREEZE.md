# MILESTONE-036 - EvidencePackage Creation Macro Milestone Freeze

## 1. Document Status

**Status: FINAL — OWNER FROZEN**

This document is the Owner Freeze record for MILESTONE-036, the first milestone produced under the Macro Milestone Protocol (activated in M035's implementation freeze, Section 49). It is authoritative.

## 2. Milestone Identity

MILESTONE-036 — Concrete Application Command Vertical Slice: EvidencePackage Creation.

## 3. Repository Authority

| Field | Value |
| --- | --- |
| Repository | `C:\Users\LuxSy\Documents\trading` |
| Branch | `master` |
| HEAD at freeze | `cd5083289008b2735281f53ab45a2c90a90b0f51` |

## 4. Frozen Predecessor Chain

M020-M035 all `APPROVED_AND_FROZEN` at every stage. M035 implementation freeze: `6853d988634ae264d6e625a90b9ba6815d908df5`; hash-recording commit `5f3b8f69afdcd7b319fd0842efb80effde8f7991`.

## 5. Macro Scope Authority

`MILESTONE_036_CONCRETE_APPLICATION_COMMAND_VERTICAL_SLICE_EVIDENCE_PACKAGE_CREATION_SCOPE.md` — one concrete command creating a new `EvidencePackage` for an existing `Run`, via `EvidencePackageRepository.add()`. Selected after a fresh architecture inventory found all three CQRS verbs (`add()`/`get()`/`save()`) proven across two aggregates each (Campaign, Run), leaving `EvidencePackage`/`Review` as the only aggregates with zero application-layer proof.

## 6. Macro Design Authority

`MILESTONE_036_CONCRETE_APPLICATION_COMMAND_VERTICAL_SLICE_EVIDENCE_PACKAGE_CREATION_DESIGN.md` — caller-supplied raw governance-ID identity model + handler-generated runtime ID (mirrors `CreateRunCommand`); Run-existence enforced entirely by the real `evidence_package.run_id → run.governance_id` foreign key, no `RunRepository` dependency; result contract `DomainIdentity[EvidencePackageId]`.

## 7. Implementation Commit

`4672cfc7137e19aa628ebe996883e10a1d3f90c3` (`feat: implement M036 Run authorization usecase` — commit title inaccuracy disclosed and disposed of in Section 37/38 below; content and lineage are correct).

## 8. Finalization Commit

`cd5083289008b2735281f53ab45a2c90a90b0f51` (`docs: finalize M036 implementation review package`) — narrow, docs-only, recorded the implementation commit's own hash. No production behavior changed.

## 9. Independent Review Authority

The independent hostile review verified: one `EvidencePackage` creation capability only; correct scope sequencing; valid domain/repository contracts; exactly one `add()` call; caller-supplied governance identity; handler-generated runtime identity; persistence-enforced Run foreign key; duplicate governance/runtime identity behavior; missing-Run FK behavior; architecture boundary correctness; live PostgreSQL evidence; full regression; build/security; governance; manifest and ZIP integrity; M020-M035 predecessor preservation.

## 10. Review Decision

**M036 MACRO MILESTONE APPROVED WITH NON-BLOCKING OBSERVATIONS.** No CRITICAL, MAJOR, or blocking MINOR finding remains.

## 11. Owner Approval

The owner formally freezes the M036 macro milestone via this document.

**M036 MACRO MILESTONE APPROVED_AND_FROZEN.**

**M036 APPROVED_AND_FROZEN** — scope, design, and implementation, at every stage, frozen as one consolidated unit per the Macro Milestone Protocol.

## 12. Frozen Production Capability

Exactly one: creation of a new `EvidencePackage` for an existing `Run`. No retrieval, mutation (`start_collection`, `add_criterion_result`, `add_artifact_reference`, `seal`, `invalidate`), listing, filtering, or pagination.

## 13. Frozen Command Contract

```python
@dataclass(frozen=True, slots=True)
class CreateEvidencePackageCommand:
    evidence_package_governance_id: str
    run_governance_id: str
```

## 14. Frozen Handler Contract

```python
class CreateEvidencePackageHandler:
    __slots__ = ("_evidence_package_repository", "_runtime_identifier_generator")

    def __init__(self, *, evidence_package_repository, runtime_identifier_generator) -> None:
        self._evidence_package_repository = evidence_package_repository
        self._runtime_identifier_generator = runtime_identifier_generator

    def handle(self, command: CreateEvidencePackageCommand) -> DomainIdentity[EvidencePackageId]:
        identity = DomainIdentity(
            governance_id=EvidencePackageId(command.evidence_package_governance_id),
            runtime_id=self._runtime_identifier_generator.generate(),
        )
        package = EvidencePackage(identity=identity, run_id=RunId(command.run_governance_id))
        self._evidence_package_repository.add(package)
        return package.identity
```

Sole dependencies: `EvidencePackageRepository`, `RuntimeIdentifierGenerator`. No `RunRepository`, `CampaignRepository`, or `Clock` — independently re-verified in this freeze via direct grep (Section 32).

## 15. Frozen Identity Semantics

Caller-supplied raw `evidence_package_governance_id` string, translated into `EvidencePackageId` by the handler (format-validated at construction). Runtime ID minted by `RuntimeIdentifierGenerator.generate()`, called exactly once. Mirrors `CreateRunHandler` exactly.

## 16. Frozen Run Referential-Integrity Model

Run existence is **not** validated by any application-level `RunRepository` lookup. Enforced entirely by the real `evidence_package.run_id → run.governance_id` foreign key (verified directly in `migrations/versions/5b58cdd7751b_create_m022_postgresql_schema.py`). A missing Run produces an unmodified `FoundationError` (category `PERSISTENCE`), never `AggregateNotFound` or `AggregateAlreadyExists`.

## 17. Frozen Creation Sequence

1. Receive command.
2. Construct `EvidencePackageId(command.evidence_package_governance_id)`.
3. Call `runtime_identifier_generator.generate()` exactly once.
4. Construct `DomainIdentity`.
5. Construct `RunId(command.run_governance_id)`.
6. Construct exactly one `EvidencePackage` aggregate.
7. Call `evidence_package_repository.add(package)` exactly once.
8. Return `package.identity` unchanged.

No `get()`/`save()` call of any kind. No retry. No Run lookup.

## 18. Frozen Result Contract

`DomainIdentity[EvidencePackageId]` — the newly created identity, returned unchanged. Mirrors `CreateRunHandler`'s return contract.

## 19. Duplicate Governance-ID Behavior

`AggregateAlreadyExists` raised by the real `uq_evidence_package_governance_id` constraint, propagated transparently — proven at unit level (fake repository) and genuinely reproduced against real PostgreSQL.

## 20. Duplicate Runtime-ID Behavior

Two different governance IDs sharing one generated runtime ID collide on the real `pk_evidence_package` constraint, raising `AggregateAlreadyExists` — genuinely reproduced against real PostgreSQL.

## 21. Missing-Run FK Behavior

Verified directly against the concrete adapter's exception-handling code: a foreign-key violation (SQLSTATE `23503`) is not classified as a unique violation by `unique_violation_constraint_name`, so it reaches the bare `raise` — an unmodified `FoundationError`, never translated. Genuinely reproduced against real PostgreSQL, with independent confirmation via `AggregateNotFound` on reload that no row was persisted despite the failure.

## 22. Arbitrary Error Semantics

Transparent, unchanged propagation of `InvalidAggregateForPersistence` and any arbitrary `add()`/generator failure. No handler-level `try`/`except`.

## 23. Validation Ownership

`EvidencePackageId`/`RunId` own format validation at construction. `DomainIdentity` validates only base identity-pair structure. `EvidencePackage.__init__` owns its own type checks. The handler performs no duplicate validation.

## 24. Transaction Non-Ownership

No application-level transaction orchestration — one repository-owned `add()` call, already atomic via its own `unit_of_work()`.

## 25. CommandEntryPoint Binding

Test-only direct construction, mirroring every prior command milestone. No production composition root.

## 26. Architecture Boundary Change

Exactly one narrow addition: `ALLOWED["usecases"]` gained `"evidence"`. `FORBIDDEN_IMPORT_PREFIXES["usecases"]` unchanged. Independently re-verified live in this freeze: `python tools/check_architecture.py .` exit 0, and the checker file's diff against the M035 baseline shows exactly one changed line.

## 27. Architecture Fixture Maintenance

The now-obsolete `usecases/bad_evidence_import.py` (would silently stop triggering) was removed. Replaced with `usecases/bad_review_import.py` (usecases still cannot import review) and `evidence/bad_usecases_import.py` (new reverse-direction evidence: evidence cannot import usecases, mirroring the `run`/`campaign` precedent). Both architecture tests reconfirmed passing in this freeze.

## 28. PostgreSQL Success Evidence

Independently reproduced across two separate fresh disposable `postgres:17` containers (implementation session + package-evidence session): golden-path creation, persisted state (`INITIALIZED`), empty `criterion_results`/`artifact_references`/`transition_history`, correct `run_id` — all verified.

## 29. Duplicate Governance-ID Evidence

Reproduced against real PostgreSQL in both sessions: second creation attempt with the same governance ID raises `AggregateAlreadyExists`.

## 30. Duplicate Runtime-ID Evidence

Reproduced against real PostgreSQL in both sessions: two different governance IDs sharing one deterministic runtime ID collide on `pk_evidence_package`.

## 31. Missing-Run Evidence

Reproduced against real PostgreSQL in both sessions: `FoundationError(category=PERSISTENCE)`, not `AggregateAlreadyExists`; independent `AggregateNotFound` confirms no row persisted.

## 32. Regression Evidence

Non-integration: 603 passed (was 585), zero regression. Integration: 132 passed (was 127). Full suite with PostgreSQL: 735 passed, 6 skipped, 92.74% coverage. Predecessor suites (`test_create_run_usecase.py`, `test_create_run_handler_contract.py`, `test_get_run_usecase.py`, `test_authorize_run_usecase.py`, `test_run_aggregate.py`, `test_module_boundaries.py`) — 93 passed. Independently re-verified in this freeze: `git status --short` empty (byte-identical), architecture checker exit 0, hostile self-audit grep (Section below) confirms zero genuine prohibited-pattern match — `grep -c "\.add("` → 1; `grep -n "RunRepository\|\.get(\|\.save("` → zero matches.

## 33. Ruff/Mypy/Build/Security Evidence

`ruff check`/`format --check` clean (224 files formatted); canonical `mypy` clean (93 source files); `python -m build` succeeds with `create_evidence_package.py` present in the built wheel; `pip_audit` reports no known vulnerabilities; `secret_scan_targets.py` — 393 targets at implementation time, 395 during package-evidence capture (consistent minor drift from newly-created package files themselves, not a defect).

## 34. External Review Package Evidence

`external-review/MILESTONE-036/MILESTONE-036-cd50832-external-review.zip`, SHA-256 `1d1747c5bf03051a8289088fc732b7b2f1b4cf8df742bc546c844fc45e189c5d` — independently re-verified against the live file in this freeze session, exact match. `manifest.sha256`: 47 entries, all verified OK (a stray scratch file caught and removed before finalizing, documented honestly in the mission's own final report). `complete.diff` byte-identical to a live regeneration.

## 35. Changed-File Surface

```
A  MILESTONE_036_CONCRETE_APPLICATION_COMMAND_VERTICAL_SLICE_EVIDENCE_PACKAGE_CREATION_DESIGN.md
A  MILESTONE_036_CONCRETE_APPLICATION_COMMAND_VERTICAL_SLICE_EVIDENCE_PACKAGE_CREATION_IMPLEMENTATION.md
A  MILESTONE_036_CONCRETE_APPLICATION_COMMAND_VERTICAL_SLICE_EVIDENCE_PACKAGE_CREATION_SCOPE.md
M  PROJECT_CHECKPOINT.md
M  src/empirical_platform/usecases/__init__.py
A  src/empirical_platform/usecases/create_evidence_package.py
M  tests/architecture/test_module_boundaries.py
A  tests/contract/test_create_evidence_package_handler_contract.py
A  tests/fixtures/illegal_imports/src/empirical_platform/evidence/bad_usecases_import.py
D  tests/fixtures/illegal_imports/src/empirical_platform/usecases/bad_evidence_import.py
A  tests/fixtures/illegal_imports/src/empirical_platform/usecases/bad_review_import.py
A  tests/integration/test_m036_create_evidence_package_usecase.py
A  tests/unit/test_create_evidence_package_usecase.py
M  tools/check_architecture.py
```

## 36. No-Scope-Creep Declaration

No `EvidencePackage` retrieval or mutation; no `Review` work; no retry policy; no composition root, registry, dispatcher, mediator, service locator, or DI framework; no transport/API layer; no schema/migration change beyond the pre-existing M022 migration; no MILESTONE-037 work exists anywhere in this milestone.

## 37. Non-Blocking Observations

**M036-OBS-0001 — cosmetic commit-subject defect.** The implementation commit's one-line title says "Run authorization usecase" (a copy-paste artifact from M035's own commit template) instead of "EvidencePackage creation usecase." Content and lineage are correct — `git show --stat 4672cfc7137e19aa628ebe996883e10a1d3f90c3` shows only `EvidencePackage`-related files changed. Disclosed in the implementation session's own review-instructions.md and independently reconfirmed here.

**M036-OBS-0002 — transient tooling interpreter mismatch.** One initial non-canonical security invocation used system Python 3.14 instead of the project `.venv`. The canonical rerun under the repository `.venv` (Python 3.13.14) passed.

**M036-OBS-0003 — pre-existing setuptools deprecation warning.** `python -m build` emits a known, pre-existing `SetuptoolsDeprecationWarning` about `project.license` as a TOML table — unrelated to this milestone's code, identical to the warning already documented in M034's own freeze record.

## 38. Observation Disposition

**M036-OBS-0001:** `ACCEPTED_COSMETIC_COMMIT_SUBJECT_DEFECT`. Git history is not amended or rewritten, per this project's own established convention (amend reserved for user-authorized exceptions only). Content and lineage remain authoritative.

**M036-OBS-0002:** `RESOLVED_BY_CANONICAL_VENV_RERUN`. No code or configuration correction required.

**M036-OBS-0003:** `ACCEPTED_PREEXISTING_BUILD_WARNING`. No M036 correction required; not touched unless MILESTONE-037 independently requires a packaging-metadata change for its own reasons.

None of the three affects behavior, architecture, PostgreSQL correctness, package integrity, or freeze eligibility.

## 39. Preserved M020-M035 Authority

No change to any M020-M035 frozen contract, source file, test, or governance document. All prior authority remains exactly as previously frozen.

## 40. Owner Freeze Declaration

**M036 MACRO MILESTONE APPROVED_AND_FROZEN.** The implementation delivered in commits `4672cfc`/`cd50832`, exactly as verified in Sections 26-34 above, is the final, frozen implementation of MILESTONE-036.

## 41. Deferred Work

`EvidencePackage` retrieval and mutation (`start_collection`, `add_criterion_result`, `add_artifact_reference`, `seal`, `invalidate`); `Review` creation and retrieval (still gated behind `EvidencePackage`, now satisfied at the creation level — retrieval/mutation remain unproven); retry-on-`OptimisticConcurrencyConflict` policy; any composition-root abstraction beyond direct binding; MILESTONE-037 and beyond.

## 42. M037 Boundary

This freeze authorizes work through MILESTONE-036 only. No MILESTONE-037 capability, terminology, sequencing decision, or forward commitment is made anywhere in this document. Section 41's "Deferred Work" is descriptive of currently-visible future candidates, not a binding selection of MILESTONE-037's scope.

## 43. Final Status

**M036 APPROVED_AND_FROZEN** — scope, design, and implementation, at every stage.

M037: NOT_STARTED. M038: NOT_STARTED.

## 44. Next Permitted Action

**MILESTONE-037 COMPLETE MACRO MILESTONE MISSION.**
