# MILESTONE-032 - Concrete Application Command Vertical Slice (Campaign Lifecycle Transition) Implementation Freeze

## 1. Document Status

**Status: APPROVED_AND_FROZEN**

This document records the owner's formal freeze of the MILESTONE-032 implementation following a hostile independent implementation review. MILESTONE-032 is now fully and completely frozen at every stage: scope, design, and implementation.

---

## 2. Repository Authority

| Field | Value |
| --- | --- |
| Repository | `C:\Users\LuxSy\Documents\trading` |
| Branch | `master` |
| Authoritative HEAD at freeze | `8db4febca15299861103c26f716d19b3a5d5bd29` |
| Milestone | MILESTONE-032 |

---

## 3. Frozen Predecessor Chain

| Milestone | Status |
| --- | --- |
| M020-M029 | APPROVED_AND_FROZEN |
| M030 | APPROVED_AND_FROZEN (scope, design, implementation) |
| M031 | APPROVED_AND_FROZEN (scope, design, implementation — implementation freeze commit `f144c963f6bcf90a8ada5cf14853fce5e73d48d8`) |

---

## 4. M032 Scope Authority

| Field | Value |
| --- | --- |
| Scope document | `MILESTONE_032_CONCRETE_APPLICATION_COMMAND_VERTICAL_SLICE_CAMPAIGN_LIFECYCLE_TRANSITION_SCOPE.md` |
| Scope candidate commit | `5ea62d02d65945f0976e42b8c011217d895723e4` |
| Status | `APPROVED_AND_FROZEN` |

---

## 5. M032 Scope-Freeze Authority

| Field | Value |
| --- | --- |
| Scope freeze document | `MILESTONE_032_CONCRETE_APPLICATION_COMMAND_VERTICAL_SLICE_CAMPAIGN_LIFECYCLE_TRANSITION_SCOPE_FREEZE.md` |
| Scope freeze commit | `b18878a514694d6663026e11d98859023c04a136` |
| Status | `APPROVED_AND_FROZEN` |

---

## 6. M032 Design Authority

| Field | Value |
| --- | --- |
| Design document | `MILESTONE_032_CONCRETE_APPLICATION_COMMAND_VERTICAL_SLICE_CAMPAIGN_LIFECYCLE_TRANSITION_DESIGN.md` |
| Design candidate commit | `50f2cd829af2e10799ab3581b4c2e56e9e04d401` |
| Design correction commit | `2f48b1e4af1b039c3b2a7e3598f85e63e007b216` |
| Status | `APPROVED_AND_FROZEN` |

---

## 7. M032 Design-Freeze Authority

| Field | Value |
| --- | --- |
| Design freeze document | `MILESTONE_032_CONCRETE_APPLICATION_COMMAND_VERTICAL_SLICE_CAMPAIGN_LIFECYCLE_TRANSITION_DESIGN_FREEZE.md` |
| Design freeze commit | `14204e4c24024fa7e1d56fbf49dccef0a1fa6a58` |
| Status | `APPROVED_AND_FROZEN` |

---

## 8. Implementation Commit

**Commit:** `2901a6e7f6c305a86a8ba7635a436c9299433519` (`feat: implement M032 campaign authorization preparation usecase`)

**Scope:** exactly 7 files (2 production, 3 new tests, 1 implementation-evidence document, 1 modified governance checkpoint) — verified via `git show --stat` against the actual commit.

---

## 9. Finalization Commit

**Commit:** `8db4febca15299861103c26f716d19b3a5d5bd29` (`docs: finalize M032 implementation review package`)

A narrow, docs-only follow-up recording the implementation commit's own hash in `PROJECT_CHECKPOINT.md` and the implementation evidence document. No production behavior changed — verified via `git show --stat` (2 files, both governance documents only).

---

## 10. Independent Hostile Implementation-Review Decision

**Decision: M032 IMPLEMENTATION APPROVED FOR OWNER FREEZE.**

The independent hostile review did not trust the implementation's own claims. It independently verified: repository truth; the exact 7-file (implementation) + 2-file (finalization) change-scope lineage; frozen design conformance against the actual production source, not the implementation document's own claims; the command and handler contracts field-for-field against `Campaign.prepare_for_authorization()`'s real signature; caller-supplied expected-version semantics (confirmed via the explicit unit test proving `save()` receives `command.expected_persisted_version`, never `loaded.persisted_version`); transparent error propagation with zero `try`/`except` in the production module; the unit and contract test suites for genuine (non-tautological) rigor; a **real PostgreSQL success path**; a **real, deterministic optimistic-concurrency conflict path** (independently reproduced against a fresh Docker container, confirming `revise_scope_statement()` as the interfering write genuinely reaches `OptimisticConcurrencyConflict` exactly as the corrected design specifies); the invalid-transition path; the unmodified architecture checker (0 violations on the real tree, all 7 pre-existing fixtures still triggering); mypy (89 source files); the build and wheel contents; security scripts (pip-audit clean, secret scan target discovery succeeding); the external-review ZIP's manifest and structural integrity from a fresh extraction; governance truth; and the absence of any scope creep, hidden capability, or M033 leakage. No CRITICAL or MAJOR finding. No correction required.

---

## 11. Implementation Surface

**New module:** `src/empirical_platform/usecases/prepare_campaign_for_authorization.py` (43 lines) — `PrepareCampaignForAuthorizationCommand`, `PrepareCampaignForAuthorizationHandler`.

**Modified file:** `src/empirical_platform/usecases/__init__.py` — export-only extension, mirroring the existing M030/M031 pattern exactly.

No other production file was created, modified, or deleted.

---

## 12. Frozen Command Contract

```python
@dataclass(frozen=True, slots=True)
class PrepareCampaignForAuthorizationCommand:
    identity: DomainIdentity[CampaignId]
    expected_persisted_version: AggregateVersion
    actor: str
    occurred_at: datetime
    correlation_id: str | None = None
    reason: str | None = None
```

Immutable, slots-based. Exactly six fields, no more, no fewer.

---

## 13. Frozen Handler Contract

```python
class PrepareCampaignForAuthorizationHandler:
    __slots__ = ("_campaign_repository",)

    def __init__(self, *, campaign_repository: CampaignRepository) -> None:
        self._campaign_repository = campaign_repository

    def handle(self, command: PrepareCampaignForAuthorizationCommand) -> SaveResult:
        loaded = self._campaign_repository.get(command.identity)
        campaign = loaded.aggregate
        campaign.prepare_for_authorization(
            actor=command.actor,
            occurred_at=command.occurred_at,
            correlation_id=command.correlation_id,
            reason=command.reason,
        )
        return self._campaign_repository.save(
            campaign, expected_persisted_version=command.expected_persisted_version
        )
```

Single dependency (`CampaignRepository`), constructor injection. Structurally satisfies `CommandHandler[PrepareCampaignForAuthorizationCommand, SaveResult]` — no inheritance. Synchronous only.

---

## 14. Identity Semantics

`command.identity` — the full `DomainIdentity[CampaignId]` object — is passed to `CampaignRepository.get()` unchanged. Proven by object-identity assertion (`repository.get_calls[0] is command.identity`), not merely equality.

---

## 15. Expected-Version Semantics

`command.expected_persisted_version` is passed unchanged to `save()`. **Never** derived from or compared against `loaded.persisted_version`. This is the design's single most load-bearing decision, and it is explicitly proven — not merely asserted — by `test_save_receives_command_version_not_loaded_persisted_version`, which constructs a `LoadedAggregate` with a *deliberately different* `persisted_version` than the command's `expected_persisted_version` and asserts the command's own value (by object identity) reaches `save()` unchanged.

---

## 16. Exact Load-Mutate-Save Sequence

```
1. loaded = campaign_repository.get(command.identity)          # exactly one get() call
2. campaign = loaded.aggregate
3. campaign.prepare_for_authorization(                          # exactly one mutation call
       actor=command.actor, occurred_at=command.occurred_at,
       correlation_id=command.correlation_id, reason=command.reason,
   )
4. result = campaign_repository.save(                            # exactly one save() call
       campaign, expected_persisted_version=command.expected_persisted_version,
   )
5. return result
```

Verified by direct source inspection (exactly one `.get(`, one `prepare_for_authorization(`, one `.save(` in the entire production module) and by unit tests. `save()` is never reached if the domain mutation raises.

---

## 17. Return Contract

The exact `SaveResult` object produced by `save()` is returned unchanged — proven by object-identity assertion (`result is save_result`).

---

## 18. Optimistic-Concurrency Behavior

Fully transparent propagation. `OptimisticConcurrencyConflict` propagates through the handler and the unmodified `CommandEntryPoint` with exact instance identity preserved. No handler-level `try`/`except`. No retry. Exactly one `save()` attempt.

---

## 19. Domain and Repository Error Behavior

`AggregateNotFound`, domain `ValueError`/`TypeError` from `prepare_for_authorization()`, `OptimisticConcurrencyConflict`, `InvalidAggregateForPersistence`, and `InvalidPersistedAggregateState` all propagate with exact exception-instance identity preserved. No wrapping, translation, suppression, nullable result, or envelope of any kind.

---

## 20. Validation Ownership

Zero validation logic in the command or handler. All domain-precondition and format validation is owned entirely by `Campaign.prepare_for_authorization()`, `DomainIdentity`/`Identifier`, and `AggregateVersion` — all unmodified, already-frozen types. Verified: `test_command_construction_performs_no_business_validation` confirms an empty-string `actor` is accepted at construction (no duplicated check).

---

## 21. Transaction Non-Ownership

No application-level transaction orchestration. No `run_composed()`. `get()` and `save()` each retain their own independent, unmodified `unit_of_work()` behavior — verified directly against the concrete `PostgresCampaignRepository` source.

---

## 22. CommandEntryPoint Binding

`CommandEntryPoint(PrepareCampaignForAuthorizationHandler(...))` constructed directly, in tests only. No registry, command bus, dispatcher, mediator, service locator, or DI framework. No production composition root.

---

## 23. Architecture Preservation

**Zero change to `tools/check_architecture.py`.** Verified: the real source tree (now including the new module) passes the unmodified checker with 0 violations; all 7 pre-existing `usecases`-scoped illegal-import fixtures still trigger, unmodified; no new fixture added.

---

## 24. PostgreSQL Success Evidence

`test_golden_path_transitions_campaign_via_command_entry_point_and_real_repository`: persists a Campaign via M030's `CreateCampaignHandler` (`DRAFT`, version 0); invokes the command through `CommandEntryPoint` with `expected_persisted_version=AggregateVersion(0)`; verifies `SaveResult.operation == UPDATED` and `SaveResult.persisted_version == AggregateVersion(1)`; independently reloads and verifies `state == READY_FOR_AUTHORIZATION`, the persisted version, and the transition record's `actor`/`correlation_id`/`reason`. **Independently reproduced by the reviewer against a fresh PostgreSQL container — PASS.**

---

## 25. PostgreSQL Conflict Evidence

`test_stale_expected_version_raises_optimistic_concurrency_conflict`: the exact frozen scenario —

1. Seed a Campaign at `DRAFT`, persisted version 0.
2. Independently reload the same identity; call `Campaign.revise_scope_statement(...)` on the separate in-memory object; `save()` it with `expected_persisted_version=AggregateVersion(0)` — succeeds, advancing the row to version 1 while preserving `DRAFT` (explicitly verified by a reload assertion before the command under test runs).
3. Invoke `PrepareCampaignForAuthorizationCommand` through `CommandEntryPoint` with the now-stale `expected_persisted_version=AggregateVersion(0)`.
4. The handler's own `get()` returns the current (`DRAFT`, version 1) Campaign; `prepare_for_authorization()` succeeds in memory; `save()` is rejected by the database's atomic version-guarded `UPDATE` — `OptimisticConcurrencyConflict` is raised with `expected_persisted_version == AggregateVersion(0)` and `actual_persisted_version == AggregateVersion(1)`.
5. No retry, no second `save()`.
6. Reload confirms the database still reflects only the interfering write.

**Independently reproduced by the reviewer against a fresh PostgreSQL container — PASS.** This confirms the design correction (M032-DESIGN-REVIEW-0001) resolved a genuine, reproducible gap, not merely a documentation concern. `revise_scope_statement()` remains test setup only — confirmed absent from all production code by direct grep.

---

## 26. PostgreSQL Invalid-Transition Evidence

`test_invalid_transition_raises_domain_error_without_persisting`: invokes the command successfully once (`DRAFT → READY_FOR_AUTHORIZATION`); invokes it again against the same identity; verifies the aggregate's own `ValueError` propagates unchanged; reloads and confirms no further write occurred. **PASS.**

No migration or schema change was required or introduced for any scenario.

---

## 27. External Review Package Verification

Independently re-verified by the reviewer, not merely re-asserted: ZIP opens cleanly, 78 entries, no traversal/absolute paths, no duplicates, no self-inclusion; all 77 manifest hashes verified against a fresh extraction — 0 failures; `complete.diff` confirmed to match the true `git diff 06f1284..8db4feb` exactly; extracted `source/`, `tests/`, `governance/` confirmed byte-identical to the live repository; no secrets, credentials, caches, venvs, or build debris found.

---

## 28. Validation Summary

| Gate | Result |
| --- | --- |
| Python | 3.13.14 |
| Focused M032 tests (unit + contract) | 22 passed |
| Focused M032 PostgreSQL integration | 3 passed |
| Full `pytest` suite, no PostgreSQL opt-in | 522 passed, 119 skipped, coverage 83.18% |
| Full `pytest` suite, real PostgreSQL | 635 passed, 6 skipped, coverage 91.98% |
| Full integration regression, real PostgreSQL | 113 passed, 6 skipped |
| mypy strict | 89 source files, 0 issues |
| Ruff format/lint | 204 files formatted, 0 lint issues |
| Architecture checker (real tree) | 0 violations |
| Architecture checker (fixtures) | all pre-existing violations trigger, unmodified |
| Build | sdist and wheel built, new module present in wheel |
| Security — pip-audit | no known vulnerabilities |
| Security — secret scan targets | 355 targets discovered |

All counts independently reproduced by the reviewer, not copied from the implementation's own claims.

---

## 29. Changed-File Summary

Both commits combined — exactly 7 files:

```
A  MILESTONE_032_CONCRETE_APPLICATION_COMMAND_VERTICAL_SLICE_CAMPAIGN_LIFECYCLE_TRANSITION_IMPLEMENTATION.md
M  PROJECT_CHECKPOINT.md
M  src/empirical_platform/usecases/__init__.py
A  src/empirical_platform/usecases/prepare_campaign_for_authorization.py
A  tests/contract/test_prepare_campaign_for_authorization_handler_contract.py
A  tests/integration/test_m032_prepare_campaign_for_authorization_usecase.py
A  tests/unit/test_prepare_campaign_for_authorization_usecase.py
```

No source, test, checker, schema, migration, or M020-M031 file touched outside this list.

---

## 30. No-Scope-Creep Declaration

Verified directly: no second Campaign mutation command; no retry/backoff/conflict-recovery policy; no composition root, registry, dispatcher, mediator, or service locator; no transport layer; no `Run`/`EvidencePackage`/`Review` command or query; no MILESTONE-033 identifier, module, or reference anywhere in the diff. Every Campaign mutation method other than `prepare_for_authorization()` is confirmed absent from production code (`revise_scope_statement()` appears only in the integration test's interfering-write setup).

---

## 31. Owner Freeze Declaration

I, the owner, declare the MILESTONE-032 implementation, as committed at `2901a6e7f6c305a86a8ba7635a436c9299433519` and finalized at `8db4febca15299861103c26f716d19b3a5d5bd29`, **APPROVED AND FROZEN** effective immediately upon this record.

**M032 IMPLEMENTATION APPROVED_AND_FROZEN**

No further change to the frozen implementation is permitted without explicit owner re-authorization, documented reason, independent review where material, and a new governance commit.

---

## 32. Preserved M020-M031 Authority

`git diff --name-status` across the entire M032 implementation-mission lineage returns empty for every M020-M031 source, test, and governance path. `Campaign`, `CampaignRepository`, `PostgresCampaignRepository`, `CommandHandler`, `CommandEntryPoint`, `AggregateVersion`, `LoadedAggregate`, `SaveResult`, `OptimisticConcurrencyConflict`, and `src/empirical_platform/usecases/create_campaign.py`/`get_campaign.py` are all byte-identical to their state at the M032 design freeze. No database schema or Alembic migration changed.

---

## 33. Deferred Work

- Retry-on-`OptimisticConcurrencyConflict` policy — now unblocked by this milestone's own completion, but not itself in scope.
- Any additional Campaign mutation command (`record_authorization`, `activate`, `suspend`, `resume`, `complete`, `cancel`, `revise_scope_statement` as its own production use case).
- Any command or query for `Run`, `EvidencePackage`, or `Review`.
- Any composition-root abstraction beyond direct binding.
- Any transport/entrypoint adapter.
- MILESTONE-033 and beyond.

---

## 34. Final Status

```
M032_SCOPE_STATUS=APPROVED_AND_FROZEN
M032_DESIGN_STATUS=APPROVED_AND_FROZEN
M032_IMPLEMENTATION_STATUS=APPROVED_AND_FROZEN
M032_STATUS=APPROVED_AND_FROZEN
```

M020-M031 remain unchanged and untouched throughout M032's entire lifecycle.

---

## 35. Next Permitted Action

**MILESTONE-033 SCOPE SELECTION.**

This freeze record does NOT authorize:

- Any further M032 implementation change without the re-authorization process in Section 31.
- Any MILESTONE-033 design or implementation (only scope selection is authorized next).

---

## 36. Final Status

```
═══════════════════════════════════════════════════════════════════════════════

              MILESTONE-032 FULLY FROZEN

═══════════════════════════════════════════════════════════════════════════════

M032 CONCRETE APPLICATION COMMAND VERTICAL SLICE (CAMPAIGN LIFECYCLE TRANSITION)

Scope:            APPROVED_AND_FROZEN
Design:           APPROVED_AND_FROZEN
Implementation:   APPROVED_AND_FROZEN

Implementation commit:        2901a6e7f6c305a86a8ba7635a436c9299433519
Finalization commit:          8db4febca15299861103c26f716d19b3a5d5bd29
Implementation freeze commit: (recorded in a following governance commit)

M020-M031:  UNCHANGED, ALL REMAIN APPROVED_AND_FROZEN
M032:       FULLY APPROVED_AND_FROZEN
M033:       NOT_STARTED

NEXT PERMITTED ACTION: MILESTONE-033 SCOPE SELECTION

═══════════════════════════════════════════════════════════════════════════════
```
