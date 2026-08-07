"""Real end-to-end Campaign retrieval composition root.

Composes, for the first time in production code, real configuration
resolution, a real PostgreSQL persistence service, the frozen MILESTONE-025
repository runtime, and the frozen MILESTONE-031 retrieval vertical slice
into one real, invocable application flow. MILESTONE-050.
"""

from __future__ import annotations

import json
import sys

from empirical_platform.application.query import QueryEntryPoint
from empirical_platform.identifiers.pairs import DomainIdentity
from empirical_platform.identifiers.types import CampaignId
from empirical_platform.shared.config.settings import (
    PostgreSQLConfigSnapshot,
    resolve_foundation_config,
)
from empirical_platform.shared.identifiers import RuntimeIdentifier
from empirical_platform.shared.persistence.postgres import PostgresPersistenceService
from empirical_platform.shared.persistence.postgres_repositories.runtime import (
    PostgresRepositoryRuntime,
)
from empirical_platform.usecases.get_campaign import (
    CampaignSnapshot,
    GetCampaignHandler,
    GetCampaignQuery,
)


def run_get_campaign(
    *,
    campaign_governance_id: str,
    campaign_runtime_id: str,
    config: PostgreSQLConfigSnapshot | None = None,
) -> CampaignSnapshot:
    """Retrieve one Campaign end-to-end against real PostgreSQL.

    `config` defaults to the real environment-resolved configuration; a
    caller may supply an explicit `PostgreSQLConfigSnapshot` to target a
    different database (used by this milestone's own integration tests).
    """
    resolved_config = config if config is not None else resolve_foundation_config().postgresql
    service = PostgresPersistenceService(resolved_config)
    try:
        service.initialize()
        runtime = PostgresRepositoryRuntime(service)
        handler = GetCampaignHandler(campaign_repository=runtime.campaigns)
        entry_point = QueryEntryPoint(handler)
        identity = DomainIdentity(
            governance_id=CampaignId(campaign_governance_id),
            runtime_id=RuntimeIdentifier(campaign_runtime_id),
        )
        return entry_point(GetCampaignQuery(identity=identity))
    finally:
        service.close()


def _snapshot_payload(snapshot: CampaignSnapshot) -> dict[str, str]:
    """Return a plain, JSON-serializable representation of one CampaignSnapshot."""
    return {
        "governance_id": str(snapshot.identity.governance_id),
        "runtime_id": str(snapshot.identity.runtime_id),
        "scope_statement": str(snapshot.scope_statement),
        "state": snapshot.state.value,
    }


def main() -> None:
    """Retrieve one Campaign by identity, supplied as two CLI arguments, and print it."""
    if len(sys.argv) != 3:
        raise SystemExit("usage: empirical-platform-get-campaign <governance_id> <runtime_id>")
    snapshot = run_get_campaign(
        campaign_governance_id=sys.argv[1],
        campaign_runtime_id=sys.argv[2],
    )
    print(json.dumps(_snapshot_payload(snapshot), sort_keys=True))


if __name__ == "__main__":
    main()
