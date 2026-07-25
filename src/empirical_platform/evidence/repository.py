"""Domain-facing EvidencePackage repository contract (MILESTONE-020)."""

from __future__ import annotations

from typing import Protocol

from empirical_platform.evidence.package import EvidencePackage
from empirical_platform.identifiers.pairs import DomainIdentity
from empirical_platform.identifiers.types import EvidencePackageId
from empirical_platform.shared.contracts.repository import LoadedAggregate, SaveResult
from empirical_platform.shared.domain.versioning import AggregateVersion


class EvidencePackageRepository(Protocol):
    """Domain-facing, persistence-neutral repository contract for EvidencePackage."""

    def get(self, identity: DomainIdentity[EvidencePackageId]) -> LoadedAggregate[EvidencePackage]:
        """Load an EvidencePackage by canonical identity.

        Raises `AggregateNotFound` when no persisted EvidencePackage exists
        for the identity, and `InvalidPersistedAggregateState` when durable
        state cannot be safely restored.
        """
        ...

    def add(self, aggregate: EvidencePackage) -> SaveResult:
        """Persist a new EvidencePackage that must not already exist.

        Raises `AggregateAlreadyExists` on duplicate `DomainIdentity`,
        `governance_id`, or `runtime_id`, and `InvalidAggregateForPersistence`
        when the in-memory aggregate is not valid for persistence.
        """
        ...

    def save(
        self, aggregate: EvidencePackage, *, expected_persisted_version: AggregateVersion
    ) -> SaveResult:
        """Persist an existing EvidencePackage guarded by optimistic concurrency.

        Raises `AggregateNotFound` when no persisted EvidencePackage exists
        for the aggregate's identity, `OptimisticConcurrencyConflict` when the
        durable version does not match `expected_persisted_version`, and
        `InvalidAggregateForPersistence` when the in-memory aggregate is not
        valid for persistence.
        """
        ...
