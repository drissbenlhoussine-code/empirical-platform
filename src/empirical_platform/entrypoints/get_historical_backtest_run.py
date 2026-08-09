"""Real end-to-end historical backtest retrieval composition root."""

from __future__ import annotations

import json
import sys

from empirical_platform.application.query import QueryEntryPoint
from empirical_platform.entrypoints._composition import postgres_repository_runtime
from empirical_platform.entrypoints.run_historical_backtest import _run_payload
from empirical_platform.identifiers.pairs import DomainIdentity
from empirical_platform.identifiers.types import BacktestRunId
from empirical_platform.shared.config.settings import PostgreSQLConfigSnapshot
from empirical_platform.shared.identifiers import RuntimeIdentifier
from empirical_platform.usecases.get_historical_backtest_run import (
    GetHistoricalBacktestRunHandler,
    GetHistoricalBacktestRunQuery,
)


def run_get_historical_backtest_run(
    *,
    backtest_run_governance_id: str,
    backtest_run_runtime_id: str,
    config: PostgreSQLConfigSnapshot | None = None,
) -> object:
    """Retrieve one historical backtest run end-to-end against real PostgreSQL."""
    with postgres_repository_runtime(config) as runtime:
        handler = GetHistoricalBacktestRunHandler(repository=runtime.historical_backtests)
        entry_point = QueryEntryPoint(handler)
        return entry_point(
            GetHistoricalBacktestRunQuery(
                identity=DomainIdentity(
                    governance_id=BacktestRunId(backtest_run_governance_id),
                    runtime_id=RuntimeIdentifier(backtest_run_runtime_id),
                )
            )
        )


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit(
            "usage: empirical-platform-get-historical-backtest-run <governance_id> <runtime_id>"
        )
    run = run_get_historical_backtest_run(
        backtest_run_governance_id=sys.argv[1],
        backtest_run_runtime_id=sys.argv[2],
    )
    print(json.dumps(_run_payload(run), sort_keys=True))


if __name__ == "__main__":
    main()
