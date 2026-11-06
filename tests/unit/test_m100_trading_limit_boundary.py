"""M100 D1 -- the trading limits are enforced at the broker submission boundary.

Everything runs over the REAL simulation broker and the REAL submit handler; nothing here talks to
a network. Each test drives ``confirm_approval`` (prepare -> approve -> authorize -> submit) and
asserts on what the SIMULATED BROKER actually received: a refused entry must leave no order behind.

The simulation configuration's limits (``simulation_configuration``): daily loss 1000, daily orders
20, simultaneous positions 12, deployable capital 100000. No threshold is invented in this file.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from pathlib import Path

import pytest
from tests.unit._m086_fakes import World, simulation_world

from empirical_platform.decision_candidate.trading_limit_gate import PortfolioRiskEvidence
from empirical_platform.shared.brokerage.simulation_paper import (
    SimulatedOrder,
    default_exit_scenario_table,
    default_scenario_table,
)
from empirical_platform.usecases.operator_console import ActionOutcome, ConsoleRefusalError
from empirical_platform.usecases.operator_console_fixtures import SIMULATION_QUOTES
from empirical_platform.usecases.paper_execution import PaperExecutionRefusedError


@pytest.fixture
def world(tmp_path: Path) -> World:
    return simulation_world(tmp_path, exits=True)


Refusal = ConsoleRefusalError | PaperExecutionRefusedError


def _try_enter(world: World, symbol: str = "AAPL") -> ActionOutcome | Refusal:
    proposal = world.proposal_id(symbol)
    view = world.service.prepare_approval(proposal)
    try:
        return world.service.confirm_approval(proposal, view.ticket)
    except (ConsoleRefusalError, PaperExecutionRefusedError) as refusal:
        return refusal


def _sent(result: ActionOutcome | Refusal) -> bool:
    return isinstance(result, ActionOutcome) and result.sent == "sent"


def _text(result: ActionOutcome | Refusal) -> str:
    return str(result.message) if isinstance(result, ActionOutcome) else str(result)


def _orders(world: World) -> int:
    return len(world.store.orders())


def _holdings(count: int) -> list[str]:
    """Synthetic symbols for background positions (the staged day only lists twelve real ones)."""
    return [f"HLD{index:02d}" for index in range(count)]


def _stage_with_extra_quotes(world: World, symbols: tuple[str, ...], *extra: str) -> None:
    """Re-stage the day so positions in `extra` symbols can be priced from a quote."""
    scenarios = default_scenario_table()
    exits = default_exit_scenario_table()
    quotes = {s: SIMULATION_QUOTES[s] for s in symbols}
    quotes.update({s: SIMULATION_QUOTES.get(s, ("10.00", "10.10")) for s in extra})
    world.store.stage(
        scenarios={s: scenarios[s] for s in symbols},
        quotes=quotes,
        exit_scenarios={s: exits[s] for s in symbols},
    )


def _filler_order(index: int, *, status: str = "rejected", symbol: str = "AAPL") -> SimulatedOrder:
    return SimulatedOrder(
        broker_order_id=f"sim-fill-{index:04d}",
        client_order_id=f"filler-{index:04d}",
        symbol=symbol,
        side="buy",
        quantity="1",
        order_type="limit",
        limit_price="1.00",
        time_in_force="day",
        extended_hours=False,
        status=status,
        filled_quantity="0",
        filled_avg_price=None,
        scenario="FILLER",
        lookups=0,
        cancel_requested=False,
        received_at="2026-09-28T13:00:00+00:00",
    )


# ---------------------------------------------------------------------------------------------
# Baseline and the daily-loss limit
# ---------------------------------------------------------------------------------------------


def test_baseline_entry_within_every_limit_is_sent(world: World) -> None:
    world.load_day(("AAPL",))
    assert _sent(_try_enter(world))
    assert _orders(world) == 1


def test_a_realized_loss_at_the_daily_limit_blocks_the_entry_and_sends_nothing(
    world: World,
) -> None:
    world.load_day(("AAPL",))
    world.store.stage_day_pnl(realized="-1000", whole_day="-1000")
    result = _try_enter(world)
    assert not _sent(result)
    assert "daily loss limit" in _text(result)
    assert _orders(world) == 0


def test_a_realized_loss_one_cent_under_the_limit_still_allows_the_entry(world: World) -> None:
    world.load_day(("AAPL",))
    world.store.stage_day_pnl(realized="-999.99", whole_day="-999.99")
    assert _sent(_try_enter(world))


def test_an_unrealized_drawdown_that_reaches_the_limit_blocks_even_if_realized_is_flat(
    world: World,
) -> None:
    """The gate reads the WORSE of realized and whole-day P&L, so floating gains cannot hide it."""
    world.load_day(("AAPL",))
    world.store.stage_day_pnl(realized="0", whole_day="-1000")
    result = _try_enter(world)
    assert not _sent(result)
    assert _orders(world) == 0


def test_a_realized_loss_masked_by_floating_gains_still_blocks(world: World) -> None:
    world.load_day(("AAPL",))
    world.store.stage_day_pnl(realized="-1500", whole_day="+200")
    assert not _sent(_try_enter(world))
    assert _orders(world) == 0


# ---------------------------------------------------------------------------------------------
# Daily order count
# ---------------------------------------------------------------------------------------------


def test_the_daily_order_count_counts_rejected_orders_too(world: World) -> None:
    world.load_day(("AAPL",))
    for index in range(20):
        world.store.put(_filler_order(index, status="rejected", symbol="MSFT"))
    result = _try_enter(world)
    assert not _sent(result)
    assert "daily limit is 20" in _text(result)
    assert _orders(world) == 20  # only the fillers; the refused entry created nothing


def test_one_order_below_the_daily_count_is_allowed(world: World) -> None:
    world.load_day(("AAPL",))
    for index in range(19):
        world.store.put(_filler_order(index, status="canceled", symbol="MSFT"))
    assert _sent(_try_enter(world))


# ---------------------------------------------------------------------------------------------
# Simultaneous positions, conflicts and exposure
# ---------------------------------------------------------------------------------------------


def test_the_simultaneous_position_limit_counts_every_symbol_not_only_the_target(
    world: World,
) -> None:
    world.load_day(("AAPL",))
    held = _holdings(12)
    _stage_with_extra_quotes(world, ("AAPL",), *held)
    for symbol in held:
        world.store.add_position(symbol, 1)
    result = _try_enter(world)
    assert not _sent(result)
    assert "simultaneous positions" in _text(result)
    assert _orders(world) == 0


def test_eleven_other_positions_leave_exactly_one_slot(world: World) -> None:
    world.load_day(("AAPL",))
    held = _holdings(11)
    _stage_with_extra_quotes(world, ("AAPL",), *held)
    for symbol in held:
        world.store.add_position(symbol, 1)
    assert _sent(_try_enter(world))


def test_an_existing_position_in_the_same_symbol_blocks_the_entry(world: World) -> None:
    world.load_day(("AAPL",))
    world.store.add_position("AAPL", 1)
    result = _try_enter(world)
    assert not _sent(result)
    assert _orders(world) == 0


def test_a_working_order_in_the_same_symbol_blocks_the_entry(world: World) -> None:
    world.load_day(("AAPL",))
    world.store.put(_filler_order(1, status="accepted", symbol="AAPL"))
    result = _try_enter(world)
    assert not _sent(result)
    assert _orders(world) == 1


def test_a_working_order_in_another_symbol_occupies_a_position_slot(world: World) -> None:
    world.load_day(("AAPL",))
    held = _holdings(11)
    _stage_with_extra_quotes(world, ("AAPL",), *held)
    for symbol in held[:10]:
        world.store.add_position(symbol, 1)
    world.store.put(_filler_order(7, status="new", symbol=held[10]))  # 11 occupied
    world.store.put(_filler_order(8, status="new", symbol="V"))  # 12 occupied -> no slot left
    assert not _sent(_try_enter(world))


def test_total_exposure_above_deployable_capital_blocks_the_entry(world: World) -> None:
    world.load_day(("AAPL",))
    _stage_with_extra_quotes(world, ("AAPL",), "META")
    world.store.add_position("META", 195)  # 195 x 512.70 = 99 976.50 of the 100 000 deployable
    result = _try_enter(world)
    assert not _sent(result)
    assert "deployable capital" in _text(result)
    assert _orders(world) == 0


# ---------------------------------------------------------------------------------------------
# Fail-closed evidence handling
# ---------------------------------------------------------------------------------------------


def test_unreadable_risk_evidence_blocks_the_entry(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    world.load_day(("AAPL",))

    def _boom(*, day_start: datetime) -> PortfolioRiskEvidence:
        raise ConnectionError("broker unreachable")

    monkeypatch.setattr(world.broker, "fetch_portfolio_risk_evidence", _boom)
    result = _try_enter(world)
    assert not _sent(result)
    assert _orders(world) == 0


def test_stale_risk_evidence_blocks_the_entry(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    world.load_day(("AAPL",))
    real = world.broker.fetch_portfolio_risk_evidence

    def _stale(*, day_start: datetime) -> PortfolioRiskEvidence:
        evidence = real(day_start=day_start)
        return replace(evidence, captured_at=evidence.captured_at.replace(year=2020))

    monkeypatch.setattr(world.broker, "fetch_portfolio_risk_evidence", _stale)
    result = _try_enter(world)
    assert not _sent(result)
    assert _orders(world) == 0


def test_missing_limits_block_new_entries_until_configured(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    world.load_day(("AAPL",))
    from empirical_platform.decision_candidate import trading_limit_gate

    def _missing(cls: object, configuration: object) -> None:
        raise ValueError("maximum_daily_loss must be a positive finite Decimal")

    monkeypatch.setattr(
        trading_limit_gate.TradingLimits, "from_configuration", classmethod(_missing)
    )
    result = _try_enter(world)
    assert not _sent(result)
    assert "stay blocked" in _text(result) or "blocked" in _text(result)
    assert _orders(world) == 0


# ---------------------------------------------------------------------------------------------
# Concurrency, broker lag, retries and restart
# ---------------------------------------------------------------------------------------------


def test_an_entry_claimed_by_another_submitter_counts_even_when_the_broker_does_not_show_it_yet(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two entries race for the last position slot; the broker's list lags behind the claim.

    11 of 12 slots are held. Entry A is sent. The broker evidence is then FROZEN at its pre-A
    state (a lagging broker). Entry B must still be refused, because A's durable claim in the
    attempts store is read at the boundary and de-duplicated against the broker only by identity.
    """
    world.load_day(("AAPL", "MSFT"))
    held = _holdings(11)
    _stage_with_extra_quotes(world, ("AAPL", "MSFT"), *held)
    for symbol in held:
        world.store.add_position(symbol, 1)

    frozen = world.broker.fetch_portfolio_risk_evidence(day_start=world.clock.utc)
    assert _sent(_try_enter(world, "AAPL"))

    monkeypatch.setattr(
        world.broker,
        "fetch_portfolio_risk_evidence",
        lambda *, day_start: replace(frozen, captured_at=world.clock.utc),
    )
    result = _try_enter(world, "MSFT")
    assert not _sent(result)
    assert "simultaneous positions" in _text(result) or "in flight" in _text(result)
    assert not [o for o in world.store.orders() if o.symbol == "MSFT"]


def test_a_retry_after_a_sent_entry_never_sends_a_second_order(world: World) -> None:
    world.load_day(("AAPL",))
    proposal = world.proposal_id("AAPL")
    view = world.service.prepare_approval(proposal)
    first = world.service.confirm_approval(proposal, view.ticket)
    again = world.service.confirm_approval(proposal, view.ticket)
    assert first.sent == "sent"
    assert _orders(world) == 1
    assert isinstance(again, ActionOutcome)


def test_limits_survive_a_restart_because_they_live_in_broker_and_database_state(
    world: World,
) -> None:
    world.load_day(("AAPL",))
    world.store.stage_day_pnl(realized="-1000", whole_day="-1000")
    restarted = world.restart()
    result = _try_enter(restarted)
    assert not _sent(result)
    assert _orders(restarted) == 0


def test_the_post_claim_boundary_alone_refuses_when_the_pre_claim_pass_is_blind(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two entries race for the last slot. The PRE-claim pass is forced to pass for the second
    one (as it would if both ran before either claimed); only the pass inside ``before_send``,
    after the claim, can stop it -- and it must, leaving a provably-unsent NOT_SENT attempt."""
    from empirical_platform.usecases import paper_execution as pe

    world.load_day(("AAPL", "MSFT"))
    held = _holdings(11)
    _stage_with_extra_quotes(world, ("AAPL", "MSFT"), *held)
    for symbol in held:
        world.store.add_position(symbol, 1)
    frozen = world.broker.fetch_portfolio_risk_evidence(day_start=world.clock.utc)
    assert _sent(_try_enter(world, "AAPL"))
    monkeypatch.setattr(
        world.broker,
        "fetch_portfolio_risk_evidence",
        lambda *, day_start: replace(frozen, captured_at=world.clock.utc),
    )
    original = pe.SubmitAuthorizedPaperOrderHandler._enforce_trading_limits

    def _blind_first_pass(self: object, **kwargs: object) -> None:
        if kwargs["exclude_attempt_id"] is None:
            return  # the pre-claim pass sees nothing wrong
        original(self, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(
        pe.SubmitAuthorizedPaperOrderHandler, "_enforce_trading_limits", _blind_first_pass
    )
    proposal = world.proposal_id("MSFT")
    view = world.service.prepare_approval(proposal)
    result = world.service.confirm_approval(proposal, view.ticket)
    assert not _sent(result)
    assert not [o for o in world.store.orders() if o.symbol == "MSFT"]
    intent = world.repositories.intents.for_proposal(proposal)
    attempt = world.repositories.attempts.for_intent(intent.intent_governance_id)
    assert attempt is not None and attempt.failure_code == "NOT_SENT"
