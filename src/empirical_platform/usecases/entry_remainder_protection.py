"""RELEASE v1 -- protect a PARTIALLY FILLED entry by cancelling its unfilled remainder.

THE GAP THIS CLOSES. While an entry is PARTIALLY_FILLED (remainder still working) the exit
pipeline refuses to close the position ("cancel the remainder and wait until the entry is
final"), because the remainder could still fill and the attributable quantity is not stable.
Nothing used to cancel that remainder automatically, so the filled shares had NO stop, target
or mandatory-liquidation protection until the DAY remainder happened to expire at the close.

WHAT THIS DOES (and nothing more). On behalf of `PositionPlanManager`, for ONE entry that is
still working but has FILLED SHARES (filled_quantity > 0): reconcile it by client_order_id,
and -- when the manager says it is urgent (a STOP/TARGET condition is met or the mandatory
deadline has arrived) or the partial entry has been working longer than
`ENTRY_PARTIAL_PROACTIVE_CANCEL_SECONDS` -- cancel the REMAINDER through the existing
`CancelPaperOrderHandler`, then reconcile until the broker says the entry is terminal. Only
then does the manager's normal STOP/TARGET/MANDATORY flow run, on the filled quantity.

STATE MACHINE (every transition re-derived from durable rows each tick; restart safe):

  working with fills (PAPER_SUBMITTED / PAPER_ACCEPTED / PARTIALLY_FILLED / CANCEL_REQUESTED)
    --reconcile by client_order_id--> terminal (FILLED / CANCELED / EXPIRED): RESOLVED
    --not urgent and younger than the proactive window--> WAITING (nothing sent)
    --urgent or older than the window, market not confirmed open--> WAITING (no cancel; the
        DAY remainder expires at the close)
    --urgent or older than the window, spacing/budget allow--> cancel -> reconcile at once
        (a fill that races the cancel is FILLED and proceeds normally)
    --cancel budget (ENTRY_MAX_CANCEL_REQUESTS) spent--> loud NEEDS_ATTENTION + durable
        ENTRY_REMAINDER_CANCEL_EXHAUSTED event; no further cancel is sent

NEVER: sends or resends an entry order, cancels an entry with ZERO fills (that is the Owner's
call), or consults the kill switch (a protective cancel must not be blockable by it). An
ambiguous cancel (the request may or may not have reached the broker) is reconciled by
client_order_id before anything else happens.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from empirical_platform.decision_candidate.paper_execution import (
    ExecutionAttempt,
    PaperExecutionEvent,
    PaperExecutionState,
)
from empirical_platform.decision_candidate.paper_execution_repositories import (
    BrokerAcknowledgementRepository,
    ExecutionAttemptRepository,
    ExecutionAuthorizationRepository,
    PaperBrokerPort,
    PaperExecutionEventRepository,
    ReconciliationRoundRepository,
    SubmissionPreviewRepository,
)
from empirical_platform.shared.brokerage.paper_time import PaperTimeSource
from empirical_platform.usecases.paper_execution import (
    CancelPaperOrderCommand,
    CancelPaperOrderHandler,
    PaperExecutionRefusedError,
    ReconcilePaperOrderCommand,
    ReconcilePaperOrderHandler,
)

__all__ = [
    "ENTRY_CANCEL_ERROR_EVENT_TYPE",
    "ENTRY_CANCEL_MIN_SPACING_SECONDS",
    "ENTRY_CLOSED_MARKET_RECONCILE_SECONDS",
    "ENTRY_MAX_CANCEL_REQUESTS",
    "ENTRY_PARTIAL_PROACTIVE_CANCEL_SECONDS",
    "ENTRY_REMAINDER_EXHAUSTED_EVENT_TYPE",
    "EntryRemainderProtector",
    "EntryRemainderResult",
    "EntryRemainderStatus",
    "entry_remainder_applies",
]

_LOG = logging.getLogger("empirical_platform.entry_remainder_protection")

#: A partial entry that has been working this long (since its first observed partial fill) has
#: its remainder cancelled even with no trigger, so protection is not left to the deadline.
ENTRY_PARTIAL_PROACTIVE_CANCEL_SECONDS = 120

#: Minimum spacing between two cancel requests for the same entry.
ENTRY_CANCEL_MIN_SPACING_SECONDS = 15

#: P2-4. While the broker CLOCK explicitly says the market is CLOSED, nothing can be cancelled
#: or sold and a DAY entry turns terminal only at the close, so reconciling a waiting partial
#: entry on every 15 s tick only grows the round/acknowledgement tables (about 11.5k rows a
#: day per such entry). Within a closed market the reconcile is repeated at most this often.
#: With the market open, or the clock unreadable, EVERY tick still reconciles first.
ENTRY_CLOSED_MARKET_RECONCILE_SECONDS = 300

#: Hard bound on cancel requests (accepted, refused or of unknown outcome) per entry.
ENTRY_MAX_CANCEL_REQUESTS = 5

ENTRY_PARTIAL_SEEN_EVENT_TYPE = "ENTRY_PARTIAL_FILL_OBSERVED"
ENTRY_CANCEL_ERROR_EVENT_TYPE = "ENTRY_REMAINDER_CANCEL_ERROR"
ENTRY_REMAINDER_EXHAUSTED_EVENT_TYPE = "ENTRY_REMAINDER_CANCEL_EXHAUSTED"
#: What `CancelPaperOrderHandler` records for every cancel request it sends.
_CANCEL_REQUESTED_EVENT_TYPE = "CANCEL_REQUESTED"

_WORKING_STATES: frozenset[PaperExecutionState] = frozenset(
    {
        PaperExecutionState.PAPER_SUBMITTED,
        PaperExecutionState.PAPER_ACCEPTED,
        PaperExecutionState.PARTIALLY_FILLED,
        PaperExecutionState.CANCEL_REQUESTED,
    }
)


def entry_remainder_applies(entry: ExecutionAttempt) -> bool:
    """True for an entry that is still working at the broker AND already holds filled shares.
    An entry with zero fills is never cancelled automatically (the Owner's call)."""
    filled = entry.filled_quantity
    return entry.state in _WORKING_STATES and filled is not None and filled > Decimal(0)


class EntryRemainderStatus(StrEnum):
    #: The entry is terminal now (or never needed this): the manager re-assesses normally.
    RESOLVED = "RESOLVED"
    #: Nothing sent this tick, by design (not due yet, spacing, or market closed).
    WAITING = "WAITING"
    #: A cancel was requested; the entry is not yet confirmed terminal.
    CANCEL_REQUESTED = "CANCEL_REQUESTED"
    #: Loud: the bounded procedure cannot make progress without the Owner.
    NEEDS_ATTENTION = "NEEDS_ATTENTION"


@dataclass(frozen=True, slots=True)
class EntryRemainderResult:
    status: EntryRemainderStatus
    detail: str


class EntryRemainderProtector:
    """Bounded, restart-safe cancel of a partial entry's remainder. No entry is ever sent."""

    __slots__ = ("_attempts", "_acknowledgements", "_events", "_broker", "_reconcile", "_cancel")

    def __init__(
        self,
        *,
        attempts: ExecutionAttemptRepository,
        acknowledgements: BrokerAcknowledgementRepository,
        events: PaperExecutionEventRepository,
        rounds: ReconciliationRoundRepository,
        authorizations: ExecutionAuthorizationRepository,
        previews: SubmissionPreviewRepository,
        broker: PaperBrokerPort,
        time_source: PaperTimeSource | None = None,
    ) -> None:
        self._attempts = attempts
        self._acknowledgements = acknowledgements
        self._events = events
        self._broker = broker
        self._reconcile = ReconcilePaperOrderHandler(
            attempts=attempts,
            acknowledgements=acknowledgements,
            events=events,
            broker=broker,
            authorizations=authorizations,
            previews=previews,
            rounds=rounds,
            time_source=time_source,
        )
        self._cancel = CancelPaperOrderHandler(
            attempts=attempts, acknowledgements=acknowledgements, events=events, broker=broker
        )

    def step(
        self, entry: ExecutionAttempt, *, now: datetime, urgent_reason: str | None
    ) -> EntryRemainderResult:
        intent = entry.intent_governance_id
        if self._closed_and_recently_reconciled(entry, now):
            return EntryRemainderResult(
                EntryRemainderStatus.WAITING,
                f"partial entry {entry.attempt_id} state={entry.state.value}: the market is "
                f"closed, so nothing can be cancelled; reconciled within the last "
                f"{ENTRY_CLOSED_MARKET_RECONCILE_SECONDS}s, next check after that. The first "
                "tick with the market open reconciles immediately",
            )
        # ALWAYS reconcile first, by client_order_id: no decision is taken on stale state.
        try:
            entry = self._reconcile.handle(ReconcilePaperOrderCommand(intent, at=now))
        except Exception as error:  # noqa: BLE001 - a failed lookup must not become a guess
            _LOG.warning("entry %s: reconcile raised %s", entry.attempt_id, type(error).__name__)
            return EntryRemainderResult(
                EntryRemainderStatus.NEEDS_ATTENTION,
                f"partial entry {entry.attempt_id}: reconciliation raised "
                f"{type(error).__name__}; no cancel decision is taken on stale state",
            )
        if not entry_remainder_applies(entry):
            return EntryRemainderResult(
                EntryRemainderStatus.RESOLVED, f"entry {entry.attempt_id} is {entry.state.value}"
            )
        first_seen = self._first_seen(entry, now)
        age = int((now - first_seen).total_seconds())
        reason = urgent_reason
        if reason is None and age >= ENTRY_PARTIAL_PROACTIVE_CANCEL_SECONDS:
            reason = (
                f"the partial entry has been working {age}s "
                f"(>= {ENTRY_PARTIAL_PROACTIVE_CANCEL_SECONDS}s)"
            )
        base = f"partial entry {entry.attempt_id} state={entry.state.value}"
        if reason is None:
            return EntryRemainderResult(
                EntryRemainderStatus.WAITING,
                f"{base}: remainder cancel scheduled in "
                f"{ENTRY_PARTIAL_PROACTIVE_CANCEL_SECONDS - age}s or at the first trigger",
            )
        cancels = [
            e
            for e in self._events.for_intent(intent)
            if e.attempt_id == entry.attempt_id
            and e.event_type in {_CANCEL_REQUESTED_EVENT_TYPE, ENTRY_CANCEL_ERROR_EVENT_TYPE}
        ]
        if len(cancels) >= ENTRY_MAX_CANCEL_REQUESTS:
            detail = (
                f"{ENTRY_REMAINDER_EXHAUSTED_EVENT_TYPE}: {base}: {len(cancels)} cancel "
                "requests did not make the entry terminal; no further cancel is sent. The "
                "filled shares are UNPROTECTED by stop/target/mandatory exit until the entry "
                "is final -- the Owner must cancel the remainder at the broker"
            )
            self._record(entry, ENTRY_REMAINDER_EXHAUSTED_EVENT_TYPE, detail, now, once=True)
            return EntryRemainderResult(EntryRemainderStatus.NEEDS_ATTENTION, detail)
        if cancels:
            last = max(e.occurred_at for e in cancels)
            if (now - last).total_seconds() < ENTRY_CANCEL_MIN_SPACING_SECONDS:
                return EntryRemainderResult(
                    EntryRemainderStatus.WAITING, f"{base}: cancel pending ({reason})"
                )
        if self._market_is_open() is not True:
            return EntryRemainderResult(
                EntryRemainderStatus.WAITING,
                f"{base}: market not confirmed open, no cancel attempted ({reason}); the DAY "
                "remainder expires at the close",
            )
        try:
            self._cancel.handle(CancelPaperOrderCommand(intent, at=now))
        except PaperExecutionRefusedError as error:
            self._record(
                entry, ENTRY_CANCEL_ERROR_EVENT_TYPE, f"cancel refused: {error}", now, suffix=now
            )
            return self._after_failed_cancel(entry, base, f"cancel refused: {error}", now)
        except Exception as error:  # noqa: BLE001 - the DELETE may or may not have arrived
            self._record(
                entry,
                ENTRY_CANCEL_ERROR_EVENT_TYPE,
                f"cancel request raised {type(error).__name__}; outcome unknown",
                now,
                suffix=now,
            )
            return self._after_failed_cancel(
                entry, base, f"cancel acknowledgement unknown ({type(error).__name__})", now
            )
        try:
            after = self._reconcile.handle(ReconcilePaperOrderCommand(intent, at=now))
        except Exception as error:  # noqa: BLE001 - reconciled again next tick
            return EntryRemainderResult(
                EntryRemainderStatus.CANCEL_REQUESTED,
                f"{base}: cancel requested ({reason}); post-cancel reconcile raised "
                f"{type(error).__name__}, retrying next tick",
            )
        if not entry_remainder_applies(after):
            return EntryRemainderResult(
                EntryRemainderStatus.RESOLVED,
                f"entry {after.attempt_id} is {after.state.value} after the remainder cancel",
            )
        return EntryRemainderResult(
            EntryRemainderStatus.CANCEL_REQUESTED,
            f"{base}: remainder cancel requested ({reason}); exit management waits until the "
            f"broker reports the entry terminal (now {after.state.value})",
        )

    # -- helpers ---------------------------------------------------------------------------

    def _closed_and_recently_reconciled(self, entry: ExecutionAttempt, now: datetime) -> bool:
        """P2-4: True only when the broker clock EXPLICITLY reports the market closed AND the
        newest durable acknowledgement for this entry is younger than the closed-market
        interval. An unreadable clock (`None`) or an open market is never throttled, so the
        'reconcile first' rule is untouched whenever a decision could be taken."""
        if self._market_is_open() is not False:
            return False
        moments = [ack.observed_at for ack in self._acknowledgements.for_attempt(entry.attempt_id)]
        if not moments:
            return False
        return (now - max(moments)).total_seconds() < ENTRY_CLOSED_MARKET_RECONCILE_SECONDS

    def _after_failed_cancel(
        self, entry: ExecutionAttempt, base: str, why: str, now: datetime
    ) -> EntryRemainderResult:
        """An ambiguous / refused cancel: reconcile by client_order_id first; only a
        broker-confirmed terminal entry proceeds. Never a resend."""
        try:
            after = self._reconcile.handle(
                ReconcilePaperOrderCommand(entry.intent_governance_id, at=now)
            )
        except Exception as error:  # noqa: BLE001
            return EntryRemainderResult(
                EntryRemainderStatus.NEEDS_ATTENTION,
                f"{base}: {why}; reconciliation raised {type(error).__name__}",
            )
        if not entry_remainder_applies(after):
            return EntryRemainderResult(
                EntryRemainderStatus.RESOLVED, f"entry {after.attempt_id} is {after.state.value}"
            )
        return EntryRemainderResult(
            EntryRemainderStatus.NEEDS_ATTENTION,
            f"{base}: {why}; reconciled by client_order_id, entry still {after.state.value}",
        )

    def _first_seen(self, entry: ExecutionAttempt, now: datetime) -> datetime:
        """When this entry first showed filled shares while working: the earliest of any
        durable partially_filled acknowledgement and this protector's own first-seen event
        (recorded once, so a restart never resets the clock)."""
        moments = [
            ack.observed_at
            for ack in self._acknowledgements.for_attempt(entry.attempt_id)
            if ack.broker_status == "partially_filled"
        ]
        seen_id = self._event_id(entry, ENTRY_PARTIAL_SEEN_EVENT_TYPE, "")
        for event in self._events.for_intent(entry.intent_governance_id):
            if event.event_id == seen_id:
                moments.append(event.occurred_at)
        if not moments:
            self._record(
                entry,
                ENTRY_PARTIAL_SEEN_EVENT_TYPE,
                f"first observed with filled_quantity={entry.filled_quantity}",
                now,
                once=True,
            )
            return now
        return min(moments)

    @staticmethod
    def _event_id(entry: ExecutionAttempt, event_type: str, suffix: str) -> str:
        digest = hashlib.sha256(f"{entry.attempt_id}|{event_type}|{suffix}".encode()).hexdigest()
        return f"EVT-ERP-{digest[:40]}"

    def _record(
        self,
        entry: ExecutionAttempt,
        event_type: str,
        detail: str,
        at: datetime,
        *,
        suffix: datetime | None = None,
        once: bool = False,
    ) -> None:
        event_id = self._event_id(entry, event_type, "" if suffix is None else suffix.isoformat())
        if once and any(
            e.event_id == event_id for e in self._events.for_intent(entry.intent_governance_id)
        ):
            return
        self._events.append(
            PaperExecutionEvent(
                event_id=event_id,
                intent_governance_id=entry.intent_governance_id,
                attempt_id=entry.attempt_id,
                event_type=event_type,
                occurred_at=at,
                detail=detail[:500],
            )
        )

    def _market_is_open(self) -> bool | None:
        try:
            return bool(self._broker.fetch_clock().is_open)
        except Exception:  # noqa: BLE001 - an unreadable clock is "not confirmed open"
            return None
