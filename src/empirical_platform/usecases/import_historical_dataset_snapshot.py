"""Import one immutable local historical dataset snapshot end-to-end.

MILESTONE-065.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from empirical_platform.decision_candidate.corporate_actions import CorporateActionManifest
from empirical_platform.decision_candidate.dataset_snapshot import DatasetSnapshotAuthority
from empirical_platform.decision_candidate.dataset_snapshot_repository import (
    CorporateActionRepository,
    DatasetSnapshotRepository,
)
from empirical_platform.decision_candidate.historical_import import (
    RawSourceFile,
    derive_split_adjusted_snapshot,
    import_raw_historical_dataset_snapshot,
    write_dataset_artifact,
)
from empirical_platform.decision_candidate.instrument_master import (
    InstrumentMaster,
    InstrumentMasterRepository,
)
from empirical_platform.decision_candidate.market_data import BarInterval
from empirical_platform.identifiers.types import DatasetId

# Explicit re-exports: `entrypoints` cannot import `decision_candidate`
# directly (architecture rule) -- the idiom established since M054.
__all__ = [
    "BarInterval",
    "CorporateActionManifest",
    "DatasetId",
    "DatasetSnapshotAuthority",
    "ImportHistoricalDatasetSnapshotCommand",
    "ImportHistoricalDatasetSnapshotHandler",
    "ImportHistoricalDatasetSnapshotResult",
    "InstrumentMaster",
    "RawSourceFile",
    "build_import_historical_dataset_snapshot_command",
]


@dataclass(frozen=True, slots=True)
class ImportHistoricalDatasetSnapshotCommand:
    """Request to import one set of local raw source files into a
    `RAW_UNADJUSTED` snapshot, and (when a corporate-action manifest is
    supplied) additionally derive a `SPLIT_ADJUSTED` snapshot from it."""

    dataset_id: DatasetId
    raw_dataset_version: str
    adjusted_dataset_version: str | None
    source_kind: str
    source_name: str
    source_reference: str
    license_note: str
    snapshot_created_at: datetime
    interval: BarInterval
    raw_source_files: tuple[RawSourceFile, ...]
    instrument_master: InstrumentMaster
    corporate_action_manifest: CorporateActionManifest | None
    raw_artifact_path: Path
    adjusted_artifact_path: Path | None


@dataclass(frozen=True, slots=True)
class ImportHistoricalDatasetSnapshotResult:
    """The immutable result of one import: the persisted `RAW_UNADJUSTED`
    snapshot, the optional persisted `SPLIT_ADJUSTED` snapshot, and the
    on-disk artifact paths a caller can hand directly to the unmodified
    M061 `run-historical-backtest` CLI."""

    raw_snapshot: DatasetSnapshotAuthority
    raw_artifact_path: Path
    raw_artifact_sha256: str
    adjusted_snapshot: DatasetSnapshotAuthority | None
    adjusted_artifact_path: Path | None
    adjusted_artifact_sha256: str | None


class ImportHistoricalDatasetSnapshotHandler:
    """Validate and persist one immutable dataset snapshot import, through
    the unmodified M064 `InstrumentMasterRepository` and the new M065
    `DatasetSnapshotRepository`/`CorporateActionRepository` -- never a
    second persistence path for instrument identity."""

    __slots__ = ("_dataset_snapshots", "_corporate_actions", "_instrument_masters")

    def __init__(
        self,
        *,
        dataset_snapshot_repository: DatasetSnapshotRepository,
        corporate_action_repository: CorporateActionRepository,
        instrument_master_repository: InstrumentMasterRepository,
    ) -> None:
        self._dataset_snapshots = dataset_snapshot_repository
        self._corporate_actions = corporate_action_repository
        self._instrument_masters = instrument_master_repository

    def handle(
        self, command: ImportHistoricalDatasetSnapshotCommand
    ) -> ImportHistoricalDatasetSnapshotResult:
        raw_snapshot, raw_series = import_raw_historical_dataset_snapshot(
            dataset_id=command.dataset_id,
            dataset_version=command.raw_dataset_version,
            source_kind=command.source_kind,
            source_name=command.source_name,
            source_reference=command.source_reference,
            license_note=command.license_note,
            snapshot_created_at=command.snapshot_created_at,
            interval=command.interval,
            raw_source_files=command.raw_source_files,
            instrument_master=command.instrument_master,
        )
        self._instrument_masters.add_all(command.instrument_master)
        self._dataset_snapshots.add(raw_snapshot)
        raw_artifact_sha256 = write_dataset_artifact(
            command.raw_artifact_path,
            dataset_id=raw_snapshot.dataset_id,
            dataset_version=raw_snapshot.dataset_version,
            source_kind=raw_snapshot.source_kind,
            series=raw_series,
        )

        adjusted_snapshot: DatasetSnapshotAuthority | None = None
        adjusted_artifact_sha256: str | None = None
        if (
            command.corporate_action_manifest is not None
            and command.adjusted_dataset_version is not None
            and command.adjusted_artifact_path is not None
        ):
            manifest = command.corporate_action_manifest
            if manifest.dataset_id != str(command.dataset_id):
                raise ValueError(
                    "corporate_action_manifest.dataset_id "
                    f"{manifest.dataset_id!r} does not match the dataset being imported "
                    f"{command.dataset_id!r}"
                )
            if manifest.dataset_version != command.raw_dataset_version:
                raise ValueError(
                    "corporate_action_manifest.dataset_version "
                    f"{manifest.dataset_version!r} does not match the raw dataset_version "
                    f"being imported {command.raw_dataset_version!r}"
                )
            adjusted_snapshot, adjusted_series = derive_split_adjusted_snapshot(
                raw_snapshot,
                raw_series,
                dataset_version=command.adjusted_dataset_version,
                snapshot_created_at=command.snapshot_created_at,
                corporate_action_manifest=command.corporate_action_manifest,
                instrument_master=command.instrument_master,
            )
            self._corporate_actions.add(command.corporate_action_manifest)
            self._dataset_snapshots.add(adjusted_snapshot)
            adjusted_artifact_sha256 = write_dataset_artifact(
                command.adjusted_artifact_path,
                dataset_id=adjusted_snapshot.dataset_id,
                dataset_version=adjusted_snapshot.dataset_version,
                source_kind=adjusted_snapshot.source_kind,
                series=adjusted_series,
            )

        return ImportHistoricalDatasetSnapshotResult(
            raw_snapshot=raw_snapshot,
            raw_artifact_path=command.raw_artifact_path,
            raw_artifact_sha256=raw_artifact_sha256,
            adjusted_snapshot=adjusted_snapshot,
            adjusted_artifact_path=command.adjusted_artifact_path,
            adjusted_artifact_sha256=adjusted_artifact_sha256,
        )


def build_import_historical_dataset_snapshot_command(
    *,
    dataset_id: str,
    raw_dataset_version: str,
    adjusted_dataset_version: str | None,
    source_kind: str,
    source_name: str,
    source_reference: str,
    license_note: str,
    snapshot_created_at: datetime,
    interval: BarInterval,
    raw_source_files: tuple[RawSourceFile, ...],
    instrument_master: InstrumentMaster,
    corporate_action_manifest: CorporateActionManifest | None,
    raw_artifact_path: str,
    adjusted_artifact_path: str | None,
) -> ImportHistoricalDatasetSnapshotCommand:
    """Build one real M065 command from plain application-layer inputs."""
    return ImportHistoricalDatasetSnapshotCommand(
        dataset_id=DatasetId(dataset_id),
        raw_dataset_version=raw_dataset_version,
        adjusted_dataset_version=adjusted_dataset_version,
        source_kind=source_kind,
        source_name=source_name,
        source_reference=source_reference,
        license_note=license_note,
        snapshot_created_at=snapshot_created_at,
        interval=interval,
        raw_source_files=raw_source_files,
        instrument_master=instrument_master,
        corporate_action_manifest=corporate_action_manifest,
        raw_artifact_path=Path(raw_artifact_path),
        adjusted_artifact_path=Path(adjusted_artifact_path) if adjusted_artifact_path else None,
    )
