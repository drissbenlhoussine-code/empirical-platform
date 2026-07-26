"""Domain-facing Campaign persistence mapper contract (MILESTONE-021).

The concrete `ConcreteCampaignMapper` at the bottom of this module is the
MILESTONE-023 concrete mapper implementation: a pure field-level
transformation between `Campaign` and `CampaignDurableRecord`, with no SQL,
transaction, or repository awareness (MILESTONE-023 Design Section 3/14).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from empirical_platform.campaign._reconstruction import CampaignReconstructionState
from empirical_platform.campaign.aggregate import Campaign, CampaignScopeStatement
from empirical_platform.campaign.lifecycle import CampaignLifecycleState
from empirical_platform.identifiers.pairs import DomainIdentity
from empirical_platform.identifiers.types import CampaignId
from empirical_platform.shared.contracts.mapping import (
    IdentityDurableRecord,
    MapperError,
    MapperErrorCategory,
    TransitionDurableRecord,
)
from empirical_platform.shared.domain.transitions import StateTransitionRecord
from empirical_platform.shared.domain.versioning import AggregateVersion, TransitionSequence
from empirical_platform.shared.identifiers import RuntimeIdentifier


@dataclass(frozen=True, slots=True)
class CampaignDurableRecord:
    """Persistence-neutral, field-level durable representation of a Campaign."""

    identity: IdentityDurableRecord
    scope_statement: str
    lifecycle_state: str
    version: int
    next_transition_sequence: int
    transition_history: tuple[TransitionDurableRecord, ...]


class CampaignMapper(Protocol):
    """Persistence-neutral mapper contract between Campaign and its durable record."""

    def to_durable_record(self, aggregate: Campaign) -> CampaignDurableRecord:
        """Transform a Campaign into its persistence-neutral durable record.

        Pure data transformation: does not mutate the aggregate, increment its
        version, or append transition history. May raise `MapperError` with
        category `INVALID_AGGREGATE_FOR_MAPPING` if the aggregate is not valid
        for mapping.
        """
        ...

    def from_durable_record(self, record: CampaignDurableRecord) -> CampaignReconstructionState:
        """Transform a durable record into a `CampaignReconstructionState`.

        Does not call the internal `_reconstruct_campaign` factory; that call
        remains a future repository implementation's responsibility. Raises
        `MapperError` with category `INVALID_DURABLE_RECORD` for durable data
        that is structurally malformed before reconstruction can validate it
        (for example, a `lifecycle_state` string matching no known state).
        """
        ...


def _identity_to_durable(identity: DomainIdentity[Any]) -> IdentityDurableRecord:
    return IdentityDurableRecord(
        governance_id=str(identity.governance_id),
        runtime_id=str(identity.runtime_id),
    )


def _identity_from_durable(record: IdentityDurableRecord) -> DomainIdentity[CampaignId]:
    return DomainIdentity(
        governance_id=CampaignId(record.governance_id),
        runtime_id=RuntimeIdentifier(record.runtime_id),
    )


def _transition_to_durable(record: StateTransitionRecord[Any]) -> TransitionDurableRecord:
    identity_reference = (
        _identity_to_durable(record.identity_reference)
        if record.identity_reference is not None
        else None
    )
    return TransitionDurableRecord(
        from_state=record.from_state,
        to_state=record.to_state,
        version=record.version.value,
        sequence=record.sequence.value,
        actor=record.actor,
        occurred_at=record.occurred_at,
        identity_reference=identity_reference,
        correlation_id=record.correlation_id,
        reason=record.reason,
    )


def _transition_from_durable(
    record: TransitionDurableRecord,
) -> StateTransitionRecord[DomainIdentity[CampaignId]]:
    identity_reference = (
        _identity_from_durable(record.identity_reference)
        if record.identity_reference is not None
        else None
    )
    return StateTransitionRecord(
        from_state=record.from_state,
        to_state=record.to_state,
        version=AggregateVersion(record.version),
        sequence=TransitionSequence(record.sequence),
        actor=record.actor,
        occurred_at=record.occurred_at,
        identity_reference=identity_reference,
        correlation_id=record.correlation_id,
        reason=record.reason,
    )


class ConcreteCampaignMapper:
    """Concrete, storage-agnostic `CampaignMapper` implementation (MILESTONE-023)."""

    def to_durable_record(self, aggregate: Campaign) -> CampaignDurableRecord:
        """Transform a Campaign into its persistence-neutral durable record."""
        return CampaignDurableRecord(
            identity=_identity_to_durable(aggregate.identity),
            scope_statement=str(aggregate.scope_statement),
            lifecycle_state=aggregate.state.value,
            version=aggregate.version.value,
            next_transition_sequence=aggregate.next_transition_sequence.value,
            transition_history=tuple(
                _transition_to_durable(record) for record in aggregate.transition_history
            ),
        )

    def from_durable_record(self, record: CampaignDurableRecord) -> CampaignReconstructionState:
        """Transform a durable record into a `CampaignReconstructionState`."""
        try:
            lifecycle_state = CampaignLifecycleState(record.lifecycle_state)
        except ValueError as exc:
            raise MapperError(
                MapperErrorCategory.INVALID_DURABLE_RECORD,
                "unknown Campaign lifecycle_state",
                aggregate_kind="Campaign",
                field="lifecycle_state",
            ) from exc
        try:
            identity = _identity_from_durable(record.identity)
            scope_statement = CampaignScopeStatement(record.scope_statement)
            transition_history = tuple(
                _transition_from_durable(item) for item in record.transition_history
            )
        except (ValueError, TypeError) as exc:
            raise MapperError(
                MapperErrorCategory.INVALID_DURABLE_RECORD,
                "Campaign durable record is structurally malformed",
                aggregate_kind="Campaign",
            ) from exc
        return CampaignReconstructionState(
            identity=identity,
            scope_statement=scope_statement,
            state=lifecycle_state,
            version=AggregateVersion(record.version),
            next_transition_sequence=TransitionSequence(record.next_transition_sequence),
            transition_history=transition_history,
        )
