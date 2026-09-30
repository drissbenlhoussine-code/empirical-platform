"""MILESTONE-087 -- position exits over real PostgreSQL and the durable simulation store.

The production composition root, the real migration chain, the real triggers. Every
"restart" is a new persistence service and a new console over the SAME database and the SAME
store file with a fresh process secret. Nothing here reaches a network.
"""

from __future__ import annotations

import threading
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from alembic import command as alembic_command
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import DBAPIError, IntegrityError
from tests.integration._m085_support import alembic_config, build_engine, config, truncate_all

from empirical_platform.decision_candidate.position_exit import PositionExitState
from empirical_platform.entrypoints._operator_console_composition import (
    ConsoleRuntime,
    compose_operator_console,
)
from empirical_platform.entrypoints._position_exit_composition import (
    compose_operator_console_with_exits,
)
from empirical_platform.shared.brokerage.paper_time import PaperTimeReading
from empirical_platform.shared.brokerage.simulation_paper import (
    SimulationStateLockedError,
    SimulationStore,
)
from empirical_platform.shared.persistence.postgres import PostgresPersistenceService
from empirical_platform.shared.persistence.postgres_repositories.paper_execution_repositories import (  # noqa: E501
    PaperSchemaHeadError,
    require_exact_m085_schema_head,
)
from empirical_platform.shared.persistence.postgres_repositories.position_exit_repositories import (  # noqa: E501
    M087_SCHEMA_HEAD,
    ExitSchemaHeadError,
    PostgresPositionExitAttemptRepository,
    require_exact_m087_schema_head,
)
from empirical_platform.usecases.operator_console import ConsoleRefusalError, ExecutionCapability
from empirical_platform.usecases.position_exit import (
    AuthorizePositionExitCommand,
    AuthorizePositionExitHandler,
)

pytestmark = pytest.mark.integration

M087_TABLES = (
    "position_exit_event",
    "position_exit_reconciliation_round",
    "position_exit_acknowledgement",
    "position_exit_attempt",
    "position_exit_authorization",
    "position_exit_preview",
)
M085_HEAD = "".join(("a7d3c9", "e14f26"))


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
    # MILESTONE-090 pinned: this suite tests M087's OWN exact-head guard
    # (`require_exact_m087_schema_head`), so it must build the database at exactly M087's head,
    # not the repository's current head -- M090's own additive migration is now later in the
    # same chain and would otherwise make the default `revision="head"` build a database this
    # guard correctly refuses. See `_m085_support.build_engine`'s own docstring.
    yield from build_engine(M087_SCHEMA_HEAD)


def _truncate(engine: Engine) -> None:
    with engine.begin() as connection:
        present = {
            row[0]
            for row in connection.execute(
                text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
            ).all()
        }
        existing = [t for t in M087_TABLES if t in present]
        if existing:
            connection.execute(text("TRUNCATE " + ", ".join(existing)))
    truncate_all(engine)


@pytest.fixture
def world(engine: Engine, tmp_path: Path) -> Iterator[dict[str, Any]]:
    _truncate(engine)
    clock = Clock()
    services: list[PostgresPersistenceService] = []
    runtimes: list[ConsoleRuntime] = []

    def process(name: str) -> ConsoleRuntime:
        service = PostgresPersistenceService(config(f"m087-console-{name}"))
        service.initialize()
        services.append(service)
        runtime = compose_operator_console_with_exits(
            ExecutionCapability.SIMULATION,
            service=service,
            state_dir=tmp_path,
            clock=clock,
            time_source=clock,
        )
        assert runtime.verified_schema_head == M087_SCHEMA_HEAD and runtime.exits is not None
        runtimes.append(runtime)
        return runtime

    try:
        yield {"engine": engine, "clock": clock, "process": process, "state_dir": tmp_path}
    finally:
        for runtime in runtimes:
            runtime.close()
        for service in services:
            service.close()


def _proposal_id(clock: Clock, symbol: str) -> str:
    return f"PRP-086-{clock.utc.strftime('%Y%m%d')}-{symbol}"


def _approve(runtime: ConsoleRuntime, proposal_id: str) -> Any:  # noqa: ANN401
    view = runtime.service.prepare_approval(proposal_id)
    return runtime.service.confirm_approval(proposal_id, view.ticket)


def _settle(runtime: ConsoleRuntime, clock: Clock, passes: int = 2) -> None:
    for _ in range(passes):
        clock.advance(5)
        runtime.service.refresh_executions()


def _open(runtime: ConsoleRuntime, clock: Clock, symbol: str = "AAPL") -> str:
    runtime.load_day()
    outcome = _approve(runtime, _proposal_id(clock, symbol))
    assert outcome.sent == "sent", outcome.message
    _settle(runtime, clock, passes=3)
    intent = f"INT-{_proposal_id(clock, symbol)}"
    entry = runtime.repositories.attempts.for_intent(intent)
    assert entry is not None and entry.state.value == "FILLED", entry
    return intent


def _sql(*parts: str) -> str:
    """Join literal fragments (table names and clauses written in this test) into a statement."""
    return "".join(parts)


def _count(engine: Engine, table: str, where: str = "TRUE") -> int:
    with engine.begin() as connection:
        return int(
            connection.execute(
                text(_sql("SELECT count(*) FROM public.", table, " WHERE ", where))
            ).scalar_one()
        )


# ---------------------------------------------------------------------------
# Migration
# ---------------------------------------------------------------------------


def test_the_migration_upgrades_downgrades_and_re_upgrades_with_an_exact_head(
    world: dict[str, Any],
) -> None:
    engine: Engine = world["engine"]
    service = PostgresPersistenceService(config("m087-head"))
    service.initialize()
    try:
        assert require_exact_m087_schema_head(service) == M087_SCHEMA_HEAD
        with engine.begin() as connection:
            assert (
                connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
                == M087_SCHEMA_HEAD
            )
        alembic_command.downgrade(alembic_config(), M085_HEAD)
        with engine.begin() as connection:
            present = {
                row[0]
                for row in connection.execute(
                    text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
                ).all()
            }
        assert not (set(M087_TABLES) & present)
        assert "paper_execution_attempt" in present and "paper_reconciliation_round" in present
        with pytest.raises(ExitSchemaHeadError, match=M087_SCHEMA_HEAD):
            require_exact_m087_schema_head(service)
        # At the M085 head: the M087 composition refuses; the M086 composition ACCEPTS, with no
        # exit path composed (M086 semantics: schema = M085 head).
        with pytest.raises(ExitSchemaHeadError):
            compose_operator_console_with_exits(
                ExecutionCapability.SIMULATION, service=service, state_dir=world["state_dir"] / "x"
            )
        m086 = compose_operator_console(
            ExecutionCapability.SIMULATION, service=service, state_dir=world["state_dir"] / "m086"
        )
        try:
            assert m086.verified_schema_head == M085_HEAD and m086.exits is None
            assert m086.service.exits is None
        finally:
            m086.close()
        # MILESTONE-090 pinned: re-upgrade to exactly M087's own head, not the repository's
        # current head (M090's own additive migration now stacks beyond it in the same chain).
        alembic_command.upgrade(alembic_config(), M087_SCHEMA_HEAD)
        with engine.begin() as connection:
            present = {
                row[0]
                for row in connection.execute(
                    text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
                ).all()
            }
        assert set(M087_TABLES) <= present
        assert require_exact_m087_schema_head(service) == M087_SCHEMA_HEAD
        # At the M087 head: the M086 public composition still refuses (it requires the exact
        # M085 head and does not silently accept a descendant); the M087 composition accepts.
        with pytest.raises(PaperSchemaHeadError, match=M085_HEAD):
            compose_operator_console(
                ExecutionCapability.SIMULATION, service=service, state_dir=world["state_dir"] / "y"
            )
        with pytest.raises(PaperSchemaHeadError):
            require_exact_m085_schema_head(service)
    finally:
        service.close()


# ---------------------------------------------------------------------------
# The round trip and the database guards
# ---------------------------------------------------------------------------


def test_the_round_trip_closes_the_position_and_the_rows_are_consistent(
    world: dict[str, Any],
) -> None:
    a = world["process"]("a")
    clock: Clock = world["clock"]
    engine: Engine = world["engine"]
    intent = _open(a, clock)
    assert a.store.position("AAPL") == 8
    exits = a.service.exits
    assert exits is not None
    review = exits.review(intent)
    assert _count(engine, "position_exit_preview") == 1
    assert _count(engine, "position_exit_attempt") == 0
    outcome = exits.confirm(intent, review.ticket)
    assert outcome.ok and outcome.sent == "sent"
    assert _count(engine, "position_exit_authorization", "consumed_at IS NOT NULL") == 1
    assert _count(engine, "position_exit_attempt") == 1
    _settle(a, clock)
    closed = a.exits.attempts.active_for_entry(intent)  # type: ignore[union-attr]
    assert closed is not None and closed.position_closed and a.store.position("AAPL") == 0
    with engine.begin() as connection:
        row = connection.execute(
            text(
                "SELECT state, filled_quantity, closed_position_verified_at, client_order_id "
                "FROM public.position_exit_attempt"
            )
        ).one()
    assert row[0] == "FILLED" and row[1] == Decimal(8) and row[2] is not None
    assert row[3].startswith("m087-")
    assert _count(engine, "position_exit_event", "event_type = 'POSITION_CLOSED_VERIFIED'") == 1
    assert _count(engine, "position_exit_reconciliation_round", "outcome = 'FOUND'") >= 1
    assert a.service.active_trades() == ()
    (history,) = a.service.history(symbol="AAPL")
    assert (
        history.execution_outcome == "Position closed (simulation)" and "realized" in history.result
    )
    # The M085 entry row is untouched by the whole exit.
    with engine.begin() as connection:
        entry_state = connection.execute(
            text("SELECT state FROM public.paper_execution_attempt")
        ).scalar_one()
    assert entry_state == "FILLED"


def test_the_database_refuses_every_rewrite_and_every_second_identity(
    world: dict[str, Any],
) -> None:
    a = world["process"]("a")
    clock: Clock = world["clock"]
    engine: Engine = world["engine"]
    intent = _open(a, clock)
    exits = a.service.exits
    assert exits is not None
    review = exits.review(intent)
    exits.confirm(intent, review.ticket)
    with engine.begin() as connection:
        preview_id, quantity, entry_attempt = connection.execute(
            text("SELECT preview_id, quantity, entry_attempt_id FROM public.position_exit_preview")
        ).one()
        attempt_id, authorization_id = connection.execute(
            text("SELECT attempt_id, authorization_id FROM public.position_exit_attempt")
        ).one()

    def refused(statement: str, **params: object) -> str:
        with pytest.raises((DBAPIError, IntegrityError)) as error, engine.begin() as connection:
            connection.execute(text(statement), params)
        return str(error.value)

    # Quantity cannot be non-positive, a partial close cannot be stored, environment is SIMULATION.
    with engine.begin() as connection:
        row = dict(
            connection.execute(text("SELECT * FROM public.position_exit_preview")).mappings().one()
        )
    for column, bad in (
        ("quantity", 0),
        ("quantity", quantity - 1),
        ("environment", "PAPER"),
        ("side", "SELL"),
    ):
        attack = dict(row)
        attack.update({"preview_id": f"ATTACK-{column}", "preview_version": 99, column: bad})
        columns = ", ".join(attack)
        placeholders = ", ".join(f":{k}" for k in attack)
        message = refused(
            _sql(
                "INSERT INTO public.position_exit_preview (",
                columns,
                ") VALUES (",
                placeholders,
                ")",
            ),
            **attack,
        )
        assert "ck_position_exit_preview" in message or "violates" in message
    # Append-only preview; one authorization per preview; consumed once.
    assert "append-only" in refused("UPDATE public.position_exit_preview SET quantity = quantity")
    assert "append-only" in refused("DELETE FROM public.position_exit_preview")
    with engine.begin() as connection:
        authorization = dict(
            connection.execute(text("SELECT * FROM public.position_exit_authorization"))
            .mappings()
            .one()
        )
    second = dict(authorization)
    second.update(
        {"authorization_id": "ATTACK-AUTH", "consumed_at": None, "consumed_by_attempt_id": None}
    )
    message = refused(
        _sql(
            "INSERT INTO public.position_exit_authorization (",
            ", ".join(second),
            ") VALUES (",
            ", ".join(f":{k}" for k in second),
            ")",
        ),
        **second,
    )
    assert "uq_position_exit_authorization_one_per_preview" in message
    assert "already been used" in refused(
        "UPDATE public.position_exit_authorization SET consumed_at = now(), "
        "consumed_by_attempt_id = 'X' WHERE authorization_id = :id",
        id=authorization_id,
    )
    # Attempt identity is immutable; a terminal row cannot be rewritten; closed twice is refused.
    assert "immutable" in refused(
        "UPDATE public.position_exit_attempt SET client_order_id = 'm087-other' "
        "WHERE attempt_id = :id",
        id=attempt_id,
    )
    premature = refused(
        "UPDATE public.position_exit_attempt SET closed_position_verified_at = now() "
        "WHERE attempt_id = :id",
        id=attempt_id,
    )
    # The update guard refuses first (before it is FILLED); the CHECK would refuse the same row.
    assert "before it is FILLED" in premature or "closed_requires_full_fill" in premature
    assert "filled_within_quantity" in refused(
        "UPDATE public.position_exit_attempt SET filled_quantity = quantity + 1 "
        "WHERE attempt_id = :id",
        id=attempt_id,
    )
    assert "not an allowed position exit transition" in refused(
        "UPDATE public.position_exit_attempt SET state = 'SUBMISSION_IN_PROGRESS' "
        "WHERE attempt_id = :id",
        id=attempt_id,
    )
    _settle(a, clock)  # FILLED and verified closed
    assert "terminal" in refused(
        "UPDATE public.position_exit_attempt SET state = 'ACCEPTED' WHERE attempt_id = :id",
        id=attempt_id,
    )
    assert "already has a verified closed position" in refused(
        "UPDATE public.position_exit_attempt SET closed_position_verified_at = now() "
        "WHERE attempt_id = :id",
        id=attempt_id,
    )
    assert "append-only" in refused("DELETE FROM public.position_exit_attempt")
    assert "append-only" in refused("DELETE FROM public.position_exit_event")
    assert "append-only" in refused(
        "UPDATE public.position_exit_acknowledgement SET http_status = 500"
    )
    assert "append-only" in refused("DELETE FROM public.position_exit_reconciliation_round")
    assert "immutable" in refused(
        "UPDATE public.position_exit_reconciliation_round SET outcome = 'NOT_FOUND' "
        "WHERE outcome IS NOT NULL"
    )


def test_two_service_instances_cannot_create_two_exit_attempts(world: dict[str, Any]) -> None:
    a = world["process"]("a")
    clock: Clock = world["clock"]
    intent = _open(a, clock)
    a.close()  # release the state-directory lock so a second console can compose
    b = world["process"]("b")
    # Two consoles, two review pages, two confirmations: exactly one exit.
    ticket_a = a.service.exits.review(intent).ticket  # type: ignore[union-attr]
    ticket_b = b.service.exits.review(intent).ticket  # type: ignore[union-attr]
    first = a.service.exits.confirm(intent, ticket_a)  # type: ignore[union-attr]
    second = b.service.exits.confirm(intent, ticket_b)  # type: ignore[union-attr]
    assert first.ok and second.title == "Already confirmed"
    assert len(b.exits.attempts.for_entry(intent)) == 1  # type: ignore[union-attr]
    # The broker's durable file, re-read: one SELL. (Each console loads the store once; two
    # consoles on one directory are refused by the lock in production, released here on purpose.)
    fresh = SimulationStore(b.store.path)
    assert len([o for o in fresh.orders() if o.side == "sell"]) == 1


def test_a_racing_claim_on_one_authorization_has_exactly_one_winner(world: dict[str, Any]) -> None:
    a = world["process"]("a")
    clock: Clock = world["clock"]
    intent = _open(a, clock)
    exits = a.service.exits
    assert exits is not None
    review = exits.review(intent)
    preview = a.exits.previews.get(review.preview_id)  # type: ignore[union-attr]
    assert preview is not None
    authorization = AuthorizePositionExitHandler(
        previews=a.exits.previews,  # type: ignore[union-attr]
        authorizations=a.exits.authorizations,  # type: ignore[union-attr]
        events=a.exits.events,  # type: ignore[union-attr]
        broker=a.broker,
        kill_switch=a.repositories.kill_switch,
        time_source=clock,
    ).handle(
        AuthorizePositionExitCommand(
            authorization_id=f"XAU-{intent}-RACE",
            preview_id=preview.preview_id,
            expected_request_fingerprint=preview.request_fingerprint,
            authorized_by="owner",
            authorized_at=clock.utc,
        )
    )
    services = [PostgresPersistenceService(config(f"m087-race-{i}")) for i in range(2)]
    for service in services:
        service.initialize()
    results: list[Any] = []
    errors: list[BaseException] = []
    barrier = threading.Barrier(2)

    def claim(index: int) -> None:
        repository = PostgresPositionExitAttemptRepository(services[index])
        try:
            barrier.wait(timeout=10)
            results.append(
                repository.claim_dispatch(
                    attempt_id=f"XAT-RACE-{index}",
                    authorization=authorization,
                    request_fingerprint_now=authorization.request_fingerprint,
                    account_reference_now=authorization.account_reference,
                    claimed_at=clock.utc,
                    broker_clock=lambda: __import__(
                        "empirical_platform.shared.brokerage.paper_time",
                        fromlist=["BoundedInstant"],
                    ).BoundedInstant(earliest=clock.utc, latest=clock.utc),
                )
            )
        except BaseException as error:  # noqa: BLE001 - collected for the assertion
            errors.append(error)

    threads = [threading.Thread(target=claim, args=(i,)) for i in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
    for service in services:
        service.close()
    assert not errors, errors
    assert sorted(r.won for r in results) == [False, True]
    assert {r.attempt.attempt_id for r in results} == {
        next(r.attempt.attempt_id for r in results if r.won)
    }
    assert _count(world["engine"], "position_exit_attempt") == 1


# ---------------------------------------------------------------------------
# Restart scenarios
# ---------------------------------------------------------------------------


def test_restart_before_confirmation_and_after_authorization_sends_nothing(
    world: dict[str, Any],
) -> None:
    a = world["process"]("a")
    clock: Clock = world["clock"]
    intent = _open(a, clock)
    review = a.service.exits.review(intent)  # type: ignore[union-attr]
    a.close()
    b = world["process"]("b")
    assert b.exits.attempts.for_entry(intent) == ()  # type: ignore[union-attr]
    assert [o for o in b.store.orders() if o.side == "sell"] == []
    with pytest.raises(ConsoleRefusalError):
        b.service.exits.confirm(intent, review.ticket)  # type: ignore[union-attr] - another process's ticket
    # An authorization granted and never used: a restart does not spend it.
    preview = b.exits.previews.get(review.preview_id)  # type: ignore[union-attr]
    assert preview is not None
    AuthorizePositionExitHandler(
        previews=b.exits.previews,  # type: ignore[union-attr]
        authorizations=b.exits.authorizations,  # type: ignore[union-attr]
        events=b.exits.events,  # type: ignore[union-attr]
        broker=b.broker,
        kill_switch=b.repositories.kill_switch,
        time_source=clock,
    ).handle(
        AuthorizePositionExitCommand(
            authorization_id=f"XAU-{intent}-1",
            preview_id=preview.preview_id,
            expected_request_fingerprint=preview.request_fingerprint,
            authorized_by="owner",
            authorized_at=clock.utc,
        )
    )
    b.close()
    c = world["process"]("c")
    clock.advance(5)
    c.service.refresh_executions()
    assert c.exits.attempts.for_entry(intent) == ()  # type: ignore[union-attr]
    assert [o for o in c.store.orders() if o.side == "sell"] == []
    (row,) = c.service.active_trades()
    assert row.category == "Open position" and row.can_review_exit
    # The Owner confirms in the new process: the existing unused authorization for the SAME
    # preview is spent (no second authorization), exactly one exit is created.
    fresh = c.service.exits.review(intent)  # type: ignore[union-attr]
    outcome = c.service.exits.confirm(intent, fresh.ticket)  # type: ignore[union-attr]
    assert outcome.ok
    assert len(c.exits.attempts.for_entry(intent)) == 1  # type: ignore[union-attr]


def test_restart_after_an_ambiguous_exit_preserves_unknown_and_reconciles_the_same_identity(
    world: dict[str, Any],
) -> None:
    a = world["process"]("a")
    clock: Clock = world["clock"]
    a.load_day()
    outcome = _approve(a, _proposal_id(clock, "KO"))  # entry: ambiguous, found on reconciliation
    assert outcome.sent == "unknown"
    _settle(a, clock, passes=3)
    intent = f"INT-{_proposal_id(clock, 'KO')}"
    entry = a.repositories.attempts.for_intent(intent)
    assert entry is not None and entry.state.value == "FILLED"
    exits = a.service.exits
    assert exits is not None
    result = exits.confirm(intent, exits.review(intent).ticket)  # KO's exit: lost across a restart
    assert result.sent == "unknown"
    (unknown,) = a.exits.attempts.for_entry(intent)  # type: ignore[union-attr]
    assert unknown.state is PositionExitState.SUBMISSION_UNKNOWN
    a.close()
    b = world["process"]("b")
    (still,) = b.exits.attempts.for_entry(intent)  # type: ignore[union-attr]
    assert still.state is PositionExitState.SUBMISSION_UNKNOWN
    (row,) = [r for r in b.service.active_trades() if r.intent_id == intent]
    assert row.category == "Needs attention"
    with pytest.raises(ConsoleRefusalError, match="already in progress"):
        b.service.exits.review(intent)  # type: ignore[union-attr]
    _settle(b, clock, passes=3)
    closed = b.exits.attempts.active_for_entry(intent)  # type: ignore[union-attr]
    assert closed is not None and closed.position_closed
    assert closed.client_order_id == unknown.client_order_id
    sells = [o for o in b.store.orders() if o.side == "sell" and o.symbol == "KO"]
    assert len(sells) == 1 and sells[0].client_order_id == unknown.client_order_id
    assert b.store.position("KO") == 0


def test_the_one_console_per_state_dir_lock_is_intact(world: dict[str, Any]) -> None:
    world["process"]("a")
    service = PostgresPersistenceService(config("m087-second"))
    service.initialize()
    try:
        with pytest.raises(SimulationStateLockedError):
            compose_operator_console_with_exits(
                ExecutionCapability.SIMULATION, service=service, state_dir=world["state_dir"]
            )
    finally:
        service.close()
