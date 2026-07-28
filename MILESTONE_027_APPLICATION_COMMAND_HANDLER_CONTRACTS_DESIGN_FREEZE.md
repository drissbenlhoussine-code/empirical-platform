# MILESTONE-027 - Application Command/Handler Contracts Design Freeze

## 1. Document Control

| Field | Value |
| --- | --- |
| Document ID | MILESTONE-027-DESIGN-FREEZE |
| Title | Application Command/Handler Contracts Design Freeze |
| Status | M027 DESIGN APPROVED AND FROZEN |
| Repository | `C:\Users\LuxSy\Documents\trading` |
| Mission type | Freeze closure only |
| New source code, tests, or runtime changes made by this closure | No |

## 2. Authority Chain

| Role | Commit | Summary |
| --- | --- | --- |
| Initial Design | `2b914ffdf4425d7d6904caaa681d39142d73ba7e` | Design MILESTONE-027 Application Command/Handler Contracts |
| Design Correction | `7753b135bb324a7c1337c542d87660a855c3ee0f` | Harden MILESTONE-027 Application Command/Handler Contracts design |

Independent review outcomes:

1. Independent hostile review of the initial design (`2b914ff`) found two MAJOR findings — generic variance on `CommandHandler` was invariant rather than contravariant/covariant (an actual `mypy --strict`-rejected Protocol definition, verified by direct experimentation, not merely a style preference); the negative type-check strategy for proving malformed handlers are mechanically rejected was undefined — and one MINOR finding: the Scope Selection document still described a `Command` marker type and a handler-level error contract as part of the selected scope, when the Design had already rejected both. Recommendation: `M027 DESIGN REQUIRES NARROW CORRECTION`.
2. The Project Owner authorized a narrow correction addressing exactly those three findings. Commit `7753b13` froze contravariant/covariant generics (`_CommandT_contra`, `_ResultT_co`), verified empirically against the project's own live `mypy --strict` configuration; froze an isolated negative-type-check fixture mechanism (`tests/typing_fixtures/command_handler/` plus a subprocess-invoking pytest test), also verified empirically, and confirmed to never pollute the canonical `mypy` gate or leak into pytest's own collection; and corrected the Scope Selection document to explicitly distinguish components evaluated, selected, and rejected. No canonical Version 1.0 decision that survived scrutiny was reopened — package placement, export-name choice (`CommandHandler` only), the decision not to freeze a `Command` marker or a handler-level error hierarchy, and the zero-repository/zero-transaction scope were all reaffirmed, not reversed.
3. The Project Owner's decision, accepted in this mission's authorization, is to freeze the corrected design following the exact precedent established for M024, M025, and M026.

Authoritative documents for this freeze:

- `MILESTONE_027_APPLICATION_COMMAND_HANDLER_CONTRACTS_SCOPE_SELECTION.md` (Version 1.1);
- `MILESTONE_027_APPLICATION_COMMAND_HANDLER_CONTRACTS_DESIGN.md` (Version 1.1);
- `PROJECT_CHECKPOINT.md` (M027 review-status fields).

Frozen baseline this design built on: MILESTONE-026 implementation freeze commit `45f4916d1fcdd76b28fffa81c23704f6b0355c3d`. That freeze is not reopened, rewritten, or reinterpreted by this closure.

## 3. Canonical Frozen Decisions

The following are frozen exactly as specified by the corrected Version 1.1 design and may not be reinterpreted or redesigned during implementation without a fresh design correction:

1. Exactly one Protocol is frozen:

   ```python
   _CommandT_contra = TypeVar("_CommandT_contra", contravariant=True)
   _ResultT_co = TypeVar("_ResultT_co", covariant=True)


   class CommandHandler(Protocol[_CommandT_contra, _ResultT_co]):
       def handle(self, command: _CommandT_contra) -> _ResultT_co: ...
   ```

   in `src/empirical_platform/shared/contracts/command.py`, exported as
   `CommandHandler` from `shared/contracts/__init__.py`.

2. No separate `Command` marker Protocol is frozen — an empty `Protocol` is structurally satisfied by every object, providing no guarantee.
3. No handler-level error/result-wrapper type, dispatcher, or runtime registry is frozen. The existing M020 `RepositoryContractError` hierarchy remains the only frozen error taxonomy a handler may let propagate.
4. `handle` is synchronous, exactly one method, exactly one positional parameter named `command`, no keyword-only requirement.
5. `_CommandT_contra`/`_ResultT_co` are module-private (leading underscore); only `CommandHandler` is a public export.
6. No `@runtime_checkable` decorator; `mypy`'s static structural check is the sole enforcement mechanism.
7. A positive, zero-runtime-cost structural-conformance proof lives inside `shared/contracts/command.py` itself, inside an `if TYPE_CHECKING:` block, so it is checked automatically by every `mypy` run (`mypy`'s configured scope is `src/` only; a `tests/`-based proof would never be checked).
8. Malformed handler shapes must be mechanically proven rejected via isolated negative typing fixtures under `tests/typing_fixtures/command_handler/` (`ok_handler.py` positive control plus four negative fixtures), checked by a dedicated `tests/unit/test_command_handler_typing.py` invoking `mypy` as a subprocess with an explicit `--config-file` — never added to `[tool.mypy] packages`, and never collected by pytest as test modules (filenames don't match pytest's default collection glob).
9. `shared/contracts/command.py` imports only the standard library `typing` module — zero edges into the existing dependency graph, no repository, persistence, transaction, or concurrency interaction of any kind.
10. No new top-level package; no `tools/check_architecture.py` change; no M020-M026 source file is touched.

## 4. Accepted Non-Blocking Observations

Carried forward explicitly, not silently:

1. `mypy` does not type-check `tests/` under the current project configuration — this is precisely why the positive conformance proof lives inside the module itself rather than in a test file (Section 3, Item 7).
2. The negative-fixture mechanism (Section 3, Item 8) introduces one additional, narrowly-scoped `mypy` subprocess invocation per fixture at test time; this is deliberate and bounded (five fixtures, one dedicated test file) and does not affect the canonical `verify.ps1` gate's scope or runtime characteristics beyond that one new test.
3. `setuptools` emits a non-blocking `project.license` TOML-table deprecation warning during `python -m build`; tracked for a future packaging cleanup, unrelated to M027.
4. This milestone introduces no concrete command or handler; "Application Service Orchestration" remains a distinct, larger, and still-premature future candidate that this milestone's contracts merely unblock, exactly as M020's repository Protocols unblocked M023.

## 5. What This Freeze Does Not Authorize

Freezing the M027 design does not authorize:

- any implementation deviating from Section 3's canonical decisions without a fresh design correction;
- any concrete `Command` or `CommandHandler` implementation for any aggregate;
- application service orchestration, transaction ownership decisions, or any wiring to `PostgresRepositoryRuntime`/`run_composed`;
- a handler-level error hierarchy, a `Command` marker type, a dispatcher, or a runtime registry;
- retry-on-`OptimisticConcurrencyConflict` policy;
- APIs, workers, CLI entrypoints, or any change to `entrypoints/`;
- Audit runtime, Decision Candidate, or Decision Freeze;
- market-data, vendor, trading, or campaign execution behavior;
- MILESTONE-028 work of any kind;
- approval or freeze of the M027 *implementation* — that remains a separate, later gate.

## 6. Final Status

```text
M027 DESIGN APPROVED AND FROZEN
```

Implementation may now proceed strictly within the boundaries frozen in Section 3, subject to its own independent review, approval, and freeze before any MILESTONE-028 work begins.
