"""M100 D1 -- the pure gate, exhaustively at its boundaries. No broker, no database, no clock."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from empirical_platform.decision_candidate.trading_limit_gate import (
    BrokerPositionExposure,
    BrokerWorkingOrder,
    InFlightEntry,
    PortfolioRiskEvidence,
    ProposedEntry,
    TradingLimits,
    entry_limit_refusals,
    is_working_status,
    trading_day_start,
)

LIMITS = TradingLimits(
    configuration_governance_id="CFG",
    configuration_version=1,
    maximum_daily_loss=Decimal("100"),
    maximum_daily_order_count=3,
    maximum_simultaneous_positions=2,
    maximum_deployable_capital=Decimal("1000"),
    maximum_capital_per_trade=Decimal("400"),
    maximum_percent_per_trade=Decimal("50"),
    maximum_position_quantity_shares=10,
)
NOW = datetime(2026, 11, 5, 15, 0, tzinfo=UTC)


def _evidence(**overrides: object) -> PortfolioRiskEvidence:
    values: dict[str, object] = {
        "captured_at": NOW,
        "positions": (),
        "working_orders": (),
        "orders_today": 0,
        "order_client_ids_today": frozenset(),
        "realized_pnl_today": Decimal(0),
        "day_pnl": Decimal(0),
    }
    values.update(overrides)
    return PortfolioRiskEvidence(**values)  # type: ignore[arg-type]


def _propose(symbol: str = "AAPL", quantity: int = 2, notional: str = "200") -> ProposedEntry:
    return ProposedEntry(symbol=symbol, quantity=quantity, notional=Decimal(notional))


def _refusals(
    evidence: PortfolioRiskEvidence, proposed: ProposedEntry | None = None, **kw: object
) -> tuple[str, ...]:
    return entry_limit_refusals(
        proposed=proposed or _propose(),
        limits=LIMITS,
        evidence=evidence,
        in_flight=kw.get("in_flight", ()),  # type: ignore[arg-type]
    )


def test_a_quiet_account_permits_the_entry() -> None:
    assert _refusals(_evidence()) == ()


@pytest.mark.parametrize(
    ("realized", "day", "blocked"),
    [
        ("-99.99", "-99.99", False),
        ("-100", "-100", True),
        ("0", "-100", True),
        ("-100", "50", True),
        ("500", "500", False),
    ],
)
def test_daily_loss_boundary(realized: str, day: str, blocked: bool) -> None:
    evidence = _evidence(realized_pnl_today=Decimal(realized), day_pnl=Decimal(day))
    assert bool(_refusals(evidence)) is blocked


@pytest.mark.parametrize(("orders", "blocked"), [(2, False), (3, True), (50, True)])
def test_daily_order_count_boundary(orders: int, blocked: bool) -> None:
    assert bool(_refusals(_evidence(orders_today=orders))) is blocked


def test_an_in_flight_entry_the_broker_already_lists_is_not_counted_twice() -> None:
    listed = BrokerWorkingOrder("cid-1", "MSFT", "buy", 1, Decimal(10))
    flight = InFlightEntry("cid-1", "MSFT", 1, Decimal(10), counted_as_order_today=True)
    evidence = _evidence(orders_today=2, working_orders=(listed,))
    assert _refusals(evidence, in_flight=(flight,)) == ()


def test_an_in_flight_entry_the_broker_has_not_listed_is_counted() -> None:
    flight = InFlightEntry("cid-9", "MSFT", 1, Decimal(10), counted_as_order_today=True)
    assert _refusals(_evidence(orders_today=2), in_flight=(flight,))  # 2 + 1 = 3 >= 3


def test_in_flight_entry_recognised_through_todays_order_ids_even_if_no_longer_working() -> None:
    flight = InFlightEntry("cid-9", "MSFT", 1, Decimal(10), counted_as_order_today=True)
    evidence = _evidence(orders_today=2, order_client_ids_today=frozenset({"cid-9"}))
    assert _refusals(evidence, in_flight=(flight,)) == ()


def test_position_slots_count_held_working_and_in_flight_symbols_once_each() -> None:
    held = BrokerPositionExposure("MSFT", 1, Decimal(10))
    assert _refusals(_evidence(positions=(held,))) == ()  # 1 of 2 used, one left
    flight = InFlightEntry("cid", "NVDA", 1, Decimal(10), counted_as_order_today=True)
    assert _refusals(_evidence(positions=(held,)), in_flight=(flight,))  # second slot taken


def test_same_symbol_conflicts_for_position_working_order_and_in_flight() -> None:
    held = BrokerPositionExposure("AAPL", 1, Decimal(10))
    working = BrokerWorkingOrder("c1", "AAPL", "sell", 1, None)
    flight = InFlightEntry("c2", "AAPL", 1, Decimal(10), counted_as_order_today=True)
    assert any("position already exists" in r for r in _refusals(_evidence(positions=(held,))))
    assert any("working broker order" in r for r in _refusals(_evidence(working_orders=(working,))))
    assert any("in flight" in r for r in _refusals(_evidence(), in_flight=(flight,)))


def test_size_and_exposure_limits() -> None:
    assert any("share position limit" in r for r in _refusals(_evidence(), _propose(quantity=11)))
    assert any("per-trade limit" in r for r in _refusals(_evidence(), _propose(notional="400.01")))
    big = BrokerPositionExposure("MSFT", 5, Decimal("700"))
    assert any(
        "deployable capital" in r
        for r in _refusals(_evidence(positions=(big,)), _propose(notional="400"))
    )
    assert _refusals(_evidence(positions=(big,)), _propose(notional="300")) == ()


def test_an_unpriced_working_buy_makes_exposure_unprovable() -> None:
    unpriced = BrokerWorkingOrder("c1", "MSFT", "buy", 1, None)
    assert any(
        "exposure cannot be computed" in r for r in _refusals(_evidence(working_orders=(unpriced,)))
    )


@pytest.mark.parametrize(
    "field", ["maximum_daily_loss", "maximum_deployable_capital", "maximum_capital_per_trade"]
)
def test_a_missing_or_nonpositive_money_limit_cannot_even_be_constructed(field: str) -> None:
    from dataclasses import replace

    with pytest.raises(ValueError, match="entries stay blocked"):
        replace(LIMITS, **{field: Decimal(0)})


def test_a_nonpositive_count_limit_cannot_be_constructed() -> None:
    from dataclasses import replace

    with pytest.raises(ValueError, match="entries stay blocked"):
        replace(LIMITS, maximum_daily_order_count=0)


@pytest.mark.parametrize(
    ("status", "working"),
    [
        ("new", True),
        ("accepted", True),
        ("partially_filled", True),
        ("pending_cancel", True),
        ("brand_new_vocabulary", True),
        ("filled", False),
        ("canceled", False),
        ("rejected", False),
        ("expired", False),
        ("done_for_day", False),
        ("FILLED", False),
    ],
)
def test_order_status_classification_is_strict_toward_unknowns(status: str, working: bool) -> None:
    assert is_working_status(status) is working


def test_trading_day_start_is_the_earlier_of_operator_and_new_york_midnight() -> None:
    helsinki = trading_day_start(datetime(2026, 11, 5, 15, 0, tzinfo=UTC), "Europe/Helsinki")
    new_york = trading_day_start(datetime(2026, 11, 5, 15, 0, tzinfo=UTC), "America/New_York")
    assert new_york == datetime(2026, 11, 5, 5, 0, tzinfo=UTC)
    assert helsinki == min(helsinki, new_york)
    assert helsinki <= new_york
