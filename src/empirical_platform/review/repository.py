"""Domain-facing Review repository contract (MILESTONE-020)."""

from __future__ import annotations

from typing import Protocol

from empirical_platform.identifiers.pairs import DomainIdentity
from empirical_platform.identifiers.types import ReviewId
from empirical_platform.review.aggregate import Review
from empirical_platform.shared.contracts.repository import LoadedAggregate, SaveResult
from empirical_platform.shared.domain.versioning import AggregateVersion


class ReviewRepository(Protocol):
    """Domain-facing, persistence-neutral repository contract for Review."""

    def get(self, identity: DomainIdentity[ReviewId]) -> LoadedAggregate[Review]:
        """Load a Review by canonical identity.

        Raises `AggregateNotFound` when no persisted Review exists for the
        identity, and `InvalidPersistedAggregateState` when durable state
        cannot be safely restored.
        """
        ...

    def add(self, aggregate: Review) -> SaveResult:
        """Persist a new Review that must not already exist.

        Raises `AggregateAlreadyExists` on duplicate `DomainIdentity`,
        `governance_id`, or `runtime_id`, and `InvalidAggregateForPersistence`
        when the in-memory aggregate is not valid for persistence.
        """
        ...

    def save(
        self, aggregate: Review, *, expected_persisted_version: AggregateVersion
    ) -> SaveResult:
        """Persist an existing Review guarded by optimistic concurrency.

        Raises `AggregateNotFound` when no persisted Review exists for the
        aggregate's identity, `OptimisticConcurrencyConflict` when the durable
        version does not match `expected_persisted_version`, and
        `InvalidAggregateForPersistence` when the in-memory aggregate is not
        valid for persistence.
        """
        ...
