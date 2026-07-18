"""Process-local Run aggregate behavior."""

from __future__ import annotations

from datetime import datetime

from empirical_platform.campaign.lifecycle import RunLifecycleState
from empirical_platform.datasets import DatasetManifest
from empirical_platform.identifiers import CampaignId, DomainIdentity, RunId
from empirical_platform.shared.domain import (
    AggregateVersion,
    StateTransitionRecord,
    TransitionSequence,
)


class Run:
    """Process-local Run aggregate root."""

    __slots__ = (
        "_campaign_id",
        "_identity",
        "_manifests",
        "_next_transition_sequence",
        "_state",
        "_transition_history",
        "_version",
    )

    _MANIFEST_APPEND_STATES = (
        RunLifecycleState.CREATED,
        RunLifecycleState.AUTHORIZED,
        RunLifecycleState.ACQUIRING,
        RunLifecycleState.NORMALIZING,
        RunLifecycleState.VALIDATING,
    )

    def __init__(self, *, identity: DomainIdentity[RunId], campaign_id: CampaignId) -> None:
        if not isinstance(identity, DomainIdentity):
            raise TypeError("identity must be a DomainIdentity[RunId]")
        if not isinstance(identity.governance_id, RunId):
            raise TypeError("identity governance_id must be a RunId")
        if not isinstance(campaign_id, CampaignId):
            raise TypeError("campaign_id must be a CampaignId")

        self._identity = identity
        self._campaign_id = campaign_id
        self._state = RunLifecycleState.CREATED
        self._version = AggregateVersion.initial()
        self._next_transition_sequence = TransitionSequence.initial()
        self._transition_history: tuple[StateTransitionRecord[DomainIdentity[RunId]], ...] = ()
        self._manifests: tuple[DatasetManifest, ...] = ()

    @property
    def identity(self) -> DomainIdentity[RunId]:
        """Return immutable Run identity."""
        return self._identity

    @property
    def campaign_id(self) -> CampaignId:
        """Return immutable Campaign context identity."""
        return self._campaign_id

    @property
    def state(self) -> RunLifecycleState:
        """Return current Run lifecycle state."""
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
    def transition_history(self) -> tuple[StateTransitionRecord[DomainIdentity[RunId]], ...]:
        """Return immutable lifecycle transition history."""
        return self._transition_history

    @property
    def manifests(self) -> tuple[DatasetManifest, ...]:
        """Return immutable Dataset Manifest collection view."""
        return self._manifests

    @property
    def current_manifest(self) -> DatasetManifest | None:
        """Return the latest appended Dataset Manifest, if one exists."""
        return self._manifests[-1] if self._manifests else None

    def authorize(
        self,
        *,
        actor: str,
        occurred_at: datetime,
        correlation_id: str | None = None,
        reason: str | None = None,
    ) -> None:
        """Transition the Run from CREATED to AUTHORIZED."""
        self._transition(
            allowed_states=(RunLifecycleState.CREATED,),
            next_state=RunLifecycleState.AUTHORIZED,
            actor=actor,
            occurred_at=occurred_at,
            correlation_id=correlation_id,
            reason=reason,
        )

    def start_acquisition(
        self,
        *,
        actor: str,
        occurred_at: datetime,
        correlation_id: str | None = None,
        reason: str | None = None,
    ) -> None:
        """Transition the Run from AUTHORIZED to ACQUIRING."""
        self._transition(
            allowed_states=(RunLifecycleState.AUTHORIZED,),
            next_state=RunLifecycleState.ACQUIRING,
            actor=actor,
            occurred_at=occurred_at,
            correlation_id=correlation_id,
            reason=reason,
        )

    def start_normalization(
        self,
        *,
        actor: str,
        occurred_at: datetime,
        correlation_id: str | None = None,
        reason: str | None = None,
    ) -> None:
        """Transition the Run from ACQUIRING to NORMALIZING."""
        self._transition(
            allowed_states=(RunLifecycleState.ACQUIRING,),
            next_state=RunLifecycleState.NORMALIZING,
            actor=actor,
            occurred_at=occurred_at,
            correlation_id=correlation_id,
            reason=reason,
        )

    def start_validation(
        self,
        *,
        actor: str,
        occurred_at: datetime,
        correlation_id: str | None = None,
        reason: str | None = None,
    ) -> None:
        """Transition the Run from NORMALIZING to VALIDATING."""
        self._transition(
            allowed_states=(RunLifecycleState.NORMALIZING,),
            next_state=RunLifecycleState.VALIDATING,
            actor=actor,
            occurred_at=occurred_at,
            correlation_id=correlation_id,
            reason=reason,
        )

    def complete_execution(
        self,
        *,
        actor: str,
        occurred_at: datetime,
        correlation_id: str | None = None,
        reason: str | None = None,
    ) -> None:
        """Transition the Run from VALIDATING to EXECUTION_COMPLETED."""
        self._transition(
            allowed_states=(RunLifecycleState.VALIDATING,),
            next_state=RunLifecycleState.EXECUTION_COMPLETED,
            actor=actor,
            occurred_at=occurred_at,
            correlation_id=correlation_id,
            reason=reason,
        )

    def cancel(
        self,
        *,
        reason: str,
        actor: str,
        occurred_at: datetime,
        correlation_id: str | None = None,
    ) -> None:
        """Cancel the Run before execution begins."""
        _require_non_empty(reason, "cancellation reason")
        self._transition(
            allowed_states=(RunLifecycleState.AUTHORIZED,),
            next_state=RunLifecycleState.CANCELLED,
            actor=actor,
            occurred_at=occurred_at,
            correlation_id=correlation_id,
            reason=reason,
        )

    def fail(
        self,
        *,
        reason: str,
        actor: str,
        occurred_at: datetime,
        correlation_id: str | None = None,
    ) -> None:
        """Fail the Run from an execution-stage lifecycle state."""
        _require_non_empty(reason, "failure reason")
        self._transition(
            allowed_states=(
                RunLifecycleState.ACQUIRING,
                RunLifecycleState.NORMALIZING,
                RunLifecycleState.VALIDATING,
            ),
            next_state=RunLifecycleState.FAILED,
            actor=actor,
            occurred_at=occurred_at,
            correlation_id=correlation_id,
            reason=reason,
        )

    def append_manifest(self, manifest: DatasetManifest) -> None:
        """Append a Run-owned immutable Dataset Manifest."""
        if not isinstance(manifest, DatasetManifest):
            raise TypeError("manifest must be a DatasetManifest")
        if self._state not in self._MANIFEST_APPEND_STATES:
            raise ValueError(f"Dataset Manifests may not be appended while {self._state.value}")
        if manifest.run_id != self._identity.governance_id:
            raise ValueError("Dataset Manifest run_id must match Run identity")
        if manifest.manifest_id is not None and any(
            existing.manifest_id == manifest.manifest_id
            for existing in self._manifests
            if existing.manifest_id is not None
        ):
            raise ValueError("Dataset Manifest manifest_id already exists in Run")

        next_version = self._version.next()
        next_manifests = (*self._manifests, manifest)

        self._version = next_version
        self._manifests = next_manifests

    def _transition(
        self,
        *,
        allowed_states: tuple[RunLifecycleState, ...],
        next_state: RunLifecycleState,
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
