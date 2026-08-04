"""Create a new Review targeting an existing EvidencePackage: concrete command and handler.

MILESTONE-042.
"""

from __future__ import annotations

from dataclasses import dataclass

from empirical_platform.identifiers.pairs import DomainIdentity
from empirical_platform.identifiers.types import EvidencePackageId, ReviewId
from empirical_platform.review.aggregate import Review, ReviewerReference, ReviewTargetReference
from empirical_platform.review.repository import ReviewRepository
from empirical_platform.shared.identifiers import RuntimeIdentifierGenerator


@dataclass(frozen=True, slots=True)
class CreateReviewCommand:
    """Request to create a new Review targeting an existing EvidencePackage.

    Carries raw, unvalidated data; `CreateReviewHandler` translates it into
    the already-frozen `ReviewId` and `EvidencePackageId` value objects,
    which perform all format validation. EvidencePackage existence is not
    validated here or in the handler -- it is enforced by the database
    foreign-key constraint on the `review.target_evidence_package_id`
    column (see
    MILESTONE_042_CONCRETE_APPLICATION_COMMAND_VERTICAL_SLICE_REVIEW_CREATION_MACRO_DESIGN.md
    Section 6).
    """

    review_governance_id: str
    target_evidence_package_governance_id: str
    reviewer_reference: str


class CreateReviewHandler:
    """Creates and persists a new Review for one command."""

    __slots__ = ("_review_repository", "_runtime_identifier_generator")

    def __init__(
        self,
        *,
        review_repository: ReviewRepository,
        runtime_identifier_generator: RuntimeIdentifierGenerator,
    ) -> None:
        self._review_repository = review_repository
        self._runtime_identifier_generator = runtime_identifier_generator

    def handle(self, command: CreateReviewCommand) -> DomainIdentity[ReviewId]:
        """Create and persist a new Review; return its identity."""
        identity = DomainIdentity(
            governance_id=ReviewId(command.review_governance_id),
            runtime_id=self._runtime_identifier_generator.generate(),
        )
        target = ReviewTargetReference(
            evidence_package_id=EvidencePackageId(command.target_evidence_package_governance_id)
        )
        reviewer = ReviewerReference(command.reviewer_reference)
        review = Review(identity=identity, target=target, reviewer=reviewer)
        self._review_repository.add(review)
        return review.identity
