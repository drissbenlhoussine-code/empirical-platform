"""MILESTONE-021 contract tests for ReviewMapper, using an in-memory fake."""

from __future__ import annotations

import uuid
from dataclasses import FrozenInstanceError
from datetime import UTC, datetime

import pytest
from tests.contract._mapper_fakes import FakeReviewMapper

from empirical_platform.identifiers.pairs import DomainIdentity
from empirical_platform.identifiers.types import EvidencePackageId, ReviewId
from empirical_platform.review._reconstruction import _reconstruct_review
from empirical_platform.review.aggregate import Review, ReviewerReference, ReviewTargetReference
from empirical_platform.review.lifecycle import ReviewDisposition
from empirical_platform.shared.contracts.mapping import MapperError, MapperErrorCategory
from empirical_platform.shared.identifiers import RuntimeIdentifier

OCCURRED_AT = datetime(2026, 7, 26, tzinfo=UTC)


def _identity() -> DomainIdentity[ReviewId]:
    return DomainIdentity(
        governance_id=ReviewId("REVIEW-0001"),
        runtime_id=RuntimeIdentifier(str(uuid.uuid4())),
    )


def _review() -> Review:
    return Review(
        identity=_identity(),
        target=ReviewTargetReference(EvidencePackageId("EVID-0001")),
        reviewer=ReviewerReference("reviewer-1"),
    )


def test_round_trip_preserves_identity_and_initial_state() -> None:
    mapper = FakeReviewMapper()
    review = _review()

    record = mapper.to_durable_record(review)
    state = mapper.from_durable_record(record)
    restored = _reconstruct_review(state)

    assert restored.identity == review.identity
    assert restored.target == review.target
    assert str(restored.reviewer) == str(review.reviewer)
    assert restored.version == review.version
    assert restored.disposition is None
    assert restored.final_disposition_rationale is None
    assert restored.cancellation_reason is None


def test_round_trip_preserves_completed_findings_and_disposition() -> None:
    mapper = FakeReviewMapper()
    review = _review()
    review.start(actor="tester", occurred_at=OCCURRED_AT)
    review.add_finding(text="finding one", rationale="because", evidence_references=("e1",))
    review.add_finding(text="finding two")
    review.complete(
        disposition=ReviewDisposition.ACCEPTED,
        final_disposition_rationale="all good",
        actor="tester",
        occurred_at=OCCURRED_AT,
    )

    record = mapper.to_durable_record(review)
    state = mapper.from_durable_record(record)
    restored = _reconstruct_review(state)

    assert [f.text for f in restored.findings] == ["finding one", "finding two"]
    assert restored.findings[0].rationale == "because"
    assert restored.findings[0].evidence_references == ("e1",)
    assert restored.findings[1].rationale is None
    assert restored.disposition is ReviewDisposition.ACCEPTED
    assert restored.final_disposition_rationale == "all good"
    assert restored.cancellation_reason is None
    assert restored.version == review.version


def test_round_trip_preserves_cancellation() -> None:
    mapper = FakeReviewMapper()
    review = _review()
    review.cancel(reason="no longer needed", actor="tester", occurred_at=OCCURRED_AT)

    record = mapper.to_durable_record(review)
    state = mapper.from_durable_record(record)
    restored = _reconstruct_review(state)

    assert restored.cancellation_reason == "no longer needed"
    assert restored.disposition is None


def test_durable_record_is_immutable() -> None:
    mapper = FakeReviewMapper()
    record = mapper.to_durable_record(_review())

    with pytest.raises(FrozenInstanceError):
        record.lifecycle_state = "changed"  # type: ignore[misc]


def test_malformed_lifecycle_state_raises_mapper_error() -> None:
    mapper = FakeReviewMapper()
    record = mapper.to_durable_record(_review())
    corrupted = type(record)(
        identity=record.identity,
        target_evidence_package_id=record.target_evidence_package_id,
        reviewer_reference=record.reviewer_reference,
        lifecycle_state="NOT_A_REAL_STATE",
        findings=record.findings,
        disposition=record.disposition,
        final_disposition_rationale=record.final_disposition_rationale,
        cancellation_reason=record.cancellation_reason,
        version=record.version,
        next_transition_sequence=record.next_transition_sequence,
        transition_history=record.transition_history,
    )

    with pytest.raises(MapperError) as excinfo:
        mapper.from_durable_record(corrupted)

    assert excinfo.value.category is MapperErrorCategory.INVALID_DURABLE_RECORD
    assert excinfo.value.aggregate_kind == "Review"


def test_malformed_disposition_raises_mapper_error() -> None:
    mapper = FakeReviewMapper()
    review = _review()
    review.start(actor="tester", occurred_at=OCCURRED_AT)
    review.add_finding(text="finding one")
    review.complete(
        disposition=ReviewDisposition.ACCEPTED,
        final_disposition_rationale="all good",
        actor="tester",
        occurred_at=OCCURRED_AT,
    )
    record = mapper.to_durable_record(review)
    corrupted = type(record)(
        identity=record.identity,
        target_evidence_package_id=record.target_evidence_package_id,
        reviewer_reference=record.reviewer_reference,
        lifecycle_state=record.lifecycle_state,
        findings=record.findings,
        disposition="NOT_A_REAL_DISPOSITION",
        final_disposition_rationale=record.final_disposition_rationale,
        cancellation_reason=record.cancellation_reason,
        version=record.version,
        next_transition_sequence=record.next_transition_sequence,
        transition_history=record.transition_history,
    )

    with pytest.raises(MapperError) as excinfo:
        mapper.from_durable_record(corrupted)

    assert excinfo.value.category is MapperErrorCategory.INVALID_DURABLE_RECORD
    assert excinfo.value.field == "disposition"
