"""MILESTONE-085 persistence-neutral and broker-neutral contracts.

WHAT IS ABSENT IS THE POINT, AGAIN. There is no `update_state` that takes any
state, no `delete`, no `force_dispatch`, no `submit_without_authorization`, and
no method that mints a `client_order_id`. A caller cannot ask this layer for a
second order identity for one intent, because no method returns one.

`claim_dispatch` IS THE EXACTLY-ONCE PRIMITIVE. It is the only method that may
be called before a network request, it must be atomic, and it must consume the
authorization in the SAME transaction that creates the attempt. Splitting those
two writes would open exactly the window this milestone exists to close: an
authorization consumed with no attempt to show for it, or an attempt holding an
authorization that another worker also consumed.

THE BROKER PORT IS NARROW ON PURPOSE. `PaperBrokerPort` has no method that takes
a URL, no method that takes arbitrary headers, no method that sends an arbitrary
body, and no method that places an order the caller described in free form. It
takes a `PaperOrderRequest` -- a type that cannot express a sell, a short, a
fractional quantity, an extended-hours order or a non-DAY time in force -- and
nothing else.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Protocol

from empirical_platform.decision_candidate.paper_execution import (
    BrokerAcknowledgement,
    ExecutionAttempt,
    ExecutionAuthorization,
    PaperAccountSnapshot,
    PaperExecutionEvent,
    PaperExecutionState,
    PaperOrderRequest,
    SubmissionPreview,
)

__all__ = [
    "BrokerAcknowledgementRepository",
    "BrokerAssetView",
    "BrokerClockView",
    "BrokerOrderView",
    "BrokerPositionView",
    "BrokerQuoteView",
    "DispatchClaim",
    "ExecutionAttemptRepository",
    "ExecutionAuthorizationRepository",
    "ExecutionKillSwitchRepository",
    "PaperAccountSnapshotRepository",
    "PaperBrokerPort",
    "PaperExecutionEventRepository",
    "PaperMarketDataPort",
    "SubmissionPreviewRepository",
]


class ExecutionKillSwitchRepository(Protocol):
    """Append-only, versioned execution stop.

    Separate from MILESTONE-084's configuration kill switch and NOT a
    replacement for it. That one refuses to PROPOSE a trade; this one refuses to
    DISPATCH one. Both are checked, because an intent approved before either was
    engaged would otherwise still be dispatchable.
    """

    def engage(self, *, changed_by: str, changed_at: datetime, reason: str) -> bool:
        """Engage the stop, returning whether this call changed anything."""
        ...

    def disengage(self, *, changed_by: str, changed_at: datetime, reason: str) -> bool: ...

    def is_engaged(self) -> bool:
        """The current state, read fresh. Never cached across a dispatch."""
        ...


class PaperAccountSnapshotRepository(Protocol):
    """Append-only store of what the paper account said, when it said it."""

    def save(self, snapshot: PaperAccountSnapshot) -> PaperAccountSnapshot: ...

    def get(self, snapshot_id: str) -> PaperAccountSnapshot | None: ...


class SubmissionPreviewRepository(Protocol):
    """Append-only store of exactly what a human was shown."""

    def save(self, preview: SubmissionPreview) -> SubmissionPreview: ...

    def get(self, preview_id: str) -> SubmissionPreview | None: ...

    def latest_for_intent(self, intent_governance_id: str) -> SubmissionPreview | None: ...

    def next_version_for_intent(self, intent_governance_id: str) -> int:
        """The version a new preview for this intent would take.

        Derived from stored rows rather than supplied, so two previews cannot
        claim to be the same version of the same intent.
        """
        ...


class ExecutionAuthorizationRepository(Protocol):
    """Append-only store of human permissions, with one controlled mutation.

    The single permitted mutation is consumption: `consumed_at` moves from NULL
    to a value exactly once and never back. Nothing else about an authorization
    may change, which is what makes an expired or spent permission genuinely
    unusable rather than merely discouraged.
    """

    def save(self, authorization: ExecutionAuthorization) -> ExecutionAuthorization: ...

    def get(self, authorization_id: str) -> ExecutionAuthorization | None: ...

    def latest_for_intent(self, intent_governance_id: str) -> ExecutionAuthorization | None: ...


class DispatchClaim(Protocol):
    """The result of winning, or losing, the race to dispatch one intent."""

    @property
    def won(self) -> bool: ...

    @property
    def attempt(self) -> ExecutionAttempt: ...


class ExecutionAttemptRepository(Protocol):
    """The dispatch lineage. One attempt per intent, ever."""

    def claim_dispatch(
        self,
        *,
        attempt_id: str,
        authorization: ExecutionAuthorization,
        request_fingerprint_now: str,
        account_reference_now: str,
        claimed_at: datetime,
        claim_clock: Callable[[], datetime] | None = None,
    ) -> DispatchClaim:
        """Atomically consume the authorization and create the one attempt.

        Returns a losing claim carrying the EXISTING attempt when another worker
        got there first, rather than raising: a duplicate dispatch request must
        be answered with the persisted winner so that the loser reconciles the
        real order instead of creating a second one.

        Refuses -- rather than claiming -- when the authorization is expired,
        already consumed, or bound to a different fingerprint or account.
        """
        ...

    def get(self, attempt_id: str) -> ExecutionAttempt | None: ...

    def for_intent(self, intent_governance_id: str) -> ExecutionAttempt | None: ...

    def by_client_order_id(self, client_order_id: str) -> ExecutionAttempt | None: ...

    def transition(
        self,
        *,
        attempt_id: str,
        target: PaperExecutionState,
        at: datetime,
        broker_order_id: str | None = None,
        broker_status: str | None = None,
        filled_quantity: str | None = None,
        filled_avg_price: str | None = None,
        failure_code: str | None = None,
        failure_detail: str | None = None,
    ) -> ExecutionAttempt:
        """Move one attempt along the closed transition table.

        The database refuses an illegal edge as well, so a direct-SQL writer
        cannot walk an attempt into a state the domain calls unreachable.
        """
        ...

    def list_recent(self, limit: int) -> tuple[ExecutionAttempt, ...]: ...


class BrokerAcknowledgementRepository(Protocol):
    """Append-only record of what the broker said, in the order it said it."""

    def append(self, acknowledgement: BrokerAcknowledgement) -> BrokerAcknowledgement: ...

    def for_attempt(self, attempt_id: str) -> tuple[BrokerAcknowledgement, ...]: ...

    def next_sequence(self, attempt_id: str) -> int: ...


class PaperExecutionEventRepository(Protocol):
    """Append-only audit trail. Never the source of state."""

    def append(self, event: PaperExecutionEvent) -> PaperExecutionEvent: ...

    def for_intent(self, intent_governance_id: str) -> tuple[PaperExecutionEvent, ...]: ...


class BrokerClockView(Protocol):
    @property
    def is_open(self) -> bool: ...

    @property
    def timestamp(self) -> datetime: ...

    @property
    def next_open(self) -> datetime | None: ...

    @property
    def next_close(self) -> datetime | None: ...


class BrokerAssetView(Protocol):
    @property
    def symbol(self) -> str: ...

    @property
    def status(self) -> str: ...

    @property
    def tradable(self) -> bool: ...

    @property
    def asset_class(self) -> str: ...

    @property
    def exchange(self) -> str: ...

    @property
    def fractionable(self) -> bool: ...


class BrokerPositionView(Protocol):
    @property
    def symbol(self) -> str: ...

    @property
    def quantity(self) -> int: ...


class BrokerOrderView(Protocol):
    """One broker order as the broker currently describes it."""

    @property
    def broker_order_id(self) -> str: ...

    @property
    def client_order_id(self) -> str: ...

    @property
    def status(self) -> str: ...

    @property
    def symbol(self) -> str: ...

    @property
    def side(self) -> str: ...

    @property
    def quantity(self) -> str: ...

    @property
    def order_type(self) -> str: ...

    @property
    def filled_quantity(self) -> str: ...

    @property
    def filled_avg_price(self) -> str | None: ...


class BrokerQuoteView(Protocol):
    @property
    def symbol(self) -> str: ...

    @property
    def bid(self) -> str | None: ...

    @property
    def ask(self) -> str | None: ...

    @property
    def captured_at(self) -> datetime: ...

    @property
    def source(self) -> str:
        """Which feed this came from, recorded so it is never mistaken for SIP."""
        ...


class PaperBrokerPort(Protocol):
    """Everything this milestone may ask a paper broker to do. Nothing more.

    Note what cannot be expressed: no URL argument, no header argument, no raw
    body, no symbol-and-side pair assembled by the caller, no sell, and no
    method that returns a new order identity. `submit_order` takes the request a
    human authorized and the id derived from persisted identity.
    """

    @property
    def endpoint_host(self) -> str:
        """The host this adapter is pinned to. Read, never set, by callers."""
        ...

    def fetch_account(self) -> tuple[int, dict[str, object]]:
        """The raw-but-sanitized account payload with its HTTP status."""
        ...

    def fetch_clock(self) -> BrokerClockView: ...

    def fetch_asset(self, symbol: str) -> BrokerAssetView: ...

    def fetch_position(self, symbol: str) -> BrokerPositionView | None: ...

    def submit_order(
        self, order: PaperOrderRequest, *, before_send: Callable[[], None] | None = None
    ) -> tuple[int, BrokerOrderView | None, str]:
        """Send the one authorized order. Returns (status, view, sanitized body).

        Raises a transport-ambiguity error -- never a generic exception -- when
        the request may have been delivered but no answer arrived, so that the
        caller can record SUBMISSION_UNKNOWN instead of guessing.
        """
        ...

    def fetch_order_by_client_order_id(
        self, client_order_id: str
    ) -> tuple[int, BrokerOrderView | None, str]:
        """Look one order up by the identity we derived. The reconciliation path."""
        ...

    def cancel_order(self, broker_order_id: str) -> tuple[int, str]: ...


class PaperMarketDataPort(Protocol):
    """Quotes only. This port cannot place, modify or cancel anything."""

    @property
    def endpoint_host(self) -> str: ...

    def fetch_quote(self, symbol: str) -> BrokerQuoteView | None: ...
