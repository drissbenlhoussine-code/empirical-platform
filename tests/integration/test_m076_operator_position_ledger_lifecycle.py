"""MILESTONE-076 -- operator-asserted position ledger against real PostgreSQL.

Includes migration up->down->up, database round-trip equality, duplicate
rejection at the constraint level, and raw-SQL inspection independent of the
repository helpers.
"""

from __future__ import annotations

import os
import threading
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal

import pytest
import sqlalchemy as sa
from alembic import command as alembic_command
from alembic.config import Config
from pydantic import SecretStr
from sqlalchemy import Engine, text

from empirical_platform.decision_candidate.operator_position_ledger import (
    LedgerRejectionError,
    LedgerRejectionReason,
    OperatorAssertedPositionEvent,
    OperatorPositionEventKind,
)
from empirical_platform.entrypoints._composition import postgres_repository_runtime
from empirical_platform.shared.config.settings import PostgreSQLConfigSnapshot
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
    """The domain rejects a duplicate first, and the UNIQUE constraint is the
    durable backstop underneath it.

    Since the owner correction there is no unvalidated `append` to call, so the
    constraint is proven where it actually lives: a raw duplicate INSERT must be
    refused by PostgreSQL itself.
    """
    config = _config()
    event = _ev("EV-7620", "OPENED", pos="POS-D", symbol="AAPL", qty=10, price="100", day=0)
    _record(config, event)

    # 1. the domain refuses it
    with pytest.raises(LedgerRejectionError) as exc:
        _record(config, event)
    assert exc.value.reason is LedgerRejectionReason.DUPLICATE_EVENT_GOVERNANCE_ID

    # 2. and the database refuses it even when the domain is bypassed entirely
    with pytest.raises(Exception) as raw:  # noqa: B017 - driver error type varies
        with clean_tables.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO operator_position_event (runtime_id, governance_id, "
                    "position_governance_id, instrument_symbol, event_kind, quantity, "
                    "asserted_price, event_timestamp, recorded_at) VALUES "
                    "('rt-dup', 'EV-7620', 'POS-D', 'AAPL', 'OPENED', 1, 1, "
                    "'2026-04-01T00:00:00+00', '2026-04-01T00:00:00+00')"
                )
            )
    assert "uq_operator_position_event_governance_id" in str(raw.value)

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


# --------------------------------------------------------------------------
# MILESTONE-076 owner correction, Finding 1: genuine concurrency attacks
# --------------------------------------------------------------------------


def _concurrent(
    config: PostgreSQLConfigSnapshot, events: list[OperatorAssertedPositionEvent]
) -> list[object]:
    """Run each event through its OWN runtime/connection, genuinely in parallel.

    A barrier makes every worker reach the write at the same moment, so the
    race this is attacking is actually exercised rather than serialised by
    thread start-up latency.
    """
    barrier = threading.Barrier(len(events))

    def worker(event: OperatorAssertedPositionEvent) -> object:
        barrier.wait(timeout=30)
        try:
            return _record(config, event)
        except Exception as exc:  # noqa: BLE001 - the outcome IS the assertion
            return exc

    with ThreadPoolExecutor(max_workers=len(events)) as pool:
        return [f.result() for f in [pool.submit(worker, e) for e in events]]


def _fold_succeeds(config: PostgreSQLConfigSnapshot) -> object:
    """The persisted ledger must always fold. If concurrency corrupted it, the
    canonical fold raises and this fails."""
    return _state(config, _T0 + timedelta(days=365))


def test_m076_concurrent_reductions_cannot_both_succeed(clean_tables: Engine) -> None:
    """The exact attack the owner specified: open 10, then two concurrent
    REDUCED(6). 6 + 6 = 12 > 10, so exactly one must win and the loser must be
    coherently rejected after seeing committed state."""
    config = _config()
    _record(
        config, _ev("EV-C01", "OPENED", pos="POS-RACE", symbol="AAPL", qty=10, price="100", day=0)
    )

    results = _concurrent(
        config,
        [
            _ev("EV-C02", "REDUCED", pos="POS-RACE", symbol="AAPL", qty=6, price="101", day=1),
            _ev("EV-C03", "REDUCED", pos="POS-RACE", symbol="AAPL", qty=6, price="102", day=1),
        ],
    )
    succeeded = [r for r in results if not isinstance(r, Exception)]
    rejected = [r for r in results if isinstance(r, LedgerRejectionError)]
    assert len(succeeded) == 1, f"expected exactly one winner, got {results}"
    assert len(rejected) == 1, f"expected one coherent rejection, got {results}"
    assert rejected[0].reason is LedgerRejectionReason.REDUCTION_EXCEEDS_OPEN_QUANTITY

    with clean_tables.begin() as conn:
        count = conn.execute(text("SELECT count(*) FROM operator_position_event")).scalar_one()
    assert count == 2  # the opening and exactly one reduction
    state = _fold_succeeds(config)
    assert state.total_open_quantity == 4  # type: ignore[attr-defined]


def test_m076_concurrent_opens_on_one_position_cannot_both_succeed(
    clean_tables: Engine,
) -> None:
    config = _config()
    results = _concurrent(
        config,
        [
            _ev("EV-C10", "OPENED", pos="POS-DUAL", symbol="MSFT", qty=5, price="400", day=0),
            _ev("EV-C11", "OPENED", pos="POS-DUAL", symbol="MSFT", qty=7, price="401", day=0),
        ],
    )
    succeeded = [r for r in results if not isinstance(r, Exception)]
    rejected = [r for r in results if isinstance(r, LedgerRejectionError)]
    assert len(succeeded) == 1, f"expected exactly one winner, got {results}"
    assert rejected[0].reason is LedgerRejectionReason.POSITION_ALREADY_OPEN
    with clean_tables.begin() as conn:
        count = conn.execute(text("SELECT count(*) FROM operator_position_event")).scalar_one()
    assert count == 1
    _fold_succeeds(config)


def test_m076_concurrent_identical_event_ids_persist_once(clean_tables: Engine) -> None:
    """Duplicate identity under contention: the domain check and the unique
    constraint must between them let exactly one row through."""
    config = _config()
    _record(
        config, _ev("EV-C20", "OPENED", pos="POS-DUP", symbol="NVDA", qty=9, price="800", day=0)
    )
    same = _ev("EV-C21", "REDUCED", pos="POS-DUP", symbol="NVDA", qty=2, price="810", day=1)
    results = _concurrent(config, [same, same])
    succeeded = [r for r in results if not isinstance(r, Exception)]
    assert len(succeeded) == 1, f"expected exactly one winner, got {results}"
    with clean_tables.begin() as conn:
        rows = (
            conn.execute(
                text("SELECT governance_id FROM operator_position_event ORDER BY governance_id")
            )
            .scalars()
            .all()
        )
    assert rows == ["EV-C20", "EV-C21"]
    _fold_succeeds(config)


def test_m076_concurrent_writers_to_different_positions_do_not_block_each_other(
    clean_tables: Engine,
) -> None:
    """The lock key is the position id, so unrelated positions must both win --
    otherwise the fix would have serialised the whole ledger."""
    config = _config()
    results = _concurrent(
        config,
        [
            _ev("EV-C30", "OPENED", pos="POS-X", symbol="AAPL", qty=1, price="100", day=0),
            _ev("EV-C31", "OPENED", pos="POS-Y", symbol="MSFT", qty=2, price="200", day=0),
        ],
    )
    assert all(not isinstance(r, Exception) for r in results), results
    state = _fold_succeeds(config)
    assert len(state.open_positions) == 2  # type: ignore[attr-defined]


# --------------------------------------------------------------------------
# Findings 2 and 3 through real persistence
# --------------------------------------------------------------------------


def test_m076_price_at_max_precision_round_trips_exactly(clean_tables: Engine) -> None:
    config = _config()
    price = Decimal("123.456789")  # exactly six decimal places
    original = _ev("EV-P01", "OPENED", pos="POS-P", symbol="AAPL", qty=2, price=str(price), day=0)
    _record(config, original)
    with postgres_repository_runtime(config) as runtime:
        loaded = runtime.operator_position_ledger.list_for_position("POS-P")
    assert loaded[0].asserted_price == price
    assert loaded[0] == original  # full semantic equality after reload


def test_m076_price_beyond_six_decimals_is_refused_before_persistence(
    clean_tables: Engine,
) -> None:
    """NUMERIC(20,6) would silently round this, so the domain refuses it."""
    with pytest.raises(LedgerRejectionError) as exc:
        _ev("EV-P02", "OPENED", pos="POS-Q", symbol="AAPL", qty=1, price="1.1234567", day=0)
    assert exc.value.reason is LedgerRejectionReason.ASSERTED_PRICE_PRECISION_EXCEEDED
    with clean_tables.begin() as conn:
        count = conn.execute(text("SELECT count(*) FROM operator_position_event")).scalar_one()
    assert count == 0


def test_m076_mixed_timezone_offsets_for_one_instant_agree(clean_tables: Engine) -> None:
    """Two events written with different offsets representing the SAME instant
    must be treated as the same instant, before and after a round trip."""
    config = _config()
    utc_moment = datetime(2026, 4, 5, 12, 0, tzinfo=UTC)
    plus_two = datetime(2026, 4, 5, 14, 0, tzinfo=timezone(timedelta(hours=2)))
    assert utc_moment == plus_two
    _record(
        config,
        OperatorAssertedPositionEvent(
            governance_id="EV-TZ1",
            runtime_id="00000000-0000-4000-8000-000000000901",
            position_governance_id="POS-TZ",
            instrument_symbol="AAPL",
            kind=OperatorPositionEventKind.OPENED,
            quantity=4,
            asserted_price=Decimal("50"),
            event_timestamp=plus_two,
            recorded_at=utc_moment,
        ),
    )
    at_boundary = _state(config, utc_moment)
    assert at_boundary.total_open_quantity == 4  # type: ignore[attr-defined]
    just_before = _state(config, utc_moment - timedelta(seconds=1))
    assert just_before.total_open_quantity == 0  # type: ignore[attr-defined]
