# MILESTONE-045 - Concrete Application Command Vertical Slice: Review Finding Recording - Macro Scope

## 1. Document Status

**Status: CANDIDATE_INTERNAL_MACRO_SCOPE**

Produced under the Macro Milestone Protocol (M035 implementation freeze, Section 49; PROJECT_CHECKPOINT.md Section 31) as part of one consolidated M045 mission (scope + design + implementation in a single pass).

## 2. Repository Authority

| Field | Value |
| --- | --- |
| Repository | `C:\Users\LuxSy\Documents\trading` |
| Branch | `master` |
| M045 frozen baseline (M044 Owner Freeze hash-recording HEAD) | `5d3bef4d512fef4f0360065f58fa1875d3c2f8dd` |

## 3. Frozen Predecessor Chain

M020-M044 all `APPROVED_AND_FROZEN` at every stage. `Review` has exactly three frozen application-layer capabilities: creation (M042), retrieval (M043), and the `ASSIGNED -> IN_PROGRESS` lifecycle transition (M044).

## 4. Fresh, Complete Architecture Inventory

A from-scratch inventory of `src/empirical_platform/usecases/*.py` (15 modules): `Review` now has `create_review.py`, `get_review.py`, and `start_review.py`. It has **zero** proof of `add_finding()` — the sole remaining Review capability that became reachable at the application layer only after M044 (it requires `IN_PROGRESS`, which no application command could produce before `start_review.py` existed).

`Review.aggregate` (fresh read) has exactly three remaining mutation methods: `add_finding()` (requires `IN_PROGRESS`; **now reachable**), `complete()` (requires `IN_PROGRESS` **and** non-empty `findings` — still blocked, since no findings can exist without `add_finding()`), `cancel()` (requires `ASSIGNED` or `IN_PROGRESS` — reachable, was never blocked).

## 5. Review Aggregate — Fully Re-Inspected Live

`add_finding()` (fresh read): checks `state is IN_PROGRESS`, constructs a `ReviewFinding` with an **internally auto-generated** `sequence` (never caller-supplied — `self._next_finding_sequence`, incremented after each append), advances `version`, appends to the `findings` tuple. **Does not** call `_transition()` — no `StateTransitionRecord` is appended, no state change. This is architecturally the owned-collection-append pattern (M039 `add_criterion_result`, M040 `add_artifact_reference`), the first proof of this pattern for `Review`.

**Genuine architectural difference from M039/M040, independently discovered:** `EvidencePackage.add_criterion_result()`/`add_artifact_reference()` both enforce caller-supplied-identifier duplicate rejection (`criterion_id`/`artifact_reference.value` already exists raises `ValueError`). `Review.add_finding()` has **no duplicate-detection concern by construction** — `sequence` is always internally generated, monotonically increasing, never caller-supplied, so no duplicate scenario is domain-reachable at all. This must be documented honestly, not silently omitted as if an oversight.

## 6. Review Infrastructure — Fully Re-Verified Live, Already Frozen

`ReviewRepository.save()`/`PostgresReviewRepository.save()` already proven for `Review` (M044). `review_finding` table (migration `5b58cdd7751b`) already exists with `PrimaryKeyConstraint(review_runtime_id, sequence)`, `ForeignKeyConstraint(review_runtime_id -> review.runtime_id)`, `CheckConstraint(sequence >= 1)` — zero infrastructure gap, zero migration required.

## 7. Why Review Finding Recording Was Not Selected At M044 — Verified, Not Assumed

M044's own scope document (Section 8, candidate 3) evaluated `add_finding()` and rejected it purely because it "requires the Review to already be `IN_PROGRESS`, which requires `start()` to exist and be exercised first" — a genuine, now-resolved sequencing prerequisite, not a leverage judgment. With `start()` now frozen, this is the first milestone at which `add_finding()` is reachable at the application layer at all.

## 8. Candidates Considered

1. **Review finding recording (`add_finding()`)** — selected. The only remaining Review capability whose prerequisite (`IN_PROGRESS` reachability) is newly satisfied by M044; the first proof of the owned-collection-append pattern (M039/M040's pattern) generalizing to `Review`; genuinely unlocks `complete()` as a future candidate (requires non-empty `findings`).
2. **Review completion/disposition (`complete()`)** — rejected: still requires non-empty `findings`, which requires `add_finding()` to exist first. Selecting this without `add_finding()` would violate "one capability only" or leave an untestable precondition.
3. **Review cancellation (`cancel()`)** — rejected: reachable from either `ASSIGNED` or `IN_PROGRESS` with no prerequisite, but selecting it now would skip past `add_finding()` — the capability whose prerequisite M044 specifically just resolved — for no architectural gain; `cancel()` remains a single-precondition transition repeating the pattern `start()` already covers, whereas `add_finding()` is the first owned-collection-append proof for `Review`, a genuinely novel architectural point.
4. **`EvidencePackage.invalidate()`** — re-evaluated a seventh time, rejected again: single-precondition transition repeating an already-proven pattern on a fully-proven aggregate.
5. **Retry-on-conflict policy** — rejected: no command-level retry abstraction exists anywhere in this codebase by deliberate design.
6. **Composition root / registry / dispatcher** — rejected: explicitly deferred since M025.
7. **Transport-neutral invocation (HTTP/API layer)** — rejected: no transport layer exists anywhere in this codebase.
8. **Audit/governance runtime** — rejected: both packages remain genuinely empty placeholder namespaces (re-confirmed fresh).
9. **Registry/dispatcher for command/query handlers** — rejected: identical reasoning to Candidate 6.

## 9. Selected M045 Scope

One concrete command appending a new finding to an existing, `IN_PROGRESS` `Review`, via `Review.add_finding()` — the third proof of the owned-collection-append pattern (after M039 `add_criterion_result`, M040 `add_artifact_reference`), and the first for `Review`.

## 10. Why This Scope Is Next

`add_finding()` is the sole Review capability whose prerequisite M044 specifically resolved; `complete()` remains genuinely blocked behind it; `cancel()` offers no comparable architectural novelty. This scope directly unlocks `complete()` as the next viable candidate after M045.

## 11. In-Scope Capability

Append one new finding (`text`, optional `rationale`, optional `evidence_references`) to an existing, `IN_PROGRESS` `Review`.

## 12. Out-of-Scope Capabilities

`Review.complete()`/`cancel()`; `EvidencePackage.invalidate()`; any retry policy; any composition root, registry, dispatcher, mediator, service locator, or DI framework; any transport/API layer; any schema/migration change; any MILESTONE-046 work.

## 13. Frozen Dependencies

`ReviewRepository.get()`/`save()` (M020); `PostgresReviewRepository.get()`/`save()` (M023, including `review_finding` reconstruction/persistence); `CommandHandler` Protocol (M027); `CommandEntryPoint` (M027); `Review.add_finding()`/`ReviewFinding` (M015/M020, domain).

## 14. Open Design Questions

Exact `AddReviewFindingCommand` field set; whether `sequence` is exposed to the caller (resolved in design: no — internally generated, mirroring `ReviewFinding`'s own construction); duplicate semantics (resolved: not domain-reachable, Section 5); conflict feasibility (resolved in design Section 6 — genuinely determined, not assumed).

## 15. Lifecycle Prerequisites

The target `Review` must be persisted and `IN_PROGRESS`. Any other state raises a domain `ValueError` via `Review.add_finding()`'s own precondition check.

## 16. Owned-Collection Implications

Each successful call appends exactly one `ReviewFinding` to `findings`; `sequence` is always internally derived from the aggregate's own `_next_finding_sequence` counter, never caller-supplied.

## 17. Duplicate Behavior

Not domain-reachable — see Section 5. No duplicate-`sequence` scenario can occur via the application layer under any caller input, since `sequence` is never caller-supplied.

## 18. Conflict Feasibility — To Be Verified During Implementation, Not Assumed

Preliminary source analysis (not yet empirically confirmed against PostgreSQL): unlike `start()` (M044), `add_finding()` does **not** call `_transition()` and does **not** change `state` — it is a state-preserving mutation, structurally identical in kind to `add_criterion_result()`/`add_artifact_reference()` (M039/M040), both of which achieved a genuine, unqualified `OptimisticConcurrencyConflict` reproduction against real PostgreSQL. Because `add_finding()` itself is the only reachable interfering write for an `IN_PROGRESS` Review (no second state-preserving method exists), the design must determine whether a second, independently-loaded `add_finding()` call — used as its own interfering write — genuinely reaches `save()` and triggers `OptimisticConcurrencyConflict`, or whether some other obstacle exists. This will be resolved with certainty only via actual PostgreSQL evidence during implementation (design Section 6), not asserted here by analogy.

## 19. Risks

Minimal. Identical infrastructure-readiness profile to M039/M040. The conflict-feasibility question (Section 18) is the only open empirical question, to be resolved with real evidence, not assumption.

## 20. M046 Boundary

This scope document authorizes work through MILESTONE-045 only. No MILESTONE-046 capability, terminology, sequencing decision, or forward commitment is made anywhere in this document.

## 21. Governance Status

**Status: CANDIDATE_INTERNAL_MACRO_SCOPE.** Part of one consolidated M045 mission; not independently frozen.
