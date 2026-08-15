"""MILESTONE-076 -- text and JSON rendering of derived operator position state.

Both renderings derive from the same object, so they cannot disagree.
"""

from __future__ import annotations

from empirical_platform.decision_candidate.operator_position_ledger import (
    OPERATOR_LEDGER_BANNER,
    DerivedPosition,
    DerivedPositionState,
)

__all__ = [
    "OPERATOR_LEDGER_BANNER",
    "render_operator_position_state_json",
    "render_operator_position_state_text",
]


def _position_json(position: DerivedPosition) -> dict[str, object]:
    return {
        "position_governance_id": position.position_governance_id,
        "instrument_symbol": position.instrument_symbol,
        "open_quantity": position.open_quantity,
        "is_open": position.is_open,
        "asserted_entry_price": position.asserted_entry_price,
        "asserted_open_notional": position.asserted_open_notional,
        "opened_at": position.opened_at.isoformat(),
        "last_event_at": position.last_event_at.isoformat(),
        "event_count": position.event_count,
    }


def render_operator_position_state_json(state: DerivedPositionState) -> dict[str, object]:
    return {
        "honesty_banner": OPERATOR_LEDGER_BANNER,
        "as_of": state.as_of.isoformat(),
        "open_positions": [_position_json(p) for p in state.open_positions],
        "closed_positions": [_position_json(p) for p in state.closed_positions],
        "total_open_quantity": state.total_open_quantity,
        "total_asserted_open_notional": state.total_asserted_open_notional,
        "considered_event_count": state.considered_event_count,
        "excluded_future_event_count": state.excluded_future_event_count,
        "limitations": list(state.limitations),
    }


def render_operator_position_state_text(state: DerivedPositionState) -> str:
    lines = ["OPERATOR-ASSERTED POSITION STATE", "=" * 32]
    lines.extend(f"  {clause}" for clause in OPERATOR_LEDGER_BANNER.split("; ") if clause)
    lines.append("")
    lines.append(f"  as_of: {state.as_of.isoformat()} (inclusive)")
    if state.open_positions:
        lines.append(f"  open positions ({len(state.open_positions)}):")
        for p in state.open_positions:
            lines.append(
                f"    {p.instrument_symbol} [{p.position_governance_id}] "
                f"qty={p.open_quantity} asserted_entry={p.asserted_entry_price} "
                f"asserted_notional={p.asserted_open_notional}"
            )
        lines.append(
            f"  total asserted open quantity {state.total_open_quantity}, "
            f"asserted notional {state.total_asserted_open_notional}"
        )
    else:
        lines.append(
            "  no open positions asserted as of this timestamp -- this reflects what the "
            "operator recorded, not a verified account state"
        )
    if state.closed_positions:
        lines.append(f"  closed positions ({len(state.closed_positions)}):")
        for p in state.closed_positions:
            lines.append(
                f"    {p.instrument_symbol} [{p.position_governance_id}] "
                f"closed after {p.event_count} event(s)"
            )
    for limitation in state.limitations:
        lines.append(f"  limitation: {limitation}")
    return "\n".join(lines)
