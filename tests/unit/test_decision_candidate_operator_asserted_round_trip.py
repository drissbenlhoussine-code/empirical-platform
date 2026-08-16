"""MILESTONE-080 unit tests.

Written from the epistemic claims in
`MILESTONE_080_OPERATOR_ASSERTED_ROUND_TRIP_RESULT_SCOPE_AND_DESIGN.md`, not
from the implementation's shape.

The timeline every temporal test is built on:

    D1  effective, early
    D2  effective, later
    D3  effective, latest
    R_LATE  recorded well after the cutoffs under test
"""

from __future__ import annotations

import dataclasses
import json
from datetime import UTC, datetime, timedelta, timezone
from decimal import ROUND_FLOOR, ROUND_UP, Decimal, localcontext

import pytest

from empirical_platform.decision_candidate.operator_asserted_round_trip import (
    ASSERTED_PRICE_DENOMINATION_LIMITATION,
    ASSERTED_ROUND_TRIP_BANNER,
    CONTEXT_DEPENDENT_COMPONENTS,
    NOT_SEPARATELY_ATTRIBUTABLE_EXECUTION_COMPONENTS,
    UNREPRESENTED_CASHFLOW_COMPONENTS,
    UNREPRESENTED_ECONOMIC_COMPONENTS,
    AssertedRoundTripReport,
    RoundTripOutcome,
    RoundTripStatus,
    RoundTripUnassessableReason,
    build_asserted_round_trip_report,
)
from empirical_platform.decision_candidate.operator_position_ledger import (
    OperatorAssertedPositionEvent,
    OperatorPositionEventKind,
    validate_appended_event,
)
from empirical_platform.usecases.asserted_round_trip_io import (
    render_round_trip_report_json,
    render_round_trip_report_text,
)

T0 = datetime(2026, 3, 1, tzinfo=UTC)
D1 = T0 + timedelta(days=1)
D2 = T0 + timedelta(days=2)
D3 = T0 + timedelta(days=3)
R_LATE = T0 + timedelta(days=40)
LATER = T0 + timedelta(days=90)


def event(
    *,
    gid: str,
    pos: str = "POS-1",
    symbol: str = "AAPL",
    kind: OperatorPositionEventKind = OperatorPositionEventKind.OPENED,
    quantity: int = 10,
    price: str = "100",
    effective: datetime,
    recorded: datetime | None = None,
    plan: str | None = None,
) -> OperatorAssertedPositionEvent:
    return OperatorAssertedPositionEvent(
        governance_id=gid,
        runtime_id=f"rt-{gid}",
        position_governance_id=pos,
        instrument_symbol=symbol,
        kind=kind,
        quantity=quantity,
        asserted_price=Decimal(price),
        event_timestamp=effective,
        recorded_at=recorded or effective,
        source_position_plan_governance_id=plan,
    )


def report(
    *,
    events: tuple[OperatorAssertedPositionEvent, ...] = (),
    effective: datetime = LATER,
    knowledge: datetime = LATER,
    ledger_available: bool = True,
) -> AssertedRoundTripReport:
    return build_asserted_round_trip_report(
        events=events,
        effective_as_of=effective,
        knowledge_as_of=knowledge,
        ledger_available=ledger_available,
    )


def closed_after(
    existing: tuple[OperatorAssertedPositionEvent, ...],
    *,
    gid: str,
    price: str,
    effective: datetime,
    recorded: datetime | None = None,
    pos: str = "POS-1",
    symbol: str = "AAPL",
) -> OperatorAssertedPositionEvent:
    """Build a CLOSED event whose quantity M076 derives, exactly as persistence does."""
    candidate = event(
        gid=gid,
        pos=pos,
        symbol=symbol,
        kind=OperatorPositionEventKind.CLOSED,
        quantity=0,
        price=price,
        effective=effective,
        recorded=recorded,
    )
    derived = validate_appended_event(existing=existing, candidate=candidate)
    return dataclasses.replace(candidate, quantity=derived)


# --------------------------------------------------------------------------
# The arithmetic itself
# --------------------------------------------------------------------------


def test_the_mandated_adversarial_position_computes_exactly() -> None:
    """OPENED 10@100, REDUCED 4@110, CLOSED 6@90 -> 980 - 1000 = -20."""
    opened = event(gid="O", effective=D1)
    reduced = event(
        gid="R", kind=OperatorPositionEventKind.REDUCED, quantity=4, price="110", effective=D2
    )
    closed = closed_after((opened, reduced), gid="C", price="90", effective=D3)
    entry = report(events=(opened, reduced, closed)).entries[0]

    assert entry.status is RoundTripStatus.FULLY_EXITED_ASSERTED
    assert (entry.opened_quantity, entry.exited_quantity, entry.still_open_quantity) == (10, 10, 0)
    assert entry.unaccounted_quantity == 0
    assert entry.asserted_entry_cost_for_exited_quantity == "1000"
    assert entry.asserted_exit_consideration == "980"
    assert entry.asserted_round_trip_result == "-20"


def test_an_asserted_gain_is_positive() -> None:
    opened = event(gid="O", effective=D1, price="100")
    closed = closed_after((opened,), gid="C", price="130", effective=D2)
    entry = report(events=(opened, closed)).entries[0]
    assert entry.asserted_round_trip_result == "300"


def test_an_asserted_loss_is_negative() -> None:
    opened = event(gid="O", effective=D1, price="100")
    closed = closed_after((opened,), gid="C", price="70", effective=D2)
    assert report(events=(opened, closed)).entries[0].asserted_round_trip_result == "-300"


def test_exact_break_even_is_zero_not_negative_zero() -> None:
    opened = event(gid="O", effective=D1, price="100")
    closed = closed_after((opened,), gid="C", price="100", effective=D2)
    result = report(events=(opened, closed)).entries[0].asserted_round_trip_result
    assert result == "0"
    assert not str(result).startswith("-")


def test_several_reductions_each_contribute_their_own_price() -> None:
    opened = event(gid="O", effective=D1, quantity=10, price="100")
    r1 = event(
        gid="R1", kind=OperatorPositionEventKind.REDUCED, quantity=3, price="120", effective=D2
    )
    r2 = event(
        gid="R2", kind=OperatorPositionEventKind.REDUCED, quantity=2, price="80", effective=D3
    )
    closed = closed_after((opened, r1, r2), gid="C", price="110", effective=D3 + timedelta(days=1))
    entry = report(events=(opened, r1, r2, closed)).entries[0]
    # 3*120 + 2*80 + 5*110 = 360 + 160 + 550 = 1070 ; cost 10*100 = 1000
    assert entry.asserted_exit_consideration == "1070"
    assert entry.asserted_round_trip_result == "70"


def test_a_reduction_landing_exactly_on_zero_closes_without_a_closed_event() -> None:
    """Proven against frozen M076: quantity 0 closes the position with no CLOSED event."""
    opened = event(gid="O", effective=D1, quantity=10, price="100")
    reduced = event(
        gid="R", kind=OperatorPositionEventKind.REDUCED, quantity=10, price="115", effective=D2
    )
    entry = report(events=(opened, reduced)).entries[0]
    assert entry.status is RoundTripStatus.FULLY_EXITED_ASSERTED
    assert entry.exit_event_count == 1
    assert entry.asserted_round_trip_result == "150"


# --------------------------------------------------------------------------
# Open and partial positions
# --------------------------------------------------------------------------


def test_an_opened_only_position_emits_no_arithmetic_at_all() -> None:
    """Design review E16: a zero would read as break-even."""
    entry = report(events=(event(gid="O", effective=D1),)).entries[0]
    assert entry.status is RoundTripStatus.NO_EXIT_ASSERTED_YET
    assert entry.asserted_round_trip_result is None
    assert entry.asserted_exit_consideration is None
    assert entry.asserted_entry_cost_for_exited_quantity is None


def test_a_partial_exit_covers_only_the_exited_quantity() -> None:
    opened = event(gid="O", effective=D1, quantity=10, price="100")
    reduced = event(
        gid="R", kind=OperatorPositionEventKind.REDUCED, quantity=4, price="130", effective=D2
    )
    entry = report(events=(opened, reduced)).entries[0]
    assert entry.status is RoundTripStatus.PARTIAL_EXIT_ASSERTED
    assert entry.exited_quantity == 4
    assert entry.still_open_quantity == 6
    # 4*130 - 4*100 = 120. NOT 10*130 - 10*100 = 300.
    assert entry.asserted_round_trip_result == "120"


def test_a_partial_result_is_never_extrapolated_to_the_open_remainder() -> None:
    opened = event(gid="O", effective=D1, quantity=10, price="100")
    reduced = event(
        gid="R", kind=OperatorPositionEventKind.REDUCED, quantity=1, price="200", effective=D2
    )
    entry = report(events=(opened, reduced)).entries[0]
    assert entry.asserted_round_trip_result == "100"
    assert entry.asserted_round_trip_result != "1000"


def test_no_unrealized_value_is_computed_for_an_open_position() -> None:
    entry = report(events=(event(gid="O", effective=D1),)).entries[0]
    fields = {f.name for f in dataclasses.fields(entry)}
    for banned in ("unrealized", "market_value", "current_value", "mark_to_market"):
        assert not any(banned in name for name in fields)


# --------------------------------------------------------------------------
# The derived-CLOSED-quantity hazard (design review T07)
# --------------------------------------------------------------------------


def _late_reduction_ledger() -> tuple[OperatorAssertedPositionEvent, ...]:
    """OPENED 10 (rec D1); REDUCED 4 (rec LATE); CLOSED 6 (rec D3).

    M076 derives the CLOSED quantity as 6 at append time from the FULL history.
    At K = D3 the visible prefix folds coherently, yet accounts for 6 of 10.
    """
    opened = event(gid="O", effective=D1, recorded=D1, quantity=10, price="100")
    reduced = event(
        gid="R",
        kind=OperatorPositionEventKind.REDUCED,
        quantity=4,
        price="110",
        effective=D2,
        recorded=R_LATE,
    )
    closed = closed_after((opened, reduced), gid="C", price="90", effective=D3, recorded=D3)
    return (opened, reduced, closed)


def test_a_coherent_fold_with_missing_exits_is_reported_as_unreconciled() -> None:
    """Design review T07, the most important finding of that review."""
    entry = report(events=_late_reduction_ledger(), effective=LATER, knowledge=D3).entries[0]
    assert entry.status is RoundTripStatus.EXIT_QUANTITY_UNRECONCILED
    assert entry.opened_quantity == 10
    assert entry.exited_quantity == 6
    assert entry.still_open_quantity == 0
    assert entry.unaccounted_quantity == 4


def test_the_unreconciled_result_covers_only_the_visible_exits() -> None:
    entry = report(events=_late_reduction_ledger(), effective=LATER, knowledge=D3).entries[0]
    # 6*90 - 6*100 = -60, NOT the full-history 980 - 1000 = -20.
    assert entry.asserted_round_trip_result == "-60"


def test_the_unreconciled_case_is_not_labelled_fully_exited() -> None:
    entry = report(events=_late_reduction_ledger(), effective=LATER, knowledge=D3).entries[0]
    assert entry.status is not RoundTripStatus.FULLY_EXITED_ASSERTED


def test_the_unreconciled_case_carries_an_explicit_limitation() -> None:
    result = report(events=_late_reduction_ledger(), effective=LATER, knowledge=D3)
    assert any("do not account for the quantity opened" in line for line in result.limitations)


def test_once_the_late_reduction_is_recorded_the_position_reconciles() -> None:
    result = report(events=_late_reduction_ledger(), effective=LATER, knowledge=LATER)
    entry = result.entries[0]
    assert entry.status is RoundTripStatus.FULLY_EXITED_ASSERTED
    assert entry.unaccounted_quantity == 0
    assert entry.asserted_round_trip_result == "-20"


def test_one_unreconciled_position_does_not_void_the_whole_report() -> None:
    healthy = event(gid="H", pos="POS-2", symbol="TSLA", effective=D1, recorded=D1)
    result = report(events=(*_late_reduction_ledger(), healthy), effective=LATER, knowledge=D3)
    assert result.outcome is RoundTripOutcome.ROUND_TRIP_REPORT_AVAILABLE
    assert result.unreconciled_count == 1
    assert result.no_exit_count == 1


# --------------------------------------------------------------------------
# The knowledge firewall, inherited from M079
# --------------------------------------------------------------------------


_VISIBLE_OPEN = (event(gid="O", effective=D1, recorded=D1, quantity=10, price="100"),)


def _at_k(events: tuple[OperatorAssertedPositionEvent, ...]) -> AssertedRoundTripReport:
    return report(events=events, effective=LATER, knowledge=D2)


def test_an_exit_recorded_after_the_cutoff_does_not_change_the_answer() -> None:
    baseline = _at_k(_VISIBLE_OPEN)
    polluted = _at_k(
        (
            *_VISIBLE_OPEN,
            event(
                gid="R",
                kind=OperatorPositionEventKind.REDUCED,
                quantity=4,
                price="500",
                effective=D2,
                recorded=R_LATE,
            ),
        )
    )
    assert baseline == polluted
    assert baseline.entries[0].asserted_round_trip_result is None


@pytest.mark.parametrize(
    "future_event",
    [
        pytest.param(
            event(
                gid="F1",
                kind=OperatorPositionEventKind.REDUCED,
                quantity=1,
                price="999",
                effective=D2,
                recorded=R_LATE,
            ),
            id="future-reduction",
        ),
        pytest.param(
            event(gid="F2", pos="POS-9", symbol="NVDA", effective=D1, recorded=R_LATE),
            id="future-other-position",
        ),
        pytest.param(
            event(gid="O", effective=D1, recorded=R_LATE, quantity=10, price="100"),
            id="future-duplicate-id",
        ),
    ],
)
def test_every_output_field_is_unchanged_by_any_post_cutoff_row(
    future_event: OperatorAssertedPositionEvent,
) -> None:
    baseline = _at_k(_VISIBLE_OPEN)
    polluted = _at_k((*_VISIBLE_OPEN, future_event))
    for slot in AssertedRoundTripReport.__slots__:
        assert getattr(baseline, slot) == getattr(polluted, slot), f"{slot} leaked post-cutoff data"


def test_text_and_json_are_unchanged_by_post_cutoff_rows() -> None:
    baseline = _at_k(_VISIBLE_OPEN)
    polluted = _at_k(
        (
            *_VISIBLE_OPEN,
            event(
                gid="F",
                kind=OperatorPositionEventKind.REDUCED,
                quantity=9,
                price="777",
                effective=D2,
                recorded=R_LATE,
            ),
        )
    )
    assert render_round_trip_report_text(baseline) == render_round_trip_report_text(polluted)
    assert render_round_trip_report_json(baseline) == render_round_trip_report_json(polluted)


def test_the_report_builder_cannot_reach_post_cutoff_events_at_all() -> None:
    """The structural guarantee, asserted directly rather than inferred."""
    import inspect

    from empirical_platform.decision_candidate import operator_asserted_round_trip as module

    parameters = inspect.signature(module._report_from_known_evidence).parameters
    assert set(parameters) == {"known", "effective_as_of", "knowledge_as_of"}
    source = inspect.getsource(module._report_from_known_evidence)
    assert ".recorded_at" not in source, "the knowledge filter belongs to the caller"
    assert "events_known_by" not in source


def test_an_exit_visible_without_its_opening_is_unresolved_not_arithmetic() -> None:
    opened = event(gid="O", effective=D1, recorded=R_LATE, quantity=10, price="100")
    closed = closed_after((opened,), gid="C", price="130", effective=D2, recorded=D2)
    entry = report(events=(opened, closed), effective=LATER, knowledge=D3).entries[0]
    assert entry.status is RoundTripStatus.UNRESOLVED_KNOWLEDGE_SEQUENCE
    assert entry.asserted_round_trip_result is None
    assert entry.rejection_reason == "POSITION_NOT_OPEN"


def test_nothing_recorded_by_the_cutoff_is_not_nothing_happened() -> None:
    result = report(events=_VISIBLE_OPEN, effective=LATER, knowledge=T0)
    assert result.outcome is RoundTripOutcome.NO_EVIDENCE_RECORDED_BY_KNOWLEDGE_CUTOFF
    assert result.entries == ()


def test_no_count_of_hidden_assertions_is_reported() -> None:
    result = _at_k(_VISIBLE_OPEN)
    assert not hasattr(result, "excluded_by_knowledge_cutoff")
    assert not hasattr(result, "total_event_count")


# --------------------------------------------------------------------------
# Cutoff boundaries and validation
# --------------------------------------------------------------------------


def test_the_knowledge_boundary_is_inclusive() -> None:
    result = report(events=(event(gid="O", effective=D1, recorded=D2),), knowledge=D2)
    assert result.visible_event_count == 1


def test_one_microsecond_past_the_knowledge_boundary_is_excluded() -> None:
    result = report(
        events=(event(gid="O", effective=D1, recorded=D2 + timedelta(microseconds=1)),),
        knowledge=D2,
    )
    assert result.outcome is RoundTripOutcome.NO_EVIDENCE_RECORDED_BY_KNOWLEDGE_CUTOFF


def test_the_effective_boundary_is_inclusive() -> None:
    result = report(events=(event(gid="O", effective=D2, recorded=D1),), effective=D2)
    assert result.visible_event_count == 1


def test_an_exit_effective_after_the_effective_cutoff_is_excluded_and_counted() -> None:
    opened = event(gid="O", effective=D1, recorded=D1, quantity=10, price="100")
    reduced = event(
        gid="R",
        kind=OperatorPositionEventKind.REDUCED,
        quantity=4,
        price="130",
        effective=D3,
        recorded=D1,
    )
    result = report(events=(opened, reduced), effective=D2, knowledge=LATER)
    assert result.excluded_by_effective_cutoff == 1
    assert result.entries[0].status is RoundTripStatus.NO_EXIT_ASSERTED_YET


@pytest.mark.parametrize("label", ["effective_as_of", "knowledge_as_of"])
def test_a_naive_cutoff_is_refused(label: str) -> None:
    kwargs = {"effective_as_of": LATER, "knowledge_as_of": LATER}
    kwargs[label] = datetime(2026, 3, 1)  # noqa: DTZ001 - deliberately naive
    with pytest.raises(ValueError, match="timezone-aware"):
        build_asserted_round_trip_report(events=(), **kwargs)


def test_two_zones_naming_the_same_instant_agree() -> None:
    utc = report(events=_VISIBLE_OPEN, effective=LATER, knowledge=D2)
    plus_two = report(
        events=_VISIBLE_OPEN,
        effective=LATER,
        knowledge=D2.astimezone(timezone(timedelta(hours=2))),
    )
    assert utc.entries[0].status == plus_two.entries[0].status
    assert utc.visible_event_count == plus_two.visible_event_count


def test_a_knowledge_cutoff_before_the_effective_cutoff_is_permitted_and_named() -> None:
    result = report(events=_VISIBLE_OPEN, effective=LATER, knowledge=D2)
    assert any("precedes the effective cutoff" in line for line in result.limitations)


# --------------------------------------------------------------------------
# Precision
# --------------------------------------------------------------------------


def test_the_maximum_supported_price_is_exact() -> None:
    top = "99999999999999.999999"
    opened = event(gid="O", effective=D1, quantity=1, price=top)
    closed = closed_after((opened,), gid="C", price=top, effective=D2)
    assert report(events=(opened, closed)).entries[0].asserted_round_trip_result == "0"


def test_the_minimum_supported_price_is_exact() -> None:
    opened = event(gid="O", effective=D1, quantity=1, price="0.000002")
    closed = closed_after((opened,), gid="C", price="0.000001", effective=D2)
    assert report(events=(opened, closed)).entries[0].asserted_round_trip_result == "-0.000001"


def test_six_decimal_places_survive_multiplication_and_summation() -> None:
    opened = event(gid="O", effective=D1, quantity=3, price="1.234567")
    closed = closed_after((opened,), gid="C", price="2.345678", effective=D2)
    entry = report(events=(opened, closed)).entries[0]
    assert entry.asserted_entry_cost_for_exited_quantity == "3.703701"
    assert entry.asserted_exit_consideration == "7.037034"
    assert entry.asserted_round_trip_result == "3.333333"


def test_no_float_appears_in_any_rendered_value() -> None:
    opened = event(gid="O", effective=D1, quantity=3, price="1.234567")
    closed = closed_after((opened,), gid="C", price="2.345678", effective=D2)
    payload = render_round_trip_report_json(report(events=(opened, closed)))

    def walk(node: object) -> None:
        if isinstance(node, float):
            raise AssertionError(f"a float reached the output: {node!r}")
        if isinstance(node, dict):
            for value in node.values():
                walk(value)
        if isinstance(node, list):
            for value in node:
                walk(value)

    walk(payload)


# --------------------------------------------------------------------------
# Lineage
# --------------------------------------------------------------------------


def test_a_cited_plan_is_reported_as_metadata() -> None:
    opened = event(gid="O", effective=D1, plan="PLAN-7")
    assert report(events=(opened,)).entries[0].cited_position_plan_governance_id == "PLAN-7"


def test_a_blank_citation_is_not_treated_as_an_identifier() -> None:
    opened = event(gid="O", effective=D1, plan="   ")
    assert report(events=(opened,)).entries[0].cited_position_plan_governance_id is None


def test_a_missing_citation_is_absence_not_an_error() -> None:
    result = report(events=(event(gid="O", effective=D1, plan=None),))
    assert result.outcome is RoundTripOutcome.ROUND_TRIP_REPORT_AVAILABLE
    assert result.entries[0].cited_position_plan_governance_id is None


def test_two_positions_citing_one_plan_stay_separate() -> None:
    a = event(gid="A", pos="POS-A", effective=D1, plan="PLAN-7")
    b = event(gid="B", pos="POS-B", symbol="TSLA", effective=D1, plan="PLAN-7")
    result = report(events=(a, b))
    assert len(result.entries) == 2
    assert {e.cited_position_plan_governance_id for e in result.entries} == {"PLAN-7"}


# --------------------------------------------------------------------------
# Honesty
# --------------------------------------------------------------------------

_FORBIDDEN = (
    "BROKER_REALIZED_PNL",
    "ACTUAL_PROFIT",
    "VERIFIED_PROCEEDS",
    "MARKET_RETURN",
    "EXECUTION_PNL",
    "PNL",
    "PROFIT",
    "REALIZED",
    "VERIFIED",
    "EXECUTED",
    "FILLED",
    "WIN_RATE",
    "EXPECTANCY",
)


def test_no_forbidden_token_appears_in_any_closed_vocabulary() -> None:
    names = [m.value for m in RoundTripStatus]
    names += [m.value for m in RoundTripOutcome]
    names += [m.value for m in RoundTripUnassessableReason]
    names += [f.name for f in dataclasses.fields(AssertedRoundTripReport)]
    opened = event(gid="O", effective=D1)
    names += [f.name for f in dataclasses.fields(report(events=(opened,)).entries[0])]
    for name in names:
        for token in _FORBIDDEN:
            assert token not in name.upper(), f"{token} appears in {name}"


def test_no_forbidden_token_appears_in_json_keys() -> None:
    opened = event(gid="O", effective=D1)
    payload = render_round_trip_report_json(report(events=(opened,)))
    keys = list(payload) + [k for entry in payload["entries"] for k in entry]  # type: ignore[union-attr]
    for key in keys:
        for token in _FORBIDDEN:
            assert token not in key.upper(), f"{token} appears in JSON key {key}"


def test_the_banner_states_what_the_result_is_not() -> None:
    for phrase in (
        "NOT broker realized profit or loss",
        "NOT verified profit",
        "NOT actual cash proceeds",
        "NOT a market return",
        "NOT a tax result",
        "ARITHMETIC ON ASSERTIONS",
    ):
        assert phrase in ASSERTED_ROUND_TRIP_BANNER


def test_every_unrepresented_economic_component_is_named_on_every_report() -> None:
    opened = event(gid="O", effective=D1)
    for result in (report(events=(opened,)), report(events=()), report(ledger_available=False)):
        if result.outcome is RoundTripOutcome.NOT_ASSESSABLE:
            continue
        assert result.unrepresented_economic_components == UNREPRESENTED_ECONOMIC_COMPONENTS
    joined = " ".join(report(events=(opened,)).limitations)
    for component in UNREPRESENTED_ECONOMIC_COMPONENTS:
        assert component in joined


def test_no_aggregate_result_across_positions_is_emitted() -> None:
    fields = {f.name for f in dataclasses.fields(AssertedRoundTripReport)}
    for banned in ("total_result", "aggregate", "net_result", "return_percent", "win"):
        assert not any(banned in name for name in fields)


# --------------------------------------------------------------------------
# Absence, ordering, determinism
# --------------------------------------------------------------------------


def test_an_unavailable_ledger_is_withheld_not_rendered_as_empty() -> None:
    result = report(ledger_available=False)
    assert result.outcome is RoundTripOutcome.NOT_ASSESSABLE
    assert result.unassessable_reason is RoundTripUnassessableReason.LEDGER_UNAVAILABLE
    assert result.entries == ()


def test_entries_are_ordered_by_instrument_then_position() -> None:
    events = (
        event(gid="C", pos="POS-C", symbol="TSLA", effective=D1),
        event(gid="A", pos="POS-A", symbol="AAPL", effective=D1),
        event(gid="B", pos="POS-B", symbol="AAPL", effective=D1),
    )
    ordered = [
        (e.instrument_symbol, e.position_governance_id) for e in report(events=events).entries
    ]
    assert ordered == [("AAPL", "POS-A"), ("AAPL", "POS-B"), ("TSLA", "POS-C")]


def test_ordering_is_unchanged_by_post_cutoff_rows() -> None:
    prefix = (
        event(gid="A", pos="POS-A", symbol="AAPL", effective=D1, recorded=D1),
        event(gid="B", pos="POS-B", symbol="TSLA", effective=D1, recorded=D1),
    )
    baseline = _at_k(prefix)
    polluted = _at_k(
        (*prefix, event(gid="Z", pos="POS-Z", symbol="AAAA", effective=D1, recorded=R_LATE))
    )
    assert [e.position_governance_id for e in baseline.entries] == [
        e.position_governance_id for e in polluted.entries
    ]


def test_two_identical_reads_are_identical() -> None:
    events = (event(gid="O", effective=D1),)
    assert report(events=events) == report(events=events)


def test_every_visible_position_appears_exactly_once() -> None:
    events = (
        event(gid="A", pos="POS-A", effective=D1),
        event(gid="B", pos="POS-B", symbol="TSLA", effective=D1),
        event(gid="C", pos="POS-C", symbol="NVDA", effective=D1),
    )
    ids = [e.position_governance_id for e in report(events=events).entries]
    assert sorted(ids) == ["POS-A", "POS-B", "POS-C"]
    assert len(ids) == len(set(ids))


def test_counts_agree_with_the_entries() -> None:
    healthy = event(gid="H", pos="POS-2", symbol="TSLA", effective=D1, recorded=D1)
    result = report(events=(*_late_reduction_ledger(), healthy), effective=LATER, knowledge=D3)
    total = (
        result.no_exit_count
        + result.partial_exit_count
        + result.fully_exited_count
        + result.unreconciled_count
        + result.unresolved_count
    )
    assert total == len(result.entries)


def test_text_and_json_agree_on_the_result() -> None:
    opened = event(gid="O", effective=D1, quantity=10, price="100")
    closed = closed_after((opened,), gid="C", price="130", effective=D2)
    result = report(events=(opened, closed))
    payload = render_round_trip_report_json(result)
    rendered = render_round_trip_report_text(result)
    assert payload["entries"][0]["asserted_round_trip_result"] == "300"  # type: ignore[index]
    assert "300" in rendered
    assert "FULLY_EXITED_ASSERTED" in rendered


# --------------------------------------------------------------------------
# Implementation review R01 — the result line must state its own coverage
# --------------------------------------------------------------------------


def test_a_partial_result_line_states_what_it_does_not_cover() -> None:
    """Implementation review R01. Regression: before the fix this line was
    worded identically to a fully-exited position's."""
    opened = event(gid="O", effective=D1, quantity=10, price="100")
    reduced = event(
        gid="R", kind=OperatorPositionEventKind.REDUCED, quantity=4, price="130", effective=D2
    )
    rendered = render_round_trip_report_text(report(events=(opened, reduced)))
    assert "on the 4 exited unit(s) ONLY" in rendered
    assert "6 still open and NOT covered" in rendered


def test_an_unreconciled_result_line_says_it_is_not_the_whole_result() -> None:
    """Implementation review R01."""
    rendered = render_round_trip_report_text(
        report(events=_late_reduction_ledger(), effective=LATER, knowledge=D3)
    )
    assert "on ONLY the 6 exited unit(s) visible here" in rendered
    assert "4 of the 10 opened are unaccounted for" in rendered
    assert "NOT the whole position's result" in rendered


def test_a_fully_exited_result_line_states_its_coverage_too() -> None:
    opened = event(gid="O", effective=D1, quantity=10, price="100")
    closed = closed_after((opened,), gid="C", price="130", effective=D2)
    rendered = render_round_trip_report_text(report(events=(opened, closed)))
    assert "on all 10 exited unit(s)" in rendered


def test_the_three_coverage_phrasings_are_distinct() -> None:
    """The point of R01: the reader must be able to tell them apart."""
    opened = event(gid="O", effective=D1, quantity=10, price="100")
    partial = event(
        gid="R", kind=OperatorPositionEventKind.REDUCED, quantity=4, price="130", effective=D2
    )
    full_closed = closed_after((opened,), gid="C", price="130", effective=D2)
    lines = set()
    for events, eff, know in (
        ((opened, partial), LATER, LATER),
        ((opened, full_closed), LATER, LATER),
        (_late_reduction_ledger(), LATER, D3),
    ):
        text = render_round_trip_report_text(report(events=events, effective=eff, knowledge=know))
        lines.add(
            next(
                line
                for line in text.split("\n")
                if line.startswith("      ASSERTED ROUND-TRIP RESULT")
            )
        )
    assert len(lines) == 3


# --------------------------------------------------------------------------
# Owner review finding 1 — exact arithmetic, independent of the ambient
# Decimal context. The previous design verdicts E04/E06/E07 tested only SMALL
# quantities against a large price and were therefore too weak to see this.
# --------------------------------------------------------------------------

#: PostgreSQL INTEGER maximum: the largest quantity M076 persistence admits.
_POSTGRES_INT_MAX = 2147483647
_MAX_PRICE = "99999999999999.999999"
_MIN_PRICE = "0.000001"


def _max_boundary_position() -> tuple[OperatorAssertedPositionEvent, ...]:
    opened = event(gid="O", effective=D1, quantity=_POSTGRES_INT_MAX, price=_MAX_PRICE)
    closed = closed_after((opened,), gid="C", price=_MIN_PRICE, effective=D2)
    return (opened, closed)


def test_the_owner_boundary_case_is_exact_to_the_last_digit() -> None:
    """Owner review attacks 1, 2, 3, 4, 5 and 6 in one position.

    Before the fix this rounded to 28 significant digits under the default
    Decimal context and silently lost six digits.
    """
    entry = report(events=_max_boundary_position()).entries[0]
    assert entry.asserted_entry_cost_for_exited_quantity == "214748364699999999997852.516353"
    assert entry.asserted_exit_consideration == "2147.483647"
    assert entry.asserted_round_trip_result == "-214748364699999999995705.032706"


def test_the_exact_product_matches_independent_integer_arithmetic() -> None:
    """Owner review attack 10, in-memory twin: recomputed with pure integers,
    which are arbitrary-precision and cannot be affected by any context."""
    entry = report(events=_max_boundary_position()).entries[0]
    scaled_entry = _POSTGRES_INT_MAX * 99999999999999999999
    scaled_exit = _POSTGRES_INT_MAX * 1
    scaled_result = scaled_exit - scaled_entry
    sign = "-" if scaled_result < 0 else ""
    whole, fraction = divmod(abs(scaled_result), 10**6)
    expected = f"{sign}{whole}.{fraction:06d}".rstrip("0").rstrip(".")
    assert entry.asserted_round_trip_result == expected


@pytest.mark.parametrize(
    ("precision", "rounding"),
    [
        pytest.param(1, None, id="prec-1"),
        pytest.param(5, None, id="prec-5"),
        pytest.param(28, None, id="prec-28-default"),
        pytest.param(9, ROUND_UP, id="prec-9-round-up"),
        pytest.param(3, ROUND_FLOOR, id="prec-3-round-floor"),
        pytest.param(60, None, id="prec-60"),
    ],
)
def test_the_result_is_independent_of_the_ambient_decimal_context(
    precision: int, rounding: str | None
) -> None:
    """Owner review attacks 8 and 9. A caller's context must not change M080."""
    events = _max_boundary_position()
    baseline = report(events=events)
    with localcontext() as context:
        context.prec = precision
        if rounding is not None:
            context.rounding = rounding
        under_context = report(events=events)
    assert under_context == baseline
    assert render_round_trip_report_json(under_context) == render_round_trip_report_json(baseline)
    assert render_round_trip_report_text(under_context) == render_round_trip_report_text(baseline)


def test_many_reductions_totalling_near_integer_max_stay_exact() -> None:
    """Owner review attack 7."""
    opened = event(gid="O", effective=D1, quantity=_POSTGRES_INT_MAX, price=_MAX_PRICE)
    reductions = tuple(
        event(
            gid=f"R{index}",
            kind=OperatorPositionEventKind.REDUCED,
            quantity=_POSTGRES_INT_MAX // 4,
            price=_MAX_PRICE,
            effective=D2 + timedelta(hours=index),
        )
        for index in range(4)
    )
    entry = report(events=(opened, *reductions)).entries[0]
    exited = (_POSTGRES_INT_MAX // 4) * 4
    scaled = exited * 99999999999999999999
    whole, fraction = divmod(scaled, 10**6)
    expected = f"{whole}.{fraction:06d}".rstrip("0").rstrip(".")
    assert entry.exited_quantity == exited
    assert entry.asserted_exit_consideration == expected
    # entry and exit at the same price: exactly zero, to the last digit
    assert entry.asserted_round_trip_result == "0"


def test_money_rendering_does_not_round_a_value_beyond_the_context_precision() -> None:
    """Owner review attack 12. The old renderer went through
    `Decimal.normalize()`, which re-rounded an exact value on the way out."""
    entry = report(events=_max_boundary_position()).entries[0]
    rendered = entry.asserted_round_trip_result
    assert rendered is not None
    digits = rendered.replace("-", "").replace(".", "")
    assert len(digits) == 30, "an exact 30-digit result must survive rendering"
    assert "E" not in rendered and "e" not in rendered


def test_text_and_json_carry_the_identical_full_precision_string() -> None:
    """Owner review attack 11."""
    result = report(events=_max_boundary_position())
    exact = result.entries[0].asserted_round_trip_result
    assert exact is not None
    payload = render_round_trip_report_json(result)
    assert payload["entries"][0]["asserted_round_trip_result"] == exact  # type: ignore[index]
    assert exact in render_round_trip_report_text(result)


def test_the_module_performs_no_decimal_arithmetic_at_all() -> None:
    """The structural form of the guarantee: no Decimal operator can round
    because no Decimal operator is used."""
    import inspect

    from empirical_platform.decision_candidate import operator_asserted_round_trip as module

    source = inspect.getsource(module._entry_for_key)
    for forbidden in ("Decimal(", ".normalize(", ".quantize(", ".scaleb("):
        assert forbidden not in source, f"{forbidden} reintroduces context sensitivity"


def test_the_minimum_price_survives_the_maximum_quantity() -> None:
    """Owner review attack 3 at the opposite extreme."""
    opened = event(gid="O", effective=D1, quantity=_POSTGRES_INT_MAX, price=_MIN_PRICE)
    closed = closed_after((opened,), gid="C", price=_MIN_PRICE, effective=D2)
    entry = report(events=(opened, closed)).entries[0]
    assert entry.asserted_entry_cost_for_exited_quantity == "2147.483647"
    assert entry.asserted_round_trip_result == "0"


# --------------------------------------------------------------------------
# Owner review finding 2 — not every excluded component is a cost
# --------------------------------------------------------------------------


def test_no_claim_survives_that_every_excluded_item_is_a_cost() -> None:
    result = report(events=(event(gid="O", effective=D1),))
    surfaces = [ASSERTED_ROUND_TRIP_BANNER, *result.limitations]
    surfaces.append(render_round_trip_report_text(result))
    joined = " ".join(surfaces).lower()
    assert "cost components" not in joined
    for field in dataclasses.fields(AssertedRoundTripReport):
        assert "cost_component" not in field.name


def test_no_claim_survives_of_a_universally_favourable_bias() -> None:
    result = report(events=(event(gid="O", effective=D1),))
    joined = " ".join(
        [ASSERTED_ROUND_TRIP_BANNER, *result.limitations, render_round_trip_report_text(result)]
    ).lower()
    for banned in (
        "systematically more favourable",
        "more favourable than a real economic outcome",
        "always more favourable",
        "upper bound",
    ):
        assert banned not in joined


def test_dividends_and_corporate_actions_are_not_classified_as_costs() -> None:
    for component in ("dividends", "corporate actions", "taxes"):
        assert component not in UNREPRESENTED_CASHFLOW_COMPONENTS
        assert component in CONTEXT_DEPENDENT_COMPONENTS


def test_the_three_component_groups_partition_the_whole_list() -> None:
    """Owner review finding 4 split the old two-way grouping into three."""
    groups = (
        set(UNREPRESENTED_CASHFLOW_COMPONENTS),
        set(CONTEXT_DEPENDENT_COMPONENTS),
        set(NOT_SEPARATELY_ATTRIBUTABLE_EXECUTION_COMPONENTS),
    )
    union: set[str] = set()
    for group in groups:
        assert not union & group, "the groups must be disjoint"
        union |= group
    assert union == set(UNREPRESENTED_ECONOMIC_COMPONENTS)


def test_the_report_says_it_is_not_a_complete_economic_outcome() -> None:
    result = report(events=(event(gid="O", effective=D1),))
    joined = " ".join(result.limitations)
    assert "NOT a complete economic outcome" in joined
    assert "NOT generally knowable" in joined


def test_the_banner_states_the_direction_is_not_knowable() -> None:
    assert "NOT generally knowable" in ASSERTED_ROUND_TRIP_BANNER
    assert "can move it either way" in ASSERTED_ROUND_TRIP_BANNER
    assert "systematically more favourable" not in ASSERTED_ROUND_TRIP_BANNER


def test_both_renderings_expose_the_corrected_terminology() -> None:
    result = report(events=(event(gid="O", effective=D1),))
    payload = render_round_trip_report_json(result)
    rendered = render_round_trip_report_text(result)
    assert "unrepresented_economic_components" in payload
    assert "excluded_cost_components" not in payload
    assert "excluded_economic_components" not in payload
    assert "NOT separately represented" in rendered
    assert "NOT generally knowable" in rendered


def test_the_original_honesty_guards_all_still_hold() -> None:
    """Finding 2's correction must not have weakened finding-agnostic guards."""
    result = report(events=_max_boundary_position())
    payload = render_round_trip_report_json(result)
    keys = list(payload) + [k for entry in payload["entries"] for k in entry]  # type: ignore[union-attr]
    for key in keys:
        for token in _FORBIDDEN:
            assert token not in key.upper()
    for phrase in (
        "NOT broker realized profit or loss",
        "NOT verified profit",
        "NOT actual cash proceeds",
        "NOT a market return",
        "NOT a tax result",
        "ARITHMETIC ON ASSERTIONS",
    ):
        assert phrase in ASSERTED_ROUND_TRIP_BANNER


# --------------------------------------------------------------------------
# Owner review finding 3 — no currency / denomination authority
# --------------------------------------------------------------------------

_CURRENCY_TOKENS = ("USD", "EUR", "GBP", "JPY", "CHF", "CAD", "AUD", "$", "€", "£", "¥")


def _without_denials(text: str) -> str:
    """Remove the two surfaces whose PURPOSE is to name currencies in order to
    deny them. What remains must contain no currency token at all.

    A blanket "USD not in output" assertion is wrong here: the banner says
    "NOT USD, NOT EUR", which is the honest statement, not a violation. The
    defect this guards against is a currency appearing as an *inferred unit*.
    """
    # The text renderer splits the banner on ". " and prints each sentence on its
    # own line, so an exact whole-string replace does not match there. Strip by
    # sentence so the same helper works for text and for JSON.
    stripped = text
    for surface in (ASSERTED_ROUND_TRIP_BANNER, ASSERTED_PRICE_DENOMINATION_LIMITATION):
        for sentence in surface.split(". "):
            stripped = stripped.replace(sentence, "")
    return stripped


def test_m076_persists_no_currency_field_at_all() -> None:
    """Owner review attack 1. The premise of finding 3, asserted rather than assumed."""
    fields = {f.name for f in dataclasses.fields(OperatorAssertedPositionEvent)}
    for banned in ("currency", "quote_currency", "price_currency", "denomination", "ccy"):
        assert not any(banned in name for name in fields), (
            f"{banned} appears in the frozen M076 event; finding 3's premise would be void"
        )


def test_no_denomination_is_invented_from_an_arbitrary_symbol() -> None:
    """Owner review attack 2."""
    for symbol in ("AAPL", "XAU", "BTC", "ZZZZ"):
        opened = event(gid="O", symbol=symbol, effective=D1, quantity=3, price="12.5")
        closed = closed_after((opened,), gid="C", price="20", effective=D2, symbol=symbol)
        result = report(events=(opened, closed))
        rendered = render_round_trip_report_text(result)
        payload = render_round_trip_report_json(result)
        residual_text = _without_denials(rendered)
        residual_json = _without_denials(json.dumps(payload))
        for token in _CURRENCY_TOKENS:
            assert token not in residual_text, f"{token} inferred as a unit for {symbol}"
            assert token not in residual_json, f"{token} in JSON for {symbol}"


def test_json_carries_no_invented_currency() -> None:
    """Owner review attack 3."""
    payload = _without_denials(
        json.dumps(render_round_trip_report_json(report(events=_max_boundary_position())))
    )
    for token in _CURRENCY_TOKENS:
        assert token not in payload


def test_text_carries_no_invented_currency() -> None:
    """Owner review attacks 4 and 5."""
    rendered = _without_denials(
        render_round_trip_report_text(report(events=_max_boundary_position()))
    )
    for token in _CURRENCY_TOKENS:
        assert token not in rendered


@pytest.mark.parametrize(
    "shape",
    ["closed", "open", "partial", "empty", "withheld"],
    ids=["closed", "open", "partial", "empty", "withheld"],
)
def test_the_denomination_limitation_rides_on_every_report_shape(shape: str) -> None:
    """Owner review attack 6."""
    opened = event(gid="O", effective=D1, quantity=10, price="100")
    if shape == "closed":
        result = report(
            events=(opened, closed_after((opened,), gid="C", price="120", effective=D2))
        )
    elif shape == "open":
        result = report(events=(opened,))
    elif shape == "partial":
        reduced = event(
            gid="R", kind=OperatorPositionEventKind.REDUCED, quantity=4, price="120", effective=D2
        )
        result = report(events=(opened, reduced))
    elif shape == "empty":
        result = report(events=())
    else:
        result = report(ledger_available=False)

    assert ASSERTED_PRICE_DENOMINATION_LIMITATION in result.limitations
    assert "UNSPECIFIED ASSERTED PRICE UNITS" in " ".join(result.limitations)
    payload = render_round_trip_report_json(result)
    assert ASSERTED_PRICE_DENOMINATION_LIMITATION in payload["limitations"]  # type: ignore[operator]


def test_the_denomination_limitation_denies_currency_and_symbol_authority() -> None:
    for phrase in (
        "does NOT establish a currency denomination",
        "no currency is persisted",
        "instrument_symbol is not a currency authority",
        "must NOT be read as USD, EUR or any other currency",
    ):
        assert phrase in ASSERTED_PRICE_DENOMINATION_LIMITATION


def test_the_banner_denies_a_denomination() -> None:
    assert "SAME UNSPECIFIED ASSERTED PRICE UNITS" in ASSERTED_ROUND_TRIP_BANNER
    assert "NO currency is persisted" in ASSERTED_ROUND_TRIP_BANNER


def test_two_values_are_not_asserted_to_share_a_denomination() -> None:
    """Owner review attack 7. A future milestone must not read these entries as a
    same-currency aggregate."""
    a = event(gid="A", effective=D1, quantity=1, price="10")
    a_close = closed_after((a,), gid="AC", price="20", effective=D2)
    result = report(events=(a, a_close))
    joined = " ".join(result.limitations)
    assert "must NOT be assumed to share a denomination" in joined
    fields = {f.name for f in dataclasses.fields(AssertedRoundTripReport)}
    for banned in ("total", "aggregate", "sum_"):
        assert not any(banned in name for name in fields), "no aggregate surface exists"


# --------------------------------------------------------------------------
# Owner review finding 4 — spread and slippage are not provably excluded
# --------------------------------------------------------------------------


def test_spread_and_slippage_are_in_the_not_separately_attributable_group() -> None:
    assert set(NOT_SEPARATELY_ATTRIBUTABLE_EXECUTION_COMPONENTS) == {"spread", "slippage"}
    for component in ("spread", "slippage"):
        assert component not in UNREPRESENTED_CASHFLOW_COMPONENTS
        assert component not in CONTEXT_DEPENDENT_COMPONENTS


def test_spread_and_slippage_are_not_claimed_definitely_excluded() -> None:
    result = report(events=_max_boundary_position())
    surfaces = " ".join(
        [ASSERTED_ROUND_TRIP_BANNER, *result.limitations, render_round_trip_report_text(result)]
    )
    assert "NOT claimed to be excluded" in surfaces
    assert "may already be embedded" in surfaces.replace(
        "MAY already be embedded", "may already be embedded"
    )


def test_spread_and_slippage_are_described_as_not_separately_attributable() -> None:
    result = report(events=_max_boundary_position())
    joined = " ".join(result.limitations)
    assert "no benchmark, quoted, intended or arrival price" in joined
    assert "NOT determinable from this data" in joined


def test_no_claim_that_spread_or_slippage_would_reduce_the_result() -> None:
    """They are deliberately absent from the group that carries a direction."""
    result = report(events=_max_boundary_position())
    directional = next(
        line for line in result.limitations if "would normally reduce a raw result" in line
    )
    assert "spread" not in directional
    assert "slippage" not in directional


def test_the_cashflow_group_no_longer_contains_execution_effects() -> None:
    assert set(UNREPRESENTED_CASHFLOW_COMPONENTS) == {
        "commissions",
        "exchange and regulatory fees",
        "financing and borrow cost",
    }


# --------------------------------------------------------------------------
# Stale-claim reconciliation
# --------------------------------------------------------------------------


def test_no_active_surface_says_costs_excluded() -> None:
    result = report(events=_max_boundary_position())
    surfaces = [
        ASSERTED_ROUND_TRIP_BANNER,
        *result.limitations,
        render_round_trip_report_text(result),
        json.dumps(render_round_trip_report_json(result)),
    ]
    joined = " ".join(surfaces).lower()
    for stale in ("costs excluded", "excluded costs", "excluded_cost_components"):
        assert stale not in joined, f"stale phrase still active: {stale}"


def test_the_exact_arithmetic_is_unchanged_by_this_pass() -> None:
    """The finding-1 correction must survive the finding-3/4 rewording untouched."""
    entry = report(events=_max_boundary_position()).entries[0]
    assert entry.asserted_round_trip_result == "-214748364699999999995705.032706"
    assert entry.asserted_entry_cost_for_exited_quantity == "214748364699999999997852.516353"


def test_the_knowledge_firewall_is_unchanged_by_this_pass() -> None:
    baseline = _at_k(_VISIBLE_OPEN)
    polluted = _at_k(
        (
            *_VISIBLE_OPEN,
            event(
                gid="F",
                kind=OperatorPositionEventKind.REDUCED,
                quantity=4,
                price="500",
                effective=D2,
                recorded=R_LATE,
            ),
        )
    )
    assert baseline == polluted
    assert render_round_trip_report_text(baseline) == render_round_trip_report_text(polluted)
