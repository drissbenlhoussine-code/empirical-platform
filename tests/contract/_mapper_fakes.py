"""Concrete, in-memory mapper test doubles for MILESTONE-021 contract tests.

These fakes are test-only scaffolding proving the frozen mapper contracts
(Protocol shape, durable-record fields, round-trip fidelity, error behavior)
are satisfiable, without implementing a database adapter, per the frozen
design's "do not implement a database adapter to test the abstract contract"
instruction. They are not exported from `empirical_platform` and are not the
mapper *implementation* MILESTONE-021's design explicitly defers.
"""

from __future__ import annotations

from typing import Any

from empirical_platform.campaign._reconstruction import CampaignReconstructionState
from empirical_platform.campaign.aggregate import Campaign, CampaignScopeStatement
from empirical_platform.campaign.lifecycle import CampaignLifecycleState, RunLifecycleState
from empirical_platform.campaign.mapper import CampaignDurableRecord
from empirical_platform.datasets import DatasetManifest
from empirical_platform.evidence._reconstruction import EvidencePackageReconstructionState
from empirical_platform.evidence.lifecycle import EvidencePackageLifecycleState
from empirical_platform.evidence.mapper import (
    CriterionResultDurableRecord,
    EvidencePackageDurableRecord,
)
from empirical_platform.evidence.package import ArtifactReference, EvidencePackage
from empirical_platform.evidence.results import CriterionResult
from empirical_platform.identifiers.pairs import DomainIdentity
from empirical_platform.identifiers.types import (
    CampaignId,
    DatasetId,
    EvidencePackageId,
    Identifier,
    ReviewId,
    RunId,
)
from empirical_platform.review._reconstruction import ReviewReconstructionState
from empirical_platform.review.aggregate import (
    Review,
    ReviewerReference,
    ReviewFinding,
    ReviewTargetReference,
)
from empirical_platform.review.lifecycle import ReviewDisposition, ReviewLifecycleState
from empirical_platform.review.mapper import ReviewDurableRecord, ReviewFindingDurableRecord
from empirical_platform.run._reconstruction import RunReconstructionState
from empirical_platform.run.aggregate import Run
from empirical_platform.run.mapper import DatasetManifestDurableRecord, RunDurableRecord
from empirical_platform.shared.contracts.mapping import (
    IdentityDurableRecord,
    MapperError,
    MapperErrorCategory,
    TransitionDurableRecord,
)
from empirical_platform.shared.domain.transitions import StateTransitionRecord
from empirical_platform.shared.domain.versioning import AggregateVersion, TransitionSequence
from empirical_platform.shared.identifiers import RuntimeIdentifier

# --- Shared, generic-shape-but-not-generic-mapper conversion helpers -----------
# (test-only; identity and transition-history shape is identical across every
# aggregate, mirroring StateTransitionRecord's own existing genericity)


def _identity_to_durable(identity: DomainIdentity[Any]) -> IdentityDurableRecord:
    return IdentityDurableRecord(
        governance_id=str(identity.governance_id),
        runtime_id=str(identity.runtime_id),
    )


def _identity_from_durable(
    record: IdentityDurableRecord, governance_cls: type[Identifier]
) -> DomainIdentity[Any]:
    return DomainIdentity(
        governance_id=governance_cls(record.governance_id),
        runtime_id=RuntimeIdentifier(record.runtime_id),
    )


def _transition_to_durable(record: StateTransitionRecord[Any]) -> TransitionDurableRecord:
    identity_reference = (
        _identity_to_durable(record.identity_reference)
        if record.identity_reference is not None
        else None
    )
    return TransitionDurableRecord(
        from_state=record.from_state,
        to_state=record.to_state,
        version=record.version.value,
        sequence=record.sequence.value,
        actor=record.actor,
        occurred_at=record.occurred_at,
        identity_reference=identity_reference,
        correlation_id=record.correlation_id,
        reason=record.reason,
    )


def _transition_from_durable(
    record: TransitionDurableRecord, governance_cls: type[Identifier]
) -> StateTransitionRecord[Any]:
    identity_reference = (
        _identity_from_durable(record.identity_reference, governance_cls)
        if record.identity_reference is not None
        else None
    )
    return StateTransitionRecord(
        from_state=record.from_state,
        to_state=record.to_state,
        version=AggregateVersion(record.version),
        sequence=TransitionSequence(record.sequence),
        actor=record.actor,
        occurred_at=record.occurred_at,
        identity_reference=identity_reference,
        correlation_id=record.correlation_id,
        reason=record.reason,
    )


# --- Campaign -------------------------------------------------------------


class FakeCampaignMapper:
    """In-memory `CampaignMapper` test double."""

    def to_durable_record(self, aggregate: Campaign) -> CampaignDurableRecord:
        return CampaignDurableRecord(
            identity=_identity_to_durable(aggregate.identity),
            scope_statement=str(aggregate.scope_statement),
            lifecycle_state=aggregate.state.value,
            version=aggregate.version.value,
            next_transition_sequence=aggregate.next_transition_sequence.value,
            transition_history=tuple(
                _transition_to_durable(record) for record in aggregate.transition_history
            ),
        )

    def from_durable_record(self, record: CampaignDurableRecord) -> CampaignReconstructionState:
        try:
            lifecycle_state = CampaignLifecycleState(record.lifecycle_state)
        except ValueError as exc:
            raise MapperError(
                MapperErrorCategory.INVALID_DURABLE_RECORD,
                "unknown Campaign lifecycle_state",
                aggregate_kind="Campaign",
                field="lifecycle_state",
            ) from exc
        return CampaignReconstructionState(
            identity=_identity_from_durable(record.identity, CampaignId),
            scope_statement=CampaignScopeStatement(record.scope_statement),
            state=lifecycle_state,
            version=AggregateVersion(record.version),
            next_transition_sequence=TransitionSequence(record.next_transition_sequence),
            transition_history=tuple(
                _transition_from_durable(item, CampaignId) for item in record.transition_history
            ),
        )


# --- Run --------------------------------------------------------------------


def _manifest_to_durable(manifest: DatasetManifest) -> DatasetManifestDurableRecord:
    return DatasetManifestDurableRecord(
        run_id=str(manifest.run_id),
        recorded_at=manifest.recorded_at,
        source=manifest.source,
        acquisition_method=manifest.acquisition_method,
        normalization_method=manifest.normalization_method,
        manifest_id=str(manifest.manifest_id) if manifest.manifest_id is not None else None,
        notes=manifest.notes,
    )


def _manifest_from_durable(record: DatasetManifestDurableRecord) -> DatasetManifest:
    return DatasetManifest(
        run_id=RunId(record.run_id),
        recorded_at=record.recorded_at,
        source=record.source,
        acquisition_method=record.acquisition_method,
        normalization_method=record.normalization_method,
        manifest_id=DatasetId(record.manifest_id) if record.manifest_id is not None else None,
        notes=record.notes,
    )


class FakeRunMapper:
    """In-memory `RunMapper` test double."""

    def to_durable_record(self, aggregate: Run) -> RunDurableRecord:
        return RunDurableRecord(
            identity=_identity_to_durable(aggregate.identity),
            campaign_id=str(aggregate.campaign_id),
            lifecycle_state=aggregate.state.value,
            manifests=tuple(_manifest_to_durable(manifest) for manifest in aggregate.manifests),
            version=aggregate.version.value,
            next_transition_sequence=aggregate.next_transition_sequence.value,
            transition_history=tuple(
                _transition_to_durable(record) for record in aggregate.transition_history
            ),
        )

    def from_durable_record(self, record: RunDurableRecord) -> RunReconstructionState:
        try:
            lifecycle_state = RunLifecycleState(record.lifecycle_state)
        except ValueError as exc:
            raise MapperError(
                MapperErrorCategory.INVALID_DURABLE_RECORD,
                "unknown Run lifecycle_state",
                aggregate_kind="Run",
                field="lifecycle_state",
            ) from exc
        return RunReconstructionState(
            identity=_identity_from_durable(record.identity, RunId),
            campaign_id=CampaignId(record.campaign_id),
            state=lifecycle_state,
            manifests=tuple(_manifest_from_durable(item) for item in record.manifests),
            version=AggregateVersion(record.version),
            next_transition_sequence=TransitionSequence(record.next_transition_sequence),
            transition_history=tuple(
                _transition_from_durable(item, RunId) for item in record.transition_history
            ),
        )


# --- EvidencePackage ----------------------------------------------------------


def _criterion_to_durable(result: CriterionResult) -> CriterionResultDurableRecord:
    return CriterionResultDurableRecord(
        evidence_package_id=str(result.evidence_package_id),
        criterion_id=result.criterion_id,
        recorded_at=result.recorded_at,
        result_label=result.result_label,
        summary=result.summary,
        evidence_references=result.evidence_references,
    )


def _criterion_from_durable(record: CriterionResultDurableRecord) -> CriterionResult:
    return CriterionResult(
        evidence_package_id=EvidencePackageId(record.evidence_package_id),
        criterion_id=record.criterion_id,
        recorded_at=record.recorded_at,
        result_label=record.result_label,
        summary=record.summary,
        evidence_references=record.evidence_references,
    )


class FakeEvidencePackageMapper:
    """In-memory `EvidencePackageMapper` test double."""

    def to_durable_record(self, aggregate: EvidencePackage) -> EvidencePackageDurableRecord:
        return EvidencePackageDurableRecord(
            identity=_identity_to_durable(aggregate.identity),
            run_id=str(aggregate.run_id),
            lifecycle_state=aggregate.state.value,
            criterion_results=tuple(
                _criterion_to_durable(result) for result in aggregate.criterion_results
            ),
            artifact_references=tuple(
                reference.value for reference in aggregate.artifact_references
            ),
            version=aggregate.version.value,
            next_transition_sequence=aggregate.next_transition_sequence.value,
            transition_history=tuple(
                _transition_to_durable(record) for record in aggregate.transition_history
            ),
        )

    def from_durable_record(
        self, record: EvidencePackageDurableRecord
    ) -> EvidencePackageReconstructionState:
        try:
            lifecycle_state = EvidencePackageLifecycleState(record.lifecycle_state)
        except ValueError as exc:
            raise MapperError(
                MapperErrorCategory.INVALID_DURABLE_RECORD,
                "unknown EvidencePackage lifecycle_state",
                aggregate_kind="EvidencePackage",
                field="lifecycle_state",
            ) from exc
        return EvidencePackageReconstructionState(
            identity=_identity_from_durable(record.identity, EvidencePackageId),
            run_id=RunId(record.run_id),
            state=lifecycle_state,
            criterion_results=tuple(
                _criterion_from_durable(item) for item in record.criterion_results
            ),
            artifact_references=tuple(
                ArtifactReference(value) for value in record.artifact_references
            ),
            version=AggregateVersion(record.version),
            next_transition_sequence=TransitionSequence(record.next_transition_sequence),
            transition_history=tuple(
                _transition_from_durable(item, EvidencePackageId)
                for item in record.transition_history
            ),
        )


# --- Review -------------------------------------------------------------------


def _finding_to_durable(finding: ReviewFinding) -> ReviewFindingDurableRecord:
    return ReviewFindingDurableRecord(
        sequence=finding.sequence,
        text=finding.text,
        rationale=finding.rationale,
        evidence_references=finding.evidence_references,
    )


def _finding_from_durable(record: ReviewFindingDurableRecord) -> ReviewFinding:
    return ReviewFinding(
        sequence=record.sequence,
        text=record.text,
        rationale=record.rationale,
        evidence_references=record.evidence_references,
    )


class FakeReviewMapper:
    """In-memory `ReviewMapper` test double."""

    def to_durable_record(self, aggregate: Review) -> ReviewDurableRecord:
        return ReviewDurableRecord(
            identity=_identity_to_durable(aggregate.identity),
            target_evidence_package_id=str(aggregate.target.evidence_package_id),
            reviewer_reference=str(aggregate.reviewer),
            lifecycle_state=aggregate.state.value,
            findings=tuple(_finding_to_durable(finding) for finding in aggregate.findings),
            disposition=aggregate.disposition.value if aggregate.disposition is not None else None,
            final_disposition_rationale=aggregate.final_disposition_rationale,
            cancellation_reason=aggregate.cancellation_reason,
            version=aggregate.version.value,
            next_transition_sequence=aggregate.next_transition_sequence.value,
            transition_history=tuple(
                _transition_to_durable(record) for record in aggregate.transition_history
            ),
        )

    def from_durable_record(self, record: ReviewDurableRecord) -> ReviewReconstructionState:
        try:
            lifecycle_state = ReviewLifecycleState(record.lifecycle_state)
        except ValueError as exc:
            raise MapperError(
                MapperErrorCategory.INVALID_DURABLE_RECORD,
                "unknown Review lifecycle_state",
                aggregate_kind="Review",
                field="lifecycle_state",
            ) from exc
        disposition: ReviewDisposition | None = None
        if record.disposition is not None:
            try:
                disposition = ReviewDisposition(record.disposition)
            except ValueError as exc:
                raise MapperError(
                    MapperErrorCategory.INVALID_DURABLE_RECORD,
                    "unknown Review disposition",
                    aggregate_kind="Review",
                    field="disposition",
                ) from exc
        return ReviewReconstructionState(
            identity=_identity_from_durable(record.identity, ReviewId),
            target=ReviewTargetReference(EvidencePackageId(record.target_evidence_package_id)),
            reviewer=ReviewerReference(record.reviewer_reference),
            state=lifecycle_state,
            findings=tuple(_finding_from_durable(item) for item in record.findings),
            disposition=disposition,
            final_disposition_rationale=record.final_disposition_rationale,
            cancellation_reason=record.cancellation_reason,
            version=AggregateVersion(record.version),
            next_transition_sequence=TransitionSequence(record.next_transition_sequence),
            transition_history=tuple(
                _transition_from_durable(item, ReviewId) for item in record.transition_history
            ),
        )
