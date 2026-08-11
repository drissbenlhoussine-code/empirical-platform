"""Real end-to-end portfolio capital-allocation evidence composition
root.

MILESTONE-067. A caller supplies the governance identity of one
already-persisted M064 `SurvivorshipAwareRobustnessStudy` and receives one
structured, persisted `PortfolioEvidenceReport` -- built entirely from
that study's own already-frozen window results and the individual M061
`HistoricalBacktestRun`s they reference. No strategy, ranking, risk,
sizing, or backtest logic is re-run.
"""

from __future__ import annotations

import json
import sys
from decimal import Decimal

from empirical_platform.application.command import CommandEntryPoint
from empirical_platform.entrypoints._composition import postgres_repository_runtime
from empirical_platform.shared.config.settings import PostgreSQLConfigSnapshot
from empirical_platform.shared.identifiers import (
    RuntimeIdentifierGenerator,
    UuidRuntimeIdentifierGenerator,
)
from empirical_platform.usecases.portfolio_study_io import portfolio_evidence_report_payload
from empirical_platform.usecases.run_portfolio_historical_evidence import (
    PortfolioCapitalPolicy,
    RunPortfolioHistoricalEvidenceHandler,
    build_run_portfolio_historical_evidence_command,
)


def run_run_portfolio_historical_evidence(
    *,
    report_governance_id: str,
    source_study_governance_id: str,
    source_study_runtime_id: str,
    initial_capital: Decimal = Decimal("100000"),
    currency: str = "USD",
    max_concurrent_positions: int = 10,
    max_capital_utilization_percent: Decimal = Decimal("1.00"),
    identifier_generator: RuntimeIdentifierGenerator | None = None,
    config: PostgreSQLConfigSnapshot | None = None,
) -> object:
    """Run one deterministic portfolio capital-allocation evidence
    evaluation end-to-end against real PostgreSQL."""
    resolved_generator = identifier_generator or UuidRuntimeIdentifierGenerator()
    capital_policy = PortfolioCapitalPolicy(
        policy_id="PORTFOLIO-CAPITAL-DEFAULT",
        version="1",
        initial_capital=initial_capital,
        currency=currency,
        max_concurrent_positions=max_concurrent_positions,
        max_capital_utilization_percent=max_capital_utilization_percent,
    )
    with postgres_repository_runtime(config) as runtime:
        handler = RunPortfolioHistoricalEvidenceHandler(
            report_repository=runtime.portfolio_studies,
            study_repository=runtime.survivorship_studies,
            historical_backtest_run_repository=runtime.historical_backtests,
        )
        entry_point = CommandEntryPoint(handler)
        return entry_point(
            build_run_portfolio_historical_evidence_command(
                report_governance_id=report_governance_id,
                source_study_governance_id=source_study_governance_id,
                source_study_runtime_id=source_study_runtime_id,
                runtime_identifier_generator=resolved_generator,
                capital_policy=capital_policy,
            )
        )


def _report_payload(report: object) -> dict[str, object]:
    return portfolio_evidence_report_payload(report)


def main() -> None:
    if len(sys.argv) not in (4, 5, 6, 7, 8):
        raise SystemExit(
            "usage: empirical-platform-run-portfolio-historical-evidence "
            "<report_governance_id> <source_study_governance_id> <source_study_runtime_id> "
            "[initial_capital] [currency] [max_concurrent_positions] "
            "[max_capital_utilization_percent]"
        )
    result = run_run_portfolio_historical_evidence(
        report_governance_id=sys.argv[1],
        source_study_governance_id=sys.argv[2],
        source_study_runtime_id=sys.argv[3],
        initial_capital=Decimal(sys.argv[4]) if len(sys.argv) > 4 else Decimal("100000"),
        currency=sys.argv[5] if len(sys.argv) > 5 else "USD",
        max_concurrent_positions=int(sys.argv[6]) if len(sys.argv) > 6 else 10,
        max_capital_utilization_percent=(
            Decimal(sys.argv[7]) if len(sys.argv) > 7 else Decimal("1.00")
        ),
    )
    print(json.dumps(_report_payload(result), sort_keys=True))


if __name__ == "__main__":
    main()
