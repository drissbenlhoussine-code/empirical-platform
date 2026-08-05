"""Add a new finding to an existing, IN_PROGRESS Review.

Concrete command and handler. MILESTONE-045.
"""

from __future__ import annotations

from dataclasses import dataclass

from empirical_platform.identifiers.pairs import DomainIdentity
from empirical_platform.identifiers.types import ReviewId
from empirical_platform.review.repository import ReviewRepository
from empirical_platform.shared.contracts.repository import SaveResult
from empirical_platform.shared.domain.versioning import AggregateVersion


@dataclass(frozen=True, slots=True)
class AddReviewFindingCommand:
    """Request to append one new finding to an existing Review."""

    identity: DomainIdentity[ReviewId]
    expected_persisted_version: AggregateVersion
    text: str
    rationale: str | None = None
    evidence_references: tuple[str, ...] = ()


class AddReviewFindingHandler:
    """Loads, appends a finding to, and persists one Review for one command."""

    __slots__ = ("_review_repository",)

    def __init__(self, *, review_repository: ReviewRepository) -> None:
        self._review_repository = review_repository

    def handle(self, command: AddReviewFindingCommand) -> SaveResult:
        """Append the requested finding to the identified Review and persist it."""
        loaded = self._review_repository.get(command.identity)
        review = loaded.aggregate
        review.add_finding(
            text=command.text,
            rationale=command.rationale,
            evidence_references=command.evidence_references,
        )
        return self._review_repository.save(
            review, expected_persisted_version=command.expected_persisted_version
        )
