"""MILESTONE-085 -- the paper-execution domain: one authorization, one dispatch.

WHAT THIS IS. The broker-neutral model of dispatching ONE persisted MILESTONE-084
approved order intent to a PAPER environment exactly once, and only after a
fresh, explicit, expiring, single-use human authorization has been bound to the
exact immutable order-intent fingerprint, the exact paper account identity and
the exact broker request.

WHAT IT IS NOT. Nothing here proves that a paper acknowledgement is a real-market
execution, that a paper fill predicts a live fill, that an order was profitable
or fillable, or that this product is ready for a live account. A paper venue
simulates; the authority package states the full list of things this does not
prove and this module deliberately restates none of them as code comments that
could drift from it.

THE M084 INTENT IS READ, NEVER REWRITTEN. An `ApprovedOrderIntent` is frozen at
`submission_state = NOT_SUBMITTED` and MILESTONE-084 provides no transition away
from it. MILESTONE-085 does not add one. Execution state lives in M085's OWN
records, keyed by the intent's governance identity, so the M084 row a human
approved is still byte-for-byte the row a human approved after this milestone
has run.

`account_mode_required` STAYS `PREPARATION`, AND THAT IS NOT PERMISSION. M084
fixes that field at `PREPARATION` precisely so that an intent cannot declare
itself ready for a paper or live account. MILESTONE-085 therefore does NOT read
it as authorization to send anything. The permission to dispatch comes from one
place only: an `ExecutionAuthorization` a human created after being shown the
exact order. Treating `PREPARATION` as a green light would be reading M084's
refusal as its opposite.

WHY SO MUCH OF THIS IS AN IDENTITY. Exactly-once is not a retry policy. It is a
question of whether two attempts can produce two orders, and the answer here is
that they cannot produce two ORDER IDENTITIES: `client_order_id` is DERIVED from
persisted identity rather than generated, so a retry, a crash, a second worker
and a reconciliation all compute the same value and address the same broker
order. The broker's own duplicate protection is not relied on for this -- Alpaca
rejects a duplicate `client_order_id` only while the first order is still
ACTIVE, so it is not a durable exactly-once authority and this milestone does
not treat it as one. The database is.

AMBIGUITY IS A STATE, NOT AN ERROR. A timeout after the request may have been
sent leaves `SUBMISSION_UNKNOWN`. That is not a failure to be retried; it is a
fact to be resolved by asking the broker about the SAME `client_order_id`. A 404
from that lookup is NOT proof that nothing was sent -- see
`RECONCILIATION_UNKNOWN_POLICY` below, which is deliberately bounded and stated
rather than assumed.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from datetime import time as clock_time
from decimal import Decimal
from enum import StrEnum
from types import MappingProxyType
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from empirical_platform.decision_candidate.operator_trading_configuration import (
    OperatorTradingConfiguration,
    OrderType,
)
from empirical_platform.decision_candidate.trade_approval import (
    ApprovalDecision,
    ApprovedOrderIntent,
    OperatorAction,
)
from empirical_platform.decision_candidate.trade_proposal import TradeProposal
from empirical_platform.shared.brokerage.paper_time import BoundedInstant, BrokerTimeBasis

__all__ = [
    "ALLOWED_PAPER_TRANSITIONS",
    "CLIENT_ORDER_ID_PREFIX",
    "DEFINITIVE_BROKER_REFUSAL_STATUSES",
    "ExecutionPolicy",
    "authorization_binding_refusal",
    "effective_liquidation_deadline",
    "entry_window_refusal",
    "execution_policy_from_configuration",
    "final_send_refusal",
    "is_definitive_broker_refusal",
    "liquidation_session_refusal",
    "quote_refusal",
    "MAXIMUM_BROKER_CLIENT_ORDER_ID_LENGTH",
    "MINIMUM_CONSECUTIVE_NOT_FOUND_OBSERVATIONS",
    "MINIMUM_SECONDS_BEFORE_NOT_FOUND_COUNTS",
    "NOT_FOUND_ALONE_RESOLVES_UNKNOWN",
    "NO_AUTHORIZATION_TIME_BASIS",
    "NO_DECISION_TIME_BASIS",
    "NO_INTENT_TIME_BASIS",
    "NO_PROPOSAL_TIME_BASIS",
    "PAPER_ENDPOINT_HOST",
    "RECONCILIATION_UNKNOWN_POLICY",
    "RESOLUTION_REQUIRES_OPERATOR_VISIBLE_EVENT",
    "RESOLUTION_WHEN_POLICY_SATISFIED",
    "TERMINAL_PAPER_STATES",
    "BrokerAcknowledgement",
    "ExecutionAttempt",
    "DecisionTimeBasis",
    "ExecutionAuthorization",
    "IntentTimeBasis",
    "M084TimeProvenance",
    "PaperAccountSnapshot",
    "PaperEnvironment",
    "PaperExecutionEvent",
    "PaperExecutionState",
    "PaperOrderRequest",
    "ProposalTimeBasis",
    "SubmissionPreview",
    "act_chronology_refusal",
    "authorize_submission",
    "bind_decision_time_basis",
    "bind_intent_time_basis",
    "bind_proposal_time_basis",
    "build_submission_preview",
    "decision_time_basis_refusal",
    "derive_client_order_id",
    "intent_time_basis_refusal",
    "is_paper_transition_allowed",
    "m084_deadline_refusal_on_broker_time",
    "m084_provenance_refusal",
    "proposal_time_basis_refusal",
    "request_fingerprint",
]

#: Why an authorization without an interval-shaped basis cannot be dispatched.
NO_AUTHORIZATION_TIME_BASIS = (
    "this authorization carries no authorization-time broker basis measured as an "
    "interval, so its expiry cannot be placed on the broker's clock; it is not "
    "dispatchable, and no basis is derived for it later"
)

#: Why an intent without its own intent-time basis cannot be dispatched. One string,
#: so the preview, pre-claim and send-boundary refusals cannot drift apart.
NO_INTENT_TIME_BASIS = (
    "this approved intent carries no intent-time broker basis: it was not issued through "
    "the Paper-bound issuance command, so its deadlines cannot be placed on the broker's "
    "clock. It is not dispatchable, and no basis is derived for it after the fact"
)

#: Why an intent whose PROPOSAL was evaluated without a basis cannot be dispatched.
NO_PROPOSAL_TIME_BASIS = (
    "this intent's proposal carries no proposal-time broker basis: it was not evaluated "
    "through the Paper-bound proposal command, so the proposal expiry and the mandatory "
    "liquidation deadline cannot be placed on the broker's clock. It is not dispatchable, "
    "and no basis is derived for it after the fact"
)

#: Why an intent whose APPROVAL was recorded without a basis cannot be dispatched.
NO_DECISION_TIME_BASIS = (
    "this intent's approval carries no decision-time broker basis: it was not recorded "
    "through the Paper-bound decision command, so the approval expiry cannot be placed on "
    "the broker's clock. It is not dispatchable, and no basis is derived for it after the fact"
)

_MAXIMUM_IDENTIFIER_LENGTH = 64
_HEX_DIGEST = re.compile(r"^[0-9a-f]{64}$")

#: The ONLY host this milestone may dispatch an order to. Not a default, not a
#: preference, and deliberately not read from a variable whose name contains the
#: word PAPER -- a name is not evidence about a value.
PAPER_ENDPOINT_HOST = "paper-api.alpaca.markets"

#: Alpaca's documented ceiling for `client_order_id`. Ours is far shorter; the
#: broker limit is recorded so that a future change to the derivation cannot
#: silently produce an id the broker would truncate or refuse.
MAXIMUM_BROKER_CLIENT_ORDER_ID_LENGTH = 128

CLIENT_ORDER_ID_PREFIX = "m085-"

#: What a "not found" answer during reconciliation is allowed to mean.
#:
#: Measured against the real paper endpoint: an unknown `client_order_id`
#: returns HTTP 404 with body code 40410000. That is NOT sufficient to conclude
#: an order was never accepted, because a request that timed out may still be in
#: flight at the broker. The policy is therefore bounded in time rather than
#: decided on the first answer, and the bound is stated here so it can be
#: reviewed instead of discovered in a log.
#: The individual bounds, typed, because callers do arithmetic with them and a
#: heterogeneous mapping would make every use site cast.
NOT_FOUND_ALONE_RESOLVES_UNKNOWN: bool = False
MINIMUM_CONSECUTIVE_NOT_FOUND_OBSERVATIONS: int = 2
MINIMUM_SECONDS_BEFORE_NOT_FOUND_COUNTS: int = 60
RESOLUTION_WHEN_POLICY_SATISFIED: str = "REJECTED"
RESOLUTION_REQUIRES_OPERATOR_VISIBLE_EVENT: bool = True

#: The same policy as one document, for the authority package to render. Derived
#: from the constants above rather than repeating them, so the published policy
#: and the enforced policy cannot disagree.
RECONCILIATION_UNKNOWN_POLICY: MappingProxyType[str, object] = MappingProxyType(
    {
        "not_found_alone_resolves_unknown": NOT_FOUND_ALONE_RESOLVES_UNKNOWN,
        "minimum_consecutive_not_found_observations": (MINIMUM_CONSECUTIVE_NOT_FOUND_OBSERVATIONS),
        "minimum_seconds_since_dispatch_before_not_found_counts": (
            MINIMUM_SECONDS_BEFORE_NOT_FOUND_COUNTS
        ),
        "resolution_when_policy_satisfied": RESOLUTION_WHEN_POLICY_SATISFIED,
        "resolution_requires_operator_visible_event": (RESOLUTION_REQUIRES_OPERATOR_VISIBLE_EVENT),
    }
)


#: HTTP statuses on `POST /v2/orders` that are a DEFINITIVE refusal by the broker.
#:
#: CORRECTIVE PASS (D2). Every other answer to a request that was delivered -- a
#: 5xx, a 3xx, a 408, a 409, a 429, a 200/201 whose body is not a valid order, or
#: any status not listed here -- is UNCERTAIN: an intermediary may have answered
#: after the broker accepted the order, so the attempt becomes SUBMISSION_UNKNOWN
#: and is resolved by reconciliation against the same `client_order_id`. A listed
#: status counts only when the body is a JSON object, i.e. the broker's own error
#: document rather than a proxy page. Absent from the list on purpose: 404 (a
#: gateway can produce it) and 429 (rate limiting is not documented as proof that
#: the order was not recorded).
DEFINITIVE_BROKER_REFUSAL_STATUSES: frozenset[int] = frozenset({400, 401, 403, 422})


def is_definitive_broker_refusal(status: int, body: str) -> bool:
    """Whether an answer to a delivered order request proves no order was created."""
    if isinstance(status, bool) or not isinstance(status, int):
        return False
    if status not in DEFINITIVE_BROKER_REFUSAL_STATUSES:
        return False
    try:
        parsed = json.loads(body)
    except (TypeError, ValueError):
        return False
    return isinstance(parsed, dict)


class PaperEnvironment(StrEnum):
    """The execution environment. Exactly one member exists.

    LIVE is not declared. A milestone that cannot reach a live venue must not
    own a symbol for one: declaring it would create a value that code could
    branch on and reviewers would have to prove unreachable.
    """

    PAPER = "PAPER"


class PaperExecutionState(StrEnum):
    """Where one intent stands on its single journey to a paper venue."""

    NOT_DISPATCHED = "NOT_DISPATCHED"
    AUTHORIZATION_PENDING = "AUTHORIZATION_PENDING"
    AUTHORIZED = "AUTHORIZED"
    DISPATCH_CLAIMED = "DISPATCH_CLAIMED"
    SUBMISSION_IN_PROGRESS = "SUBMISSION_IN_PROGRESS"
    PAPER_SUBMITTED = "PAPER_SUBMITTED"
    PAPER_ACCEPTED = "PAPER_ACCEPTED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCEL_REQUESTED = "CANCEL_REQUESTED"
    CANCELED = "CANCELED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    SUBMISSION_UNKNOWN = "SUBMISSION_UNKNOWN"


#: Terminal states. Nothing leaves these.
TERMINAL_PAPER_STATES: frozenset[PaperExecutionState] = frozenset(
    {
        PaperExecutionState.FILLED,
        PaperExecutionState.CANCELED,
        PaperExecutionState.REJECTED,
        PaperExecutionState.EXPIRED,
    }
)

#: The closed transition table, mirrored by a database trigger.
#:
#: Two edges are worth reading twice. CANCEL_REQUESTED -> FILLED exists because
#: asking to cancel does not stop a fill: the request races the venue and can
#: lose, and a model without that edge would force a real outcome into a state
#: the code calls impossible. SUBMISSION_UNKNOWN has edges to every real
#: outcome because reconciliation is how an unknown becomes known -- but it has
#: no edge back into SUBMISSION_IN_PROGRESS, so an unknown can never be quietly
#: converted into a fresh attempt.
ALLOWED_PAPER_TRANSITIONS: MappingProxyType[PaperExecutionState, frozenset[PaperExecutionState]] = (
    MappingProxyType(
        {
            PaperExecutionState.NOT_DISPATCHED: frozenset(
                {PaperExecutionState.AUTHORIZATION_PENDING}
            ),
            PaperExecutionState.AUTHORIZATION_PENDING: frozenset(
                {PaperExecutionState.AUTHORIZED, PaperExecutionState.EXPIRED}
            ),
            PaperExecutionState.AUTHORIZED: frozenset(
                {PaperExecutionState.DISPATCH_CLAIMED, PaperExecutionState.EXPIRED}
            ),
            PaperExecutionState.DISPATCH_CLAIMED: frozenset(
                {
                    PaperExecutionState.SUBMISSION_IN_PROGRESS,
                    PaperExecutionState.REJECTED,
                    PaperExecutionState.EXPIRED,
                }
            ),
            PaperExecutionState.SUBMISSION_IN_PROGRESS: frozenset(
                {
                    PaperExecutionState.PAPER_SUBMITTED,
                    PaperExecutionState.SUBMISSION_UNKNOWN,
                    PaperExecutionState.REJECTED,
                }
            ),
            PaperExecutionState.PAPER_SUBMITTED: frozenset(
                {
                    PaperExecutionState.PAPER_ACCEPTED,
                    PaperExecutionState.PARTIALLY_FILLED,
                    PaperExecutionState.FILLED,
                    PaperExecutionState.CANCEL_REQUESTED,
                    PaperExecutionState.CANCELED,
                    PaperExecutionState.REJECTED,
                    PaperExecutionState.EXPIRED,
                    PaperExecutionState.SUBMISSION_UNKNOWN,
                }
            ),
            PaperExecutionState.PAPER_ACCEPTED: frozenset(
                {
                    PaperExecutionState.PARTIALLY_FILLED,
                    PaperExecutionState.FILLED,
                    PaperExecutionState.CANCEL_REQUESTED,
                    PaperExecutionState.CANCELED,
                    PaperExecutionState.REJECTED,
                    PaperExecutionState.EXPIRED,
                    PaperExecutionState.SUBMISSION_UNKNOWN,
                }
            ),
            PaperExecutionState.PARTIALLY_FILLED: frozenset(
                {
                    PaperExecutionState.FILLED,
                    PaperExecutionState.CANCEL_REQUESTED,
                    PaperExecutionState.CANCELED,
                    PaperExecutionState.EXPIRED,
                    PaperExecutionState.SUBMISSION_UNKNOWN,
                }
            ),
            PaperExecutionState.CANCEL_REQUESTED: frozenset(
                {
                    PaperExecutionState.CANCELED,
                    PaperExecutionState.PARTIALLY_FILLED,
                    PaperExecutionState.FILLED,
                    PaperExecutionState.REJECTED,
                    PaperExecutionState.EXPIRED,
                    PaperExecutionState.SUBMISSION_UNKNOWN,
                }
            ),
            PaperExecutionState.SUBMISSION_UNKNOWN: frozenset(
                {
                    PaperExecutionState.PAPER_SUBMITTED,
                    PaperExecutionState.PAPER_ACCEPTED,
                    PaperExecutionState.PARTIALLY_FILLED,
                    PaperExecutionState.FILLED,
                    PaperExecutionState.CANCEL_REQUESTED,
                    PaperExecutionState.CANCELED,
                    PaperExecutionState.REJECTED,
                    PaperExecutionState.EXPIRED,
                }
            ),
            PaperExecutionState.FILLED: frozenset(),
            PaperExecutionState.CANCELED: frozenset(),
            PaperExecutionState.REJECTED: frozenset(),
            PaperExecutionState.EXPIRED: frozenset(),
        }
    )
)


def is_paper_transition_allowed(current: PaperExecutionState, target: PaperExecutionState) -> bool:
    """Whether `current -> target` is one of the closed allowed transitions."""
    if not isinstance(current, PaperExecutionState) or not isinstance(target, PaperExecutionState):
        raise ValueError("both states must be PaperExecutionState members")
    return target in ALLOWED_PAPER_TRANSITIONS[current]


def _require_identifier(value: str, *, field: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    if len(value) > _MAXIMUM_IDENTIFIER_LENGTH:
        raise ValueError(f"{field} must be at most {_MAXIMUM_IDENTIFIER_LENGTH} characters")


def _require_digest(value: str, *, field: str) -> None:
    if not isinstance(value, str) or not _HEX_DIGEST.match(value):
        raise ValueError(f"{field} must be a 64-character lowercase hex digest")


def _require_aware(value: datetime, *, field: str) -> None:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError(f"{field} must be a timezone-aware datetime")


def _require_positive_money(value: Decimal, *, field: str) -> None:
    if not isinstance(value, Decimal):
        raise ValueError(f"{field} must be a Decimal")
    if value.is_nan() or value.is_infinite():
        raise ValueError(f"{field} must be a finite Decimal")
    if value <= 0:
        raise ValueError(f"{field} must be positive")


@dataclass(frozen=True, slots=True)
class PaperAccountSnapshot:
    """What the paper account said about itself at one instant.

    `account_reference` is a STABLE DIGEST of the broker's account identifier,
    never the identifier itself. The product needs to prove that an
    authorization and a dispatch concern the SAME account; it does not need to
    store an external account number to do that, and storing one would put a
    real customer identifier into every audit row for no gain.
    """

    snapshot_id: str
    environment: PaperEnvironment
    endpoint_host: str
    account_reference: str
    account_status: str
    currency: str
    buying_power: Decimal
    cash: Decimal
    equity: Decimal
    multiplier: str
    shorting_enabled: bool
    trading_blocked: bool
    transfers_blocked: bool
    account_blocked: bool
    trade_suspended_by_user: bool
    captured_at: datetime

    def __post_init__(self) -> None:
        _require_identifier(self.snapshot_id, field="snapshot_id")
        _require_identifier(self.account_reference, field="account_reference")
        if not isinstance(self.environment, PaperEnvironment):
            raise ValueError("environment must be a PaperEnvironment")
        if self.endpoint_host != PAPER_ENDPOINT_HOST:
            raise ValueError(f"endpoint_host must be exactly {PAPER_ENDPOINT_HOST}")
        if self.currency != "USD":
            raise ValueError("currency must be USD")
        for field_name in ("buying_power", "cash", "equity"):
            value = getattr(self, field_name)
            if not isinstance(value, Decimal) or value.is_nan() or value.is_infinite():
                raise ValueError(f"{field_name} must be a finite Decimal")
        _require_aware(self.captured_at, field="captured_at")

    @property
    def is_dispatchable(self) -> bool:
        """Whether the ACCOUNT itself currently permits an order at all.

        Deliberately narrow: this answers a question about the account, not
        about the order, the market, the asset or the operator's policy. Those
        are separate checks and combining them here would let one of them pass
        by being forgotten.
        """
        return (
            self.account_status == "ACTIVE"
            and not self.trading_blocked
            and not self.account_blocked
            and not self.trade_suspended_by_user
        )


def _canonical_digest(payload: dict[str, object]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _decimal_text(value: Decimal | None) -> str | None:
    """The WRITTEN form: `4.00` and `4.0` differ. Used only by the request fingerprint."""
    return None if value is None else format(value, "f")


def _canonical_decimal(value: Decimal | None) -> str | None:
    """The NUMERIC form: `2000`, `2000.0` and `2000.00000000` are one value.

    The policy and preview-binding digests are recomputed from rows that went through
    PostgreSQL `numeric(20, 8)`, which returns every amount at scale 8. A digest over
    the written form would therefore change on the round trip and refuse a genuine
    row -- measured: every stored preview failed its own binding check on read.
    """
    if value is None:
        return None
    normalized = value.normalize()
    return format(normalized if normalized != 0 else Decimal(0), "f")


def _instant_text(value: datetime | None) -> str | None:
    """One instant, one spelling: UTC, whatever offset the value was read back in."""
    return None if value is None else value.astimezone(UTC).isoformat()


@dataclass(frozen=True, slots=True)
class ExecutionPolicy:
    """The send-time safety limits, taken from ONE immutable configuration version.

    CORRECTIVE PASS (D1). These limits used to arrive as command-line arguments at
    preview and again at submit, and none of them was bound to the authorization:
    an operator could authorize under 5 USD and 60 s and then submit under 500 USD
    and 99 999 s. They now have exactly one source -- the configuration version the
    M084 intent names -- and no command accepts them. The preview, the
    authorization and the final send guard all carry `fingerprint`, and the send
    guard re-derives the policy from the stored configuration and requires it to
    equal the authorized one.
    """

    configuration_governance_id: str
    configuration_version: int
    maximum_notional: Decimal
    quote_maximum_age_seconds: int
    maximum_spread_percent: Decimal
    watchlist: tuple[str, ...]
    prohibited_instruments: tuple[str, ...]
    earliest_entry_time: clock_time
    latest_entry_time: clock_time
    operator_timezone: str

    def __post_init__(self) -> None:
        _require_identifier(self.configuration_governance_id, field="configuration_governance_id")
        if isinstance(self.configuration_version, bool) or not isinstance(
            self.configuration_version, int
        ):
            raise ValueError("configuration_version must be an int")
        if self.configuration_version < 1:
            raise ValueError("configuration_version must start at 1")
        _require_positive_money(self.maximum_notional, field="maximum_notional")
        if isinstance(self.quote_maximum_age_seconds, bool) or not isinstance(
            self.quote_maximum_age_seconds, int
        ):
            raise ValueError("quote_maximum_age_seconds must be an int")
        if self.quote_maximum_age_seconds <= 0:
            raise ValueError("quote_maximum_age_seconds must be positive")
        if (
            not isinstance(self.maximum_spread_percent, Decimal)
            or not self.maximum_spread_percent.is_finite()
            or self.maximum_spread_percent < 0
        ):
            raise ValueError("maximum_spread_percent must be a finite, non-negative Decimal")
        for name in ("watchlist", "prohibited_instruments"):
            symbols = getattr(self, name)
            if not isinstance(symbols, tuple) or any(
                not isinstance(symbol, str) or not symbol or symbol != symbol.strip().upper()
                for symbol in symbols
            ):
                raise ValueError(f"{name} must be a tuple of upper-case symbols")
            if list(symbols) != sorted(set(symbols)):
                raise ValueError(f"{name} must be sorted and free of duplicates")
        if not self.watchlist:
            raise ValueError("watchlist must name at least one symbol")
        for name in ("earliest_entry_time", "latest_entry_time"):
            value = getattr(self, name)
            if not isinstance(value, clock_time) or value.tzinfo is not None:
                raise ValueError(f"{name} must be a naive time of day")
        if self.earliest_entry_time >= self.latest_entry_time:
            raise ValueError("earliest_entry_time must precede latest_entry_time")
        try:
            ZoneInfo(self.operator_timezone)
        except (ZoneInfoNotFoundError, ValueError, TypeError) as error:
            raise ValueError("operator_timezone must be a known IANA timezone") from error

    @property
    def fingerprint(self) -> str:
        return _canonical_digest(
            {
                "configuration_governance_id": self.configuration_governance_id,
                "configuration_version": self.configuration_version,
                "earliest_entry_time": self.earliest_entry_time.isoformat(),
                "latest_entry_time": self.latest_entry_time.isoformat(),
                "maximum_notional": _canonical_decimal(self.maximum_notional),
                "maximum_spread_percent": _canonical_decimal(self.maximum_spread_percent),
                "operator_timezone": self.operator_timezone,
                "prohibited_instruments": list(self.prohibited_instruments),
                "quote_maximum_age_seconds": self.quote_maximum_age_seconds,
                "watchlist": list(self.watchlist),
            }
        )

    def permits_symbol(self, symbol: str) -> bool:
        return symbol in self.watchlist and symbol not in self.prohibited_instruments


def execution_policy_from_configuration(
    configuration: OperatorTradingConfiguration,
) -> ExecutionPolicy:
    """The send-time policy of one stored configuration version. Nothing else is read."""
    if not isinstance(configuration, OperatorTradingConfiguration):
        raise ValueError("configuration must be an OperatorTradingConfiguration")
    return ExecutionPolicy(
        configuration_governance_id=configuration.configuration_governance_id,
        configuration_version=configuration.configuration_version,
        maximum_notional=configuration.maximum_capital_per_trade,
        quote_maximum_age_seconds=configuration.maximum_market_data_age_seconds,
        maximum_spread_percent=configuration.maximum_spread_percent,
        watchlist=tuple(sorted(set(configuration.watchlist))),
        prohibited_instruments=tuple(sorted(set(configuration.prohibited_instruments))),
        earliest_entry_time=configuration.earliest_entry_time,
        latest_entry_time=configuration.latest_entry_time,
        operator_timezone=configuration.operator_timezone,
    )


def quote_refusal(
    *,
    bid: Decimal | None,
    ask: Decimal | None,
    captured_at: datetime | None,
    policy: ExecutionPolicy,
    broker_now: BoundedInstant,
) -> str | None:
    """Why this quote cannot support a dispatch under `policy`, judged on the broker clock.

    Freshness is tested against the OLDEST age the broker interval permits, so an age
    of exactly the limit passes and anything older refuses. The spread is measured
    against the mid price, the same definition M084 uses when it evaluates.
    """
    if captured_at is None:
        return "no quote was captured, so its freshness cannot be established"
    oldest = broker_now.age_of(captured_at)[1]
    if oldest > policy.quote_maximum_age_seconds:
        return (
            f"the quote is {int(oldest)}s old, older than the "
            f"{policy.quote_maximum_age_seconds}s limit"
        )
    if oldest < 0:
        # A future-dated quote is a CONSISTENCY problem, not a safety margin, so it is
        # refused only when it is future-dated even at the latest instant the broker's
        # clock could now be showing. Refusing on `youngest < 0` instead would refuse
        # sub-second feed skew on a quote that is milliseconds old -- which is
        # precisely the defect that made every fresh quote unusable in an open market.
        return "the captured quote is dated after the latest possible current time"
    if bid is None or ask is None or not bid.is_finite() or not ask.is_finite():
        return "the quote has no usable bid and ask"
    if bid <= 0 or ask <= 0:
        return "the quote bid and ask must both be positive"
    if ask < bid:
        return "the quote is crossed (ask below bid)"
    spread = (ask - bid) / ((ask + bid) / Decimal(2)) * Decimal(100)
    if spread > policy.maximum_spread_percent:
        return (
            f"the quote spread {spread.quantize(Decimal('0.0001'))}% exceeds the "
            f"{policy.maximum_spread_percent}% limit"
        )
    return None


def entry_window_refusal(*, policy: ExecutionPolicy, broker_now: BoundedInstant) -> str | None:
    """Whether the whole broker interval lies inside the configured entry window.

    A time-of-day rule, so it is judged on the broker's clock in the operator's
    timezone and never through a host offset. Both ends of the interval must be inside
    the window on the same calendar date; an interval that might be outside is.
    """
    zone = ZoneInfo(policy.operator_timezone)
    earliest = broker_now.earliest.astimezone(zone)
    latest = broker_now.latest.astimezone(zone)
    if earliest.date() != latest.date():
        return "the broker time interval spans two calendar dates in the operator timezone"
    if (
        earliest.timetz().replace(tzinfo=None) < policy.earliest_entry_time
        or latest.timetz().replace(tzinfo=None) > policy.latest_entry_time
    ):
        return (
            "the broker clock is outside the configured entry window "
            f"{policy.earliest_entry_time.isoformat()}-{policy.latest_entry_time.isoformat()} "
            f"({policy.operator_timezone})"
        )
    return None


def liquidation_session_refusal(
    *, liquidation_at: datetime, policy: ExecutionPolicy, broker_now: BoundedInstant
) -> str | None:
    """Refuse a liquidation deadline written for a date other than the broker's today.

    M084 writes the mandatory liquidation as a TIME OF DAY on the evaluating host's
    calendar date. If that date is not the date the broker's clock shows now, the
    deadline cannot be evaluated conservatively at all, so it refuses.
    """
    zone = ZoneInfo(policy.operator_timezone)
    written_for = liquidation_at.astimezone(zone).date()
    if (
        broker_now.earliest.astimezone(zone).date() != written_for
        or broker_now.latest.astimezone(zone).date() != written_for
    ):
        return (
            f"the mandatory liquidation deadline was written for {written_for.isoformat()}, "
            "which is not the broker's current date; it cannot be evaluated conservatively"
        )
    return None


@dataclass(frozen=True, slots=True)
class PaperOrderRequest:
    """The exact broker request. Every field a human authorizes is here.

    Long-only and never fractional: `quantity` is an int because MILESTONE-084's
    `ApprovedOrderIntent.quantity` is an int, and no code path in this milestone
    widens it. That removes Alpaca's fractional-order rules from the reachable
    surface entirely rather than leaving them to be handled correctly.
    """

    symbol: str
    side: str
    quantity: int
    order_type: OrderType
    limit_price: Decimal | None
    time_in_force: str
    extended_hours: bool
    client_order_id: str

    def __post_init__(self) -> None:
        if self.symbol != self.symbol.strip().upper() or not self.symbol:
            raise ValueError("symbol must be upper-case and unpadded")
        if self.side != "BUY":
            raise ValueError("side must be BUY: this product is long-only")
        if isinstance(self.quantity, bool) or not isinstance(self.quantity, int):
            raise ValueError("quantity must be an int")
        if self.quantity <= 0:
            raise ValueError("quantity must be positive")
        if not isinstance(self.order_type, OrderType):
            raise ValueError("order_type must be an OrderType")
        if self.order_type is OrderType.LIMIT:
            if self.limit_price is None:
                raise ValueError("a LIMIT request must carry a limit_price")
            _require_positive_money(self.limit_price, field="limit_price")
        elif self.limit_price is not None:
            raise ValueError("a non-LIMIT request must not carry a limit_price")
        if self.time_in_force != "DAY":
            raise ValueError("time_in_force must be DAY")
        if self.extended_hours is not False:
            raise ValueError(
                "extended_hours must be False: no milestone has authorized extended-hours execution"
            )
        if not isinstance(self.client_order_id, str) or not self.client_order_id:
            raise ValueError("client_order_id must be a non-empty string")
        if len(self.client_order_id) > MAXIMUM_BROKER_CLIENT_ORDER_ID_LENGTH:
            raise ValueError("client_order_id exceeds the broker's documented maximum")

    @property
    def notional_ceiling(self) -> Decimal | None:
        """The most this request could cost, when that is knowable in advance.

        Knowable for a LIMIT order and NOT knowable for a MARKET order, which is
        exactly why this returns None rather than an estimate for the latter: a
        guessed ceiling that a caller then enforces would be a limit in name
        only.
        """
        if self.order_type is OrderType.LIMIT and self.limit_price is not None:
            return self.limit_price * Decimal(self.quantity)
        return None


def request_fingerprint(
    *,
    order: PaperOrderRequest,
    account_reference: str,
    endpoint_host: str,
    intent_governance_id: str,
    approved_fingerprint: str,
    policy_fingerprint: str,
) -> str:
    """The digest a human authorization is bound to.

    Covers the ORDER, the ACCOUNT, the ENDPOINT and the SEND-TIME POLICY together.
    Binding the order alone would let an authorization for one paper account be
    replayed against another; binding the endpoint means an authorization cannot
    survive being pointed somewhere else; binding the policy (corrective pass, D1)
    means the limits a human authorized under cannot be swapped for looser ones.

    Canonical JSON with sorted keys, so the digest depends on the values and not
    on the order a dict happened to be built in.
    """
    _require_identifier(account_reference, field="account_reference")
    _require_identifier(intent_governance_id, field="intent_governance_id")
    _require_digest(approved_fingerprint, field="approved_fingerprint")
    _require_digest(policy_fingerprint, field="policy_fingerprint")
    if endpoint_host != PAPER_ENDPOINT_HOST:
        raise ValueError(f"endpoint_host must be exactly {PAPER_ENDPOINT_HOST}")

    return _canonical_digest(
        {
            "account_reference": account_reference,
            "approved_fingerprint": approved_fingerprint,
            "endpoint_host": endpoint_host,
            "extended_hours": order.extended_hours,
            "intent_governance_id": intent_governance_id,
            "limit_price": _decimal_text(order.limit_price),
            "order_type": order.order_type.value,
            "policy_fingerprint": policy_fingerprint,
            "quantity": order.quantity,
            "side": order.side,
            "symbol": order.symbol,
            "time_in_force": order.time_in_force,
        }
    )


def derive_client_order_id(
    *, intent_governance_id: str, account_reference: str, approved_fingerprint: str
) -> str:
    """The one broker-facing order identity for this intent on this account.

    DERIVED, never generated. A random id would make a retry after an ambiguous
    timeout create a SECOND order, which is the single worst failure this
    milestone exists to prevent. Because the value is a pure function of
    persisted identity, a crashed worker, a second worker and a reconciliation
    all recompute exactly the same string.

    The approved fingerprint is included so that a different set of order terms
    is a different broker identity rather than a silent overwrite of the same
    one.
    """
    _require_identifier(intent_governance_id, field="intent_governance_id")
    _require_identifier(account_reference, field="account_reference")
    _require_digest(approved_fingerprint, field="approved_fingerprint")
    material = f"{intent_governance_id}|{account_reference}|{approved_fingerprint}"
    digest = hashlib.sha256(material.encode("utf-8")).hexdigest()[:40]
    return f"{CLIENT_ORDER_ID_PREFIX}{digest}"


@dataclass(frozen=True, slots=True)
class SubmissionPreview:
    """Exactly what a human is shown before authorizing, frozen at that instant.

    The preview is the subject of the authorization. Anything a human should
    have seen in order to consent belongs in here, because the authorization
    binds `preview_id` AND `request_fingerprint`: showing one thing and
    dispatching another is then a mismatch the database refuses rather than an
    inconsistency nobody notices.
    """

    preview_id: str
    intent_governance_id: str
    preview_version: int
    account_snapshot_id: str
    account_reference: str
    order: PaperOrderRequest
    request_fingerprint: str
    approved_fingerprint: str
    market_is_open: bool
    market_next_open: datetime | None
    market_next_close: datetime | None
    quote_bid: Decimal | None
    quote_ask: Decimal | None
    quote_captured_at: datetime | None
    quote_source: str
    asset_tradable: bool
    asset_status: str
    asset_class: str
    asset_exchange: str
    asset_fractionable: bool
    #: The send-time limits this preview was judged under, from the intent's own
    #: configuration version. Corrective pass (D1): never from a command argument.
    policy: ExecutionPolicy
    #: The approved intent's expiry, copied so an authorization cannot outlive it.
    intent_expires_at: datetime
    refusals: tuple[str, ...]
    created_at: datetime

    def __post_init__(self) -> None:
        _require_identifier(self.preview_id, field="preview_id")
        _require_identifier(self.intent_governance_id, field="intent_governance_id")
        _require_identifier(self.account_snapshot_id, field="account_snapshot_id")
        _require_identifier(self.account_reference, field="account_reference")
        _require_digest(self.request_fingerprint, field="request_fingerprint")
        _require_digest(self.approved_fingerprint, field="approved_fingerprint")
        if isinstance(self.preview_version, bool) or not isinstance(self.preview_version, int):
            raise ValueError("preview_version must be an int")
        if self.preview_version < 1:
            raise ValueError("preview_version must start at 1")
        if not isinstance(self.order, PaperOrderRequest):
            raise ValueError("order must be a PaperOrderRequest")
        if not isinstance(self.policy, ExecutionPolicy):
            raise ValueError("policy must be an ExecutionPolicy")
        _require_aware(self.intent_expires_at, field="intent_expires_at")
        if not isinstance(self.refusals, tuple) or any(
            not isinstance(reason, str) or not reason.strip() for reason in self.refusals
        ):
            raise ValueError("refusals must be a tuple of non-empty strings")
        _require_aware(self.created_at, field="created_at")

    @property
    def binding_fingerprint(self) -> str:
        """The digest an authorization copies to prove WHICH preview it was granted on.

        Covers the exact order, the account, the request fingerprint, the policy and
        its configuration version, the notional cap, the quote evidence the human was
        shown, the intent expiry and the instant the preview was frozen.
        """
        return _canonical_digest(
            {
                "account_reference": self.account_reference,
                "approved_fingerprint": self.approved_fingerprint,
                "client_order_id": self.order.client_order_id,
                "configuration_governance_id": self.policy.configuration_governance_id,
                "configuration_version": self.policy.configuration_version,
                "created_at": _instant_text(self.created_at),
                "extended_hours": self.order.extended_hours,
                "intent_expires_at": _instant_text(self.intent_expires_at),
                "intent_governance_id": self.intent_governance_id,
                "limit_price": _canonical_decimal(self.order.limit_price),
                "maximum_notional": _canonical_decimal(self.policy.maximum_notional),
                "order_type": self.order.order_type.value,
                "policy_fingerprint": self.policy.fingerprint,
                "preview_id": self.preview_id,
                "preview_version": self.preview_version,
                "quantity": self.order.quantity,
                "quote_ask": _canonical_decimal(self.quote_ask),
                "quote_bid": _canonical_decimal(self.quote_bid),
                "quote_captured_at": _instant_text(self.quote_captured_at),
                "request_fingerprint": self.request_fingerprint,
                "side": self.order.side,
                "symbol": self.order.symbol,
                "time_in_force": self.order.time_in_force,
            }
        )

    @property
    def is_authorizable(self) -> bool:
        """Whether a human may be offered this preview to authorize at all.

        A preview with refusals is still PRODUCED and still stored, because an
        operator asking "why can I not send this" deserves the list rather than
        an empty result. It simply cannot be authorized.
        """
        return not self.refusals


@dataclass(frozen=True, slots=True)
class ExecutionAuthorization:
    """One human being's explicit, expiring, single-use permission.

    Every field of the order it permits is pinned by `request_fingerprint`, and
    the account by `account_reference`. There is no member meaning "approved
    because nothing objected": this record exists only when a person created it.
    """

    authorization_id: str
    intent_governance_id: str
    preview_id: str
    preview_version: int
    request_fingerprint: str
    account_reference: str
    client_order_id: str
    authorized_by: str
    authorized_at: datetime
    expires_at: datetime
    consumed_at: datetime | None
    consumed_by_attempt_id: str | None
    #: THE PREVIEW BINDING (corrective pass, item 6). Copies of what the human was
    #: shown, compared against the stored preview by the domain and again by the
    #: database guard at insert. `preview_binding_fingerprint` is the preview's own
    #: `binding_fingerprint`; the individual fields make a mismatch nameable.
    symbol: str
    side: str
    quantity: int
    order_type: OrderType
    limit_price: Decimal | None
    maximum_notional: Decimal
    quote_bid: Decimal | None
    quote_ask: Decimal | None
    quote_captured_at: datetime | None
    configuration_governance_id: str
    configuration_version: int
    policy_fingerprint: str
    preview_binding_fingerprint: str
    #: THE AUTHORIZATION-TIME BROKER BASIS, measured as an interval when the human
    #: authorized. `basis_host_at` is this host's conservative reading AFTER the
    #: broker clock response was read, and `basis_broker_earliest_at` the broker's
    #: reported timestamp; `basis_host_requested_at` and `basis_broker_latest_at`
    #: record the round trip that justifies pairing them. See `BrokerTimeBasis`.
    #:
    #: SUPERSEDED: until `d4f18a6c2e97` this comment said the pair was "taken at the
    #: SAME moment". It was not -- `basis_host_at` was the pre-fetch command instant,
    #: and the fetch latency extended every mapped expiry. A row carrying only the
    #: pair is that legacy shape: it is readable, but not dispatchable.
    basis_host_at: datetime | None = None
    basis_broker_earliest_at: datetime | None = None
    basis_host_requested_at: datetime | None = None
    basis_broker_latest_at: datetime | None = None

    def __post_init__(self) -> None:
        for field_name in (
            "authorization_id",
            "intent_governance_id",
            "preview_id",
            "account_reference",
            "authorized_by",
        ):
            _require_identifier(getattr(self, field_name), field=field_name)
        _require_digest(self.request_fingerprint, field="request_fingerprint")
        _require_digest(self.policy_fingerprint, field="policy_fingerprint")
        _require_digest(self.preview_binding_fingerprint, field="preview_binding_fingerprint")
        _require_identifier(self.configuration_governance_id, field="configuration_governance_id")
        if isinstance(self.configuration_version, bool) or not isinstance(
            self.configuration_version, int
        ):
            raise ValueError("configuration_version must be an int")
        if isinstance(self.quantity, bool) or not isinstance(self.quantity, int):
            raise ValueError("quantity must be an int")
        if not isinstance(self.order_type, OrderType):
            raise ValueError("order_type must be an OrderType")
        _require_positive_money(self.maximum_notional, field="maximum_notional")
        if self.quote_captured_at is not None:
            _require_aware(self.quote_captured_at, field="quote_captured_at")
        if isinstance(self.preview_version, bool) or not isinstance(self.preview_version, int):
            raise ValueError("preview_version must be an int")
        if self.preview_version < 1:
            raise ValueError("preview_version must start at 1")
        _require_aware(self.authorized_at, field="authorized_at")
        _require_aware(self.expires_at, field="expires_at")
        if self.expires_at <= self.authorized_at:
            raise ValueError("expires_at must follow authorized_at")
        if (self.consumed_at is None) != (self.consumed_by_attempt_id is None):
            raise ValueError(
                "consumed_at and consumed_by_attempt_id are set together or not at all"
            )
        if self.consumed_at is not None:
            _require_aware(self.consumed_at, field="consumed_at")
        if (self.basis_host_at is None) != (self.basis_broker_earliest_at is None):
            raise ValueError(
                "basis_host_at and basis_broker_earliest_at are set together or not at all"
            )
        if (self.basis_host_requested_at is None) != (self.basis_broker_latest_at is None):
            raise ValueError(
                "basis_host_requested_at and basis_broker_latest_at are set together or not at all"
            )
        if self.basis_host_requested_at is not None and self.basis_host_at is None:
            raise ValueError("a basis interval requires the basis readings it bounds")
        authorization_basis = self.time_basis
        if authorization_basis is not None and self.authorized_at > authorization_basis.host_at:
            # The expiry is `authorized_at + validity`. An `authorized_at` later than
            # the host reading the basis pairs with would push the mapped expiry
            # later by exactly that difference, so it is refused rather than mapped.
            raise ValueError(
                "authorized_at is later than the host reading the broker basis was "
                "measured at; a future-dated authorization cannot be mapped"
            )

    def is_expired_at(self, instant: datetime) -> bool:
        _require_aware(instant, field="instant")
        return instant >= self.expires_at

    @property
    def time_basis(self) -> BrokerTimeBasis | None:
        """The interval-shaped authorization-time basis, or None when there is none.

        None both for a row with no basis and for a legacy row carrying only the
        pair: that pair's host reading preceded the broker fetch, which is the
        defect the interval replaces, so it is neither trusted nor repaired.
        """
        if (
            self.basis_host_requested_at is None
            or self.basis_host_at is None
            or self.basis_broker_earliest_at is None
            or self.basis_broker_latest_at is None
        ):
            return None
        return BrokerTimeBasis(
            host_requested_at=self.basis_host_requested_at,
            host_at=self.basis_host_at,
            broker_earliest_at=self.basis_broker_earliest_at,
            broker_latest_at=self.basis_broker_latest_at,
        )

    @property
    def has_broker_time_basis(self) -> bool:
        return self.time_basis is not None

    def on_broker_timeline(self, host_instant: datetime) -> datetime:
        """Map THIS AUTHORIZATION's own host-written expiry onto the broker's timeline.

        WHY THIS EXISTS. `expires_at` is an absolute instant produced by this host's
        wall clock. Monotonic time protects it only while one process runs. Once the
        approving process exits, a host clock that steps BACKWARD makes the stored
        expiry look further away, and a new dispatch process has no memory with
        which to notice.

        WHAT IT MAY TRANSLATE. Only deadlines written in the act this basis was
        measured for -- the authorization's own expiry. MILESTONE-084's intent
        deadlines were written earlier, under whatever host offset held when the
        intent was issued; translating them through this basis shifts them by any
        host clock movement between issuance and authorization. That was the
        second defect, and those deadlines now use `IntentTimeBasis` instead.
        """
        _require_aware(host_instant, field="host_instant")
        authorization_basis = self.time_basis
        if authorization_basis is None:
            raise ValueError(
                "this authorization carries no broker time basis measured as an interval "
                "and cannot be mapped onto the broker timeline"
            )
        return authorization_basis.on_broker_timeline(host_instant)

    @property
    def is_consumed(self) -> bool:
        return self.consumed_at is not None

    def refusal_against(
        self,
        *,
        request_fingerprint_now: str,
        account_reference_now: str,
        instant: datetime,
        broker_now: BoundedInstant | None = None,
    ) -> str | None:
        """Why this authorization does not permit the dispatch being attempted.

        Returns None when it does. Expressed as a single function so that every
        caller asks the same question the same way -- a check spread across call
        sites is a check one call site will omit.

        `instant` is this host's conservative current instant, and `broker_now`
        bounds the broker's. BOTH must permit: the host check catches elapsed work
        inside this process, and the broker check catches a host clock that moved
        between the approving process and this one. An authorization with no
        interval-shaped basis is refused outright, and so is a caller that supplies
        no `broker_now`, because the stronger of the two must never be skippable.
        """
        if self.is_consumed:
            return "the authorization has already been used"
        if self.is_expired_at(instant):
            return "the authorization has expired"
        authorization_basis = self.time_basis
        if authorization_basis is None:
            return NO_AUTHORIZATION_TIME_BASIS
        if broker_now is None:
            return (
                "this authorization carries a broker time basis and cannot be "
                "checked without the broker's current instant"
            )
        if (
            broker_now is not None
            and authorization_basis is not None
            and broker_now.possibly_at_or_after(
                authorization_basis.on_broker_timeline(self.expires_at)
            )
        ):
            return "the authorization has expired on the broker's clock"
        if self.request_fingerprint != request_fingerprint_now:
            return (
                "the order changed after it was authorized; the authorized "
                "fingerprint does not match the request being dispatched"
            )
        if self.account_reference != account_reference_now:
            return "the authorization was granted for a different paper account"
        return None


def authorization_binding_refusal(
    *, authorization: ExecutionAuthorization, preview: SubmissionPreview
) -> str | None:
    """Why `authorization` is not a permission for exactly `preview`.

    Every field the human consented to must be the preview's, the preview must have
    been authorizable, and the permission may not outlive the approved intent. The
    database insert guard asks the same questions of the stored preview row.
    """
    pairs: tuple[tuple[str, object, object], ...] = (
        ("preview_id", preview.preview_id, authorization.preview_id),
        ("preview_version", preview.preview_version, authorization.preview_version),
        ("intent_governance_id", preview.intent_governance_id, authorization.intent_governance_id),
        ("request_fingerprint", preview.request_fingerprint, authorization.request_fingerprint),
        ("account_reference", preview.account_reference, authorization.account_reference),
        ("client_order_id", preview.order.client_order_id, authorization.client_order_id),
        ("symbol", preview.order.symbol, authorization.symbol),
        ("side", preview.order.side, authorization.side),
        ("quantity", preview.order.quantity, authorization.quantity),
        ("order_type", preview.order.order_type, authorization.order_type),
        ("limit_price", preview.order.limit_price, authorization.limit_price),
        ("maximum_notional", preview.policy.maximum_notional, authorization.maximum_notional),
        ("quote_bid", preview.quote_bid, authorization.quote_bid),
        ("quote_ask", preview.quote_ask, authorization.quote_ask),
        ("quote_captured_at", preview.quote_captured_at, authorization.quote_captured_at),
        (
            "configuration_governance_id",
            preview.policy.configuration_governance_id,
            authorization.configuration_governance_id,
        ),
        (
            "configuration_version",
            preview.policy.configuration_version,
            authorization.configuration_version,
        ),
        ("policy_fingerprint", preview.policy.fingerprint, authorization.policy_fingerprint),
        (
            "preview_binding_fingerprint",
            preview.binding_fingerprint,
            authorization.preview_binding_fingerprint,
        ),
    )
    mismatched = [label for label, shown, bound in pairs if shown != bound]
    if mismatched:
        return (
            "the authorization does not describe the preview it names ("
            + ", ".join(mismatched)
            + "); it permits nothing"
        )
    if not preview.is_authorizable:
        return "the authorization names a preview that was not authorizable"
    if authorization.expires_at > preview.intent_expires_at:
        return "the authorization outlives the approved intent it would dispatch"
    return None


@dataclass(frozen=True, slots=True)
class IntentTimeBasis:
    """The broker time basis measured AT THE ISSUANCE of one exact M084 intent.

    WHY AN AUTHORIZATION'S BASIS CANNOT DO THIS JOB. MILESTONE-084's `expires_at`
    and `mandatory_liquidation_at` were written under whatever host-to-broker
    offset held when the intent was issued. An authorization is measured later.
    If the host clock moved in between, translating the intent's deadlines through
    the authorization's basis shifts them by that whole movement. Reproduced
    before this type existed: intent issued with the host correct, host clock then
    stepped back an hour, authorization taken, and a new dispatch process after the
    real intent deadline was permitted because the deadline mapped an hour late.

    WHAT BINDS IT TO ISSUANCE. `intent_created_at` must EQUAL `basis_host_at`. The
    Paper-bound issuance command measures the basis first and hands that exact
    conservative host reading to MILESTONE-084's own handler as `created_at`. A
    basis measured afterwards cannot equal the `created_at` of an intent that
    already exists, which makes a backfill unrepresentable rather than discouraged.

    WHAT BINDS IT TO THE EXACT INTENT. The fingerprint and the three M084 instants
    are copied here and compared against the stored intent on every use; the
    database compares them again at insert. The M084 record is read, never
    rewritten, reinterpreted or relaxed, and its host-timeline checks still run.

    SUPERSEDED: WHAT IT IS USED FOR. Until `e61b3f9a4c27` this basis translated the
    intent's `expires_at` and `mandatory_liquidation_at`, and the docstring called
    the proposal-to-issuance interval a residual limit "bounded only by M084's own
    approval expiry". Both were wrong: those deadlines are written when the PROPOSAL
    is evaluated, and the approval expiry was written on that same earlier host
    timeline, so it bounds nothing. Reproduced at `73a2f96`. This basis now places
    only the ISSUANCE on the broker's clock, so the recorded chronology -- issued
    before the proposal, liquidation and approval deadlines, each through its own
    basis -- can be checked. It translates no deadline.
    """

    intent_governance_id: str
    approved_fingerprint: str
    intent_created_at: datetime
    intent_expires_at: datetime
    intent_mandatory_liquidation_at: datetime
    broker_endpoint_host: str
    basis_host_requested_at: datetime
    basis_host_at: datetime
    basis_broker_earliest_at: datetime
    basis_broker_latest_at: datetime

    def __post_init__(self) -> None:
        _require_identifier(self.intent_governance_id, field="intent_governance_id")
        _require_digest(self.approved_fingerprint, field="approved_fingerprint")
        for field_name in (
            "intent_created_at",
            "intent_expires_at",
            "intent_mandatory_liquidation_at",
            "basis_host_requested_at",
            "basis_host_at",
            "basis_broker_earliest_at",
            "basis_broker_latest_at",
        ):
            _require_aware(getattr(self, field_name), field=field_name)
        if self.broker_endpoint_host != PAPER_ENDPOINT_HOST:
            raise ValueError(f"broker_endpoint_host must be exactly {PAPER_ENDPOINT_HOST}")
        if self.intent_created_at != self.basis_host_at:
            raise ValueError(
                "the intent was not issued at the instant this basis measured; an "
                "intent-time basis cannot be attached to an intent after the fact"
            )
        if self.intent_expires_at <= self.intent_created_at:
            raise ValueError("intent_expires_at must follow intent_created_at")
        # Constructing the basis validates the interval's own ordering.
        _ = self.time_basis

    @property
    def time_basis(self) -> BrokerTimeBasis:
        return BrokerTimeBasis(
            host_requested_at=self.basis_host_requested_at,
            host_at=self.basis_host_at,
            broker_earliest_at=self.basis_broker_earliest_at,
            broker_latest_at=self.basis_broker_latest_at,
        )


def bind_intent_time_basis(
    *, intent: ApprovedOrderIntent, time_basis: BrokerTimeBasis, broker_endpoint_host: str
) -> IntentTimeBasis:
    """Record the basis measured for issuing `intent`. Refuses any other intent."""
    if not isinstance(intent, ApprovedOrderIntent):
        raise ValueError("intent must be an ApprovedOrderIntent")
    if not isinstance(time_basis, BrokerTimeBasis):
        raise ValueError("time_basis must be a BrokerTimeBasis")
    return IntentTimeBasis(
        intent_governance_id=intent.intent_governance_id,
        approved_fingerprint=intent.approved_fingerprint,
        intent_created_at=intent.created_at,
        intent_expires_at=intent.expires_at,
        intent_mandatory_liquidation_at=intent.mandatory_liquidation_at,
        broker_endpoint_host=broker_endpoint_host,
        basis_host_requested_at=time_basis.host_requested_at,
        basis_host_at=time_basis.host_at,
        basis_broker_earliest_at=time_basis.broker_earliest_at,
        basis_broker_latest_at=time_basis.broker_latest_at,
    )


def intent_time_basis_refusal(
    *, intent: ApprovedOrderIntent, evidence: IntentTimeBasis | None
) -> str | None:
    """Why `evidence` cannot place this intent's deadlines on the broker's clock."""
    if evidence is None:
        return NO_INTENT_TIME_BASIS
    mismatched = [
        label
        for label, stored, recorded in (
            ("intent_governance_id", intent.intent_governance_id, evidence.intent_governance_id),
            ("approved_fingerprint", intent.approved_fingerprint, evidence.approved_fingerprint),
            ("created_at", intent.created_at, evidence.intent_created_at),
            ("expires_at", intent.expires_at, evidence.intent_expires_at),
            (
                "mandatory_liquidation_at",
                intent.mandatory_liquidation_at,
                evidence.intent_mandatory_liquidation_at,
            ),
        )
        if stored != recorded
    ]
    if mismatched:
        return (
            "the intent-time broker basis does not describe this exact intent ("
            + ", ".join(mismatched)
            + "); it cannot be used, and the intent is not dispatchable"
        )
    return None


def _basis_fields_valid(evidence: object, *, bound_field: str, act: str) -> None:
    """Shared validation for a basis bound to the act that wrote its deadlines."""
    for field_name in (
        "basis_host_requested_at",
        "basis_host_at",
        "basis_broker_earliest_at",
        "basis_broker_latest_at",
        bound_field,
    ):
        _require_aware(getattr(evidence, field_name), field=field_name)
    if getattr(evidence, "broker_endpoint_host") != PAPER_ENDPOINT_HOST:  # noqa: B009
        raise ValueError(f"broker_endpoint_host must be exactly {PAPER_ENDPOINT_HOST}")
    if getattr(evidence, bound_field) != getattr(evidence, "basis_host_at"):  # noqa: B009
        raise ValueError(
            f"the {act} did not happen at the instant this basis measured; a basis "
            f"cannot be attached to a {act} after the fact"
        )


@dataclass(frozen=True, slots=True)
class ProposalTimeBasis:
    """The broker time basis measured WHEN ONE EXACT M084 PROPOSAL WAS EVALUATED.

    WHY THIS ACT. MILESTONE-084 writes `expires_at` (evaluation + proposal expiry)
    and `mandatory_liquidation_at` (the evaluation date's liquidation time) when it
    evaluates the proposal, and copies both unchanged into the intent. They were
    written under the host-to-broker offset of THAT moment, so only a basis measured
    then may translate them. A basis measured at issuance or authorization is later
    and maps them by whatever the host clock did in between -- reproduced at `73a2f96`
    with an hour of drift and a dispatch that reached the broker.

    WHAT BINDS IT. `proposal_created_at` must EQUAL `basis_host_at`: the Paper-bound
    proposal command measures the basis first and hands that reading to M084's own
    handler as `evaluated_at`, which M084 stores as `created_at`. The fingerprint,
    version and both deadlines are copied, compared on every use, and compared again
    by the database against the stored proposal row.
    """

    proposal_governance_id: str
    proposal_version: int
    content_fingerprint: str
    proposal_created_at: datetime
    proposal_expires_at: datetime
    mandatory_liquidation_at: datetime
    broker_endpoint_host: str
    basis_host_requested_at: datetime
    basis_host_at: datetime
    basis_broker_earliest_at: datetime
    basis_broker_latest_at: datetime

    def __post_init__(self) -> None:
        _require_identifier(self.proposal_governance_id, field="proposal_governance_id")
        if isinstance(self.proposal_version, bool) or not isinstance(self.proposal_version, int):
            raise ValueError("proposal_version must be an int")
        _require_digest(self.content_fingerprint, field="content_fingerprint")
        _require_aware(self.proposal_expires_at, field="proposal_expires_at")
        _require_aware(self.mandatory_liquidation_at, field="mandatory_liquidation_at")
        _basis_fields_valid(self, bound_field="proposal_created_at", act="proposal evaluation")
        if self.proposal_expires_at <= self.proposal_created_at:
            raise ValueError("proposal_expires_at must follow proposal_created_at")
        _ = self.time_basis

    @property
    def time_basis(self) -> BrokerTimeBasis:
        return BrokerTimeBasis(
            host_requested_at=self.basis_host_requested_at,
            host_at=self.basis_host_at,
            broker_earliest_at=self.basis_broker_earliest_at,
            broker_latest_at=self.basis_broker_latest_at,
        )


@dataclass(frozen=True, slots=True)
class DecisionTimeBasis:
    """The broker time basis measured WHEN A HUMAN APPROVED ONE EXACT PROPOSAL.

    WHY THIS ACT. MILESTONE-084 writes the approval's `expires_at` as `decided_at`
    plus the approval expiry, on the host clock of the decision. Only a basis
    measured then may translate it. The approval expiry is not a bound on host
    clock movement between evaluation and issuance: it was written on the same
    host timeline it would have to bound.

    WHAT BINDS IT. `decided_at` must EQUAL `basis_host_at`, and the proposal
    identity, version, approved fingerprint and expiry are copied and compared --
    by the domain on every use and by the database against the stored approval.
    Only an APPROVE decision carries an expiry, so only an approval has one.
    """

    decision_governance_id: str
    proposal_governance_id: str
    proposal_version: int
    approved_fingerprint: str
    decided_at: datetime
    decision_expires_at: datetime
    broker_endpoint_host: str
    basis_host_requested_at: datetime
    basis_host_at: datetime
    basis_broker_earliest_at: datetime
    basis_broker_latest_at: datetime

    def __post_init__(self) -> None:
        _require_identifier(self.decision_governance_id, field="decision_governance_id")
        _require_identifier(self.proposal_governance_id, field="proposal_governance_id")
        if isinstance(self.proposal_version, bool) or not isinstance(self.proposal_version, int):
            raise ValueError("proposal_version must be an int")
        _require_digest(self.approved_fingerprint, field="approved_fingerprint")
        _require_aware(self.decision_expires_at, field="decision_expires_at")
        _basis_fields_valid(self, bound_field="decided_at", act="decision")
        if self.decision_expires_at <= self.decided_at:
            raise ValueError("decision_expires_at must follow decided_at")
        _ = self.time_basis

    @property
    def time_basis(self) -> BrokerTimeBasis:
        return BrokerTimeBasis(
            host_requested_at=self.basis_host_requested_at,
            host_at=self.basis_host_at,
            broker_earliest_at=self.basis_broker_earliest_at,
            broker_latest_at=self.basis_broker_latest_at,
        )


def bind_proposal_time_basis(
    *, proposal: TradeProposal, time_basis: BrokerTimeBasis, broker_endpoint_host: str
) -> ProposalTimeBasis:
    """Record the basis measured for evaluating `proposal`. Refuses any other proposal."""
    if not isinstance(proposal, TradeProposal):
        raise ValueError("proposal must be a TradeProposal")
    return ProposalTimeBasis(
        proposal_governance_id=proposal.proposal_governance_id,
        proposal_version=proposal.proposal_version,
        content_fingerprint=proposal.content_fingerprint,
        proposal_created_at=proposal.created_at,
        proposal_expires_at=proposal.expires_at,
        mandatory_liquidation_at=proposal.mandatory_liquidation_at,
        broker_endpoint_host=broker_endpoint_host,
        basis_host_requested_at=time_basis.host_requested_at,
        basis_host_at=time_basis.host_at,
        basis_broker_earliest_at=time_basis.broker_earliest_at,
        basis_broker_latest_at=time_basis.broker_latest_at,
    )


def bind_decision_time_basis(
    *, decision: ApprovalDecision, time_basis: BrokerTimeBasis, broker_endpoint_host: str
) -> DecisionTimeBasis:
    """Record the basis measured for one APPROVAL. Refuses a rejection or cancellation."""
    if not isinstance(decision, ApprovalDecision):
        raise ValueError("decision must be an ApprovalDecision")
    if decision.action is not OperatorAction.APPROVE or decision.expires_at is None:
        raise ValueError("only an approval carries an expiry, so only an approval has a basis")
    return DecisionTimeBasis(
        decision_governance_id=decision.decision_governance_id,
        proposal_governance_id=decision.proposal_governance_id,
        proposal_version=decision.proposal_version,
        approved_fingerprint=decision.approved_fingerprint,
        decided_at=decision.decided_at,
        decision_expires_at=decision.expires_at,
        broker_endpoint_host=broker_endpoint_host,
        basis_host_requested_at=time_basis.host_requested_at,
        basis_host_at=time_basis.host_at,
        basis_broker_earliest_at=time_basis.broker_earliest_at,
        basis_broker_latest_at=time_basis.broker_latest_at,
    )


def _mismatch(kind: str, pairs: tuple[tuple[str, object, object], ...]) -> str | None:
    mismatched = [label for label, stored, recorded in pairs if stored != recorded]
    if not mismatched:
        return None
    return (
        f"the {kind} broker basis does not describe this exact record ("
        + ", ".join(mismatched)
        + "); it cannot be used, and the intent is not dispatchable"
    )


def proposal_time_basis_refusal(
    *,
    proposal_governance_id: str,
    proposal_version: int,
    fingerprint: str,
    expires_at: datetime,
    mandatory_liquidation_at: datetime,
    evidence: ProposalTimeBasis | None,
) -> str | None:
    """Why `evidence` cannot translate this proposal's deadlines."""
    if evidence is None:
        return NO_PROPOSAL_TIME_BASIS
    return _mismatch(
        "proposal-time",
        (
            ("proposal_governance_id", proposal_governance_id, evidence.proposal_governance_id),
            ("proposal_version", proposal_version, evidence.proposal_version),
            ("fingerprint", fingerprint, evidence.content_fingerprint),
            ("expires_at", expires_at, evidence.proposal_expires_at),
            (
                "mandatory_liquidation_at",
                mandatory_liquidation_at,
                evidence.mandatory_liquidation_at,
            ),
        ),
    )


def decision_time_basis_refusal(
    *,
    decision_governance_id: str,
    proposal_governance_id: str,
    proposal_version: int,
    approved_fingerprint: str,
    evidence: DecisionTimeBasis | None,
) -> str | None:
    """Why `evidence` cannot translate this approval's expiry."""
    if evidence is None:
        return NO_DECISION_TIME_BASIS
    return _mismatch(
        "decision-time",
        (
            ("decision_governance_id", decision_governance_id, evidence.decision_governance_id),
            ("proposal_governance_id", proposal_governance_id, evidence.proposal_governance_id),
            ("proposal_version", proposal_version, evidence.proposal_version),
            ("approved_fingerprint", approved_fingerprint, evidence.approved_fingerprint),
        ),
    )


def _broker_interval(basis: BrokerTimeBasis) -> BoundedInstant:
    return BoundedInstant(earliest=basis.broker_earliest_at, latest=basis.broker_latest_at)


def effective_liquidation_deadline(
    *, liquidation_at: datetime, proposal_basis: BrokerTimeBasis
) -> datetime:
    """The mandatory liquidation deadline on the broker's clock, never extended by skew.

    CORRECTIVE PASS (T1). M084 writes this deadline as a TIME OF DAY -- today's 15:45
    in the operator timezone -- not as `evaluated_at + duration`. Translating it
    through the proposal basis adds the host-to-broker offset measured at evaluation:
    a host running 30 minutes slow moved 15:45 to 16:15 on the broker's clock, a
    hidden extension. The calendar instant itself is already on the true timeline.
    The mapped instant still matters when the host ran FAST (it is then earlier), so
    the deadline is the EARLIER of the two -- skew can only shorten it.
    """
    _require_aware(liquidation_at, field="liquidation_at")
    return min(liquidation_at, proposal_basis.on_broker_timeline(liquidation_at))


def act_chronology_refusal(
    *,
    proposal: ProposalTimeBasis,
    decision: DecisionTimeBasis,
    issued: BrokerTimeBasis,
) -> str | None:
    """Did each later act happen, on the broker's clock, before the deadlines it relied on?

    Every deadline is placed on the broker timeline ONLY through the basis of the
    act that wrote it, and every act through its own measured broker interval. An
    act whose interval might reach a deadline counts as after it. Nothing earlier
    is translated through a later basis anywhere here.
    """
    proposal_basis = proposal.time_basis
    decision_basis = decision.time_basis
    proposal_expiry = proposal_basis.on_broker_timeline(proposal.proposal_expires_at)
    if _broker_interval(decision_basis).possibly_at_or_after(proposal_expiry):
        return "the approval was recorded after the proposal had expired on the broker's clock"
    issued_interval = _broker_interval(issued)
    for deadline, label in (
        (
            proposal_expiry,
            "the proposal had expired on the broker's clock when the intent was issued",
        ),
        (
            effective_liquidation_deadline(
                liquidation_at=proposal.mandatory_liquidation_at, proposal_basis=proposal_basis
            ),
            "the mandatory liquidation deadline had passed on the broker's clock when the "
            "intent was issued",
        ),
        (
            decision_basis.on_broker_timeline(decision.decision_expires_at),
            "the approval had expired on the broker's clock when the intent was issued",
        ),
    ):
        if issued_interval.possibly_at_or_after(deadline):
            return label
    return None


@dataclass(frozen=True, slots=True)
class M084TimeProvenance:
    """The three bases behind one intent: one per act that wrote or relied on a deadline."""

    proposal: ProposalTimeBasis | None
    decision: DecisionTimeBasis | None
    intent: IntentTimeBasis | None


def m084_provenance_refusal(
    *, intent: ApprovedOrderIntent, provenance: M084TimeProvenance
) -> str | None:
    """Why this intent's recorded provenance cannot support a dispatch.

    Missing evidence for ANY of the three acts refuses; evidence describing a
    different record refuses; and the recorded chronology must show the approval
    before the proposal expired and the issuance before the proposal, liquidation
    and approval deadlines -- each deadline through its own basis.
    """
    for refusal in (
        proposal_time_basis_refusal(
            proposal_governance_id=intent.proposal_governance_id,
            proposal_version=intent.proposal_version,
            fingerprint=intent.approved_fingerprint,
            expires_at=intent.expires_at,
            mandatory_liquidation_at=intent.mandatory_liquidation_at,
            evidence=provenance.proposal,
        ),
        decision_time_basis_refusal(
            decision_governance_id=intent.decision_governance_id,
            proposal_governance_id=intent.proposal_governance_id,
            proposal_version=intent.proposal_version,
            approved_fingerprint=intent.approved_fingerprint,
            evidence=provenance.decision,
        ),
        intent_time_basis_refusal(intent=intent, evidence=provenance.intent),
    ):
        if refusal is not None:
            return refusal
    if provenance.proposal is None or provenance.decision is None or provenance.intent is None:
        # Unreachable while the rules above stand. It falls through rather than
        # raising so that removing one of them is observable as a dispatch.
        return None
    return act_chronology_refusal(
        proposal=provenance.proposal,
        decision=provenance.decision,
        issued=provenance.intent.time_basis,
    )


def m084_deadline_refusal_on_broker_time(
    *,
    intent: ApprovedOrderIntent,
    provenance: M084TimeProvenance,
    broker_now: BoundedInstant,
) -> str | None:
    """MILESTONE-084's two intent deadlines, on the broker's clock, through THEIR OWN basis.

    The intent's `expires_at` and `mandatory_liquidation_at` are the proposal's,
    copied unchanged, so they are translated only through the PROPOSAL-time basis.
    SUPERSEDED: until `e61b3f9a4c27` they were translated through the intent-time
    basis, measured later at issuance -- which let an hour of host drift between
    evaluation and issuance extend both. No authorization or issuance basis is
    consulted for them here.
    """
    refusal = m084_provenance_refusal(intent=intent, provenance=provenance)
    if refusal is not None:
        return refusal
    if provenance.proposal is None:
        return None
    proposal_basis = provenance.proposal.time_basis
    for deadline, label in (
        (
            proposal_basis.on_broker_timeline(intent.expires_at),
            "the approved intent has expired on the broker's clock",
        ),
        (
            effective_liquidation_deadline(
                liquidation_at=intent.mandatory_liquidation_at, proposal_basis=proposal_basis
            ),
            "the mandatory liquidation deadline has passed on the broker's clock",
        ),
    ):
        if broker_now.possibly_at_or_after(deadline):
            return label
    return None


@dataclass(frozen=True, slots=True)
class ExecutionAttempt:
    """The single claimed dispatch of one intent, and where it got to."""

    attempt_id: str
    intent_governance_id: str
    authorization_id: str
    client_order_id: str
    request_fingerprint: str
    state: PaperExecutionState
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

    def __post_init__(self) -> None:
        for field_name in (
            "attempt_id",
            "intent_governance_id",
            "authorization_id",
            "client_order_id",
        ):
            _require_identifier(getattr(self, field_name), field=field_name)
        _require_digest(self.request_fingerprint, field="request_fingerprint")
        if not isinstance(self.state, PaperExecutionState):
            raise ValueError("state must be a PaperExecutionState")
        _require_aware(self.claimed_at, field="claimed_at")
        if self.state in TERMINAL_PAPER_STATES and self.terminal_at is None:
            raise ValueError(f"{self.state.value} is terminal and requires terminal_at")
        if self.terminal_at is not None and self.state not in TERMINAL_PAPER_STATES:
            raise ValueError("terminal_at is only set for a terminal state")

    @property
    def is_terminal(self) -> bool:
        return self.state in TERMINAL_PAPER_STATES

    @property
    def outcome_is_known(self) -> bool:
        """Whether the broker's answer is known. UNKNOWN is not an answer."""
        return self.state is not PaperExecutionState.SUBMISSION_UNKNOWN


@dataclass(frozen=True, slots=True)
class BrokerAcknowledgement:
    """One thing the broker said, recorded as said, append-only.

    `sanitized_payload` is bounded and credential-free by construction at the
    adapter boundary. It is stored so that a later reader can see what the
    product actually received rather than the product's interpretation of it.
    """

    acknowledgement_id: str
    attempt_id: str
    sequence: int
    kind: str
    observed_at: datetime
    http_status: int
    broker_order_id: str | None
    broker_status: str | None
    client_order_id_echo: str | None
    payload_digest: str
    sanitized_payload: str

    def __post_init__(self) -> None:
        _require_identifier(self.acknowledgement_id, field="acknowledgement_id")
        _require_identifier(self.attempt_id, field="attempt_id")
        if isinstance(self.sequence, bool) or not isinstance(self.sequence, int):
            raise ValueError("sequence must be an int")
        if self.sequence < 1:
            raise ValueError("sequence must start at 1")
        if self.kind not in {"SUBMIT", "RECONCILE", "CANCEL"}:
            raise ValueError("kind must be SUBMIT, RECONCILE or CANCEL")
        _require_aware(self.observed_at, field="observed_at")
        if isinstance(self.http_status, bool) or not isinstance(self.http_status, int):
            raise ValueError("http_status must be an int")
        _require_digest(self.payload_digest, field="payload_digest")


@dataclass(frozen=True, slots=True)
class PaperExecutionEvent:
    """One audit entry. Append-only, and never the source of any state."""

    event_id: str
    intent_governance_id: str
    attempt_id: str | None
    event_type: str
    occurred_at: datetime
    detail: str

    def __post_init__(self) -> None:
        _require_identifier(self.event_id, field="event_id")
        _require_identifier(self.intent_governance_id, field="intent_governance_id")
        if not isinstance(self.event_type, str) or not self.event_type.strip():
            raise ValueError("event_type must be a non-empty string")
        _require_aware(self.occurred_at, field="occurred_at")


def build_submission_preview(
    *,
    preview_id: str,
    intent: ApprovedOrderIntent,
    account: PaperAccountSnapshot,
    preview_version: int,
    market_is_open: bool,
    market_next_open: datetime | None,
    market_next_close: datetime | None,
    quote_bid: Decimal | None,
    quote_ask: Decimal | None,
    quote_captured_at: datetime | None,
    quote_source: str,
    asset_tradable: bool,
    asset_status: str,
    asset_class: str,
    asset_exchange: str,
    asset_fractionable: bool,
    policy: ExecutionPolicy,
    existing_position_quantity: int,
    execution_kill_switch_engaged: bool,
    created_at: datetime,
    broker_now: BoundedInstant,
    m084_provenance: M084TimeProvenance,
) -> SubmissionPreview:
    """Freeze exactly what a human will be shown, refusals included.

    `m084_provenance` is REQUIRED: the bases recorded when the proposal was
    evaluated, approved and issued. A missing or mismatched one becomes a stated
    refusal, because the M084 deadlines cannot then be placed on the broker's clock.
    SUPERSEDED: until `e61b3f9a4c27` this took only the intent-time basis.

    Every refusal is COLLECTED rather than raised, so that an operator sees all
    of the reasons at once instead of fixing them one round-trip at a time. A
    preview carrying refusals cannot be authorized -- see `is_authorizable` --
    so collecting them is not the same as tolerating them.

    TWO CLOCKS, AND THEY ARE NOT INTERCHANGEABLE. `created_at` is this HOST's
    conservative current instant and is the only thing host-recorded deadlines
    are judged against -- the approved intent's expiry and its mandatory
    liquidation deadline were both written by this host's clock. `broker_now`
    bounds the BROKER's current instant and is the only thing broker-sourced
    facts are judged against -- the market session close, and the quote, which
    is stamped by Alpaca's market-data host.

    THE ONE CROSS-HOST ASSUMPTION, STATED. Quote freshness is evaluated on the
    broker timeline because `data.alpaca.markets` and `paper-api.alpaca.markets`
    are operated together and are taken to share a time base. This product
    cannot verify that from one observation, so it is recorded here as an
    assumption rather than a measurement. It replaces the previous, weaker
    assumption that the market-data host agreed with THIS machine's wall clock.
    """
    if not isinstance(intent, ApprovedOrderIntent):
        raise ValueError("intent must be an ApprovedOrderIntent")
    if not isinstance(account, PaperAccountSnapshot):
        raise ValueError("account must be a PaperAccountSnapshot")
    if not isinstance(policy, ExecutionPolicy):
        raise ValueError("policy must be the ExecutionPolicy of the intent's configuration")
    _require_aware(created_at, field="created_at")

    order = PaperOrderRequest(
        symbol=intent.symbol,
        side=intent.side,
        quantity=intent.quantity,
        order_type=intent.order_type,
        limit_price=intent.limit_price,
        time_in_force="DAY",
        extended_hours=False,
        client_order_id=derive_client_order_id(
            intent_governance_id=intent.intent_governance_id,
            account_reference=account.account_reference,
            approved_fingerprint=intent.approved_fingerprint,
        ),
    )

    refusals: list[str] = []
    if execution_kill_switch_engaged:
        refusals.append("the execution kill switch is engaged")
    if not account.is_dispatchable:
        refusals.append(f"the paper account does not permit orders ({account.account_status})")
    if account.environment is not PaperEnvironment.PAPER:
        refusals.append("the account snapshot is not a paper environment")
    if (
        intent.configuration_governance_id != policy.configuration_governance_id
        or intent.configuration_version != policy.configuration_version
    ):
        refusals.append(
            "the execution policy is not the one of the configuration version the intent names"
        )
    if intent.symbol not in policy.watchlist:
        refusals.append(f"{intent.symbol} is not on the approved watchlist")
    if intent.symbol in policy.prohibited_instruments:
        refusals.append(f"{intent.symbol} is a prohibited instrument")
    if not asset_tradable:
        refusals.append(f"{intent.symbol} is not tradable at the broker")
    if asset_status != "active":
        refusals.append(f"{intent.symbol} is not an active asset ({asset_status})")
    if asset_class != "us_equity":
        refusals.append(f"{intent.symbol} is not a US equity ({asset_class})")
    if existing_position_quantity != 0:
        refusals.append(
            f"a position of {existing_position_quantity} already exists in {intent.symbol}"
        )
    # BROKER TIMELINE. The session close is the broker's own fact, so a close
    # that MIGHT already have passed is treated as passed.
    if (
        not market_is_open
        or market_next_close is None
        or broker_now.possibly_at_or_after(market_next_close)
    ):
        refusals.append("the regular market session is closed or cannot be established")
    window_refusal = entry_window_refusal(policy=policy, broker_now=broker_now)
    if window_refusal is not None:
        refusals.append(window_refusal)
    session_refusal = liquidation_session_refusal(
        liquidation_at=intent.mandatory_liquidation_at, policy=policy, broker_now=broker_now
    )
    if session_refusal is not None:
        refusals.append(session_refusal)
    # HOST TIMELINE. Both deadlines below were written by this host's clock.
    if intent.expires_at <= created_at:
        refusals.append("the approved intent has expired")
    if intent.mandatory_liquidation_at <= created_at:
        refusals.append("the mandatory liquidation deadline has already passed")
    # BROKER TIMELINE, THROUGH THE BASIS OF THE ACT THAT WROTE THEM. The same two
    # deadlines, placed on the broker's clock with the basis measured when the
    # proposal was evaluated -- never with a later issuance or authorization basis.
    broker_deadline_refusal = m084_deadline_refusal_on_broker_time(
        intent=intent, provenance=m084_provenance, broker_now=broker_now
    )
    if broker_deadline_refusal is not None:
        refusals.append(broker_deadline_refusal)

    ceiling = order.notional_ceiling
    if ceiling is None:
        refusals.append(
            "a MARKET order has no knowable cost ceiling and cannot be authorized "
            "under a notional limit"
        )
    elif ceiling > policy.maximum_notional:
        refusals.append(
            f"the order's cost ceiling {ceiling} exceeds the limit {policy.maximum_notional}"
        )
    elif ceiling > account.buying_power:
        refusals.append(f"the order's cost ceiling {ceiling} exceeds paper buying power")

    # Freshness, positivity, crossing and spread, on the broker's clock, under the
    # configuration's own limits. One function, shared with the final send guard.
    quote_problem = quote_refusal(
        bid=quote_bid,
        ask=quote_ask,
        captured_at=quote_captured_at,
        policy=policy,
        broker_now=broker_now,
    )
    if quote_problem is not None:
        refusals.append(quote_problem)

    return SubmissionPreview(
        preview_id=preview_id,
        intent_governance_id=intent.intent_governance_id,
        preview_version=preview_version,
        account_snapshot_id=account.snapshot_id,
        account_reference=account.account_reference,
        order=order,
        request_fingerprint=request_fingerprint(
            order=order,
            account_reference=account.account_reference,
            endpoint_host=account.endpoint_host,
            intent_governance_id=intent.intent_governance_id,
            approved_fingerprint=intent.approved_fingerprint,
            policy_fingerprint=policy.fingerprint,
        ),
        approved_fingerprint=intent.approved_fingerprint,
        market_is_open=market_is_open,
        market_next_open=market_next_open,
        market_next_close=market_next_close,
        quote_bid=quote_bid,
        quote_ask=quote_ask,
        quote_captured_at=quote_captured_at,
        quote_source=quote_source,
        asset_tradable=asset_tradable,
        asset_status=asset_status,
        asset_class=asset_class,
        asset_exchange=asset_exchange,
        asset_fractionable=asset_fractionable,
        policy=policy,
        intent_expires_at=intent.expires_at,
        refusals=tuple(refusals),
        created_at=created_at,
    )


def authorize_submission(
    *,
    authorization_id: str,
    preview: SubmissionPreview,
    authorized_by: str,
    authorized_at: datetime,
    validity_seconds: int,
    time_basis: BrokerTimeBasis,
) -> ExecutionAuthorization:
    """Turn one human act into one narrow, expiring permission.

    Refuses a preview that carries refusals, and refuses a non-positive or
    unbounded validity. There is no parameter here that could express "approve
    everything like this" or "approve until further notice".

    `authorized_at` keeps its audit meaning -- the instant the human act was
    recorded -- and is NOT the mapping basis. `time_basis` is the interval measured
    for this authorization; an `authorized_at` later than its post-response host
    reading is refused, because it would push the mapped expiry later.
    """
    if not isinstance(preview, SubmissionPreview):
        raise ValueError("preview must be a SubmissionPreview")
    if not isinstance(time_basis, BrokerTimeBasis):
        raise ValueError("time_basis must be the BrokerTimeBasis measured for this authorization")
    _require_aware(authorized_at, field="authorized_at")
    if isinstance(validity_seconds, bool) or not isinstance(validity_seconds, int):
        raise ValueError("validity_seconds must be an int")
    if validity_seconds <= 0:
        raise ValueError("validity_seconds must be positive")
    if not preview.is_authorizable:
        raise ValueError("this preview cannot be authorized: " + "; ".join(preview.refusals))
    expires_at = authorized_at + timedelta(seconds=validity_seconds)
    if expires_at > preview.intent_expires_at:
        raise ValueError(
            "the requested validity would outlive the approved intent; choose a validity "
            "that expires no later than the intent does"
        )
    # The human is consenting to the quote evidence the preview showed. Once that
    # evidence is older than the configured freshness limit, it no longer describes
    # the market, so a fresh preview is required rather than an authorization.
    if (time_basis.host_at - preview.created_at).total_seconds() > (
        preview.policy.quote_maximum_age_seconds
    ):
        raise ValueError(
            "the preview is older than the configured quote freshness limit; preview again "
            "and authorize what the fresh preview shows"
        )

    authorization = ExecutionAuthorization(
        authorization_id=authorization_id,
        intent_governance_id=preview.intent_governance_id,
        preview_id=preview.preview_id,
        preview_version=preview.preview_version,
        request_fingerprint=preview.request_fingerprint,
        account_reference=preview.account_reference,
        client_order_id=preview.order.client_order_id,
        authorized_by=authorized_by,
        authorized_at=authorized_at,
        expires_at=expires_at,
        consumed_at=None,
        consumed_by_attempt_id=None,
        symbol=preview.order.symbol,
        side=preview.order.side,
        quantity=preview.order.quantity,
        order_type=preview.order.order_type,
        limit_price=preview.order.limit_price,
        maximum_notional=preview.policy.maximum_notional,
        quote_bid=preview.quote_bid,
        quote_ask=preview.quote_ask,
        quote_captured_at=preview.quote_captured_at,
        configuration_governance_id=preview.policy.configuration_governance_id,
        configuration_version=preview.policy.configuration_version,
        policy_fingerprint=preview.policy.fingerprint,
        preview_binding_fingerprint=preview.binding_fingerprint,
        # The measured interval, stored whole. SUPERSEDED: this used to pair the
        # pre-fetch `authorized_at` with the broker's reply and call the two "taken
        # at THIS moment"; the fetch latency then extended every mapped expiry.
        basis_host_at=time_basis.host_at,
        basis_broker_earliest_at=time_basis.broker_earliest_at,
        basis_host_requested_at=time_basis.host_requested_at,
        basis_broker_latest_at=time_basis.broker_latest_at,
    )
    binding = authorization_binding_refusal(authorization=authorization, preview=preview)
    if binding is not None:  # unreachable while the copies above stand
        raise ValueError(binding)
    return authorization


def final_send_refusal(
    *,
    intent: ApprovedOrderIntent,
    provenance: M084TimeProvenance,
    authorization: ExecutionAuthorization,
    policy_now: ExecutionPolicy,
    request_fingerprint_now: str,
    account_reference_now: str,
    host_now: datetime,
    broker_now: BoundedInstant,
    market_is_open: bool,
    market_next_close: datetime | None,
    quote_bid: Decimal | None,
    quote_ask: Decimal | None,
    quote_captured_at: datetime | None,
    kill_switch_engaged: bool,
) -> str | None:
    """Every condition that must hold at the LAST controllable boundary before a send.

    CORRECTIVE PASS (item 7). The caller supplies values READ FRESH for this call --
    the kill switch from the database, the configuration re-loaded and re-derived
    into `policy_now`, the broker clock and the quote fetched again -- so no value
    cached from an earlier step can satisfy this guard. The policy the send is judged
    under is the configuration's, and it must equal the one the human authorized.
    """
    _require_aware(host_now, field="host_now")
    if kill_switch_engaged:
        return "the execution kill switch is engaged"
    if (
        intent.configuration_governance_id != policy_now.configuration_governance_id
        or intent.configuration_version != policy_now.configuration_version
        or authorization.configuration_governance_id != policy_now.configuration_governance_id
        or authorization.configuration_version != policy_now.configuration_version
    ):
        return "the execution policy does not belong to the intent's configuration version"
    if authorization.policy_fingerprint != policy_now.fingerprint:
        return (
            "the execution policy re-derived from the stored configuration is not the "
            "policy the human authorized"
        )
    if authorization.maximum_notional != policy_now.maximum_notional:
        return "the authorized notional cap is not the configuration's cap"
    refusal = authorization.refusal_against(
        request_fingerprint_now=request_fingerprint_now,
        account_reference_now=account_reference_now,
        instant=host_now,
        broker_now=broker_now,
    )
    if refusal is not None:
        return refusal
    if host_now < authorization.authorized_at:
        return "the authorization is future-dated"
    if (
        authorization.symbol != intent.symbol
        or authorization.quantity != intent.quantity
        or authorization.limit_price != intent.limit_price
        or authorization.order_type != intent.order_type
        or authorization.side != intent.side
    ):
        return "the authorized order terms are not the approved intent's"
    if not policy_now.permits_symbol(intent.symbol):
        return f"{intent.symbol} is not permitted by the configuration's watchlist"
    if intent.limit_price is None or intent.order_type is not OrderType.LIMIT:
        return "only a LIMIT order has a knowable cost ceiling"
    if intent.limit_price * Decimal(intent.quantity) > policy_now.maximum_notional:
        return "the order's cost ceiling exceeds the configuration's notional cap"
    # HOST TIMELINE: deadlines this host recorded.
    if host_now >= intent.expires_at or host_now >= intent.mandatory_liquidation_at:
        return "the approved intent or liquidation deadline expired"
    # BROKER TIMELINE: the same deadlines, each through the basis of the act that wrote it.
    deadline_refusal = m084_deadline_refusal_on_broker_time(
        intent=intent, provenance=provenance, broker_now=broker_now
    )
    if deadline_refusal is not None:
        return deadline_refusal
    session_refusal = liquidation_session_refusal(
        liquidation_at=intent.mandatory_liquidation_at, policy=policy_now, broker_now=broker_now
    )
    if session_refusal is not None:
        return session_refusal
    # A close that MIGHT already have passed counts as passed.
    if (
        not market_is_open
        or market_next_close is None
        or broker_now.possibly_at_or_after(market_next_close)
    ):
        return "the regular market session is closed"
    window_refusal = entry_window_refusal(policy=policy_now, broker_now=broker_now)
    if window_refusal is not None:
        return window_refusal
    return quote_refusal(
        bid=quote_bid,
        ask=quote_ask,
        captured_at=quote_captured_at,
        policy=policy_now,
        broker_now=broker_now,
    )
