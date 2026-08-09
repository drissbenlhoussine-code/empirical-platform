"""Real end-to-end historical robustness study retrieval composition root."""

from __future__ import annotations

import json
import sys

from empirical_platform.application.query import QueryEntryPoint
from empirical_platform.entrypoints._composition import postgres_repository_runtime
from empirical_platform.entrypoints.run_historical_robustness_study import _study_payload
from empirical_platform.identifiers.pairs import DomainIdentity
from empirical_platform.identifiers.types import RobustnessStudyId
from empirical_platform.shared.config.settings import PostgreSQLConfigSnapshot
from empirical_platform.shared.identifiers import RuntimeIdentifier
from empirical_platform.usecases.get_historical_robustness_study import (
    GetHistoricalRobustnessStudyHandler,
    GetHistoricalRobustnessStudyQuery,
)


def run_get_historical_robustness_study(
    *,
    study_governance_id: str,
    study_runtime_id: str,
    config: PostgreSQLConfigSnapshot | None = None,
) -> object:
    """Retrieve one historical robustness study end-to-end against real PostgreSQL."""
    with postgres_repository_runtime(config) as runtime:
        handler = GetHistoricalRobustnessStudyHandler(repository=runtime.robustness_studies)
        entry_point = QueryEntryPoint(handler)
        return entry_point(
            GetHistoricalRobustnessStudyQuery(
                identity=DomainIdentity(
                    governance_id=RobustnessStudyId(study_governance_id),
                    runtime_id=RuntimeIdentifier(study_runtime_id),
                )
            )
        )


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit(
            "usage: empirical-platform-get-historical-robustness-study <governance_id> <runtime_id>"
        )
    study = run_get_historical_robustness_study(
        study_governance_id=sys.argv[1],
        study_runtime_id=sys.argv[2],
    )
    print(json.dumps(_study_payload(study), sort_keys=True))


if __name__ == "__main__":
    main()
