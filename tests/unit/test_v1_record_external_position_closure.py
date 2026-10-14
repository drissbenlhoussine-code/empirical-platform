"""RELEASE v1 -- `RecordExternalPositionClosureHandler` over the REAL simulation broker.

Every safety-relevant fact in the resulting record is read from a FRESH broker call, never
taken from the caller's word: these tests prove a forged or incorrect broker-order claim
(wrong side, wrong symbol, wrong quantity, not filled, not found, or a position that is not
actually zero) is refused, that a legitimate external SELL is recorded durably and
idempotently, and that an entry already carrying a platform-dispatched exit attempt is
refused outright (that case belongs to the EXISTING reconciliation path, not this one).
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from pathlib import Path

import pytest
from tests.unit._m086_fakes import World, simulation_world
from tests.unit._v1_fakes import FakeExternalPositionClosures

from empirical_platform.decision_candidate.external_position_closure import (
    external_position_closure_id,
)
from empirical_platform.decision_candidate.paper_execution import PaperExecutionState
from empirical_platform.shared.brokerage.simulation_paper import SimulatedOrder
from empirical_platform.usecases.decision_to_approval import NotFoundError
from empirical_platform.usecases.position_exit import PositionExitRefusedError
from empirical_platform.usecases.record_external_position_closure import (
    RecordExternalPositionClosureCommand,
    RecordExternalPositionClosureHandler,
)


@pytest.fixture
def world(tmp_path: Path) -> World:
    return simulation_world(tmp_path, exits=True)


def _intent(world: World, symbol: str) -> str:
    return f"INT-{world.proposal_id(symbol)}"


def _open_position(world: World, symbol: str = "AAPL") -> str:
    world.load_day((symbol,))
    proposal = world.proposal_id(symbol)
    view = world.service.prepare_approval(proposal)
    outcome = world.service.confirm_approval(proposal, view.ticket)
    assert outcome.sent == "sent", outcome.message
    for _ in range(2):
        world.clock.advance(5)
        world.service.refresh_executions()
    intent = _intent(world, symbol)
    entry = world.repositories.attempts.for_intent(intent)
    assert entry is not None and entry.state is PaperExecutionState.FILLED
    return intent


def _stage_external_sell(
    world: World,
    symbol: str,
    *,
    quantity: int,
    filled_avg_price: str,
    client_order_id: str = "EXTERNAL-SELL-1",
    side: str = "sell",
    status: str = "filled",
    filled_quantity: str | None = None,
    reduce_position: bool = True,
) -> None:
    """Puts an order directly into the simulated broker's order book, bypassing every
    Preview/Authorize/Submit handler -- modelling a trade this platform never dispatched
    (e.g. a manual broker-dashboard SELL)."""
    order = SimulatedOrder(
        broker_order_id=world.store.next_broker_order_id(),
        client_order_id=client_order_id,
        symbol=symbol,
        side=side,
        quantity=str(quantity),
        order_type="market",
        limit_price=None,
        time_in_force="day",
        extended_hours=False,
        status=status,
        filled_quantity=str(quantity) if filled_quantity is None else filled_quantity,
        filled_avg_price=filled_avg_price,
        scenario="EXIT_FILLED",
        lookups=0,
        cancel_requested=False,
        received_at=world.clock.utc.isoformat(),
    )
    world.store.put(order)
    if reduce_position:
        world.store.reduce_position(symbol, quantity)


def _handler(
    world: World, closures: FakeExternalPositionClosures
) -> RecordExternalPositionClosureHandler:
    return RecordExternalPositionClosureHandler(
        intents=world.repositories.intents,
        entry_attempts=world.repositories.attempts,
        exit_attempts=world.exits.attempts,
        closures=closures,
        events=world.exits.events,
        broker=world.broker,
    )


def _command(
    intent: str,
    *,
    client_order_id: str = "EXTERNAL-SELL-1",
    recorded_by: str = "owner",
    at: datetime,
) -> RecordExternalPositionClosureCommand:
    return RecordExternalPositionClosureCommand(
        entry_intent_governance_id=intent,
        client_order_id=client_order_id,
        recorded_by=recorded_by,
        at=at,
    )


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_a_legitimate_external_sell_is_recorded_with_broker_read_evidence(world: World) -> None:
    intent = _open_position(world)
    _stage_external_sell(world, "AAPL", quantity=8, filled_avg_price="229.50")
    closures = FakeExternalPositionClosures()
    handler = _handler(world, closures)

    closure = handler.handle(_command(intent, at=world.clock.utc))

    assert closure.closure_id == external_position_closure_id(intent)
    assert closure.entry_intent_governance_id == intent
    assert closure.symbol == "AAPL"
    assert closure.quantity == 8
    assert closure.filled_avg_price == Decimal("229.50")
    assert closure.recorded_by == "owner"
    assert closures.for_entry(intent) == closure
    events = world.exits.events.for_entry(intent)
    assert any(e.event_type == "EXTERNAL_POSITION_CLOSURE_RECORDED" for e in events)


def test_recording_twice_with_the_same_order_is_idempotent(world: World) -> None:
    intent = _open_position(world)
    _stage_external_sell(world, "AAPL", quantity=8, filled_avg_price="229.50")
    closures = FakeExternalPositionClosures()
    handler = _handler(world, closures)

    first = handler.handle(_command(intent, at=world.clock.utc))
    second = handler.handle(_command(intent, at=world.clock.utc))

    assert first == second
    assert len(closures.rows) == 1
    events = [
        e
        for e in world.exits.events.for_entry(intent)
        if e.event_type == "EXTERNAL_POSITION_CLOSURE_RECORDED"
    ]
    assert len(events) == 1  # not re-appended on the idempotent replay


def test_a_different_order_for_an_already_recorded_entry_is_refused(world: World) -> None:
    intent = _open_position(world)
    _stage_external_sell(
        world, "AAPL", quantity=8, filled_avg_price="229.50", client_order_id="EXTERNAL-SELL-1"
    )
    closures = FakeExternalPositionClosures()
    handler = _handler(world, closures)
    handler.handle(_command(intent, client_order_id="EXTERNAL-SELL-1", at=world.clock.utc))

    with pytest.raises(PositionExitRefusedError):
        handler.handle(_command(intent, client_order_id="SOME-OTHER-ORDER", at=world.clock.utc))
    assert closures.for_entry(intent).client_order_id == "EXTERNAL-SELL-1"  # unchanged


# ---------------------------------------------------------------------------
# Forged or incorrect broker evidence -- every one refused, nothing recorded
# ---------------------------------------------------------------------------


def test_an_order_the_broker_does_not_know_about_is_refused(world: World) -> None:
    intent = _open_position(world)
    closures = FakeExternalPositionClosures()
    handler = _handler(world, closures)

    with pytest.raises(PositionExitRefusedError):
        handler.handle(_command(intent, client_order_id="NEVER-EXISTED", at=world.clock.utc))
    assert closures.for_entry(intent) is None


def test_a_buy_order_cannot_be_closure_evidence(world: World) -> None:
    intent = _open_position(world)
    _stage_external_sell(
        world, "AAPL", quantity=8, filled_avg_price="229.50", side="buy", reduce_position=False
    )
    closures = FakeExternalPositionClosures()
    handler = _handler(world, closures)

    with pytest.raises(PositionExitRefusedError, match="not a SELL"):
        handler.handle(_command(intent, at=world.clock.utc))
    assert closures.for_entry(intent) is None


def test_an_order_that_is_not_filled_is_refused(world: World) -> None:
    intent = _open_position(world)
    _stage_external_sell(
        world,
        "AAPL",
        quantity=8,
        filled_avg_price="229.50",
        status="accepted",
        filled_quantity="0",
        reduce_position=False,
    )
    closures = FakeExternalPositionClosures()
    handler = _handler(world, closures)

    with pytest.raises(PositionExitRefusedError, match="not filled"):
        handler.handle(_command(intent, at=world.clock.utc))
    assert closures.for_entry(intent) is None


def test_an_order_for_a_different_symbol_is_refused(world: World) -> None:
    intent = _open_position(world, "AAPL")
    _stage_external_sell(
        world, "MSFT", quantity=8, filled_avg_price="229.50", reduce_position=False
    )
    closures = FakeExternalPositionClosures()
    handler = _handler(world, closures)

    with pytest.raises(PositionExitRefusedError, match="AAPL"):
        handler.handle(_command(intent, at=world.clock.utc))
    assert closures.for_entry(intent) is None


def test_an_order_filling_the_wrong_quantity_is_refused(world: World) -> None:
    intent = _open_position(world)  # 8 shares attributable
    _stage_external_sell(world, "AAPL", quantity=3, filled_avg_price="229.50")
    closures = FakeExternalPositionClosures()
    handler = _handler(world, closures)

    with pytest.raises(PositionExitRefusedError, match="attributable"):
        handler.handle(_command(intent, at=world.clock.utc))
    assert closures.for_entry(intent) is None


def test_a_filled_sell_that_did_not_actually_zero_the_position_is_refused(world: World) -> None:
    """The order itself looks perfect (right side, filled, right symbol/quantity) but the
    broker's CURRENT position was never reduced -- e.g. a stale or fabricated claim. This
    must be refused even though every per-order check passes."""
    intent = _open_position(world)
    _stage_external_sell(
        world, "AAPL", quantity=8, filled_avg_price="229.50", reduce_position=False
    )
    closures = FakeExternalPositionClosures()
    handler = _handler(world, closures)

    with pytest.raises(PositionExitRefusedError, match="still open"):
        handler.handle(_command(intent, at=world.clock.utc))
    assert closures.for_entry(intent) is None


def test_an_entry_that_does_not_exist_is_refused(world: World) -> None:
    closures = FakeExternalPositionClosures()
    handler = _handler(world, closures)

    with pytest.raises(NotFoundError):
        handler.handle(_command("INT-DOES-NOT-EXIST", at=world.clock.utc))


# ---------------------------------------------------------------------------
# An entry that already has a platform-dispatched exit uses the OTHER path
# ---------------------------------------------------------------------------


def test_an_entry_with_an_existing_platform_dispatched_exit_is_refused(world: World) -> None:
    intent = _open_position(world)
    review = world.service.exits.review(intent)  # type: ignore[union-attr]
    outcome = world.service.exits.confirm(intent, review.ticket)  # type: ignore[union-attr]
    assert outcome.ok and outcome.sent == "sent"
    assert world.exits.attempts.for_entry(intent) != ()

    closures = FakeExternalPositionClosures()
    handler = _handler(world, closures)

    with pytest.raises(PositionExitRefusedError, match="platform-dispatched"):
        handler.handle(_command(intent, client_order_id="EXTERNAL-SELL-1", at=world.clock.utc))
    assert closures.for_entry(intent) is None
