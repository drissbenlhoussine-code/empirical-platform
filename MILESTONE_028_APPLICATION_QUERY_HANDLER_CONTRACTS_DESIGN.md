# MILESTONE-028 - Application Query/QueryHandler Contracts Design

## 1. Document Control

| Field | Value |
| --- | --- |
| Document ID | MILESTONE-028-DESIGN |
| Title | Application Query/QueryHandler Contracts Design |
| Version | 1.0 |
| Status | DESIGN READY FOR INDEPENDENT REVIEW / NOT APPROVED / NOT FROZEN |
| Repository baseline | `64abc16156b949491ded4ff239d2c249aac569a8` |
| Authoritative scope input | `MILESTONE_028_APPLICATION_QUERY_HANDLER_CONTRACTS_SCOPE_SELECTION.md` |
| Mission type | Design only |

**Do not implement source code. Do not start M029.**

## 2. Purpose

Freeze the read-side counterpart to M027's `CommandHandler` — a single
generic, variance-correct `QueryHandler` Protocol — completing the
application-layer command/query vocabulary, with zero implementation of any
concrete query, handler, or orchestration logic.

## 3. Design Inputs

- `MILESTONE_028_APPLICATION_QUERY_HANDLER_CONTRACTS_SCOPE_SELECTION.md`
  (frozen scope: contracts only; no orchestration, no repository wiring, no
  relationship to `CommandHandler`).
- `MILESTONE_027_APPLICATION_COMMAND_HANDLER_CONTRACTS_DESIGN.md` (Version
  1.1, frozen) — this design deliberately reuses its exact, independently
  verified pattern (contravariant/covariant generics; an
  `if TYPE_CHECKING:` positive conformance proof inside the module; an
  isolated, `mypy`-verified negative type-check fixture mechanism) rather
  than re-deriving it, since `QueryHandler`'s structural shape (one method,
  one contravariant input, one covariant output) is identical in kind to
  `CommandHandler`'s. Where M027's own correction round already
  empirically verified a claim against live `mypy --strict` behavior for
  this exact shape of Protocol, this design cites that verification rather
  than repeating the experiment, since the shape being verified is
  structurally the same.
- Live `grep` evidence: no `Query`/`QueryHandler` type exists anywhere in
  the repository today.

## 4. Exact Responsibility

This milestone freezes exactly one Protocol:

```python
class QueryHandler(Protocol[_QueryT_contra, _QueryResultT_co]):
    def handle(self, query: _QueryT_contra) -> _QueryResultT_co: ...
```

It does not freeze a separate `Query` marker type, for the identical reason
M027 rejected a `Command` marker: an empty `Protocol` is structurally
satisfied by every object, providing no compile-time or runtime guarantee.

## 5. Package Placement

New file: `src/empirical_platform/shared/contracts/query.py`, alongside the
existing `repository.py`, `mapping.py`, and (design-frozen, not yet
implemented) `command.py`. Exported from
`src/empirical_platform/shared/contracts/__init__.py`.

No new top-level package. `tools/check_architecture.py`'s `ALLOWED` table
requires no change.

`query.py` does not import from, or otherwise reference, `command.py` or
`CommandHandler` in any way (Section 9).

## 6. Contracts and Types — Variance-Correct Generics

Exact frozen contract, applying M027's corrected variance pattern from the
start:

```python
"""Application-layer query handler contract."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, TypeVar

_QueryT_contra = TypeVar("_QueryT_contra", contravariant=True)
_QueryResultT_co = TypeVar("_QueryResultT_co", covariant=True)


class QueryHandler(Protocol[_QueryT_contra, _QueryResultT_co]):
    """Structural contract for a single application-layer query handler.

    A handler receives exactly one query instance and returns exactly one
    result. This Protocol makes no assumption about what a query or result
    type is, how a handler is constructed, how it is registered or
    dispatched, or what it does internally -- all of that is explicitly out
    of scope for this milestone. It shares no base type, import, or
    conversion relationship with CommandHandler.
    """

    def handle(self, query: _QueryT_contra) -> _QueryResultT_co:
        """Handle one query instance and return its result."""
        ...


if TYPE_CHECKING:

    class _ExampleQuery:
        ...

    class _ExampleQueryResult:
        ...

    class _ExampleQueryHandler:
        def handle(self, query: _ExampleQuery) -> _ExampleQueryResult: ...

    _typed_conformance_check: QueryHandler[_ExampleQuery, _ExampleQueryResult] = (
        _ExampleQueryHandler()
    )
```

Frozen, non-negotiable properties of this one method, identical in kind to
`CommandHandler`'s frozen properties:

- synchronous (`def`, not `async def`);
- exactly one method, named `handle`;
- exactly one positional parameter beyond `self`, named `query`, of type
  `_QueryT_contra`;
- no keyword-only parameter is required;
- returns `_QueryResultT_co`.

**Why the variance is type-correct:** identical reasoning to M027 Design
Section 6 — `_QueryT_contra` appears only in input position (safe to mark
contravariant: a handler accepting a *wider* query type than declared may
safely fill a narrower slot), and `_QueryResultT_co` appears only in output
position (safe to mark covariant: a handler returning a *narrower* result
type than declared may safely fill a wider slot). This is the exact same
structural pattern M027's correction round verified directly against the
project's live `mypy --strict` configuration: an invariant `TypeVar` used in
a Protocol whose sole method consumes it as a parameter and produces it as a
return is itself rejected by `mypy` (`error: Invariant type variable ...
used in protocol where contravariant/covariant one is expected [misc]`).
Since `QueryHandler`'s method shape is structurally identical to
`CommandHandler`'s (one parameter position, one return position, no other
use of either `TypeVar`), that verified result applies without needing to
re-run the experiment for a structurally-identical Protocol.

No `@runtime_checkable` decorator, for the identical reason M027 froze none:
no code path in this milestone needs runtime `isinstance` checking, and
`mypy`'s static check is the actual, sufficient enforcement mechanism.

The `if TYPE_CHECKING:` conformance check is placed inside
`shared/contracts/query.py` itself (under `src/`), not in a test file, for
the identical reason M027 froze this placement: `mypy`'s configured scope is
`packages = ["empirical_platform"]` (`src/` only) — `tests/` is not
type-checked under the current project configuration.

No new error type, no new result-wrapper type, no registry, no dispatcher,
no base class requiring inheritance, and no relationship of any kind to
`CommandHandler`.

## 7. Ownership

Nothing owns a `QueryHandler` instance as part of this milestone — identical
to M027 Design Section 7. No instance, factory, or registry is created; no
lifecycle to manage, no resource to close, no state to track.

## 8. Call Direction

None. `shared/contracts/query.py` imports nothing beyond the standard
library `typing` module. No domain package, no `bootstrap.py`, no
`FoundationRuntime`, no repository or persistence type, and no
`shared/contracts/command.py` is referenced by it, and nothing references
it back. This is a leaf addition with zero edges into the existing
dependency graph, verified by the fact that the frozen contract (Section 6)
contains no import beyond `typing`.

## 9. Relationship to `CommandHandler`

None, by explicit design decision. `QueryHandler` and `CommandHandler` share
no base Protocol, no common `TypeVar`, no conversion function, and no
import relationship in either direction. Both are independently frozen,
independently evolvable Protocols. A future milestone may reveal a genuine
need to unify them (e.g. under a common `Handler[InputT, OutputT]` base) —
this design deliberately does not anticipate that need, since doing so now
would be speculative; the Scope Selection's own Stop Conditions (Section 16)
require returning to scope selection, not silently deciding this here, if
such a need becomes concrete.

## 10. Transaction Semantics

None. `QueryHandler.handle` is not required or assumed to open, join, or
manage any transaction, unit of work, or `run_composed` scope — identical to
M027 Design Section 9. A future handler implementation may choose to read
through `PostgresRepositoryRuntime` directly (queries typically do not need
`run_composed`'s cross-aggregate atomicity, since they do not write), or may
not need to touch persistence at all — this Protocol expresses no opinion
either way.

## 11. Repository/Runtime Interaction

None. `_QueryT_contra` and `_QueryResultT_co` are unbound `TypeVar`s; neither
is constrained to, or aware of, `PostgresRepositoryRuntime`,
`FoundationRuntime`, or any M020 repository Protocol.

## 12. Concurrency Semantics

None introduced. No `ContextVar`, no lock, no thread-safety claim.

## 13. Error Taxonomy

No new error type is frozen, for the identical reason M027 froze none: no
concrete handler yet exists to reveal what failure modes it needs to
express. The existing M020 `RepositoryContractError` hierarchy remains
available, unmodified, for any future query handler that chooses to let
repository errors (e.g. `AggregateNotFound`) propagate through `handle`.

## 14. Negative Type-Check Strategy

Reuses M027's exact, empirically verified mechanism (Design Section 13),
applied to the structurally identical `QueryHandler` shape:

Exact fixture directory (future implementation):

```text
tests/typing_fixtures/query_handler/
    ok_handler.py
    wrong_method.py
    wrong_query_type.py
    wrong_result_type.py
    missing_handle.py
```

Exact frozen pytest test file: `tests/unit/test_query_handler_typing.py`,
structured identically to `tests/unit/test_command_handler_typing.py`
(Section 15 below covers both as parallel obligations).

Exact frozen algorithm — identical to M027 Design Section 13, Items 1-6,
substituting `QueryHandler`/`query` for `CommandHandler`/`command`
throughout: resolve the repository root and `pyproject.toml`; for
`ok_handler.py`, assert exit code `0` and `"Success: no issues found"` in
stdout; for each of the four negative fixtures, invoke
`[sys.executable, "-m", "mypy", "--config-file", str(pyproject_path),
str(fixture_path)]`, assert non-zero exit code, and assert stdout contains
both `"error: Incompatible types in assignment"` and `"[assignment]"` — the
identical stable diagnostic fragment M027's correction round verified for
this exact class of Protocol-assignment mismatch (missing method, wrong
method name, wrong parameter type, wrong return type all produce this same
top-level diagnostic category). No `Any`/`cast` used to force a failure. No
mutation of `pyproject.toml`'s canonical `[tool.mypy]` section.
`tests/typing_fixtures/query_handler/` is never added to `[tool.mypy]
packages`, exactly as `tests/typing_fixtures/command_handler/` is not.

**On `--explicit-package-bases`:** not frozen, for the identical, already-
verified reason M027 Design Section 13 gives — unnecessary for this fixture
shape, and freezing an unverified flag would violate that section's own
standard, which this design inherits by citing rather than re-deriving.

**On accidental pytest collection:** identical to M027 Design Section 13 —
none of the five frozen fixture filenames match pytest's default
`test_*.py`/`*_test.py` collection glob (already verified directly against
`pyproject.toml`'s `[tool.pytest.ini_options]` during M027's own correction
round), so pytest never imports or executes them as test modules.

## 15. Failure Behavior

Not applicable — a pure structural type introduces no runtime behavior and
therefore no failure path, identical to M027 Design Section 14.

## 16. Architecture Rules

- `shared/contracts/query.py` imports only the standard library `typing`
  module.
- No domain package is required to import this new contract as part of
  this milestone.
- No import of `shared.persistence`, `sqlalchemy`, `psycopg`, `boto3`, or
  `shared.contracts.command`.
- No change to `tools/check_architecture.py`'s `ALLOWED` or
  `FORBIDDEN_IMPORT_PREFIXES` tables.
- No change to `[tool.mypy] packages` in `pyproject.toml`.
- No change to any M020-M027 frozen source or design file.

## 17. Export Surface

Exact frozen export surface:

- module: `empirical_platform.shared.contracts.query`;
- canonical, public export: `QueryHandler` only;
- `shared/contracts/__init__.py` exports `QueryHandler`, alongside
  `CommandHandler` (once M027 is implemented), matching the existing
  `__all__` pattern.

`_QueryT_contra` and `_QueryResultT_co` are module-private implementation
details, named with a leading underscore, never added to `__all__`, for the
identical reason M027 froze `_CommandT_contra`/`_ResultT_co` as private.

Not exported, by explicit design decision: a `Query` marker type; a
query-level error/result-wrapper type; a dispatcher or runtime registry; any
shared base with `CommandHandler`.

## 18. Test Strategy for Future Implementation

A future implementation must add tests proving:

1. `mypy` accepts the `if TYPE_CHECKING:` structural-conformance check
   frozen in Section 6, inside `shared/contracts/query.py` itself.
2. `tests/unit/test_query_handler_typing.py` invokes the exact subprocess
   algorithm frozen in Section 14 against all five fixtures under
   `tests/typing_fixtures/query_handler/`, proving: the positive fixture
   passes cleanly; each of the four negative fixtures fails with the frozen
   `[assignment]` diagnostic fragment; and the canonical `mypy` gate is
   unaffected by the fixtures' existence.
3. A contravariant-input assignment (a handler accepting a wider query
   type) and a covariant-output assignment (a handler returning a narrower
   result type) both type-check cleanly.
4. A separate module-level import test proves `shared/contracts/query.py`
   imports cleanly with zero dependency beyond `typing`, and that only
   `QueryHandler` — not `_QueryT_contra`/`_QueryResultT_co` — is present in
   `shared/contracts/__init__.py`'s public export surface.
5. `QueryHandler` and `CommandHandler` (once M027 is implemented) share no
   base type, import relationship, or conversion function — an explicit
   negative-relationship test, not merely an absence of code.
6. `tools/check_architecture.py .` reports zero violations with the new
   file present.
7. No existing M020-M027 test is affected.
8. `build` and package-metadata gates are unaffected.

## 19. Compatibility With M020 Through M027

No source file governed by M020 through M026 is modified by this design.
M027's frozen design (`CommandHandler`) is referenced only as a naming and
pattern precedent (Section 3) — no M027 source file (none exists yet) or
design document is modified, and `QueryHandler` shares no code, import, or
type relationship with `CommandHandler` (Section 9).

## 20. Deferred Work

Explicitly out of scope for M028:

- any concrete `Query` or `QueryHandler` implementation for any aggregate;
- any relationship, shared base, or unification with `CommandHandler`;
- application service orchestration, transaction ownership decisions, or
  any wiring to `PostgresRepositoryRuntime`/`run_composed`;
- a query-level error hierarchy;
- retry semantics of any kind, including any command-vs-query distinction
  in retry behavior;
- APIs, workers, CLI entrypoints, or any change to `entrypoints/`;
- Audit runtime, Decision Candidate, Decision Freeze;
- market-data, vendor, trading, or campaign execution behavior;
- any named MILESTONE-029 work.

## 21. Acceptance Gate

The design is acceptance-ready only if it freezes, with no remaining
ambiguity:

1. the exact `QueryHandler[_QueryT_contra, _QueryResultT_co]` Protocol
   shape, with correct, verified variance — frozen, Section 6;
2. the exact package/file placement — frozen, Section 5;
3. the exact, justified decision not to freeze a `Query` marker, a
   query-level error type, or any relationship to `CommandHandler` —
   frozen, Sections 4, 9, 13;
4. the exact negative type-check strategy — frozen, Section 14;
5. the exact export surface — frozen, Section 17;
6. exact test obligations — frozen, Section 18.

## 22. Rejected Alternatives

1. **Freeze a separate, empty `Query` Protocol as a marker type.** Rejected
   for the identical reason M027 rejected a `Command` marker (Section 4).
2. **Freeze a query-level error hierarchy now.** Rejected for the identical
   reason M027 rejected a handler-level error hierarchy (Section 13).
3. **Unify `QueryHandler` and `CommandHandler` under a shared
   `Handler[InputT, OutputT]` base now.** Rejected: no concrete
   implementation of either yet exists to reveal whether unification has
   real value; premature unification risks freezing the wrong abstraction,
   exactly the class of mistake M027's own variance defect demonstrated.
   Deferred explicitly (Section 20) rather than decided either way.
4. **Add a `@runtime_checkable` decorator.** Rejected for the identical
   reason M027 rejected one (Section 6).
5. **Place the new contract in a new top-level `application` package.**
   Rejected for the identical reason M027 rejected this (placement
   precedent already established by M020 and M027 in `shared/contracts/`).
6. **Re-run the full `mypy` variance experiment from scratch for
   `QueryHandler`.** Rejected as unnecessary: `QueryHandler`'s method shape
   is structurally identical to `CommandHandler`'s (one contravariant
   parameter position, one covariant return position, no other use of
   either `TypeVar`), so the verified result from M027's correction round
   applies directly; re-running an identical experiment would not produce
   new information.

## 23. Risk Register

| Risk | Mitigation |
| --- | --- |
| A future implementer conflates this Protocol with "application services already exist" | Sections 7/8/10/11 each explicitly state no ownership, call direction, transaction, or repository interaction is introduced |
| A future implementer couples `QueryHandler` to `CommandHandler` out of convenience | Section 9 and Section 22 Item 3 explicitly document the no-relationship decision and its reasoning |
| A future implementer re-introduces invariant `TypeVar`s | Section 6 cites the exact, already-verified `mypy` error text for the structurally identical `CommandHandler` case |
| Negative fixtures accidentally pollute the canonical `mypy` gate or get collected by pytest | Section 14 freezes the identical, already-verified safeguards M027 established |
| The two Protocols silently diverge in ways that make a future unification harder than necessary | Section 9 explicitly names this as a live possibility and defers the decision rather than pretending it will never arise |

## 24. Hostile Self-Review

1. **Does this quietly become "application services"?** No — identical
   reasoning to M027 Design Section 23 Item 1.
2. **Does this presume a specific dispatch or bus mechanism?** No.
3. **Does this leak into transaction ownership?** No — Section 10.
4. **Does this leak into repository/runtime access?** No — Section 11.
5. **Does this leak into APIs/workers?** No — Section 8.
6. **Does this leak into retry policy?** No — Section 20 explicitly defers
   it, including the command-vs-query distinction that would legitimately
   apply to retry semantics.
7. **Is the "no error taxonomy" decision actually justified, or just
   avoidance?** Justified — identical reasoning to M027 (Section 13).
8. **Does this leak into M029?** No — Section 20's deferred list presumes
   no named future milestone.
9. **Is the variance direction actually correct, or just copy-pasted
   without verification?** Verified by structural equivalence, not blind
   copy-paste: Section 6 explicitly states *why* the identical shape means
   the identical verified result applies (one contravariant parameter
   position, one covariant return position, no other TypeVar use) rather
   than merely asserting "M027 did this, so we will too."
10. **Do the negative fixtures actually fail for the intended reason?**
    Guarded identically to M027 — a positive `ok_handler.py` fixture proves
    the invocation mechanism itself works.
11. **Could the negative fixtures pollute the canonical `mypy` gate or leak
    into pytest collection?** No — identical, already-verified safeguards
    (Section 14).
12. **Are the `TypeVar`s at risk of accidental public exposure?** No —
    Section 17 freezes leading-underscore naming and an explicit test
    obligation (Section 18 Item 4).
13. **Does async behavior get overclaimed anywhere?** No — Section 6
    explicitly freezes `handle` as synchronous.
14. **Does this silently decide that `QueryHandler` and `CommandHandler`
    should eventually be unified, without saying so plainly?** No — Section
    9 states this explicitly as an open, deferred question, not a silent
    assumption in either direction.

## 25. Final Status

```text
M028 DESIGN READY FOR INDEPENDENT REVIEW
M028 NOT APPROVED
M028 NOT FROZEN
M028 IMPLEMENTATION NOT STARTED
```

Do not implement source code. Do not start M029.
