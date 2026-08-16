"""MILESTONE-082 rendering. Text and JSON carry the same facts."""

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
    lines.append(f"  attested_as_of:  {report.attested_as_of.isoformat()}")
    lines.append(
        f"  {report.attested_count} attested by this cutoff, "
        f"{report.attested_after_cutoff_count} attested only after it, "
        f"{report.unattested_count} with no system receipt evidence"
    )
    for entry in report.entries:
        lines.append(
            f"    {entry.instrument_symbol} event={entry.event_governance_id} "
            f"position={entry.position_governance_id} {entry.status}"
        )
        if entry.system_received_at is None:
            lines.append(
                "      no system receipt visible at this cutoff; "
                "NOT filled in from recorded_at or event_timestamp"
            )
        else:
            lines.append(
                f"      system_received_at={entry.system_received_at.isoformat()} "
                f"attested_by={entry.attested_by} "
                "(upper bound witness on commit time, NOT the commit time)"
            )
    for limitation in report.limitations:
        lines.append(f"  {limitation}")
    return "\n".join(lines)


def render_attested_evidence_report_json(report: AttestedEvidenceReport) -> dict[str, Any]:
    return {
        "banner": ATTESTED_EVIDENCE_BANNER,
        "attested_as_of": report.attested_as_of.isoformat(),
        "attested_count": report.attested_count,
        "attested_after_cutoff_count": report.attested_after_cutoff_count,
        "unattested_count": report.unattested_count,
        "entries": [
            {
                "event_governance_id": entry.event_governance_id,
                "position_governance_id": entry.position_governance_id,
                "instrument_symbol": entry.instrument_symbol,
                "status": str(entry.status),
                "system_received_at": (
                    None
                    if entry.system_received_at is None
                    else entry.system_received_at.isoformat()
                ),
                "attested_by": entry.attested_by,
            }
            for entry in report.entries
        ],
        "limitations": list(report.limitations),
    }
