"""MILESTONE-078 rendering. Both formats consume one derived object, so they
cannot semantically diverge."""

from __future__ import annotations

from empirical_platform.decision_candidate.research_decision_follow_through import (
    FOLLOW_THROUGH_BANNER,
    FollowThroughOutcome,
    ResearchDecisionFollowThrough,
)

__all__ = [
    "render_follow_through_json",
    "render_follow_through_text",
]


def render_follow_through_json(
    audit: ResearchDecisionFollowThrough,
) -> dict[str, object]:
    return {
        "banner": FOLLOW_THROUGH_BANNER,
        "outcome": audit.outcome.value,
        "unassessable_reason": (
            None if audit.unassessable_reason is None else audit.unassessable_reason.value
        ),
        "session_governance_id": audit.session_governance_id,
        "as_of": audit.as_of.isoformat(),
        "approved_plan_count": audit.approved_plan_count,
        "with_open_asserted_position": audit.with_open_asserted_position,
        "with_closed_asserted_position": audit.with_closed_asserted_position,
        "with_no_asserted_position_recorded": audit.with_no_asserted_position_recorded,
        "excluded_future_event_count": audit.excluded_future_event_count,
        "entries": [
            {
                "rank": entry.rank,
                "instrument_symbol": entry.instrument_symbol,
                "position_plan_governance_id": entry.position_plan_governance_id,
                "status": entry.status.value,
                "open_position_count": entry.open_position_count,
                "closed_position_count": entry.closed_position_count,
                "position_governance_ids": list(entry.position_governance_ids),
            }
            for entry in audit.entries
        ],
        "unlinked_open_positions": [
            {
                "position_governance_id": position.position_governance_id,
                "instrument_symbol": position.instrument_symbol,
                "open_quantity": position.open_quantity,
                "reason": position.reason.value,
                "cited_plan_governance_id": position.cited_plan_governance_id,
            }
            for position in audit.unlinked_open_positions
        ],
        "limitations": list(audit.limitations),
    }


def render_follow_through_text(audit: ResearchDecisionFollowThrough) -> str:
    lines: list[str] = ["RESEARCH DECISION FOLLOW-THROUGH", ""]
    lines.extend(f"  {part}" for part in FOLLOW_THROUGH_BANNER.split(". ") if part)
    lines.append("")
    lines.append(f"  session: {audit.session_governance_id}")
    lines.append(f"  as_of:   {audit.as_of.isoformat()}")
    lines.append(f"  outcome: {audit.outcome}")
    if audit.unassessable_reason is not None:
        lines.append(f"  not assessable: {audit.unassessable_reason}")

    if audit.outcome is not FollowThroughOutcome.NOT_ASSESSABLE:
        lines.append(
            f"  {audit.approved_plan_count} approved plan(s): "
            f"{audit.with_open_asserted_position} with an open asserted position, "
            f"{audit.with_closed_asserted_position} with a closed one, "
            f"{audit.with_no_asserted_position_recorded} with nothing recorded"
        )
        for entry in audit.entries:
            rank = "-" if entry.rank is None else str(entry.rank)
            cited = (
                f" positions={','.join(entry.position_governance_ids)}"
                if entry.position_governance_ids
                else ""
            )
            lines.append(
                f"    [{rank}] {entry.instrument_symbol} "
                f"plan={entry.position_plan_governance_id} {entry.status}"
                f" (open={entry.open_position_count} closed={entry.closed_position_count})"
                f"{cited}"
            )
        if audit.unlinked_open_positions:
            lines.append("  open asserted positions this session's plans do not account for:")
            for position in audit.unlinked_open_positions:
                cited = position.cited_plan_governance_id or "-"
                lines.append(
                    f"    {position.instrument_symbol} "
                    f"position={position.position_governance_id} "
                    f"qty={position.open_quantity} {position.reason} cites={cited}"
                )
        else:
            lines.append(
                "  every open asserted position is accounted for by a plan of this session"
            )
    for limitation in audit.limitations:
        lines.append(f"  limitation: {limitation}")
    lines.append("")
    return "\n".join(lines)
