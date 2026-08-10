"""Retrieve one historical dataset snapshot authority by identity.

MILESTONE-065.
"""

from __future__ import annotations

from dataclasses import dataclass

from empirical_platform.decision_candidate.dataset_snapshot import DatasetSnapshotAuthority
from empirical_platform.decision_candidate.dataset_snapshot_repository import (
    DatasetSnapshotRepository,
)
from empirical_platform.identifiers.types import DatasetId


@dataclass(frozen=True, slots=True)
class GetHistoricalDatasetSnapshotQuery:
    """Request to retrieve one dataset snapshot authority by
    `(dataset_id, dataset_version)`."""

    dataset_id: DatasetId
    dataset_version: str


class GetHistoricalDatasetSnapshotHandler:
    """Retrieve one persisted dataset snapshot authority."""

    __slots__ = ("_repository",)

    def __init__(self, *, repository: DatasetSnapshotRepository) -> None:
        self._repository = repository

    def handle(self, query: GetHistoricalDatasetSnapshotQuery) -> DatasetSnapshotAuthority:
        return self._repository.get(query.dataset_id, query.dataset_version)
