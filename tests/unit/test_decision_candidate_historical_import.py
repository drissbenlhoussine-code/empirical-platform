"""MILESTONE-065 pure unit tests: historical import pipeline.

CSV parsing edge cases, raw-import order-independence and rejection
invariants, split-adjusted derivation boundary math (verified against the
real M065 fixture's own hand-inspected raw values), and dataset-artifact
hash agreement with `DatasetSnapshotAuthority.normalized_sha256`.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from empirical_platform.decision_candidate.corporate_actions import CorporateActionManifest
from empirical_platform.decision_candidate.dataset_snapshot import DatasetSnapshotAuthority
from empirical_platform.decision_candidate.historical_backtest import HistoricalInstrumentSeries
from empirical_platform.decision_candidate.historical_import import (
    RawSourceFile,
    derive_split_adjusted_snapshot,
    import_raw_historical_dataset_snapshot,
    parse_source_csv,
    write_dataset_artifact,
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
_VALID_CSV = (
    b"timestamp,open,high,low,close,volume\n"
    b"2024-03-01T09:30:00+00:00,10.0000,10.5000,9.9000,10.2000,1000\n"
    b"2024-03-01T09:31:00+00:00,10.2000,10.6000,10.1000,10.4000,1100\n"
)


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


def _fixture_manifest() -> CorporateActionManifest:
    return parse_corporate_action_manifest_file(
        str(_FIXTURE_DIR / "corporate_action_manifest.json")
    )


def _import_fixture_raw() -> tuple[
    DatasetSnapshotAuthority, tuple[HistoricalInstrumentSeries, ...]
]:
    raw_files = read_raw_source_files(str(_FIXTURE_DIR))
    return import_raw_historical_dataset_snapshot(
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


# --------------------------------------------------------------------------
# parse_source_csv
# --------------------------------------------------------------------------


def test_parse_source_csv_valid() -> None:
    bars = parse_source_csv(
        _VALID_CSV, instrument=Instrument("ALFA"), interval=BarInterval.ONE_MINUTE
    )
    assert len(bars) == 2
    assert bars[0].close == Decimal("10.2000")
    assert bars[0].volume == 1000


def test_parse_source_csv_rejects_missing_required_column() -> None:
    bad = b"timestamp,open,high,low,close\n2024-03-01T09:30:00+00:00,10,10.5,9.9,10.2\n"
    with pytest.raises(ValueError, match="must declare columns"):
        parse_source_csv(bad, instrument=Instrument("ALFA"), interval=BarInterval.ONE_MINUTE)


def test_parse_source_csv_rejects_zero_data_rows() -> None:
    header_only = b"timestamp,open,high,low,close,volume\n"
    with pytest.raises(ValueError, match="zero data rows"):
        parse_source_csv(
            header_only, instrument=Instrument("ALFA"), interval=BarInterval.ONE_MINUTE
        )


def test_parse_source_csv_rejects_invalid_timestamp() -> None:
    bad = b"timestamp,open,high,low,close,volume\nnot-a-timestamp,10,10.5,9.9,10.2,1000\n"
    with pytest.raises(ValueError, match="invalid timestamp"):
        parse_source_csv(bad, instrument=Instrument("ALFA"), interval=BarInterval.ONE_MINUTE)


def test_parse_source_csv_rejects_naive_timestamp() -> None:
    bad = b"timestamp,open,high,low,close,volume\n2024-03-01T09:30:00,10,10.5,9.9,10.2,1000\n"
    with pytest.raises(ValueError, match="timezone-aware"):
        parse_source_csv(bad, instrument=Instrument("ALFA"), interval=BarInterval.ONE_MINUTE)


def test_parse_source_csv_rejects_invalid_ohlc() -> None:
    bad = (
        b"timestamp,open,high,low,close,volume\n2024-03-01T09:30:00+00:00,10.0,9.0,9.9,10.2,1000\n"
    )
    with pytest.raises(ValueError, match="invalid OHLCV"):
        parse_source_csv(bad, instrument=Instrument("ALFA"), interval=BarInterval.ONE_MINUTE)


def test_parse_source_csv_rejects_negative_volume() -> None:
    bad = b"timestamp,open,high,low,close,volume\n2024-03-01T09:30:00+00:00,10.0,10.5,9.9,10.2,-5\n"
    with pytest.raises(ValueError, match="invalid OHLCV"):
        parse_source_csv(bad, instrument=Instrument("ALFA"), interval=BarInterval.ONE_MINUTE)


def test_parse_source_csv_rejects_non_utf8_bytes() -> None:
    with pytest.raises(ValueError, match="not valid UTF-8"):
        parse_source_csv(
            b"\xff\xfe\x00\x01", instrument=Instrument("ALFA"), interval=BarInterval.ONE_MINUTE
        )


# --------------------------------------------------------------------------
# import_raw_historical_dataset_snapshot
# --------------------------------------------------------------------------


def test_import_raw_rejects_empty_source_files() -> None:
    with pytest.raises(ValueError, match="at least one source file"):
        import_raw_historical_dataset_snapshot(
            dataset_id=DatasetId("DATASET-9001"),
            dataset_version="1",
            source_kind="X",
            source_name="X",
            source_reference="X",
            license_note="X",
            snapshot_created_at=_CREATED,
            interval=BarInterval.ONE_MINUTE,
            raw_source_files=(),
            instrument_master=_instrument_master(),
        )


def test_import_raw_rejects_duplicate_file_name() -> None:
    files = (
        RawSourceFile(file_name="ALFA.csv", instrument_symbol="ALFA", raw_bytes=_VALID_CSV),
        RawSourceFile(file_name="ALFA.csv", instrument_symbol="ALFA", raw_bytes=_VALID_CSV),
    )
    with pytest.raises(ValueError, match="duplicate file_name"):
        import_raw_historical_dataset_snapshot(
            dataset_id=DatasetId("DATASET-9001"),
            dataset_version="1",
            source_kind="X",
            source_name="X",
            source_reference="X",
            license_note="X",
            snapshot_created_at=_CREATED,
            interval=BarInterval.ONE_MINUTE,
            raw_source_files=files,
            instrument_master=_instrument_master(),
        )


def test_import_raw_rejects_unknown_instrument() -> None:
    files = (RawSourceFile(file_name="ZZZZ.csv", instrument_symbol="ZZZZ", raw_bytes=_VALID_CSV),)
    with pytest.raises(ValueError, match="unknown instrument"):
        import_raw_historical_dataset_snapshot(
            dataset_id=DatasetId("DATASET-9001"),
            dataset_version="1",
            source_kind="X",
            source_name="X",
            source_reference="X",
            license_note="X",
            snapshot_created_at=_CREATED,
            interval=BarInterval.ONE_MINUTE,
            raw_source_files=files,
            instrument_master=_instrument_master(),
        )


def test_import_raw_is_order_independent() -> None:
    files = read_raw_source_files(str(_FIXTURE_DIR))
    reversed_files = tuple(reversed(files))
    forward_snapshot, _ = import_raw_historical_dataset_snapshot(
        dataset_id=DatasetId("DATASET-6501"),
        dataset_version="1",
        source_kind="CORPORATE_ACTION_MECHANICS_FIXTURE",
        source_name="fixture",
        source_reference=str(_FIXTURE_DIR),
        license_note="synthetic, no license required",
        snapshot_created_at=_CREATED,
        interval=BarInterval.ONE_MINUTE,
        raw_source_files=files,
        instrument_master=_instrument_master(),
    )
    reverse_snapshot, _ = import_raw_historical_dataset_snapshot(
        dataset_id=DatasetId("DATASET-6501"),
        dataset_version="1",
        source_kind="CORPORATE_ACTION_MECHANICS_FIXTURE",
        source_name="fixture",
        source_reference=str(_FIXTURE_DIR),
        license_note="synthetic, no license required",
        snapshot_created_at=_CREATED,
        interval=BarInterval.ONE_MINUTE,
        raw_source_files=reversed_files,
        instrument_master=_instrument_master(),
    )
    assert forward_snapshot.bundle_sha256 == reverse_snapshot.bundle_sha256
    assert forward_snapshot.normalized_sha256 == reverse_snapshot.normalized_sha256


def test_import_raw_fixture_produces_raw_unadjusted_snapshot() -> None:
    snapshot, series = _import_fixture_raw()
    from empirical_platform.decision_candidate.dataset_snapshot import (
        CorporateActionSemantics,
        PriceSemantics,
    )

    assert snapshot.price_semantics is PriceSemantics.RAW_UNADJUSTED
    assert snapshot.corporate_action_semantics is CorporateActionSemantics.NONE_DECLARED
    assert snapshot.corporate_action_manifest_hash is None
    assert snapshot.instrument_count == 4
    assert snapshot.total_row_count == 120
    assert len(series) == 4


# --------------------------------------------------------------------------
# derive_split_adjusted_snapshot: boundary math against the real fixture
# --------------------------------------------------------------------------


def test_derive_split_adjusted_beta_two_for_one_boundary_math() -> None:
    raw_snapshot, raw_series = _import_fixture_raw()
    manifest = _fixture_manifest()
    adjusted_snapshot, adjusted_series = derive_split_adjusted_snapshot(
        raw_snapshot,
        raw_series,
        dataset_version="2-split-adjusted",
        snapshot_created_at=_CREATED,
        corporate_action_manifest=manifest,
        instrument_master=_instrument_master(),
    )
    beta_raw = next(s for s in raw_series if s.instrument == Instrument("BETA"))
    beta_adjusted = next(s for s in adjusted_series if s.instrument == Instrument("BETA"))

    # Bar 14 (09:44:00) is the last raw bar strictly before the 09:45:00
    # split boundary -- must be halved (2-for-1 split, adjustment_factor=0.5).
    raw_pre_close = beta_raw.bars[14].close
    adjusted_pre_close = beta_adjusted.bars[14].close
    assert beta_raw.bars[14].timestamp == datetime(2024, 3, 1, 9, 44, tzinfo=UTC)
    assert adjusted_pre_close == (raw_pre_close * Decimal("0.5")).quantize(Decimal("0.0001"))

    # Bar 15 (09:45:00, at/after the boundary) must be byte-identical raw==adjusted.
    assert beta_raw.bars[15].timestamp == datetime(2024, 3, 1, 9, 45, tzinfo=UTC)
    assert beta_adjusted.bars[15] == beta_raw.bars[15]

    # Volume must be inversely adjusted (doubled) for the pre-boundary bar.
    assert beta_adjusted.bars[14].volume == round(beta_raw.bars[14].volume * 2)

    assert adjusted_snapshot.bundle_sha256 == raw_snapshot.bundle_sha256
    assert adjusted_snapshot.normalized_sha256 != raw_snapshot.normalized_sha256


def test_derive_split_adjusted_gama_reverse_split_boundary_math() -> None:
    raw_snapshot, raw_series = _import_fixture_raw()
    manifest = _fixture_manifest()
    _adjusted_snapshot, adjusted_series = derive_split_adjusted_snapshot(
        raw_snapshot,
        raw_series,
        dataset_version="2-split-adjusted",
        snapshot_created_at=_CREATED,
        corporate_action_manifest=manifest,
        instrument_master=_instrument_master(),
    )
    gama_raw = next(s for s in raw_series if s.instrument == Instrument("GAMA"))
    gama_adjusted = next(s for s in adjusted_series if s.instrument == Instrument("GAMA"))

    raw_pre_close = gama_raw.bars[14].close
    adjusted_pre_close = gama_adjusted.bars[14].close
    # 1-for-5 reverse split: adjustment_factor = 5.
    assert adjusted_pre_close == (raw_pre_close * Decimal("5")).quantize(Decimal("0.0001"))
    assert gama_adjusted.bars[15] == gama_raw.bars[15]
    assert gama_adjusted.bars[14].volume == round(gama_raw.bars[14].volume * Decimal("0.2"))


def test_derive_split_adjusted_delt_symbol_change_only_bars_unchanged() -> None:
    # DELT has only a SYMBOL_CHANGE declared, no SPLIT -- split_adjustment_factor_at
    # must return 1 for every DELT bar, so its adjusted series is bar-for-bar
    # identical to its raw series.
    raw_snapshot, raw_series = _import_fixture_raw()
    manifest = _fixture_manifest()
    _adjusted_snapshot, adjusted_series = derive_split_adjusted_snapshot(
        raw_snapshot,
        raw_series,
        dataset_version="2-split-adjusted",
        snapshot_created_at=_CREATED,
        corporate_action_manifest=manifest,
        instrument_master=_instrument_master(),
    )
    delt_raw = next(s for s in raw_series if s.instrument == Instrument("DELT"))
    delt_adjusted = next(s for s in adjusted_series if s.instrument == Instrument("DELT"))
    assert delt_raw.bars == delt_adjusted.bars


def test_derive_split_adjusted_alfa_no_action_bars_unchanged() -> None:
    raw_snapshot, raw_series = _import_fixture_raw()
    manifest = _fixture_manifest()
    _adjusted_snapshot, adjusted_series = derive_split_adjusted_snapshot(
        raw_snapshot,
        raw_series,
        dataset_version="2-split-adjusted",
        snapshot_created_at=_CREATED,
        corporate_action_manifest=manifest,
        instrument_master=_instrument_master(),
    )
    alfa_raw = next(s for s in raw_series if s.instrument == Instrument("ALFA"))
    alfa_adjusted = next(s for s in adjusted_series if s.instrument == Instrument("ALFA"))
    assert alfa_raw.bars == alfa_adjusted.bars


def test_derive_split_adjusted_rejects_action_outside_instrument_history() -> None:
    from empirical_platform.decision_candidate.corporate_actions import (
        CorporateActionType,
        SplitAction,
    )

    raw_snapshot, raw_series = _import_fixture_raw()
    orphaned_action = SplitAction(
        instrument_id=InstrumentId("INSTR-ZZZZ-001"),
        action_type=CorporateActionType.SPLIT,
        effective_timestamp=datetime(2024, 3, 1, 9, 45, tzinfo=UTC),
        ratio_new_shares=2,
        ratio_old_shares=1,
        source_kind="CORPORATE_ACTION_MECHANICS_FIXTURE",
    )
    manifest = CorporateActionManifest(
        dataset_id="DATASET-6501", dataset_version="1", actions=(orphaned_action,)
    )
    with pytest.raises(ValueError, match="does not correspond to any instrument"):
        derive_split_adjusted_snapshot(
            raw_snapshot,
            raw_series,
            dataset_version="2-split-adjusted",
            snapshot_created_at=_CREATED,
            corporate_action_manifest=manifest,
            instrument_master=_instrument_master(),
        )


# --------------------------------------------------------------------------
# write_dataset_artifact: hash agreement
# --------------------------------------------------------------------------


def test_write_dataset_artifact_hash_matches_normalized_sha256(tmp_path: Path) -> None:
    raw_snapshot, raw_series = _import_fixture_raw()
    artifact_path = tmp_path / "raw_artifact.json"
    written_sha256 = write_dataset_artifact(
        artifact_path,
        dataset_id=raw_snapshot.dataset_id,
        dataset_version=raw_snapshot.dataset_version,
        source_kind=raw_snapshot.source_kind,
        series=raw_series,
    )
    assert written_sha256 == raw_snapshot.normalized_sha256
    payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    assert payload["dataset_id"] == "DATASET-6501"
    assert len(payload["instruments"]) == 4


# --------------------------------------------------------------------------
# Tamper detection (Phase 21) and dataset-version coexistence (Phase 22)
# --------------------------------------------------------------------------


def test_tampered_source_file_byte_changes_bundle_and_normalized_hash() -> None:
    original_snapshot, _ = _import_fixture_raw()

    raw_files = list(read_raw_source_files(str(_FIXTURE_DIR)))
    tampered_files = []
    for source_file in raw_files:
        if source_file.file_name == "BETA.csv":
            tampered_files.append(
                RawSourceFile(
                    file_name=source_file.file_name,
                    instrument_symbol=source_file.instrument_symbol,
                    raw_bytes=source_file.raw_bytes.replace(b",2813\r\n", b",9999\r\n"),
                )
            )
        else:
            tampered_files.append(source_file)

    tampered_snapshot, _ = import_raw_historical_dataset_snapshot(
        dataset_id=DatasetId("DATASET-6501"),
        dataset_version="1",
        source_kind="CORPORATE_ACTION_MECHANICS_FIXTURE",
        source_name="fixture",
        source_reference=str(_FIXTURE_DIR),
        license_note="synthetic, no license required",
        snapshot_created_at=_CREATED,
        interval=BarInterval.ONE_MINUTE,
        raw_source_files=tuple(tampered_files),
        instrument_master=_instrument_master(),
    )
    assert tampered_snapshot.bundle_sha256 != original_snapshot.bundle_sha256
    assert tampered_snapshot.normalized_sha256 != original_snapshot.normalized_sha256
    beta_entry = next(
        entry for entry in tampered_snapshot.source_file_manifest if entry.file_name == "BETA.csv"
    )
    original_beta_entry = next(
        entry for entry in original_snapshot.source_file_manifest if entry.file_name == "BETA.csv"
    )
    assert beta_entry.sha256 != original_beta_entry.sha256


def test_tampered_corporate_action_manifest_changes_manifest_hash_and_adjusted_snapshot() -> None:
    from empirical_platform.decision_candidate.corporate_actions import (
        CorporateActionManifest,
        CorporateActionType,
        SplitAction,
        corporate_action_manifest_hash,
    )

    original_manifest = _fixture_manifest()
    original_hash = corporate_action_manifest_hash(original_manifest)

    tampered_actions = tuple(
        SplitAction(
            instrument_id=action.instrument_id,
            action_type=action.action_type,
            effective_timestamp=action.effective_timestamp,
            ratio_new_shares=3,
            ratio_old_shares=1,
            source_kind=action.source_kind,
        )
        if isinstance(action, SplitAction) and action.action_type is CorporateActionType.SPLIT
        else action
        for action in original_manifest.actions
    )
    tampered_manifest = CorporateActionManifest(
        dataset_id=original_manifest.dataset_id,
        dataset_version=original_manifest.dataset_version,
        actions=tampered_actions,
    )
    tampered_hash = corporate_action_manifest_hash(tampered_manifest)
    assert tampered_hash != original_hash

    raw_snapshot, raw_series = _import_fixture_raw()
    original_adjusted, _ = derive_split_adjusted_snapshot(
        raw_snapshot,
        raw_series,
        dataset_version="2-split-adjusted",
        snapshot_created_at=_CREATED,
        corporate_action_manifest=original_manifest,
        instrument_master=_instrument_master(),
    )
    tampered_adjusted, _ = derive_split_adjusted_snapshot(
        raw_snapshot,
        raw_series,
        dataset_version="2-split-adjusted",
        snapshot_created_at=_CREATED,
        corporate_action_manifest=tampered_manifest,
        instrument_master=_instrument_master(),
    )
    assert (
        tampered_adjusted.corporate_action_manifest_hash
        != original_adjusted.corporate_action_manifest_hash
    )
    assert tampered_adjusted.normalized_sha256 != original_adjusted.normalized_sha256


def test_two_dataset_versions_of_same_raw_source_coexist_immutably() -> None:
    # Raw ("1") and split-adjusted ("2-split-adjusted") snapshots derived
    # from the identical raw source bytes must retain the same bundle
    # identity (same source files) while differing in dataset_version and
    # normalized_sha256 -- immutable coexistence, no mutable overwrite.
    raw_snapshot, raw_series = _import_fixture_raw()
    manifest = _fixture_manifest()
    adjusted_snapshot, _ = derive_split_adjusted_snapshot(
        raw_snapshot,
        raw_series,
        dataset_version="2-split-adjusted",
        snapshot_created_at=_CREATED,
        corporate_action_manifest=manifest,
        instrument_master=_instrument_master(),
    )
    assert raw_snapshot.dataset_id == adjusted_snapshot.dataset_id
    assert raw_snapshot.dataset_version != adjusted_snapshot.dataset_version
    assert raw_snapshot.bundle_sha256 == adjusted_snapshot.bundle_sha256
    assert raw_snapshot.normalized_sha256 != adjusted_snapshot.normalized_sha256
