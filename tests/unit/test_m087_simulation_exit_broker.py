"""MILESTONE-087 -- the simulated broker's SELL-TO-CLOSE: reduces a long, never below zero."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from empirical_platform.decision_candidate.operator_trading_configuration import OrderType
from empirical_platform.decision_candidate.paper_execution import PaperOrderRequest
from empirical_platform.decision_candidate.position_exit import PositionExitRequest
from empirical_platform.shared.brokerage.alpaca_paper import (
    BrokerAmbiguousDispatchError,
    BrokerIdentityExistsError,
    BrokerNotSentError,
)
from empirical_platform.shared.brokerage.simulation_paper import (
    SimulatedPaperBroker,
    SimulationExitScenario,
    SimulationScenario,
    SimulationStore,
    default_exit_scenario_table,
)

NOW = datetime(2026, 9, 28, 14, 0, tzinfo=UTC)


def _close(symbol: str = "AAPL", quantity: int = 8, tag: str = "1") -> PositionExitRequest:
    return PositionExitRequest(
        symbol=symbol,
        side="SELL_TO_CLOSE",
        quantity=quantity,
        order_type=OrderType.LIMIT,
        limit_price=Decimal("227.40"),
        time_in_force="DAY",
        extended_hours=False,
        client_order_id=f"m087-{tag}",
        entry_intent_governance_id="INT-1",
        account_reference="ref:abc",
        environment="SIMULATION",
    )


def _buy(symbol: str = "AAPL", quantity: int = 8) -> PaperOrderRequest:
    return PaperOrderRequest(
        symbol=symbol,
        side="BUY",
        quantity=quantity,
        order_type=OrderType.LIMIT,
        limit_price=Decimal("227.50"),
        time_in_force="DAY",
        extended_hours=False,
        client_order_id="m085-entry",
    )


@pytest.fixture
def broker(tmp_path: Path) -> SimulatedPaperBroker:
    store = SimulationStore(tmp_path / "sim.json")
    store.stage(
        scenarios={"AAPL": SimulationScenario.ACCEPTED_THEN_FILLED},
        quotes={"AAPL": ("227.40", "227.50")},
        exit_scenarios={"AAPL": SimulationExitScenario.EXIT_FILLED},
    )
    return SimulatedPaperBroker(store, clock=lambda: NOW)


def _fill_entry(broker: SimulatedPaperBroker) -> None:
    broker.submit_order(_buy())
    broker.fetch_order_by_client_order_id("m085-entry")
    broker.fetch_order_by_client_order_id("m085-entry")
    assert broker.store.position("AAPL") == 8


def test_a_close_with_no_position_is_definitively_refused_and_records_nothing(
    broker: SimulatedPaperBroker,
) -> None:
    status, view, body = broker.submit_close_order(_close())
    assert status == 403 and view is None and "no long position" in body
    assert broker.store.order("m087-1") is None


def test_a_close_for_more_than_the_position_is_refused(broker: SimulatedPaperBroker) -> None:
    _fill_entry(broker)
    status, view, body = broker.submit_close_order(_close(quantity=9))
    assert status == 403 and view is None and "insufficient qty" in body
    assert broker.store.position("AAPL") == 8 and broker.store.order("m087-1") is None


def test_a_full_close_fills_and_sets_the_position_to_zero(broker: SimulatedPaperBroker) -> None:
    _fill_entry(broker)
    status, view, _ = broker.submit_close_order(_close())
    assert status == 200 and view is not None and view.side == "sell" and view.status == "accepted"
    assert broker.store.position("AAPL") == 8  # accepted is not filled
    broker.fetch_order_by_client_order_id("m087-1")
    _, filled, payload = broker.fetch_order_by_client_order_id("m087-1")
    assert filled is not None and filled.status == "filled" and filled.filled_quantity == "8"
    assert filled.filled_avg_price == "227.40" and '"simulation": true' in payload
    assert broker.store.position("AAPL") == 0 and broker.fetch_position("AAPL") is None


def test_a_partial_close_reduces_the_position_by_the_filled_part_only(
    broker: SimulatedPaperBroker,
) -> None:
    _fill_entry(broker)
    broker.store.stage(
        scenarios={"AAPL": SimulationScenario.ACCEPTED_THEN_FILLED},
        quotes={"AAPL": ("227.40", "227.50")},
        exit_scenarios={"AAPL": SimulationExitScenario.EXIT_PARTIAL_FILL},
    )
    broker.submit_close_order(_close())
    broker.fetch_order_by_client_order_id("m087-1")
    _, view, _ = broker.fetch_order_by_client_order_id("m087-1")
    assert view is not None and view.status == "partially_filled" and view.filled_quantity == "4"
    assert broker.store.position("AAPL") == 4
    _, again, _ = broker.fetch_order_by_client_order_id("m087-1")
    assert again is not None and again.status == "partially_filled"
    assert broker.store.position("AAPL") == 4  # the rest keeps working; nothing double-counts


def test_a_duplicate_exit_identity_is_refused_by_the_broker(broker: SimulatedPaperBroker) -> None:
    _fill_entry(broker)
    broker.submit_close_order(_close())
    with pytest.raises(BrokerIdentityExistsError):
        broker.submit_close_order(_close())
    assert len([o for o in broker.store.orders() if o.side == "sell"]) == 1


def test_the_position_can_never_go_negative_even_under_a_racing_fill(
    broker: SimulatedPaperBroker,
) -> None:
    _fill_entry(broker)
    broker.submit_close_order(_close(tag="a"))
    broker.store.reduce_position("AAPL", 8)  # an external sale empties the position meanwhile
    broker.fetch_order_by_client_order_id("m087-a")
    with pytest.raises(ValueError, match="negative"):
        broker.fetch_order_by_client_order_id("m087-a")  # the fill would cross zero: refused
    assert broker.store.position("AAPL") == 0


@pytest.mark.parametrize(
    ("scenario", "error", "recorded"),
    [
        (SimulationExitScenario.EXIT_FAILURE_BEFORE_SEND, BrokerNotSentError, False),
        (
            SimulationExitScenario.EXIT_AMBIGUOUS_AFTER_POSSIBLE_SEND,
            BrokerAmbiguousDispatchError,
            True,
        ),
        (SimulationExitScenario.EXIT_RECONCILIATION_FINDS, BrokerAmbiguousDispatchError, True),
        (SimulationExitScenario.EXIT_RESTART_WHILE_UNKNOWN, BrokerAmbiguousDispatchError, True),
        (SimulationExitScenario.EXIT_RECONCILIATION_NOT_FOUND, BrokerAmbiguousDispatchError, False),
    ],
)
def test_failure_scenarios_are_recorded_exactly_when_the_request_was_delivered(
    broker: SimulatedPaperBroker,
    scenario: SimulationExitScenario,
    error: type[Exception],
    recorded: bool,
) -> None:
    _fill_entry(broker)
    broker.store.stage(
        scenarios={"AAPL": SimulationScenario.ACCEPTED_THEN_FILLED},
        quotes={"AAPL": ("227.40", "227.50")},
        exit_scenarios={"AAPL": scenario},
    )
    with pytest.raises(error):
        broker.submit_close_order(_close())
    assert (broker.store.order("m087-1") is not None) is recorded
    assert broker.store.position("AAPL") == 8  # nothing moved without a fill


def test_before_send_refusals_mean_nothing_was_sent(broker: SimulatedPaperBroker) -> None:
    _fill_entry(broker)

    def refuse() -> None:
        raise RuntimeError("kill switch engaged")

    with pytest.raises(BrokerNotSentError):
        broker.submit_close_order(_close(), before_send=refuse)
    assert broker.store.order("m087-1") is None


def test_the_default_exit_table_covers_every_staged_symbol_and_every_scenario_kind() -> None:
    table = default_exit_scenario_table()
    assert len(table) == 12
    assert set(table.values()) >= {
        SimulationExitScenario.EXIT_FILLED,
        SimulationExitScenario.EXIT_ACCEPTED_NOT_FILLED,
        SimulationExitScenario.EXIT_PARTIAL_FILL,
        SimulationExitScenario.EXIT_REJECTION,
        SimulationExitScenario.EXIT_FAILURE_BEFORE_SEND,
        SimulationExitScenario.EXIT_RECONCILIATION_FINDS,
        SimulationExitScenario.EXIT_RECONCILIATION_NOT_FOUND,
        SimulationExitScenario.EXIT_CANCEL_FILL_RACE,
        SimulationExitScenario.EXIT_RESTART_WHILE_UNKNOWN,
    }
