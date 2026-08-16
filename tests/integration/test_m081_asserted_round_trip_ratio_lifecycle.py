"""MILESTONE-081 -- the asserted round-trip result ratio against real PostgreSQL.

Every ratio is cross-checked against a numerator and denominator recomputed
INDEPENDENTLY from raw SQL, using pure integer arithmetic and NOT the M080
helper -- the mission's requirement, and the only way the cross-check is worth
anything.

Scaffolding is reused from the M080 integration suite.

Mandated scenarios, all built here:

    A. fully exited, positive asserted result
    B. fully exited, negative asserted result
    C. break-even
    D. partial exit
    E. no exit
    F. post-K exit
    G. unresolved knowledge sequence
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal, localcontext
from fractions import Fraction
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command as alembic_command
from alembic.config import Config
from pydantic import SecretStr
from sqlalchemy import text
from sqlalchemy.engine import Engine

from empirical_platform.decision_candidate.operator_asserted_round_trip import (
    ASSERTED_PRICE_DENOMINATION_LIMITATION,
    RoundTripStatus,
)
from empirical_platform.decision_candidate.operator_asserted_round_trip_ratio import (
    ASSERTED_RATIO_BANNER,
    AssertedRoundTripRatioReport,
    RatioAbsenceReason,
)
from empirical_platform.decision_candidate.operator_position_ledger import (
    OperatorAssertedPositionEvent,
    OperatorPositionEventKind,
)
from empirical_platform.entrypoints._composition import postgres_repository_runtime
from empirical_platform.shared.config.settings import PostgreSQLConfigSnapshot
from empirical_platform.usecases.asserted_round_trip_ratio_io import (
    render_round_trip_ratio_report_json,
    render_round_trip_ratio_report_text,
)
from empirical_platform.usecases.get_asserted_round_trip_ratio_report import (
    GetAssertedRoundTripRatioReportHandler,
    GetAssertedRoundTripRatioReportQuery,
)

pytestmark = pytest.mark.integration

_REPO_ROOT = Path(__file__).resolve().parents[2]
_T0 = datetime(2026, 9, 1, tzinfo=UTC)
_ALL_TABLES = ["operator_position_event"]
_NOW = _T0 + timedelta(days=120)

OPENED = OperatorPositionEventKind.OPENED
REDUCED = OperatorPositionEventKind.REDUCED
CLOSED = OperatorPositionEventKind.CLOSED

_PRICE_SCALE = 10**6


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
        application_name="empirical-platform-m081-test",
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
    effective: datetime = _NOW,
    knowledge: datetime = _NOW,
    with_ledger: bool = True,
) -> AssertedRoundTripRatioReport:
    with postgres_repository_runtime(config) as runtime:
        handler = GetAssertedRoundTripRatioReportHandler(
            operator_position_ledger_repository=(
                runtime.operator_position_ledger if with_ledger else None
            )
        )
        return handler.handle(
            GetAssertedRoundTripRatioReportQuery(
                effective_as_of=effective, knowledge_as_of=knowledge
            )
        )


def _independent_ratio_from_raw_sql(
    engine: Engine, position: str, *, knowledge: datetime, effective: datetime
) -> Fraction | None:
    """Recompute the ratio from raw rows using ONLY integer arithmetic.

    Deliberately does not touch M080 or M081 helpers -- a cross-check that
    reuses the code under test proves nothing.
    """
    with engine.begin() as conn:
        rows = list(
            conn.execute(
                text(
                    "SELECT event_kind, quantity, asserted_price FROM operator_position_event "
                    "WHERE position_governance_id = :pos AND recorded_at <= :k "
                    "AND event_timestamp <= :e ORDER BY event_timestamp, recorded_at"
                ),
                {"pos": position, "k": knowledge, "e": effective},
            )
        )

    entry_price_scaled: int | None = None
    exited = 0
    consideration = 0
    for kind, quantity, price in rows:
        scaled = int((Decimal(price) * _PRICE_SCALE).to_integral_exact())
        if str(kind) == "OPENED":
            entry_price_scaled = scaled
        else:
            exited += int(quantity)
            consideration += int(quantity) * scaled

    if entry_price_scaled is None or exited == 0:
        return None
    entry_cost = exited * entry_price_scaled
    return Fraction(consideration - entry_cost, entry_cost)


def _entry(report: AssertedRoundTripRatioReport, position: str):  # noqa: ANN202
    return next(e for e in report.entries if e.position_governance_id == position)


def _fraction(entry) -> Fraction:  # noqa: ANN001
    assert entry.ratio_numerator is not None
    assert entry.ratio_denominator is not None
    return Fraction(entry.ratio_numerator, entry.ratio_denominator)


# --------------------------------------------------------------------------
# Mandated scenarios A - G
# --------------------------------------------------------------------------


def _seed_all_scenarios(config: PostgreSQLConfigSnapshot) -> None:
    d = lambda n: _T0 + timedelta(days=n)  # noqa: E731

    # A. fully exited, POSITIVE result: 10 @ 100 -> 10 @ 150  => 1/2
    _record(
        config,
        gid="A-O",
        pos="POS-A",
        symbol="AAPL",
        kind=OPENED,
        quantity=10,
        price="100",
        effective=d(1),
        recorded=d(1),
    )
    _record(
        config,
        gid="A-C",
        pos="POS-A",
        symbol="AAPL",
        kind=CLOSED,
        quantity=10,
        price="150",
        effective=d(2),
        recorded=d(2),
    )

    # B. fully exited, NEGATIVE result: 4 @ 100 -> 4 @ 25  => -3/4
    _record(
        config,
        gid="B-O",
        pos="POS-B",
        symbol="MSFT",
        kind=OPENED,
        quantity=4,
        price="100",
        effective=d(1),
        recorded=d(1),
    )
    _record(
        config,
        gid="B-C",
        pos="POS-B",
        symbol="MSFT",
        kind=CLOSED,
        quantity=4,
        price="25",
        effective=d(2),
        recorded=d(2),
    )

    # C. break-even: 10 @ 100 -> 10 @ 100  => 0
    _record(
        config,
        gid="C-O",
        pos="POS-C",
        symbol="NVDA",
        kind=OPENED,
        quantity=10,
        price="100",
        effective=d(1),
        recorded=d(1),
    )
    _record(
        config,
        gid="C-C",
        pos="POS-C",
        symbol="NVDA",
        kind=CLOSED,
        quantity=10,
        price="100",
        effective=d(2),
        recorded=d(2),
    )

    # D. partial exit: 10 @ 100, REDUCED 1 @ 200  => 1 on the exited unit only
    _record(
        config,
        gid="D-O",
        pos="POS-D",
        symbol="TSLA",
        kind=OPENED,
        quantity=10,
        price="100",
        effective=d(1),
        recorded=d(1),
    )
    _record(
        config,
        gid="D-R",
        pos="POS-D",
        symbol="TSLA",
        kind=REDUCED,
        quantity=1,
        price="200",
        effective=d(2),
        recorded=d(2),
    )

    # E. no exit at all
    _record(
        config,
        gid="E-O",
        pos="POS-E",
        symbol="AMZN",
        kind=OPENED,
        quantity=7,
        price="55",
        effective=d(1),
        recorded=d(1),
    )

    # F. exit RECORDED far in the future (post-K for the early cutoff)
    _record(
        config,
        gid="F-O",
        pos="POS-F",
        symbol="META",
        kind=OPENED,
        quantity=8,
        price="100",
        effective=d(1),
        recorded=d(1),
    )
    _record(
        config,
        gid="F-C",
        pos="POS-F",
        symbol="META",
        kind=CLOSED,
        quantity=8,
        price="300",
        effective=d(2),
        recorded=d(90),
    )

    # G. unresolved knowledge sequence: the reduction is recorded BEFORE its opening
    _record(
        config,
        gid="G-O",
        pos="POS-G",
        symbol="NFLX",
        kind=OPENED,
        quantity=10,
        price="100",
        effective=d(1),
        recorded=d(80),
    )
    _record(
        config,
        gid="G-R",
        pos="POS-G",
        symbol="NFLX",
        kind=REDUCED,
        quantity=3,
        price="120",
        effective=d(2),
        recorded=d(3),
    )


@pytest.fixture
def seeded(clean_tables: Engine) -> Engine:
    _seed_all_scenarios(_config())
    return clean_tables


@pytest.mark.parametrize(
    ("position", "expected"),
    [("POS-A", "1/2"), ("POS-B", "-3/4"), ("POS-C", "0"), ("POS-D", "1")],
)
def test_m081_scenarios_a_to_d_produce_the_expected_exact_ratio(
    seeded: Engine, position: str, expected: str
) -> None:
    entry = _entry(_report(_config()), position)
    assert entry.ratio_exact == expected


def test_m081_scenario_e_no_exit_has_no_ratio(seeded: Engine) -> None:
    entry = _entry(_report(_config()), "POS-E")
    assert entry.status is RoundTripStatus.NO_EXIT_ASSERTED_YET
    assert entry.ratio_exact is None
    assert entry.ratio_absence_reason is RatioAbsenceReason.NO_EXIT_ASSERTED_YET


def test_m081_scenario_f_post_cutoff_exit_is_invisible_then_visible(seeded: Engine) -> None:
    early = _T0 + timedelta(days=30)
    assert _entry(_report(_config(), knowledge=early), "POS-F").ratio_exact is None
    assert _entry(_report(_config()), "POS-F").ratio_exact == "2"


def test_m081_scenario_g_unresolved_sequence_has_no_ratio(seeded: Engine) -> None:
    early = _T0 + timedelta(days=30)
    entry = _entry(_report(_config(), knowledge=early), "POS-G")
    assert entry.status is RoundTripStatus.UNRESOLVED_KNOWLEDGE_SEQUENCE
    assert entry.ratio_exact is None
    assert entry.ratio_absence_reason is RatioAbsenceReason.UNRESOLVED_KNOWLEDGE_SEQUENCE


@pytest.mark.parametrize("position", ["POS-A", "POS-B", "POS-C", "POS-D", "POS-F"])
def test_every_ratio_matches_an_independent_recomputation_from_raw_sql(
    seeded: Engine, position: str
) -> None:
    """The cross-check uses raw rows and integer arithmetic, never the M080 helper."""
    entry = _entry(_report(_config()), position)
    independent = _independent_ratio_from_raw_sql(seeded, position, knowledge=_NOW, effective=_NOW)
    assert independent is not None
    assert _fraction(entry) == independent


def test_the_partial_exit_denominator_is_the_exited_quantity_in_the_database(
    seeded: Engine,
) -> None:
    """POS-D: 1 exited of 10. The whole-position denominator would give 1/10."""
    entry = _entry(_report(_config()), "POS-D")
    assert entry.exited_quantity == 1
    assert entry.still_open_quantity == 9
    assert _fraction(entry) == Fraction(1)
    assert _fraction(entry) != Fraction(1, 10)


# --------------------------------------------------------------------------
# Cross-denomination attack (mandated)
# --------------------------------------------------------------------------


def test_two_positions_of_unknown_denomination_are_never_summed(clean_tables: Engine) -> None:
    """Mandated cross-denomination attack, against real rows.

    The MONEY ranks these two opposite to the RATIOS, which is exactly why a
    monetary comparison across unknown denominations is unsupported.
    """
    d = lambda n: _T0 + timedelta(days=n)  # noqa: E731
    config = _config()
    _record(
        config,
        gid="X-O",
        pos="POS-X",
        symbol="AAPL",
        kind=OPENED,
        quantity=10,
        price="100",
        effective=d(1),
        recorded=d(1),
    )
    _record(
        config,
        gid="X-C",
        pos="POS-X",
        symbol="AAPL",
        kind=CLOSED,
        quantity=10,
        price="150",
        effective=d(2),
        recorded=d(2),
    )
    _record(
        config,
        gid="Y-O",
        pos="POS-Y",
        symbol="7203.T",
        kind=OPENED,
        quantity=5,
        price="2000",
        effective=d(1),
        recorded=d(1),
    )
    _record(
        config,
        gid="Y-C",
        pos="POS-Y",
        symbol="7203.T",
        kind=CLOSED,
        quantity=5,
        price="2200",
        effective=d(2),
        recorded=d(2),
    )

    report = _report(config)
    payload = render_round_trip_ratio_report_json(report)

    assert _entry(report, "POS-X").ratio_exact == "1/2"
    assert _entry(report, "POS-Y").ratio_exact == "1/10"

    # The raw money would say POS-Y (1000) beat POS-X (500). The ratios say the
    # opposite. No combined figure of either kind exists.
    all_keys = set(payload) | set(payload["entries"][0])
    for forbidden in ("portfolio", "total", "combined", "aggregate", "overall", "sum"):
        assert not any(forbidden in key.lower() for key in all_keys), forbidden

    # No monetary value at all, per design D-F04.
    entry_json = json.dumps(payload["entries"])
    for money in ('"500"', '"1000"', '"1500"', '"11000"', '"10000"'):
        assert money not in entry_json

    # No currency inferred from either symbol. The banner and the denomination
    # limitation legitimately NAME currencies in order to deny them, so strip
    # those sentences first -- splitting on a marker was my assertion being
    # wrong, since the limitations follow the entries.
    rendered = render_round_trip_ratio_report_text(report)
    stripped = rendered
    for surface in (ASSERTED_RATIO_BANNER, ASSERTED_PRICE_DENOMINATION_LIMITATION):
        for sentence in surface.split(". "):
            stripped = stripped.replace(sentence.strip().rstrip("."), "")
    for token in ("USD", "JPY", "EUR", "$", "¥"):
        assert token not in stripped, token


# --------------------------------------------------------------------------
# The M079 firewall, proved across TWO databases (mandated)
# --------------------------------------------------------------------------


@pytest.fixture
def second_database(engine: Engine) -> Iterator[str]:
    name = "m081_firewall_probe"
    with engine.connect() as conn:
        conn.execution_options(isolation_level="AUTOCOMMIT")
        conn.execute(text(f'DROP DATABASE IF EXISTS "{name}"'))
        conn.execute(text(f'CREATE DATABASE "{name}"'))
    previous = os.environ.get("EMPIRICAL_PLATFORM_POSTGRES_DATABASE")
    try:
        os.environ["EMPIRICAL_PLATFORM_POSTGRES_DATABASE"] = name
        alembic_command.upgrade(_alembic_config(), "head")
    finally:
        if previous is None:
            os.environ.pop("EMPIRICAL_PLATFORM_POSTGRES_DATABASE", None)
        else:
            os.environ["EMPIRICAL_PLATFORM_POSTGRES_DATABASE"] = previous
    try:
        yield name
    finally:
        with engine.connect() as conn:
            conn.execution_options(isolation_level="AUTOCOMMIT")
            conn.execute(text(f'DROP DATABASE IF EXISTS "{name}"'))


def test_two_databases_identical_up_to_k_agree_on_every_m081_output(
    clean_tables: Engine, second_database: str
) -> None:
    """Mandated double-database temporal proof.

    Both databases carry IDENTICAL rows with `recorded_at <= K`, and radically
    different post-K futures. At K, every M081 output must match: fields,
    status, ratio, reason, counts, text, JSON and ordering.
    """
    d = lambda n: _T0 + timedelta(days=n)  # noqa: E731
    knowledge = _T0 + timedelta(days=10)

    primary = _config()
    other = _config(second_database)
    assert primary.database != other.database

    for config in (primary, other):
        _record(
            config,
            gid="FW-O",
            pos="POS-FW",
            symbol="AAPL",
            kind=OPENED,
            quantity=10,
            price="100",
            effective=d(1),
            recorded=d(1),
        )
        _record(
            config,
            gid="FW-R",
            pos="POS-FW",
            symbol="AAPL",
            kind=REDUCED,
            quantity=4,
            price="110",
            effective=d(2),
            recorded=d(5),
        )

    # Radically different, entirely post-K, futures.
    _record(
        primary,
        gid="FW-C",
        pos="POS-FW",
        symbol="AAPL",
        kind=CLOSED,
        quantity=6,
        price="90",
        effective=d(3),
        recorded=d(50),
    )
    _record(
        other,
        gid="FW-C",
        pos="POS-FW",
        symbol="AAPL",
        kind=CLOSED,
        quantity=6,
        price="9000",
        effective=d(3),
        recorded=d(60),
    )
    _record(
        other,
        gid="FW-O2",
        pos="POS-OTHER",
        symbol="ZZZZ",
        kind=OPENED,
        quantity=99,
        price="7",
        effective=d(4),
        recorded=d(70),
    )

    left = _report(primary, effective=_NOW, knowledge=knowledge)
    right = _report(other, effective=_NOW, knowledge=knowledge)

    assert left == right
    assert render_round_trip_ratio_report_text(left) == render_round_trip_ratio_report_text(right)
    assert json.dumps(render_round_trip_ratio_report_json(left), sort_keys=True) == json.dumps(
        render_round_trip_ratio_report_json(right), sort_keys=True
    )

    # And the futures genuinely differ once the cutoff advances.
    assert _report(primary, effective=_NOW, knowledge=_NOW) != _report(
        other, effective=_NOW, knowledge=_NOW
    )


# --------------------------------------------------------------------------
# Exactness and context independence against real rows
# --------------------------------------------------------------------------


def test_the_persistence_boundary_ratio_is_exact_against_raw_sql(clean_tables: Engine) -> None:
    """Max INTEGER quantity against the max NUMERIC(20,6) price, from the database."""
    d = lambda n: _T0 + timedelta(days=n)  # noqa: E731
    config = _config()
    _record(
        config,
        gid="BD-O",
        pos="POS-BD",
        symbol="AAPL",
        kind=OPENED,
        quantity=2147483647,
        price="99999999999999.999999",
        effective=d(1),
        recorded=d(1),
    )
    _record(
        config,
        gid="BD-C",
        pos="POS-BD",
        symbol="AAPL",
        kind=CLOSED,
        quantity=2147483647,
        price="0.000001",
        effective=d(2),
        recorded=d(2),
    )

    entry = _entry(_report(config), "POS-BD")
    independent = _independent_ratio_from_raw_sql(
        clean_tables, "POS-BD", knowledge=_NOW, effective=_NOW
    )
    assert independent is not None
    assert _fraction(entry) == independent
    assert _fraction(entry) > Fraction(-1)
    assert entry.ratio_decimal_approx == "~-0.999999"
    assert entry.ratio_decimal_approx != "-1"


@pytest.mark.parametrize("precision", [1, 9, 28, 60])
def test_the_database_backed_ratio_does_not_move_with_the_ambient_context(
    clean_tables: Engine, precision: int
) -> None:
    d = lambda n: _T0 + timedelta(days=n)  # noqa: E731
    config = _config()
    _record(
        config,
        gid="CT-O",
        pos="POS-CT",
        symbol="AAPL",
        kind=OPENED,
        quantity=2147483647,
        price="99999999999999.999999",
        effective=d(1),
        recorded=d(1),
    )
    _record(
        config,
        gid="CT-C",
        pos="POS-CT",
        symbol="AAPL",
        kind=CLOSED,
        quantity=2147483647,
        price="0.000001",
        effective=d(2),
        recorded=d(2),
    )

    with localcontext() as ctx:
        ctx.prec = precision
        entry = _entry(_report(config), "POS-CT")
    assert entry.ratio_exact == "-99999999999999999998/99999999999999999999"


def test_a_missing_ledger_withholds_the_report_with_the_denomination_limitation(
    clean_tables: Engine,
) -> None:
    report = _report(_config(), with_ledger=False)
    assert report.unassessable_reason is not None
    assert any("UNSPECIFIED ASSERTED PRICE UNITS" in lim for lim in report.limitations)
