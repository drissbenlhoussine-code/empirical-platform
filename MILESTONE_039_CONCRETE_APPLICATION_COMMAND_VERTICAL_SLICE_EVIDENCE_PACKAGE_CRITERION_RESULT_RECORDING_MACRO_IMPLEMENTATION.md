# MILESTONE-039 - Concrete Application Command Vertical Slice (EvidencePackage Criterion-Result Recording) Macro Implementation

## 1. Document Status

**Status: CANDIDATE_FOR_COMPLETE_INDEPENDENT_MACRO_REVIEW**

Produced within the consolidated Macro Milestone Mission, per the protocol activated in M035's implementation freeze (Section 49), used previously in M036, M037, and M038. Not approved, not frozen.

## 2. Repository Authority

| Field | Value |
| --- | --- |
| Repository | `C:\Users\LuxSy\Documents\trading` |
| Branch | `master` |
| Frozen baseline HEAD | `35cbdd09792abedb41382098241f1c39eb889f25` (`docs: record M038 owner freeze commit hash`, pushed; M038 Owner Freeze) |

## 3. Scope/Design Authority (This Mission)

- Scope: `MILESTONE_039_CONCRETE_APPLICATION_COMMAND_VERTICAL_SLICE_EVIDENCE_PACKAGE_CRITERION_RESULT_RECORDING_MACRO_SCOPE.md` — selects `EvidencePackage.add_criterion_result()`, justified against 8 evaluated candidates including a seriously considered and independently rejected Review-creation candidate.
- Design: `MILESTONE_039_CONCRETE_APPLICATION_COMMAND_VERTICAL_SLICE_EVIDENCE_PACKAGE_CRITERION_RESULT_RECORDING_MACRO_DESIGN.md` — resolves command contract and, critically, closes the real-`OptimisticConcurrencyConflict` gap M038 explicitly could not close (design Section 6).

Both produced in this same Macro Milestone Mission; none frozen independently — all three (scope, design, implementation) await one consolidated independent review.

## 4. Baseline Validation

Recorded before any change, against HEAD `35cbdd09792abedb41382098241f1c39eb889f25`: `python tools/check_architecture.py .` exit 0; `ruff check .`/`ruff format --check .` clean; canonical `mypy` clean (95 source files); `pytest -q -m "not integration"` → 648 passed, 146 deselected.

## 5. Implementation Map

One new production module (`record_evidence_package_criterion_result.py`); one export-only `__init__.py` change. **No architecture-checker change** — `usecases` already has `evidence` in `ALLOWED` (since M036). Three new test files.

## 6. Production Implementation

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

Sole dependency: `EvidencePackageRepository`. No `RunRepository`, no `CampaignRepository` — verified by hostile self-audit (Section 12). `evidence_package_id` on the constructed `CriterionResult` is derived from `package.identity.governance_id`, never from a separate command field — there is no such field on the command at all (design Section 4).

## 7. Architecture Impact

**None.** `python tools/check_architecture.py .` passes at exit 0 with zero source change to `tools/check_architecture.py`. No fixture maintenance was required.

## 8. Command and Result Semantics

Seven command fields, none redundant with `CriterionResult`'s own `evidence_package_id` (design Section 4/21). Result: `SaveResult`, mirroring every prior `save()`-based command (M032, M035, M038).

## 9. Deterministic Conflict Mechanism — Genuinely Closed the M038 Gap

Unlike M038's `start_collection()` (no non-transition interfering write available while `INITIALIZED`), `add_criterion_result()` operates on `COLLECTING`, which has a genuine sibling method — `add_artifact_reference()` — available as a state-preserving, version-advancing interfering write. **This milestone independently reproduced a genuine `OptimisticConcurrencyConflict` against real PostgreSQL** (Section 11) through the natural application call sequence, with no repository bypass and no fabricated database state — closing the boundary M038's own freeze record explicitly disclosed as unavailable for that capability.

## 10. Error Semantics

Transparent, unchanged propagation of `AggregateNotFound`, the domain `ValueError` (invalid-state `add_criterion_result()` call, or duplicate `criterion_id`), `OptimisticConcurrencyConflict` (genuinely reproducible per Section 9), and `InvalidAggregateForPersistence`. No handler-level `try`/`except`.

## 11. Tests Added and Reused

**Added** (32 tests, all passing):

- `tests/contract/test_record_evidence_package_criterion_result_handler_contract.py` (3 tests): typed-conformance, `handle` signature shape, no-inheritance.
- `tests/unit/test_record_evidence_package_criterion_result_usecase.py` (23 tests): command field/immutability/no-validation proofs; `evidence_package_id`-derived-not-supplied proof; `get()`-then-`add_criterion_result()`-then-`save()` sequence and call-count proofs; command-version-not-loaded-persisted-version proof; no-`add_artifact_reference`/`seal`/`start_collection` proof; domain `ValueError` propagation (invalid state, duplicate `criterion_id`) with `save()` never called; `AggregateNotFound`/arbitrary-`get()`-exception propagation; `OptimisticConcurrencyConflict`/arbitrary-`save()`-exception propagation via a fake repository; `CommandEntryPoint` binding and reuse.
- `tests/integration/test_m039_record_evidence_package_criterion_result_usecase.py` (6 tests, PostgreSQL, opt-in): golden path; invalid-state; duplicate-`criterion_id`; missing-identity `AggregateNotFound`; **genuine deterministic `OptimisticConcurrencyConflict`**; no-production-composition.

**Reused/re-run for regression** (all passing, zero change): `tests/unit/test_start_evidence_package_collection_usecase.py`, `tests/contract/test_start_evidence_package_collection_handler_contract.py`, `tests/unit/test_get_evidence_package_usecase.py`, `tests/contract/test_get_evidence_package_handler_contract.py`, `tests/unit/test_create_evidence_package_usecase.py`, `tests/contract/test_create_evidence_package_handler_contract.py`, `tests/architecture/test_module_boundaries.py`.

## 12. Hostile Self-Audit

Grepped `record_evidence_package_criterion_result.py` directly for every prohibited pattern: `add()`, `add_artifact_reference`, `.seal(`, `.invalidate(`, `start_collection`, `Review`, `RunRepository`/`CampaignRepository`, registry/dispatcher/mediator, `M040`, `try`/`except`, loops. **Zero genuine matches; one docstring "for" false positive**, mirroring the established false-positive pattern from every prior milestone. Exactly one `.get(` and one `.save(` call, as required.

## 13. Validation Gates

| Gate | Result |
| --- | --- |
| `git status --short` | exactly the 6 expected files (1 modified, 5 new) |
| `python tools/check_architecture.py .` | exit 0, zero source change |
| `ruff check .` / `ruff format --check .` | clean, 236 files formatted |
| canonical `mypy` | 96 source files, 0 issues |
| `pytest -q -m "not integration"` | 674 passed (was 648), 152 deselected, coverage 83.91% |
| `pytest tests/unit/test_start_evidence_package_collection_usecase.py tests/contract/test_start_evidence_package_collection_handler_contract.py tests/unit/test_get_evidence_package_usecase.py tests/contract/test_get_evidence_package_handler_contract.py tests/unit/test_create_evidence_package_usecase.py tests/contract/test_create_evidence_package_handler_contract.py tests/architecture/test_module_boundaries.py` | 65 passed |
| `pytest tests/integration/test_m039_record_evidence_package_criterion_result_usecase.py -v` (PostgreSQL, live) | **6 passed** |
| `pytest tests/integration/ -v` (PostgreSQL, live, full regression) | **146 passed, 6 skipped** |
| `pytest -q` (PostgreSQL opt-in, full suite) | **820 passed, 6 skipped**, 92.88% coverage |
| `python -m build --wheel` | succeeded; `record_evidence_package_criterion_result.py` present in built wheel |
| `python -m pip_audit` | no known vulnerabilities |
| `python tools/secret_scan_targets.py --root .` | 418 targets, captured before this implementation document itself existed on disk |

## 14. Changed Files

```
A  MILESTONE_039_CONCRETE_APPLICATION_COMMAND_VERTICAL_SLICE_EVIDENCE_PACKAGE_CRITERION_RESULT_RECORDING_MACRO_SCOPE.md
A  MILESTONE_039_CONCRETE_APPLICATION_COMMAND_VERTICAL_SLICE_EVIDENCE_PACKAGE_CRITERION_RESULT_RECORDING_MACRO_DESIGN.md
A  MILESTONE_039_CONCRETE_APPLICATION_COMMAND_VERTICAL_SLICE_EVIDENCE_PACKAGE_CRITERION_RESULT_RECORDING_MACRO_IMPLEMENTATION.md
M  PROJECT_CHECKPOINT.md
M  src/empirical_platform/usecases/__init__.py
A  src/empirical_platform/usecases/record_evidence_package_criterion_result.py
A  tests/contract/test_record_evidence_package_criterion_result_handler_contract.py
A  tests/integration/test_m039_record_evidence_package_criterion_result_usecase.py
A  tests/unit/test_record_evidence_package_criterion_result_usecase.py
```

## 15. Explicit Non-Changes

No change to: `EvidencePackage` aggregate; `EvidencePackageRepository`; `PostgresEvidencePackageRepository`; `Run`/`RunRepository`/`Campaign`/`CampaignRepository` and their adapters; `create_evidence_package.py`/`get_evidence_package.py`/`start_evidence_package_collection.py`; identity/version contracts; `CommandHandler`/`CommandEntryPoint`; `tools/check_architecture.py`; any architecture fixture; any schema or migration; any M020-M038 source or test file; any M039 governance authority beyond this mission's own three documents.

## 16. Known Limitations

None. PostgreSQL evidence, including the genuine deterministic `OptimisticConcurrencyConflict` scenario, was fully executed live in this session with no disclosed boundary of the kind M038 required.

## 17. Remaining Risks

None beyond those already inherent in the frozen design. `EvidencePackage`'s owned-collection-append write pattern is now proven; remaining deferred work (`add_artifact_reference`, `seal`, `invalidate`, `Review` work) is explicitly out of scope.

## 18. Review Status

**CANDIDATE_FOR_COMPLETE_INDEPENDENT_MACRO_REVIEW.** Scope, design, and implementation are all candidates within this single consolidated mission, per the active Macro Milestone Protocol. None frozen.

## 19. Next Permitted Action

**MILESTONE-039 COMPLETE INDEPENDENT HOSTILE MACRO REVIEW** (covering scope, design, implementation, tests, evidence, and the external-review package as one consolidated review, per the active protocol).
