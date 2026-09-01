"""MILESTONE-083 deterministic text and JSON rendering of one watermark.

Both renderers expose the SAME three facts and nothing else: the watermark
governance identity, the exact receipt governance identities in their stored
canonical order, and the captured count derived from that same stored list.
Neither renderer emits a timestamp, a receipt label, receipt metadata, event
payload, or the current receipt inventory -- none of those are fields on
`EvaluationEvidenceWatermark`, so there is nothing here that could leak them.
"""

from __future__ import annotations

from typing import Any

from empirical_platform.decision_candidate.evaluation_evidence_watermark import (
    EvaluationEvidenceWatermark,
)

__all__ = [
    "WATERMARK_BANNER",
    "render_evaluation_evidence_watermark_json",
    "render_evaluation_evidence_watermark_text",
]

WATERMARK_BANNER = (
    "PERSISTED RECEIPT-SET EVALUATION EVIDENCE WATERMARK: the exact set of M082 "
    "receipt governance identities visible to the PostgreSQL statement that "
    "captured this watermark, under that statement's own transaction snapshot, "
    "in canonical order. "
    "THIS DOES NOT CLAIM any ResearchSession, DecisionCandidate, brief or "
    "evaluation consumed this watermark -- no such binding exists in this "
    "milestone. "
    "It carries no timestamp, no receipt label, no event payload and no "
    "receipt metadata, and it is never re-derived from the current receipt "
    "inventory: this is the STORED set, fixed at capture, and it does not "
    "change when later receipts are inserted."
)


def render_evaluation_evidence_watermark_text(watermark: EvaluationEvidenceWatermark) -> str:
    lines = [
        WATERMARK_BANNER,
        "",
        f"watermark_governance_id: {watermark.watermark_governance_id}",
        f"captured_receipt_count: {watermark.captured_receipt_count}",
        "receipt_governance_ids:",
    ]
    if watermark.receipt_governance_ids:
        lines.extend(f"  - {receipt_id}" for receipt_id in watermark.receipt_governance_ids)
    else:
        lines.append("  (none)")
    lines.append("")
    return "\n".join(lines)


def render_evaluation_evidence_watermark_json(
    watermark: EvaluationEvidenceWatermark,
) -> dict[str, Any]:
    return {
        "banner": WATERMARK_BANNER,
        "watermark_governance_id": watermark.watermark_governance_id,
        "receipt_governance_ids": list(watermark.receipt_governance_ids),
        "captured_receipt_count": watermark.captured_receipt_count,
    }
