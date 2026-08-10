"""Deterministic local historical-data import pipeline.

MILESTONE-065. Parses immutable local CSV source files (one file per
instrument, keyed by its current/final ticker symbol) into the frozen M061
`HistoricalInstrumentSeries`/`HistoricalDataset` types, validates them
using the *existing* frozen `Bar`/`HistoricalInstrumentSeries`/
`HistoricalDataset` invariants (no new OHLC/chronology/duplicate-bar
validation is reinvented here), optionally applies declared split
adjustments from a `CorporateActionManifest`, and produces one immutable
`DatasetSnapshotAuthority` plus a byte-identical M061-compatible dataset
JSON artifact -- so the exact same bytes that were hashed as
`normalized_sha256` are the exact bytes handed to the unmodified, frozen
M061 `run-historical-backtest` CLI.

No network fetch. No hidden vendor call. The only input is caller-supplied
local bytes.
"""

from __future__ import annotations

import csv
import io
import json
from dataclasses import dataclass
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from pathlib import Path

from empirical_platform.decision_candidate.corporate_actions import (
    CorporateActionManifest,
    corporate_action_manifest_hash,
    split_adjustment_factor_at,
    volume_adjustment_factor_at,
)
from empirical_platform.decision_candidate.dataset_snapshot import (
    DIVIDEND_TOTAL_RETURN_HANDLING_NOT_EXERCISED,
    CorporateActionSemantics,
    DatasetSnapshotAuthority,
    PriceSemantics,
    SourceFileManifestEntry,
)
from empirical_platform.decision_candidate.historical_backtest import (
    HistoricalDataset,
    HistoricalDatasetAuthority,
    HistoricalInstrumentSeries,
    dataset_sha256,
)
from empirical_platform.decision_candidate.instrument_master import InstrumentMaster
from empirical_platform.decision_candidate.market_data import Bar, BarInterval, Instrument
from empirical_platform.identifiers.types import DatasetId

_PRICE_QUANTUM = Decimal("0.0001")
_REQUIRED_CSV_COLUMNS = {"timestamp", "open", "high", "low", "close", "volume"}


@dataclass(frozen=True, slots=True)
class RawSourceFile:
    """One immutable local source file, not yet parsed."""

    file_name: str
    instrument_symbol: str
    raw_bytes: bytes

    def __post_init__(self) -> None:
        if not self.file_name.strip():
            raise ValueError("file_name must be non-empty")
        if not self.instrument_symbol.strip():
            raise ValueError("instrument_symbol must be non-empty")
        if not self.raw_bytes:
            raise ValueError(f"source file {self.file_name!r} is empty")


def parse_source_csv(
    raw_bytes: bytes, *, instrument: Instrument, interval: BarInterval
) -> tuple[Bar, ...]:
    """Parse one CSV source file's raw bytes into a tuple of `Bar`s, in
    file order (never re-sorted -- an out-of-order or duplicate-timestamp
    file is rejected downstream by the frozen
    `HistoricalInstrumentSeries.__post_init__` check, not silently
    corrected here)."""
    try:
        text = raw_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(f"source file for {instrument} is not valid UTF-8 text") from exc
    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None or not _REQUIRED_CSV_COLUMNS.issubset(set(reader.fieldnames)):
        raise ValueError(
            f"source CSV for {instrument} must declare columns {sorted(_REQUIRED_CSV_COLUMNS)}"
        )
    bars: list[Bar] = []
    for row_index, row in enumerate(reader):
        raw_timestamp = row.get("timestamp") or ""
        try:
            timestamp = datetime.fromisoformat(raw_timestamp)
        except ValueError as exc:
            raise ValueError(
                f"invalid timestamp for {instrument} row {row_index}: {raw_timestamp!r}"
            ) from exc
        if timestamp.tzinfo is None:
            raise ValueError(f"timestamp must be timezone-aware for {instrument} row {row_index}")
        try:
            bar = Bar(
                instrument=instrument,
                interval=interval,
                timestamp=timestamp,
                open=Decimal(row["open"]),
                high=Decimal(row["high"]),
                low=Decimal(row["low"]),
                close=Decimal(row["close"]),
                volume=int(row["volume"]),
            )
        except (InvalidOperation, ValueError, TypeError) as exc:
            raise ValueError(f"invalid OHLCV row for {instrument} row {row_index}: {exc}") from exc
        bars.append(bar)
    if not bars:
        raise ValueError(f"source CSV for {instrument} contains zero data rows")
    return tuple(bars)


def _series_payload(series: HistoricalInstrumentSeries) -> dict[str, object]:
    return {
        "instrument": str(series.instrument),
        "bars": [
            {
                "instrument": str(bar.instrument),
                "interval": bar.interval.value,
                "timestamp": bar.timestamp.isoformat(),
                "open": str(bar.open),
                "high": str(bar.high),
                "low": str(bar.low),
                "close": str(bar.close),
                "volume": bar.volume,
            }
            for bar in series.bars
        ],
    }


def _canonical_artifact_bytes(
    *,
    dataset_id: DatasetId,
    dataset_version: str,
    source_kind: str,
    series: tuple[HistoricalInstrumentSeries, ...],
) -> tuple[bytes, str]:
    """The exact, deterministic byte serialization used both to compute
    `normalized_sha256` and to write the on-disk M061-compatible artifact
    -- guaranteeing the two are always identical, by construction."""
    payload = {
        "dataset_id": str(dataset_id),
        "dataset_version": dataset_version,
        "source_kind": source_kind,
        "instruments": [_series_payload(one_series) for one_series in series],
    }
    raw_bytes = json.dumps(payload, sort_keys=True).encode("utf-8")
    return raw_bytes, dataset_sha256(raw_bytes)


def write_dataset_artifact(
    path: Path,
    *,
    dataset_id: DatasetId,
    dataset_version: str,
    source_kind: str,
    series: tuple[HistoricalInstrumentSeries, ...],
) -> str:
    """Write the M061-compatible dataset JSON artifact to `path` and
    return its own SHA-256 -- always exactly equal to the corresponding
    `DatasetSnapshotAuthority.normalized_sha256`."""
    raw_bytes, sha256 = _canonical_artifact_bytes(
        dataset_id=dataset_id,
        dataset_version=dataset_version,
        source_kind=source_kind,
        series=series,
    )
    path.write_bytes(raw_bytes)
    return sha256


def dataset_snapshot_to_historical_dataset(
    snapshot: DatasetSnapshotAuthority, series: tuple[HistoricalInstrumentSeries, ...]
) -> HistoricalDataset:
    """Wrap a snapshot's own materialized series in the frozen M061
    `HistoricalDataset` type, reusing its own `__post_init__` invariants
    (canonical shared timestamp grid, no duplicate instruments) verbatim."""
    authority = HistoricalDatasetAuthority(
        dataset_id=snapshot.dataset_id,
        dataset_version=snapshot.dataset_version,
        source_kind=snapshot.source_kind,
        interval=snapshot.interval,
        start_timestamp=snapshot.start_timestamp,
        end_timestamp=snapshot.end_timestamp,
        total_bars=snapshot.total_row_count,
        instrument_count=snapshot.instrument_count,
        sha256=snapshot.normalized_sha256,
    )
    return HistoricalDataset(authority=authority, series=series)


def import_raw_historical_dataset_snapshot(
    *,
    dataset_id: DatasetId,
    dataset_version: str,
    source_kind: str,
    source_name: str,
    source_reference: str,
    license_note: str,
    snapshot_created_at: datetime,
    interval: BarInterval,
    raw_source_files: tuple[RawSourceFile, ...],
    instrument_master: InstrumentMaster,
) -> tuple[DatasetSnapshotAuthority, tuple[HistoricalInstrumentSeries, ...]]:
    """Validate and import a set of immutable local CSV source files into
    one immutable `RAW_UNADJUSTED` `DatasetSnapshotAuthority`. Every
    result is deterministic and independent of `raw_source_files`' own
    input order."""
    if not raw_source_files:
        raise ValueError("at least one source file is required")
    file_names = [source_file.file_name for source_file in raw_source_files]
    if len(set(file_names)) != len(file_names):
        raise ValueError("duplicate file_name in raw_source_files")

    symbol_to_instrument_id = {
        entry.canonical_symbol: entry.instrument_id for entry in instrument_master.entries
    }

    manifest_entries: list[SourceFileManifestEntry] = []
    series_list: list[HistoricalInstrumentSeries] = []
    seen_instrument_ids = set()
    for source_file in sorted(raw_source_files, key=lambda entry: entry.file_name):
        instrument = Instrument(source_file.instrument_symbol)
        instrument_id = symbol_to_instrument_id.get(instrument)
        if instrument_id is None:
            raise ValueError(
                f"source file {source_file.file_name!r} references unknown instrument: {instrument}"
            )
        if instrument_id in seen_instrument_ids:
            raise ValueError(f"duplicate source file for instrument {instrument_id}")
        seen_instrument_ids.add(instrument_id)

        bars = parse_source_csv(source_file.raw_bytes, instrument=instrument, interval=interval)
        series_list.append(HistoricalInstrumentSeries(instrument=instrument, bars=bars))
        manifest_entries.append(
            SourceFileManifestEntry(
                file_name=source_file.file_name,
                instrument_symbol=source_file.instrument_symbol,
                sha256=dataset_sha256(source_file.raw_bytes),
                row_count=len(bars),
            )
        )

    ordered_manifest = tuple(sorted(manifest_entries, key=lambda entry: entry.file_name))
    ordered_series = tuple(sorted(series_list, key=lambda one_series: str(one_series.instrument)))

    bundle_bytes = b"|".join(entry.sha256.encode("utf-8") for entry in ordered_manifest)
    bundle_sha256 = dataset_sha256(bundle_bytes)

    _artifact_bytes, normalized_sha256 = _canonical_artifact_bytes(
        dataset_id=dataset_id,
        dataset_version=dataset_version,
        source_kind=source_kind,
        series=ordered_series,
    )
    total_bars = sum(len(one_series.bars) for one_series in ordered_series)

    # Reuse the frozen M061 HistoricalDataset invariant check verbatim
    # (canonical shared timestamp grid across every instrument, no
    # duplicate instruments) rather than reimplementing it.
    HistoricalDataset(
        authority=HistoricalDatasetAuthority(
            dataset_id=dataset_id,
            dataset_version=dataset_version,
            source_kind=source_kind,
            interval=interval,
            start_timestamp=ordered_series[0].bars[0].timestamp,
            end_timestamp=ordered_series[0].bars[-1].timestamp,
            total_bars=total_bars,
            instrument_count=len(ordered_series),
            sha256=normalized_sha256,
        ),
        series=ordered_series,
    )

    snapshot = DatasetSnapshotAuthority(
        dataset_id=dataset_id,
        dataset_version=dataset_version,
        source_kind=source_kind,
        source_name=source_name,
        source_reference=source_reference,
        license_note=license_note,
        snapshot_created_at=snapshot_created_at,
        interval=interval,
        start_timestamp=ordered_series[0].bars[0].timestamp,
        end_timestamp=ordered_series[0].bars[-1].timestamp,
        instrument_count=len(ordered_series),
        total_row_count=total_bars,
        file_count=len(ordered_manifest),
        source_file_manifest=ordered_manifest,
        bundle_sha256=bundle_sha256,
        normalized_sha256=normalized_sha256,
        price_semantics=PriceSemantics.RAW_UNADJUSTED,
        corporate_action_semantics=CorporateActionSemantics.NONE_DECLARED,
        corporate_action_manifest_hash=None,
        dividend_handling=DIVIDEND_TOTAL_RETURN_HANDLING_NOT_EXERCISED,
    )
    return snapshot, ordered_series


def derive_split_adjusted_snapshot(
    raw_snapshot: DatasetSnapshotAuthority,
    raw_series: tuple[HistoricalInstrumentSeries, ...],
    *,
    dataset_version: str,
    snapshot_created_at: datetime,
    corporate_action_manifest: CorporateActionManifest,
    instrument_master: InstrumentMaster,
) -> tuple[DatasetSnapshotAuthority, tuple[HistoricalInstrumentSeries, ...]]:
    """Derive one immutable `SPLIT_ADJUSTED` snapshot from an already
    -imported `RAW_UNADJUSTED` one, applying `split_adjustment_factor_at`/
    `volume_adjustment_factor_at` to every bar. The raw source files (and
    their own `bundle_sha256`) are unchanged -- only the interpretation
    (and therefore `normalized_sha256`) differs."""
    symbol_to_instrument_id = {
        entry.canonical_symbol: entry.instrument_id for entry in instrument_master.entries
    }
    raw_instrument_ids = {
        symbol_to_instrument_id[one_series.instrument]
        for one_series in raw_series
        if one_series.instrument in symbol_to_instrument_id
    }
    for action in corporate_action_manifest.actions:
        if action.instrument_id not in raw_instrument_ids:
            raise ValueError(
                f"corporate action for {action.instrument_id} does not correspond to any "
                "instrument present in this dataset's own raw import -- a corporate action "
                "outside instrument history is not permitted"
            )

    adjusted_series: list[HistoricalInstrumentSeries] = []
    for one_series in raw_series:
        instrument_id = symbol_to_instrument_id.get(one_series.instrument)
        if instrument_id is None:
            raise ValueError(f"unknown instrument in raw series: {one_series.instrument}")
        adjusted_bars = []
        for bar in one_series.bars:
            price_factor = split_adjustment_factor_at(
                corporate_action_manifest, instrument_id, bar.timestamp
            )
            if price_factor == 1:
                adjusted_bars.append(bar)
                continue
            volume_factor = volume_adjustment_factor_at(
                corporate_action_manifest, instrument_id, bar.timestamp
            )
            adjusted_bars.append(
                Bar(
                    instrument=bar.instrument,
                    interval=bar.interval,
                    timestamp=bar.timestamp,
                    open=(bar.open * price_factor).quantize(_PRICE_QUANTUM),
                    high=(bar.high * price_factor).quantize(_PRICE_QUANTUM),
                    low=(bar.low * price_factor).quantize(_PRICE_QUANTUM),
                    close=(bar.close * price_factor).quantize(_PRICE_QUANTUM),
                    volume=int(
                        (Decimal(bar.volume) * volume_factor).to_integral_value(
                            rounding=ROUND_HALF_UP
                        )
                    ),
                )
            )
        adjusted_series.append(
            HistoricalInstrumentSeries(instrument=one_series.instrument, bars=tuple(adjusted_bars))
        )
    ordered_adjusted_series = tuple(
        sorted(adjusted_series, key=lambda one_series: str(one_series.instrument))
    )

    action_hash = corporate_action_manifest_hash(corporate_action_manifest)
    _artifact_bytes, normalized_sha256 = _canonical_artifact_bytes(
        dataset_id=raw_snapshot.dataset_id,
        dataset_version=dataset_version,
        source_kind=raw_snapshot.source_kind,
        series=ordered_adjusted_series,
    )
    total_bars = sum(len(one_series.bars) for one_series in ordered_adjusted_series)

    HistoricalDataset(
        authority=HistoricalDatasetAuthority(
            dataset_id=raw_snapshot.dataset_id,
            dataset_version=dataset_version,
            source_kind=raw_snapshot.source_kind,
            interval=raw_snapshot.interval,
            start_timestamp=ordered_adjusted_series[0].bars[0].timestamp,
            end_timestamp=ordered_adjusted_series[0].bars[-1].timestamp,
            total_bars=total_bars,
            instrument_count=len(ordered_adjusted_series),
            sha256=normalized_sha256,
        ),
        series=ordered_adjusted_series,
    )

    snapshot = DatasetSnapshotAuthority(
        dataset_id=raw_snapshot.dataset_id,
        dataset_version=dataset_version,
        source_kind=raw_snapshot.source_kind,
        source_name=raw_snapshot.source_name,
        source_reference=raw_snapshot.source_reference,
        license_note=raw_snapshot.license_note,
        snapshot_created_at=snapshot_created_at,
        interval=raw_snapshot.interval,
        start_timestamp=ordered_adjusted_series[0].bars[0].timestamp,
        end_timestamp=ordered_adjusted_series[0].bars[-1].timestamp,
        instrument_count=raw_snapshot.instrument_count,
        total_row_count=total_bars,
        file_count=raw_snapshot.file_count,
        source_file_manifest=raw_snapshot.source_file_manifest,
        bundle_sha256=raw_snapshot.bundle_sha256,
        normalized_sha256=normalized_sha256,
        price_semantics=PriceSemantics.SPLIT_ADJUSTED,
        corporate_action_semantics=CorporateActionSemantics.SPLIT_AND_SYMBOL_CHANGE_AWARE,
        corporate_action_manifest_hash=action_hash,
        dividend_handling=DIVIDEND_TOTAL_RETURN_HANDLING_NOT_EXERCISED,
    )
    return snapshot, ordered_adjusted_series
