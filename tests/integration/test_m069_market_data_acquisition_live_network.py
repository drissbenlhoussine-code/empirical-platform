"""MILESTONE-069 real-network acquisition proof.

Explicitly opt-in via `EMPIRICAL_PLATFORM_RUN_NETWORK_TESTS=1`, mirroring
the established `EMPIRICAL_PLATFORM_RUN_POSTGRES_TESTS` gating pattern --
never required for canonical CI/build acceptance, since it depends on a
real, unauthenticated third-party endpoint being reachable and stable.
This is the one place in the entire test suite that performs a genuine
outbound HTTP request; every other M069 test (unit, PostgreSQL
lifecycle, independent verification) uses `FakeMarketDataSource` and is
fully offline and deterministic.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from empirical_platform.decision_candidate.dataset_snapshot import DatasetSnapshotAuthority
from empirical_platform.decision_candidate.dataset_snapshot_repository import (
    DatasetSnapshotRepository,
)
from empirical_platform.decision_candidate.historical_import import parse_source_csv
from empirical_platform.decision_candidate.instrument_master import InstrumentMaster
from empirical_platform.decision_candidate.market_data import BarInterval, Instrument
from empirical_platform.decision_candidate.market_data_acquisition import (
    YAHOO_FINANCE_SOURCE_NAME,
    MarketDataFetchRequest,
    YahooFinanceChartMarketDataSource,
    translate_fetch_result_to_pipeline_csv,
)
from empirical_platform.identifiers.types import DatasetId
from empirical_platform.shared.interfaces.clock import SystemWallClock
from empirical_platform.usecases.acquire_market_data_snapshot import (
    AcquireMarketDataSnapshotHandler,
    build_acquire_market_data_snapshot_command,
    build_trivial_instrument_master,
)

pytestmark = pytest.mark.integration


def _network_enabled() -> bool:
    return os.environ.get("EMPIRICAL_PLATFORM_RUN_NETWORK_TESTS") == "1"


@dataclass
class _InMemoryDatasetSnapshotRepository(DatasetSnapshotRepository):
    added: dict[tuple[str, str], DatasetSnapshotAuthority]

    def get(self, dataset_id: DatasetId, dataset_version: str) -> DatasetSnapshotAuthority:
        return self.added[(str(dataset_id), dataset_version)]

    def add(self, snapshot: DatasetSnapshotAuthority) -> None:
        self.added[(str(snapshot.dataset_id), snapshot.dataset_version)] = snapshot


@dataclass
class _InMemoryInstrumentMasterRepository:
    added: list[InstrumentMaster]

    def add_all(self, master: InstrumentMaster) -> None:
        self.added.append(master)


@pytest.fixture(autouse=True)
def _skip_without_network_opt_in() -> None:
    if not _network_enabled():
        pytest.skip("real-network tests require explicit opt-in")


def test_real_fetch_returns_genuine_recent_daily_bars() -> None:
    """Attempt to disprove genuine acquisition: fetch real AAPL daily
    bars over the last 30 days and verify they are structurally sane,
    chronological, and parse through the unmodified frozen
    `parse_source_csv` -- never a fabricated or empty substitute."""
    clock = SystemWallClock()
    source = YahooFinanceChartMarketDataSource(clock=clock)
    end = date.today()  # noqa: DTZ011
    start = end - timedelta(days=30)
    result = source.fetch(
        MarketDataFetchRequest(
            symbol="AAPL", start_date=start, end_date=end, interval=BarInterval.ONE_DAY
        )
    )
    assert result.source_format == "YAHOO_FINANCE_CHART_JSON"
    assert result.symbol == "AAPL"
    assert "AAPL" in result.source_reference
    assert result.fetched_at.tzinfo is not None

    pipeline_csv = translate_fetch_result_to_pipeline_csv(result)
    bars = parse_source_csv(
        pipeline_csv, instrument=Instrument("AAPL"), interval=BarInterval.ONE_DAY
    )

    assert len(bars) > 0
    for prev_bar, bar in zip(bars, bars[1:], strict=False):
        assert bar.timestamp > prev_bar.timestamp  # genuinely chronological
    for bar in bars:
        assert bar.open > 0
        assert bar.high >= bar.low
        assert bar.high >= bar.open
        assert bar.high >= bar.close
        assert bar.low <= bar.open
        assert bar.low <= bar.close
        assert bar.volume > 0
    # A real, recent close is nowhere near a hand-picked round number --
    # this is genuinely fetched, not a fixture disguised as real data.
    assert bars[-1].close != Decimal("100.0000")


def test_real_acquisition_end_to_end_produces_real_dataset_snapshot(tmp_path: Path) -> None:
    """The strongest test: drive the real adapter through the full,
    unmodified acquisition handler and confirm a genuine
    `DatasetSnapshotAuthority` is produced with an honestly-labeled
    `source_name` -- never silently mistaken for a Fake/offline run."""
    clock = SystemWallClock()
    source = YahooFinanceChartMarketDataSource(clock=clock)
    snapshots = _InMemoryDatasetSnapshotRepository(added={})
    handler = AcquireMarketDataSnapshotHandler(
        dataset_snapshot_repository=snapshots,
        instrument_master_repository=_InMemoryInstrumentMasterRepository(added=[]),
        source=source,
        clock_now=clock.now(),
    )
    end = date.today()  # noqa: DTZ011
    start = end - timedelta(days=30)
    result = handler.handle(
        build_acquire_market_data_snapshot_command(
            dataset_id="DATASET-6905",
            dataset_version="1",
            symbols=("MSFT",),
            start_date=start,
            end_date=end,
            interval=BarInterval.ONE_DAY,
            instrument_master=build_trivial_instrument_master(("MSFT",)),
            artifact_path=str(tmp_path / "live_artifact.json"),
            license_note="live network acquisition proof",
        )
    )
    assert result.adapter_source_name == YAHOO_FINANCE_SOURCE_NAME
    assert result.snapshot.total_row_count > 0
    assert result.snapshot.source_kind == "MARKET_DATA_ACQUISITION"
    assert "query1.finance.yahoo.com" in result.symbol_provenance[0].source_reference
    assert result.symbol_provenance[0].fetched_at <= datetime.now(UTC)
    assert Path(result.artifact_path).exists()
    assert snapshots.added[("DATASET-6905", "1")] == result.snapshot
