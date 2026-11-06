"""M100 D1 -- the fail-closed trading-limit gate evaluated at the BROKER SUBMISSION BOUNDARY.

Why this exists. The M084 risk engine already knows the daily-loss, daily-order-count,
simultaneous-position and conflict rules, but the real PAPER path used to feed it constants
(``realized_pnl_today=0``, ``orders_submitted_today=0``, positions of one symbol only). Those
checks therefore ran once, at candidate preparation, against made-up evidence, and nothing
looked at them again when the order actually left the process.

This module is pure: it takes the limits of ONE stored configuration version and ONE fresh
broker evidence snapshot (plus this process's own durable in-flight attempts) and returns the
reasons an ENTRY must not be sent. No thresholds are invented here -- every number comes from
``OperatorTradingConfiguration``. Missing, unreadable or incomplete evidence is itself a refusal.

Risk-reducing exits never reach this module: it is invoked only on the ENTRY submission
handler. An entry limit therefore can never block a SELL-TO-CLOSE.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from empirical_platform.decision_candidate.operator_trading_configuration import (
    OperatorTradingConfiguration,
)

__all__ = [
    "trading_day_start",
    "BrokerPositionExposure",
    "BrokerWorkingOrder",
    "InFlightEntry",
    "PortfolioRiskEvidence",
    "ProposedEntry",
    "TradingLimits",
    "entry_limit_refusals",
    "is_working_status",
]

#: Broker order statuses that are DEFINITELY finished and can no longer fill. Everything else --
#: including a status this code has never heard of -- is treated as still working, so an
#: unexpected broker vocabulary can only make the gate stricter.
_TERMINAL_STATUSES = frozenset(
    {"filled", "canceled", "cancelled", "expired", "rejected", "done_for_day", "replaced"}
)


def is_working_status(status: str) -> bool:
    """Whether an order in ``status`` may still fill. Unknown vocabulary counts as working."""
    return status.strip().lower() not in _TERMINAL_STATUSES


@dataclass(frozen=True, slots=True)
class TradingLimits:
    """The entry limits of one configuration version. Nothing here has a default."""

    configuration_governance_id: str
    configuration_version: int
    maximum_daily_loss: Decimal
    maximum_daily_order_count: int
    maximum_simultaneous_positions: int
    maximum_deployable_capital: Decimal
    maximum_capital_per_trade: Decimal
    maximum_percent_per_trade: Decimal
    maximum_position_quantity_shares: int | None

    def __post_init__(self) -> None:
        for name in (
            "maximum_daily_loss",
            "maximum_deployable_capital",
            "maximum_capital_per_trade",
            "maximum_percent_per_trade",
        ):
            value = getattr(self, name)
            if not isinstance(value, Decimal) or not value.is_finite() or value <= 0:
                raise ValueError(f"{name} must be a positive finite Decimal; entries stay blocked")
        for name in ("maximum_daily_order_count", "maximum_simultaneous_positions"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"{name} must be a positive whole number; entries stay blocked")
        quantity_cap = self.maximum_position_quantity_shares
        if quantity_cap is not None and (
            isinstance(quantity_cap, bool) or not isinstance(quantity_cap, int) or quantity_cap <= 0
        ):
            raise ValueError("maximum_position_quantity_shares must be positive when present")

    @classmethod
    def from_configuration(cls, configuration: OperatorTradingConfiguration) -> TradingLimits:
        return cls(
            configuration_governance_id=configuration.configuration_governance_id,
            configuration_version=configuration.configuration_version,
            maximum_daily_loss=configuration.maximum_daily_loss,
            maximum_daily_order_count=configuration.maximum_daily_order_count,
            maximum_simultaneous_positions=configuration.maximum_simultaneous_positions,
            maximum_deployable_capital=configuration.maximum_deployable_capital,
            maximum_capital_per_trade=configuration.maximum_capital_per_trade,
            maximum_percent_per_trade=configuration.maximum_percent_per_trade,
            maximum_position_quantity_shares=configuration.maximum_position_quantity_shares,
        )


@dataclass(frozen=True, slots=True)
class BrokerPositionExposure:
    """One broker position, reduced to what the gate needs. ``cost_basis`` is |qty x avg entry|."""

    symbol: str
    quantity: int
    cost_basis: Decimal


@dataclass(frozen=True, slots=True)
class BrokerWorkingOrder:
    """One order the broker has not finished. ``notional`` is None when it cannot be priced."""

    client_order_id: str
    symbol: str
    side: str
    quantity: int
    notional: Decimal | None


@dataclass(frozen=True, slots=True)
class PortfolioRiskEvidence:
    """Everything the broker says about the account's risk, read in one pass.

    ``orders_today`` counts EVERY order submitted since the start of the operator-local day, in any
    final state (a rejected order still consumed an order). ``order_client_ids_today`` lets the gate
    avoid counting this process's own in-flight attempt twice once the broker also lists it.
    ``realized_pnl_today`` is derived from broker equity: (equity - last_equity) minus the broker's
    own unrealized intraday P&L. ``day_pnl`` is the whole day including unrealized.
    """

    captured_at: datetime
    positions: tuple[BrokerPositionExposure, ...]
    working_orders: tuple[BrokerWorkingOrder, ...]
    orders_today: int
    order_client_ids_today: frozenset[str]
    realized_pnl_today: Decimal
    day_pnl: Decimal

    def __post_init__(self) -> None:
        if self.captured_at.tzinfo is None:
            raise ValueError("captured_at must be timezone-aware")
        if isinstance(self.orders_today, bool) or self.orders_today < 0:
            raise ValueError("orders_today must be a non-negative whole number")
        for name in ("realized_pnl_today", "day_pnl"):
            value = getattr(self, name)
            if not isinstance(value, Decimal) or not value.is_finite():
                raise ValueError(f"{name} must be a finite Decimal")


@dataclass(frozen=True, slots=True)
class InFlightEntry:
    """An entry THIS system has durably claimed that the broker may not show yet."""

    client_order_id: str
    symbol: str
    quantity: int
    notional: Decimal | None
    counted_as_order_today: bool


@dataclass(frozen=True, slots=True)
class ProposedEntry:
    symbol: str
    quantity: int
    notional: Decimal


def entry_limit_refusals(
    *,
    proposed: ProposedEntry,
    limits: TradingLimits,
    evidence: PortfolioRiskEvidence,
    in_flight: Iterable[InFlightEntry],
) -> tuple[str, ...]:
    """Every reason this ENTRY may not be sent. Empty means the limits permit it.

    ``in_flight`` must already exclude the attempt being gated. An in-flight entry the broker
    already lists (matched by client_order_id) is NOT counted a second time.
    """
    refusals: list[str] = []
    symbol = proposed.symbol

    broker_order_ids = {order.client_order_id for order in evidence.working_orders}
    unseen = [
        entry
        for entry in in_flight
        if entry.client_order_id not in broker_order_ids
        and entry.client_order_id not in evidence.order_client_ids_today
    ]

    # --- existing position / working order conflicts -------------------------------------
    if any(position.symbol == symbol and position.quantity != 0 for position in evidence.positions):
        refusals.append(f"a broker position already exists in {symbol}")
    if any(order.symbol == symbol for order in evidence.working_orders):
        refusals.append(f"a working broker order already exists in {symbol}")
    if any(entry.symbol == symbol for entry in unseen):
        refusals.append(f"another entry in {symbol} is already in flight")

    # --- simultaneous positions: held + working buys + in-flight, one slot per symbol ----
    occupied = {p.symbol for p in evidence.positions if p.quantity != 0}
    occupied |= {o.symbol for o in evidence.working_orders if o.side.lower() == "buy"}
    occupied |= {entry.symbol for entry in unseen}
    if len(occupied - {symbol}) + 1 > limits.maximum_simultaneous_positions:
        refusals.append(
            f"{len(occupied - {symbol})} position slot(s) are already occupied; the limit is "
            f"{limits.maximum_simultaneous_positions} simultaneous positions"
        )

    # --- daily order count ------------------------------------------------------------------
    orders_today = evidence.orders_today + sum(
        1 for entry in unseen if entry.counted_as_order_today
    )
    if orders_today >= limits.maximum_daily_order_count:
        refusals.append(
            f"{orders_today} order(s) were already submitted today; the daily limit is "
            f"{limits.maximum_daily_order_count}"
        )

    # --- daily loss: the WORSE of realized and whole-day P&L (fail closed) ----------------------
    worst = min(evidence.realized_pnl_today, evidence.day_pnl)
    if -worst >= limits.maximum_daily_loss:
        refusals.append(
            f"today's loss {-worst} (realized {evidence.realized_pnl_today}, whole day "
            f"{evidence.day_pnl}) has reached the daily loss limit {limits.maximum_daily_loss}"
        )

    # --- size and exposure ------------------------------------------------------------------------
    if proposed.quantity <= 0:
        refusals.append("the proposed quantity is not positive")
    cap = limits.maximum_position_quantity_shares
    if cap is not None and proposed.quantity > cap:
        refusals.append(f"quantity {proposed.quantity} exceeds the {cap}-share position limit")
    per_trade = min(
        limits.maximum_capital_per_trade,
        limits.maximum_deployable_capital * limits.maximum_percent_per_trade / Decimal(100),
    )
    if proposed.notional > per_trade:
        refusals.append(
            f"order notional {proposed.notional} exceeds the per-trade limit {per_trade}"
        )

    unpriced = [
        o.symbol for o in evidence.working_orders if o.side.lower() == "buy" and o.notional is None
    ]
    unpriced += [e.symbol for e in unseen if e.notional is None]
    if unpriced:
        refusals.append(
            "exposure cannot be computed: no price for working/in-flight order(s) in "
            + ", ".join(sorted(set(unpriced)))
        )
    else:
        existing = (
            sum((p.cost_basis for p in evidence.positions), Decimal(0))
            + sum(
                (
                    o.notional or Decimal(0)
                    for o in evidence.working_orders
                    if o.side.lower() == "buy"
                ),
                Decimal(0),
            )
            + sum((e.notional or Decimal(0) for e in unseen), Decimal(0))
        )
        if existing + proposed.notional > limits.maximum_deployable_capital:
            refusals.append(
                f"total exposure {existing + proposed.notional} would exceed the deployable "
                f"capital limit {limits.maximum_deployable_capital}"
            )
    return tuple(refusals)


def trading_day_start(now: datetime, operator_timezone: str) -> datetime:
    """The start of "today": the EARLIER of operator-local midnight and New York midnight.

    The order-count window is therefore never narrower than either calendar the broker or the
    operator uses; a wider window can only count more orders, which is the fail-closed direction.
    """
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    starts = []
    for name in (operator_timezone, "America/New_York"):
        local = now.astimezone(ZoneInfo(name))
        starts.append(local.replace(hour=0, minute=0, second=0, microsecond=0))
    return min(starts)
