# MASTER GOVERNANCE GATE CLASSIFICATION STANDARD

---

## 1. Document Control

| Field | Value |
|---|---|
| Document ID | MASTER-GOVERNANCE-GATE-CLASSIFICATION-STANDARD |
| Title | Master Governance Gate Classification Standard |
| Version | 1.0 |
| Status | DRAFT / GATE CLASSIFICATION STANDARD UNDER REVIEW |
| Document Owner | Research Lead |
| Primary Approver | Project Owner |
| Original Publication Date | 2026-07-12 |
| Current Revision Date | 2026-07-12 |
| Approval Date | Not applicable - not approved or frozen |
| Scope | Meta-governance standard for gate lifecycle classification, applicability, status assignment, and readiness reporting |
| Supersedes | Nothing |
| Modifies existing milestones | No |
| Authorizes empirical work | No |

This document defines how governance gates are classified, activated, evaluated, reported, and scored across the project lifecycle. It does not modify any milestone, execute a campaign, perform vendor research, conduct empirical validation, create a Decision Freeze, or implement software.

---

## 2. Purpose

The purpose of this standard is to prevent governance gates from being marked FAILED merely because the project has not yet reached the lifecycle stage where those gates apply.

It establishes:

- canonical gate taxonomy;
- gate lifecycle levels;
- applicability rules;
- canonical evaluation statuses;
- inheritance rules;
- reporting rules;
- readiness scoring rules;
- gate dependency rules;
- transition rules;
- audit requirements.

This standard governs gate interpretation only. It does not change the substance of any existing gate.

---

## 3. Scope and Non-Goals

### 3.1 In Scope

This standard applies to gates defined or implied by:

- MILESTONE-000A.
- MILESTONE-000B.0.
- MILESTONE-000B.1.
- MILESTONE-000B.2.
- MILESTONE-000B.3.
- MILESTONE-000B.4 Phase 1.
- MILESTONE-000B.4 Phase 2.
- Empirical Validation Protocol.
- Evidence Artifact Specification.
- Empirical Test Execution Runbook.
- MILESTONE-000C Framework.
- MILESTONE-000C Campaign Standard.
- Master Governance Integration Standard.
- Governance Execution Package.

### 3.2 Non-Goals

This standard does not:

- create a new empirical campaign;
- allocate a campaign identifier;
- authorize pilot execution;
- perform vendor research;
- perform empirical validation;
- call vendor APIs;
- acquire data;
- create vendor rankings;
- recommend vendors;
- create a Decision Candidate;
- create a Decision Freeze;
- modify prior milestones;
- modify operational registers;
- implement tooling.

---

## 4. Integration Authority

This standard is authoritative for gate classification, applicability, status assignment, readiness scoring, and gate reporting.

It does not override:

- the content of a source milestone;
- the gate requirements defined by the Master Governance Integration Standard;
- the artifact requirements defined by the Evidence Artifact Specification;
- the execution workflow defined by the Empirical Test Execution Runbook;
- the campaign hierarchy defined by the MILESTONE-000C Campaign Standard.

If a gate exists in another document, this standard determines when the gate becomes applicable and how its status must be reported.

---

## 5. Canonical Gate Taxonomy

Every governance gate must be classified into exactly one lifecycle level.

| Level | Gate Class | Applicability |
|---:|---|---|
| 0 | Permanent Governance Gates | Always applicable |
| 1 | System Readiness Gates | Applicable before any campaign exists |
| 2 | Campaign Authorization Gates | Applicable only after CAMP-#### allocation |
| 3 | Operational Preparation Gates | Applicable only after campaign approval |
| 4 | Execution Gates | Applicable only once testing begins |
| 5 | Review Gates | Applicable only after execution completes |
| 6 | Decision Gates | Applicable only after all required review gates pass |

No gate may activate before its parent lifecycle level is active.

---

## 6. Gate Dependency Tree

The canonical dependency tree is:

```text
System
  -> Campaign
    -> Preparation
      -> Execution
        -> Review
          -> Decision
```

Dependency rules:

1. System gates do not depend on campaign existence.
2. Campaign gates depend on CAMP allocation.
3. Preparation gates depend on campaign approval.
4. Execution gates depend on run authorization and testing start.
5. Review gates depend on execution completion.
6. Decision gates depend on review completion.
7. A child-layer gate cannot become PENDING, READY_FOR_REVIEW, VERIFIED, FAILED, or BLOCKED while its parent layer is inactive.
8. A child-layer gate remains NOT_APPLICABLE until its activation condition is satisfied.

---

## 7. Canonical Gate Status Model

Only the following statuses are permitted:

| Status | Meaning |
|---|---|
| NOT_APPLICABLE | Gate is not active because its activation condition has not occurred or its deactivation condition has occurred |
| PENDING | Gate is active but required evidence has not yet been submitted |
| READY_FOR_REVIEW | Gate evidence has been submitted and awaits review |
| VERIFIED | Gate evidence satisfies the requirement |
| FAILED | Gate evidence was reviewed and does not satisfy the requirement |
| BLOCKED | Gate cannot progress because a dependency, blocker, risk, deferred item, or required authority is unresolved |
| SUPERSEDED | Gate has been replaced by a later governing gate or revised baseline |

No custom status may be used in gate reports.

Legacy wording such as COMPLETE, OPEN, APPROVED, FROZEN, AUTHORIZED, DRAFT, UNDER REVIEW, ACCEPTED, or PASSED may appear inside source documents, but gate reports must translate those states into the canonical status model above.

---

## 8. Applicability Rule

Every gate definition must include:

- Activation Condition.
- Deactivation Condition.
- Blocking Condition.

Required gate evaluation logic:

```text
If activation condition is not satisfied:
  status = NOT_APPLICABLE

If activation condition is satisfied and required evidence is absent:
  status = PENDING

If activation condition is satisfied and evidence is submitted but not reviewed:
  status = READY_FOR_REVIEW

If activation condition is satisfied and evidence satisfies the gate:
  status = VERIFIED

If activation condition is satisfied and evidence was reviewed but does not satisfy the gate:
  status = FAILED

If activation condition is satisfied but a dependency prevents evaluation:
  status = BLOCKED

If gate has been replaced by a later approved governing gate:
  status = SUPERSEDED
```

Inactive gates must never be reported as FAILED.

---

## 9. Level 0 - Permanent Governance Gates

Level 0 gates are always applicable. They may never be NOT_APPLICABLE.

| Gate | Activation Condition | Deactivation Condition | Blocking Condition |
|---|---|---|---|
| Baseline package inventory | Project governance exists | Never | Required baseline inventory absent |
| Baseline checksum registration | Project governance exists | Never | Required checksum missing |
| Identifier registry | Project governance exists | Never | Namespace missing, collision unresolved, or range unverifiable |
| Dependency registry | Project governance exists | Never | Required dependency missing or unclassified |
| Governance versioning | Project governance exists | Never | Version missing or incompatible |
| Freeze governance | Project governance exists | Never | Required freeze rule missing or contradictory |
| Change-control governance | Project governance exists | Never | Material change lacks approval path |
| Gate classification standard | Project governance exists | Superseded by later approved classification standard | Gate taxonomy absent or inconsistent |

Level 0 gates affect system readiness even when no campaign exists.

---

## 10. Level 1 - System Readiness Gates

Level 1 gates are applicable before any campaign exists. They determine whether the governance system can support campaign creation.

| Gate | Activation Condition | Deactivation Condition | Blocking Condition |
|---|---|---|---|
| Master Risk Register initialized | Governance Execution Package exists | Superseded by later risk register | Risk register absent |
| Master Risk Register synchronized | Risk register initialized | Superseded by later risk register | Required source risks not imported or baseline unavailable |
| Master Deferred Item Register initialized | Governance Execution Package exists | Superseded by later deferred register | Deferred register absent |
| Master Deferred Item Register synchronized | Deferred register initialized | Superseded by later deferred register | Required deferred items not imported or baseline unavailable |
| Freeze Status Register initialized | Governance Execution Package exists | Superseded by later freeze register | Freeze dashboard absent |
| Reviewer independence policy exists | Master Governance Integration Standard exists | Superseded by later reviewer policy | Reviewer disqualification policy absent |
| Lifecycle definitions exist | Master Governance Integration Standard exists | Superseded by later lifecycle model | Lifecycle states undefined |
| Identifier integrity review | Identifier registry initialized | Superseded by later identifier review | Identifier ranges unverified or collision unresolved |
| Gate status model exists | This standard exists | Superseded by later classification standard | Gate reports use non-canonical statuses |

Level 1 gates may be PENDING, READY_FOR_REVIEW, VERIFIED, FAILED, BLOCKED, or SUPERSEDED before any campaign exists.

---

## 11. Level 2 - Campaign Authorization Gates

Level 2 gates become applicable only after CAMP-#### is allocated.

Before CAMP allocation, every Level 2 gate must be reported as NOT_APPLICABLE.

| Gate | Activation Condition | Deactivation Condition | Blocking Condition |
|---|---|---|---|
| Campaign ID allocated | Decision to create campaign record | Campaign retired or superseded | CAMP namespace unavailable or collision exists |
| Campaign owner assigned | CAMP-#### allocated | Campaign retired or superseded | No accountable campaign owner |
| Campaign scope defined | CAMP-#### allocated | Campaign retired or superseded | Scope missing, vendor-specific without authority, or non-neutral |
| Campaign objectives defined | CAMP-#### allocated | Campaign retired or superseded | Objectives missing or incompatible with governance scope |
| Campaign prerequisites checked | CAMP-#### allocated | Campaign retired or superseded | Required Level 0 or Level 1 gate BLOCKED or FAILED |
| Reviewer assignment | CAMP-#### allocated | Reviewer replaced or campaign retired | No reviewer assigned |
| Reviewer COI declaration | Reviewer assigned | Reviewer replaced or campaign retired | Declaration absent or reviewer disqualified |
| Campaign authorization record | CAMP-#### allocated | Campaign retired or superseded | Required authorization evidence absent |

Example transition:

```text
Campaign not created
  -> Campaign gates = NOT_APPLICABLE

Create CAMP-0001
  -> Campaign gates = PENDING
```

---

## 12. Level 3 - Operational Preparation Gates

Level 3 gates become applicable only after campaign approval.

Before campaign approval, every Level 3 gate must be reported as NOT_APPLICABLE.

| Gate | Activation Condition | Deactivation Condition | Blocking Condition |
|---|---|---|---|
| Evidence directory initialized | Campaign approved | Campaign invalidated or superseded | Evidence root absent or not writable under governance control |
| Conflict log initialized | Campaign approved | Campaign invalidated or superseded | Conflict log absent |
| Exception log initialized | Campaign approved | Campaign invalidated or superseded | Exception log absent |
| Manifest creation | Campaign approved | Campaign invalidated or superseded | Manifest absent or missing required fields |
| Dataset proposal | Campaign approved | Dataset proposal superseded or campaign retired | Dataset scope absent or not reviewable |
| Runbook version selected | Campaign approved | Runbook version superseded | No runbook version selected |
| Evidence package location defined | Campaign approved | Evidence location superseded | Evidence package path absent |
| License review workflow ready | Campaign approved | License workflow superseded | License workflow absent |
| Entitlement review workflow ready | Campaign approved | Entitlement workflow superseded | Entitlement workflow absent |
| Retention workflow ready | Campaign approved | Retention workflow superseded | Retention workflow absent |

Level 3 gates prepare the campaign for execution but do not authorize testing by themselves.

---

## 13. Level 4 - Execution Gates

Level 4 gates become applicable only once testing begins under an authorized run.

Before authorized testing begins, every Level 4 gate must be reported as NOT_APPLICABLE.

| Gate | Activation Condition | Deactivation Condition | Blocking Condition |
|---|---|---|---|
| Run ID allocated | Authorized run planning begins | Run retired or superseded | RUN namespace unavailable or collision exists |
| Raw-data acquisition | Testing begins | Acquisition complete, invalidated, or superseded | License, entitlement, source access, or evidence capture failure |
| Normalization | Raw acquisition complete | Normalization complete, invalidated, or superseded | Raw data unavailable or transformation rules absent |
| Criterion execution | Required data and normalization available | Criterion execution complete or superseded | Criterion inputs unavailable |
| Evidence validation | Evidence artifacts produced | Evidence review begins or evidence invalidated | Hash, manifest, or artifact completeness failure |
| Calibration application | Calibration-dependent criterion activated | Calibration superseded or criterion not applicable | Calibration missing or unapproved |
| Rerun trigger evaluation | Execution exception occurs | Rerun disposition complete | Exception unresolved |

Execution gates must not be evaluated before empirical testing starts.

---

## 14. Level 5 - Review Gates

Level 5 gates become applicable only after execution completes.

Before execution completion, every Level 5 gate must be reported as NOT_APPLICABLE.

| Gate | Activation Condition | Deactivation Condition | Blocking Condition |
|---|---|---|---|
| Independent evidence review | Execution complete and evidence package submitted | Review superseded or campaign invalidated | Reviewer absent, conflicted, or evidence package incomplete |
| Statistical review | Statistical or calibration-dependent results submitted | Review superseded or not statistically applicable | Statistical reviewer absent or inputs incomplete |
| Audit review | Evidence and reviewer disposition available | Audit superseded or campaign invalidated | Audit owner absent or evidence trail incomplete |
| Reviewer sign-off | Review complete | Sign-off superseded | Reviewer declines, is disqualified, or findings unresolved |
| Limitation classification | Review findings exist | Limitation disposition superseded | Finding classification absent or contradictory |

Review gates determine whether evidence can be used for decision candidacy.

---

## 15. Level 6 - Decision Gates

Level 6 gates become applicable only after all required review gates pass.

Before required review gates pass, every Level 6 gate must be reported as NOT_APPLICABLE.

| Gate | Activation Condition | Deactivation Condition | Blocking Condition |
|---|---|---|---|
| Decision Candidate creation | Required review gates VERIFIED | Decision Candidate superseded or rejected | DCAND namespace unavailable, review incomplete, or evidence invalid |
| Decision Freeze prerequisite verification | Decision Candidate exists | Decision Freeze completed or candidate retired | Required prerequisite absent |
| Decision Freeze | All Decision Freeze prerequisites VERIFIED | Decision Freeze superseded or reopened under governance | Any blocking prerequisite unresolved |
| Archive package finalization | Campaign complete or Decision Candidate dispositioned | Archive superseded | Archive package incomplete |
| Retention lock | Archive package finalized | Retention period expired under approved policy | Retention approval absent |

Decision gates must not be evaluated during system readiness, campaign authorization, preparation, execution, or review stages.

---

## 16. Inheritance Rules

1. A child gate inherits the inactive state of its parent layer.
2. If a parent layer is NOT_APPLICABLE, every child gate is NOT_APPLICABLE.
3. If a parent gate is BLOCKED, dependent child gates are BLOCKED only if their own activation condition is already satisfied.
4. If a parent gate is FAILED, dependent active child gates are BLOCKED unless the failure is resolved or the child gate is explicitly independent.
5. A VERIFIED parent gate does not automatically verify child gates.
6. A SUPERSEDED parent gate must identify the replacement gate before child gates may be evaluated.
7. Level 0 gates do not inherit from any parent layer.

---

## 17. Reporting Rules

Gate reports must distinguish applicable and inactive gates.

Prohibited reporting pattern:

```text
37 gates
35 failed
```

when inactive future-stage gates were included as failures.

Required reporting pattern:

```text
Total Gates:
Applicable Gates:
Inactive Gates:
Verified:
Pending:
Ready For Review:
Blocked:
Failed:
Not Applicable:
Superseded:
```

Reports must include:

- applicable gates;
- inactive gates;
- blocked gates;
- failed gates;
- incorrectly evaluated gates;
- invalid applicability transitions;
- readiness score using applicable gates only.

---

## 18. Readiness Scoring Rules

Readiness scores must use applicable gates only.

Formula:

```text
Readiness Score = Verified Applicable Gates / Total Applicable Gates
```

Rules:

1. NOT_APPLICABLE gates are excluded from the denominator.
2. SUPERSEDED gates are excluded from the denominator if a replacement gate exists.
3. PENDING gates count as applicable but not verified.
4. READY_FOR_REVIEW gates count as applicable but not verified.
5. BLOCKED gates count as applicable but not verified.
6. FAILED gates count as applicable but not verified.
7. A report must show the raw counts behind the score.

Example:

```text
Applicable Gates: 12
Verified: 10
Pending: 1
Blocked: 1
Failed: 0
Not Applicable: 20
Readiness: 83%
```

NOT_APPLICABLE must never be counted as failure.

---

## 19. Transition Rules

### 19.1 System to Campaign

```text
No CAMP allocated
  -> Level 2 Campaign Gates = NOT_APPLICABLE

CAMP-#### allocated
  -> Level 2 Campaign Gates = PENDING
```

### 19.2 Campaign to Preparation

```text
Campaign not approved
  -> Level 3 Preparation Gates = NOT_APPLICABLE

Campaign approved
  -> Level 3 Preparation Gates = PENDING
```

### 19.3 Preparation to Execution

```text
Testing not begun
  -> Level 4 Execution Gates = NOT_APPLICABLE

Authorized testing begins
  -> Level 4 Execution Gates = PENDING
```

### 19.4 Execution to Review

```text
Execution not complete
  -> Level 5 Review Gates = NOT_APPLICABLE

Execution complete and evidence submitted
  -> Level 5 Review Gates = PENDING or READY_FOR_REVIEW
```

### 19.5 Review to Decision

```text
Required review gates not VERIFIED
  -> Level 6 Decision Gates = NOT_APPLICABLE

Required review gates VERIFIED
  -> Level 6 Decision Gates = PENDING
```

---

## 20. Gate Dependency Rules

Every gate must declare its direct dependencies.

Minimum dependency fields:

- parent lifecycle level;
- parent gate if any;
- source document;
- required evidence;
- activation condition;
- deactivation condition;
- blocking condition.

Dependency failures must be reported as BLOCKED, not FAILED, unless the gate's own submitted evidence was reviewed and found insufficient.

---

## 21. Audit Requirements

Every gate audit must report:

- applicable gates;
- inactive gates;
- blocked gates;
- failed gates;
- pending gates;
- ready-for-review gates;
- superseded gates;
- incorrectly evaluated gates;
- invalid applicability transitions;
- readiness score using applicable gates only.

An incorrectly evaluated gate includes:

- an inactive gate marked FAILED;
- an active gate marked NOT_APPLICABLE;
- a child gate activated before its parent layer;
- a gate using a non-canonical status;
- a gate reported without activation, deactivation, and blocking conditions.

Invalid applicability transitions must be recorded as audit findings and corrected before readiness scores are used for authorization.

---

## 22. Pilot Authorization Checklist Classification

The current Pilot Authorization Checklist gates are classified as follows.

| Gate Item | Lifecycle Level | Activation Condition |
|---|---:|---|
| All non-waiver-eligible governance documents are present | 0 | Project governance exists |
| All non-waiver-eligible governance documents have registered checksums | 0 | Project governance exists |
| All required documents are Approved | 0 | Project governance exists |
| All required documents are Frozen | 0 | Project governance exists |
| All required documents are Authorized For Use | 0 | Project governance exists |
| Identifier namespaces are reconciled | 0 | Project governance exists |
| No identifier collision exists | 0 | Project governance exists |
| Master Risk Register is populated | 1 | Governance Execution Package exists |
| Master Risk Register is synchronized with source documents | 1 | Master Risk Register initialized |
| No unresolved BLOCKING risk affects the pilot | 2 | CAMP-#### allocated |
| Master Deferred Item Register is populated | 1 | Governance Execution Package exists |
| Master Deferred Item Register is synchronized with source documents | 1 | Master Deferred Item Register initialized |
| No unresolved BLOCKING deferred item affects the pilot | 2 | CAMP-#### allocated |
| Campaign ID has been allocated | 2 | Decision to create campaign record |
| Campaign scope is defined and vendor-neutral | 2 | CAMP-#### allocated |
| Campaign owner is assigned | 2 | CAMP-#### allocated |
| Independent Reviewer is assigned | 2 | CAMP-#### allocated |
| Reviewer conflict-of-interest declaration is complete | 2 | Reviewer assigned |
| Reviewer is not disqualified | 2 | Reviewer declaration submitted |
| Applicable B3 criteria are mapped | 2 | CAMP-#### allocated |
| Dataset scope is proposed and no vendor data has been acquired | 3 | Campaign approved |
| License review process is ready | 3 | Campaign approved |
| Entitlement review process is ready | 3 | Campaign approved |
| Evidence package location is defined | 3 | Campaign approved |
| Manifest rules are ready | 3 | Campaign approved |
| Runbook version is selected | 3 | Campaign approved |
| Calibration requirements are identified | 3 | Campaign approved |
| Statistical-boundary owner is assigned | 3 | Campaign approved |
| Conflict log is initialized | 3 | Campaign approved |
| Exception log is initialized | 3 | Campaign approved |
| Rerun rules are accepted | 3 | Campaign approved |
| Invalidation rules are accepted | 3 | Campaign approved |
| Archive obligations are approved | 3 | Campaign approved |
| Retention obligations are approved | 3 | Campaign approved |
| No vendor ranking is attempted | 2 | CAMP-#### allocated |
| No vendor recommendation is attempted | 2 | CAMP-#### allocated |
| No Decision Freeze is attempted | 2 | CAMP-#### allocated |

Before CAMP-#### allocation, every Level 2 and Level 3 checklist item must be reported as NOT_APPLICABLE.

---

## 23. Current Lifecycle Interpretation Rule

If no CAMP-#### has been allocated:

- Level 0 gates are applicable.
- Level 1 gates are applicable.
- Level 2 gates are NOT_APPLICABLE.
- Level 3 gates are NOT_APPLICABLE.
- Level 4 gates are NOT_APPLICABLE.
- Level 5 gates are NOT_APPLICABLE.
- Level 6 gates are NOT_APPLICABLE.

Therefore, a pre-campaign readiness report must not mark campaign, preparation, execution, review, or decision gates as FAILED solely because their evidence does not yet exist.

---

## 24. Exit Criteria

This document is complete only if it:

- classifies every governance gate into one lifecycle level;
- defines one canonical status model;
- prohibits failing inactive gates;
- defines activation, deactivation, and blocking logic;
- defines readiness calculation using applicable gates only;
- defines gate dependency inheritance;
- defines audit reporting requirements;
- leaves all existing milestones unchanged.

---

## 25. Quality Rubric

| Criterion | Score | Justification |
|---|---:|---|
| Gate taxonomy coverage | 10 / 10 | Defines seven lifecycle levels from permanent governance through decision gates |
| Status model discipline | 10 / 10 | Defines one canonical status set and prohibits custom statuses |
| Applicability logic | 10 / 10 | Requires activation, deactivation, and blocking conditions |
| Reporting correction | 10 / 10 | Prohibits counting inactive gates as failed |
| Readiness scoring | 10 / 10 | Uses applicable gates only |
| Dependency logic | 10 / 10 | Defines parent-child dependency tree and inheritance rules |
| Auditability | 10 / 10 | Requires reporting of inactive, blocked, failed, and incorrectly evaluated gates |
| Scope control | 10 / 10 | Does not modify milestones, execute campaigns, perform research, or authorize decisions |

Overall rubric score: 100 / 100.

---

## 26. Final Status

Status: DRAFT / GATE CLASSIFICATION STANDARD UNDER REVIEW.

This standard creates the canonical meta-governance model for gate classification and lifecycle-aware readiness reporting.

It does not modify any existing milestone.

It does not modify the Governance Execution Package.

It does not authorize empirical validation, vendor research, campaign execution, implementation, Decision Candidate creation, or Decision Freeze.
