"""In-memory MILESTONE-087 exit repositories for the unit suites.

Dictionaries and lists mirroring the PostgreSQL refusals that matter to exactly-once: one
authorization per preview, single-use consumption, at most one ACTIVE exit per entry, a
unique client_order_id, immutable terminal rows (apart from the once-only closed-position
verification), completed rounds immutable. Deliberately dumb otherwise.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import datetime
from decimal import Decimal

from empirical_platform.decision_candidate.paper_execution import (
    BrokerAcknowledgement,
    ReconciliationRound,
    ReconciliationRoundOutcome,
)
from empirical_platform.decision_candidate.position_exit import (
    TERMINAL_EXIT_STATES,
    PositionExitAttempt,
    PositionExitAuthorization,
    PositionExitEvent,
    PositionExitPreview,
    PositionExitState,
    exit_absence_evaluation,
)
from empirical_platform.shared.brokerage.paper_time import BoundedInstant

_INACTIVE = {
    PositionExitState.CANCELED,
    PositionExitState.REJECTED,
    PositionExitState.EXPIRED,
}


class FakeExitPreviews:
    def __init__(self) -> None:
        self.rows: dict[str, PositionExitPreview] = {}

    def save(self, preview: PositionExitPreview) -> PositionExitPreview:
        if preview.preview_id in self.rows:
            raise ValueError("exit preview ids are unique")
        for other in self.rows.values():
            if (
                other.entry_intent_governance_id == preview.entry_intent_governance_id
                and other.preview_version == preview.preview_version
            ):
                raise ValueError("one exit preview per entry and version")
        self.rows[preview.preview_id] = preview
        return preview

    def get(self, preview_id: str) -> PositionExitPreview | None:
        return self.rows.get(preview_id)

    def latest_for_entry(self, entry_intent_governance_id: str) -> PositionExitPreview | None:
        matches = [
            p
            for p in self.rows.values()
            if p.entry_intent_governance_id == entry_intent_governance_id
        ]
        return max(matches, key=lambda p: p.preview_version) if matches else None

    def next_version_for_entry(self, entry_intent_governance_id: str) -> int:
        latest = self.latest_for_entry(entry_intent_governance_id)
        return 1 if latest is None else latest.preview_version + 1


class FakeExitAuthorizations:
    def __init__(self) -> None:
        self.rows: dict[str, PositionExitAuthorization] = {}

    def save(self, authorization: PositionExitAuthorization) -> PositionExitAuthorization:
        if authorization.authorization_id in self.rows:
            raise ValueError("exit authorization ids are unique")
        if any(a.preview_id == authorization.preview_id for a in self.rows.values()):
            raise ValueError("one exit authorization per preview")
        self.rows[authorization.authorization_id] = authorization
        return authorization

    def get(self, authorization_id: str) -> PositionExitAuthorization | None:
        return self.rows.get(authorization_id)

    def latest_for_entry(self, entry_intent_governance_id: str) -> PositionExitAuthorization | None:
        matches = [
            a
            for a in self.rows.values()
            if a.entry_intent_governance_id == entry_intent_governance_id
        ]
        return (
            max(matches, key=lambda a: (a.authorized_at, a.authorization_id)) if matches else None
        )


@dataclass
class FakeExitClaim:
    won: bool
    attempt: PositionExitAttempt


class FakeExitAttempts:
    def __init__(self, authorizations: FakeExitAuthorizations) -> None:
        self._authorizations = authorizations
        self.rows: dict[str, PositionExitAttempt] = {}
        self.transitions: list[tuple[str, PositionExitState]] = []

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
    ) -> FakeExitClaim:
        if claim_clock is not None:
            claimed_at = claim_clock()
        stored = self._authorizations.rows.get(authorization.authorization_id)
        if stored is None:
            raise ValueError("the exit authorization no longer exists")
        refusal = stored.refusal_against(
            request_fingerprint_now=request_fingerprint_now,
            account_reference_now=account_reference_now,
            instant=claimed_at,
            broker_now=None if broker_clock is None else broker_clock(),
        )
        if refusal is not None:
            if stored.is_consumed:
                existing = self.active_for_entry(stored.entry_intent_governance_id)
                if existing is not None:
                    return FakeExitClaim(won=False, attempt=existing)
            raise ValueError(f"this exit is not authorized: {refusal}")
        if self.active_for_entry(stored.entry_intent_governance_id) is not None:
            raise ValueError("at most one active exit per position")
        if any(a.client_order_id == stored.client_order_id for a in self.rows.values()):
            raise ValueError("exit client_order_id is unique")
        self._authorizations.rows[stored.authorization_id] = replace(
            stored, consumed_at=claimed_at, consumed_by_attempt_id=attempt_id
        )
        attempt = PositionExitAttempt(
            attempt_id=attempt_id,
            entry_intent_governance_id=stored.entry_intent_governance_id,
            authorization_id=stored.authorization_id,
            client_order_id=stored.client_order_id,
            request_fingerprint=stored.request_fingerprint,
            symbol=stored.symbol,
            quantity=stored.quantity,
            state=PositionExitState.DISPATCH_CLAIMED,
            claimed_at=claimed_at,
            submitted_at=None,
            acknowledged_at=None,
            terminal_at=None,
            broker_order_id=None,
            broker_status=None,
            filled_quantity=None,
            filled_avg_price=None,
            failure_code=None,
            failure_detail=None,
            closed_position_verified_at=None,
        )
        self.rows[attempt_id] = attempt
        return FakeExitClaim(won=True, attempt=attempt)

    def get(self, attempt_id: str) -> PositionExitAttempt | None:
        return self.rows.get(attempt_id)

    def for_entry(self, entry_intent_governance_id: str) -> tuple[PositionExitAttempt, ...]:
        return tuple(
            sorted(
                (
                    a
                    for a in self.rows.values()
                    if a.entry_intent_governance_id == entry_intent_governance_id
                ),
                key=lambda a: (a.claimed_at, a.attempt_id),
            )
        )

    def active_for_entry(self, entry_intent_governance_id: str) -> PositionExitAttempt | None:
        for attempt in self.for_entry(entry_intent_governance_id):
            if attempt.state not in _INACTIVE:
                return attempt
        return None

    def by_client_order_id(self, client_order_id: str) -> PositionExitAttempt | None:
        return next((a for a in self.rows.values() if a.client_order_id == client_order_id), None)

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
    ) -> PositionExitAttempt:
        current = self.rows[attempt_id]
        if current.state in TERMINAL_EXIT_STATES:
            raise ValueError(f"position exit attempt {attempt_id!r} is terminal and is immutable")
        self.transitions.append((attempt_id, target))
        terminal = target in TERMINAL_EXIT_STATES
        updated = replace(
            current,
            state=target,
            submitted_at=current.submitted_at
            or (at if target is PositionExitState.SUBMISSION_IN_PROGRESS else None),
            acknowledged_at=current.acknowledged_at
            or (
                at
                if target
                in {
                    PositionExitState.SUBMITTED,
                    PositionExitState.ACCEPTED,
                    PositionExitState.PARTIALLY_FILLED,
                }
                else None
            ),
            terminal_at=at if terminal else None,
            broker_order_id=broker_order_id or current.broker_order_id,
            broker_status=broker_status or current.broker_status,
            filled_quantity=Decimal(filled_quantity)
            if filled_quantity
            else current.filled_quantity,
            filled_avg_price=(
                Decimal(filled_avg_price) if filled_avg_price else current.filled_avg_price
            ),
            failure_code=failure_code or current.failure_code,
            failure_detail=failure_detail or current.failure_detail,
        )
        self.rows[attempt_id] = updated
        return updated

    def mark_position_closed(
        self, *, attempt_id: str, verified_at: datetime
    ) -> PositionExitAttempt:
        current = self.rows[attempt_id]
        if current.closed_position_verified_at is not None:
            return current
        updated = replace(current, closed_position_verified_at=verified_at)
        self.rows[attempt_id] = updated
        return updated

    def list_recent(self, limit: int) -> tuple[PositionExitAttempt, ...]:
        return tuple(list(self.rows.values())[:limit])


class FakeExitAcknowledgements:
    def __init__(self) -> None:
        self.rows: list[BrokerAcknowledgement] = []

    def append(self, acknowledgement: BrokerAcknowledgement) -> BrokerAcknowledgement:
        self.rows.append(acknowledgement)
        return acknowledgement

    def for_attempt(self, attempt_id: str) -> tuple[BrokerAcknowledgement, ...]:
        return tuple(r for r in self.rows if r.attempt_id == attempt_id)

    def next_sequence(self, attempt_id: str) -> int:
        return len(self.for_attempt(attempt_id)) + 1


class FakeExitEvents:
    def __init__(self) -> None:
        self.rows: list[PositionExitEvent] = []

    def append(self, event: PositionExitEvent) -> PositionExitEvent:
        if any(e.event_id == event.event_id for e in self.rows):
            raise ValueError(f"exit event {event.event_id} already exists")
        self.rows.append(event)
        return event

    def for_entry(self, entry_intent_governance_id: str) -> tuple[PositionExitEvent, ...]:
        return tuple(
            e for e in self.rows if e.entry_intent_governance_id == entry_intent_governance_id
        )


class FakeExitRounds:
    def __init__(
        self,
        attempts: FakeExitAttempts,
        acknowledgements: FakeExitAcknowledgements,
        events: FakeExitEvents,
    ) -> None:
        self._attempts = attempts
        self._acknowledgements = acknowledgements
        self._events = events
        self.rows: dict[str, ReconciliationRound] = {}

    def begin(
        self, *, attempt: PositionExitAttempt, account_reference: str, started_at: datetime
    ) -> ReconciliationRound:
        if attempt.attempt_id not in self._attempts.rows:
            raise ValueError("no such exit attempt")
        sequence = len(self.for_attempt(attempt.attempt_id)) + 1
        round_ = ReconciliationRound(
            round_id=f"XRND-{attempt.attempt_id}-{sequence}"[:64],
            attempt_id=attempt.attempt_id,
            intent_governance_id=attempt.entry_intent_governance_id,
            authorization_id=attempt.authorization_id,
            client_order_id=attempt.client_order_id,
            account_reference=account_reference,
            sequence=sequence,
            started_at=started_at,
            outcome=None,
            completed_at=None,
            acknowledgement_sequence=None,
            broker_earliest_at=None,
            broker_latest_at=None,
            detail=None,
        )
        self.rows[round_.round_id] = round_
        return round_

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
    ) -> ReconciliationRound:
        current = self.rows[round_id]
        if current.is_complete:
            raise ValueError("a completed exit round is immutable")
        updated = replace(
            current,
            outcome=outcome,
            completed_at=completed_at,
            acknowledgement_sequence=acknowledgement_sequence,
            broker_earliest_at=broker_earliest_at,
            broker_latest_at=broker_latest_at,
            detail=None if detail is None else detail[:500],
        )
        self.rows[round_id] = updated
        return updated

    def for_attempt(self, attempt_id: str) -> tuple[ReconciliationRound, ...]:
        return tuple(
            sorted(
                (r for r in self.rows.values() if r.attempt_id == attempt_id),
                key=lambda r: r.sequence,
            )
        )

    def resolve_not_found(
        self,
        *,
        attempt_id: str,
        expected_version: tuple[int, int],
        at: datetime,
        failure_code: str,
        failure_detail: str,
    ) -> PositionExitAttempt | None:
        attempt = self._attempts.rows.get(attempt_id)
        if attempt is None:
            return None
        evaluation = exit_absence_evaluation(
            state=attempt.state,
            broker_order_id=attempt.broker_order_id,
            acknowledgements=self._acknowledgements.for_attempt(attempt_id),
            events=self._events.for_entry(attempt.entry_intent_governance_id),
            rounds=self.for_attempt(attempt_id),
        )
        if evaluation.rounds_version != expected_version or not evaluation.resolvable:
            return None
        return self._attempts.transition(
            attempt_id=attempt_id,
            target=PositionExitState.REJECTED,
            at=at,
            failure_code=failure_code,
            failure_detail=failure_detail,
        )
