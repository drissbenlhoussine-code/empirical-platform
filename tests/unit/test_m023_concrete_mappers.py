"""MILESTONE-023 unit tests for the concrete, storage-agnostic mapper implementations.

Covers round-trip field fidelity (including nested child collections and
optional fields), transition-history/version/sequence preservation, ordering,
and malformed-durable-record error behavior for all four concrete mappers
(`ConcreteCampaignMapper`, `ConcreteRunMapper`, `ConcreteEvidencePackageMapper`,
`ConcreteReviewMapper`). These mappers perform pure in-memory data
transformation only: no SQL is issued and no persistence service is required
to construct or invoke them, which every test below demonstrates by never
importing or referencing any persistence/SQL module.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from empirical_platform.campaign._reconstruction import _reconstruct_campaign
from empirical_platform.campaign.aggregate import Campaign, CampaignScopeStatement
from empirical_platform.campaign.mapper import ConcreteCampaignMapper
from empirical_platform.datasets import DatasetManifest
from empirical_platform.evidence._reconstruction import _reconstruct_evidence_package
from empirical_platform.evidence.mapper import ConcreteEvidencePackageMapper
from empirical_platform.evidence.package import ArtifactReference, EvidencePackage
from empirical_platform.evidence.results import CriterionResult
from empirical_platform.identifiers.pairs import DomainIdentity
from empirical_platform.identifiers.types import (
    CampaignId,
    DatasetId,
    EvidencePackageId,
    ReviewId,
    RunId,
)
from empirical_platform.review._reconstruction import _reconstruct_review
from empirical_platform.review.aggregate import Review, ReviewerReference, ReviewTargetReference
from empirical_platform.review.lifecycle import ReviewDisposition
from empirical_platform.review.mapper import ConcreteReviewMapper
from empirical_platform.run._reconstruction import _reconstruct_run
from empirical_platform.run.aggregate import Run
from empirical_platform.run.mapper import ConcreteRunMapper
from empirical_platform.shared.contracts.mapping import MapperError, MapperErrorCategory
from empirical_platform.shared.identifiers import RuntimeIdentifier

OCCURRED_AT = datetime(2026, 7, 26, tzinfo=UTC)


def _runtime_id() -> RuntimeIdentifier:
    return RuntimeIdentifier(str(uuid.uuid4()))


# --- Campaign -----------------------------------------------------------------


def _campaign() -> Campaign:
    identity = DomainIdentity(governance_id=CampaignId("CAMP-0001"), runtime_id=_runtime_id())
    return Campaign(identity=identity, scope_statement=CampaignScopeStatement("initial scope"))


def test_campaign_round_trip_preserves_identity_and_initial_state() -> None:
    mapper = ConcreteCampaignMapper()
    campaign = _campaign()

    record = mapper.to_durable_record(campaign)
    state = mapper.from_durable_record(record)
    restored = _reconstruct_campaign(state)

    assert restored.identity == campaign.identity
    assert restored.version == campaign.version
    assert restored.state == campaign.state
    assert str(restored.scope_statement) == str(campaign.scope_statement)
    assert restored.transition_history == campaign.transition_history


def test_campaign_round_trip_preserves_non_trivial_history() -> None:
    mapper = ConcreteCampaignMapper()
    campaign = _campaign()
    campaign.prepare_for_authorization(actor="tester", occurred_at=OCCURRED_AT)
    campaign.record_authorization(reason="looks good", actor="tester", occurred_at=OCCURRED_AT)
    campaign.activate(reason="starting", actor="tester", occurred_at=OCCURRED_AT)

    record = mapper.to_durable_record(campaign)
    state = mapper.from_durable_record(record)
    restored = _reconstruct_campaign(state)

    assert restored.version == campaign.version
    assert restored.next_transition_sequence == campaign.next_transition_sequence
    assert len(restored.transition_history) == 3
    assert [t.to_state for t in restored.transition_history] == [
        t.to_state for t in campaign.transition_history
    ]
    assert [t.sequence for t in restored.transition_history] == [
        t.sequence for t in campaign.transition_history
    ]


def test_campaign_malformed_lifecycle_state_raises_mapper_error() -> None:
    mapper = ConcreteCampaignMapper()
    record = mapper.to_durable_record(_campaign())
    corrupted = type(record)(
        identity=record.identity,
        scope_statement=record.scope_statement,
        lifecycle_state="NOT_A_REAL_STATE",
        version=record.version,
        next_transition_sequence=record.next_transition_sequence,
        transition_history=record.transition_history,
    )

    with pytest.raises(MapperError) as excinfo:
        mapper.from_durable_record(corrupted)

    assert excinfo.value.category is MapperErrorCategory.INVALID_DURABLE_RECORD
    assert excinfo.value.aggregate_kind == "Campaign"


def test_campaign_malformed_scope_statement_raises_mapper_error() -> None:
    mapper = ConcreteCampaignMapper()
    record = mapper.to_durable_record(_campaign())
    corrupted = type(record)(
        identity=record.identity,
        scope_statement="",
        lifecycle_state=record.lifecycle_state,
        version=record.version,
        next_transition_sequence=record.next_transition_sequence,
        transition_history=record.transition_history,
    )

    with pytest.raises(MapperError) as excinfo:
        mapper.from_durable_record(corrupted)

    assert excinfo.value.category is MapperErrorCategory.INVALID_DURABLE_RECORD


# --- Run ------------------------------------------------------------------


def _run() -> Run:
    identity = DomainIdentity(governance_id=RunId("RUN-0001"), runtime_id=_runtime_id())
    return Run(identity=identity, campaign_id=CampaignId("CAMP-0001"))


def test_run_round_trip_preserves_identity_and_initial_state() -> None:
    mapper = ConcreteRunMapper()
    run = _run()

    record = mapper.to_durable_record(run)
    state = mapper.from_durable_record(record)
    restored = _reconstruct_run(state)

    assert restored.identity == run.identity
    assert restored.campaign_id == run.campaign_id
    assert restored.version == run.version
    assert restored.state == run.state
    assert restored.manifests == run.manifests


def test_run_round_trip_preserves_manifests_in_order_with_optional_fields() -> None:
    mapper = ConcreteRunMapper()
    run = _run()
    run.authorize(actor="tester", occurred_at=OCCURRED_AT)
    run.start_acquisition(actor="tester", occurred_at=OCCURRED_AT)
    run.append_manifest(
        DatasetManifest(
            run_id=RunId("RUN-0001"),
            recorded_at=OCCURRED_AT,
            source="s3://bucket/a",
            manifest_id=DatasetId("DATASET-0001"),
            notes=("note-a", "note-b"),
        )
    )
    run.append_manifest(
        DatasetManifest(run_id=RunId("RUN-0001"), recorded_at=OCCURRED_AT, source="s3://bucket/b")
    )

    record = mapper.to_durable_record(run)
    state = mapper.from_durable_record(record)
    restored = _reconstruct_run(state)

    assert len(restored.manifests) == 2
    assert restored.manifests[0].source == "s3://bucket/a"
    assert restored.manifests[0].manifest_id == DatasetId("DATASET-0001")
    assert restored.manifests[0].notes == ("note-a", "note-b")
    assert restored.manifests[1].source == "s3://bucket/b"
    assert restored.manifests[1].manifest_id is None
    assert restored.manifests[1].notes == ()
    assert restored.manifests == run.manifests


def test_run_malformed_lifecycle_state_raises_mapper_error() -> None:
    mapper = ConcreteRunMapper()
    record = mapper.to_durable_record(_run())
    corrupted = type(record)(
        identity=record.identity,
        campaign_id=record.campaign_id,
        lifecycle_state="NOT_A_REAL_STATE",
        manifests=record.manifests,
        version=record.version,
        next_transition_sequence=record.next_transition_sequence,
        transition_history=record.transition_history,
    )

    with pytest.raises(MapperError) as excinfo:
        mapper.from_durable_record(corrupted)

    assert excinfo.value.category is MapperErrorCategory.INVALID_DURABLE_RECORD
    assert excinfo.value.aggregate_kind == "Run"


def test_run_malformed_campaign_id_raises_mapper_error() -> None:
    mapper = ConcreteRunMapper()
    record = mapper.to_durable_record(_run())
    corrupted = type(record)(
        identity=record.identity,
        campaign_id="",
        lifecycle_state=record.lifecycle_state,
        manifests=record.manifests,
        version=record.version,
        next_transition_sequence=record.next_transition_sequence,
        transition_history=record.transition_history,
    )

    with pytest.raises(MapperError):
        mapper.from_durable_record(corrupted)


# --- EvidencePackage --------------------------------------------------------


def _evidence_package() -> EvidencePackage:
    identity = DomainIdentity(
        governance_id=EvidencePackageId("EVID-0001"), runtime_id=_runtime_id()
    )
    return EvidencePackage(identity=identity, run_id=RunId("RUN-0001"))


def test_evidence_package_round_trip_preserves_identity_and_initial_state() -> None:
    mapper = ConcreteEvidencePackageMapper()
    package = _evidence_package()

    record = mapper.to_durable_record(package)
    state = mapper.from_durable_record(record)
    restored = _reconstruct_evidence_package(state)

    assert restored.identity == package.identity
    assert restored.run_id == package.run_id
    assert restored.version == package.version
    assert restored.state == package.state
    assert restored.criterion_results == package.criterion_results
    assert restored.artifact_references == package.artifact_references


def test_evidence_package_round_trip_preserves_child_collections_in_order() -> None:
    mapper = ConcreteEvidencePackageMapper()
    package = _evidence_package()
    package.start_collection(actor="tester", occurred_at=OCCURRED_AT)
    package.add_criterion_result(
        CriterionResult(
            evidence_package_id=EvidencePackageId("EVID-0001"),
            criterion_id="crit-1",
            recorded_at=OCCURRED_AT,
            result_label="PASS",
            summary="looks good",
            evidence_references=("ref-a", "ref-b"),
        )
    )
    package.add_criterion_result(
        CriterionResult(
            evidence_package_id=EvidencePackageId("EVID-0001"),
            criterion_id="crit-2",
            recorded_at=OCCURRED_AT,
            result_label="FAIL",
        )
    )
    package.add_artifact_reference(ArtifactReference("s3://bucket/first"))
    package.add_artifact_reference(ArtifactReference("s3://bucket/second"))

    record = mapper.to_durable_record(package)
    state = mapper.from_durable_record(record)
    restored = _reconstruct_evidence_package(state)

    assert [c.criterion_id for c in restored.criterion_results] == ["crit-1", "crit-2"]
    assert restored.criterion_results[0].summary == "looks good"
    assert restored.criterion_results[0].evidence_references == ("ref-a", "ref-b")
    assert restored.criterion_results[1].summary is None
    assert restored.criterion_results[1].evidence_references == ()
    assert [str(a) for a in restored.artifact_references] == [
        "s3://bucket/first",
        "s3://bucket/second",
    ]
    assert restored.criterion_results == package.criterion_results
    assert restored.artifact_references == package.artifact_references


def test_evidence_package_malformed_lifecycle_state_raises_mapper_error() -> None:
    mapper = ConcreteEvidencePackageMapper()
    record = mapper.to_durable_record(_evidence_package())
    corrupted = type(record)(
        identity=record.identity,
        run_id=record.run_id,
        lifecycle_state="NOT_A_REAL_STATE",
        criterion_results=record.criterion_results,
        artifact_references=record.artifact_references,
        version=record.version,
        next_transition_sequence=record.next_transition_sequence,
        transition_history=record.transition_history,
    )

    with pytest.raises(MapperError) as excinfo:
        mapper.from_durable_record(corrupted)

    assert excinfo.value.category is MapperErrorCategory.INVALID_DURABLE_RECORD
    assert excinfo.value.aggregate_kind == "EvidencePackage"


def test_evidence_package_malformed_criterion_raises_mapper_error() -> None:
    mapper = ConcreteEvidencePackageMapper()
    package = _evidence_package()
    package.start_collection(actor="tester", occurred_at=OCCURRED_AT)
    package.add_criterion_result(
        CriterionResult(
            evidence_package_id=EvidencePackageId("EVID-0001"),
            criterion_id="crit-1",
            recorded_at=OCCURRED_AT,
            result_label="PASS",
        )
    )
    record = mapper.to_durable_record(package)
    corrupted_criterion = type(record.criterion_results[0])(
        evidence_package_id="",
        criterion_id=record.criterion_results[0].criterion_id,
        recorded_at=record.criterion_results[0].recorded_at,
        result_label=record.criterion_results[0].result_label,
        summary=record.criterion_results[0].summary,
        evidence_references=record.criterion_results[0].evidence_references,
    )
    corrupted = type(record)(
        identity=record.identity,
        run_id=record.run_id,
        lifecycle_state=record.lifecycle_state,
        criterion_results=(corrupted_criterion,),
        artifact_references=record.artifact_references,
        version=record.version,
        next_transition_sequence=record.next_transition_sequence,
        transition_history=record.transition_history,
    )

    with pytest.raises(MapperError):
        mapper.from_durable_record(corrupted)


# --- Review -----------------------------------------------------------------


def _review() -> Review:
    identity = DomainIdentity(governance_id=ReviewId("REVIEW-0001"), runtime_id=_runtime_id())
    return Review(
        identity=identity,
        target=ReviewTargetReference(EvidencePackageId("EVID-0001")),
        reviewer=ReviewerReference("reviewer-1"),
    )


def test_review_round_trip_preserves_identity_and_initial_state() -> None:
    mapper = ConcreteReviewMapper()
    review = _review()

    record = mapper.to_durable_record(review)
    state = mapper.from_durable_record(record)
    restored = _reconstruct_review(state)

    assert restored.identity == review.identity
    assert restored.target == review.target
    assert restored.reviewer == review.reviewer
    assert restored.version == review.version
    assert restored.state == review.state
    assert restored.findings == review.findings
    assert restored.disposition == review.disposition


def test_review_round_trip_preserves_findings_and_nullable_disposition_fields() -> None:
    mapper = ConcreteReviewMapper()
    review = _review()
    review.start(actor="tester", occurred_at=OCCURRED_AT)
    review.add_finding(text="first finding", rationale="because", evidence_references=("ref-1",))
    review.add_finding(text="second finding")
    review.complete(
        disposition=ReviewDisposition.ACCEPTED,
        final_disposition_rationale="all good",
        actor="tester",
        occurred_at=OCCURRED_AT,
    )

    record = mapper.to_durable_record(review)
    state = mapper.from_durable_record(record)
    restored = _reconstruct_review(state)

    assert [f.text for f in restored.findings] == ["first finding", "second finding"]
    assert restored.findings[0].rationale == "because"
    assert restored.findings[0].evidence_references == ("ref-1",)
    assert restored.findings[1].rationale is None
    assert restored.disposition == review.disposition
    assert restored.final_disposition_rationale == review.final_disposition_rationale
    assert restored.findings == review.findings


def test_review_malformed_lifecycle_state_raises_mapper_error() -> None:
    mapper = ConcreteReviewMapper()
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


def test_review_malformed_disposition_raises_mapper_error() -> None:
    mapper = ConcreteReviewMapper()
    review = _review()
    review.start(actor="tester", occurred_at=OCCURRED_AT)
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

    assert excinfo.value.field == "disposition"
