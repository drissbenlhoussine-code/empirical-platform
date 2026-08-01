# MILESTONE-033 - Concrete Application Command Vertical Slice (Run Creation) Scope Freeze

## 1. Milestone Identity

| Field | Value |
| --- | --- |
| Milestone | MILESTONE-033 |
| Working title | Concrete Application Command Vertical Slice (Run Creation) |
| Freeze type | Owner Scope Freeze |

## 2. Repository Authority

| Field | Value |
| --- | --- |
| Repository | `C:\Users\LuxSy\Documents\trading` |
| Branch | `master` |
| HEAD at freeze | `a01c29a30430c685a5f086ecccf4f94361f06ca8` |

## 3. Frozen Predecessor Chain

| Milestone | Status |
| --- | --- |
| M020-M029 | APPROVED_AND_FROZEN |
| M030 (Concrete Application Command Vertical Slice — Campaign Creation) | APPROVED_AND_FROZEN (scope, design, implementation) |
| M031 (Concrete Application Query Vertical Slice — Campaign Retrieval) | APPROVED_AND_FROZEN (scope, design, implementation) |
| M032 (Concrete Application Command Vertical Slice — Campaign Lifecycle Transition) | APPROVED_AND_FROZEN (scope, design, implementation — implementation freeze commit `84fcf35082aafc1a02358f2e3aa8f7de81841cc9`) |

## 4. M033 Scope Candidate Commit

`04e274240f7958d80bc0cb87f92f825b563fbd5a` (`docs: define M033 scope candidate`), hash recorded via narrow follow-up `a01c29a30430c685a5f086ecccf4f94361f06ca8` (`docs: record M033 scope candidate commit hash`).

Verified directly against the working tree: `MILESTONE_033_CONCRETE_APPLICATION_COMMAND_VERTICAL_SLICE_RUN_CREATION_SCOPE.md` is byte-identical to its content at the candidate commit (`git diff` against that commit for this file is empty).

## 5. Independent Hostile Scope-Review Decision

**M033 SCOPE APPROVED FOR OWNER FREEZE.**

The independent review verified: repository truth; the exact governance-only delta (scope document + `PROJECT_CHECKPOINT.md` only); the real absence of any Run application usecase (confirmed again in this freeze mission — zero genuine Run references in `src/empirical_platform/usecases/`, the two textual matches being `RuntimeIdentifierGenerator` substrings); Run aggregate and `RunRepository` readiness; PostgreSQL `Run` adapter readiness; the cross-aggregate dependency shape (Campaign ← Run ← EvidencePackage ← Review); Campaign-existence validation left correctly as an open design question rather than a hidden second scope; the architecture-checker impact framed as a likely narrow future extension, not a frozen decision; identity-generation questions left correctly to design; frozen-contract preservation; testability; and governance consistency. No CRITICAL, MAJOR, or blocking MINOR finding remains. No correction was required.

## 6. Verified Architectural Gap

Campaign's application-layer proof is structurally complete (`add()` — M030; `get()` — M031; `save()` with `OptimisticConcurrencyConflict` — M032). `Run`, `EvidencePackage`, and `Review` each already have frozen repository Protocols (M020) and frozen concrete PostgreSQL adapters (M023), but zero application-layer proof of any kind — independently re-verified in this freeze mission by direct repository search, not merely re-asserted from the scope document's own claims. `Run` is the least cross-aggregate-dependent of the three unproven aggregates (it references only `CampaignId`, the identifier of the one aggregate already fully proven), directly mirroring M030's own original narrowest-first reasoning.

## 7. Owner Approval

The Owner reviewed the independent scope review's conclusion and formally authorizes this Scope Freeze. **M033 SCOPE APPROVED_AND_FROZEN.**

## 8. Official Milestone Name

**MILESTONE-033: Concrete Application Command Vertical Slice (Run Creation).**

## 9. Frozen Mission Statement

Prove, with one concrete, minimal, real command, that the frozen `usecases` application-invocation pattern — established and validated exclusively against `Campaign` across M030, M031, and M032 — genuinely generalizes to a second aggregate, without introducing any Run lifecycle-transition capability, without introducing the query side, without introducing a third aggregate, and without introducing any framework, registry, or abstraction beyond what is already frozen.

## 10. Frozen In-Scope Capability

Exactly one primary capability: **one concrete application command vertical slice for creating a Run**, comprising:

- one concrete command representing "create a new Run for an existing Campaign";
- one concrete handler constructing a new `Run` and persisting it via `RunRepository.add()`;
- conformance to the frozen `CommandHandler` Protocol (M027) and invocability through the frozen `CommandEntryPoint` (M029);
- focused unit/contract/PostgreSQL integration evidence, mirroring M030's established test pattern;
- the narrowly required architecture-boundary evidence this second-aggregate extension needs.

## 11. Frozen Out-of-Scope Capabilities

- Run retrieval (any Run query).
- Any Run lifecycle-transition command.
- Any second Run command beyond this one creation capability.
- Any Campaign mutation beyond M030-M032.
- Any Campaign query beyond M031.
- Any `EvidencePackage` or `Review` usecase (command or query).
- Any retry/backoff or `OptimisticConcurrencyConflict` handling.
- Any composition root, registry, command bus, dispatcher, mediator, or service locator.
- Any dependency-injection framework.
- Any transport layer or API.
- Any audit integration.
- Any schema or migration change.
- Any market-data, vendor, trading-strategy, or empirical campaign execution behavior.
- Any MILESTONE-034 work of any kind.

## 12. Frozen Non-Goals

- This milestone is not a general-purpose "Run management" capability; it exercises exactly one operation (`add()`-based creation).
- This milestone does not decide whether `EvidencePackage`/`Review` or a Run lifecycle transition comes next — that determination belongs to a future, independently-scoped milestone.
- This milestone does not attempt to justify a composition root, transport layer, or retry policy.

## 13. Frozen Dependencies

**Depends on (frozen, read-only):** MILESTONE-020 `RunRepository` Protocol (`add()`) and `Run` aggregate; MILESTONE-023 concrete PostgreSQL `Run` repository adapter; MILESTONE-025 repository runtime composition; MILESTONE-027 `CommandHandler` Protocol; MILESTONE-029 `CommandEntryPoint`; MILESTONE-030's delivered Campaign creation vertical slice, whose pattern this milestone mirrors for a second aggregate.

**Does not depend on:** any `EvidencePackage`/`Review` material, any Campaign lifecycle-transition work beyond M032, any transport/entrypoint code, any composition-root abstraction.

## 14. Frozen Contracts Preserved

`Run` aggregate and constructor (M020); `RunRepository` Protocol, including its `add()` signature (M020); the concrete PostgreSQL `Run` repository adapter (M023); `CommandHandler` Protocol (M027); `CommandEntryPoint` (M029); everything M030/M031/M032 delivered (their concrete commands/queries/handlers, `CampaignSnapshot`, and the `usecases` package's existing architecture-checker rules for `Campaign`) — all unmodified, verified directly against the working tree in this freeze mission (Section 6 of this document; `check_architecture.py` line 29 still reads `"usecases": {"shared", "identifiers", "campaign"}` unchanged).

## 15. Open Design Questions (Explicitly Not Resolved by This Freeze)

The future Design Mission must resolve, but this freeze does **not** decide:

- exact command type name;
- exact handler type name;
- exact package/module placement;
- exact command fields and types;
- whether `RunId` is caller-supplied or generated;
- whether `RuntimeIdentifierGenerator` is used;
- how `CampaignId` is supplied;
- whether Campaign existence is validated at handler level or left to persistence;
- exact constructor dependencies;
- exact return contract;
- exact error behavior;
- exact architecture-checker extension;
- exact PostgreSQL test setup.

## 16. Architecture-Boundary Implications

A second-aggregate `usecases` extension will likely require a narrow, well-precedented future addition to `tools/check_architecture.py` (the M030 design-phase precedent added a paired `ALLOWED`/`FORBIDDEN_IMPORT_PREFIXES["usecases"]` entry when the package was first created). This freeze records the likely shape as context only — it does not select, authorize, or pre-commit to any specific checker change. The exact addition is a Design Mission determination.

## 17. Cross-Aggregate Campaign-Existence Question

Whether the Run-creation handler must verify the referenced `Campaign` exists before creating a `Run` — via an explicit `CampaignRepository.get()` call, via reliance on persistence-layer foreign-key/constraint enforcement, or via some other mechanism — is an open design question (Section 15), not a hidden second scope item. This freeze explicitly does not authorize any Campaign read, write, or validation logic as part of this milestone's own capability; any Campaign-repository interaction the design ultimately selects exists solely to support Run creation, not as an independent capability.

## 18. Identity-Generation Question

Whether the new Run's identity is supplied by the caller or generated via the frozen `RuntimeIdentifierGenerator` Protocol (mirroring M030's own precedent for Campaign) is an open design question (Section 15), not frozen here.

## 19. Acceptance Boundaries

This scope freeze is complete and design-ready because:

- exactly one write-side capability is frozen (Run creation);
- no class name, method signature, module path, dependency-injection mechanism, registry, transaction behavior, error hierarchy, or architecture-checker change is fixed;
- every excluded capability is explicit and evidence-traceable;
- the scope is independently designable without requiring the design phase to first resolve any scope-level ambiguity.

## 20. Stop Conditions

This milestone stops at: one concrete command, one concrete handler, using `Run.__init__` and `RunRepository.add()` only; proof that the `usecases`/`CommandHandler`/`CommandEntryPoint` pattern composes correctly for a second aggregate; contract, unit, architecture, and PostgreSQL integration test evidence mirroring M030's established pattern. It does not continue into any Run lifecycle transition, any Run query, any second aggregate beyond Run, composition-root work, or transport work.

## 21. Prohibited Expansion

No Run lifecycle-transition command; no Run query; no `EvidencePackage`/`Review` command or query; no composition root, registry, dispatcher, mediator, or service locator; no transport layer; no retry/backoff/idempotency policy; no MILESTONE-034 work.

## 22. Deferred Work

Any Run lifecycle-transition command (`authorize`, `start_acquisition`, `start_normalization`, `start_validation`, `complete_execution`, `cancel`, `fail`); any Run query; any additional Campaign lifecycle-transition command beyond M032; any command or query for `EvidencePackage` or `Review`; retry-on-`OptimisticConcurrencyConflict` policy; any composition-root abstraction beyond direct binding; any transport/entrypoint adapter; MILESTONE-034 and beyond.

## 23. Design and Implementation Prohibition

This freeze authorizes MILESTONE-033 **design** to begin. It does **not** authorize implementation. No production source, test, architecture-rule, schema, or migration file was touched by this freeze mission (verified in Section 6 of this document and the Validation section of the accompanying mission report). Implementation is not authorized until a design candidate exists, has passed independent hostile design review, and has been owner-frozen — matching the identical lifecycle M030, M031, and M032 each followed.

## 24. Preserved M020-M032 Authority

M020 through M032 remain `APPROVED_AND_FROZEN` at every stage, entirely untouched by this freeze mission. No frozen contract, source file, test file, governance document, schema, or migration belonging to any of those milestones was read for modification purposes or changed.

## 25. Final Status

**M033 SCOPE APPROVED_AND_FROZEN.**

## 26. Next Permitted Action

**MILESTONE-033 DESIGN MISSION.**
