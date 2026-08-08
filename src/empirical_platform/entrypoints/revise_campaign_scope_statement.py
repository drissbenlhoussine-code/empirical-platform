"""Real end-to-end Campaign scope-statement revision composition root.

Composes the frozen MILESTONE-056 vertical slice through the shared
MILESTONE-053 resource-lifecycle helper.
"""

from __future__ import annotations

import json
import sys

from empirical_platform.application.command import CommandEntryPoint
from empirical_platform.entrypoints._composition import postgres_repository_runtime
from empirical_platform.identifiers.pairs import DomainIdentity
from empirical_platform.identifiers.types import CampaignId
from empirical_platform.shared.config.settings import PostgreSQLConfigSnapshot
from empirical_platform.shared.contracts.repository import SaveResult
from empirical_platform.shared.domain.versioning import AggregateVersion
from empirical_platform.shared.identifiers import RuntimeIdentifier
from empirical_platform.usecases.revise_campaign_scope_statement import (
    ReviseCampaignScopeStatementCommand,
    ReviseCampaignScopeStatementHandler,
)


def run_revise_campaign_scope_statement(
    *,
    campaign_governance_id: str,
    campaign_runtime_id: str,
    expected_persisted_version: int,
    scope_statement: str,
    config: PostgreSQLConfigSnapshot | None = None,
) -> SaveResult:
    """Revise one Campaign's scope statement, end-to-end, against real PostgreSQL."""
    with postgres_repository_runtime(config) as runtime:
        handler = ReviseCampaignScopeStatementHandler(campaign_repository=runtime.campaigns)
        entry_point = CommandEntryPoint(handler)
        identity = DomainIdentity(
            governance_id=CampaignId(campaign_governance_id),
            runtime_id=RuntimeIdentifier(campaign_runtime_id),
        )
        command = ReviseCampaignScopeStatementCommand(
            identity=identity,
            expected_persisted_version=AggregateVersion(expected_persisted_version),
            scope_statement=scope_statement,
        )
        return entry_point(command)


def _result_payload(result: SaveResult) -> dict[str, str]:
    """Return a plain, JSON-serializable representation of one SaveResult."""
    return {
        "operation": result.operation.value,
        "persisted_version": str(result.persisted_version.value),
    }


def main() -> None:
    """Revise one Campaign's scope statement from CLI arguments, and print the result."""
    if len(sys.argv) != 5:
        raise SystemExit(
            "usage: empirical-platform-revise-campaign-scope-statement "
            "<governance_id> <runtime_id> <expected_version> <scope_statement>"
        )
    result = run_revise_campaign_scope_statement(
        campaign_governance_id=sys.argv[1],
        campaign_runtime_id=sys.argv[2],
        expected_persisted_version=int(sys.argv[3]),
        scope_statement=sys.argv[4],
    )
    print(json.dumps(_result_payload(result), sort_keys=True))


if __name__ == "__main__":
    main()
