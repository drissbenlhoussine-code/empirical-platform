# MILESTONE 000B.4 - PHASE 2 EVIDENCE ARTIFACT SPECIFICATION

---

## 1. Document Control

| Field | Value |
|---|---|
| Document ID | MILESTONE-000B.4-P2-EAS |
| Title | MILESTONE 000B.4 - PHASE 2 Evidence Artifact Specification |
| Version | 1.0 |
| Status | DRAFT / ARTIFACT SPECIFICATION UNDER REVIEW |
| Document Owner | Research Lead |
| Primary Approver | Project Owner |
| Original Publication Date | 2026-07-12 |
| Current Revision Date | 2026-07-12 |
| Approval Date | Not applicable - this document is not approved or frozen |
| Scope | Mandatory evidence artifacts for future empirical validation runs |

This document defines mandatory outputs of future empirical validation. It performs no testing, modifies no prior milestone, creates no vendor ranking, and implements no code.

---

## 2. Purpose

The purpose of this specification is to ensure every future empirical validation run produces evidence that is independently auditable, reproducible, license-safe, and traceable from raw vendor data through normalized data, transformations, per-criterion results, reviewer sign-off, and rerun metadata.

---

## 3. Scope and Non-Goals

In scope:

- Directory structure.
- Mandatory files.
- Manifest format.
- Metadata requirements.
- Raw-data preservation rules.
- Normalized-data rules.
- Checksum/hash requirements.
- Evidence naming conventions.
- Environment and software-version capture.
- License and entitlement evidence.
- Transformation, exception, and conflict logs.
- Per-criterion result files.
- Reviewer sign-off records.
- Rerun metadata.
- Audit trail and reproducibility obligations.

Out of scope:

- Vendor testing.
- Vendor API calls.
- Data downloads.
- Vendor ranking, recommendation, selection, or rejection.
- Implementation code.
- Production architecture.
- Decision Freeze.

---

## 4. Evidence Package Root

Every empirical validation run must produce a single evidence package root directory:

```text
evidence/
  milestone_000b4_p2/
    category_1_l1_market_data/
      run_<RUN_ID>/
```

`RUN_ID` must be stable and unique:

```text
YYYYMMDDTHHMMSSZ_<candidate_slug>_<product_slug>_<feed_slug>_<run_sequence>
```

Example format only:

```text
20260712T120000Z_vendor_product_feed_001
```

No vendor data is created by this specification.

---

## 5. Required Directory Structure

Each run directory must contain:

```text
run_<RUN_ID>/
  00_manifest/
  01_license_entitlement/
  02_source_references/
  03_raw/
  04_checksums/
  05_normalized/
  06_transform_logs/
  07_criterion_results/
  08_exceptions_conflicts/
  09_environment/
  10_reviewer_signoff/
  11_rerun/
  12_audit_trail/
```

No directory may be omitted. If no artifact exists for a directory, include a `README.md` explaining why and whether the absence is expected, blocked, not applicable, or a failure.

---

## 6. Evidence Naming Conventions

All artifact filenames must use:

```text
<RUN_ID>__<artifact_type>__<scope>__v<artifact_version>.<extension>
```

Allowed characters:

- lowercase letters.
- digits.
- underscore.
- hyphen.
- period before extension only.

Required conventions:

- Raw data files must include `raw`.
- Normalized data files must include `normalized`.
- Criterion result files must include the canonical criterion ID.
- Logs must include UTC creation timestamp in file metadata and manifest.
- File replacement is prohibited; create a new artifact version instead.

---

## 7. Master Run Manifest

Artifact:

```text
00_manifest/<RUN_ID>__manifest__run__v1.json
```

Purpose: single authoritative index for the run.

Producer: test runner / research operator.

Required contents:

- `run_id`
- `document_versions`
- `candidate`
- `provider_legal_entity`
- `product`
- `feed`
- `delivery_mechanism`
- `entitlement_id_or_description`
- `license_reference`
- `instrument_manifest_reference`
- `date_manifest_reference`
- `session_boundary`
- `timezone_rules`
- `extraction_start_utc`
- `extraction_end_utc`
- `raw_artifacts`
- `normalized_artifacts`
- `criterion_result_artifacts`
- `checksum_manifest`
- `environment_manifest`
- `reviewer_signoff`
- `known_blockers`
- `rerun_parent_run_id`

Validation rules:

- Must be valid JSON.
- Must reference every artifact in the package.
- Every referenced artifact must exist or be explicitly marked blocked/not applicable.
- Timestamps must be UTC ISO-8601.

Downstream consumers:

- Independent reviewer.
- Decision governance reviewer.
- Future rerun operator.

Retention:

- Retain for the full evidence-retention period allowed by license.

Immutability:

- Immutable after reviewer sign-off. Corrections require a new manifest version plus audit-trail entry.

---

## 8. License and Entitlement Evidence

Directory:

```text
01_license_entitlement/
```

Mandatory artifacts:

- license evidence record.
- entitlement evidence record.
- retention-rights record.
- redistribution/non-display/personal-use rights record.
- decision-time freshness verification record.

Purpose: prove the test was authorized and evidence retention is permitted.

Producer: research operator with project owner or legal/compliance reviewer as applicable.

Required contents:

- vendor/provider name.
- product/feed.
- account or entitlement scope.
- professional/non-professional status if relevant.
- storage permission.
- reviewer-access permission.
- retention limit.
- publication restriction.
- derived-data/non-display restriction.
- contract/order/support reference.
- verification timestamp.
- verifier identity.

Validation rules:

- Marketing language alone is insufficient.
- If a right is unknown, mark `BLOCKED_BY_LICENSE`.
- If retention is restricted, raw and derived artifacts must obey retention.

Downstream consumers:

- Test authorization gate.
- Reviewer.
- Decision Freeze gate.

Retention:

- Retain according to license and project governance; if retention is prohibited, record prohibition and store no prohibited data.

Immutability:

- Immutable once used to authorize a test.

---

## 9. Source Reference Records

Directory:

```text
02_source_references/
```

Purpose: preserve source references used during the run without bundling multiple publishers into one evidence reference.

Producer: research operator.

Required contents:

- source ID or local run source reference.
- publisher.
- title.
- URL or contract/support reference.
- access timestamp.
- claim supported.
- limitation.
- archived copy status if permitted.

Validation rules:

- One publisher per source record.
- If source capture is license-restricted, store metadata and restriction notice only.

Downstream consumers:

- Reviewer.
- Traceability matrix.

Retention:

- Retain source metadata even if source content cannot be retained.

Immutability:

- Immutable after run close.

---

## 10. Raw Data Preservation

Directory:

```text
03_raw/
```

Purpose: preserve vendor-native source records exactly as received.

Producer: extraction operator or vendor export process.

Required contents:

- raw files exactly as delivered.
- original filenames if supplied.
- delivery channel metadata.
- extraction timestamps.
- compression/encryption metadata.
- file format.
- record count where computable without changing file.

Validation rules:

- Raw data must not be edited.
- No field may be dropped.
- No timezone conversion may be applied.
- No adjusted/raw conversion may be applied.
- If license prohibits raw retention, store only permitted metadata and mark the run blocked for raw-preservation review.

Downstream consumers:

- Normalization process.
- Criterion tests.
- Reviewer.

Retention:

- Retain only as license permits.

Immutability:

- Immutable. Any change invalidates the raw artifact and requires a new extraction.

---

## 11. Checksum and Hash Manifest

Directory:

```text
04_checksums/
```

Artifact:

```text
<RUN_ID>__checksum_manifest__all_artifacts__v1.json
```

Purpose: prove artifact integrity.

Producer: evidence packaging process.

Required contents:

- artifact path.
- hash algorithm.
- hash value.
- byte size.
- creation timestamp.
- hash timestamp.

Validation rules:

- Hash every retained artifact.
- Use a collision-resistant hash such as SHA-256 unless project governance later specifies otherwise.
- Hash manifest itself must be hashed and recorded in audit trail.

Downstream consumers:

- Reviewer.
- Rerun comparator.
- Audit trail.

Retention:

- Retain for full evidence package lifetime.

Immutability:

- Immutable after run close.

---

## 12. Normalized Data Artifacts

Directory:

```text
05_normalized/
```

Purpose: store comparison-ready records without hiding vendor-native evidence.

Producer: normalization operator or test adapter.

Required contents:

- normalized records.
- schema version.
- canonical field names.
- source raw-file reference.
- raw record pointer.
- derived-field indicators.
- unmapped fields.
- unmapped codes.
- null/absent indicators.

Validation rules:

- Absence must not become zero.
- Missing fields must not be synthesized unless labeled derived.
- Every normalized record must trace to raw evidence or be explicitly project-derived.
- Adjusted data must not be labeled raw.

Downstream consumers:

- Criterion tests.
- Cross-vendor comparison.

Retention:

- Same or stricter than raw data.

Immutability:

- Immutable per artifact version; corrections require new normalized version.

---

## 13. Transformation Logs

Directory:

```text
06_transform_logs/
```

Purpose: explain every transformation from raw to normalized evidence.

Producer: normalization operator.

Required contents:

- input artifact path and hash.
- output artifact path and hash.
- transformation name.
- transformation version.
- field mapping.
- code mapping.
- timezone conversion.
- precision/rounding changes.
- derived fields.
- dropped fields, if any, with justification.
- errors and warnings.

Validation rules:

- No transformation may be undocumented.
- Dropped fields require reviewer-visible justification.
- Code mappings must reference a dictionary artifact.

Downstream consumers:

- Reviewer.
- Criterion tests.
- Rerun operator.

Retention:

- Retain with normalized artifacts.

Immutability:

- Immutable per normalized version.

---

## 14. Criterion Result Files

Directory:

```text
07_criterion_results/
```

One result file per tested canonical criterion:

```text
<RUN_ID>__criterion_<CRITERION_ID>__result__v1.json
```

Purpose: capture deterministic result evidence per B3 criterion.

Producer: criterion test operator.

Required contents:

- criterion ID.
- criterion version/baseline reference.
- applicability state.
- result state.
- inputs.
- procedure version.
- raw artifact references.
- normalized artifact references.
- result summary.
- exception references.
- evidence artifact references.
- reviewer notes.

Validation rules:

- Documentation-only support cannot produce `PASS`.
- `FAIL`, `NOT TESTABLE`, `CALIBRATION-PENDING`, and `BLOCKED BY DATA ACCESS` must cite cause.
- Every result must cite raw and/or normalized evidence unless not applicable or blocked.

Downstream consumers:

- B3 empirical result matrix.
- Decision governance.
- Reviewer.

Retention:

- Retain for full evidence package lifetime.

Immutability:

- Immutable after reviewer sign-off; corrections require new version.

---

## 15. Exception and Conflict Logs

Directory:

```text
08_exceptions_conflicts/
```

Mandatory artifacts:

- exception log.
- conflict log.
- blocked-item log.

Purpose: preserve anomalies, disagreements, and blocked evidence.

Producer: test operator and reviewer.

Required contents:

- event ID.
- timestamp.
- criterion ID if applicable.
- artifact reference.
- raw record pointer.
- exception/conflict type.
- severity.
- disposition.
- owner.
- closure evidence.

Validation rules:

- Conflict requires credible evidence disagreement, not mere absence.
- Blocked item must name the missing access, license, data, or documentation.

Downstream consumers:

- Reviewer.
- Risk register.
- Deferred-item tracker.

Retention:

- Retain with run evidence.

Immutability:

- Append-only.

---

## 16. Environment Capture

Directory:

```text
09_environment/
```

Purpose: enable reproducibility of extraction, normalization, and tests.

Producer: test operator.

Required contents:

- operating system.
- runtime versions.
- package/library versions.
- command invocations or workflow references.
- timezone settings.
- locale settings.
- hardware/cloud environment if relevant.
- environment variables relevant to reproducibility, excluding secrets.
- container/image digest if used.

Validation rules:

- Secrets must not be stored.
- Versions must be exact where possible.
- If exact capture is impossible, record limitation.

Downstream consumers:

- Rerun operator.
- Reviewer.

Retention:

- Retain with evidence package.

Immutability:

- Immutable after run close.

---

## 17. Software-Version Capture

Software artifacts used for extraction, normalization, or testing must be recorded separately from environment:

- repository URL or local path.
- commit hash or release version.
- dirty-worktree status.
- script/tool name.
- configuration file hashes.
- test adapter version.
- criterion procedure version.

If no software is used for a step, state `manual_step` and record reviewer-verifiable procedure notes.

---

## 18. Reviewer Sign-Off Records

Directory:

```text
10_reviewer_signoff/
```

Purpose: record review state without modifying evidence.

Producer: independent reviewer or assigned reviewer role.

Required contents:

- reviewer name/role.
- review timestamp.
- artifacts reviewed.
- criteria reviewed.
- open exceptions.
- pass/fail/block disposition.
- conflict disposition.
- sign-off statement.

Validation rules:

- Sign-off cannot occur if mandatory artifacts are missing without explicit blocked disposition.
- Reviewer cannot silently edit artifacts under review.

Downstream consumers:

- Protocol freeze gate.
- Decision Freeze gate.

Retention:

- Retain for full evidence package lifetime.

Immutability:

- Append-only; revisions require new sign-off version.

---

## 19. Rerun Metadata

Directory:

```text
11_rerun/
```

Purpose: make future reruns comparable.

Producer: run operator.

Required contents:

- parent run ID if rerun.
- rerun reason.
- same/different instrument manifest.
- same/different date manifest.
- same/different vendor product/feed.
- same/different entitlement.
- changed software/environment.
- expected comparability impact.

Validation rules:

- Rerun must not overwrite parent run.
- Any difference must be classified.

Downstream consumers:

- Rerun operator.
- Reviewer.
- Decision governance.

Retention:

- Retain with run evidence.

Immutability:

- Immutable after rerun close.

---

## 20. Audit Trail Requirements

Directory:

```text
12_audit_trail/
```

Purpose: preserve chain of custody.

Producer: evidence packaging process and reviewer.

Required contents:

- artifact creation events.
- artifact hash events.
- artifact validation events.
- manual review events.
- exception closure events.
- sign-off events.
- package close event.

Validation rules:

- Append-only.
- Every event must include timestamp, actor, action, target artifact, and result.
- No event may delete history.

Downstream consumers:

- Independent auditor.
- Decision governance.

Retention:

- Retain for full evidence package lifetime.

Immutability:

- Append-only and hash-anchored.

---

## 21. Artifact Inventory Matrix

| Artifact | Purpose | Producer | Required contents | Validation rules | Downstream consumers | Retention | Immutability |
|---|---|---|---|---|---|---|---|
| Master manifest | Run index | Test operator | Run metadata and artifact links | Valid JSON; references resolve | Reviewer, rerun operator | Full package lifetime | Immutable after sign-off |
| License evidence | Prove authorization | Operator / owner | Rights, limits, verifier | Unknown rights block test | Test gate, reviewer | Per license | Immutable |
| Entitlement evidence | Prove product access | Operator | Account/product/feed scope | Must match tested product | Reviewer | Per license | Immutable |
| Source records | Preserve source basis | Operator | Publisher, title, URL/ref, claim | One publisher per record | Reviewer | Metadata retained | Immutable |
| Raw snapshot | Preserve vendor-native data | Vendor/export operator | Raw files and metadata | No modification | Tests, reviewer | Per license | Immutable |
| Checksum manifest | Prove integrity | Packaging process | Hashes and sizes | Every artifact hashed | Auditor | Full package lifetime | Immutable |
| Normalized snapshot | Comparison copy | Adapter/operator | Canonical fields and raw pointers | Absence not zero; derived labeled | Criterion tests | Per license | Version immutable |
| Transformation log | Explain normalization | Adapter/operator | Mapping, conversions, warnings | No undocumented transform | Reviewer | With normalized data | Immutable |
| Criterion result | Per-B3 evidence | Test operator | Result state and evidence refs | Docs cannot PASS | Decision governance | Full package lifetime | Immutable after sign-off |
| Exception log | Preserve anomalies | Operator/reviewer | Events, severity, disposition | Closure required or blocked | Risk/deferred review | Full package lifetime | Append-only |
| Conflict log | Preserve disagreements | Operator/reviewer | Evidence disagreement | Absence alone not conflict | Governance | Full package lifetime | Append-only |
| Environment manifest | Reproduce run | Operator | OS/runtime/package versions | Exact versions where possible | Rerun operator | Full package lifetime | Immutable |
| Software manifest | Reproduce tools | Operator | Commit/version/config hashes | Dirty state disclosed | Rerun operator | Full package lifetime | Immutable |
| Reviewer sign-off | Review disposition | Reviewer | Reviewed artifacts and status | Cannot hide missing artifacts | Freeze gate | Full package lifetime | Append-only |
| Rerun metadata | Compare reruns | Operator | Parent run and deltas | Parent not overwritten | Reviewer | Full package lifetime | Immutable |
| Audit trail | Chain of custody | Packaging/reviewer | Events and actors | Append-only | Auditor | Full package lifetime | Append-only |

---

## 22. Manifest JSON Schema (Governance-Level)

The master manifest must conform to this governance-level shape:

```json
{
  "run_id": "string",
  "schema_version": "string",
  "created_utc": "string",
  "candidate": {
    "provider": "string",
    "legal_entity": "string",
    "product": "string",
    "feed": "string",
    "delivery_mechanism": "string",
    "product_version": "string"
  },
  "entitlement": {
    "entitlement_reference": "string",
    "license_reference": "string",
    "retention_limit": "string",
    "redistribution_allowed": "boolean_or_unknown",
    "reviewer_access_allowed": "boolean_or_unknown"
  },
  "sample": {
    "instrument_manifest": "path",
    "date_manifest": "path",
    "session_boundary": "string",
    "timezone": "string"
  },
  "artifacts": [
    {
      "path": "string",
      "artifact_type": "string",
      "hash": "string",
      "hash_algorithm": "string",
      "immutable": true
    }
  ],
  "open_blockers": [],
  "review": {
    "reviewer": "string",
    "status": "string",
    "signoff_artifact": "path"
  }
}
```

This is not implementation code. It is the required governance shape for future implementation.

---

## 23. Validation Rules

Before a run can be considered evidence-complete:

- Every mandatory directory exists.
- Every mandatory artifact exists or is explicitly blocked/not applicable.
- Master manifest references resolve.
- All retained artifacts are hashed.
- Raw artifacts are immutable.
- Normalized artifacts trace to raw artifacts.
- Transformation logs cover every normalized output.
- Every criterion result has an allowed state.
- Exceptions are open with owner or closed with evidence.
- License/entitlement evidence permits storage and review.
- Reviewer sign-off exists or states why sign-off is blocked.

---

## 24. Retention and Immutability Policy

Retention is governed by the strictest of:

- vendor license.
- entitlement terms.
- project governance.
- reviewer evidence requirement.

If license terms conflict with evidence-retention requirements, the run must be marked blocked for Decision Freeze use unless governance accepts an alternative audit method.

Immutability rules:

- Raw data is never edited.
- Closed manifests are never edited.
- Result files are versioned, not overwritten.
- Audit trail is append-only.
- Hash mismatches invalidate affected artifacts until explained.

---

## 25. Reproducibility Obligations

A future empirical validation run is reproducible only if an independent reviewer can:

- identify the exact product/feed tested.
- verify testing rights.
- locate the raw snapshot or lawful equivalent.
- verify hashes.
- reconstruct normalization.
- rerun or inspect per-criterion logic.
- compare rerun metadata.
- determine why any criterion was blocked, not applicable, not testable, pass, fail, or calibration-pending.

---

## 26. Final Verification Checklist

| Check | Status |
|---|---|
| No vendor testing performed | Met |
| No previous milestone document modified | Met |
| No vendor ranking, selection, rejection, or recommendation | Met |
| No implementation code created | Met |
| Mandatory artifact classes defined | Met |
| Purpose/producer/contents/validation/consumer/retention/immutability defined | Met |
| Directory structure defined | Met |
| Manifest format defined | Met |
| Raw and normalized rules defined | Met |
| License and entitlement evidence required | Met |
| Audit and reproducibility obligations defined | Met |

---

## 27. Quality Rubric

| Category | Max | Score | Evidence |
|---|---:|---:|---|
| Scope discipline | 10 | 10 | No testing, ranking, implementation, or prior-document edits |
| Artifact completeness | 10 | 10 | All requested artifact categories covered |
| Auditability | 10 | 10 | Chain of custody, hashes, sign-off, and exception logs defined |
| Reproducibility | 10 | 9 | Rerun requirements defined; future implementation may reveal additional environment capture needs |
| Licensing safety | 10 | 10 | Rights and retention evidence are mandatory gates |
| Raw preservation | 10 | 10 | Raw data immutability rules are explicit |
| Normalization transparency | 10 | 10 | Transformation and derived-field rules defined |
| Manifest rigor | 10 | 9 | Governance-level schema defined; exact machine schema remains future implementation work |
| Retention/immutability | 10 | 10 | Strict retention and versioning rules defined |
| Decision usefulness | 10 | 9 | Strong evidence package design; must be validated in a dry run before freeze |

**Total: 97/100.** Full marks are not assigned because the exact machine-enforced schema and environment-capture implementation must still be validated during a future dry run.

---

## 28. Final Status

**DRAFT / ARTIFACT SPECIFICATION UNDER REVIEW.**

This document defines mandatory evidence artifacts for future empirical validation. It does not perform testing, modify prior milestones, rank vendors, recommend vendors, select vendors, reject vendors, create implementation code, or attempt a Decision Freeze.

---

*End of MILESTONE-000B.4 Phase 2 Evidence Artifact Specification, Version 1.0.*
