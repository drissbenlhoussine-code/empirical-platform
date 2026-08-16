"""MILESTONE-080 -- FRESH SECOND VERIFICATION PASS.

Same agent, so NOT an independent review. A genuinely fresh database and
deliberately different inputs: different instruments, different governance ids,
different timestamps, prices at both ends of the frozen NUMERIC(20,6) domain,
several reductions rather than one, and REVERSED insertion order so ordering
cannot be what makes the arithmetic work.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
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
    RoundTripStatus,
)
from empirical_platform.decision_candidate.operator_position_ledger import (
    OperatorAssertedPositionEvent,
    OperatorPositionEventKind,
)
from empirical_platform.entrypoints._composition import postgres_repository_runtime
from empirical_platform.shared.config.settings import PostgreSQLConfigSnapshot
from empirical_platform.usecases.asserted_round_trip_io import render_round_trip_report_text
from empirical_platform.usecases.get_asserted_round_trip_report import (
    GetAssertedRoundTripReportHandler,
    GetAssertedRoundTripReportQuery,
)

pytestmark = pytest.mark.integration

_REPO_ROOT = Path(__file__).resolve().parents[2]
_T0 = datetime(2026, 9, 1, tzinfo=UTC)

_S1 = _T0 + timedelta(days=91)
_S2 = _T0 + timedelta(days=94)
_S3 = _T0 + timedelta(days=97)
_S_NOW = _T0 + timedelta(days=130)

_ALL_TABLES = ["operator_position_event"]


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
        application_name="empirical-platform-m080-second-pass",
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
) -> None:
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
            )
        )


def _report(
    config: PostgreSQLConfigSnapshot, *, effective: datetime, knowledge: datetime
) -> AssertedRoundTripReport:
    with postgres_repository_runtime(config) as runtime:
        handler = GetAssertedRoundTripReportHandler(
            operator_position_ledger_repository=runtime.operator_position_ledger
        )
        return handler.handle(
            GetAssertedRoundTripReportQuery(effective_as_of=effective, knowledge_as_of=knowledge)
        )


def test_m080_second_pass_multiple_reductions_at_boundary_decimals(
    clean_tables: Engine,
) -> None:
    """PLTR, three exits, prices at both ends of NUMERIC(20,6)."""
    config = _config()
    _record(
        config,
        gid="OPEV-9901",
        pos="POS-9901",
        symbol="PLTR",
        kind=OperatorPositionEventKind.OPENED,
        quantity=9,
        price="0.000002",
        effective=_S1,
        recorded=_S1,
    )
    _record(
        config,
        gid="OPEV-9902",
        pos="POS-9901",
        symbol="PLTR",
        kind=OperatorPositionEventKind.REDUCED,
        quantity=2,
        price="0.000001",
        effective=_S2,
        recorded=_S2,
    )
    _record(
        config,
        gid="OPEV-9903",
        pos="POS-9901",
        symbol="PLTR",
        kind=OperatorPositionEventKind.REDUCED,
        quantity=3,
        price="99999999999999.999999",
        effective=_S3,
        recorded=_S3,
    )
    entry = _report(config, effective=_S_NOW, knowledge=_S_NOW).entries[0]

    assert entry.status is RoundTripStatus.PARTIAL_EXIT_ASSERTED
    assert entry.exited_quantity == 5
    assert entry.still_open_quantity == 4
    # cost 5 * 0.000002 = 0.00001 ; consideration 2*0.000001 + 3*99999999999999.999999
    assert entry.asserted_entry_cost_for_exited_quantity == "0.00001"
    assert entry.asserted_exit_consideration == "299999999999999.999999"
    assert entry.asserted_round_trip_result == "299999999999999.999989"


def test_m080_second_pass_reversed_insertion_order_same_answer(
    clean_tables: Engine,
) -> None:
    """The exits are written before the opening is recorded, so insertion order
    cannot be what makes the firewall or the arithmetic work."""
    config = _config()
    # Written first, but recorded LAST.
    _record(
        config,
        gid="OPEV-9910",
        pos="POS-9910",
        symbol="COIN",
        kind=OperatorPositionEventKind.OPENED,
        quantity=8,
        price="317.250001",
        effective=_S1,
        recorded=_S3,
    )
    _record(
        config,
        gid="OPEV-9911",
        pos="POS-9910",
        symbol="COIN",
        kind=OperatorPositionEventKind.REDUCED,
        quantity=5,
        price="401.9",
        effective=_S2,
        recorded=_S2,
    )

    # At S2 the reduction is visible but its opening is not.
    at_s2 = _report(config, effective=_S_NOW, knowledge=_S2).entries[0]
    assert at_s2.status is RoundTripStatus.UNRESOLVED_KNOWLEDGE_SEQUENCE
    assert at_s2.asserted_round_trip_result is None

    # Once the opening is recorded the arithmetic appears.
    at_s3 = _report(config, effective=_S_NOW, knowledge=_S3).entries[0]
    assert at_s3.status is RoundTripStatus.PARTIAL_EXIT_ASSERTED
    # 5*401.9 - 5*317.250001 = 2009.5 - 1586.250005 = 423.249995
    assert at_s3.asserted_round_trip_result == "423.249995"
    assert at_s3.still_open_quantity == 3


def test_m080_second_pass_post_cutoff_rows_do_not_change_the_answer(
    clean_tables: Engine,
) -> None:
    """Take a report, append assertions recorded after the cutoff, take it again."""
    config = _config()
    _record(
        config,
        gid="OPEV-9920",
        pos="POS-9920",
        symbol="ARM",
        kind=OperatorPositionEventKind.OPENED,
        quantity=6,
        price="120.5",
        effective=_S1,
        recorded=_S1,
    )
    before = _report(config, effective=_S_NOW, knowledge=_S2)
    assert before.entries[0].status is RoundTripStatus.NO_EXIT_ASSERTED_YET

    _record(
        config,
        gid="OPEV-9921",
        pos="POS-9920",
        symbol="ARM",
        kind=OperatorPositionEventKind.REDUCED,
        quantity=6,
        price="900.123456",
        effective=_S2,
        recorded=_S3,  # after the cutoff below
    )
    after = _report(config, effective=_S_NOW, knowledge=_S2)
    assert after == before, "an assertion recorded after the cutoff moved the answer at it"
    assert render_round_trip_report_text(after) == render_round_trip_report_text(before)

    advanced = _report(config, effective=_S_NOW, knowledge=_S3).entries[0]
    assert advanced.status is RoundTripStatus.FULLY_EXITED_ASSERTED
    # 6*900.123456 - 6*120.5 = 5400.740736 - 723 = 4677.740736
    assert advanced.asserted_round_trip_result == "4677.740736"


def test_m080_second_pass_raw_sql_confirms_the_boundary_prices(clean_tables: Engine) -> None:
    config = _config()
    _record(
        config,
        gid="OPEV-9930",
        pos="POS-9930",
        symbol="SMCI",
        kind=OperatorPositionEventKind.OPENED,
        quantity=1,
        price="99999999999999.999999",
        effective=_S1,
        recorded=_S1,
    )
    with clean_tables.begin() as conn:
        stored = conn.execute(
            text("SELECT asserted_price FROM operator_position_event WHERE governance_id = :g"),
            {"g": "OPEV-9930"},
        ).scalar_one()
    assert stored == Decimal("99999999999999.999999")
    entry = _report(config, effective=_S_NOW, knowledge=_S_NOW).entries[0]
    assert entry.asserted_entry_price == "99999999999999.999999"
