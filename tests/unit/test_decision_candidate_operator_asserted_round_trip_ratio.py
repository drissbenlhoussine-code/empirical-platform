"""MILESTONE-081 focused tests.

Every test names the claim it defends. Claims that cannot fail are not tests.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime, timedelta
from decimal import Decimal, getcontext, localcontext
from fractions import Fraction

import pytest

from empirical_platform.decision_candidate.operator_asserted_round_trip import (
    ASSERTED_PRICE_DENOMINATION_LIMITATION,
    RoundTripOutcome,
    RoundTripStatus,
    build_asserted_round_trip_report,
)
from empirical_platform.decision_candidate.operator_asserted_round_trip_ratio import (
    ASSERTED_RATIO_BANNER,
    RATIO_APPROXIMATION_DECIMAL_PLACES,
    AssertedRoundTripRatioReport,
    PositionRoundTripRatioEntry,
    RatioAbsenceReason,
    build_asserted_round_trip_ratio_report,
)
from empirical_platform.decision_candidate.operator_position_ledger import (
    LedgerRejectionError,
    OperatorAssertedPositionEvent,
    OperatorPositionEventKind,
)
from empirical_platform.usecases.asserted_round_trip_ratio_io import (
    render_round_trip_ratio_report_json,
    render_round_trip_ratio_report_text,
)

BASE = datetime(2026, 3, 1, tzinfo=UTC)

# Every vocabulary M081 must never use for its own quantity. The first block is
# M081's own additions; the second is M080's thirteen, re-asserted so a later
# change cannot weaken the inherited guards.
FORBIDDEN_TOKENS = (
    "ROI",
    "TOTAL_RETURN",
    "INVESTMENT_RETURN",
    "PROFIT_PERCENTAGE",
    "PERFORMANCE_PERCENTAGE",
    "GAIN_PERCENT",
    "WIN_RATE",
    "HIT_RATE",
    "EXPECTANCY",
    "ACCURACY",
    "ALPHA",
    "EDGE",
    "YIELD",
    "R_MULTIPLE",
    "RMULTIPLE",
    "PNL",
    "P&L",
    "PROFIT",
    "REALIZED",
    "UNREALIZED",
    "BROKER",
    "FILL",
    "EXECUTION_RESULT",
    "CASH_PROCEEDS",
    "MARKET_VALUE",
    "PERFORMANCE",
    "RETURN",
)


def event(
    n: int,
    kind: OperatorPositionEventKind,
    quantity: int,
    price: str,
    day: int,
    *,
    position: str = "POS-1",
    symbol: str = "AAPL",
    recorded_day: int | None = None,
    plan: str | None = None,
) -> OperatorAssertedPositionEvent:
    return OperatorAssertedPositionEvent(
        governance_id=f"EVT-{n}",
        runtime_id=f"RUN-{n}",
        position_governance_id=position,
        instrument_symbol=symbol,
        kind=kind,
        quantity=quantity,
        asserted_price=Decimal(price),
        event_timestamp=BASE + timedelta(days=day),
        recorded_at=BASE + timedelta(days=recorded_day if recorded_day is not None else day),
        source_position_plan_governance_id=plan,
        note=None,
    )


def report(
    events: tuple[OperatorAssertedPositionEvent, ...],
    *,
    effective_day: int = 400,
    knowledge_day: int = 400,
) -> AssertedRoundTripRatioReport:
    return build_asserted_round_trip_ratio_report(
        events=events,
        effective_as_of=BASE + timedelta(days=effective_day),
        knowledge_as_of=BASE + timedelta(days=knowledge_day),
    )


def only(
    events: tuple[OperatorAssertedPositionEvent, ...], **kw: int
) -> PositionRoundTripRatioEntry:
    entries = report(events, **kw).entries
    assert len(entries) == 1
    return entries[0]


OPENED = OperatorPositionEventKind.OPENED
REDUCED = OperatorPositionEventKind.REDUCED
CLOSED = OperatorPositionEventKind.CLOSED


# --------------------------------------------------------------------------
# The mathematical model
# --------------------------------------------------------------------------


def test_the_mandated_lifecycle_yields_the_exact_reduced_ratio() -> None:
    """CLAIM: (4x110 + 6x90 - 10x100) / (10x100) = -20/1000 = -1/50."""
    entry = only(
        (
            event(1, OPENED, 10, "100", 0),
            event(2, REDUCED, 4, "110", 1),
            event(3, CLOSED, 6, "90", 2),
        )
    )
    assert entry.status is RoundTripStatus.FULLY_EXITED_ASSERTED
    assert (entry.ratio_numerator, entry.ratio_denominator) == (-1, 50)
    assert entry.ratio_exact == "-1/50"
    assert entry.ratio_decimal_approx == "-0.02"
    assert entry.ratio_approximation_is_exact is True


def test_the_ratio_is_reduced_so_four_eighths_and_one_half_are_one_object() -> None:
    """CLAIM: gcd reduction is applied, which is also what destroys the money."""
    entry = only((event(1, OPENED, 10, "100", 0), event(2, CLOSED, 10, "150", 1)))
    # Raw scaled money would be 500000000 / 1000000000.
    assert (entry.ratio_numerator, entry.ratio_denominator) == (1, 2)


def test_the_reduced_ratio_does_not_reveal_the_monetary_magnitude() -> None:
    """CLAIM (design D-F04): 1/2 is emitted by many different money amounts."""
    small = only((event(1, OPENED, 2, "1", 0), event(2, CLOSED, 2, "1.5", 1)))
    large = only((event(1, OPENED, 1000, "1000", 0), event(2, CLOSED, 1000, "1500", 1)))
    assert small.ratio_exact == large.ratio_exact == "1/2"
    assert (small.ratio_numerator, small.ratio_denominator) == (
        large.ratio_numerator,
        large.ratio_denominator,
    )


def test_exact_break_even_is_zero_and_never_negative_zero() -> None:
    entry = only((event(1, OPENED, 10, "100", 0), event(2, CLOSED, 10, "100", 1)))
    assert entry.ratio_numerator == 0
    assert entry.ratio_exact == "0"
    assert not entry.ratio_exact.startswith("-")
    assert entry.ratio_decimal_approx == "0"
    assert entry.ratio_approximation_is_exact is True


def test_an_exact_integer_ratio_renders_without_a_denominator() -> None:
    entry = only((event(1, OPENED, 5, "100", 0), event(2, CLOSED, 5, "300", 1)))
    assert entry.ratio_exact == "2"
    assert entry.ratio_denominator == 1


@pytest.mark.parametrize(
    ("opened_price", "exit_price", "expected"),
    [("300", "400", "1/3"), ("300", "500", "2/3"), ("700", "800", "1/7")],
)
def test_non_terminating_ratios_are_exact_rationals(
    opened_price: str, exit_price: str, expected: str
) -> None:
    """CLAIM: 1/3, 2/3 and 1/7 survive as exact values, not as decimals."""
    entry = only((event(1, OPENED, 3, opened_price, 0), event(2, CLOSED, 3, exit_price, 1)))
    assert entry.ratio_exact == expected
    assert entry.ratio_approximation_is_exact is False
    assert entry.ratio_decimal_approx is not None
    assert entry.ratio_decimal_approx.startswith("~")


def test_a_negative_ratio_carries_its_sign_on_the_numerator() -> None:
    entry = only((event(1, OPENED, 4, "100", 0), event(2, CLOSED, 4, "25", 1)))
    assert entry.ratio_exact == "-3/4"
    assert entry.ratio_numerator == -3
    assert entry.ratio_denominator == 4
    assert entry.ratio_denominator > 0


def test_a_very_large_ratio_is_exact() -> None:
    entry = only((event(1, OPENED, 1, "0.000001", 0), event(2, CLOSED, 1, "1000000", 1)))
    assert entry.ratio_denominator == 1
    assert entry.ratio_numerator == 999999999999


def test_the_denominator_is_always_strictly_positive() -> None:
    """CLAIM: division by zero is unreachable, not guarded."""
    for events in (
        (event(1, OPENED, 10, "100", 0), event(2, CLOSED, 10, "1", 1)),
        (event(1, OPENED, 1, "0.000001", 0), event(2, CLOSED, 1, "0.000002", 1)),
        (event(1, OPENED, 7, "3", 0), event(2, REDUCED, 3, "9", 1)),
    ):
        entry = only(events)
        assert entry.ratio_denominator is not None
        assert entry.ratio_denominator > 0


@pytest.mark.parametrize("bad_price", ["0", "-1", "-0.000001"])
def test_m076_rejects_the_prices_that_would_make_the_bound_reachable(bad_price: str) -> None:
    """CLAIM: the > -1 bound rests on a FROZEN invariant, so assert the invariant."""
    with pytest.raises(LedgerRejectionError):
        event(1, OPENED, 10, bad_price, 0)


def test_the_ratio_is_always_strictly_greater_than_minus_one() -> None:
    """CLAIM: a total loss (-1) is unreachable because an exit price cannot be 0."""
    entry = only(
        (
            event(1, OPENED, 2147483647, "99999999999999.999999", 0),
            event(2, CLOSED, 2147483647, "0.000001", 1),
        )
    )
    assert entry.ratio_numerator is not None
    assert entry.ratio_denominator is not None
    assert Fraction(entry.ratio_numerator, entry.ratio_denominator) > Fraction(-1)


def test_the_boundary_approximation_never_renders_the_unreachable_minus_one() -> None:
    """CLAIM (implementation R01): truncation toward zero, so no bare '-1'.

    A float of this value is exactly -1.0. Printing that would assert the very
    total loss the bound above proves impossible.
    """
    entry = only(
        (
            event(1, OPENED, 2147483647, "99999999999999.999999", 0),
            event(2, CLOSED, 2147483647, "0.000001", 1),
        )
    )
    assert float(Fraction(entry.ratio_numerator or 0, entry.ratio_denominator or 1)) == -1.0
    assert entry.ratio_decimal_approx == "~-0.999999"
    assert entry.ratio_decimal_approx != "-1"


def test_the_approximation_never_exceeds_the_exact_magnitude() -> None:
    """CLAIM: truncation toward zero, so |approx| <= |exact| always."""
    cases = [
        (event(1, OPENED, 3, "300", 0), event(2, CLOSED, 3, "400", 1)),
        (event(1, OPENED, 7, "700", 0), event(2, CLOSED, 7, "800", 1)),
        (event(1, OPENED, 3, "900", 0), event(2, CLOSED, 3, "100", 1)),
        (
            event(1, OPENED, 2147483647, "99999999999999.999999", 0),
            event(2, CLOSED, 2147483647, "0.000001", 1),
        ),
    ]
    for events in cases:
        entry = only(events)
        assert entry.ratio_decimal_approx is not None
        rendered = entry.ratio_decimal_approx.lstrip("~")
        approx = Fraction(Decimal(rendered))
        exact = Fraction(entry.ratio_numerator or 0, entry.ratio_denominator or 1)
        assert abs(approx) <= abs(exact)


@pytest.mark.parametrize("precision", [1, 5, 9, 28, 60])
def test_the_ratio_does_not_move_with_the_ambient_decimal_context(precision: int) -> None:
    """CLAIM: no Decimal operation touches the ratio, so context cannot reach it."""
    events = (
        event(1, OPENED, 2147483647, "99999999999999.999999", 0),
        event(2, CLOSED, 2147483647, "0.000001", 1),
    )
    with localcontext() as ctx:
        ctx.prec = precision
        entry = only(events)
        rendered = render_round_trip_ratio_report_text(report(events))
    assert entry.ratio_exact == "-99999999999999999998/99999999999999999999"
    assert entry.ratio_decimal_approx == "~-0.999999"
    assert "-99999999999999999998/99999999999999999999" in rendered


def test_the_module_never_builds_a_float_or_a_decimal_for_the_ratio() -> None:
    source = (
        __import__(
            "empirical_platform.decision_candidate.operator_asserted_round_trip_ratio",
            fromlist=["__file__"],
        ).__file__
        or ""
    )
    with open(source, encoding="utf-8") as handle:
        text = handle.read()
    body = text.split('"""', 2)[2]
    for forbidden in ("float(", "Decimal(", ".quantize(", ".normalize(", ".scaleb("):
        assert forbidden not in body, forbidden


# --------------------------------------------------------------------------
# Partial exit, unresolved and open semantics
# --------------------------------------------------------------------------


def test_a_partial_exit_uses_the_exited_quantity_denominator_not_the_whole_position() -> None:
    """CLAIM (design section 12): the mandated worked example.

    OPENED 10@100, REDUCED 1@200 => ratio 1, NOT 1/10.
    """
    entry = only((event(1, OPENED, 10, "100", 0), event(2, REDUCED, 1, "200", 1)))
    assert entry.status is RoundTripStatus.PARTIAL_EXIT_ASSERTED
    assert entry.exited_quantity == 1
    assert entry.still_open_quantity == 9
    assert entry.ratio_exact == "1"
    assert (entry.ratio_numerator, entry.ratio_denominator) != (1, 10)


def test_a_partial_exit_ratio_says_it_covers_the_exited_quantity_only() -> None:
    events = (event(1, OPENED, 10, "100", 0), event(2, REDUCED, 1, "200", 1))
    rendered = render_round_trip_ratio_report_text(report(events))
    assert "on the 1 exited unit(s) ONLY" in rendered


def test_an_open_position_gets_no_ratio_and_no_zero() -> None:
    """CLAIM (design section 14): absence is explicit; never 0, never break-even."""
    entry = only((event(1, OPENED, 10, "100", 0),))
    assert entry.status is RoundTripStatus.NO_EXIT_ASSERTED_YET
    assert entry.ratio_exact is None
    assert entry.ratio_numerator is None
    assert entry.ratio_denominator is None
    assert entry.ratio_decimal_approx is None
    assert entry.ratio_approximation_is_exact is None
    assert entry.ratio_absence_reason is RatioAbsenceReason.NO_EXIT_ASSERTED_YET


def test_an_open_position_still_appears_in_the_report() -> None:
    """CLAIM: absence is shown, not silently dropped."""
    rep = report((event(1, OPENED, 10, "100", 0),))
    assert len(rep.entries) == 1
    assert rep.ratio_absent_count == 1
    assert rep.ratio_available_count == 0
    rendered = render_round_trip_ratio_report_text(rep)
    assert "NO RATIO (NO_EXIT_ASSERTED_YET)" in rendered
    # The banner NAMES these in order to forbid them, so strip the denials
    # before searching -- my first version of this assertion flagged the
    # artifact's own denial and was wrong.
    stripped = _without_denials(rendered)
    for misleading in ("0%", "break-even", "breakeven", "flat"):
        assert misleading not in stripped


def test_an_unresolved_knowledge_sequence_gets_no_ratio() -> None:
    """CLAIM (design section 13): M080 emits no result, so there is none to normalize."""
    entry = only(
        (
            event(1, REDUCED, 4, "110", 1, recorded_day=1),
            event(2, OPENED, 10, "100", 0, recorded_day=9),
        ),
        knowledge_day=5,
    )
    assert entry.status is RoundTripStatus.UNRESOLVED_KNOWLEDGE_SEQUENCE
    assert entry.ratio_exact is None
    assert entry.ratio_absence_reason is RatioAbsenceReason.UNRESOLVED_KNOWLEDGE_SEQUENCE


# --------------------------------------------------------------------------
# The M079 knowledge-time firewall, inherited
# --------------------------------------------------------------------------


def test_a_post_cutoff_exit_cannot_reach_a_ratio() -> None:
    """CLAIM: the firewall is inherited structurally, not re-implemented."""
    events = (
        event(1, OPENED, 10, "100", 0, recorded_day=0),
        event(2, CLOSED, 10, "150", 1, recorded_day=300),
    )
    before = only(events, knowledge_day=100)
    after = only(events, knowledge_day=400)
    assert before.ratio_exact is None
    assert before.ratio_absence_reason is RatioAbsenceReason.NO_EXIT_ASSERTED_YET
    assert after.ratio_exact == "1/2"


@pytest.mark.parametrize(("knowledge_day", "expected"), [(299, None), (300, "1/2"), (301, "1/2")])
def test_the_knowledge_cutoff_is_inclusive(knowledge_day: int, expected: str | None) -> None:
    events = (
        event(1, OPENED, 10, "100", 0, recorded_day=0),
        event(2, CLOSED, 10, "150", 1, recorded_day=300),
    )
    assert only(events, knowledge_day=knowledge_day).ratio_exact == expected


def test_appending_a_post_cutoff_event_changes_nothing_at_the_earlier_cutoff() -> None:
    """CLAIM: object, text and JSON are all identical, not merely the value."""
    known = (
        event(1, OPENED, 10, "100", 0, recorded_day=0),
        event(2, REDUCED, 4, "110", 1, recorded_day=1),
    )
    future = (*known, event(3, CLOSED, 6, "90", 2, recorded_day=300))
    before = report(known, knowledge_day=50)
    after = report(future, knowledge_day=50)
    assert before == after
    assert render_round_trip_ratio_report_text(before) == render_round_trip_ratio_report_text(after)
    assert json.dumps(render_round_trip_ratio_report_json(before), sort_keys=True) == json.dumps(
        render_round_trip_ratio_report_json(after), sort_keys=True
    )


# --------------------------------------------------------------------------
# Denomination, aggregation and the forbidden surface
# --------------------------------------------------------------------------


def test_no_monetary_value_appears_anywhere_in_the_report() -> None:
    """CLAIM (design D-F04): M081 emits no money, at any level."""
    events = (
        event(1, OPENED, 10, "100", 0),
        event(2, REDUCED, 4, "110", 1),
        event(3, CLOSED, 6, "90", 2),
    )
    rep = report(events)
    payload = render_round_trip_ratio_report_json(rep)

    # Exact KEY comparison, not a substring scan: M081's own key
    # `asserted_round_trip_result_to_entry_cost_ratio_exact` deliberately names
    # its numerator, and a naive substring search flags it. That was my
    # assertion being wrong, not money leaking.
    entry_keys = set(payload["entries"][0])
    for money_field in (
        "asserted_entry_price",
        "asserted_entry_cost_for_exited_quantity",
        "asserted_exit_consideration",
        "asserted_round_trip_result",
    ):
        assert money_field not in entry_keys
        assert money_field not in set(payload)
        assert not any(hasattr(entry, money_field) for entry in rep.entries)

    # The M080 money for this fixture, in its rendered forms, must not appear.
    source = build_asserted_round_trip_report(
        events=events,
        effective_as_of=BASE + timedelta(days=400),
        knowledge_as_of=BASE + timedelta(days=400),
    )
    money = source.entries[0].asserted_round_trip_result
    assert money == "-20"
    entry_json = json.dumps(payload["entries"])
    assert '"-20"' not in entry_json
    assert '"1000"' not in entry_json


def test_the_report_exposes_no_aggregate_of_ratio_values() -> None:
    """CLAIM (design section 17): counts by status only, never values."""
    fields = set(AssertedRoundTripRatioReport.__dataclass_fields__)
    for forbidden in (
        "total_ratio",
        "mean_ratio",
        "average_ratio",
        "median_ratio",
        "best_ratio",
        "worst_ratio",
        "positive_ratio_count",
        "ratio_distribution",
        "sum_ratio",
    ):
        assert forbidden not in fields


def test_two_positions_of_unknown_denomination_are_never_combined() -> None:
    """CLAIM (mandated cross-denomination attack).

    Also the D-F03 case: the money ranks these two OPPOSITE to the ratios.
    """
    events = (
        event(1, OPENED, 10, "100", 0, position="POS-1", symbol="AAPL"),
        event(2, CLOSED, 10, "150", 1, position="POS-1", symbol="AAPL"),
        event(3, OPENED, 5, "2000", 0, position="POS-2", symbol="7203.T"),
        event(4, CLOSED, 5, "2200", 1, position="POS-2", symbol="7203.T"),
    )
    rep = report(events)
    by_symbol = {e.instrument_symbol: e for e in rep.entries}
    assert by_symbol["AAPL"].ratio_exact == "1/2"
    assert by_symbol["7203.T"].ratio_exact == "1/10"

    payload = render_round_trip_ratio_report_json(rep)
    assert "ratio_available_count" in payload
    # No combined value exists to be misread as a portfolio figure. Checked
    # against the KEY set: the banner legitimately uses words like "total" in
    # its denials ("NOT a total return"), and my first substring version of
    # this assertion flagged that denial and was wrong.
    all_keys = set(payload) | set(payload["entries"][0])
    for forbidden in ("portfolio", "total", "combined", "aggregate", "overall", "sum"):
        assert not any(forbidden in key.lower() for key in all_keys), forbidden


def test_no_currency_is_inferred_from_any_symbol() -> None:
    """CLAIM: symbol is not a currency authority; nothing is derived from it."""
    for symbol in ("AAPL", "XAU", "BTC", "7203.T", "ZZZZ"):
        events = (
            event(1, OPENED, 10, "100", 0, symbol=symbol),
            event(2, CLOSED, 10, "150", 1, symbol=symbol),
        )
        rendered = render_round_trip_ratio_report_text(report(events))
        stripped = _without_denials(rendered)
        for token in ("USD", "EUR", "GBP", "JPY", "CHF", "$", "€", "£", "¥"):
            assert token not in stripped, (symbol, token)


def _without_denials(text: str) -> str:
    """Remove the sentences that legitimately NAME currencies in order to deny them."""
    stripped = text
    for surface in (ASSERTED_RATIO_BANNER, ASSERTED_PRICE_DENOMINATION_LIMITATION):
        for sentence in surface.split(". "):
            stripped = stripped.replace(sentence.strip().rstrip("."), "")
    return stripped


def test_the_denomination_limitation_is_carried_verbatim_from_m080() -> None:
    rep = report((event(1, OPENED, 10, "100", 0), event(2, CLOSED, 10, "150", 1)))
    assert ASSERTED_PRICE_DENOMINATION_LIMITATION in rep.limitations


@pytest.mark.parametrize("ledger_available", [True, False])
def test_no_limitation_is_emitted_twice(ledger_available: bool) -> None:
    """CLAIM (implementation R02): the denomination denial appears exactly once.

    Found by running the CLI end-to-end. M081 prepended the limitation while
    also carrying M080's verbatim, and M080 already includes it -- so the most
    important denial in the artifact printed twice. A caveat repeated verbatim
    reads as a formatting bug and invites the reader to skim the rest.
    """
    rep = build_asserted_round_trip_ratio_report(
        events=(event(1, OPENED, 10, "100", 0), event(2, CLOSED, 10, "150", 1)),
        effective_as_of=BASE + timedelta(days=400),
        knowledge_as_of=BASE + timedelta(days=400),
        ledger_available=ledger_available,
    )
    assert rep.limitations.count(ASSERTED_PRICE_DENOMINATION_LIMITATION) == 1
    assert len(rep.limitations) == len(set(rep.limitations))
    rendered = render_round_trip_ratio_report_text(rep)
    assert rendered.count(ASSERTED_PRICE_DENOMINATION_LIMITATION) == 1


def test_the_ratio_is_never_rendered_as_a_percentage() -> None:
    """CLAIM (design D-H14): a percentage reads as a return."""
    events = (event(1, OPENED, 10, "100", 0), event(2, CLOSED, 10, "150", 1))
    rendered = render_round_trip_ratio_report_text(report(events))
    assert "%" not in rendered
    assert "%" not in json.dumps(render_round_trip_ratio_report_json(report(events)))


@pytest.mark.parametrize("token", FORBIDDEN_TOKENS)
def test_no_forbidden_token_appears_in_any_closed_vocabulary(token: str) -> None:
    """CLAIM: no status, field name or JSON key claims a return or a performance."""
    surfaces = [
        *AssertedRoundTripRatioReport.__dataclass_fields__,
        *PositionRoundTripRatioEntry.__dataclass_fields__,
        *(str(member) for member in RatioAbsenceReason),
        *(str(member) for member in RoundTripStatus),
        *(str(member) for member in RoundTripOutcome),
    ]
    events = (event(1, OPENED, 10, "100", 0), event(2, CLOSED, 10, "150", 1))
    surfaces.extend(render_round_trip_ratio_report_json(report(events)))
    surfaces.extend(render_round_trip_ratio_report_json(report(events))["entries"][0])
    # Word-boundary matching. A naive substring check reports `EDGE` inside
    # `KNOWLEDGE_AS_OF`; that was my assertion being wrong, not a leaking
    # vocabulary, and an attack that fails for the wrong reason is as
    # misleading as a test that passes for the wrong one.
    pattern = re.compile(rf"(?<![A-Z0-9]){re.escape(token)}(?![A-Z0-9])")
    for surface in surfaces:
        normalized = surface.upper().replace(" ", "_")
        assert not pattern.search(normalized), (token, surface)


def test_the_banner_denies_every_reading_m081_does_not_support() -> None:
    for denial in (
        "NOT a return",
        "NOT ROI",
        "NOT profit percentage",
        "NOT investment performance",
        "NOT annualized",
        "DIMENSIONLESS",
        "ARITHMETICALLY comparable but NOT necessarily ECONOMICALLY comparable",
        "EXITED QUANTITY ONLY",
        "no zero, no break-even",
        "NO monetary value is emitted at all",
        "NOT claimed to be excluded",
    ):
        assert denial in ASSERTED_RATIO_BANNER, denial


# --------------------------------------------------------------------------
# Ordering, structure and rendering
# --------------------------------------------------------------------------


def test_entries_are_ordered_by_identity_and_never_by_ratio_value() -> None:
    """CLAIM (design section 21): ordering by outcome would itself rank decisions."""
    events = (
        event(1, OPENED, 10, "100", 0, position="POS-9", symbol="ZZZZ"),
        event(2, CLOSED, 10, "900", 1, position="POS-9", symbol="ZZZZ"),
        event(3, OPENED, 10, "100", 0, position="POS-1", symbol="AAAA"),
        event(4, CLOSED, 10, "101", 1, position="POS-1", symbol="AAAA"),
    )
    payload = render_round_trip_ratio_report_json(report(events))
    symbols = [e["instrument_symbol"] for e in payload["entries"]]
    assert symbols == ["AAAA", "ZZZZ"]
    # By value the order would be reversed: ZZZZ has ratio 8, AAAA has 1/100.
    ratios = [e["asserted_round_trip_result_to_entry_cost_ratio_exact"] for e in payload["entries"]]
    assert ratios == ["1/100", "8"]


def test_text_and_json_agree_on_every_ratio() -> None:
    events = (
        event(1, OPENED, 10, "100", 0, position="POS-1"),
        event(2, REDUCED, 3, "150", 1, position="POS-1"),
        event(3, OPENED, 4, "50", 0, position="POS-2", symbol="MSFT"),
    )
    rep = report(events)
    rendered = render_round_trip_ratio_report_text(rep)
    payload = render_round_trip_ratio_report_json(rep)
    for entry in payload["entries"]:
        exact = entry["asserted_round_trip_result_to_entry_cost_ratio_exact"]
        if exact is None:
            assert entry["ratio_absence_reason"] is not None
        else:
            assert f"exact={exact}" in rendered


def test_the_json_payload_is_serialisable_and_deterministic() -> None:
    events = (event(1, OPENED, 10, "100", 0), event(2, CLOSED, 10, "150", 1))
    first = json.dumps(render_round_trip_ratio_report_json(report(events)), sort_keys=True)
    second = json.dumps(render_round_trip_ratio_report_json(report(events)), sort_keys=True)
    assert first == second


def test_an_empty_ledger_still_carries_the_denomination_limitation() -> None:
    rep = report(())
    assert rep.entries == ()
    assert ASSERTED_PRICE_DENOMINATION_LIMITATION in rep.limitations
    # The renderer splits the banner into one sentence per line by design, so
    # the whole string is never contiguous in the text -- my first assertion
    # searched for the joined string and was wrong.
    rendered = render_round_trip_ratio_report_text(rep)
    for sentence in ASSERTED_RATIO_BANNER.split(". "):
        assert sentence.strip().rstrip(".") in rendered


def test_a_withheld_report_still_carries_the_denomination_limitation() -> None:
    rep = build_asserted_round_trip_ratio_report(
        events=(),
        effective_as_of=BASE,
        knowledge_as_of=BASE,
        ledger_available=False,
    )
    assert rep.outcome is RoundTripOutcome.NOT_ASSESSABLE
    assert rep.unassessable_reason is not None
    assert ASSERTED_PRICE_DENOMINATION_LIMITATION in rep.limitations


def test_counts_by_status_are_emitted_but_no_count_of_positive_ratios() -> None:
    events = (
        event(1, OPENED, 10, "100", 0, position="POS-1"),
        event(2, CLOSED, 10, "150", 1, position="POS-1"),
        event(3, OPENED, 4, "50", 0, position="POS-2", symbol="MSFT"),
    )
    rep = report(events)
    assert rep.ratio_available_count == 1
    assert rep.ratio_absent_count == 1
    # Checked against KEYS: the banner denies emitting a "count of positive
    # ratios", so a substring scan of the whole payload flags that denial.
    payload = render_round_trip_ratio_report_json(rep)
    all_keys = set(payload) | set(payload["entries"][0])
    for forbidden in ("positive", "win", "negative_count"):
        assert not any(forbidden in key.lower() for key in all_keys), forbidden


def test_the_plan_citation_is_shown_but_never_dereferenced() -> None:
    """CLAIM (design D-F07): no join to M060; two positions may cite one plan."""
    events = (
        event(1, OPENED, 10, "100", 0, position="POS-1", plan="PLAN-A"),
        event(2, CLOSED, 10, "150", 1, position="POS-1", plan="PLAN-A"),
        event(3, OPENED, 20, "50", 0, position="POS-2", symbol="MSFT", plan="PLAN-A"),
        event(4, CLOSED, 20, "40", 1, position="POS-2", symbol="MSFT", plan="PLAN-A"),
    )
    rep = report(events)
    assert {e.cited_position_plan_governance_id for e in rep.entries} == {"PLAN-A"}
    # Both positions keep their own independent denominator.
    assert {e.ratio_exact for e in rep.entries} == {"1/2", "-1/5"}


def test_the_scaled_money_inversion_round_trips_on_every_shape() -> None:
    """CLAIM (design D-F02): the inversion is not point-stripping.

    `100`, `0.5` and `1.000001` render at three different scales.
    """
    cases = [
        ((event(1, OPENED, 1, "100", 0), event(2, CLOSED, 1, "200", 1)), "1"),
        ((event(1, OPENED, 2, "1", 0), event(2, CLOSED, 2, "1.5", 1)), "1/2"),
        (
            (event(1, OPENED, 1, "1", 0), event(2, CLOSED, 1, "1.000001", 1)),
            "1/1000000",
        ),
    ]
    for events, expected in cases:
        assert only(events).ratio_exact == expected


def test_the_approximation_decimal_places_constant_matches_the_rendering() -> None:
    entry = only((event(1, OPENED, 3, "300", 0), event(2, CLOSED, 3, "400", 1)))
    assert entry.ratio_decimal_approx is not None
    fraction_digits = entry.ratio_decimal_approx.lstrip("~").split(".")[1]
    assert len(fraction_digits) <= RATIO_APPROXIMATION_DECIMAL_PLACES


def test_the_ambient_context_is_not_mutated_by_building_a_report() -> None:
    before = (getcontext().prec, getcontext().rounding)
    report((event(1, OPENED, 10, "100", 0), event(2, CLOSED, 10, "150", 1)))
    assert (getcontext().prec, getcontext().rounding) == before
