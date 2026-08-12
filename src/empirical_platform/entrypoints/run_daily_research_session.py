"""Real end-to-end daily research session composition root.

MILESTONE-070. ONE command: an operator supplies a session identity, an
as-of date, an account equity + risk percent, and a list of ticker
symbols, and receives one complete, persisted, auditable daily research
session -- real market data acquired via the frozen M069 pipeline,
candidates evaluated and ranked via the frozen M057/M058 pipeline,
risk-gated and sized via the frozen M059/M060 pipeline, and backed by
frozen M061 historical backtest evidence. The operator never touches a
Campaign, Run, EvidencePackage, scan, trade plan, or position plan by
name -- the orchestrator coordinates the correct frozen stack
transparently (mission Phase 23).

Uses the real, network-capable M069 `YahooFinanceChartMarketDataSource`
by default; canonical, network-free acceptance uses the same
orchestration usecase directly with `FakeMarketDataSource` injected
(see the M070 test suite), never a second orchestration path.
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, date, datetime
from decimal import Decimal

from empirical_platform.application.command import CommandEntryPoint
from empirical_platform.entrypoints._composition import postgres_repository_runtime
from empirical_platform.shared.config.settings import PostgreSQLConfigSnapshot
from empirical_platform.shared.identifiers import UuidRuntimeIdentifierGenerator
from empirical_platform.shared.interfaces.clock import SystemWallClock
from empirical_platform.usecases.acquire_market_data_snapshot import (
    YahooFinanceChartMarketDataSource,
)
from empirical_platform.usecases.research_session_io import research_session_report_payload
from empirical_platform.usecases.run_daily_research_session import (
    RunDailyResearchSessionHandler,
    build_run_daily_research_session_command,
)


def run_run_daily_research_session(
    *,
    session_governance_id: str,
    as_of_date: str,
    lookback_days: int,
    artifact_path: str,
    account_equity: Decimal,
    risk_percent: Decimal,
    universe: tuple[str, ...],
    config: PostgreSQLConfigSnapshot | None = None,
) -> object:
    """Run one deterministic daily research session end-to-end against
    real PostgreSQL, via the real network-capable Yahoo Finance
    adapter."""
    clock = SystemWallClock()
    source = YahooFinanceChartMarketDataSource(clock=clock)
    generator = UuidRuntimeIdentifierGenerator()
    as_of = datetime.combine(date.fromisoformat(as_of_date), datetime.min.time(), tzinfo=UTC)
    with postgres_repository_runtime(config) as runtime:
        handler = RunDailyResearchSessionHandler(
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
        entry_point = CommandEntryPoint(handler)
        return entry_point(
            build_run_daily_research_session_command(
                session_governance_id=session_governance_id,
                as_of=as_of,
                universe=universe,
                lookback_days=lookback_days,
                artifact_path=artifact_path,
                account_equity=account_equity,
                risk_percent=risk_percent,
                source=source,
                runtime_identifier_generator=generator,
            )
        )


def main() -> None:
    if len(sys.argv) < 7:
        raise SystemExit(
            "usage: empirical-platform-run-daily-research "
            "<session_governance_id> <as_of_date:YYYY-MM-DD> <lookback_days> "
            "<artifact_path> <account_equity> <risk_percent> <symbol> [symbol ...]"
        )
    result = run_run_daily_research_session(
        session_governance_id=sys.argv[1],
        as_of_date=sys.argv[2],
        lookback_days=int(sys.argv[3]),
        artifact_path=sys.argv[4],
        account_equity=Decimal(sys.argv[5]),
        risk_percent=Decimal(sys.argv[6]),
        universe=tuple(sys.argv[7:]),
    )
    payload = research_session_report_payload(result)
    print(json.dumps(payload, sort_keys=True))
    if payload["FACT"]["completion_status"] != "COMPLETED":  # type: ignore[index]
        sys.exit(1)


if __name__ == "__main__":
    main()
