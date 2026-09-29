"""MILESTONE-087 -- human-approved position exit: the domain.

WHAT THIS IS. A SEPARATE model for closing a long position the platform itself opened
through MILESTONE-085. It is not an M085 entry order wearing a different side:
`PaperOrderRequest` stays structurally BUY-only and is not imported, subclassed or widened
here. An exit is a `PositionExitRequest`, whose side is the single literal
`SELL_TO_CLOSE` -- not a generic SELL -- and whose quantity is never supplied by a caller:
it is the VERIFIED attributable long quantity, or the request cannot be built.

WHAT IT CAN AND CANNOT EXPRESS. An exit can only REDUCE an existing attributable long
position, to zero, in one FULL CLOSE. It cannot open a short, increase a short, close a
position the platform did not open, or close a quantity that disagrees with the entry
evidence and the broker's own position. Every one of those is a refusal in
`exit_eligibility`, and the full-close rule is repeated as a CHECK constraint by the M087
migration so that a row a caller never validated is refused by the database too.

EXACTLY ONCE, THE M085 WAY. One preview is what a human was shown; one single-use
authorization is bound to that preview's fingerprint; the broker identity
(`client_order_id`, prefix `m087-`) is DERIVED from persisted identity, never generated;
at most one active exit attempt exists per position; an ambiguous submission is
`SUBMISSION_UNKNOWN` -- a state, never a retry -- and reconciliation addresses the SAME
identity through durable, sequence-ordered rounds. The pure helpers M085 proved for
rounds (`rounds_in_order`, `consecutive_not_found_rounds`, `waiting_lower_bound_seconds`)
and its round and acknowledgement TYPES are reused as-is; nothing in M085 is modified.

POSITION CLOSED IS A VERIFIED FACT. A FILLED exit is not a closed position. The position
is closed only when the exit attempt is FILLED for its whole quantity AND a later
reconciliation verified the broker position at zero and recorded that verification
durably (`closed_position_verified_at`, `POSITION_CLOSED_VERIFIED`).

SIMULATION AND PAPER, NEVER LIVE. `ALLOWED_EXIT_ENVIRONMENTS` names SIMULATION and PAPER
(widened from SIMULATION alone by MILESTONE-089). A request binding LIVE cannot be
constructed: no `CapabilityStatus` this repository builds carries LIVE with
`enabled=True`, and no composition function anywhere builds one.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from types import MappingProxyType

from empirical_platform.decision_candidate.operator_trading_configuration import OrderType
from empirical_platform.decision_candidate.paper_execution import (
    MINIMUM_CONSECUTIVE_NOT_FOUND_OBSERVATIONS,
    MINIMUM_SECONDS_BEFORE_NOT_FOUND_COUNTS,
    BrokerAcknowledgement,
    ReconciliationRound,
    ReconciliationRoundOutcome,
    consecutive_not_found_rounds,
    rounds_in_order,
    waiting_anchor,
    waiting_lower_bound_seconds,
)
from empirical_platform.shared.brokerage.paper_time import BoundedInstant, BrokerTimeBasis

__all__ = [
    "ALLOWED_EXIT_ENVIRONMENTS",
    "ALLOWED_EXIT_TRANSITIONS",
    "BOUND_EXIT_ORDER_STATES",
    "EXIT_CLIENT_ORDER_ID_PREFIX",
    "EXIT_SEND_BOUNDARY_EVENT_TYPE",
    "EXIT_SIDE",
    "EXIT_UNSENT_EVENT_TYPES",
    "EXIT_UNSENT_FAILURE_CODES",
    "EXIT_TRANSMITTED_UNCERTAIN_FAILURE_CODES",
    "MAXIMUM_EXIT_AUTHORIZATION_VALIDITY_SECONDS",
    "POSITION_CLOSED_VERIFIED_EVENT_TYPE",
    "POSITION_NOT_ZERO_AFTER_FILL_EVENT_TYPE",
    "TERMINAL_EXIT_STATES",
    "BrokerAcknowledgement",
    "ExitAbsenceEvaluation",
    "PositionExitAttempt",
    "PositionExitAuthorization",
    "PositionExitEvent",
    "PositionExitPreview",
    "PositionExitRequest",
    "PositionExitState",
    "PositionSnapshot",
    "RealizedResult",
    "ReconciliationRound",
    "ReconciliationRoundOutcome",
    "derive_exit_client_order_id",
    "exit_absence_evaluation",
    "exit_attempt_may_have_transmitted",
    "exit_authorization_binding_refusal",
    "exit_eligibility",
    "exit_order_terms_mismatches",
    "exit_request_fingerprint",
    "exit_send_boundary_binding",
    "is_exit_transition_allowed",
    "realized_result",
]

EXIT_SIDE = "SELL_TO_CLOSE"
EXIT_CLIENT_ORDER_ID_PREFIX = "m087-"
#: The environments an exit request may bind. MILESTONE-089 widens this from SIMULATION
#: alone to SIMULATION and PAPER -- never LIVE, which no `CapabilityStatus` in this
#: repository can carry with `enabled=True` and no composition function builds. A request
#: naming LIVE still cannot be constructed: this is the one place that boundary is drawn.
ALLOWED_EXIT_ENVIRONMENTS: frozenset[str] = frozenset({"SIMULATION", "PAPER"})
#: The longest a human exit authorization stays valid, in seconds. The mandatory
#: liquidation deadline always bounds it as well.
MAXIMUM_EXIT_AUTHORIZATION_VALIDITY_SECONDS = 300
EXIT_SEND_BOUNDARY_EVENT_TYPE = "EXIT_SEND_BOUNDARY_ENTERED"
POSITION_CLOSED_VERIFIED_EVENT_TYPE = "POSITION_CLOSED_VERIFIED"
POSITION_NOT_ZERO_AFTER_FILL_EVENT_TYPE = "POSITION_NOT_ZERO_AFTER_FILL"

_MAXIMUM_IDENTIFIER_LENGTH = 64
_HEX_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_MAXIMUM_BROKER_CLIENT_ORDER_ID_LENGTH = 128

#: Failure codes and events that record "this attempt did NOT transmit". Consulted together
#: so a rewritten code cannot erase what an append-only event recorded.
EXIT_UNSENT_FAILURE_CODES: frozenset[str] = frozenset(
    {"NOT_SENT", "IDENTITY_EXISTS_UNSENT", "IDENTITY_UNRESOLVED_UNSENT"}
)
EXIT_UNSENT_EVENT_TYPES: frozenset[str] = frozenset(
    {
        "EXIT_DISPATCH_NOT_SENT",
        "EXIT_IDENTITY_OBSERVED_BEFORE_SEND",
        "EXIT_IDENTITY_LOOKUP_INCONCLUSIVE",
        "EXIT_CLIENT_ORDER_ID_COLLISION",
    }
)
EXIT_TRANSMITTED_UNCERTAIN_FAILURE_CODES: frozenset[str] = frozenset(
    {"AMBIGUOUS", "UNUSABLE_ANSWER"}
)
_POSITIVE_OBSERVATION_EVENT_TYPES: frozenset[str] = frozenset(
    {
        "EXIT_IDENTITY_OBSERVED_BEFORE_SEND",
        "EXIT_CLIENT_ORDER_ID_COLLISION",
        "EXIT_IDENTITY_OBSERVED_NOT_ATTRIBUTED",
        "EXIT_IDENTITY_COLLISION_MISMATCH",
    }
)


# ---------------------------------------------------------------------------
# Small validators (local copies: a domain module does not import M085 privates)
# ---------------------------------------------------------------------------


def _require_identifier(value: object, *, field: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    if len(value) > _MAXIMUM_IDENTIFIER_LENGTH:
        raise ValueError(f"{field} must be at most {_MAXIMUM_IDENTIFIER_LENGTH} characters")


def _require_digest(value: object, *, field: str) -> None:
    if not isinstance(value, str) or not _HEX_DIGEST.match(value):
        raise ValueError(f"{field} must be a 64-character lowercase hex digest")


def _require_aware(value: object, *, field: str) -> None:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError(f"{field} must be a timezone-aware datetime")


def _require_whole_positive(value: object, *, field: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{field} must be an int")
    if value <= 0:
        raise ValueError(f"{field} must be positive")


def _require_positive_money(value: object, *, field: str) -> None:
    if not isinstance(value, Decimal) or value.is_nan() or value.is_infinite():
        raise ValueError(f"{field} must be a finite Decimal")
    if value <= 0:
        raise ValueError(f"{field} must be positive")


def _canonical_digest(payload: dict[str, object]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _canonical_decimal(value: Decimal | None) -> str | None:
    """`2000`, `2000.0` and `2000.00000000` are one value, as PostgreSQL numeric returns them."""
    if value is None:
        return None
    normalized = value.normalize()
    return format(normalized if normalized != 0 else Decimal(0), "f")


def _instant_text(value: datetime | None) -> str | None:
    return None if value is None else value.astimezone(UTC).isoformat()


def _whole(value: Decimal | None) -> int | None:
    """A Decimal that is a whole non-negative number, as an int; anything else is None."""
    if value is None or value.is_nan() or value.is_infinite():
        return None
    if value != value.to_integral_value() or value < 0:
        return None
    return int(value)


# ---------------------------------------------------------------------------
# States
# ---------------------------------------------------------------------------


class PositionExitState(StrEnum):
    """Where one exit attempt stands on its single journey to the simulated venue."""

    DISPATCH_CLAIMED = "DISPATCH_CLAIMED"
    SUBMISSION_IN_PROGRESS = "SUBMISSION_IN_PROGRESS"
    SUBMITTED = "SUBMITTED"
    ACCEPTED = "ACCEPTED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCEL_REQUESTED = "CANCEL_REQUESTED"
    CANCELED = "CANCELED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    SUBMISSION_UNKNOWN = "SUBMISSION_UNKNOWN"


TERMINAL_EXIT_STATES: frozenset[PositionExitState] = frozenset(
    {
        PositionExitState.FILLED,
        PositionExitState.CANCELED,
        PositionExitState.REJECTED,
        PositionExitState.EXPIRED,
    }
)

#: States in which the broker acknowledged an order bound to this attempt.
BOUND_EXIT_ORDER_STATES: frozenset[PositionExitState] = frozenset(
    {
        PositionExitState.SUBMITTED,
        PositionExitState.ACCEPTED,
        PositionExitState.PARTIALLY_FILLED,
        PositionExitState.CANCEL_REQUESTED,
    }
)

#: The closed transition table, mirrored by the M087 update trigger. Same shape as M085's:
#: CANCEL_REQUESTED -> FILLED because a cancel races the venue and can lose, and
#: SUBMISSION_UNKNOWN never returns to SUBMISSION_IN_PROGRESS, so an unknown can be
#: resolved but never quietly retried into a second SELL.
ALLOWED_EXIT_TRANSITIONS: MappingProxyType[PositionExitState, frozenset[PositionExitState]] = (
    MappingProxyType(
        {
            PositionExitState.DISPATCH_CLAIMED: frozenset(
                {
                    PositionExitState.SUBMISSION_IN_PROGRESS,
                    PositionExitState.REJECTED,
                    PositionExitState.EXPIRED,
                }
            ),
            PositionExitState.SUBMISSION_IN_PROGRESS: frozenset(
                {
                    PositionExitState.SUBMITTED,
                    PositionExitState.SUBMISSION_UNKNOWN,
                    PositionExitState.REJECTED,
                }
            ),
            PositionExitState.SUBMITTED: frozenset(
                {
                    PositionExitState.ACCEPTED,
                    PositionExitState.PARTIALLY_FILLED,
                    PositionExitState.FILLED,
                    PositionExitState.CANCEL_REQUESTED,
                    PositionExitState.CANCELED,
                    PositionExitState.REJECTED,
                    PositionExitState.EXPIRED,
                    PositionExitState.SUBMISSION_UNKNOWN,
                }
            ),
            PositionExitState.ACCEPTED: frozenset(
                {
                    PositionExitState.PARTIALLY_FILLED,
                    PositionExitState.FILLED,
                    PositionExitState.CANCEL_REQUESTED,
                    PositionExitState.CANCELED,
                    PositionExitState.REJECTED,
                    PositionExitState.EXPIRED,
                    PositionExitState.SUBMISSION_UNKNOWN,
                }
            ),
            PositionExitState.PARTIALLY_FILLED: frozenset(
                {
                    PositionExitState.FILLED,
                    PositionExitState.CANCEL_REQUESTED,
                    PositionExitState.CANCELED,
                    PositionExitState.EXPIRED,
                    PositionExitState.SUBMISSION_UNKNOWN,
                }
            ),
            PositionExitState.CANCEL_REQUESTED: frozenset(
                {
                    PositionExitState.CANCELED,
                    PositionExitState.PARTIALLY_FILLED,
                    PositionExitState.FILLED,
                    PositionExitState.REJECTED,
                    PositionExitState.EXPIRED,
                    PositionExitState.SUBMISSION_UNKNOWN,
                }
            ),
            PositionExitState.SUBMISSION_UNKNOWN: frozenset(
                {
                    PositionExitState.SUBMITTED,
                    PositionExitState.ACCEPTED,
                    PositionExitState.PARTIALLY_FILLED,
                    PositionExitState.FILLED,
                    PositionExitState.CANCEL_REQUESTED,
                    PositionExitState.CANCELED,
                    PositionExitState.REJECTED,
                    PositionExitState.EXPIRED,
                }
            ),
            PositionExitState.FILLED: frozenset(),
            PositionExitState.CANCELED: frozenset(),
            PositionExitState.REJECTED: frozenset(),
            PositionExitState.EXPIRED: frozenset(),
        }
    )
)


def is_exit_transition_allowed(current: PositionExitState, target: PositionExitState) -> bool:
    if not isinstance(current, PositionExitState) or not isinstance(target, PositionExitState):
        raise ValueError("both states must be PositionExitState members")
    return target in ALLOWED_EXIT_TRANSITIONS[current]


# ---------------------------------------------------------------------------
# The position evidence and the eligibility rule
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class PositionSnapshot:
    """Everything the eligibility rule judged, frozen at one instant.

    `entry_*` comes from the ONE M085 entry attempt the position is attributed to;
    `exits_filled_quantity` is what earlier M087 exits already sold from it;
    `broker_position_quantity` is what the simulated broker holds in the symbol NOW;
    `competing_entry_attempt_ids` are other entry attempts in the same symbol that also
    hold shares, which make attribution ambiguous. Nothing here is a guess: a value the
    record does not hold is None and makes the position ineligible.
    """

    symbol: str
    entry_intent_governance_id: str
    entry_attempt_id: str | None
    entry_state: str | None
    entry_filled_quantity: Decimal | None
    entry_avg_fill_price: Decimal | None
    exits_filled_quantity: Decimal
    broker_position_quantity: int
    competing_entry_attempt_ids: tuple[str, ...]
    captured_at: datetime

    def __post_init__(self) -> None:
        if not self.symbol or self.symbol != self.symbol.strip().upper():
            raise ValueError("symbol must be upper-case and unpadded")
        _require_identifier(self.entry_intent_governance_id, field="entry_intent_governance_id")
        if isinstance(self.broker_position_quantity, bool) or not isinstance(
            self.broker_position_quantity, int
        ):
            raise ValueError("broker_position_quantity must be an int")
        if not isinstance(self.exits_filled_quantity, Decimal) or self.exits_filled_quantity < 0:
            raise ValueError("exits_filled_quantity must be a non-negative Decimal")
        _require_aware(self.captured_at, field="captured_at")

    @property
    def attributable_quantity(self) -> int | None:
        """The whole number of shares this system can PROVE it holds from this entry.

        Entry filled quantity minus what earlier exits already sold, when both are whole
        numbers and the difference is positive. None otherwise: an unprovable quantity is
        not a quantity.
        """
        filled = _whole(self.entry_filled_quantity)
        sold = _whole(self.exits_filled_quantity)
        if filled is None or sold is None:
            return None
        remaining = filled - sold
        return remaining if remaining > 0 else None

    @property
    def digest(self) -> str:
        return _canonical_digest(
            {
                "symbol": self.symbol,
                "entry_intent_governance_id": self.entry_intent_governance_id,
                "entry_attempt_id": self.entry_attempt_id,
                "entry_state": self.entry_state,
                "entry_filled_quantity": _canonical_decimal(self.entry_filled_quantity),
                "entry_avg_fill_price": _canonical_decimal(self.entry_avg_fill_price),
                "exits_filled_quantity": _canonical_decimal(self.exits_filled_quantity),
                "broker_position_quantity": self.broker_position_quantity,
                "competing_entry_attempt_ids": list(self.competing_entry_attempt_ids),
                # `captured_at` is evidence, not identity: the SAME position observed again
                # later must produce the same digest, or the dispatch-time re-check could
                # never match the fingerprint the human confirmed.
            }
        )


#: The operator-facing sentence every ineligible position shows.
POSITION_NEEDS_ATTENTION = "Position requires operator attention before it can be closed safely."

#: Entry states from which a stable attributable position can exist. FILLED is the normal
#: case; CANCELED covers a partially filled entry whose remainder was cancelled and can no
#: longer fill. PARTIALLY_FILLED is deliberately absent: the remainder may still fill.
_STABLE_ENTRY_STATES: frozenset[str] = frozenset({"FILLED", "CANCELED"})


def exit_eligibility(
    snapshot: PositionSnapshot, *, existing_exit: PositionExitAttempt | None
) -> tuple[str, ...]:
    """Why this position may NOT be closed now. Empty means eligible for a full close.

    Conservative on purpose. The position belongs to exactly one known M085 entry
    lifecycle whose quantity is stable, the broker agrees with the attributable quantity,
    no other entry in the symbol also holds shares, and no exit for it is already in flight
    or filled. Anything the evidence cannot prove is a refusal, never a guess about which
    shares belong to this system.
    """
    refusals: list[str] = []
    if snapshot.entry_attempt_id is None or snapshot.entry_state is None:
        refusals.append("no entry execution is on record for this position")
        return tuple(refusals)
    if snapshot.entry_state == "PARTIALLY_FILLED":
        refusals.append(
            "the entry order is partially filled and its remainder can still fill; cancel the "
            "remainder and wait until the entry is final before closing"
        )
    elif snapshot.entry_state == "SUBMISSION_UNKNOWN":
        refusals.append("the entry order's outcome is unknown; the position cannot be attributed")
    elif snapshot.entry_state not in _STABLE_ENTRY_STATES:
        refusals.append(
            f"the entry order is {snapshot.entry_state}; only a filled entry, or a cancelled "
            "entry that left a proven filled position, can be closed"
        )
    filled = _whole(snapshot.entry_filled_quantity)
    if snapshot.entry_filled_quantity is None or filled is None:
        refusals.append("the entry's filled quantity is not a proven whole number of shares")
    elif filled <= 0:
        refusals.append("the entry filled nothing; there is no position to close")
    attributable = snapshot.attributable_quantity
    if filled is not None and filled > 0 and attributable is None:
        refusals.append("earlier exits already sold the whole attributable quantity")
    if snapshot.broker_position_quantity <= 0:
        refusals.append("the broker reports no long position in this symbol")
    elif attributable is not None and snapshot.broker_position_quantity != attributable:
        refusals.append(
            f"the broker position ({snapshot.broker_position_quantity}) does not equal the "
            f"attributable entry quantity ({attributable}); the shares cannot be attributed "
            "to this entry alone"
        )
    if snapshot.competing_entry_attempt_ids:
        refusals.append(
            "another entry in the same symbol also holds shares "
            f"({', '.join(snapshot.competing_entry_attempt_ids)}); attribution is ambiguous"
        )
    if existing_exit is not None:
        if existing_exit.position_closed:
            refusals.append("this position is already closed")
        elif not existing_exit.is_terminal:
            refusals.append(
                f"an exit is already in progress ({existing_exit.state.value}); a second exit "
                "cannot be prepared while it is open"
            )
        elif existing_exit.state is PositionExitState.FILLED:
            refusals.append(
                "an exit filled but the broker position was not yet verified at zero; wait for "
                "reconciliation"
            )
    return tuple(dict.fromkeys(refusals))


# ---------------------------------------------------------------------------
# The request and its identity
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class PositionExitRequest:
    """The exact SELL-TO-CLOSE request. Every field a human confirms is here.

    `side` is the single literal `SELL_TO_CLOSE`; `quantity` is whole and positive and is
    checked against the position by `PositionExitPreview`, never taken from a caller's
    free choice; `environment` must be one this milestone permits (SIMULATION only).
    """

    symbol: str
    side: str
    quantity: int
    order_type: OrderType
    limit_price: Decimal | None
    time_in_force: str
    extended_hours: bool
    client_order_id: str
    entry_intent_governance_id: str
    account_reference: str
    environment: str

    def __post_init__(self) -> None:
        if self.symbol != self.symbol.strip().upper() or not self.symbol:
            raise ValueError("symbol must be upper-case and unpadded")
        if self.side != EXIT_SIDE:
            raise ValueError(f"side must be {EXIT_SIDE}: an exit only closes an existing long")
        _require_whole_positive(self.quantity, field="quantity")
        if not isinstance(self.order_type, OrderType):
            raise ValueError("order_type must be an OrderType")
        if self.order_type is OrderType.LIMIT:
            if self.limit_price is None:
                raise ValueError("a LIMIT exit must carry a limit_price")
            _require_positive_money(self.limit_price, field="limit_price")
        elif self.limit_price is not None:
            raise ValueError("a non-LIMIT exit must not carry a limit_price")
        if self.time_in_force != "DAY":
            raise ValueError("time_in_force must be DAY")
        if self.extended_hours is not False:
            raise ValueError("extended_hours must be False")
        if not isinstance(self.client_order_id, str) or not self.client_order_id.startswith(
            EXIT_CLIENT_ORDER_ID_PREFIX
        ):
            raise ValueError(f"client_order_id must start with {EXIT_CLIENT_ORDER_ID_PREFIX!r}")
        if len(self.client_order_id) > _MAXIMUM_BROKER_CLIENT_ORDER_ID_LENGTH:
            raise ValueError("client_order_id exceeds the broker's documented maximum")
        _require_identifier(self.entry_intent_governance_id, field="entry_intent_governance_id")
        _require_identifier(self.account_reference, field="account_reference")
        if self.environment not in ALLOWED_EXIT_ENVIRONMENTS:
            raise ValueError(
                f"environment must be one of {sorted(ALLOWED_EXIT_ENVIRONMENTS)}; "
                f"{self.environment!r} cannot be bound to an exit in this milestone"
            )

    @property
    def broker_side(self) -> str:
        """What the venue is told: a plain sell, which the venue applies to the long held."""
        return "sell"


def derive_exit_client_order_id(
    *, entry_intent_governance_id: str, account_reference: str, preview_id: str
) -> str:
    """The one broker-facing identity for this exit preview on this account.

    DERIVED from persisted identity, never generated: a crashed worker, a second worker
    and every reconciliation recompute the same string. The preview id is part of the
    material, so a NEW exit prepared after a cancelled or rejected one is a NEW identity,
    while retries of the SAME preview are the same identity and collide at the broker.
    """
    _require_identifier(entry_intent_governance_id, field="entry_intent_governance_id")
    _require_identifier(account_reference, field="account_reference")
    _require_identifier(preview_id, field="preview_id")
    material = f"{entry_intent_governance_id}|{account_reference}|{preview_id}"
    return EXIT_CLIENT_ORDER_ID_PREFIX + hashlib.sha256(material.encode("utf-8")).hexdigest()[:40]


def exit_request_fingerprint(
    *,
    request: PositionExitRequest,
    entry_attempt_id: str,
    position_digest: str,
    liquidation_deadline: datetime,
) -> str:
    """The digest a human exit authorization is bound to.

    Covers the request (symbol, side, quantity, type, price, time in force, extended
    hours, identity), the account, the environment, the entry it closes, the position
    evidence it was judged on and the mandatory liquidation deadline. Any of those
    changing after the review page was shown is a different fingerprint and a refusal.
    """
    _require_identifier(entry_attempt_id, field="entry_attempt_id")
    _require_digest(position_digest, field="position_digest")
    _require_aware(liquidation_deadline, field="liquidation_deadline")
    return _canonical_digest(
        {
            "account_reference": request.account_reference,
            "client_order_id": request.client_order_id,
            "entry_attempt_id": entry_attempt_id,
            "entry_intent_governance_id": request.entry_intent_governance_id,
            "environment": request.environment,
            "extended_hours": request.extended_hours,
            # Canonical numeric form: the fingerprint is recomputed from rows that went through
            # PostgreSQL numeric(20, 8), where 227.40 comes back as 227.40000000.
            "limit_price": _canonical_decimal(request.limit_price),
            "liquidation_deadline": _instant_text(liquidation_deadline),
            "order_type": request.order_type.value,
            "position_digest": position_digest,
            "quantity": request.quantity,
            "side": request.side,
            "symbol": request.symbol,
            "time_in_force": request.time_in_force,
        }
    )


# ---------------------------------------------------------------------------
# Preview, authorization, attempt, event
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class PositionExitPreview:
    """Exactly what the Owner was shown on the exit review page, frozen at that instant."""

    preview_id: str
    entry_intent_governance_id: str
    entry_attempt_id: str
    preview_version: int
    account_reference: str
    environment: str
    request: PositionExitRequest
    request_fingerprint: str
    position: PositionSnapshot
    quote_bid: Decimal | None
    quote_ask: Decimal | None
    quote_captured_at: datetime | None
    quote_source: str
    liquidation_deadline: datetime
    created_at: datetime

    def __post_init__(self) -> None:
        _require_identifier(self.preview_id, field="preview_id")
        _require_identifier(self.entry_intent_governance_id, field="entry_intent_governance_id")
        _require_identifier(self.entry_attempt_id, field="entry_attempt_id")
        _require_identifier(self.account_reference, field="account_reference")
        _require_whole_positive(self.preview_version, field="preview_version")
        if not isinstance(self.request, PositionExitRequest):
            raise ValueError("request must be a PositionExitRequest")
        if not isinstance(self.position, PositionSnapshot):
            raise ValueError("position must be a PositionSnapshot")
        _require_digest(self.request_fingerprint, field="request_fingerprint")
        _require_aware(self.liquidation_deadline, field="liquidation_deadline")
        _require_aware(self.created_at, field="created_at")
        if self.quote_captured_at is not None:
            _require_aware(self.quote_captured_at, field="quote_captured_at")
        if self.request.entry_intent_governance_id != self.entry_intent_governance_id:
            raise ValueError("the request must close the entry this preview describes")
        if self.request.account_reference != self.account_reference:
            raise ValueError("the request must bind the preview's account")
        if self.request.environment != self.environment:
            raise ValueError("the request must bind the preview's environment")
        if self.position.symbol != self.request.symbol:
            raise ValueError("the position and the request must name one symbol")
        if self.position.entry_attempt_id != self.entry_attempt_id:
            raise ValueError("the position evidence must describe the entry attempt named")
        # THE FULL-CLOSE RULE. The quantity is the verified attributable quantity AND the
        # broker's position, or the preview cannot exist. Mirrored by a CHECK constraint.
        if self.request.quantity != self.position.attributable_quantity:
            raise ValueError(
                "an exit closes the whole attributable position: the request quantity must "
                "equal the verified attributable quantity"
            )
        if self.request.quantity != self.position.broker_position_quantity:
            raise ValueError("the request quantity must equal the broker's current position")
        expected = exit_request_fingerprint(
            request=self.request,
            entry_attempt_id=self.entry_attempt_id,
            position_digest=self.position.digest,
            liquidation_deadline=self.liquidation_deadline,
        )
        if expected != self.request_fingerprint:
            raise ValueError("request_fingerprint does not describe this preview")

    @property
    def binding_fingerprint(self) -> str:
        """The digest an authorization copies to prove WHICH review page it was granted on."""
        return _canonical_digest(
            {
                "account_reference": self.account_reference,
                "client_order_id": self.request.client_order_id,
                "created_at": _instant_text(self.created_at),
                "entry_attempt_id": self.entry_attempt_id,
                "entry_intent_governance_id": self.entry_intent_governance_id,
                "environment": self.environment,
                "limit_price": _canonical_decimal(self.request.limit_price),
                "liquidation_deadline": _instant_text(self.liquidation_deadline),
                "order_type": self.request.order_type.value,
                "position_digest": self.position.digest,
                "preview_id": self.preview_id,
                "preview_version": self.preview_version,
                "quantity": self.request.quantity,
                "quote_ask": _canonical_decimal(self.quote_ask),
                "quote_bid": _canonical_decimal(self.quote_bid),
                "quote_captured_at": _instant_text(self.quote_captured_at),
                "request_fingerprint": self.request_fingerprint,
                "side": self.request.side,
                "symbol": self.request.symbol,
                "time_in_force": self.request.time_in_force,
            }
        )


@dataclass(frozen=True, slots=True)
class PositionExitAuthorization:
    """One human's explicit, expiring, single-use permission to close ONE position once.

    Bound to the preview it was granted on (`preview_binding_fingerprint`), to the exact
    request (`request_fingerprint`), to the account and to the derived broker identity.
    Carries the broker time basis measured when it was granted, so its expiry can be
    judged on the broker's clock as well as this host's (the M085 lesson: a host clock
    that steps between processes must not hold a permission open).
    """

    authorization_id: str
    entry_intent_governance_id: str
    preview_id: str
    preview_version: int
    request_fingerprint: str
    preview_binding_fingerprint: str
    account_reference: str
    client_order_id: str
    symbol: str
    quantity: int
    authorized_by: str
    authorized_at: datetime
    expires_at: datetime
    basis_host_requested_at: datetime
    basis_host_at: datetime
    basis_broker_earliest_at: datetime
    basis_broker_latest_at: datetime
    consumed_at: datetime | None
    consumed_by_attempt_id: str | None

    def __post_init__(self) -> None:
        for field_name in (
            "authorization_id",
            "entry_intent_governance_id",
            "preview_id",
            "account_reference",
            "client_order_id",
            "authorized_by",
        ):
            _require_identifier(getattr(self, field_name), field=field_name)
        _require_whole_positive(self.preview_version, field="preview_version")
        _require_digest(self.request_fingerprint, field="request_fingerprint")
        _require_digest(self.preview_binding_fingerprint, field="preview_binding_fingerprint")
        if not self.client_order_id.startswith(EXIT_CLIENT_ORDER_ID_PREFIX):
            raise ValueError("an exit authorization binds an m087- client order id")
        _require_whole_positive(self.quantity, field="quantity")
        _require_aware(self.authorized_at, field="authorized_at")
        _require_aware(self.expires_at, field="expires_at")
        if self.expires_at <= self.authorized_at:
            raise ValueError("expires_at must follow authorized_at")
        # The basis is validated by constructing it.
        self.time_basis  # noqa: B018 - validation through the property
        if self.authorized_at > self.basis_host_at:
            raise ValueError("authorized_at is later than the host reading of the broker basis")
        if (self.consumed_at is None) != (self.consumed_by_attempt_id is None):
            raise ValueError(
                "consumed_at and consumed_by_attempt_id are set together or not at all"
            )
        if self.consumed_at is not None:
            _require_aware(self.consumed_at, field="consumed_at")

    @property
    def time_basis(self) -> BrokerTimeBasis:
        return BrokerTimeBasis(
            host_requested_at=self.basis_host_requested_at,
            host_at=self.basis_host_at,
            broker_earliest_at=self.basis_broker_earliest_at,
            broker_latest_at=self.basis_broker_latest_at,
        )

    @property
    def is_consumed(self) -> bool:
        return self.consumed_at is not None

    def is_expired_at(self, instant: datetime) -> bool:
        _require_aware(instant, field="instant")
        return instant >= self.expires_at

    def refusal_against(
        self,
        *,
        request_fingerprint_now: str,
        account_reference_now: str,
        instant: datetime,
        broker_now: BoundedInstant | None,
    ) -> str | None:
        """Why this authorization does not permit the exit being attempted; None when it does.

        Both clocks must permit: the host instant catches work inside this process, the
        broker instant catches a host clock that moved between the authorizing and the
        dispatching process. A caller supplying no broker instant is refused.
        """
        if self.is_consumed:
            return "the exit authorization has already been used"
        if self.is_expired_at(instant):
            return "the exit authorization has expired"
        if broker_now is None:
            return "the exit authorization cannot be checked without the broker's current instant"
        if broker_now.possibly_at_or_after(self.time_basis.on_broker_timeline(self.expires_at)):
            return "the exit authorization has expired on the broker's clock"
        if self.request_fingerprint != request_fingerprint_now:
            return (
                "the exit changed after it was authorized; the authorized fingerprint does not "
                "match the request being dispatched"
            )
        if self.account_reference != account_reference_now:
            return "the exit authorization was granted for a different account"
        return None


def exit_authorization_binding_refusal(
    *, authorization: PositionExitAuthorization, preview: PositionExitPreview
) -> str | None:
    """Why `authorization` is not a permission for exactly `preview`."""
    pairs: tuple[tuple[str, object, object], ...] = (
        ("preview_id", preview.preview_id, authorization.preview_id),
        ("preview_version", preview.preview_version, authorization.preview_version),
        (
            "entry_intent_governance_id",
            preview.entry_intent_governance_id,
            authorization.entry_intent_governance_id,
        ),
        ("request_fingerprint", preview.request_fingerprint, authorization.request_fingerprint),
        (
            "preview_binding_fingerprint",
            preview.binding_fingerprint,
            authorization.preview_binding_fingerprint,
        ),
        ("account_reference", preview.account_reference, authorization.account_reference),
        ("client_order_id", preview.request.client_order_id, authorization.client_order_id),
        ("symbol", preview.request.symbol, authorization.symbol),
        ("quantity", preview.request.quantity, authorization.quantity),
    )
    mismatched = [label for label, shown, bound in pairs if shown != bound]
    if mismatched:
        return (
            "the exit authorization does not describe the review it names ("
            + ", ".join(mismatched)
            + "); it permits nothing"
        )
    if authorization.expires_at > preview.liquidation_deadline:
        return "the exit authorization outlives the mandatory liquidation deadline"
    return None


@dataclass(frozen=True, slots=True)
class PositionExitAttempt:
    """The single claimed dispatch of one exit, and where it got to."""

    attempt_id: str
    entry_intent_governance_id: str
    authorization_id: str
    client_order_id: str
    request_fingerprint: str
    symbol: str
    quantity: int
    state: PositionExitState
    claimed_at: datetime
    submitted_at: datetime | None
    acknowledged_at: datetime | None
    terminal_at: datetime | None
    broker_order_id: str | None
    broker_status: str | None
    filled_quantity: Decimal | None
    filled_avg_price: Decimal | None
    failure_code: str | None
    failure_detail: str | None
    #: Set ONCE, after the attempt is FILLED for its whole quantity and a reconciliation
    #: verified the broker position at zero. This, not FILLED, is "position closed".
    closed_position_verified_at: datetime | None

    def __post_init__(self) -> None:
        for field_name in (
            "attempt_id",
            "entry_intent_governance_id",
            "authorization_id",
            "client_order_id",
        ):
            _require_identifier(getattr(self, field_name), field=field_name)
        _require_digest(self.request_fingerprint, field="request_fingerprint")
        _require_whole_positive(self.quantity, field="quantity")
        if not isinstance(self.state, PositionExitState):
            raise ValueError("state must be a PositionExitState")
        _require_aware(self.claimed_at, field="claimed_at")
        if self.state in TERMINAL_EXIT_STATES and self.terminal_at is None:
            raise ValueError(f"{self.state.value} is terminal and requires terminal_at")
        if self.terminal_at is not None and self.state not in TERMINAL_EXIT_STATES:
            raise ValueError("terminal_at is only set for a terminal state")
        if self.filled_quantity is not None and (
            self.filled_quantity < 0 or self.filled_quantity > Decimal(self.quantity)
        ):
            raise ValueError("filled_quantity must lie within [0, quantity]: never over-sold")
        if self.closed_position_verified_at is not None:
            _require_aware(self.closed_position_verified_at, field="closed_position_verified_at")
            if self.state is not PositionExitState.FILLED or self.filled_quantity != Decimal(
                self.quantity
            ):
                raise ValueError(
                    "closed_position_verified_at requires a FILLED attempt for its whole quantity"
                )

    @property
    def is_terminal(self) -> bool:
        return self.state in TERMINAL_EXIT_STATES

    @property
    def outcome_is_known(self) -> bool:
        return self.state is not PositionExitState.SUBMISSION_UNKNOWN

    @property
    def fully_filled(self) -> bool:
        return self.state is PositionExitState.FILLED and self.filled_quantity == Decimal(
            self.quantity
        )

    @property
    def position_closed(self) -> bool:
        """Verified: filled for the whole quantity AND the broker position was seen at zero."""
        return self.fully_filled and self.closed_position_verified_at is not None


@dataclass(frozen=True, slots=True)
class PositionExitEvent:
    """One audit entry about an exit. Append-only, never the source of state."""

    event_id: str
    entry_intent_governance_id: str
    attempt_id: str | None
    event_type: str
    occurred_at: datetime
    detail: str

    def __post_init__(self) -> None:
        _require_identifier(self.event_id, field="event_id")
        _require_identifier(self.entry_intent_governance_id, field="entry_intent_governance_id")
        if not isinstance(self.event_type, str) or not self.event_type.strip():
            raise ValueError("event_type must be a non-empty string")
        _require_aware(self.occurred_at, field="occurred_at")


# ---------------------------------------------------------------------------
# Realized result: only when every input is proven
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class RealizedResult:
    quantity: int
    entry_avg_fill_price: Decimal
    exit_avg_fill_price: Decimal
    realized_pnl: Decimal


def realized_result(
    *, entry_avg_fill_price: Decimal | None, exit_attempt: PositionExitAttempt | None
) -> RealizedResult | None:
    """(exit average fill − entry average fill) × closed quantity, or None.

    None whenever any input is not proven: no exit, an exit that is not a verified closed
    position, a missing actual fill price on either side, or a non-whole quantity. No
    estimate is ever substituted.
    """
    if exit_attempt is None or not exit_attempt.position_closed:
        return None
    if entry_avg_fill_price is None or exit_attempt.filled_avg_price is None:
        return None
    if entry_avg_fill_price <= 0 or exit_attempt.filled_avg_price <= 0:
        return None
    quantity = _whole(exit_attempt.filled_quantity)
    if quantity is None or quantity <= 0:
        return None
    return RealizedResult(
        quantity=quantity,
        entry_avg_fill_price=entry_avg_fill_price,
        exit_avg_fill_price=exit_attempt.filled_avg_price,
        realized_pnl=(exit_attempt.filled_avg_price - entry_avg_fill_price) * Decimal(quantity),
    )


# ---------------------------------------------------------------------------
# Send boundary, lineage, terms comparison, absence policy
# ---------------------------------------------------------------------------


def exit_send_boundary_binding(
    *,
    attempt_id: str,
    authorization_id: str,
    request_fingerprint: str,
    account_reference: str,
    client_order_id: str,
    identity_lookup_status: int,
) -> str:
    """The detail of the durable send-boundary event, bound to the attempt's identity."""
    return json.dumps(
        {
            "account_reference": account_reference,
            "attempt_id": attempt_id,
            "authorization_id": authorization_id,
            "client_order_id": client_order_id,
            "identity_lookup_status": identity_lookup_status,
            "request_fingerprint": request_fingerprint,
        },
        sort_keys=True,
        separators=(",", ":"),
    )


def _boundary_event_binds(event: object, attempt: PositionExitAttempt) -> bool:
    if getattr(event, "event_type", None) != EXIT_SEND_BOUNDARY_EVENT_TYPE:
        return False
    if getattr(event, "attempt_id", None) != attempt.attempt_id:
        return False
    try:
        binding = json.loads(str(getattr(event, "detail", "")))
    except json.JSONDecodeError:
        return False
    return (
        isinstance(binding, dict)
        and binding.get("attempt_id") == attempt.attempt_id
        and binding.get("authorization_id") == attempt.authorization_id
        and binding.get("client_order_id") == attempt.client_order_id
        and binding.get("request_fingerprint") == attempt.request_fingerprint
    )


def exit_attempt_may_have_transmitted(
    attempt: PositionExitAttempt, events: Iterable[object]
) -> bool:
    """Could THIS durable exit attempt have created an order at the broker?

    No unsent marker (code or append-only event), and, for the uncertain states, a
    send-boundary event bound to this attempt. Acknowledged states carry a broker id the
    broker itself echoed and need no further proof.
    """
    events = tuple(events)
    if attempt.failure_code in EXIT_UNSENT_FAILURE_CODES or any(
        getattr(e, "event_type", None) in EXIT_UNSENT_EVENT_TYPES for e in events
    ):
        return False
    if attempt.state is PositionExitState.SUBMISSION_IN_PROGRESS:
        return any(_boundary_event_binds(e, attempt) for e in events)
    if attempt.state is PositionExitState.SUBMISSION_UNKNOWN:
        code = attempt.failure_code or ""
        transmitted_code = code in EXIT_TRANSMITTED_UNCERTAIN_FAILURE_CODES or code.startswith(
            "UNCERTAIN_HTTP_"
        )
        return transmitted_code and any(_boundary_event_binds(e, attempt) for e in events)
    return attempt.state in BOUND_EXIT_ORDER_STATES


def exit_order_terms_mismatches(
    *, expected: PositionExitRequest, actual: object, bound_broker_order_id: str | None = None
) -> tuple[str, ...]:
    """The terms on which a broker order under our identity differs from the authorized exit."""

    def text(name: str) -> str | None:
        value = getattr(actual, name, None)
        return None if value is None else str(value)

    mismatches: list[str] = []
    if text("client_order_id") != expected.client_order_id:
        mismatches.append("client_order_id")
    if (text("symbol") or "").upper() != expected.symbol:
        mismatches.append("symbol")
    if (text("side") or "").lower() != expected.broker_side:
        mismatches.append("side")
    try:
        if Decimal(text("quantity") or "nan") != Decimal(expected.quantity):
            mismatches.append("quantity")
    except Exception:  # noqa: BLE001 - an unparseable quantity is a mismatch
        mismatches.append("quantity")
    if (text("order_type") or "").upper() != expected.order_type.value:
        mismatches.append("order_type")
    actual_limit = text("limit_price")
    if expected.limit_price is None:
        if actual_limit is not None:
            mismatches.append("limit_price")
    else:
        try:
            if actual_limit is None or Decimal(actual_limit) != expected.limit_price:
                mismatches.append("limit_price")
        except Exception:  # noqa: BLE001
            mismatches.append("limit_price")
    tif = text("time_in_force")
    if tif is not None and tif.upper() != expected.time_in_force:
        mismatches.append("time_in_force")
    extended = getattr(actual, "extended_hours", None)
    if extended is not None and bool(extended) is not expected.extended_hours:
        mismatches.append("extended_hours")
    if bound_broker_order_id is not None and text("broker_order_id") != bound_broker_order_id:
        mismatches.append("broker_order_id")
    return tuple(mismatches)


def _positively_observed(acknowledgements: Iterable[object], events: Iterable[object]) -> bool:
    if any(getattr(a, "broker_order_id", None) is not None for a in acknowledgements):
        return True
    return any(getattr(e, "event_type", None) in _POSITIVE_OBSERVATION_EVENT_TYPES for e in events)


@dataclass(frozen=True, slots=True)
class ExitAbsenceEvaluation:
    rounds_version: tuple[int, int]
    incomplete_sequences: tuple[int, ...]
    found_sequences: tuple[int, ...]
    consecutive_not_found: int
    waiting_lower_bound_seconds: float | None
    resolvable: bool
    reason: str


def exit_absence_evaluation(
    *,
    state: PositionExitState,
    broker_order_id: str | None,
    acknowledgements: Iterable[BrokerAcknowledgement],
    events: Iterable[object],
    rounds: Iterable[ReconciliationRound],
) -> ExitAbsenceEvaluation:
    """Whether the bounded not-found policy may resolve THIS exit attempt (the M085 rule).

    A SUBMISSION_UNKNOWN attempt, no broker id and no positive observation, no FOUND round,
    no incomplete round, at least the minimum consecutive completed NOT_FOUND rounds in
    sequence order, and a broker-time waiting lower bound of at least the minimum.
    """
    ordered = rounds_in_order(rounds)
    version = (len(ordered), ordered[-1].sequence if ordered else 0)
    incomplete = tuple(r.sequence for r in ordered if not r.is_complete)
    found = tuple(r.sequence for r in ordered if r.outcome is ReconciliationRoundOutcome.FOUND)
    run = consecutive_not_found_rounds(ordered)
    lower_bound = waiting_lower_bound_seconds(ordered)
    anchor = waiting_anchor(ordered)

    def verdict(resolvable: bool, reason: str) -> ExitAbsenceEvaluation:
        return ExitAbsenceEvaluation(
            rounds_version=version,
            incomplete_sequences=incomplete,
            found_sequences=found,
            consecutive_not_found=run,
            waiting_lower_bound_seconds=lower_bound,
            resolvable=resolvable,
            reason=reason,
        )

    if state in BOUND_EXIT_ORDER_STATES:
        return verdict(False, "a bound, acknowledged exit order is never resolved by absence")
    if state is not PositionExitState.SUBMISSION_UNKNOWN:
        return verdict(False, f"state {state.value} is not resolvable by absence")
    if broker_order_id is not None or _positively_observed(acknowledgements, events):
        return verdict(False, "an order under this identity was positively observed")
    if found:
        return verdict(False, "a completed round FOUND an order under this identity")
    if incomplete:
        return verdict(False, "an incomplete round could invalidate an absence decision")
    if run < MINIMUM_CONSECUTIVE_NOT_FOUND_OBSERVATIONS:
        return verdict(False, f"only {run} consecutive completed not-found round(s)")
    if lower_bound is None:
        return verdict(False, "no compatible broker-time evidence for the waiting interval")
    if lower_bound < MINIMUM_SECONDS_BEFORE_NOT_FOUND_COUNTS:
        return verdict(
            False,
            f"the waiting interval lower bound is {int(lower_bound)}s on the broker clock; "
            f"{MINIMUM_SECONDS_BEFORE_NOT_FOUND_COUNTS}s are required",
        )
    return verdict(
        True,
        f"{run} consecutive completed not-found rounds; waiting lower bound {int(lower_bound)}s "
        f"on the broker clock from anchor round {None if anchor is None else anchor.sequence}",
    )
