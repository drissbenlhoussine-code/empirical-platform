# MILESTONE-000C EMPIRICAL VALIDATION CAMPAIGN STANDARD

---

## 1. Document Control

| Field | Value |
|---|---|
| Document ID | MILESTONE-000C-CAMPAIGN-STANDARD |
| Title | MILESTONE-000C Empirical Validation Campaign Standard |
| Version | 1.0 |
| Status | DRAFT / CAMPAIGN STANDARD UNDER REVIEW |
| Document Owner | Research Lead |
| Primary Approver | Project Owner |
| Original Publication Date | 2026-07-12 |
| Current Revision Date | 2026-07-12 |
| Approval Date | Not applicable |
| Parent milestone | MILESTONE-000C Empirical Validation Framework |

This document defines what constitutes an Empirical Validation Campaign. It does not execute a campaign, perform empirical validation, modify previous milestones, create vendor-specific content, implement software, rank vendors, recommend vendors, or freeze any decision.

---

## 2. Purpose

The purpose of this standard is to provide the canonical governance model for every future empirical validation campaign under MILESTONE-000C.

It defines campaign identity, lifecycle, versioning, ownership, authorization, phases, run hierarchy, review, audit, completion, archival, and freeze governance.

---

## 3. Campaign Definition

An **Empirical Validation Campaign** is a governed collection of one or more validation runs designed to produce reproducible empirical evidence for a defined scope, product class, dataset class, criterion set, or vendor-candidate question.

A campaign is not:

- a vendor selection;
- a vendor ranking;
- a single raw data download;
- an implementation project;
- a Decision Freeze;
- a replacement for B3 criteria or 000B vendor research.

---

## 4. Campaign Hierarchy

Canonical hierarchy:

```text
Campaign
  -> Run
      -> Dataset
      -> Evidence Package
      -> Criterion Results
      -> Review
      -> Decision Candidate
```

Definitions:

| Entity | Definition |
|---|---|
| Campaign | Parent governance container for a scoped empirical validation effort |
| Run | One execution attempt under the campaign |
| Dataset | The raw and normalized data scope used in a run |
| Evidence Package | Complete artifact bundle proving what happened in the run |
| Criterion Results | Per-B3 or campaign-specific empirical result artifacts |
| Review | Independent or assigned review of evidence and results |
| Decision Candidate | A result set eligible for later Decision Freeze consideration, not a decision itself |

---

## 5. Campaign Identity Model

Every campaign must have:

- Campaign ID.
- Campaign title.
- Campaign version.
- Campaign owner.
- Campaign reviewer.
- Scope statement.
- Linked protocol.
- Linked artifact specification.
- Linked execution runbook.
- Linked criteria baseline.
- Linked candidate/product/feed scope if applicable.
- Campaign status.

Campaign ID format:

```text
CAMP-#### 
```

Campaign IDs are immutable once assigned.

---

## 6. Campaign Versioning

Campaign versioning follows semantic governance versioning:

- `v0.x`: draft design revisions.
- `v1.0`: first authorized campaign design.
- `v1.x`: non-breaking campaign-governance or scope clarifications.
- `v2.0`: material scope or methodology change requiring reauthorization.

Run outputs do not change campaign version by themselves unless the campaign design changes.

Any campaign version change must record:

- reason;
- affected runs;
- affected evidence packages;
- whether prior runs remain comparable;
- reviewer disposition.

---

## 7. Campaign Ownership

| Role | Responsibility |
|---|---|
| Campaign Owner | Defines scope, maintains campaign governance, requests authorization |
| Test Operator | Executes approved runs under the runbook |
| Evidence Custodian | Maintains evidence package integrity and retention |
| Reviewer | Reviews evidence, exceptions, conflicts, and completion |
| Calibration Owner | Owns campaign-specific calibration and statistical-boundary questions |
| Project Owner | Approves campaign authorization, suspension, restart, closure, or freeze |

One person may hold multiple roles only if independence limitations are disclosed.

---

## 8. Campaign Objectives

Campaign objectives must state:

- what empirical question is being tested;
- what criteria or dimensions are in scope;
- what product/feed/dataset class is in scope;
- what evidence must be produced;
- what would make the campaign valid, invalid, blocked, or incomplete;
- what downstream decision process may consume the campaign evidence.

Objectives must not include vendor preference, ranking, or recommendation.

---

## 9. Campaign Prerequisites

Before authorization, a campaign must have:

- approved or draft-accepted empirical validation protocol;
- evidence artifact specification;
- execution runbook;
- scope statement;
- sample-design plan or deferred calibration statement;
- license/entitlement precondition plan;
- reviewer assignment;
- risk review;
- archival and retention plan;
- campaign audit plan.

No campaign may proceed to execution if testing rights are unknown.

---

## 10. Campaign Authorization Workflow

Authorization steps:

1. Campaign proposal drafted.
2. Scope reviewed against 000B dependencies.
3. Protocol, artifact spec, and runbook references confirmed.
4. Calibration dependencies identified.
5. License/entitlement preconditions reviewed.
6. Reviewer assigned.
7. Risks and stop conditions reviewed.
8. Project Owner authorizes, rejects, or returns for revision.

Authorization states:

- PROPOSED.
- AUTHORIZATION REVIEW.
- AUTHORIZED FOR RUN PLANNING.
- REVISION REQUIRED.
- REJECTED AS OUT OF SCOPE.

Authorization does not permit vendor testing until run-level license and entitlement checks pass.

---

## 11. Campaign Phases

| Phase | Purpose | Exit condition |
|---|---|---|
| Proposal | Define campaign identity and scope | Proposal accepted for authorization review |
| Authorization | Confirm campaign may proceed to planning | Authorized for run planning |
| Planning | Build sample/run/evidence plan | Run plan approved |
| Pre-Run Review | Verify license, entitlement, environment, reviewer, and evidence package setup | Run authorized |
| Execution | Conduct one or more approved runs | Run evidence package completed |
| Evidence Review | Review artifacts, criterion results, exceptions, conflicts | Reviewer disposition issued |
| Audit | Verify reproducibility, traceability, and governance compliance | Campaign audit completed |
| Completion | Mark campaign complete, blocked, invalid, rerun-required, or freeze-eligible | Completion record approved |
| Archive | Preserve evidence under retention rules | Archive record complete |

---

## 12. Run Hierarchy

A campaign may contain one or more runs.

Run types:

- Initial run.
- Rerun.
- Partial rerun.
- Invalidation rerun.
- Calibration rerun.
- Evidence-reconstruction run.

Every run must link to:

- campaign ID;
- run ID;
- run version or sequence;
- dataset ID;
- evidence package ID;
- criterion result set;
- review record;
- audit record.

Runs must not overwrite prior runs.

---

## 13. Dataset Relationship

Each run uses a dataset scope consisting of:

- instrument manifest;
- date manifest;
- session boundary;
- product/feed identity;
- raw data snapshot;
- normalized comparison copy;
- dataset snapshot ID.

Dataset identity must distinguish:

- raw vendor-native data;
- normalized project comparison data;
- vendor-derived fields;
- project-derived fields;
- missing/inaccessible data;
- adjusted versus raw data.

---

## 14. Evidence Package Relationship

Each run must produce one evidence package conforming to the Evidence Artifact Specification.

The evidence package is the authoritative record for:

- what was acquired;
- what was transformed;
- what was tested;
- what failed or was blocked;
- what reviewer approved;
- what can be reproduced;
- what may be used downstream.

No campaign result is valid without an evidence package.

---

## 15. Criterion Results Relationship

Criterion results are child artifacts of a run and evidence package.

Each criterion result must link:

- campaign ID;
- run ID;
- dataset ID;
- evidence package ID;
- criterion ID;
- result state;
- raw evidence;
- normalized evidence;
- exceptions/conflicts;
- reviewer disposition.

Criterion results do not select vendors. They only describe empirical evidence states.

---

## 16. Review Relationship

Review is a governed evaluation of run evidence.

Review outputs:

- reviewer sign-off;
- reviewer rejection;
- non-blocking limitation record;
- blocking exception record;
- rerun-required record;
- campaign audit input.

Review must be linked to evidence artifacts, not informal summaries.

---

## 17. Decision Candidate Relationship

A Decision Candidate is a campaign output that may later be considered by a Decision Freeze process.

It is not a decision.

A Decision Candidate requires:

- campaign completion;
- valid run evidence;
- reviewed criterion results;
- no blocking unresolved exception;
- no blocking unresolved conflict;
- decision-time licensing/pricing freshness still separately required;
- DEC-0033 or successor Decision Freeze gate still satisfied later.

---

## 18. Naming Conventions

Campaign file and artifact names must use:

```text
campaign_<CAMP_ID>__<short_scope>__v<version>
run_<RUN_ID>__<campaign_id>__<sequence>
dataset_<DATASET_ID>__<run_id>
evidence_<EVIDENCE_ID>__<run_id>
review_<REVIEW_ID>__<run_id>
audit_<AUDIT_ID>__<campaign_id>
```

Names must be lowercase except formal IDs, must avoid spaces, and must not encode rankings or vendor preference.

---

## 19. Identifier Strategy

| Identifier | Format | Scope |
|---|---|---|
| Campaign ID | CAMP-#### | Campaign governance object |
| Run ID | RUN-#### | Execution attempt |
| Dataset ID | DATASET-#### | Dataset scope and snapshot |
| Evidence Package ID | EVID-#### | Artifact bundle |
| Review ID | REVIEW-#### | Reviewer disposition |
| Audit ID | AUD-#### | Campaign audit |
| Decision Candidate ID | DCAND-#### | Freeze-eligible evidence candidate |

Identifiers are immutable. If an object is invalidated, its identifier remains and its state changes; it is not deleted or reused.

---

## 20. Campaign State Model

Allowed states:

- DRAFT.
- AUTHORIZATION REVIEW.
- AUTHORIZED FOR RUN PLANNING.
- RUN PLANNING.
- RUN AUTHORIZED.
- RUNNING.
- SUSPENDED.
- RERUN REQUIRED.
- REVIEW IN PROGRESS.
- AUDIT IN PROGRESS.
- COMPLETED - EVIDENCE VALID.
- COMPLETED - EVIDENCE LIMITED.
- INVALIDATED.
- ARCHIVED.
- FROZEN - CAMPAIGN COMPLETE.

Only `FROZEN - CAMPAIGN COMPLETE` indicates campaign governance freeze. It is not vendor Decision Freeze.

---

## 21. Suspension and Restart Rules

Suspend a campaign when:

- license or entitlement becomes uncertain;
- sample manifest is invalid;
- product/feed mismatch appears;
- raw data integrity fails;
- reviewer independence concern appears;
- calibration dependency blocks interpretation;
- evidence package cannot be completed.

Restart requires:

- suspension cause record;
- corrective action;
- reviewer approval;
- project owner approval if scope changes;
- new run ID if evidence execution restarts.

Suspension does not erase prior evidence.

---

## 22. Reviewer Workflow

Reviewer workflow:

1. Review campaign scope.
2. Review authorization evidence.
3. Review run plan.
4. Review evidence package completeness.
5. Review criterion results.
6. Review exceptions and conflicts.
7. Review reproducibility package.
8. Issue disposition.

Reviewer dispositions:

- APPROVE.
- APPROVE WITH NON-BLOCKING LIMITATIONS.
- REVISION REQUIRED.
- RERUN REQUIRED.
- REJECT EVIDENCE.
- ESCALATE TO PROJECT OWNER.

---

## 23. Campaign Audit Requirements

Campaign audit must verify:

- campaign identity;
- campaign version;
- authorization record;
- run hierarchy;
- dataset identity;
- evidence package completeness;
- criterion result traceability;
- reviewer disposition;
- exception/conflict handling;
- rerun history;
- archival readiness;
- no vendor ranking, recommendation, selection, or rejection;
- no unapproved scope change.

Audit outputs:

- audit report;
- audit state;
- unresolved blocker list;
- freeze eligibility statement.

---

## 24. Completion Criteria

A campaign may be marked complete only when:

- all planned runs are complete, invalidated, or explicitly waived;
- evidence packages are verified;
- criterion results are reviewed;
- exceptions and conflicts are dispositioned;
- reproducibility obligations are satisfied or limitations recorded;
- audit report is complete;
- owner signs completion record;
- reviewer signs or records refusal.

Completion does not imply vendor selection.

---

## 25. Archival Rules

Archive requires:

- campaign completion or invalidation state;
- evidence retention review;
- final manifest;
- final audit report;
- access-control record;
- retention expiry record;
- checksum verification;
- archive location.

Archived campaigns are read-only. Corrections require a new campaign version, new run, or audit addendum.

---

## 26. Campaign Freeze Governance

A campaign may be frozen only when:

- completion criteria pass;
- audit passes or passes with non-blocking limitations;
- reviewer sign-off is present;
- no blocking exception remains;
- no blocking conflict remains;
- retention and archival obligations are satisfied;
- Project Owner approves freeze.

Campaign freeze does not select a vendor and does not replace Decision Freeze governance.

---

## 27. Final Verification

| Check | Status |
|---|---|
| Campaign identity model defined | Met |
| Campaign lifecycle defined | Met |
| Campaign versioning defined | Met |
| Campaign ownership defined | Met |
| Campaign objectives and prerequisites defined | Met |
| Authorization workflow defined | Met |
| Campaign phases defined | Met |
| Run hierarchy defined | Met |
| Campaign/Run/Dataset/Evidence/Result/Review/Decision Candidate relationship defined | Met |
| Naming conventions and identifier strategy defined | Met |
| Campaign state model defined | Met |
| Suspension/restart rules defined | Met |
| Reviewer workflow defined | Met |
| Audit, completion, archival, and freeze governance defined | Met |
| No campaign executed | Met |
| No empirical validation performed | Met |
| No previous milestone modified | Met |
| No vendor-specific content introduced | Met |
| No implementation created | Met |

---

## 28. Quality Rubric

| Category | Max | Score | Evidence |
|---|---:|---:|---|
| Scope discipline | 10 | 10 | No campaign execution, testing, implementation, or vendor-specific content |
| Identity model | 10 | 10 | Campaign, run, dataset, evidence, review, and decision-candidate entities defined |
| Lifecycle completeness | 10 | 10 | Proposal through archive/freeze covered |
| Versioning/state rigor | 10 | 9 | Versioning and state model defined; first campaign may refine states |
| Ownership clarity | 10 | 10 | Roles and responsibilities defined |
| Authorization controls | 10 | 10 | Authorization workflow and prerequisites defined |
| Review/audit governance | 10 | 10 | Reviewer workflow and audit requirements defined |
| Suspension/restart safety | 10 | 9 | Rules defined; first invalidation may refine restart details |
| Archival/freeze governance | 10 | 10 | Archive and campaign freeze separated from Decision Freeze |
| Future usability | 10 | 9 | Strong parent standard; needs validation in first campaign design |

**Total: 97/100.** Full marks are not assigned because campaign state and restart details may need refinement after first campaign design.

---

## 29. Final Status

**DRAFT / CAMPAIGN STANDARD UNDER REVIEW.**

This document defines the parent standard for future empirical validation campaigns. It does not execute any campaign, perform empirical validation, modify prior milestones, create vendor-specific content, implement software, rank vendors, recommend vendors, select vendors, reject vendors, or freeze any decision.

---

*End of MILESTONE-000C Empirical Validation Campaign Standard, Version 1.0.*
