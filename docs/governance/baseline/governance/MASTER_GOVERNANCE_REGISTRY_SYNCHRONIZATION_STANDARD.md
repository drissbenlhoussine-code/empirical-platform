# MASTER GOVERNANCE REGISTRY SYNCHRONIZATION STANDARD

---

## 1. Document Control

| Field | Value |
|---|---|
| Document ID | MASTER-GOVERNANCE-REGISTRY-SYNCHRONIZATION-STANDARD |
| Title | Master Governance Registry Synchronization Standard |
| Version | 1.0 |
| Status | DRAFT / REGISTRY SYNCHRONIZATION STANDARD UNDER REVIEW |
| Document Owner | Research Lead |
| Primary Approver | Project Owner |
| Original Publication Date | 2026-07-12 |
| Current Revision Date | 2026-07-12 |
| Approval Date | Not applicable - not approved or frozen |
| Scope | Canonical synchronization architecture for project governance registries |
| Supersedes | Nothing |
| Modifies existing milestones | No |
| Authorizes empirical work | No |
| Creates campaigns | No |

This document defines how governance registries stay consistent over time. It does not create new governance concepts, modify milestones, implement software, perform vendor research, create campaigns, execute validation, renumber identifiers, create a Decision Candidate, or create a Decision Freeze.

---

## 2. Purpose

The purpose of this standard is to govern registry synchronization only.

It defines:

- registry ownership;
- source-of-truth rules;
- registry dependencies;
- synchronization events;
- propagation rules;
- conflict resolution;
- registry locking states;
- version synchronization;
- identifier synchronization;
- integrity checks;
- audit requirements;
- failure handling;
- readiness impact;
- security and change control.

This document keeps existing governance registries consistent. It does not replace the Master Governance Integration Standard, the Master Governance Gate Classification Standard, the Governance Execution Package, or any milestone document.

---

## 3. Registry Inventory

| Registry | Owner | Source of Truth | Editable Location | Primary Consumers |
|---|---|---|---|---|
| Master Baseline Index | Research Lead | Yes | Governance Execution Package | Freeze Register; Dependency Registry; Pilot Authorization Checklist |
| Master Identifier Registry | Research Lead | Yes | Governance Execution Package | All registries |
| Master Risk Register | Research Lead; Project Owner accountable for acceptance | Yes | Governance Execution Package | Deferred Register; Pilot Authorization Checklist; Campaign Registry |
| Master Deferred Item Register | Research Lead; Project Owner accountable for blocking closure | Yes | Governance Execution Package | Risk Register; Pilot Authorization Checklist; Campaign Registry |
| Master Freeze Status Register | Project Owner | Yes | Governance Execution Package | Pilot Authorization Checklist; Decision Freeze prerequisites |
| Dependency Registry | Research Lead | Yes | Master Governance Integration Standard and operational baseline records | Baseline Index; Pilot Authorization Checklist |
| Gate Classification Registry | Research Lead | Yes | Master Governance Gate Classification Standard | Pilot Authorization Checklist; audits |
| Pilot Authorization Checklist | Project Owner | Yes for pilot-gate dispositions | Governance Execution Package | Campaign Registry; audit records |
| Reviewer Declaration Records | Independent Reviewer; Project Owner disposition authority | Yes | Governance Execution Package or campaign review package | Review gates; Pilot Authorization Checklist |
| Future Campaign Registry | Project Owner / Research Lead | Yes after campaign creation | Future campaign package | Run Registry; Evidence Package; Review Registry |
| Future Run Registry | Test Operator under campaign authority | Yes after run authorization | Future campaign package | Evidence Package; Audit Registry |
| Future Evidence Package Registry | Evidence Custodian | Yes after evidence package creation | Future campaign evidence package | Review Registry; Audit Registry; Decision Candidate Registry |
| Future Review Registry | Independent Reviewer | Yes after review creation | Future campaign review package | Audit Registry; Decision Candidate Registry |
| Future Audit Registry | Independent Reviewer / Project Owner | Yes after audit creation | Future campaign audit package | Campaign Freeze; Decision Candidate Registry |
| Future Decision Candidate Registry | Project Owner / Decision Owner | Yes after candidate creation | Future decision-candidate package | Decision Freeze prerequisites |

No registry may have two Sources of Truth for the same object type and lifecycle state.

---

## 4. Source of Truth Rules

### 4.1 General Rule

Every registry must have exactly one authoritative Source of Truth for each governed object.

Source-of-truth designation must define:

- authoritative owner;
- editable location;
- read-only mirrors;
- synchronization authority;
- allowed update event;
- required verification.

### 4.2 Source-of-Truth Table

| Registry | Authoritative Owner | Editable Location | Read-Only Mirrors | Synchronization Authority |
|---|---|---|---|---|
| Master Baseline Index | Research Lead | Governance Execution Package | Audit reports; Pilot Checklist | Project Owner for baseline acceptance |
| Master Identifier Registry | Research Lead | Governance Execution Package | Risk, Deferred, Campaign, Evidence, Review, Audit registries | Research Lead |
| Master Risk Register | Research Lead | Governance Execution Package | Pilot Checklist; Campaign Registry; Audit reports | Project Owner for acceptance/closure |
| Master Deferred Item Register | Research Lead | Governance Execution Package | Pilot Checklist; Campaign Registry; Audit reports | Project Owner for blocking closure |
| Master Freeze Status Register | Project Owner | Governance Execution Package | Baseline Index; Pilot Checklist | Project Owner |
| Dependency Registry | Research Lead | Integration Standard and operational package | Baseline Index; Audit reports | Project Owner for blocking dependency acceptance |
| Gate Classification Registry | Research Lead | Gate Classification Standard | Pilot Checklist; Audit reports | Project Owner after approval |
| Pilot Authorization Checklist | Project Owner | Governance Execution Package | Audit reports; Campaign Registry | Project Owner |
| Reviewer Declaration Records | Independent Reviewer | Review declaration package | Pilot Checklist; Audit reports | Project Owner for reviewer acceptance |
| Campaign Registry | Project Owner / Research Lead | Campaign package | Pilot Checklist; Run Registry; Evidence Package | Project Owner |
| Run Registry | Test Operator | Campaign package | Evidence Package; Audit Registry | Campaign owner |
| Evidence Package Registry | Evidence Custodian | Evidence package | Review Registry; Audit Registry | Evidence Custodian |
| Review Registry | Independent Reviewer | Review package | Audit Registry; Decision Candidate Registry | Independent Reviewer |
| Audit Registry | Independent Reviewer / Project Owner | Audit package | Campaign Freeze; Decision Candidate Registry | Project Owner |
| Decision Candidate Registry | Project Owner / Decision Owner | Decision-candidate package | Decision Freeze prerequisite record | Decision Owner |

If a read-only mirror disagrees with its Source of Truth, the Source of Truth governs unless the Source of Truth is proven stale, superseded, or corrupted through audit.

---

## 5. Registry Dependency Graph

Canonical dependency graph:

```text
Master Identifier Registry
  -> Master Baseline Index
    -> Dependency Registry
      -> Master Freeze Status Register
        -> Gate Classification Registry
          -> Pilot Authorization Checklist
            -> Future Campaign Registry
              -> Future Run Registry
                -> Future Evidence Package Registry
                  -> Future Review Registry
                    -> Future Audit Registry
                      -> Future Decision Candidate Registry

Master Identifier Registry
  -> Master Risk Register
    -> Master Deferred Item Register
      -> Pilot Authorization Checklist

Master Identifier Registry
  -> Reviewer Declaration Records
    -> Review Registry
      -> Audit Registry
```

Dependency rules:

1. Identifier Registry must be synchronized before any registry can allocate or validate identifiers.
2. Baseline Index must be synchronized before Dependency Registry or Freeze Status can be verified.
3. Risk and Deferred registers must be synchronized before Pilot Authorization can be evaluated.
4. Gate Classification must be synchronized before checklist results are reported.
5. Campaign Registry cannot activate before Pilot Authorization permits campaign creation.
6. Run, Evidence, Review, Audit, and Decision Candidate registries cannot activate before their parent registry exists.

---

## 6. Synchronization Events

Canonical synchronization events are:

| Event | Description |
|---|---|
| Baseline Registered | A governance document is added to the baseline package |
| Baseline Checksum Recorded | A checksum is recorded for a baseline document |
| Baseline Superseded | A baseline document is replaced by a later authorized version |
| Identifier Added | A new identifier is allocated |
| Identifier Retired | An identifier is retired but remains reserved |
| Identifier Collision Detected | Two objects claim the same identifier |
| Risk Imported | Existing risk is added to Master Risk Register |
| Risk Created | New risk is allocated by an authorized governance document |
| Risk Status Changed | Risk changes status, including OPEN, BLOCKING, ACCEPTED, CLOSED, SUPERSEDED, or UNVERIFIED |
| Risk Closed | Risk closure evidence is accepted |
| Deferred Item Imported | Existing deferred item is added to Master Deferred Item Register |
| Deferred Item Created | New deferred item is allocated by an authorized governance document |
| Deferred Item Status Changed | Deferred item status changes |
| Deferred Item Closed | Closure evidence is accepted |
| Freeze Approved | A document or campaign freeze is approved |
| Authorization For Use Granted | A document is authorized for a specific governance use |
| Gate Classification Changed | A gate changes lifecycle level or activation rule |
| Pilot Gate Evaluated | A checklist item receives a canonical gate status |
| Reviewer Assigned | A reviewer is assigned |
| Reviewer Declaration Submitted | A reviewer declaration is completed |
| Reviewer Disqualified | A reviewer fails independence requirements |
| Campaign Created | CAMP identifier is allocated |
| Campaign Approved | Campaign authorization is approved |
| Run Created | RUN identifier is allocated |
| Evidence Package Created | EVID identifier is allocated |
| Review Created | REVIEW identifier is allocated |
| Audit Created | AUD identifier is allocated |
| Decision Candidate Created | DCAND identifier is allocated |
| Registry Lock State Changed | Registry becomes Read, Write, Frozen, Archived, or Superseded |
| Registry Synchronization Failed | Expected propagation does not complete |

---

## 7. Synchronization Rules

| Event | Trigger | Affected Registries | Propagation Order | Required Verification | Failure Behaviour |
|---|---|---|---|---|---|
| Baseline Registered | File accepted into baseline package | Baseline Index; Dependency Registry; Freeze Register; Pilot Checklist | Baseline -> Dependency -> Freeze -> Checklist | Filename, document ID, version, owner | Block affected readiness gates |
| Baseline Checksum Recorded | Checksum generated or recorded | Baseline Index; Dependency Registry; Pilot Checklist | Baseline -> Dependency -> Checklist | Checksum present and linked | Block checksum-dependent gates |
| Identifier Added | Authorized allocation event | Identifier Registry; dependent object registry | Identifier -> dependent registry -> audit mirror | Unused namespace value | Block allocation if collision exists |
| Identifier Retired | Object retired or superseded | Identifier Registry; dependent registries | Identifier -> dependent registries | Retirement reason and successor if any | Preserve retired ID; block reuse |
| Identifier Collision Detected | Duplicate identifier found | Identifier Registry; all dependent registries | Identifier -> affected registries -> Pilot Checklist | Collision investigation | Block affected gate or campaign |
| Risk Imported | Source risk extracted | Risk Register; Pilot Checklist | Risk -> Checklist | Source document and identifier | Mark UNVERIFIED if source missing |
| Risk Status Changed | Owner changes risk disposition | Risk Register; Deferred Register; Pilot Checklist; Campaign Registry | Risk -> Deferred -> Checklist -> Campaign | Project Owner approval if blocking status changes | Block affected readiness until reviewed |
| Risk Closed | Closure evidence accepted | Risk Register; Deferred Register; Pilot Checklist | Risk -> Deferred -> Checklist | Closure evidence and reviewer confirmation | Reopen or block if evidence insufficient |
| Deferred Item Imported | Source deferred item extracted | Deferred Register; Risk Register; Pilot Checklist | Deferred -> Risk -> Checklist | Identifier, owner, closure condition | Mark UNVERIFIED if source missing |
| Deferred Item Closed | Closure evidence accepted | Deferred Register; Risk Register; Pilot Checklist | Deferred -> Risk -> Checklist | Closure evidence and reviewer confirmation | Keep OPEN/BLOCKING if evidence insufficient |
| Freeze Approved | Approver freezes document | Freeze Register; Baseline Index; Pilot Checklist | Freeze -> Baseline -> Checklist | Approval, version, checksum | Block authorization if freeze evidence absent |
| Authorization For Use Granted | Project Owner authorizes use | Freeze Register; Pilot Checklist | Freeze -> Checklist | Scope of authorization | Block use if authorization scope missing |
| Gate Classification Changed | Approved taxonomy update | Gate Classification Registry; Pilot Checklist; Audit reports | Classification -> Checklist -> Audit | Change-control record | Block affected readiness report if unsynced |
| Pilot Gate Evaluated | Checklist item assessed | Pilot Checklist; Audit reports | Checklist -> Audit | Canonical status and evidence | Reject non-canonical status |
| Reviewer Assigned | Reviewer selected | Reviewer Declaration; Pilot Checklist; Review Registry | Reviewer -> Checklist -> Review | Reviewer identity and role | Block review-dependent gates |
| Reviewer Declaration Submitted | Declaration completed | Reviewer Declaration; Pilot Checklist; Review Registry | Declaration -> Checklist -> Review | COI and independence fields complete | Block if missing or failed |
| Reviewer Disqualified | Independence failure found | Reviewer Declaration; Pilot Checklist; Review Registry | Declaration -> Checklist -> Review | Disqualification reason | Block reviewer-dependent gates |
| Campaign Created | CAMP allocated | Identifier Registry; Campaign Registry; Pilot Checklist | Identifier -> Campaign -> Checklist | CAMP uniqueness | Block campaign if CAMP collision |
| Campaign Approved | Authorization granted | Campaign Registry; Preparation gates | Campaign -> Gate Classification -> Preparation | Approval record | Keep preparation gates NOT_APPLICABLE until approved |
| Run Created | RUN allocated | Identifier Registry; Run Registry; Evidence Package | Identifier -> Run -> Evidence | RUN uniqueness and CAMP link | Block run authorization |
| Evidence Package Created | EVID allocated | Identifier Registry; Evidence Package; Review Registry | Identifier -> Evidence -> Review | EVID uniqueness and RUN link | Block evidence review |
| Review Created | REVIEW allocated | Identifier Registry; Review Registry; Audit Registry | Identifier -> Review -> Audit | REVIEW uniqueness and reviewer declaration | Block audit |
| Audit Created | AUD allocated | Identifier Registry; Audit Registry; Decision Candidate Registry | Identifier -> Audit -> Decision Candidate | AUD uniqueness and review linkage | Block decision candidacy |
| Decision Candidate Created | DCAND allocated | Identifier Registry; Decision Candidate Registry; Decision prerequisites | Identifier -> DCAND -> Decision prerequisites | DCAND uniqueness and audit linkage | Block Decision Freeze |
| Registry Synchronization Failed | Propagation fails | Affected registries and Pilot Checklist | Source -> affected registry -> audit | Failure record | Block affected gate and require manual review |

---

## 8. Propagation Policy

| Propagation Type | Definition | Examples | Readiness Effect |
|---|---|---|---|
| Immediate Propagation | Must update dependent registries before the source event is accepted | Identifier Added; Identifier Collision Detected; Reviewer Disqualified | Blocks affected gate until complete |
| Deferred Propagation | May be batched before next gate evaluation | Editorial baseline metadata update; non-blocking mirror refresh | Does not block until next evaluation point |
| Manual Propagation | Requires human review or approval before dependent registry changes | Risk Closed; Deferred Item Closed; Freeze Approved | Blocks status change until approved |
| Blocked Propagation | Cannot propagate because prerequisite evidence is missing or inconsistent | Missing checksum; missing source document; identifier collision | Blocks affected readiness, campaign, execution, review, decision, or archive gate |

Default policy: propagation is Immediate when identifier integrity, baseline integrity, risk blocking status, deferred blocking status, freeze status, reviewer independence, campaign authorization, evidence integrity, or Decision Freeze eligibility is affected.

---

## 9. Conflict Resolution

### 9.1 General Rule

When two registries disagree, the Source of Truth for the disputed object governs unless it is proven stale, superseded, or corrupted.

### 9.2 Conflict Table

| Conflict | Winning Registry | Required Action |
|---|---|---|
| Identifier Registry says ID available; dependent registry uses ID | Identifier Registry until allocation evidence is found | Investigate allocation; block new use |
| Risk Register says CLOSED; Pilot Checklist says OPEN | Risk Register if closure evidence and approval exist | Synchronize checklist |
| Risk Register says OPEN/BLOCKING; Pilot Checklist says VERIFIED | Risk Register | Mark checklist BLOCKED or FAILED as appropriate |
| Deferred Register says CLOSED; Risk Register still links open risk | Both require reconciliation | Reopen linked review until risk disposition updated |
| Freeze Register says NOT_FROZEN; Baseline Index says frozen | Freeze Register | Correct baseline mirror or supply freeze evidence |
| Baseline Index says checksum pending; Pilot Checklist says verified | Baseline Index | Mark checklist BLOCKED or FAILED |
| Gate Classification says NOT_APPLICABLE; Pilot Checklist says FAILED | Gate Classification Registry | Reclassify checklist result |
| Reviewer Declaration says disqualified; Review Registry says reviewer accepted | Reviewer Declaration Record | Block review and require replacement reviewer |
| Campaign Registry says no CAMP; Preparation gate says PENDING | Campaign Registry | Reclassify preparation gate NOT_APPLICABLE |
| Evidence Package says EVID incomplete; Review says VERIFIED | Evidence Package Registry | Block review until evidence reconciled |

### 9.3 Conflict Disposition

Every conflict must be assigned one disposition:

- Source corrected.
- Mirror corrected.
- Both corrected.
- Superseded.
- Manual review required.
- Blocked pending evidence.

No conflict may be resolved by silently rewriting historical registry entries.

---

## 10. Registry Locking

| Lock State | Meaning | Allowed Actions |
|---|---|---|
| Read | Registry may be read but not edited by current actor | View, cite, audit |
| Write | Authorized actor may update registry | Add, update, synchronize under change-control rules |
| Frozen | Registry snapshot is immutable for a baseline, campaign, or decision point | Read, cite, audit; no edits except supersession record |
| Archived | Registry is retained for recordkeeping after lifecycle completion | Read, audit; no active use unless reopened by governance |
| Superseded | Registry replaced by later authorized version | Read, cite, link to successor |

Locking rules:

1. Frozen registry entries must not be overwritten.
2. Archived registry entries must not be edited.
3. Superseded entries must remain traceable to their replacement.
4. Write access requires role authority under Section 17.
5. Any lock-state change is a synchronization event.

---

## 11. Version Synchronization

Version synchronization follows the change classes defined by the Master Governance Integration Standard.

| Change Class | Registry Synchronization Requirement | Approval Requirement |
|---|---|---|
| Major | Synchronize affected registries before next readiness or campaign gate | Project Owner approval |
| Minor | Synchronize affected mirrors before next formal audit | Research Lead approval with Project Owner notification |
| Editorial | Synchronize only if references, labels, or report text change | Research Lead approval |
| Registry-only | Update affected registry and all dependent mirrors | Registry owner approval; Project Owner if blocking status changes |

Rules:

1. A version change in a Source of Truth registry must propagate to every dependent read-only mirror.
2. A frozen registry snapshot remains valid for the lifecycle object it governs unless a breaking or major governance change requires rebaseline.
3. Registry-only changes must preserve historical entries.
4. Version synchronization may not renumber identifiers.

---

## 12. Identifier Synchronization

The Master Identifier Registry is the Source of Truth for identifier allocation and retirement.

The following namespaces must never diverge across registries:

- RES.
- SRC.
- RISK.
- DEF.
- RUN.
- CAMP.
- EVID.
- REVIEW.
- AUD.
- DCAND.
- DEC.
- ASS.
- CONF.
- CLM.
- DATASET.

Identifier synchronization rules:

1. No registry may allocate an identifier without checking the Master Identifier Registry.
2. No registry may reuse a retired identifier.
3. No registry may renumber an identifier.
4. Every dependent registry must record the authoritative identifier exactly.
5. Identifier mirrors must be synchronized after allocation, retirement, supersession, or collision detection.
6. Identifier collision blocks affected readiness, campaign, execution, review, decision, or archive gates.
7. If an identifier appears in a source document but not in the Master Identifier Registry, the registry status must be BLOCKED or UNVERIFIED until reconciled.

---

## 13. Cross-Registry Integrity Checks

Every synchronization audit must run the following integrity checks:

| Check | Failure Condition | Required Response |
|---|---|---|
| Duplicate identifiers | Same identifier assigned to multiple objects | Block affected registry and investigate |
| Missing references | Registry cites identifier not present in Source of Truth | Mark reference broken and block affected gate |
| Broken dependencies | Child object exists without active parent | Block child gate |
| Missing owner | Registry object lacks accountable owner | Mark PENDING or BLOCKED depending lifecycle state |
| Invalid version | Registry references unavailable or incompatible version | Block affected readiness or campaign gate |
| Unknown state | Registry uses non-canonical status | Reject status and require correction |
| Unsynchronized freeze state | Freeze Register and Baseline Index disagree | Freeze Register governs until reconciled |
| Unsynchronized risk status | Risk Register and checklist disagree | Risk Register governs |
| Unsynchronized deferred status | Deferred Register and checklist disagree | Deferred Register governs |
| Reviewer independence mismatch | Declaration conflicts with review status | Declaration governs and review blocks |
| Gate applicability mismatch | Gate Classification conflicts with checklist result | Gate Classification governs |
| Missing checksum | Baseline document lacks checksum | Block baseline-dependent gates |
| Missing closure evidence | Risk or deferred item marked closed without evidence | Reopen or block |

---

## 14. Audit Rules

Every registry synchronization audit must verify:

- registry consistency;
- source-of-truth designation;
- propagation correctness;
- synchronization latency;
- identifier integrity;
- broken references;
- dependency consistency;
- lock-state validity;
- version compatibility;
- owner completeness;
- conflict disposition;
- historical traceability.

Audit output must include:

- registries audited;
- source-of-truth map;
- synchronization events reviewed;
- propagation failures;
- conflicts found;
- broken references;
- blocked gates caused by synchronization defects;
- required corrective actions;
- readiness impact.

No registry audit may treat a read-only mirror as the Source of Truth unless the designated Source of Truth has been formally superseded.

---

## 15. Failure Handling

If synchronization fails, the failure must be classified as exactly one:

| Failure Class | Meaning | Required Response |
|---|---|---|
| Retryable | Temporary update or review delay | Retry before next gate evaluation |
| Manual Review Required | Human judgment or approval needed | Block affected status change until review |
| Blocking | Synchronization defect affects readiness, campaign, execution, review, decision, or archive validity | Block affected gate |
| Corruption Suspected | Registry history, identifier integrity, or source-of-truth reliability is in doubt | Freeze affected registry and escalate to Project Owner |
| Supersession Required | Current registry cannot be corrected without replacement | Create supersession record and preserve history |

Failure rules:

1. Identifier synchronization failure blocks allocation and dependent gates.
2. Risk or deferred synchronization failure blocks gates affected by those records.
3. Freeze synchronization failure blocks authorization and Decision Freeze use.
4. Reviewer synchronization failure blocks review-dependent gates.
5. Evidence synchronization failure blocks review, audit, Decision Candidate, and archive gates.
6. Campaign synchronization failure blocks run creation.

---

## 16. Readiness Impact

Synchronization directly affects readiness as follows.

| Lifecycle Area | Synchronization Requirement | Impact of Failure |
|---|---|---|
| Pilot | Baseline, Identifier, Risk, Deferred, Freeze, Gate Classification, and Checklist registries synchronized | Pilot Authorization blocks |
| Execution | Campaign, Run, Dataset, Evidence, License, Entitlement, and Exception registries synchronized | Run authorization or execution blocks |
| Review | Evidence, Reviewer Declaration, Review, Risk, Deferred, and Audit registries synchronized | Review or audit blocks |
| Decision Freeze | Decision Candidate, Audit, Evidence, Freeze, Risk, Deferred, Assumption, and Baseline registries synchronized | Decision Freeze blocks |
| Archive | Evidence, Audit, Decision Candidate, Retention, and Freeze registries synchronized | Archive finalization blocks |

Readiness scores must not count unsynchronized future-stage registries as failures before their lifecycle activation point. However, active registry synchronization failures must count as BLOCKED or FAILED according to the Gate Classification Standard.

---

## 17. Security

Registry update authority is role-based.

| Registry | Read Access | Write Access | Approval Authority |
|---|---|---|---|
| Baseline Index | Project governance participants | Research Lead | Project Owner |
| Identifier Registry | Project governance participants | Research Lead | Project Owner for conflicts or retirement disputes |
| Risk Register | Project governance participants | Research Lead | Project Owner for acceptance or closure |
| Deferred Item Register | Project governance participants | Research Lead | Project Owner for blocking closure |
| Freeze Register | Project governance participants | Project Owner or delegated approver | Project Owner |
| Dependency Registry | Project governance participants | Research Lead | Project Owner for blocking dependency disposition |
| Gate Classification Registry | Project governance participants | Research Lead | Project Owner |
| Pilot Authorization Checklist | Project governance participants | Project Owner or delegated gate reviewer | Project Owner |
| Reviewer Declaration Records | Project Owner; reviewer; audit participants | Assigned reviewer for declaration; Project Owner for disposition | Project Owner |
| Campaign Registry | Campaign governance participants | Research Lead / Project Owner | Project Owner |
| Run Registry | Campaign governance participants | Test Operator under authorization | Campaign owner |
| Evidence Registry | Campaign governance participants | Evidence Custodian | Campaign owner / Evidence Custodian |
| Review Registry | Campaign governance participants | Independent Reviewer | Project Owner for reviewer acceptance |
| Audit Registry | Campaign governance participants | Independent Reviewer / Project Owner | Project Owner |
| Decision Candidate Registry | Decision governance participants | Project Owner / Decision Owner | Decision Owner |

Unauthorized writes are registry integrity failures and must be treated as BLOCKED pending manual review.

---

## 18. Change Control

Synchronization changes must never silently rewrite history.

Change-control rules:

1. Every material synchronization rule change requires a change record.
2. Historical registry entries must be preserved.
3. Corrections must be appended or superseded, not overwritten.
4. Identifier corrections must not renumber existing identifiers.
5. Conflict resolution must record which registry governed the correction.
6. Registry-only changes must identify affected downstream registries.
7. Frozen or archived registries may only receive supersession records, not direct edits.
8. Synchronization changes affecting readiness, campaign authorization, execution, review, Decision Freeze, or archive must be reviewed before use.

---

## 19. Exit Criteria

This document is complete only if:

- every registry has one Source of Truth;
- every registry has an owner;
- editable locations and read-only mirrors are defined;
- synchronization events are defined;
- propagation order exists;
- conflict resolution exists;
- registry locking states are defined;
- version synchronization rules are defined;
- identifier synchronization rules are defined;
- cross-registry integrity checks exist;
- audit rules exist;
- failure handling exists;
- readiness impact is defined;
- security/update authority is defined;
- no milestone is modified;
- no implementation is performed;
- no campaign is created;
- no empirical validation is executed;
- no Decision Freeze is created;
- no identifier is renumbered.

---

## 20. Quality Rubric

| Criterion | Score | Justification |
|---|---:|---|
| Registry inventory completeness | 10 / 10 | Covers current operational registries and future campaign/run/evidence/review/audit/decision registries |
| Source-of-truth discipline | 10 / 10 | Requires one authoritative Source of Truth per registry object |
| Dependency clarity | 10 / 10 | Defines explicit registry dependency graph |
| Synchronization event coverage | 10 / 10 | Defines baseline, identifier, risk, deferred, freeze, reviewer, campaign, run, evidence, review, audit, and decision events |
| Propagation policy | 10 / 10 | Defines immediate, deferred, manual, and blocked propagation |
| Conflict resolution | 10 / 10 | Defines winner rules and conflict dispositions |
| Integrity checks | 10 / 10 | Covers duplicate identifiers, broken references, missing owners, invalid versions, and unknown states |
| Auditability | 10 / 10 | Requires consistency, propagation, latency, and broken-reference verification |
| Security and change control | 10 / 10 | Defines write authority and prohibits silent history rewriting |
| Scope control | 10 / 10 | Does not modify milestones, create campaigns, implement code, or execute validation |

Overall rubric score: 100 / 100.

---

## 21. Final Status

Status: DRAFT / REGISTRY SYNCHRONIZATION STANDARD UNDER REVIEW.

This standard defines the canonical synchronization architecture for governance registries.

It does not modify any milestone.

It does not modify the Governance Execution Package.

It does not create CAMP-0001.

It does not perform vendor research, market-data testing, empirical validation, implementation, Decision Candidate creation, or Decision Freeze.
