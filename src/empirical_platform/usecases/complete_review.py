"""Complete an existing, IN_PROGRESS Review with non-empty findings.

Concrete command and handler. MILESTONE-046.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from empirical_platform.identifiers.pairs import DomainIdentity
from empirical_platform.identifiers.types import ReviewId
from empirical_platform.review.lifecycle import ReviewDisposition as ReviewDisposition
from empirical_platform.review.repository import ReviewRepository
from empirical_platform.shared.contracts.repository import SaveResult
from empirical_platform.shared.domain.versioning import AggregateVersion


@dataclass(frozen=True, slots=True)
class CompleteReviewCommand:
    """Request to transition an existing Review from IN_PROGRESS to COMPLETED."""

    identity: DomainIdentity[ReviewId]
    expected_persisted_version: AggregateVersion
    disposition: ReviewDisposition
    final_disposition_rationale: str
    actor: str
    occurred_at: datetime
    correlation_id: str | None = None


class CompleteReviewHandler:
    """Loads, completes, and persists one Review for one command."""

    __slots__ = ("_review_repository",)

    def __init__(self, *, review_repository: ReviewRepository) -> None:
        self._review_repository = review_repository

    def handle(self, command: CompleteReviewCommand) -> SaveResult:
        """Transition the identified Review to COMPLETED and persist it."""
        loaded = self._review_repository.get(command.identity)
        review = loaded.aggregate
        review.complete(
            disposition=command.disposition,
            final_disposition_rationale=command.final_disposition_rationale,
            actor=command.actor,
            occurred_at=command.occurred_at,
            correlation_id=command.correlation_id,
        )
        return self._review_repository.save(
            review, expected_persisted_version=command.expected_persisted_version
        )
