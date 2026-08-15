"""MILESTONE-080 -- Operator-asserted round-trip result. Pure, I/O-free.

WHAT THIS IS. The arithmetic implied by the operator's OWN asserted prices and
quantities, for the quantity they assert they exited, computed from evidence
recorded by a knowledge cutoff K about what they say happened by an effective
cutoff E.

WHAT THIS IS NOT. Not broker realized profit or loss. Not verified profit. Not
an actual execution result. Not actual cash proceeds. Not investment
performance. Not a market return. Not a tax result. Not evidence that any trade
occurred or occurred at the stated price. It excludes commissions, spread,
slippage, exchange and regulatory fees, taxes, dividends, corporate actions and
financing cost -- because M076 stores none of them -- so it is NOT a complete
economic outcome, and the DIRECTION of the total omitted effect is not generally
knowable.

THE GAP THIS CLOSES. M076 validates and persists an `asserted_price` on EVERY
lifecycle event, including REDUCED and CLOSED. A repository-wide search shows
the only derivation that reads a price reads `opening.asserted_price` alone. The
asserted price of every exit is write-only data: stored, validated,
round-tripped, and read by nothing. This module reads it.

WHAT ALREADY EXISTS AND IS NOT THIS. `realized_pnl` and `profit_factor` exist in
M062, M063 and M067 -- all of them SIMULATED over historical bars in a backtest.
None touches an operator assertion. Those are a different kind of claim and this
module does not join them.

SEPARATION OF DUTIES. This module adds exactly one thing: the arithmetic.
  - the knowledge filter `recorded_at <= K` is M079's `events_known_by`
  - the effective filter and the lifecycle fold are frozen M076's
  - open vs closed is frozen M076's, never decided here
  - the plan-citation projection is M078's `cited_plan_by_position`
  - the session -> ledger join is M078's, and is OUT OF SCOPE here

NO POST-CUTOFF EVIDENCE MAY INFLUENCE ANY OUTPUT. The M079 invariant is
inherited whole and enforced the same way: `build_asserted_round_trip_report`
filters once and delegates to `_report_from_known_evidence`, which is never
given the unfiltered events and therefore cannot consult them.

THE DERIVED-CLOSED-QUANTITY HAZARD (design review T07). M076 derives a CLOSED
event's quantity at APPEND time from the full effective-time history, and
persists it. That derivation is not redone per knowledge cutoff. So a
knowledge-filtered prefix can fold COHERENTLY while its visible exit components
fail to account for the opened quantity -- for example an opening of 10 and a
close of 6 whose explanatory reduction was not recorded until later. Treating
"the fold says closed" as "the exits are complete" would report a partial number
as a whole one. This module reconciles the quantities from visible evidence
alone and reports EXIT_QUANTITY_UNRECONCILED when they disagree.

This module is pure: no I/O, no clock, no randomness, no float.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from empirical_platform.decision_candidate.operator_evidence_availability import events_known_by
from empirical_platform.decision_candidate.operator_position_ledger import (
    LedgerRejectionError,
    OperatorAssertedPositionEvent,
    OperatorPositionEventKind,
    derive_position_state,
)
from empirical_platform.decision_candidate.research_decision_follow_through import (
    cited_plan_by_position,
)

__all__ = [
    "ASSERTED_ROUND_TRIP_BANNER",
    "EXCLUDED_ECONOMIC_COMPONENTS",
    "EXCLUDED_FRICTION_COMPONENTS",
    "EXCLUDED_NON_DIRECTIONAL_COMPONENTS",
    "AssertedRoundTripReport",
    "PositionRoundTripEntry",
    "RoundTripOutcome",
    "RoundTripStatus",
    "RoundTripUnassessableReason",
    "build_asserted_round_trip_report",
]

ASSERTED_ROUND_TRIP_BANNER = (
    "arithmetic over the operator's OWN asserted prices and quantities, for the "
    "quantity they assert they exited, from evidence the ledger RECORDS as having been "
    "recorded by the knowledge cutoff about what it says happened by the effective "
    "cutoff. This is ARITHMETIC ON ASSERTIONS, not a measurement of anything that "
    "happened. NOT broker realized profit or loss; NOT verified profit; NOT an actual "
    "execution result; NOT actual cash proceeds; NOT investment performance; NOT a "
    "market return; NOT a tax result; NOT evidence that any trade occurred or occurred "
    "at the stated price; NOT advice. It EXCLUDES commissions, spread, slippage, "
    "exchange and regulatory fees, taxes, dividends, corporate actions and financing "
    "cost, because the ledger stores none of them -- so this is NOT a complete "
    "economic outcome. The DIRECTION of the total omitted effect is NOT generally "
    "knowable: frictions such as commissions, spread, slippage and fees would "
    "normally reduce a raw result, while dividends, corporate actions and tax "
    "effects can move the real economic outcome in either direction. No result is "
    "computed for a still-open quantity, because no market price exists here. "
    "Nothing recorded after the knowledge cutoff influences any figure below."
)

#: Named individually rather than summarised, so no reader has to infer which
# components are missing. Design review H08.
#
# OWNER REVIEW FINDING 2. This was previously called EXCLUDED_COST_COMPONENTS and
# the artifact claimed every omitted item was a cost, so every result was
# "systematically more favourable" than reality. That claim is FALSE: a dividend
# on a long position can raise the real outcome, corporate actions can move it
# either way, and tax effects are jurisdiction- and context-dependent. The list
# is therefore named for what it actually contains -- economic components -- and
# the two groups are separated so the honest statement can be made about each.
EXCLUDED_ECONOMIC_COMPONENTS = (
    "commissions",
    "spread",
    "slippage",
    "exchange and regulatory fees",
    "taxes",
    "dividends",
    "corporate actions",
    "financing and borrow cost",
)

#: Frictions: omitting these makes a raw result look better than reality.
EXCLUDED_FRICTION_COMPONENTS = (
    "commissions",
    "spread",
    "slippage",
    "exchange and regulatory fees",
    "financing and borrow cost",
)

#: Components whose omission has NO generally knowable direction.
EXCLUDED_NON_DIRECTIONAL_COMPONENTS = (
    "taxes",
    "dividends",
    "corporate actions",
)


class RoundTripStatus(StrEnum):
    """What the knowledge-visible evidence supports for one position key."""

    #: Opened, with nothing exited by the effective cutoff as recorded by the
    #: knowledge cutoff. NO arithmetic is emitted -- deliberately not a zero,
    #: which would read as break-even.
    NO_EXIT_ASSERTED_YET = "NO_EXIT_ASSERTED_YET"
    #: Some quantity exited, the position still open. The arithmetic covers the
    #: EXITED quantity only and is never extrapolated to the open remainder.
    PARTIAL_EXIT_ASSERTED = "PARTIAL_EXIT_ASSERTED"
    #: Closed, and the visible exit quantities reconcile exactly to the opened
    #: quantity.
    FULLY_EXITED_ASSERTED = "FULLY_EXITED_ASSERTED"
    #: The visible exit components do not account for the opened quantity. See
    #: the module docstring: this is reachable through a coherent fold, and is a
    #: knowledge state rather than corruption.
    EXIT_QUANTITY_UNRECONCILED = "EXIT_QUANTITY_UNRECONCILED"
    #: The evidence recorded by the cutoff does not fold. M079's word, carried
    #: through unchanged: from that evidence alone it cannot be known whether
    #: this is temporary incompleteness or ledger incoherence.
    UNRESOLVED_KNOWLEDGE_SEQUENCE = "UNRESOLVED_KNOWLEDGE_SEQUENCE"


class RoundTripOutcome(StrEnum):
    """Closed vocabulary for the report as a whole."""

    ROUND_TRIP_REPORT_AVAILABLE = "ROUND_TRIP_REPORT_AVAILABLE"
    #: Nothing had been recorded by the knowledge cutoff. Distinct from "nothing
    #: happened" -- the ledger was simply silent at that moment.
    NO_EVIDENCE_RECORDED_BY_KNOWLEDGE_CUTOFF = "NO_EVIDENCE_RECORDED_BY_KNOWLEDGE_CUTOFF"
    NOT_ASSESSABLE = "NOT_ASSESSABLE"


class RoundTripUnassessableReason(StrEnum):
    """Why the report was withheld. Absence is never rendered as a pass."""

    LEDGER_UNAVAILABLE = "LEDGER_UNAVAILABLE"


#: M076 validates that an asserted price carries at most this many decimal
# places, so every persisted price is an exact integer multiple of 10**-6.
_PRICE_SCALE_EXPONENT = 6
_PRICE_SCALE = 10**_PRICE_SCALE_EXPONENT


def _scaled_price(price: Decimal) -> int:
    """`price` expressed exactly as an integer count of 10**-6 units.

    OWNER REVIEW FINDING 1. This conversion is deliberately built from the
    Decimal's own digit tuple rather than from arithmetic, because every
    Decimal operation -- multiplication, division, `scaleb`, even `normalize`
    -- is evaluated under the AMBIENT context and silently rounds to its
    precision. `as_tuple()` is pure data and is context-free.

    Frozen M076 caps the scale at six decimal places, so `exponent >= -6` and
    the shift below is a non-negative integer power: the result is exact for
    every persistence-valid price.
    """
    sign, digits, exponent = price.as_tuple()
    if not isinstance(exponent, int):  # NaN / Infinity carry a string exponent
        raise AssertionError(f"invariant violated: asserted price is not finite: {price}")
    shift = exponent + _PRICE_SCALE_EXPONENT
    if shift < 0:
        raise AssertionError(
            "invariant violated: frozen M076 admits at most "
            f"{_PRICE_SCALE_EXPONENT} decimal places, got {-exponent} in {price}"
        )
    # Scaling by appending zero digits rather than multiplying by a power keeps
    # the operation unambiguously integral -- `int ** int` is typed `Any`,
    # because a negative exponent would yield a float, and `shift` is proven
    # non-negative just above.
    unscaled = int("".join(str(digit) for digit in digits) + "0" * shift)
    return -unscaled if sign else unscaled


def _money_from_scaled(scaled: int) -> str:
    """Canonical signed decimal string from an exact 10**-6-scaled integer.

    OWNER REVIEW FINDING 1. The previous implementation rendered through
    `Decimal.normalize()`, which is context-sensitive: an exact value carrying
    more than the ambient precision (28 significant digits by default) was
    silently re-rounded on the way out, so even exact arithmetic could not have
    been rendered faithfully. This function performs no Decimal operation at
    all -- it is integer division and string formatting, so it cannot round.

    The output matches frozen M076's `format(value.normalize(), "f")` idiom for
    every value both can express: trailing fractional zeros are stripped, the
    point disappears when the fraction is empty, and no exponent form is ever
    produced. Negative zero is impossible by construction rather than by guard,
    because the sign is taken from the integer.
    """
    sign = "-" if scaled < 0 else ""
    whole, fraction = divmod(abs(scaled), _PRICE_SCALE)
    rendered_fraction = f"{fraction:0{_PRICE_SCALE_EXPONENT}d}".rstrip("0")
    if rendered_fraction:
        return f"{sign}{whole}.{rendered_fraction}"
    return f"{sign}{whole}"


@dataclass(frozen=True, slots=True)
class PositionRoundTripEntry:
    """One position key's asserted round-trip arithmetic.

    Every monetary field is a canonical string, never a float, and every one is
    arithmetic over operator assertions rather than a measurement.
    """

    position_governance_id: str
    instrument_symbol: str
    status: RoundTripStatus
    #: What the operator's OPENED event cited, projected by M078. Reported as
    #: metadata only: M080 makes NO claim that this position belongs to any
    #: research session, which is M078's question and M078's authority.
    cited_position_plan_governance_id: str | None
    opened_quantity: int
    exited_quantity: int
    still_open_quantity: int
    #: opened - exited - still_open. Non-zero only in the unreconciled state.
    unaccounted_quantity: int
    asserted_entry_price: str | None
    #: exited_quantity x asserted entry price.
    asserted_entry_cost_for_exited_quantity: str | None
    #: sum over visible exits of (quantity x that exit's asserted price).
    asserted_exit_consideration: str | None
    #: exit consideration - entry cost for the exited quantity. NOT P&L.
    asserted_round_trip_result: str | None
    exit_event_count: int
    visible_event_count: int
    #: M076's own rejection reason for the knowledge-filtered fold, when it does
    #: not fold. Taken only from the filtered attempt, so it cannot leak.
    rejection_reason: str | None


@dataclass(frozen=True, slots=True)
class AssertedRoundTripReport:
    """The whole report at one (effective, knowledge) cutoff pair.

    Every field is a function of the evidence recorded by the knowledge cutoff
    and of the two cutoffs themselves. There is deliberately no total-ledger
    count and no count of assertions hidden by the knowledge cutoff: both would
    be functions of post-cutoff rows, which is exactly what M079 froze out.

    There is also deliberately NO aggregate result across positions, no return
    percentage and no win rate. An aggregate implies a performance claim, which
    this milestone does not have the authority to make.
    """

    outcome: RoundTripOutcome
    unassessable_reason: RoundTripUnassessableReason | None
    effective_as_of: datetime
    knowledge_as_of: datetime
    known_event_count: int
    visible_event_count: int
    excluded_by_effective_cutoff: int
    no_exit_count: int
    partial_exit_count: int
    fully_exited_count: int
    unreconciled_count: int
    unresolved_count: int
    excluded_economic_components: tuple[str, ...] = EXCLUDED_ECONOMIC_COMPONENTS
    entries: tuple[PositionRoundTripEntry, ...] = ()
    limitations: tuple[str, ...] = field(default_factory=tuple)


def _entry_order(entry: PositionRoundTripEntry) -> tuple[str, str]:
    return (entry.instrument_symbol, entry.position_governance_id)


def _group_by_position(
    events: tuple[OperatorAssertedPositionEvent, ...],
) -> dict[str, tuple[OperatorAssertedPositionEvent, ...]]:
    grouped: dict[str, list[OperatorAssertedPositionEvent]] = {}
    for event in events:
        grouped.setdefault(event.position_governance_id, []).append(event)
    return {key: tuple(value) for key, value in grouped.items()}


def _opening_of(
    events: tuple[OperatorAssertedPositionEvent, ...],
) -> OperatorAssertedPositionEvent:
    """The single OPENED event of a key that folded successfully.

    A folded key always has exactly one. The invariant is asserted rather than
    silently tolerated -- M079's R01 lesson, where a `continue` on a supposedly
    impossible branch could have dropped a position with no entry and no count.
    """
    for event in events:
        if event.kind is OperatorPositionEventKind.OPENED:
            return event
    raise AssertionError(
        "invariant violated: a key that folded through M076 must carry exactly one OPENED event"
    )


def _entry_for_key(
    *,
    key: str,
    key_events: tuple[OperatorAssertedPositionEvent, ...],
    effective_as_of: datetime,
    cited_plan: str | None,
) -> PositionRoundTripEntry:
    """Evaluate ONE position key from its knowledge- and effective-visible events."""
    symbol = key_events[0].instrument_symbol
    try:
        state = derive_position_state(events=key_events, as_of=effective_as_of)
    except LedgerRejectionError as failure:
        # The evidence recorded by this cutoff does not fold. Whether it would
        # fold once more evidence is recorded is UNKNOWABLE here, and answering
        # it would mean reading assertions recorded after the cutoff.
        return PositionRoundTripEntry(
            position_governance_id=key,
            instrument_symbol=symbol,
            status=RoundTripStatus.UNRESOLVED_KNOWLEDGE_SEQUENCE,
            cited_position_plan_governance_id=cited_plan,
            opened_quantity=0,
            exited_quantity=0,
            still_open_quantity=0,
            unaccounted_quantity=0,
            asserted_entry_price=None,
            asserted_entry_cost_for_exited_quantity=None,
            asserted_exit_consideration=None,
            asserted_round_trip_result=None,
            exit_event_count=0,
            visible_event_count=len(key_events),
            rejection_reason=failure.reason.value,
        )

    positions = (*state.open_positions, *state.closed_positions)
    if not positions:
        raise AssertionError(
            "invariant violated: a non-empty, effective-filtered single-key event group "
            "must fold to exactly one position"
        )
    position = positions[0]

    opening = _opening_of(key_events)
    exits = tuple(
        event
        for event in key_events
        if event.kind in (OperatorPositionEventKind.REDUCED, OperatorPositionEventKind.CLOSED)
    )
    exited_quantity = sum(event.quantity for event in exits)
    still_open = position.open_quantity
    opened_quantity = opening.quantity
    unaccounted = opened_quantity - exited_quantity - still_open

    if unaccounted != 0:
        status = RoundTripStatus.EXIT_QUANTITY_UNRECONCILED
    elif exited_quantity == 0:
        status = RoundTripStatus.NO_EXIT_ASSERTED_YET
    elif position.is_open:
        status = RoundTripStatus.PARTIAL_EXIT_ASSERTED
    else:
        status = RoundTripStatus.FULLY_EXITED_ASSERTED

    entry_price_scaled = _scaled_price(opening.asserted_price)
    if exited_quantity > 0:
        # OWNER REVIEW FINDING 1. Every monetary quantity here is an integer
        # multiple of 10**-6, because M076 caps the price scale at six decimal
        # places and quantities are `int`. So the whole computation is carried
        # in Python integers, which are arbitrary-precision and, unlike Decimal,
        # entirely independent of the ambient context's precision and rounding
        # mode. Nothing here can round.
        entry_cost_scaled = exited_quantity * entry_price_scaled
        consideration_scaled = sum(
            event.quantity * _scaled_price(event.asserted_price) for event in exits
        )
        result_scaled = consideration_scaled - entry_cost_scaled
        entry_cost_text: str | None = _money_from_scaled(entry_cost_scaled)
        consideration_text: str | None = _money_from_scaled(consideration_scaled)
        result_text: str | None = _money_from_scaled(result_scaled)
    else:
        # Nothing exited means NO arithmetic, not a zero: a zero would read as
        # break-even. Design review E16.
        entry_cost_text = None
        consideration_text = None
        result_text = None

    return PositionRoundTripEntry(
        position_governance_id=key,
        instrument_symbol=symbol,
        status=status,
        cited_position_plan_governance_id=cited_plan,
        opened_quantity=opened_quantity,
        exited_quantity=exited_quantity,
        still_open_quantity=still_open,
        unaccounted_quantity=unaccounted,
        asserted_entry_price=_money_from_scaled(entry_price_scaled),
        asserted_entry_cost_for_exited_quantity=entry_cost_text,
        asserted_exit_consideration=consideration_text,
        asserted_round_trip_result=result_text,
        exit_event_count=len(exits),
        visible_event_count=len(key_events),
        rejection_reason=None,
    )


def _report_from_known_evidence(
    *,
    known: tuple[OperatorAssertedPositionEvent, ...],
    effective_as_of: datetime,
    knowledge_as_of: datetime,
) -> AssertedRoundTripReport:
    """Build the report from evidence recorded by the cutoff, and nothing else.

    This function is deliberately never given the unfiltered event set. It is
    the structural form of the M079 invariant inherited by M080: post-cutoff
    evidence cannot influence any output because it is not reachable from here.
    """
    visible = tuple(e for e in known if e.event_timestamp <= effective_as_of)
    excluded_by_effective = len(known) - len(visible)

    limitations: list[str] = [
        "every figure here is arithmetic over what the operator ASSERTED, not a broker "
        "record, not a verified fill, and not evidence that any trade occurred",
        "the result EXCLUDES these economic components, none of which the ledger "
        "stores: " + ", ".join(EXCLUDED_ECONOMIC_COMPONENTS) + ". It is therefore NOT a "
        "complete economic outcome",
        "the DIRECTION of the total omitted effect is NOT generally knowable: "
        + ", ".join(EXCLUDED_FRICTION_COMPONENTS)
        + " are frictions whose omission would normally make a raw result look better "
        "than reality, but "
        + ", ".join(EXCLUDED_NON_DIRECTIONAL_COMPONENTS)
        + " can move the real economic outcome in either direction, so no universal "
        "bound in either direction is claimed",
        "assertions recorded after the knowledge cutoff are excluded and influence "
        "nothing above; that exclusion is the firewall's own effect, not an absence of "
        "activity. By construction this report cannot say how many there were, because "
        "counting them would require reading the very evidence the cutoff excludes",
        "no result is computed for a still-open quantity: the platform holds no "
        "authoritative current market price, so no unrealized figure is invented",
        "no aggregate across positions, no return percentage and no win rate is "
        "emitted; each is a performance claim this milestone has no authority to make",
    ]
    if excluded_by_effective:
        limitations.append(
            f"{excluded_by_effective} assertion(s) were recorded by the knowledge cutoff "
            "but are stamped after the effective cutoff, and are excluded"
        )
    if knowledge_as_of < effective_as_of:
        limitations.append(
            f"the knowledge cutoff ({knowledge_as_of.isoformat()}) precedes the effective "
            f"cutoff ({effective_as_of.isoformat()}); this asks what was recorded then "
            "about what had happened by the later moment, which is meaningful but easy "
            "to misread"
        )

    if not known:
        return AssertedRoundTripReport(
            outcome=RoundTripOutcome.NO_EVIDENCE_RECORDED_BY_KNOWLEDGE_CUTOFF,
            unassessable_reason=None,
            effective_as_of=effective_as_of,
            knowledge_as_of=knowledge_as_of,
            known_event_count=0,
            visible_event_count=0,
            excluded_by_effective_cutoff=0,
            no_exit_count=0,
            partial_exit_count=0,
            fully_exited_count=0,
            unreconciled_count=0,
            unresolved_count=0,
            limitations=tuple(limitations),
        )

    # M078's public lineage projection, over the SAME visible events. M080 makes
    # no claim that a citation links this position to any research session.
    cited = cited_plan_by_position(visible)

    entries = tuple(
        sorted(
            (
                _entry_for_key(
                    key=key,
                    key_events=key_events,
                    effective_as_of=effective_as_of,
                    cited_plan=cited.get(key),
                )
                for key, key_events in _group_by_position(visible).items()
            ),
            key=_entry_order,
        )
    )

    def count(status: RoundTripStatus) -> int:
        return sum(1 for entry in entries if entry.status is status)

    if any(e.status is RoundTripStatus.EXIT_QUANTITY_UNRECONCILED for e in entries):
        limitations.append(
            "one or more positions have exit quantities that do not account for the "
            "quantity opened, from the evidence recorded by this cutoff. The result "
            "shown for them covers only the exits actually visible here and must not be "
            "read as the whole position's result"
        )
    if any(e.status is RoundTripStatus.PARTIAL_EXIT_ASSERTED for e in entries):
        limitations.append(
            "one or more positions are only partly exited; their result covers the "
            "exited quantity alone and is not extrapolated to the quantity still open"
        )
    if any(e.status is RoundTripStatus.UNRESOLVED_KNOWLEDGE_SEQUENCE for e in entries):
        limitations.append(
            "one or more positions have evidence that does not fold at this knowledge "
            "cutoff; from the evidence recorded by this cutoff alone it cannot be known "
            "whether that is temporary incompleteness or underlying ledger incoherence, "
            "and no arithmetic is attempted for them"
        )

    return AssertedRoundTripReport(
        outcome=RoundTripOutcome.ROUND_TRIP_REPORT_AVAILABLE,
        unassessable_reason=None,
        effective_as_of=effective_as_of,
        knowledge_as_of=knowledge_as_of,
        known_event_count=len(known),
        visible_event_count=len(visible),
        excluded_by_effective_cutoff=excluded_by_effective,
        no_exit_count=count(RoundTripStatus.NO_EXIT_ASSERTED_YET),
        partial_exit_count=count(RoundTripStatus.PARTIAL_EXIT_ASSERTED),
        fully_exited_count=count(RoundTripStatus.FULLY_EXITED_ASSERTED),
        unreconciled_count=count(RoundTripStatus.EXIT_QUANTITY_UNRECONCILED),
        unresolved_count=count(RoundTripStatus.UNRESOLVED_KNOWLEDGE_SEQUENCE),
        entries=entries,
        limitations=tuple(limitations),
    )


def build_asserted_round_trip_report(
    *,
    events: tuple[OperatorAssertedPositionEvent, ...],
    effective_as_of: datetime,
    knowledge_as_of: datetime,
    ledger_available: bool = True,
) -> AssertedRoundTripReport:
    """Build the asserted round-trip report at `(effective_as_of, knowledge_as_of)`.

    Both cutoffs are required, inclusive, and must be timezone-aware. Neither
    has a default: a default on either dimension would silently choose an
    epistemic stance on the caller's behalf.

    `events` is read exactly once, by M079's `events_known_by`. Everything after
    that point sees only the survivors, so two ledgers agreeing on
    `recorded_at <= K` produce identical reports however much they differ
    afterwards.
    """
    for label, moment in (
        ("effective_as_of", effective_as_of),
        ("knowledge_as_of", knowledge_as_of),
    ):
        if moment.tzinfo is None or moment.utcoffset() is None:
            raise ValueError(f"{label} must be timezone-aware; a naive datetime has no instant")

    if not ledger_available:
        return AssertedRoundTripReport(
            outcome=RoundTripOutcome.NOT_ASSESSABLE,
            unassessable_reason=RoundTripUnassessableReason.LEDGER_UNAVAILABLE,
            effective_as_of=effective_as_of,
            knowledge_as_of=knowledge_as_of,
            known_event_count=0,
            visible_event_count=0,
            excluded_by_effective_cutoff=0,
            no_exit_count=0,
            partial_exit_count=0,
            fully_exited_count=0,
            unreconciled_count=0,
            unresolved_count=0,
            limitations=(
                "the operator position ledger could not be read; the report is withheld "
                "rather than presented as if nothing had been recorded",
            ),
        )

    return _report_from_known_evidence(
        known=events_known_by(events, knowledge_as_of),
        effective_as_of=effective_as_of,
        knowledge_as_of=knowledge_as_of,
    )
