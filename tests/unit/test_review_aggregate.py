from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime

import pytest

from empirical_platform.identifiers import (
    DomainIdentity,
    EvidencePackageId,
    ReviewId,
    RunId,
)
from empirical_platform.review import (
    Review,
    ReviewDisposition,
    ReviewerReference,
    ReviewFinding,
    ReviewLifecycleState,
    ReviewTargetReference,
)
from empirical_platform.shared.domain import AggregateVersion, TransitionSequence
from empirical_platform.shared.identifiers import RuntimeIdentifier

OCCURRED_AT = datetime(2026, 7, 18, tzinfo=UTC)


def _identity(value: str = "REVIEW-0001") -> DomainIdentity[ReviewId]:
    return DomainIdentity(
        governance_id=ReviewId(value),
        runtime_id=RuntimeIdentifier("123e4567-e89b-42d3-a456-426614174001"),
    )


def _target(value: str = "EVID-0001") -> ReviewTargetReference:
    return ReviewTargetReference(EvidencePackageId(value))


def _reviewer(value: str = "reviewer-001") -> ReviewerReference:
    return ReviewerReference(value)


def _review() -> Review:
    return Review(identity=_identity(), target=_target(), reviewer=_reviewer())


def _in_progress_review() -> Review:
    review = _review()
    review.start(actor="Reviewer", occurred_at=OCCURRED_AT)
    return review


def _review_with_finding() -> Review:
    review = _in_progress_review()
    review.add_finding(text="Evidence package is internally consistent.")
    return review


def _snapshot(review: Review) -> tuple[object, ...]:
    return (
        review.identity,
        review.target,
        review.reviewer,
        review.state,
        review.version,
        review.next_transition_sequence,
        review.transition_history,
        review.findings,
        review.disposition,
        review.final_disposition_rationale,
        review.cancellation_reason,
    )


def test_construction_sets_assigned_identity_target_reviewer_and_empty_content() -> None:
    identity = _identity()
    target = _target()
    reviewer = _reviewer()

    review = Review(identity=identity, target=target, reviewer=reviewer)

    assert review.identity == identity
    assert review.target == target
    assert review.target.target_kind == "EVIDENCE_PACKAGE"
    assert review.reviewer == reviewer
    assert review.state is ReviewLifecycleState.ASSIGNED
    assert review.version == AggregateVersion.initial()
    assert review.next_transition_sequence == TransitionSequence.initial()
    assert review.transition_history == ()
    assert review.findings == ()
    assert review.disposition is None
    assert review.final_disposition_rationale is None
    assert review.cancellation_reason is None


def test_construction_rejects_invalid_identity_target_and_reviewer() -> None:
    with pytest.raises(TypeError, match="DomainIdentity"):
        Review(  # type: ignore[arg-type]
            identity=ReviewId("REVIEW-0001"),
            target=_target(),
            reviewer=_reviewer(),
        )
    with pytest.raises(TypeError, match="ReviewId"):
        Review(
            identity=DomainIdentity(
                governance_id=RunId("RUN-0001"),
                runtime_id=RuntimeIdentifier("123e4567-e89b-42d3-a456-426614174001"),
            ),
            target=_target(),
            reviewer=_reviewer(),
        )
    with pytest.raises(TypeError, match="ReviewTargetReference"):
        Review(identity=_identity(), target=EvidencePackageId("EVID-0001"), reviewer=_reviewer())  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="ReviewerReference"):
        Review(identity=_identity(), target=_target(), reviewer="reviewer-001")  # type: ignore[arg-type]


def test_target_reference_is_evidence_package_only_and_immutable() -> None:
    target = ReviewTargetReference(EvidencePackageId("EVID-0001"))

    assert target.evidence_package_id == EvidencePackageId("EVID-0001")
    assert target.target_kind == "EVIDENCE_PACKAGE"
    assert not hasattr(target, "run_id")
    with pytest.raises(TypeError, match="EvidencePackageId"):
        ReviewTargetReference(RunId("RUN-0001"))  # type: ignore[arg-type]
    with pytest.raises(FrozenInstanceError):
        target.evidence_package_id = EvidencePackageId("EVID-0002")  # type: ignore[misc]


def test_reviewer_reference_is_opaque_data_only_and_immutable() -> None:
    reviewer = ReviewerReference("reviewer-001")

    assert str(reviewer) == "reviewer-001"
    assert reviewer == ReviewerReference("reviewer-001")
    assert not hasattr(reviewer, "authorize")
    assert not hasattr(reviewer, "is_independent")
    with pytest.raises(TypeError, match="string"):
        ReviewerReference(123)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="non-empty"):
        ReviewerReference(" ")
    with pytest.raises(FrozenInstanceError):
        reviewer.value = "changed"  # type: ignore[misc]


def test_start_records_assigned_to_in_progress_transition() -> None:
    review = _review()

    review.start(
        actor="Reviewer",
        occurred_at=OCCURRED_AT,
        correlation_id="corr-1",
        reason="begin review",
    )

    assert review.state is ReviewLifecycleState.IN_PROGRESS
    assert review.version == AggregateVersion(1)
    assert review.next_transition_sequence == TransitionSequence(2)
    assert len(review.transition_history) == 1
    record = review.transition_history[0]
    assert record.from_state == "ASSIGNED"
    assert record.to_state == "IN_PROGRESS"
    assert record.version == AggregateVersion(1)
    assert record.sequence == TransitionSequence(1)
    assert record.actor == "Reviewer"
    assert record.occurred_at == OCCURRED_AT
    assert record.identity_reference == review.identity
    assert record.correlation_id == "corr-1"
    assert record.reason == "begin review"


def test_start_rejection_paths_are_atomic() -> None:
    review = _in_progress_review()
    before = _snapshot(review)

    with pytest.raises(ValueError, match="IN_PROGRESS"):
        review.start(actor="Reviewer", occurred_at=OCCURRED_AT)

    assert _snapshot(review) == before

    assigned = _review()
    before_timestamp = _snapshot(assigned)
    with pytest.raises(TypeError, match="datetime"):
        assigned.start(actor="Reviewer", occurred_at="now")  # type: ignore[arg-type]
    assert _snapshot(assigned) == before_timestamp

    before_actor = _snapshot(assigned)
    with pytest.raises(ValueError, match="actor"):
        assigned.start(actor=" ", occurred_at=OCCURRED_AT)
    assert _snapshot(assigned) == before_actor


def test_finding_validates_fields_and_is_immutable() -> None:
    finding = ReviewFinding(
        sequence=1,
        text="Finding text.",
        rationale="Rationale.",
        evidence_references=("artifact://opaque/reference",),
    )

    assert finding.sequence == 1
    assert finding.text == "Finding text."
    assert finding.rationale == "Rationale."
    assert finding.evidence_references == ("artifact://opaque/reference",)
    with pytest.raises(TypeError, match="integer"):
        ReviewFinding(sequence=True, text="Finding text.")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="positive"):
        ReviewFinding(sequence=0, text="Finding text.")
    with pytest.raises(TypeError, match="finding text"):
        ReviewFinding(sequence=1, text=123)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="finding text"):
        ReviewFinding(sequence=1, text=" ")
    with pytest.raises(ValueError, match="finding rationale"):
        ReviewFinding(sequence=1, text="Finding text.", rationale=" ")
    with pytest.raises(TypeError, match="tuple"):
        ReviewFinding(sequence=1, text="Finding text.", evidence_references=["ref"])  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="evidence reference"):
        ReviewFinding(sequence=1, text="Finding text.", evidence_references=(" ",))
    with pytest.raises(FrozenInstanceError):
        finding.text = "changed"  # type: ignore[misc]


def test_add_finding_only_while_in_progress_and_increments_content_version() -> None:
    review = _in_progress_review()

    review.add_finding(
        text="First finding.",
        rationale="Because the evidence was sealed.",
        evidence_references=("artifact://opaque/1",),
    )
    review.add_finding(text="Second finding.")

    assert review.version == AggregateVersion(3)
    assert review.next_transition_sequence == TransitionSequence(2)
    assert len(review.transition_history) == 1
    assert [finding.sequence for finding in review.findings] == [1, 2]
    assert [finding.text for finding in review.findings] == [
        "First finding.",
        "Second finding.",
    ]
    with pytest.raises(AttributeError):
        review.findings.append(ReviewFinding(sequence=3, text="not possible"))  # type: ignore[attr-defined]


def test_add_finding_rejection_paths_are_atomic_after_prior_success() -> None:
    review = _in_progress_review()
    review.add_finding(text="First finding.")

    for kwargs, error in (
        ({"text": " "}, "finding text"),
        ({"text": 123}, "finding text"),
        ({"text": "Second finding.", "rationale": " "}, "finding rationale"),
        (
            {"text": "Second finding.", "evidence_references": (" ",)},
            "evidence reference",
        ),
        (
            {"text": "Second finding.", "evidence_references": ["ref"]},
            "tuple",
        ),
    ):
        before = _snapshot(review)
        with pytest.raises((TypeError, ValueError), match=error):
            review.add_finding(**kwargs)  # type: ignore[arg-type]
        assert _snapshot(review) == before

    assigned = _review()
    before_assigned = _snapshot(assigned)
    with pytest.raises(ValueError, match="IN_PROGRESS"):
        assigned.add_finding(text="Finding text.")
    assert _snapshot(assigned) == before_assigned


def test_complete_requires_in_progress_findings_disposition_and_rationale() -> None:
    assigned = _review()
    before_assigned = _snapshot(assigned)
    with pytest.raises(ValueError, match="IN_PROGRESS"):
        assigned.complete(
            disposition=ReviewDisposition.ACCEPTED,
            final_disposition_rationale="Final rationale.",
            actor="Reviewer",
            occurred_at=OCCURRED_AT,
        )
    assert _snapshot(assigned) == before_assigned

    no_findings = _in_progress_review()
    before_no_findings = _snapshot(no_findings)
    with pytest.raises(ValueError, match="at least one finding"):
        no_findings.complete(
            disposition=ReviewDisposition.ACCEPTED,
            final_disposition_rationale="Final rationale.",
            actor="Reviewer",
            occurred_at=OCCURRED_AT,
        )
    assert _snapshot(no_findings) == before_no_findings

    invalid_disposition = _review_with_finding()
    before_invalid_disposition = _snapshot(invalid_disposition)
    with pytest.raises(TypeError, match="ReviewDisposition"):
        invalid_disposition.complete(
            disposition="ACCEPTED",  # type: ignore[arg-type]
            final_disposition_rationale="Final rationale.",
            actor="Reviewer",
            occurred_at=OCCURRED_AT,
        )
    assert _snapshot(invalid_disposition) == before_invalid_disposition

    blank_rationale = _review_with_finding()
    before_blank_rationale = _snapshot(blank_rationale)
    with pytest.raises(ValueError, match="final disposition rationale"):
        blank_rationale.complete(
            disposition=ReviewDisposition.ACCEPTED,
            final_disposition_rationale=" ",
            actor="Reviewer",
            occurred_at=OCCURRED_AT,
        )
    assert _snapshot(blank_rationale) == before_blank_rationale


def test_complete_records_disposition_once_and_preserves_findings() -> None:
    review = _review_with_finding()
    findings = review.findings

    review.complete(
        disposition=ReviewDisposition.CHANGES_REQUESTED,
        final_disposition_rationale="Changes are required before acceptance.",
        actor="Reviewer",
        occurred_at=OCCURRED_AT,
        correlation_id="corr-2",
    )

    assert review.state is ReviewLifecycleState.COMPLETED
    assert review.version == AggregateVersion(3)
    assert review.next_transition_sequence == TransitionSequence(3)
    assert review.findings == findings
    assert review.disposition is ReviewDisposition.CHANGES_REQUESTED
    assert review.final_disposition_rationale == "Changes are required before acceptance."
    assert review.cancellation_reason is None
    assert len(review.transition_history) == 2
    record = review.transition_history[1]
    assert record.from_state == "IN_PROGRESS"
    assert record.to_state == "COMPLETED"
    assert record.version == AggregateVersion(3)
    assert record.sequence == TransitionSequence(2)
    assert record.reason == "Changes are required before acceptance."
    assert record.correlation_id == "corr-2"

    before_repeated = _snapshot(review)
    with pytest.raises(ValueError, match="COMPLETED"):
        review.complete(
            disposition=ReviewDisposition.ACCEPTED,
            final_disposition_rationale="replacement",
            actor="Reviewer",
            occurred_at=OCCURRED_AT,
        )
    assert _snapshot(review) == before_repeated


def test_cancellation_from_assigned_and_in_progress_records_reason_without_disposition() -> None:
    assigned = _review()
    assigned.cancel(reason="assignment withdrawn", actor="Coordinator", occurred_at=OCCURRED_AT)

    assert assigned.state is ReviewLifecycleState.CANCELLED
    assert assigned.version == AggregateVersion(1)
    assert assigned.next_transition_sequence == TransitionSequence(2)
    assert assigned.cancellation_reason == "assignment withdrawn"
    assert assigned.disposition is None
    assert len(assigned.transition_history) == 1
    assert assigned.transition_history[0].from_state == "ASSIGNED"
    assert assigned.transition_history[0].to_state == "CANCELLED"

    in_progress = _review_with_finding()
    findings = in_progress.findings
    in_progress.cancel(
        reason="governed cancellation",
        actor="Coordinator",
        occurred_at=OCCURRED_AT,
        correlation_id="corr-3",
    )

    assert in_progress.state is ReviewLifecycleState.CANCELLED
    assert in_progress.version == AggregateVersion(3)
    assert in_progress.next_transition_sequence == TransitionSequence(3)
    assert in_progress.findings == findings
    assert in_progress.disposition is None
    assert in_progress.final_disposition_rationale is None
    assert in_progress.cancellation_reason == "governed cancellation"
    assert len(in_progress.transition_history) == 2
    assert in_progress.transition_history[1].from_state == "IN_PROGRESS"
    assert in_progress.transition_history[1].to_state == "CANCELLED"
    assert in_progress.transition_history[1].reason == "governed cancellation"


def test_cancellation_rejection_paths_are_atomic() -> None:
    review = _review_with_finding()

    for kwargs, error in (
        ({"reason": " ", "actor": "Coordinator", "occurred_at": OCCURRED_AT}, "reason"),
        ({"reason": 123, "actor": "Coordinator", "occurred_at": OCCURRED_AT}, "reason"),
        ({"reason": "cancel", "actor": " ", "occurred_at": OCCURRED_AT}, "actor"),
        ({"reason": "cancel", "actor": "Coordinator", "occurred_at": "now"}, "datetime"),
    ):
        before = _snapshot(review)
        with pytest.raises((TypeError, ValueError), match=error):
            review.cancel(**kwargs)  # type: ignore[arg-type]
        assert _snapshot(review) == before

    review.cancel(reason="cancel", actor="Coordinator", occurred_at=OCCURRED_AT)
    before_repeated = _snapshot(review)
    with pytest.raises(ValueError, match="CANCELLED"):
        review.cancel(reason="again", actor="Coordinator", occurred_at=OCCURRED_AT)
    assert _snapshot(review) == before_repeated


def test_terminal_immutability_blocks_findings_lifecycle_changes_and_reopen() -> None:
    completed = _review_with_finding()
    completed.complete(
        disposition=ReviewDisposition.ACCEPTED,
        final_disposition_rationale="Accepted.",
        actor="Reviewer",
        occurred_at=OCCURRED_AT,
    )
    before_completed = _snapshot(completed)
    with pytest.raises(ValueError, match="IN_PROGRESS"):
        completed.add_finding(text="late finding")
    with pytest.raises(ValueError, match="COMPLETED"):
        completed.start(actor="Reviewer", occurred_at=OCCURRED_AT)
    with pytest.raises(ValueError, match="COMPLETED"):
        completed.cancel(reason="late cancel", actor="Coordinator", occurred_at=OCCURRED_AT)
    assert _snapshot(completed) == before_completed

    cancelled = _review_with_finding()
    cancelled.cancel(reason="cancel", actor="Coordinator", occurred_at=OCCURRED_AT)
    before_cancelled = _snapshot(cancelled)
    with pytest.raises(ValueError, match="IN_PROGRESS"):
        cancelled.add_finding(text="late finding")
    with pytest.raises(ValueError, match="CANCELLED"):
        cancelled.start(actor="Reviewer", occurred_at=OCCURRED_AT)
    assert _snapshot(cancelled) == before_cancelled
    assert not hasattr(cancelled, "reopen")
    assert not hasattr(completed, "replace_disposition")


def test_mixed_completion_sequence_has_exact_cumulative_version_sequence_and_history() -> None:
    review = _review()

    review.start(actor="Reviewer", occurred_at=OCCURRED_AT)
    review.add_finding(text="First finding.")
    review.add_finding(text="Second finding.", evidence_references=("artifact://opaque/2",))
    review.complete(
        disposition=ReviewDisposition.INCONCLUSIVE,
        final_disposition_rationale="The available evidence is inconclusive.",
        actor="Reviewer",
        occurred_at=OCCURRED_AT,
    )

    assert review.state is ReviewLifecycleState.COMPLETED
    assert review.version == AggregateVersion(4)
    assert review.next_transition_sequence == TransitionSequence(3)
    assert [finding.sequence for finding in review.findings] == [1, 2]
    assert [record.to_state for record in review.transition_history] == [
        "IN_PROGRESS",
        "COMPLETED",
    ]
    assert [record.sequence for record in review.transition_history] == [
        TransitionSequence(1),
        TransitionSequence(2),
    ]


def test_mixed_cancellation_sequence_has_exact_cumulative_version_sequence_and_history() -> None:
    review = _review()

    review.start(actor="Reviewer", occurred_at=OCCURRED_AT)
    review.add_finding(text="Finding before cancellation.")
    review.cancel(reason="scope withdrawn", actor="Coordinator", occurred_at=OCCURRED_AT)

    assert review.state is ReviewLifecycleState.CANCELLED
    assert review.version == AggregateVersion(3)
    assert review.next_transition_sequence == TransitionSequence(3)
    assert [finding.sequence for finding in review.findings] == [1]
    assert review.disposition is None
    assert review.final_disposition_rationale is None
    assert review.cancellation_reason == "scope withdrawn"
    assert [record.to_state for record in review.transition_history] == [
        "IN_PROGRESS",
        "CANCELLED",
    ]


def test_review_has_no_deferred_infrastructure_or_cross_aggregate_surface() -> None:
    review = _review_with_finding()

    assert not hasattr(review, "save")
    assert not hasattr(review, "load")
    assert not hasattr(review, "repository")
    assert not hasattr(review, "session")
    assert not hasattr(review, "database")
    assert not hasattr(review, "bucket")
    assert not hasattr(review, "object_key")
    assert not hasattr(review, "dispatch")
    assert not hasattr(review, "audit")
    assert not hasattr(review, "decision_candidate")
    assert not hasattr(review, "validate_target")
    assert not hasattr(review, "load_target")
    assert not hasattr(review, "authorize")
    assert not hasattr(review, "is_independent")
