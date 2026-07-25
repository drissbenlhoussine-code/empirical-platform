"""MILESTONE-020 contract tests for RunRepository, using an in-memory fake."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from tests.contract._fakes import FakeRunRepository

from empirical_platform.identifiers.pairs import DomainIdentity
from empirical_platform.identifiers.types import CampaignId, RunId
from empirical_platform.run.aggregate import Run
from empirical_platform.shared.contracts.repository import (
    AggregateAlreadyExists,
    AggregateNotFound,
    OptimisticConcurrencyConflict,
    SaveOperation,
)
from empirical_platform.shared.domain.versioning import AggregateVersion
from empirical_platform.shared.identifiers import RuntimeIdentifier

OCCURRED_AT = datetime(2026, 7, 26, tzinfo=UTC)


def _identity(governance_value: str = "RUN-0001") -> DomainIdentity[RunId]:
    return DomainIdentity(
        governance_id=RunId(governance_value),
        runtime_id=RuntimeIdentifier(str(uuid.uuid4())),
    )


def _run(identity: DomainIdentity[RunId] | None = None) -> Run:
    return Run(identity=identity or _identity(), campaign_id=CampaignId("CAMP-0001"))


def test_get_missing_raises_aggregate_not_found() -> None:
    repository = FakeRunRepository()

    with pytest.raises(AggregateNotFound) as excinfo:
        repository.get(_identity())

    assert excinfo.value.aggregate_kind == "Run"


def test_add_creates_and_returns_created_result() -> None:
    repository = FakeRunRepository()
    run = _run()

    result = repository.add(run)

    assert result.operation is SaveOperation.CREATED
    assert result.persisted_version == run.version


def test_add_duplicate_full_identity_raises_already_exists() -> None:
    repository = FakeRunRepository()
    identity = _identity()
    repository.add(_run(identity))

    with pytest.raises(AggregateAlreadyExists):
        repository.add(_run(identity))


def test_add_duplicate_governance_id_raises_already_exists() -> None:
    repository = FakeRunRepository()
    repository.add(_run(_identity("RUN-0002")))

    colliding_identity = DomainIdentity(
        governance_id=RunId("RUN-0002"), runtime_id=RuntimeIdentifier(str(uuid.uuid4()))
    )
    with pytest.raises(AggregateAlreadyExists):
        repository.add(_run(colliding_identity))


def test_add_duplicate_runtime_id_raises_already_exists() -> None:
    repository = FakeRunRepository()
    shared_runtime_id = RuntimeIdentifier(str(uuid.uuid4()))
    repository.add(
        _run(DomainIdentity(governance_id=RunId("RUN-0003"), runtime_id=shared_runtime_id))
    )

    colliding_identity = DomainIdentity(
        governance_id=RunId("RUN-0004"), runtime_id=shared_runtime_id
    )
    with pytest.raises(AggregateAlreadyExists):
        repository.add(_run(colliding_identity))


def test_get_after_add_returns_loaded_aggregate_with_persisted_version() -> None:
    repository = FakeRunRepository()
    identity = _identity()
    run = _run(identity)
    repository.add(run)

    loaded = repository.get(identity)

    assert loaded.aggregate is run
    assert loaded.persisted_version == AggregateVersion.initial()


def test_loaded_persisted_version_does_not_change_when_aggregate_mutates() -> None:
    repository = FakeRunRepository()
    identity = _identity()
    run = _run(identity)
    repository.add(run)

    loaded = repository.get(identity)
    token_before_mutation = loaded.persisted_version

    run.authorize(actor="tester", occurred_at=OCCURRED_AT)

    assert loaded.persisted_version == token_before_mutation
    assert loaded.persisted_version != run.version


def test_loaded_aggregate_is_immutable() -> None:
    repository = FakeRunRepository()
    identity = _identity()
    run = _run(identity)
    repository.add(run)
    loaded = repository.get(identity)

    with pytest.raises(AttributeError):
        loaded.aggregate = run  # type: ignore[misc]
    with pytest.raises(AttributeError):
        loaded.persisted_version = AggregateVersion.initial()  # type: ignore[misc]


def test_save_on_missing_persisted_state_raises_aggregate_not_found() -> None:
    repository = FakeRunRepository()
    run = _run()

    with pytest.raises(AggregateNotFound):
        repository.save(run, expected_persisted_version=run.version)


def test_save_after_mutation_with_correct_expected_version_returns_updated() -> None:
    repository = FakeRunRepository()
    identity = _identity()
    run = _run(identity)
    repository.add(run)
    loaded = repository.get(identity)

    run.authorize(actor="tester", occurred_at=OCCURRED_AT)
    result = repository.save(run, expected_persisted_version=loaded.persisted_version)

    assert result.operation is SaveOperation.UPDATED
    assert result.persisted_version == run.version


def test_save_stale_expected_version_raises_conflict_with_facts() -> None:
    repository = FakeRunRepository()
    identity = _identity()
    run = _run(identity)
    repository.add(run)
    stale_version = run.version

    run.authorize(actor="tester", occurred_at=OCCURRED_AT)
    repository.save(run, expected_persisted_version=stale_version)
    run.start_acquisition(actor="tester", occurred_at=OCCURRED_AT)

    with pytest.raises(OptimisticConcurrencyConflict) as excinfo:
        repository.save(run, expected_persisted_version=stale_version)

    assert excinfo.value.expected_persisted_version == stale_version
    assert excinfo.value.aggregate_current_version == run.version
    assert excinfo.value.actual_persisted_version is not None
    assert excinfo.value.actual_persisted_version != stale_version


def test_save_unchanged_returns_unchanged() -> None:
    repository = FakeRunRepository()
    identity = _identity()
    run = _run(identity)
    repository.add(run)
    loaded = repository.get(identity)

    result = repository.save(run, expected_persisted_version=loaded.persisted_version)

    assert result.operation is SaveOperation.UNCHANGED
    assert result.persisted_version == run.version


def test_repeated_save_requires_latest_expected_version() -> None:
    repository = FakeRunRepository()
    identity = _identity()
    run = _run(identity)
    repository.add(run)
    first_expected_version = run.version

    run.authorize(actor="tester", occurred_at=OCCURRED_AT)
    first_result = repository.save(run, expected_persisted_version=first_expected_version)

    run.start_acquisition(actor="tester", occurred_at=OCCURRED_AT)
    second_result = repository.save(run, expected_persisted_version=first_result.persisted_version)

    assert second_result.operation is SaveOperation.UPDATED
    assert second_result.persisted_version == run.version
