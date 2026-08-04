# MILESTONE-041 - Concrete Application Command Vertical Slice (EvidencePackage Sealing) Macro Implementation

## 1. Document Status

**Status: CANDIDATE_FOR_COMPLETE_INDEPENDENT_MACRO_REVIEW**

Produced within the consolidated Macro Milestone Mission, per the protocol activated in M035's implementation freeze (Section 49), used previously in M036 through M040. Not approved, not frozen.

## 2. Repository Authority

| Field | Value |
| --- | --- |
| Repository | `C:\Users\LuxSy\Documents\trading` |
| Branch | `master` |
| Frozen baseline HEAD | `917bd9aa80ce5168d416a0501ae72befad7bd8a8` (`docs: record M040 owner freeze commit hash`, pushed; M040 Owner Freeze) |

## 3. Scope/Design Authority (This Mission)

- Scope: `MILESTONE_041_CONCRETE_APPLICATION_COMMAND_VERTICAL_SLICE_EVIDENCE_PACKAGE_SEALING_MACRO_SCOPE.md` — selects `EvidencePackage.seal()`, the first milestone in this lineage whose own preconditions are satisfiable exclusively via frozen application commands, and defers Review creation a fourth time to preserve semantic alignment with a genuinely sealed target.
- Design: `MILESTONE_041_CONCRETE_APPLICATION_COMMAND_VERTICAL_SLICE_EVIDENCE_PACKAGE_SEALING_MACRO_DESIGN.md` — a transition-command shape identical to M038's, but with a genuinely new two-sided precondition (both `criterion_results` and `artifact_references` non-empty) requiring three distinct domain-`ValueError` test scenarios.

Both produced in this same Macro Milestone Mission; none frozen independently — all three (scope, design, implementation) await one consolidated independent review.

## 4. Baseline Validation

Recorded before any change, against HEAD `917bd9aa80ce5168d416a0501ae72befad7bd8a8`: `python tools/check_architecture.py .` exit 0; `ruff check .`/`ruff format --check .` clean; canonical `mypy` clean (97 source files); `pytest -q -m "not integration"` → 699 passed, 158 deselected.

## 5. Implementation Map

One new production module (`seal_evidence_package.py`); one export-only `__init__.py` change. **No architecture-checker change** — `usecases` already has `evidence` in `ALLOWED` (since M036). Three new test files.

## 6. Production Implementation

```python
@dataclass(frozen=True, slots=True)
class SealEvidencePackageCommand:
    identity: DomainIdentity[EvidencePackageId]
    expected_persisted_version: AggregateVersion
    actor: str
    occurred_at: datetime
    correlation_id: str | None = None
    reason: str | None = None


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

Sole dependency: `EvidencePackageRepository`. No `RunRepository`, no `CampaignRepository` — verified by hostile self-audit (Section 12). Field-for-field identical to `StartEvidencePackageCollectionCommand`/`StartEvidencePackageCollectionHandler` (M038) — the two-collection precondition is entirely `EvidencePackage.seal()`'s own concern, never duplicated in the handler.

## 7. Architecture Impact

**None.** `python tools/check_architecture.py .` passes at exit 0 with zero source change to `tools/check_architecture.py`. No fixture maintenance was required.

## 8. Command and Result Semantics

Six command fields, identical shape to `StartEvidencePackageCollectionCommand`. Result: `SaveResult`, mirroring every prior transition command (M032, M035, M038).

## 9. Preconditions — Newly Reachable via Frozen Commands Only

For the first time in this lineage, every one of this milestone's own preconditions (`COLLECTING` state, non-empty `criterion_results`, non-empty `artifact_references`) is satisfiable using exclusively frozen application commands: M036 (`add`) → M038 (`start_collection`) → M039 (`add_criterion_result`) → M040 (`add_artifact_reference`) → `seal()`. No test scaffolding bypass of any kind was required for setup, unlike the risk M040's own scope document identified for `seal()` before this milestone.

## 10. Error Semantics — Three Distinct Domain-ValueError Scenarios

Transparent, unchanged propagation of `AggregateNotFound`, `OptimisticConcurrencyConflict`, `InvalidAggregateForPersistence`, and — uniquely among every transition command to date — **three** independently distinguishable domain `ValueError` scenarios: empty `criterion_results`, empty `artifact_references`, and invalid lifecycle state. Each independently tested at both unit and PostgreSQL integration level (Section 11). No handler-level `try`/`except`.

## 11. Tests Added and Reused

**Added** (34 tests, all passing):

- `tests/contract/test_seal_evidence_package_handler_contract.py` (3 tests): typed-conformance, `handle` signature shape, no-inheritance.
- `tests/unit/test_seal_evidence_package_usecase.py` (24 tests): command field/immutability/no-validation proofs; `get()`-then-`seal()`-then-`save()` sequence and call-count proofs; command-version-not-loaded-persisted-version proof; transition-history proof; collection-preservation proof (no `add_criterion_result`/`add_artifact_reference`/`invalidate`/`start_collection` call); all three domain-`ValueError` scenarios (empty criterion results, empty artifact references, already-`SEALED` state) with `save()` never called; `AggregateNotFound`/arbitrary-`get()`-exception propagation; `OptimisticConcurrencyConflict`/arbitrary-`save()`-exception propagation via a fake repository; `CommandEntryPoint` binding and reuse.
- `tests/integration/test_m041_seal_evidence_package_usecase.py` (7 tests, PostgreSQL, opt-in): golden path; empty-criterion-results; empty-artifact-references; already-`SEALED` invalid-state; missing-identity `AggregateNotFound`; **genuine deterministic `OptimisticConcurrencyConflict`**; no-production-composition.

**Reused/re-run for regression** (all passing, zero change): `tests/unit/test_record_evidence_package_artifact_reference_usecase.py`, `tests/contract/test_record_evidence_package_artifact_reference_handler_contract.py`, `tests/unit/test_record_evidence_package_criterion_result_usecase.py`, `tests/contract/test_record_evidence_package_criterion_result_handler_contract.py`, `tests/unit/test_start_evidence_package_collection_usecase.py`, `tests/contract/test_start_evidence_package_collection_handler_contract.py`, `tests/architecture/test_module_boundaries.py`.

## 12. Hostile Self-Audit

Grepped `seal_evidence_package.py` directly for every prohibited pattern: `add()`, `add_criterion_result`, `add_artifact_reference`, `.invalidate(`, `start_collection`, `Review`, `RunRepository`/`CampaignRepository`, registry/dispatcher/mediator, `M042`, `try`/`except`, loops. **Zero genuine matches; one docstring "for" false positive**, mirroring the established false-positive pattern from every prior milestone. Exactly one `.get(` and one `.save(` call, as required.

## 13. Validation Gates

| Gate | Result |
| --- | --- |
| `git status --short` | exactly the 6 expected files (1 modified, 5 new) |
| `python tools/check_architecture.py .` | exit 0, zero source change |
| `ruff check .` / `ruff format --check .` | clean, 244 files formatted |
| canonical `mypy` | 98 source files, 0 issues |
| `pytest -q -m "not integration"` | 726 passed (was 699), 165 deselected, coverage 84.10% |
| `pytest tests/unit/test_record_evidence_package_artifact_reference_usecase.py tests/contract/test_record_evidence_package_artifact_reference_handler_contract.py tests/unit/test_record_evidence_package_criterion_result_usecase.py tests/contract/test_record_evidence_package_criterion_result_handler_contract.py tests/unit/test_start_evidence_package_collection_usecase.py tests/contract/test_start_evidence_package_collection_handler_contract.py tests/architecture/test_module_boundaries.py` | 77 passed |
| `pytest tests/integration/test_m041_seal_evidence_package_usecase.py -v` (PostgreSQL, live) | **7 passed** |
| `pytest tests/integration/ -v` (PostgreSQL, live, full regression) | **159 passed, 6 skipped** |
| `pytest -q` (PostgreSQL opt-in, full suite) | **885 passed, 6 skipped**, 92.97% coverage |
| `python -m build --wheel` | succeeded; `seal_evidence_package.py` present in built wheel |
| `python -m pip_audit` | no known vulnerabilities |
| `python tools/secret_scan_targets.py --root .` | 434 targets, captured before this implementation document itself existed on disk |

## 14. Changed Files

```
A  MILESTONE_041_CONCRETE_APPLICATION_COMMAND_VERTICAL_SLICE_EVIDENCE_PACKAGE_SEALING_MACRO_SCOPE.md
A  MILESTONE_041_CONCRETE_APPLICATION_COMMAND_VERTICAL_SLICE_EVIDENCE_PACKAGE_SEALING_MACRO_DESIGN.md
A  MILESTONE_041_CONCRETE_APPLICATION_COMMAND_VERTICAL_SLICE_EVIDENCE_PACKAGE_SEALING_MACRO_IMPLEMENTATION.md
M  PROJECT_CHECKPOINT.md
M  src/empirical_platform/usecases/__init__.py
A  src/empirical_platform/usecases/seal_evidence_package.py
A  tests/contract/test_seal_evidence_package_handler_contract.py
A  tests/integration/test_m041_seal_evidence_package_usecase.py
A  tests/unit/test_seal_evidence_package_usecase.py
```

## 15. Explicit Non-Changes

No change to: `EvidencePackage` aggregate; `EvidencePackageRepository`; `PostgresEvidencePackageRepository`; `Run`/`RunRepository`/`Campaign`/`CampaignRepository` and their adapters; `create_evidence_package.py`/`get_evidence_package.py`/`start_evidence_package_collection.py`/`record_evidence_package_criterion_result.py`/`record_evidence_package_artifact_reference.py`; identity/version contracts; `CommandHandler`/`CommandEntryPoint`; `tools/check_architecture.py`; any architecture fixture; any schema or migration; any M020-M040 source or test file; any M041 governance authority beyond this mission's own three documents.

## 16. Known Limitations

None. PostgreSQL evidence, including the genuine deterministic `OptimisticConcurrencyConflict` scenario and both distinct empty-collection precondition failures, was fully executed live in this session with no disclosed boundary.

## 17. Remaining Risks

None beyond those already inherent in the frozen design. `EvidencePackage`'s lifecycle-completion path is now proven (create → collect → record → seal); `invalidate()` becomes cleanly reachable at a future milestone using only frozen application commands. Remaining deferred work (`invalidate`, `Review` work) is explicitly out of scope.

## 18. Review Status

**CANDIDATE_FOR_COMPLETE_INDEPENDENT_MACRO_REVIEW.** Scope, design, and implementation are all candidates within this single consolidated mission, per the active Macro Milestone Protocol. None frozen.

## 19. Next Permitted Action

**MILESTONE-041 COMPLETE INDEPENDENT HOSTILE MACRO REVIEW** (covering scope, design, implementation, tests, evidence, and the external-review package as one consolidated review, per the active protocol).
