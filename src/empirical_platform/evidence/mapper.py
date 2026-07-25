"""Domain-facing EvidencePackage persistence mapper contract (MILESTONE-021)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from empirical_platform.evidence._reconstruction import EvidencePackageReconstructionState
from empirical_platform.evidence.package import EvidencePackage
from empirical_platform.shared.contracts.mapping import (
    IdentityDurableRecord,
    TransitionDurableRecord,
)


@dataclass(frozen=True, slots=True)
class CriterionResultDurableRecord:
    """Persistence-neutral, field-level durable representation of a Criterion Result."""

    evidence_package_id: str
    criterion_id: str
    recorded_at: datetime
    result_label: str
    summary: str | None
    evidence_references: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class EvidencePackageDurableRecord:
    """Persistence-neutral, field-level durable representation of an EvidencePackage."""

    identity: IdentityDurableRecord
    run_id: str
    lifecycle_state: str
    criterion_results: tuple[CriterionResultDurableRecord, ...]
    artifact_references: tuple[str, ...]
    version: int
    next_transition_sequence: int
    transition_history: tuple[TransitionDurableRecord, ...]


class EvidencePackageMapper(Protocol):
    """Persistence-neutral mapper contract between EvidencePackage and its durable record."""

    def to_durable_record(self, aggregate: EvidencePackage) -> EvidencePackageDurableRecord:
        """Transform an EvidencePackage into its persistence-neutral durable record.

        Pure data transformation: does not mutate the aggregate, increment its
        version, or append transition history. May raise `MapperError` with
        category `INVALID_AGGREGATE_FOR_MAPPING` if the aggregate is not valid
        for mapping.
        """
        ...

    def from_durable_record(
        self, record: EvidencePackageDurableRecord
    ) -> EvidencePackageReconstructionState:
        """Transform a durable record into an `EvidencePackageReconstructionState`.

        Does not call the internal `_reconstruct_evidence_package` factory;
        that call remains a future repository implementation's responsibility.
        Raises `MapperError` with category `INVALID_DURABLE_RECORD` for durable
        data that is structurally malformed before reconstruction can validate it.
        """
        ...
