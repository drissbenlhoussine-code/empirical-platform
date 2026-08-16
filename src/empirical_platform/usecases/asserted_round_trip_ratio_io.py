"""MILESTONE-081 rendering. Text and JSON carry the same facts.

DESIGN REVIEW D-F04: no monetary value is rendered anywhere, at any level.
DESIGN REVIEW D-H14: the ratio is never rendered as a percentage with a `%`
sign, because a percentage reads as a return, which this is not.
DESIGN REVIEW D-F09 / section 21: entries are ordered by persisted identity,
never by value -- ordering by outcome would itself be a ranking claim.
"""

from __future__ import annotations

from typing import Any

from empirical_platform.decision_candidate.operator_asserted_round_trip_ratio import (
    ASSERTED_RATIO_BANNER,
    AssertedRoundTripRatioReport,
    PositionRoundTripRatioEntry,
)

__all__ = [
    "render_round_trip_ratio_report_json",
    "render_round_trip_ratio_report_text",
]


def _ordered(
    entries: tuple[PositionRoundTripRatioEntry, ...],
) -> tuple[PositionRoundTripRatioEntry, ...]:
    return tuple(sorted(entries, key=lambda e: (e.instrument_symbol, e.position_governance_id)))


def _ratio_phrase(entry: PositionRoundTripRatioEntry) -> str:
    """State the coverage on the line the number appears on.

    M080's R01 lesson: the number is what gets quoted, so its caveat has to be
    on the same line, not elsewhere in the report.
    """
    if entry.ratio_exact is None:
        return f"NO RATIO ({entry.ratio_absence_reason})"

    coverage = (
        f"on all {entry.exited_quantity} exited unit(s)"
        if entry.still_open_quantity == 0 and entry.unaccounted_quantity == 0
        else f"on the {entry.exited_quantity} exited unit(s) ONLY"
    )
    approximation = (
        f"{entry.ratio_decimal_approx}"
        if entry.ratio_approximation_is_exact
        else f"{entry.ratio_decimal_approx} (APPROXIMATE)"
    )
    return (
        f"ASSERTED ROUND-TRIP RESULT RATIO {coverage}, dimensionless, "
        f"exact={entry.ratio_exact} approx={approximation}"
    )


def render_round_trip_ratio_report_text(report: AssertedRoundTripRatioReport) -> str:
    lines: list[str] = ["OPERATOR-ASSERTED ROUND-TRIP RESULT RATIO", ""]
    for sentence in ASSERTED_RATIO_BANNER.split(". "):
        stripped = sentence.strip().rstrip(".")
        if stripped:
            lines.append(f"  {stripped}")
    lines.append("")
    lines.append(f"  effective_as_of: {report.effective_as_of.isoformat()}")
    lines.append(f"  knowledge_as_of: {report.knowledge_as_of.isoformat()}")
    lines.append(f"  outcome:         {report.outcome}")

    if report.unassessable_reason is not None:
        lines.append(f"  reason:          {report.unassessable_reason}")
    else:
        lines.append(
            f"  {report.visible_event_count} of {report.known_event_count} assertion(s) "
            f"recorded by the knowledge cutoff are visible; "
            f"{report.excluded_by_effective_cutoff} excluded as effective after the "
            f"effective cutoff. Assertions recorded after the knowledge cutoff are "
            f"excluded and are deliberately not counted"
        )
        lines.append(
            f"  {report.ratio_available_count} position(s) with a ratio, "
            f"{report.ratio_absent_count} without, "
            f"{report.unreconciled_count} unreconciled, "
            f"{report.unresolved_count} unresolved at this knowledge cutoff"
        )
        lines.append(
            "  economic components NOT separately represented (this is NOT a "
            "complete economic outcome): " + ", ".join(report.unrepresented_economic_components)
        )
        for entry in _ordered(report.entries):
            lines.append(
                f"    {entry.instrument_symbol} position={entry.position_governance_id} "
                f"{entry.status}"
            )
            lines.append(
                f"      opened={entry.opened_quantity} exited={entry.exited_quantity} "
                f"still_open={entry.still_open_quantity} "
                f"unaccounted={entry.unaccounted_quantity}"
            )
            lines.append(f"      {_ratio_phrase(entry)}")

    for limitation in report.limitations:
        lines.append(f"  {limitation}")
    return "\n".join(lines)


def render_round_trip_ratio_report_json(
    report: AssertedRoundTripRatioReport,
) -> dict[str, Any]:
    return {
        "banner": ASSERTED_RATIO_BANNER,
        "outcome": str(report.outcome),
        "unassessable_reason": (
            None if report.unassessable_reason is None else str(report.unassessable_reason)
        ),
        "effective_as_of": report.effective_as_of.isoformat(),
        "knowledge_as_of": report.knowledge_as_of.isoformat(),
        "known_event_count": report.known_event_count,
        "visible_event_count": report.visible_event_count,
        "excluded_by_effective_cutoff": report.excluded_by_effective_cutoff,
        "ratio_available_count": report.ratio_available_count,
        "ratio_absent_count": report.ratio_absent_count,
        "unreconciled_count": report.unreconciled_count,
        "unresolved_count": report.unresolved_count,
        "unrepresented_economic_components": list(report.unrepresented_economic_components),
        "entries": [
            {
                "position_governance_id": entry.position_governance_id,
                "instrument_symbol": entry.instrument_symbol,
                "status": str(entry.status),
                "cited_position_plan_governance_id": entry.cited_position_plan_governance_id,
                "opened_quantity": entry.opened_quantity,
                "exited_quantity": entry.exited_quantity,
                "still_open_quantity": entry.still_open_quantity,
                "unaccounted_quantity": entry.unaccounted_quantity,
                "asserted_round_trip_result_to_entry_cost_ratio_exact": entry.ratio_exact,
                "asserted_round_trip_result_to_entry_cost_ratio_decimal_approx": (
                    entry.ratio_decimal_approx
                ),
                "ratio_numerator": entry.ratio_numerator,
                "ratio_denominator": entry.ratio_denominator,
                "ratio_approximation_is_exact": entry.ratio_approximation_is_exact,
                "ratio_absence_reason": (
                    None if entry.ratio_absence_reason is None else str(entry.ratio_absence_reason)
                ),
            }
            for entry in _ordered(report.entries)
        ],
        "limitations": list(report.limitations),
    }
