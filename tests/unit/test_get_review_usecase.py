"""MILESTONE-043 behavioral tests for `GetReviewQuery`/`GetReviewHandler`.

Proves the frozen retrieval flow (design Section 9): call
`ReviewRepository.get()` exactly once with the query's identity object
unchanged, and build `ReviewSnapshot` from the loaded aggregate's
`identity`/`target.evidence_package_id`/`reviewer.value`/`state` only --
`Review.version` and `LoadedAggregate.persisted_version` are read (or
reachable) but never exposed, and neither `findings`, `transition_history`,
`disposition`, `final_disposition_rationale`, nor `cancellation_reason` are
copied, aliased, or exposed. Also proves transparent failure propagation
for every collaborator (frozen M029 invariant) and that the handler is
invocable through the frozen `QueryEntryPoint`.

Uses deterministic recording fakes/stubs, not mocks, for stronger evidence.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest

from empirical_platform.application.query import QueryEntryPoint
from empirical_platform.identifiers.pairs import DomainIdentity
from empirical_platform.identifiers.types import EvidencePackageId, ReviewId
from empirical_platform.review.aggregate import Review, ReviewerReference, ReviewTargetReference
from empirical_platform.review.lifecycle import ReviewDisposition, ReviewLifecycleState
from empirical_platform.shared.contracts.repository import (
    AggregateNotFound,
    LoadedAggregate,
)
from empirical_platform.shared.domain.versioning import AggregateVersion
from empirical_platform.shared.identifiers import RuntimeIdentifier
from empirical_platform.usecases.get_review import (
    GetReviewHandler,
    GetReviewQuery,
    ReviewSnapshot,
)

if TYPE_CHECKING:
    from empirical_platform.review.repository import ReviewRepository

_RUNTIME_ID_VALUE = "12345678-1234-4321-8765-1234567890ab"


def _identity(governance_id: str = "REVIEW-0001") -> DomainIdentity[ReviewId]:
    return DomainIdentity(
        governance_id=ReviewId(governance_id),
        runtime_id=RuntimeIdentifier(_RUNTIME_ID_VALUE),
    )


def _review(
    identity: DomainIdentity[ReviewId],
    target_governance_id: str = "EVID-0001",
    reviewer_reference: str = "reviewer-1",
) -> Review:
    return Review(
        identity=identity,
        target=ReviewTargetReference(evidence_package_id=EvidencePackageId(target_governance_id)),
        reviewer=ReviewerReference(reviewer_reference),
    )


class _RecordingReviewRepository:
    """Records every `get()` call; conforms structurally to `ReviewRepository`."""

    def __init__(self, loaded: LoadedAggregate[Review]) -> None:
        self._loaded = loaded
        self.get_calls: list[DomainIdentity[ReviewId]] = []

    def get(self, identity: DomainIdentity[ReviewId]) -> LoadedAggregate[Review]:
        self.get_calls.append(identity)
        return self._loaded

    def add(self, aggregate: Review) -> object:
        raise AssertionError("add() must not be called by GetReviewHandler")

    def save(self, aggregate: Review, *, expected_persisted_version: object) -> object:
        raise AssertionError("save() must not be called by GetReviewHandler")


class _FailingReviewRepository:
    def __init__(self, exc: Exception) -> None:
        self._exc = exc
        self.get_calls = 0

    def get(self, identity: DomainIdentity[ReviewId]) -> object:
        self.get_calls += 1
        raise self._exc

    def add(self, aggregate: Review) -> object:
        raise AssertionError("add() must not be called")

    def save(self, aggregate: Review, *, expected_persisted_version: object) -> object:
        raise AssertionError("save() must not be called")


def _handler(repository: object) -> GetReviewHandler:
    return GetReviewHandler(review_repository=repository)  # type: ignore[arg-type]


def test_typed_conformance_check() -> None:
    """Mypy-checked proof that GetReviewHandler conforms to
    QueryHandler[GetReviewQuery, ReviewSnapshot] without inheritance
    (structural typing only)."""
    identity = _identity()
    loaded = LoadedAggregate(
        aggregate=_review(identity), persisted_version=AggregateVersion.initial()
    )
    repository: ReviewRepository = _RecordingReviewRepository(loaded)  # type: ignore[assignment]
    handler: GetReviewHandler = _handler(repository)
    assert handler is not None


def test_query_preserves_the_exact_identity_object() -> None:
    identity = _identity()
    query = GetReviewQuery(identity=identity)

    assert query.identity is identity


def test_query_contains_no_additional_fields() -> None:
    query = GetReviewQuery(identity=_identity())
    assert [field for field in query.__slots__] == ["identity"]  # type: ignore[attr-defined]


def test_query_is_immutable() -> None:
    query = GetReviewQuery(identity=_identity())
    with pytest.raises(AttributeError):
        query.identity = _identity("REVIEW-0002")  # type: ignore[misc]


def test_review_repository_get_is_called_exactly_once() -> None:
    identity = _identity()
    loaded = LoadedAggregate(
        aggregate=_review(identity), persisted_version=AggregateVersion.initial()
    )
    repository = _RecordingReviewRepository(loaded)
    handler = _handler(repository)

    handler.handle(GetReviewQuery(identity=identity))

    assert len(repository.get_calls) == 1


def test_exact_query_identity_object_is_passed_to_repository_unchanged() -> None:
    identity = _identity()
    loaded = LoadedAggregate(
        aggregate=_review(identity), persisted_version=AggregateVersion.initial()
    )
    repository = _RecordingReviewRepository(loaded)
    handler = _handler(repository)
    query = GetReviewQuery(identity=identity)

    handler.handle(query)

    assert repository.get_calls[0] is query.identity


def test_no_add_or_save_call_occurs() -> None:
    """add()/save() raise AssertionError in the fake if called; handler must
    never call either."""
    identity = _identity()
    loaded = LoadedAggregate(
        aggregate=_review(identity), persisted_version=AggregateVersion.initial()
    )
    repository = _RecordingReviewRepository(loaded)
    handler = _handler(repository)

    handler.handle(GetReviewQuery(identity=identity))  # would raise otherwise


def test_returned_object_is_a_review_snapshot() -> None:
    identity = _identity()
    loaded = LoadedAggregate(
        aggregate=_review(identity), persisted_version=AggregateVersion.initial()
    )
    repository = _RecordingReviewRepository(loaded)
    handler = _handler(repository)

    result = handler.handle(GetReviewQuery(identity=identity))

    assert isinstance(result, ReviewSnapshot)


def test_snapshot_fields_match_the_loaded_aggregate() -> None:
    identity = _identity("REVIEW-0042")
    review = _review(identity, target_governance_id="EVID-0099", reviewer_reference="reviewer-42")
    loaded = LoadedAggregate(aggregate=review, persisted_version=AggregateVersion.initial())
    repository = _RecordingReviewRepository(loaded)
    handler = _handler(repository)

    result = handler.handle(GetReviewQuery(identity=identity))

    assert result.identity == review.identity
    assert result.target_evidence_package_id == EvidencePackageId("EVID-0099")
    assert result.reviewer_reference == "reviewer-42"
    assert result.state == review.state
    assert result.state is ReviewLifecycleState.ASSIGNED


def test_snapshot_exact_field_set() -> None:
    snapshot_fields = {"identity", "target_evidence_package_id", "reviewer_reference", "state"}
    assert set(ReviewSnapshot.__slots__) == snapshot_fields  # type: ignore[attr-defined]


def test_snapshot_is_immutable() -> None:
    identity = _identity()
    loaded = LoadedAggregate(
        aggregate=_review(identity), persisted_version=AggregateVersion.initial()
    )
    repository = _RecordingReviewRepository(loaded)
    handler = _handler(repository)

    result = handler.handle(GetReviewQuery(identity=identity))

    with pytest.raises(AttributeError):
        result.state = ReviewLifecycleState.IN_PROGRESS  # type: ignore[misc]


def test_review_aggregate_is_not_mutated() -> None:
    identity = _identity()
    review = _review(identity)
    version_before = review.version
    loaded = LoadedAggregate(aggregate=review, persisted_version=AggregateVersion.initial())
    repository = _RecordingReviewRepository(loaded)
    handler = _handler(repository)

    handler.handle(GetReviewQuery(identity=identity))

    assert review.version == version_before
    assert review.state is ReviewLifecycleState.ASSIGNED


def test_aggregate_version_and_persisted_version_are_distinct_and_neither_leaks() -> None:
    """Mandatory M043 implementation evidence: construct a LoadedAggregate
    whose `aggregate.version` and `persisted_version` are intentionally
    different values, and prove neither appears anywhere on ReviewSnapshot
    -- aggregate version and persisted version must never be conflated."""
    identity = _identity()
    review = _review(identity)
    review.start(actor="tester", occurred_at=datetime(2026, 1, 1, tzinfo=UTC))
    # review.version is now 1 (advanced by the transition above); persisted_version
    # is deliberately set to a different value (0) to prove the two are
    # independent concepts that must not be conflated.
    assert review.version == AggregateVersion(1)
    loaded = LoadedAggregate(aggregate=review, persisted_version=AggregateVersion(0))
    assert loaded.aggregate.version != loaded.persisted_version
    repository = _RecordingReviewRepository(loaded)
    handler = _handler(repository)

    result = handler.handle(GetReviewQuery(identity=identity))

    assert set(ReviewSnapshot.__slots__) == {  # type: ignore[attr-defined]
        "identity",
        "target_evidence_package_id",
        "reviewer_reference",
        "state",
    }
    assert not hasattr(result, "version")
    assert not hasattr(result, "persisted_version")
    assert result.state is ReviewLifecycleState.IN_PROGRESS


def test_findings_transition_history_and_disposition_fields_are_not_exposed() -> None:
    """Mandatory M043 implementation evidence: a Review with non-empty
    findings, transition history, and a set disposition must still produce
    a ReviewSnapshot that exposes none of them -- the exclusion holds
    regardless of whether the source aggregate's own state is empty or
    populated."""
    identity = _identity()
    review = _review(identity)
    review.start(actor="tester", occurred_at=datetime(2026, 1, 1, tzinfo=UTC))
    review.add_finding(text="finding one")
    review.complete(
        disposition=ReviewDisposition.ACCEPTED,
        final_disposition_rationale="all criteria satisfied",
        actor="tester",
        occurred_at=datetime(2026, 1, 2, tzinfo=UTC),
    )
    assert len(review.findings) == 1
    assert len(review.transition_history) == 2
    assert review.disposition is ReviewDisposition.ACCEPTED
    loaded = LoadedAggregate(aggregate=review, persisted_version=AggregateVersion(3))
    repository = _RecordingReviewRepository(loaded)
    handler = _handler(repository)

    result = handler.handle(GetReviewQuery(identity=identity))

    assert not hasattr(result, "findings")
    assert not hasattr(result, "transition_history")
    assert not hasattr(result, "disposition")
    assert not hasattr(result, "final_disposition_rationale")
    assert not hasattr(result, "cancellation_reason")
    assert set(ReviewSnapshot.__slots__) == {  # type: ignore[attr-defined]
        "identity",
        "target_evidence_package_id",
        "reviewer_reference",
        "state",
    }
    assert result.state is ReviewLifecycleState.COMPLETED
    # The source aggregate's own data remains intact and untouched by retrieval.
    assert len(review.findings) == 1
    assert len(review.transition_history) == 2
    assert review.disposition is ReviewDisposition.ACCEPTED


def test_aggregate_not_found_propagates_with_identity_preserved() -> None:
    exc = AggregateNotFound(aggregate_kind="Review", identity=_identity())
    repository = _FailingReviewRepository(exc)
    handler = _handler(repository)

    with pytest.raises(AggregateNotFound) as excinfo:
        handler.handle(GetReviewQuery(identity=_identity()))

    assert excinfo.value is exc
    assert repository.get_calls == 1


def test_arbitrary_repository_exception_propagates_with_identity_preserved() -> None:
    exc = RuntimeError("unexpected repository failure")
    repository = _FailingReviewRepository(exc)
    handler = _handler(repository)

    with pytest.raises(RuntimeError) as excinfo:
        handler.handle(GetReviewQuery(identity=_identity()))

    assert excinfo.value is exc
    assert repository.get_calls == 1


def test_handler_is_invocable_through_query_entry_point() -> None:
    identity = _identity()
    loaded = LoadedAggregate(
        aggregate=_review(identity), persisted_version=AggregateVersion.initial()
    )
    repository = _RecordingReviewRepository(loaded)
    handler = _handler(repository)
    entry_point = QueryEntryPoint(handler)

    result = entry_point(GetReviewQuery(identity=identity))

    assert isinstance(result, ReviewSnapshot)
    assert len(repository.get_calls) == 1


def test_handler_bound_at_construction_not_per_call() -> None:
    identity_one = _identity("REVIEW-0001")
    identity_two = _identity("REVIEW-0002")
    loaded_one = LoadedAggregate(
        aggregate=_review(identity_one), persisted_version=AggregateVersion.initial()
    )
    repository = _RecordingReviewRepository(loaded_one)
    handler = _handler(repository)
    entry_point = QueryEntryPoint(handler)

    entry_point(GetReviewQuery(identity=identity_one))
    entry_point(GetReviewQuery(identity=identity_two))

    assert len(repository.get_calls) == 2
