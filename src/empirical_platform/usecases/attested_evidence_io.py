"""MILESTONE-082 rendering. Text and JSON carry the same facts.

Neither renderer may introduce a field the domain report does not carry. In
particular there is no future-tail count and no placeholder entry for an event
the snapshot cannot see -- see Owner review finding 1.
"""

from __future__ import annotations

from typing import Any

from empirical_platform.decision_candidate.operator_event_receipt import (
    ATTESTED_EVIDENCE_BANNER,
    AttestedEvidenceReport,
)

__all__ = ["render_attested_evidence_report_json", "render_attested_evidence_report_text"]


def render_attested_evidence_report_text(report: AttestedEvidenceReport) -> str:
    lines: list[str] = ["SYSTEM-RECEIPT-ATTESTED OPERATOR EVIDENCE", ""]
    for sentence in ATTESTED_EVIDENCE_BANNER.split(". "):
        stripped = sentence.strip().rstrip(".")
        if stripped:
            lines.append(f"  {stripped}")
    lines.append("")
    lines.append(f"  receipt_label_cutoff:  {report.receipt_label_cutoff.isoformat()}")
    lines.append(
        f"  {report.attested_count} event(s) carry a receipt labelled at or before this cutoff"
    )
    lines.append("  this snapshot cannot say how many events it excluded, and does not guess")
    for entry in report.entries:
        lines.append(
            f"    {entry.instrument_symbol} event={entry.event_governance_id} "
            f"position={entry.position_governance_id}"
        )
        lines.append(
            f"      system_received_at={entry.system_received_at.isoformat()} "
            f"attested_by={entry.attested_by} "
            "(system-assigned label, NOT a bound on commit time)"
        )
    for limitation in report.limitations:
        lines.append(f"  {limitation}")
    return "\n".join(lines)


def render_attested_evidence_report_json(report: AttestedEvidenceReport) -> dict[str, Any]:
    return {
        "banner": ATTESTED_EVIDENCE_BANNER,
        "receipt_label_cutoff": report.receipt_label_cutoff.isoformat(),
        "attested_count": report.attested_count,
        "entries": [
            {
                "event_governance_id": entry.event_governance_id,
                "position_governance_id": entry.position_governance_id,
                "instrument_symbol": entry.instrument_symbol,
                "system_received_at": entry.system_received_at.isoformat(),
                "attested_by": entry.attested_by,
            }
            for entry in report.entries
        ],
        "limitations": list(report.limitations),
    }
