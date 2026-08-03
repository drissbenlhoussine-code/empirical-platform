# MILESTONE-037 - Concrete Application Query Vertical Slice (EvidencePackage Retrieval) Macro Implementation

## 1. Document Status

**Status: CANDIDATE_FOR_COMPLETE_INDEPENDENT_MACRO_REVIEW**

Produced within the consolidated Macro Milestone Mission, per the protocol activated in M035's implementation freeze (Section 49) and used previously in M036. Not approved, not frozen.

## 2. Repository Authority

| Field | Value |
| --- | --- |
| Repository | `C:\Users\LuxSy\Documents\trading` |
| Branch | `master` |
| Frozen baseline HEAD | `ce65d890404c975a10821224c501cd386fd63e6f` (`docs: record M036 owner freeze commit hash`, pushed; M036 Owner Freeze) |

## 3. Scope/Design Authority (This Mission)

- Scope: `MILESTONE_037_CONCRETE_APPLICATION_QUERY_VERTICAL_SLICE_EVIDENCE_PACKAGE_RETRIEVAL_MACRO_SCOPE.md` — selects EvidencePackage retrieval, justified against 8 evaluated candidates from a fresh architecture inventory.
- Design: `MILESTONE_037_CONCRETE_APPLICATION_QUERY_VERTICAL_SLICE_EVIDENCE_PACKAGE_RETRIEVAL_MACRO_DESIGN.md` — resolves query identity model, result contract, error semantics.

Both produced in this same Macro Milestone Mission; none frozen independently — all three (scope, design, implementation) await one consolidated independent review.

## 4. Baseline Validation

Recorded before any change, against HEAD `ce65d890404c975a10821224c501cd386fd63e6f`: `python tools/check_architecture.py .` exit 0; `ruff check .`/`ruff format --check .` clean; canonical `mypy` clean (93 source files); `pytest -q -m "not integration"` → 603 passed, 138 deselected.

## 5. Implementation Map

One new production module (`get_evidence_package.py`); one export-only `__init__.py` change. **No architecture-checker change** — `usecases` already has `evidence` in `ALLOWED` (added in M036), so this read-only query used an already-permitted import edge, exactly as the design (Section 15) predicted and this session independently re-verified live (Section 7). Three new test files.

## 6. Production Implementation

```python
@dataclass(frozen=True, slots=True)
class GetEvidencePackageQuery:
    identity: DomainIdentity[EvidencePackageId]


@dataclass(frozen=True, slots=True)
class EvidencePackageSnapshot:
    identity: DomainIdentity[EvidencePackageId]
    run_id: RunId
    state: EvidencePackageLifecycleState


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

Sole dependency: `EvidencePackageRepository`. No write call of any kind — verified by hostile self-audit (Section 12).

## 7. Architecture Impact

**None.** `python tools/check_architecture.py .` passes at exit 0 with zero source change to `tools/check_architecture.py` — independently re-verified live in this session (`git diff tools/check_architecture.py` empty). No fixture maintenance was required.

## 8. Identity and Result Semantics

Identity: caller-supplied full `DomainIdentity[EvidencePackageId]`, passed unchanged to the already-frozen `EvidencePackageRepository.get()` (M020/M023) — mirrors `GetRunQuery`/`GetCampaignQuery` exactly, independently justified in the design (Section 4) since a governance-ID-only lookup would require altering the frozen repository Protocol.

Result: `EvidencePackageSnapshot(identity, run_id, state)` — deliberately bounded, excluding `version`, `persisted_version`, `criterion_results`, `artifact_references`, and `transition_history`, mirroring `RunSnapshot`'s own established exclusions (design Section 6).

## 9. Error Semantics

Transparent, unchanged propagation of `AggregateNotFound` and `InvalidPersistedAggregateState`. No handler-level `try`/`except`.

## 10. Tests Added and Reused

**Added** (24 tests, all passing):

- `tests/contract/test_get_evidence_package_handler_contract.py` (3 tests): typed-conformance, `handle` signature shape, no-inheritance.
- `tests/unit/test_get_evidence_package_usecase.py` (18 tests): identity-preservation, exactly-one-`get()`-call proof, no-add/save-call proof, snapshot field-set/immutability proof, aggregate-non-mutation proof, aggregate-version-vs-persisted-version non-conflation proof, criterion-results/artifact-references/transition-history non-exposure proof (both empty and non-empty source states), `AggregateNotFound`/arbitrary-exception propagation, `QueryEntryPoint` binding and reuse.
- `tests/integration/test_m037_get_evidence_package_usecase.py` (4 tests, PostgreSQL, opt-in): golden path; missing-identity `AggregateNotFound`; no-production-composition; criterion-result/artifact-reference/transition table eager-load regression.

**Reused/re-run for regression** (all passing, zero change): `tests/unit/test_get_run_usecase.py`, `tests/contract/test_get_run_handler_contract.py`, `tests/unit/test_create_evidence_package_usecase.py`, `tests/contract/test_create_evidence_package_handler_contract.py`, `tests/unit/test_get_campaign_usecase.py`, `tests/architecture/test_module_boundaries.py`.

## 11. PostgreSQL Evidence — Executed Live

A fresh, disposable `postgres:17` container (`m037-postgres-impl`, isolated non-default host port `55437`) ran all 4 M037-specific tests: **PASSED**, including the not-found scenario (`test_missing_full_identity_raises_aggregate_not_found`) and the eager-load regression (`test_criterion_result_and_artifact_reference_tables_load_without_error`). Full integration regression: **136 passed** (up from 132), 6 pre-existing skips unrelated to M037. Full suite with PostgreSQL opt-in: **760 passed** (up from 735), 6 skipped, 92.78% coverage. No disclosed limitation.

## 12. Hostile Self-Audit

Grepped `get_evidence_package.py` directly for every prohibited pattern: `add()`, `save()`/`delete()` of any kind, every `EvidencePackage` mutation method (`start_collection`, `add_criterion_result`, `add_artifact_reference`, `.seal(`, `.invalidate(`), `Review`, `RunRepository`/`CampaignRepository`, registry/dispatcher/mediator, `M038`, `try`/`except`, loops. **Zero genuine matches; one docstring "for one" false positive** (mirrors M036's own three-false-positive precedent exactly). Exactly one `.get(` call, as required.

## 13. Validation Gates

| Gate | Result |
| --- | --- |
| `git status --short` | exactly the 6 expected files (1 modified, 5 new) |
| `python tools/check_architecture.py .` | exit 0, zero source change |
| `ruff check .` / `ruff format --check .` | clean, 228 files formatted |
| canonical `mypy` | 94 source files, 0 issues |
| `pytest -q -m "not integration"` | 624 passed (was 603), 142 deselected, coverage 83.68% |
| `pytest tests/unit/test_get_run_usecase.py tests/contract/test_get_run_handler_contract.py tests/unit/test_create_evidence_package_usecase.py tests/contract/test_create_evidence_package_handler_contract.py tests/unit/test_get_campaign_usecase.py tests/architecture/test_module_boundaries.py` | 57 passed |
| `pytest tests/integration/test_m037_get_evidence_package_usecase.py -v` (PostgreSQL, live) | **4 passed** |
| `pytest tests/integration/ -v` (PostgreSQL, live, full regression) | **136 passed, 6 skipped** |
| `pytest -q` (PostgreSQL opt-in, full suite) | **760 passed, 6 skipped**, 92.78% coverage |
| `python -m build --wheel` | succeeded; `get_evidence_package.py` present in built wheel |
| `python -m pip_audit` | no known vulnerabilities |
| `python tools/secret_scan_targets.py --root .` | 402 targets, captured at evidence-collection time (before this implementation document itself existed on disk), up from 395 at M036's own package-evidence capture |

## 14. Changed Files

```
A  MILESTONE_037_CONCRETE_APPLICATION_QUERY_VERTICAL_SLICE_EVIDENCE_PACKAGE_RETRIEVAL_MACRO_SCOPE.md
A  MILESTONE_037_CONCRETE_APPLICATION_QUERY_VERTICAL_SLICE_EVIDENCE_PACKAGE_RETRIEVAL_MACRO_DESIGN.md
A  MILESTONE_037_CONCRETE_APPLICATION_QUERY_VERTICAL_SLICE_EVIDENCE_PACKAGE_RETRIEVAL_MACRO_IMPLEMENTATION.md
M  PROJECT_CHECKPOINT.md
M  src/empirical_platform/usecases/__init__.py
A  src/empirical_platform/usecases/get_evidence_package.py
A  tests/contract/test_get_evidence_package_handler_contract.py
A  tests/integration/test_m037_get_evidence_package_usecase.py
A  tests/unit/test_get_evidence_package_usecase.py
```

## 15. Explicit Non-Changes

No change to: `EvidencePackage` aggregate; `EvidencePackageRepository`; `PostgresEvidencePackageRepository`; `Run`/`RunRepository`/`Campaign`/`CampaignRepository` and their adapters; identity/version contracts; `QueryHandler`/`QueryEntryPoint`; `tools/check_architecture.py`; any architecture fixture; any schema or migration; any M020-M036 source or test file; any M037 governance authority beyond this mission's own three documents.

## 16. Known Limitations

None. PostgreSQL evidence, including the not-found scenario and the collection-table eager-load regression, was fully executed live in this session.

## 17. Remaining Risks

None beyond those already inherent in the frozen design (deferred `EvidencePackage` mutation/`save()`, deferred `Review` work — both explicitly out of scope, per Section 11 of the scope document).

## 18. Review Status

**CANDIDATE_FOR_COMPLETE_INDEPENDENT_MACRO_REVIEW.** Scope, design, and implementation are all candidates within this single consolidated mission, per the active Macro Milestone Protocol. None frozen.

## 19. Next Permitted Action

**MILESTONE-037 COMPLETE INDEPENDENT HOSTILE MACRO REVIEW** (covering scope, design, implementation, tests, evidence, and the external-review package as one consolidated review, per the active protocol).
