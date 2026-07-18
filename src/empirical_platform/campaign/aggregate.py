"""Process-local Campaign aggregate behavior."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from empirical_platform.campaign.lifecycle import CampaignLifecycleState
from empirical_platform.identifiers import CampaignId, DomainIdentity
from empirical_platform.shared.domain import (
    AggregateVersion,
    StateTransitionRecord,
    TransitionSequence,
)


@dataclass(frozen=True, slots=True)
class CampaignScopeStatement:
    """Immutable Campaign-local scope statement."""

    value: str

    def __post_init__(self) -> None:
        _require_non_empty(self.value, "campaign scope statement")

    def __str__(self) -> str:
        return self.value


class Campaign:
    """Process-local Campaign aggregate root."""

    __slots__ = (
        "_identity",
        "_next_transition_sequence",
        "_scope_statement",
        "_state",
        "_transition_history",
        "_version",
    )

    def __init__(
        self,
        *,
        identity: DomainIdentity[CampaignId],
        scope_statement: CampaignScopeStatement,
    ) -> None:
        if not isinstance(identity, DomainIdentity):
            raise TypeError("identity must be a DomainIdentity[CampaignId]")
        if not isinstance(identity.governance_id, CampaignId):
            raise TypeError("identity governance_id must be a CampaignId")
        if not isinstance(scope_statement, CampaignScopeStatement):
            raise TypeError("scope_statement must be a CampaignScopeStatement")

        self._identity = identity
        self._scope_statement = scope_statement
        self._state = CampaignLifecycleState.DRAFT
        self._version = AggregateVersion.initial()
        self._next_transition_sequence = TransitionSequence.initial()
        self._transition_history: tuple[StateTransitionRecord[DomainIdentity[CampaignId]], ...] = ()

    @property
    def identity(self) -> DomainIdentity[CampaignId]:
        """Return immutable Campaign identity."""
        return self._identity

    @property
    def scope_statement(self) -> CampaignScopeStatement:
        """Return immutable Campaign scope statement."""
        return self._scope_statement

    @property
    def state(self) -> CampaignLifecycleState:
        """Return current Campaign lifecycle state."""
        return self._state

    @property
    def version(self) -> AggregateVersion:
        """Return current aggregate version."""
        return self._version

    @property
    def next_transition_sequence(self) -> TransitionSequence:
        """Return the sequence available for the next lifecycle transition."""
        return self._next_transition_sequence

    @property
    def transition_history(
        self,
    ) -> tuple[StateTransitionRecord[DomainIdentity[CampaignId]], ...]:
        """Return immutable lifecycle transition history."""
        return self._transition_history

    def revise_scope_statement(self, scope_statement: CampaignScopeStatement) -> None:
        """Replace the Campaign scope statement while still in DRAFT."""
        if not isinstance(scope_statement, CampaignScopeStatement):
            raise TypeError("scope_statement must be a CampaignScopeStatement")
        if self._state is not CampaignLifecycleState.DRAFT:
            raise ValueError(
                "scope statement may be revised only while DRAFT; "
                f"current state is {self._state.value}"
            )

        self._version = self._version.next()
        self._scope_statement = scope_statement

    def prepare_for_authorization(
        self,
        *,
        actor: str,
        occurred_at: datetime,
        correlation_id: str | None = None,
        reason: str | None = None,
    ) -> None:
        """Transition from DRAFT to READY_FOR_AUTHORIZATION."""
        self._transition(
            allowed_states=(CampaignLifecycleState.DRAFT,),
            next_state=CampaignLifecycleState.READY_FOR_AUTHORIZATION,
            actor=actor,
            occurred_at=occurred_at,
            correlation_id=correlation_id,
            reason=reason,
        )

    def record_authorization(
        self,
        *,
        reason: str,
        actor: str,
        occurred_at: datetime,
        correlation_id: str | None = None,
    ) -> None:
        """Record local authorization review outcome without executing authority."""
        _require_non_empty(reason, "authorization reason")
        self._transition(
            allowed_states=(CampaignLifecycleState.READY_FOR_AUTHORIZATION,),
            next_state=CampaignLifecycleState.AUTHORIZED,
            actor=actor,
            occurred_at=occurred_at,
            correlation_id=correlation_id,
            reason=reason,
        )

    def activate(
        self,
        *,
        reason: str,
        actor: str,
        occurred_at: datetime,
        correlation_id: str | None = None,
    ) -> None:
        """Record local activation without starting Runs or execution behavior."""
        _require_non_empty(reason, "activation reason")
        self._transition(
            allowed_states=(CampaignLifecycleState.AUTHORIZED,),
            next_state=CampaignLifecycleState.ACTIVE,
            actor=actor,
            occurred_at=occurred_at,
            correlation_id=correlation_id,
            reason=reason,
        )

    def suspend(
        self,
        *,
        reason: str,
        actor: str,
        occurred_at: datetime,
        correlation_id: str | None = None,
    ) -> None:
        """Suspend an active Campaign locally."""
        _require_non_empty(reason, "suspension reason")
        self._transition(
            allowed_states=(CampaignLifecycleState.ACTIVE,),
            next_state=CampaignLifecycleState.SUSPENDED,
            actor=actor,
            occurred_at=occurred_at,
            correlation_id=correlation_id,
            reason=reason,
        )

    def resume(
        self,
        *,
        reason: str,
        actor: str,
        occurred_at: datetime,
        correlation_id: str | None = None,
    ) -> None:
        """Resume a suspended Campaign locally."""
        _require_non_empty(reason, "resume reason")
        self._transition(
            allowed_states=(CampaignLifecycleState.SUSPENDED,),
            next_state=CampaignLifecycleState.ACTIVE,
            actor=actor,
            occurred_at=occurred_at,
            correlation_id=correlation_id,
            reason=reason,
        )

    def complete(
        self,
        *,
        reason: str,
        actor: str,
        occurred_at: datetime,
        correlation_id: str | None = None,
    ) -> None:
        """Record local completion without querying Runs or Reviews."""
        _require_non_empty(reason, "completion reason")
        self._transition(
            allowed_states=(CampaignLifecycleState.ACTIVE,),
            next_state=CampaignLifecycleState.COMPLETED,
            actor=actor,
            occurred_at=occurred_at,
            correlation_id=correlation_id,
            reason=reason,
        )

    def cancel(
        self,
        *,
        actor: str,
        occurred_at: datetime,
        reason: str | None = None,
        correlation_id: str | None = None,
    ) -> None:
        """Cancel the Campaign from an allowed non-terminal state."""
        if self._state in (
            CampaignLifecycleState.AUTHORIZED,
            CampaignLifecycleState.ACTIVE,
            CampaignLifecycleState.SUSPENDED,
        ):
            if reason is None:
                raise TypeError("cancellation reason must be a string")
            _require_non_empty(reason, "cancellation reason")
        else:
            _require_optional_non_empty(reason, "reason")
        self._transition(
            allowed_states=(
                CampaignLifecycleState.DRAFT,
                CampaignLifecycleState.READY_FOR_AUTHORIZATION,
                CampaignLifecycleState.AUTHORIZED,
                CampaignLifecycleState.ACTIVE,
                CampaignLifecycleState.SUSPENDED,
            ),
            next_state=CampaignLifecycleState.CANCELLED,
            actor=actor,
            occurred_at=occurred_at,
            correlation_id=correlation_id,
            reason=reason,
        )

    def _transition(
        self,
        *,
        allowed_states: tuple[CampaignLifecycleState, ...],
        next_state: CampaignLifecycleState,
        actor: str,
        occurred_at: datetime,
        correlation_id: str | None,
        reason: str | None,
    ) -> None:
        if self._state not in allowed_states:
            allowed = ", ".join(state.value for state in allowed_states)
            raise ValueError(f"cannot transition from {self._state.value}; expected {allowed}")
        if not isinstance(occurred_at, datetime):
            raise TypeError("occurred_at must be a datetime")
        _require_non_empty(actor, "actor")
        _require_optional_non_empty(correlation_id, "correlation_id")
        _require_optional_non_empty(reason, "reason")

        next_version = self._version.next()
        current_sequence = self._next_transition_sequence
        next_sequence = current_sequence.next()
        record = StateTransitionRecord(
            from_state=self._state.value,
            to_state=next_state.value,
            version=next_version,
            sequence=current_sequence,
            actor=actor,
            occurred_at=occurred_at,
            identity_reference=self._identity,
            correlation_id=correlation_id,
            reason=reason,
        )
        next_history = (*self._transition_history, record)

        self._state = next_state
        self._version = next_version
        self._next_transition_sequence = next_sequence
        self._transition_history = next_history


def _require_non_empty(value: str, field_name: str) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    if value.strip() == "":
        raise ValueError(f"{field_name} must be non-empty")


def _require_optional_non_empty(value: str | None, field_name: str) -> None:
    if value is None:
        return
    _require_non_empty(value, field_name)
