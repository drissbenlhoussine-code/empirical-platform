"""Pure, offline application-layer tests for MILESTONE-069's
`AcquireMarketDataSnapshotHandler`, using `FakeMarketDataSource` and
in-memory repositories -- no network, no PostgreSQL. Mirrors the
established M065 `_InMemoryDatasetSnapshotRepository`/
`_InMemoryInstrumentMasterRepository` precedent
(`tests/unit/test_m065_dataset_snapshot_application.py`).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from empirical_platform.decision_candidate.dataset_snapshot import (
    CorporateActionSemantics,
    DatasetSnapshotAuthority,
    PriceSemantics,
)
from empirical_platform.decision_candidate.dataset_snapshot_repository import (
    DatasetSnapshotRepository,
)
from empirical_platform.decision_candidate.instrument_master import InstrumentMaster
from empirical_platform.decision_candidate.market_data import BarInterval
from empirical_platform.decision_candidate.market_data_acquisition import FakeMarketDataSource
from empirical_platform.identifiers.types import DatasetId
from empirical_platform.shared.interfaces.clock import FixedWallClock
from empirical_platform.usecases.acquire_market_data_snapshot import (
    AcquireMarketDataSnapshotHandler,
    build_acquire_market_data_snapshot_command,
    build_trivial_instrument_master,
)
from empirical_platform.usecases.market_data_acquisition_io import (
    acquire_market_data_snapshot_result_payload,
)

_CLOCK = FixedWallClock(datetime(2026, 8, 11, 12, 0, tzinfo=UTC))

_AAPL_CSV = (
    b"timestamp,open,high,low,close,volume\n"
    b"2024-06-03T00:00:00+00:00,192.9000,194.9900,192.5200,194.0300,50080500\n"
    b"2024-06-04T00:00:00+00:00,194.6400,195.3200,193.0300,194.3500,47471400\n"
)
_MSFT_CSV = (
    b"timestamp,open,high,low,close,volume\n"
    b"2024-06-03T00:00:00+00:00,415.0000,417.5000,413.0000,416.2500,20000000\n"
    b"2024-06-04T00:00:00+00:00,416.5000,418.0000,414.0000,417.0000,19000000\n"
)


@dataclass
class _InMemoryDatasetSnapshotRepository(DatasetSnapshotRepository):
    added: dict[tuple[str, str], DatasetSnapshotAuthority]

    def get(self, dataset_id: DatasetId, dataset_version: str) -> DatasetSnapshotAuthority:
        return self.added[(str(dataset_id), dataset_version)]

    def add(self, snapshot: DatasetSnapshotAuthority) -> None:
        key = (str(snapshot.dataset_id), snapshot.dataset_version)
        if key in self.added:
            raise ValueError(f"snapshot already exists for {key}")
        self.added[key] = snapshot


@dataclass
class _InMemoryInstrumentMasterRepository:
    added: list[InstrumentMaster]

    def add_all(self, master: InstrumentMaster) -> None:
        self.added.append(master)


def _handler(
    source: FakeMarketDataSource,
) -> tuple[AcquireMarketDataSnapshotHandler, _InMemoryDatasetSnapshotRepository]:
    snapshots = _InMemoryDatasetSnapshotRepository(added={})
    handler = AcquireMarketDataSnapshotHandler(
        dataset_snapshot_repository=snapshots,
        instrument_master_repository=_InMemoryInstrumentMasterRepository(added=[]),
        source=source,
        clock_now=_CLOCK.now(),
    )
    return handler, snapshots


def test_acquire_single_symbol_produces_raw_unadjusted_snapshot(tmp_path: Path) -> None:
    source = FakeMarketDataSource({"AAPL": _AAPL_CSV}, clock=_CLOCK)
    handler, snapshots = _handler(source)
    command = build_acquire_market_data_snapshot_command(
        dataset_id="DATASET-6900",
        dataset_version="1",
        symbols=("AAPL",),
        start_date=date(2024, 6, 1),
        end_date=date(2024, 6, 5),
        interval=BarInterval.ONE_DAY,
        instrument_master=build_trivial_instrument_master(("AAPL",)),
        artifact_path=str(tmp_path / "artifact.json"),
        license_note="test",
    )
    result = handler.handle(command)
    assert result.snapshot.price_semantics is PriceSemantics.RAW_UNADJUSTED
    assert result.snapshot.corporate_action_semantics is CorporateActionSemantics.NONE_DECLARED
    assert result.snapshot.instrument_count == 1
    assert result.snapshot.total_row_count == 2
    assert result.adapter_source_name == "FAKE_OFFLINE_FIXTURE"
    assert len(result.symbol_provenance) == 1
    assert result.symbol_provenance[0].symbol == "AAPL"
    assert snapshots.added[("DATASET-6900", "1")] == result.snapshot
    assert Path(result.artifact_path).exists()


def test_acquire_multiple_symbols_produces_one_multi_instrument_snapshot(tmp_path: Path) -> None:
    source = FakeMarketDataSource({"AAPL": _AAPL_CSV, "MSFT": _MSFT_CSV}, clock=_CLOCK)
    handler, _snapshots = _handler(source)
    command = build_acquire_market_data_snapshot_command(
        dataset_id="DATASET-6901",
        dataset_version="1",
        symbols=("AAPL", "MSFT"),
        start_date=date(2024, 6, 1),
        end_date=date(2024, 6, 5),
        interval=BarInterval.ONE_DAY,
        instrument_master=build_trivial_instrument_master(("AAPL", "MSFT")),
        artifact_path=str(tmp_path / "artifact.json"),
        license_note="test",
    )
    result = handler.handle(command)
    assert result.snapshot.instrument_count == 2
    assert result.snapshot.total_row_count == 4
    assert {p.symbol for p in result.symbol_provenance} == {"AAPL", "MSFT"}


def test_acquire_missing_symbol_fixture_raises(tmp_path: Path) -> None:
    source = FakeMarketDataSource({"AAPL": _AAPL_CSV}, clock=_CLOCK)
    handler, _snapshots = _handler(source)
    command = build_acquire_market_data_snapshot_command(
        dataset_id="DATASET-6902",
        dataset_version="1",
        symbols=("ZZZZ",),
        start_date=date(2024, 6, 1),
        end_date=date(2024, 6, 5),
        interval=BarInterval.ONE_DAY,
        instrument_master=build_trivial_instrument_master(("ZZZZ",)),
        artifact_path=str(tmp_path / "artifact.json"),
        license_note="test",
    )
    with pytest.raises(Exception, match="no fixture bars registered"):
        handler.handle(command)


def test_acquire_deterministic_replay_same_fixtures_produce_identical_snapshot_content(
    tmp_path: Path,
) -> None:
    source_a = FakeMarketDataSource({"AAPL": _AAPL_CSV}, clock=_CLOCK)
    handler_a, _ = _handler(source_a)
    result_a = handler_a.handle(
        build_acquire_market_data_snapshot_command(
            dataset_id="DATASET-6903",
            dataset_version="1",
            symbols=("AAPL",),
            start_date=date(2024, 6, 1),
            end_date=date(2024, 6, 5),
            interval=BarInterval.ONE_DAY,
            instrument_master=build_trivial_instrument_master(("AAPL",)),
            artifact_path=str(tmp_path / "a.json"),
            license_note="test",
        )
    )
    source_b = FakeMarketDataSource({"AAPL": _AAPL_CSV}, clock=_CLOCK)
    handler_b, _ = _handler(source_b)
    result_b = handler_b.handle(
        build_acquire_market_data_snapshot_command(
            dataset_id="DATASET-6903",
            dataset_version="1",
            symbols=("AAPL",),
            start_date=date(2024, 6, 1),
            end_date=date(2024, 6, 5),
            interval=BarInterval.ONE_DAY,
            instrument_master=build_trivial_instrument_master(("AAPL",)),
            artifact_path=str(tmp_path / "b.json"),
            license_note="test",
        )
    )
    # Same input bytes -> identical normalized content hash, independent
    # of the different dataset_id/artifact path used for each run.
    assert result_a.snapshot.normalized_sha256 == result_b.snapshot.normalized_sha256
    assert result_a.artifact_sha256 == result_b.artifact_sha256


def test_build_trivial_instrument_master_one_entry_per_symbol() -> None:
    master = build_trivial_instrument_master(("AAPL", "MSFT"))
    symbols = {str(entry.canonical_symbol) for entry in master.entries}
    assert symbols == {"AAPL", "MSFT"}
    ids = {str(entry.instrument_id) for entry in master.entries}
    assert ids == {"INSTR-AAPL-001", "INSTR-MSFT-001"}


def test_result_payload_serializes_to_json_offline(tmp_path: Path) -> None:
    """Direct, network-free coverage of
    `acquire_market_data_snapshot_result_payload` -- otherwise only ever
    exercised by the network+PostgreSQL-gated real CLI subprocess test,
    which is never required for canonical CI."""
    source = FakeMarketDataSource({"AAPL": _AAPL_CSV}, clock=_CLOCK)
    handler, _snapshots = _handler(source)
    result = handler.handle(
        build_acquire_market_data_snapshot_command(
            dataset_id="DATASET-6906",
            dataset_version="1",
            symbols=("AAPL",),
            start_date=date(2024, 6, 1),
            end_date=date(2024, 6, 5),
            interval=BarInterval.ONE_DAY,
            instrument_master=build_trivial_instrument_master(("AAPL",)),
            artifact_path=str(tmp_path / "artifact.json"),
            license_note="test",
        )
    )
    payload = acquire_market_data_snapshot_result_payload(result)
    # Must be genuinely JSON-serializable -- no Decimal/datetime/enum
    # objects leaking through unconverted.
    serialized = json.dumps(payload, sort_keys=True)
    round_tripped = json.loads(serialized)

    assert round_tripped["adapter_source_name"] == "FAKE_OFFLINE_FIXTURE"
    assert round_tripped["artifact_sha256"] == result.artifact_sha256
    assert round_tripped["snapshot"]["dataset_id"] == "DATASET-6906"
    assert round_tripped["snapshot"]["normalized_sha256"] == result.snapshot.normalized_sha256
    assert len(round_tripped["symbol_provenance"]) == 1
    assert round_tripped["symbol_provenance"][0]["symbol"] == "AAPL"
    assert round_tripped["symbol_provenance"][0]["fetched_at"] == _CLOCK.now().isoformat()
