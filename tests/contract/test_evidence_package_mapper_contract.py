"""MILESTONE-021 contract tests for EvidencePackageMapper, using an in-memory fake."""

from __future__ import annotations

import uuid
from dataclasses import FrozenInstanceError
from datetime import UTC, datetime

import pytest
from tests.contract._mapper_fakes import FakeEvidencePackageMapper

from empirical_platform.evidence._reconstruction import _reconstruct_evidence_package
from empirical_platform.evidence.package import ArtifactReference, EvidencePackage
from empirical_platform.evidence.results import CriterionResult
from empirical_platform.identifiers.pairs import DomainIdentity
from empirical_platform.identifiers.types import EvidencePackageId, RunId
from empirical_platform.shared.contracts.mapping import MapperError, MapperErrorCategory
from empirical_platform.shared.identifiers import RuntimeIdentifier

OCCURRED_AT = datetime(2026, 7, 26, tzinfo=UTC)


def _identity() -> DomainIdentity[EvidencePackageId]:
    return DomainIdentity(
        governance_id=EvidencePackageId("EVID-0001"),
        runtime_id=RuntimeIdentifier(str(uuid.uuid4())),
    )


def _package() -> EvidencePackage:
    return EvidencePackage(_identity(), RunId("RUN-0001"))


def test_round_trip_preserves_identity_and_initial_state() -> None:
    mapper = FakeEvidencePackageMapper()
    package = _package()

    record = mapper.to_durable_record(package)
    state = mapper.from_durable_record(record)
    restored = _reconstruct_evidence_package(state)

    assert restored.identity == package.identity
    assert restored.run_id == package.run_id
    assert restored.version == package.version
    assert restored.state == package.state


def test_round_trip_preserves_sealed_contents_and_order() -> None:
    mapper = FakeEvidencePackageMapper()
    package = _package()
    package.start_collection(actor="tester", occurred_at=OCCURRED_AT)
    package.add_criterion_result(
        CriterionResult(
            evidence_package_id=EvidencePackageId("EVID-0001"),
            criterion_id="crit-1",
            recorded_at=OCCURRED_AT,
            result_label="PASS",
            summary="looks fine",
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
    package.add_artifact_reference(ArtifactReference("artifact-1"))
    package.seal(actor="tester", occurred_at=OCCURRED_AT, reason="complete")

    record = mapper.to_durable_record(package)
    state = mapper.from_durable_record(record)
    restored = _reconstruct_evidence_package(state)

    assert [r.criterion_id for r in restored.criterion_results] == ["crit-1", "crit-2"]
    assert restored.criterion_results[0].evidence_references == ("ref-a", "ref-b")
    assert restored.criterion_results[1].summary is None
    assert [a.value for a in restored.artifact_references] == ["artifact-1"]
    assert restored.version == package.version
    assert restored.state == package.state


def test_durable_record_is_immutable() -> None:
    mapper = FakeEvidencePackageMapper()
    record = mapper.to_durable_record(_package())

    with pytest.raises(FrozenInstanceError):
        record.lifecycle_state = "changed"  # type: ignore[misc]


def test_malformed_lifecycle_state_raises_mapper_error() -> None:
    mapper = FakeEvidencePackageMapper()
    record = mapper.to_durable_record(_package())
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
