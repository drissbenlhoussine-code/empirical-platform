"""Immutable Criterion Result primitive owned conceptually by Evidence Package."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from empirical_platform.identifiers import EvidencePackageId


@dataclass(frozen=True, slots=True)
class CriterionResult:
    """Generic, scoring-engine-neutral Criterion Result."""

    evidence_package_id: EvidencePackageId
    criterion_id: str
    recorded_at: datetime
    result_label: str
    summary: str | None = None
    evidence_references: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.evidence_package_id, EvidencePackageId):
            raise TypeError("evidence_package_id must be an EvidencePackageId")
        _require_non_empty(self.criterion_id, "criterion_id")
        _require_non_empty(self.result_label, "result_label")
        _require_optional_non_empty(self.summary, "summary")
        object.__setattr__(self, "evidence_references", tuple(self.evidence_references))
        for reference in self.evidence_references:
            _require_non_empty(reference, "evidence_references")


def _require_non_empty(value: str, field_name: str) -> None:
    if value.strip() == "":
        raise ValueError(f"{field_name} must be non-empty")


def _require_optional_non_empty(value: str | None, field_name: str) -> None:
    if value is not None:
        _require_non_empty(value, field_name)
