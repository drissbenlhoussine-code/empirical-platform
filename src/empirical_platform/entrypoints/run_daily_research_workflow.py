"""One-command pre-market daily research workflow composition root.

MILESTONE-073. Closes the sharpest friction found in a fresh, live
20-area product-reality audit: an operator's real morning routine
required two separate commands (`run-daily-research` then
`daily-brief`), a hand-invented session identifier, and fully retyped
universe/equity/risk-percent inputs every single day, with no
persisted defaults anywhere.

This module introduces zero new business logic, zero new domain
model, and zero new persistence. It is pure composition-root
orchestration over two already-frozen, unmodified usecase handlers:
`RunDailyResearchSessionHandler` (MILESTONE-070) and
`BuildDailyResearchBriefHandler` (MILESTONE-072), sharing one
PostgreSQL runtime so the just-created session's own identity is
passed directly into the brief -- never re-discovered via a separate
"latest session" lookup.
"""

from __future__ import annotations

import json
import random
import sys
import tempfile
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from empirical_platform.application.query import QueryEntryPoint
from empirical_platform.entrypoints._composition import postgres_repository_runtime
from empirical_platform.identifiers.pairs import DomainIdentity
from empirical_platform.identifiers.types import ResearchSessionId
from empirical_platform.shared.config.settings import PostgreSQLConfigSnapshot
from empirical_platform.shared.identifiers import UuidRuntimeIdentifierGenerator
from empirical_platform.shared.interfaces.clock import SystemWallClock
from empirical_platform.usecases.acquire_market_data_snapshot import (
    YahooFinanceChartMarketDataSource,
)
from empirical_platform.usecases.build_daily_research_brief import (
    BuildDailyResearchBriefHandler,
    BuildDailyResearchBriefQuery,
    DailyResearchBrief,
)
from empirical_platform.usecases.daily_research_brief_io import (
    render_daily_research_brief_json,
    render_daily_research_brief_text,
)
from empirical_platform.usecases.run_daily_research_session import (
    RunDailyResearchSessionHandler,
    build_run_daily_research_session_command,
)

_USAGE = (
    "usage: empirical-platform-daily-workflow [--json] "
    "[--as-of YYYY-MM-DD] [--lookback-days N] "
    "[--account-equity X] [--risk-percent X] "
    "[--artifact-path PATH] [--no-historical-evidence] "
    "<symbol> [symbol ...]"
)

#: Sensible, documented, overridable defaults -- avoids a 30-argument
#: CLI (mirroring RunDailyResearchSessionCommand's own precedent of
#: frozen defaults for everything not genuinely operator-necessary).
_DEFAULT_LOOKBACK_DAYS = 20
_DEFAULT_ACCOUNT_EQUITY = Decimal("100000")
_DEFAULT_RISK_PERCENT = Decimal("0.01")


def _random_session_governance_id(rng: random.Random) -> str:
    """Auto-generate a session governance id so the operator never
    has to hand-invent one. Collision handling mirrors the existing,
    established `_derived_governance_id` precedent (MILESTONE-070):
    a residual collision probability is inherent to the shared
    4-digit keyspace; `AggregateAlreadyExists` is the honest,
    disclosed backstop, never silently swallowed."""
    return f"RESEARCH-{rng.randint(0, 9999):04d}"


def _default_artifact_path(session_governance_id: str) -> str:
    return str(Path(tempfile.gettempdir()) / "empirical-platform" / f"{session_governance_id}.json")


def run_daily_research_workflow(
    *,
    symbols: tuple[str, ...],
    as_of_date: str | None,
    lookback_days: int,
    account_equity: Decimal,
    risk_percent: Decimal,
    artifact_path: str | None,
    config: PostgreSQLConfigSnapshot | None = None,
    rng: random.Random | None = None,
    include_historical_evidence: bool = True,
) -> DailyResearchBrief:
    """Run one complete daily research session against real
    PostgreSQL and the real network-capable Yahoo Finance adapter,
    then immediately build the resulting brief for that exact session
    -- one command, one artifact, no separate "find the latest
    session" step.

    Rejects a duplicate symbol before ever reaching the frozen M070
    orchestrator: `RunDailyResearchSessionHandler`'s own honest
    -failure path itself constructs a `ResearchSession` to record
    *any* failure, and that construction's own duplicate-instrument
    validation raises uncaught when the duplicate is the requested
    universe itself -- a genuine, pre-existing defect confirmed to
    predate this milestone (reproduced identically via the
    already-frozen, unmodified `run-daily-research` entrypoint).
    M070 is not reopened to fix this; this entrypoint instead rejects
    the malformed input honestly before it ever reaches that code
    path.
    """
    if len(set(symbols)) != len(symbols):
        raise ValueError(f"duplicate symbol in universe: {symbols!r}")
    clock = SystemWallClock()
    source = YahooFinanceChartMarketDataSource(clock=clock)
    generator = UuidRuntimeIdentifierGenerator()
    resolved_rng = rng if rng is not None else random.Random()  # noqa: S311

    resolved_as_of = (
        datetime.combine(date.fromisoformat(as_of_date), datetime.min.time(), tzinfo=UTC)
        if as_of_date is not None
        else datetime.combine(clock.now().date(), datetime.min.time(), tzinfo=UTC)
    )
    session_governance_id = _random_session_governance_id(resolved_rng)
    resolved_artifact_path = (
        artifact_path
        if artifact_path is not None
        else _default_artifact_path(session_governance_id)
    )
    Path(resolved_artifact_path).parent.mkdir(parents=True, exist_ok=True)

    with postgres_repository_runtime(config) as runtime:
        session_handler = RunDailyResearchSessionHandler(
            campaign_repository=runtime.campaigns,
            run_repository=runtime.runs,
            evidence_package_repository=runtime.evidence_packages,
            dataset_snapshot_repository=runtime.dataset_snapshots,
            instrument_master_repository=runtime.instrument_masters,
            decision_candidate_repository=runtime.decision_candidates,
            trading_opportunity_scan_repository=runtime.trading_opportunity_scans,
            trade_plan_repository=runtime.trade_plans,
            position_plan_repository=runtime.position_plans,
            historical_backtest_repository=runtime.historical_backtests,
            research_session_repository=runtime.research_sessions,
            clock=clock,
            runtime_identifier_generator=generator,
        )
        session = session_handler.handle(
            build_run_daily_research_session_command(
                session_governance_id=session_governance_id,
                as_of=resolved_as_of,
                universe=symbols,
                lookback_days=lookback_days,
                artifact_path=resolved_artifact_path,
                account_equity=account_equity,
                risk_percent=risk_percent,
                source=source,
                runtime_identifier_generator=generator,
            )
        )

        brief_handler = BuildDailyResearchBriefHandler(
            research_session_repository=runtime.research_sessions,
            decision_candidate_repository=runtime.decision_candidates,
            trade_plan_repository=runtime.trade_plans,
            position_plan_repository=runtime.position_plans,
            historical_evidence_query_repository=(
                runtime.historical_portfolio_evidence_query
                if include_historical_evidence
                else None
            ),
        )
        entry_point = QueryEntryPoint(brief_handler)
        return entry_point(
            BuildDailyResearchBriefQuery(
                identity=DomainIdentity(
                    governance_id=ResearchSessionId(session_governance_id),
                    runtime_id=session.identity.runtime_id,
                )
            )
        )


def _parse_args(args: list[str]) -> dict[str, object]:
    as_json = False
    as_of_date: str | None = None
    lookback_days = _DEFAULT_LOOKBACK_DAYS
    account_equity = _DEFAULT_ACCOUNT_EQUITY
    risk_percent = _DEFAULT_RISK_PERCENT
    artifact_path: str | None = None
    symbols: list[str] = []
    include_historical_evidence = True

    i = 0
    while i < len(args):
        arg = args[i]
        if arg == "--json":
            as_json = True
            i += 1
        elif arg == "--as-of":
            _require_value(args, i, "--as-of")
            as_of_date = args[i + 1]
            i += 2
        elif arg == "--lookback-days":
            _require_value(args, i, "--lookback-days")
            lookback_days = _parse_int(args[i + 1], "--lookback-days")
            i += 2
        elif arg == "--account-equity":
            _require_value(args, i, "--account-equity")
            account_equity = _parse_decimal(args[i + 1], "--account-equity")
            i += 2
        elif arg == "--risk-percent":
            _require_value(args, i, "--risk-percent")
            risk_percent = _parse_decimal(args[i + 1], "--risk-percent")
            i += 2
        elif arg == "--artifact-path":
            _require_value(args, i, "--artifact-path")
            artifact_path = args[i + 1]
            i += 2
        elif arg == "--no-historical-evidence":
            include_historical_evidence = False
            i += 1
        elif arg.startswith("--"):
            raise SystemExit(_USAGE)
        else:
            symbols.append(arg)
            i += 1

    if not symbols:
        raise SystemExit(_USAGE)

    return {
        "as_json": as_json,
        "as_of_date": as_of_date,
        "lookback_days": lookback_days,
        "account_equity": account_equity,
        "risk_percent": risk_percent,
        "artifact_path": artifact_path,
        "symbols": tuple(symbols),
        "include_historical_evidence": include_historical_evidence,
    }


def _require_value(args: list[str], i: int, flag: str) -> None:
    if i + 1 >= len(args):
        raise SystemExit(f"{flag} requires a value\n{_USAGE}")


def _parse_int(raw: str, flag: str) -> int:
    try:
        return int(raw)
    except ValueError as exc:
        raise SystemExit(f"{flag} must be an integer, got {raw!r}\n{_USAGE}") from exc


def _parse_decimal(raw: str, flag: str) -> Decimal:
    try:
        return Decimal(raw)
    except InvalidOperation as exc:
        raise SystemExit(f"{flag} must be a decimal number, got {raw!r}\n{_USAGE}") from exc


def main() -> None:
    parsed = _parse_args(sys.argv[1:])
    try:
        brief = run_daily_research_workflow(
            symbols=parsed["symbols"],  # type: ignore[arg-type]
            as_of_date=parsed["as_of_date"],  # type: ignore[arg-type]
            lookback_days=parsed["lookback_days"],  # type: ignore[arg-type]
            account_equity=parsed["account_equity"],  # type: ignore[arg-type]
            risk_percent=parsed["risk_percent"],  # type: ignore[arg-type]
            artifact_path=parsed["artifact_path"],  # type: ignore[arg-type]
            include_historical_evidence=parsed["include_historical_evidence"],  # type: ignore[arg-type]
        )
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    if parsed["as_json"]:
        print(json.dumps(render_daily_research_brief_json(brief), sort_keys=True))
    else:
        print(render_daily_research_brief_text(brief), end="")


if __name__ == "__main__":
    main()
