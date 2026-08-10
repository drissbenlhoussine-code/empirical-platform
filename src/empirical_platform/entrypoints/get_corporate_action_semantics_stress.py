"""Real end-to-end corporate-action semantics stress retrieval composition
root."""

from __future__ import annotations

import json
import sys

from empirical_platform.application.query import QueryEntryPoint
from empirical_platform.entrypoints._composition import postgres_repository_runtime
from empirical_platform.identifiers.pairs import DomainIdentity
from empirical_platform.identifiers.types import CorporateActionStressId
from empirical_platform.shared.config.settings import PostgreSQLConfigSnapshot
from empirical_platform.shared.identifiers import RuntimeIdentifier
from empirical_platform.usecases.get_corporate_action_semantics_stress import (
    GetCorporateActionSemanticsStressHandler,
    GetCorporateActionSemanticsStressQuery,
)
from empirical_platform.usecases.historical_import_io import (
    corporate_action_semantics_stress_payload,
)


def run_get_corporate_action_semantics_stress(
    *,
    stress_governance_id: str,
    stress_runtime_id: str,
    config: PostgreSQLConfigSnapshot | None = None,
) -> object:
    """Retrieve one corporate-action semantics stress diagnostic result
    end-to-end against real PostgreSQL."""
    with postgres_repository_runtime(config) as runtime:
        handler = GetCorporateActionSemanticsStressHandler(
            repository=runtime.corporate_action_semantics_stresses
        )
        entry_point = QueryEntryPoint(handler)
        return entry_point(
            GetCorporateActionSemanticsStressQuery(
                identity=DomainIdentity(
                    governance_id=CorporateActionStressId(stress_governance_id),
                    runtime_id=RuntimeIdentifier(stress_runtime_id),
                )
            )
        )


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit(
            "usage: empirical-platform-get-corporate-action-semantics-stress "
            "<governance_id> <runtime_id>"
        )
    result = run_get_corporate_action_semantics_stress(
        stress_governance_id=sys.argv[1], stress_runtime_id=sys.argv[2]
    )
    print(json.dumps(corporate_action_semantics_stress_payload(result), sort_keys=True))


if __name__ == "__main__":
    main()
