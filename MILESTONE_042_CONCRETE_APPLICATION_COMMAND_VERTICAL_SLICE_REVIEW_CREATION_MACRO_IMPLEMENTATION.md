# MILESTONE-042 - Concrete Application Command Vertical Slice (Review Creation) Macro Implementation

## 1. Document Status

**Status: CANDIDATE_FOR_COMPLETE_INDEPENDENT_MACRO_REVIEW**

Produced within the consolidated Macro Milestone Mission, per the protocol activated in M035's implementation freeze (Section 49), used previously in M036 through M041. Not approved, not frozen.

## 2. Repository Authority

| Field | Value |
| --- | --- |
| Repository | `C:\Users\LuxSy\Documents\trading` |
| Branch | `master` |
| Frozen baseline HEAD | `95c52eaeeb28c65f8eabf8feccace7d24cb6967f` (`docs: record M041 owner freeze commit hash`, pushed; M041 Owner Freeze) |

## 3. Scope/Design Authority (This Mission)

- Scope: `MILESTONE_042_CONCRETE_APPLICATION_COMMAND_VERTICAL_SLICE_REVIEW_CREATION_MACRO_SCOPE.md` — selects `Review` creation after a fresh, complete architecture inventory found `Review` the only aggregate in the entire domain model with zero application-layer proof of any verb, and confirmed the precondition four prior scope documents (M037/M039/M040/M041) had each independently deferred Review pending — `EvidencePackage` reaching a genuinely `SEALED` state via frozen commands — is now satisfied.
- Design: `MILESTONE_042_CONCRETE_APPLICATION_COMMAND_VERTICAL_SLICE_REVIEW_CREATION_MACRO_DESIGN.md` — the third proof of the `add()`-with-real-FK pattern (after M033, M036), applied to `Review` → `EvidencePackage`.

Both produced in this same Macro Milestone Mission; none frozen independently — all three (scope, design, implementation) await one consolidated independent review.

## 4. Baseline Validation

Recorded before any change, against HEAD `95c52eaeeb28c65f8eabf8feccace7d24cb6967f`: `python tools/check_architecture.py .` exit 0; `ruff check .`/`ruff format --check .` clean; canonical `mypy` clean (98 source files); `pytest -q -m "not integration"` → 726 passed, 165 deselected.

## 5. Implementation Map

One new production module (`create_review.py`); one export-only `__init__.py` change; one narrow architecture-checker addition (`"review"` added to `ALLOWED["usecases"]`); fixture maintenance (removed the now-obsolete `usecases/bad_review_import.py`, added `review/bad_usecases_import.py`, updated the corresponding assertions in `test_module_boundaries.py`). Three new test files.

## 6. Production Implementation

```python
@dataclass(frozen=True, slots=True)
class CreateReviewCommand:
    review_governance_id: str
    target_evidence_package_governance_id: str
    reviewer_reference: str


class CreateReviewHandler:
    __slots__ = ("_review_repository", "_runtime_identifier_generator")

    def __init__(self, *, review_repository, runtime_identifier_generator) -> None:
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

Sole dependencies: `ReviewRepository`, `RuntimeIdentifierGenerator`. No `EvidencePackageRepository`, no `RunRepository`, no `CampaignRepository` — verified by hostile self-audit (Section 12) and independently re-confirmed via direct-SQL adversarial testing (Section 13).

## 7. Architecture Impact

**Exactly one narrow addition, as pre-authorized by the design:** `ALLOWED["usecases"]` gained `"review"`. `FORBIDDEN_IMPORT_PREFIXES["usecases"]` unchanged. `python tools/check_architecture.py .` passes at exit 0.

**Fixture maintenance (required consequence, not scope creep):** the pre-existing negative fixture `usecases/bad_review_import.py` proved `usecases` could not import `review` — now legitimately allowed, so it was removed (its assertion would otherwise silently stop triggering, the identical staleness risk M036 handled for its own `bad_evidence_import.py`). Replaced with `review/bad_usecases_import.py` (new reverse-direction evidence: `review` cannot import `usecases`, mirroring the `campaign`/`run`/`evidence` precedent — `review` was the only aggregate missing this fixture, confirmed live before this milestone). `test_module_boundaries.py`'s assertion list updated accordingly. Both architecture tests pass: `test_current_source_tree_respects_boundaries`, `test_negative_fixture_detects_illegal_import`.

## 8. Identity, Target-Existence, and Result Semantics

Identity: caller-supplied raw governance-ID string + handler-generated runtime ID via `RuntimeIdentifierGenerator.generate()` (called exactly once) — mirrors `CreateEvidencePackageHandler`/`CreateRunHandler` exactly.

Target existence: **not** validated by any application-level `EvidencePackageRepository` lookup — enforced entirely by the real `review.target_evidence_package_id → evidence_package.governance_id` foreign key, verified directly against the concrete adapter's exception path (design Section 11): a FK violation (SQLSTATE `23503`) is not classified as a unique violation by `unique_violation_constraint_name`, so it reaches the bare `raise` — an unmodified `FoundationError`, mirroring M033's/M036's own hostile-review-verified pattern, independently re-confirmed here against `Review`'s own adapter code and via direct-SQL testing (Section 13), not merely asserted by analogy.

Result: `DomainIdentity[ReviewId]` (the newly created identity), mirroring `CreateEvidencePackageHandler`'s/`CreateRunHandler`'s return.

## 9. Error Semantics

Transparent, unchanged propagation of `AggregateAlreadyExists` (duplicate `governance_id`/`runtime_id`), `InvalidAggregateForPersistence`, and the raw `FoundationError` for the missing-target FK-violation scenario. No handler-level `try`/`except`.

## 10. Tests Added and Reused

**Added** (24 tests, all passing):

- `tests/contract/test_create_review_handler_contract.py` (3 tests): typed-conformance, `handle` signature shape, no-inheritance.
- `tests/unit/test_create_review_usecase.py` (16 tests): identity/generator/aggregate-construction/`add()`-call-count/return-value proofs; constructor-shape proof of no `EvidencePackageRepository` dependency; malformed-ID propagation (all three fields, including the empty-reviewer-reference case); `AggregateAlreadyExists`/generator-failure propagation; no-pre-read proof; `CommandEntryPoint` binding and reuse; plain-unvalidated-carrier proof.
- `tests/integration/test_m042_create_review_usecase.py` (5 tests, PostgreSQL, opt-in): golden path (against a genuinely `SEALED` target — the real-world-aligned scenario this milestone's scope selected Review for); duplicate governance-ID; duplicate runtime-ID; missing-target raw `FoundationError`; no-production-composition.

**Reused/re-run for regression** (all passing, zero change): `tests/unit/test_create_evidence_package_usecase.py`, `tests/contract/test_create_evidence_package_handler_contract.py`, `tests/unit/test_create_run_usecase.py`, `tests/contract/test_create_run_handler_contract.py`, `tests/architecture/test_module_boundaries.py`.

## 11. PostgreSQL Evidence — Executed Live

A fresh, disposable `postgres:17` container ran all 5 M042-specific tests: **PASSED**, including the FK-violation scenario, confirmed via `FoundationErrorCategory.PERSISTENCE` (not `AggregateAlreadyExists`) and via `AggregateNotFound` on reload that no row was persisted. Full integration regression: **164 passed** (up from 159), 6 pre-existing skips unrelated to M042. Full suite with PostgreSQL opt-in: **909 passed** (up from 885), 6 skipped, 93.06% coverage. Container stopped and removed after evidence capture.

## 12. Hostile Self-Audit — Static

Grepped `create_review.py` directly for every prohibited pattern: `EvidencePackageRepository`, `RunRepository`, `CampaignRepository`, persistence imports, `try`/`except`, loops, retry, cache, a second `.add(`, `.get(`/`.save(`/`.delete(` of any kind, every `Review` mutation method (`start`, `add_finding`, `complete`, `cancel`), registry/dispatcher/mediator, transport, `M043`. **Zero matches beyond the single expected `.add()` call and one docstring "for" false positive.**

## 13. Hostile Self-Audit — Direct-SQL Adversarial Verification

Beyond static review, a standalone script bypassing the repository/ORM layer entirely — querying PostgreSQL with raw SQL for all verification reads, mirroring the identical technique M041's independent hostile review used — was written and run against a fresh disposable container. Full transcript: `evidence/hostile-self-review-direct-sql-verification.txt`. Key findings, all independently confirmed via raw SQL row inspection, not ORM-mediated reads: (1) Review creation genuinely succeeds against an `EvidencePackage` still `INITIALIZED` (deliberately chosen as the adversarial case) — confirming no hidden state dependency exists beyond the documented FK-only constraint; (2) duplicate governance-ID genuinely raises `AggregateAlreadyExists` with zero duplicate row inserted; (3) missing target genuinely raises an unmodified `FoundationError(category=PERSISTENCE)` with zero row inserted; (4) a freshly created `Review` has exactly zero `review_finding` and zero `review_transition` rows. No contradiction found.

## 14. Validation Gates

| Gate | Result |
| --- | --- |
| `git status --short` | exactly the 9 expected files (3 modified, 1 deleted, 5 new — plus 2 governance docs already present from Phases 3-4) |
| `python tools/check_architecture.py .` | exit 0 |
| `ruff check .` / `ruff format --check .` | clean, 248 files formatted |
| canonical `mypy` | 99 source files, 0 issues |
| `pytest -q -m "not integration"` | 745 passed (was 726), 170 deselected, coverage 84.20% |
| `pytest tests/unit/test_create_evidence_package_usecase.py tests/contract/test_create_evidence_package_handler_contract.py tests/unit/test_create_run_usecase.py tests/contract/test_create_run_handler_contract.py tests/architecture/test_module_boundaries.py` | 38 passed |
| `pytest tests/integration/test_m042_create_review_usecase.py -v` (PostgreSQL, live) | **5 passed** |
| `pytest tests/integration/ -v` (PostgreSQL, live, full regression) | **164 passed, 6 skipped** |
| `pytest -q` (PostgreSQL opt-in, full suite) | **909 passed, 6 skipped**, 93.06% coverage |
| `python -m build --wheel` | succeeded; `create_review.py` present in built wheel |
| `python -m pip_audit` | no known vulnerabilities |
| `python tools/secret_scan_targets.py --root .` | 442 targets, captured before this implementation document itself existed on disk |

## 15. Changed Files

```
A  MILESTONE_042_CONCRETE_APPLICATION_COMMAND_VERTICAL_SLICE_REVIEW_CREATION_MACRO_SCOPE.md
A  MILESTONE_042_CONCRETE_APPLICATION_COMMAND_VERTICAL_SLICE_REVIEW_CREATION_MACRO_DESIGN.md
A  MILESTONE_042_CONCRETE_APPLICATION_COMMAND_VERTICAL_SLICE_REVIEW_CREATION_MACRO_IMPLEMENTATION.md
M  PROJECT_CHECKPOINT.md
M  src/empirical_platform/usecases/__init__.py
A  src/empirical_platform/usecases/create_review.py
M  tools/check_architecture.py
M  tests/architecture/test_module_boundaries.py
D  tests/fixtures/illegal_imports/src/empirical_platform/usecases/bad_review_import.py
A  tests/fixtures/illegal_imports/src/empirical_platform/review/bad_usecases_import.py
A  tests/contract/test_create_review_handler_contract.py
A  tests/integration/test_m042_create_review_usecase.py
A  tests/unit/test_create_review_usecase.py
```

## 16. Explicit Non-Changes

No change to: `Review` aggregate; `ReviewRepository`; `PostgresReviewRepository`; `ConcreteReviewMapper`; `EvidencePackage`/`Run`/`Campaign` and their repositories/adapters; identity/version contracts; `CommandHandler`/`CommandEntryPoint`; any schema or migration; any M020-M041 source or test file beyond the necessary architecture-fixture maintenance in Section 7; any M042 governance authority beyond this mission's own three documents.

## 17. Known Limitations

None. PostgreSQL evidence, including the FK-violation scenario and the direct-SQL adversarial verification, was fully executed live in this session.

## 18. Remaining Risks

None beyond those already inherent in the frozen design (deferred `Review` retrieval and lifecycle transitions — both explicitly out of scope, both natural future candidates).

## 19. Review Status

**CANDIDATE_FOR_COMPLETE_INDEPENDENT_MACRO_REVIEW.** Scope, design, and implementation are all candidates within this single consolidated mission, per the active Macro Milestone Protocol. None frozen.

## 20. Next Permitted Action

**MILESTONE-042 COMPLETE INDEPENDENT HOSTILE MACRO REVIEW** (covering scope, design, implementation, tests, evidence, and the external-review package as one consolidated review, per the active protocol).
