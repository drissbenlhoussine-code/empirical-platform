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
from empirical_platform.shared.brokerage.simulation_paper import SimulationStateLockedError
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
    (held,) = a.service.active_trades()  # the filled entry is an open position, exit locked
    assert held.position_open and "M087" in held.exit_status
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
    a.close()  # the first process ends and releases the state-directory lock

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
    # The restarted process shows both as OPEN POSITIONS (exit locked), from durable rows only.
    held = {row.symbol: row for row in b.service.active_trades()}
    assert held["KO"].position_open and held["KO"].state is HumanState.FILLED
    assert held["MSFT"].position_open and held["MSFT"].state is HumanState.PARTIALLY_FILLED
    assert "M087" in held["KO"].exit_status and not held["KO"].can_cancel
    b.close()  # the lock is exclusive: the second restart can only begin once b has stopped
    c = world["process"]("c")  # and again after a second restart, without any refresh
    assert {row.symbol for row in c.service.active_trades() if row.position_open} == {"KO", "MSFT"}
    c.close()
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


def test_a_second_console_on_the_same_state_dir_is_refused_before_touching_state(
    world: dict[str, Any],
) -> None:
    a = world["process"]("a")
    a.load_day()
    store_bytes = a.store.path.read_bytes()
    service = PostgresPersistenceService(config("m086-console-second"))
    service.initialize()
    try:
        with pytest.raises(SimulationStateLockedError):
            compose_operator_console(
                ExecutionCapability.SIMULATION,
                service=service,
                state_dir=world["state_dir"],
                clock=world["clock"],
                time_source=world["clock"],
            )
        assert a.store.path.read_bytes() == store_bytes  # nothing was read into a second store
        assert a.state_lock is not None and a.state_lock.held
        a.close()  # the first console stops: the lock is released ...
        # BUG FIX (not production logic): this composition was missing clock=/time_source=,
        # so it silently fell back to compose_operator_console's real-wall-clock default
        # while "a" wrote its proposals against `world["clock"]`, a frozen simulated clock
        # fixed at a literal 2026-09-28 instant. Once enough real time has passed since that
        # literal date, the proposals' expires_at (created_at + 1h) looks passed to a console
        # reading real time, and needs_action_count silently drops to 0 -- a test bug, not a
        # production one: this is the SAME clock "a" used, restated for the second process
        # exactly as a real restart would supply it (the launcher passes one real clock to
        # every composition in a process lifetime; two consoles in a lifetime never see two
        # different clocks). Nothing about proposal.expired_at() or any expiry computation
        # changed.
        second = compose_operator_console(
            ExecutionCapability.SIMULATION,
            service=service,
            state_dir=world["state_dir"],
            clock=world["clock"],
            time_source=world["clock"],
        )
        try:
            assert second.service.today().needs_action_count == 12  # ... and the state is intact
        finally:
            second.close()
    finally:
        service.close()


def test_a_second_launcher_process_is_refused_with_exit_code_2(world: dict[str, Any]) -> None:
    """Real subprocesses: the first launcher holds the state directory; a second is refused."""
    import os
    import subprocess
    import sys
    import time
    from pathlib import Path

    environment = dict(os.environ)
    environment["PYTHONUNBUFFERED"] = "1"
    state_dir = Path(world["state_dir"]) / "launcher"
    argv = [
        sys.executable,
        "-m",
        "empirical_platform.entrypoints.operator_console",
        "--no-browser",
        "--state-dir",
        str(state_dir),
        "--reconcile-every",
        "0",
    ]
    first = subprocess.Popen(  # noqa: S603 - fixed argv, no shell
        [*argv, "--port", "8099"],
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    try:
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline and not (state_dir / "console.lock").exists():
            if first.poll() is not None:
                output = first.stdout.read() if first.stdout else ""
                raise AssertionError(f"first console exited early: {output}")
            time.sleep(0.2)
        assert (state_dir / "console.lock").exists()
        time.sleep(1.0)
        second = subprocess.run(  # noqa: S603 - fixed argv, no shell
            [*argv, "--port", "8098"],
            env=environment,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        assert second.returncode == 2, second.stderr
        assert "REFUSED" in second.stderr
        assert "already owns the simulation state directory" in second.stderr
        assert "OPERATOR CONSOLE" not in second.stdout  # it never got as far as serving
        assert first.poll() is None  # the first one is unaffected
    finally:
        first.terminate()
        try:
            first.wait(timeout=30)
        except subprocess.TimeoutExpired:
            first.kill()
