# MILESTONE-028 - Application Query/QueryHandler Contracts Design

## 1. Document Control

| Field | Value |
| --- | --- |
| Document ID | MILESTONE-028-DESIGN |
| Title | Application Query/QueryHandler Contracts Design |
| Version | 1.1 |
| Status | DESIGN NARROW CORRECTION COMPLETE - READY FOR FINAL INDEPENDENT RE-REVIEW / NOT APPROVED / NOT FROZEN |
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
  nominal relationship to `CommandHandler`).
- `MILESTONE_027_APPLICATION_COMMAND_HANDLER_CONTRACTS_DESIGN.md` (Version
  1.1, frozen) — this design deliberately reuses its exact, independently
  verified pattern (contravariant/covariant generics; an
  `if TYPE_CHECKING:` positive conformance proof inside the module; an
  isolated, `mypy`-verified negative type-check fixture mechanism) rather
  than re-deriving it, since `QueryHandler`'s structural shape (one method,
  one contravariant input, one covariant output) is identical in kind to
  `CommandHandler`'s.
- Live `grep` evidence: no `Query`/`QueryHandler` type exists anywhere in
  the repository today.
- Direct, live `mypy` experimentation (this correction round) proving both
  that a single concrete class can structurally satisfy `CommandHandler`
  and `QueryHandler` simultaneously when their type arguments align (Section
  9), and that genuinely mismatched type arguments are still correctly
  rejected (Section 9) — not merely asserted.

## 4. Exact Responsibility

This milestone freezes exactly one Protocol:

```python
class QueryHandler(Protocol[_QueryT_contra, _QueryResultT_co]):
    def handle(self, query: _QueryT_contra) -> _QueryResultT_co: ...
```

It does not freeze a separate `Query` marker type, for the identical reason
M027 rejected a `Command` marker: an empty `Protocol` is structurally
satisfied by every object, providing no compile-time or runtime guarantee.
**This design does not introduce a nominal marker class for the opposite
reason either** — i.e., not as a device to *prevent* `QueryHandler` from
being structurally satisfiable alongside `CommandHandler`. Section 9
explains why no such prevention is attempted.

## 5. Package Placement

New file: `src/empirical_platform/shared/contracts/query.py`, alongside the
existing `repository.py`, `mapping.py`, and (design-frozen, not yet
implemented) `command.py`. Exported from
`src/empirical_platform/shared/contracts/__init__.py`.

No new top-level package. `tools/check_architecture.py`'s `ALLOWED` table
requires no change.

`query.py` does not import from, or otherwise reference, `command.py` or
`CommandHandler` — this is a declared-relationship fact (Section 9), not a
claim about structural typing behavior.

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
    of scope for this milestone. QueryHandler declares no inheritance,
    import, alias, or shared-base relationship with CommandHandler (Section
    9); Python's structural typing may still accept a single concrete class
    as satisfying both Protocols when its method shape and type arguments
    happen to align with both -- this Protocol does not attempt to prevent
    that (Section 9).
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
contravariant), and `_QueryResultT_co` appears only in output position (safe
to mark covariant). This is the exact same structural pattern M027's
correction round verified directly against the project's live `mypy
--strict` configuration: an invariant `TypeVar` used in a Protocol whose
sole method consumes it as a parameter and produces it as a return is
itself rejected by `mypy`. Since `QueryHandler`'s method shape is
structurally identical to `CommandHandler`'s, that verified result applies
without needing to re-run the experiment for a structurally-identical
Protocol.

No `@runtime_checkable` decorator, for the identical reason M027 froze none:
no code path in this milestone needs runtime `isinstance` checking, and
`mypy`'s static check is the actual, sufficient enforcement mechanism.

The `if TYPE_CHECKING:` conformance check is placed inside
`shared/contracts/query.py` itself (under `src/`), not in a test file, for
the identical reason M027 froze this placement.

No new error type, no new result-wrapper type, no registry, no dispatcher,
no base class requiring inheritance, and no *declared* relationship of any
kind to `CommandHandler` (Section 9 covers the distinction between declared
relationship and structural-typing reality in full).

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

## 9. Relationship to `CommandHandler` — Declared Relationship and Structural-Typing Reality

**Correction record (Version 1.1):** Version 1.0 described `QueryHandler`
and `CommandHandler` as "fully independent... at the type level" and
sharing "no type relationship." Direct experimentation with the project's
own `mypy --strict` configuration, performed during this correction round,
proved that phrasing overstated the truth: because both are structural
`Protocol`s with the identical callable shape
(`def handle(self, value: InputT) -> OutputT`), **one concrete class can
structurally satisfy both Protocols simultaneously** whenever its parameter
and return types happen to align with both Protocols' type arguments. This
section replaces the Version 1.0 wording with the precise, verified truth,
distinguishing two genuinely different things that were previously
conflated under one word ("independent"):

**Declared relationship (frozen, exact):**

- `QueryHandler` and `CommandHandler` are separate public semantic
  vocabularies, each with its own name, its own module, and its own meaning
  to a human reader;
- neither imports, inherits from, aliases, wraps, or extends the other —
  verified directly: `shared/contracts/query.py`'s only import is the
  standard library `typing` module (Section 6, Section 8);
- no shared `Handler` or `RequestHandler` base Protocol is introduced;
- no common `TypeVar` is shared between the two definitions;
- no nominal runtime relationship exists (no subclassing, no registration);
- no dispatcher, registry, or runtime routing relationship exists between
  them.

**Structural-typing reality (frozen, exact, verified):**

- Python's `Protocol` typing is structural, not nominal: a class satisfies a
  `Protocol` by having a matching method shape, regardless of any declared
  inheritance;
- verified directly during this correction round: a single concrete class
  defining exactly `def handle(self, value: Value) -> Outcome: ...` type-
  checks cleanly as **both** `CommandHandler[Value, Outcome]` **and**
  `QueryHandler[Value, Outcome]` simultaneously, with zero `mypy` errors,
  when the same `Value`/`Outcome` types are used for both assignments;
- also verified directly: assigning that same concrete class to a
  `CommandHandler[Unrelated, Outcome]`-typed variable, where `Unrelated` is
  a genuinely different type than the handler's declared parameter type,
  is correctly rejected by `mypy` with an `Incompatible types in
  assignment [assignment]` error — structural compatibility is not
  universal; it only arises when the concrete handler's actual parameter
  and return types genuinely match both Protocols' type arguments;
- **this milestone does not attempt to prevent or mechanically defeat this
  structural-typing property.** Introducing a nominal marker class (e.g. a
  required, unique, unused sentinel field) purely to force `QueryHandler`
  and `CommandHandler` to become structurally incompatible would be
  fighting Python's own type system for no functional benefit, would
  complicate the Protocol shape beyond what any real caller needs, and
  is explicitly rejected (Section 23);
- **semantic separation between "this is read intent" and "this is write
  intent" is therefore enforced outside the Protocol definition, not by
  it** — specifically, by: distinct query and command value types chosen by
  application-layer authors (a `GetCampaignQuery` and a `CreateCampaignCommand`
  are different concrete classes even if, hypothetically, some other pair
  happened to share a shape); concrete application-layer code review;
  handler naming and module placement conventions; and future orchestration
  boundaries (e.g. a future dispatcher milestone that only ever looks up
  handlers by their registered *command* or *query* type, never by
  structural duck-typing).

A future milestone may reveal a genuine need to formally unify
`CommandHandler` and `QueryHandler` under a shared base (e.g. if an
orchestration boundary wants to treat both uniformly) — this design
deliberately does not anticipate that need now, since doing so would be
speculative before any concrete implementation of either exists. The Scope
Selection's own Stop Conditions require returning to scope selection, not
silently deciding this here, if such a need becomes concrete.

## 10. Read-Only Semantics

**Correction record (Version 1.1, new section):** Version 1.0 described
queries as "state-reading" (in the Scope Selection's CQRS framing) without
stating plainly enough that `QueryHandler` cannot mechanically enforce that
property. This section freezes the precise, honest scope of what the
Protocol does and does not guarantee.

`QueryHandler` expresses **read-side intent and vocabulary only**. Frozen,
exact limitations:

- the Protocol does not, and structurally cannot, inspect the implementation
  body of any concrete `handle` method — `Protocol` conformance is checked
  purely by method signature, never by what the method's body actually
  does;
- it cannot prevent a concrete handler from calling a repository's `add`,
  `save`, or any other mutating method;
- it cannot enforce a read-only database transaction mode;
- it cannot enforce cache-only access;
- it cannot enforce the absence of side effects of any kind;
- no read-only transaction mode, session type, or persistence abstraction is
  introduced by this milestone — no M020 repository Protocol, no
  `PostgresPersistenceService` method, and no `PostgresRepositoryRuntime`
  method is added, removed, or changed;
- no runtime guard, decorator, or wrapper enforcing non-mutation is
  introduced by this milestone, and none is planned as part of it.

Concrete read-only enforcement, if ever wanted, belongs entirely to future,
separate work — not to this contract:

- a future concrete-handler-implementation milestone, which alone can
  decide what persistence access a specific query handler actually needs;
- future architecture review (e.g. a `tools/check_architecture.py` rule, if
  one is ever wanted, restricting which repository methods query-handler
  modules may call — not attempted here);
- a future, separate repository-access or transaction policy milestone;
- tests written for each concrete query handler, individually proving that
  handler does not mutate state — `QueryHandler` the Protocol cannot write
  that test on any implementation's behalf.

This milestone's only claim is naming and vocabulary: calling something a
"query handler" documents *intent* to a human reader and to any future
static-analysis tool that might key off the name or module location. It is
not, and cannot be, a machine-enforced guarantee.

## 11. Transaction Semantics

None. `QueryHandler.handle` is not required or assumed to open, join, or
manage any transaction, unit of work, or `run_composed` scope — identical to
M027 Design Section 9. A future handler implementation may choose to read
through `PostgresRepositoryRuntime` directly, or may not need to touch
persistence at all — this Protocol expresses no opinion either way, and
(per Section 10) cannot enforce that a "query" handler only reads.

## 12. Repository/Runtime Interaction

None. `_QueryT_contra` and `_QueryResultT_co` are unbound `TypeVar`s; neither
is constrained to, or aware of, `PostgresRepositoryRuntime`,
`FoundationRuntime`, or any M020 repository Protocol.

## 13. Concurrency Semantics

None introduced. No `ContextVar`, no lock, no thread-safety claim.

## 14. Error Taxonomy

No new error type is frozen, for the identical reason M027 froze none: no
concrete handler yet exists to reveal what failure modes it needs to
express. The existing M020 `RepositoryContractError` hierarchy remains
available, unmodified, for any future query handler that chooses to let
repository errors (e.g. `AggregateNotFound`) propagate through `handle`.

## 15. Negative Type-Check Strategy

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
(Section 19 below covers both as parallel obligations).

Exact frozen algorithm — identical to M027 Design Section 13, Items 1-6,
substituting `QueryHandler`/`query` for `CommandHandler`/`command`
throughout: resolve the repository root and `pyproject.toml`; for
`ok_handler.py`, assert exit code `0` and `"Success: no issues found"` in
stdout; for each of the four negative fixtures, invoke
`[sys.executable, "-m", "mypy", "--config-file", str(pyproject_path),
str(fixture_path)]`, assert non-zero exit code, and assert stdout contains
both `"error: Incompatible types in assignment"` and `"[assignment]"`. No
`Any`/`cast` used to force a failure. No mutation of `pyproject.toml`'s
canonical `[tool.mypy]` section. `tests/typing_fixtures/query_handler/` is
never added to `[tool.mypy] packages`, exactly as
`tests/typing_fixtures/command_handler/` is not.

**On `--explicit-package-bases`:** not frozen, for the identical,
already-verified reason M027 Design Section 13 gives.

**On accidental pytest collection:** identical to M027 Design Section 13 —
none of the five frozen fixture filenames match pytest's default
`test_*.py`/`*_test.py` collection glob.

## 16. Failure Behavior

Not applicable — a pure structural type introduces no runtime behavior and
therefore no failure path, identical to M027 Design Section 14.

## 17. Architecture Rules

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

## 18. Export Surface

Exact frozen export surface:

- module: `empirical_platform.shared.contracts.query`;
- canonical, public export: `QueryHandler` only;
- `shared/contracts/__init__.py` exports `QueryHandler`, alongside
  `CommandHandler` (once M027 is implemented), matching the existing
  `__all__` pattern.

`_QueryT_contra` and `_QueryResultT_co` are module-private implementation
details, named with a leading underscore, never added to `__all__`.

Not exported, by explicit design decision: a `Query` marker type; a
query-level error/result-wrapper type; a dispatcher or runtime registry; any
shared base with `CommandHandler`.

## 19. Test Strategy for Future Implementation

A future implementation must add tests proving:

1. `mypy` accepts the `if TYPE_CHECKING:` structural-conformance check
   frozen in Section 6, inside `shared/contracts/query.py` itself.
2. `tests/unit/test_query_handler_typing.py` invokes the exact subprocess
   algorithm frozen in Section 15 against all five fixtures under
   `tests/typing_fixtures/query_handler/`, proving: the positive fixture
   passes cleanly; each of the four negative fixtures fails with the frozen
   `[assignment]` diagnostic fragment; and the canonical `mypy` gate is
   unaffected by the fixtures' existence.
3. A contravariant-input assignment and a covariant-output assignment both
   type-check cleanly.
4. A separate module-level import test proves `shared/contracts/query.py`
   imports cleanly with zero dependency beyond `typing`, and that only
   `QueryHandler` — not `_QueryT_contra`/`_QueryResultT_co` — is present in
   `shared/contracts/__init__.py`'s public export surface.
5. **Declared-relationship tests** (Section 9): `QueryHandler` does not
   inherit from `CommandHandler`; `CommandHandler` does not inherit from
   `QueryHandler`; no shared `Handler`/`RequestHandler` base class exists in
   the codebase; `shared/contracts/query.py` does not import
   `shared/contracts/command.py` (or `CommandHandler`); `shared/contracts/command.py`
   does not import `shared/contracts/query.py` (or `QueryHandler`).
6. **Structural-compatibility tests** (Section 9): a deliberately
   type-compatible concrete example class (defined for test purposes only)
   is accepted by `mypy` as satisfying *both* `CommandHandler[X, Y]` and
   `QueryHandler[X, Y]` for the same `X`/`Y` — documented in the test itself,
   via a comment or docstring, as an *expected* property of Python's
   structural typing, not a regression or defect to be fixed. A second
   example, using genuinely incompatible type arguments (e.g. assigning a
   handler typed for `X` to a `CommandHandler[Z, Y]` slot where `Z` is
   unrelated to `X`), must still be rejected by `mypy` — proving structural
   compatibility is conditional on actual type alignment, not universal.
7. **Read-only-limitation tests** (Section 10): the `QueryHandler` Protocol
   module exports no repository method, no transaction method, no
   decorator, and no runtime guard; importing
   `shared/contracts/query.py` has no side effect (no connection opened, no
   global state mutated); no docstring or comment anywhere in the module
   claims that non-mutation is mechanically guaranteed.
8. `tools/check_architecture.py .` reports zero violations with the new
   file present.
9. No existing M020-M027 test is affected.
10. `build` and package-metadata gates are unaffected.

## 20. Compatibility With M020 Through M027

No source file governed by M020 through M026 is modified by this design.
M027's frozen design (`CommandHandler`) is referenced only as a naming and
pattern precedent (Section 3) — no M027 source file (none exists yet) or
design document is modified. `QueryHandler` declares no code, import, or
inheritance relationship with `CommandHandler` (Section 9); Python's
structural typing may still consider a sufficiently-shaped concrete class
compatible with both, which this design explicitly does not attempt to
prevent (Section 9).

## 21. Deferred Work

Explicitly out of scope for M028:

- any concrete `Query` or `QueryHandler` implementation for any aggregate;
- any *declared* relationship, shared base, or unification with
  `CommandHandler` (structural compatibility, where type arguments happen
  to align, is not "in scope" to prevent — Section 9);
- a shared `Handler`/`RequestHandler` base Protocol;
- a nominal command/query class hierarchy;
- application service orchestration, transaction ownership decisions, or
  any wiring to `PostgresRepositoryRuntime`/`run_composed`;
- a query-level error hierarchy;
- a query bus, dispatcher, or runtime registry;
- read-only transaction enforcement, caching, pagination wrappers, or
  result envelopes of any kind (Section 10);
- retry semantics of any kind, including any command-vs-query distinction
  in retry behavior;
- APIs, workers, CLI entrypoints, or any change to `entrypoints/`;
- Audit runtime, Decision Candidate, Decision Freeze;
- market-data, vendor, trading, or campaign execution behavior;
- any named MILESTONE-029 work.

## 22. Acceptance Gate

The design is acceptance-ready only if it freezes, with no remaining
ambiguity:

1. the exact `QueryHandler[_QueryT_contra, _QueryResultT_co]` Protocol
   shape, with correct, verified variance — frozen, Section 6;
2. the exact package/file placement — frozen, Section 5;
3. the exact, justified decision not to freeze a `Query` marker or a
   query-level error type — frozen, Sections 4, 14;
4. the exact, honest declared-relationship-vs-structural-typing-reality
   distinction with respect to `CommandHandler`, with no overclaim of
   nominal or type-level non-interchangeability — frozen, Section 9;
5. the exact, honest limits of what `QueryHandler` can and cannot enforce
   about read-only behavior — frozen, Section 10;
6. the exact negative type-check strategy — frozen, Section 15;
7. the exact export surface — frozen, Section 18;
8. exact test obligations, including the declared-relationship,
   structural-compatibility, and read-only-limitation obligations — frozen,
   Section 19.

Both the MAJOR finding (structural interchangeability) and the MINOR
finding (read-only semantics) from the narrow-correction review are
resolved by this Version 1.1; no acceptance-gate item remains open.

## 23. Rejected Alternatives

1. **Freeze a separate, empty `Query` Protocol as a marker type.** Rejected
   for the identical reason M027 rejected a `Command` marker (Section 4).
2. **Freeze a query-level error hierarchy now.** Rejected for the identical
   reason M027 rejected a handler-level error hierarchy (Section 14).
3. **Unify `QueryHandler` and `CommandHandler` under a shared
   `Handler[InputT, OutputT]` base now.** Rejected: no concrete
   implementation of either yet exists to reveal whether unification has
   real value; premature unification risks freezing the wrong abstraction.
   Deferred explicitly (Section 21) rather than decided either way.
4. **Add a `@runtime_checkable` decorator.** Rejected for the identical
   reason M027 rejected one (Section 6).
5. **Place the new contract in a new top-level `application` package.**
   Rejected for the identical reason M027 rejected this.
6. **Re-run the full `mypy` variance experiment from scratch for
   `QueryHandler`.** Rejected as unnecessary: the shape is structurally
   identical to `CommandHandler`'s verified case (Section 6).
7. **Introduce a nominal marker field or sentinel attribute purely to make
   `QueryHandler` and `CommandHandler` structurally incompatible.**
   Rejected (Version 1.1, new): fighting Python's own structural type
   system for no functional benefit would complicate the Protocol shape
   beyond what any real caller needs, and would not actually prevent
   deliberate misuse by an author determined to satisfy both Protocols —
   it would only add friction for legitimate, accidental structural
   overlap. Semantic separation is enforced by naming, placement, and
   review (Section 9), not by type-system trickery.
8. **Add a read-only transaction mode, decorator, or runtime guard to
   enforce non-mutation.** Rejected (Version 1.1, new): this milestone
   freezes vocabulary only; any enforcement mechanism belongs to a future,
   separate milestone that can make an informed decision once concrete
   query handlers exist to enforce it against (Section 10).

## 24. Risk Register

| Risk | Mitigation |
| --- | --- |
| A future implementer conflates this Protocol with "application services already exist" | Sections 7/8/11/12 each explicitly state no ownership, call direction, transaction, or repository interaction is introduced |
| A future implementer re-introduces invariant `TypeVar`s | Section 6 cites the exact, already-verified `mypy` error text for the structurally identical `CommandHandler` case |
| Negative fixtures accidentally pollute the canonical `mypy` gate or get collected by pytest | Section 15 freezes the identical, already-verified safeguards M027 established |
| A future reader assumes `QueryHandler` and `CommandHandler` are nominally or structurally guaranteed incompatible | Section 9 freezes the precise, verified truth and Section 19 Item 6 makes the structural-compatibility case an explicit, named test obligation rather than a surprise |
| A future implementer or reviewer assumes a "query handler" is mechanically prevented from mutating state | Section 10 freezes the precise limits of what the Protocol can and cannot enforce, and names exactly where real enforcement must live instead |
| A future implementer adds a nominal marker to "fix" structural overlap, reintroducing exactly the anti-pattern this correction round rejected | Section 23 Item 7 names this exact temptation and its rejection reasoning |

## 25. Version 1.1 Independent Review Correction Record

An independent hostile review of Version 1.0 of this design returned:

```text
M028 DESIGN REQUIRES NARROW CORRECTION
```

Exactly one MAJOR finding and one MINOR finding were returned.

**Finding 1 (MAJOR — structural interchangeability):** Version 1.0 stated
`QueryHandler` and `CommandHandler` are "fully independent... at the type
level" and share "no type relationship." This overstated the truth: direct
`mypy --strict` experimentation performed during this correction round
proved a single concrete class can structurally satisfy both Protocols
simultaneously when its parameter/return types align with both. Corrected
by rewriting Section 9 to distinguish the declared relationship (no
inheritance, import, alias, or shared base — all still true and frozen)
from the structural-typing reality (Python's `Protocol` system does not,
and this design does not attempt to, prevent structural compatibility when
types align), and by adding explicit test obligations (Section 19 Items 5-6)
proving both the declared-relationship facts and the structural-compatibility
behavior.

**Finding 2 (MINOR — read-only semantics):** Version 1.0 described queries
as "state-reading" without stating plainly that the Protocol cannot enforce
this. Corrected by adding Section 10 (Read-Only Semantics), a dedicated
section freezing exactly what `QueryHandler` can and cannot guarantee about
mutation, and naming exactly where real enforcement must eventually live
(a future, separate milestone) rather than being smuggled into this one.

No canonical Version 1.0 decision was reopened, reversed, or reinterpreted:
the field name/type/position, the `isinstance`-free pure-Protocol shape, the
variance direction, the package placement, the export surface, and the
decision not to freeze a `Query` marker or error hierarchy are all
unchanged. Both corrections document and test already-true (or now
explicitly-decided-against) properties; neither required a new mechanism,
a new field, or a change to the frozen Protocol's method shape.

### 25.1 Hostile Self-Review of the Correction

1. **Does the corrected design still claim structural incompatibility
   anywhere?** No — a full sweep for "fully independent," "no type
   relationship," and "interchang-" (as a stem) was performed across this
   document during the correction; every remaining use of "independent" or
   "no relationship" in Sections 7-9, 20-21 refers only to the *declared*
   relationship (no import/inheritance/shared base), immediately adjacent
   to or cross-referencing Section 9's explicit structural-typing-reality
   paragraph.
2. **Could a future implementer still misread this as claiming type-level
   isolation?** Unlikely: Section 9 is titled to name both halves
   explicitly ("Declared Relationship and Structural-Typing Reality") and
   states the verified `mypy` behavior in the same breath as the declared
   facts, rather than in a separate, easy-to-skip section.
3. **Does the correction accidentally introduce a shared base or import
   between the two Protocols?** No — Section 8 and Section 9's "declared
   relationship" list are unchanged from Version 1.0 in substance (only in
   precision of the surrounding claims); no new import or base was added.
4. **Does the correction accidentally suggest a nominal marker should be
   added to prevent structural overlap?** No — Section 23 Item 7 explicitly
   rejects this, naming the exact temptation and why it would be
   counterproductive.
5. **Does the read-only correction accidentally introduce enforcement code
   or a runtime guard?** No — Section 10 explicitly freezes that no such
   mechanism is introduced by this milestone, and Section 23 Item 8 rejects
   adding one now.
6. **Does the read-only correction leave any documentation claim implying
   mechanical guarantee?** No — a full sweep for "read-only," "state-
   reading," and "non-mutation" across this document confirms every use is
   now paired with an explicit "not mechanically enforced" qualifier
   (Sections 2, 9's application-layer-value-type mention, 10, 11).
7. **Does this correction leak into M029?** No — Sections 21's deferred
   list is unchanged in kind; nothing here presumes or requires any named
   future milestone.

### 25.2 Both Findings Resolved

- Finding 1 resolved: Section 9 (rewritten), Section 19 Items 5-6 (new),
  Section 22 Item 4 (new), Section 23 Item 7 (new), Section 24 (new risk
  row).
- Finding 2 resolved: Section 10 (new), Section 19 Item 7 (new), Section 22
  Item 5 (new), Section 23 Item 8 (new), Section 24 (new risk row).

## 26. Hostile Self-Review

1. **Does this quietly become "application services"?** No — identical
   reasoning to M027 Design Section 23 Item 1.
2. **Does this presume a specific dispatch or bus mechanism?** No.
3. **Does this leak into transaction ownership?** No — Section 11.
4. **Does this leak into repository/runtime access?** No — Section 12.
5. **Does this leak into APIs/workers?** No — Section 8.
6. **Does this leak into retry policy?** No — Section 21 explicitly defers
   it.
7. **Is the "no error taxonomy" decision actually justified, or just
   avoidance?** Justified — identical reasoning to M027 (Section 14).
8. **Does this leak into M029?** No — Section 21's deferred list presumes
   no named future milestone.
9. **Is the variance direction actually correct, or just copy-pasted
   without verification?** Verified by structural equivalence (Section 6).
10. **Do the negative fixtures actually fail for the intended reason?**
    Guarded identically to M027 — a positive `ok_handler.py` fixture proves
    the invocation mechanism itself works.
11. **Could the negative fixtures pollute the canonical `mypy` gate or leak
    into pytest collection?** No — identical, already-verified safeguards
    (Section 15).
12. **Are the `TypeVar`s at risk of accidental public exposure?** No —
    Section 18 freezes leading-underscore naming and an explicit test
    obligation (Section 19 Item 4).
13. **Does async behavior get overclaimed anywhere?** No — Section 6
    explicitly freezes `handle` as synchronous.
14. **Does this claim `QueryHandler` and `CommandHandler` are structurally
    incompatible, when they are not?** No — Section 9 freezes the precise,
    verified truth: no *declared* relationship exists, but structural
    compatibility is possible and not prevented, by design.
15. **Does this claim read-only behavior is mechanically enforced, when it
    is not?** No — Section 10 explicitly freezes the opposite: intent only,
    no enforcement, no runtime guard.
16. **Is a nominal marker class hiding anywhere as a disguised attempt to
    block structural matching?** No — no marker type of any kind is
    frozen in this design (Section 4, Section 23 Item 7).

## 27. Final Status

```text
M028 DESIGN NARROW CORRECTION COMPLETE
READY FOR FINAL INDEPENDENT RE-REVIEW
NOT APPROVED
NOT FROZEN
M028 IMPLEMENTATION NOT STARTED
```

Do not implement source code. Do not start M029.
