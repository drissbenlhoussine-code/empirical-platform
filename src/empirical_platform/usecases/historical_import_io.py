"""Usecase-layer parsing and serialization helpers for MILESTONE-065."""

from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Protocol, cast

from empirical_platform.decision_candidate.corporate_actions import (
    CorporateActionManifest,
    CorporateActionType,
    SplitAction,
    SymbolChangeAction,
)
from empirical_platform.decision_candidate.historical_import import RawSourceFile
from empirical_platform.decision_candidate.instrument_master import InstrumentId
from empirical_platform.decision_candidate.market_data import Instrument
from empirical_platform.usecases.survivorship_study_io import (
    parse_instrument_master_file as parse_instrument_master_file,
)

__all__ = [
    "corporate_action_semantics_stress_payload",
    "dataset_snapshot_payload",
    "parse_corporate_action_manifest_file",
    "parse_instrument_master_file",
    "read_raw_source_files",
]


def parse_corporate_action_manifest_file(path: str) -> CorporateActionManifest:
    """Load the local corporate-action manifest fixture file. No tamper
    detection at this layer -- the manifest's own semantic hash is
    computed and compared explicitly by the caller (the import usecase),
    against a caller-declared expected hash, before any snapshot is
    derived from it."""
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    actions: list[SplitAction | SymbolChangeAction] = []
    for entry in raw["actions"]:
        action_type = CorporateActionType(entry["action_type"])
        instrument_id = InstrumentId(entry["instrument_id"])
        effective_timestamp = datetime.fromisoformat(entry["effective_timestamp"])
        if action_type is CorporateActionType.SYMBOL_CHANGE:
            actions.append(
                SymbolChangeAction(
                    instrument_id=instrument_id,
                    action_type=action_type,
                    effective_timestamp=effective_timestamp,
                    old_symbol=Instrument(entry["old_symbol"]),
                    new_symbol=Instrument(entry["new_symbol"]),
                    source_kind=entry["source_kind"],
                )
            )
        else:
            actions.append(
                SplitAction(
                    instrument_id=instrument_id,
                    action_type=action_type,
                    effective_timestamp=effective_timestamp,
                    ratio_new_shares=int(entry["ratio_new_shares"]),
                    ratio_old_shares=int(entry["ratio_old_shares"]),
                    source_kind=entry["source_kind"],
                )
            )
    return CorporateActionManifest(
        dataset_id=raw["dataset_id"], dataset_version=raw["dataset_version"], actions=tuple(actions)
    )


def read_raw_source_files(directory: str) -> tuple[RawSourceFile, ...]:
    """Read every `*.csv` file directly inside `directory` as one immutable
    local source file, keyed by its own filename stem (the current/final
    ticker symbol)."""
    source_dir = Path(directory)
    csv_paths = sorted(source_dir.glob("*.csv"))
    if not csv_paths:
        raise ValueError(f"no .csv source files found in {directory!r}")
    return tuple(
        RawSourceFile(
            file_name=csv_path.name,
            instrument_symbol=csv_path.stem,
            raw_bytes=csv_path.read_bytes(),
        )
        for csv_path in csv_paths
    )


class _ValueEnumView(Protocol):
    value: str


class _SourceFileEntryView(Protocol):
    file_name: str
    instrument_symbol: str
    sha256: str
    row_count: int


class DatasetSnapshotPayloadView(Protocol):
    dataset_id: object
    dataset_version: str
    source_kind: str
    source_name: str
    source_reference: str
    license_note: str
    snapshot_created_at: datetime
    interval: _ValueEnumView
    start_timestamp: datetime
    end_timestamp: datetime
    instrument_count: int
    total_row_count: int
    file_count: int
    source_file_manifest: tuple[_SourceFileEntryView, ...]
    bundle_sha256: str
    normalized_sha256: str
    price_semantics: _ValueEnumView
    corporate_action_semantics: _ValueEnumView
    corporate_action_manifest_hash: str | None
    dividend_handling: str


def dataset_snapshot_payload(snapshot: object) -> dict[str, object]:
    typed = cast(DatasetSnapshotPayloadView, snapshot)
    return {
        "dataset_id": str(typed.dataset_id),
        "dataset_version": typed.dataset_version,
        "source_kind": typed.source_kind,
        "source_name": typed.source_name,
        "source_reference": typed.source_reference,
        "license_note": typed.license_note,
        "snapshot_created_at": typed.snapshot_created_at.isoformat(),
        "interval": typed.interval.value,
        "start_timestamp": typed.start_timestamp.isoformat(),
        "end_timestamp": typed.end_timestamp.isoformat(),
        "instrument_count": typed.instrument_count,
        "total_row_count": typed.total_row_count,
        "file_count": typed.file_count,
        "source_file_manifest": [
            {
                "file_name": entry.file_name,
                "instrument_symbol": entry.instrument_symbol,
                "sha256": entry.sha256,
                "row_count": entry.row_count,
            }
            for entry in typed.source_file_manifest
        ],
        "bundle_sha256": typed.bundle_sha256,
        "normalized_sha256": typed.normalized_sha256,
        "price_semantics": typed.price_semantics.value,
        "corporate_action_semantics": typed.corporate_action_semantics.value,
        "corporate_action_manifest_hash": typed.corporate_action_manifest_hash,
        "dividend_handling": typed.dividend_handling,
    }


class StressPayloadView(Protocol):
    identity: object
    dataset_id: object
    correct_dataset_version: str
    correct_run_id: object
    naive_dataset_version: str
    naive_run_id: object
    comparison: _ValueEnumView
    correct_executed_trade_count: int
    naive_executed_trade_count: int
    correct_net_pnl_total: Decimal
    naive_net_pnl_total: Decimal
    correct_total_r_total: Decimal
    naive_total_r_total: Decimal


def corporate_action_semantics_stress_payload(result: object) -> dict[str, object]:
    typed = cast(StressPayloadView, result)
    identity = typed.identity
    return {
        "governance_id": str(identity.governance_id),  # type: ignore[attr-defined]
        "runtime_id": str(identity.runtime_id),  # type: ignore[attr-defined]
        "dataset_id": str(typed.dataset_id),
        "correct_dataset_version": typed.correct_dataset_version,
        "correct_run_id": str(typed.correct_run_id),
        "naive_dataset_version": typed.naive_dataset_version,
        "naive_run_id": str(typed.naive_run_id),
        "comparison": typed.comparison.value,
        "correct_executed_trade_count": typed.correct_executed_trade_count,
        "naive_executed_trade_count": typed.naive_executed_trade_count,
        "correct_net_pnl_total": str(typed.correct_net_pnl_total),
        "naive_net_pnl_total": str(typed.naive_net_pnl_total),
        "correct_total_r_total": str(typed.correct_total_r_total),
        "naive_total_r_total": str(typed.naive_total_r_total),
    }
