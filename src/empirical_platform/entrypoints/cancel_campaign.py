"""Real end-to-end Campaign cancellation composition root.

Composes, for the first time in production code, real configuration
resolution, a real PostgreSQL persistence service, the frozen MILESTONE-025
repository runtime, and the frozen MILESTONE-047 cancellation vertical slice
into one real, invocable application flow -- the first write command
composed through a production entrypoint, pairing with MILESTONE-050's own
read-only `get_campaign` composition. MILESTONE-051.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime

from empirical_platform.application.command import CommandEntryPoint
from empirical_platform.identifiers.pairs import DomainIdentity
from empirical_platform.identifiers.types import CampaignId
from empirical_platform.shared.config.settings import (
    PostgreSQLConfigSnapshot,
    resolve_foundation_config,
)
from empirical_platform.shared.contracts.repository import SaveResult
from empirical_platform.shared.domain.versioning import AggregateVersion
from empirical_platform.shared.identifiers import RuntimeIdentifier
from empirical_platform.shared.persistence.postgres import PostgresPersistenceService
from empirical_platform.shared.persistence.postgres_repositories.runtime import (
    PostgresRepositoryRuntime,
)
from empirical_platform.usecases.cancel_campaign import (
    CancelCampaignCommand,
    CancelCampaignHandler,
)


def run_cancel_campaign(
    *,
    campaign_governance_id: str,
    campaign_runtime_id: str,
    expected_persisted_version: int,
    actor: str,
    occurred_at: datetime,
    reason: str | None = None,
    correlation_id: str | None = None,
    config: PostgreSQLConfigSnapshot | None = None,
) -> SaveResult:
    """Cancel one Campaign end-to-end against real PostgreSQL.

    `config` defaults to the real environment-resolved configuration; a
    caller may supply an explicit `PostgreSQLConfigSnapshot` to target a
    different database (used by this milestone's own integration tests).
    """
    resolved_config = config if config is not None else resolve_foundation_config().postgresql
    service = PostgresPersistenceService(resolved_config)
    try:
        service.initialize()
        runtime = PostgresRepositoryRuntime(service)
        handler = CancelCampaignHandler(campaign_repository=runtime.campaigns)
        entry_point = CommandEntryPoint(handler)
        identity = DomainIdentity(
            governance_id=CampaignId(campaign_governance_id),
            runtime_id=RuntimeIdentifier(campaign_runtime_id),
        )
        command = CancelCampaignCommand(
            identity=identity,
            expected_persisted_version=AggregateVersion(expected_persisted_version),
            actor=actor,
            occurred_at=occurred_at,
            reason=reason,
            correlation_id=correlation_id,
        )
        return entry_point(command)
    finally:
        service.close()


def _result_payload(result: SaveResult) -> dict[str, str]:
    """Return a plain, JSON-serializable representation of one SaveResult."""
    return {
        "operation": result.operation.value,
        "persisted_version": str(result.persisted_version.value),
    }


def main() -> None:
    """Cancel one Campaign by identity, supplied via CLI arguments, and print the result."""
    if len(sys.argv) not in (6, 7, 8):
        raise SystemExit(
            "usage: empirical-platform-cancel-campaign "
            "<governance_id> <runtime_id> <expected_version> <actor> <occurred_at_iso> "
            "[reason] [correlation_id]"
        )
    result = run_cancel_campaign(
        campaign_governance_id=sys.argv[1],
        campaign_runtime_id=sys.argv[2],
        expected_persisted_version=int(sys.argv[3]),
        actor=sys.argv[4],
        occurred_at=datetime.fromisoformat(sys.argv[5]),
        reason=sys.argv[6] if len(sys.argv) > 6 else None,
        correlation_id=sys.argv[7] if len(sys.argv) > 7 else None,
    )
    print(json.dumps(_result_payload(result), sort_keys=True))


if __name__ == "__main__":
    main()
