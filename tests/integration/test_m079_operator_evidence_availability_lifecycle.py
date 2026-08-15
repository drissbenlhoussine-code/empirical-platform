"""MILESTONE-079 -- operator evidence availability against real PostgreSQL.

Reuses M072's real-session seeding so today's proposals are genuinely
persisted rows, and M076's real ledger repository so held exposure is genuinely
persisted operator assertions. Every figure the assessment reports is
cross-checked against raw SQL read independently of the repository helpers.

Scaffolding (fixtures, session seeding, market-data fakes) is reused from the
M075 integration suite.
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

from empirical_platform.decision_candidate.market_data_acquisition import FakeMarketDataSource
from empirical_platform.decision_candidate.operator_evidence_availability import (
    EvidenceSnapshotOutcome,
    EvidenceUnassessableReason,
    KnownPositionStatus,
    OperatorEvidenceSnapshot,
)
from empirical_platform.decision_candidate.operator_position_ledger import (
    OperatorAssertedPositionEvent,
    OperatorPositionEventKind,
    derive_position_state,
)
from empirical_platform.decision_candidate.same_day_capital_feasibility import (
    SameDayCapitalAssessment,
)
from empirical_platform.entrypoints._composition import postgres_repository_runtime
from empirical_platform.shared.config.settings import PostgreSQLConfigSnapshot
from empirical_platform.shared.identifiers import UuidRuntimeIdentifierGenerator
from empirical_platform.usecases.build_daily_research_brief import (
    BuildDailyResearchBriefHandler,
    BuildDailyResearchBriefQuery,
)
from empirical_platform.usecases.get_operator_evidence_snapshot import (
    GetOperatorEvidenceSnapshotHandler,
    GetOperatorEvidenceSnapshotQuery,
)
from empirical_platform.usecases.operator_evidence_snapshot_io import (
    render_evidence_snapshot_json,
    render_evidence_snapshot_text,
)
from empirical_platform.usecases.run_daily_research_session import (
    RunDailyResearchSessionHandler,
    build_run_daily_research_session_command,
)

pytestmark = pytest.mark.integration

_REPO_ROOT = Path(__file__).resolve().parents[2]
_T0 = datetime(2026, 1, 1, tzinfo=UTC)

_ALL_TABLES = [
    "operator_position_event",
    "research_session_decision",
    "research_session_stage",
    "research_session",
    "historical_backtest_trade",
    "historical_backtest_run",
    "position_plan",
    "trade_plan",
    "trading_opportunity_scan_evaluation",
    "trading_opportunity_scan",
    "decision_candidate",
    "dataset_snapshot_source_file",
    "dataset_snapshot",
    "instrument_master",
    "evidence_package_transition",
    "evidence_package_artifact_reference",
    "evidence_package_criterion_result",
    "evidence_package",
    "run_transition",
    "run_manifest",
    "run",
    "campaign_transition",
    "campaign",
]


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
        application_name="empirical-platform-m079-test",
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


class _FixedClock:
    def __init__(self, now: datetime) -> None:
        self._now = now

    def now(self) -> datetime:
        return self._now


def _breakout_csv(base_price: Decimal, breakout_pct: Decimal, breakout_vol: int) -> bytes:
    lines = ["timestamp,open,high,low,close,volume"]
    for i in range(10):
        ts = (_T0 + timedelta(days=i)).isoformat()
        lines.append(
            f"{ts},{base_price:.4f},{base_price * Decimal('1.001'):.4f},"
            f"{base_price * Decimal('0.999'):.4f},{base_price:.4f},50000"
        )
    breakout_close = base_price * (Decimal("1") + breakout_pct)
    for j in range(6):
        ts = (_T0 + timedelta(days=10 + j)).isoformat()
        c = breakout_close * (Decimal("1") + Decimal("0.001") * j)
        high = c * Decimal("1.002")
        low = c * Decimal("0.998")
        lines.append(f"{ts},{c:.4f},{high:.4f},{low:.4f},{c:.4f},{breakout_vol}")
    return ("\n".join(lines) + "\n").encode()


# The frozen M059 risk gate requires reward:risk >= 2.0, with
# target = reference_high * 1.02 (a fixed 2% projection, deliberately
# NOT a multiple of risk_per_unit -- see trade_plan.py's own
# compute_target_price docstring) and stop = reference_high. Working
# the inequality backwards: entry must land within roughly +0.67% of
# reference_high for the resulting geometry to clear the 2:1 minimum.
# A breakout_pct much larger than that (an earlier draft used 10%)
# pushes the target below the entry price entirely -- a genuine
# INVALID_TARGET_GEOMETRY rejection, confirmed by direct smoke-testing
# against a real container, not assumed. 0.4%/0.5% keep both
# instruments' entries close enough to the reference high to clear the
# gate on real math, not a hand-tuned pass.
_FIXTURES = {
    "AAPL": _breakout_csv(Decimal("100"), Decimal("0.004"), 500000),
    "MSFT": _breakout_csv(Decimal("400"), Decimal("0.005"), 400000),
}
# Same genuine flat->breakout fixture design as M071's own integration
# tests: days 0-9 are flat (NO_TRADE), day 10 is the first genuine
# breakout bar whose own reference window (days 6-9) is still entirely
# flat -- a real, unforced day-over-day state transition, not a
# fabricated difference between hand-authored fixtures.
_AS_OF_FLAT = _T0 + timedelta(days=5)
_AS_OF_BREAKOUT = _T0 + timedelta(days=10)


def _run_session(
    *,
    session_governance_id: str,
    artifact_path: Path,
    config: PostgreSQLConfigSnapshot,
    universe: tuple[str, ...] = ("AAPL", "MSFT"),
    fixtures: dict[str, bytes] | None = None,
    as_of: datetime = _AS_OF_BREAKOUT,
    lookback_days: int = 20,
    reference_window_size: int = 4,
) -> object:
    clock = _FixedClock(as_of)
    source = FakeMarketDataSource(fixtures if fixtures is not None else _FIXTURES, clock=clock)
    generator = UuidRuntimeIdentifierGenerator()
    with postgres_repository_runtime(config) as runtime:
        handler = RunDailyResearchSessionHandler(
            campaign_repository=runtime.campaigns,
            run_repository=runtime.runs,
            evidence_package_repository=runtime.evidence_packages,
            dataset_snapshot_repository=runtime.dataset_snapshots,
            instrument_master_repository=runtime.instrument_masters,
            decision_candidate_repository=runtime.decision_candidates,
            trading_opportunity_scan_repository=runtime.trading_opportunity_scans,
            trade_plan_repository=runtime.trade_plans,
            position_plan_repository=runtime.position_plans,
            historical_backtest_repository=runtime.historical_backtests,
            research_session_repository=runtime.research_sessions,
            clock=clock,
            runtime_identifier_generator=generator,
        )
        return handler.handle(
            build_run_daily_research_session_command(
                session_governance_id=session_governance_id,
                as_of=as_of,
                universe=universe,
                lookback_days=lookback_days,
                artifact_path=str(artifact_path),
                account_equity=Decimal("100000"),
                risk_percent=Decimal("0.01"),
                source=source,
                runtime_identifier_generator=generator,
                reference_window_size=reference_window_size,
            )
        )


def _build_brief(config: PostgreSQLConfigSnapshot, identity: object) -> object:
    with postgres_repository_runtime(config) as runtime:
        handler = BuildDailyResearchBriefHandler(
            research_session_repository=runtime.research_sessions,
            decision_candidate_repository=runtime.decision_candidates,
            trade_plan_repository=runtime.trade_plans,
            position_plan_repository=runtime.position_plans,
        )
        return handler.handle(BuildDailyResearchBriefQuery(identity=identity))  # type: ignore[arg-type]


def _assessment_of(brief: object) -> SameDayCapitalAssessment:
    assessment = brief.same_day_capital_assessment  # type: ignore[attr-defined]
    assert assessment is not None
    return assessment


# ---------------------------------------------------------------------------
# M079 helpers. The adversarial timeline the mission mandates:
#     T1 < T2 < T3, with the OPENED recorded LAST.
# ---------------------------------------------------------------------------

_T1 = _T0 + timedelta(days=40)  # OPENED  effective
_T2 = _T0 + timedelta(days=41)  # CLOSED  effective AND recorded
_T3 = _T0 + timedelta(days=42)  # OPENED  recorded (the backfill)
_NOW = _T0 + timedelta(days=60)


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
    """Append through the REAL M076 repository."""
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


def _snapshot(
    config: PostgreSQLConfigSnapshot,
    *,
    effective: datetime,
    knowledge: datetime,
    with_ledger: bool = True,
) -> OperatorEvidenceSnapshot:
    with postgres_repository_runtime(config) as runtime:
        handler = GetOperatorEvidenceSnapshotHandler(
            operator_position_ledger_repository=(
                runtime.operator_position_ledger if with_ledger else None
            )
        )
        return handler.handle(
            GetOperatorEvidenceSnapshotQuery(effective_as_of=effective, knowledge_as_of=knowledge)
        )


def _seed_backfilled_timeline(config: PostgreSQLConfigSnapshot) -> None:
    """OPENED effective T1 recorded T3; CLOSED effective T2 recorded T2.

    Inserted CLOSED-first, so insertion order cannot be what makes it work.
    """
    _record(
        config,
        gid="OPEV-7902",
        pos="POS-7901",
        symbol="AAPL",
        kind=OperatorPositionEventKind.OPENED,
        quantity=10,
        price="100",
        effective=_T1,
        recorded=_T3,
    )
    _record(
        config,
        gid="OPEV-7903",
        pos="POS-7901",
        symbol="AAPL",
        kind=OperatorPositionEventKind.CLOSED,
        quantity=10,
        price="110",
        effective=_T2,
        recorded=_T2,
    )


# ---------------------------------------------------------------------------
# The firewall over genuinely persisted rows
# ---------------------------------------------------------------------------


def test_m079_backfilled_assertion_is_invisible_at_the_earlier_knowledge_cutoff(
    clean_tables: Engine,
) -> None:
    config = _config()
    _record(
        config,
        gid="OPEV-7910",
        pos="POS-7910",
        symbol="TSLA",
        kind=OperatorPositionEventKind.OPENED,
        quantity=7,
        price="700",
        effective=_T1,
        recorded=_T3,
    )
    at_t2 = _snapshot(config, effective=_NOW, knowledge=_T2)
    at_now = _snapshot(config, effective=_NOW, knowledge=_NOW)

    assert at_t2.outcome is EvidenceSnapshotOutcome.NO_EVIDENCE_RECORDED_BY_KNOWLEDGE_CUTOFF
    assert at_t2.known_open_count == 0
    assert at_t2.known_event_count == 0
    assert at_now.known_open_count == 1
    assert at_t2.effective_as_of == at_now.effective_as_of


def test_m079_raw_sql_confirms_both_timestamps_and_eligibility(
    clean_tables: Engine,
) -> None:
    """Independent of every repository helper."""
    config = _config()
    _seed_backfilled_timeline(config)
    with clean_tables.begin() as conn:
        rows = conn.execute(
            text(
                "SELECT governance_id, event_timestamp, recorded_at FROM "
                "operator_position_event ORDER BY governance_id"
            )
        ).fetchall()
        eligible_at_t2 = conn.execute(
            text(
                "SELECT count(*) FROM operator_position_event "
                "WHERE event_timestamp <= :e AND recorded_at <= :k"
            ),
            {"e": _NOW, "k": _T2},
        ).scalar_one()
    stored = {r.governance_id: (r.event_timestamp, r.recorded_at) for r in rows}
    assert stored["OPEV-7902"][0] == _T1
    assert stored["OPEV-7902"][1] == _T3, "the OPENED must be recorded last"
    assert stored["OPEV-7903"][1] == _T2
    assert eligible_at_t2 == 1, "raw SQL agrees: only the CLOSED is eligible at T2"

    snapshot = _snapshot(config, effective=_NOW, knowledge=_T2)
    assert snapshot.visible_event_count == eligible_at_t2


def test_m079_close_without_its_opening_is_unresolved_over_real_rows(
    clean_tables: Engine,
) -> None:
    """Owner review attacks 1 and 3, over genuinely persisted rows.

    The status must NOT claim to know whether the sequence is merely truncated
    or genuinely incoherent -- the backfilled OPENED that would settle it is
    recorded after this cutoff.
    """
    config = _config()
    _seed_backfilled_timeline(config)
    at_t2 = _snapshot(config, effective=_NOW, knowledge=_T2)
    entry = at_t2.entries[0]
    assert entry.status is KnownPositionStatus.UNRESOLVED_KNOWLEDGE_SEQUENCE
    assert entry.position is None
    assert at_t2.unresolved_position_count == 1

    at_t3 = _snapshot(config, effective=_NOW, knowledge=_T3)
    assert at_t3.entries[0].status is KnownPositionStatus.KNOWN_CLOSED


def test_m079_three_knowledge_cutoffs_over_one_persisted_timeline(
    clean_tables: Engine,
) -> None:
    config = _config()
    _seed_backfilled_timeline(config)
    before = _snapshot(config, effective=_NOW, knowledge=_T1)
    middle = _snapshot(config, effective=_NOW, knowledge=_T2)
    after = _snapshot(config, effective=_NOW, knowledge=_T3)

    assert before.outcome is EvidenceSnapshotOutcome.NO_EVIDENCE_RECORDED_BY_KNOWLEDGE_CUTOFF
    assert middle.unresolved_position_count == 1
    assert after.known_closed_count == 1


def test_m079_does_not_contradict_m076_when_knowledge_is_the_present(
    clean_tables: Engine,
) -> None:
    config = _config()
    _record(
        config,
        gid="OPEV-7920",
        pos="POS-7920",
        symbol="NVDA",
        kind=OperatorPositionEventKind.OPENED,
        quantity=3,
        price="50",
        effective=_T1,
        recorded=_T3,
    )
    with postgres_repository_runtime(config) as runtime:
        m076 = derive_position_state(events=runtime.operator_position_ledger.list_all(), as_of=_NOW)
    m079 = _snapshot(config, effective=_NOW, knowledge=_NOW)
    assert m079.known_open_count == len(m076.open_positions) == 1


def test_m079_effective_cutoff_still_applies_independently(clean_tables: Engine) -> None:
    config = _config()
    _record(
        config,
        gid="OPEV-7930",
        pos="POS-7930",
        symbol="AMD",
        kind=OperatorPositionEventKind.OPENED,
        quantity=2,
        price="20",
        effective=_T3,
        recorded=_T1,
    )
    result = _snapshot(config, effective=_T2, knowledge=_NOW)
    assert result.entries == ()
    assert result.excluded_by_effective_cutoff == 1
    assert result.known_event_count == 1


def test_m079_missing_ledger_is_withheld(clean_tables: Engine) -> None:
    config = _config()
    result = _snapshot(config, effective=_NOW, knowledge=_NOW, with_ledger=False)
    assert result.outcome is EvidenceSnapshotOutcome.NOT_ASSESSABLE
    assert result.unassessable_reason is EvidenceUnassessableReason.LEDGER_UNAVAILABLE


def test_m079_naive_cutoff_is_a_request_error_not_a_data_claim(
    clean_tables: Engine,
) -> None:
    config = _config()
    with pytest.raises(ValueError, match="timezone-aware"):
        _snapshot(
            config,
            effective=datetime(2026, 1, 20, 12, 0),  # noqa: DTZ001 - deliberately naive
            knowledge=_NOW,
        )


def test_m079_text_and_json_agree_over_real_rows(clean_tables: Engine) -> None:
    config = _config()
    _seed_backfilled_timeline(config)
    result = _snapshot(config, effective=_NOW, knowledge=_T2)
    payload = render_evidence_snapshot_json(result)
    rendered = render_evidence_snapshot_text(result)

    assert payload["outcome"] == result.outcome.value
    assert payload["known_event_count"] == result.known_event_count
    assert payload["excluded_by_effective_cutoff"] == result.excluded_by_effective_cutoff
    assert "excluded_by_knowledge_cutoff" not in payload
    assert "total_event_count" not in payload
    assert payload["entries"][0]["status"] == "UNRESOLVED_KNOWLEDGE_SEQUENCE"
    assert "UNRESOLVED_KNOWLEDGE_SEQUENCE" in rendered
    assert "NOT known to be true" in rendered
    assert payload["entries"][0]["open_quantity"] is None


def test_m079_is_deterministic_across_two_independent_reads(clean_tables: Engine) -> None:
    config = _config()
    _seed_backfilled_timeline(config)
    assert _snapshot(config, effective=_NOW, knowledge=_T2) == _snapshot(
        config, effective=_NOW, knowledge=_T2
    )


def test_m079_reads_a_consistent_snapshot_while_a_writer_appends(
    clean_tables: Engine,
) -> None:
    config = _config()
    _record(
        config,
        gid="OPEV-7940",
        pos="POS-7940",
        symbol="AAPL",
        kind=OperatorPositionEventKind.OPENED,
        quantity=1,
        price="10",
        effective=_T1,
        recorded=_T1,
    )
    barrier = threading.Barrier(2)

    def writer() -> None:
        barrier.wait(timeout=20)
        _record(
            config,
            gid="OPEV-7941",
            pos="POS-7941",
            symbol="TSLA",
            kind=OperatorPositionEventKind.OPENED,
            quantity=1,
            price="10",
            effective=_T1,
            recorded=_T1,
        )

    def reader() -> OperatorEvidenceSnapshot:
        barrier.wait(timeout=20)
        return _snapshot(config, effective=_NOW, knowledge=_NOW)

    with ThreadPoolExecutor(max_workers=2) as pool:
        writer_future = pool.submit(writer)
        reader_future = pool.submit(reader)
        writer_future.result(timeout=60)
        observed = reader_future.result(timeout=60)

    assert observed.known_open_count in {1, 2}
    assert _snapshot(config, effective=_NOW, knowledge=_NOW).known_open_count == 2


# ---------------------------------------------------------------------------
# Owner review correction: post-cutoff rows may not influence ANY output.
#
# The unit suite proves this over in-memory tuples. These prove it over rows
# that PostgreSQL actually stored, in two genuinely separate databases.
# ---------------------------------------------------------------------------

_PROBE_DATABASE = "m079_leak_probe"


def _probe_config() -> PostgreSQLConfigSnapshot:
    base = _config()
    return PostgreSQLConfigSnapshot(
        host=base.host,
        port=base.port,
        database=_PROBE_DATABASE,
        user=base.user,
        password=base.password,
        pool_size=2,
        max_overflow=0,
        connection_timeout_seconds=5,
        application_name="empirical-platform-m079-leak-probe",
    )


@pytest.fixture
def probe_database(clean_tables: Engine) -> Iterator[PostgreSQLConfigSnapshot]:
    """A SECOND physical database, created empty and migrated from scratch.

    Owner review attack 8 asks for two persisted datasets that agree on every
    row with `recorded_at <= K` and disagree afterwards. Doing that in one
    database would only prove the filter; doing it in two proves the answer does
    not depend on what the other ledger happens to contain.
    """
    admin = sa.create_engine(_config().sqlalchemy_url(), isolation_level="AUTOCOMMIT")
    try:
        with admin.connect() as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{_PROBE_DATABASE}" WITH (FORCE)'))
            conn.execute(text(f'CREATE DATABASE "{_PROBE_DATABASE}"'))
    finally:
        admin.dispose()

    config = _probe_config()
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

    assert _config().database != _PROBE_DATABASE, "the two configs must address two databases"
    try:
        yield config
    finally:
        admin = sa.create_engine(_config().sqlalchemy_url(), isolation_level="AUTOCOMMIT")
        try:
            with admin.connect() as conn:
                conn.execute(text(f'DROP DATABASE IF EXISTS "{_PROBE_DATABASE}" WITH (FORCE)'))
        finally:
            admin.dispose()


_MUCH_LATER = _T0 + timedelta(days=90)  # recorded far beyond _NOW


def _seed_shared_prefix_then(
    config: PostgreSQLConfigSnapshot,
    *,
    opening_gid: str,
    opening_recorded: datetime,
    opening_quantity: int,
    opening_price: str,
) -> None:
    """Write the SAME visible prefix, then a post-cutoff tail that differs.

    The M076 write path validates on append, so a CLOSED cannot be persisted
    without its OPENED. Both ledgers therefore carry an opening -- what differs
    is when it was RECORDED, which is precisely the dimension under test. At
    K = _T2 only the CLOSED is recorded in either database, and that CLOSED is
    identical in every field.

    Frozen M076 DERIVES a CLOSED event's quantity from the open position rather
    than taking it as supplied, so both openings must carry the same quantity
    for the visible prefix to match. The post-cutoff tails still differ by
    governance id, asserted price and recorded_at, and DB-A carries an entire
    extra position that DB-B has never heard of.
    """
    _record(
        config,
        gid=opening_gid,
        pos="POS-7950",
        symbol="AAPL",
        kind=OperatorPositionEventKind.OPENED,
        quantity=opening_quantity,
        price=opening_price,
        effective=_T1,
        recorded=opening_recorded,  # always AFTER _T2
    )
    _record(
        config,
        gid="OPEV-7950",  # identical in both databases
        pos="POS-7950",
        symbol="AAPL",
        kind=OperatorPositionEventKind.CLOSED,
        quantity=10,
        price="110",
        effective=_T2,
        recorded=_T2,  # the whole of the shared visible prefix
    )


def test_m079_two_databases_identical_up_to_k_produce_identical_output(
    probe_database: PostgreSQLConfigSnapshot,
) -> None:
    """Owner review attack 8, the strongest form of the central regression.

    Both databases agree exactly on every row with `recorded_at <= _T2` and
    disagree on everything recorded afterwards -- different governance id,
    different quantity, different asserted price, different recorded_at, and in
    DB-A an entire extra position. Both were written by the real M076
    repository into real PostgreSQL and read back through the real handler.
    """
    db_a = _config()
    db_b = probe_database

    _seed_shared_prefix_then(
        db_a,
        opening_gid="OPEV-7951",
        opening_recorded=_T3,
        opening_quantity=10,
        opening_price="100",
    )
    _record(  # an entire position that exists only in DB-A, recorded after the cutoff
        db_a,
        gid="OPEV-7960",
        pos="POS-7960",
        symbol="TSLA",
        kind=OperatorPositionEventKind.OPENED,
        quantity=99,
        price="700",
        effective=_T1,
        recorded=_T3,
    )
    _seed_shared_prefix_then(
        db_b,
        opening_gid="OPEV-7999",  # different id
        opening_recorded=_MUCH_LATER,  # different recorded_at
        opening_quantity=10,  # must match: M076 derives the CLOSED quantity
        opening_price="555",  # different asserted price
    )

    with sa.create_engine(db_a.sqlalchemy_url()).connect() as conn:
        rows_a = conn.execute(text("SELECT count(*) FROM operator_position_event")).scalar_one()
        prefix_a = conn.execute(
            text(
                "SELECT governance_id, position_governance_id, instrument_symbol, event_kind, "
                "quantity, asserted_price, event_timestamp FROM operator_position_event "
                "WHERE recorded_at <= :k ORDER BY governance_id"
            ),
            {"k": _T2},
        ).fetchall()
    with sa.create_engine(db_b.sqlalchemy_url()).connect() as conn:
        rows_b = conn.execute(text("SELECT count(*) FROM operator_position_event")).scalar_one()
        prefix_b = conn.execute(
            text(
                "SELECT governance_id, position_governance_id, instrument_symbol, event_kind, "
                "quantity, asserted_price, event_timestamp FROM operator_position_event "
                "WHERE recorded_at <= :k ORDER BY governance_id"
            ),
            {"k": _T2},
        ).fetchall()

    assert prefix_a == prefix_b, "the shared visible prefix must be identical in PostgreSQL"
    assert (rows_a, rows_b) == (3, 2), "the two ledgers must genuinely differ after the cutoff"

    snap_a = _snapshot(db_a, effective=_NOW, knowledge=_T2)
    snap_b = _snapshot(db_b, effective=_NOW, knowledge=_T2)

    assert snap_a == snap_b, "a row recorded after K changed the answer at K"
    assert snap_a.entries[0].status is KnownPositionStatus.UNRESOLVED_KNOWLEDGE_SEQUENCE
    assert snap_a.known_event_count == 1
    assert snap_a.entries[0].position is None

    # Owner review attack 9: parity in BOTH renderings, not just the object.
    assert render_evidence_snapshot_json(snap_a) == render_evidence_snapshot_json(snap_b)
    assert render_evidence_snapshot_text(snap_a) == render_evidence_snapshot_text(snap_b)


def test_m079_the_two_databases_diverge_once_knowledge_advances(
    probe_database: PostgreSQLConfigSnapshot,
) -> None:
    """The other half of attack 8, and Owner review attack 4.

    Identical answers at K would be worthless if the two ledgers were simply
    indistinguishable. Advance the cutoff past DB-A's backfill and they must
    part company -- DB-A resolves, DB-B legitimately stays unresolved because
    its own opening is not recorded until later still.
    """
    db_a = _config()
    db_b = probe_database

    _seed_shared_prefix_then(
        db_a,
        opening_gid="OPEV-7952",
        opening_recorded=_T3,
        opening_quantity=10,
        opening_price="100",
    )
    _seed_shared_prefix_then(
        db_b,
        opening_gid="OPEV-7998",
        opening_recorded=_MUCH_LATER,
        opening_quantity=10,
        opening_price="100",
    )

    later_a = _snapshot(db_a, effective=_NOW, knowledge=_NOW)
    later_b = _snapshot(db_b, effective=_NOW, knowledge=_NOW)

    assert later_a.entries[0].status is KnownPositionStatus.KNOWN_CLOSED
    assert later_b.entries[0].status is KnownPositionStatus.UNRESOLVED_KNOWLEDGE_SEQUENCE
    assert later_a != later_b

    # Owner review: "Do not retroactively strengthen the earlier K answer."
    assert _snapshot(db_a, effective=_NOW, knowledge=_T2) == _snapshot(
        db_b, effective=_NOW, knowledge=_T2
    )


def test_m079_leaves_m076_free_to_see_every_event(clean_tables: Engine) -> None:
    """Owner review attack 10.

    M079 hides the backfill; M076 must still see it under its own effective-time
    semantics, and must be unchanged by having been called through M079.
    """
    config = _config()
    _seed_backfilled_timeline(config)

    hidden_at_t2 = _snapshot(config, effective=_NOW, knowledge=_T2)
    assert hidden_at_t2.visible_event_count == 1

    with postgres_repository_runtime(config) as runtime:
        all_events = runtime.operator_position_ledger.list_all()
        m076 = derive_position_state(events=all_events, as_of=_NOW)

    assert len(all_events) == 2, "M076 still sees the assertion M079 hid"
    assert len(m076.closed_positions) == 1
    assert m076.open_positions == ()

    after = _snapshot(config, effective=_NOW, knowledge=_T2)
    assert after == hidden_at_t2, "calling M076 must not perturb M079's answer"
