"""MILESTONE-086 -- the Operator Console over real PostgreSQL and the durable simulation store.

Composition is the production composition root; every "restart" is a new persistence
service and a new console over the SAME database and the SAME store file, with a fresh
process secret. Nothing here reaches a network.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.engine import Engine
from tests.integration._m085_support import build_engine, config, truncate_all

from empirical_platform.decision_candidate.paper_execution import PaperExecutionState
from empirical_platform.entrypoints._operator_console_composition import (
    ConsoleRuntime,
    compose_operator_console,
)
from empirical_platform.shared.brokerage.paper_time import PaperTimeReading
from empirical_platform.shared.persistence.postgres import PostgresPersistenceService
from empirical_platform.usecases.operator_console import (
    CapabilityRefusedError,
    ConsoleRefusalError,
    ExecutionCapability,
    HumanState,
)

pytestmark = pytest.mark.integration


class Clock:
    def __init__(self) -> None:
        self.utc = datetime(2026, 9, 28, 14, 0, tzinfo=UTC)
        self.monotonic = 500.0

    def advance(self, seconds: float) -> None:
        self.utc += timedelta(seconds=seconds)
        self.monotonic += seconds

    def read(self) -> PaperTimeReading:
        return PaperTimeReading(self.utc, self.monotonic)

    def __call__(self) -> datetime:
        return self.utc


@pytest.fixture(scope="module")
def engine() -> Iterator[Engine]:
    yield from build_engine()


@pytest.fixture
def world(engine: Engine, tmp_path: Path) -> Iterator[dict[str, Any]]:
    truncate_all(engine)
    clock = Clock()
    services: list[PostgresPersistenceService] = []

    def process(name: str) -> ConsoleRuntime:
        service = PostgresPersistenceService(config(f"m086-console-{name}"))
        service.initialize()
        services.append(service)
        return compose_operator_console(
            ExecutionCapability.SIMULATION,
            service=service,
            state_dir=tmp_path,
            clock=clock,
            time_source=clock,
        )

    try:
        yield {"engine": engine, "clock": clock, "process": process, "state_dir": tmp_path}
    finally:
        for service in services:
            service.close()


def _proposal_id(clock: Clock, symbol: str) -> str:
    return f"PRP-086-{clock.utc.strftime('%Y%m%d')}-{symbol}"


def _approve(runtime: ConsoleRuntime, proposal_id: str) -> Any:  # noqa: ANN401
    view = runtime.service.prepare_approval(proposal_id)
    return runtime.service.confirm_approval(proposal_id, view.ticket)


def test_paper_and_live_cannot_be_composed(world: dict[str, Any]) -> None:
    service = PostgresPersistenceService(config("m086-console-refused"))
    service.initialize()
    try:
        for capability in (ExecutionCapability.PAPER, ExecutionCapability.LIVE):
            with pytest.raises(CapabilityRefusedError):
                compose_operator_console(capability, service=service, state_dir=world["state_dir"])
    finally:
        service.close()


def test_the_daily_scenario_end_to_end_on_postgres(world: dict[str, Any]) -> None:
    a = world["process"]("a")
    report = a.load_day()
    assert len(report.proposed) == 12 and report.refused == ()
    today = a.service.today()
    assert (
        today.needs_action_count == 12
        and today.capability.capability is ExecutionCapability.SIMULATION
    )
    proposal_id = _proposal_id(world["clock"], "AAPL")
    outcome = _approve(a, proposal_id)
    assert outcome.ok and outcome.sent == "sent"
    # The M085 rows are real and consistent: one intent, one consumed authorization, one attempt.
    with world["engine"].begin() as connection:
        attempts = connection.execute(
            text("SELECT state FROM public.paper_execution_attempt")
        ).all()
        authorizations = connection.execute(
            text("SELECT consumed_at IS NOT NULL FROM public.paper_execution_authorization")
        ).all()
        intents = connection.execute(
            text("SELECT count(*) FROM public.approved_order_intent")
        ).scalar_one()
    assert [row[0] for row in attempts] == ["PAPER_ACCEPTED"]
    assert [row[0] for row in authorizations] == [True]
    assert intents == 1
    world["clock"].advance(5)
    a.service.refresh_executions()
    world["clock"].advance(5)
    a.service.refresh_executions()
    execution = a.service.execution(f"INT-{proposal_id}")
    assert execution.state is HumanState.FILLED and execution.is_terminal
    assert a.service.active_trades() == ()
    history = a.service.history(symbol="AAPL")
    assert (
        history[0].final_state is HumanState.FILLED
        and history[0].execution_kind == "Simulation execution"
    )
    # A duplicate confirmation after the fact creates nothing.
    with pytest.raises(ConsoleRefusalError):
        a.service.prepare_approval(proposal_id)
    assert len(a.store.orders()) == 1


def test_restart_after_an_ambiguous_execution_reconstructs_and_resolves(
    world: dict[str, Any],
) -> None:
    a = world["process"]("a")
    a.load_day()
    ko = _proposal_id(world["clock"], "KO")
    msft = _proposal_id(world["clock"], "MSFT")
    unknown = _approve(a, ko)
    assert unknown.sent == "unknown"
    _approve(a, msft)
    view = a.service.prepare_approval(_proposal_id(world["clock"], "NVDA"))  # page left open
    a.service.set_kill_switch(engaged=True, reason="before restart")
    orders_before = len(a.store.orders())

    b = world["process"]("b")  # restarted process: new service, new secret, same database and store
    assert b.service.opportunity(ko).state is HumanState.NEEDS_ATTENTION
    assert b.service.opportunity(msft).state is HumanState.ACCEPTED
    assert b.service.today().kill_switch_engaged is True  # durable, not browser memory
    with pytest.raises(ConsoleRefusalError):
        b.service.confirm_approval(_proposal_id(world["clock"], "NVDA"), view.ticket)  # old page
    assert len(b.service.active_trades()) == 2
    world["clock"].advance(5)
    b.service.refresh_executions()  # a refresh reconciles; it never sends
    assert b.service.opportunity(ko).state is HumanState.ACCEPTED
    world["clock"].advance(5)
    b.service.refresh_executions()
    assert b.service.opportunity(ko).state is HumanState.FILLED
    assert b.service.opportunity(msft).state is HumanState.PARTIALLY_FILLED
    assert len(b.store.orders()) == orders_before
    with world["engine"].begin() as connection:
        rows = connection.execute(
            text(
                "SELECT intent_governance_id, state FROM public.paper_execution_attempt ORDER BY 1"
            )
        ).all()
    assert [(r[0], r[1]) for r in rows] == [
        (f"INT-{ko}", PaperExecutionState.FILLED.value),
        (f"INT-{msft}", PaperExecutionState.PARTIALLY_FILLED.value),
    ]
    b.service.set_kill_switch(engaged=False, reason="")
    assert _approve(b, _proposal_id(world["clock"], "NVDA")).ok


def test_the_absence_policy_and_the_kill_switch_hold_on_postgres(world: dict[str, Any]) -> None:
    a = world["process"]("a")
    a.load_day()
    xom = _proposal_id(world["clock"], "XOM")
    assert _approve(a, xom).sent == "unknown"
    world["clock"].advance(61)
    a.service.refresh_executions()
    assert a.service.opportunity(xom).state is HumanState.NEEDS_ATTENTION
    world["clock"].advance(61)
    a.service.refresh_executions()
    assert a.service.opportunity(xom).state is HumanState.REJECTED
    a.service.set_kill_switch(engaged=True, reason="stop")
    aapl = _proposal_id(world["clock"], "AAPL")
    ticket = a.service.prepare_approval(aapl).ticket
    with pytest.raises(ConsoleRefusalError):
        a.service.confirm_approval(aapl, ticket)
    with world["engine"].begin() as connection:
        count = connection.execute(
            text("SELECT count(*) FROM public.paper_execution_attempt")
        ).scalar_one()
    assert count == 1  # XOM only; the blocked approval wrote no attempt
