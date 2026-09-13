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
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from types import MappingProxyType

from empirical_platform.decision_candidate.operator_trading_configuration import OrderType
from empirical_platform.decision_candidate.trade_approval import ApprovedOrderIntent
from empirical_platform.shared.brokerage.paper_time import BoundedInstant

__all__ = [
    "ALLOWED_PAPER_TRANSITIONS",
    "CLIENT_ORDER_ID_PREFIX",
    "MAXIMUM_BROKER_CLIENT_ORDER_ID_LENGTH",
    "MINIMUM_CONSECUTIVE_NOT_FOUND_OBSERVATIONS",
    "MINIMUM_SECONDS_BEFORE_NOT_FOUND_COUNTS",
    "NOT_FOUND_ALONE_RESOLVES_UNKNOWN",
    "PAPER_ENDPOINT_HOST",
    "RECONCILIATION_UNKNOWN_POLICY",
    "RESOLUTION_REQUIRES_OPERATOR_VISIBLE_EVENT",
    "RESOLUTION_WHEN_POLICY_SATISFIED",
    "TERMINAL_PAPER_STATES",
    "BrokerAcknowledgement",
    "ExecutionAttempt",
    "ExecutionAuthorization",
    "PaperAccountSnapshot",
    "PaperEnvironment",
    "PaperExecutionEvent",
    "PaperExecutionState",
    "PaperOrderRequest",
    "SubmissionPreview",
    "authorize_submission",
    "build_submission_preview",
    "derive_client_order_id",
    "is_paper_transition_allowed",
    "request_fingerprint",
]

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
) -> str:
    """The digest a human authorization is bound to.

    Covers the ORDER, the ACCOUNT and the ENDPOINT together. Binding the order
    alone would let an authorization for one paper account be replayed against
    another; binding the endpoint means an authorization cannot survive being
    pointed somewhere else.

    Canonical JSON with sorted keys, so the digest depends on the values and not
    on the order a dict happened to be built in.
    """
    _require_identifier(account_reference, field="account_reference")
    _require_identifier(intent_governance_id, field="intent_governance_id")
    _require_digest(approved_fingerprint, field="approved_fingerprint")
    if endpoint_host != PAPER_ENDPOINT_HOST:
        raise ValueError(f"endpoint_host must be exactly {PAPER_ENDPOINT_HOST}")

    payload = {
        "account_reference": account_reference,
        "approved_fingerprint": approved_fingerprint,
        "endpoint_host": endpoint_host,
        "extended_hours": order.extended_hours,
        "intent_governance_id": intent_governance_id,
        "limit_price": None if order.limit_price is None else format(order.limit_price, "f"),
        "order_type": order.order_type.value,
        "quantity": order.quantity,
        "side": order.side,
        "symbol": order.symbol,
        "time_in_force": order.time_in_force,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


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
        if not isinstance(self.refusals, tuple) or any(
            not isinstance(reason, str) or not reason.strip() for reason in self.refusals
        ):
            raise ValueError("refusals must be a tuple of non-empty strings")
        _require_aware(self.created_at, field="created_at")

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
    #: THE BROKER TIME BASIS. Two readings taken at the SAME moment the human
    #: authorized: this host's clock, and the earliest instant the broker's clock
    #: could then have been showing. Their difference is a measured, conservative
    #: host-to-broker mapping, and it is what makes a stored host deadline
    #: survive a host clock that later moves. Nullable because a row written
    #: before this basis existed has none; such a row cannot be dispatched.
    basis_host_at: datetime | None = None
    basis_broker_earliest_at: datetime | None = None

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

    def is_expired_at(self, instant: datetime) -> bool:
        _require_aware(instant, field="instant")
        return instant >= self.expires_at

    @property
    def has_broker_time_basis(self) -> bool:
        return self.basis_host_at is not None and self.basis_broker_earliest_at is not None

    def on_broker_timeline(self, host_instant: datetime) -> datetime:
        """Map an instant written by THIS host onto the broker's timeline.

        WHY THIS EXISTS. `expires_at`, and MILESTONE-084's `expires_at` and
        `mandatory_liquidation_at`, are absolute instants produced by this host's
        wall clock. Monotonic time protects them only while one process runs. Once
        the approving process exits, a host clock that steps BACKWARD makes every
        stored deadline look further away, and a new dispatch process has no
        memory with which to notice. Measured, not argued: with the basis removed,
        an hour-long backward step let a 300-second approval dispatch.

        The mapping is the difference between two readings taken at the same
        moment, so it carries no assumption about either clock's accuracy. The
        EARLIEST broker reading is used, which makes every mapped deadline the
        soonest it could be -- the conservative direction for expiry.

        This does not reinterpret the MILESTONE-084 record. That value is frozen,
        is still stored and rendered exactly as M084 wrote it, and is still
        enforced on the host timeline as well; this is an ADDITIONAL M085 bound
        measured at the moment a human authorized.
        """
        _require_aware(host_instant, field="host_instant")
        if self.basis_host_at is None or self.basis_broker_earliest_at is None:
            raise ValueError(
                "this authorization carries no broker time basis and cannot be "
                "mapped onto the broker timeline"
            )
        return host_instant + (self.basis_broker_earliest_at - self.basis_host_at)

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
        between the approving process and this one. A caller that supplies no
        `broker_now` gets the host check alone and is refused outright once a
        basis exists, because the stronger of the two must never be skippable.
        """
        if self.is_consumed:
            return "the authorization has already been used"
        if self.is_expired_at(instant):
            return "the authorization has expired"
        if self.has_broker_time_basis and broker_now is None:
            return (
                "this authorization carries a broker time basis and cannot be "
                "checked without the broker's current instant"
            )
        if (
            self.has_broker_time_basis
            and broker_now is not None
            and broker_now.possibly_at_or_after(self.on_broker_timeline(self.expires_at))
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
    approved_watchlist: frozenset[str],
    maximum_notional: Decimal,
    quote_maximum_age_seconds: int,
    existing_position_quantity: int,
    execution_kill_switch_engaged: bool,
    created_at: datetime,
    broker_now: BoundedInstant,
) -> SubmissionPreview:
    """Freeze exactly what a human will be shown, refusals included.

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
    if intent.symbol not in approved_watchlist:
        refusals.append(f"{intent.symbol} is not on the approved watchlist")
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
    # HOST TIMELINE. Both deadlines below were written by this host's clock.
    if intent.expires_at <= created_at:
        refusals.append("the approved intent has expired")
    if intent.mandatory_liquidation_at <= created_at:
        refusals.append("the mandatory liquidation deadline has already passed")

    ceiling = order.notional_ceiling
    if ceiling is None:
        refusals.append(
            "a MARKET order has no knowable cost ceiling and cannot be authorized "
            "under a notional limit"
        )
    elif ceiling > maximum_notional:
        refusals.append(f"the order's cost ceiling {ceiling} exceeds the limit {maximum_notional}")
    elif ceiling > account.buying_power:
        refusals.append(f"the order's cost ceiling {ceiling} exceeds paper buying power")

    if quote_captured_at is None:
        refusals.append("no quote was captured, so its freshness cannot be established")
    else:
        # Freshness is a SAFETY bound and must hold across the whole interval, so
        # it is tested against the OLDEST age the evidence permits.
        oldest = broker_now.age_of(quote_captured_at)[1]
        if oldest > quote_maximum_age_seconds:
            refusals.append(
                f"the quote is {int(oldest)}s old, older than the "
                f"{quote_maximum_age_seconds}s limit"
            )
        elif oldest < 0:
            # A future-dated quote is a CONSISTENCY problem, not a safety margin,
            # so it is refused only when it is future-dated even at the latest
            # instant the broker's clock could now be showing. Refusing on
            # `youngest < 0` instead would refuse sub-second feed skew on a quote
            # that is milliseconds old -- which is precisely the defect that made
            # every fresh quote unusable in an open market.
            refusals.append("the captured quote is dated after the latest possible current time")

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
    broker_now: BoundedInstant,
) -> ExecutionAuthorization:
    """Turn one human act into one narrow, expiring permission.

    Refuses a preview that carries refusals, and refuses a non-positive or
    unbounded validity. There is no parameter here that could express "approve
    everything like this" or "approve until further notice".
    """
    if not isinstance(preview, SubmissionPreview):
        raise ValueError("preview must be a SubmissionPreview")
    _require_aware(authorized_at, field="authorized_at")
    if isinstance(validity_seconds, bool) or not isinstance(validity_seconds, int):
        raise ValueError("validity_seconds must be an int")
    if validity_seconds <= 0:
        raise ValueError("validity_seconds must be positive")
    if not preview.is_authorizable:
        raise ValueError("this preview cannot be authorized: " + "; ".join(preview.refusals))

    from datetime import timedelta

    return ExecutionAuthorization(
        authorization_id=authorization_id,
        intent_governance_id=preview.intent_governance_id,
        preview_id=preview.preview_id,
        preview_version=preview.preview_version,
        request_fingerprint=preview.request_fingerprint,
        account_reference=preview.account_reference,
        client_order_id=preview.order.client_order_id,
        authorized_by=authorized_by,
        authorized_at=authorized_at,
        expires_at=authorized_at + timedelta(seconds=validity_seconds),
        consumed_at=None,
        consumed_by_attempt_id=None,
        # Both readings are taken at THIS moment, which is what makes their
        # difference a measurement rather than an assumption.
        basis_host_at=authorized_at,
        basis_broker_earliest_at=broker_now.earliest,
    )
