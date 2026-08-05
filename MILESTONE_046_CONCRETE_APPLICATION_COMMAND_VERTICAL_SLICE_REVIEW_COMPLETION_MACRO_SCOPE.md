# MILESTONE-046 - Concrete Application Command Vertical Slice: Review Completion - Macro Scope

## 1. Document Status

**Status: CANDIDATE_INTERNAL_MACRO_SCOPE**

Produced under the Macro Milestone Protocol (M035 implementation freeze, Section 49; PROJECT_CHECKPOINT.md Section 31) as part of one consolidated M046 mission (scope + design + implementation in a single pass).

## 2. Repository Authority

| Field | Value |
| --- | --- |
| Repository | `C:\Users\LuxSy\Documents\trading` |
| Branch | `master` |
| M046 frozen baseline (M045 Owner Freeze hash-recording HEAD) | `3488fcb4fcc29e427d9244acca776fd3adac0597` |

## 3. Frozen Predecessor Chain

M020-M045 all `APPROVED_AND_FROZEN` at every stage. `Review` has exactly four frozen application-layer capabilities: creation (M042), retrieval (M043), the `ASSIGNED -> IN_PROGRESS` transition (M044), and finding recording (M045).

## 4. Fresh, Complete Architecture Inventory

A from-scratch inventory of `src/empirical_platform/usecases/*.py` (16 modules): `Review` now has `create_review.py`, `get_review.py`, `start_review.py`, and `add_review_finding.py`. It has **zero** proof of `complete()` — the sole remaining Review capability whose **full** prerequisite chain (`IN_PROGRESS` reachability **and** non-empty `findings`) is now, for the first time, simultaneously satisfiable via frozen application commands only (M044 reaches `IN_PROGRESS`; M045 populates `findings`).

`Review.aggregate` (fresh read) has exactly two remaining mutation methods: `complete()` (requires `IN_PROGRESS` **and** non-empty `findings`; state-changing, `IN_PROGRESS -> COMPLETED`, sets `disposition`/`final_disposition_rationale`), `cancel()` (requires `ASSIGNED` or `IN_PROGRESS`; state-changing, `-> CANCELLED`, sets `cancellation_reason`; no findings prerequisite, reachable since M044).

## 5. Review Aggregate — Fully Re-Inspected Live

`complete()` (fresh read): checks `state is IN_PROGRESS`, checks `findings` non-empty, validates `disposition` is a `ReviewDisposition`, validates `final_disposition_rationale` non-empty, then calls the shared `_transition()` helper (`IN_PROGRESS -> COMPLETED`, advances `version`, appends one `StateTransitionRecord`), then sets `_disposition`/`_final_disposition_rationale`. This is the first Review transition gated by **two independent preconditions simultaneously** (state **and** owned-collection non-emptiness) — architecturally identical in kind to `EvidencePackage.seal()` (M041), the only prior milestone with this exact multi-precondition-transition shape.

`ReviewDisposition` (fresh read, `review/lifecycle.py`): `ACCEPTED`, `REJECTED`, `CHANGES_REQUESTED`, `INCONCLUSIVE` — four values, already frozen since M012.

## 6. Review Infrastructure — Fully Re-Verified Live, Already Frozen

`ReviewRepository.save()`/`PostgresReviewRepository.save()` already proven for `Review` (M044, M045) — zero infrastructure gap, zero migration required.

## 7. Why Review Completion Was Not Selected At M045 — Verified, Not Assumed

M045's own scope document (Section 8, candidate 2) evaluated `complete()` and rejected it purely because it "still requires non-empty `findings`, which requires `add_finding()` to exist first" — a genuine, now-resolved sequencing prerequisite. With `add_finding()` now frozen, `complete()`'s full prerequisite chain (both `IN_PROGRESS` reachability, resolved at M044, **and** non-empty `findings`, resolved at M045) is satisfied for the first time.

## 8. Candidates Considered

1. **Review completion (`complete()`)** — selected. The only remaining Review capability whose full prerequisite chain is newly, simultaneously satisfied; the first Review transition gated by two independent preconditions at once (mirroring `EvidencePackage.seal()`'s unique architectural shape, M041); represents the terminal, real-world-central disposition-setting capability this project's Review workflow exists to reach — closing the last genuinely novel Review-lifecycle gap.
2. **Review cancellation (`cancel()`)** — rejected: reachable with no prerequisite since M044, but architecturally a repeat of the single-precondition-transition pattern `start()` already covers (no findings-non-emptiness gate, no disposition to set); selecting it now would skip past `complete()` — the capability whose full prerequisite chain M045 specifically just resolved — for no comparable architectural gain. `complete()` is preferred as the more central, more architecturally novel capability, consistent with the identical reasoning applied at M044 (preferring `start()` over `cancel()`) and M045 (preferring `add_finding()` over `cancel()`).
3. **`EvidencePackage.invalidate()`** — re-evaluated an eighth time, rejected again: single-precondition transition repeating an already-proven pattern (M032, M035, M038, M041) on a fully-proven aggregate.
4. **Retry-on-conflict policy** — rejected: no command-level retry abstraction exists anywhere in this codebase by deliberate design.
5. **Composition root / registry / dispatcher** — rejected: explicitly deferred since M025.
6. **Transport-neutral invocation (HTTP/API layer)** — rejected: no transport layer exists anywhere in this codebase.
7. **Audit/governance runtime** — rejected: both packages remain genuinely empty placeholder namespaces (re-confirmed fresh).
8. **Registry/dispatcher for command/query handlers** — rejected: identical reasoning to Candidate 5.

## 9. Selected M046 Scope

One concrete command completing an existing, `IN_PROGRESS` `Review` with non-empty `findings`, via `Review.complete()` — the fifth proof of the `get()`→mutate→`save()`/`OptimisticConcurrencyConflict` pattern (after M032, M035, M038, M044), and the second multi-precondition transition in this project's lineage (after M041 `seal()`).

## 10. Why This Scope Is Next

`complete()` is the sole remaining Review capability whose full prerequisite chain is newly satisfied. `cancel()` offers no comparable architectural novelty and is explicitly deprioritized on the same leverage grounds applied consistently since M044. This closes the last genuinely novel gap in Review's lifecycle-transition vocabulary.

## 11. In-Scope Capability

Complete an existing, `IN_PROGRESS` `Review` with non-empty `findings`, setting a final `disposition` and `final_disposition_rationale`, via `CompleteReviewCommand`/`CompleteReviewHandler`.

## 12. Out-of-Scope Capabilities

`Review.cancel()`; `EvidencePackage.invalidate()`; any retry policy; any composition root, registry, dispatcher, mediator, service locator, or DI framework; any transport/API layer; any schema/migration change; any MILESTONE-047 work.

## 13. Frozen Dependencies

`ReviewRepository.get()`/`save()` (M020); `PostgresReviewRepository.get()`/`save()` (M023); `CommandHandler` Protocol (M027); `CommandEntryPoint` (M027); `Review.complete()`/`ReviewDisposition` (M012/M015/M020, domain).

## 14. Open Design Questions

Exact `CompleteReviewCommand` field set; whether `disposition` is caller-supplied as the raw `ReviewDisposition` enum or a string requiring conversion (resolved in design: caller-supplied `ReviewDisposition` directly, mirroring how `Review.complete()`'s own signature already requires the enum type, with no intermediate string-to-enum translation needed at the application layer since no identifier-style value object exists for disposition); conflict feasibility (open, to be verified during implementation, not assumed).

## 15. Lifecycle Prerequisites

The target `Review` must be persisted, `IN_PROGRESS`, and have at least one finding. Any other state or empty `findings` raises a domain `ValueError` via `Review.complete()`'s own precondition checks.

## 16. Disposition Implications

A successful `complete()` call sets exactly one `disposition` (one of `ACCEPTED`/`REJECTED`/`CHANGES_REQUESTED`/`INCONCLUSIVE`) and one `final_disposition_rationale`, both immutable thereafter (no further Review capability in this codebase mutates them).

## 17. Duplicate Behavior

Not applicable — `complete()` is a state transition, not an owned-collection append; there is no "duplicate" concept for a single disposition-setting call. A second `complete()` attempt on an already-`COMPLETED` Review is an invalid-state call (domain `ValueError`), not a duplicate-data scenario.

## 18. Conflict Feasibility — To Be Verified During Implementation, Not Assumed

Preliminary source analysis (not yet empirically confirmed against PostgreSQL): `complete()` **changes state** (`IN_PROGRESS -> COMPLETED`), so — mirroring the exact reasoning independently applied at M038 and M044 — using `complete()` itself as the interfering write against a second `complete()` command-under-test would produce a domain `ValueError` for the second caller (its own fresh `get()` would see `COMPLETED` already, failing its own precondition before `save()`), not `OptimisticConcurrencyConflict`. However, unlike `start()` (M044), `Review` now has a **second, distinct, state-preserving mutation available** — `add_finding()` (M045) — which does not change `state` and does not conflict with `complete()`'s own preconditions (an additional finding only helps satisfy "non-empty `findings`", never hurts it). Whether `add_finding()` genuinely serves as a viable interfering write for a real, caller-driven `OptimisticConcurrencyConflict` reproduction against `complete()` — mirroring M039's own resolution (using a *different* method as the interferer) — will be determined empirically during implementation, not assumed by analogy.

## 19. Risks

Minimal. Identical infrastructure-readiness profile to M032/M035/M038/M044. The conflict-feasibility question (Section 18) is the only open empirical question, to be resolved with real evidence.

## 20. M047 Boundary

This scope document authorizes work through MILESTONE-046 only. No MILESTONE-047 capability, terminology, sequencing decision, or forward commitment is made anywhere in this document.

## 21. Governance Status

**Status: CANDIDATE_INTERNAL_MACRO_SCOPE.** Part of one consolidated M046 mission; not independently frozen.
