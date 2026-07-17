# Governance Baseline Registration

## Purpose

This directory contains repository-registered copies of external governance and architecture artifacts used to reconcile MILESTONE-012 traceability.

Registration means the artifact has been copied into the repository with a recorded source path and SHA-256 checksum. Registration does not establish document authority, approval, freeze, or final governance authority.

## Scope

The current registration scope is limited to artifacts needed for MILESTONE-012 external artifact registration and baseline reconciliation:

- prior architecture artifacts;
- empirical validation governance artifacts;
- master governance standards;
- baseline registration evidence;
- CAMP-0001 draft/review artifacts.

No implementation, schema, API, repository, worker, job ledger, outbox, campaign execution, Decision Candidate, or Decision Freeze artifact is stored here.

## Directory Structure

| Directory | Purpose |
| --- | --- |
| `architecture/` | Prior architecture and engineering-design documents |
| `empirical/` | Empirical validation framework, protocol, evidence, and runbook documents |
| `governance/` | Master governance standards |
| `governance/baseline_registration/` | Operational baseline-registration evidence |
| `campaign/` | CAMP-0001 proposal and authorization-review artifacts |
| `manifest/` | Canonical baseline manifests |

## Authority Rules

Artifacts retain their stated status after registration. A draft artifact remains draft. An operational report with unresolved gaps remains unresolved. A registered copy may be cited as evidence of the exact content reviewed, but it may not be silently promoted into an approved or frozen baseline.

Authority classifications are recorded in `manifest/MILESTONE_012_EXTERNAL_BASELINE_MANIFEST.md`.

## Immutability Expectations

Registered artifact copies are treated as immutable evidence for the registration event. Do not edit registered copies in place. If a source artifact changes, register the new version as a new artifact record with a new checksum and supersession note.

## Version Registration

New versions require:

- original external path;
- repository path;
- original filename;
- SHA-256 checksum;
- version or revision;
- stated status;
- authority classification;
- supersession relationship;
- registration date.

## Superseded Artifacts

Superseded artifacts remain retained unless a governance retention rule explicitly permits removal. Supersession must be recorded in the manifest before a newer artifact is treated as the current candidate.

## Checksum Requirements

Every registered artifact must have a SHA-256 checksum. The copied file hash must match the source file hash at registration time.

## Prohibited Changes

Do not silently edit registered baseline artifacts. Do not normalize line endings, rewrite headings, revise statuses, or correct content in copied artifacts. Corrections belong in a new source artifact or a reconciliation report.

## Relationship to MILESTONE-012

This directory resolves the previous MILESTONE-012 problem that external artifacts existed only outside the repository. It does not resolve approval or freeze readiness because most registered artifacts remain draft or unresolved-authority evidence.

## Registration Versus Approval

Repository registration proves artifact identity and traceability. Approval/freeze requires a separate governance decision that verifies authority, status, dependencies, and readiness.
