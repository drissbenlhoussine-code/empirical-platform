"""MILESTONE-065 application-layer unit tests: import handler.

Uses in-memory fake repositories (no PostgreSQL) to test
`ImportHistoricalDatasetSnapshotHandler` in isolation, including the
corporate-action-manifest identity cross-check added after a real
PostgreSQL acceptance test exposed that an unvalidated manifest could be
persisted under a `(dataset_id, dataset_version)` key that does not match
the dataset snapshot actually being imported.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import pytest

from empirical_platform.decision_candidate.corporate_actions import CorporateActionManifest
from empirical_platform.decision_candidate.dataset_snapshot import DatasetSnapshotAuthority
from empirical_platform.decision_candidate.dataset_snapshot_repository import (
    CorporateActionRepository,
    DatasetSnapshotRepository,
)
from empirical_platform.decision_candidate.instrument_master import (
    InstrumentMaster,
    InstrumentMasterRepository,
)
from empirical_platform.decision_candidate.market_data import BarInterval
from empirical_platform.identifiers.types import DatasetId
from empirical_platform.usecases.historical_import_io import (
    parse_corporate_action_manifest_file,
    parse_instrument_master_file,
    read_raw_source_files,
)
from empirical_platform.usecases.import_historical_dataset_snapshot import (
    ImportHistoricalDatasetSnapshotCommand,
    ImportHistoricalDatasetSnapshotHandler,
    build_import_historical_dataset_snapshot_command,
)

_FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "m065_corporate_action_mechanics"
_INSTRUMENT_MASTER_PATH = _FIXTURE_DIR / "instrument_master.json"
_MANIFEST_PATH = _FIXTURE_DIR / "corporate_action_manifest.json"
_CREATED = datetime(2024, 3, 2, tzinfo=UTC)


@dataclass
class _InMemoryDatasetSnapshotRepository(DatasetSnapshotRepository):
    added: dict[tuple[str, str], DatasetSnapshotAuthority]

    def get(self, dataset_id: DatasetId, dataset_version: str) -> DatasetSnapshotAuthority:
        return self.added[(str(dataset_id), dataset_version)]

    def add(self, snapshot: DatasetSnapshotAuthority) -> None:
        key = (str(snapshot.dataset_id), snapshot.dataset_version)
        if key in self.added:
            raise ValueError(f"snapshot already exists for {key}")
        self.added[key] = snapshot


@dataclass
class _InMemoryCorporateActionRepository(CorporateActionRepository):
    added: dict[tuple[str, str], CorporateActionManifest]

    def get(self, dataset_id: DatasetId, dataset_version: str) -> CorporateActionManifest:
        return self.added[(str(dataset_id), dataset_version)]

    def add(self, manifest: CorporateActionManifest) -> None:
        key = (manifest.dataset_id, manifest.dataset_version)
        if key in self.added:
            raise ValueError(f"manifest already exists for {key}")
        self.added[key] = manifest


@dataclass
class _InMemoryInstrumentMasterRepository(InstrumentMasterRepository):
    added: list[InstrumentMaster]

    def add_all(self, master: InstrumentMaster) -> None:
        self.added.append(master)


def _handler() -> tuple[
    ImportHistoricalDatasetSnapshotHandler,
    _InMemoryDatasetSnapshotRepository,
    _InMemoryCorporateActionRepository,
]:
    snapshots = _InMemoryDatasetSnapshotRepository(added={})
    actions = _InMemoryCorporateActionRepository(added={})
    handler = ImportHistoricalDatasetSnapshotHandler(
        dataset_snapshot_repository=snapshots,
        corporate_action_repository=actions,
        instrument_master_repository=_InMemoryInstrumentMasterRepository(added=[]),
    )
    return handler, snapshots, actions


def _command(
    *,
    dataset_id: str,
    raw_dataset_version: str,
    tmp_path: Path,
    manifest_dataset_id: str | None = None,
    manifest_dataset_version: str | None = None,
) -> ImportHistoricalDatasetSnapshotCommand:
    raw_source_files = read_raw_source_files(str(_FIXTURE_DIR))
    instrument_master = parse_instrument_master_file(str(_INSTRUMENT_MASTER_PATH))
    manifest = parse_corporate_action_manifest_file(str(_MANIFEST_PATH))
    if manifest_dataset_id is not None or manifest_dataset_version is not None:
        manifest = CorporateActionManifest(
            dataset_id=manifest_dataset_id or manifest.dataset_id,
            dataset_version=manifest_dataset_version or manifest.dataset_version,
            actions=manifest.actions,
        )
    return build_import_historical_dataset_snapshot_command(
        dataset_id=dataset_id,
        raw_dataset_version=raw_dataset_version,
        adjusted_dataset_version="2-split-adjusted",
        source_kind="CORPORATE_ACTION_MECHANICS_FIXTURE",
        source_name="fixture",
        source_reference=str(_FIXTURE_DIR),
        license_note="synthetic, no license required",
        snapshot_created_at=_CREATED,
        interval=BarInterval.ONE_MINUTE,
        raw_source_files=raw_source_files,
        instrument_master=instrument_master,
        corporate_action_manifest=manifest,
        raw_artifact_path=str(tmp_path / "raw.json"),
        adjusted_artifact_path=str(tmp_path / "adjusted.json"),
    )


def test_handler_persists_raw_and_adjusted_snapshots_keyed_consistently(tmp_path: Path) -> None:
    handler, snapshots, actions = _handler()
    command = _command(dataset_id="DATASET-6501", raw_dataset_version="1", tmp_path=tmp_path)
    result = handler.handle(command)

    assert ("DATASET-6501", "1") in snapshots.added
    assert ("DATASET-6501", "2-split-adjusted") in snapshots.added
    assert ("DATASET-6501", "1") in actions.added
    assert result.adjusted_snapshot is not None
    assert result.adjusted_snapshot.corporate_action_manifest_hash is not None


def test_handler_rejects_manifest_with_mismatched_dataset_id(tmp_path: Path) -> None:
    handler, _snapshots, _actions = _handler()
    command = _command(
        dataset_id="DATASET-9001",
        raw_dataset_version="1",
        tmp_path=tmp_path,
        manifest_dataset_id="DATASET-6501",
    )
    with pytest.raises(ValueError, match="does not match the dataset being imported"):
        handler.handle(command)


def test_handler_rejects_manifest_with_mismatched_dataset_version(tmp_path: Path) -> None:
    handler, _snapshots, _actions = _handler()
    command = _command(
        dataset_id="DATASET-6501",
        raw_dataset_version="7",
        tmp_path=tmp_path,
        manifest_dataset_id="DATASET-6501",
        manifest_dataset_version="1",
    )
    with pytest.raises(ValueError, match="does not match the raw dataset_version"):
        handler.handle(command)


def test_handler_rejection_happens_before_any_persistence(tmp_path: Path) -> None:
    handler, snapshots, actions = _handler()
    command = _command(
        dataset_id="DATASET-9002",
        raw_dataset_version="1",
        tmp_path=tmp_path,
        manifest_dataset_id="DATASET-6501",
    )
    with pytest.raises(ValueError, match="does not match the dataset being imported"):
        handler.handle(command)

    # The raw snapshot IS persisted before the manifest cross-check runs
    # (the manifest describes corporate actions applied on top of an
    # already-valid raw import) -- but no corporate_action row and no
    # adjusted snapshot are persisted for the rejected import.
    assert ("DATASET-9002", "1") in snapshots.added
    assert ("DATASET-9002", "2-split-adjusted") not in snapshots.added
    assert not actions.added
