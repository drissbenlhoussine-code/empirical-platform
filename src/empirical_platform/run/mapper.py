"""Domain-facing Run persistence mapper contract (MILESTONE-021).

The concrete `ConcreteRunMapper` at the bottom of this module is the
MILESTONE-023 concrete mapper implementation.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol

from empirical_platform.campaign.lifecycle import RunLifecycleState
from empirical_platform.datasets import DatasetManifest
from empirical_platform.identifiers.pairs import DomainIdentity
from empirical_platform.identifiers.types import CampaignId, DatasetId, RunId
from empirical_platform.run._reconstruction import RunReconstructionState
from empirical_platform.run.aggregate import Run
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
class DatasetManifestDurableRecord:
    """Persistence-neutral, field-level durable representation of a Dataset Manifest."""

    run_id: str
    recorded_at: datetime
    source: str
    acquisition_method: str | None
    normalization_method: str | None
    manifest_id: str | None
    notes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RunDurableRecord:
    """Persistence-neutral, field-level durable representation of a Run."""

    identity: IdentityDurableRecord
    campaign_id: str
    lifecycle_state: str
    manifests: tuple[DatasetManifestDurableRecord, ...]
    version: int
    next_transition_sequence: int
    transition_history: tuple[TransitionDurableRecord, ...]


class RunMapper(Protocol):
    """Persistence-neutral mapper contract between Run and its durable record."""

    def to_durable_record(self, aggregate: Run) -> RunDurableRecord:
        """Transform a Run into its persistence-neutral durable record.

        Pure data transformation: does not mutate the aggregate, increment its
        version, or append transition history. May raise `MapperError` with
        category `INVALID_AGGREGATE_FOR_MAPPING` if the aggregate is not valid
        for mapping.
        """
        ...

    def from_durable_record(self, record: RunDurableRecord) -> RunReconstructionState:
        """Transform a durable record into a `RunReconstructionState`.

        Does not call the internal `_reconstruct_run` factory; that call
        remains a future repository implementation's responsibility. Raises
        `MapperError` with category `INVALID_DURABLE_RECORD` for durable data
        that is structurally malformed before reconstruction can validate it.
        """
        ...


def _identity_to_durable(identity: DomainIdentity[Any]) -> IdentityDurableRecord:
    return IdentityDurableRecord(
        governance_id=str(identity.governance_id),
        runtime_id=str(identity.runtime_id),
    )


def _identity_from_durable(record: IdentityDurableRecord) -> DomainIdentity[RunId]:
    return DomainIdentity(
        governance_id=RunId(record.governance_id),
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
) -> StateTransitionRecord[DomainIdentity[RunId]]:
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


def _manifest_to_durable(manifest: DatasetManifest) -> DatasetManifestDurableRecord:
    return DatasetManifestDurableRecord(
        run_id=str(manifest.run_id),
        recorded_at=manifest.recorded_at,
        source=manifest.source,
        acquisition_method=manifest.acquisition_method,
        normalization_method=manifest.normalization_method,
        manifest_id=str(manifest.manifest_id) if manifest.manifest_id is not None else None,
        notes=manifest.notes,
    )


def _manifest_from_durable(record: DatasetManifestDurableRecord) -> DatasetManifest:
    return DatasetManifest(
        run_id=RunId(record.run_id),
        recorded_at=record.recorded_at,
        source=record.source,
        acquisition_method=record.acquisition_method,
        normalization_method=record.normalization_method,
        manifest_id=DatasetId(record.manifest_id) if record.manifest_id is not None else None,
        notes=record.notes,
    )


class ConcreteRunMapper:
    """Concrete, storage-agnostic `RunMapper` implementation (MILESTONE-023)."""

    def to_durable_record(self, aggregate: Run) -> RunDurableRecord:
        """Transform a Run into its persistence-neutral durable record."""
        return RunDurableRecord(
            identity=_identity_to_durable(aggregate.identity),
            campaign_id=str(aggregate.campaign_id),
            lifecycle_state=aggregate.state.value,
            manifests=tuple(_manifest_to_durable(manifest) for manifest in aggregate.manifests),
            version=aggregate.version.value,
            next_transition_sequence=aggregate.next_transition_sequence.value,
            transition_history=tuple(
                _transition_to_durable(record) for record in aggregate.transition_history
            ),
        )

    def from_durable_record(self, record: RunDurableRecord) -> RunReconstructionState:
        """Transform a durable record into a `RunReconstructionState`."""
        try:
            lifecycle_state = RunLifecycleState(record.lifecycle_state)
        except ValueError as exc:
            raise MapperError(
                MapperErrorCategory.INVALID_DURABLE_RECORD,
                "unknown Run lifecycle_state",
                aggregate_kind="Run",
                field="lifecycle_state",
            ) from exc
        try:
            identity = _identity_from_durable(record.identity)
            campaign_id = CampaignId(record.campaign_id)
            manifests = tuple(_manifest_from_durable(item) for item in record.manifests)
            transition_history = tuple(
                _transition_from_durable(item) for item in record.transition_history
            )
        except (ValueError, TypeError) as exc:
            raise MapperError(
                MapperErrorCategory.INVALID_DURABLE_RECORD,
                "Run durable record is structurally malformed",
                aggregate_kind="Run",
            ) from exc
        return RunReconstructionState(
            identity=identity,
            campaign_id=campaign_id,
            state=lifecycle_state,
            manifests=manifests,
            version=AggregateVersion(record.version),
            next_transition_sequence=TransitionSequence(record.next_transition_sequence),
            transition_history=transition_history,
        )
