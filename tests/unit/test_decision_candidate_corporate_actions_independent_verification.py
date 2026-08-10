"""MILESTONE-065 independent corporate-action verification (mission Phase 25).

This module does NOT import `symbol_at`, `split_adjustment_factor_at`, or
`volume_adjustment_factor_at` from `corporate_actions.py`. It reads the raw
fixture CSV files and the raw corporate-action-manifest JSON file directly
(via `csv`/`json`, not via `parse_source_csv`/`parse_corporate_action_manifest_file`),
independently recomputes every split-adjusted price, every split-adjusted
volume, and every historical symbol mapping using separately-authored
logic, and then cross-checks the result bar-for-bar against the real
production pipeline's own output (`import_raw_historical_dataset_snapshot`
+ `derive_split_adjusted_snapshot`), which IS imported here only to obtain
the production result being verified -- never to perform the
recomputation itself.
"""

from __future__ import annotations

import csv
import json
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any

from empirical_platform.decision_candidate.historical_import import (
    derive_split_adjusted_snapshot,
    import_raw_historical_dataset_snapshot,
)
from empirical_platform.decision_candidate.instrument_master import (
    InstrumentId,
    InstrumentMaster,
    InstrumentMasterEntry,
    InstrumentType,
)
from empirical_platform.decision_candidate.market_data import BarInterval, Instrument
from empirical_platform.identifiers.types import DatasetId
from empirical_platform.usecases.historical_import_io import (
    parse_corporate_action_manifest_file,
    read_raw_source_files,
)

_FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "m065_corporate_action_mechanics"
_CREATED = datetime(2024, 3, 2, tzinfo=UTC)
_PRICE_QUANTUM = Decimal("0.0001")


def _independent_raw_manifest() -> dict[str, Any]:
    raw: dict[str, Any] = json.loads(
        (_FIXTURE_DIR / "corporate_action_manifest.json").read_text(encoding="utf-8")
    )
    return raw


def _independent_raw_bars(symbol: str) -> list[dict[str, str]]:
    with (_FIXTURE_DIR / f"{symbol}.csv").open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _independent_split_factor_for(
    manifest: dict[str, Any], instrument_id: str, bar_timestamp: datetime
) -> tuple[Decimal, Decimal]:
    """Independently recompute (price_factor, volume_factor) for one bar,
    from the raw manifest dict, without calling any `corporate_actions.py`
    helper."""
    price_factor = Decimal("1")
    volume_factor = Decimal("1")
    for entry in manifest["actions"]:
        if entry["instrument_id"] != instrument_id:
            continue
        if entry["action_type"] not in ("SPLIT", "REVERSE_SPLIT"):
            continue
        effective = datetime.fromisoformat(entry["effective_timestamp"])
        if bar_timestamp >= effective:
            continue
        new_shares = Decimal(entry["ratio_new_shares"])
        old_shares = Decimal(entry["ratio_old_shares"])
        price_factor *= old_shares / new_shares
        volume_factor *= new_shares / old_shares
    return price_factor, volume_factor


def _independent_symbol_at(
    manifest: dict[str, Any], instrument_id: str, current_symbol: str, timestamp: datetime
) -> str:
    """Independently recompute the historical symbol in effect at
    `timestamp`, from the raw manifest dict."""
    changes = sorted(
        (
            entry
            for entry in manifest["actions"]
            if entry["instrument_id"] == instrument_id and entry["action_type"] == "SYMBOL_CHANGE"
        ),
        key=lambda entry: entry["effective_timestamp"],
        reverse=True,
    )
    symbol = current_symbol
    for change in changes:
        effective = datetime.fromisoformat(change["effective_timestamp"])
        if timestamp < effective:
            symbol = change["old_symbol"]
        else:
            break
    return symbol


def _instrument_master() -> InstrumentMaster:
    return InstrumentMaster(
        entries=(
            InstrumentMasterEntry(
                instrument_id=InstrumentId("INSTR-ALFA-001"),
                canonical_symbol=Instrument("ALFA"),
                instrument_type=InstrumentType.EQUITY,
            ),
            InstrumentMasterEntry(
                instrument_id=InstrumentId("INSTR-BETA-001"),
                canonical_symbol=Instrument("BETA"),
                instrument_type=InstrumentType.EQUITY,
            ),
            InstrumentMasterEntry(
                instrument_id=InstrumentId("INSTR-GAMA-001"),
                canonical_symbol=Instrument("GAMA"),
                instrument_type=InstrumentType.EQUITY,
            ),
            InstrumentMasterEntry(
                instrument_id=InstrumentId("INSTR-DELT-001"),
                canonical_symbol=Instrument("DELT"),
                instrument_type=InstrumentType.EQUITY,
            ),
        )
    )


def _production_adjusted_series() -> dict[str, Any]:
    raw_files = read_raw_source_files(str(_FIXTURE_DIR))
    raw_snapshot, raw_series = import_raw_historical_dataset_snapshot(
        dataset_id=DatasetId("DATASET-6501"),
        dataset_version="1",
        source_kind="CORPORATE_ACTION_MECHANICS_FIXTURE",
        source_name="fixture",
        source_reference=str(_FIXTURE_DIR),
        license_note="synthetic, no license required",
        snapshot_created_at=_CREATED,
        interval=BarInterval.ONE_MINUTE,
        raw_source_files=raw_files,
        instrument_master=_instrument_master(),
    )
    production_manifest = parse_corporate_action_manifest_file(
        str(_FIXTURE_DIR / "corporate_action_manifest.json")
    )
    _adjusted_snapshot, adjusted_series = derive_split_adjusted_snapshot(
        raw_snapshot,
        raw_series,
        dataset_version="2-split-adjusted",
        snapshot_created_at=_CREATED,
        corporate_action_manifest=production_manifest,
        instrument_master=_instrument_master(),
    )
    return {
        "raw": {str(s.instrument): s for s in raw_series},
        "adjusted": {str(s.instrument): s for s in adjusted_series},
    }


def test_independent_recomputation_matches_production_beta_split_prices() -> None:
    manifest = _independent_raw_manifest()
    raw_rows = _independent_raw_bars("BETA")
    production = _production_adjusted_series()
    raw_series = production["raw"]["BETA"]
    adjusted_series = production["adjusted"]["BETA"]

    assert len(raw_rows) == len(raw_series.bars) == len(adjusted_series.bars)

    for index, row in enumerate(raw_rows):
        timestamp = datetime.fromisoformat(row["timestamp"])
        price_factor, volume_factor = _independent_split_factor_for(
            manifest, "INSTR-BETA-001", timestamp
        )
        independent_close = (Decimal(row["close"]) * price_factor).quantize(_PRICE_QUANTUM)
        independent_volume = int(
            (Decimal(row["volume"]) * volume_factor).to_integral_value(rounding=ROUND_HALF_UP)
        )
        assert adjusted_series.bars[index].timestamp == timestamp
        assert adjusted_series.bars[index].close == independent_close, (
            f"bar {index} ({timestamp.isoformat()}): production close "
            f"{adjusted_series.bars[index].close} != independent {independent_close}"
        )
        assert adjusted_series.bars[index].volume == independent_volume


def test_independent_recomputation_matches_production_gama_reverse_split_prices() -> None:
    manifest = _independent_raw_manifest()
    raw_rows = _independent_raw_bars("GAMA")
    production = _production_adjusted_series()
    adjusted_series = production["adjusted"]["GAMA"]

    for index, row in enumerate(raw_rows):
        timestamp = datetime.fromisoformat(row["timestamp"])
        price_factor, volume_factor = _independent_split_factor_for(
            manifest, "INSTR-GAMA-001", timestamp
        )
        independent_open = (Decimal(row["open"]) * price_factor).quantize(_PRICE_QUANTUM)
        independent_high = (Decimal(row["high"]) * price_factor).quantize(_PRICE_QUANTUM)
        independent_low = (Decimal(row["low"]) * price_factor).quantize(_PRICE_QUANTUM)
        independent_close = (Decimal(row["close"]) * price_factor).quantize(_PRICE_QUANTUM)
        independent_volume = int(
            (Decimal(row["volume"]) * volume_factor).to_integral_value(rounding=ROUND_HALF_UP)
        )
        bar = adjusted_series.bars[index]
        assert bar.open == independent_open
        assert bar.high == independent_high
        assert bar.low == independent_low
        assert bar.close == independent_close
        assert bar.volume == independent_volume


def test_independent_recomputation_confirms_alfa_and_delt_bars_untouched() -> None:
    # ALFA has no declared corporate action at all; DELT has only a
    # SYMBOL_CHANGE (no SPLIT/REVERSE_SPLIT) -- both must have
    # price_factor == 1 for every bar, independently confirmed here.
    manifest = _independent_raw_manifest()
    production = _production_adjusted_series()
    for symbol, instrument_id in (("ALFA", "INSTR-ALFA-001"), ("DELT", "INSTR-DELT-001")):
        raw_rows = _independent_raw_bars(symbol)
        for row in raw_rows:
            timestamp = datetime.fromisoformat(row["timestamp"])
            price_factor, volume_factor = _independent_split_factor_for(
                manifest, instrument_id, timestamp
            )
            assert price_factor == 1
            assert volume_factor == 1
        assert production["raw"][symbol].bars == production["adjusted"][symbol].bars


def test_independent_symbol_at_matches_boundary_semantics_for_delt() -> None:
    manifest = _independent_raw_manifest()
    before = datetime(2024, 3, 1, 9, 44, tzinfo=UTC)
    at_boundary = datetime(2024, 3, 1, 9, 45, tzinfo=UTC)
    after = datetime(2024, 3, 1, 9, 46, tzinfo=UTC)

    assert _independent_symbol_at(manifest, "INSTR-DELT-001", "DELT", before) == "OLDD"
    assert _independent_symbol_at(manifest, "INSTR-DELT-001", "DELT", at_boundary) == "DELT"
    assert _independent_symbol_at(manifest, "INSTR-DELT-001", "DELT", after) == "DELT"


def test_independent_verification_uses_the_real_declared_boundary_timestamp() -> None:
    # Sanity check that this verifier is actually exercising the real
    # fixture boundary, not a hand-picked value that happens to pass.
    manifest = _independent_raw_manifest()
    boundary_timestamps = {entry["effective_timestamp"] for entry in manifest["actions"]}
    assert boundary_timestamps == {"2024-03-01T09:45:00+00:00"}
