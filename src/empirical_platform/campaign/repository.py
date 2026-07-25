"""Domain-facing Campaign repository contract (MILESTONE-020)."""

from __future__ import annotations

from typing import Protocol

from empirical_platform.campaign.aggregate import Campaign
from empirical_platform.identifiers.pairs import DomainIdentity
from empirical_platform.identifiers.types import CampaignId
from empirical_platform.shared.contracts.repository import LoadedAggregate, SaveResult
from empirical_platform.shared.domain.versioning import AggregateVersion


class CampaignRepository(Protocol):
    """Domain-facing, persistence-neutral repository contract for Campaign."""

    def get(self, identity: DomainIdentity[CampaignId]) -> LoadedAggregate[Campaign]:
        """Load a Campaign by canonical identity.

        Raises `AggregateNotFound` when no persisted Campaign exists for the
        identity, and `InvalidPersistedAggregateState` when durable state
        cannot be safely restored.
        """
        ...

    def add(self, aggregate: Campaign) -> SaveResult:
        """Persist a new Campaign that must not already exist.

        Raises `AggregateAlreadyExists` on duplicate `DomainIdentity`,
        `governance_id`, or `runtime_id`, and `InvalidAggregateForPersistence`
        when the in-memory aggregate is not valid for persistence.
        """
        ...

    def save(
        self, aggregate: Campaign, *, expected_persisted_version: AggregateVersion
    ) -> SaveResult:
        """Persist an existing Campaign guarded by optimistic concurrency.

        Raises `AggregateNotFound` when no persisted Campaign exists for the
        aggregate's identity, `OptimisticConcurrencyConflict` when the durable
        version does not match `expected_persisted_version`, and
        `InvalidAggregateForPersistence` when the in-memory aggregate is not
        valid for persistence.
        """
        ...
