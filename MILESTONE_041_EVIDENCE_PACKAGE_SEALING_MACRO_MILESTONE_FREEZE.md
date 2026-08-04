# MILESTONE-041 - EvidencePackage Sealing Macro Milestone Freeze

## 1. Document Status

**Status: FINAL — OWNER FROZEN**

This document is the Owner Freeze record for MILESTONE-041, the sixth milestone produced under the Macro Milestone Protocol (M035 implementation freeze, Section 49; PROJECT_CHECKPOINT.md Section 31). It is authoritative.

## 2. Milestone Identity

MILESTONE-041 — Concrete Application Command Vertical Slice: EvidencePackage Sealing.

## 3. Repository Authority

| Field | Value |
| --- | --- |
| Repository | `C:\Users\LuxSy\Documents\trading` |
| Branch | `master` |
| HEAD at freeze | `a7ae5e25f2305e6aa88410c1917443a20b9f3ae6` |

## 4. Frozen Predecessor Chain

M020-M040 all `APPROVED_AND_FROZEN` at every stage. M040 Owner Freeze: `MILESTONE_040_EVIDENCE_PACKAGE_ARTIFACT_REFERENCE_RECORDING_MACRO_MILESTONE_FREEZE.md`, freeze commit `62dd6595ce6d039f67c25ebc891b1cd4efab1e73`, hash-recording commit `917bd9aa80ce5168d416a0501ae72befad7bd8a8`.

## 5. Macro Scope Authority

`MILESTONE_041_CONCRETE_APPLICATION_COMMAND_VERTICAL_SLICE_EVIDENCE_PACKAGE_SEALING_MACRO_SCOPE.md` — one concrete command transitioning an existing, `COLLECTING` `EvidencePackage` to `SEALED`, via `EvidencePackage.seal()`. Selected after a fresh architecture inventory found `seal()` the only remaining candidate whose own preconditions were satisfiable exclusively via already-frozen application commands (M036 → M038 → M039 → M040 → `seal()`) with no scaffolding compromise required — the first milestone in this project's lineage to reach that state. Review creation was evaluated a fourth time and again deliberately deferred, not because its FK is unreachable but because sealing first lets a future Review-creation milestone target a genuinely completed package.

## 6. Macro Design Authority

`MILESTONE_041_CONCRETE_APPLICATION_COMMAND_VERTICAL_SLICE_EVIDENCE_PACKAGE_SEALING_MACRO_DESIGN.md` — a six-field command, field-for-field identical to `StartEvidencePackageCollectionCommand` (M038); the first transition in this project with **three** independently distinguishable domain-`ValueError` scenarios (empty criterion results, empty artifact references, invalid state) rather than a single precondition; a deterministic-conflict mechanism using `add_artifact_reference()` (frozen since M040) as the interfering write, producing a genuine `OptimisticConcurrencyConflict`.

## 7. Implementation Commit

`7f332e7006e8fe452bac1bc62b23fb73fdb7f963` (`feat: implement M041 EvidencePackage sealing usecase`).

## 8. Finalization Commit

`4db6fa4417ffe62ae055f60b40d8ad0dadbd4f9c` (`docs: finalize M041 macro milestone review package`) — narrow, checkpoint-only, recorded the implementation commit's own hash. No production behavior changed.

## 9. Correction Lineage

A post-implementation hostile author self-review (pre-independent-review, read-only) found one confirmed, minor, documentation-only defect: `MILESTONE_041_..._MACRO_DESIGN.md` Section 18 originally claimed an `INITIALIZED` `EvidencePackage` would be rejected by `seal()`'s state precondition "before either collection precondition is even reached." Direct source reading of `EvidencePackage.seal()`/`_transition()` proved this backwards — the two collection-precondition checks execute before `_transition()`'s state check, so an `INITIALIZED` package (necessarily empty on both collections) fails on the empty-criterion-results check first, never reaching the state check. The actual unit and PostgreSQL tests were already correct — both use an already-`SEALED` package (both collections populated) to genuinely isolate the state-precondition path — and the implementation document already described this correctly; only the design document's prose was wrong. Corrected via:

- Correction commit: `556b21263182eed229b6528b37c4fa2c4d1e69d6` (`docs: correct M041 seal precondition-order design wording`).
- Hash-recording commit: `a7ae5e25f2305e6aa88410c1917443a20b9f3ae6` (`docs: record M041 design correction commit hash`).

No source, test, or contract changed as a result. The external-review package was refreshed against the corrected HEAD and re-validated (new ZIP SHA-256 below).

## 10. Independent Review Authority

The independent hostile review, following the corrected candidate, independently re-verified — via direct SQL bypassing the ORM/repository/test-framework layers entirely — that: the interfering write is real and persisted; the command-under-test's `seal()` was never persisted after a genuine conflict; the raised exception was genuinely `OptimisticConcurrencyConflict`, not a domain `ValueError`; exactly one transition record existed at that point in the lifecycle. It further independently reproduced repository truth, commit lineage, the full changed-file audit, production-source mechanics (exactly one `get()`/`seal()`/`save()`), all test counts, the full regression suite, build, security, the ZIP SHA-256, the manifest, and `complete.diff` byte-equality — all with zero drift and zero contradiction found.

## 11. Review Decision

**M041 MACRO MILESTONE APPROVED WITH NON-BLOCKING OBSERVATIONS.** No CRITICAL, MAJOR, or blocking MINOR finding remains.

## 12. Owner Approval

The owner formally freezes the M041 macro milestone via this document.

**M041 MACRO MILESTONE APPROVED_AND_FROZEN.**

**M041 APPROVED_AND_FROZEN** — scope, design, and implementation, at every stage, frozen as one consolidated unit per the Macro Milestone Protocol.

## 13. Frozen Production Capability

Exactly one: transition of an existing, `COLLECTING` `EvidencePackage` (with non-empty `criterion_results` and `artifact_references`) to `SEALED`. No `invalidate`, `add_criterion_result`, `add_artifact_reference`, `start_collection`, or any second command/capability.

## 14. Frozen Command Contract

```python
@dataclass(frozen=True, slots=True)
class SealEvidencePackageCommand:
    identity: DomainIdentity[EvidencePackageId]
    expected_persisted_version: AggregateVersion
    actor: str
    occurred_at: datetime
    correlation_id: str | None = None
    reason: str | None = None
```

Exactly six fields, field-for-field identical to `StartEvidencePackageCollectionCommand` (M038).

## 15. Frozen Handler Contract

```python
class SealEvidencePackageHandler:
    __slots__ = ("_evidence_package_repository",)

    def __init__(self, *, evidence_package_repository: EvidencePackageRepository) -> None:
        self._evidence_package_repository = evidence_package_repository

    def handle(self, command: SealEvidencePackageCommand) -> SaveResult:
        loaded = self._evidence_package_repository.get(command.identity)
        package = loaded.aggregate
        package.seal(
            actor=command.actor,
            occurred_at=command.occurred_at,
            correlation_id=command.correlation_id,
            reason=command.reason,
        )
        return self._evidence_package_repository.save(
            package, expected_persisted_version=command.expected_persisted_version
        )
```

Sole dependency: `EvidencePackageRepository`. Independently re-confirmed at both self-review and independent-review stages: exactly one `.get(`, one `.seal(`, one `.save(`; zero `.add(`; zero other mutation method references.

## 16. Frozen Load–Mutate–Save Sequence

1. Receive `SealEvidencePackageCommand`.
2. Call `evidence_package_repository.get(command.identity)` exactly once.
3. Call `package.seal(...)` exactly once.
4. Call `evidence_package_repository.save(package, expected_persisted_version=command.expected_persisted_version)` exactly once.
5. Return the exact `SaveResult`, unchanged.

## 17. Frozen Identity and Expected-Version Semantics

`command.identity` passed to `get()` unchanged. `command.expected_persisted_version` — never `loaded.persisted_version` — passed to `save()`, independently re-verified via source inspection and via direct-SQL adversarial testing (a deliberately stale value genuinely triggered a real conflict).

## 18. Frozen Result Contract

`SaveResult`, returned exactly as received from `EvidencePackageRepository.save()` — no wrapping, no reconstruction.

## 19. Frozen Transition and Collection Semantics

A successful `seal()` call transitions `COLLECTING` → `SEALED`, advances `version` by exactly one, and appends exactly one `StateTransitionRecord` (`from_state="COLLECTING"`, `to_state="SEALED"`). Neither `criterion_results` nor `artifact_references` is mutated by `seal()` — both remain populated and unchanged, independently re-confirmed by direct SQL inspection.

## 20. Frozen Three-Part Precondition Model

`EvidencePackage.seal()` checks preconditions in this exact, source-verified order: (1) `criterion_results` non-empty, (2) `artifact_references` non-empty, (3) `state == COLLECTING` (via `_transition()`). An `INITIALIZED` package fails on precondition (1) first and is not a valid fixture for isolating lifecycle-state invalidity — the invalid-state scenario instead uses an already-`SEALED` package (both collections populated, so (1) and (2) pass, and (3) genuinely fails). This is the corrected, source-true model recorded in Design Section 18 (Section 9 above).

## 21. Approved Conflict Model

Independently re-verified via direct SQL, bypassing the repository/ORM layer for verification reads:

1. `EvidencePackage` is `COLLECTING` with both collections populated (`persisted_version = 3`).
2. An independent writer loads a separate aggregate instance and calls `add_artifact_reference()` (frozen, state-preserving) — in-memory version advances, state remains `COLLECTING`.
3. The independent writer saves using the version it loaded with — succeeds, durable `persisted_version` advances to 4.
4. The command under test retains the pre-interference version (3) — now stale.
5. The handler reloads the current `COLLECTING` state (still both collections populated), calls `seal()` — domain-valid.
6. `save()` is called with the stale `expected_persisted_version=3`; the repository's version guard rejects it against the actual durable version 4.
7. `OptimisticConcurrencyConflict` is raised — confirmed genuinely, by exception type inspection via both the frozen test suite and an independent direct-SQL adversarial script, never a domain `ValueError`.
8. No retry or second `save()` occurs. The interfering `ArtifactReference` remains persisted and authoritative; the losing `seal()` attempt is never persisted — state remains `COLLECTING`, version remains 4, verified via raw SQL query, not ORM-mediated reads.

No direct SQL fabrication, no patched aggregate internals, no invalid row, no second production command were used to produce this evidence.

## 22. Approved PostgreSQL Evidence

Independently reproduced at self-review, independent-review, and direct-SQL-adversarial stages, against fresh disposable `postgres:17` containers each time: golden path (`SaveResult.persisted_version == AggregateVersion(4)`, `state == SEALED`, exactly one transition record, both collections preserved); empty-criterion-results rejection; empty-artifact-references rejection; invalid-state rejection (already-`SEALED`); missing-identity `AggregateNotFound`; the genuine deterministic conflict (Section 21). 7 PostgreSQL integration tests, all passing at every re-run with zero drift. Full integration regression: 159 passed, 6 skipped (up from 152 pre-M041). Full suite with PostgreSQL: 885 passed, 6 skipped, 92.97% coverage.

## 23. Full Regression and Toolchain Evidence

Independently reproduced at both self-review and independent-review stages, zero drift each time: non-integration suite 726 passed, 165 deselected, 84.10% coverage; architecture checker exit 0, zero source change; `ruff format --check`/`ruff check` clean, 244 files formatted; canonical `mypy` clean, 98 source files; `python -m build --wheel` succeeds; `python -m pip_audit` reports no known vulnerabilities. Secret-scan count reproduced at 435 at final independent-review time (time-scoped; no security defect under any observed count).

## 24. Approved Package Hash

`external-review/MILESTONE-041/MILESTONE-041-a7ae5e2-external-review.zip` — SHA-256 `c38fbbb24edbcc56314b039c8bcdf9eae37c4956bc11fe32bacdd1071e126846`, independently recomputed and matched at both package-refresh time and independent-review time. 28 entries, `testzip()` clean, no duplicates, no unsafe paths, no debris. `manifest.sha256`: 27/27 verified, including from a fresh short-path extraction. `complete.diff` (baseline `917bd9a` through corrected HEAD `a7ae5e2`) byte-identical to a live regeneration at both refresh and independent-review time. Packaged source/tests/governance confirmed byte-identical to the live repository at both stages.

## 25. Changed-File Surface (Implementation + Correction, Cumulative)

```
A  MILESTONE_041_CONCRETE_APPLICATION_COMMAND_VERTICAL_SLICE_EVIDENCE_PACKAGE_SEALING_MACRO_DESIGN.md
A  MILESTONE_041_CONCRETE_APPLICATION_COMMAND_VERTICAL_SLICE_EVIDENCE_PACKAGE_SEALING_MACRO_IMPLEMENTATION.md
A  MILESTONE_041_CONCRETE_APPLICATION_COMMAND_VERTICAL_SLICE_EVIDENCE_PACKAGE_SEALING_MACRO_SCOPE.md
M  PROJECT_CHECKPOINT.md
M  src/empirical_platform/usecases/__init__.py
A  src/empirical_platform/usecases/seal_evidence_package.py
A  tests/contract/test_seal_evidence_package_handler_contract.py
A  tests/integration/test_m041_seal_evidence_package_usecase.py
A  tests/unit/test_seal_evidence_package_usecase.py
```

Exactly nine files across implementation, finalization, and the narrow design-wording correction — independently re-confirmed at every review stage.

## 26. Non-Blocking Observations and Disposition

**M041-OBS-0001 — pre-existing setuptools deprecation warning.** `python -m build` continues to emit the same pre-existing `SetuptoolsDeprecationWarning` about `project.license` as a TOML table, identical to the warning documented in every prior EvidencePackage milestone's freeze record. Disposition: `ACCEPTED_PREEXISTING_BUILD_WARNING`. No correction required.

**M041-SELFREVIEW-0001 — design-doc precondition-ordering claim.** Disposition: `RESOLVED_BY_TRACKED_CORRECTION` (Section 9). No further action.

**NB-1 (independent review) — `M041_FINALIZATION_COMMIT=PENDING` in checkpoint at review time.** Disposition: confirmed consistent with this project's own established convention (identical pattern in M038/M039/M040, resolved only at each milestone's own Owner Freeze). Resolved by this freeze (Section 28).

None of the above affects production behavior, concurrency correctness, PostgreSQL correctness, architecture, package integrity, predecessor authority, or freeze eligibility.

## 27. No-Scope-Creep Declaration

No `invalidate`/`add_criterion_result`/`add_artifact_reference`/`start_collection` call; no `Review` work; no retry policy; no composition root, registry, dispatcher, mediator, service locator, or DI framework; no transport/API layer; no schema/migration change; no MILESTONE-042 work exists anywhere in this milestone — independently re-confirmed at self-review and independent-review stages via full-delta grep sweeps.

## 28. Preserved M020-M040 Authority

No change to any M020-M040 frozen contract, source file, test, or governance document — independently re-confirmed at every review stage. All prior authority remains exactly as previously frozen.

## 29. Owner Freeze Declaration

**M041 MACRO MILESTONE APPROVED_AND_FROZEN.** The implementation delivered in commits `7f332e7`/`4db6fa4`, corrected in commits `556b212`/`a7ae5e2`, exactly as independently re-verified in Sections 10 and 20-24 above, is the final, frozen implementation of MILESTONE-041.

## 30. Deferred Work

`invalidate()`; `Review` creation and retrieval; retry-on-conflict policy; any composition-root abstraction beyond direct binding; MILESTONE-042 and beyond.

## 31. M042 Boundary

This freeze authorizes work through MILESTONE-041 only. No MILESTONE-042 capability, terminology, sequencing decision, or forward commitment is made anywhere in this document. Section 30's "Deferred Work" is descriptive of currently-visible future candidates, not a binding selection of MILESTONE-042's scope.

## 32. Final Status

**M041 APPROVED_AND_FROZEN** — scope, design, and implementation, at every stage.

M042: NOT_STARTED.

## 33. Next Permitted Action

**MILESTONE-042 COMPLETE MACRO MILESTONE MISSION.**
