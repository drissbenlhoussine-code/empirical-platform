"""MILESTONE-083 -- pure row-mapping unit test. No database.

`_row_to_watermark` is the one piece of
`PostgresEvaluationEvidenceWatermarkRepository` with no PostgreSQL dependency
of its own: it maps an already-fetched row `Mapping` into
`EvaluationEvidenceWatermark`. Everything else in that class opens a real
connection and is covered by
`tests/integration/test_m083_evaluation_evidence_watermark_lifecycle.py`
against real PostgreSQL instead.
"""

from __future__ import annotations

from empirical_platform.shared.persistence.postgres_repositories.evaluation_evidence_watermark_repository import (  # noqa: E501
    _row_to_watermark,
)


def test_row_to_watermark_maps_a_plain_mapping() -> None:
    watermark = _row_to_watermark(
        {"watermark_governance_id": "WM-ROW", "receipt_governance_ids": ["RC-A", "RC-B"]}
    )
    assert watermark.watermark_governance_id == "WM-ROW"
    assert watermark.receipt_governance_ids == ("RC-A", "RC-B")


def test_row_to_watermark_maps_an_empty_receipt_array() -> None:
    watermark = _row_to_watermark(
        {"watermark_governance_id": "WM-EMPTY-ROW", "receipt_governance_ids": []}
    )
    assert watermark.receipt_governance_ids == ()


def test_row_to_watermark_coerces_non_string_column_values() -> None:
    """A defensive `str()` coercion, exercised against non-`str` DBAPI values
    (e.g. a driver returning a `memoryview` or a psycopg-specific text type)
    rather than assumed to be a no-op."""

    class _Weird:
        def __str__(self) -> str:
            return "WM-WEIRD"

    watermark = _row_to_watermark(
        {"watermark_governance_id": _Weird(), "receipt_governance_ids": [_Weird()]}
    )
    assert watermark.watermark_governance_id == "WM-WEIRD"
    assert watermark.receipt_governance_ids == ("WM-WEIRD",)
