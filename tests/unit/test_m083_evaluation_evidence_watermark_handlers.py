"""MILESTONE-083 -- handler wiring, exercised against an in-memory repository.

No database: these tests establish that each handler delegates to the port it
was given and returns exactly what the port produced, mirroring
`tests/unit/test_m082_receipt_handlers.py`'s pattern for the same reason --
this is the part of the usecase layer that does not depend on PostgreSQL.
"""

from __future__ import annotations

import pytest

from empirical_platform.decision_candidate.evaluation_evidence_watermark import (
    EvaluationEvidenceWatermark,
)
from empirical_platform.usecases.capture_evaluation_evidence_watermark import (
    CaptureEvaluationEvidenceWatermarkCommand,
    CaptureEvaluationEvidenceWatermarkHandler,
    GetEvaluationEvidenceWatermarkHandler,
    GetEvaluationEvidenceWatermarkQuery,
    WatermarkNotFoundError,
)


class _FakeWatermarks:
    """Records what the handler asked for, and answers with fixed rows."""

    def __init__(self, rows: tuple[EvaluationEvidenceWatermark, ...] = ()) -> None:
        self.rows = {row.watermark_governance_id: row for row in rows}
        self.captured: list[str] = []

    def capture(self, *, watermark_governance_id: str) -> EvaluationEvidenceWatermark:
        self.captured.append(watermark_governance_id)
        existing = self.rows.get(watermark_governance_id)
        if existing is not None:
            return existing
        created = EvaluationEvidenceWatermark(
            watermark_governance_id=watermark_governance_id, receipt_governance_ids=()
        )
        self.rows[watermark_governance_id] = created
        return created

    def get(self, watermark_governance_id: str) -> EvaluationEvidenceWatermark | None:
        return self.rows.get(watermark_governance_id)


def test_a_blank_capture_command_identity_is_refused() -> None:
    with pytest.raises(ValueError, match="watermark_governance_id must be non-empty"):
        CaptureEvaluationEvidenceWatermarkCommand(watermark_governance_id="   ")


def test_a_blank_get_query_identity_is_refused() -> None:
    with pytest.raises(ValueError, match="watermark_governance_id must be non-empty"):
        GetEvaluationEvidenceWatermarkQuery(watermark_governance_id="")


def test_the_capture_handler_passes_the_identity_through_unchanged() -> None:
    watermarks = _FakeWatermarks()
    handler = CaptureEvaluationEvidenceWatermarkHandler(
        evaluation_evidence_watermark_repository=watermarks
    )
    result = handler.handle(
        CaptureEvaluationEvidenceWatermarkCommand(watermark_governance_id="WM-1")
    )
    assert watermarks.captured == ["WM-1"]
    assert result.watermark_governance_id == "WM-1"


def test_a_repository_failure_propagates_rather_than_reading_as_an_empty_set() -> None:
    """An infrastructure fault is not an empty evidence set."""

    class _Broken(_FakeWatermarks):
        def capture(self, **_: object) -> EvaluationEvidenceWatermark:
            raise RuntimeError("connection lost")

    handler = CaptureEvaluationEvidenceWatermarkHandler(
        evaluation_evidence_watermark_repository=_Broken()
    )
    with pytest.raises(RuntimeError, match="connection lost"):
        handler.handle(CaptureEvaluationEvidenceWatermarkCommand(watermark_governance_id="WM-2"))


def test_the_get_handler_returns_the_stored_watermark_unchanged() -> None:
    existing = EvaluationEvidenceWatermark(
        watermark_governance_id="WM-EXISTING", receipt_governance_ids=("RC-A", "RC-B")
    )
    watermarks = _FakeWatermarks((existing,))
    handler = GetEvaluationEvidenceWatermarkHandler(
        evaluation_evidence_watermark_repository=watermarks
    )
    result = handler.handle(
        GetEvaluationEvidenceWatermarkQuery(watermark_governance_id="WM-EXISTING")
    )
    assert result == existing


def test_the_get_handler_refuses_an_identity_that_was_never_captured() -> None:
    handler = GetEvaluationEvidenceWatermarkHandler(
        evaluation_evidence_watermark_repository=_FakeWatermarks()
    )
    with pytest.raises(WatermarkNotFoundError, match="WM-MISSING"):
        handler.handle(GetEvaluationEvidenceWatermarkQuery(watermark_governance_id="WM-MISSING"))
