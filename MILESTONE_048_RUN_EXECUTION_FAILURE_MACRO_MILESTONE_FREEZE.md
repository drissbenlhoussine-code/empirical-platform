# MILESTONE-048 - Run Execution Failure Macro Milestone Freeze

## 1. Document Status

**Status: FINAL — OWNER FROZEN**

This document is the Owner Freeze record for MILESTONE-048, the thirteenth milestone produced under the Macro Milestone Protocol (M035 implementation freeze, Section 49; PROJECT_CHECKPOINT.md Section 31). It is authoritative.

## 2. Milestone Identity

MILESTONE-048 — Concrete Application Command Vertical Slice: Run Execution Failure.

## 3. Repository Authority

| Field | Value |
| --- | --- |
| Repository | `C:\Users\LuxSy\Documents\trading` |
| Branch | `master` |
| HEAD at freeze (pre-freeze-commit) | `cc1526dde697e453c9498ecc26a663251589c0ad` |
| origin/master at freeze (pre-freeze-commit) | `cc1526dde697e453c9498ecc26a663251589c0ad` (0/0, clean tree) |

## 4. Frozen Predecessor Chain

M020-M047 all `APPROVED_AND_FROZEN` at every stage. M047 Owner Freeze: `MILESTONE_047_CAMPAIGN_CANCELLATION_MACRO_MILESTONE_FREEZE.md`, freeze commit `53e3c4786922ea82e5d85ba5ce59dbfeb9dad934`, hash-recording commit `85706955abce892d14937ad00307717b6170085e`.

## 5. Scope Authority

`MILESTONE_048_CONCRETE_APPLICATION_COMMAND_VERTICAL_SLICE_RUN_EXECUTION_FAILURE_MACRO_SCOPE.md` — a fresh architecture inventory found Run carries the single largest remaining absolute application-layer gap (7 of 8 domain methods unproven). A direct comparison of the four remaining negative/terminal candidates (`Run.cancel()`, `Run.fail()`, `Review.cancel()`, `EvidencePackage.invalidate()`) against the now-frozen `Campaign.cancel()` (M047) precedent found `Run.fail()` uniquely combines the second-widest `allowed_states` (3 elements) with a semantically distinct scenario (mid-execution failure, not deliberate abandonment) — the only remaining candidate that generalizes the negative/terminal axis to a new real-world scenario.

## 6. Design Authority

`MILESTONE_048_CONCRETE_APPLICATION_COMMAND_VERTICAL_SLICE_RUN_EXECUTION_FAILURE_MACRO_DESIGN.md` — a six-field command mirroring `Run.fail()`'s own actual signature (`reason` unconditionally required, unlike `Campaign.cancel()`'s state-dependent optionality). Conflict feasibility (whether `append_manifest()` genuinely serves this new target transition) raised as an open empirical question, not assumed, and confirmed genuinely achievable during implementation.

## 7. Implementation Commit

`c78099fdd0638a252de94ce3f21cc1512ccdfea6` (`feat: implement M048 Run execution failure usecase`).

## 8. Finalization Commit

`cc1526dde697e453c9498ecc26a663251589c0ad` (`docs: finalize M048 macro milestone review package`) — narrow, checkpoint-only, recorded the implementation commit's own hash. No production behavior changed. Deliberately does not cite a package-level ZIP hash in its commit message, per the established practice since M044.

## 9. Independent Review Authority

A 27-phase independent hostile review, treating every source file, test, governance document, commit message, and packaged claim as potentially false, independently re-derived: repository truth and commit lineage (exactly 9 files, zero unauthorized change); M047 freeze ordering and purity; a fresh architecture inventory re-deriving all 4 remaining negative-terminal candidates' `allowed_states` shapes directly from source, confirming `Run.fail()`'s selection is genuinely `HIGHEST_LEVERAGE`; a full source read of `fail_run.py` with programmatic call-count verification; a non-tautological adversarial script proving identity/version pass-through and `SaveResult` identity; an exhaustive domain-level probe exercising all 8 lifecycle states (3 allowed with manifest preservation, 5 disallowed) plus signature-level confirmation that `reason` has no default; a second adversarial script proving transparent propagation of 6 error scenarios using exception types distinct from both the implementation's and prior review's own audits (`BufferError`, `ArithmeticError`); an independent count of all 30 M048 tests; and — most critically — a **freshly authored direct-SQL adversarial script**, run against a **separately provisioned, never-reused** PostgreSQL container (`m048-review-independent`, port 56147), that independently reproduced the genuine conflict scenario using `append_manifest()` as the interferer and confirmed via raw SQL that a genuine, unqualified `OptimisticConcurrencyConflict` is reached, with the interferer's manifest persisted and authoritative and the stale failure transition never persisted. The review additionally re-ran the full regression suite (twice — once at implementation-package-evidence time and once independently on the review's own fresh container), architecture checker, toolchain, and external-review package verification (fresh extraction, ZIP/manifest/`complete.diff` byte-identity), all independently matching every claim.

## 10. Review Decision

**M048 MACRO MILESTONE APPROVED WITH NON-BLOCKING OBSERVATIONS.** No CRITICAL, MAJOR, or blocking MINOR finding survived independent verification — the review's own final report recorded zero findings of any severity.

## 11. Owner Approval

The owner formally freezes the M048 macro milestone via this document.

**M048 MACRO MILESTONE APPROVED_AND_FROZEN.**

**M048 APPROVED_AND_FROZEN** — scope, design, and implementation, at every stage, frozen as one consolidated unit per the Macro Milestone Protocol.

## 12. Frozen Production Capability

Exactly one: failing an existing Run from any of its three execution-stage states (`ACQUIRING`, `NORMALIZING`, `VALIDATING`), via `FailRunCommand`/`FailRunHandler` (`src/empirical_platform/usecases/fail_run.py`). No Run cancellation, no Run forward-pipeline transition, no `Review.cancel()`, no `EvidencePackage.invalidate()`.

## 13. Frozen Command Contract

```python
@dataclass(frozen=True, slots=True)
class FailRunCommand:
    identity: DomainIdentity[RunId]
    expected_persisted_version: AggregateVersion
    reason: str
    actor: str
    occurred_at: datetime
    correlation_id: str | None = None
```

Exactly six fields, mirroring `Run.fail()`'s own actual signature — `reason` unconditionally required (no default), unlike M047's `Campaign.cancel()` state-dependent optionality.

## 14. Frozen Handler Contract

```python
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

Sole dependency: `RunRepository`. Independently re-confirmed: exactly one `.get(`, one `.fail(`, one `.save(`; zero `.add(`.

## 15. Frozen Identity Semantics

`command.identity` passed to `get()` unchanged — independently verified via Python's `is` operator in a freshly written, non-reused adversarial script during the independent review.

## 16. Frozen Expected-Version Semantics

`command.expected_persisted_version` — never `loaded.persisted_version` — passed to `save()`. Independently re-verified via a **non-tautological** adversarial script: `loaded.persisted_version=505`, `command.expected_persisted_version=17` (genuinely different), `save()` genuinely received the command's own version object (`is` check true).

## 17. Exact Load–Mutate–Save Sequence

1. Receive `FailRunCommand`.
2. Call `run_repository.get(command.identity)` exactly once.
3. Receive `LoadedAggregate[Run]`.
4. Call `run.fail(reason=..., actor=..., occurred_at=..., correlation_id=...)` exactly once.
5. Call `run_repository.save(run, expected_persisted_version=command.expected_persisted_version)` exactly once.
6. Return the exact `SaveResult`, unchanged.

No second `get()`/`save()`, no second mutation, no retry, no transaction orchestration, no second capability.

## 18. Frozen Result Contract

`SaveResult`, returned exactly as received from `RunRepository.save()` (`is` identity, independently confirmed) — no wrapping, no reconstruction.

## 19. Allowed Source States

Exactly three: `ACQUIRING`, `NORMALIZING`, `VALIDATING` — independently exercised and confirmed to each successfully reach `FAILED` in the review's exhaustive state-by-state probe.

## 20. Invalid Source States

All five remaining states (`CREATED`, `AUTHORIZED`, `EXECUTION_COMPLETED`, `FAILED`, `CANCELLED`) independently confirmed to raise `ValueError("cannot transition from {state}; expected ...")` via `_transition()`'s own state-membership check.

## 21. Required Reason Semantics

`reason` is unconditionally required at the Python signature level (no default, confirmed via `inspect.signature` inspection); an empty/whitespace-only `reason` is independently confirmed to raise `ValueError("failure reason must be non-empty")` from all three allowed states. Unlike M047's `Campaign.cancel()`, there is no state-dependent `TypeError` branch.

## 22. Failure Target State

On success, `Run.state` becomes `FAILED` — a terminal state, from any of the three allowed source states.

## 23. Aggregate-Version Semantics

`Run.version` advances by exactly one on successful failure, inside `_transition()` — independently confirmed for all three source states.

## 24. Persisted-Version Semantics

`save()` is guarded by `command.expected_persisted_version`, never the handler's own `loaded.persisted_version` — see Section 16.

## 25. Transition-History Semantics

Exactly one new `StateTransitionRecord` is appended per failure (`from_state=<source>`, `to_state="FAILED"`), independently confirmed for all three source states.

## 26. Manifest Preservation

Existing `Run.manifests` are independently confirmed unchanged in both count and content across a successful `fail()` call, for all three allowed source states.

## 27. Actor/Time/Reason/Correlation Semantics

`actor`, `occurred_at`, `reason`, `correlation_id` pass unchanged from the command into `fail()` and, from there, into the resulting `StateTransitionRecord` — independently confirmed via the review's own adversarial scripts.

## 28. Missing-Run Behavior

`RunRepository.get()` raising `AggregateNotFound` propagates through the handler unchanged (exact instance, `is` check) — `save()` is never called.

## 29. Invalid-State Behavior

A Run outside `ACQUIRING`/`NORMALIZING`/`VALIDATING` causes `fail()`/`_transition()` to raise `ValueError("cannot transition from {state}; expected ...")` — `save()` is never called. Independently reproduced against real PostgreSQL from `AUTHORIZED`.

## 30. Empty-Reason Behavior

An empty/whitespace `reason` causes `fail()`'s own `_require_non_empty` call to raise `ValueError("failure reason must be non-empty")` — `save()` is never called. Independently reproduced against real PostgreSQL.

## 31. Arbitrary Error Semantics

Independently re-verified via adversarially-chosen, domain-unrelated exception types (`BufferError` from `get()`, `ArithmeticError` from `save()`): both propagate through the handler with exact instance identity, unmodified.

## 32. Validation Ownership

All domain validation (state, reason emptiness, actor/time/correlation presence) lives in `Run.fail()`/`_transition()`. The command performs zero business validation at construction — independently confirmed (an empty-string `reason` is accepted at construction time; only `Run.fail()`'s own internal validation rejects it downstream).

## 33. Transaction Non-Ownership

The handler owns no transaction, retry, or unit-of-work construct of any kind. `PostgresRunRepository.save()`'s own `unit_of_work()` context manager (frozen since M023) is the sole transactional boundary.

## 34. CommandEntryPoint Binding

`CommandEntryPoint(FailRunHandler(...))` works unmodified — independently re-confirmed via both the unit test suite and a fresh PostgreSQL-backed script.

## 35. Architecture Preservation

`usecases` already permitted `run` in `ALLOWED["usecases"]` since M033 — zero architecture-checker change required. `python tools/check_architecture.py .` exit 0, independently re-verified. Zero fixture change.

## 36. PostgreSQL Success Evidence

Golden-path failure independently reproduced against a fresh, disposable container (`m048-review-independent`, port 56147) from `ACQUIRING` via the M048 integration test file (6/6 passed).

## 37. PostgreSQL Empty-Reason Evidence

`test_empty_reason_raises_domain_value_error` independently reproduced against the review's own fresh container.

## 38. PostgreSQL Invalid-State Evidence

`test_invalid_state_still_authorized_raises_domain_value_error` independently reproduced against the review's own fresh container.

## 39. PostgreSQL Missing-Run Evidence

`test_missing_run_raises_aggregate_not_found` independently reproduced against the review's own fresh container.

## 40. Genuine Optimistic-Conflict Evidence

Independently re-verified via a **freshly authored** direct-SQL adversarial script (separate from the implementation session's own script), against a separately provisioned container: real production handlers set up a Run in `ACQUIRING`; a distinct `append_manifest()` call by an independently-loaded interferer genuinely advanced the persisted version while preserving `ACQUIRING` (still within `fail()`'s own `allowed_states`); the stale `FailRunCommand` call raised `type(raised) is OptimisticConcurrencyConflict` exactly — never a domain `ValueError`. No direct-SQL version fabrication, invalid row insertion, patched aggregate internals, or second production command was used anywhere to manufacture this conflict.

## 41. Winner/Loser Persistence Semantics

Raw SQL confirmed directly: the interferer's write is authoritative (`version=3`, `lifecycle_state='ACQUIRING'`, 1 manifest row); the stale `fail()` call is entirely absent (0 `run_transition` rows with `to_state='FAILED'`) — no partial or fabricated persistence of any kind.

## 42. Full Regression Evidence

Independently reproduced at implementation time, package-evidence time, and independent-review time, zero drift each time: focused unit+contract 24 passed; M048 focused PostgreSQL 6 passed; non-integration suite 892 passed, 202 deselected, coverage 84.78%; full integration regression 196 passed, 6 skipped (up from 190 pre-M048); full suite with PostgreSQL **1088 passed, 6 skipped, coverage 93.65%**.

## 43. Ruff/Mypy/Build Evidence

`ruff format --check`: 272 files already formatted. `ruff check`: all checks passed. Canonical bare `mypy` invocation: 105 source files, 0 issues. `python -m build --wheel`: succeeds; wheel contains `fail_run.py`, zero `tests`/`external-review`/`__pycache__`/`.pyc` entries.

## 44. Security and pip-audit Evidence

`pip-audit`: no known vulnerabilities. Secret-scan target count: 491, independently reproduced against live source and reconciled against `git ls-files` (491 tracked, 0 untracked-non-ignored).

## 45. External Review Package Verification

`external-review/MILESTONE-048/MILESTONE-048-cc1526d-external-review.zip` — SHA-256 `f6d6140a6a99da286a75a39c1f0300e7849aaa2879d60476e5aa20befa130d79`, independently recomputed and matched at package-build time and independent-review time (including a fresh extraction). 28 entries, no duplicates, no unsafe paths, no self-inclusion. `manifest.sha256`: 27/27 verified, including from a fresh extraction. `complete.diff`: byte-identical to a fresh `git diff` regeneration of the exact same commit range. All packaged `source/`/`tests/`/`governance/PROJECT_CHECKPOINT.md` files: byte-identical to the live repository.

## 46. Changed-File Surface

```
A  MILESTONE_048_CONCRETE_APPLICATION_COMMAND_VERTICAL_SLICE_RUN_EXECUTION_FAILURE_MACRO_DESIGN.md
A  MILESTONE_048_CONCRETE_APPLICATION_COMMAND_VERTICAL_SLICE_RUN_EXECUTION_FAILURE_MACRO_IMPLEMENTATION.md
A  MILESTONE_048_CONCRETE_APPLICATION_COMMAND_VERTICAL_SLICE_RUN_EXECUTION_FAILURE_MACRO_SCOPE.md
M  PROJECT_CHECKPOINT.md
M  src/empirical_platform/usecases/__init__.py
A  src/empirical_platform/usecases/fail_run.py
A  tests/contract/test_fail_run_handler_contract.py
A  tests/integration/test_m048_fail_run_usecase.py
A  tests/unit/test_fail_run_usecase.py
```

Exactly nine files, independently re-confirmed via `git diff --name-status` against the M047 baseline at both review stages, byte-for-byte identical to the external-review package manifest.

## 47. No-Scope-Creep Declaration

No Run cancellation, forward-pipeline transition (`start_acquisition`/`start_normalization`/`start_validation`/`complete_execution` appear only inside test fixtures as direct domain-method calls, test setup only, never through a production command); no `Campaign`/`EvidencePackage`/`Review` capability; no retry policy; no composition root, registry, dispatcher, mediator, service locator, or DI framework; no transport/API layer; no schema/migration change; no MILESTONE-049 work exists anywhere in this milestone — independently re-confirmed via a full-delta grep sweep including governance prose.

## 48. Preserved M020-M047 Authority

No change to any M020-M047 frozen contract, source file, test, or governance document — independently re-confirmed via `git diff --name-only` restricted to `src/empirical_platform/{campaign,run,evidence,review}/`, `shared/persistence/`, and `migrations/`, returning zero matches. `PROJECT_CHECKPOINT.md`'s only removed lines across the entire M047-to-M048 diff are M048's own prior placeholder text, never an M047 field.

## 49. Owner Freeze Declaration

**M048 MACRO MILESTONE APPROVED_AND_FROZEN.** The implementation delivered in commit `c78099f`, finalized in commit `cc1526d`, exactly as independently re-verified across a 27-phase independent hostile review (Sections 9, 19-45 above), is the final, frozen implementation of MILESTONE-048.

## 50. Deferred Work

`Run.cancel()`; remaining Run forward-pipeline transitions; `Review.cancel()`; `EvidencePackage.invalidate()`; other Campaign lifecycle transitions; retry-on-conflict policy; any composition-root abstraction beyond direct binding; MILESTONE-049 and beyond.

## 51. M049 Boundary

This freeze authorizes work through MILESTONE-048 only. No MILESTONE-049 capability, terminology, sequencing decision, or forward commitment is made anywhere in this document. Section 50's "Deferred Work" is descriptive of currently-visible future candidates, not a binding selection of MILESTONE-049's scope.

## 52. Final Status

**M048 APPROVED_AND_FROZEN** — scope, design, and implementation, at every stage.

M049: NOT_STARTED (pending this freeze's completion).

## 53. Next Permitted Action

**MILESTONE-049 COMPLETE MACRO MILESTONE MISSION.**
