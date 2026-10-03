"""Adversarial offline contracts; simulated transport is never acceptance evidence."""

from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
from empirical_ibkr.paper import IBKRPaperAdapter, liquid_interval
from empirical_ibkr.session import IBKRSession
from tests.unit.test_v1_entry_risk_contract import config, risk

from empirical_platform.decision_candidate.approved_plan import ApprovedPlan, ExitTriggerKind
from empirical_platform.decision_candidate.helsinki_calendar import (
    helsinki_session,
    require_helsinki_open,
)
from empirical_platform.decision_candidate.market_access_ports import (
    AccountTruth,
    DispatchRecord,
    PositionsSnapshot,
    PositionTruth,
    ResolvedContract,
)
from empirical_platform.decision_candidate.market_identity import (
    BrokerIdentity,
    Currency,
    InstrumentIdentity,
    MarketQuote,
    PaperAccountIdentity,
)
from empirical_platform.decision_candidate.market_plan import (
    MarketPlan,
    OrderPurpose,
    OrderTruth,
    read_market_plan,
)
from empirical_platform.decision_candidate.operator_trading_configuration import (
    OperatorTradingConfiguration,
    configuration_fingerprint,
)
from empirical_platform.usecases.market_access import MarketAccessService, require_acceptance_policy

NOW = datetime(2026, 10, 2, 10, tzinfo=UTC)


def policy() -> OperatorTradingConfiguration:
    return config(
        base_currency="EUR",
        watchlist=("NOKIA",),
        permitted_markets=("XHEL",),
        maximum_capital_per_trade=Decimal("500"),
        maximum_simultaneous_positions=1,
    )


def instrument() -> InstrumentIdentity:
    return InstrumentIdentity(
        BrokerIdentity.IBKR_PAPER, "123", "NOKIA", "XHEL", "HEX", "HEX", Currency.EUR, "STK"
    )


def plan() -> MarketPlan:
    p = policy()
    return MarketPlan(
        "PLAN-TEST",
        instrument(),
        PaperAccountIdentity(BrokerIdentity.IBKR_PAPER, "DU12345", Currency.EUR, 71),
        p.configuration_governance_id,
        p.configuration_version,
        configuration_fingerprint(p),
        "a" * 64,
        risk(),
        Decimal("110"),
        Decimal("500"),
        Decimal("101"),
        NOW + timedelta(hours=3),
        NOW + timedelta(minutes=2),
        NOW,
        MarketQuote(instrument(), Decimal("99"), Decimal("100"), NOW, NOW, True),
    )


class Journal:
    def __init__(self) -> None:
        self.plan = plan()
        self.approved = self.plan.approve("test-owner", self.plan.fingerprint, NOW)
        self.records: dict[OrderPurpose, DispatchRecord] = {}
        self.truths: dict[OrderPurpose, OrderTruth | None] = {}
        self.engaged = False
        self.closed = False
        self.canceled = False

    def get_plan(self, plan_id: str) -> MarketPlan:
        assert plan_id == self.plan.plan_id
        return self.plan

    def approval(self, plan_id: str) -> ApprovedPlan:
        return self.approved

    def kill_switch(self) -> bool:
        return self.engaged

    def entry_count(self, since: datetime) -> int:
        return int(OrderPurpose.ENTRY in self.records)

    def dispatch(self, plan_id: str, purpose: OrderPurpose) -> DispatchRecord | None:
        return self.records.get(purpose)

    def reserve(
        self,
        p: MarketPlan,
        purpose: OrderPurpose,
        order_id: int,
        quantity: Decimal,
        limit_price: Decimal,
        now: datetime,
    ) -> DispatchRecord | None:
        if purpose in self.records:
            return None
        record = DispatchRecord(
            p.plan_id,
            purpose,
            order_id,
            p.order_reference(purpose),
            quantity,
            limit_price,
            "CLAIMED",
        )
        self.records[purpose] = record
        return record

    def observe(self, p: MarketPlan, record: DispatchRecord, truth: OrderTruth | None) -> None:
        self.truths[record.purpose] = truth

    def active_plans(self) -> tuple[MarketPlan, ...]:
        return () if self.closed else (self.plan,)

    def claim_trigger(self, plan_id: str, kind: ExitTriggerKind, now: datetime) -> bool:
        if self.approved.triggered_exit_kind is not None:
            return False
        self.approved = replace(self.approved, triggered_exit_kind=kind, triggered_exit_at=now)
        return True

    def close_verified(
        self, p: MarketPlan, pnl: Decimal, now: datetime, verification: PositionsSnapshot
    ) -> None:
        self.closed = True

    def claim_cancel(self, record: DispatchRecord, now: datetime) -> bool:
        if self.canceled:
            return False
        self.canceled = True
        return True


class Broker:
    def __init__(self) -> None:
        self.identity = plan().account
        self.at = NOW
        self.bid, self.ask = Decimal("99.5"), Decimal("100")
        self.holdings: tuple[PositionTruth, ...] = ()
        self.orders: tuple[OrderTruth, ...] = ()
        self.truths: dict[OrderPurpose, OrderTruth] = {}
        self.sent: list[DispatchRecord] = []
        self.cancels = 0
        self.ambiguous = False
        self.before: Any = lambda: None

    def account(self) -> AccountTruth:
        return AccountTruth(
            self.identity, Decimal("5000"), Decimal("5000"), Decimal("0"), self.at, True
        )

    def resolve(self, symbol: str) -> ResolvedContract:
        session = helsinki_session(self.at)
        return ResolvedContract(
            instrument(), Decimal("0.01"), session.opens_at, session.closes_at, self.at
        )

    def quote(self, i: InstrumentIdentity) -> MarketQuote:
        return MarketQuote(i, self.bid, self.ask, self.at, self.at, True)

    def positions(self) -> tuple[PositionTruth, ...]:
        return self.holdings

    def positions_snapshot(self) -> PositionsSnapshot:
        return PositionsSnapshot(self.identity, self.holdings, self.at)

    def open_orders(self) -> tuple[OrderTruth, ...]:
        return self.orders

    def next_order_id(self) -> int:
        return max((record.order_id for record in self.sent), default=0) + 1

    def send_bound(
        self, p: MarketPlan, record: DispatchRecord, *, before_send: Callable[[], None]
    ) -> None:
        self.before()
        before_send()
        self.sent.append(record)
        if self.ambiguous:
            raise RuntimeError("test transport lost acknowledgement")

    def reconcile(self, p: MarketPlan, record: DispatchRecord) -> OrderTruth | None:
        return self.truths.get(record.purpose)

    def cancel_bound(self, p: MarketPlan, record: DispatchRecord) -> None:
        self.cancels += 1

    def fill(self, purpose: OrderPurpose, *, quantity: str = "1", status: str = "FILLED") -> None:
        record = next(r for r in self.sent if r.purpose == purpose)
        self.truths[purpose] = OrderTruth(
            instrument(),
            self.identity,
            record.reference,
            record.order_id,
            record.order_id + 100,
            purpose,
            record.quantity,
            Decimal(quantity),
            Decimal("100"),
            status,
            self.at,
        )
        self.holdings = (
            ()
            if purpose is OrderPurpose.CLOSE
            else (PositionTruth(self.identity, instrument(), Decimal(quantity), self.at),)
        )


def service(journal: Journal, broker: Broker) -> MarketAccessService:
    return MarketAccessService(journal=journal, broker=broker, policy=policy, now=lambda: broker.at)  # type: ignore[arg-type]


def test_plan_round_trip_and_immutable_route() -> None:
    p = plan()
    assert read_market_plan(p.document()) == p
    assert (
        p.fingerprint
        != replace(
            p,
            instrument=replace(p.instrument, contract_id="124"),
            entry_quote=replace(p.entry_quote, instrument=replace(p.instrument, contract_id="124")),
        ).fingerprint
    )
    assert p.fingerprint != replace(p, account=replace(p.account, client_id=72)).fingerprint
    assert p.order_reference(OrderPurpose.ENTRY) != p.order_reference(OrderPurpose.CLOSE)
    with pytest.raises(ValueError):
        p.approve("test-owner", "0" * 64, NOW)
    with pytest.raises(ValueError):
        p.approve("test-owner", p.fingerprint, p.approval_expires)


@pytest.mark.parametrize(
    "changes",
    [
        {"exchange": "SMART"},
        {"currency": Currency.USD},
        {"primary_exchange": "NYSE"},
        {"contract_id": "00123"},
        {"contract_id": "0"},
        {"broker": "LIVE"},
        {"security_type": "CFD"},
    ],
)
def test_wrong_identity_refused(changes: dict[str, Any]) -> None:
    with pytest.raises(ValueError):
        replace(instrument(), **changes)


@pytest.mark.parametrize(
    "at,status",
    [
        ("2026-10-03T10:00:00+00:00", "CLOSED"),
        ("2026-12-24T10:00:00+00:00", "CLOSED"),
        ("2026-10-02T07:00:00+00:00", "OPEN"),
        ("2026-10-26T08:00:00+00:00", "OPEN"),
        ("2026-10-02T15:25:00+00:00", "CLOSING_AUCTION"),
        ("2027-10-01T10:00:00+00:00", "UNVERIFIED_CALENDAR"),
    ],
)
def test_calendar_dst_holiday_auction_unknown_year(at: str, status: str) -> None:
    assert helsinki_session(datetime.fromisoformat(at)).status == status


def test_broker_short_session_intersection_and_discovery_before_open() -> None:
    opens, closes = liquid_interval(
        "20261002:1000-20261002:1300", "Europe/Helsinki", NOW - timedelta(hours=5)
    )
    with pytest.raises(ValueError):
        require_helsinki_open(NOW, broker_liquid_open=opens, broker_liquid_close=closes)


@pytest.mark.parametrize(
    "changes",
    [
        {"realtime": False},
        {"source_at": NOW - timedelta(seconds=61)},
        {"received_at": NOW + timedelta(seconds=1)},
        {"instrument": replace(instrument(), contract_id="456")},
    ],
)
def test_bad_quote_refused(changes: dict[str, Any]) -> None:
    q = MarketQuote(instrument(), Decimal("99"), Decimal("100"), NOW, NOW, True)
    with pytest.raises(ValueError):
        replace(q, **changes).validate(instrument(), NOW, 60)


def test_duplicate_unknown_and_restart_never_resend() -> None:
    j, b = Journal(), Broker()
    b.ambiguous = True
    with pytest.raises(RuntimeError):
        service(j, b).submit_entry(j.plan.plan_id)
    service(j, b).submit_entry(j.plan.plan_id)
    assert len(b.sent) == 1 and j.truths[OrderPurpose.ENTRY] is None


def test_expiry_at_last_boundary_prevents_dispatch() -> None:
    j, b = Journal(), Broker()
    b.before = lambda: setattr(b, "at", j.plan.approval_expires)
    with pytest.raises(ValueError, match="expired"):
        service(j, b).submit_entry(j.plan.plan_id)
    assert not b.sent


def test_kill_blocks_entry_but_not_approved_full_exit_and_zero_required() -> None:
    j, b = Journal(), Broker()
    j.engaged = True
    with pytest.raises(ValueError, match="kill switch"):
        service(j, b).submit_entry(j.plan.plan_id)
    j.engaged = False
    service(j, b).submit_entry(j.plan.plan_id)
    b.fill(OrderPurpose.ENTRY)
    j.engaged = True
    b.bid, b.ask = Decimal("110"), Decimal("111")
    service(j, b).manage_exits_once(now=NOW)
    service(j, b).manage_exits_once(now=NOW)
    assert len(b.sent) == 2 and b.sent[-1].purpose is OrderPurpose.CLOSE
    b.fill(OrderPurpose.CLOSE)
    b.holdings = (PositionTruth(b.identity, instrument(), Decimal("1"), NOW),)
    service(j, b).manage_exits_once(now=NOW)
    assert not j.closed
    b.holdings = ()
    service(j, b).manage_exits_once(now=NOW)
    assert j.closed


def test_partial_fill_cancel_once_then_close_exact_attributable_fraction() -> None:
    j, b = Journal(), Broker()
    service(j, b).submit_entry(j.plan.plan_id)
    b.fill(OrderPurpose.ENTRY, quantity="0.5", status="PARTIAL")
    b.bid, b.ask = Decimal("94"), Decimal("95")
    service(j, b).manage_exits_once(now=NOW)
    service(j, b).manage_exits_once(now=NOW)
    assert b.cancels == 1 and len(b.sent) == 1
    b.fill(OrderPurpose.ENTRY, quantity="0.5", status="CANCELED")
    service(j, b).manage_exits_once(now=NOW)
    assert b.sent[-1].quantity == Decimal("0.5")


def test_cross_routing_and_changed_policy_refused() -> None:
    j, b = Journal(), Broker()
    b.identity = PaperAccountIdentity(BrokerIdentity.ALPACA_PAPER, "test-alpaca", Currency.USD)
    with pytest.raises(ValueError, match="identity"):
        service(j, b).submit_entry(j.plan.plan_id)
    with pytest.raises(ValueError):
        require_acceptance_policy(config())
    assert not b.sent


def test_sdk_adapter_defaults_to_read_only() -> None:
    session = IBKRSession(account="DU12345")
    adapter = IBKRPaperAdapter(session)
    with pytest.raises(RuntimeError):
        adapter.send_bound(
            plan(),
            DispatchRecord(
                plan().plan_id,
                OrderPurpose.ENTRY,
                1,
                plan().order_reference(OrderPurpose.ENTRY),
                Decimal("1"),
                Decimal("100"),
                "CLAIMED",
            ),
            before_send=lambda: None,
        )
    for port in (7496, 4001):
        with pytest.raises(ValueError):
            IBKRSession(account="DU12345", port=port)
