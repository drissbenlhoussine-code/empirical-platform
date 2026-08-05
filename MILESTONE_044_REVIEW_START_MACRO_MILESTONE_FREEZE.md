# MILESTONE-044 - Review Start Macro Milestone Freeze

## 1. Document Status

**Status: FINAL — OWNER FROZEN**

This document is the Owner Freeze record for MILESTONE-044, the ninth milestone produced under the Macro Milestone Protocol (M035 implementation freeze, Section 49; PROJECT_CHECKPOINT.md Section 31). It is authoritative.

## 2. Milestone Identity

MILESTONE-044 — Concrete Application Command Vertical Slice: Review Lifecycle Transition (`start()`).

## 3. Repository Authority

| Field | Value |
| --- | --- |
| Repository | `C:\Users\LuxSy\Documents\trading` |
| Branch | `master` |
| HEAD at freeze (pre-freeze-commit) | `e64414222d6ec45342612fb9788750430fa85c27` |
| origin/master at freeze (pre-freeze-commit) | `e64414222d6ec45342612fb9788750430fa85c27` (0/0, clean tree) |

## 4. Frozen Predecessor Chain

M020-M043 all `APPROVED_AND_FROZEN` at every stage. M043 Owner Freeze: `MILESTONE_043_REVIEW_RETRIEVAL_MACRO_MILESTONE_FREEZE.md`, freeze commit `4b9770cd2dd80fa1b1968871f08167c07f8fddca`, hash-recording commit `a2902092755bef6951e11512183240b33a463088`.

## 5. Macro Scope Authority

`MILESTONE_044_CONCRETE_APPLICATION_COMMAND_VERTICAL_SLICE_REVIEW_LIFECYCLE_TRANSITION_MACRO_SCOPE.md` — a fresh architecture inventory found `Review` had `create` (M042) and `get` (M043) but zero command-side proof of `ReviewRepository.save()`/`OptimisticConcurrencyConflict` propagation. One concrete command transitioning an existing, `ASSIGNED` `Review` to `IN_PROGRESS`, via `Review.start()` — the fourth proof of the `get()`→mutate→`save()`/`OptimisticConcurrencyConflict` pattern (after M032 Campaign, M035 Run, M038 EvidencePackage). `add_finding()`/`complete()` remain genuinely blocked behind `start()`'s own prior non-existence; `cancel()`/`EvidencePackage.invalidate()` were both evaluated and rejected as lower-leverage repeats of an already-proven pattern.

## 6. Macro Design Authority

`MILESTONE_044_CONCRETE_APPLICATION_COMMAND_VERTICAL_SLICE_REVIEW_LIFECYCLE_TRANSITION_MACRO_DESIGN.md` — a six-field command, field-for-field identical to `StartEvidencePackageCollectionCommand` (M038). Conflict feasibility independently determined, not assumed: `Review` has no state-preserving mutation reachable while `ASSIGNED`, mirroring M038's identical, already-accepted resolution for `start_collection()`.

## 7. Implementation Commit

`37733f357bcabb864a0a0576bba4621685d35621` (`feat: implement M044 Review lifecycle transition usecase`).

## 8. Finalization Commit

`e64414222d6ec45342612fb9788750430fa85c27` (`docs: finalize M044 macro milestone review package`) — narrow, checkpoint-only, recorded the implementation commit's own hash. No production behavior changed. Deliberately does not cite a package-level ZIP hash in its commit message, avoiding the staleness pattern identified and disclosed in M043's own freeze record (Section 42).

## 9. Independent Review Authority

A 26-phase independent hostile review, treating every source file, test, governance document, commit message, and packaged claim as potentially false, independently re-derived: repository truth and commit lineage (exactly 9 files, zero unauthorized change); M043 freeze ordering and purity; a fresh architecture inventory at the exact M044 baseline commit tree confirming `Review` had zero `save()`/conflict proof before this milestone; the honest, non-overstated `cancel()` rejection reasoning; zero scope-creep across the full production+test delta; a full domain-contract read of `Review.start()`/`_transition()`/`PostgresReviewRepository.save()`; exact command/handler-shape verification; a non-tautological adversarial script proving the caller-supplied `expected_persisted_version` reaches `save()` unchanged and is never replaced by `loaded.persisted_version`; exact result-identity, transition-semantics, and error-propagation verification (5 exception types, 3 adversarially chosen); and — most critically — a **freshly authored direct-SQL adversarial script**, run against a **separately provisioned, never-reused** PostgreSQL container, that independently reproduced the exact 10-step racing-callers sequence described in the review mission and confirmed via raw SQL that the second caller genuinely receives a plain domain `ValueError` (never `OptimisticConcurrencyConflict`), with the final persisted state being exactly the first writer's result and zero corruption. The review additionally re-ran the full regression suite, architecture checker, toolchain (`ruff`/`mypy`/`build`/`security.ps1`/`verify.ps1`), and external-review package verification (ZIP/manifest/`complete.diff`), all independently matching every claim with zero drift.

## 10. Review Decision

**M044 MACRO MILESTONE APPROVED WITH NON-BLOCKING OBSERVATIONS.** No CRITICAL, MAJOR, MINOR, or OBSERVATION finding survived independent verification — the review's own final report recorded zero findings.

## 11. Owner Approval

The owner formally freezes the M044 macro milestone via this document.

**M044 MACRO MILESTONE APPROVED_AND_FROZEN.**

**M044 APPROVED_AND_FROZEN** — scope, design, and implementation, at every stage, frozen as one consolidated unit per the Macro Milestone Protocol.

## 12. Frozen Production Capability

Exactly one: transition of an existing, `ASSIGNED` `Review` to `IN_PROGRESS`, via `StartReviewCommand`/`StartReviewHandler` (`src/empirical_platform/usecases/start_review.py`). No `Review.add_finding()`/`complete()`/`cancel()`, no `EvidencePackage.invalidate()`, and no second command.

## 13. Frozen Command Contract

```python
@dataclass(frozen=True, slots=True)
class StartReviewCommand:
    identity: DomainIdentity[ReviewId]
    expected_persisted_version: AggregateVersion
    actor: str
    occurred_at: datetime
    correlation_id: str | None = None
    reason: str | None = None
```

Exactly six fields, field-for-field identical to `StartEvidencePackageCollectionCommand` (M038).

## 14. Frozen Handler Contract

```python
class StartReviewHandler:
    __slots__ = ("_review_repository",)

    def __init__(self, *, review_repository: ReviewRepository) -> None:
        self._review_repository = review_repository

    def handle(self, command: StartReviewCommand) -> SaveResult:
        loaded = self._review_repository.get(command.identity)
        review = loaded.aggregate
        review.start(
            actor=command.actor,
            occurred_at=command.occurred_at,
            correlation_id=command.correlation_id,
            reason=command.reason,
        )
        return self._review_repository.save(
            review, expected_persisted_version=command.expected_persisted_version
        )
```

Sole dependency: `ReviewRepository`. Independently re-confirmed: exactly one `.get(`, one `.start(`, one `.save(`; zero `.add(`; zero other collaborator.

## 15. Frozen Identity Semantics

`command.identity` passed to `get()` unchanged — independently verified via Python's `is` operator (true object identity) in a freshly written adversarial script.

## 16. Frozen Expected-Version Semantics

`command.expected_persisted_version` — never `loaded.persisted_version` — passed to `save()`. Independently re-verified via a **non-tautological** adversarial script: `loaded.persisted_version=77`, `command.expected_persisted_version=3` (genuinely different values), `save()` genuinely received the command's own version object (`is` check true), never the loaded value.

## 17. Exact Load–Mutate–Save Sequence

1. Receive `StartReviewCommand`.
2. Call `review_repository.get(command.identity)` exactly once.
3. Call `review.start(...)` exactly once.
4. Call `review_repository.save(review, expected_persisted_version=command.expected_persisted_version)` exactly once.
5. Return the exact `SaveResult`, unchanged.

No second `get()`/`save()`, no retry, no transaction orchestration, no second capability.

## 18. Frozen Result Contract

`SaveResult`, returned exactly as received from `ReviewRepository.save()` — independently verified via `is` identity check — no wrapping, no reconstruction.

## 19. Review Source State

`ASSIGNED` — the sole allowed starting state, enforced by `Review._transition(allowed_states=(ASSIGNED,), ...)`.

## 20. Review Target State

`IN_PROGRESS`.

## 21. Aggregate-Version Semantics

A successful `start()` call advances `Review.version` by exactly one — independently re-confirmed via a freshly written script.

## 22. Persisted-Version Semantics

`PostgresReviewRepository.save()`'s `UPDATE ... WHERE version = :expected_persisted_version` is the sole authoritative concurrency gate — independently re-confirmed via fresh source reading.

## 23. Transition-History Semantics

Exactly one `StateTransitionRecord` appended (`from_state="ASSIGNED"`, `to_state="IN_PROGRESS"`) per successful `start()` call — independently re-confirmed.

## 24. Actor/Time/Reason/Correlation Semantics

`actor`, `occurred_at`, `correlation_id`, `reason` from the command are preserved exactly onto the resulting transition record — independently re-confirmed with adversarially chosen values, including verifying `findings`/`disposition`/`cancellation_reason` remain untouched.

## 25. Not-Found Behavior

A missing full identity raises `AggregateNotFound`, unmodified, independently reproduced against real PostgreSQL and via unit-level `is` checks.

## 26. Invalid-State Behavior

A `start()` attempt against a non-`ASSIGNED` Review raises a domain `ValueError` before `save()` is ever reached — independently reproduced against real PostgreSQL, with raw SQL confirming state/version/transition-count unchanged after the failed attempt.

## 27. Arbitrary Error Semantics

No `try`/`except` anywhere in `StartReviewHandler`. Independently verified with 5 exception types — including 3 chosen adversarially by the reviewer (`InvalidAggregateForPersistence`, `TypeError`, `StopIteration`) beyond the frozen test suite's own coverage — all propagate with exact instance identity (`is`) preserved.

## 28. Validation Ownership

None owned by `StartReviewCommand` itself; all validation is owned by `Review.start()`'s own precondition checks and the shared `_transition()` invariant checks.

## 29. Transaction Non-Ownership

The handler owns no transaction/unit-of-work boundary; `PostgresReviewRepository.save()` opens its own `unit_of_work()` scope internally, identical to every other frozen `save()`-pattern repository.

## 30. CommandEntryPoint Binding

`CommandEntryPoint(StartReviewHandler(...))` works unmodified — independently re-confirmed by a dedicated integration test and by the independent review's own direct-SQL adversarial script.

## 31. Architecture Preservation

Zero architecture-checker or fixture change this milestone. Independently re-confirmed: `git diff` on `tools/check_architecture.py` and every fixture file between the M043 baseline and this HEAD shows no change at all; the negative fixture set still correctly reports 29 violations.

## 32. PostgreSQL Success Evidence

Golden-path transition independently reproduced at implementation time and independent-review time, each against a freshly provisioned, disposable `postgres:17` container never reused across sessions: `SaveResult.operation=UPDATED`, `persisted_version=1`; reload confirms `IN_PROGRESS`, version 1, exactly one transition record with correct actor/correlation/reason; raw SQL cross-check confirms identical persisted state.

## 33. PostgreSQL Missing-Review Evidence

A missing full identity independently reproduced to raise `AggregateNotFound` against real PostgreSQL; raw SQL confirms zero row for the missing identity.

## 34. PostgreSQL Invalid-State Evidence

A second `start()` attempt against an already-`IN_PROGRESS` Review independently reproduced to raise a domain `ValueError`, never reaching `save()`; raw SQL confirms persisted state/version/transition-count unchanged after the failed attempt.

## 35. Racing-Caller Evidence

The exact 10-step racing-callers sequence independently reproduced via a freshly authored direct-SQL adversarial script against a separately provisioned container: first caller succeeds (`IN_PROGRESS`, version 1); second caller's own fresh `get()` sees `IN_PROGRESS` already and its own `start()` call fails the domain precondition check with a plain `ValueError`, confirmed via `isinstance(exc, OptimisticConcurrencyConflict) is False` and `type(exc) is ValueError`; raw SQL confirms the final persisted state is exactly the first writer's result (`IN_PROGRESS`, version 1, exactly 1 transition record) with zero corruption.

## 36. Real Concurrency Boundary

Independently confirmed genuine, not assumed: `Review` has no state-preserving mutation reachable while `ASSIGNED` — `add_finding()` requires `IN_PROGRESS` (fails on `ASSIGNED` before reaching any conflict), `cancel()` changes state away from `ASSIGNED`. The only reachable interfering write against an `ASSIGNED` Review is `start()` itself, which is state-changing. Consequently, a true `OptimisticConcurrencyConflict` reproduction via genuine, caller-driven, real-PostgreSQL evidence is **not achievable** for `start()` specifically — mirroring M038's identical, already-accepted boundary for `start_collection()`. No direct-SQL version fabrication, invalid row insertion, patched aggregate internals, or second production command were used anywhere to manufacture a conflict that is not genuinely reachable via a real caller path.

## 37. Unit-Level Conflict Propagation Boundary

`OptimisticConcurrencyConflict` propagation itself is proven exclusively at the unit level, via a fake `ReviewRepository` whose `save()` raises it directly, unconstrained by `Review`'s own domain preconditions (`tests/unit/test_start_review_usecase.py::test_optimistic_concurrency_conflict_from_save_propagates_unchanged`). This boundary is explicit, disclosed, and precedented (M038) throughout every governance document — independently confirmed via an exhaustive grep sweep that found zero claim of live PostgreSQL `OptimisticConcurrencyConflict` anywhere.

## 38. Full Regression Evidence

Independently reproduced at implementation time and independent-review time, zero drift each time: focused unit+contract 24 passed; M044 focused PostgreSQL 4 passed; targeted M042+M043+M044 regression 13 passed; non-integration suite 790 passed, 178 deselected, coverage 84.39%; full integration regression 172 passed, 6 skipped (up from 168 pre-M044); full suite with PostgreSQL 962 passed, 6 skipped, coverage 93.15%.

## 39. Ruff/Mypy/Build Evidence

`ruff format --check`: 256 files already formatted. `ruff check`: all checks passed. Canonical `mypy`: 101 source files, 0 issues. `python -m build --wheel`: succeeds; wheel contains `start_review.py`, zero `tests`/`external-review`/`__pycache__`/`.pyc` entries.

## 40. Security and pip-audit Evidence

`scripts/security.ps1` and `scripts/verify.ps1`: both independently re-run end-to-end, both succeed with no thrown error. `pip-audit` (embedded and standalone): no known vulnerabilities. Secret-scan target count: 459, independently cross-checked against `git ls-files` (459 tracked, 0 untracked-non-ignored) — fully reconciled.

## 41. External Review Package Verification

`external-review/MILESTONE-044/MILESTONE-044-e644142-external-review.zip` — SHA-256 `991b24e426421699f6c7f2c37bfa3815241d592474e63256eb03686e7002d6e1`, independently recomputed and matched at package-build time and independent-review time. 28 entries, `testzip()` clean, no duplicates, no unsafe paths, no self-inclusion. `manifest.sha256`: 27/27 verified, including from a fresh extraction. `complete.diff`: byte-identical to a live regeneration. All packaged files: byte-identical to the live repository.

## 42. Changed-File Surface

```
A  MILESTONE_044_CONCRETE_APPLICATION_COMMAND_VERTICAL_SLICE_REVIEW_LIFECYCLE_TRANSITION_MACRO_DESIGN.md
A  MILESTONE_044_CONCRETE_APPLICATION_COMMAND_VERTICAL_SLICE_REVIEW_LIFECYCLE_TRANSITION_MACRO_IMPLEMENTATION.md
A  MILESTONE_044_CONCRETE_APPLICATION_COMMAND_VERTICAL_SLICE_REVIEW_LIFECYCLE_TRANSITION_MACRO_SCOPE.md
M  PROJECT_CHECKPOINT.md
M  src/empirical_platform/usecases/__init__.py
A  src/empirical_platform/usecases/start_review.py
A  tests/contract/test_start_review_handler_contract.py
A  tests/integration/test_m044_start_review_usecase.py
A  tests/unit/test_start_review_usecase.py
```

Exactly nine files, independently re-confirmed via `git diff --name-status` against the M043 baseline at both review stages, byte-for-byte identical to the external-review package manifest.

## 43. No-Scope-Creep Declaration

No `Review.add_finding()`/`complete()`/`cancel()` production capability; no `EvidencePackage.invalidate()`; no retry policy; no composition root, registry, dispatcher, mediator, service locator, or DI framework; no transport/API layer; no schema/migration change; no MILESTONE-045 work exists anywhere in this milestone — independently re-confirmed via a full-delta grep sweep including governance prose, finding only explicit exclusion/boundary declarations and one negative-assertion test docstring, never actual work.

## 44. Preserved M020-M043 Authority

No change to any M020-M043 frozen contract, source file, test, or governance document — independently re-confirmed via `git diff --name-only` restricted to `src/empirical_platform/{review,evidence,campaign,run}/` and `migrations/`, returning zero matches. `PROJECT_CHECKPOINT.md`'s only removed lines across the entire M043-to-M044 diff are M044's own prior placeholder text, never an M043 field. All prior authority remains exactly as previously frozen.

## 45. Owner Freeze Declaration

**M044 MACRO MILESTONE APPROVED_AND_FROZEN.** The implementation delivered in commit `37733f3`, finalized in commit `e644142`, exactly as independently re-verified across a 26-phase independent hostile review (Sections 9, 19-41 above), is the final, frozen implementation of MILESTONE-044.

## 46. Deferred Work

`Review.add_finding()`/`complete()`/`cancel()`; `EvidencePackage.invalidate()`; retry-on-conflict policy; any composition-root abstraction beyond direct binding; MILESTONE-045 and beyond.

## 47. M045 Boundary

This freeze authorizes work through MILESTONE-044 only. No MILESTONE-045 capability, terminology, sequencing decision, or forward commitment is made anywhere in this document. Section 46's "Deferred Work" is descriptive of currently-visible future candidates, not a binding selection of MILESTONE-045's scope.

## 48. Final Status

**M044 APPROVED_AND_FROZEN** — scope, design, and implementation, at every stage.

M045: NOT_STARTED (pending this freeze's completion).

## 49. Next Permitted Action

**MILESTONE-045 COMPLETE MACRO MILESTONE MISSION.**
