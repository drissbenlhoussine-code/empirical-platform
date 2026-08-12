"""Real end-to-end daily research session retrieval composition root.

MILESTONE-070. Retrieves a persisted, completed (or failed) session and
its own final report without rerunning the pipeline (mission Phase 15).
"""

from __future__ import annotations

import json
import sys

from empirical_platform.application.query import QueryEntryPoint
from empirical_platform.entrypoints._composition import postgres_repository_runtime
from empirical_platform.identifiers.pairs import DomainIdentity
from empirical_platform.identifiers.types import ResearchSessionId
from empirical_platform.shared.config.settings import PostgreSQLConfigSnapshot
from empirical_platform.shared.identifiers import RuntimeIdentifier
from empirical_platform.usecases.get_daily_research_session import (
    GetDailyResearchSessionHandler,
    GetDailyResearchSessionQuery,
)
from empirical_platform.usecases.research_session_io import research_session_report_payload


def run_get_daily_research_session(
    *,
    session_governance_id: str,
    session_runtime_id: str,
    config: PostgreSQLConfigSnapshot | None = None,
) -> object:
    """Retrieve one daily research session end-to-end against real
    PostgreSQL."""
    with postgres_repository_runtime(config) as runtime:
        handler = GetDailyResearchSessionHandler(repository=runtime.research_sessions)
        entry_point = QueryEntryPoint(handler)
        return entry_point(
            GetDailyResearchSessionQuery(
                identity=DomainIdentity(
                    governance_id=ResearchSessionId(session_governance_id),
                    runtime_id=RuntimeIdentifier(session_runtime_id),
                )
            )
        )


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit(
            "usage: empirical-platform-get-daily-research "
            "<session_governance_id> <session_runtime_id>"
        )
    result = run_get_daily_research_session(
        session_governance_id=sys.argv[1], session_runtime_id=sys.argv[2]
    )
    print(json.dumps(research_session_report_payload(result), sort_keys=True))


if __name__ == "__main__":
    main()
