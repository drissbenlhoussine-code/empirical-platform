"""Retrieve a Review by full identity: concrete query and handler.

MILESTONE-043.
"""

from __future__ import annotations

from dataclasses import dataclass

from empirical_platform.identifiers.pairs import DomainIdentity
from empirical_platform.identifiers.types import EvidencePackageId, ReviewId
from empirical_platform.review.lifecycle import ReviewLifecycleState
from empirical_platform.review.repository import ReviewRepository


@dataclass(frozen=True, slots=True)
class GetReviewQuery:
    """Request to retrieve a Review by its full frozen identity."""

    identity: DomainIdentity[ReviewId]


@dataclass(frozen=True, slots=True)
class ReviewSnapshot:
    """Immutable, milestone-local, bounded Review header/status read value.

    Deliberately excludes `Review.version` (aggregate domain state) and
    `LoadedAggregate.persisted_version` (repository concurrency metadata),
    and does not expose `findings`, `transition_history`, `disposition`,
    `final_disposition_rationale`, or `cancellation_reason` -- see
    MILESTONE_043_CONCRETE_APPLICATION_QUERY_VERTICAL_SLICE_REVIEW_RETRIEVAL_MACRO_DESIGN.md
    Section 6.
    """

    identity: DomainIdentity[ReviewId]
    target_evidence_package_id: EvidencePackageId
    reviewer_reference: str
    state: ReviewLifecycleState


class GetReviewHandler:
    """Retrieves a Review for one `GetReviewQuery`."""

    __slots__ = ("_review_repository",)

    def __init__(self, *, review_repository: ReviewRepository) -> None:
        self._review_repository = review_repository

    def handle(self, query: GetReviewQuery) -> ReviewSnapshot:
        """Load a Review by identity and return its bounded read-side snapshot."""
        loaded = self._review_repository.get(query.identity)
        return ReviewSnapshot(
            identity=loaded.aggregate.identity,
            target_evidence_package_id=loaded.aggregate.target.evidence_package_id,
            reviewer_reference=loaded.aggregate.reviewer.value,
            state=loaded.aggregate.state,
        )
