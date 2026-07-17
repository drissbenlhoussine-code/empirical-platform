# MILESTONE 000C - EMPIRICAL VALIDATION FRAMEWORK

---

## 1. Document Control

| Field | Value |
|---|---|
| Document ID | MILESTONE-000C |
| Title | MILESTONE-000C - Empirical Validation Framework |
| Version | 1.0 |
| Status | DRAFT / FRAMEWORK UNDER REVIEW |
| Document Owner | Research Lead |
| Primary Approver | Project Owner |
| Original Publication Date | 2026-07-12 |
| Current Revision Date | 2026-07-12 |
| Approval Date | Not applicable - not approved or frozen |
| Scope | Governance framework for future empirical validation campaigns |
| Prior milestone dependencies | MILESTONE-000A; MILESTONE-000B.0; MILESTONE-000B.1; MILESTONE-000B.2; MILESTONE-000B.3; MILESTONE-000B.4 Phase 1; MILESTONE-000B.4 Phase 2 |
| Level-3 dependencies | Empirical Validation Protocol; Evidence Artifact Specification; Empirical Test Execution Runbook |

This milestone creates the governance framework that will later contain empirical validation campaigns. It does not execute tests, call APIs, download market data, compare vendors, recommend vendors, assign scores, or perform implementation.

---

## 2. Purpose

MILESTONE-000C transforms the completed research framework into a controlled empirical-validation governance layer.

It defines how future empirical validation campaigns will be authorized, calibrated, executed, reviewed, audited, reproduced, and frozen. It does not contain vendor empirical results.

---

## 3. Scope

In scope:

- Empirical validation governance.
- Campaign lifecycle.
- Campaign stages.
- Dependency boundaries.
- Calibration workflow.
- Statistical-boundary ownership.
- Evidence review workflow.
- Reviewer responsibilities.
- Audit workflow.
- Freeze governance.
- Identifier strategy.
- Reproducibility requirements.
- Milestone exit criteria.

Out of scope:

- Vendor testing.
- Vendor API calls.
- Market-data download.
- Vendor comparison or scoring.
- Vendor recommendation, selection, or rejection.
- Production implementation.
- Actual empirical result tables.

---

## 4. Objectives

MILESTONE-000C must make future empirical validation:

- reproducible;
- auditable;
- vendor-neutral;
- license-safe;
- statistically governed;
- traceable to 000B baselines;
- separable from vendor selection;
- reviewable before Decision Freeze;
- capable of producing durable evidence artifacts.

---

## 5. Boundaries

MILESTONE-000C governs empirical validation campaigns. It does not supersede:

- MILESTONE-000A governance controls.
- MILESTONE-000B.0 research methodology.
- MILESTONE-000B.3 canonical data-quality criteria.
- MILESTONE-000B.4 vendor research findings.

000C may define campaign mechanics, calibration ownership, and evidence gates. It may not alter B3 criteria, vendor research claims, or Decision Freeze requirements.

---

## 6. Dependency on 000B Milestones

| Dependency | Role in 000C |
|---|---|
| 000B.0 Research Methodology | Provides evidence sufficiency, comparison completeness, and Decision Freeze discipline |
| 000B.1 Domain Definition | Defines market/domain scope to be empirically validated |
| 000B.2 Canonical Data Model | Provides canonical field and model expectations for mapping |
| 000B.3 Data Quality Standard | Provides frozen B3 quality criteria to be empirically tested |
| 000B.4 Phase 1 Vendor Evaluation Framework | Provides frozen dimensions and vendor-evaluation structure |
| 000B.4 Phase 2 Vendor Research | Provides candidate universe, documentation-level claims, risks, deferred items, and unresolved blockers |

000C consumes these dependencies by citation and governance reference. It does not edit them.

---

## 7. Relationship to Level-3 Validation Documents

| Document | Role |
|---|---|
| Empirical Validation Protocol | Defines what must be tested and how B3 criteria are operationalized |
| Evidence Artifact Specification | Defines mandatory evidence package outputs and artifact requirements |
| Empirical Test Execution Runbook | Defines operational sequence for a future validation session |

000C is the parent empirical-validation framework. The Level-3 documents are campaign-enabling controls under 000C governance.

---

## 8. Empirical Validation Campaign Lifecycle

Every future campaign follows this lifecycle:

1. Campaign proposal.
2. Scope confirmation.
3. Calibration readiness review.
4. License and entitlement preauthorization.
5. Sample manifest approval.
6. Environment and evidence package initialization.
7. Raw data acquisition authorization.
8. Execution under the runbook.
9. Evidence package assembly.
10. Criterion-level review.
11. Exception and conflict review.
12. Reproducibility review.
13. Campaign audit.
14. Campaign close, rerun, or invalidation.
15. Eligibility assessment for downstream Decision Freeze use.

No lifecycle stage may be skipped silently.

---

## 9. Campaign Stages

| Stage | Purpose | Exit condition |
|---|---|---|
| Proposal | Define candidate/product/feed/date/instrument scope | Campaign proposal accepted for review |
| Authorization | Confirm license, entitlement, retention, and reviewer access | Authorization record approved |
| Calibration | Resolve any 000C-owned thresholds or metric definitions | Calibration record approved or deferred |
| Setup | Prepare manifest, environment, and evidence directory | Pre-run checklist approved |
| Execution | Run empirical validation under the runbook | Evidence package generated |
| Review | Independent review of artifacts, results, exceptions, conflicts | Reviewer sign-off or rejection |
| Audit | Verify reproducibility, traceability, and governance compliance | Audit report complete |
| Close | Mark valid, invalidated, rerun required, or archived | Campaign closure record |

---

## 10. Evidence Review Workflow

Evidence review must verify:

- license and entitlement basis;
- tested product/feed/version;
- raw snapshot integrity;
- normalized snapshot traceability;
- transformation logs;
- per-criterion result files;
- exception logs;
- conflict logs;
- reviewer sign-off;
- rerun instructions;
- environment and software versions;
- decision-time freshness record.

Evidence review does not decide vendor selection.

---

## 11. Reviewer Responsibilities

Reviewers must:

- verify artifact completeness;
- reject undocumented transformations;
- reject PASS states based only on documentation;
- verify blocked/not-testable states;
- verify exception disposition;
- verify conflict handling;
- verify raw-to-normalized traceability;
- verify no license violation is introduced;
- document open residual risk;
- refuse sign-off when evidence is incomplete.

Reviewer independence limitations must be disclosed.

---

## 12. Calibration Workflow

Calibration-owned items include:

- C3 quote-availability metric thresholds.
- Any tolerance for timestamp continuity.
- Any tolerance for ingestion-lag anomaly classification.
- Any statistical sample-size/power decisions.
- Any minimum historical overlap threshold.
- Any acceptable missingness tolerance not frozen in B3.

Calibration workflow:

1. Identify calibration-dependent question.
2. Classify whether inherited, illustrative, engineering-minimum, calibration-dependent, or statistical-design.
3. Propose calibration method.
4. Record assumptions.
5. Review strongest opposing evidence.
6. Approve, defer, or reject calibration.
7. Attach calibration record to affected campaigns.

No arbitrary numeric threshold may be introduced without calibration classification.

---

## 13. Statistical-Boundary Ownership

Statistical-boundary owner: Project Owner or delegated 000C Statistical Reviewer.

Responsibilities:

- approve sample-size logic;
- approve power or confidence approach if used;
- approve stratification rules;
- approve treatment of rare events;
- approve rerun comparability rules;
- prevent accidental scientific thresholds from appearing as protocol mechanics.

Statistical decisions are separate from vendor selection decisions.

---

## 14. Decision Ownership

000C may create decisions about empirical validation framework mechanics. It may not create vendor-selection decisions.

Decision ownership:

- Research Lead proposes framework decisions.
- Project Owner approves framework decisions.
- Independent Reviewer reviews evidence and audit readiness.
- Future Decision Freeze owner remains governed by 000B.0 and DEC-0033.

---

## 15. Reproducibility Requirements

Every campaign must be reproducible through:

- stable campaign ID;
- stable run ID;
- sample manifest;
- product/feed/version record;
- license/entitlement record;
- raw snapshot or lawful retention equivalent;
- checksum manifest;
- normalized snapshot;
- transformation log;
- environment manifest;
- software-version manifest;
- per-criterion result files;
- exception/conflict logs;
- rerun metadata.

If license restrictions prevent raw-data retention, the campaign must document an alternate lawful audit method or be blocked for Decision Freeze use.

---

## 16. Audit Workflow

Audit sequence:

1. Verify campaign authorization.
2. Verify evidence package completeness.
3. Verify manifest resolution.
4. Verify checksums.
5. Verify criterion-result provenance.
6. Verify exception/conflict disposition.
7. Verify calibration records.
8. Verify reviewer sign-off.
9. Verify no vendor ranking or selection occurred.
10. Produce campaign audit report.

Audit result states:

- AUDIT PASS.
- AUDIT PASS WITH NON-BLOCKING LIMITATIONS.
- AUDIT FAIL.
- AUDIT BLOCKED.
- RERUN REQUIRED.

---

## 17. Freeze Governance

000C itself may be frozen only after:

- framework exit criteria pass;
- Level-3 documents are internally consistent;
- calibration governance is sufficient;
- evidence review and audit workflows are complete;
- identifier strategy is stable;
- no blocking framework gap remains.

A future empirical campaign may be frozen only after:

- campaign evidence package passes audit;
- license/entitlement record is current;
- calibration requirements are resolved;
- reviewer signs off;
- no blocking exception or conflict remains;
- rerun requirement is either completed or explicitly waived.

Campaign freeze is not vendor Decision Freeze.

---

## 18. Document Hierarchy

| Level | Documents |
|---|---|
| Level 0 - Governance | 000A Project Governance; 000B.0 Research Methodology |
| Level 1 - Technical Foundation | 000B.1 Domain Definition; 000B.2 Canonical Data Model; 000B.3 Data Quality Standard |
| Level 2 - Vendor Research | 000B.4 Phase 1 Vendor Evaluation Framework; 000B.4 Phase 2 Vendor Research |
| Level 3 - Empirical Validation Framework | MILESTONE-000C; Empirical Validation Protocol; Evidence Artifact Specification; Empirical Test Execution Runbook |
| Level 4 - Actual Empirical Testing | Future campaigns, not started |

000C governs Level 3 and future Level 4 campaign structure.

---

## 19. Identifier Strategy

Identifier namespaces continue from 000B.4 observed ceilings:

- RES continues after RES-0040.
- DEC continues after DEC-0040.
- ASS continues after ASS-0013.
- RISK continues after RISK-0029.
- SRC, CLM, and CONF continue only when new source evidence, claims, or conflicts are actually created.

000C-specific campaign identifiers:

| Identifier | Format | Purpose |
|---|---|---|
| Campaign ID | CAMP-#### | Empirical validation campaign |
| Run ID | RUN-#### or timestamped run ID | Individual execution run |
| Artifact ID | ART-#### | Evidence artifact when a global artifact index is needed |
| Calibration ID | CAL-#### | Calibration decision or threshold record |
| Audit ID | AUD-#### | Campaign audit record |

These campaign identifiers are proposed for 000C governance and are not retroactively applied to 000B documents.

---

## 20. Framework Research Registry

**RES-0041 - Empirical validation campaign governance**
Status: PARTIALLY ANSWERED. Owner: Research Lead. Scope: MILESTONE-000C Sections 8-17. Result: campaign lifecycle, stages, review, audit, and freeze governance defined. Stop condition: independent review confirms lifecycle is sufficient for first campaign authorization. Last reviewed: 2026-07-12.

**RES-0042 - Calibration and statistical-boundary governance**
Status: PARTIALLY ANSWERED. Owner: Project Owner / Statistical Reviewer. Scope: Sections 12-13. Result: calibration workflow and ownership defined. Stop condition: first calibration record template passes review. Last reviewed: 2026-07-12.

**RES-0043 - Empirical validation document hierarchy and identifier strategy**
Status: ANSWERED FOR DRAFT. Owner: Research Lead. Scope: Sections 18-19. Result: hierarchy and identifier strategy defined. Stop condition: no namespace collision found in framework audit. Last reviewed: 2026-07-12.

---

## 21. Framework Decisions

**DEC-0041 - 000C governs empirical campaigns, not vendor selection**
Problem: empirical validation could be confused with vendor decision-making. Options: combine validation and selection; separate validation framework from selection; defer validation governance. Selected option: separate validation framework from vendor selection. Rationale: preserves research integrity and DEC-0033 boundary. Supporting evidence: 000B.0 and 000B.4 governance by citation. Opposing evidence: separation adds documents. Risk: process overhead. Validation/reversal condition: project owner determines future decision framework requires consolidation without weakening evidence controls.

**DEC-0042 - Campaign lifecycle must include authorization, calibration, execution, review, audit, and close**
Problem: empirical runs need consistent governance. Options: ad hoc campaign flow; runbook-only flow; lifecycle-governed campaign model. Selected option: lifecycle-governed campaign model. Rationale: prevents unreviewed evidence from reaching Decision Freeze. Risk: slower execution. Validation/reversal condition: first dry-run audit finds lifecycle stage unnecessary or missing.

**DEC-0043 - Calibration ownership is separate from execution ownership**
Problem: test operators may accidentally create statistical thresholds. Options: allow operator thresholds; freeze all thresholds here; assign calibration owner. Selected option: assign calibration/statistical-boundary owner. Rationale: prevents arbitrary thresholds. Risk: delays C3 and tolerance-based conclusions. Validation/reversal condition: calibration workflow fails independent review.

---

## 22. Framework Risks

| Risk ID | Statement | Control | Blocking condition |
|---|---|---|---|
| RISK-0030 | 000C could be mistaken for permission to start vendor testing | Final status and scope prohibit testing | Blocks framework freeze if ambiguous |
| RISK-0031 | Calibration decisions could smuggle arbitrary thresholds into evidence review | Calibration workflow and statistical owner required | Blocks affected campaign |
| RISK-0032 | Campaign audit could become a rubber stamp | Explicit audit states and reviewer duties | Blocks campaign freeze |
| RISK-0033 | License restrictions could prevent reproducibility | Evidence and license gates inherited from Level-3 documents | Blocks Decision-Freeze use |
| RISK-0034 | Vendor selection pressure could bias campaign design | 000C separates validation from selection | Blocks campaign approval if bias found |

---

## 23. Milestone Exit Criteria

| Criterion | Status |
|---|---|
| Scope defined | Met |
| Objectives defined | Met |
| Boundaries defined | Met |
| Dependencies on 000B milestones defined | Met |
| Relationship to Level-3 documents defined | Met |
| Campaign lifecycle and stages defined | Met |
| Evidence review workflow defined | Met |
| Reviewer responsibilities defined | Met |
| Calibration workflow and statistical ownership defined | Met |
| Decision ownership defined | Met |
| Reproducibility and audit workflow defined | Met |
| Freeze governance defined | Met |
| Document hierarchy defined | Met |
| Identifier strategy defined | Met |
| No testing, vendor comparison, scoring, recommendation, or implementation | Met |
| Ready for APPROVED AND FROZEN status | Not met - requires independent audit and review |

---

## 24. Quality Rubric

| Category | Max | Score | Evidence |
|---|---:|---:|---|
| Scope discipline | 10 | 10 | No testing, API calls, market-data download, ranking, scoring, recommendation, or implementation |
| Dependency clarity | 10 | 10 | 000B and Level-3 dependencies mapped |
| Campaign lifecycle completeness | 10 | 10 | Proposal through close and audit defined |
| Evidence review governance | 10 | 10 | Review workflow and reviewer duties defined |
| Calibration/statistical governance | 10 | 9 | Ownership and workflow defined; actual calibration templates still need review |
| Reproducibility governance | 10 | 10 | Required reproducibility artifacts defined by reference and framework |
| Audit workflow | 10 | 9 | Audit states and sequence defined; first dry-run audit may refine |
| Freeze governance | 10 | 10 | Framework freeze and campaign freeze separated from vendor Decision Freeze |
| Identifier strategy | 10 | 9 | Strategy defined; future campaign namespaces need first-use validation |
| Decision usefulness | 10 | 9 | Strong framework, still draft pending independent audit |

**Total: 96/100.** Full marks are not assigned because calibration templates, campaign identifier first-use, and dry-run audit refinement remain open.

---

## 25. Final Verification

| Check | Status |
|---|---|
| No empirical testing performed | Met |
| No API calls performed | Met |
| No market data downloaded | Met |
| No vendor compared, ranked, scored, recommended, selected, or rejected | Met |
| No implementation created | Met |
| Prior milestone documents not modified | Met |
| Status agrees with Document Control | Met |
| Level 4 testing remains not started | Met |

---

## 26. Final Status

**DRAFT / FRAMEWORK UNDER REVIEW.**

MILESTONE-000C Version 1.0 establishes the empirical validation framework. It is not approved or frozen. It creates no vendor empirical evidence and authorizes no vendor Decision Freeze.

---

*End of MILESTONE-000C Empirical Validation Framework, Version 1.0.*
