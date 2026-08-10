"""Immutable historical dataset snapshot authority.

MILESTONE-065. A `DatasetSnapshotAuthority` is the governance record for
one immutable, versioned import of local historical market-data source
files: which files were imported, their own raw-byte hashes, the
resulting canonical (normalized) content hash, the declared price
semantics, and the declared corporate-action semantics. It is deliberately
richer than the frozen M061 `HistoricalDatasetAuthority` (which only
tracks a single already-canonical dataset file's own identity) --
`DatasetSnapshotAuthority` tracks *provenance*: what raw source produced
this data and how it was interpreted, before a M061-compatible dataset
JSON artifact is ever produced from it.

The M061 dataset JSON artifact this module's import pipeline produces
(see `historical_import.py`) is auditable against this snapshot via
SHA-256 equality: `HistoricalBacktestRun.dataset_sha256 ==
DatasetSnapshotAuthority.normalized_sha256`, since the artifact writer and
the snapshot's own hash are computed over the identical bytes -- no new
foreign key into the frozen M061 schema is required or added.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from empirical_platform.decision_candidate.market_data import BarInterval
from empirical_platform.identifiers.types import DatasetId

DIVIDEND_TOTAL_RETURN_HANDLING_NOT_EXERCISED = "DIVIDEND_TOTAL_RETURN_HANDLING_NOT_EXERCISED"


class PriceSemantics(StrEnum):
    """Closed price-semantics vocabulary. A dataset snapshot declares
    exactly one of these -- raw and adjusted prices are never silently
    mixed within one snapshot."""

    RAW_UNADJUSTED = "RAW_UNADJUSTED"
    SPLIT_ADJUSTED = "SPLIT_ADJUSTED"
    TOTAL_RETURN_ADJUSTED = "TOTAL_RETURN_ADJUSTED"


class CorporateActionSemantics(StrEnum):
    """Whether, and how, the snapshot's own bar prices already encode
    corporate-action knowledge."""

    NONE_DECLARED = "NONE_DECLARED"
    SPLIT_AND_SYMBOL_CHANGE_AWARE = "SPLIT_AND_SYMBOL_CHANGE_AWARE"


@dataclass(frozen=True, slots=True)
class SourceFileManifestEntry:
    """One immutable raw source file's own identity: which instrument
    symbol it covers (as declared in the file, which may be a pre-rename
    symbol), its raw-byte SHA-256, and its own row count."""

    file_name: str
    instrument_symbol: str
    sha256: str
    row_count: int

    def __post_init__(self) -> None:
        if not self.file_name.strip():
            raise ValueError("file_name must be non-empty")
        if not self.instrument_symbol.strip():
            raise ValueError("instrument_symbol must be non-empty")
        if len(self.sha256) != 64:
            raise ValueError("sha256 must be a full SHA-256 hex digest")
        if self.row_count < 1:
            raise ValueError("row_count must be at least 1")


@dataclass(frozen=True, slots=True)
class DatasetSnapshotAuthority:
    """One immutable, versioned historical dataset snapshot's own full
    provenance record."""

    dataset_id: DatasetId
    dataset_version: str
    source_kind: str
    source_name: str
    source_reference: str
    license_note: str
    snapshot_created_at: datetime
    interval: BarInterval
    start_timestamp: datetime
    end_timestamp: datetime
    instrument_count: int
    total_row_count: int
    file_count: int
    source_file_manifest: tuple[SourceFileManifestEntry, ...]
    bundle_sha256: str
    normalized_sha256: str
    price_semantics: PriceSemantics
    corporate_action_semantics: CorporateActionSemantics
    corporate_action_manifest_hash: str | None
    dividend_handling: str

    def __post_init__(self) -> None:
        for field_name in (
            "dataset_version",
            "source_kind",
            "source_name",
            "source_reference",
            "license_note",
            "dividend_handling",
        ):
            if not getattr(self, field_name).strip():
                raise ValueError(f"{field_name} must be non-empty")
        if len(self.bundle_sha256) != 64:
            raise ValueError("bundle_sha256 must be a full SHA-256 hex digest")
        if len(self.normalized_sha256) != 64:
            raise ValueError("normalized_sha256 must be a full SHA-256 hex digest")
        if (
            self.corporate_action_manifest_hash is not None
            and len(self.corporate_action_manifest_hash) != 64
        ):
            raise ValueError(
                "corporate_action_manifest_hash must be a full SHA-256 hex digest when set"
            )
        if (
            self.corporate_action_semantics
            is CorporateActionSemantics.SPLIT_AND_SYMBOL_CHANGE_AWARE
        ):
            if self.corporate_action_manifest_hash is None:
                raise ValueError(
                    "corporate_action_manifest_hash must be set when "
                    "corporate_action_semantics declares awareness"
                )
        elif self.corporate_action_manifest_hash is not None:
            raise ValueError(
                "corporate_action_manifest_hash must be None when no corporate-action "
                "semantics are declared"
            )
        if self.snapshot_created_at.tzinfo is None:
            raise ValueError("snapshot_created_at must be timezone-aware")
        if self.start_timestamp.tzinfo is None or self.end_timestamp.tzinfo is None:
            raise ValueError("start_timestamp/end_timestamp must be timezone-aware")
        if self.start_timestamp >= self.end_timestamp:
            raise ValueError("start_timestamp must be strictly before end_timestamp")
        if self.instrument_count < 1:
            raise ValueError("instrument_count must be at least 1")
        if self.total_row_count < 1:
            raise ValueError("total_row_count must be at least 1")
        if self.file_count < 1:
            raise ValueError("file_count must be at least 1")
        if len(self.source_file_manifest) != self.file_count:
            raise ValueError("file_count must match the supplied source_file_manifest length")
        file_names = [entry.file_name for entry in self.source_file_manifest]
        if len(set(file_names)) != len(file_names):
            raise ValueError("source_file_manifest must not contain duplicate file_name values")
