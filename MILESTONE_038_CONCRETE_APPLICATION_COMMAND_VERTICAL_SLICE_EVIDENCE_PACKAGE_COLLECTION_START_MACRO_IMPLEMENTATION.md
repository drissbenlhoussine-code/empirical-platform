# MILESTONE-038 - Concrete Application Command Vertical Slice (EvidencePackage Collection Start) Macro Implementation

## 1. Document Status

**Status: CANDIDATE_FOR_COMPLETE_INDEPENDENT_MACRO_REVIEW**

Produced within the consolidated Macro Milestone Mission, per the protocol activated in M035's implementation freeze (Section 49), used previously in M036 and M037. Not approved, not frozen.

## 2. Repository Authority

| Field | Value |
| --- | --- |
| Repository | `C:\Users\LuxSy\Documents\trading` |
| Branch | `master` |
| Frozen baseline HEAD | `4674601db269da2e2b554e13e16bc62564aeaa08` (`docs: record M037 owner freeze commit hash`, pushed; M037 Owner Freeze) |

## 3. Scope/Design Authority (This Mission)

- Scope: `MILESTONE_038_CONCRETE_APPLICATION_COMMAND_VERTICAL_SLICE_EVIDENCE_PACKAGE_COLLECTION_START_MACRO_SCOPE.md` — selects `EvidencePackage.start_collection()`, justified against 8 evaluated candidates from a fresh architecture inventory.
- Design: `MILESTONE_038_CONCRETE_APPLICATION_COMMAND_VERTICAL_SLICE_EVIDENCE_PACKAGE_COLLECTION_START_MACRO_DESIGN.md` — resolves command contract, and independently derives a new deterministic-conflict-scenario mechanism (Section 6) since `EvidencePackage` has no non-transition interfering write available while `INITIALIZED`, unlike Campaign/Run.

Both produced in this same Macro Milestone Mission; none frozen independently — all three (scope, design, implementation) await one consolidated independent review.

## 4. Baseline Validation

Recorded before any change, against HEAD `4674601db269da2e2b554e13e16bc62564aeaa08`: `python tools/check_architecture.py .` exit 0; `ruff check .`/`ruff format --check .` clean; canonical `mypy` clean (94 source files); `pytest -q -m "not integration"` → 624 passed, 142 deselected.

## 5. Implementation Map

One new production module (`start_evidence_package_collection.py`); one export-only `__init__.py` change. **No architecture-checker change** — `usecases` already has `evidence` in `ALLOWED` (since M036), independently re-verified live (`git diff` on `tools/check_architecture.py` for this mission's commit range is empty). Three new test files.

## 6. Production Implementation

```python
@dataclass(frozen=True, slots=True)
class StartEvidencePackageCollectionCommand:
    identity: DomainIdentity[EvidencePackageId]
    expected_persisted_version: AggregateVersion
    actor: str
    occurred_at: datetime
    correlation_id: str | None = None
    reason: str | None = None


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

Sole dependency: `EvidencePackageRepository`. No `RunRepository`, no `CampaignRepository` — verified by hostile self-audit (Section 12).

## 7. Architecture Impact

**None.** `python tools/check_architecture.py .` passes at exit 0 with zero source change to `tools/check_architecture.py`. No fixture maintenance was required.

## 8. Command and Result Semantics

Command fields mirror `AuthorizeRunCommand` exactly (`identity`, `expected_persisted_version`, `actor`, `occurred_at`, `correlation_id`, `reason`) — independently justified in the design (Section 4) since `start_collection()`'s own signature requires the identical field set. Result: `SaveResult`, mirroring `AuthorizeRunHandler`'s/`PrepareCampaignForAuthorizationHandler`'s return contract (design Section 9).

## 9. Deterministic Conflict Mechanism — Disclosed Boundary

**Independently derived, not copied from M032/M035 (design Section 6):** `EvidencePackage` has no non-transition mutation available while `INITIALIZED` — `start_collection()` is the only method operating on that state. Two independently loaded callers racing the same transition therefore produce a domain-level `ValueError` (the second caller's own `start_collection()` call is invalid once the first has already advanced the durable state to `COLLECTING`, so it never reaches `save()`) — **not** a repository-level `OptimisticConcurrencyConflict`. This is a genuine, disclosed boundary of this specific transition (design Section 20), independently reproduced live against real PostgreSQL (Section 11) and not misrepresented as a standard `OptimisticConcurrencyConflict` PostgreSQL reproduction. `OptimisticConcurrencyConflict` propagation itself remains fully proven at the unit level via a fake repository unconstrained by `EvidencePackage`'s own state machine (Section 10).

## 10. Error Semantics

Transparent, unchanged propagation of `AggregateNotFound`, the domain `ValueError` (invalid-state `start_collection()`), `OptimisticConcurrencyConflict` (proven at unit level per Section 9), and `InvalidAggregateForPersistence`. No handler-level `try`/`except`.

## 11. Tests Added and Reused

**Added** (28 tests, all passing):

- `tests/contract/test_start_evidence_package_collection_handler_contract.py` (3 tests): typed-conformance, `handle` signature shape, no-inheritance.
- `tests/unit/test_start_evidence_package_collection_usecase.py` (21 tests): command field/immutability/no-validation proofs; `get()`-then-`start_collection()`-then-`save()` sequence and call-count proofs; command-version-not-loaded-persisted-version proof; transition-history proof; domain `ValueError` propagation with `save()` never called; `AggregateNotFound`/arbitrary-`get()`-exception propagation; `OptimisticConcurrencyConflict`/arbitrary-`save()`-exception propagation via a fake repository unconstrained by the aggregate's own state machine; `CommandEntryPoint` binding and reuse.
- `tests/integration/test_m038_start_evidence_package_collection_usecase.py` (4 tests, PostgreSQL, opt-in): golden path; two-racing-callers domain `ValueError` (Section 9); missing-identity `AggregateNotFound`; no-production-composition.

**Reused/re-run for regression** (all passing, zero change): `tests/unit/test_authorize_run_usecase.py`, `tests/contract/test_authorize_run_handler_contract.py`, `tests/unit/test_get_evidence_package_usecase.py`, `tests/contract/test_get_evidence_package_handler_contract.py`, `tests/unit/test_create_evidence_package_usecase.py`, `tests/contract/test_create_evidence_package_handler_contract.py`, `tests/architecture/test_module_boundaries.py`.

## 12. Hostile Self-Audit

Grepped `start_evidence_package_collection.py` directly for every prohibited pattern: `add()`, every `EvidencePackage` mutation method other than `start_collection` (`add_criterion_result`, `add_artifact_reference`, `.seal(`, `.invalidate(`), `Review`, `RunRepository`/`CampaignRepository`, registry/dispatcher/mediator, `M039`, `try`/`except`, loops. **Zero genuine matches; two docstring "for" false positives** ("for an existing EvidencePackage", "for one command"), mirroring the established false-positive pattern from every prior milestone. Exactly one `.get(` and one `.save(` call, as required.

## 13. Validation Gates

| Gate | Result |
| --- | --- |
| `git status --short` | exactly the 6 expected files (1 modified, 5 new) |
| `python tools/check_architecture.py .` | exit 0, zero source change |
| `ruff check .` / `ruff format --check .` | clean, 232 files formatted |
| canonical `mypy` | 95 source files, 0 issues |
| `pytest -q -m "not integration"` | 648 passed (was 624), 146 deselected, coverage 83.79% |
| `pytest tests/unit/test_authorize_run_usecase.py tests/contract/test_authorize_run_handler_contract.py tests/unit/test_get_evidence_package_usecase.py tests/contract/test_get_evidence_package_handler_contract.py tests/unit/test_create_evidence_package_usecase.py tests/contract/test_create_evidence_package_handler_contract.py tests/architecture/test_module_boundaries.py` | 65 passed |
| `pytest tests/integration/test_m038_start_evidence_package_collection_usecase.py -v` (PostgreSQL, live) | **4 passed** |
| `pytest tests/integration/ -v` (PostgreSQL, live, full regression) | **140 passed, 6 skipped** |
| `pytest -q` (PostgreSQL opt-in, full suite) | **788 passed, 6 skipped**, 92.83% coverage |
| `python -m build --wheel` | succeeded; `start_evidence_package_collection.py` present in built wheel |
| `python -m pip_audit` | no known vulnerabilities |
| `python tools/secret_scan_targets.py --root .` | 410 targets, captured before this implementation document itself existed on disk |

## 14. Changed Files

```
A  MILESTONE_038_CONCRETE_APPLICATION_COMMAND_VERTICAL_SLICE_EVIDENCE_PACKAGE_COLLECTION_START_MACRO_SCOPE.md
A  MILESTONE_038_CONCRETE_APPLICATION_COMMAND_VERTICAL_SLICE_EVIDENCE_PACKAGE_COLLECTION_START_MACRO_DESIGN.md
A  MILESTONE_038_CONCRETE_APPLICATION_COMMAND_VERTICAL_SLICE_EVIDENCE_PACKAGE_COLLECTION_START_MACRO_IMPLEMENTATION.md
M  PROJECT_CHECKPOINT.md
M  src/empirical_platform/usecases/__init__.py
A  src/empirical_platform/usecases/start_evidence_package_collection.py
A  tests/contract/test_start_evidence_package_collection_handler_contract.py
A  tests/integration/test_m038_start_evidence_package_collection_usecase.py
A  tests/unit/test_start_evidence_package_collection_usecase.py
```

## 15. Explicit Non-Changes

No change to: `EvidencePackage` aggregate; `EvidencePackageRepository`; `PostgresEvidencePackageRepository`; `Run`/`RunRepository`/`Campaign`/`CampaignRepository` and their adapters; `create_evidence_package.py`/`get_evidence_package.py`; identity/version contracts; `CommandHandler`/`CommandEntryPoint`; `tools/check_architecture.py`; any architecture fixture; any schema or migration; any M020-M037 source or test file; any M038 governance authority beyond this mission's own three documents.

## 16. Known Limitations

The PostgreSQL "conflict" evidence for this specific transition manifests as a domain `ValueError`, not `OptimisticConcurrencyConflict` — disclosed and explained in Section 9, not a hidden gap. `OptimisticConcurrencyConflict` propagation itself is fully covered at the unit level. No other limitation.

## 17. Remaining Risks

None beyond those already inherent in the frozen design. `EvidencePackage`'s create-retrieve-transition trio is now complete (M036/M037/M038); remaining deferred work (`add_criterion_result`/`add_artifact_reference`/`seal`/`invalidate`, `Review` work) is explicitly out of scope.

## 18. Review Status

**CANDIDATE_FOR_COMPLETE_INDEPENDENT_MACRO_REVIEW.** Scope, design, and implementation are all candidates within this single consolidated mission, per the active Macro Milestone Protocol. None frozen.

## 19. Next Permitted Action

**MILESTONE-038 COMPLETE INDEPENDENT HOSTILE MACRO REVIEW** (covering scope, design, implementation, tests, evidence, and the external-review package as one consolidated review, per the active protocol).
