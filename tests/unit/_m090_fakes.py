"""In-memory MILESTONE-090 fakes for the opportunity-engine usecase suites.

A dedicated fake set, not a reuse of `tests/unit/_m085_fakes.py`'s `FakeBroker`/
`FakeMarketData`: those fix the broker clock to real wall-clock time and a single hardcoded
asset, neither of which is controllable enough to test the session gate or per-symbol
eligibility deterministically. Every knob here is an explicit, settable attribute.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from empirical_platform.decision_candidate.opportunity_engine import (
    OpportunityDecision,
    OpportunityStatus,
    TradingOpportunity,
    is_opportunity_transition_allowed,
)


@dataclass
class FakeClockView:
    is_open: bool
    timestamp: datetime
    next_open: datetime | None = None
    next_close: datetime | None = None


@dataclass
class FakeAssetView:
    symbol: str
    status: str = "active"
    tradable: bool = True
    asset_class: str = "us_equity"
    exchange: str = "NASDAQ"
    fractionable: bool = True


@dataclass
class FakeQuoteView:
    symbol: str
    bid: str | None
    ask: str | None
    captured_at: datetime
    source: str = "test-feed"


@dataclass
class FakeBarView:
    symbol: str
    timestamp: datetime
    open: str
    high: str
    low: str
    close: str
    volume: int


class FakeOpportunityBroker:
    """`PaperBrokerPort`, fully implemented, every fact settable."""

    endpoint_host = "test-broker"

    def __init__(
        self,
        *,
        clock: FakeClockView,
        assets: dict[str, FakeAssetView | None] | None = None,
        account_equity: str = "100000",
        account_status: int = 200,
    ) -> None:
        self.clock = clock
        self.assets: dict[str, FakeAssetView | None] = assets or {}
        self.account_equity = account_equity
        self.account_status = account_status
        self.asset_lookups: list[str] = []

    def fetch_account(self) -> tuple[int, dict[str, object]]:
        if self.account_status != 200:
            return self.account_status, {}
        return 200, {
            "id": "test-account",
            "equity": self.account_equity,
            "cash": self.account_equity,
        }

    def fetch_clock(self) -> FakeClockView:
        return self.clock

    def fetch_asset(self, symbol: str) -> FakeAssetView:
        self.asset_lookups.append(symbol)
        asset = self.assets.get(symbol)
        if asset is None:
            from empirical_platform.shared.brokerage.alpaca_paper import BrokerResponseInvalidError

            raise BrokerResponseInvalidError(f"no such asset {symbol}")
        return asset

    def fetch_position(self, symbol: str) -> object | None:
        del symbol
        return None

    def submit_order(self, order: object, *, before_send: object = None) -> tuple[int, object, str]:
        raise AssertionError("GenerateOpportunitiesHandler must never submit an order")

    def fetch_order_by_client_order_id(self, client_order_id: str) -> tuple[int, object, str]:
        del client_order_id
        return 404, None, "{}"

    def cancel_order(self, broker_order_id: str) -> tuple[int, str]:
        raise AssertionError("the opportunity engine must never cancel an order")


class FakeOpportunityMarketData:
    """`PaperMarketDataPort`, quotes only, per-symbol settable."""

    endpoint_host = "test-market-data"

    def __init__(self, quotes: dict[str, FakeQuoteView | None] | None = None) -> None:
        self.quotes: dict[str, FakeQuoteView | None] = quotes or {}

    def fetch_quote(self, symbol: str) -> FakeQuoteView | None:
        return self.quotes.get(symbol)


class FakeBars:
    """`IntradayBarsPort`, per-symbol settable."""

    endpoint_host = "test-market-data"

    def __init__(self, bars: dict[str, tuple[FakeBarView, ...]] | None = None) -> None:
        self.bars: dict[str, tuple[FakeBarView, ...]] = bars or {}
        self.requests: list[str] = []

    def fetch_minute_bars(
        self, symbol: str, *, start: datetime, end: datetime, limit: int
    ) -> tuple[FakeBarView, ...]:
        del start, end, limit
        self.requests.append(symbol)
        return self.bars.get(symbol, ())


class FakeOpportunities:
    def __init__(self) -> None:
        self.rows: dict[str, TradingOpportunity] = {}

    def save(self, opportunity: TradingOpportunity) -> TradingOpportunity:
        if opportunity.opportunity_id in self.rows:
            raise ValueError("opportunity ids are unique")
        self.rows[opportunity.opportunity_id] = opportunity
        return opportunity

    def get(self, opportunity_id: str) -> TradingOpportunity | None:
        return self.rows.get(opportunity_id)

    def latest_for_symbol_today(
        self, symbol: str, *, session_date: str
    ) -> TradingOpportunity | None:
        matches = [
            o
            for o in self.rows.values()
            if o.symbol == symbol and o.generated_at.date().isoformat() == session_date
        ]
        return max(matches, key=lambda o: o.generated_at) if matches else None

    def list_for_session(self, session_date: str) -> tuple[TradingOpportunity, ...]:
        return tuple(
            o for o in self.rows.values() if o.generated_at.date().isoformat() == session_date
        )

    def transition(
        self, *, opportunity_id: str, target: OpportunityStatus, at: datetime
    ) -> TradingOpportunity:
        current = self.rows.get(opportunity_id)
        if current is None:
            raise ValueError(f"no opportunity {opportunity_id!r}")
        if not is_opportunity_transition_allowed(current.status, target):
            raise ValueError(f"{current.status.value} -> {target.value} is not allowed")
        from dataclasses import replace

        updated = replace(current, status=target)
        self.rows[opportunity_id] = updated
        return updated


class FakeOpportunityDecisions:
    def __init__(self) -> None:
        self.rows: dict[str, OpportunityDecision] = {}

    def save(self, decision: OpportunityDecision) -> OpportunityDecision:
        if decision.opportunity_id in self.rows:
            raise ValueError("at most one decision per opportunity")
        self.rows[decision.opportunity_id] = decision
        return decision

    def for_opportunity(self, opportunity_id: str) -> OpportunityDecision | None:
        return self.rows.get(opportunity_id)
