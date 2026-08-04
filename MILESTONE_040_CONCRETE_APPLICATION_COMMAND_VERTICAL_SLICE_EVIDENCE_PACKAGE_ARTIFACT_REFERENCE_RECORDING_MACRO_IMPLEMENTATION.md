# MILESTONE-040 - Concrete Application Command Vertical Slice (EvidencePackage Artifact-Reference Recording) Macro Implementation

## 1. Document Status

**Status: CANDIDATE_FOR_COMPLETE_INDEPENDENT_MACRO_REVIEW**

Produced within the consolidated Macro Milestone Mission, per the protocol activated in M035's implementation freeze (Section 49), used previously in M036 through M039. Not approved, not frozen.

## 2. Repository Authority

| Field | Value |
| --- | --- |
| Repository | `C:\Users\LuxSy\Documents\trading` |
| Branch | `master` |
| Frozen baseline HEAD | `0fc2e29b4420ec51b0fcda56d0d3892702d1d8ed` (`docs: record M039 owner freeze commit hash`, pushed; M039 Owner Freeze) |

## 3. Scope/Design Authority (This Mission)

- Scope: `MILESTONE_040_CONCRETE_APPLICATION_COMMAND_VERTICAL_SLICE_EVIDENCE_PACKAGE_ARTIFACT_REFERENCE_RECORDING_MACRO_SCOPE.md` — selects `EvidencePackage.add_artifact_reference()`, explicitly rejecting `seal()` as unreachable without a scaffolding compromise and rejecting Review creation on architectural-leverage grounds, not merely because its FK exists.
- Design: `MILESTONE_040_CONCRETE_APPLICATION_COMMAND_VERTICAL_SLICE_EVIDENCE_PACKAGE_ARTIFACT_REFERENCE_RECORDING_MACRO_DESIGN.md` — the simplest command shape of any milestone to date (no ownership-derivation question, unlike M039), and a genuine deterministic-conflict mechanism mirroring M039's own in reverse.

Both produced in this same Macro Milestone Mission; none frozen independently — all three (scope, design, implementation) await one consolidated independent review.

## 4. Baseline Validation

Recorded before any change, against HEAD `0fc2e29b4420ec51b0fcda56d0d3892702d1d8ed`: `python tools/check_architecture.py .` exit 0; `ruff check .`/`ruff format --check .` clean; canonical `mypy` clean (96 source files); `pytest -q -m "not integration"` → 674 passed, 152 deselected.

## 5. Implementation Map

One new production module (`record_evidence_package_artifact_reference.py`); one export-only `__init__.py` change. **No architecture-checker change** — `usecases` already has `evidence` in `ALLOWED` (since M036). Three new test files.

## 6. Production Implementation

```python
@dataclass(frozen=True, slots=True)
class RecordEvidencePackageArtifactReferenceCommand:
    identity: DomainIdentity[EvidencePackageId]
    expected_persisted_version: AggregateVersion
    value: str


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

Sole dependency: `EvidencePackageRepository`. No `RunRepository`, no `CampaignRepository` — verified by hostile self-audit (Section 12). Three fields total; `ArtifactReference` is constructed inline from `command.value` with no ownership-derivation step (unlike M039), since `ArtifactReference` carries no `evidence_package_id` field.

## 7. Architecture Impact

**None.** `python tools/check_architecture.py .` passes at exit 0 with zero source change to `tools/check_architecture.py`. No fixture maintenance was required.

## 8. Command and Result Semantics

Three command fields — the simplest of any milestone to date. Result: `SaveResult`, mirroring every prior `save()`-based command (M032, M035, M038, M039).

## 9. Deterministic Conflict Mechanism — Reverse Pairing of M039

`add_artifact_reference()` operates on `COLLECTING`, which has a genuine, now-frozen sibling method — `add_criterion_result()` (M039) — usable as the interfering write, the exact reverse of M039's own mechanism. **This milestone independently reproduced a genuine `OptimisticConcurrencyConflict` against real PostgreSQL** through the natural application call sequence, with no repository bypass and no fabricated database state.

## 10. Error Semantics

Transparent, unchanged propagation of `AggregateNotFound`, the domain `ValueError` (invalid-state call, or duplicate `value`), `OptimisticConcurrencyConflict` (genuinely reproducible per Section 9), and `InvalidAggregateForPersistence`. No handler-level `try`/`except`.

## 11. Tests Added and Reused

**Added** (31 tests, all passing):

- `tests/contract/test_record_evidence_package_artifact_reference_handler_contract.py` (3 tests): typed-conformance, `handle` signature shape, no-inheritance.
- `tests/unit/test_record_evidence_package_artifact_reference_usecase.py` (22 tests): command field/immutability/no-validation proofs; no-`evidence_package_id`-field proof; `get()`-then-`add_artifact_reference()`-then-`save()` sequence and call-count proofs; command-version-not-loaded-persisted-version proof; no-`add_criterion_result`/`seal`/`start_collection` proof; domain `ValueError` propagation (invalid state, duplicate `value`) with `save()` never called; `AggregateNotFound`/arbitrary-`get()`-exception propagation; `OptimisticConcurrencyConflict`/arbitrary-`save()`-exception propagation via a fake repository; `CommandEntryPoint` binding and reuse.
- `tests/integration/test_m040_record_evidence_package_artifact_reference_usecase.py` (6 tests, PostgreSQL, opt-in): golden path; invalid-state; duplicate-`value`; missing-identity `AggregateNotFound`; **genuine deterministic `OptimisticConcurrencyConflict`**; no-production-composition.

**Reused/re-run for regression** (all passing, zero change): `tests/unit/test_record_evidence_package_criterion_result_usecase.py`, `tests/contract/test_record_evidence_package_criterion_result_handler_contract.py`, `tests/unit/test_start_evidence_package_collection_usecase.py`, `tests/contract/test_start_evidence_package_collection_handler_contract.py`, `tests/unit/test_get_evidence_package_usecase.py`, `tests/contract/test_get_evidence_package_handler_contract.py`, `tests/architecture/test_module_boundaries.py`.

## 12. Hostile Self-Audit

Grepped `record_evidence_package_artifact_reference.py` directly for every prohibited pattern: `add()`, `add_criterion_result`, `.seal(`, `.invalidate(`, `start_collection`, `Review`, `RunRepository`/`CampaignRepository`, registry/dispatcher/mediator, `M041`, `try`/`except`, loops. **Zero genuine matches; one docstring "for" false positive**, mirroring the established false-positive pattern from every prior milestone. Exactly one `.get(` and one `.save(` call, as required.

## 13. Validation Gates

| Gate | Result |
| --- | --- |
| `git status --short` | exactly the 6 expected files (1 modified, 5 new) |
| `python tools/check_architecture.py .` | exit 0, zero source change |
| `ruff check .` / `ruff format --check .` | clean, 240 files formatted |
| canonical `mypy` | 97 source files, 0 issues |
| `pytest -q -m "not integration"` | 699 passed (was 674), 158 deselected, coverage 84.00% |
| `pytest tests/unit/test_record_evidence_package_criterion_result_usecase.py tests/contract/test_record_evidence_package_criterion_result_handler_contract.py tests/unit/test_start_evidence_package_collection_usecase.py tests/contract/test_start_evidence_package_collection_handler_contract.py tests/unit/test_get_evidence_package_usecase.py tests/contract/test_get_evidence_package_handler_contract.py tests/architecture/test_module_boundaries.py` | 73 passed |
| `pytest tests/integration/test_m040_record_evidence_package_artifact_reference_usecase.py -v` (PostgreSQL, live) | **6 passed** |
| `pytest tests/integration/ -v` (PostgreSQL, live, full regression) | **152 passed, 6 skipped** |
| `pytest -q` (PostgreSQL opt-in, full suite) | **851 passed, 6 skipped**, 92.92% coverage |
| `python -m build --wheel` | succeeded; `record_evidence_package_artifact_reference.py` present in built wheel |
| `python -m pip_audit` | no known vulnerabilities |
| `python tools/secret_scan_targets.py --root .` | 426 targets, captured before this implementation document itself existed on disk |

## 14. Changed Files

```
A  MILESTONE_040_CONCRETE_APPLICATION_COMMAND_VERTICAL_SLICE_EVIDENCE_PACKAGE_ARTIFACT_REFERENCE_RECORDING_MACRO_SCOPE.md
A  MILESTONE_040_CONCRETE_APPLICATION_COMMAND_VERTICAL_SLICE_EVIDENCE_PACKAGE_ARTIFACT_REFERENCE_RECORDING_MACRO_DESIGN.md
A  MILESTONE_040_CONCRETE_APPLICATION_COMMAND_VERTICAL_SLICE_EVIDENCE_PACKAGE_ARTIFACT_REFERENCE_RECORDING_MACRO_IMPLEMENTATION.md
M  PROJECT_CHECKPOINT.md
M  src/empirical_platform/usecases/__init__.py
A  src/empirical_platform/usecases/record_evidence_package_artifact_reference.py
A  tests/contract/test_record_evidence_package_artifact_reference_handler_contract.py
A  tests/integration/test_m040_record_evidence_package_artifact_reference_usecase.py
A  tests/unit/test_record_evidence_package_artifact_reference_usecase.py
```

## 15. Explicit Non-Changes

No change to: `EvidencePackage` aggregate; `EvidencePackageRepository`; `PostgresEvidencePackageRepository`; `Run`/`RunRepository`/`Campaign`/`CampaignRepository` and their adapters; `create_evidence_package.py`/`get_evidence_package.py`/`start_evidence_package_collection.py`/`record_evidence_package_criterion_result.py`; identity/version contracts; `CommandHandler`/`CommandEntryPoint`; `tools/check_architecture.py`; any architecture fixture; any schema or migration; any M020-M039 source or test file; any M040 governance authority beyond this mission's own three documents.

## 16. Known Limitations

None. PostgreSQL evidence, including the genuine deterministic `OptimisticConcurrencyConflict` scenario, was fully executed live in this session with no disclosed boundary.

## 17. Remaining Risks

None beyond those already inherent in the frozen design. `EvidencePackage`'s owned-collection-append vocabulary is now complete (both `add_criterion_result` and `add_artifact_reference` proven); `seal()` is now cleanly reachable at a future milestone using only frozen application commands for its own precondition setup. Remaining deferred work (`seal`, `invalidate`, `Review` work) is explicitly out of scope.

## 18. Review Status

**CANDIDATE_FOR_COMPLETE_INDEPENDENT_MACRO_REVIEW.** Scope, design, and implementation are all candidates within this single consolidated mission, per the active Macro Milestone Protocol. None frozen.

## 19. Next Permitted Action

**MILESTONE-040 COMPLETE INDEPENDENT HOSTILE MACRO REVIEW** (covering scope, design, implementation, tests, evidence, and the external-review package as one consolidated review, per the active protocol).
