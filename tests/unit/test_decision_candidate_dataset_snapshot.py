"""MILESTONE-065 pure unit tests: dataset snapshot authority domain."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from empirical_platform.decision_candidate.dataset_snapshot import (
    DIVIDEND_TOTAL_RETURN_HANDLING_NOT_EXERCISED,
    CorporateActionSemantics,
    DatasetSnapshotAuthority,
    PriceSemantics,
    SourceFileManifestEntry,
)
from empirical_platform.decision_candidate.market_data import BarInterval
from empirical_platform.identifiers.types import DatasetId

_SHA = "a" * 64
_START = datetime(2024, 3, 1, 9, 30, tzinfo=UTC)
_END = datetime(2024, 3, 1, 10, 0, tzinfo=UTC)
_CREATED = datetime(2024, 3, 2, tzinfo=UTC)


def _entry(**overrides: object) -> SourceFileManifestEntry:
    fields = {
        "file_name": "BETA.csv",
        "instrument_symbol": "BETA",
        "sha256": _SHA,
        "row_count": 30,
    }
    fields.update(overrides)
    return SourceFileManifestEntry(**fields)  # type: ignore[arg-type]


def _snapshot(**overrides: object) -> DatasetSnapshotAuthority:
    fields: dict[str, object] = {
        "dataset_id": DatasetId("DATASET-6501"),
        "dataset_version": "1",
        "source_kind": "CORPORATE_ACTION_MECHANICS_FIXTURE",
        "source_name": "fixture",
        "source_reference": "tests/fixtures/m065_corporate_action_mechanics/",
        "license_note": "synthetic, no license required",
        "snapshot_created_at": _CREATED,
        "interval": BarInterval.ONE_MINUTE,
        "start_timestamp": _START,
        "end_timestamp": _END,
        "instrument_count": 1,
        "total_row_count": 30,
        "file_count": 1,
        "source_file_manifest": (_entry(),),
        "bundle_sha256": _SHA,
        "normalized_sha256": _SHA,
        "price_semantics": PriceSemantics.RAW_UNADJUSTED,
        "corporate_action_semantics": CorporateActionSemantics.NONE_DECLARED,
        "corporate_action_manifest_hash": None,
        "dividend_handling": DIVIDEND_TOTAL_RETURN_HANDLING_NOT_EXERCISED,
    }
    fields.update(overrides)
    return DatasetSnapshotAuthority(**fields)  # type: ignore[arg-type]


# --------------------------------------------------------------------------
# SourceFileManifestEntry
# --------------------------------------------------------------------------


def test_source_file_manifest_entry_rejects_empty_file_name() -> None:
    with pytest.raises(ValueError, match="file_name"):
        _entry(file_name="  ")


def test_source_file_manifest_entry_rejects_empty_instrument_symbol() -> None:
    with pytest.raises(ValueError, match="instrument_symbol"):
        _entry(instrument_symbol="")


def test_source_file_manifest_entry_rejects_short_sha256() -> None:
    with pytest.raises(ValueError, match="SHA-256"):
        _entry(sha256="abc123")


def test_source_file_manifest_entry_rejects_non_positive_row_count() -> None:
    with pytest.raises(ValueError, match="row_count"):
        _entry(row_count=0)


# --------------------------------------------------------------------------
# DatasetSnapshotAuthority
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "field_name",
    ["dataset_version", "source_kind", "source_name", "source_reference", "license_note"],
)
def test_snapshot_rejects_empty_string_fields(field_name: str) -> None:
    with pytest.raises(ValueError, match=field_name):
        _snapshot(**{field_name: "   "})


def test_snapshot_rejects_short_bundle_sha256() -> None:
    with pytest.raises(ValueError, match="bundle_sha256"):
        _snapshot(bundle_sha256="short")


def test_snapshot_rejects_short_normalized_sha256() -> None:
    with pytest.raises(ValueError, match="normalized_sha256"):
        _snapshot(normalized_sha256="short")


def test_snapshot_requires_manifest_hash_when_corporate_action_aware() -> None:
    with pytest.raises(ValueError, match="corporate_action_manifest_hash must be set"):
        _snapshot(
            corporate_action_semantics=CorporateActionSemantics.SPLIT_AND_SYMBOL_CHANGE_AWARE,
            corporate_action_manifest_hash=None,
        )


def test_snapshot_rejects_manifest_hash_when_no_semantics_declared() -> None:
    with pytest.raises(ValueError, match="must be None when no corporate-action"):
        _snapshot(
            corporate_action_semantics=CorporateActionSemantics.NONE_DECLARED,
            corporate_action_manifest_hash=_SHA,
        )


def test_snapshot_rejects_short_manifest_hash_when_set() -> None:
    with pytest.raises(ValueError, match="corporate_action_manifest_hash must be a full"):
        _snapshot(
            corporate_action_semantics=CorporateActionSemantics.SPLIT_AND_SYMBOL_CHANGE_AWARE,
            corporate_action_manifest_hash="short",
        )


def test_snapshot_accepts_valid_corporate_action_aware_record() -> None:
    snapshot = _snapshot(
        corporate_action_semantics=CorporateActionSemantics.SPLIT_AND_SYMBOL_CHANGE_AWARE,
        corporate_action_manifest_hash=_SHA,
    )
    assert snapshot.corporate_action_manifest_hash == _SHA


def test_snapshot_rejects_naive_snapshot_created_at() -> None:
    with pytest.raises(ValueError, match="snapshot_created_at"):
        _snapshot(snapshot_created_at=datetime(2024, 3, 2))  # noqa: DTZ001


def test_snapshot_rejects_naive_start_timestamp() -> None:
    with pytest.raises(ValueError, match="start_timestamp/end_timestamp"):
        _snapshot(start_timestamp=datetime(2024, 3, 1, 9, 30))  # noqa: DTZ001


def test_snapshot_rejects_start_not_strictly_before_end() -> None:
    with pytest.raises(ValueError, match="start_timestamp must be strictly before"):
        _snapshot(start_timestamp=_END, end_timestamp=_END)


def test_snapshot_rejects_non_positive_instrument_count() -> None:
    with pytest.raises(ValueError, match="instrument_count"):
        _snapshot(instrument_count=0)


def test_snapshot_rejects_non_positive_total_row_count() -> None:
    with pytest.raises(ValueError, match="total_row_count"):
        _snapshot(total_row_count=0)


def test_snapshot_rejects_non_positive_file_count() -> None:
    with pytest.raises(ValueError, match="file_count"):
        _snapshot(file_count=0)


def test_snapshot_rejects_file_count_mismatch() -> None:
    with pytest.raises(ValueError, match="file_count must match"):
        _snapshot(file_count=2, source_file_manifest=(_entry(),))


def test_snapshot_rejects_duplicate_file_name_in_manifest() -> None:
    with pytest.raises(ValueError, match="duplicate file_name"):
        _snapshot(
            file_count=2,
            source_file_manifest=(_entry(), _entry()),
        )
