"""Domain-facing Review persistence mapper contract (MILESTONE-021)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from empirical_platform.review._reconstruction import ReviewReconstructionState
from empirical_platform.review.aggregate import Review
from empirical_platform.shared.contracts.mapping import (
    IdentityDurableRecord,
    TransitionDurableRecord,
)


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
