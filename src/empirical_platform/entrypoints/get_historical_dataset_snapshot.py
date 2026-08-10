"""Real end-to-end historical dataset snapshot retrieval composition
root."""

from __future__ import annotations

import json
import sys

from empirical_platform.application.query import QueryEntryPoint
from empirical_platform.entrypoints._composition import postgres_repository_runtime
from empirical_platform.identifiers.types import DatasetId
from empirical_platform.shared.config.settings import PostgreSQLConfigSnapshot
from empirical_platform.usecases.get_historical_dataset_snapshot import (
    GetHistoricalDatasetSnapshotHandler,
    GetHistoricalDatasetSnapshotQuery,
)
from empirical_platform.usecases.historical_import_io import dataset_snapshot_payload


def run_get_historical_dataset_snapshot(
    *,
    dataset_id: str,
    dataset_version: str,
    config: PostgreSQLConfigSnapshot | None = None,
) -> object:
    """Retrieve one historical dataset snapshot authority end-to-end
    against real PostgreSQL."""
    with postgres_repository_runtime(config) as runtime:
        handler = GetHistoricalDatasetSnapshotHandler(repository=runtime.dataset_snapshots)
        entry_point = QueryEntryPoint(handler)
        return entry_point(
            GetHistoricalDatasetSnapshotQuery(
                dataset_id=DatasetId(dataset_id), dataset_version=dataset_version
            )
        )


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit(
            "usage: empirical-platform-get-historical-dataset-snapshot "
            "<dataset_id> <dataset_version>"
        )
    snapshot = run_get_historical_dataset_snapshot(
        dataset_id=sys.argv[1], dataset_version=sys.argv[2]
    )
    print(json.dumps(dataset_snapshot_payload(snapshot), sort_keys=True))


if __name__ == "__main__":
    main()
