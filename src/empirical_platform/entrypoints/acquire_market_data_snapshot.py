"""Real end-to-end market-data acquisition composition root.

MILESTONE-069. A caller supplies one or more ticker symbols, an explicit
date range, and a dataset identity, and receives one persisted
`RAW_UNADJUSTED` `DatasetSnapshotAuthority` built from real historical
daily bars fetched from Yahoo Finance's unofficial, no-authentication
chart endpoint -- plus an on-disk M061-compatible dataset JSON artifact
that can be handed directly to the unmodified, frozen
`empirical-platform-run-historical-backtest` CLI. Retrieval reuses the
existing, unmodified `empirical-platform-get-historical-dataset-snapshot`
CLI verbatim; no second retrieval path is introduced.

A trivial `InstrumentMaster` (one entry per requested symbol, type
`EQUITY`, `InstrumentId` derived deterministically from the symbol) is
constructed automatically -- richer venue/instrument-type classification
is M064's own job, out of scope here.
"""

from __future__ import annotations

import json
import sys
from datetime import date

from empirical_platform.application.command import CommandEntryPoint
from empirical_platform.entrypoints._composition import postgres_repository_runtime
from empirical_platform.shared.config.settings import PostgreSQLConfigSnapshot
from empirical_platform.shared.interfaces.clock import SystemWallClock
from empirical_platform.usecases.acquire_market_data_snapshot import (
    AcquireMarketDataSnapshotHandler,
    BarInterval,
    YahooFinanceChartMarketDataSource,
    build_acquire_market_data_snapshot_command,
    build_trivial_instrument_master,
)
from empirical_platform.usecases.market_data_acquisition_io import (
    acquire_market_data_snapshot_result_payload,
)


def run_acquire_market_data_snapshot(
    *,
    dataset_id: str,
    dataset_version: str,
    symbols: tuple[str, ...],
    start_date: str,
    end_date: str,
    artifact_path: str,
    config: PostgreSQLConfigSnapshot | None = None,
) -> object:
    """Acquire one deterministic real-market-data snapshot end-to-end
    against real PostgreSQL, via the real network-capable Yahoo Finance
    adapter."""
    clock = SystemWallClock()
    source = YahooFinanceChartMarketDataSource(clock=clock)
    instrument_master = build_trivial_instrument_master(symbols)
    with postgres_repository_runtime(config) as runtime:
        handler = AcquireMarketDataSnapshotHandler(
            dataset_snapshot_repository=runtime.dataset_snapshots,
            instrument_master_repository=runtime.instrument_masters,
            source=source,
            clock_now=clock.now(),
        )
        entry_point = CommandEntryPoint(handler)
        return entry_point(
            build_acquire_market_data_snapshot_command(
                dataset_id=dataset_id,
                dataset_version=dataset_version,
                symbols=symbols,
                start_date=date.fromisoformat(start_date),
                end_date=date.fromisoformat(end_date),
                interval=BarInterval.ONE_DAY,
                instrument_master=instrument_master,
                artifact_path=artifact_path,
                license_note=(
                    "Real historical daily bars fetched from Yahoo Finance's unofficial, "
                    "no-authentication chart JSON endpoint -- read-only, publicly-published "
                    "price data, not a licensed vendor relationship."
                ),
            )
        )


def main() -> None:
    if len(sys.argv) < 7:
        raise SystemExit(
            "usage: empirical-platform-acquire-market-data-snapshot "
            "<dataset_id> <dataset_version> <start_date:YYYY-MM-DD> <end_date:YYYY-MM-DD> "
            "<artifact_path> <symbol> [symbol ...]"
        )
    result = run_acquire_market_data_snapshot(
        dataset_id=sys.argv[1],
        dataset_version=sys.argv[2],
        start_date=sys.argv[3],
        end_date=sys.argv[4],
        artifact_path=sys.argv[5],
        symbols=tuple(sys.argv[6:]),
    )
    print(json.dumps(acquire_market_data_snapshot_result_payload(result), sort_keys=True))


if __name__ == "__main__":
    main()
