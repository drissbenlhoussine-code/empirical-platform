"""MILESTONE-082 rendering. Text and JSON carry the same facts.

Neither renderer may introduce a field the domain report does not carry. In
particular there is no future-tail count and no placeholder entry for an event
the view cannot see -- see Owner review finding 1.

The heading says RECEIPT-LABEL-CUTOFF VIEW, not "snapshot": Owner review finding
5 established that repeated evaluation at the same cutoff can legitimately
return more, because a label can be backdated.

EVERY RENDERED FIELD COMES FROM THE RECEIPT ROW. No position, no instrument, no
payload of any kind -- owner review finding 7 proved that resolving those from
the current M076 row let a post-attestation UPDATE change the artifact while the
receipt stood still.

NEITHER RENDERER ASSERTS SANCTIONED-PATH PROVENANCE FOR ANY INDIVIDUAL ROW
(owner review finding 13). The text renderer previously said each entry's label
was "applied on the sanctioned attest path" -- a claim it cannot authenticate. A
direct SQL receipt for a genuinely prior-committed event is deliberately
accepted, and it carried FORGED-BY-DIRECT-SQL and FORGED-VERSION straight into
that sentence. JSON never made the assertion, so the claimed text/JSON parity was
incomplete as well. Both now say the same thing: provenance is unauthenticated.
"""

from __future__ import annotations

from typing import Any

from empirical_platform.decision_candidate.operator_event_receipt import (
    ATTESTED_EVIDENCE_BANNER,
    AttestedEvidenceReport,
)

__all__ = ["render_attested_evidence_report_json", "render_attested_evidence_report_text"]


def render_attested_evidence_report_text(report: AttestedEvidenceReport) -> str:
    lines: list[str] = ["RECEIPT-LABEL-CUTOFF VIEW OF SYSTEM-RECEIPT-ATTESTED EVIDENCE", ""]
    for sentence in ATTESTED_EVIDENCE_BANNER.split(". "):
        stripped = sentence.strip().rstrip(".")
        if stripped:
            lines.append(f"  {stripped}")
    lines.append("")
    lines.append(f"  receipt_label_cutoff:  {report.receipt_label_cutoff.isoformat()}")
    lines.append(
        f"  {report.attested_count} event(s) carry a receipt labelled at or before this cutoff"
    )
    lines.append("  this view cannot say how many events it excluded, and does not guess")
    lines.append("  re-evaluating this same cutoff later can return MORE: a label can be backdated")
    for entry in report.entries:
        lines.append(f"    receipt={entry.receipt_governance_id} event={entry.event_governance_id}")
        lines.append(
            f"      system_received_at={entry.system_received_at.isoformat()} "
            f"attested_by={entry.attested_by} attester_version={entry.attester_version} "
            "(UNAUTHENTICATED PROVENANCE: nothing here proves this row came "
            "through attest(); direct SQL may supply any allowed value)"
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
                "receipt_governance_id": entry.receipt_governance_id,
                "event_governance_id": entry.event_governance_id,
                "system_received_at": entry.system_received_at.isoformat(),
                "attested_by": entry.attested_by,
                "attester_version": entry.attester_version,
            }
            for entry in report.entries
        ],
        "limitations": list(report.limitations),
    }
