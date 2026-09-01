"""MILESTONE-083 watermark capture command and get query."""

from __future__ import annotations

from dataclasses import dataclass

from empirical_platform.decision_candidate.evaluation_evidence_watermark import (
    EvaluationEvidenceWatermark,
)
from empirical_platform.decision_candidate.evaluation_evidence_watermark_repository import (
    EvaluationEvidenceWatermarkRepository,
)

__all__ = [
    "CaptureEvaluationEvidenceWatermarkCommand",
    "CaptureEvaluationEvidenceWatermarkHandler",
    "GetEvaluationEvidenceWatermarkHandler",
    "GetEvaluationEvidenceWatermarkQuery",
    "WatermarkNotFoundError",
]


@dataclass(frozen=True, slots=True)
class CaptureEvaluationEvidenceWatermarkCommand:
    """Capture one watermark. The caller supplies ONLY the identity.

    DELIBERATELY no receipt identity, timestamp, cutoff, sequence, count or
    digest parameter -- accepting any of those here would let a caller
    influence the persisted set, which is precisely the exact-set
    completeness this milestone exists to make database-enforced rather than
    caller-trusted.
    """

    watermark_governance_id: str

    def __post_init__(self) -> None:
        if not self.watermark_governance_id.strip():
            raise ValueError("watermark_governance_id must be non-empty")


class CaptureEvaluationEvidenceWatermarkHandler:
    """Writes one watermark through the append-only watermark repository."""

    __slots__ = ("_watermarks",)

    def __init__(
        self, *, evaluation_evidence_watermark_repository: EvaluationEvidenceWatermarkRepository
    ) -> None:
        self._watermarks = evaluation_evidence_watermark_repository

    def handle(
        self, command: CaptureEvaluationEvidenceWatermarkCommand
    ) -> EvaluationEvidenceWatermark:
        # A database-level failure PROPAGATES, as in M082: an infrastructure
        # fault is not an empty evidence set, and disguising it would be a
        # false claim about what the receipt store actually holds.
        return self._watermarks.capture(watermark_governance_id=command.watermark_governance_id)


@dataclass(frozen=True, slots=True)
class GetEvaluationEvidenceWatermarkQuery:
    watermark_governance_id: str

    def __post_init__(self) -> None:
        if not self.watermark_governance_id.strip():
            raise ValueError("watermark_governance_id must be non-empty")


class WatermarkNotFoundError(RuntimeError):
    """Raised when a watermark is requested that was never captured.

    Deliberately NOT a soft None-returning query at the use case boundary: a
    caller asking for one specific watermark by identity wants either that
    watermark or an explicit refusal, not a value it must remember to check.
    The repository protocol itself still returns `None` (see
    `EvaluationEvidenceWatermarkRepository.get`) -- this type exists only at
    this narrower, identity-specific use case.
    """


class GetEvaluationEvidenceWatermarkHandler:
    """Reads one persisted watermark's STORED set. Never touches the receipt store."""

    __slots__ = ("_watermarks",)

    def __init__(
        self, *, evaluation_evidence_watermark_repository: EvaluationEvidenceWatermarkRepository
    ) -> None:
        self._watermarks = evaluation_evidence_watermark_repository

    def handle(self, query: GetEvaluationEvidenceWatermarkQuery) -> EvaluationEvidenceWatermark:
        watermark = self._watermarks.get(query.watermark_governance_id)
        if watermark is None:
            raise WatermarkNotFoundError(
                f"no evaluation evidence watermark with governance_id "
                f"{query.watermark_governance_id!r} has ever been captured"
            )
        return watermark
