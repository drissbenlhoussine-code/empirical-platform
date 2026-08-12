"""Real end-to-end daily research session comparison composition root.

MILESTONE-071. Compares one target session against its own most recent
prior session sharing the same universe -- closes the "day-over-day
change detection"/"research-session comparison" gap: an operator sees
exactly what changed since the last research session for the same
instruments.
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
from empirical_platform.usecases.compare_daily_research_sessions import (
    CompareDailyResearchSessionsHandler,
    CompareDailyResearchSessionsQuery,
    SessionComparisonResult,
)
from empirical_platform.usecases.research_session_io import (
    daily_research_session_comparison_payload,
)


def run_compare_daily_research_sessions(
    *,
    session_governance_id: str,
    session_runtime_id: str,
    config: PostgreSQLConfigSnapshot | None = None,
) -> SessionComparisonResult:
    """Compare one daily research session end-to-end against real
    PostgreSQL."""
    with postgres_repository_runtime(config) as runtime:
        handler = CompareDailyResearchSessionsHandler(repository=runtime.research_sessions)
        entry_point = QueryEntryPoint(handler)
        return entry_point(
            CompareDailyResearchSessionsQuery(
                identity=DomainIdentity(
                    governance_id=ResearchSessionId(session_governance_id),
                    runtime_id=RuntimeIdentifier(session_runtime_id),
                )
            )
        )


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit(
            "usage: empirical-platform-compare-daily-research "
            "<session_governance_id> <session_runtime_id>"
        )
    result = run_compare_daily_research_sessions(
        session_governance_id=sys.argv[1], session_runtime_id=sys.argv[2]
    )
    print(json.dumps(daily_research_session_comparison_payload(result), sort_keys=True))


if __name__ == "__main__":
    main()
