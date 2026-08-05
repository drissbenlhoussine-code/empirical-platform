# MILESTONE-042 - Review Creation Macro Milestone Freeze

## 1. Document Status

**Status: FINAL — OWNER FROZEN**

This document is the Owner Freeze record for MILESTONE-042, the seventh milestone produced under the Macro Milestone Protocol (M035 implementation freeze, Section 49; PROJECT_CHECKPOINT.md Section 31). It is authoritative.

## 2. Milestone Identity

MILESTONE-042 — Concrete Application Command Vertical Slice: Review Creation.

## 3. Repository Authority

| Field | Value |
| --- | --- |
| Repository | `C:\Users\LuxSy\Documents\trading` |
| Branch | `master` |
| HEAD at freeze (pre-freeze-commit) | `01c0cbacf75989442aa1289321c5990c6d3235eb` |
| origin/master at freeze (pre-freeze-commit) | `01c0cbacf75989442aa1289321c5990c6d3235eb` (0/0, clean tree) |

## 4. Frozen Predecessor Chain

M020-M041 all `APPROVED_AND_FROZEN` at every stage. M041 Owner Freeze: `MILESTONE_041_EVIDENCE_PACKAGE_SEALING_MACRO_MILESTONE_FREEZE.md`, freeze commit `22cd0afdb84c9a789f380b67db72614b8231bd39`, hash-recording commit `95c52eaeeb28c65f8eabf8feccace7d24cb6967f`.

## 5. Macro Scope Authority

`MILESTONE_042_CONCRETE_APPLICATION_COMMAND_VERTICAL_SLICE_REVIEW_CREATION_MACRO_SCOPE.md` — a fresh, complete architecture inventory (not assumed from any prior milestone's conclusions) found `Review` the only aggregate in the entire domain model with zero application-layer proof of any verb. One concrete command creating a new `Review` targeting an existing `EvidencePackage`, via `ReviewRepository.add()` — the third proof of the `add()`-with-real-FK pattern (after M033, M036). Four prior scope documents (M037/M039/M040/M041) had each independently deferred Review creation pending `EvidencePackage` reaching a genuinely `SEALED` state via frozen commands — a condition M041 satisfied. `EvidencePackage.invalidate()` was seriously evaluated and rejected as lower-leverage (repeating an already-four-times-proven single-precondition-transition pattern on a fully-proven aggregate, versus closing the one aggregate with zero proof of anything).

## 6. Macro Design Authority

`MILESTONE_042_CONCRETE_APPLICATION_COMMAND_VERTICAL_SLICE_REVIEW_CREATION_MACRO_DESIGN.md` — a three-field command (`review_governance_id`, `target_evidence_package_governance_id`, `reviewer_reference`), mirroring `CreateEvidencePackageCommand`'s shape. Target existence enforced entirely by the real `review.target_evidence_package_id -> evidence_package.governance_id` foreign key; no `EvidencePackageRepository` dependency.

## 7. Implementation Commit

`4614c73f0807f9c1db29c51039ce33b254a69d71` (`feat: implement M042 Review creation usecase`).

## 8. Finalization Commit

`01c0cbacf75989442aa1289321c5990c6d3235eb` (`docs: finalize M042 macro milestone review package`) — narrow, checkpoint-only, recorded the implementation commit's own hash and the external-review package ZIP SHA-256. No production behavior changed.

## 9. Independent Review Authority

The independent hostile macro review (27-phase mission) independently re-verified, from scratch and without trusting the implementation session's own claims: repository truth and commit lineage; the changed-file count (13, not the mission's own inaccurate "9" premise — see Section 46); the scope-selection reasoning (fresh 12-module grep confirming zero prior `review` usecases references); the domain contract (`Review.__init__` and `review/aggregate.py` full-file grep confirmed zero lifecycle-state reference to the target `EvidencePackage`); the schema (fresh read of the `review` table's FK and CHECK constraints — no target-state constraint); the command/handler contracts (fresh full read of `create_review.py` plus a targeted prohibited-pattern grep — zero matches for `try/except/retry/get(/save(`); all test counts (19 focused, 745/170/84.20% non-integration, 5/164/909 PostgreSQL, all reproduced against a freshly provisioned container this review itself stood up); the architecture-checker diff (exactly one line) and fixture maintenance; the ZIP SHA-256 (exact match); the scope-creep and predecessor-preservation sweeps (zero matches). It further independently wrote and ran its own direct-SQL adversarial script — separate from the implementation session's own script — reproducing, via raw SQL row inspection against a self-provisioned `postgres:17` container, that Review creation succeeds against a deliberately non-`SEALED` (`INITIALIZED`) target with no hidden state dependency, that duplicate governance-ID raises `AggregateAlreadyExists` with zero duplicate row persisted, and that a missing target raises an unmodified `FoundationError(PERSISTENCE)` with zero row persisted.

## 10. Validation-Completion Authority

A subsequent narrow independent review-validation-completion mission independently rebuilt the sdist/wheel from the canonical `.venv`, inspected full wheel and sdist contents (`create_review.py` present; no `tests/`, `external-review/`, `__pycache__/`, or `.pyc` entries), smoke-imported `CreateReviewCommand`/`CreateReviewHandler` both directly and via the `usecases` package `__init__`, ran `scripts/security.ps1` and `scripts/verify.ps1` end-to-end (the latter's own negative architecture-fixture step independently re-confirmed the fixture-maintenance claim via a mechanism distinct from the pytest-based fixture test), ran `pip-audit` standalone, reproduced the secret-scan target count (443, see Section 47), and reconfirmed the external-review ZIP SHA-256 byte-for-byte.

## 11. Review Decision

**M042 MACRO MILESTONE APPROVED WITH NON-BLOCKING OBSERVATIONS.** No CRITICAL, MAJOR, or blocking MINOR finding was raised at any review stage.

## 12. Owner Approval

The owner formally freezes the M042 macro milestone via this document.

**M042 MACRO MILESTONE APPROVED_AND_FROZEN.**

**M042 APPROVED_AND_FROZEN** — scope, design, and implementation, at every stage, frozen as one consolidated unit per the Macro Milestone Protocol.

## 13. Frozen Production Capability

Exactly one: creation of a new `Review` targeting an existing `EvidencePackage` by governance ID, via `CreateReviewCommand`/`CreateReviewHandler` (`src/empirical_platform/usecases/create_review.py`). No `Review.start()`/`add_finding()`/`complete()`/`cancel()`, no `Review` retrieval, no `EvidencePackage.invalidate()`, and no second command/capability.

## 14. Frozen Command Contract

```python
@dataclass(frozen=True, slots=True)
class CreateReviewCommand:
    review_governance_id: str
    target_evidence_package_governance_id: str
    reviewer_reference: str
```

Exactly three fields, no `__post_init__`, no `expected_persisted_version`, no runtime-ID field, no actor/time/reason/retry/transport metadata.

## 15. Frozen Handler Contract

```python
class CreateReviewHandler:
    __slots__ = ("_review_repository", "_runtime_identifier_generator")

    def __init__(
        self,
        *,
        review_repository: ReviewRepository,
        runtime_identifier_generator: RuntimeIdentifierGenerator,
    ) -> None:
        self._review_repository = review_repository
        self._runtime_identifier_generator = runtime_identifier_generator

    def handle(self, command: CreateReviewCommand) -> DomainIdentity[ReviewId]:
        identity = DomainIdentity(
            governance_id=ReviewId(command.review_governance_id),
            runtime_id=self._runtime_identifier_generator.generate(),
        )
        target = ReviewTargetReference(
            evidence_package_id=EvidencePackageId(command.target_evidence_package_governance_id)
        )
        reviewer = ReviewerReference(command.reviewer_reference)
        review = Review(identity=identity, target=target, reviewer=reviewer)
        self._review_repository.add(review)
        return review.identity
```

Exactly two dependencies: `ReviewRepository`, `RuntimeIdentifierGenerator`. No `EvidencePackageRepository`, no concrete adapter, no transaction manager, no registry, no dispatcher. Independently re-confirmed by prohibited-pattern grep at both independent-review stages: zero `try`/`except`/`retry`/`get(`/`save(` matches in the file.

## 16. Frozen Identity Model

`DomainIdentity[ReviewId]` constructed from the caller-supplied `review_governance_id` string (converted via `ReviewId(...)`) paired with exactly one freshly generated `RuntimeIdentifier`. No pre-existing identity is loaded or reused.

## 17. Runtime-ID Generation

`runtime_identifier_generator.generate()` is called exactly once per `handle()` invocation. Its return value is used unmodified as the `DomainIdentity.runtime_id`.

## 18. Target EvidencePackage Reference

`ReviewTargetReference(evidence_package_id=EvidencePackageId(command.target_evidence_package_governance_id))` — a frozen, slotted value object performing only `isinstance()` type validation in `__post_init__`. No existence check, no lifecycle-state check, no repository call of any kind.

## 19. Frozen Creation Sequence

1. Receive `CreateReviewCommand`.
2. Construct `ReviewId` from `command.review_governance_id`.
3. Generate exactly one runtime ID.
4. Construct `DomainIdentity[ReviewId]`.
5. Construct `EvidencePackageId`/`ReviewTargetReference` from `command.target_evidence_package_governance_id`.
6. Construct `ReviewerReference` from `command.reviewer_reference`.
7. Construct exactly one `Review` aggregate.
8. Call `review_repository.add(review)` exactly once.
9. Return `review.identity` unchanged.

No `get()`, no `save()`, no second `add()`, no parent-repository lookup, no retry, no transaction orchestration, no second capability.

## 20. Frozen Result Contract

Returns `DomainIdentity[ReviewId]` exactly (`review.identity`, unwrapped) — no envelope, no wrapper type.

## 21. Review Initial State

`Review.__init__` unconditionally sets `self._state = ReviewLifecycleState.ASSIGNED` after `isinstance()` type checks on `identity`, `target`, and `reviewer` — independently re-confirmed by a fresh full read of `review/aggregate.py` lines 84-112 at both independent-review stages.

## 22. Review Initial Version

Freshly created `Review` aggregates persist at `version = 0`; `SaveResult.persisted_version` from `ReviewRepository.add()` reflects this, independently confirmed both via the frozen test suite and via direct-SQL row inspection (`version=0` in the raw `review` table row).

## 23. Referential-Integrity Ownership

Target existence is enforced **entirely** by the real PostgreSQL foreign key `review.target_evidence_package_id -> evidence_package.governance_id` (migration `5b58cdd7751b`, fresh-read confirmed). No application-level `EvidencePackageRepository` dependency exists anywhere in `create_review.py`.

## 24. No Target Pre-Load

The handler never loads, queries, or reads the target `EvidencePackage` in any form before calling `review_repository.add()`. Target-existence enforcement occurs entirely inside the database at INSERT time.

## 25. No Target-State Requirement

Independently re-confirmed, twice, by two separately written direct-SQL adversarial scripts (implementation-time hostile self-review, and this freeze's own independent review): `Review` creation has **no** domain-level or application-level dependency on the target `EvidencePackage`'s lifecycle state. `review/aggregate.py`, `ReviewTargetReference.__post_init__`, and the `review` table's `CheckConstraint`s were each independently confirmed to contain no reference of any kind to `EvidencePackageLifecycleState`, `SEALED`, or any other target-state token.

## 26. INITIALIZED Target Evidence

Both direct-SQL adversarial scripts independently reproduced, against separately provisioned fresh `postgres:17` containers: `Review` creation succeeds identically whether the target `EvidencePackage` is `INITIALIZED`, `COLLECTING`, or `SEALED`. The golden-path integration test deliberately uses a genuinely `SEALED` target because that is the real-world-aligned scenario this milestone's scope was selected to unlock — not because the code requires it.

## 27. Duplicate Governance Behavior

A duplicate `review_governance_id` raises `AggregateAlreadyExists` (mapped from the real PostgreSQL `uq_review_governance_id` unique-constraint violation via `PostgresReviewRepository.add()`'s `_ROOT_UNIQUE_CONSTRAINTS` check), independently reproduced via both the frozen test suite and direct-SQL row-count inspection (zero duplicate row persisted after the failed attempt).

## 28. Duplicate Runtime Behavior

A duplicate runtime ID (mapped from the real PostgreSQL `pk_review` primary-key violation) likewise raises `AggregateAlreadyExists`, independently reproduced via the frozen test suite.

## 29. Missing-Target Behavior

A missing target `EvidencePackage` raises an **unmodified** `FoundationError(category=PERSISTENCE)` — the FK violation (SQLSTATE 23503) is not a unique-constraint name recognized by `_ROOT_UNIQUE_CONSTRAINTS`, so it bare-reraises without translation to `AggregateNotFound` or any other type. Independently reproduced via both the frozen test suite and direct-SQL row-count inspection (zero row persisted after the failure).

## 30. Arbitrary Error Semantics

No `try`/`except` block exists anywhere in `CreateReviewHandler`. Any exception raised by `ReviewId(...)`, `EvidencePackageId(...)`, `runtime_identifier_generator.generate()`, `Review(...)`, or `review_repository.add(...)` propagates to the caller with exact instance identity preserved — independently re-confirmed by source inspection at every review stage.

## 31. Validation Ownership

All format validation is owned by the already-frozen `ReviewId`/`EvidencePackageId` value objects. `CreateReviewCommand` itself performs no validation — it is a plain, unvalidated data carrier, independently confirmed by a dedicated unit test (`test_command_is_a_plain_unvalidated_data_carrier`).

## 32. Transaction Non-Ownership

The handler owns no transaction/unit-of-work boundary of its own; `PostgresReviewRepository.add()` opens exactly one `unit_of_work()` scope internally, identical to every other frozen `add()`-pattern repository (M033, M036).

## 33. CommandEntryPoint Binding

`CommandEntryPoint(CreateReviewHandler(...))` works unmodified — independently re-confirmed by a dedicated integration test (`test_no_production_composition_machinery_is_required`) and by this freeze's own direct-SQL adversarial script, which invoked the handler exclusively through `CommandEntryPoint.__call__`.

## 34. Architecture Boundary Change

Exactly one line changed in `tools/check_architecture.py`: `"usecases"` gains `"review"` in `ALLOWED`. No `FORBIDDEN_IMPORT_PREFIXES` change. Independently re-confirmed via `git diff` at every review stage — the diff is exactly one changed line, nothing else in the file.

## 35. Architecture Fixture Maintenance

`tests/fixtures/illegal_imports/src/empirical_platform/usecases/bad_review_import.py` deleted (would silently stop triggering once `review` became allowed — the obsolete-fixture pattern established at M036). `tests/fixtures/illegal_imports/src/empirical_platform/review/bad_usecases_import.py` added, proving the reverse direction (`review` importing `usecases`) remains blocked. Independently re-confirmed both via the pytest-based fixture test (`tests/architecture/test_module_boundaries.py`, 2 passed) and, at the validation-completion stage, via `scripts/verify.ps1`'s own negative-fixture invocation (`check_architecture.py tests/fixtures/illegal_imports`), which lists `review may not import usecases` and does **not** list the deleted `bad_review_import.py` violation — an independent confirmation via a mechanism distinct from pytest.

## 36. PostgreSQL Success Evidence

Golden-path creation independently reproduced at implementation time, independent-review time, and freeze-verification time, each against a freshly provisioned, disposable `postgres:17` container: `Review` persisted with `lifecycle_state='ASSIGNED'`, `version=0`, zero `review_finding`/`review_transition` rows, target `evidence_package_id` matching the command's target, confirmed by raw SQL row inspection independent of the ORM.

## 37. PostgreSQL Duplicate-Governance Evidence

Independently reproduced against a freshly provisioned container: `AggregateAlreadyExists` raised, row count for the governance ID remains exactly 1 after the duplicate attempt (raw SQL count, not ORM-mediated).

## 38. PostgreSQL Duplicate-Runtime Evidence

Independently reproduced via the frozen test suite (`test_duplicate_runtime_id_raises_aggregate_already_exists`), passing at every re-run against a fresh container.

## 39. PostgreSQL Missing-Target Evidence

Independently reproduced against a freshly provisioned container: unmodified `FoundationError(category=persistence_error)` raised, row count for the attempted governance ID remains exactly 0 (raw SQL count).

## 40. Direct-SQL Adversarial Verification

Two separately authored scripts (implementation-time hostile self-review; this freeze's own independent review), each against its own freshly provisioned `postgres:17` container, each bypassing the ORM/repository layer for verification reads, independently confirmed identical results: no hidden target-state dependency; duplicate governance ID and missing target both behave exactly as documented with zero spurious rows persisted in either case. No direct SQL was used by production code at any point — direct SQL was used exclusively for independent verification reads.

## 41. Full Regression Evidence

Independently reproduced at independent-review and validation-completion stages, zero drift each time: focused unit+contract 19 passed; architecture fixtures 2 passed; non-integration suite 745 passed, 170 deselected/skipped, coverage 84.20%; M042 focused PostgreSQL integration 5 passed; full integration regression 164 passed, 6 skipped (up from 159 pre-M042); full suite with PostgreSQL 909 passed, 6 skipped, coverage 93.06%.

## 42. Ruff/Mypy/Build Evidence

`ruff format --check`: 248 files already formatted. `ruff check`: all checks passed. Canonical `mypy`: 99 source files, 0 issues. `python -m build --sdist --wheel`: succeeds; wheel contains 104 files under `empirical_platform/`/`*.dist-info/` only, `create_review.py` present, zero `tests`/`external-review`/`__pycache__`/`.pyc` entries in either the wheel or the sdist. Direct and package-level (`usecases/__init__.py`) smoke imports of `CreateReviewCommand`/`CreateReviewHandler` both succeed.

## 43. Security and pip-audit Evidence

`scripts/security.ps1`: passed (exit 0). `pip-audit` (both embedded and standalone): no known vulnerabilities found (the local unpublished `empirical-platform` package itself correctly skip-audited). `detect_secrets scan`: zero findings against all discovered targets, independently reproduced at the independent-review stage (443 targets) and re-confirmed identical at the validation-completion stage.

## 44. External Review Package Verification

`external-review/MILESTONE-042/MILESTONE-042-01c0cba-external-review.zip` — SHA-256 `37bccfc3986e039eb03cfe400505dd13910d2e78129552923bc19871c87ea6e0`, independently recomputed and matched at both the independent-review stage and the validation-completion stage. 32 entries; `manifest.sha256` 31/31. ZIP not rebuilt or modified by either review stage.

## 45. Changed-File Surface

```
A  MILESTONE_042_CONCRETE_APPLICATION_COMMAND_VERTICAL_SLICE_REVIEW_CREATION_MACRO_DESIGN.md
A  MILESTONE_042_CONCRETE_APPLICATION_COMMAND_VERTICAL_SLICE_REVIEW_CREATION_MACRO_IMPLEMENTATION.md
A  MILESTONE_042_CONCRETE_APPLICATION_COMMAND_VERTICAL_SLICE_REVIEW_CREATION_MACRO_SCOPE.md
M  PROJECT_CHECKPOINT.md
M  src/empirical_platform/usecases/__init__.py
A  src/empirical_platform/usecases/create_review.py
M  tests/architecture/test_module_boundaries.py
A  tests/contract/test_create_review_handler_contract.py
A  tests/fixtures/illegal_imports/src/empirical_platform/review/bad_usecases_import.py
D  tests/fixtures/illegal_imports/src/empirical_platform/usecases/bad_review_import.py
A  tests/integration/test_m042_create_review_usecase.py
A  tests/unit/test_create_review_usecase.py
M  tools/check_architecture.py
```

Exactly thirteen files across implementation and finalization, independently re-confirmed via `git diff --name-status` against the M041 baseline at every review stage, byte-for-byte identical to the external-review package manifest.

## 46. Non-Blocking Observations and Disposition

**M042-REVIEW-0001 — review-mission premise inaccuracy.** The independent hostile review mission's own stated premise ("Expected changed-file count: 9 tracked files") did not match the actual, independently verified delta of 13 files. Disposition: `ACCEPTED_REVIEW_PROMPT_COUNT_INACCURACY`. All 13 files are legitimately necessary — the mission's own premise was inaccurate, not the implementation. The repository and review package already describe the real thirteen-file surface correctly (Section 45).

**M042-REVIEW-0002 — packaged secret-scan count drift.** The external-review package's bundled evidence (`external-review/MILESTONE-042/evidence/security-secret-scan-targets.txt`) records 442 targets; independent final validation reproduced 443 tracked scan targets, confirmed identical at both the M042 implementation commit and the finalization commit via `git ls-tree -r --name-only`. Disposition: `ACCEPTED_NON_BLOCKING_EVIDENCE_COUNT_DRIFT`. The independent scan covered all 443 targets and found zero secrets under either count. No source, test, or review-package correction is required solely to change this historical evidence count.

**M042-OBS-BUILD — pre-existing setuptools deprecation warning.** `python -m build` continues to emit the same pre-existing `SetuptoolsDeprecationWarning` about `project.license` as a TOML table, identical to the warning documented in every prior milestone's freeze record. Disposition: `ACCEPTED_PREEXISTING_BUILD_WARNING`. No correction required.

None of the above affects Review creation behavior, identity semantics, referential integrity, PostgreSQL correctness, architecture, package integrity, predecessor authority, or freeze eligibility.

## 47. No-Scope-Creep Declaration

No `Review.start()`/`add_finding()`/`complete()`/`cancel()`; no `Review` retrieval; no `EvidencePackage.invalidate()`; no retry policy; no composition root, registry, dispatcher, mediator, service locator, or DI framework; no transport/API layer; no schema/migration change; no MILESTONE-043 work exists anywhere in this milestone — independently re-confirmed at implementation-time self-audit, independent-review, and validation-completion stages via full-delta grep sweeps.

## 48. No-Scope-Creep Declaration (Predecessor Authority)

No change to any M020-M041 frozen contract, source file, test, or governance document — independently re-confirmed at every review stage via `git diff --name-only` restricted to `src/empirical_platform/{review,evidence,campaign,run}/` and `migrations/`, returning zero matches. All prior authority remains exactly as previously frozen.

## 49. Preserved M020-M041 Authority

M020-M041 remain `APPROVED_AND_FROZEN` at every stage, unmodified by this milestone. `PROJECT_CHECKPOINT.md`'s M041 field block is byte-unchanged across the entire M041-to-M042 diff — the diff contains only additive new content, independently re-confirmed via targeted diff inspection.

## 50. Owner Freeze Declaration

**M042 MACRO MILESTONE APPROVED_AND_FROZEN.** The implementation delivered in commit `4614c73`, finalized in commit `01c0cba`, exactly as independently re-verified across two independent review stages (Sections 9-10, 25-44 above), is the final, frozen implementation of MILESTONE-042.

## 51. Deferred Work

`Review` retrieval; `Review` lifecycle transitions (`start`/`add_finding`/`complete`/`cancel`); `EvidencePackage.invalidate()`; retry-on-conflict policy; any composition-root abstraction beyond direct binding; MILESTONE-043 and beyond.

## 52. M043 Boundary

This freeze authorizes work through MILESTONE-042 only. No MILESTONE-043 capability, terminology, sequencing decision, or forward commitment is made anywhere in this document. Section 51's "Deferred Work" is descriptive of currently-visible future candidates, not a binding selection of MILESTONE-043's scope.

## 53. Final Status

**M042 APPROVED_AND_FROZEN** — scope, design, and implementation, at every stage.

M043: NOT_STARTED (pending this freeze's completion).

## 54. Next Permitted Action

**MILESTONE-043 COMPLETE MACRO MILESTONE MISSION.**
