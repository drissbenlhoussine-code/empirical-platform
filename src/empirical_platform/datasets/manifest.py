"""Immutable Dataset Manifest primitive owned conceptually by Run."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from empirical_platform.identifiers import DatasetId, RunId


@dataclass(frozen=True, slots=True)
class DatasetManifest:
    """Storage-layout-neutral Dataset Manifest owned by a Run."""

    run_id: RunId
    recorded_at: datetime
    source: str
    acquisition_method: str | None = None
    normalization_method: str | None = None
    manifest_id: DatasetId | None = None
    notes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.run_id, RunId):
            raise TypeError("run_id must be a RunId")
        if self.manifest_id is not None and not isinstance(self.manifest_id, DatasetId):
            raise TypeError("manifest_id must be a DatasetId when provided")
        _require_non_empty(self.source, "source")
        _require_optional_non_empty(self.acquisition_method, "acquisition_method")
        _require_optional_non_empty(self.normalization_method, "normalization_method")
        object.__setattr__(self, "notes", tuple(self.notes))
        for note in self.notes:
            _require_non_empty(note, "notes")


def _require_non_empty(value: str, field_name: str) -> None:
    if value.strip() == "":
        raise ValueError(f"{field_name} must be non-empty")


def _require_optional_non_empty(value: str | None, field_name: str) -> None:
    if value is not None:
        _require_non_empty(value, field_name)
