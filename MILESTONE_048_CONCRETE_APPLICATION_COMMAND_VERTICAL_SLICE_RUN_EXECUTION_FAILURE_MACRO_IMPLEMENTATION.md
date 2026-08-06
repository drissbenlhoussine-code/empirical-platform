# MILESTONE-048 - Concrete Application Command Vertical Slice: Run Execution Failure - Macro Implementation

## 1. Document Status

**Status: CANDIDATE_FOR_COMPLETE_INDEPENDENT_MACRO_REVIEW**

Produced in the same consolidated M048 mission as the scope and design documents.

## 2. Repository Authority

| Field | Value |
| --- | --- |
| Repository | `C:\Users\LuxSy\Documents\trading` |
| Branch | `master` |
| M048 frozen baseline | `85706955abce892d14937ad00307717b6170085e` |

## 3. Delivered Capability

Failing an existing Run from any of its three execution-stage states (`ACQUIRING`, `NORMALIZING`, `VALIDATING`), via `FailRunCommand`/`FailRunHandler` (`src/empirical_platform/usecases/fail_run.py`).

## 4. Production Source

```python
@dataclass(frozen=True, slots=True)
class FailRunCommand:
    identity: DomainIdentity[RunId]
    expected_persisted_version: AggregateVersion
    reason: str
    actor: str
    occurred_at: datetime
    correlation_id: str | None = None


class FailRunHandler:
    __slots__ = ("_run_repository",)

    def __init__(self, *, run_repository: RunRepository) -> None:
        self._run_repository = run_repository

    def handle(self, command: FailRunCommand) -> SaveResult:
        loaded = self._run_repository.get(command.identity)
        run = loaded.aggregate
        run.fail(
            reason=command.reason,
            actor=command.actor,
            occurred_at=command.occurred_at,
            correlation_id=command.correlation_id,
        )
        return self._run_repository.save(
            run, expected_persisted_version=command.expected_persisted_version
        )
```

## 5. Changed-File Surface

```
A  MILESTONE_048_CONCRETE_APPLICATION_COMMAND_VERTICAL_SLICE_RUN_EXECUTION_FAILURE_MACRO_DESIGN.md
A  MILESTONE_048_CONCRETE_APPLICATION_COMMAND_VERTICAL_SLICE_RUN_EXECUTION_FAILURE_MACRO_IMPLEMENTATION.md
A  MILESTONE_048_CONCRETE_APPLICATION_COMMAND_VERTICAL_SLICE_RUN_EXECUTION_FAILURE_MACRO_SCOPE.md
M  PROJECT_CHECKPOINT.md
A  src/empirical_platform/usecases/fail_run.py
M  src/empirical_platform/usecases/__init__.py
A  tests/contract/test_fail_run_handler_contract.py
A  tests/integration/test_m048_fail_run_usecase.py
A  tests/unit/test_fail_run_usecase.py
```

Nine files. No architecture-checker or fixture change required — `usecases` already permits `run` (added M033).

## 6. Architecture Impact

None. `python tools/check_architecture.py .` exit 0, independently re-verified after this implementation.

## 7. Conflict Feasibility — Result (Empirically Confirmed, Not Assumed)

Scope Section 11 / design Section 13 raised conflict feasibility as an open question — whether `Run.append_manifest()` (M035's own frozen interfering write, state-preserving across `_MANIFEST_APPEND_STATES`) genuinely serves as a viable interfering write against `fail()` when failing from `ACQUIRING`. **Result: genuinely achievable.** The integration test `test_stale_expected_version_raises_optimistic_concurrency_conflict` independently confirmed, against real PostgreSQL: two independently-loaded callers, with the interfering write being `append_manifest()` (state-preserving, does not invalidate `fail()`'s own preconditions since `state` remains `ACQUIRING`, still within `fail()`'s allowed set), genuinely produces an unqualified `OptimisticConcurrencyConflict`. This reuses the mechanism M035 originally established (for `authorize()`) and M047 already reused once (`revise_scope_statement()` for `Campaign.cancel()`), applied here to a third target transition and re-confirmed empirically rather than assumed by analogy.

## 8. Test Evidence

- Focused unit + contract: **24 passed** (21 unit + 3 contract).
- M048 focused PostgreSQL integration (fresh disposable `postgres:17` container, port 55947): **6 passed**, including the genuine `OptimisticConcurrencyConflict` reproduction, the golden path from `ACQUIRING`, the invalid-state rejection from `AUTHORIZED`, and the empty-reason rejection.
- Full integration regression: **196 passed** (up from 190), 6 skipped.
- Full suite with PostgreSQL: **1088 passed** (up from 1058), 6 skipped, coverage 93.65%.
- `ruff format --check` / `ruff check`: clean, 272 files formatted.
- Canonical bare `mypy`: clean, 105 source files.
- `pip-audit`: no known vulnerabilities.
- Secret-scan target count: 490 at implementation time, reconciled exactly against the 7 new tracked files added since the M047 baseline (483 + 7 = 490).

## 9. Hostile Self-Audit

Targeted prohibited-pattern grep on `fail_run.py` (`try:|except|retry|while |sleep(|import psycopg|import boto3|import sqlalchemy|dispatcher|registry|locator|mediator`): zero matches. `usecases/__init__.py` diff confirmed purely additive (no line removed). A fresh, non-reused adversarial script independently confirmed: identity pass-through (`is` check), non-tautological expected-version pass-through (`loaded.persisted_version=777` vs `command.expected_persisted_version=42`, deliberately mismatched), exact `SaveResult` identity pass-through, and transparent propagation of six adversarial exception scenarios (`AggregateNotFound`, adversarial `LookupError`, domain `ValueError` from `AUTHORIZED`, domain `ValueError` from empty reason, adversarial `OSError`, genuine `OptimisticConcurrencyConflict`). Scope-creep grep across the full diff for `.start_acquisition(`/`.start_normalization(`/`.start_validation(`/`.complete_execution(`/`.cancel(`/`M049`/`composition`/`registry`/`dispatcher`/`mediator`: zero genuine matches inside `fail_run.py` itself (the test files' own fixtures call `start_acquisition()` directly as test setup only, exactly as documented in the design, Section 14, and the integration test file's own module docstring — never through any production command).

## 10. No-Scope-Creep Declaration

No `Run.start_acquisition()`/`start_normalization()`/`start_validation()`/`complete_execution()`/`cancel()` production capability (test-setup-only direct domain-method calls, never through a handler); no `Campaign`/`EvidencePackage`/`Review` capability; no retry policy; no composition root, registry, dispatcher, mediator, service locator, or DI framework; no transport/API layer; no schema/migration change; no MILESTONE-049 work.

## 11. Status

**CANDIDATE_FOR_COMPLETE_INDEPENDENT_MACRO_REVIEW.**
