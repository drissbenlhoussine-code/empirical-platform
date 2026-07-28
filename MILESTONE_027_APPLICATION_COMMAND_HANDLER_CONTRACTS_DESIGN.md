# MILESTONE-027 - Application Command/Handler Contracts Design

## 1. Document Control

| Field | Value |
| --- | --- |
| Document ID | MILESTONE-027-DESIGN |
| Title | Application Command/Handler Contracts Design |
| Version | 1.1 |
| Status | DESIGN NARROW CORRECTION COMPLETE - READY FOR FINAL INDEPENDENT RE-REVIEW / NOT APPROVED / NOT FROZEN |
| Repository baseline | `45f4916d1fcdd76b28fffa81c23704f6b0355c3d` |
| Authoritative scope input | `MILESTONE_027_APPLICATION_COMMAND_HANDLER_CONTRACTS_SCOPE_SELECTION.md` |
| Mission type | Design only |

**Do not implement source code. Do not start M028.**

## 2. Purpose

Freeze the persistence-neutral, domain-agnostic vocabulary for an
application-layer command handler — a single generic, variance-correct
`CommandHandler` Protocol — with zero implementation of any concrete
command, handler, or orchestration logic, exactly mirroring how M020 froze
repository Protocols before M023 implemented any concrete adapter.

## 3. Design Inputs

- `MILESTONE_027_APPLICATION_COMMAND_HANDLER_CONTRACTS_SCOPE_SELECTION.md`
  (frozen scope: contracts only; no orchestration, no repository wiring, no
  APIs/workers).
- `src/empirical_platform/shared/contracts/repository.py` and
  `src/empirical_platform/shared/contracts/mapping.py` (read in full — the
  established placement and style precedent for domain-agnostic contracts
  under `shared/contracts/`).
- `pyproject.toml`'s `[tool.mypy]` section (read in full: `strict = true`,
  `mypy_path = "src"`, `packages = ["empirical_platform"]` — confirming
  `tests/` is outside mypy's configured scope, and that `mypy_path` makes
  `empirical_platform.*` resolvable even for a file passed explicitly on the
  command line from outside the `packages` walk).
- Live `grep` evidence: no `Command`/`Handler` type exists anywhere in the
  repository today.
- Direct, live `mypy` experimentation (this correction round) proving both
  the variance defect (Section 6) and the negative-fixture mechanism
  (Section 13) against the actual project `pyproject.toml` configuration,
  not merely asserted.

## 4. Exact Responsibility

This milestone freezes exactly one Protocol:

```python
class CommandHandler(Protocol[_CommandT_contra, _ResultT_co]):
    def handle(self, command: _CommandT_contra) -> _ResultT_co: ...
```

It does not freeze a separate `Command` marker type. An empty Protocol with
no required members is structurally satisfied by every object in Python
(`Protocol` structural typing has nothing to check against), so it would
provide no compile-time or runtime guarantee — freezing one would be
decorative, not load-bearing. This is a deliberate, narrower-than-initially-
scoped outcome of this Design phase (see Section 16, Rejected Alternatives).

## 5. Package Placement

New file: `src/empirical_platform/shared/contracts/command.py`, alongside the
existing `repository.py` and `mapping.py`. Exported from
`src/empirical_platform/shared/contracts/__init__.py`, matching the existing
`__all__` pattern for `repository.py`'s exports.

No new top-level package. `tools/check_architecture.py`'s `ALLOWED` table
requires no change: `shared` is already importable by every domain package,
and this new file introduces no import of `sqlalchemy`, `psycopg`, `boto3`,
or `shared.persistence`.

## 6. Contracts and Types — Variance-Correct Generics

**Correction record (Version 1.1):** Version 1.0 froze plain invariant
`TypeVar`s (`CommandT = TypeVar("CommandT")`, `ResultT = TypeVar("ResultT")`).
Direct experimentation with the project's own `mypy --strict` configuration,
performed during this correction round, proved this was not merely a style
preference but an actual defect: mypy itself rejects an invariant `TypeVar`
used in a `Protocol` whose sole method consumes it as a parameter and
produces it as a return, with:

```text
error: Invariant type variable "CommandT" used in protocol where contravariant one is expected  [misc]
error: Invariant type variable "ResultT" used in protocol where covariant one is expected  [misc]
```

Had Version 1.0's code block ever been implemented verbatim, it would have
failed the project's own canonical `mypy` gate immediately. This is corrected
here, before any implementation was authorized, which is exactly what a
design-stage review exists to catch.

Exact frozen contract:

```python
"""Application-layer command handler contract."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, TypeVar

_CommandT_contra = TypeVar("_CommandT_contra", contravariant=True)
_ResultT_co = TypeVar("_ResultT_co", covariant=True)


class CommandHandler(Protocol[_CommandT_contra, _ResultT_co]):
    """Structural contract for a single application-layer command handler.

    A handler receives exactly one command instance and returns exactly one
    result. This Protocol makes no assumption about what a command or result
    type is, how a handler is constructed, how it is registered or
    dispatched, or what it does internally -- all of that is explicitly out
    of scope for this milestone.
    """

    def handle(self, command: _CommandT_contra) -> _ResultT_co:
        """Handle one command instance and return its result."""
        ...
```

Frozen, non-negotiable properties of this one method:

- synchronous (`def`, not `async def`) — no asynchronous behavior is claimed
  or implied anywhere in this milestone;
- exactly one method, named `handle`;
- exactly one positional parameter beyond `self`, named `command`, of type
  `_CommandT_contra`;
- no keyword-only parameter is required;
- returns `_ResultT_co`.

**Why the variance is type-correct:** `_CommandT_contra` appears only in
input (parameter) position, so it is safe to mark contravariant — a
`CommandHandler[NarrowCmd, Res]` slot may safely hold a handler whose
`handle` accepts a *wider* command type than `NarrowCmd` (e.g. `Cmd`, a
superclass), because such a handler can handle anything a `NarrowCmd`-typed
caller would ever pass it. `_ResultT_co` appears only in output (return)
position, so it is safe to mark covariant — a `CommandHandler[Cmd, Res]` slot
may safely hold a handler whose `handle` returns a *narrower* result type
than `Res` (e.g. a subclass), because any caller expecting `Res` can safely
receive the narrower subtype. Both directions were verified directly against
the project's own `mypy --strict` configuration during this correction round:
a handler accepting a broader command type, and a handler returning a
narrower result type, both type-check cleanly against the corrected
contravariant/covariant Protocol with zero errors — and both would be
(correctly) rejected under the Version 1.0 invariant definition, which mypy
itself refuses to even accept as a valid Protocol definition in the first
place (Section 6, correction record, above).

```python
if TYPE_CHECKING:

    class _ExampleCommand:
        ...

    class _ExampleResult:
        ...

    class _ExampleHandler:
        def handle(self, command: _ExampleCommand) -> _ExampleResult: ...

    _typed_conformance_check: CommandHandler[_ExampleCommand, _ExampleResult] = (
        _ExampleHandler()
    )
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
ownership, which the Scope Selection document's own Stop Conditions
explicitly identify as scope creep into "Application Service Orchestration."

## 10. Repository/Runtime Interaction

None. `_CommandT_contra` and `_ResultT_co` are unbound `TypeVar`s; neither is
constrained to, or aware of, `PostgresRepositoryRuntime`, `FoundationRuntime`,
or any M020 repository Protocol. A future handler implementation is free to
accept a repository runtime as a constructor dependency, but that decision
belongs to that future implementation, not to this contract.

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
own design-correction history (M022, M025, M026, and this very milestone's
variance defect) has repeatedly had to fix after the fact. The existing M020
`RepositoryContractError` hierarchy (`AggregateNotFound`,
`AggregateAlreadyExists`, `OptimisticConcurrencyConflict`,
`InvalidAggregateForPersistence`, `InvalidPersistedAggregateState`) remains
available, unmodified, for any future handler that chooses to let repository
errors propagate through `handle`; nothing here shadows or duplicates it.

## 13. Negative Type-Check Strategy

**Correction record (Version 1.1):** Version 1.0 required that malformed
handler implementations be mechanically proven rejected, but froze no exact
mechanism for doing so. This section freezes one, verified directly against
the project's actual `mypy --strict` configuration during this correction
round — not merely proposed.

**Frozen mechanism — isolated negative typing fixtures, checked by an
explicit `mypy` subprocess invocation, kept entirely outside the canonical
`mypy` gate:**

Exact fixture directory (future implementation):

```text
tests/typing_fixtures/command_handler/
    ok_handler.py
    wrong_method.py
    wrong_command_type.py
    wrong_result_type.py
    missing_handle.py
```

Each fixture is a small, standalone module that imports the real
`CommandHandler` from `empirical_platform.shared.contracts.command`, defines
one minimal command/result pair and one handler class, and assigns an
instance of that handler to a `CommandHandler[...]`-typed variable:

- `ok_handler.py`: a correctly-shaped handler — a **positive** isolated
  fixture, proving the invocation mechanism itself works (guards against a
  false-positive where every fixture "fails" merely because the subprocess
  invocation is broken, e.g. an import error, rather than because of the
  intended type mismatch).
- `wrong_method.py`: defines `process(self, command: Cmd) -> Res` instead of
  `handle`.
- `wrong_command_type.py`: defines `handle(self, command: OtherCmd) -> Res`
  where `OtherCmd` is unrelated to the expected command type.
- `wrong_result_type.py`: defines `handle(self, command: Cmd) -> OtherRes`
  where `OtherRes` is unrelated to the expected result type.
- `missing_handle.py`: defines a class with no `handle` method at all.

Exact frozen pytest test file: `tests/unit/test_command_handler_typing.py`.

Exact frozen algorithm, verified directly against the four negative fixture
shapes above using a locally-defined equivalent Protocol during this
correction round:

1. Resolve the repository root from the test file's own path (e.g.
   `Path(__file__).resolve().parents[2]`), and resolve
   `pyproject.toml` beneath it.
2. For `ok_handler.py`: invoke
   `[sys.executable, "-m", "mypy", "--config-file", str(pyproject_path), str(fixture_path)]`
   as a subprocess; assert exit code `0` and that stdout contains
   `"Success: no issues found"`.
3. For each of the four negative fixtures: invoke the identical subprocess
   command against that fixture; assert the exit code is non-zero; assert
   stdout contains both stable diagnostic fragments `"error: Incompatible
   types in assignment"` and the mypy error code `"[assignment]"` — verified
   directly, during this correction round, to be the exact, stable substring
   mypy emits for all four malformed-handler shapes (missing method, wrong
   method name, wrong parameter type, and wrong return type each produce this
   identical top-level diagnostic category; the two signature-mismatch cases
   additionally emit `note:` lines naming the exact expected/got signatures,
   which the test may assert on for extra precision but is not required to).
4. No use of `Any` or `cast` anywhere in the fixtures to force a failure —
   each fixture fails because its handler's shape is genuinely incompatible
   with `CommandHandler[...]`, not because type-checking was artificially
   defeated.
5. No mutation of `pyproject.toml`'s canonical `[tool.mypy]` section for the
   fixtures' benefit. `--config-file` is passed explicitly on the subprocess
   command line specifically so the fixtures reuse the exact canonical
   strictness configuration without requiring any config change.
6. `tests/typing_fixtures/command_handler/` is never added to
   `[tool.mypy] packages` (which stays exactly `["empirical_platform"]`), so
   the canonical `python -m mypy` gate run in `verify.ps1` never walks these
   fixtures and is unaffected by them; only the one dedicated
   subprocess-invoking pytest test ever executes `mypy` against them.

**On `--explicit-package-bases`:** verified directly during this correction
round to be unnecessary for this fixture shape (single-file, no `__init__.py`,
no package ambiguity) — invoking plain `python -m mypy --config-file
<path-to-pyproject.toml> <fixture-file>` was sufficient to reproduce every
diagnostic above, both from the repository root and from an unrelated
working directory. It is not frozen as part of the command, since freezing
an unverified flag would violate this same section's own standard.

**On accidental pytest collection of the fixtures themselves:** verified
directly against `pyproject.toml`'s `[tool.pytest.ini_options]` (no custom
`python_files` pattern is set, so pytest's default `test_*.py`/`*_test.py`
collection glob applies). None of the five frozen fixture filenames
(`ok_handler.py`, `wrong_method.py`, `wrong_command_type.py`,
`wrong_result_type.py`, `missing_handle.py`) match that glob, so pytest's own
collection pass never imports them as test modules in their own right —
they are only ever read and passed as a file path argument to the `mypy`
subprocess invoked by `test_command_handler_typing.py`. This closes the
"runtime fixture leakage" failure mode: the fixtures never execute as
Python at collection time, only their source text is type-checked.

## 14. Failure Behavior

Not applicable — a pure structural type introduces no runtime behavior and
therefore no failure path. `CommandHandler` cannot itself raise, fail to
construct, or leak a resource, since this milestone constructs no instance
of anything at runtime. (The negative-fixture mechanism in Section 13 proves
*rejection at type-check time*, which is a distinct concern from runtime
failure behavior.)

## 15. Architecture Rules

- `shared/contracts/command.py` imports only the standard library `typing`
  module.
- No domain package (`campaign`/`run`/`evidence`/`review`) is required to
  import this new contract as part of this milestone.
- No import of `shared.persistence`, `sqlalchemy`, `psycopg`, or `boto3`.
- No change to `tools/check_architecture.py`'s `ALLOWED` or
  `FORBIDDEN_IMPORT_PREFIXES` tables.
- No change to `[tool.mypy] packages` in `pyproject.toml` — `tests/typing_fixtures/`
  is deliberately never added to it (Section 13).
- No change to any M020-M026 frozen source file.

## 16. Export Surface

Exact frozen export surface:

- module: `empirical_platform.shared.contracts.command`;
- canonical, public export: `CommandHandler` only;
- `shared/contracts/__init__.py` exports `CommandHandler`, matching the
  existing `__all__` pattern already used for `repository.py`'s exports.

`_CommandT_contra` and `_ResultT_co` are module-private implementation
details, not public exports — named with a leading underscore for exactly
that reason, and never added to `shared/contracts/__init__.py`'s `__all__`.
There is no concrete public need for callers to reference the `TypeVar`
objects themselves; a caller only ever needs `CommandHandler[SomeCommand,
SomeResult]`, never the bare `TypeVar`.

Not exported, by explicit design decision (Section 4, Section 12, Section 9):

- a `Command` marker type (none is frozen at all);
- a handler-level error/result-wrapper type (none is frozen at all);
- a dispatcher or runtime registry (none is frozen at all).

## 17. Test Strategy for Future Implementation

A future implementation must add tests proving:

1. `mypy` (run as part of `verify.ps1`, scoped to `packages =
   ["empirical_platform"]`) accepts the `if TYPE_CHECKING:`
   structural-conformance check frozen in Section 6, inside
   `shared/contracts/command.py` itself.
2. `tests/unit/test_command_handler_typing.py` invokes the exact subprocess
   algorithm frozen in Section 13 against all five fixtures under
   `tests/typing_fixtures/command_handler/`, proving: the positive fixture
   passes cleanly; each of the four negative fixtures fails with the frozen
   `[assignment]` diagnostic fragment; and the canonical `mypy` gate (Item 1)
   is unaffected by the fixtures' existence.
3. A contravariant-input assignment (a handler accepting a wider command
   type than the slot's declared command type) and a covariant-output
   assignment (a handler returning a narrower result type than the slot's
   declared result type) both type-check cleanly — either as additional
   `if TYPE_CHECKING:` proofs in the module, or as additional fixtures,
   demonstrating the variance correction (Section 6) is real and not merely
   asserted.
4. A separate module-level import test (pytest, not mypy) proves
   `shared/contracts/command.py` imports cleanly with zero dependency beyond
   `typing` (import-graph proof that Section 8's "zero edges" claim holds),
   and that only `CommandHandler` — not `_CommandT_contra`/`_ResultT_co` — is
   present in `shared/contracts/__init__.py`'s public export surface.
5. `tools/check_architecture.py .` reports zero violations with the new file
   present.
6. No existing M020-M026 test is affected (full `verify.ps1` regression,
   unmodified pass count).
7. `build` and package-metadata gates are unaffected — no new dependency, no
   packaging change.

## 18. Compatibility With M020 Through M026

No source file governed by M020 (Repository Protocols), M021 (mapper
contracts), M022 (schema/migration), M023 (concrete adapters), M024
(`run_composed`), M025 (`PostgresRepositoryRuntime`), or M026
(`FoundationRuntime.repository_runtime`) is modified by this design. This
milestone only adds one new, zero-dependency file under
`shared/contracts/`, one small typing-fixture directory under `tests/`
(never walked by the canonical `mypy` gate), and exports one name from
`shared/contracts/__init__.py`.

## 19. Deferred Work

Explicitly out of scope for M027:

- any concrete `Command` or `CommandHandler` implementation for any
  aggregate;
- application service orchestration, transaction ownership decisions, or
  any wiring to `PostgresRepositoryRuntime`/`run_composed`;
- a handler-level error hierarchy (Section 12);
- a `Command` marker type (Section 4);
- a dispatcher or runtime registry (Section 16);
- retry-on-`OptimisticConcurrencyConflict` policy;
- APIs, workers, CLI entrypoints, or any change to `entrypoints/`;
- Audit runtime, Decision Candidate, Decision Freeze;
- market-data, vendor, trading, or campaign execution behavior;
- any named MILESTONE-028 work.

## 20. Acceptance Criteria

The design is acceptance-ready only if it freezes, with no remaining
ambiguity:

1. the exact `CommandHandler[_CommandT_contra, _ResultT_co]` Protocol shape,
   with correct, verified variance — frozen, Section 6;
2. the exact package/file placement — frozen, Section 5;
3. the exact, justified decision not to freeze a separate `Command` marker
   type — frozen, Section 4;
4. the exact, justified decision not to freeze a handler-level error type —
   frozen, Section 12;
5. the exact negative type-check strategy, verified against live `mypy`
   behavior — frozen, Section 13;
6. the exact export surface, including that the `TypeVar`s are private —
   frozen, Section 16;
7. exact test obligations for the future implementation — frozen, Section 17.

Both narrow-correction findings and the one MINOR finding (Scope Selection
staleness) are resolved by this Version 1.1; no acceptance-gate item remains
open.

## 21. Rejected Alternatives

1. **Freeze a separate, empty `Command` Protocol as a marker type.**
   Rejected in Section 4: an empty `Protocol` is structurally satisfied by
   every object, providing no compile-time or runtime guarantee; freezing
   one would be purely decorative.
2. **Freeze a handler-level error hierarchy now.** Rejected in Section 12:
   with no concrete handler yet in existence, any such hierarchy would be a
   guess, and this project's own history shows guessed contracts tend to
   require a correction round once a real implementation reveals the actual
   shape needed — this milestone's own variance defect (Section 6) is a
   fresh, concrete instance of exactly that pattern.
3. **Add a `@runtime_checkable` decorator for `isinstance` support.**
   Rejected in Section 6: no code path in this milestone needs runtime
   `isinstance` checking, and `runtime_checkable` only checks method
   presence, not signature — `mypy`'s static check is the real enforcement
   and is already sufficient.
4. **Constrain `_CommandT_contra`/`_ResultT_co` to a bound (e.g. requiring a
   common base class).** Rejected: any such bound would presume a shape for
   commands and results that no concrete implementation yet justifies;
   unbound `TypeVar`s keep the contract maximally permissive until a real
   need narrows it.
5. **Place the new contract in a new top-level `application` package instead
   of `shared/contracts/`.** Rejected: introducing a new top-level package
   is a larger architectural decision than this narrow milestone warrants,
   and would require an `ALLOWED`/`FORBIDDEN_IMPORT_PREFIXES` table change
   this milestone does not need; `shared/contracts/` already serves this
   exact role for M020's repository Protocols.
6. **Use plain invariant `TypeVar`s (Version 1.0).** Rejected: proven, by
   direct experimentation against the project's own `mypy --strict`
   configuration (Section 6), to be an actual mypy-rejected Protocol
   definition, not a valid but merely less-precise alternative.
7. **Prove malformed-handler rejection only informally, without a mechanical
   test.** Rejected: this milestone's Scope Selection explicitly requires
   malformed implementations be *mechanically* proven rejected; an informal
   claim would not survive the acceptance gate (Section 20).
8. **Export `_CommandT_contra`/`_ResultT_co` as public names.** Rejected in
   Section 16: no concrete public need exists for a caller to reference the
   bare `TypeVar` objects; `CommandHandler[...]` alone is sufficient for
   every use this milestone anticipates.

## 22. Risk Register

| Risk | Mitigation |
| --- | --- |
| A future implementer conflates this Protocol with "application services already exist" | Section 7/8/9/10 each explicitly state no ownership, call direction, transaction, or repository interaction is introduced |
| A future implementer invents a `Command` marker type anyway, out of habit | Section 4/21 Item 1 explicitly document why one was not frozen, with reasoning a future reader can re-evaluate |
| A future implementer adds a handler-level error type without re-deriving why M020's errors weren't reused | Section 12/21 Item 2 name the exact reasoning and the exact prior-milestone pattern this decision is based on |
| A future implementer re-introduces invariant `TypeVar`s, reproducing the corrected defect | Section 6's correction record names the exact mypy error text produced by the invariant form, making the mistake immediately self-diagnosing if repeated |
| A future implementer's negative fixtures accidentally get walked by the canonical `mypy` gate, turning intentionally-broken code into a build failure | Section 13 Item 6 and Section 15 explicitly freeze that `[tool.mypy] packages` never includes the fixture directory |
| A future implementer exports the private `TypeVar`s by accident | Section 16 and Section 17 Item 4 make "only `CommandHandler` is exported" an explicit, named test obligation |

## 23. Hostile Self-Review

1. **Does this quietly become "application services"?** No — no instance,
   factory, registry, or dispatcher is created; Section 7 states nothing
   owns a `CommandHandler` as part of this milestone.
2. **Does this presume a specific dispatch or bus mechanism?** No — the
   Protocol describes a callable shape only; Section 21 Item 5 and the
   Scope Selection's own Non-Goals explicitly exclude any registry/bus.
3. **Does this leak into transaction ownership?** No — Section 9 explicitly
   states no transaction semantics are introduced or assumed.
4. **Does this leak into repository/runtime access?** No — Section 10
   confirms `_CommandT_contra`/`_ResultT_co` are unconstrained and reference
   no persistence type.
5. **Does this leak into APIs/workers?** No — nothing in `entrypoints/` is
   touched; Section 8 confirms zero edges into the existing dependency
   graph.
6. **Does this leak into retry policy?** No — Section 19 explicitly defers
   it, consistent with the checkpoint's own deferred-capabilities ordering.
7. **Is the "no error taxonomy" decision actually justified, or just
   avoidance?** Justified: Section 12 gives a concrete, falsifiable reason
   (no concrete handler exists yet to reveal the real shape) grounded in
   this project's own repeated design-correction history — now including
   this milestone's own variance defect as a fresh data point.
8. **Does this leak into M028?** No — Section 19's deferred list is
   identical in kind to every prior milestone's deferred list; nothing here
   presumes or requires any named future milestone.
9. **Is the variance direction actually correct, or just asserted?**
   Verified, not asserted: Section 6 documents the exact `mypy --strict`
   error produced by the invariant (Version 1.0) form, and the exact
   contravariant-input/covariant-output assignments that type-check cleanly
   under the corrected form — both reproduced directly during this
   correction round, not reasoned about in the abstract.
10. **Do the negative fixtures actually fail for the intended reason, or
    could they pass/fail for an unrelated reason (e.g. a broken import)?**
    Guarded against: Section 13 freezes a positive (`ok_handler.py`) fixture
    specifically to prove the invocation mechanism itself works, so a
    universal "everything fails" false positive (e.g. from a broken
    `--config-file` path) would be caught by the positive fixture failing
    too, not silently masked.
11. **Could the negative fixtures accidentally pollute or weaken the
    canonical `mypy` gate?** No — Section 13 Item 6 and Section 15 freeze
    that `tests/typing_fixtures/` is never added to `[tool.mypy] packages`;
    the canonical gate's scope (`["empirical_platform"]`) is unchanged.
12. **Are the `TypeVar`s at risk of accidental public exposure?** No —
    Section 16 freezes the leading-underscore naming and the exact
    `__all__` contents (`CommandHandler` only), and Section 17 Item 4 makes
    non-export of the `TypeVar`s a named test obligation.
13. **Does async behavior get overclaimed anywhere?** No — Section 6
    explicitly freezes `handle` as synchronous (`def`, not `async def`); no
    sentence in this document claims or implies asynchronous support.
14. **Could the negative fixtures leak into the normal test run as
    executable code rather than as mypy-checked text?** No — verified
    directly against `pyproject.toml`'s pytest configuration (Section 13):
    none of the five frozen fixture filenames match pytest's default
    `test_*.py`/`*_test.py` collection glob, so pytest never imports or
    executes them; they are only ever read as source text by the `mypy`
    subprocess.

## 24. Final Status

```text
M027 DESIGN NARROW CORRECTION COMPLETE
READY FOR FINAL INDEPENDENT RE-REVIEW
NOT APPROVED
NOT FROZEN
M027 IMPLEMENTATION NOT STARTED
```

Do not implement source code. Do not start M028.
