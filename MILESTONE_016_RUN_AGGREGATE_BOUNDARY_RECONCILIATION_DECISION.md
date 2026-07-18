# MILESTONE-016 - Run Aggregate Boundary Reconciliation Decision

## 1. Document Control

| Field | Value |
| --- | --- |
| Document ID | MILESTONE-016 |
| Title | Run Aggregate Boundary Reconciliation Decision |
| Version | 1.0 |
| Status | BOUNDARY DECISION READY FOR INDEPENDENT REVIEW |
| Mission type | Architecture boundary decision only |
| Baseline | `91be63a212af8c1113652d8fe53c6dcdfc327e91` |
| Implementation performed | None |
| Source modified | No |
| Architecture rules modified | No |
| Schemas or migrations created | No |

## 2. Baseline

The M016 execution baseline was verified before this decision was drafted.

| Check | Required | Observed |
| --- | --- | --- |
| HEAD | `91be63a212af8c1113652d8fe53c6dcdfc327e91` | `91be63a212af8c1113652d8fe53c6dcdfc327e91` |
| Branch | `master` | `master` |
| Working tree | Clean | Clean |

## 3. Problem Statement

MILESTONE-012 defines Run as an aggregate root that owns Dataset Manifest records. MILESTONE-013 implemented `DatasetManifest` as an immutable primitive in `empirical_platform.datasets`, while Run lifecycle primitives currently live in `empirical_platform.campaign`. The architecture checker currently permits `datasets -> campaign`, but does not permit `campaign -> datasets`.

Therefore, implementing future Run aggregate behavior under the current `campaign` package would either avoid the required Dataset Manifest ownership boundary or require an architecture-rule change without an approved boundary decision.

This document resolves the architecture boundary only. It does not implement Run behavior.

## 4. Repository Evidence

| Evidence ID | Evidence | Decision relevance |
| --- | --- | --- |
| M016-DEC-EVID-0001 | `MILESTONE_012_CANONICAL_RUNTIME_DOMAIN_KERNEL_DESIGN.md` | Defines Campaign, Run, Evidence Package, and Review aggregate roots; states Run owns Dataset Manifests; defers persistence, repositories, Audit, and Decision Candidate |
| M016-DEC-EVID-0002 | `MILESTONE_013_PROCESS_LOCAL_DOMAIN_PRIMITIVE_FOUNDATION.md` | Implements lifecycle enums, identity pairing, transition/version primitives, `DatasetManifest`, and `CriterionResult`; no aggregate behavior |
| M016-DEC-EVID-0003 | `MILESTONE_014_PROCESS_LOCAL_EVIDENCE_PACKAGE_AGGREGATE_BEHAVIOR.md` | Freezes Evidence Package behavior with immutable parent `RunId`; leaves Run and Campaign deferred |
| M016-DEC-EVID-0004 | `MILESTONE_015_PROCESS_LOCAL_REVIEW_AGGREGATE_BEHAVIOR.md` | Freezes Review behavior for Evidence Package targets only; leaves Run-target Review, Run, and Campaign deferred |
| M016-DEC-EVID-0005 | `MILESTONE_016_RUN_AGGREGATE_BOUNDARY_RECONCILIATION_SCOPE_SELECTION.md` | Requires an architecture boundary decision, boundary questions, and documentation-only deliverables |
| M016-DEC-EVID-0006 | `tools/check_architecture.py` | Current source of truth for package dependency rules |
| M016-DEC-EVID-0007 | `src/empirical_platform/campaign/lifecycle.py` | Defines `CampaignLifecycleState` and `RunLifecycleState` only |
| M016-DEC-EVID-0008 | `src/empirical_platform/datasets/manifest.py` | Defines immutable `DatasetManifest` with `RunId`, optional `DatasetId`, and storage-layout-neutral facts |
| M016-DEC-EVID-0009 | `src/empirical_platform/evidence/package.py` | Evidence Package depends on `RunId`, not Run aggregate behavior |
| M016-DEC-EVID-0010 | `src/empirical_platform/review/aggregate.py` | Review targets Evidence Package only and rejects Run IDs as targets |

## 5. Package Inventory

| Package | Current contents | Public exports | Current allowed imports | Current consumers |
| --- | --- | --- | --- | --- |
| `empirical_platform.campaign` | Campaign and Run lifecycle enums; no aggregate behavior | `CampaignLifecycleState`, `RunLifecycleState` | `shared`, `identifiers`, `governance`, `registry` | lifecycle tests |
| `empirical_platform.datasets` | Immutable `DatasetManifest`; no aggregate behavior | `DatasetManifest` | `shared`, `identifiers`, `campaign` | Dataset Manifest tests |
| `empirical_platform.evidence` | Evidence Package lifecycle, aggregate, artifact reference, Criterion Result | `EvidencePackage`, `ArtifactReference`, `CriterionResult`, `EvidencePackageLifecycleState` | `shared`, `identifiers`, `datasets`, `validation` | Evidence Package tests |
| `empirical_platform.review` | Review lifecycle, disposition, aggregate, target/reference/finding values | `Review`, `ReviewTargetReference`, `ReviewerReference`, `ReviewFinding`, `ReviewLifecycleState`, `ReviewDisposition` | `shared`, `identifiers`, `evidence` | Review tests |
| `empirical_platform.identifiers` | Governance identifier value objects and domain identity pairing | `CampaignId`, `RunId`, `DatasetId`, `EvidencePackageId`, `ReviewId`, `AuditId`, `DecisionCandidateId`, `DomainIdentity`, `pair_identity` | `shared` | domain packages and tests |
| `empirical_platform.shared` | Foundation interfaces, health, config, logging, persistence/object-storage adapters, domain versioning and transitions | shared primitives and infrastructure foundation | none for domain packages | broad foundation consumers |
| `empirical_platform.run` | Does not exist | None | Not defined | None |

## 6. Required Distinctions

| Concern | Decision |
| --- | --- |
| Conceptual domain ownership | Run conceptually owns Dataset Manifest records. |
| Physical package placement | `DatasetManifest` remains physically defined in `empirical_platform.datasets`. |
| Import direction | Future Run behavior may import `datasets`; Campaign must not import `datasets`. |
| Lifecycle authority | Run lifecycle authority belongs to future Run aggregate behavior; Dataset Manifest has no independent lifecycle. |
| Aggregate containment | Dataset Manifest is an immutable owned record, not an aggregate root. |
| Persistence ownership | Dataset Manifest persistence remains within future Run persistence boundary; no schema is defined here. |
| Public export ownership | `empirical_platform.datasets` remains the public export owner for `DatasetManifest`. |

## 7. Options Evaluated

### Option A - Keep DatasetManifest in `datasets`, create future `run` package

Boundary:

```text
run -> datasets
run -> campaign lifecycle or relocated lifecycle after explicit decision
campaign -> identifiers and future Run summary/reference surface only
campaign !-> datasets
```

Benefits:

- Preserves the existing `DatasetManifest` public export.
- Avoids moving a frozen primitive.
- Gives Run its own aggregate boundary instead of overloading `campaign`.
- Allows Campaign to remain a coordination aggregate without direct Dataset Manifest access.

Risks:

- Requires future package creation.
- Requires future architecture-rule update to include `run`.
- Requires a later decision on whether `RunLifecycleState` stays in `campaign` or is re-exported/moved.

Disposition: selected.

### Option B - Move DatasetManifest into future `run` package

Boundary:

```text
run owns and defines DatasetManifest physically
datasets no longer exports DatasetManifest
```

Benefits:

- Aligns conceptual ownership and physical placement.
- Reduces direct dependency from future Run to `datasets`.

Risks:

- Breaks existing `empirical_platform.datasets.DatasetManifest` public export.
- Creates source movement and import churn.
- Treats package placement as domain semantics.
- Provides little benefit while `DatasetManifest` is already storage-layout-neutral.

Disposition: rejected.

### Option C - Keep Run aggregate under `campaign`

Boundary:

```text
campaign contains Campaign lifecycle, Run lifecycle, and Run aggregate
campaign -> datasets required for DatasetManifest ownership
```

Benefits:

- Avoids creating a new top-level package.
- Matches the current location of `RunLifecycleState`.

Risks:

- Requires changing architecture rules to permit `campaign -> datasets`.
- Blurs Campaign and Run aggregate responsibilities.
- Makes future Campaign implementation more likely to reach into Run-owned Dataset Manifest details.

Disposition: rejected.

### Option D - Shared contract or re-export layer

Boundary:

```text
shared/domain or another neutral package exports DatasetManifest-like contract
run and datasets depend on that contract
```

Benefits:

- Could avoid direct `run -> datasets` dependency.

Risks:

- Introduces speculative abstraction before the first Run aggregate exists.
- Weakens the clear current public export.
- Risks placing domain-specific data in `shared`.

Disposition: rejected.

### Option E - No package change; opaque reference only

Boundary:

```text
future Run stores opaque manifest references instead of DatasetManifest values
```

Benefits:

- Avoids architecture-rule change.
- Avoids source movement.

Risks:

- Violates M012/M013 expectation that Dataset Manifest is an immutable Run-owned record.
- Prevents local Run enforcement of Dataset Manifest immutability/supersession.
- Defers too much required behavior to unspecified external services.

Disposition: rejected.

## 8. Evaluation Matrix

| Criterion | Option A | Option B | Option C | Option D | Option E |
| --- | --- | --- | --- | --- | --- |
| Frozen-decision compatibility | HIGH | MEDIUM | MEDIUM | MEDIUM | LOW |
| Conceptual clarity | HIGH | MEDIUM | LOW | LOW | LOW |
| Dependency direction | HIGH | MEDIUM | LOW | MEDIUM | MEDIUM |
| Module cohesion | HIGH | MEDIUM | LOW | LOW | LOW |
| Scope size | MEDIUM | HIGH | MEDIUM | MEDIUM | LOW |
| Migration cost | LOW | HIGH | MEDIUM | MEDIUM | LOW |
| Public API stability | HIGH | LOW | HIGH | MEDIUM | HIGH |
| Testability | HIGH | MEDIUM | MEDIUM | MEDIUM | LOW |
| Future persistence clarity | HIGH | MEDIUM | LOW | LOW | LOW |
| Campaign coupling | LOW | LOW | HIGH | MEDIUM | LOW |
| Evidence coupling | LOW | LOW | MEDIUM | MEDIUM | MEDIUM |
| Circular dependency risk | LOW | LOW | MEDIUM | MEDIUM | LOW |
| Speculative abstraction risk | LOW | LOW | LOW | HIGH | MEDIUM |
| Reversibility | HIGH | LOW | MEDIUM | MEDIUM | MEDIUM |
| Long-term maintainability | HIGH | MEDIUM | LOW | LOW | LOW |

| Risk type | Option A | Option B | Option C | Option D | Option E |
| --- | --- | --- | --- | --- | --- |
| Architectural risk | LOW | MEDIUM | HIGH | HIGH | HIGH |
| Migration risk | LOW | HIGH | MEDIUM | MEDIUM | LOW |
| Coupling risk | LOW | MEDIUM | HIGH | MEDIUM | MEDIUM |
| Frozen-decision risk | LOW | MEDIUM | MEDIUM | MEDIUM | HIGH |
| Implementation ambiguity | LOW | MEDIUM | MEDIUM | HIGH | HIGH |

## 9. Selected Decision

MILESTONE-016 selects Option A.

Future Run aggregate behavior shall live in a new top-level package:

```text
empirical_platform.run
```

`DatasetManifest` shall remain physically defined and publicly exported by:

```text
empirical_platform.datasets
```

Future Run behavior may directly import `DatasetManifest` from `empirical_platform.datasets`, but that dependency is not implemented in this milestone.

Campaign must not directly import `DatasetManifest` or `empirical_platform.datasets`.

## 10. Run Package Boundary

A future implementation milestone may create:

```text
src/empirical_platform/run/
```

Future Run aggregate behavior belongs in `empirical_platform.run`, not in `empirical_platform.campaign`.

`RunLifecycleState` currently remains in `empirical_platform.campaign.lifecycle`. This decision does not move it.

A later implementation milestone must decide explicitly whether future `empirical_platform.run` imports `RunLifecycleState` from `campaign`, re-exports it from `run`, or performs a separately reviewed lifecycle relocation. No lifecycle relocation is required before the next Run scope-selection mission, but the choice must be resolved before or during Run implementation.

## 11. DatasetManifest Ownership and Placement

| Concern | Decision |
| --- | --- |
| Conceptual owner | Run |
| Physical defining package | `empirical_platform.datasets` |
| Public export owner | `empirical_platform.datasets` |
| Allowed future consumer | `empirical_platform.run` |
| Campaign access | Forbidden direct access |
| Movement | Deferred and not recommended unless later evidence proves necessity |
| Semantics | Unchanged: immutable, Run-owned, storage-layout-neutral, vendor-neutral, no independent lifecycle |

`DatasetManifest` remains a value object / owned record. It is not promoted to an aggregate root.

## 12. Allowed Dependency Directions

The selected future architecture permits these directions after an explicit implementation milestone updates source and architecture rules:

```text
run -> datasets
run -> identifiers
run -> shared
run -> campaign lifecycle only if lifecycle remains physically in campaign
datasets -> identifiers
datasets -> shared
evidence -> identifiers
evidence -> datasets
review -> evidence
campaign -> identifiers
campaign -> shared
campaign -> future run identity/summary surface only if explicitly introduced later
```

No dependency-direction change is made in this document.

## 13. Forbidden Dependency Directions

The selected architecture forbids:

```text
campaign -> datasets
campaign -> DatasetManifest
datasets -> run
datasets -> evidence
datasets -> review
run -> evidence for initial Run aggregate behavior
run -> review
run -> persistence adapters
run -> object-storage adapters
review -> run for current Review behavior
shared -> any domain package
```

Future Campaign behavior may depend on Run identities or bounded summaries only after a separately reviewed public surface exists. It must not load Run internals or Dataset Manifest records directly.

## 14. Campaign Boundary

Campaign remains a separate aggregate boundary.

Campaign may reference:

- `CampaignId`;
- `RunId`;
- future bounded Run summary/reference data if explicitly introduced later.

Campaign must not:

- import `DatasetManifest`;
- inspect Dataset Manifest contents;
- own Dataset Manifest lifecycle;
- mutate Run execution history;
- implement Run orchestration in the aggregate.

Campaign orchestration, completion based on active Run summaries, and authorization workflow remain deferred.

## 15. Evidence and Review Compatibility

Evidence Package behavior remains compatible because it already stores immutable parent `RunId` context and does not load Run aggregate behavior.

Review behavior remains compatible because M015 froze Review targets as Evidence Package only. Run-target Review behavior remains deferred and must not be inferred from this decision.

No Evidence Package or Review behavior changes are authorized.

## 16. Public Export Compatibility

Existing public exports remain valid:

```text
from empirical_platform.datasets import DatasetManifest
from empirical_platform.campaign import CampaignLifecycleState, RunLifecycleState
from empirical_platform.identifiers import CampaignId, RunId, DatasetId
```

No public re-export is introduced by this document.

Future `empirical_platform.run` may define its own public exports only in a later implementation milestone.

## 17. Deferred Source Changes

Deferred source changes include:

- creating `src/empirical_platform/run/`;
- implementing a Run aggregate;
- adding future Run tests;
- adding future Run package exports;
- importing `DatasetManifest` from future Run behavior;
- deciding whether to re-export or relocate `RunLifecycleState`;
- updating import paths if a lifecycle move is separately approved.

None of these changes are performed or authorized for execution in this milestone.

## 18. Deferred Architecture-Rule Changes

Deferred architecture-rule changes include:

- adding `run` to `tools/check_architecture.py`;
- defining allowed imports for `run`;
- defining whether `campaign -> run` is allowed for public summaries or remains forbidden;
- adding negative fixtures for forbidden `campaign -> datasets` and `datasets -> run` imports;
- adding positive tests for future `run -> datasets` if implemented.

The current architecture checker remains unchanged.

## 19. Future Run Implementation Prerequisites

A future Run scope-selection mission may proceed only if it accepts this decision or explicitly supersedes it through review.

The future Run implementation scope must define:

- exact Run module path;
- allowed Run imports;
- whether `RunLifecycleState` remains imported from `campaign`;
- Run identity pairing;
- Campaign context representation as immutable `CampaignId`;
- Dataset Manifest append/supersession behavior;
- local Run invariant set;
- transition history behavior;
- terminal state behavior;
- excluded cross-aggregate behaviors.

The future scope must still exclude repositories, schemas, persistence mappings, APIs, workers, job ledger, outbox, Audit, Decision Candidate, Decision Freeze, market data, vendor behavior, trading behavior, and campaign execution unless separately authorized.

## 20. Risks and Mitigations

| Risk | Severity | Mitigation |
| --- | --- | --- |
| Future `run -> campaign` lifecycle import could create awkward naming | MINOR | Later scope must either keep the import narrow or explicitly review lifecycle relocation/re-export |
| Adding a `run` package requires architecture-rule update | MINOR | Defer to implementation milestone with explicit checker and fixture updates |
| Campaign may later overreach into Run internals | MAJOR | This decision forbids Campaign direct access to Dataset Manifest and Run internals |
| DatasetManifest physical placement may be mistaken for aggregate ownership | MAJOR | This decision separates conceptual ownership from package placement |
| Future persistence design may overfit to current package placement | MINOR | Persistence remains deferred and tied to aggregate ownership, not package location alone |

## 21. Decision Consequences

Positive consequences:

- Run receives a distinct aggregate boundary.
- `DatasetManifest` remains stable and public.
- Campaign is protected from Dataset Manifest coupling.
- The future Run implementation scope no longer needs to invent package placement.

Negative consequences:

- A new top-level `run` package will likely be required later.
- Architecture checker changes are deferred but unavoidable if Run implementation proceeds.
- `RunLifecycleState` remains physically in `campaign` until a later reviewed decision.

Deferred costs:

- future package creation;
- future architecture-rule update;
- future lifecycle import/re-export/relocation decision;
- future Run tests and fixtures.

## 22. Compatibility Guarantees

This decision preserves:

- M012 aggregate root definitions;
- Run conceptual ownership of Dataset Manifest records;
- Dataset Manifest immutability and storage-layout neutrality;
- Campaign lifecycle semantics;
- Run lifecycle semantics;
- Evidence Package parent `RunId` behavior;
- Review Evidence-Package-only target behavior;
- governance/runtime identity separation;
- absence of repository contracts, schemas, migrations, APIs, workers, job ledger, outbox, Audit runtime, Decision Candidate runtime, and Decision Freeze behavior.

## 23. Stop Conditions

Stop future work if:

- Run implementation is attempted inside `empirical_platform.campaign` without a superseding decision;
- `DatasetManifest` is moved without explicit review;
- `campaign -> datasets` is introduced;
- Dataset Manifest semantics are redesigned;
- architecture rules are changed without corresponding negative fixtures;
- persistence, repositories, schemas, or migrations are introduced before Run behavior is frozen;
- Campaign behavior attempts to inspect Dataset Manifest contents;
- Run implementation requires Evidence Package or Review internals.

## 24. Hostile Self-Review

| ID | Severity | Section | Finding | Evidence | Impact | Correction | Disposition |
| --- | --- | --- | --- | --- | --- | --- | --- |
| M016-DECISION-ISSUE-0001 | MAJOR | Selected decision | Initial draft risked implying the `run` package exists now. | Repository has no `src/empirical_platform/run`. | Could imply unperformed source creation. | Wording changed to future package and deferred source changes. | Resolved |
| M016-DECISION-ISSUE-0002 | MAJOR | Dependency directions | Initial draft needed explicit `campaign !-> datasets`. | Architecture checker currently forbids `campaign -> datasets`; Campaign does not need Dataset Manifest. | Could permit Campaign coupling. | Added forbidden dependency directions and Campaign boundary. | Resolved |
| M016-DECISION-ISSUE-0003 | MAJOR | DatasetManifest | Initial draft needed explicit preservation of public export ownership. | Existing tests import `DatasetManifest` from `empirical_platform.datasets`. | Could break public API. | Added public export compatibility and no-move decision. | Resolved |
| M016-DECISION-ISSUE-0004 | MINOR | Run lifecycle | Initial draft needed to avoid smuggling lifecycle relocation. | `RunLifecycleState` currently lives in `campaign.lifecycle`. | Could imply source movement. | Marked lifecycle movement as deferred and not required here. | Resolved |
| M016-DECISION-ISSUE-0005 | MINOR | Persistence | Initial draft needed to avoid schema implications. | M012 defers repository/schema decisions; `migrations/versions` is empty. | Could leak persistence design. | Added explicit persistence deferral and compatibility guarantees. | Resolved |

## 25. Final Decision

Final decision:

```text
Keep DatasetManifest in empirical_platform.datasets.
Create future Run aggregate behavior under a new empirical_platform.run package.
Permit future run -> datasets dependency after an explicit implementation milestone updates architecture rules.
Forbid campaign -> datasets.
Keep Campaign limited to Run identity or later bounded Run summary/reference surfaces.
Defer all source moves, public re-exports, architecture-rule changes, repositories, schemas, migrations, APIs, workers, and runtime behavior.
```

Final status:

```text
BOUNDARY DECISION READY FOR INDEPENDENT REVIEW
```
