# MILESTONE-021 - Aggregate Persistence Mapper Contract Implementation Scope Selection

## 1. Document Control

| Field | Value |
| --- | --- |
| Document ID | MILESTONE-021-IMPL-SCOPE |
| Title | Aggregate Persistence Mapper Contract Implementation Scope Selection |
| Version | 1.0 |
| Status | IMPLEMENTATION SCOPE SELECTED |
| Repository | `C:\Users\LuxSy\Documents\trading` |
| Frozen baseline | `abeba5a1407a8d31ce6d07fe3e071804d2385457` |
| Baseline status | MILESTONE-021 DESIGN APPROVED AND FROZEN |
| Mission type | Implementation scope confirmation only |

## 2. Purpose

MILESTONE-021's Design (Version 1.0, frozen) already fully specifies what an implementation must build (Sections 7-16). This document does not re-derive scope; it confirms the frozen design is implementable as written and records the one design-deferred decision (mapper-local error shape) resolved immediately before implementation, per the Design Freeze record's accepted observations.

## 3. Confirmed Implementable Without Design Contradiction

Verified against live repository evidence before writing any code:

- all four `*ReconstructionState` types (`CampaignReconstructionState`, `RunReconstructionState`, `EvidencePackageReconstructionState`, `ReviewReconstructionState`) read in full, field-by-field, from `src/empirical_platform/{campaign,run,evidence,review}/_reconstruction.py`;
- all nested owned value objects (`DatasetManifest`, `CriterionResult`, `ArtifactReference`, `ReviewFinding`, `ReviewTargetReference`, `ReviewerReference`) read in full;
- `StateTransitionRecord[IdentityReferenceT]` and `AggregateVersion`/`TransitionSequence` read and confirmed unchanged;
- no field, collection, or optional value in any of the four `*ReconstructionState` types requires a durable-record concept the frozen Design (Section 10) did not anticipate.

No contradiction between the frozen Design and live M019/M020 code was found. Implementation proceeds without a stop-condition trigger (Design Section 16 was not invoked).

## 4. Scope Confirmed

Exactly the frozen Design's Sections 7-16:

- `CampaignMapper`, `RunMapper`, `EvidencePackageMapper`, `ReviewMapper` Protocols;
- `CampaignDurableRecord`, `RunDurableRecord` (+ `DatasetManifestDurableRecord`), `EvidencePackageDurableRecord` (+ `CriterionResultDurableRecord`), `ReviewDurableRecord` (+ `ReviewFindingDurableRecord`);
- shared `IdentityDurableRecord` and `TransitionDurableRecord` (justified in the Implementation Report as reuse of an already-shared generic shape, not a new generic mapper abstraction);
- the mapper-local error type deferred by the Design (Section 4 below).

## 5. Mapper-Local Error Shape (resolved now, per Design Freeze accepted observation)

Selected: `MapperErrorCategory` (closed `StrEnum`: `INVALID_DURABLE_RECORD`, `INVALID_AGGREGATE_FOR_MAPPING`) and `MapperError` (plain `Exception` subclass carrying `category`, `safe_message`, `aggregate_kind`, `field`), placed in `empirical_platform.shared.contracts.mapping`. Mirrors `ReconstructionError`/`ReconstructionErrorCategory`'s exact shape (M019 precedent) rather than `RepositoryContractError`'s shape, preserving the Design's explicit requirement that the mapper not depend on repository-contract vocabulary (Design Section 13).

## 6. Non-Goals (unchanged from Design)

Repository implementation, PostgreSQL schema/migrations, SQL, Unit of Work beyond the existing primitive, application services, APIs, workers, and any MILESTONE-022 work remain out of scope, exactly as the frozen Design Section 22 states.

## 7. Final Status

```text
IMPLEMENTATION SCOPE SELECTED — PROCEEDING TO IMPLEMENTATION
```
