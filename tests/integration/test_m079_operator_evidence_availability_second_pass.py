"""MILESTONE-079 -- FRESH SECOND VERIFICATION PASS.

Reuses M072's real-session seeding so today's proposals are genuinely
persisted rows, and M076's real ledger repository so held exposure is genuinely
persisted operator assertions. Every figure the assessment reports is
cross-checked against raw SQL read independently of the repository helpers.

Scaffolding (fixtures, session seeding, market-data fakes) is reused from the
M075 integration suite.
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

from empirical_platform.decision_candidate.market_data_acquisition import FakeMarketDataSource
from empirical_platform.decision_candidate.operator_evidence_availability import (
    KnownPositionStatus,
    OperatorEvidenceSnapshot,
)
from empirical_platform.decision_candidate.operator_position_ledger import (
    OperatorAssertedPositionEvent,
    OperatorPositionEventKind,
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
        application_name="empirical-platform-m079-second-pass",
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
# Fresh second pass: a database created empty, different symbols, different
# ids, different timestamps, and REVERSED insertion order.
# ---------------------------------------------------------------------------

_S1 = _T0 + timedelta(days=91, hours=3)  # OPENED effective
_S2 = _T0 + timedelta(days=93, hours=7)  # REDUCED effective and recorded
_S3 = _T0 + timedelta(days=95, hours=11)  # OPENED recorded (backfill)
_S_NOW = _T0 + timedelta(days=120)


def test_m079_second_pass_reversed_insertion_order_same_answer(
    clean_tables: Engine,
) -> None:
    """Insertion order must not affect eligibility: the REDUCED is written
    first and the backfilled OPENED second."""
    config = _config()
    _record(
        config,
        gid="OPEV-9902",
        pos="POS-9901",
        symbol="SMCI",
        kind=OperatorPositionEventKind.OPENED,
        quantity=44,
        price="317.250001",
        effective=_S1,
        recorded=_S3,
    )
    _record(
        config,
        gid="OPEV-9903",
        pos="POS-9901",
        symbol="SMCI",
        kind=OperatorPositionEventKind.REDUCED,
        quantity=19,
        price="401.9",
        effective=_S2,
        recorded=_S2,
    )

    at_s2 = _snapshot(config, effective=_S_NOW, knowledge=_S2)
    assert at_s2.entries[0].status is KnownPositionStatus.INCOMPLETE_KNOWLEDGE_SEQUENCE
    assert at_s2.entries[0].position is None
    assert at_s2.excluded_by_knowledge_cutoff == 1

    at_s3 = _snapshot(config, effective=_S_NOW, knowledge=_S3)
    entry = at_s3.entries[0]
    assert entry.status is KnownPositionStatus.KNOWN_OPEN
    assert entry.position is not None
    assert entry.position.open_quantity == 25
    # Valued at the ORIGINAL asserted entry price, never the reduction's price.
    assert entry.position.asserted_entry_price == "317.250001"
    assert "401.9" not in render_evidence_snapshot_text(at_s3)


def test_m079_second_pass_raw_sql_eligibility_at_each_cutoff(
    clean_tables: Engine,
) -> None:
    config = _config()
    _record(
        config,
        gid="OPEV-9910",
        pos="POS-9910",
        symbol="PLTR",
        kind=OperatorPositionEventKind.OPENED,
        quantity=8,
        price="0.000001",
        effective=_S1,
        recorded=_S3,
    )
    _record(
        config,
        gid="OPEV-9911",
        pos="POS-9911",
        symbol="COIN",
        kind=OperatorPositionEventKind.OPENED,
        quantity=6,
        price="99999999999999.999999",
        effective=_S1,
        recorded=_S1,
    )
    with clean_tables.begin() as conn:
        for cutoff, expected in ((_S1, 1), (_S2, 1), (_S3, 2)):
            count = conn.execute(
                text(
                    "SELECT count(*) FROM operator_position_event "
                    "WHERE event_timestamp <= :e AND recorded_at <= :k"
                ),
                {"e": _S_NOW, "k": cutoff},
            ).scalar_one()
            assert count == expected
            assert (
                _snapshot(config, effective=_S_NOW, knowledge=cutoff).visible_event_count
                == expected
            )


def test_m079_second_pass_is_deterministic_on_a_fresh_database(
    clean_tables: Engine,
) -> None:
    config = _config()
    _record(
        config,
        gid="OPEV-9920",
        pos="POS-9920",
        symbol="ARM",
        kind=OperatorPositionEventKind.OPENED,
        quantity=13,
        price="7.000001",
        effective=_S1,
        recorded=_S2,
    )
    a = _snapshot(config, effective=_S_NOW, knowledge=_S_NOW)
    b = _snapshot(config, effective=_S_NOW, knowledge=_S_NOW)
    assert a == b
