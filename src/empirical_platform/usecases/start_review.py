"""Start an existing Review, transitioning it from ASSIGNED to IN_PROGRESS.

MILESTONE-044.
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
class StartReviewCommand:
    """Request to transition an existing Review from ASSIGNED to IN_PROGRESS."""

    identity: DomainIdentity[ReviewId]
    expected_persisted_version: AggregateVersion
    actor: str
    occurred_at: datetime
    correlation_id: str | None = None
    reason: str | None = None


class StartReviewHandler:
    """Loads, starts, and persists one Review for one command."""

    __slots__ = ("_review_repository",)

    def __init__(self, *, review_repository: ReviewRepository) -> None:
        self._review_repository = review_repository

    def handle(self, command: StartReviewCommand) -> SaveResult:
        """Transition the identified Review to IN_PROGRESS and persist it."""
        loaded = self._review_repository.get(command.identity)
        review = loaded.aggregate
        review.start(
            actor=command.actor,
            occurred_at=command.occurred_at,
            correlation_id=command.correlation_id,
            reason=command.reason,
        )
        return self._review_repository.save(
            review, expected_persisted_version=command.expected_persisted_version
        )
