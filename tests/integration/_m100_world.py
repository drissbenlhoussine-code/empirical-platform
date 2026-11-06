"""The shared world of the M100 acceptance matrix: real stores, real composition, scripted wire.

Not a test module. `World` assembles, per test:

  * Store A/B (one database, `alembic upgrade head`) and Store C (its own chain, to head), both
    REAL Postgres test databases, emptied between tests;
  * the REAL production composition `paper_operator_console_with_exit_runtime()` -- the exact
    function the deployed console calls -- entered as a "process lifetime" (`World.stack()`);
    leaving the `with` closes every connection and drops every object, so entering it again is a
    genuine restart that can only know what Postgres knows;
  * the REAL `AlpacaPaperClient`/`AlpacaPaperMarketDataClient` it builds, talking to the local
    scripted exchange (`_m100_fake_alpaca`) through the redirected transport;
  * one `VirtualClock` shared by the host time source, the wire's clock and every `now=`.

Only the broker/market-data WIRE is fake. Handlers, repositories, state machines, the console
service, the WSGI routes and the plan manager are the production code.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.engine import Engine
from tests.integration._m085_support import config
from tests.integration._m100_fake_alpaca import (
    FakeAlpacaExchange,
    VirtualClock,
    serve_exchange,
)
from tests.unit.test_m084_domain_core import a_configuration
from tests.unit.test_m086_operator_console_routes import Client, Reply

from empirical_platform.decision_candidate.approved_plan import ApprovedPlan
from empirical_platform.decision_candidate.paper_execution import (
    ExecutionAttempt,
    PaperExecutionState,
)
from empirical_platform.decision_candidate.position_exit import (
    PositionExitAttempt,
    PositionExitState,
)
from empirical_platform.entrypoints._operator_console_web import SecuritySession
from empirical_platform.entrypoints._paper_operator_console_composition import PaperConsoleBackend
from empirical_platform.entrypoints._paper_position_exit_composition import (
    paper_operator_console_with_exit_runtime,
)
from empirical_platform.entrypoints.paper_operator_console_app import build_paper_application
from empirical_platform.shared.brokerage import paper_time
from empirical_platform.shared.persistence.postgres import PostgresPersistenceService
from empirical_platform.shared.persistence.postgres_repositories.runtime import (
    PostgresRepositoryRuntime,
)
from empirical_platform.usecases.paper_operator_console import (
    V1_CONFIGURATION_ID,
    V1PreparedCandidate,
    prepare_v1_paper_candidate,
)
from empirical_platform.usecases.position_plan_manager import PlanEvaluationOutcome

SYMBOL = "AAPL"


def v1_configuration(**overrides: Any) -> Any:
    """The Owner's `CFG-089-PAPER`, risk contract v2, shaped for the acceptance scenario.

    Quantity cap 4 (so a partial fill is possible), a $10 planned-loss cap, a 1% stop and a 2%
    target. The entry window spans the operator's day and the operator timezone is placed so
    that "now" reads mid-morning (the same device `_default_configuration` uses), so the real
    chronology rules neither fire nor are weakened.
    """
    from empirical_platform.usecases.operator_console_fixtures import simulation_timezone_for

    now = paper_time.SystemPaperTimeSource().read().utc
    from datetime import time as clock_time

    defaults: dict[str, Any] = dict(
        configuration_governance_id=V1_CONFIGURATION_ID,
        configuration_version=1,
        watchlist=(SYMBOL,),
        risk_contract_version=2,
        maximum_position_quantity_shares=4,
        maximum_planned_loss_per_trade=Decimal("10"),
        maximum_deployable_capital=Decimal("2000"),
        maximum_capital_per_trade=Decimal("500"),
        maximum_percent_per_trade=Decimal("100"),
        minimum_cash_reserve=Decimal("0"),
        maximum_simultaneous_positions=2,
        maximum_daily_order_count=5,
        maximum_daily_loss=Decimal("500"),
        maximum_spread_percent=Decimal("0.50"),
        maximum_estimated_slippage_percent=Decimal("0.50"),
        stop_loss_percent=Decimal("1"),
        profit_exit_percent=Decimal("2"),
        earliest_entry_time=clock_time(0, 1),
        latest_entry_time=clock_time(23, 58),
        mandatory_liquidation_time=clock_time(23, 59),
        operator_timezone=simulation_timezone_for(now),
        proposal_expiry_seconds=3600,
        approval_expiry_seconds=1800,
        minimum_price=Decimal("1"),
        maximum_price=Decimal("1000"),
        minimum_liquidity_shares=100_000,
        maximum_market_data_age_seconds=60,
        permitted_order_types=(a_configuration().default_order_type,),
    )
    defaults.update(overrides)
    return a_configuration(**defaults)


_STORE_B_TABLES_SQL = (
    "SELECT tablename FROM pg_tables WHERE schemaname = 'public' AND tablename <> 'alembic_version'"
)


def empty_database(engine: Engine) -> None:
    """TRUNCATE every table except the migration marker, so the schema is built once."""
    with engine.begin() as connection:
        tables = [row[0] for row in connection.execute(text(_STORE_B_TABLES_SQL)).all()]
        if tables:
            connection.execute(text("TRUNCATE " + ", ".join(f'public."{t}"' for t in tables)))


@dataclass
class Stack:
    """One 'process lifetime': the real composition, plus a browser-like WSGI client."""

    world: World
    backend: PaperConsoleBackend
    client: Client
    #: The confirmation ticket the Owner was shown for each proposal (a browser keeps it in the
    #: page); re-submitting it is how a blocked approval is resumed.
    tickets: dict[str, tuple[str, str]] = field(default_factory=dict)

    @property
    def service(self) -> Any:
        return self.backend.service

    @property
    def repositories(self) -> Any:
        return self.backend._repositories  # noqa: SLF001

    @property
    def exits(self) -> Any:
        return self.backend._exits  # noqa: SLF001

    @property
    def plans(self) -> Any:
        return self.backend._plans  # noqa: SLF001

    @property
    def manager(self) -> Any:
        return self.backend._plan_manager  # noqa: SLF001

    # -- the production steps, driven the way the Owner / the manager drive them -----------

    def prepare(self) -> V1PreparedCandidate:
        """Step 3 -- `prepare_v1_paper_candidate`, on the stack's REAL repositories/clients.

        The virtual clock moves 1.1 s first: the proposal/context ids carry whole seconds, and
        a refused earlier prepare in the same second has already written its context row.
        """
        self.world.clock.advance(1.1)
        return prepare_v1_paper_candidate(
            configurations=self.repositories.configurations,
            contexts=self.repositories.contexts,
            proposals=self.repositories.proposals,
            watermarks=self.backend._watermarks,  # noqa: SLF001
            time_bases=self.repositories.time_bases,
            broker=self.backend._broker,  # noqa: SLF001
            market_data=self.backend._market_data,  # noqa: SLF001
            bars=self.backend._market_data,  # noqa: SLF001
            attempts=self.repositories.attempts,
            time_source=self.backend._time_source,  # noqa: SLF001
            now=self.world.clock.now(),
        )

    def review_page(self, proposal_id: str, action: str = "APPROVE") -> Reply:
        return self.client.get(f"/confirm?action={action}&proposal={proposal_id}")

    def ticket_of(self, page: Reply) -> tuple[str, str]:
        ticket = re.search(r'name="ticket" value="([^"]+)"', page.body)
        csrf = re.search(r'name="csrf_token" value="([^"]+)"', page.body)
        assert ticket and csrf, page.body[:400]
        return ticket.group(1), csrf.group(1)

    def approve_via_route(self, proposal_id: str, *, resume: bool = False) -> Reply:
        """Owner approval, as the browser does it: GET /confirm, then POST /confirm-approval.

        `resume=True` re-submits the ticket already shown (the review page refuses a proposal
        that is no longer PREPARED, so a blocked approval can only be resumed that way).
        """
        if resume:
            ticket, csrf = self.tickets[proposal_id]
        else:
            page = self.review_page(proposal_id)
            assert page.code == 200, page.body[:300]
            ticket, csrf = self.ticket_of(page)
            self.tickets[proposal_id] = (ticket, csrf)
        return self.client.post(
            "/confirm-approval",
            {"proposal": proposal_id, "ticket": ticket, "csrf_token": csrf},
        )

    def entry_attempt(self, proposal_id: str) -> ExecutionAttempt | None:
        intent = self.repositories.intents.for_proposal(proposal_id)
        return (
            None
            if intent is None
            else self.repositories.attempts.for_intent(intent.intent_governance_id)
        )

    def plan_for(self, proposal_id: str) -> ApprovedPlan | None:
        intent = self.repositories.intents.for_proposal(proposal_id)
        return None if intent is None else self.plans.for_entry(intent.intent_governance_id)

    def refresh(self) -> tuple[str, ...]:
        """The Owner's 'Check with the broker' action: reconcile every open execution."""
        return self.service.refresh_executions()

    def tick(self) -> tuple[PlanEvaluationOutcome, ...]:
        """One plan-manager poll at the virtual 'now' (exactly what PlanManagerThread does)."""
        assert self.manager is not None
        return self.manager.evaluate_once(now=self.world.clock.now())

    def exit_attempts(self, intent_id: str) -> list[PositionExitAttempt]:
        return list(self.exits.attempts.for_entry(intent_id))


class World:
    def __init__(
        self,
        engine_b: Engine,
        engine_c: Engine,
        exchange: FakeAlpacaExchange,
        clock: VirtualClock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        self.engine_b = engine_b
        self.engine_c = engine_c
        self.exchange = exchange
        self.clock = clock
        self.monkeypatch = monkeypatch

    def save_configuration(self, configuration: Any) -> None:
        service = PostgresPersistenceService(config())
        service.initialize()
        try:
            PostgresRepositoryRuntime(service).operator_trading_configurations.save(configuration)
        finally:
            service.close()

    @contextmanager
    def stack(self) -> Iterator[Stack]:
        with paper_operator_console_with_exit_runtime() as backend:
            # The service and the exit console default to the REAL wall clock; hand them the
            # shared virtual one so every deadline in the scenario is judged on one timeline.
            backend.service._clock = self.clock.now  # noqa: SLF001
            if backend.service.exits is not None:
                backend.service.exits._clock = self.clock.now  # noqa: SLF001
            app = build_paper_application(backend, security=SecuritySession())
            yield Stack(self, backend, Client(app))

    # -- a position, the long way round -------------------------------------------------

    def enter_position(
        self, stack: Stack, *, fill: int | None = None, price: str = "100.00"
    ) -> tuple[str, str, int]:
        """prepare -> Owner approval (route) -> broker accepts -> fill -> reconcile.

        Returns (proposal_id, intent_id, quantity). `fill=None` fills the whole order.
        """
        prepared = stack.prepare()
        proposal_id = prepared.proposal.proposal_governance_id
        reply = stack.approve_via_route(proposal_id)
        assert reply.code == 303, reply.body[:500]
        attempt = stack.entry_attempt(proposal_id)
        assert attempt is not None and attempt.state is PaperExecutionState.PAPER_ACCEPTED, attempt
        quantity = int(prepared.proposal.quantity)
        self.exchange.fill(attempt.client_order_id, quantity if fill is None else fill, price)
        stack.refresh()
        intent = stack.repositories.intents.for_proposal(proposal_id)
        assert intent is not None
        return proposal_id, intent.intent_governance_id, quantity


def exit_state(attempt: PositionExitAttempt | None) -> str | None:
    return None if attempt is None else attempt.state.value


__all__ = [
    "SYMBOL",
    "PositionExitState",
    "Stack",
    "World",
    "datetime",
    "empty_database",
    "exit_state",
    "serve_exchange",
    "v1_configuration",
]
