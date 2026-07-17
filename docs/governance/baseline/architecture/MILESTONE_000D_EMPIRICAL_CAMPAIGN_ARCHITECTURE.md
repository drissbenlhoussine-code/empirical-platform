# MILESTONE-000D EMPIRICAL CAMPAIGN ARCHITECTURE

---

## 1. Document Control

| Field | Value |
|---|---|
| Document ID | MILESTONE-000D |
| Title | MILESTONE-000D - Empirical Campaign Architecture |
| Version | 1.0 |
| Status | DRAFT / ARCHITECTURE UNDER REVIEW |
| Document Owner | Research Lead |
| Primary Approver | Project Owner |
| Original Publication Date | 2026-07-12 |
| Current Revision Date | 2026-07-12 |
| Approval Date | Not applicable - not approved or frozen |
| Scope | Conceptual architecture for future empirical validation campaign execution |
| Governance Dependencies | MILESTONE-000A through MILESTONE-000C; Master Governance Integration Standard; Master Governance Gate Classification Standard; Master Governance Registry Synchronization Standard |
| Research Dependencies | MILESTONE-000B.1 through MILESTONE-000B.4 |
| Implementation Status | No implementation |
| Empirical Execution Status | Not started |

This milestone designs the architecture that will later execute empirical validation campaigns. It bridges governance, research, and future implementation without implementing software, testing vendors, calling APIs, downloading market data, comparing vendors, ranking vendors, recommending vendors, creating a Decision Candidate, or creating a Decision Freeze.

---

## 2. Architecture Overview

MILESTONE-000D defines the conceptual execution architecture for empirical validation campaigns.

Canonical execution flow:

```text
Campaign
  -> Authorization
    -> Preparation
      -> Acquisition
        -> Normalization
          -> Validation
            -> Evidence
              -> Review
                -> Audit
                  -> Decision Candidate
```

The architecture separates:

- campaign governance from empirical execution;
- raw acquisition from normalization;
- validation results from evidence review;
- evidence review from audit;
- Decision Candidate eligibility from Decision Freeze.

No stage may execute unless its parent governance gates are active and satisfied.

---

## 3. Component Architecture

The architecture contains the following conceptual components.

| Component | Purpose | Primary Inputs | Primary Outputs |
|---|---|---|---|
| Campaign Controller | Coordinates campaign lifecycle, state transitions, and gate checks | Campaign proposal, authorization record, gate status | Campaign state, run authorization |
| Registry Coordinator | Reads governance registries and verifies synchronization state | Identifier, risk, deferred, freeze, baseline, gate, and synchronization registries | Gate readiness disposition |
| Dataset Manager | Defines dataset scope and preserves raw/normalized dataset boundaries | Dataset proposal, entitlement evidence, acquisition outputs | Dataset records and dataset state |
| Acquisition Coordinator | Controls authorized vendor-neutral acquisition workflow | Authorization, entitlement, license clearance, dataset scope | Raw dataset and acquisition log |
| Normalization Boundary Manager | Maintains raw-preserving transformation boundaries | Raw dataset, canonical field rules, transformation policy | Normalized dataset and transformation log |
| Validation Engine | Applies approved criterion checks to available data | Normalized dataset, raw references, B3 criteria, calibration records | Criterion results |
| Evidence Manager | Builds evidence packages and enforces artifact completeness | Raw data, normalized data, logs, criterion results | Evidence Package |
| Exception and Conflict Manager | Captures operational exceptions and evidence conflicts | Run events, validation anomalies, reviewer findings | Exception log and conflict log |
| Review Manager | Coordinates independent review and reviewer declarations | Evidence package, reviewer declaration, criterion results | Review record |
| Audit Manager | Verifies lifecycle, evidence, review, and traceability integrity | Review record, evidence package, registries | Audit record |
| Decision Candidate Builder | Creates candidate evidence bundle only when review and audit gates pass | Audit record, evidence package, review disposition | Decision Candidate |

These are logical components only. This document defines no code, API, database schema, workflow engine, or implementation design.

---

## 4. Campaign Object Model

Canonical execution objects:

| Object | Definition | Identifier Namespace | Parent Object |
|---|---|---|---|
| Campaign | Governed validation effort with defined scope and objectives | CAMP | None |
| Run | One authorized execution attempt under a campaign | RUN | Campaign |
| Dataset | Raw and normalized data scope used by a run | DATASET | Run |
| Evidence Package | Complete artifact bundle proving what happened | EVID | Run |
| Criterion Result | Per-criterion validation output | CRIT or ART where globally indexed | Evidence Package |
| Review | Independent review of evidence and results | REVIEW | Evidence Package |
| Audit | Governance and evidence integrity audit | AUD | Review / Campaign |
| Decision Candidate | Evidence bundle eligible for later decision governance | DCAND | Audit |

Object rules:

1. No Run may exist without a Campaign.
2. No Dataset may exist without a Run.
3. No Evidence Package may exist without a Run.
4. No Criterion Result may exist without an Evidence Package.
5. No Review may be accepted without an Evidence Package.
6. No Audit may be accepted without a Review.
7. No Decision Candidate may exist without a successful or limitation-accepted Audit.
8. No Decision Candidate is a Decision Freeze.

---

## 5. Execution Lifecycle

| Stage | Objective | Activation Condition | Output |
|---|---|---|---|
| Campaign Draft | Define campaign scope and objectives | Campaign proposal created | Draft campaign proposal |
| Authorization Review | Assess readiness to request authorization | Proposal exists | Authorization review disposition |
| Authorization | Decide whether campaign may proceed | Required governance gates satisfied | Authorization record |
| Preparation | Prepare operational evidence structures | Campaign authorized | Evidence directory, logs, manifest, dataset proposal |
| Acquisition | Acquire raw data under authorization | License, entitlement, and run authorization satisfied | Raw dataset and acquisition log |
| Normalization | Create auditable normalized dataset | Raw dataset preserved | Normalized dataset and transformation log |
| Validation | Execute approved criterion checks | Required data and criteria available | Criterion results |
| Evidence Packaging | Assemble required artifacts | Run artifacts available | Evidence Package |
| Review | Independent review of evidence and results | Evidence Package complete enough for review | Review record |
| Audit | Verify governance, traceability, and reproducibility | Review complete | Audit record |
| Decision Candidate Assessment | Determine whether evidence can become candidate | Audit accepted | Decision Candidate or rejection record |
| Closure | Archive, invalidate, or close campaign | Final disposition reached | Archive record |

This lifecycle is conceptual. It does not authorize execution.

---

## 6. Data Flow

Canonical data flow:

```text
Vendor Data
  -> Raw Dataset
    -> Normalized Dataset
      -> Validation Engine
        -> Criterion Results
          -> Evidence Package
            -> Review
              -> Audit
```

Data-flow rules:

1. Vendor Data must not be acquired before authorization.
2. Raw Dataset must be preserved before normalization.
3. Normalized Dataset must reference raw source records and transformation logs.
4. Validation Engine must not invent unavailable fields.
5. Criterion Results must link to raw and normalized evidence where applicable.
6. Evidence Package must include manifests, hashes, logs, and review materials.
7. Review must not alter evidence.
8. Audit must verify traceability and reproducibility.

---

## 7. Governance Integration

Every execution stage must reference active governance registries.

| Stage | Required Governance Integration |
|---|---|
| Campaign Draft | Identifier Registry; Gate Classification; Registry Synchronization |
| Authorization Review | Baseline Index; Dependency Registry; Risk Register; Deferred Register; Freeze Register |
| Authorization | Pilot Authorization Checklist; Reviewer Declaration; Gate Classification |
| Preparation | Identifier Registry; Evidence Artifact Specification; Runbook; Deferred Register |
| Acquisition | License evidence; entitlement evidence; Risk Register; Exception Log |
| Normalization | Transformation log; Evidence Specification; Risk Register |
| Validation | B3 criteria; Protocol; Calibration record; Deferred Register |
| Evidence Packaging | Evidence Artifact Specification; checksum register; audit trail |
| Review | Reviewer declaration; Review Registry; Risk and Deferred status |
| Audit | Audit Registry; Registry Synchronization; traceability checks |
| Decision Candidate Assessment | Decision Candidate Registry; Decision Freeze prerequisites; audit disposition |

Governance integration rule: if a required active governance registry is BLOCKED or unsynchronized, the dependent execution stage must not proceed.

---

## 8. Failure Architecture

Failure propagation is explicit and lifecycle-bound.

| Failure Type | Detection Point | Propagation | Required Disposition |
|---|---|---|---|
| Dataset failure | Acquisition, normalization, validation | Blocks run; may trigger rerun or invalidation | Exception log and reviewer disposition |
| Evidence corruption | Evidence packaging or audit | Blocks review, audit, Decision Candidate | Quarantine evidence and run integrity check |
| Missing entitlement | Authorization or acquisition | Blocks acquisition and run authorization | Entitlement evidence or campaign limitation |
| License violation | Authorization, acquisition, retention review | Blocks acquisition, evidence retention, Decision Candidate | Stop condition and legal/governance review |
| Validation failure | Criterion execution | Blocks criterion PASS, not necessarily campaign closure | Criterion result disposition |
| Calibration failure | Calibration-dependent validation | Blocks affected criteria | Calibration review or criterion limitation |
| Reviewer conflict | Review assignment or audit | Blocks review acceptance | Replacement reviewer or campaign block |
| Registry synchronization failure | Any gate transition | Blocks dependent gate | Synchronization repair or manual review |
| Identifier collision | Object creation | Blocks object creation | Registry correction before proceeding |

Failure architecture rule: a failure must propagate only to affected dependent objects and gates. Future-stage gates that are not active remain NOT_APPLICABLE.

---

## 9. Reproducibility Model

A campaign is reproducible only if an independent researcher can reconstruct:

- campaign scope;
- authorization basis;
- run identity;
- dataset scope;
- acquisition method and entitlement context;
- raw-data snapshot;
- normalized-data derivation;
- transformation logs;
- validation criteria;
- criterion result generation;
- environment and software-version context;
- evidence hashes;
- exception and conflict history;
- reviewer disposition;
- audit disposition;
- archive package.

Reproducibility obligations:

1. Raw data must be preserved when license permits.
2. If raw preservation is restricted, the limitation must be explicit.
3. Every transformation must be logged.
4. Every criterion result must link to inputs and evidence.
5. Every review and audit must cite the evidence package version.
6. Every rerun must preserve lineage to the original run.

---

## 10. State Machine

### 10.1 Campaign State

```text
DRAFT
  -> READY_FOR_AUTHORIZATION
  -> AUTHORIZED
  -> PREPARATION
  -> EXECUTION
  -> REVIEW
  -> AUDIT
  -> DECISION_CANDIDATE
  -> CLOSED
```

### 10.2 Run State

```text
NOT_CREATED
  -> PLANNED
  -> AUTHORIZED
  -> ACTIVE
  -> BLOCKED
  -> VALID
  -> INVALIDATED
  -> RERUN_REQUIRED
  -> ARCHIVED
```

### 10.3 Evidence State

```text
NOT_CREATED
  -> INITIALIZED
  -> CAPTURING
  -> COMPLETE
  -> REVIEWABLE
  -> AUDITED
  -> LIMITED
  -> INVALIDATED
  -> ARCHIVED
```

### 10.4 Review State

```text
NOT_STARTED
  -> ASSIGNED
  -> COI_SUBMITTED
  -> IN_REVIEW
  -> ACCEPTED
  -> ACCEPTED_WITH_LIMITATIONS
  -> REJECTED
  -> SUPERSEDED
```

### 10.5 Audit State

```text
NOT_STARTED
  -> IN_AUDIT
  -> PASS
  -> PASS_WITH_LIMITATIONS
  -> FAIL
  -> BLOCKED
  -> SUPERSEDED
```

### 10.6 Decision Candidate State

```text
NOT_APPLICABLE
  -> ELIGIBLE
  -> CREATED
  -> REJECTED
  -> SUPERSEDED
  -> ARCHIVED
```

State-machine rule: state names in this architecture are conceptual and must be mapped to the canonical gate status model before readiness reporting.

---

## 11. Dependency Graph

```text
Campaign
  -> Authorization Review
    -> Authorization Record
      -> Run
        -> Dataset
          -> Raw Dataset
          -> Normalized Dataset
        -> Evidence Package
          -> Criterion Results
          -> Transformation Logs
          -> Exception Logs
          -> Conflict Logs
        -> Review
          -> Reviewer Declaration
          -> Review Report
        -> Audit
          -> Audit Report
        -> Decision Candidate
```

Dependency constraints:

- Campaign depends on governance baseline readiness.
- Authorization depends on active gate verification.
- Run depends on campaign authorization.
- Dataset depends on run authorization.
- Evidence Package depends on dataset and run artifacts.
- Review depends on evidence package and reviewer independence.
- Audit depends on review and evidence traceability.
- Decision Candidate depends on audit acceptance.

---

## 12. Traceability Model

Traceability chain:

```text
Campaign
  -> Run
    -> Dataset
      -> Evidence Package
        -> Criterion Result
          -> Review
            -> Audit
              -> Decision Candidate
```

Each object must preserve:

| Object | Required Trace Links |
|---|---|
| Campaign | Governance dependencies, scope, owner, risks, deferred items |
| Run | Campaign ID, run authorization, runbook version |
| Dataset | Run ID, data scope, entitlement context, raw snapshot |
| Evidence Package | Run ID, dataset ID, manifest, hashes, artifact inventory |
| Criterion Result | Evidence Package ID, criterion ID, inputs, result state |
| Review | Evidence Package ID, reviewer declaration, findings |
| Audit | Review ID, evidence package, traceability checks |
| Decision Candidate | Audit ID, evidence package, review disposition |

Traceability is continuous only when every object can be followed forward and backward without orphan identifiers.

---

## 13. Security Boundaries

Logical trust boundaries:

| Boundary | Purpose | Examples |
|---|---|---|
| Governance Boundary | Controls authorization, gates, identifiers, risk, and freeze state | Baseline Index, Identifier Registry, Risk Register |
| Campaign Boundary | Controls campaign state and scope | Campaign Registry, Campaign Proposal |
| Acquisition Boundary | Separates authorized data access from governance planning | Entitlement, license, acquisition logs |
| Raw Evidence Boundary | Preserves original data without normalization changes | Raw dataset, raw hashes |
| Transformation Boundary | Records changes between raw and normalized datasets | Transformation logs |
| Validation Boundary | Produces criterion results without altering evidence | Validation Engine outputs |
| Review Boundary | Prevents reviewer from modifying evidence | Review records |
| Audit Boundary | Verifies integrity without changing source evidence | Audit records |
| Decision Boundary | Separates evidence eligibility from Decision Freeze | Decision Candidate records |

Security rule: no component may silently cross a trust boundary without a logged artifact and governance-visible state transition.

---

## 14. Scalability

The architecture supports multiple campaigns by enforcing:

- unique CAMP identifiers;
- unique RUN identifiers under each campaign;
- independent evidence packages;
- campaign-scoped registries where appropriate;
- shared master registries for identifiers, risks, deferred items, freeze status, and gate classification;
- immutable archive records;
- explicit parent-child lineage.

Multiple campaigns may coexist if:

- identifier namespaces remain collision-free;
- campaign scopes do not silently overlap;
- evidence packages remain isolated;
- reviewers disclose conflicts per campaign;
- shared risks and deferred items propagate consistently.

---

## 15. Extensibility

Future domains may be added without changing the core architecture.

Potential future domains:

- L2 market depth.
- L3 order-level data.
- Options.
- Futures.
- Corporate actions.
- Reference data.
- Calendar data.
- Alternative market data.

Extensibility rules:

1. A new domain must define its own campaign scope.
2. The object model remains Campaign -> Run -> Dataset -> Evidence -> Review -> Audit.
3. Domain-specific criteria may extend validation inputs but must not bypass B3 or successor criteria.
4. Evidence packaging remains raw-preserving and reproducible.
5. Registry synchronization remains mandatory.
6. Decision Candidate remains separate from Decision Freeze.

---

## 16. Exit Criteria

MILESTONE-000D is complete only if:

- every execution object is defined;
- lifecycle is complete;
- governance integration is complete;
- data flow is defined;
- failure propagation is defined;
- reproducibility is preserved;
- state machines are defined;
- dependency graph is complete;
- traceability is continuous;
- security boundaries are defined;
- multi-campaign scalability is addressed;
- future-domain extensibility is addressed;
- no implementation exists;
- no empirical execution occurs;
- no vendor is selected, ranked, rejected, or recommended;
- no API design is created;
- no database schema is created;
- no workflow engine implementation is created;
- no Decision Candidate or Decision Freeze is created.

---

## 17. Final Status

Status: DRAFT / ARCHITECTURE UNDER REVIEW.

This document defines conceptual architecture only.

It does not implement software.

It does not execute empirical validation.

It does not call APIs or download data.

It does not compare, rank, recommend, select, or reject vendors.

It does not authorize CAMP-0001.

It does not create a Decision Candidate.

It does not create a Decision Freeze.
