"""RELEASE v1 schema-blocker fix -- the REAL integrated deployment shape, booted for real.

Release Blocker 5's real governance acceptance found that `require_exact_m085_schema_head`
permanently rejected the real deployment database once it was correctly migrated past M085:
Store A (the main `migrations/` chain, feeding `ApprovedPlan`) and Store B
(`paper_execution_runtime()`'s own database) are the SAME physical database in real
deployment, and `alembic upgrade head` on that one chain reaches the v1 head
(`c6e2a4f8b901`), never the literal, frozen M085 revision the old guard demanded. No prior
test caught this: every Postgres suite pins its own test database to the exact revision ITS
OWN guard expects (`test_m085_corrective_pass_postgres.py` pins to `M085_SCHEMA_HEAD`,
`test_m087_position_exit_postgres.py` steps the chain milestone by milestone, and nothing
anywhere composed the REAL `paper_operator_console_with_exit_runtime()` -- the function real
deployment actually calls -- against a database migrated the ordinary way, all the way to
head.

THIS SUITE DOES EXACTLY THAT. Store A/B: `tests.integration._m085_support.build_engine("head")`
-- the NORMAL `alembic upgrade head` over the main chain, never pinned to an older milestone.
Store C: `tests.integration._m089_support.build_engine_c("head")` -- its own, separate,
self-contained chain, likewise taken to its own real head. The REAL composition function is
then called with no test-only parameters, driven entirely through the SAME environment
variables real deployment sets (`EMPIRICAL_PLATFORM_POSTGRES_*`, `EMPIRICAL_PLATFORM_PAPER_
EXIT_POSTGRES_DATABASE`, the three `EMPIRICAL_ALPACA_PAPER_*` credential variables) --
proving the schema guards, the dual-store composition and the plan-manager wiring all work
together exactly as a real boot would exercise them, not as a specially-assembled stand-in
for them.

ZERO BROKER WRITES FROM BOOT ALONE, PROVEN AT THE TRANSPORT SEAM. `no_broker_network` replaces
`AlpacaPaperClient`'s own `_StrictConnection.request` -- the one place any HTTP request to
Alpaca's real endpoint actually leaves this process (see `shared.brokerage.alpaca_paper`) --
with a recorder that raises immediately if anything ever calls it. Composition, the
schema guards, and one plan-manager tick over an empty `approved_plan` table make zero
Alpaca HTTP calls of ANY kind (not just submissions): this is a stronger proof than counting
submit calls on a fake broker, because it would also catch an accidental `fetch_account`/
`fetch_clock` call nothing here asked for.

NEITHER DATABASE IS EVER THE REAL DEPLOYED DATABASE. Both `engine` and `engine_c` resolve
through `_m085_support.config()`/`_m089_support.store_c_config()`, the SAME disposable-test
databases used by the other integration suites, with this suite's additional explicit
_test database-name guard. The real
`empirical_platform_paper`/`empirical_platform_paper_exit` databases are never opened here.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from datetime import UTC, datetime
from threading import Event

import pytest
from sqlalchemy import text
from sqlalchemy.engine import Engine
from tests.integration._m085_support import build_engine, postgres_enabled
from tests.integration._m089_support import build_engine_c, store_c_config

from empirical_platform.entrypoints._paper_position_exit_composition import (
    paper_operator_console_with_exit_runtime,
)
from empirical_platform.shared.brokerage import alpaca_paper
from empirical_platform.shared.persistence.postgres_repositories.approved_plan_repositories import (  # noqa: E501
    V1_APPROVED_PLAN_SCHEMA_HEAD,
    PostgresApprovedPlanRepository,
)
from empirical_platform.shared.persistence.postgres_repositories.paper_execution_repositories import (  # noqa: E501
    M085_SCHEMA_HEAD,
    V1_INTEGRATED_SCHEMA_HEAD,
    PaperSchemaHeadError,
    SchemaCompatibilityError,
    require_exact_m085_schema_head,
)
from empirical_platform.shared.persistence.postgres_repositories.paper_position_exit_schema import (  # noqa: E501
    M089_SCHEMA_HEAD,
    PaperExitSchemaHeadError,
)
from empirical_platform.usecases.operator_console import OperatorConsoleService
from empirical_platform.usecases.operator_console_exits import ExitRepositories
from empirical_platform.usecases.position_plan_manager import (
    PlanManagerThread,
    PositionPlanManager,
)

pytestmark = pytest.mark.integration

#: Test-shaped, never a real Alpaca key: same convention as `test_m085_paper_composition.py`'s
#: own `_KEY`/`_KEY_TAIL`, spelled differently only so the two files' constants never collide.
_FAKE_KEY = "AKTESTKEYVALUEDEPLOY0"
_FAKE_KEY_TAIL = "TESTVALUEDEPLOY000000000000000000000000001"
_PAPER_URL = "https://paper-api.alpaca.markets"


@pytest.fixture(autouse=True)
def disposable_database_names() -> None:
    """Refuse production names before any destructive integration fixture runs."""
    if postgres_enabled():
        for name in (
            "EMPIRICAL_PLATFORM_POSTGRES_DATABASE",
            "EMPIRICAL_PLATFORM_PAPER_EXIT_POSTGRES_DATABASE",
        ):
            if not os.environ.get(name, "").endswith("_test"):
                pytest.fail(f"{name} must explicitly name a disposable _test database")


@pytest.fixture
def engine(disposable_database_names: None) -> Iterator[Engine]:
    """Store A/B, migrated the ORDINARY way -- `alembic upgrade head` -- never pinned."""
    if not postgres_enabled():
        pytest.skip("PostgreSQL integration tests require explicit opt-in")
    yield from build_engine("head")


@pytest.fixture
def engine_c(disposable_database_names: None) -> Iterator[Engine]:
    """Store C, migrated through its own separate chain to its own real head."""
    if not postgres_enabled():
        pytest.skip("PostgreSQL integration tests require explicit opt-in")
    yield from build_engine_c("head")


@pytest.fixture
def no_broker_network(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str]]:
    """Zero Alpaca HTTP calls are PERMITTED, not merely expected.

    Patched at `_StrictConnection.request` -- the one seam every Alpaca call in this
    codebase funnels through (`AlpacaPaperClient`/`AlpacaPaperMarketDataClient` both build
    one) -- so this catches a call this test did not anticipate, not only a `submit_order`.
    """
    calls: list[tuple[str, str]] = []

    def _recording_request(
        self: object, method: str, path: str, *, body: str | None = None, before_send: object = None
    ) -> tuple[int, dict[str, str], bytes]:
        calls.append((method, path))
        raise AssertionError(
            f"a real HTTP request was attempted during boot alone: {method} {path} -- "
            "boot must make zero broker calls"
        )

    monkeypatch.setattr(alpaca_paper._StrictConnection, "request", _recording_request)
    return calls


@pytest.fixture
def real_deployment_environment(
    monkeypatch: pytest.MonkeyPatch, engine: Engine, engine_c: Engine
) -> None:
    """Exactly the environment variables real deployment sets -- nothing injected into the
    composition function, which takes none of its own: `paper_operator_console_with_exit_
    runtime()` reads `os.environ` through `resolve_foundation_config()` precisely as the real
    console binary does, so driving it through the environment (not a test-only parameter)
    is what makes this the REAL deployment shape rather than a specially wired test path.
    """
    del engine, engine_c  # fixture ORDER only: the databases must exist before this runs
    monkeypatch.setenv("EMPIRICAL_ALPACA_PAPER_API_KEY", _FAKE_KEY)
    monkeypatch.setenv("EMPIRICAL_ALPACA_PAPER_SECRET_KEY", _FAKE_KEY_TAIL)
    monkeypatch.setenv("EMPIRICAL_ALPACA_PAPER_BASE_URL", _PAPER_URL)
    # Store C's database name is independent of EMPIRICAL_PLATFORM_POSTGRES_DATABASE (same
    # server, a distinct database) -- set explicitly to the SAME name `engine_c` migrated,
    # rather than assumed from ambient environment.
    monkeypatch.setenv("EMPIRICAL_PLATFORM_PAPER_EXIT_POSTGRES_DATABASE", store_c_config().database)


def test_store_a_and_b_are_the_one_reviewed_v1_head(engine: Engine) -> None:
    with engine.begin() as connection:
        revisions = [
            row[0]
            for row in connection.execute(text("SELECT version_num FROM public.alembic_version"))
        ]
    assert revisions == [V1_INTEGRATED_SCHEMA_HEAD]
    # Two independently-defined constants, in two different modules, naming the SAME
    # physical database's head -- the root cause of the reported bug, confirmed directly
    # rather than trusted from either module's own docstring.
    assert V1_INTEGRATED_SCHEMA_HEAD == V1_APPROVED_PLAN_SCHEMA_HEAD


def test_store_c_is_at_its_own_m089_head(engine_c: Engine) -> None:
    with engine_c.begin() as connection:
        revisions = [
            row[0]
            for row in connection.execute(text("SELECT version_num FROM public.alembic_version"))
        ]
    assert revisions == [M089_SCHEMA_HEAD]


def test_the_real_integrated_console_boots_against_databases_at_full_head(
    real_deployment_environment: None,
    no_broker_network: list[tuple[str, str]],
    engine: Engine,
    engine_c: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The exact scenario Release Blocker 5 found broken, reproduced and proven fixed.

    `paper_operator_console_with_exit_runtime()` -- the REAL composition the `paper-exit`
    console capability calls, not a hand-assembled stand-in for it -- against BOTH databases
    migrated the ordinary way to their real heads. Before this fix, Store A/B's old guard
    (`require_exact_m085_schema_head`) refused exactly this database; this test is the
    regression guard for that failure mode.
    """
    del engine, engine_c  # already proven at head by the two tests above; used for ordering
    with paper_operator_console_with_exit_runtime() as backend:
        assert isinstance(backend.service, OperatorConsoleService)
        assert backend.service.exits is not None  # the exit path IS composed, unlike M088 PAPER
        assert isinstance(backend._plans, PostgresApprovedPlanRepository)  # noqa: SLF001
        assert isinstance(backend._plan_manager, PositionPlanManager)  # noqa: SLF001
        assert isinstance(backend._exits, ExitRepositories)  # noqa: SLF001

        # PositionPlanManager/PlanManagerThread initialize AND run a real tick, over the
        # live Store A/Store C repositories, before anything is torn down. The
        # `approved_plan` table is empty (no plan has been approved in this disposable
        # database), so the tick's two queries (list_unclaimed/list_claimed) find nothing
        # and the loop makes no broker call -- `no_broker_network` proves that directly
        # rather than inferring it from the table being empty.
        completed = Event()
        original = PositionPlanManager.evaluate_once

        def observed_tick(self: PositionPlanManager, *, now: datetime) -> object:
            result = original(self, now=now)
            completed.set()  # only a successful real tick counts
            return result

        monkeypatch.setattr(PositionPlanManager, "evaluate_once", observed_tick)
        manager_thread = PlanManagerThread(
            backend._plan_manager,  # noqa: SLF001
            now=lambda: datetime.now(UTC),
        )
        manager_thread.start()
        try:
            assert completed.wait(timeout=10), "the real Plan Manager tick did not complete"
        finally:
            manager_thread.stop()

    assert no_broker_network == []


@pytest.mark.parametrize(
    "statement",
    [
        "UPDATE public.alembic_version SET version_num = 'unreviewed_future'",
        "DROP TABLE public.paper_reconciliation_round CASCADE",
        "ALTER TABLE public.trade_proposal DROP COLUMN risk_contract",
        "ALTER TABLE public.approved_order_intent DISABLE TRIGGER v1_entry_risk_guard",
        "CREATE OR REPLACE FUNCTION public.v1_entry_risk_guard() "
        "RETURNS trigger AS $$ BEGIN RETURN NEW; END; $$ LANGUAGE plpgsql",
        "ALTER TABLE public.paper_execution_attempt DROP COLUMN state CASCADE",
        "ALTER TABLE public.paper_execution_attempt DISABLE TRIGGER "
        "paper_execution_attempt_guard_update_trigger",
        "ALTER TABLE public.paper_execution_attempt DROP CONSTRAINT "
        "uq_paper_attempt_one_per_intent",
        "CREATE OR REPLACE FUNCTION "
        "public.paper_execution_attempt_guard_update() "
        "RETURNS trigger AS $$ BEGIN RETURN NEW; END; $$ LANGUAGE plpgsql",
    ],
)
def test_incompatible_main_contract_refuses_real_boot(
    real_deployment_environment: None,
    no_broker_network: list[tuple[str, str]],
    engine: Engine,
    statement: str,
) -> None:
    # Function-scoped disposable databases are recreated for each corruption case.
    with engine.begin() as connection:
        connection.execute(text(statement))
    with pytest.raises(SchemaCompatibilityError):
        with paper_operator_console_with_exit_runtime():
            pytest.fail("incompatible main database was accepted")
    assert no_broker_network == []


def test_wrong_store_c_head_refuses_real_boot(
    real_deployment_environment: None,
    no_broker_network: list[tuple[str, str]],
    engine_c: Engine,
) -> None:
    with engine_c.begin() as connection:
        connection.execute(
            text("UPDATE public.alembic_version SET version_num = 'unreviewed_future'")
        )
    with pytest.raises(PaperExitSchemaHeadError):
        with paper_operator_console_with_exit_runtime():
            pytest.fail("incompatible Store C was accepted")
    assert no_broker_network == []


def test_historical_guard_still_rejects_full_head(engine: Engine) -> None:
    from tests.integration._m085_support import config

    from empirical_platform.shared.persistence.postgres import PostgresPersistenceService

    service = PostgresPersistenceService(config())
    service.initialize()
    try:
        with pytest.raises(PaperSchemaHeadError):
            require_exact_m085_schema_head(service)
    finally:
        service.close()


def test_contract_is_the_unchanged_historical_m085_contract() -> None:
    from empirical_platform.shared.persistence.postgres_repositories.paper_execution_repositories import (  # noqa: E501
        _M085_REQUIRED_TABLES,
    )
    from empirical_platform.shared.persistence.postgres_repositories.paper_schema_contract import (
        M085_CONTRACT,
        M085_CONTRACT_SELECT,
    )

    if not postgres_enabled():
        pytest.skip("PostgreSQL integration tests require explicit opt-in")
    for historical_engine in build_engine(M085_SCHEMA_HEAD):
        with historical_engine.connect() as connection:
            rows = connection.execute(
                text(M085_CONTRACT_SELECT), {"tables": list(_M085_REQUIRED_TABLES)}
            )
            assert dict(rows.tuples().all()) == M085_CONTRACT
