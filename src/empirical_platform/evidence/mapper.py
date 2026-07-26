"""Domain-facing EvidencePackage persistence mapper contract (MILESTONE-021).

The concrete `ConcreteEvidencePackageMapper` at the bottom of this module is
the MILESTONE-023 concrete mapper implementation.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol

from empirical_platform.evidence._reconstruction import EvidencePackageReconstructionState
from empirical_platform.evidence.lifecycle import EvidencePackageLifecycleState
from empirical_platform.evidence.package import ArtifactReference, EvidencePackage
from empirical_platform.evidence.results import CriterionResult
from empirical_platform.identifiers.pairs import DomainIdentity
from empirical_platform.identifiers.types import EvidencePackageId, RunId
from empirical_platform.shared.contracts.mapping import (
    IdentityDurableRecord,
    MapperError,
    MapperErrorCategory,
    TransitionDurableRecord,
)
from empirical_platform.shared.domain.transitions import StateTransitionRecord
from empirical_platform.shared.domain.versioning import AggregateVersion, TransitionSequence
from empirical_platform.shared.identifiers import RuntimeIdentifier


@dataclass(frozen=True, slots=True)
class CriterionResultDurableRecord:
    """Persistence-neutral, field-level durable representation of a Criterion Result."""

    evidence_package_id: str
    criterion_id: str
    recorded_at: datetime
    result_label: str
    summary: str | None
    evidence_references: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class EvidencePackageDurableRecord:
    """Persistence-neutral, field-level durable representation of an EvidencePackage."""

    identity: IdentityDurableRecord
    run_id: str
    lifecycle_state: str
    criterion_results: tuple[CriterionResultDurableRecord, ...]
    artifact_references: tuple[str, ...]
    version: int
    next_transition_sequence: int
    transition_history: tuple[TransitionDurableRecord, ...]


class EvidencePackageMapper(Protocol):
    """Persistence-neutral mapper contract between EvidencePackage and its durable record."""

    def to_durable_record(self, aggregate: EvidencePackage) -> EvidencePackageDurableRecord:
        """Transform an EvidencePackage into its persistence-neutral durable record.

        Pure data transformation: does not mutate the aggregate, increment its
        version, or append transition history. May raise `MapperError` with
        category `INVALID_AGGREGATE_FOR_MAPPING` if the aggregate is not valid
        for mapping.
        """
        ...

    def from_durable_record(
        self, record: EvidencePackageDurableRecord
    ) -> EvidencePackageReconstructionState:
        """Transform a durable record into an `EvidencePackageReconstructionState`.

        Does not call the internal `_reconstruct_evidence_package` factory;
        that call remains a future repository implementation's responsibility.
        Raises `MapperError` with category `INVALID_DURABLE_RECORD` for durable
        data that is structurally malformed before reconstruction can validate it.
        """
        ...


def _identity_to_durable(identity: DomainIdentity[Any]) -> IdentityDurableRecord:
    return IdentityDurableRecord(
        governance_id=str(identity.governance_id),
        runtime_id=str(identity.runtime_id),
    )


def _identity_from_durable(record: IdentityDurableRecord) -> DomainIdentity[EvidencePackageId]:
    return DomainIdentity(
        governance_id=EvidencePackageId(record.governance_id),
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
    record: TransitionDurableRecord,
) -> StateTransitionRecord[DomainIdentity[EvidencePackageId]]:
    identity_reference = (
        _identity_from_durable(record.identity_reference)
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


class ConcreteEvidencePackageMapper:
    """Concrete, storage-agnostic `EvidencePackageMapper` implementation (MILESTONE-023)."""

    def to_durable_record(self, aggregate: EvidencePackage) -> EvidencePackageDurableRecord:
        """Transform an EvidencePackage into its persistence-neutral durable record."""
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
        """Transform a durable record into an `EvidencePackageReconstructionState`."""
        try:
            lifecycle_state = EvidencePackageLifecycleState(record.lifecycle_state)
        except ValueError as exc:
            raise MapperError(
                MapperErrorCategory.INVALID_DURABLE_RECORD,
                "unknown EvidencePackage lifecycle_state",
                aggregate_kind="EvidencePackage",
                field="lifecycle_state",
            ) from exc
        try:
            identity = _identity_from_durable(record.identity)
            run_id = RunId(record.run_id)
            criterion_results = tuple(
                _criterion_from_durable(item) for item in record.criterion_results
            )
            artifact_references = tuple(
                ArtifactReference(value) for value in record.artifact_references
            )
            transition_history = tuple(
                _transition_from_durable(item) for item in record.transition_history
            )
        except (ValueError, TypeError) as exc:
            raise MapperError(
                MapperErrorCategory.INVALID_DURABLE_RECORD,
                "EvidencePackage durable record is structurally malformed",
                aggregate_kind="EvidencePackage",
            ) from exc
        return EvidencePackageReconstructionState(
            identity=identity,
            run_id=run_id,
            state=lifecycle_state,
            criterion_results=criterion_results,
            artifact_references=artifact_references,
            version=AggregateVersion(record.version),
            next_transition_sequence=TransitionSequence(record.next_transition_sequence),
            transition_history=transition_history,
        )
