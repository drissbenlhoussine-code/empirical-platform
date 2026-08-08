"""Real end-to-end Run Dataset Manifest composition root.

Composes the frozen MILESTONE-055 vertical slice through the shared
MILESTONE-053 resource-lifecycle helper.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime

from empirical_platform.application.command import CommandEntryPoint
from empirical_platform.entrypoints._composition import postgres_repository_runtime
from empirical_platform.identifiers.pairs import DomainIdentity
from empirical_platform.identifiers.types import RunId
from empirical_platform.shared.config.settings import PostgreSQLConfigSnapshot
from empirical_platform.shared.contracts.repository import SaveResult
from empirical_platform.shared.domain.versioning import AggregateVersion
from empirical_platform.shared.identifiers import RuntimeIdentifier
from empirical_platform.usecases.append_run_manifest import (
    AppendRunManifestCommand,
    AppendRunManifestHandler,
)


def run_append_run_manifest(
    *,
    run_governance_id: str,
    run_runtime_id: str,
    expected_persisted_version: int,
    recorded_at: datetime,
    source: str,
    acquisition_method: str | None = None,
    normalization_method: str | None = None,
    manifest_id: str | None = None,
    notes: tuple[str, ...] = (),
    config: PostgreSQLConfigSnapshot | None = None,
) -> SaveResult:
    """Append one Dataset Manifest to a Run, end-to-end, against real PostgreSQL."""
    with postgres_repository_runtime(config) as runtime:
        handler = AppendRunManifestHandler(run_repository=runtime.runs)
        entry_point = CommandEntryPoint(handler)
        identity = DomainIdentity(
            governance_id=RunId(run_governance_id),
            runtime_id=RuntimeIdentifier(run_runtime_id),
        )
        command = AppendRunManifestCommand(
            identity=identity,
            expected_persisted_version=AggregateVersion(expected_persisted_version),
            recorded_at=recorded_at,
            source=source,
            acquisition_method=acquisition_method,
            normalization_method=normalization_method,
            manifest_id=manifest_id,
            notes=notes,
        )
        return entry_point(command)


def _result_payload(result: SaveResult) -> dict[str, str]:
    """Return a plain, JSON-serializable representation of one SaveResult."""
    return {
        "operation": result.operation.value,
        "persisted_version": str(result.persisted_version.value),
    }


def main() -> None:
    """Append one Dataset Manifest from CLI arguments, and print the result."""
    if len(sys.argv) not in (6, 7, 8):
        raise SystemExit(
            "usage: empirical-platform-append-run-manifest "
            "<governance_id> <runtime_id> <expected_version> <recorded_at_iso> <source> "
            "[acquisition_method] [normalization_method]"
        )
    result = run_append_run_manifest(
        run_governance_id=sys.argv[1],
        run_runtime_id=sys.argv[2],
        expected_persisted_version=int(sys.argv[3]),
        recorded_at=datetime.fromisoformat(sys.argv[4]),
        source=sys.argv[5],
        acquisition_method=sys.argv[6] if len(sys.argv) > 6 else None,
        normalization_method=sys.argv[7] if len(sys.argv) > 7 else None,
    )
    print(json.dumps(_result_payload(result), sort_keys=True))


if __name__ == "__main__":
    main()
