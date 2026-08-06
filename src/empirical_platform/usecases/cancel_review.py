"""Cancel an existing Review from a non-terminal state.

Concrete command and handler. MILESTONE-049.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from empirical_platform.identifiers.pairs import DomainIdentity
from empirical_platform.identifiers.types import ReviewId
from empirical_platform.review.repository import ReviewRepository
from empirical_platform.shared.contracts.repository import SaveResult
from empirical_platform.shared.domain.versioning import AggregateVersion


@dataclass(frozen=True, slots=True)
class CancelReviewCommand:
    """Request to cancel an existing Review from a non-terminal state."""

    identity: DomainIdentity[ReviewId]
    expected_persisted_version: AggregateVersion
    reason: str
    actor: str
    occurred_at: datetime
    correlation_id: str | None = None


class CancelReviewHandler:
    """Loads, cancels, and persists one Review for one command."""

    __slots__ = ("_review_repository",)

    def __init__(self, *, review_repository: ReviewRepository) -> None:
        self._review_repository = review_repository

    def handle(self, command: CancelReviewCommand) -> SaveResult:
        """Cancel the identified Review and persist it."""
        loaded = self._review_repository.get(command.identity)
        review = loaded.aggregate
        review.cancel(
            reason=command.reason,
            actor=command.actor,
            occurred_at=command.occurred_at,
            correlation_id=command.correlation_id,
        )
        return self._review_repository.save(
            review, expected_persisted_version=command.expected_persisted_version
        )
