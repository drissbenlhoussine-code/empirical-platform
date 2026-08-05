# MILESTONE-044 - Concrete Application Command Vertical Slice: Review Lifecycle Transition - Macro Implementation

## 1. Document Status

**Status: CANDIDATE_FOR_COMPLETE_INDEPENDENT_MACRO_REVIEW**

Produced in the same consolidated M044 mission as the scope and design documents.

## 2. Repository Authority

| Field | Value |
| --- | --- |
| Repository | `C:\Users\LuxSy\Documents\trading` |
| Branch | `master` |
| M044 frozen baseline | `a2902092755bef6951e11512183240b33a463088` |

## 3. Delivered Capability

Transition of an existing, `ASSIGNED` `Review` to `IN_PROGRESS`, via `StartReviewCommand`/`StartReviewHandler` (`src/empirical_platform/usecases/start_review.py`).

## 4. Production Source

```python
@dataclass(frozen=True, slots=True)
class StartReviewCommand:
    identity: DomainIdentity[ReviewId]
    expected_persisted_version: AggregateVersion
    actor: str
    occurred_at: datetime
    correlation_id: str | None = None
    reason: str | None = None


class StartReviewHandler:
    __slots__ = ("_review_repository",)

    def __init__(self, *, review_repository: ReviewRepository) -> None:
        self._review_repository = review_repository

    def handle(self, command: StartReviewCommand) -> SaveResult:
        loaded = self._review_repository.get(command.identity)
        review = loaded.aggregate
        review.start(
            actor=command.actor,
            occurred_at=command.occurred_at,
            correlation_id=command.correlation_id,
            reason=command.reason,
        )
        return self._review_repository.save(
            review, expected_persisted_version=command.expected_persisted_version
        )
```

## 5. Changed-File Surface

```
A  MILESTONE_044_CONCRETE_APPLICATION_COMMAND_VERTICAL_SLICE_REVIEW_LIFECYCLE_TRANSITION_MACRO_DESIGN.md
A  MILESTONE_044_CONCRETE_APPLICATION_COMMAND_VERTICAL_SLICE_REVIEW_LIFECYCLE_TRANSITION_MACRO_IMPLEMENTATION.md
A  MILESTONE_044_CONCRETE_APPLICATION_COMMAND_VERTICAL_SLICE_REVIEW_LIFECYCLE_TRANSITION_MACRO_SCOPE.md
M  PROJECT_CHECKPOINT.md
A  src/empirical_platform/usecases/start_review.py
M  src/empirical_platform/usecases/__init__.py
A  tests/contract/test_start_review_handler_contract.py
A  tests/integration/test_m044_start_review_usecase.py
A  tests/unit/test_start_review_usecase.py
```

Nine files. No architecture-checker or fixture change required — `usecases` already permits `review` (added M042).

## 6. Architecture Impact

None. `python tools/check_architecture.py .` exit 0, independently re-verified after this implementation.

## 7. Conflict Feasibility — Result

As independently determined in the scope/design documents (not assumed by analogy): `Review` has no state-preserving mutation reachable while `ASSIGNED`. Two racing callers against the same `ASSIGNED` Review produce a **domain-level `ValueError`** (the second caller's own fresh `get()` sees `IN_PROGRESS` already, failing its own `start()` precondition check before ever reaching `save()`) — independently reproduced against real PostgreSQL (`test_two_racing_callers_second_start_raises_domain_value_error`). `OptimisticConcurrencyConflict` propagation itself is proven exclusively at the unit level via a fake repository (`test_optimistic_concurrency_conflict_from_save_propagates_unchanged`), mirroring M038's identical, already-accepted resolution for `start_collection()`.

## 8. Test Evidence

- Focused unit + contract: **24 passed** (21 unit + 3 contract).
- Non-integration suite: **790 passed** (up from 766), 178 deselected (up from 174), coverage 84.39%.
- M044 focused PostgreSQL integration (fresh disposable `postgres:17` container, port 55544): **4 passed**, including the golden path and the two-racing-callers domain-`ValueError` race.
- Full integration regression: **172 passed** (up from 168), 6 skipped.
- Full suite with PostgreSQL: **962 passed** (up from 934), 6 skipped, coverage 93.15%.
- `ruff format --check` / `ruff check`: clean, 256 files formatted.
- Canonical `mypy`: clean, 101 source files.
- `pip-audit`: no known vulnerabilities.
- Secret-scan target count: 458 (452 tracked post-M043-freeze + 6 new untracked files at implementation time), independently reconciled — no anomaly.

## 9. Hostile Self-Audit

Targeted prohibited-pattern grep on `start_review.py` (`try:|except|retry|while |sleep(|Repository(|import psycopg|import boto3|import sqlalchemy`): **zero matches**. `usecases/__init__.py` diff confirmed purely additive (no line removed). Scope-creep grep across the full diff for `add_finding`/`.complete(`/`.cancel(`/`invalidate`/`M045`/`composition`/`registry`/`dispatcher`/`mediator`: the only matches are the negative-assertion test name/docstring (`test_no_production_composition_machinery_is_required`) proving the *absence* of composition machinery — zero genuine matches anywhere.

## 10. No-Scope-Creep Declaration

No `Review.add_finding()`/`complete()`/`cancel()` production capability; no `EvidencePackage.invalidate()`; no retry policy; no composition root, registry, dispatcher, mediator, service locator, or DI framework; no transport/API layer; no schema/migration change; no MILESTONE-045 work.

## 11. Status

**CANDIDATE_FOR_COMPLETE_INDEPENDENT_MACRO_REVIEW.**
