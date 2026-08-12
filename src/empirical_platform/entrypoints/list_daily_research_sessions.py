"""Real end-to-end daily research session listing composition root.

MILESTONE-071. Lists the most recent daily research sessions, optionally
restricted to an exact universe -- closes the "session history/
navigation" gap: an operator can find a session without already knowing
its exact runtime id.
"""

from __future__ import annotations

import json
import sys

from empirical_platform.application.query import QueryEntryPoint
from empirical_platform.entrypoints._composition import postgres_repository_runtime
from empirical_platform.shared.config.settings import PostgreSQLConfigSnapshot
from empirical_platform.usecases.list_daily_research_sessions import (
    ListDailyResearchSessionsHandler,
    ListDailyResearchSessionsQuery,
    ResearchSessionSummary,
)
from empirical_platform.usecases.research_session_io import daily_research_session_list_payload


def run_list_daily_research_sessions(
    *,
    universe: tuple[str, ...] | None,
    limit: int,
    config: PostgreSQLConfigSnapshot | None = None,
) -> tuple[ResearchSessionSummary, ...]:
    """List recent daily research sessions end-to-end against real
    PostgreSQL."""
    with postgres_repository_runtime(config) as runtime:
        handler = ListDailyResearchSessionsHandler(repository=runtime.research_sessions)
        entry_point = QueryEntryPoint(handler)
        return entry_point(ListDailyResearchSessionsQuery(universe=universe, limit=limit))


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit("usage: empirical-platform-list-daily-research <limit> [symbol ...]")
    limit = int(sys.argv[1])
    symbols = tuple(sys.argv[2:])
    universe = symbols if symbols else None
    result = run_list_daily_research_sessions(universe=universe, limit=limit)
    print(json.dumps(daily_research_session_list_payload(result), sort_keys=True))


if __name__ == "__main__":
    main()
