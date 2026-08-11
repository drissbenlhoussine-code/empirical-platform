"""Usecase-layer JSON serialization helpers for MILESTONE-069."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol, cast

from empirical_platform.usecases.historical_import_io import dataset_snapshot_payload

__all__ = ["acquire_market_data_snapshot_result_payload"]


class _SymbolProvenanceView(Protocol):
    symbol: str
    source_reference: str
    fetched_at: datetime
    raw_bytes_sha256: str


class AcquireMarketDataSnapshotResultPayloadView(Protocol):
    snapshot: object
    artifact_path: str
    artifact_sha256: str
    adapter_source_name: str
    symbol_provenance: tuple[_SymbolProvenanceView, ...]


def _provenance_payload(provenance: _SymbolProvenanceView) -> dict[str, object]:
    return {
        "symbol": provenance.symbol,
        "source_reference": provenance.source_reference,
        "fetched_at": provenance.fetched_at.isoformat(),
        "raw_bytes_sha256": provenance.raw_bytes_sha256,
    }


def acquire_market_data_snapshot_result_payload(result: object) -> dict[str, object]:
    typed = cast(AcquireMarketDataSnapshotResultPayloadView, result)
    return {
        "snapshot": dataset_snapshot_payload(typed.snapshot),
        "artifact_path": typed.artifact_path,
        "artifact_sha256": typed.artifact_sha256,
        "adapter_source_name": typed.adapter_source_name,
        "symbol_provenance": [_provenance_payload(p) for p in typed.symbol_provenance],
    }
