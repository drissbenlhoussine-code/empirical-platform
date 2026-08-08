"""Real end-to-end Campaign creation composition root.

Composes, for the first time in production code, real configuration
resolution, a real PostgreSQL persistence service, the frozen MILESTONE-025
repository runtime, and the frozen MILESTONE-030 creation vertical slice
into one real, invocable application flow -- the first entrypoint to
exercise the repository's `.add()` code path and the first production
construction of `UuidRuntimeIdentifierGenerator`, completing a full
create -> retrieve -> cancel real-world-usable trio for Campaign alongside
MILESTONE-050's `get_campaign` and MILESTONE-051's `cancel_campaign`.
MILESTONE-052.
"""

from __future__ import annotations

import json
import sys

from empirical_platform.application.command import CommandEntryPoint
from empirical_platform.identifiers.pairs import DomainIdentity
from empirical_platform.identifiers.types import CampaignId
from empirical_platform.shared.config.settings import (
    PostgreSQLConfigSnapshot,
    resolve_foundation_config,
)
from empirical_platform.shared.identifiers import (
    RuntimeIdentifierGenerator,
    UuidRuntimeIdentifierGenerator,
)
from empirical_platform.shared.persistence.postgres import PostgresPersistenceService
from empirical_platform.shared.persistence.postgres_repositories.runtime import (
    PostgresRepositoryRuntime,
)
from empirical_platform.usecases.create_campaign import (
    CreateCampaignCommand,
    CreateCampaignHandler,
)


def run_create_campaign(
    *,
    campaign_governance_id: str,
    scope_statement: str,
    identifier_generator: RuntimeIdentifierGenerator | None = None,
    config: PostgreSQLConfigSnapshot | None = None,
) -> DomainIdentity[CampaignId]:
    """Create one Campaign end-to-end against real PostgreSQL.

    `config` defaults to the real environment-resolved configuration; a
    caller may supply an explicit `PostgreSQLConfigSnapshot` to target a
    different database (used by this milestone's own integration tests).
    `identifier_generator` defaults to a real, collision-resistant
    `UuidRuntimeIdentifierGenerator`; a caller may supply a deterministic
    substitute (used by this milestone's own integration tests) to assert a
    predictable identity.
    """
    resolved_config = config if config is not None else resolve_foundation_config().postgresql
    resolved_generator = identifier_generator or UuidRuntimeIdentifierGenerator()
    service = PostgresPersistenceService(resolved_config)
    try:
        service.initialize()
        runtime = PostgresRepositoryRuntime(service)
        handler = CreateCampaignHandler(
            campaign_repository=runtime.campaigns,
            runtime_identifier_generator=resolved_generator,
        )
        entry_point = CommandEntryPoint(handler)
        command = CreateCampaignCommand(
            campaign_governance_id=campaign_governance_id,
            scope_statement=scope_statement,
        )
        return entry_point(command)
    finally:
        service.close()


def _identity_payload(identity: DomainIdentity[CampaignId]) -> dict[str, str]:
    """Return a plain, JSON-serializable representation of one DomainIdentity."""
    return {
        "governance_id": str(identity.governance_id),
        "runtime_id": str(identity.runtime_id),
    }


def main() -> None:
    """Create one Campaign from CLI arguments, and print its new identity."""
    if len(sys.argv) != 3:
        raise SystemExit(
            "usage: empirical-platform-create-campaign <governance_id> <scope_statement>"
        )
    identity = run_create_campaign(
        campaign_governance_id=sys.argv[1],
        scope_statement=sys.argv[2],
    )
    print(json.dumps(_identity_payload(identity), sort_keys=True))


if __name__ == "__main__":
    main()
