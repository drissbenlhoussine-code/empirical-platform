"""MILESTONE-079 rendering. Both formats consume one derived object."""

from __future__ import annotations

from empirical_platform.decision_candidate.operator_evidence_availability import (
    EVIDENCE_AVAILABILITY_BANNER,
    EvidenceSnapshotOutcome,
    OperatorEvidenceSnapshot,
)

__all__ = [
    "render_evidence_snapshot_json",
    "render_evidence_snapshot_text",
]


def render_evidence_snapshot_json(
    snapshot: OperatorEvidenceSnapshot,
) -> dict[str, object]:
    return {
        "banner": EVIDENCE_AVAILABILITY_BANNER,
        "outcome": snapshot.outcome.value,
        "unassessable_reason": (
            None if snapshot.unassessable_reason is None else snapshot.unassessable_reason.value
        ),
        "effective_as_of": snapshot.effective_as_of.isoformat(),
        "knowledge_as_of": snapshot.knowledge_as_of.isoformat(),
        "known_event_count": snapshot.known_event_count,
        "visible_event_count": snapshot.visible_event_count,
        "excluded_by_effective_cutoff": snapshot.excluded_by_effective_cutoff,
        "known_open_count": snapshot.known_open_count,
        "known_closed_count": snapshot.known_closed_count,
        "unresolved_position_count": snapshot.unresolved_position_count,
        "entries": [
            {
                "position_governance_id": entry.position_governance_id,
                "instrument_symbol": entry.instrument_symbol,
                "status": entry.status.value,
                "rejection_reason": entry.rejection_reason,
                "visible_event_count": entry.visible_event_count,
                "open_quantity": (None if entry.position is None else entry.position.open_quantity),
                "asserted_entry_price": (
                    None if entry.position is None else entry.position.asserted_entry_price
                ),
                "asserted_open_notional": (
                    None if entry.position is None else entry.position.asserted_open_notional
                ),
                "opened_at": (
                    None if entry.position is None else entry.position.opened_at.isoformat()
                ),
            }
            for entry in snapshot.entries
        ],
        "limitations": list(snapshot.limitations),
    }


def render_evidence_snapshot_text(snapshot: OperatorEvidenceSnapshot) -> str:
    lines: list[str] = ["OPERATOR EVIDENCE AVAILABILITY SNAPSHOT", ""]
    lines.extend(f"  {part}" for part in EVIDENCE_AVAILABILITY_BANNER.split(". ") if part)
    lines.append("")
    lines.append(f"  effective_as_of: {snapshot.effective_as_of.isoformat()}")
    lines.append(f"  knowledge_as_of: {snapshot.knowledge_as_of.isoformat()}")
    lines.append(f"  outcome:         {snapshot.outcome}")
    if snapshot.unassessable_reason is not None:
        lines.append(f"  not assessable:  {snapshot.unassessable_reason}")

    if snapshot.outcome is not EvidenceSnapshotOutcome.NOT_ASSESSABLE:
        lines.append(
            f"  {snapshot.visible_event_count} of {snapshot.known_event_count} assertion(s) "
            f"recorded by the knowledge cutoff are visible; "
            f"{snapshot.excluded_by_effective_cutoff} excluded as effective after the "
            "effective cutoff. Assertions recorded after the knowledge cutoff are excluded "
            "and are deliberately not counted"
        )
        lines.append(
            f"  {snapshot.known_open_count} known open, "
            f"{snapshot.known_closed_count} known closed, "
            f"{snapshot.unresolved_position_count} unresolved at this knowledge cutoff"
        )
        for entry in snapshot.entries:
            if entry.position is None:
                lines.append(
                    f"    {entry.instrument_symbol} position={entry.position_governance_id} "
                    f"{entry.status} ({entry.rejection_reason}) "
                    f"visible_events={entry.visible_event_count}"
                )
            else:
                lines.append(
                    f"    {entry.instrument_symbol} position={entry.position_governance_id} "
                    f"{entry.status} qty={entry.position.open_quantity} "
                    f"asserted_entry={entry.position.asserted_entry_price} "
                    f"asserted_notional={entry.position.asserted_open_notional}"
                )
    for limitation in snapshot.limitations:
        lines.append(f"  limitation: {limitation}")
    lines.append("")
    return "\n".join(lines)
