# MILESTONE-028 - Application Query/QueryHandler Contracts Implementation

## 1. Document Control

| Field | Value |
| --- | --- |
| Document ID | MILESTONE-028-IMPLEMENTATION |
| Title | Application Query/QueryHandler Contracts Implementation |
| Status | IMPLEMENTATION COMPLETE - READY FOR INDEPENDENT REVIEW |
| Frozen design | `MILESTONE_028_APPLICATION_QUERY_HANDLER_CONTRACTS_DESIGN.md` (Version 1.1) |
| Design freeze | `MILESTONE_028_APPLICATION_QUERY_HANDLER_CONTRACTS_DESIGN_FREEZE.md` |

## 2. Scope

Implements exactly the frozen `QueryHandler[_QueryT_contra, _QueryResultT_co]`
Protocol: correct module placement, correct variance, correct exports, the
frozen `TYPE_CHECKING` conformance proof, the frozen negative-typing-fixture
mechanism, the frozen declared-relationship/structural-compatibility
obligations with `CommandHandler`, and unit tests. No concrete query,
handler, orchestration, dispatcher, registry, dependency injection, retry
logic, runtime behavior, API, worker, `Query` marker, error hierarchy,
result/pagination wrapper, or read-only enforcement mechanism is introduced.
No M020-M027 source file changed.

## 3. Files Changed

| File | Change |
| --- | --- |
| `src/empirical_platform/shared/contracts/query.py` | New — frozen `QueryHandler` Protocol, contravariant/covariant generics, `TYPE_CHECKING` conformance and variance proofs |
| `src/empirical_platform/shared/contracts/__init__.py` | Modified — exports `QueryHandler` alongside the existing, unchanged `CommandHandler` export |
| `tests/typing_fixtures/query_handler/ok_handler.py` | New — positive fixture |
| `tests/typing_fixtures/query_handler/wrong_method.py` | New — negative fixture (wrong method name) |
| `tests/typing_fixtures/query_handler/wrong_query_type.py` | New — negative fixture (wrong query type) |
| `tests/typing_fixtures/query_handler/wrong_result_type.py` | New — negative fixture (wrong result type) |
| `tests/typing_fixtures/query_handler/missing_handle.py` | New — negative fixture (missing `handle`) |
| `tests/typing_fixtures/command_query_relationship/dual_satisfaction.py` | New — positive fixture proving expected structural dual-satisfaction |
| `tests/typing_fixtures/command_query_relationship/mismatched_dual_satisfaction.py` | New — negative fixture proving mismatched type arguments are still rejected |
| `tests/unit/test_query_handler_typing.py` | New — 6 tests, subprocess-invoked `mypy` against the five `query_handler` fixtures |
| `tests/unit/test_query_handler_contract.py` | New — 4 tests, import-graph/export-surface/variance-proof-presence tests |
| `tests/unit/test_command_query_relationship.py` | New — 12 tests, declared-relationship, structural-compatibility, and read-only-limitation tests |
| `MILESTONE_028_APPLICATION_QUERY_HANDLER_CONTRACTS_IMPLEMENTATION_SCOPE.md` | New |
| `MILESTONE_028_APPLICATION_QUERY_HANDLER_CONTRACTS_IMPLEMENTATION.md` | New (this document) |
| `PROJECT_CHECKPOINT.md` | Updated (checkpoint-content-baseline semantics) |

No M020 Repository Protocol, M021 mapper contract, M022 schema/migration,
M023 concrete adapter, M024 `run_composed`, M025 `PostgresRepositoryRuntime`,
M026 `FoundationRuntime`, or M027 `CommandHandler` source file is touched.

## 4. Exact Frozen Contract

```python
"""Application-layer query handler contract."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, TypeVar

_QueryT_contra = TypeVar("_QueryT_contra", contravariant=True)
_QueryResultT_co = TypeVar("_QueryResultT_co", covariant=True)


class QueryHandler(Protocol[_QueryT_contra, _QueryResultT_co]):
    def handle(self, query: _QueryT_contra) -> _QueryResultT_co: ...
```

Implemented verbatim against the frozen Design Section 6/4 code block, with
the module's `if TYPE_CHECKING:` block extended (beyond the frozen minimum
conformance proof) with two additional, mypy-verified variance proofs — see
Section 6 below, mirroring exactly the same pattern M027's implementation
used for `CommandHandler`.

## 5. Package Placement and Exports

`src/empirical_platform/shared/contracts/query.py`, alongside the existing
`repository.py`/`mapping.py`/`command.py`, exactly as frozen.
`shared/contracts/__init__.py` exports `QueryHandler` alongside the
existing, unmodified `CommandHandler` export — `_QueryT_contra`/
`_QueryResultT_co` remain module-private, never added to `__all__`, proven
by `test_query_handler_and_command_handler_are_both_exported`.

## 6. Variance Proof

Identical pattern to M027's `CommandHandler` implementation: two additional
`if TYPE_CHECKING:` blocks inside `query.py` itself (not in `tests/`, for
the identical reason the base conformance proof lives there):

- `_contravariant_input_check`: a handler accepting the wider
  `_ExampleQuery` is assigned to a `QueryHandler[_NarrowExampleQuery,
  _ExampleQueryResult]`-typed slot — type-checks cleanly.
- `_covariant_output_check`: a handler returning the narrower
  `_NarrowExampleQueryResult` is assigned to a `QueryHandler[_ExampleQuery,
  _ExampleQueryResult]`-typed slot — type-checks cleanly.

Both are verified by the canonical `mypy` gate on every `verify.ps1`/`mypy`
run. `test_variance_proofs_are_present_in_the_type_checked_module` only
confirms this mypy-checked code has not been silently deleted; the actual
type-safety proof is `mypy`'s job, already passing.

## 7. Negative Type-Check Strategy

Implemented exactly as frozen (Design Section 15):
`tests/typing_fixtures/query_handler/` contains the five frozen files.
`tests/unit/test_query_handler_typing.py` invokes the identical subprocess
algorithm M027 established, verified directly against the real
implementation to produce the identical diagnostics the frozen design
predicted. Confirmed, by reading `pyproject.toml` directly at test time,
that this fixture directory never appears in `[tool.mypy] packages`. None
of the five fixture filenames match pytest's default collection glob.

## 8. Declared Relationship and Structural-Compatibility (Design Section 9)

Implemented and tested as two distinct, non-overlapping claims, exactly as
the frozen design requires:

**Declared relationship** (`tests/unit/test_command_query_relationship.py`):
`QueryHandler` does not inherit from `CommandHandler` and vice versa
(`test_query_handler_does_not_inherit_from_command_handler`,
`test_command_handler_does_not_inherit_from_query_handler`); no custom
shared base exists beyond `typing.Protocol`/`typing.Generic`
(`test_no_shared_custom_base_beyond_protocol_and_object`); `query.py` does
not import `command.py` and vice versa
(`test_query_module_does_not_import_command_module`,
`test_command_module_does_not_import_query_module` — both AST-based,
inspecting the actual source files directly).

**Structural-compatibility reality**: `tests/typing_fixtures/command_query_relationship/dual_satisfaction.py`
proves a single concrete class with an aligned `handle` signature
type-checks cleanly as both `CommandHandler[Value, Outcome]` and
`QueryHandler[Value, Outcome]` simultaneously — verified via
`test_compatible_concrete_class_satisfies_both_protocols_simultaneously`,
which documents this in its own docstring as an *expected* property of
Python's structural typing, not a defect.
`mismatched_dual_satisfaction.py` proves this compatibility is conditional,
not universal: assigning the same handler to a `CommandHandler` slot with a
genuinely unrelated type argument is still correctly rejected by `mypy` —
verified via `test_mismatched_type_arguments_are_still_rejected`.

## 9. Read-Only Semantics (Design Section 10)

Implemented as documentation-and-test obligations only, with zero runtime
mechanism, exactly as frozen: `query.py` exports no repository, transaction,
session, or unit-of-work-related name
(`test_query_handler_module_exports_no_repository_or_transaction_api`); no
decorator or class decorator exists anywhere in the module
(`test_query_handler_module_defines_no_decorator_or_runtime_guard`);
importing the module has no side effect, proven by forcing a fresh
re-execution of its module-level code via `importlib.reload`
(`test_importing_query_module_has_no_side_effect`); and no docstring or
comment in the module claims mechanical non-mutation enforcement
(`test_no_documentation_claims_mechanical_non_mutation_guarantee`, which
sweeps for forbidden claim phrases directly in the source text).

## 10. Ownership, Call Direction, Transaction/Repository/Concurrency

Unchanged from the frozen design (Sections 7-8, 11-12): no instance,
factory, or registry created; `query.py` imports only `typing`; no
transaction, no repository/runtime reference, no concurrency primitive.
Verified directly by `test_module_has_zero_dependency_beyond_typing`
(AST-based import-graph check).

## 11. Error Taxonomy

No new error type introduced, exactly as frozen (Design Section 14). The
existing M020 `RepositoryContractError` hierarchy is untouched.

## 12. Tests Added

**`tests/unit/test_query_handler_typing.py`** (6 tests): 1 positive-fixture
test, 4 parametrized negative-fixture tests, 1 canonical-mypy-scope test —
structurally identical to M027's `test_command_handler_typing.py`.

**`tests/unit/test_query_handler_contract.py`** (4 tests): module import,
AST-based zero-dependency test, export-surface test (both `QueryHandler`
and `CommandHandler` present; both private `TypeVar` pairs absent),
variance-proof-presence test.

**`tests/unit/test_command_query_relationship.py`** (12 tests): 5
declared-relationship tests, 3 structural-compatibility tests (2 mypy
subprocess invocations plus 1 canonical-scope check), 4 read-only-limitation
tests.

All 22 new tests pass; combined with the 416 pre-existing tests (which
already include M027's own 10), `verify.ps1` reports the totals in Section
14, with zero modification to any pre-existing test file.

## 13. Architecture and Security

- `tools/check_architecture.py .` — 0 violations. `query.py` imports only
  the standard library `typing` module; no `ALLOWED`/`FORBIDDEN` table
  change required.
- No domain package imports the new contract.
- No import cycle between `command.py` and `query.py` in either direction
  (Section 8).
- Secret scan (`scripts/security.ps1`): clean.
- No credential, connection, or persistence-adjacent concern anywhere in
  the new files. No network, filesystem, process, or database interaction
  of any kind.

## 14. Full Validation Loop

| Gate | Result |
| --- | --- |
| Python | 3.13.14 |
| `python -m compileall -q src tests tools migrations` | PASS |
| `ruff format --check .` / `ruff check .` | PASS — 176 files formatted |
| `mypy` | PASS, 0 issues, 82 source files |
| Focused M028 tests | PASS — 22/22 |
| `scripts/security.ps1` | PASS — pip-audit clean, secret scan 302 targets |
| `scripts/verify.ps1` | PASS — 438 passed, 110 skipped, coverage 82.77% |
| `tools/check_architecture.py .` | PASS, 0 violations |
| `python -m build` | PASS (sdist + wheel) |
| `git diff --check` | PASS |

## 15. Hostile Self-Review

1. **Invariant or reversed `TypeVar`s?** No — `_QueryT_contra` is
   `contravariant=True` (input position only), `_QueryResultT_co` is
   `covariant=True` (output position only), byte-for-byte matching the
   frozen Design Section 6 code block.
2. **Incorrect query-result variance?** No — verified via the two
   `TYPE_CHECKING` proofs, mypy-checked on every run.
3. **Private `TypeVar` leakage?** No —
   `test_query_handler_and_command_handler_are_both_exported` proves
   `_QueryT_contra`/`_QueryResultT_co` absent from both `__all__` and the
   module namespace.
4. **`Query` marker introduction?** No — no marker type exists anywhere.
5. **Query error hierarchy introduction?** No — no new error type exists.
6. **Result/pagination wrapper introduction?** No — `QueryHandler` returns
   a bare `_QueryResultT_co`, nothing else.
7. **`runtime_checkable` introduction?** No — no such decorator anywhere.
8. **Async or overload introduction?** No — `handle` is `def`, not
   `async def`; exactly one signature, no `@overload`.
9. **Inheritance/shared base/alias with `CommandHandler`?** No — proven
   directly by `test_query_handler_does_not_inherit_from_command_handler`,
   `test_command_handler_does_not_inherit_from_query_handler`, and
   `test_no_shared_custom_base_beyond_protocol_and_object`.
10. **Runtime cross-contract registration?** No — no registry, no
    dispatcher, no runtime code of any kind exists.
11. **Structural compatibility proof not actually checked?** No — both
    relationship fixtures are invoked via a genuine `mypy` subprocess
    against the real implementation, not asserted informally.
12. **Mismatched compatibility fixture failing for an arbitrary reason?**
    No — the exact diagnostic (`error: Incompatible types in assignment`,
    `[assignment]`) is asserted, and the failure's `note:` lines (verified
    manually) confirm it fails specifically because of the mismatched
    parameter type, not an unrelated syntax/import error.
13. **Positive typing fixture passing under a weakened config?** No —
    `--config-file` explicitly points at the canonical, unmodified
    `pyproject.toml`; no strictness flag was relaxed anywhere.
14. **Negative fixtures contaminating canonical mypy?** No —
    `test_fixtures_are_not_part_of_canonical_mypy_package_scope` and
    `test_relationship_fixtures_are_not_part_of_canonical_mypy_package_scope`
    both read `pyproject.toml` directly and assert `packages ==
    ["empirical_platform"]`.
15. **Pytest auto-collection of fixtures?** No — none of the seven fixture
    filenames match pytest's default `test_*.py`/`*_test.py` glob.
16. **Runtime `TYPE_CHECKING` fixture leakage?** No — all `TYPE_CHECKING`
    proof code has zero runtime effect; it is never imported or executed
    outside static analysis.
17. **Read-only enforcement overclaim?** No —
    `test_no_documentation_claims_mechanical_non_mutation_guarantee` sweeps
    the actual module source for forbidden claim phrases and finds none.
18. **Repository/transaction/decorator/guard introduction?** No — proven
    directly by `test_query_handler_module_exports_no_repository_or_transaction_api`
    and `test_query_handler_module_defines_no_decorator_or_runtime_guard`.
19. **Dispatcher/registry/query-bus/cache leakage?** No — no such code
    exists anywhere in this implementation.
20. **Architecture-rule widening?** No — `check_architecture.py` reports 0
    violations; no `ALLOWED`/`FORBIDDEN_IMPORT_PREFIXES` table touched.
21. **Packaging omission?** No — `query.py` is part of the
    `empirical_platform.shared.contracts` package already included in
    `python -m build`'s output; no new packaging configuration was needed.
22. **M027 modification?** No — `git diff --name-status` confirms
    `command.py` is untouched; only `__init__.py` gained one new,
    additive import/export line.
23. **M029 leakage?** No — nothing here presumes or requires any named
    future milestone.
24. **Documentation claims unsupported by code?** No — every claim in
    Sections 4-11 above is backed by a specific, named, passing test.

No genuine finding required a correction; no source, test, or documentation
change resulted from this pass beyond what Sections 4-13 already describe.

## 16. Deferred Work

Any concrete `Query`/`QueryHandler` implementation, any declared
relationship/shared base/unification with `CommandHandler`, application
service orchestration, a query-level error hierarchy, a `Query` marker,
dispatcher/registry, read-only transaction enforcement, caching, pagination
wrappers, result envelopes, retry policy, APIs, workers, Audit runtime,
Decision Candidate, Decision Freeze, market-data/vendor/trading/campaign
execution behavior, and MILESTONE-029 implementation — all unchanged from
the frozen Design's Section 20/21 deferred list.

## 17. Final Status

```text
M028 APPLICATION QUERY/QUERYHANDLER CONTRACTS IMPLEMENTATION COMPLETE
READY FOR INDEPENDENT REVIEW
NOT APPROVED
NOT FROZEN
M029 NOT STARTED
```
