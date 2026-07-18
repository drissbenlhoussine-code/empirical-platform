# MILESTONE-016 - Run Aggregate Boundary Reconciliation Scope Selection

## 1. Document Control

| Field | Value |
| --- | --- |
| Document ID | MILESTONE-016 |
| Title | Run Aggregate Boundary Reconciliation Scope Selection |
| Version | 1.0 |
| Status | SCOPE CANDIDATE SELECTED |
| Frozen baseline | `e864d72c000911ed6cfa6fd137b5db3cd353c733` |
| Baseline meaning | MILESTONE-015 approved and frozen |
| Mission type | Repository evidence scope selection only |
| Selected next milestone type | Architecture boundary decision milestone |
| Implementation performed | None |
| Source modified | No |
| Schemas or migrations created | No |

## 2. Baseline Verification

Required baseline:

```text
e864d72c000911ed6cfa6fd137b5db3cd353c733
```

Observed before this document:

| Check | Result |
| --- | --- |
| Branch | `master` |
| HEAD | `e864d72c000911ed6cfa6fd137b5db3cd353c733` |
| Working tree | Clean |

## 3. Repository Evidence Reviewed

| Evidence ID | Repository evidence | Relevance |
| --- | --- | --- |
| M016-EVID-0001 | `MILESTONE_012_CANONICAL_RUNTIME_DOMAIN_KERNEL_DESIGN.md` Sections 11, 12, 15, 23, 24, 30 | Defines Run as aggregate root, Run-owned Dataset Manifest, local Run invariants, deferred repository/schema boundaries |
| M016-EVID-0002 | `MILESTONE_013_PROCESS_LOCAL_DOMAIN_PRIMITIVE_FOUNDATION.md` | Implements `RunLifecycleState`, `DatasetManifest`, identity pairing, versioning, and transition primitives |
| M016-EVID-0003 | `MILESTONE_014_PROCESS_LOCAL_EVIDENCE_PACKAGE_AGGREGATE_BEHAVIOR.md` | Freezes Evidence Package aggregate behavior and leaves Run aggregate behavior deferred |
| M016-EVID-0004 | `MILESTONE_015_PROCESS_LOCAL_REVIEW_AGGREGATE_BEHAVIOR.md` | Freezes Review aggregate behavior and leaves Run, Campaign, persistence, Audit, and Decision Candidate deferred |
| M016-EVID-0005 | `tools/check_architecture.py` | Shows current `campaign` may not import `datasets`, while `datasets` imports `campaign` |
| M016-EVID-0006 | `src/empirical_platform/campaign/lifecycle.py` | Contains frozen Campaign and Run lifecycle primitives but no aggregate behavior |
| M016-EVID-0007 | `src/empirical_platform/campaign/__init__.py` | States Campaign module has no aggregate behavior implemented |
| M016-EVID-0008 | `src/empirical_platform/datasets/manifest.py` | Implements immutable Dataset Manifest conceptually owned by Run |
| M016-EVID-0009 | `migrations/versions` | Empty; no domain schema or repository exists |
| M016-EVID-0010 | repository `TODO/FIXME` scan | No TODO/FIXME marker found |

## 4. Completed Context

The repository has frozen:

- platform foundation;
- persistence connectivity without domain schema;
- object storage connectivity without object layout;
- unified infrastructure runtime;
- canonical runtime domain kernel design;
- process-local domain primitives;
- process-local Evidence Package aggregate behavior;
- process-local Review aggregate behavior.

Remaining domain aggregates and runtime concepts include Run, Campaign, Audit, Decision Candidate, repository contracts, persistence schema, and cross-aggregate governance flows.

## 5. Candidate Inventory

| Candidate | Architectural layer | Dependencies | Frozen prerequisites | Unresolved prerequisites | Local or cross-aggregate | Size | Risk | Evidence support |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Run aggregate boundary reconciliation | Domain architecture documentation | M012-M015, architecture checker, package inventory | Run lifecycle and Dataset Manifest primitives exist | package placement; Dataset Manifest ownership; Campaign context handling | Boundary design for future local aggregate | Small | Low | Run is next central aggregate, but current dependency direction blocks safe implementation |
| Process-local Run aggregate behavior | Domain implementation | Run lifecycle, Dataset Manifest, CampaignId, versioning | primitives exist | module boundary and scope snapshot semantics unresolved | Mostly local with Campaign context | Medium | High | M012 defines Run root, but implementation would risk architecture drift |
| Process-local Campaign aggregate behavior | Domain implementation | Campaign lifecycle, Run summaries, Review outcomes | lifecycle enum exists | Run behavior absent; completion is cross-aggregate | Cross-aggregate-heavy | Medium | High | Campaign completion depends on Runs and Reviews |
| Domain repository contract design | Persistence/domain boundary | aggregate semantics, PostgreSQL foundation | persistence connectivity exists | Run and Campaign behavior unresolved; no schema | Cross-layer | Large | High | M012 defers repository APIs |
| Domain schema/migration design | Persistence implementation | repository contracts, aggregate models | PostgreSQL foundation exists | repositories absent; Run/Campaign unresolved | Persistence | Large | High | M012 explicitly says no schema/table/migration defined |
| Audit runtime design | Domain/governance | Evidence, Review, audit authority | Evidence and Review exist | audit authority and process-compliance model deferred | Cross-aggregate/governance | Medium | High | M012 defers Audit |
| Decision Candidate runtime design | Decision governance | Review, Audit, sufficiency gates | Review exists | Audit absent; sufficiency governance deferred | Governance gate | Medium | High | M012 defers Decision Candidate |
| Architecture/test hardening | Engineering quality | existing test suite | suite is green | no concrete defect cluster | Cross-cutting | Small | Medium | Useful but not the next domain unblocker |

## 6. Comparison Matrix

| Criterion | Run boundary reconciliation | Run implementation | Campaign implementation | Repository contracts | Schema design | Audit design | Decision Candidate design | Test hardening |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Architectural ordering | 10 | 9 | 6 | 7 | 4 | 5 | 3 | 5 |
| Dependency readiness | 9 | 6 | 4 | 5 | 3 | 4 | 2 | 7 |
| Isolation | 10 | 6 | 4 | 5 | 2 | 4 | 3 | 8 |
| Independent testability | 9 | 7 | 5 | 5 | 4 | 5 | 4 | 8 |
| Reversibility | 10 | 6 | 5 | 5 | 3 | 5 | 4 | 8 |
| Auditability benefit | 8 | 8 | 7 | 7 | 6 | 8 | 7 | 5 |
| Long-term architectural impact | 10 | 8 | 7 | 8 | 7 | 7 | 7 | 5 |
| Implementation confidence | 10 | 5 | 4 | 4 | 2 | 3 | 3 | 7 |
| Total /80 | 76 | 55 | 42 | 46 | 31 | 41 | 33 | 53 |

## 7. Rejected Candidates

### Process-local Run aggregate behavior

Run is the correct next domain area, but direct implementation is not yet safe. M012 says Run owns Dataset Manifests, while the current architecture checker allows `datasets` to import `campaign`, not the reverse. Because `RunLifecycleState` currently lives in `campaign` and `DatasetManifest` lives in `datasets`, coding Run behavior under the current `campaign` package would either avoid required Dataset Manifest ownership or alter dependency direction without a frozen decision.

### Process-local Campaign aggregate behavior

Campaign behavior is premature. Campaign completion depends on active Run summaries and Review dispositions, which are cross-aggregate concerns. Run behavior is not implemented.

### Repository contract design

Repository contracts should not precede settled aggregate boundaries. M012 explicitly defers repository APIs, and the Run package-placement question would leak into contract shape.

### Domain schema/migration design

Schema design is premature and explicitly deferred. `migrations/versions` is empty and must remain empty until repository contracts and aggregate persistence ownership are settled.

### Audit runtime design

Audit remains deferred by M012 and requires process-compliance authority design. Review exists now, but Audit still risks duplicating Review or governance workflow.

### Decision Candidate runtime design

Decision Candidate remains deferred and depends on Audit, Review sufficiency, and governance decision gates. It is not next.

### Architecture/test hardening

No TODO/FIXME marker or failing validation cluster justifies a cross-cutting hardening milestone ahead of the Run boundary problem.

## 8. Selected Scope

Selected next milestone:

```text
MILESTONE-016 - Run Aggregate Boundary Reconciliation
```

Purpose:

```text
Resolve the package, ownership, and local-invariant boundary required before any Run aggregate implementation.
```

Architectural layer:

```text
Domain architecture / scope reconciliation
```

This is a documentation-only milestone. It is not Run aggregate implementation.

MILESTONE-016 is classified as:

```text
ARCHITECTURE BOUNDARY DECISION MILESTONE
```

It is not a source/package refactor milestone and not an architecture-rule implementation milestone.

## 9. Scope Boundary

MILESTONE-016 may define only:

- where future Run aggregate behavior belongs in the package/module structure;
- how Run may own Dataset Manifest records without violating module-boundary rules;
- whether a new `run` package is required or whether existing package ownership remains sufficient;
- how Campaign context is represented as immutable identity context only;
- which Run invariants are local and which remain cross-aggregate;
- which future implementation files would be allowed after MILESTONE-016 freezes;
- which tests would be required for a later Run implementation.

MILESTONE-016 must explicitly distinguish:

- domain ownership;
- physical package placement;
- import/reference direction;
- lifecycle authority;
- persistence ownership.

These are not interchangeable. Conceptual Run ownership of Dataset Manifest records does not by itself require physically moving `DatasetManifest`, changing its public export, or changing architecture rules.

## 10. Required Boundary Questions

MILESTONE-016 must answer each question below with repository evidence:

1. Which aggregate conceptually owns Dataset Manifest records?
2. Which package physically defines `DatasetManifest`?
3. Which packages may import `DatasetManifest`?
4. Where will future Run aggregate code live?
5. May future Run behavior depend directly on `empirical_platform.datasets`?
6. May future Campaign behavior depend on future Run behavior?
7. May future Campaign behavior depend directly on `empirical_platform.datasets`?
8. Does Campaign need `DatasetManifest` at all, or only Run identity/status summaries?
9. Is a public re-export allowed, and from which package if allowed?
10. Is a new shared contract prohibited, allowed, or deferred?
11. Are source moves allowed in MILESTONE-016?
12. Are architecture-rule changes allowed in MILESTONE-016?
13. What remains deferred to Run implementation?
14. What remains deferred to Campaign implementation?
15. What compatibility guarantees from MILESTONE-012 through MILESTONE-015 must remain frozen?

If any of these questions cannot be answered without source changes, MILESTONE-016 must stop and report `REVISION REQUIRED` rather than implementing the change.

## 11. Required Deliverables

MILESTONE-016 must produce documentation only:

- exact conflict statement;
- package and public-export inventory;
- ownership matrix;
- allowed dependency-direction decision;
- public-interface decision;
- future Run aggregate location decision;
- DatasetManifest placement decision;
- compatibility analysis against MILESTONE-012 through MILESTONE-015;
- explicit deferral of any migration, refactor, package move, or architecture-rule change not authorized by the decision;
- downstream prerequisites for a later Run implementation;
- independent review, correction pass if required, and freeze decision.

MILESTONE-016 must not silently authorize moving `DatasetManifest`, changing imports, changing package exports, modifying the architecture checker, or creating Run aggregate code.

## 12. Explicit Non-Goals

MILESTONE-016 must not implement:

- Run aggregate behavior;
- Campaign aggregate behavior;
- Dataset Manifest mutation behavior;
- Evidence Package changes;
- Review changes;
- repository contracts;
- persistence schema, tables, columns, migrations, or ORM mappings;
- APIs, workers, schedulers, job ledger, outbox, or event dispatch;
- Audit runtime;
- Decision Candidate runtime;
- Decision Freeze;
- campaign execution;
- market-data, vendor, or trading behavior.

MILESTONE-016 must not perform source-file moves, public re-exports, or architecture-rule changes unless the boundary decision explicitly classifies them as deferred follow-up work. This scope-selection document authorizes no such change.

## 13. Dependencies

| Dependency | Required role |
| --- | --- |
| MILESTONE-012 | Run aggregate root, lifecycle, local invariants, persistence deferrals |
| MILESTONE-013 | Run lifecycle enum, Dataset Manifest primitive, versioning, transition primitives |
| MILESTONE-014 | Evidence Package behavior already references Run by immutable `RunId` context |
| MILESTONE-015 | Review behavior is now frozen and remains downstream of Run/Evidence |
| Architecture checker | Current package-dependency truth source |

## 14. Validation Expectations

A future MILESTONE-016 document must be accepted only if:

- it modifies no source code;
- it creates no schema or migration;
- it defines a single package-placement decision for future Run behavior;
- it reconciles Run-owned Dataset Manifest behavior with architecture rules;
- it separates local Run invariants from Campaign/Evidence/Review cross-aggregate rules;
- it defines stop conditions for any future Run implementation;
- `security.ps1`, `verify.ps1`, `git diff --check`, and `git status --short` pass.

## 15. Hostile-Review Focus

The hostile review must look for:

- disguised Run implementation;
- architecture-rule changes without evidence;
- Dataset Manifest ownership hand-waving;
- Campaign authorization behavior leaking into Run;
- execution behavior hidden behind lifecycle names;
- repository/schema assumptions;
- event/outbox assumptions;
- persistence ownership claims;
- premature evidence/review reconciliation.

## 16. Stop Conditions

Stop MILESTONE-016 if:

- a source-code change is required;
- a schema or repository decision becomes necessary;
- Run implementation behavior is introduced;
- Campaign authorization or execution workflow is introduced;
- architecture changes cannot be justified from frozen M012-M015 evidence;
- the package-boundary decision remains unresolved.

## 17. Issue Register

| Issue ID | Severity | Finding | Correction | Disposition |
| --- | --- | --- | --- | --- |
| M016-SCOPE-REVIEW-ISSUE-0001 | MAJOR | Initial scope did not explicitly classify MILESTONE-016 as an architecture boundary decision milestone. | Added explicit milestone-type classification and prohibited source/package refactor or architecture-rule implementation scope. | Resolved |
| M016-SCOPE-REVIEW-ISSUE-0002 | MAJOR | Initial scope did not enumerate the required boundary questions needed to make the milestone actionable. | Added mandatory boundary-question list covering ownership, placement, imports, Run location, Campaign dependencies, source moves, architecture-rule changes, and deferrals. | Resolved |
| M016-SCOPE-REVIEW-ISSUE-0003 | MINOR | Initial scope could imply conceptual ownership and package placement are the same concern. | Added explicit distinction among domain ownership, package placement, reference direction, lifecycle authority, and persistence ownership. | Resolved |

## 18. Final Decision

The next bounded milestone is:

```text
MILESTONE-016 - Run Aggregate Boundary Reconciliation
```

Final scope-selection status:

```text
SCOPE CANDIDATE SELECTED
```

This decision explicitly does not authorize Run aggregate implementation. The repository evidence shows that no aggregate implementation, repository contract, schema, Audit, or Decision Candidate milestone is implementation-ready until the Run boundary is reconciled.
