"""MILESTONE-089 -- Store C (the PAPER exit-lifecycle database) over real PostgreSQL.

TWO REAL, SEPARATE DATABASES, ONE PROCESS. Store B is built through the real M084/M085 chain
(exactly as `test_m085_paper_execution_postgres.py` does) so a genuine FILLED entry attempt
exists; Store C is a second, independently migrated database
(`migrations_paper_exit`'s own chain). `usecases.position_exit`'s handlers
(`AssessPositionExitHandler`/`PreviewPositionExitHandler`/`AuthorizePositionExitHandler`/
`SubmitAuthorizedPositionExitHandler`/`ReconcilePositionExitHandler`) are composed with Store
B's `intents`/`entry_attempts` repositories and Store C's exit repositories, over a
`SimulatedPaperBroker`/`SimulatedMarketData` pair (no network; PAPER's own real Alpaca adapter
is exercised separately by the read-only smoke test, never by this suite). This proves the
cross-database composition genuinely works -- not each side in isolation -- and that Store C's
database-level guards hold without the M087 preview-insert trigger, which does not exist here.

NEITHER STORE IS EVER THE REAL DEPLOYED DATABASE. `_m085_support.config()`'s database and
`_m089_support.store_c_config()`'s database are asserted disposable-test-shaped before any
`DROP SCHEMA` runs (see each module). This suite never opens a connection to
`empirical_platform_paper` (the real M085 Paper entry database Store B mirrors the SHAPE of,
never the deployment of).
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import DBAPIError, IntegrityError
from tests.integration._m085_support import (
    CHAIN_AT,
    a_basis_at,
    a_policy,
    an_approved_intent,
    build_engine,
    config,
    truncate_all,
)
from tests.integration._m089_support import (
    M089_TABLES,
    build_engine_c,
    store_c_config,
    truncate_all_c,
)
from tests.unit._m085_fakes import a_provenance

from empirical_platform.decision_candidate.paper_execution import (
    PAPER_ENDPOINT_HOST,
    ExecutionAuthorization,
    PaperAccountSnapshot,
    PaperEnvironment,
    PaperExecutionState,
    authorize_submission,
    build_submission_preview,
)
from empirical_platform.entrypoints._composition import postgres_repository_runtime
from empirical_platform.shared.brokerage.paper_time import BoundedInstant, PaperTimeReading
from empirical_platform.shared.brokerage.simulation_paper import (
    SimulatedMarketData,
    SimulatedPaperBroker,
    SimulationStore,
)
from empirical_platform.shared.persistence.postgres import PostgresPersistenceService
from empirical_platform.shared.persistence.postgres_repositories.paper_execution_repositories import (  # noqa: E501
    PostgresPaperExecutionRuntime,
)
from empirical_platform.shared.persistence.postgres_repositories.paper_position_exit_schema import (
    M089_SCHEMA_HEAD,
    PaperExitSchemaHeadError,
    require_exact_m089_schema_head,
)
from empirical_platform.shared.persistence.postgres_repositories.position_exit_repositories import (  # noqa: E501
    M087_SCHEMA_HEAD,
    PostgresPositionExitRuntime,
)
from empirical_platform.shared.persistence.postgres_repositories.runtime import (
    PostgresRepositoryRuntime,
)
from empirical_platform.usecases.position_exit import (
    AssessPositionExitHandler,
    AuthorizePositionExitCommand,
    AuthorizePositionExitHandler,
    PreviewPositionExitCommand,
    PreviewPositionExitHandler,
    ReconcilePositionExitCommand,
    ReconcilePositionExitHandler,
    SubmitAuthorizedPositionExitCommand,
    SubmitAuthorizedPositionExitHandler,
)

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Store B: a real filled entry attempt, built through the real M084/M085 chain
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def engine_b() -> Iterator[Engine]:
    yield from build_engine()


@pytest.fixture(scope="module")
def engine_c() -> Iterator[Engine]:
    yield from build_engine_c()


def _an_account() -> PaperAccountSnapshot:
    return PaperAccountSnapshot(
        snapshot_id="SNP-089-0001",
        environment=PaperEnvironment.PAPER,
        endpoint_host=PAPER_ENDPOINT_HOST,
        account_reference="ref:m089-account",
        account_status="ACTIVE",
        currency="USD",
        buying_power=Decimal("100000"),
        cash=Decimal("100000"),
        equity=Decimal("100000"),
        multiplier="4",
        shorting_enabled=True,
        trading_blocked=False,
        transfers_blocked=False,
        account_blocked=False,
        trade_suspended_by_user=False,
        captured_at=CHAIN_AT,
    )


def _filled_entry_attempt(
    paper: PostgresPaperExecutionRuntime,
    store: SimulationStore,
    *,
    intent_id: str,
    proposal_id: str,
    context_id: str,
    watermark_id: str,
    configuration_id: str,
    filled_avg_price: str = "200.00",
) -> tuple[str, str, Decimal, Decimal]:
    """A real Store-B chain, dispatched and filled directly at the repository level.

    ALSO adds the matching quantity to the SimulatedPaperBroker's own JSON position store
    (`store.add_position`), which the raw repository writes below never touch: the broker's
    position truth and Store B's entry-attempt row must agree for `AssessPositionExitHandler`'s
    live re-verification to find the position eligible, exactly as production requires the two
    to agree (Phase 4/7: "broker position truth overrides local assumptions").

    Returns (intent_governance_id, symbol, filled_quantity, filled_avg_price).
    """
    with postgres_repository_runtime(config("m089-chain")) as m084:
        intent = an_approved_intent(
            m084,
            intent_id=intent_id,
            proposal_id=proposal_id,
            context_id=context_id,
            watermark_id=watermark_id,
            configuration_id=configuration_id,
        )
    account = paper.paper_account_snapshots.save(_an_account())
    preview = build_submission_preview(
        preview_id=f"PVW-{intent_id}",
        intent=intent,
        account=account,
        preview_version=paper.submission_previews.next_version_for_intent(
            intent.intent_governance_id
        ),
        market_is_open=True,
        market_next_open=None,
        market_next_close=CHAIN_AT + timedelta(hours=3),
        quote_bid=Decimal("199.95"),
        quote_ask=Decimal("200.10"),
        quote_captured_at=CHAIN_AT - timedelta(seconds=5),
        quote_source="alpaca-iex",
        asset_tradable=True,
        asset_status="active",
        asset_class="us_equity",
        asset_exchange="NASDAQ",
        asset_fractionable=True,
        policy=a_policy(configuration_id=configuration_id),
        existing_position_quantity=0,
        execution_kill_switch_engaged=False,
        created_at=CHAIN_AT,
        broker_now=BoundedInstant(earliest=CHAIN_AT, latest=CHAIN_AT),
        m084_provenance=a_provenance(intent),
    )
    paper.submission_previews.save(preview)
    authorization: ExecutionAuthorization = authorize_submission(
        authorization_id=f"AUT-{intent_id}",
        preview=preview,
        authorized_by="owner",
        authorized_at=CHAIN_AT,
        validity_seconds=60,
        time_basis=a_basis_at(CHAIN_AT),
    )
    paper.execution_authorizations.save(authorization)
    claim = paper.execution_attempts.claim_dispatch(
        attempt_id=f"ATT-{intent_id}",
        authorization=authorization,
        request_fingerprint_now=authorization.request_fingerprint,
        account_reference_now=authorization.account_reference,
        broker_clock=lambda: BoundedInstant(earliest=CHAIN_AT, latest=CHAIN_AT),
        claimed_at=CHAIN_AT,
    )
    assert claim.won
    paper.execution_attempts.transition(
        attempt_id=claim.attempt.attempt_id,
        target=PaperExecutionState.SUBMISSION_IN_PROGRESS,
        at=CHAIN_AT,
    )
    paper.execution_attempts.transition(
        attempt_id=claim.attempt.attempt_id,
        target=PaperExecutionState.PAPER_SUBMITTED,
        at=CHAIN_AT,
        broker_order_id=f"SIM-{intent_id}",
        broker_status="new",
    )
    filled = paper.execution_attempts.transition(
        attempt_id=claim.attempt.attempt_id,
        target=PaperExecutionState.FILLED,
        at=CHAIN_AT,
        broker_order_id=f"SIM-{intent_id}",
        broker_status="filled",
        filled_quantity=str(intent.quantity),
        filled_avg_price=filled_avg_price,
    )
    assert filled.state is PaperExecutionState.FILLED
    assert filled.filled_quantity is not None and filled.filled_quantity == Decimal(intent.quantity)
    store.add_position(intent.symbol, intent.quantity)
    return (
        intent.intent_governance_id,
        intent.symbol,
        filled.filled_quantity,
        filled.filled_avg_price,
    )


# ---------------------------------------------------------------------------
# Schema head
# ---------------------------------------------------------------------------


def test_the_store_c_migration_produces_exactly_the_m089_head(engine_c: Engine) -> None:
    truncate_all_c(engine_c)
    with engine_c.begin() as connection:
        present = {
            row[0]
            for row in connection.execute(
                text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
            ).all()
        }
    assert set(M089_TABLES) <= present
    assert "paper_execution_attempt" not in present  # Store C never carries Store B's entry table
    with engine_c.begin() as connection:
        head = connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
    assert head == M089_SCHEMA_HEAD

    service = PostgresPersistenceService(store_c_config("m089-head"))
    service.initialize()
    try:
        assert require_exact_m089_schema_head(service) == M089_SCHEMA_HEAD
    finally:
        service.close()


def test_the_guard_refuses_no_revision_and_the_wrong_revision(engine_c: Engine) -> None:
    with engine_c.begin() as connection:
        connection.execute(text("DELETE FROM alembic_version"))
    service = PostgresPersistenceService(store_c_config("m089-empty"))
    service.initialize()
    try:
        with pytest.raises(PaperExitSchemaHeadError, match="none"):
            require_exact_m089_schema_head(service)
        with engine_c.begin() as connection:
            connection.execute(
                text("INSERT INTO alembic_version (version_num) VALUES (:v)"),
                {"v": M087_SCHEMA_HEAD},
            )
        # Store A/B's own M087 head is NOT Store C's head: the guard must not accept it.
        with pytest.raises(PaperExitSchemaHeadError, match=M089_SCHEMA_HEAD):
            require_exact_m089_schema_head(service)
    finally:
        service.close()
        with engine_c.begin() as connection:
            connection.execute(text("DELETE FROM alembic_version"))
            connection.execute(
                text("INSERT INTO alembic_version (version_num) VALUES (:v)"),
                {"v": M089_SCHEMA_HEAD},
            )


# ---------------------------------------------------------------------------
# The cross-database round trip
# ---------------------------------------------------------------------------


class _Clock:
    def __init__(self, at: datetime) -> None:
        self.at = at
        self.monotonic = 1000.0

    def __call__(self) -> datetime:
        return self.at

    def read(self) -> PaperTimeReading:
        return PaperTimeReading(self.at, self.monotonic)

    def advance(self, seconds: float) -> None:
        self.at += timedelta(seconds=seconds)
        self.monotonic += seconds


@pytest.fixture
def world(engine_b: Engine, engine_c: Engine, tmp_path: Path) -> Iterator[dict[str, object]]:
    truncate_all(engine_b)
    truncate_all_c(engine_c)
    store_b_service = PostgresPersistenceService(config("m089-store-b"))
    store_b_service.initialize()
    store_c_service = PostgresPersistenceService(store_c_config("m089-store-c"))
    store_c_service.initialize()
    paper = PostgresPaperExecutionRuntime(store_b_service)
    exit_runtime = PostgresPositionExitRuntime(store_c_service)
    # The SAME long-lived Store B service backs both the M084 and M085 repositories (one
    # database, two milestones' tables) -- unlike `_filled_entry_attempt`'s own short-lived
    # `postgres_repository_runtime` use, which only needs to persist the intent and return.
    store_b_m084 = PostgresRepositoryRuntime(store_b_service)
    intents = store_b_m084.approved_order_intents
    configurations = store_b_m084.operator_trading_configurations
    store = SimulationStore(tmp_path / "broker.json")
    store.stage(scenarios={}, quotes={"AAPL": ("199.95", "200.10")})
    clock = _Clock(CHAIN_AT)
    broker = SimulatedPaperBroker(store, clock=clock)
    market_data = SimulatedMarketData(store, clock=clock)
    try:
        yield {
            "paper": paper,
            "exits": exit_runtime,
            "intents": intents,
            "configurations": configurations,
            "broker": broker,
            "market_data": market_data,
            "store": store,
            "clock": clock,
            "engine_b": engine_b,
            "engine_c": engine_c,
        }
    finally:
        store_c_service.close()
        store_b_service.close()


def _prepare_and_confirm_exit(world: dict[str, object], *, intent_id: str) -> object:
    preview = PreviewPositionExitHandler(
        intents=world["intents"],  # type: ignore[arg-type]
        entry_attempts=world["paper"].execution_attempts,  # type: ignore[attr-defined]
        exit_attempts=world["exits"].attempts,  # type: ignore[attr-defined]
        previews=world["exits"].previews,  # type: ignore[attr-defined]
        events=world["exits"].events,  # type: ignore[attr-defined]
        broker=world["broker"],  # type: ignore[arg-type]
        market_data=world["market_data"],  # type: ignore[arg-type]
        configurations=world["configurations"],  # type: ignore[arg-type]
        environment="PAPER",
        time_source=world["clock"],  # type: ignore[arg-type]
    ).handle(
        PreviewPositionExitCommand(
            entry_intent_governance_id=intent_id,
            preview_id=f"XPV-{intent_id}-1",
            created_at=world["clock"](),  # type: ignore[operator]
        )
    )
    AuthorizePositionExitHandler(
        previews=world["exits"].previews,  # type: ignore[attr-defined]
        authorizations=world["exits"].authorizations,  # type: ignore[attr-defined]
        events=world["exits"].events,  # type: ignore[attr-defined]
        broker=world["broker"],  # type: ignore[arg-type]
        kill_switch=world["paper"].execution_kill_switch,  # type: ignore[attr-defined]
        time_source=world["clock"],  # type: ignore[arg-type]
    ).handle(
        AuthorizePositionExitCommand(
            authorization_id=f"XAU-{intent_id}-1",
            preview_id=preview.preview_id,
            expected_request_fingerprint=preview.request_fingerprint,
            authorized_by="owner",
            authorized_at=world["clock"](),  # type: ignore[operator]
        )
    )
    return SubmitAuthorizedPositionExitHandler(
        intents=world["intents"],  # type: ignore[arg-type]
        entry_attempts=world["paper"].execution_attempts,  # type: ignore[attr-defined]
        previews=world["exits"].previews,  # type: ignore[attr-defined]
        authorizations=world["exits"].authorizations,  # type: ignore[attr-defined]
        attempts=world["exits"].attempts,  # type: ignore[attr-defined]
        acknowledgements=world["exits"].acknowledgements,  # type: ignore[attr-defined]
        events=world["exits"].events,  # type: ignore[attr-defined]
        broker=world["broker"],  # type: ignore[arg-type]
        configurations=world["configurations"],  # type: ignore[arg-type]
        kill_switch=world["paper"].execution_kill_switch,  # type: ignore[attr-defined]
        time_source=world["clock"],  # type: ignore[arg-type]
    ).handle(
        SubmitAuthorizedPositionExitCommand(
            entry_intent_governance_id=intent_id,
            attempt_id=f"XAT-{intent_id}-1",
            at=world["clock"](),  # type: ignore[operator]
        )
    )


def test_the_cross_database_round_trip_closes_the_position(world: dict[str, object]) -> None:
    paper: PostgresPaperExecutionRuntime = world["paper"]  # type: ignore[assignment]
    store: SimulationStore = world["store"]  # type: ignore[assignment]
    intent_id, symbol, filled_qty, _ = _filled_entry_attempt(
        paper,
        store,
        intent_id="INT-089-0001",
        proposal_id="PRP-089-0001",
        context_id="ECX-089-0001",
        watermark_id="WM-089-0001",
        configuration_id="CFG-089-0001",
    )
    broker: SimulatedPaperBroker = world["broker"]  # type: ignore[assignment]
    assert broker.fetch_position(symbol) is not None
    assert int(broker.fetch_position(symbol).quantity) == int(filled_qty)  # type: ignore[union-attr]

    assessment = AssessPositionExitHandler(
        intents=world["intents"],  # type: ignore[arg-type]
        entry_attempts=paper.execution_attempts,
        exit_attempts=world["exits"].attempts,  # type: ignore[attr-defined]
        broker=broker,
    ).handle(intent_id, at=world["clock"]())  # type: ignore[operator]
    assert assessment.eligible, assessment.refusals

    result = _prepare_and_confirm_exit(world, intent_id=intent_id)
    assert result.dispatched

    exit_runtime: PostgresPositionExitRuntime = world["exits"]  # type: ignore[assignment]
    clock: _Clock = world["clock"]  # type: ignore[assignment]
    attempt = exit_runtime.attempts.active_for_entry(intent_id)
    assert attempt is not None
    for _ in range(3):
        clock.advance(5)
        attempt = ReconcilePositionExitHandler(
            attempts=exit_runtime.attempts,
            acknowledgements=exit_runtime.acknowledgements,
            events=exit_runtime.events,
            rounds=exit_runtime.rounds,
            authorizations=exit_runtime.authorizations,
            previews=exit_runtime.previews,
            broker=broker,
            time_source=clock,
        ).handle(ReconcilePositionExitCommand(attempt_id=attempt.attempt_id, at=clock.at))
        if attempt.position_closed:
            break
    assert attempt is not None and attempt.position_closed
    assert broker.fetch_position(symbol) is None or broker.fetch_position(symbol).quantity == 0  # type: ignore[union-attr]

    engine_c: Engine = world["engine_c"]  # type: ignore[assignment]
    with engine_c.begin() as connection:
        row = connection.execute(
            text("SELECT state, client_order_id FROM public.position_exit_attempt")
        ).one()
    assert row[0] == "FILLED"
    assert row[1].startswith("m087-")

    with engine_c.begin() as connection:
        preview_env = connection.execute(
            text("SELECT environment FROM public.position_exit_preview")
        ).scalar_one()
    assert preview_env == "PAPER"

    # The Store B entry row is untouched by the whole exit.
    engine_b: Engine = world["engine_b"]  # type: ignore[assignment]
    with engine_b.begin() as connection:
        entry_state = connection.execute(
            text(
                "SELECT state FROM public.paper_execution_attempt WHERE intent_governance_id = :i"
            ),
            {"i": intent_id},
        ).scalar_one()
    assert entry_state == "FILLED"


def test_a_preview_names_an_entry_attempt_that_exists_only_in_store_b(
    world: dict[str, object],
) -> None:
    """The key architectural property: Store C has no local FK/trigger over `entry_attempt_id`."""
    paper: PostgresPaperExecutionRuntime = world["paper"]  # type: ignore[assignment]
    store: SimulationStore = world["store"]  # type: ignore[assignment]
    intent_id, _symbol, _qty, _price = _filled_entry_attempt(
        paper,
        store,
        intent_id="INT-089-0002",
        proposal_id="PRP-089-0002",
        context_id="ECX-089-0002",
        watermark_id="WM-089-0002",
        configuration_id="CFG-089-0002",
    )
    engine_c: Engine = world["engine_c"]  # type: ignore[assignment]
    with engine_c.begin() as connection:
        present = {
            row[0]
            for row in connection.execute(
                text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
            ).all()
        }
    assert "paper_execution_attempt" not in present

    broker: SimulatedPaperBroker = world["broker"]  # type: ignore[assignment]
    preview = PreviewPositionExitHandler(
        intents=world["intents"],  # type: ignore[arg-type]
        entry_attempts=paper.execution_attempts,
        exit_attempts=world["exits"].attempts,  # type: ignore[attr-defined]
        previews=world["exits"].previews,  # type: ignore[attr-defined]
        events=world["exits"].events,  # type: ignore[attr-defined]
        broker=broker,
        market_data=world["market_data"],  # type: ignore[arg-type]
        configurations=world["configurations"],  # type: ignore[arg-type]
        environment="PAPER",
        time_source=world["clock"],  # type: ignore[arg-type]
    ).handle(
        PreviewPositionExitCommand(
            entry_intent_governance_id=intent_id,
            preview_id="XPV-INT-089-0002-1",
            created_at=world["clock"](),  # type: ignore[operator]
        )
    )
    # Saved into Store C with no local table Store C could have checked it against.
    with engine_c.begin() as connection:
        stored = connection.execute(
            text("SELECT entry_attempt_id FROM public.position_exit_preview WHERE preview_id = :p"),
            {"p": preview.preview_id},
        ).scalar_one()
    assert stored == preview.entry_attempt_id


# ---------------------------------------------------------------------------
# Database-level guards, adapted for Store C (no preview-insert trigger)
# ---------------------------------------------------------------------------


def _refused(engine: Engine, statement: str, **params: object) -> str:
    with pytest.raises((DBAPIError, IntegrityError)) as error, engine.begin() as connection:
        connection.execute(text(statement), params)
    return str(error.value)


def test_the_preview_environment_check_accepts_only_paper(
    world: dict[str, object], engine_c: Engine
) -> None:
    paper: PostgresPaperExecutionRuntime = world["paper"]  # type: ignore[assignment]
    store: SimulationStore = world["store"]  # type: ignore[assignment]
    intent_id, _symbol, _qty, _price = _filled_entry_attempt(
        paper,
        store,
        intent_id="INT-089-0003",
        proposal_id="PRP-089-0003",
        context_id="ECX-089-0003",
        watermark_id="WM-089-0003",
        configuration_id="CFG-089-0003",
    )
    preview = PreviewPositionExitHandler(
        intents=world["intents"],  # type: ignore[arg-type]
        entry_attempts=paper.execution_attempts,
        exit_attempts=world["exits"].attempts,  # type: ignore[attr-defined]
        previews=world["exits"].previews,  # type: ignore[attr-defined]
        events=world["exits"].events,  # type: ignore[attr-defined]
        broker=world["broker"],  # type: ignore[arg-type]
        market_data=world["market_data"],  # type: ignore[arg-type]
        configurations=world["configurations"],  # type: ignore[arg-type]
        environment="PAPER",
        time_source=world["clock"],  # type: ignore[arg-type]
    ).handle(
        PreviewPositionExitCommand(
            entry_intent_governance_id=intent_id,
            preview_id="XPV-INT-089-0003-1",
            created_at=world["clock"](),  # type: ignore[operator]
        )
    )
    with engine_c.begin() as connection:
        row = dict(
            connection.execute(
                text("SELECT * FROM public.position_exit_preview WHERE preview_id = :p"),
                {"p": preview.preview_id},
            )
            .mappings()
            .one()
        )
    for column, bad in (
        ("environment", "SIMULATION"),
        ("quantity", 0),
        ("side", "SELL"),
    ):
        attack = dict(row)
        attack.update({"preview_id": f"ATTACK-{column}", "preview_version": 99, column: bad})
        columns = ", ".join(attack)
        placeholders = ", ".join(f":{k}" for k in attack)
        message = _refused(
            engine_c,
            "".join(
                (
                    "INSERT INTO public.position_exit_preview (",
                    columns,
                    ") VALUES (",
                    placeholders,
                    ")",
                )
            ),
            **attack,
        )
        assert "ck_position_exit_preview" in message or "violates" in message


def test_the_preview_table_is_append_only_and_client_order_id_keeps_the_m087_prefix(
    world: dict[str, object], engine_c: Engine
) -> None:
    paper: PostgresPaperExecutionRuntime = world["paper"]  # type: ignore[assignment]
    store: SimulationStore = world["store"]  # type: ignore[assignment]
    intent_id, _symbol, _qty, _price = _filled_entry_attempt(
        paper,
        store,
        intent_id="INT-089-0004",
        proposal_id="PRP-089-0004",
        context_id="ECX-089-0004",
        watermark_id="WM-089-0004",
        configuration_id="CFG-089-0004",
    )
    preview = PreviewPositionExitHandler(
        intents=world["intents"],  # type: ignore[arg-type]
        entry_attempts=paper.execution_attempts,
        exit_attempts=world["exits"].attempts,  # type: ignore[attr-defined]
        previews=world["exits"].previews,  # type: ignore[attr-defined]
        events=world["exits"].events,  # type: ignore[attr-defined]
        broker=world["broker"],  # type: ignore[arg-type]
        market_data=world["market_data"],  # type: ignore[arg-type]
        configurations=world["configurations"],  # type: ignore[arg-type]
        environment="PAPER",
        time_source=world["clock"],  # type: ignore[arg-type]
    ).handle(
        PreviewPositionExitCommand(
            entry_intent_governance_id=intent_id,
            preview_id="XPV-INT-089-0004-1",
            created_at=world["clock"](),  # type: ignore[operator]
        )
    )
    assert preview.request.client_order_id.startswith("m087-")
    assert "append-only" in _refused(
        engine_c,
        "UPDATE public.position_exit_preview SET quantity = quantity WHERE preview_id = :p",
        p=preview.preview_id,
    )
    assert "append-only" in _refused(
        engine_c,
        "DELETE FROM public.position_exit_preview WHERE preview_id = :p",
        p=preview.preview_id,
    )


def test_at_most_one_active_exit_per_position_in_store_c(
    world: dict[str, object], engine_c: Engine
) -> None:
    paper: PostgresPaperExecutionRuntime = world["paper"]  # type: ignore[assignment]
    store: SimulationStore = world["store"]  # type: ignore[assignment]
    intent_id, symbol, filled_qty, _price = _filled_entry_attempt(
        paper,
        store,
        intent_id="INT-089-0005",
        proposal_id="PRP-089-0005",
        context_id="ECX-089-0005",
        watermark_id="WM-089-0005",
        configuration_id="CFG-089-0005",
    )
    result = _prepare_and_confirm_exit(world, intent_id=intent_id)
    assert result.dispatched
    exit_runtime: PostgresPositionExitRuntime = world["exits"]  # type: ignore[assignment]
    active = exit_runtime.attempts.active_for_entry(intent_id)
    assert active is not None
    # A second attempt for the SAME entry, bound to a different (fabricated) authorization,
    # violates the partial unique index over non-terminal-or-filled states.
    with engine_c.begin() as connection:
        auth_row = dict(
            connection.execute(
                text(
                    "SELECT * FROM public.position_exit_authorization WHERE authorization_id = :a"
                ),
                {"a": active.authorization_id},
            )
            .mappings()
            .one()
        )
    fabricated_auth = dict(auth_row)
    fabricated_auth.update(
        {
            "authorization_id": "ATTACK-SECOND-AUTH",
            "consumed_at": None,
            "consumed_by_attempt_id": None,
        }
    )
    # Every other field describes the SAME preview exactly (as the insert guard requires);
    # only the identity differs. The one-per-preview unique index is what refuses this, not
    # the insert guard's "does not describe the preview" check.
    columns = ", ".join(fabricated_auth)
    placeholders = ", ".join(f":{k}" for k in fabricated_auth)
    message = _refused(
        engine_c,
        "".join(
            (
                "INSERT INTO public.position_exit_authorization (",
                columns,
                ") VALUES (",
                placeholders,
                ")",
            )
        ),
        **fabricated_auth,
    )
    assert "uq_position_exit_authorization_one_per_preview" in message
