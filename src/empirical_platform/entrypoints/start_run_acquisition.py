"""Real end-to-end Run acquisition-start composition root.

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
from empirical_platform.usecases.start_run_acquisition import (
    StartRunAcquisitionCommand,
    StartRunAcquisitionHandler,
)


def run_start_run_acquisition(
    *,
    run_governance_id: str,
    run_runtime_id: str,
    expected_persisted_version: int,
    actor: str,
    occurred_at: datetime,
    correlation_id: str | None = None,
    reason: str | None = None,
    config: PostgreSQLConfigSnapshot | None = None,
) -> SaveResult:
    """Start acquisition on one Run, end-to-end, against real PostgreSQL."""
    with postgres_repository_runtime(config) as runtime:
        handler = StartRunAcquisitionHandler(run_repository=runtime.runs)
        entry_point = CommandEntryPoint(handler)
        identity = DomainIdentity(
            governance_id=RunId(run_governance_id),
            runtime_id=RuntimeIdentifier(run_runtime_id),
        )
        command = StartRunAcquisitionCommand(
            identity=identity,
            expected_persisted_version=AggregateVersion(expected_persisted_version),
            actor=actor,
            occurred_at=occurred_at,
            correlation_id=correlation_id,
            reason=reason,
        )
        return entry_point(command)


def _result_payload(result: SaveResult) -> dict[str, str]:
    """Return a plain, JSON-serializable representation of one SaveResult."""
    return {
        "operation": result.operation.value,
        "persisted_version": str(result.persisted_version.value),
    }


def main() -> None:
    """Start acquisition on one Run from CLI arguments, and print the result."""
    if len(sys.argv) not in (6, 7, 8):
        raise SystemExit(
            "usage: empirical-platform-start-run-acquisition "
            "<governance_id> <runtime_id> <expected_version> <actor> <occurred_at_iso> "
            "[correlation_id] [reason]"
        )
    result = run_start_run_acquisition(
        run_governance_id=sys.argv[1],
        run_runtime_id=sys.argv[2],
        expected_persisted_version=int(sys.argv[3]),
        actor=sys.argv[4],
        occurred_at=datetime.fromisoformat(sys.argv[5]),
        correlation_id=sys.argv[6] if len(sys.argv) > 6 else None,
        reason=sys.argv[7] if len(sys.argv) > 7 else None,
    )
    print(json.dumps(_result_payload(result), sort_keys=True))


if __name__ == "__main__":
    main()
