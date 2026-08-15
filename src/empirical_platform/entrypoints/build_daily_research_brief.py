"""Real end-to-end daily research brief composition root.

MILESTONE-072. Builds one operator-facing daily research brief for an
already-persisted session -- defaulting to the single most recent
session across all universes when no session is explicitly selected --
and renders it as either deterministic plain text (default) or JSON
(`--json`), both derived from the same authoritative brief model.
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
from empirical_platform.usecases.build_daily_research_brief import (
    BuildDailyResearchBriefHandler,
    BuildDailyResearchBriefQuery,
    DailyResearchBrief,
)
from empirical_platform.usecases.daily_research_brief_io import (
    render_daily_research_brief_json,
    render_daily_research_brief_text,
)
from empirical_platform.usecases.list_daily_research_sessions import (
    ListDailyResearchSessionsHandler,
    ListDailyResearchSessionsQuery,
)

_USAGE = (
    "usage: empirical-platform-daily-brief [--json] [--no-historical-evidence] "
    "[--no-capital-feasibility] [--no-portfolio-aware-feasibility] "
    "[<session_governance_id> <session_runtime_id>]"
)


def run_build_daily_research_brief(
    *,
    session_governance_id: str | None,
    session_runtime_id: str | None,
    config: PostgreSQLConfigSnapshot | None = None,
    include_historical_evidence: bool = True,
    include_capital_feasibility: bool = True,
    include_portfolio_aware_feasibility: bool = True,
) -> DailyResearchBrief:
    """Build one daily research brief end-to-end against real
    PostgreSQL. With no explicit session, defaults to the single most
    recent session across all universes."""
    with postgres_repository_runtime(config) as runtime:
        if session_governance_id is not None and session_runtime_id is not None:
            identity = DomainIdentity(
                governance_id=ResearchSessionId(session_governance_id),
                runtime_id=RuntimeIdentifier(session_runtime_id),
            )
        else:
            list_handler = ListDailyResearchSessionsHandler(repository=runtime.research_sessions)
            recent = QueryEntryPoint(list_handler)(
                ListDailyResearchSessionsQuery(universe=None, limit=1)
            )
            if not recent:
                raise SystemExit(
                    "no daily research session has ever been run -- "
                    "run empirical-platform-run-daily-research first"
                )
            identity = recent[0].identity

        handler = BuildDailyResearchBriefHandler(
            research_session_repository=runtime.research_sessions,
            decision_candidate_repository=runtime.decision_candidates,
            trade_plan_repository=runtime.trade_plans,
            position_plan_repository=runtime.position_plans,
            historical_evidence_query_repository=(
                runtime.historical_portfolio_evidence_query if include_historical_evidence else None
            ),
            include_capital_feasibility=include_capital_feasibility,
            operator_position_ledger_repository=(
                runtime.operator_position_ledger if include_portfolio_aware_feasibility else None
            ),
            include_portfolio_aware_feasibility=include_portfolio_aware_feasibility,
        )
        entry_point = QueryEntryPoint(handler)
        return entry_point(BuildDailyResearchBriefQuery(identity=identity))


def main() -> None:
    args = sys.argv[1:]
    as_json = "--json" in args
    include_historical_evidence = "--no-historical-evidence" not in args
    include_capital_feasibility = "--no-capital-feasibility" not in args
    include_portfolio_aware = "--no-portfolio-aware-feasibility" not in args
    positional = [
        a
        for a in args
        if a
        not in (
            "--json",
            "--no-historical-evidence",
            "--no-capital-feasibility",
            "--no-portfolio-aware-feasibility",
        )
    ]

    if len(positional) not in (0, 2):
        raise SystemExit(_USAGE)

    session_governance_id = positional[0] if positional else None
    session_runtime_id = positional[1] if positional else None

    brief = run_build_daily_research_brief(
        session_governance_id=session_governance_id,
        session_runtime_id=session_runtime_id,
        include_historical_evidence=include_historical_evidence,
        include_capital_feasibility=include_capital_feasibility,
        include_portfolio_aware_feasibility=include_portfolio_aware,
    )
    if as_json:
        print(json.dumps(render_daily_research_brief_json(brief), sort_keys=True))
    else:
        print(render_daily_research_brief_text(brief), end="")


if __name__ == "__main__":
    main()
