from __future__ import annotations

from datetime import UTC, datetime

import pytest

from empirical_platform.campaign import RunLifecycleState
from empirical_platform.datasets import DatasetManifest
from empirical_platform.identifiers import CampaignId, DatasetId, DomainIdentity, ReviewId, RunId
from empirical_platform.run import Run
from empirical_platform.shared.domain import AggregateVersion, TransitionSequence
from empirical_platform.shared.identifiers import RuntimeIdentifier

OCCURRED_AT = datetime(2026, 7, 18, tzinfo=UTC)
_DEFAULT_MANIFEST_ID = object()


def _identity(value: str = "RUN-0001") -> DomainIdentity[RunId]:
    return DomainIdentity(
        governance_id=RunId(value),
        runtime_id=RuntimeIdentifier("123e4567-e89b-42d3-a456-426614174017"),
    )


def _run(value: str = "RUN-0001") -> Run:
    return Run(identity=_identity(value), campaign_id=CampaignId("CAMP-0001"))


def _manifest(
    *,
    run_id: RunId | None = None,
    manifest_id: DatasetId | None | object = _DEFAULT_MANIFEST_ID,
    source: str = "raw capture manifest",
) -> DatasetManifest:
    resolved_manifest_id: DatasetId | None
    if manifest_id is _DEFAULT_MANIFEST_ID:
        resolved_manifest_id = DatasetId("DATASET-0001")
    elif manifest_id is None or isinstance(manifest_id, DatasetId):
        resolved_manifest_id = manifest_id
    else:
        raise TypeError("manifest_id must be a DatasetId or None")
    return DatasetManifest(
        run_id=run_id if run_id is not None else RunId("RUN-0001"),
        manifest_id=resolved_manifest_id,
        recorded_at=OCCURRED_AT,
        source=source,
        acquisition_method="manual fixture",
        normalization_method="canonical transform",
        notes=("process-local note",),
    )


def _snapshot(run: Run) -> tuple[object, ...]:
    return (
        run.identity,
        run.campaign_id,
        run.state,
        run.version,
        run.next_transition_sequence,
        run.transition_history,
        run.manifests,
        run.current_manifest,
    )


def _authorized_run() -> Run:
    run = _run()
    run.authorize(actor="Campaign Operator", occurred_at=OCCURRED_AT)
    return run


def _acquiring_run() -> Run:
    run = _authorized_run()
    run.start_acquisition(actor="Run Operator", occurred_at=OCCURRED_AT)
    return run


def _normalizing_run() -> Run:
    run = _acquiring_run()
    run.start_normalization(actor="Run Operator", occurred_at=OCCURRED_AT)
    return run


def _validating_run() -> Run:
    run = _normalizing_run()
    run.start_validation(actor="Run Operator", occurred_at=OCCURRED_AT)
    return run


def test_construction_sets_identity_campaign_lifecycle_version_sequence_and_empty_manifests() -> (
    None
):
    identity = _identity()
    run = Run(identity=identity, campaign_id=CampaignId("CAMP-0001"))

    assert run.identity == identity
    assert run.campaign_id == CampaignId("CAMP-0001")
    assert run.state is RunLifecycleState.CREATED
    assert run.version == AggregateVersion.initial()
    assert run.next_transition_sequence == TransitionSequence.initial()
    assert run.transition_history == ()
    assert run.manifests == ()
    assert run.current_manifest is None


def test_construction_rejects_wrong_identity_and_campaign_context() -> None:
    with pytest.raises(TypeError, match="DomainIdentity"):
        Run(identity=RunId("RUN-0001"), campaign_id=CampaignId("CAMP-0001"))  # type: ignore[arg-type]

    with pytest.raises(TypeError, match="RunId"):
        Run(
            identity=DomainIdentity(
                governance_id=ReviewId("REVIEW-0001"),
                runtime_id=RuntimeIdentifier("123e4567-e89b-42d3-a456-426614174017"),
            ),
            campaign_id=CampaignId("CAMP-0001"),
        )

    with pytest.raises(TypeError, match="CampaignId"):
        Run(identity=_identity(), campaign_id=RunId("RUN-0001"))  # type: ignore[arg-type]


def test_identity_and_campaign_context_have_no_mutation_surface() -> None:
    run = _run()

    assert not hasattr(run, "set_identity")
    assert not hasattr(run, "set_campaign_id")
    assert not hasattr(run, "campaign")
    assert not hasattr(run, "load_campaign")


@pytest.mark.parametrize(
    ("method_name", "from_state", "to_state", "actor", "reason"),
    (
        (
            "authorize",
            RunLifecycleState.CREATED,
            RunLifecycleState.AUTHORIZED,
            "Campaign Operator",
            None,
        ),
        (
            "start_acquisition",
            RunLifecycleState.AUTHORIZED,
            RunLifecycleState.ACQUIRING,
            "Run Operator",
            None,
        ),
        (
            "start_normalization",
            RunLifecycleState.ACQUIRING,
            RunLifecycleState.NORMALIZING,
            "Run Operator",
            None,
        ),
        (
            "start_validation",
            RunLifecycleState.NORMALIZING,
            RunLifecycleState.VALIDATING,
            "Run Operator",
            None,
        ),
        (
            "complete_execution",
            RunLifecycleState.VALIDATING,
            RunLifecycleState.EXECUTION_COMPLETED,
            "Run Operator",
            None,
        ),
        (
            "cancel",
            RunLifecycleState.AUTHORIZED,
            RunLifecycleState.CANCELLED,
            "Campaign Operator",
            "no execution should begin",
        ),
        (
            "fail",
            RunLifecycleState.ACQUIRING,
            RunLifecycleState.FAILED,
            "Run Operator",
            "acquisition failure",
        ),
        (
            "fail",
            RunLifecycleState.NORMALIZING,
            RunLifecycleState.FAILED,
            "Run Operator",
            "normalization failure",
        ),
        (
            "fail",
            RunLifecycleState.VALIDATING,
            RunLifecycleState.FAILED,
            "Run Operator",
            "validation failure",
        ),
    ),
)
def test_every_allowed_lifecycle_transition_records_one_history_entry(
    method_name: str,
    from_state: RunLifecycleState,
    to_state: RunLifecycleState,
    actor: str,
    reason: str | None,
) -> None:
    run = _run_at_state(from_state)
    before_version = run.version
    before_sequence = run.next_transition_sequence
    before_history_length = len(run.transition_history)

    kwargs = {
        "actor": actor,
        "occurred_at": OCCURRED_AT,
        "correlation_id": "corr-1",
    }
    if reason is not None:
        kwargs["reason"] = reason
    getattr(run, method_name)(**kwargs)

    assert run.state is to_state
    assert run.version == before_version.next()
    assert run.next_transition_sequence == before_sequence.next()
    assert len(run.transition_history) == before_history_length + 1
    record = run.transition_history[-1]
    assert record.from_state == from_state.value
    assert record.to_state == to_state.value
    assert record.version == before_version.next()
    assert record.sequence == before_sequence
    assert record.actor == actor
    assert record.occurred_at == OCCURRED_AT
    assert record.identity_reference == run.identity
    assert record.correlation_id == "corr-1"
    assert record.reason == reason


def test_invalid_lifecycle_operations_are_atomic_from_every_state() -> None:
    operations = {
        "authorize": {"actor": "Campaign Operator", "occurred_at": OCCURRED_AT},
        "start_acquisition": {"actor": "Run Operator", "occurred_at": OCCURRED_AT},
        "start_normalization": {"actor": "Run Operator", "occurred_at": OCCURRED_AT},
        "start_validation": {"actor": "Run Operator", "occurred_at": OCCURRED_AT},
        "complete_execution": {"actor": "Run Operator", "occurred_at": OCCURRED_AT},
        "cancel": {
            "reason": "no execution should begin",
            "actor": "Campaign Operator",
            "occurred_at": OCCURRED_AT,
        },
        "fail": {
            "reason": "execution failure",
            "actor": "Run Operator",
            "occurred_at": OCCURRED_AT,
        },
    }
    allowed = {
        (RunLifecycleState.CREATED, "authorize"),
        (RunLifecycleState.AUTHORIZED, "start_acquisition"),
        (RunLifecycleState.AUTHORIZED, "cancel"),
        (RunLifecycleState.ACQUIRING, "start_normalization"),
        (RunLifecycleState.ACQUIRING, "fail"),
        (RunLifecycleState.NORMALIZING, "start_validation"),
        (RunLifecycleState.NORMALIZING, "fail"),
        (RunLifecycleState.VALIDATING, "complete_execution"),
        (RunLifecycleState.VALIDATING, "fail"),
    }

    for state in RunLifecycleState:
        for operation_name, kwargs in operations.items():
            if (state, operation_name) in allowed:
                continue
            run = _run_at_state(state)
            before = _snapshot(run)
            with pytest.raises(ValueError, match=state.value):
                getattr(run, operation_name)(**kwargs)
            assert _snapshot(run) == before


def test_lifecycle_transition_rejects_invalid_metadata_without_mutation() -> None:
    for kwargs, error in (
        ({"actor": " ", "occurred_at": OCCURRED_AT}, "actor"),
        ({"actor": "Campaign Operator", "occurred_at": "now"}, "datetime"),
        (
            {
                "actor": "Campaign Operator",
                "occurred_at": OCCURRED_AT,
                "correlation_id": " ",
            },
            "correlation_id",
        ),
        (
            {"actor": "Campaign Operator", "occurred_at": OCCURRED_AT, "reason": " "},
            "reason",
        ),
    ):
        run = _run()
        before = _snapshot(run)
        with pytest.raises((TypeError, ValueError), match=error):
            run.authorize(**kwargs)  # type: ignore[arg-type]
        assert _snapshot(run) == before


def test_cancel_and_fail_require_reasons_without_partial_mutation() -> None:
    authorized = _authorized_run()
    before_authorized = _snapshot(authorized)
    with pytest.raises(ValueError, match="cancellation reason"):
        authorized.cancel(reason=" ", actor="Campaign Operator", occurred_at=OCCURRED_AT)
    assert _snapshot(authorized) == before_authorized

    acquiring = _acquiring_run()
    before_acquiring = _snapshot(acquiring)
    with pytest.raises(TypeError, match="failure reason"):
        acquiring.fail(reason=123, actor="Run Operator", occurred_at=OCCURRED_AT)  # type: ignore[arg-type]
    assert _snapshot(acquiring) == before_acquiring


@pytest.mark.parametrize(
    "state",
    (
        RunLifecycleState.CREATED,
        RunLifecycleState.AUTHORIZED,
        RunLifecycleState.ACQUIRING,
        RunLifecycleState.NORMALIZING,
        RunLifecycleState.VALIDATING,
    ),
)
def test_manifest_append_is_allowed_before_terminal_states(state: RunLifecycleState) -> None:
    run = _run_at_state(state)
    before_version = run.version
    before_sequence = run.next_transition_sequence
    before_history = run.transition_history
    manifest = _manifest()

    run.append_manifest(manifest)

    assert run.manifests == (manifest,)
    assert run.current_manifest == manifest
    assert run.version == before_version.next()
    assert run.next_transition_sequence == before_sequence
    assert run.transition_history == before_history


@pytest.mark.parametrize(
    "state",
    (
        RunLifecycleState.EXECUTION_COMPLETED,
        RunLifecycleState.FAILED,
        RunLifecycleState.CANCELLED,
    ),
)
def test_manifest_append_is_rejected_after_terminal_states(state: RunLifecycleState) -> None:
    run = _run_at_state(state)
    before = _snapshot(run)

    with pytest.raises(ValueError, match=state.value):
        run.append_manifest(_manifest())

    assert _snapshot(run) == before


def test_manifest_append_rejects_wrong_type_wrong_run_and_duplicate_identity_atomically() -> None:
    run = _authorized_run()

    before_type = _snapshot(run)
    with pytest.raises(TypeError, match="DatasetManifest"):
        run.append_manifest("manifest")  # type: ignore[arg-type]
    assert _snapshot(run) == before_type

    before_wrong_run = _snapshot(run)
    with pytest.raises(ValueError, match="run_id"):
        run.append_manifest(
            _manifest(run_id=RunId("RUN-9999"), manifest_id=DatasetId("DATASET-0099"))
        )
    assert _snapshot(run) == before_wrong_run

    first = _manifest(manifest_id=DatasetId("DATASET-0001"), source="first")
    run.append_manifest(first)
    before_duplicate = _snapshot(run)
    with pytest.raises(ValueError, match="manifest_id"):
        run.append_manifest(_manifest(manifest_id=DatasetId("DATASET-0001"), source="duplicate"))
    assert _snapshot(run) == before_duplicate


def test_manifest_append_allows_multiple_unidentified_manifests_in_order() -> None:
    run = _authorized_run()
    first = _manifest(manifest_id=None, source="first")
    second = _manifest(manifest_id=None, source="second")

    run.append_manifest(first)
    run.append_manifest(second)

    assert run.manifests == (first, second)
    assert run.current_manifest == second
    assert run.version == AggregateVersion(3)
    assert run.next_transition_sequence == TransitionSequence(2)
    assert len(run.transition_history) == 1


def test_supersession_is_append_only_and_does_not_mutate_prior_manifest() -> None:
    run = _authorized_run()
    first = _manifest(manifest_id=DatasetId("DATASET-0001"), source="first")
    superseding = _manifest(manifest_id=DatasetId("DATASET-0002"), source="superseding")

    run.append_manifest(first)
    run.append_manifest(superseding)

    assert run.manifests[0] == first
    assert run.manifests[1] == superseding
    assert run.current_manifest == superseding
    assert not hasattr(first, "superseded_by")
    assert not hasattr(run, "replace_manifest")
    assert not hasattr(run, "remove_manifest")
    assert not hasattr(run, "reorder_manifests")


def test_manifest_collection_view_is_immutable_and_caller_reference_safe() -> None:
    run = _authorized_run()
    manifest = _manifest()
    run.append_manifest(manifest)

    with pytest.raises(AttributeError):
        run.manifests.append(_manifest(manifest_id=DatasetId("DATASET-0002")))  # type: ignore[attr-defined]
    assert run.manifests == (manifest,)
    assert run.current_manifest == manifest


def test_mixed_sequence_has_exact_cumulative_version_sequence_history_and_manifest_order() -> None:
    run = _run()
    first = _manifest(manifest_id=DatasetId("DATASET-0001"), source="created-scope")
    second = _manifest(manifest_id=DatasetId("DATASET-0002"), source="normalized-scope")

    run.append_manifest(first)
    run.authorize(actor="Campaign Operator", occurred_at=OCCURRED_AT)
    run.start_acquisition(actor="Run Operator", occurred_at=OCCURRED_AT)
    run.append_manifest(second)
    run.start_normalization(actor="Run Operator", occurred_at=OCCURRED_AT)
    run.start_validation(actor="Run Operator", occurred_at=OCCURRED_AT)
    run.complete_execution(actor="Run Operator", occurred_at=OCCURRED_AT)

    assert run.state is RunLifecycleState.EXECUTION_COMPLETED
    assert run.version == AggregateVersion(7)
    assert run.next_transition_sequence == TransitionSequence(6)
    assert run.manifests == (first, second)
    assert run.current_manifest == second
    assert [record.to_state for record in run.transition_history] == [
        "AUTHORIZED",
        "ACQUIRING",
        "NORMALIZING",
        "VALIDATING",
        "EXECUTION_COMPLETED",
    ]
    assert [record.sequence for record in run.transition_history] == [
        TransitionSequence(1),
        TransitionSequence(2),
        TransitionSequence(3),
        TransitionSequence(4),
        TransitionSequence(5),
    ]
    assert [record.version for record in run.transition_history] == [
        AggregateVersion(2),
        AggregateVersion(3),
        AggregateVersion(5),
        AggregateVersion(6),
        AggregateVersion(7),
    ]


def test_terminal_immutability_blocks_lifecycle_and_manifest_mutation() -> None:
    terminal_runs = (
        _run_at_state(RunLifecycleState.EXECUTION_COMPLETED),
        _run_at_state(RunLifecycleState.FAILED),
        _run_at_state(RunLifecycleState.CANCELLED),
    )

    for run in terminal_runs:
        before = _snapshot(run)
        with pytest.raises(ValueError, match=run.state.value):
            run.append_manifest(_manifest(manifest_id=DatasetId("DATASET-0099")))
        with pytest.raises(ValueError, match=run.state.value):
            run.authorize(actor="Campaign Operator", occurred_at=OCCURRED_AT)
        with pytest.raises(ValueError, match=run.state.value):
            run.start_acquisition(actor="Run Operator", occurred_at=OCCURRED_AT)
        assert _snapshot(run) == before

    assert not hasattr(terminal_runs[0], "reopen")
    assert not hasattr(terminal_runs[0], "restart")
    assert not hasattr(terminal_runs[0], "retry")


def test_run_has_no_deferred_infrastructure_or_cross_aggregate_surface() -> None:
    run = _authorized_run()

    assert not hasattr(run, "save")
    assert not hasattr(run, "load")
    assert not hasattr(run, "repository")
    assert not hasattr(run, "session")
    assert not hasattr(run, "database")
    assert not hasattr(run, "bucket")
    assert not hasattr(run, "object_key")
    assert not hasattr(run, "dispatch")
    assert not hasattr(run, "evidence_package")
    assert not hasattr(run, "review")
    assert not hasattr(run, "audit")
    assert not hasattr(run, "decision_candidate")


def _run_at_state(state: RunLifecycleState) -> Run:
    run = _run()
    if state is RunLifecycleState.CREATED:
        return run

    run.authorize(actor="Campaign Operator", occurred_at=OCCURRED_AT)
    if state in (RunLifecycleState.AUTHORIZED, RunLifecycleState.CANCELLED):
        if state is RunLifecycleState.CANCELLED:
            run.cancel(
                reason="no execution should begin",
                actor="Campaign Operator",
                occurred_at=OCCURRED_AT,
            )
        return run

    run.start_acquisition(actor="Run Operator", occurred_at=OCCURRED_AT)
    if state in (RunLifecycleState.ACQUIRING, RunLifecycleState.FAILED):
        if state is RunLifecycleState.FAILED:
            run.fail(
                reason="acquisition failure",
                actor="Run Operator",
                occurred_at=OCCURRED_AT,
            )
        return run

    run.start_normalization(actor="Run Operator", occurred_at=OCCURRED_AT)
    if state is RunLifecycleState.NORMALIZING:
        return run

    run.start_validation(actor="Run Operator", occurred_at=OCCURRED_AT)
    if state is RunLifecycleState.VALIDATING:
        return run

    run.complete_execution(actor="Run Operator", occurred_at=OCCURRED_AT)
    return run
