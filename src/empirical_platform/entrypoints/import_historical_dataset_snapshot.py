"""Real end-to-end historical dataset snapshot import composition root.

MILESTONE-065. A caller supplies a local directory of raw CSV source files
(one file per instrument, keyed by its current/final ticker symbol), a
local instrument-master file, and a local corporate-action manifest file,
and receives one persisted `RAW_UNADJUSTED` dataset snapshot authority
plus (since the manifest is always supplied) one derived `SPLIT_ADJUSTED`
snapshot authority -- and two on-disk M061-compatible dataset JSON
artifacts that can be handed directly to the unmodified, frozen
`empirical-platform-run-historical-backtest` CLI.
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime

from empirical_platform.application.command import CommandEntryPoint
from empirical_platform.entrypoints._composition import postgres_repository_runtime
from empirical_platform.shared.config.settings import PostgreSQLConfigSnapshot
from empirical_platform.usecases.historical_import_io import (
    dataset_snapshot_payload,
    parse_corporate_action_manifest_file,
    parse_instrument_master_file,
    read_raw_source_files,
)
from empirical_platform.usecases.import_historical_dataset_snapshot import (
    BarInterval,
    ImportHistoricalDatasetSnapshotHandler,
    build_import_historical_dataset_snapshot_command,
)


def run_import_historical_dataset_snapshot(
    *,
    dataset_id: str,
    raw_dataset_version: str,
    adjusted_dataset_version: str,
    source_kind: str,
    source_name: str,
    source_reference: str,
    license_note: str,
    interval: str,
    source_files_dir: str,
    instrument_master_file: str,
    corporate_action_manifest_file: str,
    raw_artifact_path: str,
    adjusted_artifact_path: str,
    config: PostgreSQLConfigSnapshot | None = None,
) -> object:
    """Import one deterministic historical dataset snapshot end-to-end
    against real PostgreSQL."""
    raw_source_files = read_raw_source_files(source_files_dir)
    instrument_master = parse_instrument_master_file(instrument_master_file)
    corporate_action_manifest = parse_corporate_action_manifest_file(corporate_action_manifest_file)
    with postgres_repository_runtime(config) as runtime:
        handler = ImportHistoricalDatasetSnapshotHandler(
            dataset_snapshot_repository=runtime.dataset_snapshots,
            corporate_action_repository=runtime.corporate_actions,
            instrument_master_repository=runtime.instrument_masters,
        )
        entry_point = CommandEntryPoint(handler)
        return entry_point(
            build_import_historical_dataset_snapshot_command(
                dataset_id=dataset_id,
                raw_dataset_version=raw_dataset_version,
                adjusted_dataset_version=adjusted_dataset_version,
                source_kind=source_kind,
                source_name=source_name,
                source_reference=source_reference,
                license_note=license_note,
                snapshot_created_at=datetime.now(UTC),
                interval=BarInterval(interval),
                raw_source_files=raw_source_files,
                instrument_master=instrument_master,
                corporate_action_manifest=corporate_action_manifest,
                raw_artifact_path=raw_artifact_path,
                adjusted_artifact_path=adjusted_artifact_path,
            )
        )


def _result_payload(result: object) -> dict[str, object]:
    raw_snapshot = result.raw_snapshot  # type: ignore[attr-defined]
    adjusted_snapshot = result.adjusted_snapshot  # type: ignore[attr-defined]
    return {
        "raw_snapshot": dataset_snapshot_payload(raw_snapshot),
        "raw_artifact_path": str(result.raw_artifact_path),  # type: ignore[attr-defined]
        "raw_artifact_sha256": result.raw_artifact_sha256,  # type: ignore[attr-defined]
        "adjusted_snapshot": (
            dataset_snapshot_payload(adjusted_snapshot) if adjusted_snapshot is not None else None
        ),
        "adjusted_artifact_path": (
            str(result.adjusted_artifact_path)  # type: ignore[attr-defined]
            if result.adjusted_artifact_path is not None  # type: ignore[attr-defined]
            else None
        ),
        "adjusted_artifact_sha256": result.adjusted_artifact_sha256,  # type: ignore[attr-defined]
    }


def main() -> None:
    if len(sys.argv) != 14:
        raise SystemExit(
            "usage: empirical-platform-import-historical-dataset-snapshot "
            "<dataset_id> <raw_dataset_version> <adjusted_dataset_version> <source_kind> "
            "<source_name> <source_reference> <license_note> <interval> <source_files_dir> "
            "<instrument_master_file> <corporate_action_manifest_file> <raw_artifact_path> "
            "<adjusted_artifact_path>"
        )
    result = run_import_historical_dataset_snapshot(
        dataset_id=sys.argv[1],
        raw_dataset_version=sys.argv[2],
        adjusted_dataset_version=sys.argv[3],
        source_kind=sys.argv[4],
        source_name=sys.argv[5],
        source_reference=sys.argv[6],
        license_note=sys.argv[7],
        interval=sys.argv[8],
        source_files_dir=sys.argv[9],
        instrument_master_file=sys.argv[10],
        corporate_action_manifest_file=sys.argv[11],
        raw_artifact_path=sys.argv[12],
        adjusted_artifact_path=sys.argv[13],
    )
    print(json.dumps(_result_payload(result), sort_keys=True))


if __name__ == "__main__":
    main()
