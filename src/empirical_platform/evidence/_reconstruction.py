"""Internal Evidence Package reconstruction contract implementation."""

from __future__ import annotations

from dataclasses import dataclass

from empirical_platform.evidence.lifecycle import EvidencePackageLifecycleState
from empirical_platform.evidence.package import ArtifactReference, EvidencePackage
from empirical_platform.evidence.results import CriterionResult
from empirical_platform.identifiers import DomainIdentity, EvidencePackageId, RunId
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
class EvidencePackageReconstructionState:
    """Persistence-neutral Evidence Package reconstruction state."""

    identity: DomainIdentity[EvidencePackageId]
    run_id: RunId
    state: EvidencePackageLifecycleState
    criterion_results: tuple[CriterionResult, ...]
    artifact_references: tuple[ArtifactReference, ...]
    version: AggregateVersion
    next_transition_sequence: TransitionSequence
    transition_history: tuple[StateTransitionRecord[DomainIdentity[EvidencePackageId]], ...]

    def __post_init__(self) -> None:
        _require_instance(
            self.identity,
            DomainIdentity,
            category=ReconstructionErrorCategory.INVALID_AGGREGATE_IDENTITY,
            field="identity",
        )
        if not isinstance(self.identity.governance_id, EvidencePackageId):
            raise ReconstructionError(
                ReconstructionErrorCategory.INVALID_AGGREGATE_IDENTITY,
                "identity governance_id must be an EvidencePackageId",
                field="identity",
            )
        _require_instance(
            self.run_id,
            RunId,
            category=ReconstructionErrorCategory.INVALID_AGGREGATE_IDENTITY,
            field="run_id",
        )
        _require_instance(
            self.state,
            EvidencePackageLifecycleState,
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
            "criterion_results",
            _materialize_tuple(
                self.criterion_results,
                element_type=CriterionResult,
                field="criterion_results",
            ),
        )
        object.__setattr__(
            self,
            "artifact_references",
            _materialize_tuple(
                self.artifact_references,
                element_type=ArtifactReference,
                field="artifact_references",
            ),
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
    ("INITIALIZED", "COLLECTING"),
    ("COLLECTING", "SEALED"),
    ("SEALED", "INVALIDATED"),
}
_TERMINAL_STATES = {"INVALIDATED"}


def _reconstruct_evidence_package(
    state: EvidencePackageReconstructionState,
) -> EvidencePackage:
    """Restore an Evidence Package from validated persistence-neutral state."""
    if not isinstance(state, EvidencePackageReconstructionState):
        raise ReconstructionError(
            ReconstructionErrorCategory.WRONG_RECONSTRUCTION_INPUT,
            "state must be EvidencePackageReconstructionState",
            field="state",
        )
    highest_history_version = _validate_transition_history(
        state.transition_history,
        identity=state.identity,
        current_state=state.state,
        initial_state=EvidencePackageLifecycleState.INITIALIZED,
        allowed_edges=_ALLOWED_EDGES,
        terminal_states=_TERMINAL_STATES,
        next_transition_sequence=state.next_transition_sequence,
        allow_empty_states={"INITIALIZED"},
    )
    _validate_contents(state)
    version_floor = max(
        highest_history_version.value,
        len(state.criterion_results) + len(state.artifact_references),
    )
    if state.version.value < version_floor:
        raise ReconstructionError(
            ReconstructionErrorCategory.INVALID_AGGREGATE_VERSION,
            "Evidence Package version is lower than restored state requires",
            field="version",
        )
    _validate_lifecycle_content_compatibility(state)

    package = object.__new__(EvidencePackage)
    package._identity = state.identity  # noqa: SLF001
    package._run_id = state.run_id  # noqa: SLF001
    package._state = state.state  # noqa: SLF001
    package._version = state.version  # noqa: SLF001
    package._next_transition_sequence = state.next_transition_sequence  # noqa: SLF001
    package._transition_history = state.transition_history  # noqa: SLF001
    package._criterion_results = state.criterion_results  # noqa: SLF001
    package._artifact_references = state.artifact_references  # noqa: SLF001
    return package


def _validate_contents(state: EvidencePackageReconstructionState) -> None:
    seen_criterion_ids: set[str] = set()
    for result in state.criterion_results:
        if result.evidence_package_id != state.identity.governance_id:
            raise ReconstructionError(
                ReconstructionErrorCategory.INVALID_COLLECTION_ELEMENT,
                "Criterion Result evidence_package_id must match Evidence Package identity",
                field="criterion_results",
            )
        if result.criterion_id in seen_criterion_ids:
            raise ReconstructionError(
                ReconstructionErrorCategory.DUPLICATE_OWNED_VALUE,
                "Criterion Result criterion_id already exists in Evidence Package",
                field="criterion_results",
            )
        seen_criterion_ids.add(result.criterion_id)

    seen_references: set[str] = set()
    for reference in state.artifact_references:
        if reference.value in seen_references:
            raise ReconstructionError(
                ReconstructionErrorCategory.DUPLICATE_OWNED_VALUE,
                "artifact reference already exists in Evidence Package",
                field="artifact_references",
            )
        seen_references.add(reference.value)


def _validate_lifecycle_content_compatibility(
    state: EvidencePackageReconstructionState,
) -> None:
    has_results = bool(state.criterion_results)
    has_references = bool(state.artifact_references)
    if state.state is EvidencePackageLifecycleState.INITIALIZED and (has_results or has_references):
        raise ReconstructionError(
            ReconstructionErrorCategory.INCONSISTENT_CURRENT_STATE,
            "INITIALIZED Evidence Package cannot contain results or artifact references",
            field="state",
        )
    if state.state in (
        EvidencePackageLifecycleState.SEALED,
        EvidencePackageLifecycleState.INVALIDATED,
    ) and not (has_results and has_references):
        raise ReconstructionError(
            ReconstructionErrorCategory.INCONSISTENT_CURRENT_STATE,
            "terminal Evidence Package state requires results and artifact references",
            field="state",
        )
    if state.state is EvidencePackageLifecycleState.INVALIDATED:
        if not state.transition_history or state.transition_history[-1].reason is None:
            raise ReconstructionError(
                ReconstructionErrorCategory.INCONSISTENT_TERMINAL_METADATA,
                "invalidated Evidence Package requires final transition reason",
                field="transition_history",
            )
