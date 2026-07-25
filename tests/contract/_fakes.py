"""In-memory repository test doubles for MILESTONE-020 contract tests.

These fakes are test-only scaffolding, not product code. They exist to verify
the frozen MILESTONE-020 repository-contract semantics (identity uniqueness,
optimistic concurrency, save-result shape, error taxonomy) without a database
adapter, per the frozen design's "do not implement a database adapter to test
the abstract contract" instruction. `InMemoryRepositoryFake` is intentionally
generic *test* infrastructure; it is not shipped, not exported from
`empirical_platform`, and is not the "generic concrete repository" the frozen
design forbids as a product abstraction.
"""

from __future__ import annotations

from typing import Any, Protocol

from empirical_platform.campaign.aggregate import Campaign
from empirical_platform.campaign.repository import CampaignRepository
from empirical_platform.evidence.package import EvidencePackage
from empirical_platform.evidence.repository import EvidencePackageRepository
from empirical_platform.identifiers.pairs import DomainIdentity
from empirical_platform.review.aggregate import Review
from empirical_platform.review.repository import ReviewRepository
from empirical_platform.run.aggregate import Run
from empirical_platform.run.repository import RunRepository
from empirical_platform.shared.contracts.repository import (
    AggregateAlreadyExists,
    AggregateNotFound,
    LoadedAggregate,
    OptimisticConcurrencyConflict,
    SaveOperation,
    SaveResult,
)
from empirical_platform.shared.domain.versioning import AggregateVersion


class _IdentifiedVersionedAggregate(Protocol):
    """Structural shape every frozen aggregate root already satisfies."""

    @property
    def identity(self) -> DomainIdentity[Any]: ...

    @property
    def version(self) -> AggregateVersion: ...


class InMemoryRepositoryFake[AggregateT: _IdentifiedVersionedAggregate]:
    """Minimal in-memory test double implementing the frozen contract semantics."""

    def __init__(self, *, aggregate_kind: str) -> None:
        self._aggregate_kind = aggregate_kind
        self._by_pair: dict[tuple[str, str], tuple[AggregateT, AggregateVersion]] = {}
        self._governance_keys: dict[str, tuple[str, str]] = {}
        self._runtime_keys: dict[str, tuple[str, str]] = {}

    def get(self, identity: DomainIdentity[Any]) -> LoadedAggregate[AggregateT]:
        entry = self._by_pair.get(self._pair_key(identity))
        if entry is None:
            raise AggregateNotFound(aggregate_kind=self._aggregate_kind, identity=identity)
        aggregate, persisted_version = entry
        return LoadedAggregate(aggregate=aggregate, persisted_version=persisted_version)

    def add(self, aggregate: AggregateT) -> SaveResult:
        identity = aggregate.identity
        pair_key = self._pair_key(identity)
        governance_key = str(identity.governance_id)
        runtime_key = str(identity.runtime_id)
        if (
            pair_key in self._by_pair
            or governance_key in self._governance_keys
            or runtime_key in self._runtime_keys
        ):
            raise AggregateAlreadyExists(aggregate_kind=self._aggregate_kind, identity=identity)

        self._by_pair[pair_key] = (aggregate, aggregate.version)
        self._governance_keys[governance_key] = pair_key
        self._runtime_keys[runtime_key] = pair_key
        return SaveResult(operation=SaveOperation.CREATED, persisted_version=aggregate.version)

    def save(
        self, aggregate: AggregateT, *, expected_persisted_version: AggregateVersion
    ) -> SaveResult:
        identity = aggregate.identity
        pair_key = self._pair_key(identity)
        entry = self._by_pair.get(pair_key)
        if entry is None:
            raise AggregateNotFound(aggregate_kind=self._aggregate_kind, identity=identity)
        _, durable_version = entry
        if durable_version != expected_persisted_version:
            raise OptimisticConcurrencyConflict(
                aggregate_kind=self._aggregate_kind,
                identity=identity,
                expected_persisted_version=expected_persisted_version,
                aggregate_current_version=aggregate.version,
                actual_persisted_version=durable_version,
            )

        operation = (
            SaveOperation.UNCHANGED
            if aggregate.version == durable_version
            else SaveOperation.UPDATED
        )
        self._by_pair[pair_key] = (aggregate, aggregate.version)
        return SaveResult(operation=operation, persisted_version=aggregate.version)

    @staticmethod
    def _pair_key(identity: DomainIdentity[Any]) -> tuple[str, str]:
        return (str(identity.governance_id), str(identity.runtime_id))


class FakeCampaignRepository:
    """In-memory `CampaignRepository` test double."""

    def __init__(self) -> None:
        self._engine: InMemoryRepositoryFake[Campaign] = InMemoryRepositoryFake(
            aggregate_kind="Campaign"
        )

    def get(self, identity: DomainIdentity[Any]) -> LoadedAggregate[Campaign]:
        return self._engine.get(identity)

    def add(self, aggregate: Campaign) -> SaveResult:
        return self._engine.add(aggregate)

    def save(
        self, aggregate: Campaign, *, expected_persisted_version: AggregateVersion
    ) -> SaveResult:
        return self._engine.save(aggregate, expected_persisted_version=expected_persisted_version)


class FakeRunRepository:
    """In-memory `RunRepository` test double."""

    def __init__(self) -> None:
        self._engine: InMemoryRepositoryFake[Run] = InMemoryRepositoryFake(aggregate_kind="Run")

    def get(self, identity: DomainIdentity[Any]) -> LoadedAggregate[Run]:
        return self._engine.get(identity)

    def add(self, aggregate: Run) -> SaveResult:
        return self._engine.add(aggregate)

    def save(self, aggregate: Run, *, expected_persisted_version: AggregateVersion) -> SaveResult:
        return self._engine.save(aggregate, expected_persisted_version=expected_persisted_version)


class FakeEvidencePackageRepository:
    """In-memory `EvidencePackageRepository` test double."""

    def __init__(self) -> None:
        self._engine: InMemoryRepositoryFake[EvidencePackage] = InMemoryRepositoryFake(
            aggregate_kind="EvidencePackage"
        )

    def get(self, identity: DomainIdentity[Any]) -> LoadedAggregate[EvidencePackage]:
        return self._engine.get(identity)

    def add(self, aggregate: EvidencePackage) -> SaveResult:
        return self._engine.add(aggregate)

    def save(
        self, aggregate: EvidencePackage, *, expected_persisted_version: AggregateVersion
    ) -> SaveResult:
        return self._engine.save(aggregate, expected_persisted_version=expected_persisted_version)


class FakeReviewRepository:
    """In-memory `ReviewRepository` test double."""

    def __init__(self) -> None:
        self._engine: InMemoryRepositoryFake[Review] = InMemoryRepositoryFake(
            aggregate_kind="Review"
        )

    def get(self, identity: DomainIdentity[Any]) -> LoadedAggregate[Review]:
        return self._engine.get(identity)

    def add(self, aggregate: Review) -> SaveResult:
        return self._engine.add(aggregate)

    def save(
        self, aggregate: Review, *, expected_persisted_version: AggregateVersion
    ) -> SaveResult:
        return self._engine.save(aggregate, expected_persisted_version=expected_persisted_version)


def assert_conforms_to_campaign_repository(repository: CampaignRepository) -> None:
    """Statically document Protocol conformance; exercised by mypy, not at runtime."""


def assert_conforms_to_run_repository(repository: RunRepository) -> None:
    """Statically document Protocol conformance; exercised by mypy, not at runtime."""


def assert_conforms_to_evidence_package_repository(repository: EvidencePackageRepository) -> None:
    """Statically document Protocol conformance; exercised by mypy, not at runtime."""


def assert_conforms_to_review_repository(repository: ReviewRepository) -> None:
    """Statically document Protocol conformance; exercised by mypy, not at runtime."""
