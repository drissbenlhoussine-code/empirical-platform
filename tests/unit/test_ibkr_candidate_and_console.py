"""Canonical sizing and review rendering, without a broker or personal database."""

from dataclasses import replace
from datetime import datetime, timedelta
from decimal import Decimal

import pytest
from tests.unit.test_ibkr_market_access import NOW, Broker, Journal, plan, policy, service

from empirical_platform.decision_candidate.market_identity import Currency, InstrumentIdentity
from empirical_platform.decision_candidate.market_plan import MarketPlan
from empirical_platform.decision_candidate.product_market_inputs import TradingCostEstimate
from empirical_platform.entrypoints._market_console_routes import register_market_routes
from empirical_platform.entrypoints._operator_console_web import Request, Router, SecuritySession
from empirical_platform.usecases.market_candidate import prepare_market_plan
from empirical_platform.usecases.market_console import full_plan_fields


class CandidateBroker(Broker):
    def last_trade(self, instrument: InstrumentIdentity) -> tuple[Decimal, datetime]:
        return Decimal("100"), self.at

    def average_daily_volume(self, instrument: InstrumentIdentity) -> tuple[int, datetime]:
        return 200_000, self.at


class CandidateJournal(Journal):
    def save_plan(self, p: MarketPlan) -> None:
        self.plan = p


def costs() -> TradingCostEstimate:
    return TradingCostEstimate(
        "TEST-COST-1", "TEST-ONLY-EVIDENCE", "NOKIA", Decimal("1"), Decimal("0.01"), NOW
    )


def test_prepare_uses_canonical_sizing_and_has_complete_immutable_review() -> None:
    journal, broker = CandidateJournal(), CandidateBroker()
    p = prepare_market_plan(
        broker=broker,
        journal=journal,
        policy=policy(),
        symbol="NOKIA",
        costs=costs(),
        cost_currency=Currency.EUR,
        now=lambda: NOW,
    )  # type: ignore[arg-type]
    assert p.risk.quantity == 1 and p.risk.planned_loss <= 5
    assert p.risk.stop_price == Decimal("98") and p.target == Decimal("104")
    assert p.entry_quote.ask == 100 and not broker.sent
    fields = dict(full_plan_fields(p))
    assert fields["Broker"] == "IBKR_PAPER" and fields["Market"] == "XHEL"
    assert fields["Currency"] == "EUR" and fields["Full-plan fingerprint"] == p.fingerprint
    assert fields["Bid (EUR)"] == "99.5" and fields["Target price gain (EUR)"] == "4"


@pytest.mark.parametrize(
    "kind", ["currency", "stale_cost", "kill", "closed", "watchlist", "liquidity"]
)
def test_candidate_gate_has_no_fallback_or_fabricated_input(kind: str) -> None:
    journal, broker = CandidateJournal(), CandidateBroker()
    configured = policy()
    estimate = costs()
    currency = Currency.EUR
    if kind == "currency":
        currency = Currency.USD
    elif kind == "stale_cost":
        estimate = replace(estimate, observed_at=NOW - timedelta(minutes=5))
    elif kind == "kill":
        journal.engaged = True
    elif kind == "closed":
        broker.at = NOW + timedelta(days=1)
    elif kind == "watchlist":
        configured = replace(configured, watchlist=("OTHER",))
    elif kind == "liquidity":
        configured = replace(configured, minimum_liquidity_shares=300_000)
    with pytest.raises(ValueError):
        prepare_market_plan(
            broker=broker,
            journal=journal,
            policy=configured,
            symbol="NOKIA",
            costs=estimate,
            cost_currency=currency,
            now=lambda: broker.at,
        )  # type: ignore[arg-type]
    assert not broker.sent


def test_existing_console_panel_is_read_only_and_labels_unverified_setup() -> None:
    router = Router(SecuritySession())
    register_market_routes(router)
    assert set(router._routes) == {("GET", "/markets")}
    response = router._routes[("GET", "/markets")](Request("GET", "/markets", {}, {}, {}, {}), "")
    body = response.body.decode()
    assert "NASDAQ HELSINKI" in body and "IBKR PAPER" in body and "EUR" in body
    assert "OWNER SETUP REQUIRED" in body and 'href="/health"' in body
    assert "<form" not in body


@pytest.mark.parametrize(
    "kind",
    [
        "unapproved",
        "risk",
        "quantity",
        "notional",
        "watchlist",
        "ask",
        "spread",
        "cash",
        "daily_loss",
        "unknown_route",
    ],
)
def test_final_entry_checks_refuse_before_dispatch(
    kind: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    journal, broker = Journal(), Broker()
    if kind == "unapproved":
        monkeypatch.setattr(journal, "approval", lambda _: None)
    elif kind == "risk":
        journal.plan = replace(
            plan(), risk=replace(plan().risk, maximum_planned_loss_per_trade=Decimal("6"))
        )
    elif kind == "quantity":
        journal.plan = replace(
            plan(), risk=replace(plan().risk, maximum_position_quantity_shares=2)
        )
    elif kind == "notional":
        journal.plan = replace(plan(), maximum_notional=Decimal("501"))
    elif kind == "watchlist":
        other = replace(plan().instrument, symbol="OTHER")
        journal.plan = replace(
            plan(), instrument=other, entry_quote=replace(plan().entry_quote, instrument=other)
        )
    elif kind == "ask":
        broker.ask = Decimal("100.01")
    elif kind == "spread":
        broker.bid = Decimal("98")
    elif kind == "cash":
        current = broker.account()
        monkeypatch.setattr(broker, "account", lambda: replace(current, cash=Decimal("1000")))
    elif kind == "daily_loss":
        current = broker.account()
        monkeypatch.setattr(
            broker, "account", lambda: replace(current, realized_pnl=Decimal("-500"))
        )
    elif kind == "unknown_route":
        current_contract = broker.resolve("NOKIA")
        monkeypatch.setattr(
            broker,
            "resolve",
            lambda _: replace(
                current_contract, instrument=replace(current_contract.instrument, contract_id="456")
            ),
        )
    with pytest.raises(ValueError):
        service(journal, broker).submit_entry(journal.plan.plan_id)
    assert not broker.sent
