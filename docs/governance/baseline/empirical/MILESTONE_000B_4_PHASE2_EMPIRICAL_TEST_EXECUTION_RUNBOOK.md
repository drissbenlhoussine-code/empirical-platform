# MILESTONE 000B.4 - PHASE 2 EMPIRICAL TEST EXECUTION RUNBOOK

---

## 1. Document Control

| Field | Value |
|---|---|
| Document ID | MILESTONE-000B.4-P2-ETER |
| Title | MILESTONE 000B.4 - PHASE 2 Empirical Test Execution Runbook |
| Version | 1.0 |
| Status | DRAFT / RUNBOOK UNDER REVIEW |
| Document Owner | Research Lead |
| Primary Approver | Project Owner |
| Original Publication Date | 2026-07-12 |
| Current Revision Date | 2026-07-12 |
| Approval Date | Not applicable |
| Complements | MILESTONE-000B.4-P2-C1-EVP; MILESTONE-000B.4-P2-EAS |

This runbook describes the execution workflow for a future empirical validation session. It does not perform testing, write implementation code, select a vendor, rank a vendor, recommend a vendor, or modify any previous milestone document.

---

## 2. Purpose

The purpose of this runbook is to make a future empirical validation session executable by an independent researcher with identical procedural behavior.

The runbook defines operational sequence, stop gates, reviewer checkpoints, evidence capture checkpoints, invalidation handling, rerun handling, archival, and rollback.

---

## 3. Scope and Non-Goals

In scope:

- Pre-run checklist.
- Environment verification.
- License and entitlement verification.
- Dataset preparation workflow.
- Evidence directory initialization.
- Manifest creation.
- Generic vendor-neutral raw-data acquisition procedure.
- Normalization sequence.
- Criterion execution order.
- Evidence checkpoints.
- Exception and conflict logging.
- Reviewer checkpoints.
- Rerun procedure.
- Post-run integrity verification.
- Evidence package verification.
- Archival and rollback.

Out of scope:

- Performing tests.
- Downloading vendor data.
- Calling APIs.
- Writing code.
- Choosing, ranking, recommending, selecting, or rejecting vendors.
- Decision Freeze.

---

## 4. Operational Step Template

Every step in this runbook is governed by:

| Field | Meaning |
|---|---|
| Objective | Why the step exists |
| Inputs | Required inputs before starting |
| Outputs | Artifacts or decisions produced |
| Required evidence | Evidence that must be captured |
| Failure conditions | Conditions that make the step fail |
| Stop conditions | Conditions requiring the run to pause or abort |
| Reviewer responsibilities | What reviewer must inspect or approve |

---

## 5. Run State Machine

Allowed run states:

- `NOT_STARTED`
- `PRECHECK_IN_PROGRESS`
- `BLOCKED_PRE_RUN`
- `AUTHORIZED_FOR_ACQUISITION`
- `ACQUISITION_IN_PROGRESS`
- `ACQUISITION_BLOCKED`
- `NORMALIZATION_IN_PROGRESS`
- `CRITERION_EXECUTION_IN_PROGRESS`
- `REVIEW_IN_PROGRESS`
- `RUN_VALID`
- `RUN_INVALIDATED`
- `ARCHIVED`
- `RERUN_REQUIRED`

State transitions must be recorded in the audit trail.

---

## 6. Pre-Run Checklist

Objective: confirm the run may begin.

Inputs:

- Approved protocol version.
- Evidence artifact specification.
- Candidate/product/feed selected for testing by prior governance, not by this runbook.
- Draft run ID.
- Assigned operator.
- Assigned reviewer.

Outputs:

- Pre-run checklist record.
- Initial run state.

Required evidence:

- Protocol version reference.
- Artifact-spec version reference.
- Operator/reviewer assignment.
- Candidate/product/feed identity record.

Failure conditions:

- No reviewer assigned.
- Candidate/product/feed identity incomplete.
- Protocol or artifact spec unavailable.

Stop conditions:

- Any failure condition.
- Any attempt to use this runbook to select a vendor.

Reviewer responsibilities:

- Verify that the runbook is being used only for execution of a separately authorized test.
- Confirm no ranking or selection is occurring inside the run.

---

## 7. Environment Verification

Objective: ensure the execution environment can be reproduced.

Inputs:

- Environment manifest template.
- Software-version manifest template.
- Planned execution machine or environment.

Outputs:

- Environment manifest.
- Software-version manifest.

Required evidence:

- OS/runtime/package versions.
- Tool/script versions if any.
- Configuration hashes.
- Timezone and locale settings.
- Dirty-state disclosure if local tooling is used.

Failure conditions:

- Environment cannot be captured.
- Required version information unavailable.
- Secrets appear in captured metadata.

Stop conditions:

- Secrets cannot be removed.
- Environment capture is insufficient for rerun.

Reviewer responsibilities:

- Confirm reproducibility metadata is sufficient.
- Confirm no secret or credential is stored.

---

## 8. License Verification

Objective: verify the run is legally allowed.

Inputs:

- License agreement, order form, support response, or approved entitlement record.
- Evidence artifact retention requirements.

Outputs:

- License evidence record.
- Retention-rights record.

Required evidence:

- Permitted testing scope.
- Storage/retention rights.
- Reviewer access rights.
- Redistribution restrictions.
- Derived-data/non-display rights where relevant.

Failure conditions:

- Testing rights unknown.
- Retention prohibited for required evidence.
- Reviewer access prohibited.

Stop conditions:

- Any license right required for the run is unknown or denied.

Reviewer responsibilities:

- Verify that marketing language alone is not used as permission.
- Confirm license evidence covers the actual product/feed under test.

---

## 9. Entitlement Verification

Objective: verify the operator is entitled to the exact product/feed/version being tested.

Inputs:

- Entitlement record.
- Product/feed identity.
- Account or institution access evidence.

Outputs:

- Entitlement evidence record.

Required evidence:

- Product name.
- Feed name.
- Delivery mechanism.
- Account/institution status.
- Professional/non-professional status if relevant.
- Access tier.
- Product version or dataset version.

Failure conditions:

- Entitlement does not match product/feed.
- Product tier is ambiguous.
- Access route cannot be documented.

Stop conditions:

- Product/feed mismatch.
- Entitlement insufficient for test scope.

Reviewer responsibilities:

- Confirm entitlement matches the run manifest.
- Flag product-tier mismatch before acquisition.

---

## 10. Dataset Preparation Workflow

Objective: prepare the standardized sample manifest without acquiring data.

Inputs:

- Approved sample-design rules.
- Instrument universe.
- Date universe.
- Session calendar.
- Special-event references.

Outputs:

- Instrument manifest.
- Date manifest.
- Session-boundary record.
- Special-event inclusion record.

Required evidence:

- Instrument inclusion rationale.
- Date inclusion rationale.
- Core Trading Session boundary.
- Timezone and daylight-saving rules.
- Halt/LULD, half-day, ordinary-day, and corporate-action-adjacent labels where applicable.

Failure conditions:

- Sample manifest cannot be reproduced.
- Instruments/dates differ across vendors without reason.
- Numeric sample size is introduced without proper 000C classification.

Stop conditions:

- 000C-dependent decision is required but unresolved.

Reviewer responsibilities:

- Confirm sample rules are vendor-neutral.
- Confirm no sample-selection bias is introduced.

---

## 11. Evidence Directory Initialization

Objective: create the evidence package skeleton.

Inputs:

- Run ID.
- Evidence Artifact Specification.

Outputs:

- Complete evidence directory tree.
- Initial audit-trail entry.

Required evidence:

- Created directory listing.
- Run ID creation timestamp.
- Package root path.

Failure conditions:

- Directory structure incomplete.
- Duplicate run ID.
- Operator lacks storage permission.

Stop conditions:

- Duplicate or nonconforming run ID.
- Storage location violates license or retention policy.

Reviewer responsibilities:

- Confirm directory structure matches the artifact specification.
- Confirm no existing run is overwritten.

---

## 12. Manifest Creation

Objective: create the master run index before acquisition.

Inputs:

- Candidate/product/feed identity.
- License and entitlement records.
- Dataset manifests.
- Environment manifests.
- Evidence directory path.

Outputs:

- Master run manifest.

Required evidence:

- Manifest JSON.
- Manifest hash after creation.
- Audit-trail entry.

Failure conditions:

- Manifest references missing records.
- Manifest uses unknown candidate/product/feed.
- Manifest timestamps are not UTC.

Stop conditions:

- Manifest cannot resolve required pre-run evidence.

Reviewer responsibilities:

- Review manifest completeness before acquisition.

---

## 13. Raw-Data Acquisition Procedure

Objective: acquire vendor-native raw data in a generic, vendor-neutral way during a future authorized run.

Inputs:

- Authorized license and entitlement.
- Master manifest.
- Sample manifests.
- Vendor delivery mechanism.

Outputs:

- Raw vendor files.
- Acquisition log.
- Extraction timestamp record.

Required evidence:

- Acquisition start/end UTC.
- Delivery mechanism.
- Raw filenames.
- File sizes.
- Record counts where safely computable.
- Any vendor-side extraction parameters.

Failure conditions:

- Access denied.
- Product/feed differs from manifest.
- Extraction parameters differ from sample manifest.
- License prohibits retaining acquired data.

Stop conditions:

- Unauthorized access required.
- Raw data cannot be preserved or lawfully inspected.
- Vendor data arrives in an unexpected product/feed/version.

Reviewer responsibilities:

- Confirm raw acquisition matches manifest.
- Confirm no substitution occurred silently.

---

## 14. Raw Evidence Checkpoint

Objective: verify raw evidence integrity before normalization.

Inputs:

- Raw files.
- Acquisition log.

Outputs:

- Raw checksum manifest.
- Raw inventory record.

Required evidence:

- SHA-256 or approved hash.
- Byte sizes.
- Raw file paths.
- Hash timestamp.

Failure conditions:

- Hash cannot be computed.
- Raw files changed after hash.
- Raw inventory and manifest disagree.

Stop conditions:

- Raw evidence integrity cannot be established.

Reviewer responsibilities:

- Confirm raw data is immutable before normalization begins.

---

## 15. Normalization Sequence

Objective: create a comparison copy without hiding vendor-native evidence.

Inputs:

- Raw files.
- Field-mapping procedure.
- Code dictionaries.
- Session calendar.

Outputs:

- Normalized data files.
- Transformation logs.
- Unmapped-field report.
- Unmapped-code report.

Required evidence:

- Input raw artifact references.
- Output normalized artifact references.
- Field transformations.
- Derived fields.
- Timezone conversions.
- Precision changes.

Failure conditions:

- Missing field is converted to zero.
- Derived field is unlabeled.
- Raw/adjusted distinction is lost.
- Transformation is undocumented.

Stop conditions:

- Normalization cannot preserve traceability to raw records.
- Required code dictionary unavailable for applicable criterion.

Reviewer responsibilities:

- Inspect transformation logs.
- Confirm raw records remain authoritative.

---

## 16. Normalized Evidence Checkpoint

Objective: verify normalized evidence before criterion execution.

Inputs:

- Normalized files.
- Transformation logs.
- Raw checksum manifest.

Outputs:

- Normalized checksum manifest.
- Normalization review checkpoint.

Required evidence:

- Normalized file hashes.
- Raw-to-normalized linkage sample.
- Unmapped fields/codes.

Failure conditions:

- Normalized records lack raw pointers.
- Transformation logs incomplete.
- Hash mismatch.

Stop conditions:

- Normalized evidence cannot be audited.

Reviewer responsibilities:

- Approve or block criterion execution.

---

## 17. Criterion Execution Order

Objective: execute future tests in a reproducible order.

Inputs:

- Normalized evidence.
- Raw evidence.
- Criterion procedures.
- Applicability matrix.

Outputs:

- Per-criterion result files.

Required execution order:

1. Manifest/provenance checks: P3.
2. Scope/applicability checks: C5, C6, C7, A7, CA1, CA2, CA4, CA6.
3. Field/code mapping checks: A4, A5.
4. Timestamp and session checks: T1, T2, T3, C2, A6.
5. Completeness checks: C1a, C1b-i, C1b-ii, C1b-iii, C4.
6. Record integrity checks: T4, T5, T6, P1, P2.
7. Accuracy checks: A1, A2, A3.
8. Calibration-pending metrics: C3.

Failure conditions:

- Prerequisite criterion blocked.
- Required evidence missing.
- Procedure version mismatch.

Stop conditions:

- P3 fails in a way that invalidates snapshot linkage.
- License issue discovered mid-run.
- Raw evidence integrity failure.

Reviewer responsibilities:

- Confirm blocked prerequisite logic is followed.
- Confirm no criterion is marked PASS from documentation alone.

---

## 18. Evidence Capture Checkpoints

Objective: make evidence capture observable during the run.

Mandatory checkpoints:

- Pre-run authorization checkpoint.
- Directory initialization checkpoint.
- Manifest checkpoint.
- Raw acquisition checkpoint.
- Raw checksum checkpoint.
- Normalization checkpoint.
- Per-criterion result checkpoint.
- Exception/conflict checkpoint.
- Reviewer sign-off checkpoint.
- Archive checkpoint.

Every checkpoint must write an audit-trail entry.

Failure conditions:

- Checkpoint omitted.
- Audit trail missing actor/timestamp/action.

Stop conditions:

- Missing checkpoint for a completed phase.

Reviewer responsibilities:

- Verify checkpoint sequence before final sign-off.

---

## 19. Exception Handling Workflow

Objective: handle anomalies without hiding them.

Inputs:

- Exception event.
- Affected artifact.
- Criterion ID if applicable.

Outputs:

- Exception log entry.
- Owner assignment.
- Disposition.

Required evidence:

- Event timestamp.
- Raw/normalized pointer.
- Exception class.
- Severity.
- Proposed disposition.

Failure conditions:

- Exception lacks artifact pointer.
- Exception is resolved without evidence.

Stop conditions:

- Blocking exception affects raw integrity, license, manifest, or snapshot linkage.

Reviewer responsibilities:

- Approve exception disposition.
- Require rerun if exception invalidates the run.

---

## 20. Conflict Logging Workflow

Objective: record credible evidence disagreements.

Inputs:

- Two or more conflicting evidence sources/artifacts.

Outputs:

- Conflict log entry.
- Blocking/non-blocking status.

Required evidence:

- Conflicting artifact references.
- Statement of disagreement.
- Affected criterion or result.
- Owner.
- Required resolution evidence.

Failure conditions:

- Absence of evidence is logged as conflict.
- Conflict lacks downstream impact.

Stop conditions:

- Conflict affects a blocking criterion or test authorization.

Reviewer responsibilities:

- Confirm conflict is genuine.
- Confirm confidence/result state reflects open conflict.

---

## 21. Reviewer Checkpoints

Objective: ensure independent review occurs before evidence is trusted.

Reviewer checkpoints:

- Pre-run authorization.
- License/entitlement verification.
- Manifest approval.
- Raw evidence integrity.
- Normalization approval.
- Criterion result review.
- Exception/conflict disposition.
- Final package verification.

Failure conditions:

- Reviewer is also sole operator without disclosure.
- Reviewer signs off without required artifacts.

Stop conditions:

- Reviewer rejects any blocking checkpoint.

Reviewer responsibilities:

- Record reviewed artifacts.
- Record open blockers.
- Refuse sign-off if evidence is incomplete.

---

## 22. Rerun Procedure

Objective: rerun a validation session without overwriting prior evidence.

Inputs:

- Parent run ID.
- Rerun reason.
- Approved rerun scope.

Outputs:

- New run ID.
- Rerun metadata.
- Delta report.

Required evidence:

- Parent manifest reference.
- Differences in sample, product, entitlement, environment, software, or procedure.
- Expected comparability impact.

Failure conditions:

- Parent run overwritten.
- Rerun differences undocumented.

Stop conditions:

- Rerun cannot preserve comparability and no governance waiver exists.

Reviewer responsibilities:

- Confirm rerun is traceable to parent.
- Confirm delta report is complete.

---

## 23. Post-Run Integrity Verification

Objective: verify the completed run is internally consistent.

Inputs:

- Full evidence package.

Outputs:

- Post-run integrity report.

Required evidence:

- Manifest resolution report.
- Hash verification report.
- Criterion result inventory.
- Open exception/conflict inventory.
- License/retention compliance check.

Failure conditions:

- Broken manifest links.
- Hash mismatch.
- Missing required result file.
- Unauthorized retained data.

Stop conditions:

- Any integrity failure not resolved by evidence.

Reviewer responsibilities:

- Approve integrity report or mark run invalidated.

---

## 24. Evidence Package Verification

Objective: verify package completeness against the Evidence Artifact Specification.

Inputs:

- Evidence package root.
- Artifact specification.

Outputs:

- Evidence package verification record.

Required evidence:

- Directory checklist.
- Mandatory file checklist.
- Artifact inventory matrix.
- Missing artifact dispositions.

Failure conditions:

- Required directory missing.
- Required artifact missing without blocked/not applicable disposition.
- Artifact naming violation.

Stop conditions:

- Package cannot support independent audit.

Reviewer responsibilities:

- Confirm every mandatory artifact is present or properly dispositioned.

---

## 25. Archival Procedure

Objective: close and archive a valid evidence package.

Inputs:

- Run valid state.
- Reviewer sign-off.
- License retention rules.

Outputs:

- Archive record.
- Final checksum manifest.
- Final audit-trail entry.

Required evidence:

- Archive path.
- Retention expiry if any.
- Access controls.
- Final package hash.

Failure conditions:

- Archive violates license.
- Archive path lacks access control.
- Final hash mismatch.

Stop conditions:

- Retention right unresolved.
- Reviewer sign-off missing.

Reviewer responsibilities:

- Confirm archive is compliant and complete.

---

## 26. Rollback / Invalidation Procedure

Objective: handle invalid runs without deleting evidence.

Inputs:

- Invalidation trigger.
- Affected run ID.

Outputs:

- Run invalidation record.
- Rollback/audit entry.
- Rerun recommendation if applicable.

Invalidation triggers:

- License violation or unresolved license right.
- Wrong product/feed.
- Raw evidence hash mismatch.
- Missing raw snapshot where required.
- Manifest corruption.
- Snapshot linkage failure.
- Unauthorized transformation.
- Reviewer rejection.

Required evidence:

- Reason for invalidation.
- Affected artifacts.
- Whether evidence must be deleted, retained, quarantined, or redacted under license.
- Rerun requirements.

Failure conditions:

- Evidence deleted without audit trail.
- Invalid run reused in comparison.

Stop conditions:

- Any invalidation trigger.

Reviewer responsibilities:

- Confirm invalid run is excluded from Decision Freeze evidence.
- Confirm rollback does not erase audit history.

---

## 27. Final Run Completion Criteria

A run may be marked `RUN_VALID` only if:

- License and entitlement evidence passed.
- Manifest resolves.
- Raw evidence integrity is established or lawfully blocked with accepted disposition.
- Normalization is traceable.
- Criterion result files exist or are properly blocked/not applicable.
- Exceptions and conflicts are dispositioned.
- Reviewer sign-off is complete.
- Archive requirements are satisfied.

---

## 28. Quality Rubric

| Category | Max | Score | Evidence |
|---|---:|---:|---|
| Scope discipline | 10 | 10 | No testing, code, ranking, recommendation, selection, rejection, or prior-document edits |
| Operational completeness | 10 | 10 | Covers pre-run through archive and invalidation |
| Step consistency | 10 | 10 | Every step includes objective, inputs, outputs, evidence, failure/stop conditions, and reviewer duties |
| Evidence integration | 10 | 10 | Aligns with evidence package, manifest, checksum, logs, and sign-off expectations |
| License safety | 10 | 10 | License and entitlement gates appear before acquisition |
| Reproducibility | 10 | 9 | Rerun procedure is defined; future dry run may refine delta categories |
| Reviewer governance | 10 | 10 | Reviewer checkpoints are explicit |
| Exception/conflict handling | 10 | 10 | Workflows separate anomaly, conflict, block, and invalidation |
| Archival/rollback clarity | 10 | 9 | Clear governance process; future storage implementation may add details |
| Independent executability | 10 | 9 | Procedurally executable; exact tool commands intentionally omitted |

**Total: 97/100.** Full marks are not assigned because a future dry run may refine rerun delta categories, storage details, and tool-specific execution notes.

---

## 29. Final Status

**DRAFT / RUNBOOK UNDER REVIEW.**

This runbook defines execution procedure only. It performs no empirical validation, downloads no vendor data, calls no vendor API, writes no implementation code, selects no vendor, rejects no vendor, recommends no vendor, ranks no vendor, and attempts no Decision Freeze.

---

*End of MILESTONE-000B.4 Phase 2 Empirical Test Execution Runbook, Version 1.0.*
