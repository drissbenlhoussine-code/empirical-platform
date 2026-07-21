from __future__ import annotations

from collections.abc import Callable
from dataclasses import FrozenInstanceError
from datetime import UTC, datetime
from types import ModuleType
from typing import Any

import pytest

import empirical_platform.campaign as campaign_exports
import empirical_platform.evidence as evidence_exports
import empirical_platform.review as review_exports
import empirical_platform.run as run_exports
from empirical_platform.campaign import (
    Campaign,
    CampaignLifecycleState,
    CampaignScopeStatement,
    RunLifecycleState,
)
from empirical_platform.campaign._reconstruction import (
    CampaignReconstructionState,
    _reconstruct_campaign,
)
from empirical_platform.datasets import DatasetManifest
from empirical_platform.evidence import (
    ArtifactReference,
    CriterionResult,
    EvidencePackage,
    EvidencePackageLifecycleState,
)
from empirical_platform.evidence._reconstruction import (
    EvidencePackageReconstructionState,
    _reconstruct_evidence_package,
)
from empirical_platform.identifiers import (
    CampaignId,
    DatasetId,
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
from empirical_platform.review._reconstruction import ReviewReconstructionState, _reconstruct_review
from empirical_platform.run import Run
from empirical_platform.run._reconstruction import RunReconstructionState, _reconstruct_run
from empirical_platform.shared.domain import (
    AggregateVersion,
    ReconstructionError,
    ReconstructionErrorCategory,
    StateTransitionRecord,
    TransitionSequence,
)
from empirical_platform.shared.identifiers import RuntimeIdentifier

OCCURRED_AT = datetime(2026, 7, 21, tzinfo=UTC)


def _identity(identifier: object, suffix: str = "100") -> DomainIdentity[Any]:
    return DomainIdentity(
        governance_id=identifier,  # type: ignore[arg-type]
        runtime_id=RuntimeIdentifier(f"123e4567-e89b-42d3-a456-426614174{suffix}"),
    )


def _campaign_identity(value: str = "CAMP-0001") -> DomainIdentity[CampaignId]:
    return _identity(CampaignId(value), "101")


def _run_identity(value: str = "RUN-0001") -> DomainIdentity[RunId]:
    return _identity(RunId(value), "102")


def _package_identity(value: str = "EVID-0001") -> DomainIdentity[EvidencePackageId]:
    return _identity(EvidencePackageId(value), "103")


def _review_identity(value: str = "REVIEW-0001") -> DomainIdentity[ReviewId]:
    return _identity(ReviewId(value), "104")


def _record(
    *,
    identity: DomainIdentity[Any],
    from_state: str,
    to_state: str,
    version: int,
    sequence: int,
    reason: str | None = None,
) -> StateTransitionRecord[DomainIdentity[Any]]:
    return StateTransitionRecord(
        from_state=from_state,
        to_state=to_state,
        version=AggregateVersion(version),
        sequence=TransitionSequence(sequence),
        actor="reconstruction-test",
        occurred_at=OCCURRED_AT,
        identity_reference=identity,
        reason=reason,
    )


def _manifest(
    run_id: RunId | None = None,
    manifest_id: DatasetId | None = None,
    source: str = "source",
) -> DatasetManifest:
    return DatasetManifest(
        run_id=run_id or RunId("RUN-0001"),
        manifest_id=manifest_id or DatasetId("DATASET-0001"),
        recorded_at=OCCURRED_AT,
        source=source,
    )


def _result(
    package_id: EvidencePackageId | None = None,
    criterion_id: str = "B3-L1-QUOTE-COVERAGE",
) -> CriterionResult:
    return CriterionResult(
        evidence_package_id=package_id or EvidencePackageId("EVID-0001"),
        criterion_id=criterion_id,
        recorded_at=OCCURRED_AT,
        result_label="OBSERVED",
    )


def _artifact(value: str = "artifact://opaque/1") -> ArtifactReference:
    return ArtifactReference(value)


def _finding(sequence: int = 1, text: str = "Finding") -> ReviewFinding:
    return ReviewFinding(sequence=sequence, text=text)


def test_reconstruction_error_contract_is_persistence_neutral() -> None:
    assert {category.value for category in ReconstructionErrorCategory} == {
        "WrongReconstructionInput",
        "InvalidAggregateIdentity",
        "InvalidLifecycleState",
        "InvalidAggregateVersion",
        "InvalidTransitionSequence",
        "InvalidTransitionHistory",
        "InconsistentCurrentState",
        "InvalidCollectionElement",
        "DuplicateOwnedValue",
        "InconsistentTerminalMetadata",
        "UnauthorizedReconstructionPath",
    }
    error = ReconstructionError(
        ReconstructionErrorCategory.INVALID_AGGREGATE_VERSION,
        "bad version",
        field="version",
        context="Campaign",
    )

    assert str(error) == "bad version"
    assert error.category is ReconstructionErrorCategory.INVALID_AGGREGATE_VERSION
    assert error.field == "version"
    assert error.context == "Campaign"
    assert "sql" not in {category.value.lower() for category in ReconstructionErrorCategory}


@pytest.mark.parametrize(
    "state",
    (
        CampaignReconstructionState(
            identity=_campaign_identity(),
            scope_statement=CampaignScopeStatement("scope"),
            state=CampaignLifecycleState.DRAFT,
            version=AggregateVersion.initial(),
            next_transition_sequence=TransitionSequence.initial(),
            transition_history=[],
        ),
        RunReconstructionState(
            identity=_run_identity(),
            campaign_id=CampaignId("CAMP-0001"),
            state=RunLifecycleState.CREATED,
            manifests=[],
            version=AggregateVersion.initial(),
            next_transition_sequence=TransitionSequence.initial(),
            transition_history=[],
        ),
        EvidencePackageReconstructionState(
            identity=_package_identity(),
            run_id=RunId("RUN-0001"),
            state=EvidencePackageLifecycleState.INITIALIZED,
            criterion_results=[],
            artifact_references=[],
            version=AggregateVersion.initial(),
            next_transition_sequence=TransitionSequence.initial(),
            transition_history=[],
        ),
        ReviewReconstructionState(
            identity=_review_identity(),
            target=ReviewTargetReference(EvidencePackageId("EVID-0001")),
            reviewer=ReviewerReference("reviewer"),
            state=ReviewLifecycleState.ASSIGNED,
            findings=[],
            disposition=None,
            final_disposition_rationale=None,
            cancellation_reason=None,
            version=AggregateVersion.initial(),
            next_transition_sequence=TransitionSequence.initial(),
            transition_history=[],
        ),
    ),
)
def test_state_records_are_immutable_slots_and_materialize_tuples(state: object) -> None:
    assert not hasattr(state, "__dict__")
    with pytest.raises(FrozenInstanceError):
        state.version = AggregateVersion(9)  # type: ignore[attr-defined]
    assert isinstance(state.transition_history, tuple)  # type: ignore[attr-defined]


def test_campaign_reconstruction_restores_initial_draft_and_positive_draft_version() -> None:
    initial = _reconstruct_campaign(
        CampaignReconstructionState(
            identity=_campaign_identity(),
            scope_statement=CampaignScopeStatement("scope"),
            state=CampaignLifecycleState.DRAFT,
            version=AggregateVersion.initial(),
            next_transition_sequence=TransitionSequence.initial(),
            transition_history=(),
        )
    )
    revised = _reconstruct_campaign(
        CampaignReconstructionState(
            identity=_campaign_identity(),
            scope_statement=CampaignScopeStatement("revised"),
            state=CampaignLifecycleState.DRAFT,
            version=AggregateVersion(3),
            next_transition_sequence=TransitionSequence.initial(),
            transition_history=(),
        )
    )

    assert isinstance(initial, Campaign)
    assert initial.state is CampaignLifecycleState.DRAFT
    assert revised.version == AggregateVersion(3)
    revised.revise_scope_statement(CampaignScopeStatement("after load"))
    assert revised.version == AggregateVersion(4)


def test_campaign_reconstruction_restores_terminal_history_without_scope_revision_history() -> None:
    identity = _campaign_identity()
    history = (
        _record(
            identity=identity,
            from_state="DRAFT",
            to_state="READY_FOR_AUTHORIZATION",
            version=2,
            sequence=1,
        ),
        _record(
            identity=identity,
            from_state="READY_FOR_AUTHORIZATION",
            to_state="AUTHORIZED",
            version=3,
            sequence=2,
            reason="ok",
        ),
        _record(
            identity=identity,
            from_state="AUTHORIZED",
            to_state="ACTIVE",
            version=4,
            sequence=3,
            reason="start",
        ),
        _record(
            identity=identity,
            from_state="ACTIVE",
            to_state="COMPLETED",
            version=5,
            sequence=4,
            reason="done",
        ),
    )

    campaign = _reconstruct_campaign(
        CampaignReconstructionState(
            identity=identity,
            scope_statement=CampaignScopeStatement("current scope"),
            state=CampaignLifecycleState.COMPLETED,
            version=AggregateVersion(5),
            next_transition_sequence=TransitionSequence(5),
            transition_history=history,
        )
    )

    assert campaign.transition_history == history
    assert campaign.scope_statement == CampaignScopeStatement("current scope")
    with pytest.raises(ValueError, match="COMPLETED"):
        campaign.revise_scope_statement(CampaignScopeStatement("late"))


def test_campaign_reconstruction_rejects_missing_required_transition_reasons() -> None:
    identity = _campaign_identity()
    required_reason_edges = (
        ("READY_FOR_AUTHORIZATION", "AUTHORIZED", CampaignLifecycleState.AUTHORIZED),
        ("AUTHORIZED", "ACTIVE", CampaignLifecycleState.ACTIVE),
        ("ACTIVE", "SUSPENDED", CampaignLifecycleState.SUSPENDED),
        ("SUSPENDED", "ACTIVE", CampaignLifecycleState.ACTIVE),
        ("ACTIVE", "COMPLETED", CampaignLifecycleState.COMPLETED),
        ("AUTHORIZED", "CANCELLED", CampaignLifecycleState.CANCELLED),
        ("ACTIVE", "CANCELLED", CampaignLifecycleState.CANCELLED),
        ("SUSPENDED", "CANCELLED", CampaignLifecycleState.CANCELLED),
    )

    prefix_by_from_state: dict[str, tuple[StateTransitionRecord[DomainIdentity[Any]], ...]] = {
        "READY_FOR_AUTHORIZATION": (
            _record(
                identity=identity,
                from_state="DRAFT",
                to_state="READY_FOR_AUTHORIZATION",
                version=1,
                sequence=1,
            ),
        ),
        "AUTHORIZED": (
            _record(
                identity=identity,
                from_state="DRAFT",
                to_state="READY_FOR_AUTHORIZATION",
                version=1,
                sequence=1,
            ),
            _record(
                identity=identity,
                from_state="READY_FOR_AUTHORIZATION",
                to_state="AUTHORIZED",
                version=2,
                sequence=2,
                reason="authorization accepted",
            ),
        ),
        "ACTIVE": (
            _record(
                identity=identity,
                from_state="DRAFT",
                to_state="READY_FOR_AUTHORIZATION",
                version=1,
                sequence=1,
            ),
            _record(
                identity=identity,
                from_state="READY_FOR_AUTHORIZATION",
                to_state="AUTHORIZED",
                version=2,
                sequence=2,
                reason="authorization accepted",
            ),
            _record(
                identity=identity,
                from_state="AUTHORIZED",
                to_state="ACTIVE",
                version=3,
                sequence=3,
                reason="activation accepted",
            ),
        ),
        "SUSPENDED": (
            _record(
                identity=identity,
                from_state="DRAFT",
                to_state="READY_FOR_AUTHORIZATION",
                version=1,
                sequence=1,
            ),
            _record(
                identity=identity,
                from_state="READY_FOR_AUTHORIZATION",
                to_state="AUTHORIZED",
                version=2,
                sequence=2,
                reason="authorization accepted",
            ),
            _record(
                identity=identity,
                from_state="AUTHORIZED",
                to_state="ACTIVE",
                version=3,
                sequence=3,
                reason="activation accepted",
            ),
            _record(
                identity=identity,
                from_state="ACTIVE",
                to_state="SUSPENDED",
                version=4,
                sequence=4,
                reason="pause",
            ),
        ),
    }

    for from_state, to_state, restored_state in required_reason_edges:
        prefix = prefix_by_from_state[from_state]
        history = (
            *prefix,
            _record(
                identity=identity,
                from_state=from_state,
                to_state=to_state,
                version=len(prefix) + 1,
                sequence=len(prefix) + 1,
            ),
        )
        with pytest.raises(ReconstructionError) as exc_info:
            _reconstruct_campaign(
                CampaignReconstructionState(
                    identity=identity,
                    scope_statement=CampaignScopeStatement("current scope"),
                    state=restored_state,
                    version=AggregateVersion(len(history)),
                    next_transition_sequence=TransitionSequence(len(history) + 1),
                    transition_history=history,
                )
            )
        assert exc_info.value.category is ReconstructionErrorCategory.INCONSISTENT_TERMINAL_METADATA


def test_campaign_reconstruction_allows_optional_pre_authorization_reasons() -> None:
    identity = _campaign_identity()
    ready_history = (
        _record(
            identity=identity,
            from_state="DRAFT",
            to_state="READY_FOR_AUTHORIZATION",
            version=1,
            sequence=1,
        ),
    )
    cancelled_history = (
        _record(
            identity=identity,
            from_state="READY_FOR_AUTHORIZATION",
            to_state="CANCELLED",
            version=2,
            sequence=2,
        ),
    )

    ready = _reconstruct_campaign(
        CampaignReconstructionState(
            identity=identity,
            scope_statement=CampaignScopeStatement("ready scope"),
            state=CampaignLifecycleState.READY_FOR_AUTHORIZATION,
            version=AggregateVersion(1),
            next_transition_sequence=TransitionSequence(2),
            transition_history=ready_history,
        )
    )
    cancelled = _reconstruct_campaign(
        CampaignReconstructionState(
            identity=identity,
            scope_statement=CampaignScopeStatement("cancelled scope"),
            state=CampaignLifecycleState.CANCELLED,
            version=AggregateVersion(2),
            next_transition_sequence=TransitionSequence(3),
            transition_history=(*ready_history, *cancelled_history),
        )
    )

    assert ready.transition_history[-1].reason is None
    assert cancelled.transition_history[-1].reason is None


def test_run_reconstruction_restores_manifest_order_and_current_manifest() -> None:
    identity = _run_identity()
    first = _manifest(source="first")
    second = _manifest(manifest_id=DatasetId("DATASET-0002"), source="second")
    history = (
        _record(
            identity=identity, from_state="CREATED", to_state="AUTHORIZED", version=1, sequence=1
        ),
    )

    run = _reconstruct_run(
        RunReconstructionState(
            identity=identity,
            campaign_id=CampaignId("CAMP-0001"),
            state=RunLifecycleState.AUTHORIZED,
            manifests=[first, second],
            version=AggregateVersion(3),
            next_transition_sequence=TransitionSequence(2),
            transition_history=history,
        )
    )

    assert isinstance(run, Run)
    assert run.manifests == (first, second)
    assert run.current_manifest == second
    run.append_manifest(_manifest(manifest_id=DatasetId("DATASET-0003"), source="third"))
    assert run.version == AggregateVersion(4)


def test_evidence_package_reconstruction_restores_sealed_contents() -> None:
    identity = _package_identity()
    result = _result()
    artifact = _artifact()
    history = (
        _record(
            identity=identity,
            from_state="INITIALIZED",
            to_state="COLLECTING",
            version=1,
            sequence=1,
        ),
        _record(
            identity=identity, from_state="COLLECTING", to_state="SEALED", version=3, sequence=2
        ),
    )

    package = _reconstruct_evidence_package(
        EvidencePackageReconstructionState(
            identity=identity,
            run_id=RunId("RUN-0001"),
            state=EvidencePackageLifecycleState.SEALED,
            criterion_results=(result,),
            artifact_references=(artifact,),
            version=AggregateVersion(3),
            next_transition_sequence=TransitionSequence(3),
            transition_history=history,
        )
    )

    assert isinstance(package, EvidencePackage)
    assert package.criterion_results == (result,)
    assert package.artifact_references == (artifact,)
    with pytest.raises(ValueError, match="COLLECTING"):
        package.add_artifact_reference(_artifact("artifact://opaque/2"))


def test_review_reconstruction_restores_terminal_metadata_and_next_finding_sequence() -> None:
    identity = _review_identity()
    findings = (_finding(1), _finding(2, "Finding again"))
    history = (
        _record(
            identity=identity, from_state="ASSIGNED", to_state="IN_PROGRESS", version=1, sequence=1
        ),
        _record(
            identity=identity,
            from_state="IN_PROGRESS",
            to_state="COMPLETED",
            version=3,
            sequence=2,
            reason="accepted",
        ),
    )

    review = _reconstruct_review(
        ReviewReconstructionState(
            identity=identity,
            target=ReviewTargetReference(EvidencePackageId("EVID-0001")),
            reviewer=ReviewerReference("reviewer"),
            state=ReviewLifecycleState.COMPLETED,
            findings=findings,
            disposition=ReviewDisposition.ACCEPTED,
            final_disposition_rationale="accepted",
            cancellation_reason=None,
            version=AggregateVersion(3),
            next_transition_sequence=TransitionSequence(3),
            transition_history=history,
        )
    )

    assert isinstance(review, Review)
    assert review.findings == findings
    assert review.disposition is ReviewDisposition.ACCEPTED
    assert review.final_disposition_rationale == "accepted"
    assert review._next_finding_sequence == 3  # noqa: SLF001


@pytest.mark.parametrize(
    ("factory", "state"),
    (
        (_reconstruct_campaign, "wrong"),
        (_reconstruct_run, "wrong"),
        (_reconstruct_evidence_package, "wrong"),
        (_reconstruct_review, "wrong"),
    ),
)
def test_factories_reject_wrong_state_type(
    factory: Callable[[object], object],
    state: object,
) -> None:
    with pytest.raises(ReconstructionError) as exc_info:
        factory(state)
    assert exc_info.value.category is ReconstructionErrorCategory.WRONG_RECONSTRUCTION_INPUT


def test_malformed_history_cases_are_rejected() -> None:
    identity = _campaign_identity()
    valid = CampaignReconstructionState(
        identity=identity,
        scope_statement=CampaignScopeStatement("scope"),
        state=CampaignLifecycleState.READY_FOR_AUTHORIZATION,
        version=AggregateVersion(1),
        next_transition_sequence=TransitionSequence(2),
        transition_history=(
            _record(
                identity=identity,
                from_state="DRAFT",
                to_state="READY_FOR_AUTHORIZATION",
                version=1,
                sequence=1,
            ),
        ),
    )

    cases = (
        {"transition_history": (), "state": CampaignLifecycleState.READY_FOR_AUTHORIZATION},
        {
            "transition_history": (
                _record(
                    identity=identity,
                    from_state="READY_FOR_AUTHORIZATION",
                    to_state="AUTHORIZED",
                    version=1,
                    sequence=1,
                ),
            )
        },
        {
            "transition_history": (
                _record(
                    identity=identity,
                    from_state="DRAFT",
                    to_state="READY_FOR_AUTHORIZATION",
                    version=1,
                    sequence=2,
                ),
            )
        },
        {
            "transition_history": (
                _record(
                    identity=identity,
                    from_state="DRAFT",
                    to_state="AUTHORIZED",
                    version=1,
                    sequence=1,
                ),
            )
        },
        {"next_transition_sequence": TransitionSequence(3)},
    )
    for updates in cases:
        data = (
            dict(valid.__dict__)
            if hasattr(valid, "__dict__")
            else {
                "identity": valid.identity,
                "scope_statement": valid.scope_statement,
                "state": valid.state,
                "version": valid.version,
                "next_transition_sequence": valid.next_transition_sequence,
                "transition_history": valid.transition_history,
            }
        )
        data.update(updates)
        with pytest.raises(ReconstructionError):
            _reconstruct_campaign(CampaignReconstructionState(**data))


def test_collection_and_terminal_malformed_states_are_rejected() -> None:
    run_identity = _run_identity()
    with pytest.raises(ReconstructionError) as wrong_run:
        _reconstruct_run(
            RunReconstructionState(
                identity=run_identity,
                campaign_id=CampaignId("CAMP-0001"),
                state=RunLifecycleState.CREATED,
                manifests=(_manifest(run_id=RunId("RUN-9999")),),
                version=AggregateVersion(1),
                next_transition_sequence=TransitionSequence.initial(),
                transition_history=(),
            )
        )
    assert wrong_run.value.category is ReconstructionErrorCategory.INVALID_COLLECTION_ELEMENT

    with pytest.raises(ReconstructionError) as duplicate_manifest:
        _reconstruct_run(
            RunReconstructionState(
                identity=run_identity,
                campaign_id=CampaignId("CAMP-0001"),
                state=RunLifecycleState.CREATED,
                manifests=(_manifest(source="a"), _manifest(source="b")),
                version=AggregateVersion(2),
                next_transition_sequence=TransitionSequence.initial(),
                transition_history=(),
            )
        )
    assert duplicate_manifest.value.category is ReconstructionErrorCategory.DUPLICATE_OWNED_VALUE

    package_identity = _package_identity()
    with pytest.raises(ReconstructionError):
        _reconstruct_evidence_package(
            EvidencePackageReconstructionState(
                identity=package_identity,
                run_id=RunId("RUN-0001"),
                state=EvidencePackageLifecycleState.SEALED,
                criterion_results=(),
                artifact_references=(),
                version=AggregateVersion(1),
                next_transition_sequence=TransitionSequence(3),
                transition_history=(
                    _record(
                        identity=package_identity,
                        from_state="INITIALIZED",
                        to_state="COLLECTING",
                        version=1,
                        sequence=1,
                    ),
                    _record(
                        identity=package_identity,
                        from_state="COLLECTING",
                        to_state="SEALED",
                        version=2,
                        sequence=2,
                    ),
                ),
            )
        )

    review_identity = _review_identity()
    with pytest.raises(ReconstructionError):
        _reconstruct_review(
            ReviewReconstructionState(
                identity=review_identity,
                target=ReviewTargetReference(EvidencePackageId("EVID-0001")),
                reviewer=ReviewerReference("reviewer"),
                state=ReviewLifecycleState.COMPLETED,
                findings=(_finding(1),),
                disposition=None,
                final_disposition_rationale=None,
                cancellation_reason=None,
                version=AggregateVersion(2),
                next_transition_sequence=TransitionSequence(3),
                transition_history=(
                    _record(
                        identity=review_identity,
                        from_state="ASSIGNED",
                        to_state="IN_PROGRESS",
                        version=1,
                        sequence=1,
                    ),
                    _record(
                        identity=review_identity,
                        from_state="IN_PROGRESS",
                        to_state="COMPLETED",
                        version=2,
                        sequence=2,
                    ),
                ),
            )
        )


def test_additional_history_and_version_floor_defects_are_rejected() -> None:
    identity = _campaign_identity()
    other_identity = _campaign_identity("CAMP-0002")
    terminal_then_followed = (
        _record(identity=identity, from_state="DRAFT", to_state="CANCELLED", version=1, sequence=1),
        _record(
            identity=identity,
            from_state="CANCELLED",
            to_state="READY_FOR_AUTHORIZATION",
            version=2,
            sequence=2,
        ),
    )
    identity_mismatch = (
        _record(
            identity=other_identity,
            from_state="DRAFT",
            to_state="READY_FOR_AUTHORIZATION",
            version=1,
            sequence=1,
        ),
    )

    for history in (terminal_then_followed, identity_mismatch):
        with pytest.raises(ReconstructionError):
            _reconstruct_campaign(
                CampaignReconstructionState(
                    identity=identity,
                    scope_statement=CampaignScopeStatement("scope"),
                    state=CampaignLifecycleState.READY_FOR_AUTHORIZATION,
                    version=AggregateVersion(2),
                    next_transition_sequence=TransitionSequence(3),
                    transition_history=history,
                )
            )

    with pytest.raises(ReconstructionError) as low_version:
        _reconstruct_run(
            RunReconstructionState(
                identity=_run_identity(),
                campaign_id=CampaignId("CAMP-0001"),
                state=RunLifecycleState.CREATED,
                manifests=(
                    _manifest(manifest_id=DatasetId("DATASET-0001")),
                    _manifest(manifest_id=DatasetId("DATASET-0002")),
                ),
                version=AggregateVersion(1),
                next_transition_sequence=TransitionSequence.initial(),
                transition_history=(),
            )
        )
    assert low_version.value.category is ReconstructionErrorCategory.INVALID_AGGREGATE_VERSION


def test_run_reconstruction_allows_multiple_unidentified_manifests() -> None:
    identity = _run_identity()
    first = DatasetManifest(
        run_id=RunId("RUN-0001"),
        manifest_id=None,
        recorded_at=OCCURRED_AT,
        source="first",
    )
    second = DatasetManifest(
        run_id=RunId("RUN-0001"),
        manifest_id=None,
        recorded_at=OCCURRED_AT,
        source="second",
    )

    run = _reconstruct_run(
        RunReconstructionState(
            identity=identity,
            campaign_id=CampaignId("CAMP-0001"),
            state=RunLifecycleState.CREATED,
            manifests=(first, second),
            version=AggregateVersion(2),
            next_transition_sequence=TransitionSequence.initial(),
            transition_history=(),
        )
    )

    assert run.manifests == (first, second)
    assert run.current_manifest == second


def test_evidence_package_reconstruction_restores_invalidated_package() -> None:
    identity = _package_identity()
    history = (
        _record(
            identity=identity,
            from_state="INITIALIZED",
            to_state="COLLECTING",
            version=1,
            sequence=1,
        ),
        _record(
            identity=identity, from_state="COLLECTING", to_state="SEALED", version=3, sequence=2
        ),
        _record(
            identity=identity,
            from_state="SEALED",
            to_state="INVALIDATED",
            version=4,
            sequence=3,
            reason="digest mismatch",
        ),
    )

    package = _reconstruct_evidence_package(
        EvidencePackageReconstructionState(
            identity=identity,
            run_id=RunId("RUN-0001"),
            state=EvidencePackageLifecycleState.INVALIDATED,
            criterion_results=(_result(),),
            artifact_references=(_artifact(),),
            version=AggregateVersion(4),
            next_transition_sequence=TransitionSequence(4),
            transition_history=history,
        )
    )

    assert package.state is EvidencePackageLifecycleState.INVALIDATED
    assert package.transition_history[-1].reason == "digest mismatch"


def test_review_reconstruction_restores_cancelled_review_and_allows_duplicate_text() -> None:
    identity = _review_identity()
    findings = (_finding(1, "same"), _finding(2, "same"))
    history = (
        _record(
            identity=identity, from_state="ASSIGNED", to_state="IN_PROGRESS", version=1, sequence=1
        ),
        _record(
            identity=identity,
            from_state="IN_PROGRESS",
            to_state="CANCELLED",
            version=3,
            sequence=2,
            reason="scope withdrawn",
        ),
    )

    review = _reconstruct_review(
        ReviewReconstructionState(
            identity=identity,
            target=ReviewTargetReference(EvidencePackageId("EVID-0001")),
            reviewer=ReviewerReference("reviewer"),
            state=ReviewLifecycleState.CANCELLED,
            findings=findings,
            disposition=None,
            final_disposition_rationale=None,
            cancellation_reason="scope withdrawn",
            version=AggregateVersion(3),
            next_transition_sequence=TransitionSequence(3),
            transition_history=history,
        )
    )

    assert review.findings == findings
    assert [finding.text for finding in review.findings] == ["same", "same"]
    assert review.cancellation_reason == "scope withdrawn"
    assert review._next_finding_sequence == 3  # noqa: SLF001


def test_visibility_no_public_exports() -> None:
    modules: tuple[ModuleType, ...] = (
        campaign_exports,
        run_exports,
        evidence_exports,
        review_exports,
    )
    forbidden = {
        "CampaignReconstructionState",
        "RunReconstructionState",
        "EvidencePackageReconstructionState",
        "ReviewReconstructionState",
        "_reconstruct_campaign",
        "_reconstruct_run",
        "_reconstruct_evidence_package",
        "_reconstruct_review",
    }
    for module in modules:
        exported = set(getattr(module, "__all__", ()))
        assert exported.isdisjoint(forbidden)
        for name in forbidden:
            assert not hasattr(module, name)
