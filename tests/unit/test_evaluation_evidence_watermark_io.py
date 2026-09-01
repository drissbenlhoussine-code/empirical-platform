"""MILESTONE-083 -- pure rendering unit tests. No database.

Mirrors how M082's text/JSON renderers are covered directly (see
`tests/unit/test_decision_candidate_operator_event_receipt.py`), since
rendering a `EvaluationEvidenceWatermark` has no PostgreSQL dependency at all.
"""

from __future__ import annotations

from empirical_platform.decision_candidate.evaluation_evidence_watermark import (
    EvaluationEvidenceWatermark,
)
from empirical_platform.usecases.evaluation_evidence_watermark_io import (
    WATERMARK_BANNER,
    render_evaluation_evidence_watermark_json,
    render_evaluation_evidence_watermark_text,
)


def test_text_rendering_lists_every_receipt_id_in_stored_order() -> None:
    watermark = EvaluationEvidenceWatermark(
        watermark_governance_id="WM-TXT", receipt_governance_ids=("RC-A", "RC-B")
    )
    rendered = render_evaluation_evidence_watermark_text(watermark)
    assert WATERMARK_BANNER in rendered
    assert "watermark_governance_id: WM-TXT" in rendered
    assert "captured_receipt_count: 2" in rendered
    assert "  - RC-A" in rendered
    assert "  - RC-B" in rendered


def test_text_rendering_states_none_explicitly_for_an_empty_set() -> None:
    watermark = EvaluationEvidenceWatermark(
        watermark_governance_id="WM-EMPTY-TXT", receipt_governance_ids=()
    )
    rendered = render_evaluation_evidence_watermark_text(watermark)
    assert "captured_receipt_count: 0" in rendered
    assert "(none)" in rendered


def test_json_rendering_exposes_exactly_four_keys() -> None:
    watermark = EvaluationEvidenceWatermark(
        watermark_governance_id="WM-JSON", receipt_governance_ids=("RC-A",)
    )
    payload = render_evaluation_evidence_watermark_json(watermark)
    assert set(payload) == {
        "banner",
        "watermark_governance_id",
        "receipt_governance_ids",
        "captured_receipt_count",
    }
    assert payload["watermark_governance_id"] == "WM-JSON"
    assert payload["receipt_governance_ids"] == ["RC-A"]
    assert payload["captured_receipt_count"] == 1
    assert payload["banner"] == WATERMARK_BANNER


def test_json_rendering_uses_a_plain_list_not_a_tuple() -> None:
    """A tuple is not directly `json.dumps`-serializable in the same shape."""
    watermark = EvaluationEvidenceWatermark(
        watermark_governance_id="WM-LIST", receipt_governance_ids=("RC-A", "RC-B")
    )
    payload = render_evaluation_evidence_watermark_json(watermark)
    assert isinstance(payload["receipt_governance_ids"], list)


def test_no_rendering_ever_mentions_event_payload_fields() -> None:
    watermark = EvaluationEvidenceWatermark(
        watermark_governance_id="WM-NOPAYLOAD", receipt_governance_ids=("RC-A",)
    )
    text = render_evaluation_evidence_watermark_text(watermark)
    json_payload = render_evaluation_evidence_watermark_json(watermark)
    for forbidden in ("instrument", "quantity", "price", "event_timestamp"):
        assert forbidden not in text
        assert forbidden not in str(json_payload)
