"""Internal Campaign reconstruction contract implementation."""

from __future__ import annotations

from dataclasses import dataclass

from empirical_platform.campaign.aggregate import Campaign, CampaignScopeStatement
from empirical_platform.campaign.lifecycle import CampaignLifecycleState
from empirical_platform.identifiers import CampaignId, DomainIdentity
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
class CampaignReconstructionState:
    """Persistence-neutral Campaign reconstruction state."""

    identity: DomainIdentity[CampaignId]
    scope_statement: CampaignScopeStatement
    state: CampaignLifecycleState
    version: AggregateVersion
    next_transition_sequence: TransitionSequence
    transition_history: tuple[StateTransitionRecord[DomainIdentity[CampaignId]], ...]

    def __post_init__(self) -> None:
        _require_instance(
            self.identity,
            DomainIdentity,
            category=ReconstructionErrorCategory.INVALID_AGGREGATE_IDENTITY,
            field="identity",
        )
        if not isinstance(self.identity.governance_id, CampaignId):
            raise ReconstructionError(
                ReconstructionErrorCategory.INVALID_AGGREGATE_IDENTITY,
                "identity governance_id must be a CampaignId",
                field="identity",
            )
        _require_instance(
            self.scope_statement,
            CampaignScopeStatement,
            category=ReconstructionErrorCategory.INVALID_COLLECTION_ELEMENT,
            field="scope_statement",
        )
        _require_instance(
            self.state,
            CampaignLifecycleState,
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
            "transition_history",
            _materialize_tuple(
                self.transition_history,
                element_type=StateTransitionRecord,
                field="transition_history",
            ),
        )


_ALLOWED_EDGES = {
    ("DRAFT", "READY_FOR_AUTHORIZATION"),
    ("READY_FOR_AUTHORIZATION", "AUTHORIZED"),
    ("AUTHORIZED", "ACTIVE"),
    ("ACTIVE", "SUSPENDED"),
    ("SUSPENDED", "ACTIVE"),
    ("ACTIVE", "COMPLETED"),
    ("DRAFT", "CANCELLED"),
    ("READY_FOR_AUTHORIZATION", "CANCELLED"),
    ("AUTHORIZED", "CANCELLED"),
    ("ACTIVE", "CANCELLED"),
    ("SUSPENDED", "CANCELLED"),
}
_TERMINAL_STATES = {"COMPLETED", "CANCELLED"}


def _reconstruct_campaign(state: CampaignReconstructionState) -> Campaign:
    """Restore a Campaign from validated persistence-neutral state."""
    if not isinstance(state, CampaignReconstructionState):
        raise ReconstructionError(
            ReconstructionErrorCategory.WRONG_RECONSTRUCTION_INPUT,
            "state must be CampaignReconstructionState",
            field="state",
        )
    highest_history_version = _validate_transition_history(
        state.transition_history,
        identity=state.identity,
        current_state=state.state,
        initial_state=CampaignLifecycleState.DRAFT,
        allowed_edges=_ALLOWED_EDGES,
        terminal_states=_TERMINAL_STATES,
        next_transition_sequence=state.next_transition_sequence,
        allow_empty_states={"DRAFT"},
    )
    if state.version < highest_history_version:
        raise ReconstructionError(
            ReconstructionErrorCategory.INVALID_AGGREGATE_VERSION,
            "Campaign version is lower than transition history requires",
            field="version",
        )
    _validate_campaign_terminal_reason(state)

    campaign = object.__new__(Campaign)
    campaign._identity = state.identity  # noqa: SLF001
    campaign._scope_statement = state.scope_statement  # noqa: SLF001
    campaign._state = state.state  # noqa: SLF001
    campaign._version = state.version  # noqa: SLF001
    campaign._next_transition_sequence = state.next_transition_sequence  # noqa: SLF001
    campaign._transition_history = state.transition_history  # noqa: SLF001
    return campaign


def _validate_campaign_terminal_reason(state: CampaignReconstructionState) -> None:
    if not state.transition_history:
        return
    required_reason_edges = {
        ("READY_FOR_AUTHORIZATION", "AUTHORIZED"),
        ("AUTHORIZED", "ACTIVE"),
        ("ACTIVE", "SUSPENDED"),
        ("SUSPENDED", "ACTIVE"),
        ("ACTIVE", "COMPLETED"),
        ("AUTHORIZED", "CANCELLED"),
        ("ACTIVE", "CANCELLED"),
        ("SUSPENDED", "CANCELLED"),
    }
    for record in state.transition_history:
        if (record.from_state or "", record.to_state) in required_reason_edges:
            if record.reason is None:
                raise ReconstructionError(
                    ReconstructionErrorCategory.INCONSISTENT_TERMINAL_METADATA,
                    "Campaign transition requires a reason",
                    field="transition_history",
                )
    final_record = state.transition_history[-1]
    if state.state is CampaignLifecycleState.CANCELLED and final_record.from_state in {
        "AUTHORIZED",
        "ACTIVE",
        "SUSPENDED",
    }:
        if final_record.reason is None:
            raise ReconstructionError(
                ReconstructionErrorCategory.INCONSISTENT_TERMINAL_METADATA,
                "post-authorization Campaign cancellation requires a reason",
                field="transition_history",
            )
