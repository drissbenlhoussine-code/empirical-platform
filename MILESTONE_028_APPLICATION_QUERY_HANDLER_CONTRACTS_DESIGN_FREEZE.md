# MILESTONE-028 - Application Query/QueryHandler Contracts Design Freeze

## 1. Document Control

| Field | Value |
| --- | --- |
| Document ID | MILESTONE-028-DESIGN-FREEZE |
| Title | Application Query/QueryHandler Contracts Design Freeze |
| Status | M028 DESIGN APPROVED AND FROZEN |
| Repository | `C:\Users\LuxSy\Documents\trading` |
| Mission type | Freeze closure only |
| New source code, tests, or runtime changes made by this closure | No |

## 2. Authority Chain

| Role | Commit | Summary |
| --- | --- | --- |
| Initial Design | `db99194277aecef7b5a5c74f576a940d6e24e399` | Design MILESTONE-028 Application Query/QueryHandler Contracts |
| Design Correction | `bff0865f7f2495b1854a86d04c0db66ecb0512b1` | Harden MILESTONE-028 Application Query/QueryHandler Contracts design |

Independent review outcomes:

1. Independent hostile review of the initial design (`db99194`) found one MAJOR finding — the document overstated that `QueryHandler` and `CommandHandler` are "fully independent... at the type level" and share "no type relationship," when Python's structural `Protocol` typing can accept one concrete class as satisfying both simultaneously when parameter/return types align (verified directly against the project's own `mypy --strict` configuration) — and one MINOR finding — the document described queries as "state-reading" without stating plainly that `QueryHandler` cannot mechanically enforce that property. Recommendation: `M028 DESIGN REQUIRES NARROW CORRECTION`.
2. The Project Owner authorized a narrow correction addressing exactly those two findings. Commit `bff0865` rewrote Section 9 to distinguish the *declared* relationship (no inheritance, import, alias, or shared base — verified unchanged and still true) from the *structural-typing reality* (a single concrete class can satisfy both Protocols when types align; this design does not attempt to prevent that), backed by direct `mypy` experimentation proving both the compatible case and the correctly-rejected incompatible case; and added Section 10 (Read-Only Semantics), freezing the exact, honest limits of what `QueryHandler` can and cannot enforce about mutation. No canonical Version 1.0 decision — field shape, variance, package placement, export surface, or the decisions not to freeze a `Query` marker or error hierarchy — was reopened or reversed.
3. The Project Owner's decision, accepted in this mission's authorization, is:

```text
M028 DESIGN APPROVED FOR OWNER FREEZE
```

Authoritative documents for this freeze:

- `MILESTONE_028_APPLICATION_QUERY_HANDLER_CONTRACTS_SCOPE_SELECTION.md`;
- `MILESTONE_028_APPLICATION_QUERY_HANDLER_CONTRACTS_DESIGN.md` (Version 1.1);
- `PROJECT_CHECKPOINT.md` (M028 review-status fields, updated separately per Phase 3).

Frozen baseline this design built on: MILESTONE-027 design freeze commit `64abc16156b949491ded4ff239d2c249aac569a8`. That freeze is not reopened, rewritten, or reinterpreted by this closure. (MILESTONE-027 *implementation* has since separately proceeded to commit `c7bc632a1568203f33635191ea70b4e5784e1d86`, on a parallel track authorized by a separate Owner decision — this freeze does not depend on, and is not affected by, that implementation's status.)

## 3. Canonical Frozen Decisions

The following are frozen exactly as specified by the corrected Version 1.1 design and may not be reinterpreted or redesigned during implementation without a fresh design correction:

1. Exactly one Protocol is frozen:

   ```python
   _QueryT_contra = TypeVar("_QueryT_contra", contravariant=True)
   _QueryResultT_co = TypeVar("_QueryResultT_co", covariant=True)


   class QueryHandler(Protocol[_QueryT_contra, _QueryResultT_co]):
       def handle(self, query: _QueryT_contra) -> _QueryResultT_co: ...
   ```

   in `src/empirical_platform/shared/contracts/query.py`, exported as
   `QueryHandler` from `shared/contracts/__init__.py`.
2. `handle` is synchronous, exactly one method, exactly one positional parameter named `query`, no keyword-only requirement, no `@runtime_checkable`.
3. `_QueryT_contra`/`_QueryResultT_co` are module-private (leading underscore); only `QueryHandler` is a public export.
4. No `Query` marker Protocol, no query-level error/result-wrapper type, no dispatcher, no runtime registry.
5. **Declared relationship to `CommandHandler`**: no inheritance, no import (in either direction), no alias, no shared base, no common `TypeVar`, no nominal runtime relationship, no dispatcher/registry relationship — `shared/contracts/query.py` imports only the standard library `typing` module.
6. **Structural-typing reality, frozen as an explicit, non-overclaiming fact**: Python's structural `Protocol` typing means one concrete class can satisfy both `CommandHandler[X, Y]` and `QueryHandler[X, Y]` simultaneously when its `handle` method's actual parameter/return types align with both; this is not prevented, and no nominal marker or sentinel field is introduced to defeat it. Genuinely mismatched type arguments are still correctly rejected by `mypy` — structural compatibility is conditional on real type alignment, not universal or automatic.
7. **Read-only semantics, frozen as an explicit, non-overclaiming fact**: `QueryHandler` expresses read-side intent and vocabulary only. It cannot inspect a `handle` implementation's body, cannot prevent a concrete handler from calling mutating repository methods, and cannot enforce a read-only transaction mode, cache-only access, or absence of side effects. No read-only transaction mode, session type, or persistence abstraction is introduced by this milestone. Real non-mutation enforcement belongs to future, separate work (a future concrete-handler milestone, architecture review, a repository-access/transaction-policy milestone, or per-handler tests).
8. A positive, zero-runtime-cost `if TYPE_CHECKING:` structural-conformance proof lives inside `shared/contracts/query.py` itself, checked automatically by the canonical `mypy` gate (scoped to `src/` only).
9. Malformed handler shapes must be mechanically proven rejected via isolated negative typing fixtures under `tests/typing_fixtures/query_handler/` (`ok_handler.py` plus four negative fixtures), checked by a dedicated `tests/unit/test_query_handler_typing.py` invoking `mypy` as a subprocess with an explicit `--config-file` — never added to `[tool.mypy] packages`, and never collected by pytest as test modules.
10. No new top-level package; no `tools/check_architecture.py` change; no M020-M027 source file is touched.

## 4. Accepted Non-Blocking Observations

Carried forward explicitly, not silently:

1. `mypy` does not type-check `tests/` under the current project configuration — this is precisely why the positive conformance proof lives inside the module itself.
2. The negative-fixture mechanism introduces one additional, narrowly-scoped `mypy` subprocess invocation per fixture at test time; bounded (five fixtures, one dedicated test file); does not affect the canonical gate's scope.
3. `setuptools` emits a non-blocking `project.license` TOML-table deprecation warning during `python -m build`; tracked for a future packaging cleanup, unrelated to M028.
4. This milestone introduces no concrete query or handler; "Application Service Orchestration" remains a distinct, larger, still-premature future candidate that this milestone's contracts merely unblock.
5. A future implementer may deliberately (or accidentally) write a concrete class satisfying both `CommandHandler` and `QueryHandler`; this is a disclosed, expected property of Python's structural typing (Section 3, Item 6), not a defect — semantic separation is a naming/review/application-layer concern, not a type-system one.
6. `QueryHandler` naming a handler as "read side" is documentation of intent only; nothing in this milestone mechanically prevents a mislabeled handler from mutating state (Section 3, Item 7).

## 5. What This Freeze Does Not Authorize

Freezing the M028 design does not authorize:

- any implementation deviating from Section 3's canonical decisions without a fresh design correction;
- any concrete `Query`/`QueryHandler` implementation for any aggregate;
- a shared `Handler`/`RequestHandler` base with `CommandHandler`, or any nominal marker introduced to defeat structural compatibility;
- application service orchestration, transaction ownership decisions, or any wiring to `PostgresRepositoryRuntime`/`run_composed`;
- a query-level error hierarchy, a query bus, a dispatcher, or a runtime registry;
- read-only transaction enforcement, caching, pagination wrappers, or result envelopes;
- retry semantics of any kind;
- APIs, workers, CLI entrypoints, or any change to `entrypoints/`;
- Audit runtime, Decision Candidate, or Decision Freeze;
- market-data, vendor, trading, or campaign execution behavior;
- MILESTONE-029 work of any kind;
- MILESTONE-028 *implementation* — that remains a separate, later gate, and additionally may not begin until MILESTONE-027 implementation is independently reviewed, approved, frozen, and pushed (an explicit Owner sequencing decision, not a type-level dependency — Design Section 3/9).

## 6. Final Status

```text
M028 DESIGN APPROVED AND FROZEN
```

Implementation may proceed strictly within the boundaries frozen in Section 3, subject to its own independent review, approval, and freeze, and subject to MILESTONE-027 implementation being independently reviewed, approved, frozen, and pushed first.
