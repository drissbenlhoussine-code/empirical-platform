# MILESTONE-027 - Application Command/Handler Contracts Design

## 1. Document Control

| Field | Value |
| --- | --- |
| Document ID | MILESTONE-027-DESIGN |
| Title | Application Command/Handler Contracts Design |
| Version | 1.0 |
| Status | DESIGN READY FOR INDEPENDENT REVIEW / NOT APPROVED / NOT FROZEN |
| Repository baseline | `45f4916d1fcdd76b28fffa81c23704f6b0355c3d` |
| Authoritative scope input | `MILESTONE_027_APPLICATION_COMMAND_HANDLER_CONTRACTS_SCOPE_SELECTION.md` |
| Mission type | Design only |

**Do not implement source code. Do not start M028.**

## 2. Purpose

Freeze the persistence-neutral, domain-agnostic vocabulary for an
application-layer command handler — a single generic `CommandHandler`
Protocol — with zero implementation of any concrete command, handler, or
orchestration logic, exactly mirroring how M020 froze repository Protocols
before M023 implemented any concrete adapter.

## 3. Design Inputs

- `MILESTONE_027_APPLICATION_COMMAND_HANDLER_CONTRACTS_SCOPE_SELECTION.md`
  (frozen scope: contracts only; no orchestration, no repository wiring, no
  APIs/workers).
- `src/empirical_platform/shared/contracts/repository.py` and
  `src/empirical_platform/shared/contracts/mapping.py` (read in full — the
  established placement and style precedent for domain-agnostic contracts
  under `shared/contracts/`).
- Live `grep` evidence: no `Command`/`Handler` type exists anywhere in the
  repository today.

## 4. Exact Responsibility

This milestone freezes exactly one Protocol:

```python
class CommandHandler(Protocol[CommandT, ResultT]):
    def handle(self, command: CommandT) -> ResultT: ...
```

It does not freeze a separate `Command` marker type. An empty Protocol with
no required members is structurally satisfied by every object in Python
(`Protocol` structural typing has nothing to check against), so it would
provide no compile-time or runtime guarantee — freezing one would be
decorative, not load-bearing. `CommandT` is a plain, unbound `TypeVar`;
"a command" is simply whatever concrete type a future handler's author binds
`CommandT` to. This is a deliberate, narrower-than-initially-scoped outcome
of this Design phase (see Section 15, Rejected Alternatives).

## 5. Package Placement

New file: `src/empirical_platform/shared/contracts/command.py`, alongside the
existing `repository.py` and `mapping.py`. Exported from
`src/empirical_platform/shared/contracts/__init__.py`, matching the existing
`__all__` pattern for `repository.py`'s exports.

No new top-level package. `tools/check_architecture.py`'s `ALLOWED` table
requires no change: `shared` is already importable by every domain package,
and this new file introduces no import of `sqlalchemy`, `psycopg`, `boto3`,
or `shared.persistence`.

## 6. Contracts and Types

Exact frozen contract:

```python
"""Application-layer command handler contract."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, TypeVar

CommandT = TypeVar("CommandT")
ResultT = TypeVar("ResultT")


class CommandHandler(Protocol[CommandT, ResultT]):
    """Structural contract for a single application-layer command handler.

    A handler receives exactly one command instance and returns exactly one
    result. This Protocol makes no assumption about what a command or result
    type is, how a handler is constructed, how it is registered or
    dispatched, or what it does internally -- all of that is explicitly out
    of scope for this milestone.
    """

    def handle(self, command: CommandT) -> ResultT:
        """Handle one command instance and return its result."""
        ...


if TYPE_CHECKING:

    class _ConformanceCheck:
        """Type-checker-only proof that a minimal class satisfies
        CommandHandler[CommandT, ResultT] structurally. Never instantiated;
        exists only so `mypy` verifies this module's own contract against a
        concrete shape on every run."""

        def handle(self, command: int) -> str: ...

    _typed_conformance_check: CommandHandler[int, str] = _ConformanceCheck()
```

No `@runtime_checkable` decorator is frozen: `runtime_checkable` only allows
`isinstance()` to check for the *presence* of the `handle` method, not its
signature, and this milestone introduces no code path that needs an
`isinstance` check against this Protocol — static `mypy` checking (already
run in `verify.ps1`) is the actual enforcement mechanism for structural
conformance, and is sufficient.

The `if TYPE_CHECKING:` conformance check is placed inside
`shared/contracts/command.py` itself (under `src/`), not in a test file,
because `mypy`'s configured scope is `packages = ["empirical_platform"]`
(`src/` only) — `tests/` is not type-checked under the current project
configuration (an already-accepted, pre-existing observation carried through
M025/M026's own accepted non-blocking observations). A structural-conformance
proof placed in `tests/` would silently never be checked by anything; placing
it in the module itself guarantees `mypy` verifies it on every single
`verify.ps1`/`mypy` invocation, with zero runtime cost (the `TYPE_CHECKING`
guard means none of this code executes or is even imported at runtime).

No new error type, no new result-wrapper type, no registry, no dispatcher,
no base class requiring inheritance.

## 7. Ownership

Nothing owns a `CommandHandler` instance as part of this milestone. The
Protocol describes a shape a future concrete handler class will satisfy;
this milestone creates no instance, no factory, and no registry. There is no
lifecycle to manage, no resource to close, and no state to track.

## 8. Call Direction

None. Nothing in the existing repository calls into or is called by this new
contract. `shared/contracts/command.py` imports nothing beyond the standard
library `typing` module. No domain package, no `bootstrap.py`, no
`FoundationRuntime`, and no repository or persistence type is referenced by
it, and nothing references it back. This is a leaf addition with zero edges
into the existing dependency graph, verified by the fact that the frozen
contract (Section 6) contains no import beyond `typing`.

## 9. Transaction Semantics

None. `CommandHandler.handle` is not required or assumed to open, join, or
manage any transaction, unit of work, or `run_composed` scope. A future
handler implementation may choose to use `PostgresRepositoryRuntime.run_composed`
internally, or may not need to — this Protocol expresses no opinion either
way, by design, since deciding that would require deciding transaction
ownership, which Section 16 (Stop Conditions) in the Scope Selection
document explicitly identifies as scope creep into "Application Service
Orchestration."

## 10. Repository/Runtime Interaction

None. `CommandT` and `ResultT` are unbound `TypeVar`s; neither is constrained
to, or aware of, `PostgresRepositoryRuntime`, `FoundationRuntime`, or any
M020 repository Protocol. A future handler implementation is free to accept
a repository runtime as a constructor dependency, but that decision belongs
to that future implementation, not to this contract.

## 11. Concurrency Semantics

None introduced. No `ContextVar`, no lock, no thread-safety claim is made or
needed for a pure structural Protocol with no state.

## 12. Error Taxonomy

No new error type is frozen. `CommandHandler.handle` carries no explicit
`raises` contract beyond ordinary Python exception propagation. This is a
deliberate decision, not an oversight: inventing a handler-level error
hierarchy now, with no concrete handler yet in existence to reveal what
failure modes it actually needs to express, risks freezing the wrong shape
and requiring a correction later — exactly the failure mode this project's
own design-correction history (M022, M025, M026) has repeatedly had to fix
after the fact. The existing M020 `RepositoryContractError` hierarchy
(`AggregateNotFound`, `AggregateAlreadyExists`, `OptimisticConcurrencyConflict`,
`InvalidAggregateForPersistence`, `InvalidPersistedAggregateState`) remains
available, unmodified, for any future handler that chooses to let repository
errors propagate through `handle`; nothing here shadows or duplicates it.

## 13. Failure Behavior

Not applicable — a pure structural type introduces no runtime behavior and
therefore no failure path. `CommandHandler` cannot itself raise, fail to
construct, or leak a resource, since this milestone constructs no instance
of anything.

## 14. Architecture Rules

- `shared/contracts/command.py` imports only the standard library `typing`
  module.
- No domain package (`campaign`/`run`/`evidence`/`review`) is required to
  import this new contract as part of this milestone.
- No import of `shared.persistence`, `sqlalchemy`, `psycopg`, or `boto3`.
- No change to `tools/check_architecture.py`'s `ALLOWED` or
  `FORBIDDEN_IMPORT_PREFIXES` tables.
- No change to any M020-M026 frozen source file.

## 15. Test Strategy for Future Implementation

A future implementation must add tests proving:

1. `mypy` (run as part of `verify.ps1`, scoped to `packages =
   ["empirical_platform"]`) accepts the `if TYPE_CHECKING:`
   structural-conformance check frozen in Section 6, inside
   `shared/contracts/command.py` itself — this is the actual enforcement
   mechanism, not a `tests/`-based check, since `mypy` does not type-check
   `tests/` under the current project configuration.
2. A `tests/unit/test_m027_command_handler_contracts.py` file imports
   `CommandHandler` and constructs a minimal example class at runtime
   (exercised by pytest, not mypy) purely to prove the module imports
   cleanly with zero dependency beyond `typing` (import-graph proof that
   Section 8's "zero edges" claim holds) — this test proves importability,
   not structural type-conformance, which is `mypy`'s job per Item 1.
3. `tools/check_architecture.py .` reports zero violations with the new file
   present.
4. No existing M020-M026 test is affected (full `verify.ps1` regression,
   unmodified pass count).

## 16. Compatibility With M020 Through M026

No source file governed by M020 (Repository Protocols), M021 (mapper
contracts), M022 (schema/migration), M023 (concrete adapters), M024
(`run_composed`), M025 (`PostgresRepositoryRuntime`), or M026
(`FoundationRuntime.repository_runtime`) is modified by this design. This
milestone only adds one new, zero-dependency file under
`shared/contracts/` and exports one name from `shared/contracts/__init__.py`.

## 17. Deferred Work

Explicitly out of scope for M027:

- any concrete `Command` or `CommandHandler` implementation for any
  aggregate;
- application service orchestration, transaction ownership decisions, or
  any wiring to `PostgresRepositoryRuntime`/`run_composed`;
- a handler-level error hierarchy (Section 12);
- retry-on-`OptimisticConcurrencyConflict` policy;
- APIs, workers, CLI entrypoints, or any change to `entrypoints/`;
- Audit runtime, Decision Candidate, Decision Freeze;
- market-data, vendor, trading, or campaign execution behavior;
- any named MILESTONE-028 work.

## 18. Acceptance Criteria

The design is acceptance-ready only if it freezes, with no remaining
ambiguity:

1. the exact `CommandHandler[CommandT, ResultT]` Protocol shape — frozen,
   Section 6;
2. the exact package/file placement — frozen, Section 5;
3. the exact, justified decision not to freeze a separate `Command` marker
   type — frozen, Section 4;
4. the exact, justified decision not to freeze a handler-level error type —
   frozen, Section 12;
5. exact test obligations for the future implementation — frozen, Section 15.

## 19. Rejected Alternatives

1. **Freeze a separate, empty `Command` Protocol as a marker type.**
   Rejected in Section 4: an empty `Protocol` is structurally satisfied by
   every object, providing no compile-time or runtime guarantee; freezing
   one would be purely decorative.
2. **Freeze a handler-level error hierarchy now.** Rejected in Section 12:
   with no concrete handler yet in existence, any such hierarchy would be a
   guess, and this project's own history (M022/M025/M026) shows guessed
   contracts tend to require a correction round once a real implementation
   reveals the actual shape needed. Better to defer until a concrete
   handler exists.
3. **Add a `@runtime_checkable` decorator for `isinstance` support.**
   Rejected in Section 6: no code path in this milestone needs runtime
   `isinstance` checking, and `runtime_checkable` only checks method
   presence, not signature — `mypy`'s static check is the real enforcement
   and is already sufficient.
4. **Constrain `CommandT`/`ResultT` to a bound (e.g. requiring a common base
   class).** Rejected: any such bound would presume a shape for commands and
   results that no concrete implementation yet justifies; unbound `TypeVar`s
   keep the contract maximally permissive until a real need narrows it.
5. **Place the new contract in a new top-level `application` package instead
   of `shared/contracts/`.** Rejected: introducing a new top-level package
   is a larger architectural decision than this narrow milestone warrants,
   and would require an `ALLOWED`/`FORBIDDEN_IMPORT_PREFIXES` table change
   this milestone does not need; `shared/contracts/` already serves this
   exact role for M020's repository Protocols.

## 20. Risk Register

| Risk | Mitigation |
| --- | --- |
| A future implementer conflates this Protocol with "application services already exist" | Section 7/8/9/10 each explicitly state no ownership, call direction, transaction, or repository interaction is introduced |
| A future implementer invents a `Command` marker type anyway, out of habit | Section 4/19 Item 1 explicitly document why one was not frozen, with reasoning a future reader can re-evaluate |
| A future implementer adds a handler-level error type without re-deriving why M020's errors weren't reused | Section 12/19 Item 2 name the exact reasoning and the exact prior-milestone pattern this decision is based on |

## 21. Hostile Self-Review

1. **Does this quietly become "application services"?** No — no instance,
   factory, registry, or dispatcher is created; Section 7 states nothing
   owns a `CommandHandler` as part of this milestone.
2. **Does this presume a specific dispatch or bus mechanism?** No — the
   Protocol describes a callable shape only; Section 19 Item 5 and the
   Scope Selection's own Non-Goals explicitly exclude any registry/bus.
3. **Does this leak into transaction ownership?** No — Section 9 explicitly
   states no transaction semantics are introduced or assumed.
4. **Does this leak into repository/runtime access?** No — Section 10
   confirms `CommandT`/`ResultT` are unconstrained and reference no
   persistence type.
5. **Does this leak into APIs/workers?** No — nothing in `entrypoints/` is
   touched; Section 8 confirms zero edges into the existing dependency
   graph.
6. **Does this leak into retry policy?** No — Section 17 explicitly defers
   it, consistent with the checkpoint's own deferred-capabilities ordering.
7. **Is the "no error taxonomy" decision actually justified, or just
   avoidance?** Justified: Section 12 gives a concrete, falsifiable reason
   (no concrete handler exists yet to reveal the real shape) grounded in
   this project's own repeated design-correction history, not mere
   convenience.
8. **Does this leak into M028?** No — Section 17's deferred list is
   identical in kind to every prior milestone's deferred list; nothing here
   presumes or requires any named future milestone.
9. **Are the frozen test obligations actually enforceable, or merely
   aspirational?** A genuine gap was caught and corrected during this same
   authoring pass: an initial draft of Section 15 Item 1 proposed proving
   structural conformance via a `tests/`-based example class checked by
   `mypy` — but `mypy`'s configured scope is `packages =
   ["empirical_platform"]` (`src/` only), so a `tests/`-based conformance
   check would silently never be type-checked by anything, making the
   obligation unenforceable in practice. Corrected by moving the
   structural-conformance proof into an `if TYPE_CHECKING:` block inside
   `shared/contracts/command.py` itself (Section 6), where `mypy` verifies
   it on every run with zero runtime cost; the `tests/`-based test now
   proves only importability (Section 15 Item 2), which pytest genuinely
   does check.

## 22. Final Status

```text
M027 DESIGN READY FOR INDEPENDENT REVIEW
M027 NOT APPROVED
M027 NOT FROZEN
M027 IMPLEMENTATION NOT STARTED
```

Do not implement source code. Do not start M028.
