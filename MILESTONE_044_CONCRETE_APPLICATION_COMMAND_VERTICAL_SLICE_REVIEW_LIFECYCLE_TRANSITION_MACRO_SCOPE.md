# MILESTONE-044 - Concrete Application Command Vertical Slice: Review Lifecycle Transition - Macro Scope

## 1. Document Status

**Status: CANDIDATE_INTERNAL_MACRO_SCOPE**

Produced under the Macro Milestone Protocol (M035 implementation freeze, Section 49; PROJECT_CHECKPOINT.md Section 31) as part of one consolidated M044 mission (scope + design + implementation in a single pass).

## 2. Repository Authority

| Field | Value |
| --- | --- |
| Repository | `C:\Users\LuxSy\Documents\trading` |
| Branch | `master` |
| M044 frozen baseline (M043 Owner Freeze hash-recording HEAD) | `a2902092755bef6951e11512183240b33a463088` |

## 3. Frozen Predecessor Chain

M020-M043 all `APPROVED_AND_FROZEN` at every stage. `Review` has exactly two frozen application-layer capabilities: creation (M042) and retrieval (M043).

## 4. Fresh, Complete Architecture Inventory

A from-scratch inventory of `src/empirical_platform/usecases/*.py` (14 modules): `Review` now has `create_review.py` and `get_review.py`; it has **zero** command-side proof of `ReviewRepository.save()` or `OptimisticConcurrencyConflict` propagation. `grep` across all 14 modules confirms zero `.save(` call sites and zero `OptimisticConcurrencyConflict` references anywhere referencing `Review`. `ReviewRepository.save()` (Protocol, M020) and `PostgresReviewRepository.save()` (concrete adapter, M023) are both already frozen with zero infrastructure gap.

`Review.aggregate` (fresh read) has exactly four remaining mutation methods: `start()` (`ASSIGNED -> IN_PROGRESS`, single precondition), `add_finding()` (requires `IN_PROGRESS`, not a lifecycle transition — no `StateTransitionRecord`), `complete()` (requires `IN_PROGRESS` **and** non-empty `findings`), `cancel()` (requires `ASSIGNED` or `IN_PROGRESS`).

## 5. Review Aggregate — Fully Re-Inspected Live

`start()` (lines 168-184): checks `allowed_states=(ASSIGNED,)`, transitions to `IN_PROGRESS`, calls the shared `_transition()` helper (advances `version`, appends one `StateTransitionRecord`). No owned-collection interaction. Identical shape to `EvidencePackage.start_collection()` (M038) and `Campaign.prepare_for_authorization()` (M032): a single-precondition, newly-created-aggregate, first transition.

## 6. Review Infrastructure — Fully Re-Verified Live, Already Frozen

`ReviewRepository.save()` and `PostgresReviewRepository.save()` were both already frozen (M020/M023) with zero infrastructure gap — identical starting condition to M032 (Campaign), M035 (Run), and M038 (EvidencePackage), each of which required no repository, mapper, or migration work for their own first transition.

## 7. Why Review's First Transition Was Not Selected At M043 — Verified, Not Assumed

M043's own scope document (Section 8, candidate 2) evaluated `start()` and rejected it purely on **leverage** grounds ("lower-leverage... pure repetition, zero new architectural proof") in favor of retrieval, which closed a genuinely zero-proof verb category. That reasoning does not claim `start()` was unreachable or blocked — only that retrieval was higher-leverage *at that time*. With retrieval now frozen, `Review` genuinely has zero remaining query-side gap; the highest-leverage remaining gap has shifted to the command/write side, specifically `save()`/`OptimisticConcurrencyConflict` propagation, which `start()` is the only reachable capability to exercise (see Section 8 below for why `add_finding()`/`complete()` remain unreachable).

## 8. Candidates Considered

1. **Review's first lifecycle transition, `start()` (`ASSIGNED -> IN_PROGRESS`)** — selected. The only remaining Review capability with no unmet prerequisite (both `create` and `get` now exist), and the first proof that `save()`/`OptimisticConcurrencyConflict` generalizes to `Review` — a genuinely new architectural proof point, not a repeat of Campaign's/Run's/EvidencePackage's own already-proven generalization (each aggregate's `save()` path must still be independently proven; M032→M035→M038 proved it for three aggregates, `Review` remains unproven).
2. **Review finding recording (`add_finding()`)** — rejected: still requires `start()` to exist and be exercised first to reach `IN_PROGRESS` at the application layer (unchanged from M043's own analysis; retrieval does not resolve this prerequisite).
3. **Review completion/disposition (`complete()`)** — rejected: still requires both `start()` and `add_finding()` first — the deepest prerequisite chain of any candidate.
4. **Review cancellation (`cancel()`)** — rejected: while reachable from `ASSIGNED` directly (no prerequisite on `start()`), it is architecturally a repeat of the identical single-precondition-transition pattern `start()` already covers, and selecting it *instead of* `start()` would leave `start()` — the more real-world-central, forward-progressing transition — deferred with no clear future justification, since `cancel()` and `start()` cannot both be "the" first-transition milestone. `start()` is preferred as the more central, less terminal capability.
5. **`EvidencePackage.invalidate()`** — re-evaluated a sixth time, rejected again: still a single-precondition transition repeating an already-proven pattern on a fully-proven aggregate (`EvidencePackage.save()`/conflict already proven at M038 and M041). Lower architectural novelty than `Review.start()`, which proves `save()` generalizes to a *fourth* aggregate.
6. **Retry-on-conflict policy** — rejected: no command-level retry abstraction exists anywhere in this codebase by deliberate design; explicitly out of scope for "no architecture redesign."
7. **Composition root / registry / dispatcher** — rejected: explicitly deferred since M025; direct constructor injection remains the frozen pattern.
8. **Transport-neutral invocation (HTTP/API layer)** — rejected: no transport layer exists anywhere in this codebase.
9. **Audit/governance runtime** — rejected: both packages remain genuinely empty placeholder namespaces (re-confirmed fresh).
10. **Registry/dispatcher for command/query handlers** — rejected: identical reasoning to Candidate 7.

## 9. Selected M044 Scope

One concrete command transitioning an existing, `ASSIGNED` `Review` to `IN_PROGRESS`, via `Review.start()` — the fourth proof of the `get()`→mutate→`save()`/`OptimisticConcurrencyConflict` pattern (after M032 Campaign, M035 Run, M038 EvidencePackage).

## 10. Why This Scope Is Next

`Review` now has both `create` and `get`; the only remaining gap with no unmet prerequisite is `start()`. `add_finding()` and `complete()` remain genuinely blocked behind `start()`'s own non-existence; selecting either now would violate "one capability only" or leave an untestable precondition. `cancel()` and `EvidencePackage.invalidate()` are both lower-leverage repeats of an already-proven pattern.

## 11. In-Scope Capability

Transition an existing, `ASSIGNED` `Review` to `IN_PROGRESS`, via `StartReviewCommand`/`StartReviewHandler`.

## 12. Out-of-Scope Capabilities

`Review.add_finding()`/`complete()`/`cancel()`; `EvidencePackage.invalidate()`; any retry policy; any composition root, registry, dispatcher, mediator, service locator, or DI framework; any transport/API layer; any schema/migration change; any MILESTONE-045 work.

## 13. Frozen Dependencies

`ReviewRepository.get()`/`save()` (M020, Protocol); `PostgresReviewRepository.get()`/`save()` (M023, concrete adapter); `CommandHandler` Protocol (M027); `CommandEntryPoint` (M027); `Review.start()` (M015/M020, domain); `OptimisticConcurrencyConflict` (M020).

## 14. Open Design Questions

Exact `StartReviewCommand` field set; conflict-mechanism feasibility for `start()` specifically — resolved in the design document (Section 6): mirroring `StartEvidencePackageCollectionCommand`'s exact shape (`identity`, `expected_persisted_version`, `actor`, `occurred_at`, `correlation_id=None`, `reason=None`).

## 15. Lifecycle Prerequisites

The target `Review` must be persisted and in `ASSIGNED` state. Any other state raises a domain `ValueError` via `Review._transition()`'s precondition check.

## 16. Owned-Collection Implications

None. `start()` does not read or mutate `findings`.

## 17. Conflict Feasibility — Genuinely Determined, Not Assumed

Independently inspected `Review.aggregate` for any state-preserving mutation reachable while `ASSIGNED` (the precondition for a genuine `OptimisticConcurrencyConflict` reproduction, mirroring the exact reasoning M038's design independently discovered for `EvidencePackage.start_collection()`, Section 6.1 of that design). Finding: **no state-preserving mutation exists for a `Review` still `ASSIGNED`** — `add_finding()` requires `IN_PROGRESS` (fails on ASSIGNED before reaching any conflict), `cancel()` changes state away from `ASSIGNED`. The only reachable interfering write against an `ASSIGNED` Review is `start()` itself, which is state-changing. Consequently, exactly as with M038's `start_collection()`: **a true `OptimisticConcurrencyConflict` reproduction via genuine, caller-driven, real-PostgreSQL evidence is not achievable for `start()` specifically.** Two racing callers against the same `ASSIGNED` Review produce a **domain-level `ValueError`** (the second caller's own fresh `get()` sees `IN_PROGRESS` already, so its own `start()` call fails the precondition check before ever reaching `save()`) — this is the honest, real scenario, and is the primary PostgreSQL race scenario for this milestone. `OptimisticConcurrencyConflict` propagation itself is proven at the unit level via a fake repository (unconstrained by `Review`'s own domain preconditions), mirroring M038's identical, already-accepted resolution exactly. This is recorded as a scope-appropriate boundary, not a defect.

## 18. Risks

Minimal. Identical infrastructure-readiness profile to M032/M035/M038, all of which shipped with zero infrastructure gap. The conflict-feasibility boundary (Section 17) is a known, precedented, already-accepted pattern (M038), not a novel risk.

## 19. M045 Boundary

This scope document authorizes work through MILESTONE-044 only. No MILESTONE-045 capability, terminology, sequencing decision, or forward commitment is made anywhere in this document.

## 20. Governance Status

**Status: CANDIDATE_INTERNAL_MACRO_SCOPE.** Part of one consolidated M044 mission; not independently frozen.
