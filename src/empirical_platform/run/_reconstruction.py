"""Internal Run reconstruction contract implementation."""

from __future__ import annotations

from dataclasses import dataclass

from empirical_platform.campaign.lifecycle import RunLifecycleState
from empirical_platform.datasets import DatasetManifest
from empirical_platform.identifiers import CampaignId, DomainIdentity, RunId
from empirical_platform.run.aggregate import Run
from empirical_platform.shared.domain import (
    AggregateVersion,
    StateTransitionRecord,
    TransitionSequence,
)
from empirical_platform.shared.domain.reconstruction import (
    ReconstructionError,
    ReconstructionErrorCategory,
    _materialize_tuple,
    _require_instance,
    _validate_transition_history,
)


@dataclass(frozen=True, slots=True)
class RunReconstructionState:
    """Persistence-neutral Run reconstruction state."""

    identity: DomainIdentity[RunId]
    campaign_id: CampaignId
    state: RunLifecycleState
    manifests: tuple[DatasetManifest, ...]
    version: AggregateVersion
    next_transition_sequence: TransitionSequence
    transition_history: tuple[StateTransitionRecord[DomainIdentity[RunId]], ...]

    def __post_init__(self) -> None:
        _require_instance(
            self.identity,
            DomainIdentity,
            category=ReconstructionErrorCategory.INVALID_AGGREGATE_IDENTITY,
            field="identity",
        )
        if not isinstance(self.identity.governance_id, RunId):
            raise ReconstructionError(
                ReconstructionErrorCategory.INVALID_AGGREGATE_IDENTITY,
                "identity governance_id must be a RunId",
                field="identity",
            )
        _require_instance(
            self.campaign_id,
            CampaignId,
            category=ReconstructionErrorCategory.INVALID_AGGREGATE_IDENTITY,
            field="campaign_id",
        )
        _require_instance(
            self.state,
            RunLifecycleState,
            category=ReconstructionErrorCategory.INVALID_LIFECYCLE_STATE,
            field="state",
        )
        _require_instance(
            self.version,
            AggregateVersion,
            category=ReconstructionErrorCategory.INVALID_AGGREGATE_VERSION,
            field="version",
        )
        _require_instance(
            self.next_transition_sequence,
            TransitionSequence,
            category=ReconstructionErrorCategory.INVALID_TRANSITION_SEQUENCE,
            field="next_transition_sequence",
        )
        object.__setattr__(
            self,
            "manifests",
            _materialize_tuple(self.manifests, element_type=DatasetManifest, field="manifests"),
        )
        object.__setattr__(
            self,
            "transition_history",
            _materialize_tuple(
                self.transition_history,
                element_type=StateTransitionRecord,
                field="transition_history",
            ),
        )


_ALLOWED_EDGES = {
    ("CREATED", "AUTHORIZED"),
    ("AUTHORIZED", "ACQUIRING"),
    ("ACQUIRING", "NORMALIZING"),
    ("NORMALIZING", "VALIDATING"),
    ("VALIDATING", "EXECUTION_COMPLETED"),
    ("AUTHORIZED", "CANCELLED"),
    ("ACQUIRING", "FAILED"),
    ("NORMALIZING", "FAILED"),
    ("VALIDATING", "FAILED"),
}
_TERMINAL_STATES = {"EXECUTION_COMPLETED", "FAILED", "CANCELLED"}


def _reconstruct_run(state: RunReconstructionState) -> Run:
    """Restore a Run from validated persistence-neutral state."""
    if not isinstance(state, RunReconstructionState):
        raise ReconstructionError(
            ReconstructionErrorCategory.WRONG_RECONSTRUCTION_INPUT,
            "state must be RunReconstructionState",
            field="state",
        )
    highest_history_version = _validate_transition_history(
        state.transition_history,
        identity=state.identity,
        current_state=state.state,
        initial_state=RunLifecycleState.CREATED,
        allowed_edges=_ALLOWED_EDGES,
        terminal_states=_TERMINAL_STATES,
        next_transition_sequence=state.next_transition_sequence,
        allow_empty_states={"CREATED"},
    )
    _validate_manifests(state)
    version_floor = max(highest_history_version.value, len(state.manifests))
    if state.version.value < version_floor:
        raise ReconstructionError(
            ReconstructionErrorCategory.INVALID_AGGREGATE_VERSION,
            "Run version is lower than restored state requires",
            field="version",
        )
    _validate_terminal_reason(state)

    run = object.__new__(Run)
    run._identity = state.identity  # noqa: SLF001
    run._campaign_id = state.campaign_id  # noqa: SLF001
    run._state = state.state  # noqa: SLF001
    run._version = state.version  # noqa: SLF001
    run._next_transition_sequence = state.next_transition_sequence  # noqa: SLF001
    run._transition_history = state.transition_history  # noqa: SLF001
    run._manifests = state.manifests  # noqa: SLF001
    return run


def _validate_manifests(state: RunReconstructionState) -> None:
    seen_manifest_ids: set[object] = set()
    for manifest in state.manifests:
        if manifest.run_id != state.identity.governance_id:
            raise ReconstructionError(
                ReconstructionErrorCategory.INVALID_COLLECTION_ELEMENT,
                "Dataset Manifest run_id must match Run identity",
                field="manifests",
            )
        if manifest.manifest_id is None:
            continue
        if manifest.manifest_id in seen_manifest_ids:
            raise ReconstructionError(
                ReconstructionErrorCategory.DUPLICATE_OWNED_VALUE,
                "Dataset Manifest manifest_id already exists in Run",
                field="manifests",
            )
        seen_manifest_ids.add(manifest.manifest_id)


def _validate_terminal_reason(state: RunReconstructionState) -> None:
    if state.state not in (RunLifecycleState.FAILED, RunLifecycleState.CANCELLED):
        return
    if not state.transition_history or state.transition_history[-1].reason is None:
        raise ReconstructionError(
            ReconstructionErrorCategory.INCONSISTENT_TERMINAL_METADATA,
            "Run failure or cancellation requires a final transition reason",
            field="transition_history",
        )
