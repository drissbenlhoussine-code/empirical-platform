"""Typed market-access ports; no HTTP status codes or broker-specific payloads."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Protocol

from empirical_platform.decision_candidate.approved_plan import ApprovedPlan, ExitTriggerKind
from empirical_platform.decision_candidate.market_identity import (
    InstrumentIdentity,
    MarketQuote,
    PaperAccountIdentity,
)
from empirical_platform.decision_candidate.market_plan import MarketPlan, OrderPurpose, OrderTruth


@dataclass(frozen=True, slots=True)
class AccountTruth:
    identity: PaperAccountIdentity
    cash: Decimal
    equity: Decimal
    realized_pnl: Decimal
    observed_at: datetime
    ready: bool


@dataclass(frozen=True, slots=True)
class PositionTruth:
    account: PaperAccountIdentity
    instrument: InstrumentIdentity
    quantity: Decimal
    observed_at: datetime


@dataclass(frozen=True, slots=True)
class ResolvedContract:
    instrument: InstrumentIdentity
    minimum_tick: Decimal
    liquid_open: datetime | None
    liquid_close: datetime | None
    observed_at: datetime


@dataclass(frozen=True, slots=True)
class PositionsSnapshot:
    account: PaperAccountIdentity
    positions: tuple[PositionTruth, ...]
    observed_at: datetime


@dataclass(frozen=True, slots=True)
class MarketHistoryEntry:
    plan: MarketPlan
    status: str
    realized_price_pnl: Decimal | None
    closed_at: datetime | None


@dataclass(frozen=True, slots=True)
class DispatchRecord:
    plan_id: str
    purpose: OrderPurpose
    order_id: int
    reference: str
    quantity: Decimal
    limit_price: Decimal
    state: str


class MarketReadPort(Protocol):
    @property
    def identity(self) -> PaperAccountIdentity: ...
    def account(self) -> AccountTruth: ...
    def resolve(self, symbol: str) -> ResolvedContract: ...
    def quote(self, instrument: InstrumentIdentity) -> MarketQuote: ...
    def positions(self) -> tuple[PositionTruth, ...]: ...
    def positions_snapshot(self) -> PositionsSnapshot: ...
    def open_orders(self) -> tuple[OrderTruth, ...]: ...
    def reconcile(self, plan: MarketPlan, record: DispatchRecord) -> OrderTruth | None: ...


class MarketExecutionPort(MarketReadPort, Protocol):
    def next_order_id(self) -> int: ...
    def send_bound(
        self, plan: MarketPlan, record: DispatchRecord, *, before_send: Callable[[], None]
    ) -> None:
        """Only a durable claimed request; any uncertain delivery is never retried."""
        ...

    def cancel_bound(self, plan: MarketPlan, record: DispatchRecord) -> None: ...


class MarketCandidateDataPort(MarketReadPort, Protocol):
    def last_trade(self, instrument: InstrumentIdentity) -> tuple[Decimal, datetime]: ...
    def average_daily_volume(self, instrument: InstrumentIdentity) -> tuple[int, datetime]: ...


class MarketJournal(Protocol):
    def save_plan(self, plan: MarketPlan) -> None: ...
    def get_plan(self, plan_id: str) -> MarketPlan: ...
    def approve(
        self, plan_id: str, owner: str, fingerprint: str, now: datetime
    ) -> ApprovedPlan: ...
    def approval(self, plan_id: str) -> ApprovedPlan | None: ...
    def active_plans(self) -> tuple[MarketPlan, ...]: ...
    def history(self) -> tuple[MarketHistoryEntry, ...]: ...
    def claim_trigger(self, plan_id: str, kind: ExitTriggerKind, now: datetime) -> bool: ...
    def reserve(
        self,
        plan: MarketPlan,
        purpose: OrderPurpose,
        order_id: int,
        quantity: Decimal,
        limit_price: Decimal,
        now: datetime,
    ) -> DispatchRecord | None: ...
    def dispatch(self, plan_id: str, purpose: OrderPurpose) -> DispatchRecord | None: ...
    def observe(
        self, plan: MarketPlan, record: DispatchRecord, truth: OrderTruth | None
    ) -> None: ...
    def truth(self, plan_id: str, purpose: OrderPurpose) -> OrderTruth | None: ...
    def close_verified(
        self,
        plan: MarketPlan,
        realized_price_pnl: Decimal,
        now: datetime,
        verification: PositionsSnapshot,
    ) -> None: ...
    def entry_count(self, since: datetime) -> int: ...
    def kill_switch(self) -> bool: ...
    def claim_cancel(self, record: DispatchRecord, now: datetime) -> bool: ...


class ApprovedExitCycle(Protocol):
    """Narrow Plan Manager extension: no entry or generic order capability."""

    def manage_exits_once(self, *, now: datetime) -> tuple[str, ...]: ...
