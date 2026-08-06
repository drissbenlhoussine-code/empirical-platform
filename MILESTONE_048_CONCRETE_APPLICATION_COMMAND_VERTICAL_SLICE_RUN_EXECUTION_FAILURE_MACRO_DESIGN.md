# MILESTONE-048 - Concrete Application Command Vertical Slice: Run Execution Failure - Macro Design

## 1. Document Status

**Status: CANDIDATE_INTERNAL_MACRO_DESIGN**

Produced in the same consolidated M048 mission as the scope document.

## 2. Repository Authority

| Field | Value |
| --- | --- |
| Repository | `C:\Users\LuxSy\Documents\trading` |
| Branch | `master` |
| M048 frozen baseline | `85706955abce892d14937ad00307717b6170085e` |

## 3. Command Shape

`Run.fail()`'s own actual signature is `fail(self, *, reason: str, actor: str, occurred_at: datetime, correlation_id: str | None = None)` — unlike `Campaign.cancel()`, `reason` here is unconditionally **required** (no default, no state-dependent optionality). The command mirrors this exactly, adding only the two universal command-level fields every prior milestone has required (`identity`, `expected_persisted_version`), in the same relative order as `fail()`'s own parameter list:

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

Six fields. Not copying `CancelCampaignCommand`'s shape verbatim (which makes `reason` optional with a `None` default) — `fail()`'s own signature has no such optionality, so `FailRunCommand.reason` is a required field with no default, matching the domain method precisely.

## 4. Handler Shape

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

Sole dependency: `RunRepository`. Exactly one `.get(`, one `.fail(`, one `.save(` — identical load-mutate-save shape to every prior command (M030-M047), differing only in which domain method is invoked and which repository is used.

## 5. Identity and Expected-Version Semantics

`command.identity` passed to `get()` unchanged. `command.expected_persisted_version` — never `loaded.persisted_version` — passed to `save()`. Both to be independently re-verified via a non-tautological adversarial script during implementation's own hostile self-audit, mirroring M046/M047's own technique.

## 6. Validation Ownership

All domain validation — the three-state `allowed_states` check, the `reason`/`actor`/`occurred_at`/`correlation_id` presence checks — lives entirely inside `Run.fail()`'s own `_require_non_empty` call and `_transition()`. The command performs zero business validation at construction, mirroring M046/M047: `FailRunCommand(reason="", ...)` is always constructible regardless of what state the identified Run is actually in — only `Run.fail()` itself, once invoked against a loaded aggregate, decides whether an empty `reason` is acceptable (it is not, but the rejection happens inside the domain method, not the command).

## 7. Repository Interaction Sequence

1. Receive `FailRunCommand`.
2. `run_repository.get(command.identity)` exactly once.
3. `run.fail(reason=..., actor=..., occurred_at=..., correlation_id=...)` exactly once.
4. `run_repository.save(run, expected_persisted_version=command.expected_persisted_version)` exactly once.
5. Return the exact `SaveResult`, unchanged.

No second `get()`/`save()`, no retry, no transaction orchestration, no second capability.

## 8. Error Propagation

No `try`/`except` anywhere in the handler. Three distinct failure scenarios must propagate transparently, unmodified:

1. `AggregateNotFound` from `get()` (missing Run).
2. Domain `ValueError` from `fail()`/`_transition()` — Run in a state outside the three allowed states (e.g. still `AUTHORIZED`, never started; or already `EXECUTION_COMPLETED`/`FAILED`/`CANCELLED`).
3. Domain `ValueError` from `fail()`'s own `_require_non_empty` — empty-string `reason`.
4. `OptimisticConcurrencyConflict` from `save()` (stale `expected_persisted_version`).

Unlike `Campaign.cancel()` (M047), there is no `TypeError` branch here — `reason` is unconditionally required and always a `str` at the type level; only its emptiness is validated at the domain layer, producing a single `ValueError`, not a state-dependent `TypeError`/`ValueError` split. This is architecturally simpler than M047's own three-mode failure surface, but the `allowed_states` reachability (3 elements) remains the second-widest in the project.

## 9. Result Contract

`SaveResult`, returned exactly as received from `RunRepository.save()` — no wrapping, no reconstruction. To be independently re-verified via an `is`-identity check.

## 10. Transaction Ownership

The handler owns no transaction, retry, or unit-of-work construct. `PostgresRunRepository.save()`'s own `unit_of_work()` context manager (frozen since M023) is the sole transactional boundary.

## 11. `CommandEntryPoint` Binding

`CommandEntryPoint(FailRunHandler(...))` must work unmodified, mirroring every prior command handler's binding.

## 12. Architecture Impact

None. `usecases` already permits `run` in `ALLOWED["usecases"]` since M033. `python tools/check_architecture.py .` must remain exit 0 with zero fixture change.

## 13. Real Conflict Mechanism — the Central Design Decision

`Run.append_manifest()` (M035's own frozen interfering write) requires `state` to be one of `_MANIFEST_APPEND_STATES = (CREATED, AUTHORIZED, ACQUIRING, NORMALIZING, VALIDATING)` and does not call `_transition()` — it never changes `_state`, only `_manifests` and `_version`. `fail()`'s own `allowed_states` (`ACQUIRING`, `NORMALIZING`, `VALIDATING`) is a strict subset of `_MANIFEST_APPEND_STATES`. Therefore: a Run in `ACQUIRING` (or `NORMALIZING`/`VALIDATING`), failed by a stale caller while an independently-loaded interferer calls `append_manifest()` first, should reach a genuine, unqualified `OptimisticConcurrencyConflict` — the interferer's write leaves `state` unchanged (still within `fail()`'s own allowed set) and only advances `version`, so the stale caller's own `fail()` call still passes its own domain preconditions and only fails at the `save()` layer's version guard. This mirrors M035's own already-proven mechanism (originally built for `authorize()`) and M047's own reuse pattern (`revise_scope_statement()` reapplied to `cancel()`), but is applied here to a third target transition (`fail()`) and must be empirically re-confirmed during implementation, not assumed by analogy.

## 14. Test Strategy

- **Unit/contract**: identity/version pass-through (non-tautological), no second `get()`/`save()`, no `add()` call, `SaveResult` identity pass-through, transparent propagation of all failure scenarios (Section 8) including two adversarially-chosen exception types beyond the domain's own vocabulary, and structural `CommandHandler` conformance.
- **PostgreSQL integration**: golden-path failure from at least one execution-stage state (`ACQUIRING`, reached via direct domain-method calls on an independently loaded aggregate as test setup only — `authorize()` has a production command (M035) but `start_acquisition()` does not yet, so this milestone's own test fixtures call it directly, exactly as M047's own fixtures called `record_authorization()`/`activate()` directly); invalid-state rejection (from `AUTHORIZED`, never started); empty-reason rejection; missing-Run rejection (`AggregateNotFound`); genuine `OptimisticConcurrencyConflict` reproduction (Section 13).

## 15. Rejected Alternatives

- An optional `reason` field mirroring `CancelCampaignCommand` — rejected, `fail()`'s own signature has no such optionality; `reason` is unconditionally required.
- A `TypeError` branch mirroring `CancelCampaignCommand`'s conditional validation — rejected, `fail()` has no state-dependent validation; only a single unconditional `ValueError` for emptiness.

## 16. Risks

`append_manifest()`'s own precondition set is broader than `fail()`'s three allowed states — the conflict-reproduction test must specifically choose an overlapping state (`ACQUIRING`, `NORMALIZING`, or `VALIDATING`), carried forward from the scope document's own Section 13 risk disclosure.

## 17. M049 Boundary

This design resolves exactly one MILESTONE-048 capability. No MILESTONE-049 capability, terminology, sequencing decision, or forward commitment is made anywhere in this document.

## 18. Status

**CANDIDATE_INTERNAL_MACRO_DESIGN.**
