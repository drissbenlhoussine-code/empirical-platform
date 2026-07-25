"""MILESTONE-020 contract tests for EvidencePackageRepository, using an in-memory fake."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from tests.contract._fakes import FakeEvidencePackageRepository

from empirical_platform.evidence.package import ArtifactReference, EvidencePackage
from empirical_platform.identifiers.pairs import DomainIdentity
from empirical_platform.identifiers.types import EvidencePackageId, RunId
from empirical_platform.shared.contracts.repository import (
    AggregateAlreadyExists,
    AggregateNotFound,
    OptimisticConcurrencyConflict,
    SaveOperation,
)
from empirical_platform.shared.domain.versioning import AggregateVersion
from empirical_platform.shared.identifiers import RuntimeIdentifier

OCCURRED_AT = datetime(2026, 7, 26, tzinfo=UTC)


def _identity(governance_value: str = "EVID-0001") -> DomainIdentity[EvidencePackageId]:
    return DomainIdentity(
        governance_id=EvidencePackageId(governance_value),
        runtime_id=RuntimeIdentifier(str(uuid.uuid4())),
    )


def _package(identity: DomainIdentity[EvidencePackageId] | None = None) -> EvidencePackage:
    return EvidencePackage(identity or _identity(), RunId("RUN-0001"))


def test_get_missing_raises_aggregate_not_found() -> None:
    repository = FakeEvidencePackageRepository()

    with pytest.raises(AggregateNotFound) as excinfo:
        repository.get(_identity())

    assert excinfo.value.aggregate_kind == "EvidencePackage"


def test_add_creates_and_returns_created_result() -> None:
    repository = FakeEvidencePackageRepository()
    package = _package()

    result = repository.add(package)

    assert result.operation is SaveOperation.CREATED
    assert result.persisted_version == package.version


def test_add_duplicate_full_identity_raises_already_exists() -> None:
    repository = FakeEvidencePackageRepository()
    identity = _identity()
    repository.add(_package(identity))

    with pytest.raises(AggregateAlreadyExists):
        repository.add(_package(identity))


def test_add_duplicate_governance_id_raises_already_exists() -> None:
    repository = FakeEvidencePackageRepository()
    repository.add(_package(_identity("EVID-0002")))

    colliding_identity = DomainIdentity(
        governance_id=EvidencePackageId("EVID-0002"),
        runtime_id=RuntimeIdentifier(str(uuid.uuid4())),
    )
    with pytest.raises(AggregateAlreadyExists):
        repository.add(_package(colliding_identity))


def test_add_duplicate_runtime_id_raises_already_exists() -> None:
    repository = FakeEvidencePackageRepository()
    shared_runtime_id = RuntimeIdentifier(str(uuid.uuid4()))
    repository.add(
        _package(
            DomainIdentity(
                governance_id=EvidencePackageId("EVID-0003"), runtime_id=shared_runtime_id
            )
        )
    )

    colliding_identity = DomainIdentity(
        governance_id=EvidencePackageId("EVID-0004"), runtime_id=shared_runtime_id
    )
    with pytest.raises(AggregateAlreadyExists):
        repository.add(_package(colliding_identity))


def test_get_after_add_returns_loaded_aggregate_with_persisted_version() -> None:
    repository = FakeEvidencePackageRepository()
    identity = _identity()
    package = _package(identity)
    repository.add(package)

    loaded = repository.get(identity)

    assert loaded.aggregate is package
    assert loaded.persisted_version == AggregateVersion.initial()


def test_loaded_persisted_version_does_not_change_when_aggregate_mutates() -> None:
    repository = FakeEvidencePackageRepository()
    identity = _identity()
    package = _package(identity)
    repository.add(package)

    package.start_collection(actor="tester", occurred_at=OCCURRED_AT)
    loaded = repository.get(identity)
    token_before_mutation = loaded.persisted_version

    package.add_artifact_reference(ArtifactReference("artifact-1"))

    assert loaded.persisted_version == token_before_mutation
    assert loaded.persisted_version != package.version


def test_loaded_aggregate_is_immutable() -> None:
    repository = FakeEvidencePackageRepository()
    identity = _identity()
    package = _package(identity)
    repository.add(package)
    loaded = repository.get(identity)

    with pytest.raises(AttributeError):
        loaded.aggregate = package  # type: ignore[misc]
    with pytest.raises(AttributeError):
        loaded.persisted_version = AggregateVersion.initial()  # type: ignore[misc]


def test_save_on_missing_persisted_state_raises_aggregate_not_found() -> None:
    repository = FakeEvidencePackageRepository()
    package = _package()

    with pytest.raises(AggregateNotFound):
        repository.save(package, expected_persisted_version=package.version)


def test_save_after_mutation_with_correct_expected_version_returns_updated() -> None:
    repository = FakeEvidencePackageRepository()
    identity = _identity()
    package = _package(identity)
    repository.add(package)
    package.start_collection(actor="tester", occurred_at=OCCURRED_AT)
    loaded = repository.get(identity)

    package.add_artifact_reference(ArtifactReference("artifact-1"))
    result = repository.save(package, expected_persisted_version=loaded.persisted_version)

    assert result.operation is SaveOperation.UPDATED
    assert result.persisted_version == package.version


def test_save_stale_expected_version_raises_conflict_with_facts() -> None:
    repository = FakeEvidencePackageRepository()
    identity = _identity()
    package = _package(identity)
    repository.add(package)
    stale_version = package.version
    package.start_collection(actor="tester", occurred_at=OCCURRED_AT)

    package.add_artifact_reference(ArtifactReference("artifact-1"))
    repository.save(package, expected_persisted_version=stale_version)
    package.add_artifact_reference(ArtifactReference("artifact-2"))

    with pytest.raises(OptimisticConcurrencyConflict) as excinfo:
        repository.save(package, expected_persisted_version=stale_version)

    assert excinfo.value.expected_persisted_version == stale_version
    assert excinfo.value.aggregate_current_version == package.version
    assert excinfo.value.actual_persisted_version is not None
    assert excinfo.value.actual_persisted_version != stale_version


def test_save_unchanged_returns_unchanged() -> None:
    repository = FakeEvidencePackageRepository()
    identity = _identity()
    package = _package(identity)
    repository.add(package)
    loaded = repository.get(identity)

    result = repository.save(package, expected_persisted_version=loaded.persisted_version)

    assert result.operation is SaveOperation.UNCHANGED
    assert result.persisted_version == package.version


def test_repeated_save_requires_latest_expected_version() -> None:
    repository = FakeEvidencePackageRepository()
    identity = _identity()
    package = _package(identity)
    repository.add(package)
    first_expected_version = package.version
    package.start_collection(actor="tester", occurred_at=OCCURRED_AT)

    package.add_artifact_reference(ArtifactReference("artifact-1"))
    first_result = repository.save(package, expected_persisted_version=first_expected_version)

    package.add_artifact_reference(ArtifactReference("artifact-2"))
    second_result = repository.save(
        package, expected_persisted_version=first_result.persisted_version
    )

    assert second_result.operation is SaveOperation.UPDATED
    assert second_result.persisted_version == package.version
