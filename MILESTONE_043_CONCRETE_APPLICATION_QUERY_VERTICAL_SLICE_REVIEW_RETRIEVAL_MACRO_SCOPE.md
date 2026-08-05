# MILESTONE-043 - Concrete Application Query Vertical Slice: Review Retrieval - Macro Scope

## 1. Document Status

**Status: CANDIDATE_INTERNAL_MACRO_SCOPE**

Produced under the Macro Milestone Protocol (M035 implementation freeze, Section 49; PROJECT_CHECKPOINT.md Section 31) as part of one consolidated M043 mission (scope + design + implementation in a single pass).

## 2. Repository Authority

| Field | Value |
| --- | --- |
| Repository | `C:\Users\LuxSy\Documents\trading` |
| Branch | `master` |
| M043 frozen baseline (M042 Owner Freeze hash-recording HEAD) | `be1a5995bab1ea5a65499835999b0a0595aa4075` |

## 3. Frozen Predecessor Chain

M020-M042 all `APPROVED_AND_FROZEN` at every stage. `Review` has exactly one frozen application-layer capability: creation, via `CreateReviewCommand`/`CreateReviewHandler` (M042, `MILESTONE_042_REVIEW_CREATION_MACRO_MILESTONE_FREEZE.md`).

## 4. Fresh, Complete Architecture Inventory

A from-scratch inventory (not assumed from any prior milestone's conclusions) of `src/empirical_platform/usecases/*.py`:

```
authorize_run.py, create_campaign.py, create_evidence_package.py,
create_review.py, create_run.py, get_campaign.py, get_evidence_package.py,
get_run.py, prepare_campaign_for_authorization.py,
record_evidence_package_artifact_reference.py,
record_evidence_package_criterion_result.py, seal_evidence_package.py,
start_evidence_package_collection.py
```

13 modules. Capability matrix, independently re-derived by cross-referencing every module against every aggregate:

| Aggregate | create/add | retrieve/get | transition/save | owned-collection append | conflict evidence |
| --- | --- | --- | --- | --- | --- |
| Campaign | M030 | M031 | M032 | — | M032 |
| Run | M033 | M034 | M035 | — | M035 |
| EvidencePackage | M036 | M037 | M038, M041 | M039, M040 | M041 |
| Review | M042 | **none** | **none** | **none** | **none** |

`Review` is the **only** aggregate in the entire domain model with zero query-side (`QueryHandler`) proof of any kind. Every other aggregate already has both a frozen `add`/`create` command and a frozen `get`/retrieve query. This is the same category of gap — "zero proof of an entire verb category" — that justified M042's own selection (Review then had zero proof of any *command* verb); M043 closes the symmetric gap on the *query* side.

## 5. Review Aggregate — Fully Re-Inspected Live

Fresh full read of `src/empirical_platform/review/aggregate.py` (316 lines) and `src/empirical_platform/review/lifecycle.py`:

- `Review.__init__(identity, target, reviewer)` — unconditional `ASSIGNED` initial state, `version = AggregateVersion.initial()`, empty `findings`/`transition_history`, `disposition = None`.
- `start()` — single-precondition transition, `ASSIGNED -> IN_PROGRESS`.
- `add_finding()` — owned-collection append, requires `IN_PROGRESS`; bumps `version` but does **not** call `_transition()` and does **not** append a `StateTransitionRecord` (no `from_state`/`to_state` pair — findings are not a lifecycle transition).
- `complete()` — two-precondition transition (`IN_PROGRESS` state **and** non-empty `findings`), `IN_PROGRESS -> COMPLETED`, sets `disposition`/`final_disposition_rationale`.
- `cancel()` — transition from either `ASSIGNED` or `IN_PROGRESS` to `CANCELLED`, sets `cancellation_reason`.

## 6. Review Infrastructure — Fully Re-Verified Live, Already Frozen

`ReviewRepository.get()` (Protocol, M020) and `PostgresReviewRepository.get()` (concrete adapter, M023) are both already frozen and fully implemented — fresh read of `review_repository.py` lines 124-190 confirms `get()` performs a complete reconstruction (root row + `review_finding` rows + `review_transition` rows) with the identical `AggregateNotFound`/`InvalidPersistedAggregateState` error semantics already proven for every other aggregate's `get()`. **Zero infrastructure gap** — identical starting condition to M031 (Campaign), M034 (Run), and M037 (EvidencePackage), each of which required no repository, mapper, or migration work.

## 7. Why Review Retrieval Was Not Selected At M042 — Verified, Not Assumed

M042's own scope document evaluated only command-side candidates (Review creation was itself the selection). No prior scope document evaluated Review retrieval, because before M042, no `Review` existed anywhere in the persisted domain to retrieve — retrieval only became a coherent, testable capability once creation existed. This is confirmed, not assumed: `git log -p -- src/empirical_platform/usecases/get_review.py` returns nothing (the file has never existed at any prior commit).

## 8. Candidates Considered

1. **Review retrieval (`GetReviewQuery`/`GetReviewHandler`)** — selected. Closes the only remaining zero-proof verb category in the domain model. Zero infrastructure gap. No sequencing prerequisite on any other new capability.
2. **Review's first lifecycle transition, `start()` (`ASSIGNED -> IN_PROGRESS`)** — rejected as lower-leverage. This would be the *fifth* instance of the already four-times-proven "single-precondition, newly-created-aggregate, first transition" pattern (M032 Campaign, M035 Run, M038 EvidencePackage-start-collection, and structurally M041 EvidencePackage-seal's third precondition is state-based too) — pure repetition, zero new architectural proof, exactly the same "already four-times-proven pattern" reasoning that has repeatedly deprioritized `EvidencePackage.invalidate()` in every scope document since M038.
3. **Review finding recording (`add_finding()`)** — rejected: `add_finding()` requires the Review to already be `IN_PROGRESS`, which requires `start()` to exist and be exercised first. Selecting this without also implementing `start()` would violate "one capability only" (two commands) or leave an untestable precondition (no way to reach `IN_PROGRESS` at the application layer).
4. **Review completion/disposition (`complete()`)** — rejected: requires **both** `IN_PROGRESS` state (via `start()`) **and** non-empty `findings` (via `add_finding()`) — a two-capability sequencing prerequisite, the deepest dependency chain of any candidate considered.
5. **`EvidencePackage.invalidate()`** — re-evaluated a fifth time, rejected again on the identical grounds recorded in every scope document since M038: repeats an already-proven single-precondition-transition pattern on a fully-proven aggregate.
6. **Retry-on-conflict policy** — rejected: no command-level retry abstraction exists anywhere in this codebase by deliberate design (every freeze record's "Deferred Work" section lists this); introducing one now would be a framework decision far exceeding "one concrete vertical slice," explicitly out of scope for the Macro Milestone Protocol's "no architecture redesign" rule.
7. **Composition root / registry / dispatcher** — rejected: explicitly deferred in every milestone since M025; direct constructor injection remains this project's frozen, deliberate pattern.
8. **Transport-neutral invocation (HTTP/API layer)** — rejected: no transport layer exists anywhere in this codebase; introducing one is a framework-level decision, not a vertical slice.
9. **Audit/governance runtime** — rejected: `audit`/`governance` packages are empty placeholder namespaces (confirmed, Section 4 of the M042 scope document's own inventory, unchanged since); populating either is a new subsystem, not a vertical slice.
10. **Registry/dispatcher for command/query handlers** — rejected: identical reasoning to Candidate 7; `CommandEntryPoint`/`QueryEntryPoint` direct binding remains the frozen pattern (M027/M029).

## 9. Selected M043 Scope

One concrete query retrieving an existing `Review` by full identity, returning a bounded, immutable `ReviewSnapshot` — the fourth proof of the `get()`-retrieval pattern (after M031 Campaign, M034 Run, M037 EvidencePackage), and the first `QueryHandler`-side proof of any kind for `Review`.

## 10. Why This Scope Is Next

After M043, every aggregate in the domain model (`Campaign`, `Run`, `EvidencePackage`, `Review`) will have both a frozen `add`/`create` command and a frozen `get`/retrieve query — closing the last "zero verb-category proof" gap anywhere in the system. No lifecycle-transition candidate (Section 8, items 2-4) is selectable without either violating "one capability only" or leaving an unreachable precondition; retrieval has no such sequencing dependency and requires zero new infrastructure.

## 11. In-Scope Capability

Retrieve one existing `Review` by its full frozen `DomainIdentity[ReviewId]`, returning a bounded snapshot (identity, target `EvidencePackageId`, reviewer reference, lifecycle state).

## 12. Out-of-Scope Capabilities

`Review.start()`/`add_finding()`/`complete()`/`cancel()`; `EvidencePackage.invalidate()`; any retry policy; any composition root, registry, dispatcher, mediator, service locator, or DI framework; any transport/API layer; any schema/migration change; any MILESTONE-044 work.

## 13. Frozen Dependencies

`ReviewRepository.get()` (M020, Protocol); `PostgresReviewRepository.get()` (M023, concrete adapter); `QueryHandler` Protocol (M028); `QueryEntryPoint` (M029); `Review`/`ReviewTargetReference`/`ReviewerReference` (M012/M020, domain); `ReviewId`/`EvidencePackageId` (M014, identifiers); `DomainIdentity` (M017).

## 14. Open Design Questions

Exact `ReviewSnapshot` field set — resolved in the design document (Section 6/7): mirrors `EvidencePackageSnapshot`'s bounded shape (identity + FK-parent-equivalent reference + lifecycle state), excluding `findings` (unbounded owned collection, no milestone-local consumer), `disposition`/`final_disposition_rationale`/`cancellation_reason` (state-dependent, only meaningful for a subset of lifecycle states, no milestone-local consumer), `version`/`persisted_version` (aggregate/repository concurrency metadata, never exposed by any prior snapshot), and `transition_history` (unbounded, excluded by every prior snapshot).

## 15. Lifecycle Prerequisites

None. `ReviewRepository.get()` operates identically regardless of the target `Review`'s lifecycle state (`ASSIGNED`, `IN_PROGRESS`, `COMPLETED`, or `CANCELLED`) — retrieval is not gated by any state.

## 16. Architecture-Boundary Considerations

None. `usecases` already has `review` in `ALLOWED["usecases"]` (added at M042). `tools/check_architecture.py` requires zero change.

## 17. Concurrency Feasibility

Not applicable. `get()` is a pure read; no version guard, no conflict possibility, no save.

## 18. Risks

Minimal. Identical infrastructure-readiness profile to M031/M034/M037, all of which shipped with zero infrastructure gap and zero regression.

## 19. M044 Boundary

This scope document authorizes work through MILESTONE-043 only. No MILESTONE-044 capability, terminology, sequencing decision, or forward commitment is made anywhere in this document.

## 20. Governance Status

**Status: CANDIDATE_INTERNAL_MACRO_SCOPE.** Part of one consolidated M043 mission; not independently frozen.
