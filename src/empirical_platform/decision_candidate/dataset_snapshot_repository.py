"""Persistence-neutral repository contracts for M065 dataset snapshots,
corporate actions, and the corporate-action semantics stress diagnostic."""

from __future__ import annotations

from typing import Protocol

from empirical_platform.decision_candidate.corporate_action_stress import (
    CorporateActionSemanticsStressResult,
)
from empirical_platform.decision_candidate.corporate_actions import CorporateActionManifest
from empirical_platform.decision_candidate.dataset_snapshot import DatasetSnapshotAuthority
from empirical_platform.identifiers.pairs import DomainIdentity
from empirical_platform.identifiers.types import CorporateActionStressId, DatasetId


class DatasetSnapshotRepository(Protocol):
    """Persistence-neutral repository contract for immutable dataset
    snapshot authorities, keyed by `(dataset_id, dataset_version)`."""

    def get(self, dataset_id: DatasetId, dataset_version: str) -> DatasetSnapshotAuthority:
        """Load a dataset snapshot authority by its own identity."""
        ...

    def add(self, snapshot: DatasetSnapshotAuthority) -> None:
        """Persist a new dataset snapshot authority that must not already exist."""
        ...


class CorporateActionRepository(Protocol):
    """Persistence-neutral repository contract for declared corporate
    actions, keyed by the same `(dataset_id, dataset_version)` as the
    dataset snapshot they belong to."""

    def get(self, dataset_id: DatasetId, dataset_version: str) -> CorporateActionManifest:
        """Load the corporate-action manifest declared for one dataset
        snapshot version."""
        ...

    def add(self, manifest: CorporateActionManifest) -> None:
        """Persist a new corporate-action manifest that must not already exist."""
        ...


class CorporateActionSemanticsStressRepository(Protocol):
    """Persistence-neutral repository contract for immutable
    corporate-action semantics stress diagnostic results."""

    def get(
        self, identity: DomainIdentity[CorporateActionStressId]
    ) -> CorporateActionSemanticsStressResult:
        """Load a stress diagnostic result by canonical identity."""
        ...

    def add(self, result: CorporateActionSemanticsStressResult) -> None:
        """Persist a new stress diagnostic result that must not already exist."""
        ...
