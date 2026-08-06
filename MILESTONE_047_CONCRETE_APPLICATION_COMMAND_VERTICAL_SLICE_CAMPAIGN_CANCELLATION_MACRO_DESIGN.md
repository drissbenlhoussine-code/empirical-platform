# MILESTONE-047 - Concrete Application Command Vertical Slice: Campaign Cancellation - Macro Design

## 1. Document Status

**Status: CANDIDATE_INTERNAL_MACRO_DESIGN**

Produced in the same consolidated M047 mission as the scope document.

## 2. Repository Authority

| Field | Value |
| --- | --- |
| Repository | `C:\Users\LuxSy\Documents\trading` |
| Branch | `master` |
| M047 frozen baseline | `3ecd75e68d6cac5c6c6661376684a3eba3045f4b` |

## 3. Command Shape

`Campaign.cancel()`'s own actual signature is `cancel(self, *, actor, occurred_at, reason=None, correlation_id=None)` — no `disposition`-equivalent field, `reason` genuinely optional at the Python-signature level (the state-dependent requirement is enforced inside the method body, not the signature). The command mirrors this exactly, adding only the two universal command-level fields every prior milestone has required (`identity`, `expected_persisted_version`):

```python
@dataclass(frozen=True, slots=True)
class CancelCampaignCommand:
    identity: DomainIdentity[CampaignId]
    expected_persisted_version: AggregateVersion
    actor: str
    occurred_at: datetime
    reason: str | None = None
    correlation_id: str | None = None
```

Six fields. Not copying `CompleteReviewCommand`'s shape (which has a mandatory `disposition` and mandatory `final_disposition_rationale` — `cancel()` has neither) or `PrepareCampaignForAuthorizationCommand`'s shape verbatim (field order differs: `reason` before `correlation_id` here, matching `cancel()`'s own parameter order, whereas `prepare_for_authorization()` orders `correlation_id` before `reason`).

## 4. Handler Shape

```python
class CancelCampaignHandler:
    __slots__ = ("_campaign_repository",)

    def __init__(self, *, campaign_repository: CampaignRepository) -> None:
        self._campaign_repository = campaign_repository

    def handle(self, command: CancelCampaignCommand) -> SaveResult:
        loaded = self._campaign_repository.get(command.identity)
        campaign = loaded.aggregate
        campaign.cancel(
            actor=command.actor,
            occurred_at=command.occurred_at,
            reason=command.reason,
            correlation_id=command.correlation_id,
        )
        return self._campaign_repository.save(
            campaign, expected_persisted_version=command.expected_persisted_version
        )
```

Sole dependency: `CampaignRepository`. Exactly one `.get(`, one `.cancel(`, one `.save(` — identical load-mutate-save shape to every prior command (M030-M046), differing only in which domain method is invoked and which repository is used.

## 5. Identity and Expected-Version Semantics

`command.identity` passed to `get()` unchanged. `command.expected_persisted_version` — never `loaded.persisted_version` — passed to `save()`. Both to be independently re-verified via a non-tautological adversarial script during implementation's own hostile self-audit, mirroring M046's own technique.

## 6. Validation Ownership

All domain validation — the five-state `allowed_states` check, the state-dependent conditional `reason` requirement, `actor`/`occurred_at`/`correlation_id` presence checks — lives entirely inside `Campaign.cancel()` (evaluated first) and `_transition()` (evaluated second, structurally unreachable to disagree with `cancel()`'s own state check since both consult the identical `allowed_states` tuple). The command performs zero business validation at construction, mirroring M046: `CancelCampaignCommand(reason=None, ...)` is always constructible regardless of what state the identified Campaign is actually in — only `Campaign.cancel()` itself, once invoked against a loaded aggregate, decides whether `None` is acceptable.

## 7. Repository Interaction Sequence

1. Receive `CancelCampaignCommand`.
2. `campaign_repository.get(command.identity)` exactly once.
3. `campaign.cancel(actor=..., occurred_at=..., reason=..., correlation_id=...)` exactly once.
4. `campaign_repository.save(campaign, expected_persisted_version=command.expected_persisted_version)` exactly once.
5. Return the exact `SaveResult`, unchanged.

No second `get()`/`save()`, no retry, no transaction orchestration, no second capability.

## 8. Error Propagation

No `try`/`except` anywhere in the handler. Five distinct failure scenarios must propagate transparently, unmodified:

1. `AggregateNotFound` from `get()` (missing Campaign).
2. Domain `ValueError` from `cancel()`/`_transition()` — Campaign in a state outside the five allowed states (`READY_FOR_AUTHORIZATION`... wait, that is allowed; the disallowed states are `COMPLETED` and `CANCELLED`, the two terminal states).
3. Domain `TypeError` from `cancel()` — cancelling from `AUTHORIZED`/`ACTIVE`/`SUSPENDED` with `reason=None`.
4. Domain `ValueError` from `cancel()`/`_require_non_empty` — cancelling with an empty-string `reason` (whether required or merely present).
5. `OptimisticConcurrencyConflict` from `save()` (stale `expected_persisted_version`).

Scenarios 2-4 are genuinely distinct from every prior milestone's error surface: M030-M046 each had exactly one non-conflict domain failure mode (a single `ValueError` for wrong state, occasionally a second `ValueError` for a missing precondition like M046's empty findings). `cancel()` is the first transition with three distinct non-conflict domain failure modes, two of which (`TypeError` for missing-when-required `reason`, `ValueError` for present-when-must-be-empty `reason`) depend on which of the five allowed states the aggregate started in.

## 9. Result Contract

`SaveResult`, returned exactly as received from `CampaignRepository.save()` — no wrapping, no reconstruction. To be independently re-verified via an `is`-identity check.

## 10. Transaction Ownership

The handler owns no transaction, retry, or unit-of-work construct. `PostgresCampaignRepository.save()`'s own `unit_of_work()` context manager (frozen since M023) is the sole transactional boundary.

## 11. `CommandEntryPoint` Binding

`CommandEntryPoint(CancelCampaignHandler(...))` must work unmodified, mirroring every prior command handler's binding.

## 12. Architecture Impact

None. `usecases` already permits `campaign` in `ALLOWED["usecases"]` since M030. `python tools/check_architecture.py .` must remain exit 0 with zero fixture change.

## 13. Real Conflict Mechanism — the Central Design Decision

`Campaign.revise_scope_statement()` (M032's own frozen interfering write) requires `state is DRAFT` and does not call `_transition()` — it never changes `_state`, only `_scope_statement` and `_version`. `cancel()`'s own `allowed_states` includes `DRAFT`. Therefore: a Campaign in `DRAFT`, cancelled by a stale caller while an independently-loaded interferer calls `revise_scope_statement()` first, should reach a genuine, unqualified `OptimisticConcurrencyConflict` — the interferer's write leaves `state=DRAFT` (still within `cancel()`'s own allowed set) and only advances `version`, so the stale caller's own `cancel()` call still passes its own domain preconditions and only fails at the `save()` layer's version guard. This mirrors M032's own already-proven mechanism exactly, but is applied here to a new target transition (`cancel()` instead of `prepare_for_authorization()`) and must be empirically re-confirmed during implementation, not assumed by analogy (per this project's established discipline: M039, M040, M045, M046 each independently confirmed rather than assumed their own conflict mechanisms).

## 14. Test Strategy

- **Unit/contract**: identity/version pass-through (non-tautological), no second `get()`/`save()`, no `add()` call, `SaveResult` identity pass-through, transparent propagation of all five failure scenarios (Section 8) including two adversarially-chosen exception types beyond the domain's own vocabulary, and structural `CommandHandler` conformance.
- **PostgreSQL integration**: golden-path cancellation from `DRAFT` (directly reachable via the existing, frozen M030 `CreateCampaignHandler`); golden-path cancellation from `AUTHORIZED` (reached via direct domain-method calls on an independently loaded aggregate as test setup only — `record_authorization()`/`activate()` have no production command yet, so this milestone's own test fixtures call them directly, exactly as M046's own fixtures called the frozen M044/M045 handlers, except here no handler exists yet for these intermediate Campaign states, so the aggregate methods are invoked directly and persisted via the repository's own `save()`, never fabricated); invalid-state rejection (from `COMPLETED`); missing-`reason`-when-required rejection (from `AUTHORIZED`, `reason=None`); missing-Campaign rejection (`AggregateNotFound`); genuine `OptimisticConcurrencyConflict` reproduction (Section 13).

## 15. Rejected Alternatives

- A `disposition`-style field mirroring `CompleteReviewCommand` — rejected, `cancel()`'s own signature has no such parameter.
- Making `reason` mandatory at the command level — rejected, would misrepresent `cancel()`'s own conditional-optionality signature and would force every caller (including `DRAFT`/`READY_FOR_AUTHORIZATION` cancellations, where `reason` may legitimately be omitted) to always supply one.

## 16. Risks

The two-branch conditional validation (Section 8, scenarios 3-4) must be tested from at least one state in each branch (`DRAFT` for the optional branch, `AUTHORIZED` for the required branch) to avoid a false claim of full precondition coverage — carried forward from the scope document's own Section 13 risk disclosure.

## 17. M048 Boundary

This design resolves exactly one MILESTONE-047 capability. No MILESTONE-048 capability, terminology, sequencing decision, or forward commitment is made anywhere in this document.

## 18. Status

**CANDIDATE_INTERNAL_MACRO_DESIGN.**
