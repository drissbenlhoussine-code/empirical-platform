"""RELEASE v1 -- reconciling a position closed OUTSIDE this platform's own exit pipeline.

THE PROBLEM. A plan's position can be closed by a human directly on the broker's own
dashboard (not through this platform's Preview -> Authorize -> Submit chain), for example
when this console could not load the plan at all (see
`external-review/INCIDENT-2026-10-14-aapl-overdue-recovery/evidence.md`). Nothing durable
records that outside fact: `ApprovedPlanRepository`'s one controlled mutation is
`claim_exit_trigger` (see its own docstring), `PositionExitAttempt`'s lifecycle assumes a
dispatch THIS platform claimed, and `PositionPlanManager` has no way to learn a trigger it
claimed will never be resolved by its own Preview/Authorize/Submit chain. Left alone, it
retries forever (`NEEDS_ATTENTION` every poll) for a plan that can never succeed.

WHY THIS CANNOT ITSELF PRODUCE A BUY OR SELL. This handler calls exactly two broker methods,
both read-only: `ExitBrokerPort.fetch_order_by_client_order_id` (to verify the CALLER-NAMED
order, never to place one) and `ExitBrokerPort.fetch_position` (to verify the broker holds
zero, right now). It never imports or calls `submit_close_order`, `cancel_order`, or any
Preview/Authorize/Submit handler, and never constructs a `PositionExitPreview`,
`PositionExitAuthorization`, or `PositionExitAttempt`. See
`tests/architecture/test_v1_external_position_closure_boundaries.py` for the static proof.

THE ORIGINAL `ApprovedPlan` ROW IS NEVER TOUCHED. Recording a closure here writes only a new
`ExternalPositionClosure` row (Store C) and one `PositionExitEvent` audit entry; it never
calls `ApprovedPlanRepository.claim_exit_trigger` or any other plan mutation.
`decision_candidate/approved_plan.py`'s row, including `triggered_exit_kind`/
`triggered_exit_at`, is preserved exactly as the automatic manager (or a legacy read) wrote
it -- `PositionPlanManager` is taught to check for a recorded closure instead
(`usecases.position_plan_manager`'s own `PlanOutcomeKind.EXTERNALLY_CLOSED`).

EVERY SAFETY-RELEVANT FACT IS READ FROM THE BROKER, NOT ASSERTED. The caller supplies only
WHICH order to check (`client_order_id`) and WHO is recording it (`recorded_by`); every
other fact in the resulting record -- symbol, quantity, broker_order_id, filled_avg_price --
is read from that one broker lookup, never trusted from the caller. Recording is refused
unless ALL of the following hold, each checked against a FRESH broker read:

  1. An entry exists for the named `entry_intent_governance_id` and is filled (there is an
     open position to reconcile at all).
  2. No platform-dispatched exit attempt already exists for this entry (that case belongs to
     the EXISTING reconciliation path -- `ReconcilePositionExitHandler` -- not this one).
  3. The named order exists at the broker, is a SELL, is fully FILLED, is for the exact
     symbol, and filled EXACTLY the attributable open quantity -- never a partial match.
  4. The broker's CURRENT position in the symbol is zero. A historically-filled SELL whose
     shares were since re-bought (or that never actually zeroed the position) is refused:
     this handler verifies the position is closed NOW, not merely that one qualifying order
     once existed.

IDEMPOTENT, NEVER OVERWRITTEN. If a closure is already recorded for this entry under the
SAME `client_order_id`, a repeat call returns the existing record unchanged (no second
broker read, no second event). A repeat call naming a DIFFERENT order for an entry that
already has a recorded closure is refused outright -- a recorded closure is never replaced.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation

from empirical_platform.decision_candidate.external_position_closure import (
    EXTERNAL_POSITION_CLOSURE_RECORDED_EVENT_TYPE,
    ExternalPositionClosure,
    external_position_closure_id,
)
from empirical_platform.decision_candidate.external_position_closure_repositories import (
    ExternalPositionClosureRepository,
)
from empirical_platform.decision_candidate.paper_execution_repositories import (
    ExecutionAttemptRepository,
)
from empirical_platform.decision_candidate.position_exit import PositionExitEvent
from empirical_platform.decision_candidate.position_exit_repositories import (
    ExitBrokerPort,
    PositionExitAttemptRepository,
    PositionExitEventRepository,
)
from empirical_platform.decision_candidate.product_repositories import (
    ApprovedOrderIntentRepository,
)
from empirical_platform.usecases.position_exit import (
    AssessPositionExitHandler,
    PositionExitRefusedError,
)

__all__ = [
    "ExternalPositionClosure",
    "RecordExternalPositionClosureCommand",
    "RecordExternalPositionClosureHandler",
]


def _event_id(*parts: str) -> str:
    digest = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()
    return "XEV-ext-" + digest[:32]


@dataclass(frozen=True, slots=True)
class RecordExternalPositionClosureCommand:
    entry_intent_governance_id: str
    #: Which broker order to verify. This is the ONLY evidence-shaped input: every other
    #: fact in the resulting record is read from the broker's answer about this order, not
    #: supplied here.
    client_order_id: str
    recorded_by: str
    at: datetime


class RecordExternalPositionClosureHandler:
    """Verify, then durably record, that an entry's position was closed by a broker order
    this platform never dispatched. Read-only against the broker; see the module docstring."""

    __slots__ = ("_assess", "_closures", "_events", "_broker")

    def __init__(
        self,
        *,
        intents: ApprovedOrderIntentRepository,
        entry_attempts: ExecutionAttemptRepository,
        exit_attempts: PositionExitAttemptRepository,
        closures: ExternalPositionClosureRepository,
        events: PositionExitEventRepository,
        broker: ExitBrokerPort,
    ) -> None:
        self._assess = AssessPositionExitHandler(
            intents=intents,
            entry_attempts=entry_attempts,
            exit_attempts=exit_attempts,
            external_closures=closures,
            broker=broker,
        )
        self._closures = closures
        self._events = events
        self._broker = broker

    def handle(self, command: RecordExternalPositionClosureCommand) -> ExternalPositionClosure:
        if not isinstance(command.recorded_by, str) or not command.recorded_by.strip():
            raise ValueError("recorded_by must be a non-empty string")

        existing = self._closures.for_entry(command.entry_intent_governance_id)
        if existing is not None:
            if existing.client_order_id == command.client_order_id:
                return existing  # idempotent: the same evidence was already recorded
            raise PositionExitRefusedError(
                f"entry {command.entry_intent_governance_id!r} already has an external "
                f"closure recorded under order {existing.client_order_id!r}; refusing to "
                f"record a different order {command.client_order_id!r} for the same entry"
            )

        assessment = self._assess.handle(command.entry_intent_governance_id, at=command.at)
        entry = assessment.entry_attempt
        if entry is None or entry.filled_quantity is None or entry.filled_quantity <= 0:
            raise PositionExitRefusedError(
                "no filled entry exists for this intent; there is no position to reconcile"
            )
        if assessment.existing_exit is not None:
            raise PositionExitRefusedError(
                "this position already has a platform-dispatched exit attempt "
                f"({assessment.existing_exit.attempt_id}); use the normal reconciliation "
                "path (ReconcilePositionExitHandler), not an external closure"
            )
        attributable = assessment.snapshot.attributable_quantity
        if attributable is None or attributable <= 0:
            raise PositionExitRefusedError(
                "no attributable open quantity remains for this entry; there is nothing to "
                "reconcile as externally closed"
            )

        status, view, _sanitized = self._broker.fetch_order_by_client_order_id(
            command.client_order_id
        )
        if status != 200 or view is None:
            raise PositionExitRefusedError(
                f"the broker does not confirm order {command.client_order_id!r} "
                f"(HTTP {status}); nothing was recorded"
            )
        if view.side.strip().lower() != "sell":
            raise PositionExitRefusedError(
                f"order {command.client_order_id!r} is a {view.side!r} order, not a SELL; "
                "it cannot be closure evidence"
            )
        if view.status.strip().lower() != "filled":
            raise PositionExitRefusedError(
                f"order {command.client_order_id!r} is {view.status!r}, not filled; "
                "nothing was recorded"
            )
        if view.symbol != assessment.entry_intent.symbol:
            raise PositionExitRefusedError(
                f"order {command.client_order_id!r} is for {view.symbol!r}, not "
                f"{assessment.entry_intent.symbol!r}; it cannot close this position"
            )
        try:
            filled_quantity = Decimal(view.filled_quantity)
        except InvalidOperation as error:
            raise PositionExitRefusedError(
                "the broker's filled quantity for this order is not numeric"
            ) from error
        if filled_quantity != Decimal(attributable):
            raise PositionExitRefusedError(
                f"order {command.client_order_id!r} filled {filled_quantity} shares, not the "
                f"attributable {attributable}; it cannot close this exact position"
            )
        if view.filled_avg_price is None:
            raise PositionExitRefusedError(
                f"order {command.client_order_id!r} has no filled average price; "
                "nothing was recorded"
            )
        try:
            filled_avg_price = Decimal(view.filled_avg_price)
        except InvalidOperation as error:
            raise PositionExitRefusedError(
                "the broker's filled average price for this order is not numeric"
            ) from error

        # THE POSITION, VERIFIED NOW -- not merely that a qualifying order once existed.
        position = self._broker.fetch_position(assessment.entry_intent.symbol)
        live_quantity = 0 if position is None else int(position.quantity)
        if live_quantity != 0:
            raise PositionExitRefusedError(
                f"the broker currently reports {live_quantity} shares of "
                f"{assessment.entry_intent.symbol!r} still open; this position is not "
                "actually closed, so nothing was recorded"
            )

        closure = ExternalPositionClosure(
            closure_id=external_position_closure_id(command.entry_intent_governance_id),
            entry_intent_governance_id=command.entry_intent_governance_id,
            symbol=assessment.entry_intent.symbol,
            quantity=attributable,
            broker_order_id=view.broker_order_id,
            client_order_id=view.client_order_id,
            filled_avg_price=filled_avg_price,
            recorded_by=command.recorded_by,
            recorded_at=command.at,
        )
        saved = self._closures.save(closure)
        self._events.append(
            PositionExitEvent(
                event_id=_event_id(saved.closure_id, saved.client_order_id),
                entry_intent_governance_id=saved.entry_intent_governance_id,
                attempt_id=None,
                event_type=EXTERNAL_POSITION_CLOSURE_RECORDED_EVENT_TYPE,
                occurred_at=command.at,
                detail=(
                    f"external closure recorded: SELL {saved.quantity} {saved.symbol} @ "
                    f"{saved.filled_avg_price} broker_order={saved.broker_order_id} "
                    f"client_order={saved.client_order_id} recorded_by={saved.recorded_by}"
                )[:500],
            )
        )
        return saved
