"""Domain-facing Run repository contract (MILESTONE-020)."""

from __future__ import annotations

from typing import Protocol

from empirical_platform.identifiers.pairs import DomainIdentity
from empirical_platform.identifiers.types import RunId
from empirical_platform.run.aggregate import Run
from empirical_platform.shared.contracts.repository import LoadedAggregate, SaveResult
from empirical_platform.shared.domain.versioning import AggregateVersion


class RunRepository(Protocol):
    """Domain-facing, persistence-neutral repository contract for Run."""

    def get(self, identity: DomainIdentity[RunId]) -> LoadedAggregate[Run]:
        """Load a Run by canonical identity.

        Raises `AggregateNotFound` when no persisted Run exists for the
        identity, and `InvalidPersistedAggregateState` when durable state
        cannot be safely restored.
        """
        ...

    def add(self, aggregate: Run) -> SaveResult:
        """Persist a new Run that must not already exist.

        Raises `AggregateAlreadyExists` on duplicate `DomainIdentity`,
        `governance_id`, or `runtime_id`, and `InvalidAggregateForPersistence`
        when the in-memory aggregate is not valid for persistence.
        """
        ...

    def save(self, aggregate: Run, *, expected_persisted_version: AggregateVersion) -> SaveResult:
        """Persist an existing Run guarded by optimistic concurrency.

        Raises `AggregateNotFound` when no persisted Run exists for the
        aggregate's identity, `OptimisticConcurrencyConflict` when the durable
        version does not match `expected_persisted_version`, and
        `InvalidAggregateForPersistence` when the in-memory aggregate is not
        valid for persistence.
        """
        ...
