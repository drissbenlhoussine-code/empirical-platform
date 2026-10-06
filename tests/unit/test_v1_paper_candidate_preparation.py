"""RELEASE v1 Release Blocker (in-console Owner gate) -- `prepare_v1_paper_candidate`.

Proves the NEW real preparation path, under the Owner's own `CFG-089-PAPER` and real
live-shaped Alpaca evidence, is genuinely different from M088's `prepare_paper_candidate`
(synthetic `CFG-088-PAPER` safety-input quote): it reads the live quote/account/asset/bar
evidence it is handed, refuses cleanly with nothing persisted when any gate fails, and is
NOT day-idempotent -- a fresh click must reach a fresh market-priced proposal.

Everything here runs against IN-MEMORY fakes (`_m085_fakes.py`, `_m086_fakes.py`) -- no
PostgreSQL, no network. Nothing in this file can reach the real Alpaca paper endpoint.
"""

from __future__ import annotations

import time as _time
from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
from decimal import Decimal

import pytest
from tests.unit._m085_fakes import FakeBar, FakeBroker, FakeMarketData, FakeTimeBases
from tests.unit._m086_fakes import (
    MemoryConfigurations,
    MemoryContexts,
    MemoryProposals,
    MemoryWatermarks,
)
from tests.unit.test_m084_domain_core import a_configuration

from empirical_platform.shared.brokerage.paper_time import SystemPaperTimeSource
from empirical_platform.usecases.paper_operator_console import (
    V1_CONFIGURATION_ID,
    V1PaperCandidateRefusedError,
    prepare_v1_paper_candidate,
)

_NO_CONFIGURATION_OVERRIDE = object()


def _now() -> datetime:
    # Mirrors test_m088_paper_operator_console.py's own reasoning: FakeBroker.fetch_clock()
    # answers real wall-clock time by M085 design, so the fixtures below must track real
    # time too, or the (real, unweakened) chronology/session guards correctly refuse.
    return datetime.now(UTC)


@dataclass
class _LiveQuote:
    symbol: str = "AAPL"
    bid: str = "332.74"
    ask: str = "332.78"
    captured_at: datetime | None = None
    source: str = "alpaca-iex"

    def __post_init__(self) -> None:
        if self.captured_at is None:
            self.captured_at = _now() - timedelta(seconds=2)


@dataclass
class _WideSpreadQuote:
    """A real-shaped quote whose spread (~0.37%) exceeds a 0.10% ceiling on purpose."""

    symbol: str = "AAPL"
    bid: str = "332.06"
    ask: str = "333.30"
    captured_at: datetime | None = None
    source: str = "alpaca-iex"

    def __post_init__(self) -> None:
        if self.captured_at is None:
            self.captured_at = _now() - timedelta(seconds=2)


@dataclass
class _Clock:
    is_open: bool
    timestamp: datetime | None = None
    next_open: datetime | None = None
    next_close: datetime | None = None

    def __post_init__(self) -> None:
        now = _now()
        if self.timestamp is None:
            self.timestamp = now
        if self.next_open is None:
            far = timedelta(hours=10) if not self.is_open else timedelta(hours=20)
            self.next_open = now + far
        if self.next_close is None:
            recent = -timedelta(hours=2) if not self.is_open else timedelta(hours=2)
            self.next_close = now + recent


def _open_broker(clock: object | None = None) -> FakeBroker:
    broker = FakeBroker()
    resolved = clock or _Clock(is_open=True)
    broker.fetch_clock = lambda: resolved  # type: ignore[method-assign]
    return broker


def _v1_configuration(**overrides: object) -> object:
    defaults: dict[str, object] = dict(
        configuration_governance_id=V1_CONFIGURATION_ID,
        configuration_version=1,
        watchlist=("AAPL",),
        risk_contract_version=2,
        maximum_position_quantity_shares=1,
        maximum_planned_loss_per_trade=Decimal("5"),
        maximum_deployable_capital=Decimal("500"),
        maximum_capital_per_trade=Decimal("500"),
        maximum_percent_per_trade=Decimal("100"),
        minimum_cash_reserve=Decimal("0"),
        maximum_simultaneous_positions=1,
        maximum_daily_order_count=1,
        maximum_spread_percent=Decimal("0.50"),
        maximum_estimated_slippage_percent=Decimal("0.10"),
        # Mirrors the real CFG-089-PAPER percentages: at the fixed $332.78 test ask, a 2%
        # stop (the generic `a_configuration` default) would itself exceed the $5 planned-
        # loss cap below and refuse every "should succeed" test for the wrong reason.
        stop_loss_percent=Decimal("1"),
        profit_exit_percent=Decimal("2"),
        # Wide, fixed, naive entry/liquidation bounds -- a unit test must not depend on
        # which hour it happens to run in any particular timezone (the real CFG-089-PAPER
        # configuration's own 09:35-15:30 America/New_York window is exercised separately,
        # by the real preflight/acceptance work, not by this fast in-memory suite).
        earliest_entry_time=time(0, 1),
        latest_entry_time=time(23, 58),
        mandatory_liquidation_time=time(23, 59),
        operator_timezone="UTC",
        proposal_expiry_seconds=120,
        approval_expiry_seconds=60,
    )
    defaults.update(overrides)
    return a_configuration(**defaults)


def _repositories(configuration: object = _NO_CONFIGURATION_OVERRIDE) -> tuple:
    configurations = MemoryConfigurations()
    configurations.save(  # type: ignore[arg-type]
        _v1_configuration() if configuration is _NO_CONFIGURATION_OVERRIDE else configuration
    )
    return configurations, MemoryContexts(), MemoryProposals()


def _prepare(
    *,
    configuration: object = _NO_CONFIGURATION_OVERRIDE,
    broker: FakeBroker | None = None,
    market_data: FakeMarketData | None = None,
    now: datetime | None = None,
) -> tuple:
    configurations, contexts, proposals = _repositories(configuration)
    resolved_market_data = market_data or FakeMarketData(quote=_LiveQuote())
    result = prepare_v1_paper_candidate(
        configurations=configurations,
        contexts=contexts,
        proposals=proposals,
        watermarks=MemoryWatermarks(),
        time_bases=FakeTimeBases(),
        broker=broker or _open_broker(),
        market_data=resolved_market_data,
        bars=resolved_market_data,
        time_source=SystemPaperTimeSource(),
        now=now or _now(),
    )
    return result, configurations, contexts, proposals


class TestRealPreparationPath:
    def test_prepares_under_the_owners_real_configuration_with_live_evidence(self) -> None:
        result, _configurations, _contexts, proposals = _prepare()
        assert result.proposal.configuration_governance_id == V1_CONFIGURATION_ID
        assert result.proposal.symbol == "AAPL"
        assert result.proposal.status.value == "PREPARED"
        assert result.quote_bid == Decimal("332.74")
        assert result.quote_ask == Decimal("332.78")
        assert proposals.get(result.proposal.proposal_governance_id) is result.proposal

    def test_the_synthetic_m088_path_is_never_used_by_the_v1_function(self) -> None:
        """CFG-088-PAPER's own synthetic acceptance quote never appears here: the v1 path
        reads the real fakes' quote (332.78), nowhere near M088's fixed $4.00 limit."""
        result, *_ = _prepare()
        assert result.proposal.limit_price == Decimal("332.78")
        assert result.proposal.configuration_governance_id != "CFG-088-PAPER"

    def test_is_not_day_idempotent_two_calls_produce_two_fresh_proposals(self) -> None:
        configurations, contexts, proposals = _repositories()
        watermarks = MemoryWatermarks()
        broker, market_data = _open_broker(), FakeMarketData(quote=_LiveQuote())

        def _call() -> object:
            return prepare_v1_paper_candidate(
                configurations=configurations,
                contexts=contexts,
                proposals=proposals,
                watermarks=watermarks,
                time_bases=FakeTimeBases(),
                broker=broker,
                market_data=market_data,
                bars=market_data,
                time_source=SystemPaperTimeSource(),
                now=_now(),
            )

        first = _call()
        _time.sleep(1.05)  # a real, if tiny, advance -- the governance id carries whole seconds
        second = _call()
        assert first.proposal.proposal_governance_id != second.proposal.proposal_governance_id
        assert len(proposals.rows) == 2


class TestRefusalsWriteNothing:
    def test_missing_configuration_refuses_before_anything_is_written(self) -> None:
        configurations = MemoryConfigurations()  # CFG-089-PAPER deliberately absent
        contexts = MemoryContexts()
        proposals = MemoryProposals()
        with pytest.raises(V1PaperCandidateRefusedError, match="no Owner configuration"):
            prepare_v1_paper_candidate(
                configurations=configurations,
                contexts=contexts,
                proposals=proposals,
                watermarks=MemoryWatermarks(),
                time_bases=FakeTimeBases(),
                broker=_open_broker(),
                market_data=FakeMarketData(quote=_LiveQuote()),
                bars=FakeMarketData(quote=_LiveQuote()),
                time_source=SystemPaperTimeSource(),
                now=_now(),
            )
        assert proposals.rows == {}
        assert contexts.rows == {}

    def test_a_legacy_risk_v1_configuration_is_refused_not_silently_accepted(self) -> None:
        # A v1 policy cannot itself carry quantity/loss limits (a real, unrelated domain
        # rule -- `OperatorTradingConfiguration.__post_init__` refuses to construct one that
        # does), so both must be cleared to actually build the historical shape under test.
        legacy = _v1_configuration(
            risk_contract_version=1,
            maximum_position_quantity_shares=None,
            maximum_planned_loss_per_trade=None,
        )
        with pytest.raises(V1PaperCandidateRefusedError, match="risk contract v2"):
            _prepare(configuration=legacy)

    def test_a_closed_market_refuses_and_persists_nothing(self) -> None:
        configurations, contexts, proposals = _repositories()
        with pytest.raises(V1PaperCandidateRefusedError, match="market is closed"):
            prepare_v1_paper_candidate(
                configurations=configurations,
                contexts=contexts,
                proposals=proposals,
                watermarks=MemoryWatermarks(),
                time_bases=FakeTimeBases(),
                broker=_open_broker(clock=_Clock(is_open=False)),
                market_data=FakeMarketData(quote=_LiveQuote()),
                bars=FakeMarketData(quote=_LiveQuote()),
                time_source=SystemPaperTimeSource(),
                now=_now(),
            )
        assert proposals.rows == {}
        assert contexts.rows == {}

    def test_excessive_spread_is_refused_by_the_real_engine_never_relaxed(self) -> None:
        """The exact production gate: 0.10% ceiling, real spread evaluated honestly.

        Only the PROPOSAL stays unwritten here -- exactly M084's own NO_TRADE contract
        ("persisting a row for every refusal would fill the proposal table with things
        nobody proposed"). The evaluation context this was judged against is a real,
        already-measured evidence record and is kept, same as every M084/M085 NO_TRADE.
        """
        configurations, contexts, proposals = _repositories()
        with pytest.raises(V1PaperCandidateRefusedError, match="SLIPPAGE_TOO_HIGH"):
            prepare_v1_paper_candidate(
                configurations=configurations,
                contexts=contexts,
                proposals=proposals,
                watermarks=MemoryWatermarks(),
                time_bases=FakeTimeBases(),
                broker=_open_broker(),
                market_data=FakeMarketData(quote=_WideSpreadQuote()),
                bars=FakeMarketData(quote=_WideSpreadQuote()),
                time_source=SystemPaperTimeSource(),
                now=_now(),
            )
        assert proposals.rows == {}

    def test_a_watchlist_of_more_than_one_symbol_refuses_the_one_candidate_action(self) -> None:
        with pytest.raises(V1PaperCandidateRefusedError, match="exactly one"):
            _prepare(configuration=_v1_configuration(watchlist=("AAPL", "MSFT")))

    def test_an_untradable_asset_is_refused(self) -> None:
        class _Untradable:
            symbol = "AAPL"
            status = "inactive"
            tradable = False
            asset_class = "us_equity"
            exchange = "NASDAQ"
            fractionable = True

        broker = _open_broker()
        broker.fetch_asset = lambda symbol: _Untradable()  # type: ignore[method-assign]
        with pytest.raises(V1PaperCandidateRefusedError, match="not currently tradable"):
            _prepare(broker=broker)

    def test_no_liquidity_evidence_is_refused(self) -> None:
        # First `fetch_minute_bars` call (recent window, for last-trade) sees a real bar;
        # the second (previous session, for liquidity) sees none -- proving the liquidity
        # gate is evaluated on its OWN evidence, not accidentally satisfied by the first.
        market_data = FakeMarketData(quote=_LiveQuote(), bars_sequence=[(FakeBar(),), ()])
        with pytest.raises(V1PaperCandidateRefusedError, match="no liquidity evidence"):
            _prepare(market_data=market_data)


class TestPrepareButtonStaysAvailableAllDay:
    """RELEASE v1 regression: the old M088 Today template only showed the Prepare button
    when the opportunities list was completely EMPTY. That made it impossible to prepare a
    second, fresh candidate once any proposal existed for today -- exactly what today's real
    in-console acceptance work needed to do repeatedly (expired/refused candidates are
    historical cards, not reasons to stop). The button must now appear alongside cards too.
    """

    def _a_card(self) -> object:
        from empirical_platform.usecases.operator_console import (
            HumanState,
            OpportunityCard,
            TermsView,
        )

        terms = TermsView(
            symbol="AAPL",
            side="BUY",
            quantity=1,
            order_type="LIMIT",
            limit_price="332.78",
            time_in_force="DAY",
            extended_hours="No",
            currency="USD",
            notional="332.78",
            fingerprint_short="abc123def456",
        )
        return OpportunityCard(
            proposal_id="PRP-089-PAPER-TEST",
            proposal_version=1,
            symbol="AAPL",
            terms=terms,
            maximum_capital="500.00",
            stop_price="329.45",
            target_price="339.44",
            risk_amount="3.33",
            risk_percent="1.00%",
            target_gain="6.66",
            reward_risk_ratio="2.00:1",
            mandatory_exit=_now(),
            reason="Proposed by strategy TEST: 25 of 25 risk checks passed",
            evidence=(),
            created_at=_now(),
            expires_at=_now() + timedelta(minutes=2),
            state=HumanState.EXPIRED,
            decision_available=False,
            blocked_note=None,
            attention_note=None,
            intent_id=None,
            execution=None,
            scenario=None,
        )

    def test_the_prepare_form_is_present_even_with_a_card_already_on_today(self) -> None:
        from empirical_platform.entrypoints._operator_console_html import today_page
        from empirical_platform.usecases.operator_console import (
            CapabilityStatus,
            ExecutionCapability,
            TodayView,
        )

        view = TodayView(
            session_date=_now().date().isoformat(),
            generated_at=_now(),
            system_status="Operating",
            market_status="Open",
            kill_switch_engaged=False,
            capability=CapabilityStatus(ExecutionCapability.PAPER, True, "Paper", "note"),
            opportunities=(self._a_card(),),
            needs_action_count=0,
            active_positions_count=0,
            active_executions_count=0,
            open_opportunities_count=0,
        )
        page = today_page(view, "csrf-token")
        assert 'action="/prepare-candidate"' in page
        assert "Prepare a fresh Paper candidate" in page
