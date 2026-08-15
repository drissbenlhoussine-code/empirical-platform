"""MILESTONE-080 -- asserted round-trip arithmetic against real PostgreSQL.

Every figure the report emits is cross-checked against raw SQL read
independently of the repository helpers. Scaffolding is reused from the M079
integration suite.

The mandated adversarial position:

    OPENED  q=10  price=100
    REDUCED q=4   price=110
    CLOSED  q=6   price=90     <- quantity DERIVED by frozen M076

with `recorded_at` staggered so the opening is known early, the reduction later
and the close later still.
"""

from __future__ import annotations

import os
import threading
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command as alembic_command
from alembic.config import Config
from pydantic import SecretStr
from sqlalchemy import text
from sqlalchemy.engine import Engine

from empirical_platform.decision_candidate.operator_asserted_round_trip import (
    AssertedRoundTripReport,
    RoundTripOutcome,
    RoundTripStatus,
)
from empirical_platform.decision_candidate.operator_position_ledger import (
    OperatorAssertedPositionEvent,
    OperatorPositionEventKind,
    derive_position_state,
)
from empirical_platform.entrypoints._composition import postgres_repository_runtime
from empirical_platform.shared.config.settings import PostgreSQLConfigSnapshot
from empirical_platform.usecases.asserted_round_trip_io import (
    render_round_trip_report_json,
    render_round_trip_report_text,
)
from empirical_platform.usecases.get_asserted_round_trip_report import (
    GetAssertedRoundTripReportHandler,
    GetAssertedRoundTripReportQuery,
)

pytestmark = pytest.mark.integration

_REPO_ROOT = Path(__file__).resolve().parents[2]
_T0 = datetime(2026, 5, 1, tzinfo=UTC)

_ALL_TABLES = ["operator_position_event"]

_E1 = _T0 + timedelta(days=1)  # OPENED  effective
_E2 = _T0 + timedelta(days=2)  # REDUCED effective
_E3 = _T0 + timedelta(days=3)  # CLOSED  effective
_K1 = _T0 + timedelta(days=1)  # only the opening is recorded
_K2 = _T0 + timedelta(days=5)  # the reduction is now recorded
_K3 = _T0 + timedelta(days=9)  # the close is now recorded
_NOW = _T0 + timedelta(days=60)


def _postgres_enabled() -> bool:
    return os.environ.get("EMPIRICAL_PLATFORM_RUN_POSTGRES_TESTS") == "1"


def _config(database: str | None = None) -> PostgreSQLConfigSnapshot:
    return PostgreSQLConfigSnapshot(
        host=os.environ.get("EMPIRICAL_PLATFORM_POSTGRES_HOST", "localhost"),
        port=int(os.environ.get("EMPIRICAL_PLATFORM_POSTGRES_PORT", "5432")),
        database=database
        or os.environ.get("EMPIRICAL_PLATFORM_POSTGRES_DATABASE", "empirical_platform"),
        user=os.environ.get("EMPIRICAL_PLATFORM_POSTGRES_USER", "empirical"),
        password=SecretStr(os.environ["EMPIRICAL_PLATFORM_POSTGRES_PASSWORD"]),
        pool_size=2,
        max_overflow=0,
        connection_timeout_seconds=5,
        application_name="empirical-platform-m080-test",
    )


def _alembic_config() -> Config:
    cfg = Config(str(_REPO_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(_REPO_ROOT / "migrations"))
    return cfg


def _reset_public_schema(engine: Engine) -> None:
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
    _reset_public_schema(engine)
    alembic_command.upgrade(_alembic_config(), "head")
    yield engine
    _reset_public_schema(engine)


@pytest.fixture
def clean_tables(upgraded_schema: Engine) -> Engine:
    with upgraded_schema.begin() as conn:
        conn.execute(text(f"TRUNCATE {', '.join(_ALL_TABLES)} CASCADE"))  # noqa: S608
    return upgraded_schema


def _record(
    config: PostgreSQLConfigSnapshot,
    *,
    gid: str,
    pos: str,
    symbol: str,
    kind: OperatorPositionEventKind,
    quantity: int,
    price: str,
    effective: datetime,
    recorded: datetime,
    plan: str | None = None,
) -> None:
    """Append through the REAL M076 repository, so quantities are derived as in production."""
    with postgres_repository_runtime(config) as runtime:
        runtime.operator_position_ledger.append_validated(
            OperatorAssertedPositionEvent(
                governance_id=gid,
                runtime_id=f"rt-{gid}",
                position_governance_id=pos,
                instrument_symbol=symbol,
                kind=kind,
                quantity=quantity,
                asserted_price=Decimal(price),
                event_timestamp=effective,
                recorded_at=recorded,
                source_position_plan_governance_id=plan,
            )
        )


def _report(
    config: PostgreSQLConfigSnapshot,
    *,
    effective: datetime,
    knowledge: datetime,
    with_ledger: bool = True,
) -> AssertedRoundTripReport:
    with postgres_repository_runtime(config) as runtime:
        handler = GetAssertedRoundTripReportHandler(
            operator_position_ledger_repository=(
                runtime.operator_position_ledger if with_ledger else None
            )
        )
        return handler.handle(
            GetAssertedRoundTripReportQuery(effective_as_of=effective, knowledge_as_of=knowledge)
        )


def _seed_mandated_position(
    config: PostgreSQLConfigSnapshot,
    *,
    pos: str = "POS-8001",
    symbol: str = "AAPL",
    plan: str | None = "PLAN-8001",
) -> None:
    """OPENED 10@100 (rec K1), REDUCED 4@110 (rec K2), CLOSED 6@90 (rec K3)."""
    _record(
        config,
        gid=f"OPEV-{pos}-O",
        pos=pos,
        symbol=symbol,
        kind=OperatorPositionEventKind.OPENED,
        quantity=10,
        price="100",
        effective=_E1,
        recorded=_K1,
        plan=plan,
    )
    _record(
        config,
        gid=f"OPEV-{pos}-R",
        pos=pos,
        symbol=symbol,
        kind=OperatorPositionEventKind.REDUCED,
        quantity=4,
        price="110",
        effective=_E2,
        recorded=_K2,
    )
    _record(
        config,
        gid=f"OPEV-{pos}-C",
        pos=pos,
        symbol=symbol,
        kind=OperatorPositionEventKind.CLOSED,
        quantity=0,  # derived by frozen M076
        price="90",
        effective=_E3,
        recorded=_K3,
    )


# ---------------------------------------------------------------------------
# The arithmetic over genuinely persisted rows
# ---------------------------------------------------------------------------


def test_m080_mandated_position_arithmetic_over_real_rows(clean_tables: Engine) -> None:
    config = _config()
    _seed_mandated_position(config)
    entry = _report(config, effective=_NOW, knowledge=_NOW).entries[0]

    assert entry.status is RoundTripStatus.FULLY_EXITED_ASSERTED
    assert (entry.opened_quantity, entry.exited_quantity, entry.still_open_quantity) == (10, 10, 0)
    assert entry.asserted_entry_cost_for_exited_quantity == "1000"
    assert entry.asserted_exit_consideration == "980"
    assert entry.asserted_round_trip_result == "-20"
    assert entry.cited_position_plan_governance_id == "PLAN-8001"


def test_m080_raw_sql_independently_confirms_every_input(clean_tables: Engine) -> None:
    """Independent of every repository helper."""
    config = _config()
    _seed_mandated_position(config)
    with clean_tables.begin() as conn:
        rows = conn.execute(
            text(
                "SELECT governance_id, event_kind, quantity, asserted_price, "
                "event_timestamp, recorded_at FROM operator_position_event "
                "ORDER BY event_timestamp"
            )
        ).fetchall()
    by_kind = {r.event_kind: r for r in rows}

    assert by_kind["OPENED"].quantity == 10
    assert by_kind["OPENED"].asserted_price == Decimal("100.000000")
    assert by_kind["OPENED"].event_timestamp == _E1
    assert by_kind["OPENED"].recorded_at == _K1
    assert by_kind["REDUCED"].quantity == 4
    assert by_kind["REDUCED"].asserted_price == Decimal("110.000000")
    assert by_kind["REDUCED"].recorded_at == _K2
    # The CLOSED quantity was DERIVED by frozen M076, not supplied.
    assert by_kind["CLOSED"].quantity == 6
    assert by_kind["CLOSED"].asserted_price == Decimal("90.000000")
    assert by_kind["CLOSED"].recorded_at == _K3

    consideration = (
        by_kind["REDUCED"].quantity * by_kind["REDUCED"].asserted_price
        + by_kind["CLOSED"].quantity * by_kind["CLOSED"].asserted_price
    )
    cost = 10 * by_kind["OPENED"].asserted_price
    entry = _report(config, effective=_NOW, knowledge=_NOW).entries[0]
    assert Decimal(entry.asserted_exit_consideration or "0") == consideration
    assert Decimal(entry.asserted_round_trip_result or "0") == consideration - cost


def test_m080_arithmetic_evolves_only_as_evidence_is_recorded(clean_tables: Engine) -> None:
    """Three knowledge cutoffs over one persisted timeline."""
    config = _config()
    _seed_mandated_position(config)

    at_k1 = _report(config, effective=_NOW, knowledge=_K1).entries[0]
    assert at_k1.status is RoundTripStatus.NO_EXIT_ASSERTED_YET
    assert at_k1.asserted_round_trip_result is None

    at_k2 = _report(config, effective=_NOW, knowledge=_K2).entries[0]
    assert at_k2.status is RoundTripStatus.PARTIAL_EXIT_ASSERTED
    assert at_k2.exited_quantity == 4
    assert at_k2.still_open_quantity == 6
    assert at_k2.asserted_round_trip_result == "40"  # 4*110 - 4*100

    at_k3 = _report(config, effective=_NOW, knowledge=_K3).entries[0]
    assert at_k3.status is RoundTripStatus.FULLY_EXITED_ASSERTED
    assert at_k3.asserted_round_trip_result == "-20"


def test_m080_raw_sql_eligibility_agrees_at_each_cutoff(clean_tables: Engine) -> None:
    config = _config()
    _seed_mandated_position(config)
    for cutoff, expected in ((_K1, 1), (_K2, 2), (_K3, 3)):
        with clean_tables.begin() as conn:
            eligible = conn.execute(
                text(
                    "SELECT count(*) FROM operator_position_event "
                    "WHERE event_timestamp <= :e AND recorded_at <= :k"
                ),
                {"e": _NOW, "k": cutoff},
            ).scalar_one()
        assert eligible == expected
        assert _report(config, effective=_NOW, knowledge=cutoff).visible_event_count == eligible


def test_m080_leaves_m076_free_to_see_every_event(clean_tables: Engine) -> None:
    """M080 hides what M079's firewall hides; M076 still sees everything."""
    config = _config()
    _seed_mandated_position(config)
    hidden = _report(config, effective=_NOW, knowledge=_K1)
    assert hidden.visible_event_count == 1

    with postgres_repository_runtime(config) as runtime:
        all_events = runtime.operator_position_ledger.list_all()
        m076 = derive_position_state(events=all_events, as_of=_NOW)

    assert len(all_events) == 3
    assert len(m076.closed_positions) == 1
    assert _report(config, effective=_NOW, knowledge=_K1) == hidden


def test_m080_text_and_json_agree_over_real_rows(clean_tables: Engine) -> None:
    config = _config()
    _seed_mandated_position(config)
    report = _report(config, effective=_NOW, knowledge=_NOW)
    payload = render_round_trip_report_json(report)
    rendered = render_round_trip_report_text(report)

    assert payload["entries"][0]["asserted_round_trip_result"] == "-20"  # type: ignore[index]
    assert "-20" in rendered
    assert "FULLY_EXITED_ASSERTED" in rendered
    assert "excluded_by_knowledge_cutoff" not in payload
    assert "commissions" in rendered


def test_m080_numeric_round_trip_renders_identically_from_postgres(
    clean_tables: Engine,
) -> None:
    """A six-decimal price reloaded from NUMERIC(20,6) must render as it was written."""
    config = _config()
    _record(
        config,
        gid="OPEV-8100-O",
        pos="POS-8100",
        symbol="SMCI",
        kind=OperatorPositionEventKind.OPENED,
        quantity=3,
        price="1.234567",
        effective=_E1,
        recorded=_K1,
    )
    _record(
        config,
        gid="OPEV-8100-C",
        pos="POS-8100",
        symbol="SMCI",
        kind=OperatorPositionEventKind.CLOSED,
        quantity=0,
        price="2.345678",
        effective=_E2,
        recorded=_K2,
    )
    entry = _report(config, effective=_NOW, knowledge=_NOW).entries[0]
    assert entry.asserted_entry_cost_for_exited_quantity == "3.703701"
    assert entry.asserted_exit_consideration == "7.037034"
    assert entry.asserted_round_trip_result == "3.333333"


def test_m080_missing_ledger_is_withheld(clean_tables: Engine) -> None:
    report = _report(_config(), effective=_NOW, knowledge=_NOW, with_ledger=False)
    assert report.outcome is RoundTripOutcome.NOT_ASSESSABLE
    assert report.entries == ()


def test_m080_is_deterministic_across_two_independent_reads(clean_tables: Engine) -> None:
    config = _config()
    _seed_mandated_position(config)
    assert _report(config, effective=_NOW, knowledge=_NOW) == _report(
        config, effective=_NOW, knowledge=_NOW
    )


def test_m080_reads_a_consistent_snapshot_while_a_writer_appends(
    clean_tables: Engine,
) -> None:
    config = _config()
    _seed_mandated_position(config)
    barrier = threading.Barrier(2)

    def writer() -> None:
        barrier.wait(timeout=20)
        _record(
            config,
            gid="OPEV-8200-O",
            pos="POS-8200",
            symbol="TSLA",
            kind=OperatorPositionEventKind.OPENED,
            quantity=1,
            price="10",
            effective=_E1,
            recorded=_K1,
        )

    def reader() -> AssertedRoundTripReport:
        barrier.wait(timeout=20)
        return _report(config, effective=_NOW, knowledge=_NOW)

    with ThreadPoolExecutor(max_workers=2) as pool:
        writer_future = pool.submit(writer)
        reader_future = pool.submit(reader)
        writer_future.result(timeout=60)
        observed = reader_future.result(timeout=60)

    assert len(observed.entries) in {1, 2}
    assert len(_report(config, effective=_NOW, knowledge=_NOW).entries) == 2


# ---------------------------------------------------------------------------
# The double-database temporal leak proof (mission section 16)
#
# Two physical databases whose rows with `recorded_at <= K` are identical, and
# whose futures after K are radically different. At K the FULL report objects,
# their text and their JSON must all be identical -- not merely the amount.
# ---------------------------------------------------------------------------

_PROBE_DATABASE = "m080_leak_probe"


@pytest.fixture
def probe_database(clean_tables: Engine) -> Iterator[PostgreSQLConfigSnapshot]:
    """A SECOND physical database, created empty and migrated from scratch."""
    admin = sa.create_engine(_config().sqlalchemy_url(), isolation_level="AUTOCOMMIT")
    try:
        with admin.connect() as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{_PROBE_DATABASE}" WITH (FORCE)'))
            conn.execute(text(f'CREATE DATABASE "{_PROBE_DATABASE}"'))
    finally:
        admin.dispose()

    # alembic resolves its target from the environment, so the override is
    # scoped to the migration alone. Leaving it set across the yield would point
    # _config() at the probe database too, and the test would silently compare a
    # database with itself.
    previous = os.environ.get("EMPIRICAL_PLATFORM_POSTGRES_DATABASE")
    os.environ["EMPIRICAL_PLATFORM_POSTGRES_DATABASE"] = _PROBE_DATABASE
    try:
        alembic_command.upgrade(_alembic_config(), "head")
    finally:
        if previous is None:
            os.environ.pop("EMPIRICAL_PLATFORM_POSTGRES_DATABASE", None)
        else:
            os.environ["EMPIRICAL_PLATFORM_POSTGRES_DATABASE"] = previous

    config = _config(_PROBE_DATABASE)
    assert _config().database != config.database, "the two configs must address two databases"
    try:
        yield config
    finally:
        admin = sa.create_engine(_config().sqlalchemy_url(), isolation_level="AUTOCOMMIT")
        try:
            with admin.connect() as conn:
                conn.execute(text(f'DROP DATABASE IF EXISTS "{_PROBE_DATABASE}" WITH (FORCE)'))
        finally:
            admin.dispose()


_MUCH_LATER = _T0 + timedelta(days=120)


def _shared_opening(config: PostgreSQLConfigSnapshot, *, gid: str) -> None:
    """The identical visible prefix: OPENED 10 @ 100, recorded at K1."""
    _record(
        config,
        gid=gid,
        pos="POS-8300",
        symbol="AAPL",
        kind=OperatorPositionEventKind.OPENED,
        quantity=10,
        price="100",
        effective=_E1,
        recorded=_K1,
    )


def test_m080_two_databases_identical_up_to_k_produce_identical_reports(
    probe_database: PostgreSQLConfigSnapshot,
) -> None:
    """Mission section 16. The M079 invariant carried into M080."""
    db_a = _config()
    db_b = probe_database

    _shared_opening(db_a, gid="OPEV-8300-O")
    _shared_opening(db_b, gid="OPEV-8300-O")

    # DB-A: a reduction and a close, both recorded AFTER the cutoff.
    _record(
        db_a,
        gid="OPEV-8300-R",
        pos="POS-8300",
        symbol="AAPL",
        kind=OperatorPositionEventKind.REDUCED,
        quantity=4,
        price="110",
        effective=_E2,
        recorded=_K2,
    )
    _record(
        db_a,
        gid="OPEV-8300-C",
        pos="POS-8300",
        symbol="AAPL",
        kind=OperatorPositionEventKind.CLOSED,
        quantity=0,
        price="90",
        effective=_E3,
        recorded=_K3,
    )
    # DB-B: a radically different future -- one close at a wildly different
    # price, recorded far later, plus an entire extra position.
    _record(
        db_b,
        gid="OPEV-8399-C",
        pos="POS-8300",
        symbol="AAPL",
        kind=OperatorPositionEventKind.CLOSED,
        quantity=0,
        price="9999.999999",
        effective=_E3,
        recorded=_MUCH_LATER,
    )
    _record(
        db_b,
        gid="OPEV-8400-O",
        pos="POS-8400",
        symbol="NVDA",
        kind=OperatorPositionEventKind.OPENED,
        quantity=77,
        price="500",
        effective=_E1,
        recorded=_MUCH_LATER,
    )

    with sa.create_engine(db_a.sqlalchemy_url()).connect() as conn:
        rows_a = conn.execute(text("SELECT count(*) FROM operator_position_event")).scalar_one()
        prefix_a = conn.execute(
            text(
                "SELECT governance_id, position_governance_id, instrument_symbol, "
                "event_kind, quantity, asserted_price, event_timestamp "
                "FROM operator_position_event WHERE recorded_at <= :k ORDER BY governance_id"
            ),
            {"k": _K1},
        ).fetchall()
    with sa.create_engine(db_b.sqlalchemy_url()).connect() as conn:
        rows_b = conn.execute(text("SELECT count(*) FROM operator_position_event")).scalar_one()
        prefix_b = conn.execute(
            text(
                "SELECT governance_id, position_governance_id, instrument_symbol, "
                "event_kind, quantity, asserted_price, event_timestamp "
                "FROM operator_position_event WHERE recorded_at <= :k ORDER BY governance_id"
            ),
            {"k": _K1},
        ).fetchall()

    assert prefix_a == prefix_b, "the shared visible prefix must be identical in PostgreSQL"
    assert (rows_a, rows_b) == (3, 3)
    assert rows_a == rows_b  # same count, deliberately different content

    report_a = _report(db_a, effective=_NOW, knowledge=_K1)
    report_b = _report(db_b, effective=_NOW, knowledge=_K1)

    # Not just the amount: the whole object, and both renderings.
    assert report_a == report_b, "a row recorded after K changed the report at K"
    assert report_a.entries[0].status is RoundTripStatus.NO_EXIT_ASSERTED_YET
    assert report_a.entries[0].asserted_round_trip_result is None
    assert report_a.limitations == report_b.limitations
    assert [e.position_governance_id for e in report_a.entries] == [
        e.position_governance_id for e in report_b.entries
    ]
    assert render_round_trip_report_json(report_a) == render_round_trip_report_json(report_b)
    assert render_round_trip_report_text(report_a) == render_round_trip_report_text(report_b)


def test_m080_the_two_databases_diverge_once_knowledge_advances(
    probe_database: PostgreSQLConfigSnapshot,
) -> None:
    """Identical answers at K would be worthless if the ledgers were the same."""
    db_a = _config()
    db_b = probe_database

    _shared_opening(db_a, gid="OPEV-8300-O")
    _shared_opening(db_b, gid="OPEV-8300-O")
    _record(
        db_a,
        gid="OPEV-8300-C",
        pos="POS-8300",
        symbol="AAPL",
        kind=OperatorPositionEventKind.CLOSED,
        quantity=0,
        price="90",
        effective=_E3,
        recorded=_K3,
    )
    _record(
        db_b,
        gid="OPEV-8399-C",
        pos="POS-8300",
        symbol="AAPL",
        kind=OperatorPositionEventKind.CLOSED,
        quantity=0,
        price="150",
        effective=_E3,
        recorded=_K3,
    )

    later_a = _report(db_a, effective=_NOW, knowledge=_NOW).entries[0]
    later_b = _report(db_b, effective=_NOW, knowledge=_NOW).entries[0]
    assert later_a.asserted_round_trip_result == "-100"  # 10*90 - 10*100
    assert later_b.asserted_round_trip_result == "500"  # 10*150 - 10*100
    assert later_a != later_b

    # ...and the earlier answer is NOT retroactively strengthened by that.
    assert _report(db_a, effective=_NOW, knowledge=_K1) == _report(
        db_b, effective=_NOW, knowledge=_K1
    )
