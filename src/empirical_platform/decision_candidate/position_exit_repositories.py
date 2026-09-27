"""MILESTONE-087 persistence-neutral and broker-neutral contracts for position exits.

WHAT IS ABSENT IS THE POINT. No `update_state` that takes any state, no `delete`, no
`force_close`, no method that mints a `client_order_id`, and no method that accepts a
caller-chosen sell quantity. `claim_dispatch` is the exactly-once primitive: it consumes
the authorization and creates the ONE attempt in one transaction, and hands a losing
caller the persisted winner instead of an error.

THE BROKER PORT IS NARROW ON PURPOSE. `ExitBrokerPort.submit_close_order` takes a
`PositionExitRequest` -- a type that can only express SELL_TO_CLOSE of a whole positive
quantity in a permitted environment -- and nothing else. It is implemented by the
SIMULATION broker only in this milestone; no Alpaca adapter implements it.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Protocol

from empirical_platform.decision_candidate.paper_execution import (
    BrokerAcknowledgement,
    ReconciliationRound,
    ReconciliationRoundOutcome,
)
from empirical_platform.decision_candidate.paper_execution_repositories import (
    BrokerClockView,
    BrokerOrderView,
    BrokerPositionView,
)
from empirical_platform.decision_candidate.position_exit import (
    PositionExitAttempt,
    PositionExitAuthorization,
    PositionExitEvent,
    PositionExitPreview,
    PositionExitRequest,
    PositionExitState,
)
from empirical_platform.shared.brokerage.paper_time import BoundedInstant

__all__ = [
    "ExitBrokerPort",
    "ExitDispatchClaim",
    "PositionExitAcknowledgementRepository",
    "PositionExitAttemptRepository",
    "PositionExitAuthorizationRepository",
    "PositionExitEventRepository",
    "PositionExitPreviewRepository",
    "PositionExitRoundRepository",
]


class PositionExitPreviewRepository(Protocol):
    """Append-only store of exactly what the Owner was shown on the exit review page."""

    def save(self, preview: PositionExitPreview) -> PositionExitPreview: ...

    def get(self, preview_id: str) -> PositionExitPreview | None: ...

    def latest_for_entry(self, entry_intent_governance_id: str) -> PositionExitPreview | None: ...

    def next_version_for_entry(self, entry_intent_governance_id: str) -> int: ...


class PositionExitAuthorizationRepository(Protocol):
    """Append-only human permissions; consumption is the one controlled mutation."""

    def save(self, authorization: PositionExitAuthorization) -> PositionExitAuthorization: ...

    def get(self, authorization_id: str) -> PositionExitAuthorization | None: ...

    def latest_for_entry(
        self, entry_intent_governance_id: str
    ) -> PositionExitAuthorization | None: ...


class ExitDispatchClaim(Protocol):
    @property
    def won(self) -> bool: ...

    @property
    def attempt(self) -> PositionExitAttempt: ...


class PositionExitAttemptRepository(Protocol):
    """The exit dispatch lineage. At most one ACTIVE exit per position, ever."""

    def claim_dispatch(
        self,
        *,
        attempt_id: str,
        authorization: PositionExitAuthorization,
        request_fingerprint_now: str,
        account_reference_now: str,
        claimed_at: datetime,
        claim_clock: Callable[[], datetime] | None = None,
        broker_clock: Callable[[], BoundedInstant] | None = None,
    ) -> ExitDispatchClaim:
        """Atomically consume the authorization and create the one attempt.

        Returns a losing claim carrying the EXISTING active attempt when another worker got
        there first. Refuses -- rather than claiming -- when the authorization is expired,
        consumed, or bound to a different fingerprint or account.
        """
        ...

    def get(self, attempt_id: str) -> PositionExitAttempt | None: ...

    def for_entry(self, entry_intent_governance_id: str) -> tuple[PositionExitAttempt, ...]:
        """Every exit attempt ever made for this entry, oldest first."""
        ...

    def active_for_entry(self, entry_intent_governance_id: str) -> PositionExitAttempt | None:
        """The exit that is open or filled for this entry, if any (the one active identity)."""
        ...

    def by_client_order_id(self, client_order_id: str) -> PositionExitAttempt | None: ...

    def transition(
        self,
        *,
        attempt_id: str,
        target: PositionExitState,
        at: datetime,
        broker_order_id: str | None = None,
        broker_status: str | None = None,
        filled_quantity: str | None = None,
        filled_avg_price: str | None = None,
        failure_code: str | None = None,
        failure_detail: str | None = None,
    ) -> PositionExitAttempt: ...

    def mark_position_closed(
        self, *, attempt_id: str, verified_at: datetime
    ) -> PositionExitAttempt:
        """Record, once, that the broker position was verified at zero after a full fill."""
        ...

    def list_recent(self, limit: int) -> tuple[PositionExitAttempt, ...]: ...


class PositionExitAcknowledgementRepository(Protocol):
    def append(self, acknowledgement: BrokerAcknowledgement) -> BrokerAcknowledgement: ...

    def for_attempt(self, attempt_id: str) -> tuple[BrokerAcknowledgement, ...]: ...

    def next_sequence(self, attempt_id: str) -> int: ...


class PositionExitRoundRepository(Protocol):
    """Durable reconciliation rounds for exits: begun before the network, completed once."""

    def begin(
        self, *, attempt: PositionExitAttempt, account_reference: str, started_at: datetime
    ) -> ReconciliationRound: ...

    def complete(
        self,
        round_id: str,
        *,
        outcome: ReconciliationRoundOutcome,
        completed_at: datetime,
        acknowledgement_sequence: int | None = None,
        broker_earliest_at: datetime | None = None,
        broker_latest_at: datetime | None = None,
        detail: str | None = None,
    ) -> ReconciliationRound: ...

    def for_attempt(self, attempt_id: str) -> tuple[ReconciliationRound, ...]: ...

    def resolve_not_found(
        self,
        *,
        attempt_id: str,
        expected_version: tuple[int, int],
        at: datetime,
        failure_code: str,
        failure_detail: str,
    ) -> PositionExitAttempt | None: ...


class PositionExitEventRepository(Protocol):
    def append(self, event: PositionExitEvent) -> PositionExitEvent: ...

    def for_entry(self, entry_intent_governance_id: str) -> tuple[PositionExitEvent, ...]: ...


class ExitBrokerPort(Protocol):
    """Everything this milestone may ask a broker to do about an exit. Nothing more."""

    @property
    def endpoint_host(self) -> str: ...

    def fetch_account(self) -> tuple[int, dict[str, object]]: ...

    def fetch_clock(self) -> BrokerClockView: ...

    def fetch_position(self, symbol: str) -> BrokerPositionView | None: ...

    def submit_close_order(
        self, request: PositionExitRequest, *, before_send: Callable[[], None] | None = None
    ) -> tuple[int, BrokerOrderView | None, str]:
        """Send the one authorized SELL-TO-CLOSE. Returns (status, view, sanitized body).

        Raises a transport-ambiguity error -- never a generic exception -- when the request
        may have been delivered but no answer arrived.
        """
        ...

    def fetch_order_by_client_order_id(
        self, client_order_id: str
    ) -> tuple[int, BrokerOrderView | None, str]: ...

    def cancel_order(self, broker_order_id: str) -> tuple[int, str]: ...
