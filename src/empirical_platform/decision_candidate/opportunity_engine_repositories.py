"""MILESTONE-090 -- persistence-neutral and broker-neutral contracts for the opportunity engine.

A SEPARATE PORT FROM `PaperMarketDataPort`, DELIBERATELY. `PaperMarketDataPort` (M085) is
documented as "quotes only, this port cannot place, modify or cancel anything" and is already
implemented by `SimulatedMarketData` (M086) and every M085-M089 test fake. Adding a bars method
to it would force every one of those to grow a method they never use, for zero benefit and real
blast radius on already-reviewed code. `IntradayBarsPort` is new and narrow: one method, read
evidence, nothing else. `AlpacaPaperMarketDataClient` (M085/M090) implements BOTH ports -- one
concrete class satisfying two Protocols is ordinary duck typing, not a widened capability.

THE PERSISTENCE PORTS MIRROR M084's OWN DISCIPLINE. `OpportunityRepository` is append-only
except the one state-transition write path; `OpportunityDecisionRepository` is append-only,
exactly one decision per opportunity (a real Owner action, durably recorded, never inferred).
Neither port can express a broker write: there is no method here, or anywhere in this module,
that submits, cancels or modifies an order.
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from empirical_platform.decision_candidate.opportunity_engine import (
    OpportunityDecision,
    OpportunityStatus,
    TradingOpportunity,
)

__all__ = [
    "BrokerBarView",
    "IntradayBarsPort",
    "OpportunityDecisionRepository",
    "OpportunityRepository",
]


class BrokerBarView(Protocol):
    """One real OHLCV bar as the broker's market-data feed describes it. Read-only evidence."""

    @property
    def symbol(self) -> str: ...

    @property
    def timestamp(self) -> datetime: ...

    @property
    def open(self) -> str: ...

    @property
    def high(self) -> str: ...

    @property
    def low(self) -> str: ...

    @property
    def close(self) -> str: ...

    @property
    def volume(self) -> int: ...


class IntradayBarsPort(Protocol):
    """Everything the opportunity engine may ask a market-data feed for. Nothing more.

    One method. No order-shaped argument exists to accept, and no order-shaped answer exists
    to return: this port cannot place, modify or cancel anything, exactly like
    `PaperMarketDataPort`, and is kept separate from it (see module docstring).
    """

    @property
    def endpoint_host(self) -> str: ...

    def fetch_minute_bars(
        self, symbol: str, *, start: datetime, end: datetime, limit: int
    ) -> tuple[BrokerBarView, ...]: ...


class OpportunityRepository(Protocol):
    """Durable store of every generated opportunity. Append-only except one transition."""

    def save(self, opportunity: TradingOpportunity) -> TradingOpportunity:
        """Persist a newly generated opportunity. Refuses a duplicate `opportunity_id`."""
        ...

    def get(self, opportunity_id: str) -> TradingOpportunity | None: ...

    def latest_for_symbol_today(
        self, symbol: str, *, session_date: str
    ) -> TradingOpportunity | None:
        """The most recently generated opportunity for `symbol` on `session_date`, if any."""
        ...

    def list_for_session(self, session_date: str) -> tuple[TradingOpportunity, ...]: ...

    def transition(
        self, *, opportunity_id: str, target: OpportunityStatus, at: datetime
    ) -> TradingOpportunity:
        """Move ONE opportunity to a new status. Refuses a transition the domain disallows."""
        ...


class OpportunityDecisionRepository(Protocol):
    """Durable record of the Owner's one action on one opportunity. Append-only, single-use."""

    def save(self, decision: OpportunityDecision) -> OpportunityDecision:
        """Persist the Owner's decision. Refuses a second decision for the same opportunity."""
        ...

    def for_opportunity(self, opportunity_id: str) -> OpportunityDecision | None: ...
