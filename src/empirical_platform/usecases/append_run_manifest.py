"""Append a Dataset Manifest to an existing Run: concrete command and handler.

MILESTONE-055.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from empirical_platform.identifiers.pairs import DomainIdentity
from empirical_platform.identifiers.types import DatasetId, RunId
from empirical_platform.run import DatasetManifest
from empirical_platform.run.repository import RunRepository
from empirical_platform.shared.contracts.repository import SaveResult
from empirical_platform.shared.domain.versioning import AggregateVersion


@dataclass(frozen=True, slots=True)
class AppendRunManifestCommand:
    """Request to append one new Dataset Manifest to an existing Run."""

    identity: DomainIdentity[RunId]
    expected_persisted_version: AggregateVersion
    recorded_at: datetime
    source: str
    acquisition_method: str | None = None
    normalization_method: str | None = None
    manifest_id: str | None = None
    notes: tuple[str, ...] = ()


class AppendRunManifestHandler:
    """Loads, appends a Dataset Manifest to, and persists one Run for one command."""

    __slots__ = ("_run_repository",)

    def __init__(self, *, run_repository: RunRepository) -> None:
        self._run_repository = run_repository

    def handle(self, command: AppendRunManifestCommand) -> SaveResult:
        """Append the requested Dataset Manifest to the identified Run and persist it."""
        loaded = self._run_repository.get(command.identity)
        run = loaded.aggregate
        manifest = DatasetManifest(
            run_id=run.identity.governance_id,
            recorded_at=command.recorded_at,
            source=command.source,
            acquisition_method=command.acquisition_method,
            normalization_method=command.normalization_method,
            manifest_id=DatasetId(command.manifest_id) if command.manifest_id else None,
            notes=command.notes,
        )
        run.append_manifest(manifest)
        return self._run_repository.save(
            run, expected_persisted_version=command.expected_persisted_version
        )
