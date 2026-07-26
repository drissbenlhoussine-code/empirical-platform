# MILESTONE-024 - Multi-Aggregate Persistence Unit of Work Design

## 1. Document Control

| Field | Value |
| --- | --- |
| Document ID | MILESTONE-024-DESIGN |
| Title | Multi-Aggregate Persistence Unit of Work Design |
| Version | 1.0 |
| Status | DESIGN READY FOR INDEPENDENT REVIEW |
| Repository | `C:\Users\LuxSy\Documents\trading` |
| Frozen baseline | `4ce800d3609ba7c621eadffc338bc5bc2503228d` (MILESTONE-023 APPROVED AND FROZEN) |
| Mission type | Design only |
| Source code, migrations, repository adapters modified | No |

## 2. Baseline

Verified live against the frozen M023 state:

- `src/empirical_platform/shared/persistence/postgres.py` defines `PostgresPersistenceService.unit_of_work() -> PostgresUnitOfWork`, which unconditionally constructs `PostgresUnitOfWork(self)` and returns it, un-entered;
- `PostgresUnitOfWork.__enter__` checks a module-level `_active_unit_of_work: ContextVar[bool]` (default `False`); if already `True`, raises `FoundationError(message="Nested persistence units of work are not supported")`; otherwise sets it to `True`, opens a real SQLAlchemy `Connection` and begins a transaction;
- `PostgresUnitOfWork.__exit__` commits on success or rolls back on exception (via `commit()`/`rollback()`), then `_complete()` closes the connection and resets the ContextVar via `_reset_context()`;
- `execute()` binds named parameters via SQLAlchemy's `text()` and returns `list[dict[str, object]]` (or `[]` for non-row-returning statements);
- all four M023 concrete repository adapters (`PostgresCampaignRepository`, `PostgresRunRepository`, `PostgresEvidencePackageRepository`, `PostgresReviewRepository`) call `with self._service.unit_of_work() as work:` exactly once per `get`/`add`/`save` invocation, and construct their return value (`LoadedAggregate` or `SaveResult`) only after that `with` block exits without exception — i.e., after a successful commit;
- the frozen M020 Repository Protocols (`get(identity)` / `add(aggregate)` / `save(aggregate, *, expected_persisted_version)`) take no session, transaction, or Unit-of-Work parameter anywhere;
- no application service, runtime composition root, or dependency-injection container exists anywhere in the repository.

## 3. Problem Statement

A caller today cannot compose two repository operations — whether on the same aggregate repository or across different aggregate repositories — into one atomic transaction. Calling a second repository operation while a first is still open (e.g. nesting `with campaign_repo... :` inside `with run_repo...:`) raises `FoundationError` by design (M023 Design Section 11 point 5), because each operation unconditionally opens its own `PostgresUnitOfWork` and the reentrancy guard forbids more than one being active at once.

This design defines a composition primitive that lets a caller group multiple repository operations into one atomic transaction, without changing the M020 Repository Protocol surface and without changing any M023 concrete repository adapter's source code.

## 4. Design Principles

1. **The M020 Repository Protocol surface is immutable.** `get`/`add`/`save` accept exactly the parameters they accept today. No session, transaction, or Unit-of-Work object is ever passed to or returned from a repository method.
2. **No M023 concrete repository adapter file changes.** All four adapters keep calling `with self._service.unit_of_work() as work:` exactly as written today. The composition mechanism is invisible to them.
3. **Single-operation behavior is unchanged when no composed scope is open.** Every M023 test that exercises `get`/`add`/`save` in isolation must continue to pass unmodified — this design adds a capability, it does not alter existing behavior.
4. **Only the new, explicit composition primitive enables joining.** A caller who nests two `with service.unit_of_work():` blocks *without* using the new primitive still gets today's exact `FoundationError` — the reentrancy guard's default-forbidding behavior is preserved for anyone not opting in.
5. **Exactly one real transaction backs a composed scope.** However many repository operations run inside it, there is one SQLAlchemy connection, one transaction, one commit or one rollback, owned exclusively by the outermost composed scope.

## 5. Composition Primitive Shape

A new class, `PostgresComposedUnitOfWork`, added to `src/empirical_platform/shared/persistence/postgres.py` (same module as `PostgresUnitOfWork`; no new top-level package, no architecture-checker change required — see Section 13):

```python
class PostgresComposedUnitOfWork:
    """Groups multiple repository operations into one atomic transaction."""

    def __init__(self, service: PostgresPersistenceService) -> None: ...
    def __enter__(self) -> PostgresComposedUnitOfWork: ...
    def __exit__(self, exc_type, exc, traceback) -> Literal[False]: ...
```

`service.composed_unit_of_work()` is the one new public method added to `PostgresPersistenceService`, mirroring the existing `unit_of_work()` factory:

```python
def composed_unit_of_work(self) -> PostgresComposedUnitOfWork:
    """Create a bounded scope multiple repository operations can join."""
    self._ensure_can_work("composed_unit_of_work")
    return PostgresComposedUnitOfWork(self)
```

Usage by a future caller (an application service or script — not designed here, see Section 19):

```python
with service.composed_unit_of_work():
    campaign_repo.save(campaign, expected_persisted_version=v1)
    run_repo.add(run)
# both persisted atomically, or neither is, on any exception
```

## 6. Ambient-Scope Join Mechanism

A second module-level `ContextVar` is added, holding the active real unit of work rather than a bare boolean:

```python
_active_composed_scope: ContextVar[PostgresUnitOfWork | None] = ContextVar(
    "active_persistence_composed_scope", default=None
)
```

`PostgresComposedUnitOfWork.__enter__`:

1. constructs `PostgresUnitOfWork(self._service)` **directly** (never through `self._service.unit_of_work()`, the public factory — see the boxed warning below) and enters it (`.__enter__()`) — this goes through the *existing, unmodified* reentrancy check against `_active_unit_of_work` in `PostgresUnitOfWork.__enter__` itself, so a composed scope cannot be opened while an ordinary (non-composed) unit of work, or another composed scope, is already active — both draw from the exact same guard;
2. stores the now-open `PostgresUnitOfWork` instance in `_active_composed_scope`.

> **Why not call `self._service.unit_of_work()` in step 1:** that public factory is the one gaining the new join-check branch (below). If `PostgresComposedUnitOfWork.__enter__` called it, opening a *second* composed scope while the first is still active would incorrectly find `_active_composed_scope` already populated and silently *join* the first scope's transaction instead of raising — directly contradicting Section 7's stated rule that nested composed scopes must raise, not stack. Constructing `PostgresUnitOfWork` directly bypasses the join branch entirely and forces every composed-scope entry through the one, unmodified `_active_unit_of_work` reentrancy check, which has no notion of "composed" at all and simply refuses any second concurrent unit of work regardless of kind.

`PostgresComposedUnitOfWork.__exit__`:

1. delegates directly to the real `PostgresUnitOfWork.__exit__` it opened in step 1 (commit on `exc_type is None`, else rollback) — this is the *only* place `commit()`/`rollback()` is called for anything that happened inside the composed scope;
2. resets `_active_composed_scope` back to `None`.

`PostgresPersistenceService.unit_of_work()` gains exactly one new branch, checked first:

```python
def unit_of_work(self) -> PostgresUnitOfWork:
    self._ensure_can_work("unit_of_work")
    joined = _active_composed_scope.get()
    if joined is not None:
        return _JoinedUnitOfWork(joined)
    return PostgresUnitOfWork(self)
```

`_JoinedUnitOfWork` is a thin, private wrapper (same `execute`/`commit`/`rollback`/`__enter__`/`__exit__` shape as `PostgresUnitOfWork`, satisfying the same `PersistenceUnitOfWork` Protocol) that:

- `__enter__`: does **not** touch `_active_unit_of_work` (the real, already-open `PostgresUnitOfWork` already holds it) and does **not** open a new connection — it simply returns itself;
- `execute(...)`: forwards directly to the joined real `PostgresUnitOfWork.execute(...)`, so all statements from every joined operation run against the *same* connection and transaction;
- `commit()` / `rollback()`: **no-ops.** Ownership of the real transaction belongs exclusively to the `PostgresComposedUnitOfWork` that opened it;
- `__exit__`: **no-op**, always returns `False` (never suppresses an exception) — an exception raised by the repository operation using this joined handle propagates unmodified, out through the composed scope's own `with` block, triggering the real `PostgresUnitOfWork.rollback()` in `PostgresComposedUnitOfWork.__exit__`.

Because `PostgresCampaignRepository`/`PostgresRunRepository`/`PostgresEvidencePackageRepository`/`PostgresReviewRepository` only ever call `self._service.unit_of_work()` and use it via `with ... as work:` — never inspecting its concrete type — every one of the four adapters participates in a composed scope correctly with **zero source changes**, satisfying Design Principle 2 exactly.

## 7. Nesting and Reentrancy Semantics

| Caller sequence | Behavior |
| --- | --- |
| `service.unit_of_work()` used alone (today's only pattern) | Unchanged: opens and closes exactly as in M023. |
| `service.unit_of_work()` nested inside another `service.unit_of_work()`, **without** a composed scope | Unchanged: raises `FoundationError("Nested persistence units of work are not supported")`, exactly as M023 froze it. |
| `service.composed_unit_of_work()` opened, then one or more `service.unit_of_work()` calls made while it is open | Each such call transparently joins (Section 6); no error. |
| `service.composed_unit_of_work()` opened while another `service.composed_unit_of_work()` (or a plain `service.unit_of_work()`) is already open | Raises `FoundationError("Nested persistence units of work are not supported")` — `PostgresComposedUnitOfWork.__enter__`'s own call to `service.unit_of_work()` hits the same, unmodified `PostgresUnitOfWork.__enter__` reentrancy check as any other nested attempt. Composed scopes do not stack; exactly one may be active at a time. |
| `service.unit_of_work()` called with **no** composed scope active (the overwhelming common case, including every existing M023 test) | Unchanged: `_active_composed_scope.get()` returns `None`, so a fresh `PostgresUnitOfWork` is created exactly as today. |

## 8. Return-Value Semantics Inside a Composed Transaction

M023 froze commit-before-return: a repository's `LoadedAggregate`/`SaveResult` is constructed only after its own `with self._service.unit_of_work() as work:` block exits without exception — which M023 correctly equates with "after a successful commit," because in M023's world that block's `__exit__` *is* the commit.

Inside a composed scope, that equivalence changes, and this design states the change explicitly rather than leaving it implicit: a repository operation's own inner `with` block exits (returning control to the repository method, which then constructs and returns its `SaveResult`/`LoadedAggregate`) as soon as its statements have executed against the shared connection — **before** the outer `PostgresComposedUnitOfWork` commits. The individual operation's return value is therefore available before the data is durably committed; only the composed scope's own exit durably commits (or rolls back) everything that happened inside it, including operations whose own return values were already produced.

This is a deliberate, disclosed relaxation scoped **only** to operations invoked while a composed scope is active — standalone M023 behavior (Section 7, no composed scope active) is completely unaffected, and commit-before-return remains exactly true for it. A caller composing multiple operations already knows, by using `composed_unit_of_work()` at all, that atomicity spans the whole block; this design does not attempt to hide that from them by fabricating a false "already durable" guarantee per inner call.

## 9. Cross-Aggregate Worked Example

Demonstrating the primitive composes a genuine two-aggregate transaction (Section 11 of the Scope Selection requires at least one concrete example):

```python
campaign_repo = PostgresCampaignRepository(service)
run_repo = PostgresRunRepository(service)

loaded_campaign = campaign_repo.get(campaign_identity)
campaign = loaded_campaign.aggregate
campaign.activate(actor="ops", occurred_at=now)

new_run = Run(identity=run_identity, campaign_id=campaign_identity.governance_id)

with service.composed_unit_of_work():
    campaign_repo.save(campaign, expected_persisted_version=loaded_campaign.persisted_version)
    run_repo.add(new_run)
# Campaign's activation and the new Run's creation commit together, or neither does.
```

If `run_repo.add(new_run)` raises `AggregateAlreadyExists` (a duplicate governance_id, say), the exception propagates out of the `with service.composed_unit_of_work():` block unmodified, `PostgresComposedUnitOfWork.__exit__` rolls back the single shared transaction, and the `Campaign`'s `save()` — despite having already returned a `SaveResult` moments earlier — is **not** durably committed. This is the direct, concrete consequence of Section 8's disclosed semantics, demonstrated end-to-end.

## 10. Error Translation

Unchanged from M023 (Section 9): SQLSTATE + constraint-name based translation, never parsed message text. A failure on any joined operation surfaces through that operation's own existing error-translation path (each repository adapter's own `except FoundationError` / diagnostic-query logic, untouched by this design) exactly as it would standalone; the only difference is that the transaction rolled back as a side effect is the shared one, not a dedicated one.

## 11. Architecture Enforcement

`PostgresComposedUnitOfWork`, `_JoinedUnitOfWork`, and `_active_composed_scope` all live in `src/empirical_platform/shared/persistence/postgres.py` — the same module as the existing `PostgresUnitOfWork` and `PostgresPersistenceService`. `ALLOWED["shared"]` already permits everything this design needs (it was last widened by M023 to include `identifiers`, unrelated to this change). No entry in `ALLOWED` or `FORBIDDEN_IMPORT_PREFIXES` requires modification. Running `tools/check_architecture.py .` against a repository with this design implemented is expected to report the same 0 violations as today, since no new cross-package import is introduced anywhere.

## 12. Security Considerations

No new credential handling, connection-string construction, or secret storage. `execute()`'s existing parameter-binding behavior (`text()` + named parameters) is unchanged and reused unmodified by every joined operation. A composed scope does hold one connection open for the duration of every operation nested inside it, which is longer than any single M023 operation holds one today; this design sets an explicit constraint for a future implementation: a composed scope's total held-open duration should be bounded by ordinary application-level operation counts (a handful of repository calls), never by long-running or unbounded loops, and a future implementation milestone must not use `composed_unit_of_work()` to wrap anything resembling batch/bulk processing without revisiting this constraint.

## 13. Test Strategy (for a future Implementation milestone)

- two-repository-operation atomic commit against real PostgreSQL (e.g. the Section 9 worked example, both rows verified present after commit);
- two-repository-operation atomic rollback when the second operation fails (verify neither row is present after the composed scope exits with an exception);
- every existing M023 single-operation test continues to pass completely unmodified (regression proof that Section 7's "no composed scope active" row is real, not aspirational);
- nested `composed_unit_of_work()`-while-already-open raises `FoundationError`, matching Section 7's stated behavior;
- a composed scope opened while an ordinary `unit_of_work()` is already open (and vice versa) raises `FoundationError`, matching Section 7;
- a composed transaction where the *first* operation's own optimistic-concurrency guard fails (`OptimisticConcurrencyConflict`) still rolls back cleanly and leaves no partial state, even though no SQL from the second, never-reached operation ever executed.

## 14. Compatibility with M019 through M023

No frozen M019 reconstruction rule, M020 Repository Protocol, M021 Mapper Protocol, or M022 schema is touched. No M023 concrete repository adapter source file is modified — the four classes remain byte-for-byte as frozen. The one behavioral extension (Section 6) is additive and inactive by default: with no composed scope ever opened, `PostgresPersistenceService.unit_of_work()` takes the exact same code path it does today (`_active_composed_scope.get()` returns `None` unconditionally, falling through to `return PostgresUnitOfWork(self)`), and `PostgresUnitOfWork.__enter__`/`__exit__`'s own logic is not modified at all.

## 15. Explicit Non-Goals

This design does not:

- change any M020 Repository Protocol signature;
- modify any M023 concrete repository adapter's source code;
- design how a caller obtains repository instances (Candidate E, repository runtime composition — independent, deferred);
- design an application service or use-case orchestration layer (Candidate F — deferred, depends on this milestone and Candidate E);
- design retry-on-`OptimisticConcurrencyConflict` policy (Candidate J — deferred, depends on Candidate F);
- introduce a generic/shared concrete repository or mapper base class;
- touch APIs, workers, Audit, Decision Candidate, Decision Freeze, trading, vendor, or empirical execution behavior.

## 16. Deferred Work

- the actual implementation of `PostgresComposedUnitOfWork`, `_JoinedUnitOfWork`, `_active_composed_scope`, and `PostgresPersistenceService.composed_unit_of_work()` (this milestone is design-only);
- repository runtime composition (Candidate E);
- application services (Candidate F);
- service-level optimistic-concurrency retry policy (Candidate J);
- any MILESTONE-025 work.

## 17. Hostile Self-Review

| ID | Severity | Section | Finding | Evidence | Impact | Correction | Disposition |
| --- | --- | --- | --- | --- | --- | --- | --- |
| M024-DESIGN-ISSUE-0001 | MAJOR | 8 | Initial framing risked implying commit-before-return still holds per-operation inside a composed scope, which would be false and would mislead a future implementer into writing code that assumes early durability. | Traced the exact mechanics: a joined operation's own `with` block exits (and its `SaveResult` is constructed) as soon as its own statements run, before the outer composed scope's real commit. | A future implementer relying on an implied per-operation durability guarantee inside a composed transaction could ship a defect where a caller acts on a `SaveResult` before the data is actually durable. | Made Section 8 an explicit, named section stating the relaxation precisely, scoped only to composed-scope participants, and added the Section 9 worked example demonstrating a `SaveResult` existing for data that is then rolled back. | Resolved |
| M024-DESIGN-ISSUE-0002 | MAJOR | 6 | Considered making `_active_unit_of_work` itself hold the real `PostgresUnitOfWork` (removing the separate boolean ContextVar) rather than adding a second `_active_composed_scope` ContextVar, to "simplify" the primitive. | Doing so would mean *any* nested `unit_of_work()` call (not just ones inside an explicit `composed_unit_of_work()`) could silently join an ambient scope, contradicting Design Principle 4 (only the new, explicit primitive enables joining) and turning every existing nested-call error case into silent, unintended composition. | Would have silently changed M023's frozen reentrancy-rejection behavior for ordinary callers who never opted into composition — a real regression, not an enhancement. | Kept the two ContextVars separate: `_active_unit_of_work` (boolean, existing, unmodified, governs raw reentrancy) and `_active_composed_scope` (new, holds the real UoW, consulted only by the new join branch in `unit_of_work()`). Ordinary nested calls still raise exactly as before; only calls made *underneath* an open `composed_unit_of_work()` ever see `_active_composed_scope` populated. | Resolved |
| M024-DESIGN-ISSUE-0003 | MINOR | 11 | Needed to confirm directly, rather than assume, that no `ALLOWED`/`FORBIDDEN_IMPORT_PREFIXES` change is required, since the new primitive touches transaction internals. | Re-read `tools/check_architecture.py` live: `shared.persistence.postgres` is already the module `PostgresUnitOfWork`/`PostgresPersistenceService` live in today; adding new classes to the same file introduces no new cross-package import anywhere. | Low; would have been an unverified assumption otherwise. | Stated the "0 violations expected" claim in Section 11 only after confirming no import boundary changes. | Resolved |
| M024-DESIGN-ISSUE-0004 | MINOR | 6 | Considered whether `_JoinedUnitOfWork`'s `execute()` needs its own error translation, duplicating `PostgresUnitOfWork.execute()`'s existing `try/except`. | It does not: `_JoinedUnitOfWork.execute()` forwards directly to the real `PostgresUnitOfWork.execute()`, which already performs `translate_persistence_error()` itself; duplicating it would risk a double-wrapped `FoundationError`. | Low; would have been redundant, potentially confusing error-wrapping otherwise. | Section 6 specifies "forwards directly," not "re-implements," making the delegation (not duplication) explicit. | Resolved |

| M024-DESIGN-ISSUE-0005 | MAJOR | 6, 7 | A separate, later hostile-review pass (attacking specifically for "nested transaction ambiguity") found that having `PostgresComposedUnitOfWork.__enter__` open its real unit of work by calling the public `self._service.unit_of_work()` factory would recursively hit that same method's new join-check branch, meaning a *second* composed scope opened while the first was still active would incorrectly find `_active_composed_scope` already populated and silently join rather than raise — directly contradicting Section 7's own stated table row for that exact case. | Traced the call path step by step for the "composed nested inside composed" row of Section 7's table against the mechanism as originally drafted. | Would have silently produced two composed scopes sharing one transaction with no error, an incorrect and untested-for behavior a future implementer could easily miss without this trace. | Section 6 now specifies `PostgresComposedUnitOfWork.__enter__` constructs `PostgresUnitOfWork` **directly**, never via the public factory, forcing it through the one unmodified `_active_unit_of_work` guard that has no notion of "composed" and simply refuses any second concurrent unit of work of any kind. | Resolved |

No unresolved design finding remains.

## 18. Implementation Acceptance Gate (for a future Implementation milestone, not satisfied by this design)

A future M024 implementation is acceptable only if:

- every M023 test passes completely unmodified;
- `PostgresComposedUnitOfWork`/`_JoinedUnitOfWork`/`_active_composed_scope` are implemented exactly as specified in Sections 5-7;
- the Section 9 worked example passes against real PostgreSQL, both for the commit case and the rollback-on-failure case;
- `tools/check_architecture.py .` reports 0 new violations;
- no M023 concrete repository adapter source file is modified.

## 19. Final Decision

```text
DESIGN READY FOR INDEPENDENT REVIEW
NOT APPROVED
NOT FROZEN
```
