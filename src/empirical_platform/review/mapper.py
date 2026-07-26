"""Domain-facing Review persistence mapper contract (MILESTONE-021).

The concrete `ConcreteReviewMapper` at the bottom of this module is the
MILESTONE-023 concrete mapper implementation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from empirical_platform.identifiers.pairs import DomainIdentity
from empirical_platform.identifiers.types import EvidencePackageId, ReviewId
from empirical_platform.review._reconstruction import ReviewReconstructionState
from empirical_platform.review.aggregate import (
    Review,
    ReviewerReference,
    ReviewFinding,
    ReviewTargetReference,
)
from empirical_platform.review.lifecycle import ReviewDisposition, ReviewLifecycleState
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
class ReviewFindingDurableRecord:
    """Persistence-neutral, field-level durable representation of a Review Finding."""

    sequence: int
    text: str
    rationale: str | None
    evidence_references: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ReviewDurableRecord:
    """Persistence-neutral, field-level durable representation of a Review."""

    identity: IdentityDurableRecord
    target_evidence_package_id: str
    reviewer_reference: str
    lifecycle_state: str
    findings: tuple[ReviewFindingDurableRecord, ...]
    disposition: str | None
    final_disposition_rationale: str | None
    cancellation_reason: str | None
    version: int
    next_transition_sequence: int
    transition_history: tuple[TransitionDurableRecord, ...]


class ReviewMapper(Protocol):
    """Persistence-neutral mapper contract between Review and its durable record."""

    def to_durable_record(self, aggregate: Review) -> ReviewDurableRecord:
        """Transform a Review into its persistence-neutral durable record.

        Pure data transformation: does not mutate the aggregate, increment its
        version, or append transition history. May raise `MapperError` with
        category `INVALID_AGGREGATE_FOR_MAPPING` if the aggregate is not valid
        for mapping.
        """
        ...

    def from_durable_record(self, record: ReviewDurableRecord) -> ReviewReconstructionState:
        """Transform a durable record into a `ReviewReconstructionState`.

        Does not call the internal `_reconstruct_review` factory; that call
        remains a future repository implementation's responsibility. Raises
        `MapperError` with category `INVALID_DURABLE_RECORD` for durable data
        that is structurally malformed before reconstruction can validate it.
        """
        ...


def _identity_to_durable(identity: DomainIdentity[Any]) -> IdentityDurableRecord:
    return IdentityDurableRecord(
        governance_id=str(identity.governance_id),
        runtime_id=str(identity.runtime_id),
    )


def _identity_from_durable(record: IdentityDurableRecord) -> DomainIdentity[ReviewId]:
    return DomainIdentity(
        governance_id=ReviewId(record.governance_id),
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
) -> StateTransitionRecord[DomainIdentity[ReviewId]]:
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


class ConcreteReviewMapper:
    """Concrete, storage-agnostic `ReviewMapper` implementation (MILESTONE-023)."""

    def to_durable_record(self, aggregate: Review) -> ReviewDurableRecord:
        """Transform a Review into its persistence-neutral durable record."""
        return ReviewDurableRecord(
            identity=_identity_to_durable(aggregate.identity),
            target_evidence_package_id=str(aggregate.target.evidence_package_id),
            reviewer_reference=str(aggregate.reviewer),
            lifecycle_state=aggregate.state.value,
            findings=tuple(_finding_to_durable(finding) for finding in aggregate.findings),
            disposition=(
                aggregate.disposition.value if aggregate.disposition is not None else None
            ),
            final_disposition_rationale=aggregate.final_disposition_rationale,
            cancellation_reason=aggregate.cancellation_reason,
            version=aggregate.version.value,
            next_transition_sequence=aggregate.next_transition_sequence.value,
            transition_history=tuple(
                _transition_to_durable(record) for record in aggregate.transition_history
            ),
        )

    def from_durable_record(self, record: ReviewDurableRecord) -> ReviewReconstructionState:
        """Transform a durable record into a `ReviewReconstructionState`."""
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
        try:
            identity = _identity_from_durable(record.identity)
            target = ReviewTargetReference(EvidencePackageId(record.target_evidence_package_id))
            reviewer = ReviewerReference(record.reviewer_reference)
            findings = tuple(_finding_from_durable(item) for item in record.findings)
            transition_history = tuple(
                _transition_from_durable(item) for item in record.transition_history
            )
        except (ValueError, TypeError) as exc:
            raise MapperError(
                MapperErrorCategory.INVALID_DURABLE_RECORD,
                "Review durable record is structurally malformed",
                aggregate_kind="Review",
            ) from exc
        return ReviewReconstructionState(
            identity=identity,
            target=target,
            reviewer=reviewer,
            state=lifecycle_state,
            findings=findings,
            disposition=disposition,
            final_disposition_rationale=record.final_disposition_rationale,
            cancellation_reason=record.cancellation_reason,
            version=AggregateVersion(record.version),
            next_transition_sequence=TransitionSequence(record.next_transition_sequence),
            transition_history=transition_history,
        )
