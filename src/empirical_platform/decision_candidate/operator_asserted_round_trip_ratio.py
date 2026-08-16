"""MILESTONE-081 -- Operator-Asserted Round-Trip Result Ratio.

For each position that frozen M080 gives a monetary result, this module reports
the EXACT RATIONAL ratio of that result to the asserted entry cost of the SAME
exited quantity:

                asserted_round_trip_result
    ratio  =  ----------------------------------------
              asserted_entry_cost_for_exited_quantity

WHY THIS EXISTS. M080 emits a per-position monetary value while forbidding a
reader to combine two of them, because no currency is persisted on an M076
event. A reader asking "which of these two positions did better" therefore had
exactly one option -- divide the money themselves -- which is precisely the
unsupported act M080's denomination limitation forbids. This module supplies the
one comparison primitive that is provably safe and makes the unsafe one
structurally unavailable.

DIMENSIONLESS BY EXACT CANCELLATION. Both quantities are integer multiples of
10^-6 of the SAME unspecified asserted price unit, for the SAME position, from
the SAME events. The scale cancels identically, so the ratio is the exact
quotient of two integers and needs no scale reasoning at all.

TWO PROVABLE BOUNDS, both inherited from frozen M076's `asserted_price > 0` and
positive integer quantities -- neither is a defensive guard:

  * the denominator is exited_quantity x entry_price, hence STRICTLY POSITIVE,
    so division by zero is UNREACHABLE. There is no guard because no guard can
    be reached.
  * exit consideration is a sum of strictly positive terms, so
    result > -entry_cost, hence ratio > -1 ALWAYS AND STRICTLY. A ratio of
    exactly -1 (a total loss) would require an asserted exit price of zero,
    which M076 rejects.

DESIGN REVIEW D-F01. A float rendering of the NUMERIC(20,6) extreme prints
exactly -1.0 while the exact value is strictly greater than -1 -- it would
assert the very total loss the bound above proves unreachable. The ratio is
therefore an exact reduced rational and never a float; the decimal rendering is
an explicitly labelled approximation produced by integer division.

DESIGN REVIEW D-F04, PARTIALLY RETRACTED BY OWNER REVIEW FINDING 2. This module
emits NO MONETARY VALUE ANYWHERE, at any level: no field is named, typed or
labelled as money, and the ratio is gcd-reduced.

    RETRACTED: the original claim continued "...and reduction actively destroys
    the monetary magnitude: 500 over 1000 becomes 1/2, from which 500 is
    unrecoverable." THAT IS NOT UNIVERSALLY TRUE and must not be relied on.
    When the two M080 scaled operands are already COPRIME, reduction changes
    nothing and the emitted pair IS the original scaled pair. A ledger of one
    unit opened at 0.000003 and closed at 0.000004 emits 1/3, whose numerator
    and denominator are exactly the scaled result and scaled entry cost; since
    M080's scale is publicly fixed at 10^-6, a knowledgeable reader can read the
    money straight back off it.

The honest statement, which is what this module actually guarantees:

  * M081 does not SEMANTICALLY expose or label any field as a monetary value;
  * it emits only the exact reduced ratio and its metadata;
  * a ratio does not GENERALLY identify a unique original scale factor, because
    infinitely many operand pairs reduce to the same rational;
  * BUT when the scaled operands are already coprime the reduced pair coincides
    with them, so no promise of non-recoverability is made or implied.

gcd reduction is a NORMALISATION so that 4/8 and 1/2 are one value. It is NOT a
confidentiality boundary and was never a sound basis for one. The frozen
requirement here is SEMANTIC NON-AGGREGATION AND NON-DENOMINATION -- M081 offers
no monetary field to sum and establishes no currency -- not information-theoretic
secrecy. A reader who wants the money should run M080, which carries its own
denomination banner.

M081 ADDS EXACTLY ONE THING: the ratio. The knowledge filter, the effective
filter, the fold, open-versus-closed and the statuses are all frozen M080's,
consumed unmodified. Nothing recorded after the knowledge cutoff can reach a
ratio, because this module is never handed anything but M080's output.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from math import gcd

from empirical_platform.decision_candidate.operator_asserted_round_trip import (
    UNREPRESENTED_ECONOMIC_COMPONENTS,
    AssertedRoundTripReport,
    PositionRoundTripEntry,
    RoundTripOutcome,
    RoundTripStatus,
    RoundTripUnassessableReason,
    build_asserted_round_trip_report,
)
from empirical_platform.decision_candidate.operator_position_ledger import (
    OperatorAssertedPositionEvent,
)

__all__ = [
    "ASSERTED_RATIO_BANNER",
    "RATIO_APPROXIMATION_DECIMAL_PLACES",
    "AssertedRoundTripRatioReport",
    "PositionRoundTripRatioEntry",
    "RatioAbsenceReason",
    "build_asserted_round_trip_ratio_report",
]

#: How many decimal places the LABELLED APPROXIMATION carries. The exact value
# is always the reduced rational; this number only ever describes the
# approximation, never the value itself.
RATIO_APPROXIMATION_DECIMAL_PLACES = 6

#: M080's own money rendering carries exactly this many decimal places at most,
# because frozen M076 caps an asserted price at six.
_MONEY_DECIMAL_PLACES = 6


class RatioAbsenceReason(StrEnum):
    """Why a position carries no ratio. Never a zero, never a break-even."""

    NO_EXIT_ASSERTED_YET = "NO_EXIT_ASSERTED_YET"
    UNRESOLVED_KNOWLEDGE_SEQUENCE = "UNRESOLVED_KNOWLEDGE_SEQUENCE"


ASSERTED_RATIO_BANNER = (
    "OPERATOR-ASSERTED ROUND-TRIP RESULT RATIO: for each position, the EXACT "
    "RATIONAL ratio of the M080 asserted round-trip result to the asserted "
    "entry cost of the SAME exited quantity, from evidence the ledger RECORDS "
    "as having been recorded by the knowledge cutoff. "
    "This is a RATIO OF ARITHMETIC ON ASSERTIONS, not a measurement of anything "
    "that happened. "
    "It is NOT a return; NOT a total return; NOT ROI; NOT profit percentage; "
    "NOT investment performance; NOT a market return; NOT a tax result; NOT "
    "verified; NOT evidence that any trade occurred or occurred at the stated "
    "price; NOT advice. "
    "It is DIMENSIONLESS because the same unspecified asserted price units "
    "appear in the numerator and the denominator of the SAME position and "
    "cancel exactly. That cancellation does NOT denominate the underlying "
    "money and does NOT establish any currency. "
    "Two ratios are ARITHMETICALLY comparable but NOT necessarily ECONOMICALLY "
    "comparable: the economic components M080 leaves unrepresented remain "
    "unrepresented here, they may differ between positions, and spread and "
    "slippage remain NOT claimed to be excluded. "
    "A partial-exit ratio covers the EXITED QUANTITY ONLY and says nothing "
    "about the position's eventual outcome. "
    "No ratio is invented for a position with no asserted exit: there is no "
    "zero, no break-even and no flat. "
    "NO aggregate, mean, distribution, best, worst or count of positive ratios "
    "is emitted, and NO monetary value is emitted at all. "
    "It is NOT annualized and NOT time-weighted. "
    "Only positions the operator chose to record are visible, so no statement "
    "about typical outcomes may be built on this. "
    "Nothing recorded after the knowledge cutoff influences any figure below."
)


def _scaled_from_money(rendered: str) -> int:
    """Invert M080's exact money rendering to its scaled integer, losslessly.

    DESIGN REVIEW D-F02. The naive inversion -- stripping the decimal point --
    is WRONG and silently right on the first example: M080 renders `100` with no
    point, `0.5` with one place and `1.000001` with six, and stripping the point
    conflates all three scales. The fraction must be right-padded to exactly six
    digits first.

    This is an inversion, never a recomputation: M080 remains the sole source of
    the arithmetic. `_money_from_scaled` is injective, so this recovers the
    original integer exactly, with no Decimal operation anywhere.
    """
    negative = rendered.startswith("-")
    digits = rendered[1:] if negative else rendered
    whole, _, fraction = digits.partition(".")
    if len(fraction) > _MONEY_DECIMAL_PLACES:
        raise AssertionError(
            f"invariant violated: M080 rendered more than {_MONEY_DECIMAL_PLACES} "
            f"decimal places: {rendered}"
        )
    scaled = int(whole + fraction.ljust(_MONEY_DECIMAL_PLACES, "0"))
    return -scaled if negative else scaled


def _reduced(numerator: int, denominator: int) -> tuple[int, int]:
    """Reduce to lowest terms with the sign carried by the numerator.

    The denominator is strictly positive on every reachable input (see the
    module docstring), so no sign normalisation of the denominator is possible
    to reach; it is asserted rather than handled.
    """
    if denominator <= 0:
        raise AssertionError(
            f"invariant violated: asserted entry cost is not positive: {denominator}"
        )
    divisor = gcd(abs(numerator), denominator)
    return numerator // divisor, denominator // divisor


def _decimal_approximation(numerator: int, denominator: int) -> tuple[str, bool]:
    """Render a labelled approximation by INTEGER division only.

    No float and no Decimal is used, so the result cannot vary with the caller's
    ambient context. Returns the rendering and whether it is EXACT for this
    entry -- design review D-F05, because `0.333333` otherwise reads as a value
    rather than a truncation.

    IMPLEMENTATION REVIEW R01, found by executing the boundary case. The first
    version rounded ROUND_HALF_EVEN, and at the NUMERIC(20,6) extreme it
    rendered `-1` -- a value the exact ratio PROVABLY CANNOT TAKE (see the
    module docstring). An `is_exact=False` flag beside it was not enough: the
    string is what a reader quotes, and `-1` reads as the total loss the bound
    forbids.

    The rounding policy is therefore TRUNCATION TOWARD ZERO, chosen
    deliberately over half-even. Truncating toward zero guarantees
    `|approximation| <= |exact value|`, so the approximation can never cross a
    bound the exact value does not reach, and can never print a magnitude the
    ledger's arithmetic cannot produce. An inexact approximation is additionally
    prefixed with `~` so the truncation travels with the value into JSON and
    into anything that quotes it, not only in a separate boolean.

    OWNER REVIEW FINDING 1. Truncation toward zero has one degenerate case the
    first version got wrong: a NON-ZERO ratio whose magnitude is below
    10^-RATIO_APPROXIMATION_DECIMAL_PLACES truncates to a quotient of zero, and
    the sign was then applied only when the quotient was non-zero. So
    `-1/2000000` -- reachable from a perfectly ordinary M076 ledger -- rendered
    `~0`, ERASING the fact that the exact value is negative. Worse, `+1/10000000`
    rendered the identical string, so a tiny gain and a tiny loss were
    indistinguishable.

    Increasing the precision would only move the boundary, not remove it, so
    that is deliberately not the fix. Instead, when the magnitude truncates
    away entirely, the renderer stops pretending to be a point value and states
    the BOUND it actually knows, which is exactly true and carries the sign
    unambiguously:

        exact < 0, |exact| < 10^-6   ->   ">-0.000001 and <0"
        exact > 0, |exact| < 10^-6   ->   ">0 and <0.000001"

    A signed zero (`~-0`) was rejected: `-0` reads as negative zero, and the
    exact ratio is never zero in this branch -- it is a small non-zero number,
    which is what the bound says. An exact zero is unaffected and still renders
    `0`, so the two cases can never be confused.
    """
    scale = 10**RATIO_APPROXIMATION_DECIMAL_PLACES
    negative = numerator < 0
    magnitude = abs(numerator)

    # Truncation toward zero: take the floor of the magnitude, never round up.
    quotient, remainder = divmod(magnitude * scale, denominator)
    exact = remainder == 0

    if quotient == 0 and numerator != 0:
        # The whole magnitude truncated away. State the bound, not a point.
        smallest = f"0.{'0' * (RATIO_APPROXIMATION_DECIMAL_PLACES - 1)}1"
        if negative:
            return f">-{smallest} and <0", False
        return f">0 and <{smallest}", False

    whole, fraction = divmod(quotient, scale)
    rendered = f"{whole}.{fraction:0{RATIO_APPROXIMATION_DECIMAL_PLACES}d}".rstrip("0").rstrip(".")
    if not rendered:
        rendered = "0"
    if negative:
        rendered = f"-{rendered}"
    return (rendered if exact else f"~{rendered}"), exact


def _render_exact(numerator: int, denominator: int) -> str:
    """The authoritative value: a reduced rational, or a bare integer."""
    if denominator == 1:
        return str(numerator)
    return f"{numerator}/{denominator}"


@dataclass(frozen=True, slots=True)
class PositionRoundTripRatioEntry:
    """One position's dimensionless ratio, or an explicit absence.

    Carries NO monetary value -- design review D-F04.
    """

    position_governance_id: str
    instrument_symbol: str
    status: RoundTripStatus
    cited_position_plan_governance_id: str | None
    opened_quantity: int
    exited_quantity: int
    still_open_quantity: int
    unaccounted_quantity: int
    ratio_numerator: int | None
    ratio_denominator: int | None
    ratio_exact: str | None
    ratio_decimal_approx: str | None
    ratio_approximation_is_exact: bool | None
    ratio_absence_reason: RatioAbsenceReason | None


@dataclass(frozen=True, slots=True)
class AssertedRoundTripRatioReport:
    """The whole report. Carries NO monetary value at any level."""

    outcome: RoundTripOutcome
    unassessable_reason: RoundTripUnassessableReason | None
    effective_as_of: datetime
    knowledge_as_of: datetime
    known_event_count: int
    visible_event_count: int
    excluded_by_effective_cutoff: int
    ratio_available_count: int
    ratio_absent_count: int
    unreconciled_count: int
    unresolved_count: int
    unrepresented_economic_components: tuple[str, ...]
    entries: tuple[PositionRoundTripRatioEntry, ...]
    limitations: tuple[str, ...]


def _ratio_entry(source: PositionRoundTripEntry) -> PositionRoundTripRatioEntry:
    """Normalize exactly one M080 entry. Never recomputes M080's arithmetic."""
    numerator: int | None = None
    denominator: int | None = None
    exact_text: str | None = None
    approx_text: str | None = None
    approx_is_exact: bool | None = None
    absence: RatioAbsenceReason | None = None

    result = source.asserted_round_trip_result
    entry_cost = source.asserted_entry_cost_for_exited_quantity

    if result is not None and entry_cost is not None:
        # Both are set together or neither is -- frozen M080 derives them under
        # one `if exited_quantity > 0`. Asserted rather than assumed:
        numerator, denominator = _reduced(
            _scaled_from_money(result), _scaled_from_money(entry_cost)
        )
        exact_text = _render_exact(numerator, denominator)
        approx_text, approx_is_exact = _decimal_approximation(numerator, denominator)
    elif source.status is RoundTripStatus.UNRESOLVED_KNOWLEDGE_SEQUENCE:
        absence = RatioAbsenceReason.UNRESOLVED_KNOWLEDGE_SEQUENCE
    else:
        absence = RatioAbsenceReason.NO_EXIT_ASSERTED_YET

    return PositionRoundTripRatioEntry(
        position_governance_id=source.position_governance_id,
        instrument_symbol=source.instrument_symbol,
        status=source.status,
        cited_position_plan_governance_id=source.cited_position_plan_governance_id,
        opened_quantity=source.opened_quantity,
        exited_quantity=source.exited_quantity,
        still_open_quantity=source.still_open_quantity,
        unaccounted_quantity=source.unaccounted_quantity,
        ratio_numerator=numerator,
        ratio_denominator=denominator,
        ratio_exact=exact_text,
        ratio_decimal_approx=approx_text,
        ratio_approximation_is_exact=approx_is_exact,
        ratio_absence_reason=absence,
    )


def _limitations(source: AssertedRoundTripReport) -> tuple[str, ...]:
    """M080's limitations, carried verbatim, plus the ones M081 itself owes.

    IMPLEMENTATION REVIEW R02, found by running the CLI end-to-end against real
    PostgreSQL. M081 originally PREPENDED
    `ASSERTED_PRICE_DENOMINATION_LIMITATION` as well as carrying M080's
    limitations verbatim -- but M080 already includes it, on every report shape
    including the withheld one, so the most important denial in the artifact was
    printed TWICE. A caveat repeated verbatim reads as a formatting bug and
    invites the reader to skim the rest.

    M080's limitations already carry it, so it is not added again here.
    """
    return (
        *source.limitations,
        "limitation: the ratio is DIMENSIONLESS only because the same "
        "unspecified asserted price units appear in its numerator and "
        "denominator for the SAME position and cancel exactly. That "
        "cancellation does NOT denominate the underlying money and does NOT "
        "establish a currency for anything",
        "limitation: two ratios are ARITHMETICALLY comparable but NOT "
        "necessarily ECONOMICALLY comparable. The unrepresented economic "
        "components above may differ between positions, and spread and slippage "
        "remain not separately attributable, so a larger ratio means only that "
        "the operator's asserted prices imply a larger arithmetic ratio",
        "limitation: a partial-exit ratio covers the EXITED QUANTITY ONLY. Its "
        "denominator is the asserted entry cost of exactly that quantity, never "
        "of the whole position, and it says nothing about the eventual outcome "
        "of the quantity still open",
        "limitation: the exact reduced rational is the authoritative value. Any "
        f"decimal shown is an APPROXIMATION to "
        f"{RATIO_APPROXIMATION_DECIMAL_PLACES} places, computed by integer "
        "division and TRUNCATED TOWARD ZERO so that it can never show a "
        "magnitude larger than the exact value, and it is prefixed with '~' "
        "whenever it is not exact",
        "limitation: NO monetary value is emitted anywhere in this report: no "
        "field is named, typed or labelled as money, and no monetary total can "
        "be formed from what is here. This is a SEMANTIC boundary, NOT a "
        "confidentiality one -- the ratio is reduced to lowest terms, and when "
        "the underlying scaled operands are already coprime the reduced pair "
        "coincides with them, so monetary magnitude is NOT promised to be "
        "unrecoverable. Run M080 for the money, where the denomination "
        "limitation travels with it",
        "limitation: NO aggregate, mean, median, distribution, best, worst or "
        "count of positive ratios is emitted. Averaging these would weight a "
        "one-unit exit equally with a ten-thousand-unit exit, and a "
        "value-weighted average would require summing money across unspecified "
        "denominations, which M080 forbids",
        "limitation: only positions the operator chose to record are visible at "
        "all, so no statement about typical or expected outcomes may be built "
        "on this report",
        "limitation: no ratio is annualized and none is time-weighted; holding "
        "period is not represented",
    )


def build_asserted_round_trip_ratio_report(
    *,
    events: tuple[OperatorAssertedPositionEvent, ...],
    effective_as_of: datetime,
    knowledge_as_of: datetime,
    ledger_available: bool = True,
) -> AssertedRoundTripRatioReport:
    """Build the ratio report at `(effective_as_of, knowledge_as_of)`.

    Delegates every temporal and lifecycle decision to frozen M080 and adds
    exactly one thing: the ratio. The M079 knowledge-time firewall is inherited
    structurally -- there is no code path here that sees an event M080 did not
    already filter.
    """
    source = build_asserted_round_trip_report(
        events=events,
        effective_as_of=effective_as_of,
        knowledge_as_of=knowledge_as_of,
        ledger_available=ledger_available,
    )

    entries = tuple(_ratio_entry(entry) for entry in source.entries)
    available = sum(1 for entry in entries if entry.ratio_exact is not None)

    return AssertedRoundTripRatioReport(
        outcome=source.outcome,
        unassessable_reason=source.unassessable_reason,
        effective_as_of=source.effective_as_of,
        knowledge_as_of=source.knowledge_as_of,
        known_event_count=source.known_event_count,
        visible_event_count=source.visible_event_count,
        excluded_by_effective_cutoff=source.excluded_by_effective_cutoff,
        ratio_available_count=available,
        ratio_absent_count=len(entries) - available,
        unreconciled_count=source.unreconciled_count,
        unresolved_count=source.unresolved_count,
        unrepresented_economic_components=UNREPRESENTED_ECONOMIC_COMPONENTS,
        entries=entries,
        limitations=_limitations(source),
    )
