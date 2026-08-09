"""Real end-to-end historical backtest composition root.

MILESTONE-061. A caller supplies one fixed local dataset fixture file plus
explicit sizing/cost inputs and receives one structured, persisted,
deterministic historical-validation result.
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
from empirical_platform.usecases.historical_backtest_io import (
    historical_backtest_run_payload,
)
from empirical_platform.usecases.historical_backtest_io import (
    parse_historical_backtest_dataset_file as _parse_dataset_file,
)
from empirical_platform.usecases.run_historical_backtest import (
    RunHistoricalBacktestHandler,
    build_run_historical_backtest_command,
)


def run_historical_backtest(
    *,
    run_governance_id: str,
    dataset_file: str,
    account_equity: Decimal,
    risk_percent: Decimal,
    reference_window_size: int = 5,
    holding_horizon_bars: int = 3,
    entry_slippage_bps: Decimal = Decimal("5"),
    exit_slippage_bps: Decimal = Decimal("5"),
    fixed_commission_per_side: Decimal = Decimal("0"),
    identifier_generator: RuntimeIdentifierGenerator | None = None,
    config: PostgreSQLConfigSnapshot | None = None,
) -> object:
    """Run one deterministic historical backtest end-to-end against real PostgreSQL."""
    resolved_generator = identifier_generator or UuidRuntimeIdentifierGenerator()
    dataset = _parse_dataset_file(dataset_file)
    with postgres_repository_runtime(config) as runtime:
        handler = RunHistoricalBacktestHandler(repository=runtime.historical_backtests)
        entry_point = CommandEntryPoint(handler)
        return entry_point(
            build_run_historical_backtest_command(
                run_governance_id=run_governance_id,
                dataset=dataset,
                runtime_identifier_generator=resolved_generator,
                account_equity=account_equity,
                risk_percent=risk_percent,
                reference_window_size=reference_window_size,
                holding_horizon_bars=holding_horizon_bars,
                entry_slippage_bps=entry_slippage_bps,
                exit_slippage_bps=exit_slippage_bps,
                fixed_commission_per_side=fixed_commission_per_side,
            )
        )


def _run_payload(run: object) -> dict[str, object]:
    return historical_backtest_run_payload(run)


def main() -> None:
    if len(sys.argv) not in (5, 6, 7, 8, 9):
        raise SystemExit(
            "usage: empirical-platform-run-historical-backtest "
            "<run_governance_id> <dataset_file> <account_equity> <risk_percent> "
            "[reference_window_size] [holding_horizon_bars] [entry_slippage_bps] "
            "[exit_slippage_bps]"
        )
    run = run_historical_backtest(
        run_governance_id=sys.argv[1],
        dataset_file=sys.argv[2],
        account_equity=Decimal(sys.argv[3]),
        risk_percent=Decimal(sys.argv[4]),
        reference_window_size=int(sys.argv[5]) if len(sys.argv) > 5 else 5,
        holding_horizon_bars=int(sys.argv[6]) if len(sys.argv) > 6 else 3,
        entry_slippage_bps=Decimal(sys.argv[7]) if len(sys.argv) > 7 else Decimal("5"),
        exit_slippage_bps=Decimal(sys.argv[8]) if len(sys.argv) > 8 else Decimal("5"),
    )
    print(json.dumps(_run_payload(run), sort_keys=True))


if __name__ == "__main__":
    main()
