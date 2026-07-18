from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime

import pytest

from empirical_platform.evidence import (
    ArtifactReference,
    CriterionResult,
    EvidencePackage,
    EvidencePackageLifecycleState,
)
from empirical_platform.identifiers import DomainIdentity, EvidencePackageId, RunId
from empirical_platform.shared.domain import AggregateVersion, TransitionSequence
from empirical_platform.shared.identifiers import RuntimeIdentifier

OCCURRED_AT = datetime(2026, 7, 18, tzinfo=UTC)


def _identity(value: str = "EVID-0001") -> DomainIdentity[EvidencePackageId]:
    return DomainIdentity(
        governance_id=EvidencePackageId(value),
        runtime_id=RuntimeIdentifier("123e4567-e89b-42d3-a456-426614174000"),
    )


def _package() -> EvidencePackage:
    return EvidencePackage(identity=_identity(), run_id=RunId("RUN-0001"))


def _result(criterion_id: str = "B3-L1-QUOTE-COVERAGE") -> CriterionResult:
    return CriterionResult(
        evidence_package_id=EvidencePackageId("EVID-0001"),
        criterion_id=criterion_id,
        recorded_at=OCCURRED_AT,
        result_label="OBSERVED",
        summary="Process-local result.",
        evidence_references=("artifact://opaque/reference",),
    )


def _collecting_package() -> EvidencePackage:
    package = _package()
    package.start_collection(actor="Evidence Manager", occurred_at=OCCURRED_AT)
    return package


def _snapshot(package: EvidencePackage) -> tuple[object, ...]:
    return (
        package.identity,
        package.run_id,
        package.state,
        package.version,
        package.next_transition_sequence,
        package.transition_history,
        package.criterion_results,
        package.artifact_references,
    )


def _sealed_package() -> EvidencePackage:
    package = _collecting_package()
    package.add_criterion_result(_result())
    package.add_artifact_reference(ArtifactReference("artifact://opaque/reference"))
    package.seal(actor="Evidence Manager", occurred_at=OCCURRED_AT)
    return package


def test_construction_sets_initial_identity_lifecycle_version_sequence_and_empty_collections() -> (
    None
):
    identity = _identity()
    package = EvidencePackage(identity=identity, run_id=RunId("RUN-0001"))

    assert package.identity == identity
    assert package.run_id == RunId("RUN-0001")
    assert package.state is EvidencePackageLifecycleState.INITIALIZED
    assert package.version == AggregateVersion.initial()
    assert package.next_transition_sequence == TransitionSequence.initial()
    assert package.transition_history == ()
    assert package.criterion_results == ()
    assert package.artifact_references == ()


def test_construction_rejects_invalid_identity_and_run_context() -> None:
    with pytest.raises(TypeError, match="DomainIdentity"):
        EvidencePackage(  # type: ignore[arg-type]
            identity=EvidencePackageId("EVID-0001"),
            run_id=RunId("RUN-0001"),
        )
    with pytest.raises(TypeError, match="EvidencePackageId"):
        EvidencePackage(  # type: ignore[arg-type]
            identity=DomainIdentity(
                governance_id=RunId("RUN-0001"),
                runtime_id=RuntimeIdentifier("123e4567-e89b-42d3-a456-426614174000"),
            ),
            run_id=RunId("RUN-0001"),
        )
    with pytest.raises(TypeError, match="RunId"):
        EvidencePackage(identity=_identity(), run_id=EvidencePackageId("EVID-0001"))  # type: ignore[arg-type]


def test_artifact_reference_is_opaque_immutable_and_hash_stable() -> None:
    reference = ArtifactReference("artifact://opaque/reference")

    assert str(reference) == "artifact://opaque/reference"
    assert reference == ArtifactReference("artifact://opaque/reference")
    assert hash(reference) == hash(ArtifactReference("artifact://opaque/reference"))
    assert not hasattr(reference, "bucket")
    assert not hasattr(reference, "object_key")
    assert not hasattr(reference, "checksum")
    with pytest.raises(FrozenInstanceError):
        reference.value = "changed"  # type: ignore[misc]


def test_artifact_reference_rejects_invalid_values() -> None:
    with pytest.raises(TypeError, match="string"):
        ArtifactReference(123)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="non-empty"):
        ArtifactReference(" ")


def test_start_collection_records_lifecycle_transition() -> None:
    package = _package()

    package.start_collection(
        actor="Evidence Manager",
        occurred_at=OCCURRED_AT,
        correlation_id="corr-1",
        reason="collection scope known",
    )

    assert package.state is EvidencePackageLifecycleState.COLLECTING
    assert package.version == AggregateVersion(1)
    assert package.next_transition_sequence == TransitionSequence(2)
    assert len(package.transition_history) == 1
    record = package.transition_history[0]
    assert record.from_state == "INITIALIZED"
    assert record.to_state == "COLLECTING"
    assert record.version == AggregateVersion(1)
    assert record.sequence == TransitionSequence(1)
    assert record.actor == "Evidence Manager"
    assert record.occurred_at == OCCURRED_AT
    assert record.identity_reference == package.identity
    assert record.correlation_id == "corr-1"
    assert record.reason == "collection scope known"


def test_start_collection_is_rejected_outside_initialized_without_mutation() -> None:
    package = _collecting_package()
    before = _snapshot(package)

    with pytest.raises(ValueError, match="COLLECTING"):
        package.start_collection(actor="Evidence Manager", occurred_at=OCCURRED_AT)

    assert _snapshot(package) == before


def test_criterion_result_can_be_added_only_while_collecting_and_increments_content_version() -> (
    None
):
    package = _collecting_package()

    package.add_criterion_result(_result())

    assert package.version == AggregateVersion(2)
    assert package.next_transition_sequence == TransitionSequence(2)
    assert package.transition_history[0].to_state == "COLLECTING"
    assert len(package.transition_history) == 1
    assert package.criterion_results == (_result(),)


def test_criterion_result_rejection_paths_are_atomic() -> None:
    package = _package()
    before = _snapshot(package)
    with pytest.raises(ValueError, match="COLLECTING"):
        package.add_criterion_result(_result())
    assert _snapshot(package) == before

    collecting_wrong_type = _collecting_package()
    before_wrong_type = _snapshot(collecting_wrong_type)
    with pytest.raises(TypeError, match="CriterionResult"):
        collecting_wrong_type.add_criterion_result(ArtifactReference("artifact"))  # type: ignore[arg-type]
    assert _snapshot(collecting_wrong_type) == before_wrong_type

    collecting = _collecting_package()
    collecting.add_criterion_result(_result())
    before_duplicate = _snapshot(collecting)
    with pytest.raises(ValueError, match="criterion_id"):
        collecting.add_criterion_result(_result())
    assert _snapshot(collecting) == before_duplicate

    mismatch = _collecting_package()
    before_mismatch = _snapshot(mismatch)
    with pytest.raises(ValueError, match="evidence_package_id"):
        mismatch.add_criterion_result(
            CriterionResult(
                evidence_package_id=EvidencePackageId("EVID-0002"),
                criterion_id="B3-L1-QUOTE-COVERAGE",
                recorded_at=OCCURRED_AT,
                result_label="OBSERVED",
            )
        )
    assert _snapshot(mismatch) == before_mismatch


def test_artifact_reference_can_be_added_only_while_collecting_and_increments_content_version() -> (
    None
):
    package = _collecting_package()
    reference = ArtifactReference("artifact://opaque/reference")

    package.add_artifact_reference(reference)

    assert package.version == AggregateVersion(2)
    assert package.next_transition_sequence == TransitionSequence(2)
    assert package.transition_history[0].to_state == "COLLECTING"
    assert len(package.transition_history) == 1
    assert package.artifact_references == (reference,)


def test_artifact_reference_rejection_paths_are_atomic() -> None:
    package = _package()
    reference = ArtifactReference("artifact://opaque/reference")
    before = _snapshot(package)
    with pytest.raises(ValueError, match="COLLECTING"):
        package.add_artifact_reference(reference)
    assert _snapshot(package) == before

    collecting_wrong_type = _collecting_package()
    before_wrong_type = _snapshot(collecting_wrong_type)
    with pytest.raises(TypeError, match="ArtifactReference"):
        collecting_wrong_type.add_artifact_reference("artifact")  # type: ignore[arg-type]
    assert _snapshot(collecting_wrong_type) == before_wrong_type

    collecting = _collecting_package()
    collecting.add_artifact_reference(reference)
    before_duplicate = _snapshot(collecting)
    with pytest.raises(ValueError, match="already exists"):
        collecting.add_artifact_reference(ArtifactReference("artifact://opaque/reference"))
    assert _snapshot(collecting) == before_duplicate


def test_seal_requires_contents_and_records_lifecycle_transition() -> None:
    no_contents = _collecting_package()
    before_no_contents = _snapshot(no_contents)
    with pytest.raises(ValueError, match="Criterion Result"):
        no_contents.seal(actor="Evidence Manager", occurred_at=OCCURRED_AT)
    assert _snapshot(no_contents) == before_no_contents

    only_reference = _collecting_package()
    only_reference.add_artifact_reference(ArtifactReference("artifact://opaque/reference"))
    before_only_reference = _snapshot(only_reference)
    with pytest.raises(ValueError, match="Criterion Result"):
        only_reference.seal(actor="Evidence Manager", occurred_at=OCCURRED_AT)
    assert _snapshot(only_reference) == before_only_reference

    no_reference = _collecting_package()
    no_reference.add_criterion_result(_result())
    before_no_reference = _snapshot(no_reference)
    with pytest.raises(ValueError, match="artifact reference"):
        no_reference.seal(actor="Evidence Manager", occurred_at=OCCURRED_AT)
    assert _snapshot(no_reference) == before_no_reference

    package = _sealed_package()

    assert package.state is EvidencePackageLifecycleState.SEALED
    assert package.version == AggregateVersion(4)
    assert package.next_transition_sequence == TransitionSequence(3)
    assert len(package.transition_history) == 2
    assert package.transition_history[1].from_state == "COLLECTING"
    assert package.transition_history[1].to_state == "SEALED"
    assert package.transition_history[1].version == AggregateVersion(4)
    assert package.transition_history[1].sequence == TransitionSequence(2)


def test_sealed_package_rejects_content_changes_without_mutation() -> None:
    package = _sealed_package()
    before_result = _snapshot(package)
    with pytest.raises(ValueError, match="COLLECTING"):
        package.add_criterion_result(_result("B3-L1-TRADE-COVERAGE"))
    assert _snapshot(package) == before_result

    before_reference = _snapshot(package)
    with pytest.raises(ValueError, match="COLLECTING"):
        package.add_artifact_reference(ArtifactReference("artifact://opaque/after-seal"))
    assert _snapshot(package) == before_reference


def test_invalid_lifecycle_transitions_are_rejected_without_mutation() -> None:
    initialized = _package()
    before_initialized = _snapshot(initialized)
    with pytest.raises(ValueError, match="INITIALIZED"):
        initialized.invalidate(
            reason="cannot invalidate before seal",
            actor="Evidence Manager",
            occurred_at=OCCURRED_AT,
        )
    assert _snapshot(initialized) == before_initialized

    collecting = _collecting_package()
    before_collecting = _snapshot(collecting)
    with pytest.raises(ValueError, match="COLLECTING"):
        collecting.invalidate(
            reason="cannot invalidate before seal",
            actor="Evidence Manager",
            occurred_at=OCCURRED_AT,
        )
    assert _snapshot(collecting) == before_collecting

    sealed = _sealed_package()
    before_sealed = _snapshot(sealed)
    with pytest.raises(ValueError, match="SEALED"):
        sealed.seal(actor="Evidence Manager", occurred_at=OCCURRED_AT)
    assert _snapshot(sealed) == before_sealed


def test_lifecycle_transition_rejects_invalid_timestamp_without_mutation() -> None:
    package = _package()
    before = _snapshot(package)

    with pytest.raises(TypeError, match="datetime"):
        package.start_collection(actor="Evidence Manager", occurred_at="now")  # type: ignore[arg-type]

    assert _snapshot(package) == before


def test_invalidate_requires_reason_and_preserves_sealed_contents() -> None:
    package = _sealed_package()
    sealed_results = package.criterion_results
    sealed_references = package.artifact_references

    before_wrong_type = _snapshot(package)
    with pytest.raises(TypeError, match="string"):
        package.invalidate(reason=123, actor="Evidence Manager", occurred_at=OCCURRED_AT)  # type: ignore[arg-type]
    assert _snapshot(package) == before_wrong_type

    with pytest.raises(ValueError, match="reason"):
        package.invalidate(reason=" ", actor="Evidence Manager", occurred_at=OCCURRED_AT)

    package.invalidate(
        reason="digest mismatch",
        actor="Evidence Manager",
        occurred_at=OCCURRED_AT,
        correlation_id="corr-2",
    )

    assert package.state is EvidencePackageLifecycleState.INVALIDATED
    assert package.version == AggregateVersion(5)
    assert package.next_transition_sequence == TransitionSequence(4)
    assert package.criterion_results == sealed_results
    assert package.artifact_references == sealed_references
    assert len(package.transition_history) == 3
    assert package.transition_history[2].from_state == "SEALED"
    assert package.transition_history[2].to_state == "INVALIDATED"
    assert package.transition_history[2].reason == "digest mismatch"
    assert package.transition_history[2].correlation_id == "corr-2"

    before_repeated_invalidation = _snapshot(package)
    with pytest.raises(ValueError, match="INVALIDATED"):
        package.invalidate(
            reason="second invalidation attempt",
            actor="Evidence Manager",
            occurred_at=OCCURRED_AT,
        )
    assert _snapshot(package) == before_repeated_invalidation


def test_collection_views_are_immutable_and_preserve_insertion_order() -> None:
    package = _collecting_package()
    first = _result("B3-L1-QUOTE-COVERAGE")
    second = _result("B3-L1-TRADE-COVERAGE")
    first_reference = ArtifactReference("artifact://opaque/1")
    second_reference = ArtifactReference("artifact://opaque/2")

    package.add_criterion_result(first)
    package.add_criterion_result(second)
    package.add_artifact_reference(first_reference)
    package.add_artifact_reference(second_reference)

    assert package.criterion_results == (first, second)
    assert package.artifact_references == (first_reference, second_reference)
    with pytest.raises(AttributeError):
        package.criterion_results.append(first)  # type: ignore[attr-defined]
    with pytest.raises(AttributeError):
        package.artifact_references.append(first_reference)  # type: ignore[attr-defined]


def test_evidence_package_has_no_deferred_infrastructure_or_cross_aggregate_surface() -> None:
    package = _sealed_package()

    assert not hasattr(package, "save")
    assert not hasattr(package, "load")
    assert not hasattr(package, "repository")
    assert not hasattr(package, "session")
    assert not hasattr(package, "bucket")
    assert not hasattr(package, "object_key")
    assert not hasattr(package, "dispatch")
    assert not hasattr(package, "review")
    assert not hasattr(package, "campaign")
    assert not hasattr(package, "run")
