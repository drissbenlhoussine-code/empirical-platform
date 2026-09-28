"""MILESTONE-086 -- the deterministic simulation broker, scenario by scenario."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from empirical_platform.decision_candidate.operator_trading_configuration import OrderType
from empirical_platform.decision_candidate.paper_execution import (
    PAPER_ENDPOINT_HOST,
    PaperOrderRequest,
    is_client_order_id_collision,
    is_definitive_broker_refusal,
    order_terms_mismatches,
)
from empirical_platform.shared.brokerage.alpaca_paper import (
    BrokerAmbiguousDispatchError,
    BrokerIdentityExistsError,
    BrokerNotSentError,
)
from empirical_platform.shared.brokerage.simulation_paper import (
    SIMULATION_ACCOUNT_ID,
    SIMULATION_MARKET_DATA_HOST,
    SimulatedMarketData,
    SimulatedPaperBroker,
    SimulationScenario,
    SimulationStore,
    default_scenario_table,
)

_NOW = datetime(2026, 9, 28, 14, 0, tzinfo=UTC)


def _order(
    symbol: str = "AAPL", client_order_id: str = "m085-test-1", quantity: int = 4
) -> PaperOrderRequest:
    return PaperOrderRequest(
        symbol=symbol,
        side="BUY",
        quantity=quantity,
        order_type=OrderType.LIMIT,
        limit_price=Decimal("227.50"),
        time_in_force="DAY",
        extended_hours=False,
        client_order_id=client_order_id,
    )


@pytest.fixture
def store(tmp_path: Path) -> SimulationStore:
    s = SimulationStore(tmp_path / "sim.json")
    s.stage(scenarios=default_scenario_table(), quotes={"AAPL": ("227.40", "227.50")})
    return s


@pytest.fixture
def broker(store: SimulationStore) -> SimulatedPaperBroker:
    return SimulatedPaperBroker(store, clock=lambda: _NOW)


def test_the_store_is_durable_and_atomic(tmp_path: Path) -> None:
    path = tmp_path / "sim.json"
    first = SimulationStore(path)
    first.stage(scenarios={"AAPL": SimulationScenario.PARTIAL_FILL}, quotes={"AAPL": ("1", "2")})
    SimulatedPaperBroker(first, clock=lambda: _NOW).submit_order(_order())
    second = SimulationStore(path)  # a restarted process
    assert second.scenario_for("AAPL") is SimulationScenario.PARTIAL_FILL
    assert second.order("m085-test-1") is not None
    assert not list(tmp_path.glob(".simulation-*"))  # no temp file left behind


def test_unknown_identities_are_not_found_and_the_account_is_marked_simulated(
    broker: SimulatedPaperBroker,
) -> None:
    status, view, body = broker.fetch_order_by_client_order_id("m085-never-sent")
    assert (status, view) == (404, None) and "40410000" in body
    status, account = broker.fetch_account()
    assert (
        status == 200 and account["id"] == SIMULATION_ACCOUNT_ID and account["simulation"] is True
    )
    assert account["shorting_enabled"] is False and account["multiplier"] == "1"
    assert broker.endpoint_host == PAPER_ENDPOINT_HOST  # a domain invariant, documented
    assert (
        SimulatedMarketData(broker.store, clock=lambda: _NOW).endpoint_host
        == SIMULATION_MARKET_DATA_HOST
    )
    quote = SimulatedMarketData(broker.store, clock=lambda: _NOW).fetch_quote("AAPL")
    assert (
        quote is not None
        and quote.source == "SIMULATION"
        and quote.captured_at == _NOW - timedelta(seconds=2)
    )
    assert SimulatedMarketData(broker.store, clock=lambda: _NOW).fetch_quote("ZZZZ") is None


def test_accepted_then_filled_progresses_only_through_lookups(broker: SimulatedPaperBroker) -> None:
    status, view, body = broker.submit_order(_order())
    assert status == 200 and view is not None and view.status == "accepted"
    assert view.broker_order_id.startswith("sim-") and '"simulation": true' in body
    assert order_terms_mismatches(expected=_order(), actual=view) == ()
    _, first, _ = broker.fetch_order_by_client_order_id("m085-test-1")
    assert first is not None and first.status == "accepted"
    _, second, _ = broker.fetch_order_by_client_order_id("m085-test-1")
    assert second is not None and second.status == "filled"
    assert second.filled_quantity == "4" and second.filled_avg_price == "227.50"
    position = broker.fetch_position("AAPL")
    assert position is not None and position.quantity == 4
    _, third, _ = broker.fetch_order_by_client_order_id("m085-test-1")
    assert third is not None and third.status == "filled"  # terminal never changes


def test_a_second_order_under_the_same_identity_is_refused_as_a_collision(
    broker: SimulatedPaperBroker,
) -> None:
    broker.submit_order(_order())
    with pytest.raises(BrokerIdentityExistsError) as raised:
        broker.submit_order(_order())
    assert raised.value.http_status == 422 and raised.value.request_sent
    assert is_client_order_id_collision(422, raised.value.sanitized_body or "")
    assert len(broker.store.orders()) == 1


def test_before_send_failures_mean_nothing_was_sent(broker: SimulatedPaperBroker) -> None:
    def refuse() -> None:
        raise RuntimeError("policy said no")

    with pytest.raises(BrokerNotSentError):
        broker.submit_order(_order(), before_send=refuse)
    assert broker.store.orders() == ()


def test_network_failure_before_send_records_nothing(store: SimulationStore) -> None:
    broker = SimulatedPaperBroker(store, clock=lambda: _NOW)
    with pytest.raises(BrokerNotSentError):
        broker.submit_order(_order("META", "m085-meta"))
    assert store.order("m085-meta") is None


@pytest.mark.parametrize("symbol", ["GOOGL", "JPM", "PG", "KO"])
def test_delivered_but_ambiguous_scenarios_record_the_order_then_lose_the_answer(
    store: SimulationStore, symbol: str
) -> None:
    broker = SimulatedPaperBroker(store, clock=lambda: _NOW)
    with pytest.raises(BrokerAmbiguousDispatchError):
        broker.submit_order(_order(symbol, f"m085-{symbol}"))
    assert store.order(f"m085-{symbol}") is not None  # the broker holds it
    status, view, _ = broker.fetch_order_by_client_order_id(f"m085-{symbol}")
    assert status == 200 and view is not None and view.status == "accepted"


def test_a_lost_request_is_never_found(store: SimulationStore) -> None:
    broker = SimulatedPaperBroker(store, clock=lambda: _NOW)
    with pytest.raises(BrokerAmbiguousDispatchError):
        broker.submit_order(_order("XOM", "m085-xom"))
    assert store.order("m085-xom") is None
    assert broker.fetch_order_by_client_order_id("m085-xom")[0] == 404


def test_a_broker_rejection_is_a_definitive_refusal(store: SimulationStore) -> None:
    broker = SimulatedPaperBroker(store, clock=lambda: _NOW)
    status, view, body = broker.submit_order(_order("AMZN", "m085-amzn"))
    assert status == 403 and view is None
    assert is_definitive_broker_refusal(status, body)
    assert store.order("m085-amzn") is None


def test_partial_fill_and_not_filled(store: SimulationStore) -> None:
    broker = SimulatedPaperBroker(store, clock=lambda: _NOW)
    broker.submit_order(_order("MSFT", "m085-msft", quantity=4))
    broker.fetch_order_by_client_order_id("m085-msft")
    _, view, _ = broker.fetch_order_by_client_order_id("m085-msft")
    assert view is not None and view.status == "partially_filled" and view.filled_quantity == "2"
    broker.submit_order(_order("NVDA", "m085-nvda"))
    for _ in range(3):
        _, view, _ = broker.fetch_order_by_client_order_id("m085-nvda")
    assert view is not None and view.status == "accepted"
    broker.submit_order(_order("MSFT", "m085-msft-1", quantity=1))
    broker.fetch_order_by_client_order_id("m085-msft-1")
    _, one, _ = broker.fetch_order_by_client_order_id("m085-msft-1")
    assert one is not None and one.status == "accepted"  # one share cannot half-fill


def test_cancel_success_and_the_cancel_fill_race(store: SimulationStore) -> None:
    broker = SimulatedPaperBroker(store, clock=lambda: _NOW)
    _, v, _ = broker.submit_order(_order("V", "m085-v"))
    _, j, _ = broker.submit_order(_order("JNJ", "m085-jnj"))
    assert v is not None and j is not None
    assert broker.cancel_order(v.broker_order_id)[0] == 204
    assert broker.cancel_order(j.broker_order_id)[0] == 204
    assert broker.cancel_order("sim-nope")[0] == 404
    _, v2, _ = broker.fetch_order_by_client_order_id("m085-v")
    _, j2, _ = broker.fetch_order_by_client_order_id("m085-jnj")
    assert v2 is not None and v2.status == "canceled"
    assert j2 is not None and j2.status == "filled"
    assert broker.cancel_order(j.broker_order_id)[0] == 422  # already final


def test_the_clock_and_market_state_come_from_the_store(store: SimulationStore) -> None:
    broker = SimulatedPaperBroker(store, clock=lambda: _NOW)
    clock = broker.fetch_clock()
    assert clock.is_open and clock.timestamp == _NOW and clock.next_close is not None
    store.set_market_open(False)
    closed = broker.fetch_clock()
    assert not closed.is_open and closed.next_open is not None
    asset = broker.fetch_asset("aapl")
    assert asset.symbol == "AAPL" and asset.tradable and asset.asset_class == "us_equity"
    assert broker.fetch_position("AAPL") is None
