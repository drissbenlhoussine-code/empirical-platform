"""MILESTONE-080 rendering. Both formats consume one derived object."""

from __future__ import annotations

from empirical_platform.decision_candidate.operator_asserted_round_trip import (
    ASSERTED_ROUND_TRIP_BANNER,
    CONTEXT_DEPENDENT_COMPONENTS,
    NOT_SEPARATELY_ATTRIBUTABLE_EXECUTION_COMPONENTS,
    UNREPRESENTED_CASHFLOW_COMPONENTS,
    AssertedRoundTripReport,
    RoundTripOutcome,
    RoundTripStatus,
)

__all__ = [
    "render_round_trip_report_json",
    "render_round_trip_report_text",
]


def render_round_trip_report_json(report: AssertedRoundTripReport) -> dict[str, object]:
    return {
        "banner": ASSERTED_ROUND_TRIP_BANNER,
        "outcome": report.outcome.value,
        "unassessable_reason": (
            None if report.unassessable_reason is None else report.unassessable_reason.value
        ),
        "effective_as_of": report.effective_as_of.isoformat(),
        "knowledge_as_of": report.knowledge_as_of.isoformat(),
        "known_event_count": report.known_event_count,
        "visible_event_count": report.visible_event_count,
        "excluded_by_effective_cutoff": report.excluded_by_effective_cutoff,
        "no_exit_count": report.no_exit_count,
        "partial_exit_count": report.partial_exit_count,
        "fully_exited_count": report.fully_exited_count,
        "unreconciled_count": report.unreconciled_count,
        "unresolved_count": report.unresolved_count,
        "unrepresented_economic_components": list(report.unrepresented_economic_components),
        "entries": [
            {
                "position_governance_id": entry.position_governance_id,
                "instrument_symbol": entry.instrument_symbol,
                "status": entry.status.value,
                "cited_position_plan_governance_id": entry.cited_position_plan_governance_id,
                "opened_quantity": entry.opened_quantity,
                "exited_quantity": entry.exited_quantity,
                "still_open_quantity": entry.still_open_quantity,
                "unaccounted_quantity": entry.unaccounted_quantity,
                "asserted_entry_price": entry.asserted_entry_price,
                "asserted_entry_cost_for_exited_quantity": (
                    entry.asserted_entry_cost_for_exited_quantity
                ),
                "asserted_exit_consideration": entry.asserted_exit_consideration,
                "asserted_round_trip_result": entry.asserted_round_trip_result,
                "exit_event_count": entry.exit_event_count,
                "visible_event_count": entry.visible_event_count,
                "rejection_reason": entry.rejection_reason,
            }
            for entry in report.entries
        ],
        "limitations": list(report.limitations),
    }


def render_round_trip_report_text(report: AssertedRoundTripReport) -> str:
    lines: list[str] = ["OPERATOR-ASSERTED ROUND-TRIP RESULT", ""]
    lines.extend(f"  {part}" for part in ASSERTED_ROUND_TRIP_BANNER.split(". ") if part)
    lines.append("")
    lines.append(f"  effective_as_of: {report.effective_as_of.isoformat()}")
    lines.append(f"  knowledge_as_of: {report.knowledge_as_of.isoformat()}")
    lines.append(f"  outcome:         {report.outcome}")
    if report.unassessable_reason is not None:
        lines.append(f"  not assessable:  {report.unassessable_reason}")

    if report.outcome is not RoundTripOutcome.NOT_ASSESSABLE:
        lines.append(
            f"  {report.visible_event_count} of {report.known_event_count} assertion(s) "
            f"recorded by the knowledge cutoff are visible; "
            f"{report.excluded_by_effective_cutoff} excluded as effective after the "
            "effective cutoff. Assertions recorded after the knowledge cutoff are "
            "excluded and are deliberately not counted"
        )
        lines.append(
            f"  {report.fully_exited_count} fully exited, "
            f"{report.partial_exit_count} partly exited, "
            f"{report.no_exit_count} with no exit asserted, "
            f"{report.unreconciled_count} unreconciled, "
            f"{report.unresolved_count} unresolved at this knowledge cutoff"
        )
        lines.append(
            "  economic components NOT separately represented (this is NOT a complete "
            "economic outcome): " + ", ".join(report.unrepresented_economic_components)
        )
        lines.append(
            "  the direction of the total effect is NOT generally knowable: "
            + ", ".join(UNREPRESENTED_CASHFLOW_COMPONENTS)
            + " would normally reduce a raw result, while "
            + ", ".join(CONTEXT_DEPENDENT_COMPONENTS)
            + " can move the real outcome either way"
        )
        lines.append(
            "  "
            + ", ".join(NOT_SEPARATELY_ATTRIBUTABLE_EXECUTION_COMPONENTS)
            + " are NOT claimed to be excluded: the prices are the operator's own, so "
            "such effects may already be embedded in them and are not separately "
            "attributable from this data"
        )
        for entry in report.entries:
            head = (
                f"    {entry.instrument_symbol} position={entry.position_governance_id} "
                f"{entry.status}"
            )
            if entry.cited_position_plan_governance_id is not None:
                head += f" cites_plan={entry.cited_position_plan_governance_id}"
            lines.append(head)
            if entry.rejection_reason is not None:
                lines.append(
                    f"      no arithmetic attempted ({entry.rejection_reason}); "
                    f"visible_events={entry.visible_event_count}"
                )
                continue
            lines.append(
                f"      opened={entry.opened_quantity} exited={entry.exited_quantity} "
                f"still_open={entry.still_open_quantity} "
                f"unaccounted={entry.unaccounted_quantity}"
            )
            if entry.asserted_round_trip_result is None:
                lines.append(
                    "      no exit asserted yet, so no arithmetic is emitted "
                    "(deliberately not zero)"
                )
                continue
            lines.append(
                f"      asserted entry price={entry.asserted_entry_price} "
                f"entry cost for exited={entry.asserted_entry_cost_for_exited_quantity} "
                f"exit consideration={entry.asserted_exit_consideration}"
            )
            # IMPLEMENTATION REVIEW R01. The result line must state the
            # quantity it covers AT THE POINT THE NUMBER IS READ. A report-level
            # limitation is not enough: the number is what gets quoted, and an
            # identical line for a fully-exited position, a mostly-open one and
            # one missing exits let a partial figure read as a whole result.
            if entry.status is RoundTripStatus.EXIT_QUANTITY_UNRECONCILED:
                coverage = (
                    f"on ONLY the {entry.exited_quantity} exited unit(s) visible here; "
                    f"{entry.unaccounted_quantity} of the {entry.opened_quantity} opened "
                    "are unaccounted for at this knowledge cutoff, so this is NOT the "
                    "whole position's result"
                )
            elif entry.status is RoundTripStatus.PARTIAL_EXIT_ASSERTED:
                coverage = (
                    f"on the {entry.exited_quantity} exited unit(s) ONLY; "
                    f"{entry.still_open_quantity} still open and NOT covered"
                )
            else:
                coverage = f"on all {entry.exited_quantity} exited unit(s)"
            lines.append(
                f"      ASSERTED ROUND-TRIP RESULT {coverage}, in unspecified asserted "
                f"price units, with the economic components above not separately "
                f"represented: {entry.asserted_round_trip_result}"
            )
    for limitation in report.limitations:
        lines.append(f"  limitation: {limitation}")
    lines.append("")
    return "\n".join(lines)
