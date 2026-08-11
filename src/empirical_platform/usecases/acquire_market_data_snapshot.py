"""Acquire real historical market-data bars end-to-end and import them
through the unmodified, frozen M065 dataset-snapshot pipeline.

MILESTONE-069.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from empirical_platform.decision_candidate.dataset_snapshot import DatasetSnapshotAuthority
from empirical_platform.decision_candidate.dataset_snapshot_repository import (
    DatasetSnapshotRepository,
)
from empirical_platform.decision_candidate.historical_import import (
    RawSourceFile,
    import_raw_historical_dataset_snapshot,
    write_dataset_artifact,
)
from empirical_platform.decision_candidate.instrument_master import (
    InstrumentId,
    InstrumentMaster,
    InstrumentMasterEntry,
    InstrumentMasterRepository,
    InstrumentType,
)
from empirical_platform.decision_candidate.market_data import BarInterval, Instrument
from empirical_platform.decision_candidate.market_data_acquisition import (
    MarketDataFetchRequest,
    MarketDataSource,
    YahooFinanceChartMarketDataSource,
    translate_fetch_result_to_pipeline_csv,
)
from empirical_platform.identifiers.types import DatasetId

# Explicit re-exports: `entrypoints` cannot import `decision_candidate`
# directly (architecture rule) -- the idiom established since M054.
__all__ = [
    "AcquireMarketDataSnapshotCommand",
    "AcquireMarketDataSnapshotHandler",
    "AcquireMarketDataSnapshotResult",
    "AcquisitionSymbolProvenance",
    "BarInterval",
    "DatasetSnapshotAuthority",
    "InstrumentMaster",
    "YahooFinanceChartMarketDataSource",
    "build_acquire_market_data_snapshot_command",
    "build_trivial_instrument_master",
]


@dataclass(frozen=True, slots=True)
class AcquisitionSymbolProvenance:
    """One immutable, per-symbol audit record of exactly what was fetched
    and from where -- never persisted separately (the frozen M065
    `SourceFileManifestEntry.sha256` already carries the same integrity
    guarantee over the translated bytes actually parsed), but always
    returned so a caller can independently verify the request that
    produced this dataset."""

    symbol: str
    source_reference: str
    fetched_at: datetime
    raw_bytes_sha256: str

    def __post_init__(self) -> None:
        if not self.symbol.strip():
            raise ValueError("symbol must be non-empty")
        if not self.source_reference.strip():
            raise ValueError("source_reference must be non-empty")
        if self.fetched_at.tzinfo is None:
            raise ValueError("fetched_at must be timezone-aware")
        if len(self.raw_bytes_sha256) != 64:
            raise ValueError("raw_bytes_sha256 must be a full SHA-256 hex digest")


@dataclass(frozen=True, slots=True)
class AcquireMarketDataSnapshotCommand:
    """Request to fetch one or more instruments' own real historical bars
    over an explicit date range via one named adapter, and import the
    result into one `RAW_UNADJUSTED` `DatasetSnapshotAuthority`."""

    dataset_id: DatasetId
    dataset_version: str
    symbols: tuple[str, ...]
    start_date: date
    end_date: date
    interval: BarInterval
    instrument_master: InstrumentMaster
    artifact_path: str
    license_note: str


@dataclass(frozen=True, slots=True)
class AcquireMarketDataSnapshotResult:
    """The immutable result of one acquisition: the persisted snapshot,
    the on-disk M061-compatible artifact, and the per-symbol fetch
    provenance."""

    snapshot: DatasetSnapshotAuthority
    artifact_path: str
    artifact_sha256: str
    adapter_source_name: str
    symbol_provenance: tuple[AcquisitionSymbolProvenance, ...]


class AcquireMarketDataSnapshotHandler:
    """Fetch real bars via one injected `MarketDataSource` adapter and
    persist through the unmodified M065
    `DatasetSnapshotRepository`/M064 `InstrumentMasterRepository` --
    never a second persistence path, never a parallel import engine."""

    __slots__ = ("_dataset_snapshots", "_instrument_masters", "_source", "_clock_now")

    def __init__(
        self,
        *,
        dataset_snapshot_repository: DatasetSnapshotRepository,
        instrument_master_repository: InstrumentMasterRepository,
        source: MarketDataSource,
        clock_now: datetime,
    ) -> None:
        self._dataset_snapshots = dataset_snapshot_repository
        self._instrument_masters = instrument_master_repository
        self._source = source
        self._clock_now = clock_now

    def handle(self, command: AcquireMarketDataSnapshotCommand) -> AcquireMarketDataSnapshotResult:
        raw_source_files: list[RawSourceFile] = []
        provenance: list[AcquisitionSymbolProvenance] = []
        for symbol in command.symbols:
            request = MarketDataFetchRequest(
                symbol=symbol,
                start_date=command.start_date,
                end_date=command.end_date,
                interval=command.interval,
            )
            result = self._source.fetch(request)
            pipeline_csv = translate_fetch_result_to_pipeline_csv(result)
            raw_source_files.append(
                RawSourceFile(
                    file_name=f"{symbol}.{self._source.source_name}.csv",
                    instrument_symbol=symbol,
                    raw_bytes=pipeline_csv,
                )
            )
            provenance.append(
                AcquisitionSymbolProvenance(
                    symbol=symbol,
                    source_reference=result.source_reference,
                    fetched_at=result.fetched_at,
                    raw_bytes_sha256=_sha256_hex(pipeline_csv),
                )
            )

        snapshot, series = import_raw_historical_dataset_snapshot(
            dataset_id=command.dataset_id,
            dataset_version=command.dataset_version,
            source_kind="MARKET_DATA_ACQUISITION",
            source_name=self._source.source_name,
            source_reference=", ".join(p.source_reference for p in provenance),
            license_note=command.license_note,
            snapshot_created_at=self._clock_now,
            interval=command.interval,
            raw_source_files=tuple(raw_source_files),
            instrument_master=command.instrument_master,
        )
        self._instrument_masters.add_all(command.instrument_master)
        self._dataset_snapshots.add(snapshot)
        artifact_sha256 = write_dataset_artifact(
            Path(command.artifact_path),
            dataset_id=snapshot.dataset_id,
            dataset_version=snapshot.dataset_version,
            source_kind=snapshot.source_kind,
            series=series,
        )

        return AcquireMarketDataSnapshotResult(
            snapshot=snapshot,
            artifact_path=command.artifact_path,
            artifact_sha256=artifact_sha256,
            adapter_source_name=self._source.source_name,
            symbol_provenance=tuple(provenance),
        )


def _sha256_hex(raw_bytes: bytes) -> str:
    return hashlib.sha256(raw_bytes).hexdigest()


def build_acquire_market_data_snapshot_command(
    *,
    dataset_id: str,
    dataset_version: str,
    symbols: tuple[str, ...],
    start_date: date,
    end_date: date,
    interval: BarInterval,
    instrument_master: InstrumentMaster,
    artifact_path: str,
    license_note: str,
) -> AcquireMarketDataSnapshotCommand:
    """Build one real M069 command from plain application-layer inputs."""
    return AcquireMarketDataSnapshotCommand(
        dataset_id=DatasetId(dataset_id),
        dataset_version=dataset_version,
        symbols=symbols,
        start_date=start_date,
        end_date=end_date,
        interval=interval,
        instrument_master=instrument_master,
        artifact_path=artifact_path,
        license_note=license_note,
    )


def build_trivial_instrument_master(symbols: tuple[str, ...]) -> InstrumentMaster:
    """Build one minimal `InstrumentMaster` with exactly one `EQUITY`
    entry per requested symbol, `InstrumentId` derived deterministically
    from the symbol (`INSTR-{SYMBOL}-001`). Richer venue/instrument-type
    classification is M064's own job -- out of scope for a real-data
    acquisition command whose only job is to fetch bars."""
    return InstrumentMaster(
        entries=tuple(
            InstrumentMasterEntry(
                instrument_id=InstrumentId(f"INSTR-{symbol}-001"),
                canonical_symbol=Instrument(symbol),
                instrument_type=InstrumentType.EQUITY,
            )
            for symbol in symbols
        )
    )
