"""MILESTONE-076 -- operator-asserted position ledger against real PostgreSQL.

Includes migration up->down->up, database round-trip equality, duplicate
rejection at the constraint level, and raw-SQL inspection independent of the
repository helpers.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
import sqlalchemy as sa
from alembic import command as alembic_command
from alembic.config import Config
from pydantic import SecretStr
from sqlalchemy import Engine, text

from empirical_platform.decision_candidate.operator_position_ledger import (
    LedgerRejectionError,
    OperatorAssertedPositionEvent,
    OperatorPositionEventKind,
)
from empirical_platform.entrypoints._composition import postgres_repository_runtime
from empirical_platform.shared.config.settings import PostgreSQLConfigSnapshot
from empirical_platform.shared.contracts.repository import AggregateAlreadyExists
from empirical_platform.usecases.get_operator_position_state import (
    GetOperatorPositionStateHandler,
    GetOperatorPositionStateQuery,
)
from empirical_platform.usecases.operator_position_ledger_io import (
    render_operator_position_state_json,
    render_operator_position_state_text,
)
from empirical_platform.usecases.record_operator_position_event import (
    RecordOperatorPositionEventCommand,
    RecordOperatorPositionEventHandler,
)

_REPO_ROOT = __import__("pathlib").Path(__file__).resolve().parents[2]
_T0 = datetime(2026, 4, 1, 14, 30, tzinfo=UTC)


def _postgres_enabled() -> bool:
    return os.environ.get("EMPIRICAL_PLATFORM_RUN_POSTGRES_TESTS") == "1"


def _config() -> PostgreSQLConfigSnapshot:
    return PostgreSQLConfigSnapshot(
        host=os.environ.get("EMPIRICAL_PLATFORM_POSTGRES_HOST", "localhost"),
        port=int(os.environ.get("EMPIRICAL_PLATFORM_POSTGRES_PORT", "5432")),
        database=os.environ.get("EMPIRICAL_PLATFORM_POSTGRES_DATABASE", "empirical_platform"),
        user=os.environ.get("EMPIRICAL_PLATFORM_POSTGRES_USER", "empirical"),
        password=SecretStr(os.environ["EMPIRICAL_PLATFORM_POSTGRES_PASSWORD"]),
        pool_size=2,
        max_overflow=0,
        connection_timeout_seconds=5,
        application_name="empirical-platform-m076-test",
    )


def _alembic_config() -> Config:
    cfg = Config(str(_REPO_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(_REPO_ROOT / "migrations"))
    return cfg


def _reset(engine: Engine) -> None:
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))


@pytest.fixture(scope="module")
def engine() -> Iterator[Engine]:
    if not _postgres_enabled():
        pytest.skip("PostgreSQL integration tests require explicit opt-in")
    eng = sa.create_engine(_config().sqlalchemy_url())
    try:
        yield eng
    finally:
        eng.dispose()


@pytest.fixture(scope="module")
def upgraded_schema(engine: Engine) -> Iterator[Engine]:
    _reset(engine)
    alembic_command.upgrade(_alembic_config(), "head")
    yield engine
    _reset(engine)


@pytest.fixture
def clean_tables(upgraded_schema: Engine) -> Engine:
    with upgraded_schema.begin() as conn:
        conn.execute(text("TRUNCATE operator_position_event CASCADE"))
    return upgraded_schema


def _ev(
    gid: str,
    kind: str,
    *,
    pos: str,
    symbol: str,
    qty: int,
    price: str,
    day: int,
    plan: str | None = None,
) -> OperatorAssertedPositionEvent:
    return OperatorAssertedPositionEvent(
        governance_id=gid,
        runtime_id=f"00000000-0000-4000-8000-{abs(hash(gid)) % 10**12:012d}",
        position_governance_id=pos,
        instrument_symbol=symbol,
        kind=OperatorPositionEventKind[kind],
        quantity=qty,
        asserted_price=Decimal(price),
        event_timestamp=_T0 + timedelta(days=day),
        recorded_at=_T0 + timedelta(days=40),
        source_position_plan_governance_id=plan,
    )


def _record(config: PostgreSQLConfigSnapshot, event: OperatorAssertedPositionEvent) -> object:
    with postgres_repository_runtime(config) as runtime:
        handler = RecordOperatorPositionEventHandler(
            ledger_repository=runtime.operator_position_ledger
        )
        return handler.handle(RecordOperatorPositionEventCommand(event=event))


def _state(config: PostgreSQLConfigSnapshot, as_of: datetime) -> object:
    with postgres_repository_runtime(config) as runtime:
        handler = GetOperatorPositionStateHandler(
            ledger_repository=runtime.operator_position_ledger
        )
        return handler.handle(GetOperatorPositionStateQuery(as_of=as_of))


def test_m076_full_lifecycle_with_raw_sql_verification(clean_tables: Engine) -> None:
    config = _config()
    _record(
        config,
        _ev(
            "EV-7601",
            "OPENED",
            pos="POS-A",
            symbol="AAPL",
            qty=100,
            price="150.25",
            day=0,
            plan="POSP-1",
        ),
    )
    _record(
        config, _ev("EV-7602", "REDUCED", pos="POS-A", symbol="AAPL", qty=40, price="161.00", day=2)
    )

    state = _state(config, _T0 + timedelta(days=3))
    assert state.total_open_quantity == 60  # type: ignore[attr-defined]
    assert state.open_positions[0].asserted_open_notional == "9015"  # type: ignore[attr-defined]

    # Raw SQL, independent of the repository helpers.
    with clean_tables.begin() as conn:
        rows = list(
            conn.execute(
                text(
                    "SELECT governance_id, event_kind, quantity, asserted_price, "
                    "source_position_plan_governance_id FROM operator_position_event "
                    "ORDER BY event_timestamp, governance_id"
                )
            ).mappings()
        )
    assert [r["event_kind"] for r in rows] == ["OPENED", "REDUCED"]
    assert [int(r["quantity"]) for r in rows] == [100, 40]
    assert rows[0]["source_position_plan_governance_id"] == "POSP-1"
    assert rows[1]["source_position_plan_governance_id"] is None

    closed = _record(
        config, _ev("EV-7603", "CLOSED", pos="POS-A", symbol="AAPL", qty=0, price="170", day=5)
    )
    assert closed.quantity == 60  # type: ignore[attr-defined]  # derived, not supplied
    after = _state(config, _T0 + timedelta(days=6))
    assert after.open_positions == ()  # type: ignore[attr-defined]
    assert len(after.closed_positions) == 1  # type: ignore[attr-defined]


def test_m076_database_round_trip_preserves_every_field(clean_tables: Engine) -> None:
    config = _config()
    original = _ev(
        "EV-7610",
        "OPENED",
        pos="POS-R",
        symbol="NVDA",
        qty=7,
        price="900.123456",
        day=1,
        plan="POSP-9",
    )
    _record(config, original)
    with postgres_repository_runtime(config) as runtime:
        loaded = runtime.operator_position_ledger.list_for_position("POS-R")
    assert len(loaded) == 1
    assert loaded[0] == original


def test_m076_duplicate_event_is_rejected_by_the_database_constraint(
    clean_tables: Engine,
) -> None:
    config = _config()
    event = _ev("EV-7620", "OPENED", pos="POS-D", symbol="AAPL", qty=10, price="100", day=0)
    _record(config, event)
    # The domain rejects it first...
    with pytest.raises(LedgerRejectionError):
        _record(config, event)
    # ...and the unique constraint is the durable backstop.
    with postgres_repository_runtime(config) as runtime:
        with pytest.raises(AggregateAlreadyExists):
            runtime.operator_position_ledger.append(event)
    with clean_tables.begin() as conn:
        count = conn.execute(text("SELECT count(*) FROM operator_position_event")).scalar_one()
    assert count == 1


def test_m076_future_events_excluded_and_boundary_inclusive(clean_tables: Engine) -> None:
    config = _config()
    _record(
        config, _ev("EV-7630", "OPENED", pos="POS-F", symbol="MSFT", qty=20, price="400", day=0)
    )
    _record(
        config, _ev("EV-7631", "CLOSED", pos="POS-F", symbol="MSFT", qty=0, price="410", day=10)
    )
    past = _state(config, _T0 + timedelta(days=1))
    assert past.total_open_quantity == 20  # type: ignore[attr-defined]
    assert past.excluded_future_event_count == 1  # type: ignore[attr-defined]
    boundary = _state(config, _T0)
    assert boundary.total_open_quantity == 20  # type: ignore[attr-defined]


def test_m076_out_of_order_backdated_insert_is_rejected(clean_tables: Engine) -> None:
    config = _config()
    _record(
        config, _ev("EV-7640", "OPENED", pos="POS-B", symbol="AAPL", qty=10, price="100", day=0)
    )
    _record(config, _ev("EV-7641", "CLOSED", pos="POS-B", symbol="AAPL", qty=0, price="110", day=6))
    with pytest.raises(LedgerRejectionError):
        _record(
            config, _ev("EV-7642", "OPENED", pos="POS-B", symbol="AAPL", qty=5, price="105", day=3)
        )
    with clean_tables.begin() as conn:
        count = conn.execute(text("SELECT count(*) FROM operator_position_event")).scalar_one()
    assert count == 2


def test_m076_text_and_json_agree(clean_tables: Engine) -> None:
    config = _config()
    _record(config, _ev("EV-7650", "OPENED", pos="POS-J", symbol="TSLA", qty=3, price="250", day=0))
    state = _state(config, _T0 + timedelta(days=1))
    payload = render_operator_position_state_json(state)  # type: ignore[arg-type]
    rendered = render_operator_position_state_text(state)  # type: ignore[arg-type]
    assert payload["total_open_quantity"] == 3
    assert payload["total_asserted_open_notional"] == "750"
    assert "TSLA" in rendered
    assert "750" in rendered
    assert "NOT a broker record" in rendered


def test_m076_migration_is_reversible(engine: Engine) -> None:
    """up -> down -> up, proving downgrade() genuinely works."""
    cfg = _alembic_config()
    _reset(engine)
    alembic_command.upgrade(cfg, "head")
    with engine.begin() as conn:
        assert (
            conn.execute(text("SELECT to_regclass('public.operator_position_event')")).scalar_one()
            is not None
        )
    alembic_command.downgrade(cfg, "-1")
    with engine.begin() as conn:
        assert (
            conn.execute(text("SELECT to_regclass('public.operator_position_event')")).scalar_one()
            is None
        )
    alembic_command.upgrade(cfg, "head")
    with engine.begin() as conn:
        assert (
            conn.execute(text("SELECT to_regclass('public.operator_position_event')")).scalar_one()
            is not None
        )
