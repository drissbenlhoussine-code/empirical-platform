"""MILESTONE-081 fresh second verification pass.

Same agent, so NOT an independent review. A genuinely fresh database, created
empty and migrated from scratch, with deliberately different inputs from the
first suite: different instruments, different position keys, different
timestamps, THREE exits on one position rather than two, prices at both ends of
the frozen NUMERIC(20, 6) domain in a single position, and REVERSED recording
order so that recording order cannot be what makes the arithmetic work.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from fractions import Fraction
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command as alembic_command
from alembic.config import Config
from pydantic import SecretStr
from sqlalchemy import text

from empirical_platform.decision_candidate.operator_asserted_round_trip import RoundTripStatus
from empirical_platform.decision_candidate.operator_asserted_round_trip_ratio import (
    AssertedRoundTripRatioReport,
)
from empirical_platform.decision_candidate.operator_position_ledger import (
    OperatorAssertedPositionEvent,
    OperatorPositionEventKind,
)
from empirical_platform.entrypoints._composition import postgres_repository_runtime
from empirical_platform.shared.config.settings import PostgreSQLConfigSnapshot
from empirical_platform.usecases.get_asserted_round_trip_ratio_report import (
    GetAssertedRoundTripRatioReportHandler,
    GetAssertedRoundTripRatioReportQuery,
)

pytestmark = pytest.mark.integration

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DATABASE = "m081_second_pass"
_T0 = datetime(2026, 11, 15, tzinfo=UTC)
_NOW = _T0 + timedelta(days=200)

OPENED = OperatorPositionEventKind.OPENED
REDUCED = OperatorPositionEventKind.REDUCED
CLOSED = OperatorPositionEventKind.CLOSED


def _postgres_enabled() -> bool:
    return os.environ.get("EMPIRICAL_PLATFORM_RUN_POSTGRES_TESTS") == "1"


def _config(database: str) -> PostgreSQLConfigSnapshot:
    return PostgreSQLConfigSnapshot(
        host=os.environ.get("EMPIRICAL_PLATFORM_POSTGRES_HOST", "localhost"),
        port=int(os.environ.get("EMPIRICAL_PLATFORM_POSTGRES_PORT", "5432")),
        database=database,
        user=os.environ.get("EMPIRICAL_PLATFORM_POSTGRES_USER", "empirical"),
        password=SecretStr(os.environ["EMPIRICAL_PLATFORM_POSTGRES_PASSWORD"]),
        pool_size=2,
        max_overflow=0,
        connection_timeout_seconds=5,
        application_name="empirical-platform-m081-second-pass",
    )


def _alembic_config() -> Config:
    cfg = Config(str(_REPO_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(_REPO_ROOT / "migrations"))
    return cfg


@pytest.fixture(scope="module")
def fresh_database() -> Iterator[str]:
    if not _postgres_enabled():
        pytest.skip("PostgreSQL integration tests require explicit opt-in")
    admin = sa.create_engine(
        _config(
            os.environ.get("EMPIRICAL_PLATFORM_POSTGRES_DATABASE", "empirical_platform")
        ).sqlalchemy_url()
    )
    try:
        with admin.connect() as conn:
            conn.execution_options(isolation_level="AUTOCOMMIT")
            conn.execute(text(f'DROP DATABASE IF EXISTS "{_DATABASE}"'))
            conn.execute(text(f'CREATE DATABASE "{_DATABASE}"'))
        previous = os.environ.get("EMPIRICAL_PLATFORM_POSTGRES_DATABASE")
        try:
            # Scoped to the alembic call ONLY: leaving it set across the yield
            # would make later comparisons compare a database with itself.
            os.environ["EMPIRICAL_PLATFORM_POSTGRES_DATABASE"] = _DATABASE
            alembic_command.upgrade(_alembic_config(), "head")
        finally:
            if previous is None:
                os.environ.pop("EMPIRICAL_PLATFORM_POSTGRES_DATABASE", None)
            else:
                os.environ["EMPIRICAL_PLATFORM_POSTGRES_DATABASE"] = previous
        yield _DATABASE
    finally:
        with admin.connect() as conn:
            conn.execution_options(isolation_level="AUTOCOMMIT")
            conn.execute(text(f'DROP DATABASE IF EXISTS "{_DATABASE}"'))
        admin.dispose()


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
                source_position_plan_governance_id=None,
            )
        )


def _report(
    config: PostgreSQLConfigSnapshot, *, knowledge: datetime = _NOW
) -> AssertedRoundTripRatioReport:
    with postgres_repository_runtime(config) as runtime:
        handler = GetAssertedRoundTripRatioReportHandler(
            operator_position_ledger_repository=runtime.operator_position_ledger
        )
        return handler.handle(
            GetAssertedRoundTripRatioReportQuery(effective_as_of=_NOW, knowledge_as_of=knowledge)
        )


def _entry(report: AssertedRoundTripRatioReport, pos: str):  # noqa: ANN202
    return next(e for e in report.entries if e.position_governance_id == pos)


def test_three_exits_on_one_position_each_contribute_their_own_price(
    fresh_database: str,
) -> None:
    """PLTR: OPENED 9 @ 10; exits of 2 @ 30, 3 @ 20, 4 @ 5.

    consideration = 60 + 60 + 20 = 140 ; entry cost = 9 x 10 = 90
    result = 50 ; ratio = 50/90 = 5/9
    """
    d = lambda n: _T0 + timedelta(days=n)  # noqa: E731
    config = _config(fresh_database)
    _record(
        config,
        gid="SP-O",
        pos="SP-100",
        symbol="PLTR",
        kind=OPENED,
        quantity=9,
        price="10",
        effective=d(91),
        recorded=d(91),
    )
    _record(
        config,
        gid="SP-R1",
        pos="SP-100",
        symbol="PLTR",
        kind=REDUCED,
        quantity=2,
        price="30",
        effective=d(92),
        recorded=d(92),
    )
    _record(
        config,
        gid="SP-R2",
        pos="SP-100",
        symbol="PLTR",
        kind=REDUCED,
        quantity=3,
        price="20",
        effective=d(93),
        recorded=d(93),
    )
    _record(
        config,
        gid="SP-C",
        pos="SP-100",
        symbol="PLTR",
        kind=CLOSED,
        quantity=4,
        price="5",
        effective=d(94),
        recorded=d(94),
    )

    entry = _entry(_report(config), "SP-100")
    assert entry.status is RoundTripStatus.FULLY_EXITED_ASSERTED
    assert entry.exited_quantity == 9
    assert entry.ratio_exact == "5/9"
    assert entry.ratio_approximation_is_exact is False
    assert entry.ratio_decimal_approx == "~0.555555"
    assert Fraction(5, 9) - Fraction(Decimal("0.555555")) > 0  # truncated, never rounded up


def test_both_ends_of_the_numeric_domain_in_one_position(fresh_database: str) -> None:
    """COIN: entry 0.000002, exits at 0.000001 and 99999999999999.999999."""
    d = lambda n: _T0 + timedelta(days=n)  # noqa: E731
    config = _config(fresh_database)
    _record(
        config,
        gid="SP2-O",
        pos="SP-200",
        symbol="COIN",
        kind=OPENED,
        quantity=2,
        price="0.000002",
        effective=d(101),
        recorded=d(101),
    )
    _record(
        config,
        gid="SP2-R",
        pos="SP-200",
        symbol="COIN",
        kind=REDUCED,
        quantity=1,
        price="0.000001",
        effective=d(102),
        recorded=d(102),
    )
    _record(
        config,
        gid="SP2-C",
        pos="SP-200",
        symbol="COIN",
        kind=CLOSED,
        quantity=1,
        price="99999999999999.999999",
        effective=d(103),
        recorded=d(103),
    )

    entry = _entry(_report(config), "SP-200")
    # consideration = 1 + 99999999999999999999 (scaled) ; entry cost = 2 x 2 = 4
    assert entry.ratio_denominator is not None
    assert entry.ratio_denominator > 0
    assert Fraction(entry.ratio_numerator or 0, entry.ratio_denominator) > Fraction(-1)
    assert entry.ratio_numerator is not None
    assert entry.ratio_numerator > 0


def test_reversed_recording_order_does_not_change_the_ratio(fresh_database: str) -> None:
    """ARM: the opening carries a LATER `recorded_at` than the reduction.

    Before the opening is known the sequence is unresolved and carries no ratio;
    once it is known the ratio is exactly what in-order recording would give.
    """
    d = lambda n: _T0 + timedelta(days=n)  # noqa: E731
    config = _config(fresh_database)
    # Frozen M076 validates each append against the derived state, so a REDUCED
    # cannot physically be appended before its OPENED. The reversal that matters
    # here is in KNOWLEDGE time, not append order: the opening is written first
    # but carries a LATER `recorded_at` than the reduction, so at an early
    # cutoff the reduction is visible and its opening is not.
    _record(
        config,
        gid="SP3-O",
        pos="SP-300",
        symbol="ARM",
        kind=OPENED,
        quantity=8,
        price="100",
        effective=d(111),
        recorded=d(130),
    )
    _record(
        config,
        gid="SP3-R",
        pos="SP-300",
        symbol="ARM",
        kind=REDUCED,
        quantity=5,
        price="140",
        effective=d(112),
        recorded=d(112),
    )

    early = _entry(_report(config, knowledge=_T0 + timedelta(days=120)), "SP-300")
    assert early.status is RoundTripStatus.UNRESOLVED_KNOWLEDGE_SEQUENCE
    assert early.ratio_exact is None

    later = _entry(_report(config), "SP-300")
    # exited 5 @ 140 = 700 ; entry cost 5 x 100 = 500 ; result 200 ; 200/500 = 2/5
    assert later.status is RoundTripStatus.PARTIAL_EXIT_ASSERTED
    assert later.ratio_exact == "2/5"


def test_a_post_cutoff_row_appended_between_two_reads_changes_nothing(
    fresh_database: str,
) -> None:
    """SMCI: the firewall holds on a database that already carries other data."""
    d = lambda n: _T0 + timedelta(days=n)  # noqa: E731
    config = _config(fresh_database)
    knowledge = _T0 + timedelta(days=125)
    _record(
        config,
        gid="SP4-O",
        pos="SP-400",
        symbol="SMCI",
        kind=OPENED,
        quantity=6,
        price="50",
        effective=d(121),
        recorded=d(121),
    )
    _record(
        config,
        gid="SP4-R",
        pos="SP-400",
        symbol="SMCI",
        kind=REDUCED,
        quantity=2,
        price="75",
        effective=d(122),
        recorded=d(122),
    )

    before = _report(config, knowledge=knowledge)
    _record(
        config,
        gid="SP4-C",
        pos="SP-400",
        symbol="SMCI",
        kind=CLOSED,
        quantity=4,
        price="500",
        effective=d(123),
        recorded=d(180),
    )
    after = _report(config, knowledge=knowledge)

    assert before == after
    assert _entry(before, "SP-400").ratio_exact == "1/2"
    assert _entry(_report(config), "SP-400").ratio_exact != "1/2"
