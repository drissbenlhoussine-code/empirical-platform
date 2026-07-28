# MILESTONE-027 - Application Command/Handler Contracts Implementation

## 1. Document Control

| Field | Value |
| --- | --- |
| Document ID | MILESTONE-027-IMPLEMENTATION |
| Title | Application Command/Handler Contracts Implementation |
| Status | IMPLEMENTATION COMPLETE - READY FOR INDEPENDENT REVIEW |
| Frozen design | `MILESTONE_027_APPLICATION_COMMAND_HANDLER_CONTRACTS_DESIGN.md` (Version 1.1) |
| Design freeze | `MILESTONE_027_APPLICATION_COMMAND_HANDLER_CONTRACTS_DESIGN_FREEZE.md` |

## 2. Scope

Implements exactly the frozen `CommandHandler[_CommandT_contra, _ResultT_co]`
Protocol: correct module placement, correct variance, correct exports, the
frozen `TYPE_CHECKING` conformance proof, the frozen negative-typing-fixture
mechanism, and unit tests. No concrete command, handler, orchestration,
dispatcher, registry, dependency injection, retry logic, runtime behavior,
API, worker, `Command` marker, or error hierarchy is introduced. No M020-M026
source file changed.

## 3. Files Changed

| File | Change |
| --- | --- |
| `src/empirical_platform/shared/contracts/command.py` | New — frozen `CommandHandler` Protocol, contravariant/covariant generics, `TYPE_CHECKING` conformance and variance proofs |
| `src/empirical_platform/shared/contracts/__init__.py` | Modified — exports `CommandHandler`, alphabetically placed in the existing `__all__` pattern |
| `tests/typing_fixtures/command_handler/ok_handler.py` | New — positive fixture |
| `tests/typing_fixtures/command_handler/wrong_method.py` | New — negative fixture (wrong method name) |
| `tests/typing_fixtures/command_handler/wrong_command_type.py` | New — negative fixture (wrong command type) |
| `tests/typing_fixtures/command_handler/wrong_result_type.py` | New — negative fixture (wrong result type) |
| `tests/typing_fixtures/command_handler/missing_handle.py` | New — negative fixture (missing `handle`) |
| `tests/unit/test_command_handler_typing.py` | New — 6 tests, subprocess-invoked `mypy` against the five fixtures |
| `tests/unit/test_command_handler_contract.py` | New — 4 tests, import-graph/export-surface/variance-proof-presence tests |
| `MILESTONE_027_APPLICATION_COMMAND_HANDLER_CONTRACTS_IMPLEMENTATION_SCOPE.md` | New |
| `MILESTONE_027_APPLICATION_COMMAND_HANDLER_CONTRACTS_IMPLEMENTATION.md` | New (this document) |
| `PROJECT_CHECKPOINT.md` | Updated (checkpoint-content-baseline semantics) |

No M020 Repository Protocol, M021 mapper contract, M022 schema/migration,
M023 concrete adapter, M024 `run_composed`, M025 `PostgresRepositoryRuntime`,
or M026 `FoundationRuntime` source file is touched.

## 4. Exact Frozen Contract

```python
"""Application-layer command handler contract."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, TypeVar

_CommandT_contra = TypeVar("_CommandT_contra", contravariant=True)
_ResultT_co = TypeVar("_ResultT_co", covariant=True)


class CommandHandler(Protocol[_CommandT_contra, _ResultT_co]):
    def handle(self, command: _CommandT_contra) -> _ResultT_co: ...
```

Implemented verbatim against the frozen Design Section 6/4 code block, with
the module's `if TYPE_CHECKING:` block extended (beyond the frozen minimum
conformance proof) with two additional, mypy-verified variance proofs — see
Section 6 below.

## 5. Package Placement and Exports

`src/empirical_platform/shared/contracts/command.py`, alongside the existing
`repository.py`/`mapping.py`, exactly as frozen. `shared/contracts/__init__.py`
exports `CommandHandler` only — `_CommandT_contra`/`_ResultT_co` remain
module-private, never added to `__all__`, proven by
`test_only_command_handler_is_exported`.

## 6. Variance Proof

The frozen design's Test Strategy Section 17 Item 3 required a
contravariant-input and covariant-output type-check proof, either as
additional `if TYPE_CHECKING:` proofs in the module or as additional
fixtures. Implemented as two additional `if TYPE_CHECKING:` blocks inside
`command.py` itself (not in `tests/`, for the identical reason the frozen
design placed the base conformance proof there — `mypy`'s configured scope
is `src/` only):

- `_contravariant_input_check`: a handler accepting the wider
  `_ExampleCommand` is assigned to a `CommandHandler[_NarrowExampleCommand,
  _ExampleResult]`-typed slot — type-checks cleanly, proving
  `_CommandT_contra`'s contravariance is real.
- `_covariant_output_check`: a handler returning the narrower
  `_NarrowExampleResult` is assigned to a `CommandHandler[_ExampleCommand,
  _ExampleResult]`-typed slot — type-checks cleanly, proving
  `_ResultT_co`'s covariance is real.

Both are verified by the canonical `mypy` gate (they live in `src/`, inside
`packages = ["empirical_platform"]`'s scope) on every `verify.ps1`/`mypy`
run — not by a runtime pytest assertion, since Python does not enforce type
annotations at runtime and a pytest-level `isinstance` check would prove
nothing about static variance correctness. `test_command_handler_contract.py`'s
`test_variance_proofs_are_present_in_the_type_checked_module` only confirms
this mypy-checked code has not been silently deleted from the module; the
actual type-safety proof is `mypy`'s job, already passing.

## 7. Negative Type-Check Strategy

Implemented exactly as frozen (Design Section 13):
`tests/typing_fixtures/command_handler/` contains the five frozen files.
`tests/unit/test_command_handler_typing.py` invokes
`[sys.executable, "-m", "mypy", "--config-file", <pyproject.toml>, <fixture>]`
as a subprocess for each, asserting:

- `ok_handler.py` exits `0` with `"Success: no issues found"` in stdout;
- each of the four negative fixtures exits non-zero with
  `"error: Incompatible types in assignment"` and `"[assignment]"` in
  stdout — verified directly against the real implementation (not a stub)
  during this implementation, producing the identical diagnostics the
  frozen design predicted;
- `tests/typing_fixtures/command_handler/` is confirmed, by reading
  `pyproject.toml` directly at test time, to never appear in
  `[tool.mypy] packages` (which stays exactly `["empirical_platform"]`).

None of the five fixture filenames match pytest's default `test_*.py`/
`*_test.py` collection glob, confirmed directly — pytest never imports or
executes them; only `test_command_handler_typing.py`'s subprocess calls
read their source text.

## 8. Ownership, Call Direction, Transaction/Repository/Concurrency

Unchanged from the frozen design (Sections 7-11): no instance, factory, or
registry created; `command.py` imports only `typing`; no transaction, no
repository/runtime reference, no concurrency primitive. Verified directly by
`test_module_has_zero_dependency_beyond_typing` (AST-based import-graph
check).

## 9. Error Taxonomy

No new error type introduced, exactly as frozen (Design Section 12). The
existing M020 `RepositoryContractError` hierarchy is untouched.

## 10. Tests Added

**`tests/unit/test_command_handler_typing.py`** (6 tests):

- 1 positive-fixture test (`ok_handler.py` type-checks cleanly);
- 4 parametrized negative-fixture tests (one per malformed shape);
- 1 test confirming `[tool.mypy] packages` still reads exactly
  `["empirical_platform"]`, proving the fixtures cannot have polluted the
  canonical gate's scope.

**`tests/unit/test_command_handler_contract.py`** (4 tests):

- module import test;
- AST-based zero-dependency-beyond-`typing` test;
- export-surface test (`CommandHandler` in `__all__`; `_CommandT_contra`/
  `_ResultT_co` absent from both `__all__` and the module namespace);
- variance-proof-presence test (Section 6).

All 10 pass; combined with the 406 pre-existing tests, `verify.ps1` reports
**416 passed, 110 skipped**, coverage **82.73%**, with zero modification to
any pre-existing test file.

## 11. Architecture and Security

- `tools/check_architecture.py .` — 0 violations. `command.py` imports only
  the standard library `typing` module; no `ALLOWED`/`FORBIDDEN` table
  change required.
- No domain package imports the new contract.
- Secret scan (`scripts/security.ps1`): clean, 285 targets.
- No credential, connection, or persistence-adjacent concern anywhere in the
  new files.

## 12. Full Validation Loop

| Gate | Result |
| --- | --- |
| Python | 3.13.14 |
| `python -m compileall -q src tests tools migrations` | PASS |
| `ruff format --check .` / `ruff check .` | PASS |
| `mypy` | PASS, 0 issues, 81 source files |
| `scripts/security.ps1` | PASS — pip-audit clean, secret scan 285 targets |
| `scripts/verify.ps1` | PASS — 416 passed, 110 skipped, coverage 82.73% |
| `tools/check_architecture.py .` | PASS, 0 violations |
| `python -m build` | PASS (sdist + wheel) |
| `git diff --check` | PASS |

## 13. Hostile Self-Review

1. **Was orchestration, an application service, a dispatcher, a registry,
   dependency injection, retry logic, or runtime behavior introduced?** No —
   `command.py` contains exactly one Protocol, two `TypeVar`s, and
   `TYPE_CHECKING`-only proof code with zero runtime effect. No instance is
   ever constructed at runtime by this milestone.
2. **Was an API or worker touched?** No — `entrypoints/` is untouched;
   `check_architecture.py` confirms no new import edge exists anywhere.
3. **Was a `Command` marker invented?** No — exactly as frozen (Design
   Section 4), no marker type exists in `command.py` or anywhere else.
4. **Was an error hierarchy invented?** No — exactly as frozen (Design
   Section 12), no new error type exists.
5. **Does the implementation deviate from the frozen variance?** No — the
   `TypeVar` declarations, `contravariant=True`/`covariant=True` flags, and
   the single `handle` method signature are byte-for-byte the frozen code
   block (Design Section 6), verified by direct comparison during
   implementation.
6. **Do the fixtures actually fail for the intended reason against the real
   (not stubbed) implementation?** Yes — verified directly (Section 7); the
   real `CommandHandler` produces the identical diagnostics the design's
   stub-based experimentation predicted.
7. **Were the `TypeVar`s accidentally exported?** No —
   `test_only_command_handler_is_exported` proves both their absence from
   `__all__` and from the module namespace itself.
8. **Did any M020-M026 file change?** No — `git diff --name-status`
   confirms the only modified existing file is
   `shared/contracts/__init__.py`.
9. **Does this leak into M028?** No — nothing here presumes or requires any
   named future milestone; `QueryHandler` (M028, design-only) is not
   referenced anywhere in this implementation.

No genuine finding required a correction; no source, test, or documentation
change resulted from this pass beyond what Sections 4-12 already describe.

## 14. Deferred Work

Any concrete `Command`/`CommandHandler` implementation, application service
orchestration, a handler-level error hierarchy, a `Command` marker,
dispatcher/registry, retry policy, APIs, workers, Audit runtime, Decision
Candidate, Decision Freeze, market-data/vendor/trading/campaign execution
behavior, and MILESTONE-028 implementation — all unchanged from the frozen
Design's Section 19 deferred list.

## 15. Final Status

```text
M027 IMPLEMENTATION COMPLETE
READY FOR INDEPENDENT REVIEW
NOT APPROVED
NOT FROZEN
M028 IMPLEMENTATION NOT STARTED
```
