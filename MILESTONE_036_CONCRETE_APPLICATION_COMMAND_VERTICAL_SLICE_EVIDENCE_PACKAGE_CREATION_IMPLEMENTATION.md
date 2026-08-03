# MILESTONE-036 - Concrete Application Command Vertical Slice (EvidencePackage Creation) Implementation

## 1. Document Status

**Status: CANDIDATE_FOR_INDEPENDENT_IMPLEMENTATION_REVIEW**

Produced within the consolidated Macro Milestone Mission, per the protocol activated in M035's implementation freeze (Section 49). Not approved, not frozen.

## 2. Repository Authority

| Field | Value |
| --- | --- |
| Repository | `C:\Users\LuxSy\Documents\trading` |
| Branch | `master` |
| Frozen baseline HEAD | `5f3b8f69afdcd7b319fd0842efb80effde8f7991` |

## 3. Scope/Design Authority (This Mission)

- Scope: `MILESTONE_036_CONCRETE_APPLICATION_COMMAND_VERTICAL_SLICE_EVIDENCE_PACKAGE_CREATION_SCOPE.md` — selects one EvidencePackage creation command vertical slice.
- Design: `MILESTONE_036_CONCRETE_APPLICATION_COMMAND_VERTICAL_SLICE_EVIDENCE_PACKAGE_CREATION_DESIGN.md` — resolves identity model, Run-existence validation, result contract, error semantics.

Both produced in this same Macro Milestone Mission, per the active protocol; none frozen independently — all three (scope, design, implementation) await one consolidated independent review.

## 4. Baseline Validation

Recorded before any change, against HEAD `5f3b8f69afdcd7b319fd0842efb80effde8f7991`: `python tools/check_architecture.py .` exit 0; `ruff check .` clean; canonical `mypy` clean (92 source files); `pytest -q -m "not integration"` → 585 passed, 133 deselected, coverage 83.49%.

## 5. Implementation Map

One new production module; one export-only `__init__.py` change; one narrow architecture-checker addition (`"evidence"` to `ALLOWED["usecases"]`); two architecture-fixture changes (removed the now-obsolete `usecases/bad_evidence_import.py`, added `usecases/bad_review_import.py` and `evidence/bad_usecases_import.py`) plus the corresponding assertion updates in `test_module_boundaries.py`; three new test files.

## 6. Production Implementation

```python
@dataclass(frozen=True, slots=True)
class CreateEvidencePackageCommand:
    evidence_package_governance_id: str
    run_governance_id: str


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

Sole dependencies: `EvidencePackageRepository`, `RuntimeIdentifierGenerator`. No `RunRepository`, no `Clock` — verified by hostile self-audit (Section 12).

## 7. Architecture Impact

**Exactly one narrow addition, as pre-authorized by the design:** `ALLOWED["usecases"]` gained `"evidence"`. `FORBIDDEN_IMPORT_PREFIXES["usecases"]` unchanged. `python tools/check_architecture.py .` passes at exit 0.

**Fixture maintenance (required consequence, not scope creep):** the pre-existing negative fixture `usecases/bad_evidence_import.py` proved `usecases` could not import `evidence` — now legitimately allowed, so it was removed (its assertion would otherwise silently stop triggering, exactly the staleness risk M033 handled identically for its own `bad_run_import.py`). Replaced with `usecases/bad_review_import.py` (proves `usecases` still cannot import `review`) and `evidence/bad_usecases_import.py` (proves the reverse direction — `evidence` cannot import `usecases` — new evidence, mirroring the `run/bad_usecases_import.py`/`campaign/bad_usecases_import.py` precedent). `test_module_boundaries.py`'s assertion list updated accordingly (`"usecases may not import evidence"` removed; `"usecases may not import review"` and `"evidence may not import usecases"` added). Both architecture tests pass: `test_current_source_tree_respects_boundaries`, `test_negative_fixture_detects_illegal_import`.

## 8. Identity, Run-Existence, and Result Semantics

Identity: caller-supplied raw governance-ID string + handler-generated runtime ID via `RuntimeIdentifierGenerator.generate()` (called exactly once) — mirrors `CreateRunHandler` exactly, independently justified in the design (Section 4) as the correct model for a *creation* command (nothing exists yet to reference via full `DomainIdentity`).

Run-existence: **not** validated by any application-level `RunRepository` lookup — enforced entirely by the real `evidence_package.run_id → run.governance_id` foreign key, verified directly against the concrete adapter's exception path (design Section 3): a FK violation (SQLSTATE `23503`) is not classified as a unique violation by `unique_violation_constraint_name`, so it reaches the bare `raise` — an unmodified `FoundationError`, never translated, exactly mirroring M033's own hostile-review-verified Campaign-existence mechanism, independently re-confirmed here against `EvidencePackage`'s own adapter code, not merely asserted by analogy.

Result: `DomainIdentity[EvidencePackageId]` (the newly created identity), mirroring `CreateRunHandler`'s return, independently justified in the design (Section 6) as correct for creation (no "before" state, caller needs the new identity to reference this package going forward).

## 9. Error Semantics

Transparent, unchanged propagation of `AggregateAlreadyExists` (duplicate `governance_id`/`runtime_id`), `InvalidAggregateForPersistence`, and the raw `FoundationError` for the missing-Run FK-violation scenario. No handler-level `try`/`except`.

## 10. Tests Added and Reused

**Added** (23 tests, all passing):

- `tests/contract/test_create_evidence_package_handler_contract.py` (3 tests): typed-conformance, `handle` signature shape, no-inheritance.
- `tests/unit/test_create_evidence_package_usecase.py` (15 tests): identity/generator/aggregate-construction/`add()`-call-count/return-value proofs; constructor-shape proof of no `RunRepository`; malformed-ID propagation (both IDs); `AggregateAlreadyExists`/generator-failure propagation; no-pre-read proof; `CommandEntryPoint` binding and reuse; plain-unvalidated-carrier proof.
- `tests/integration/test_m036_create_evidence_package_usecase.py` (5 tests, PostgreSQL, opt-in): golden path (state/version/collections all verified empty/`INITIALIZED`); duplicate governance-ID; duplicate runtime-ID; missing-Run raw `FoundationError`; no-production-composition.

**Reused/re-run for regression** (all passing, zero change): `tests/unit/test_create_run_usecase.py`, `tests/contract/test_create_run_handler_contract.py`, `tests/unit/test_get_run_usecase.py`, `tests/unit/test_authorize_run_usecase.py`, `tests/unit/test_run_aggregate.py`, `tests/architecture/test_module_boundaries.py`.

## 11. PostgreSQL Evidence — Executed Live

A fresh, disposable `postgres:17` container (`m036-postgres-impl`, isolated non-default host port) ran all 5 M036-specific tests: **PASSED**, including the FK-violation scenario (`test_missing_run_raises_raw_foundation_error_not_translated`, confirming `FoundationErrorCategory.PERSISTENCE`, not `AggregateAlreadyExists`, and confirming via `AggregateNotFound` on reload that no row was persisted). Full integration regression: **132 passed** (up from 127), 6 pre-existing skips unrelated to M036. Full suite with PostgreSQL opt-in: **735 passed** (up from 712), 6 skipped, 92.74% coverage. Container stopped and removed after evidence capture. No disclosed limitation.

## 12. Hostile Self-Audit

Grepped `create_evidence_package.py` directly for every prohibited pattern: `RunRepository`, `CampaignRepository`, `ReviewRepository`, persistence imports, `try`/`except`, loops, retry, cache, a second `.add(`, `.get(`/`.save(`/`.delete(` of any kind, every `EvidencePackage` mutation method (`start_collection`, `add_criterion_result`, `add_artifact_reference`, `.seal(`, `.invalidate(`), `Review`, registry/dispatcher/mediator, transport, `M037`. **Zero matches beyond the single expected `.add()` call and three docstring "for" false positives.**

## 13. Validation Gates

| Gate | Result |
| --- | --- |
| `git status --short` | exactly the 12 expected files (4 modified, 8 new) |
| `python tools/check_architecture.py .` | exit 0 |
| `ruff check .` / `ruff format --check .` | clean, 224 files formatted |
| canonical `mypy` | 93 source files, 0 issues |
| `pytest -q -m "not integration"` | 603 passed (was 585), 138 deselected, coverage 83.58% |
| `pytest tests/unit/test_create_run_usecase.py tests/contract/test_create_run_handler_contract.py tests/unit/test_get_run_usecase.py tests/unit/test_authorize_run_usecase.py tests/unit/test_run_aggregate.py tests/architecture/test_module_boundaries.py` | 93 passed |
| `pytest tests/integration/test_m036_create_evidence_package_usecase.py -v` (PostgreSQL, live) | **5 passed** |
| `pytest tests/integration/ -v` (PostgreSQL, live, full regression) | **132 passed, 6 skipped** |
| `pytest -q` (PostgreSQL opt-in, full suite) | **735 passed, 6 skipped**, 92.74% coverage |
| `python -m build --wheel` | succeeded; `create_evidence_package.py` present in built wheel |
| `python -m pip_audit` | no known vulnerabilities |
| `python tools/secret_scan_targets.py --root .` | 393 targets (up from 386, consistent with 6 new tracked files) |

## 14. Changed Files

```
A  MILESTONE_036_CONCRETE_APPLICATION_COMMAND_VERTICAL_SLICE_EVIDENCE_PACKAGE_CREATION_SCOPE.md
A  MILESTONE_036_CONCRETE_APPLICATION_COMMAND_VERTICAL_SLICE_EVIDENCE_PACKAGE_CREATION_DESIGN.md
A  MILESTONE_036_CONCRETE_APPLICATION_COMMAND_VERTICAL_SLICE_EVIDENCE_PACKAGE_CREATION_IMPLEMENTATION.md
M  PROJECT_CHECKPOINT.md
M  src/empirical_platform/usecases/__init__.py
A  src/empirical_platform/usecases/create_evidence_package.py
M  tools/check_architecture.py
M  tests/architecture/test_module_boundaries.py
D  tests/fixtures/illegal_imports/src/empirical_platform/usecases/bad_evidence_import.py
A  tests/fixtures/illegal_imports/src/empirical_platform/usecases/bad_review_import.py
A  tests/fixtures/illegal_imports/src/empirical_platform/evidence/bad_usecases_import.py
A  tests/contract/test_create_evidence_package_handler_contract.py
A  tests/integration/test_m036_create_evidence_package_usecase.py
A  tests/unit/test_create_evidence_package_usecase.py
```

## 15. Explicit Non-Changes

No change to: `EvidencePackage` aggregate; `EvidencePackageRepository`; `PostgresEvidencePackageRepository`; `Run`/`RunRepository`/`Campaign`/`CampaignRepository` and their adapters; identity/version contracts; `CommandHandler`/`CommandEntryPoint`; any schema or migration; any M020-M035 source or test file beyond the necessary architecture-fixture maintenance in Section 7; any M036 governance authority beyond this mission's own three documents.

## 16. Known Limitations

None. PostgreSQL evidence, including the FK-violation scenario, was fully executed live in this session.

## 17. Remaining Risks

None beyond those already inherent in the frozen design (deferred `EvidencePackage` retrieval/mutation, deferred `Review` work — both explicitly out of scope).

## 18. Review Status

**CANDIDATE_FOR_INDEPENDENT_IMPLEMENTATION_REVIEW.** Scope, design, and implementation are all candidates within this single consolidated mission, per the active Macro Milestone Protocol. None frozen.

## 19. Next Permitted Action

**MILESTONE-036 INDEPENDENT IMPLEMENTATION REVIEW** (covering scope, design, implementation, tests, evidence, and the external-review package as one consolidated review, per the active protocol).
