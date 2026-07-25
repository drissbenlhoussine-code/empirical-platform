"""MILESTONE-020 contract tests for ReviewRepository, using an in-memory fake."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from tests.contract._fakes import FakeReviewRepository

from empirical_platform.identifiers.pairs import DomainIdentity
from empirical_platform.identifiers.types import EvidencePackageId, ReviewId
from empirical_platform.review.aggregate import Review, ReviewerReference, ReviewTargetReference
from empirical_platform.shared.contracts.repository import (
    AggregateAlreadyExists,
    AggregateNotFound,
    OptimisticConcurrencyConflict,
    SaveOperation,
)
from empirical_platform.shared.domain.versioning import AggregateVersion
from empirical_platform.shared.identifiers import RuntimeIdentifier

OCCURRED_AT = datetime(2026, 7, 26, tzinfo=UTC)


def _identity(governance_value: str = "REVIEW-0001") -> DomainIdentity[ReviewId]:
    return DomainIdentity(
        governance_id=ReviewId(governance_value),
        runtime_id=RuntimeIdentifier(str(uuid.uuid4())),
    )


def _review(identity: DomainIdentity[ReviewId] | None = None) -> Review:
    return Review(
        identity=identity or _identity(),
        target=ReviewTargetReference(EvidencePackageId("EVID-0001")),
        reviewer=ReviewerReference("reviewer-1"),
    )


def test_get_missing_raises_aggregate_not_found() -> None:
    repository = FakeReviewRepository()

    with pytest.raises(AggregateNotFound) as excinfo:
        repository.get(_identity())

    assert excinfo.value.aggregate_kind == "Review"


def test_add_creates_and_returns_created_result() -> None:
    repository = FakeReviewRepository()
    review = _review()

    result = repository.add(review)

    assert result.operation is SaveOperation.CREATED
    assert result.persisted_version == review.version


def test_add_duplicate_full_identity_raises_already_exists() -> None:
    repository = FakeReviewRepository()
    identity = _identity()
    repository.add(_review(identity))

    with pytest.raises(AggregateAlreadyExists):
        repository.add(_review(identity))


def test_add_duplicate_governance_id_raises_already_exists() -> None:
    repository = FakeReviewRepository()
    repository.add(_review(_identity("REVIEW-0002")))

    colliding_identity = DomainIdentity(
        governance_id=ReviewId("REVIEW-0002"), runtime_id=RuntimeIdentifier(str(uuid.uuid4()))
    )
    with pytest.raises(AggregateAlreadyExists):
        repository.add(_review(colliding_identity))


def test_add_duplicate_runtime_id_raises_already_exists() -> None:
    repository = FakeReviewRepository()
    shared_runtime_id = RuntimeIdentifier(str(uuid.uuid4()))
    repository.add(
        _review(DomainIdentity(governance_id=ReviewId("REVIEW-0003"), runtime_id=shared_runtime_id))
    )

    colliding_identity = DomainIdentity(
        governance_id=ReviewId("REVIEW-0004"), runtime_id=shared_runtime_id
    )
    with pytest.raises(AggregateAlreadyExists):
        repository.add(_review(colliding_identity))


def test_get_after_add_returns_loaded_aggregate_with_persisted_version() -> None:
    repository = FakeReviewRepository()
    identity = _identity()
    review = _review(identity)
    repository.add(review)

    loaded = repository.get(identity)

    assert loaded.aggregate is review
    assert loaded.persisted_version == AggregateVersion.initial()


def test_loaded_persisted_version_does_not_change_when_aggregate_mutates() -> None:
    repository = FakeReviewRepository()
    identity = _identity()
    review = _review(identity)
    repository.add(review)

    loaded = repository.get(identity)
    token_before_mutation = loaded.persisted_version

    review.start(actor="tester", occurred_at=OCCURRED_AT)

    assert loaded.persisted_version == token_before_mutation
    assert loaded.persisted_version != review.version


def test_loaded_aggregate_is_immutable() -> None:
    repository = FakeReviewRepository()
    identity = _identity()
    review = _review(identity)
    repository.add(review)
    loaded = repository.get(identity)

    with pytest.raises(AttributeError):
        loaded.aggregate = review  # type: ignore[misc]
    with pytest.raises(AttributeError):
        loaded.persisted_version = AggregateVersion.initial()  # type: ignore[misc]


def test_save_on_missing_persisted_state_raises_aggregate_not_found() -> None:
    repository = FakeReviewRepository()
    review = _review()

    with pytest.raises(AggregateNotFound):
        repository.save(review, expected_persisted_version=review.version)


def test_save_after_mutation_with_correct_expected_version_returns_updated() -> None:
    repository = FakeReviewRepository()
    identity = _identity()
    review = _review(identity)
    repository.add(review)
    loaded = repository.get(identity)

    review.start(actor="tester", occurred_at=OCCURRED_AT)
    result = repository.save(review, expected_persisted_version=loaded.persisted_version)

    assert result.operation is SaveOperation.UPDATED
    assert result.persisted_version == review.version


def test_save_stale_expected_version_raises_conflict_with_facts() -> None:
    repository = FakeReviewRepository()
    identity = _identity()
    review = _review(identity)
    repository.add(review)
    stale_version = review.version

    review.start(actor="tester", occurred_at=OCCURRED_AT)
    repository.save(review, expected_persisted_version=stale_version)
    review.add_finding(text="finding one")

    with pytest.raises(OptimisticConcurrencyConflict) as excinfo:
        repository.save(review, expected_persisted_version=stale_version)

    assert excinfo.value.expected_persisted_version == stale_version
    assert excinfo.value.aggregate_current_version == review.version
    assert excinfo.value.actual_persisted_version is not None
    assert excinfo.value.actual_persisted_version != stale_version


def test_save_unchanged_returns_unchanged() -> None:
    repository = FakeReviewRepository()
    identity = _identity()
    review = _review(identity)
    repository.add(review)
    loaded = repository.get(identity)

    result = repository.save(review, expected_persisted_version=loaded.persisted_version)

    assert result.operation is SaveOperation.UNCHANGED
    assert result.persisted_version == review.version


def test_repeated_save_requires_latest_expected_version() -> None:
    repository = FakeReviewRepository()
    identity = _identity()
    review = _review(identity)
    repository.add(review)
    first_expected_version = review.version

    review.start(actor="tester", occurred_at=OCCURRED_AT)
    first_result = repository.save(review, expected_persisted_version=first_expected_version)

    review.add_finding(text="finding one")
    second_result = repository.save(
        review, expected_persisted_version=first_result.persisted_version
    )

    assert second_result.operation is SaveOperation.UPDATED
    assert second_result.persisted_version == review.version
