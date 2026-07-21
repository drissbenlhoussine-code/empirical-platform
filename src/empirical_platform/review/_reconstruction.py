"""Internal Review reconstruction contract implementation."""

from __future__ import annotations

from dataclasses import dataclass

from empirical_platform.identifiers import DomainIdentity, ReviewId
from empirical_platform.review.aggregate import (
    Review,
    ReviewerReference,
    ReviewFinding,
    ReviewTargetReference,
)
from empirical_platform.review.lifecycle import ReviewDisposition, ReviewLifecycleState
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
class ReviewReconstructionState:
    """Persistence-neutral Review reconstruction state."""

    identity: DomainIdentity[ReviewId]
    target: ReviewTargetReference
    reviewer: ReviewerReference
    state: ReviewLifecycleState
    findings: tuple[ReviewFinding, ...]
    disposition: ReviewDisposition | None
    final_disposition_rationale: str | None
    cancellation_reason: str | None
    version: AggregateVersion
    next_transition_sequence: TransitionSequence
    transition_history: tuple[StateTransitionRecord[DomainIdentity[ReviewId]], ...]

    def __post_init__(self) -> None:
        _require_instance(
            self.identity,
            DomainIdentity,
            category=ReconstructionErrorCategory.INVALID_AGGREGATE_IDENTITY,
            field="identity",
        )
        if not isinstance(self.identity.governance_id, ReviewId):
            raise ReconstructionError(
                ReconstructionErrorCategory.INVALID_AGGREGATE_IDENTITY,
                "identity governance_id must be a ReviewId",
                field="identity",
            )
        _require_instance(
            self.target,
            ReviewTargetReference,
            category=ReconstructionErrorCategory.INVALID_COLLECTION_ELEMENT,
            field="target",
        )
        _require_instance(
            self.reviewer,
            ReviewerReference,
            category=ReconstructionErrorCategory.INVALID_COLLECTION_ELEMENT,
            field="reviewer",
        )
        _require_instance(
            self.state,
            ReviewLifecycleState,
            category=ReconstructionErrorCategory.INVALID_LIFECYCLE_STATE,
            field="state",
        )
        if self.disposition is not None and not isinstance(self.disposition, ReviewDisposition):
            raise ReconstructionError(
                ReconstructionErrorCategory.INCONSISTENT_TERMINAL_METADATA,
                "disposition must be a ReviewDisposition when provided",
                field="disposition",
            )
        _require_optional_str(self.final_disposition_rationale, "final_disposition_rationale")
        _require_optional_str(self.cancellation_reason, "cancellation_reason")
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
            "findings",
            _materialize_tuple(self.findings, element_type=ReviewFinding, field="findings"),
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
    ("ASSIGNED", "IN_PROGRESS"),
    ("IN_PROGRESS", "COMPLETED"),
    ("ASSIGNED", "CANCELLED"),
    ("IN_PROGRESS", "CANCELLED"),
}
_TERMINAL_STATES = {"COMPLETED", "CANCELLED"}


def _reconstruct_review(state: ReviewReconstructionState) -> Review:
    """Restore a Review from validated persistence-neutral state."""
    if not isinstance(state, ReviewReconstructionState):
        raise ReconstructionError(
            ReconstructionErrorCategory.WRONG_RECONSTRUCTION_INPUT,
            "state must be ReviewReconstructionState",
            field="state",
        )
    highest_history_version = _validate_transition_history(
        state.transition_history,
        identity=state.identity,
        current_state=state.state,
        initial_state=ReviewLifecycleState.ASSIGNED,
        allowed_edges=_ALLOWED_EDGES,
        terminal_states=_TERMINAL_STATES,
        next_transition_sequence=state.next_transition_sequence,
        allow_empty_states={"ASSIGNED"},
    )
    _validate_findings(state)
    version_floor = max(highest_history_version.value, len(state.findings))
    if state.version.value < version_floor:
        raise ReconstructionError(
            ReconstructionErrorCategory.INVALID_AGGREGATE_VERSION,
            "Review version is lower than restored state requires",
            field="version",
        )
    _validate_terminal_metadata(state)

    review = object.__new__(Review)
    review._identity = state.identity  # noqa: SLF001
    review._target = state.target  # noqa: SLF001
    review._reviewer = state.reviewer  # noqa: SLF001
    review._state = state.state  # noqa: SLF001
    review._version = state.version  # noqa: SLF001
    review._next_transition_sequence = state.next_transition_sequence  # noqa: SLF001
    review._transition_history = state.transition_history  # noqa: SLF001
    review._findings = state.findings  # noqa: SLF001
    review._next_finding_sequence = (state.findings[-1].sequence + 1) if state.findings else 1  # noqa: SLF001
    review._disposition = state.disposition  # noqa: SLF001
    review._final_disposition_rationale = state.final_disposition_rationale  # noqa: SLF001
    review._cancellation_reason = state.cancellation_reason  # noqa: SLF001
    return review


def _require_optional_str(value: str | None, field: str) -> None:
    if value is None:
        return
    if not isinstance(value, str):
        raise ReconstructionError(
            ReconstructionErrorCategory.INCONSISTENT_TERMINAL_METADATA,
            f"{field} must be a string when provided",
            field=field,
        )


def _validate_findings(state: ReviewReconstructionState) -> None:
    for index, finding in enumerate(state.findings, start=1):
        if finding.sequence != index:
            raise ReconstructionError(
                ReconstructionErrorCategory.INVALID_COLLECTION_ELEMENT,
                "Review finding sequences must be contiguous from 1",
                field="findings",
            )


def _validate_terminal_metadata(state: ReviewReconstructionState) -> None:
    if state.state is ReviewLifecycleState.COMPLETED:
        if not state.findings:
            raise ReconstructionError(
                ReconstructionErrorCategory.INCONSISTENT_TERMINAL_METADATA,
                "completed Review requires at least one finding",
                field="findings",
            )
        if state.disposition is None or not state.final_disposition_rationale:
            raise ReconstructionError(
                ReconstructionErrorCategory.INCONSISTENT_TERMINAL_METADATA,
                "completed Review requires disposition and final rationale",
                field="disposition",
            )
        if state.cancellation_reason is not None:
            raise ReconstructionError(
                ReconstructionErrorCategory.INCONSISTENT_TERMINAL_METADATA,
                "completed Review cannot have cancellation reason",
                field="cancellation_reason",
            )
        return

    if state.state is ReviewLifecycleState.CANCELLED:
        if state.disposition is not None or state.final_disposition_rationale is not None:
            raise ReconstructionError(
                ReconstructionErrorCategory.INCONSISTENT_TERMINAL_METADATA,
                "cancelled Review cannot have final disposition metadata",
                field="disposition",
            )
        if not state.cancellation_reason:
            raise ReconstructionError(
                ReconstructionErrorCategory.INCONSISTENT_TERMINAL_METADATA,
                "cancelled Review requires cancellation reason",
                field="cancellation_reason",
            )
        return

    if (
        state.disposition is not None
        or state.final_disposition_rationale is not None
        or state.cancellation_reason is not None
    ):
        raise ReconstructionError(
            ReconstructionErrorCategory.INCONSISTENT_TERMINAL_METADATA,
            "non-terminal Review cannot have terminal metadata",
            field="state",
        )
