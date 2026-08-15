"""MILESTONE-076 -- Operator-asserted position ledger. Pure, I/O-free.

WHAT THIS IS. An append-only log of what the operator SAYS they did, and a
deterministic fold of that log into "what is held as of a timestamp". Before
this milestone the platform had 43 tables and not one modelled an operational
position: `position_plan` is a terminal sizing verdict with no lifecycle, M071
continuity carries decisions but no exposure, and the only OPEN/CLOSED concepts
in the repository live in M067/M068 historical *simulation*. Every day started
from zero.

WHAT THIS IS NOT. Not a broker record. Not a verified fill. Not an execution.
Not evidence that any trade occurred, or occurred at the stated price. Not P&L,
realized or unrealized. Not a market valuation. Not a paper-trading claim. Not
a profitability claim and not advice.

THE CENTRAL BOUNDARY. An approved `PositionPlan` is a RECOMMENDATION, not an
action, and this module never derives a position from one. Only an explicit
operator assertion -- an OPENED event -- creates a position. A plan may be cited
as what motivated the assertion, and that citation is informational: it is never
required, never validated as a precondition, and never changes how an event is
folded.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

__all__ = [
    "ASSERTED_PRICE_MAX_DECIMAL_PLACES",
    "ASSERTED_PRICE_MAX_INTEGER_DIGITS",
    "OPERATOR_LEDGER_BANNER",
    "DerivedPosition",
    "DerivedPositionState",
    "LedgerRejectionError",
    "LedgerRejectionReason",
    "OperatorAssertedPositionEvent",
    "OperatorPositionEventKind",
    "derive_position_state",
    "validate_appended_event",
]

#: MILESTONE-076 owner correction (Finding 3). The persisted column is
# NUMERIC(20, 6), so a price carrying more than six decimal places could be
# silently rounded on the way to PostgreSQL -- an accepted value would then
# reload as a DIFFERENT value, breaking deterministic replay and making the
# rendered price disagree with the stored one. The domain therefore refuses any
# price persistence cannot round-trip exactly. Rejecting is chosen over
# quantizing because silently altering a number the operator asserted is itself
# a small dishonesty.
ASSERTED_PRICE_MAX_DECIMAL_PLACES = 6

#: MILESTONE-076 owner correction (final). NUMERIC(20, 6) bounds the TOTAL
# precision at 20 digits, not just the scale, so at most 20 - 6 = 14 digits may
# sit left of the point. PostgreSQL states it directly: "A field with precision
# 20, scale 6 must round to an absolute value less than 10^14."
#
# Bounding the scale alone was not enough. `Decimal("100000000000000")` passed
# every domain check and was then refused by the database -- which broke M076's
# own claim that an accepted price round-trips deterministically, since a value
# that cannot be stored cannot round-trip at all.
ASSERTED_PRICE_MAX_INTEGER_DIGITS = 14

OPERATOR_LEDGER_BANNER = (
    "what the operator ASSERTED they did, and nothing more. NOT a broker record; "
    "NOT a verified fill; NOT an execution; NOT evidence that any trade occurred or "
    "occurred at the stated price; NOT realized or unrealized P&L; NOT a market "
    "valuation; NOT a paper-trading claim; NOT a profitability claim; NOT advice."
)


class OperatorPositionEventKind(StrEnum):
    """Closed vocabulary. Every member is an assertion by a human, which is why
    none of them is called EXECUTED, FILLED, or anything implying a broker."""

    OPENED = "OPENED"
    REDUCED = "REDUCED"
    CLOSED = "CLOSED"


class LedgerRejectionReason(StrEnum):
    """Closed vocabulary of why an appended event would make the ledger
    incoherent. Never silently dropped."""

    POSITION_NOT_OPEN = "POSITION_NOT_OPEN"
    POSITION_ALREADY_OPEN = "POSITION_ALREADY_OPEN"
    POSITION_ALREADY_CLOSED = "POSITION_ALREADY_CLOSED"
    REDUCTION_EXCEEDS_OPEN_QUANTITY = "REDUCTION_EXCEEDS_OPEN_QUANTITY"
    INSTRUMENT_MISMATCH_FOR_POSITION = "INSTRUMENT_MISMATCH_FOR_POSITION"
    DUPLICATE_EVENT_GOVERNANCE_ID = "DUPLICATE_EVENT_GOVERNANCE_ID"
    NON_POSITIVE_QUANTITY = "NON_POSITIVE_QUANTITY"
    NAIVE_TIMESTAMP = "NAIVE_TIMESTAMP"
    NON_POSITIVE_ASSERTED_PRICE = "NON_POSITIVE_ASSERTED_PRICE"
    #: Covers BOTH NUMERIC(20, 6) bounds -- too many decimal places, and too
    # many digits left of the point. One reason is kept rather than two because
    # the invariant is single: "exactly representable by the persisted column".
    # The detail message names which bound was exceeded.
    ASSERTED_PRICE_PRECISION_EXCEEDED = "ASSERTED_PRICE_PRECISION_EXCEEDED"


class LedgerRejectionError(Exception):
    """Raised when appending an event would make the ledger incoherent.

    Deliberately a plain exception rather than a slotted dataclass:
    `@dataclass(slots=True)` rebuilds the class object, which breaks zero-arg
    `super()` resolution in an Exception subclass and makes the error
    unraisable in some paths. Integration testing caught exactly that.
    """

    def __init__(self, *, reason: LedgerRejectionReason, detail: str) -> None:
        super().__init__(f"{reason.value}: {detail}")
        self.reason = reason
        self.detail = detail


@dataclass(frozen=True, slots=True)
class OperatorAssertedPositionEvent:
    """One immutable assertion.

    `event_timestamp` is when the operator says it happened and is the ONLY
    field that drives the fold. `recorded_at` is when it was written down and
    is audit metadata that never affects derived state.

    For CLOSED, `quantity` is derived by the ledger rather than supplied, so a
    supplied quantity can never disagree with the open quantity.
    """

    governance_id: str
    runtime_id: str
    position_governance_id: str
    instrument_symbol: str
    kind: OperatorPositionEventKind
    quantity: int
    asserted_price: Decimal
    event_timestamp: datetime
    recorded_at: datetime
    source_position_plan_governance_id: str | None = None
    note: str | None = None

    def __post_init__(self) -> None:
        # Finding 2: the whole temporal model -- inclusive `as_of`, exclusion of
        # later events, TIMESTAMPTZ persistence -- depends on an unambiguous
        # instant. A naive datetime has no instant, and comparing one against an
        # aware one raises at runtime, so it is refused at the boundary.
        for label, moment in (
            ("event_timestamp", self.event_timestamp),
            ("recorded_at", self.recorded_at),
        ):
            if moment.tzinfo is None or moment.utcoffset() is None:
                raise LedgerRejectionError(
                    reason=LedgerRejectionReason.NAIVE_TIMESTAMP,
                    detail=(
                        f"{label} must be timezone-aware; got a naive datetime {moment.isoformat()}"
                    ),
                )
        # Finding 3: positivity is a domain invariant, not something the domain
        # leaves to a database CHECK constraint.
        if self.asserted_price <= 0:
            raise LedgerRejectionError(
                reason=LedgerRejectionReason.NON_POSITIVE_ASSERTED_PRICE,
                detail=f"asserted_price must be > 0, got {self.asserted_price}",
            )
        exponent = self.asserted_price.as_tuple().exponent
        if not isinstance(exponent, int):
            raise LedgerRejectionError(
                reason=LedgerRejectionReason.NON_POSITIVE_ASSERTED_PRICE,
                detail=f"asserted_price must be finite, got {self.asserted_price}",
            )
        integer_digits = max(0, len(self.asserted_price.as_tuple().digits) + exponent)
        if integer_digits > ASSERTED_PRICE_MAX_INTEGER_DIGITS:
            raise LedgerRejectionError(
                reason=LedgerRejectionReason.ASSERTED_PRICE_PRECISION_EXCEEDED,
                detail=(
                    f"asserted_price {self.asserted_price} needs {integer_digits} digits "
                    f"left of the point; persistence is NUMERIC(20, "
                    f"{ASSERTED_PRICE_MAX_DECIMAL_PLACES}) and admits at most "
                    f"{ASSERTED_PRICE_MAX_INTEGER_DIGITS}"
                ),
            )
        if -exponent > ASSERTED_PRICE_MAX_DECIMAL_PLACES:
            raise LedgerRejectionError(
                reason=LedgerRejectionReason.ASSERTED_PRICE_PRECISION_EXCEEDED,
                detail=(
                    f"asserted_price {self.asserted_price} carries {-exponent} decimal "
                    f"places; persistence is NUMERIC(20, "
                    f"{ASSERTED_PRICE_MAX_DECIMAL_PLACES}) and could not round-trip it "
                    "exactly"
                ),
            )
        if (
            self.kind
            in (
                OperatorPositionEventKind.OPENED,
                OperatorPositionEventKind.REDUCED,
            )
            and self.quantity <= 0
        ):
            raise LedgerRejectionError(
                reason=LedgerRejectionReason.NON_POSITIVE_QUANTITY,
                detail=f"{self.kind.value} requires quantity > 0, got {self.quantity}",
            )
        if self.quantity < 0:
            raise LedgerRejectionError(
                reason=LedgerRejectionReason.NON_POSITIVE_QUANTITY,
                detail=f"quantity must never be negative, got {self.quantity}",
            )


@dataclass(frozen=True, slots=True)
class DerivedPosition:
    """One position key's state at an `as_of`. Every value is derived from
    operator assertions; none is a market observation."""

    position_governance_id: str
    instrument_symbol: str
    open_quantity: int
    is_open: bool
    asserted_entry_price: str
    #: quantity x asserted entry price. NOT a market value and NOT P&L -- it is
    # what the operator said they committed at the price they said they paid.
    asserted_open_notional: str
    opened_at: datetime
    last_event_at: datetime
    event_count: int


@dataclass(frozen=True, slots=True)
class DerivedPositionState:
    """The whole derived state at one `as_of`."""

    as_of: datetime
    open_positions: tuple[DerivedPosition, ...]
    closed_positions: tuple[DerivedPosition, ...]
    total_open_quantity: int
    total_asserted_open_notional: str
    considered_event_count: int
    excluded_future_event_count: int
    limitations: tuple[str, ...] = field(default_factory=tuple)


def _money(value: Decimal) -> str:
    """Canonical monetary string.

    PostgreSQL NUMERIC(20, 6) round-trips `Decimal("750")` as
    `Decimal("750.000000")`. Those compare equal, but `str()` does not, so the
    same position rendered from memory and from the database produced different
    text. `normalize()` alone is worse -- it yields `7.5E+2` -- so the exponent
    is expanded with `format(..., "f")`.
    """
    normalized = value.normalize()
    return format(normalized, "f")


def _order_key(event: OperatorAssertedPositionEvent) -> tuple[datetime, str]:
    """Total order. `governance_id` is unique, so timestamp ties are resolved
    deterministically rather than arbitrarily."""
    return (event.event_timestamp, event.governance_id)


def _fold_one_position(
    events: tuple[OperatorAssertedPositionEvent, ...],
) -> tuple[int, bool, OperatorAssertedPositionEvent]:
    """Fold one position key's ordered events into (open_quantity, is_open,
    opening_event). Raises LedgerRejectionError on any impossible transition.

    This is the single source of truth for coherence: appending re-folds the
    ENTIRE resulting sequence, so a back-dated event that would invalidate a
    later one is rejected rather than silently accepted.
    """
    quantity = 0
    opened = False
    closed = False
    opening: OperatorAssertedPositionEvent | None = None

    for event in events:
        if opening is not None and event.instrument_symbol != opening.instrument_symbol:
            raise LedgerRejectionError(
                reason=LedgerRejectionReason.INSTRUMENT_MISMATCH_FOR_POSITION,
                detail=(
                    f"position {event.position_governance_id} opened on "
                    f"{opening.instrument_symbol} but event {event.governance_id} cites "
                    f"{event.instrument_symbol}"
                ),
            )
        if event.kind is OperatorPositionEventKind.OPENED:
            if opened and not closed:
                raise LedgerRejectionError(
                    reason=LedgerRejectionReason.POSITION_ALREADY_OPEN,
                    detail=f"position {event.position_governance_id} is already open",
                )
            if closed:
                raise LedgerRejectionError(
                    reason=LedgerRejectionReason.POSITION_ALREADY_CLOSED,
                    detail=(
                        f"position {event.position_governance_id} was closed; a new entry "
                        "requires a new position_governance_id"
                    ),
                )
            opened = True
            opening = event
            quantity = event.quantity
        elif event.kind is OperatorPositionEventKind.REDUCED:
            if not opened or closed:
                raise LedgerRejectionError(
                    reason=LedgerRejectionReason.POSITION_NOT_OPEN,
                    detail=f"position {event.position_governance_id} is not open to reduce",
                )
            if event.quantity > quantity:
                raise LedgerRejectionError(
                    reason=LedgerRejectionReason.REDUCTION_EXCEEDS_OPEN_QUANTITY,
                    detail=(
                        f"reduction of {event.quantity} exceeds open quantity {quantity} "
                        f"for position {event.position_governance_id}"
                    ),
                )
            quantity -= event.quantity
            if quantity == 0:
                # A reduction that lands exactly on zero closes the position.
                closed = True
        else:  # CLOSED
            if not opened or closed:
                raise LedgerRejectionError(
                    reason=(
                        LedgerRejectionReason.POSITION_ALREADY_CLOSED
                        if closed
                        else LedgerRejectionReason.POSITION_NOT_OPEN
                    ),
                    detail=f"position {event.position_governance_id} is not open to close",
                )
            quantity = 0
            closed = True

    if opening is None:
        raise LedgerRejectionError(
            reason=LedgerRejectionReason.POSITION_NOT_OPEN,
            detail="no OPENED event exists for this position",
        )
    return quantity, not closed, opening


def _group(
    events: tuple[OperatorAssertedPositionEvent, ...],
) -> dict[str, tuple[OperatorAssertedPositionEvent, ...]]:
    grouped: dict[str, list[OperatorAssertedPositionEvent]] = {}
    for event in sorted(events, key=_order_key):
        grouped.setdefault(event.position_governance_id, []).append(event)
    return {key: tuple(value) for key, value in grouped.items()}


def validate_appended_event(
    *,
    existing: tuple[OperatorAssertedPositionEvent, ...],
    candidate: OperatorAssertedPositionEvent,
) -> int:
    """Validate that appending `candidate` keeps the ledger coherent, and return
    the effective quantity the event carries (derived for CLOSED).

    The whole resulting sequence for that position key is re-folded in timestamp
    order, so a back-dated event that would invalidate a later one is rejected.
    """
    if any(event.governance_id == candidate.governance_id for event in existing):
        raise LedgerRejectionError(
            reason=LedgerRejectionReason.DUPLICATE_EVENT_GOVERNANCE_ID,
            detail=f"event {candidate.governance_id} has already been recorded",
        )

    same_key = tuple(
        event
        for event in existing
        if event.position_governance_id == candidate.position_governance_id
    )
    if candidate.kind is OperatorPositionEventKind.CLOSED:
        # Derive the closing quantity from the state immediately before this
        # event, so a supplied value can never disagree with reality.
        prior = tuple(e for e in same_key if _order_key(e) < _order_key(candidate))
        remaining = _fold_one_position(tuple(sorted(prior, key=_order_key)))[0] if prior else 0
        candidate = OperatorAssertedPositionEvent(
            governance_id=candidate.governance_id,
            runtime_id=candidate.runtime_id,
            position_governance_id=candidate.position_governance_id,
            instrument_symbol=candidate.instrument_symbol,
            kind=candidate.kind,
            quantity=remaining,
            asserted_price=candidate.asserted_price,
            event_timestamp=candidate.event_timestamp,
            recorded_at=candidate.recorded_at,
            source_position_plan_governance_id=candidate.source_position_plan_governance_id,
            note=candidate.note,
        )

    _fold_one_position(tuple(sorted((*same_key, candidate), key=_order_key)))
    return candidate.quantity


def derive_position_state(
    *,
    events: tuple[OperatorAssertedPositionEvent, ...],
    as_of: datetime,
) -> DerivedPositionState:
    """Fold operator assertions into what is held as of `as_of`.

    `as_of` is INCLUSIVE: an event stamped exactly at `as_of` is counted. Events
    after `as_of` are excluded even though their rows already exist, so a query
    about the past can never see the future.
    """
    if as_of.tzinfo is None or as_of.utcoffset() is None:
        raise LedgerRejectionError(
            reason=LedgerRejectionReason.NAIVE_TIMESTAMP,
            detail=f"as_of must be timezone-aware; got a naive datetime {as_of.isoformat()}",
        )
    considered = tuple(e for e in events if e.event_timestamp <= as_of)
    excluded = len(events) - len(considered)

    open_positions: list[DerivedPosition] = []
    closed_positions: list[DerivedPosition] = []

    for key in sorted(_group(considered)):
        ordered = _group(considered)[key]
        quantity, is_open, opening = _fold_one_position(ordered)
        notional = Decimal(quantity) * opening.asserted_price
        derived = DerivedPosition(
            position_governance_id=key,
            instrument_symbol=opening.instrument_symbol,
            open_quantity=quantity,
            is_open=is_open,
            asserted_entry_price=_money(opening.asserted_price),
            asserted_open_notional=_money(notional),
            opened_at=opening.event_timestamp,
            last_event_at=ordered[-1].event_timestamp,
            event_count=len(ordered),
        )
        (open_positions if is_open else closed_positions).append(derived)

    total_quantity = sum(p.open_quantity for p in open_positions)
    total_notional = sum((Decimal(p.asserted_open_notional) for p in open_positions), Decimal("0"))
    limitations = [
        "every value here is what the operator asserted, not a broker record or a verified fill",
        "notional is quantity x asserted entry price -- not a market value and not P&L",
    ]
    if excluded:
        limitations.append(f"{excluded} event(s) stamped after the requested as_of were excluded")
    return DerivedPositionState(
        as_of=as_of,
        open_positions=tuple(open_positions),
        closed_positions=tuple(closed_positions),
        total_open_quantity=total_quantity,
        total_asserted_open_notional=_money(total_notional),
        considered_event_count=len(considered),
        excluded_future_event_count=excluded,
        limitations=tuple(limitations),
    )
