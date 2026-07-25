"""Domain-facing Run persistence mapper contract (MILESTONE-021)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from empirical_platform.run._reconstruction import RunReconstructionState
from empirical_platform.run.aggregate import Run
from empirical_platform.shared.contracts.mapping import (
    IdentityDurableRecord,
    TransitionDurableRecord,
)


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
