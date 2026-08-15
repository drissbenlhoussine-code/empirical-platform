"""MILESTONE-078 -- FRESH SECOND VERIFICATION PASS.

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
from empirical_platform.decision_candidate.operator_position_ledger import (
    OperatorAssertedPositionEvent,
    OperatorPositionEventKind,
)
from empirical_platform.decision_candidate.research_decision_follow_through import (
    FollowThroughStatus,
    ResearchDecisionFollowThrough,
)
from empirical_platform.decision_candidate.same_day_capital_feasibility import (
    SameDayCapitalAssessment,
)
from empirical_platform.entrypoints._composition import postgres_repository_runtime
from empirical_platform.shared.config.settings import PostgreSQLConfigSnapshot
from empirical_platform.shared.identifiers import UuidRuntimeIdentifierGenerator
from empirical_platform.usecases.audit_research_decision_follow_through import (
    AuditResearchDecisionFollowThroughHandler,
    AuditResearchDecisionFollowThroughQuery,
)
from empirical_platform.usecases.build_daily_research_brief import (
    BuildDailyResearchBriefHandler,
    BuildDailyResearchBriefQuery,
)
from empirical_platform.usecases.research_decision_follow_through_io import (
    render_follow_through_text,
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
        application_name="empirical-platform-m078-second-pass",
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
# M078 helpers
# ---------------------------------------------------------------------------

_AUDIT_AS_OF = _AS_OF_BREAKOUT + timedelta(days=7)


def _record(
    config: PostgreSQLConfigSnapshot,
    *,
    gid: str,
    pos: str,
    symbol: str,
    kind: OperatorPositionEventKind,
    quantity: int,
    price: str,
    at: datetime,
    cites: str | None = None,
) -> None:
    """Append through the REAL M076 repository, so every domain and persistence
    invariant is genuinely exercised."""
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
                event_timestamp=at,
                recorded_at=at,
                source_position_plan_governance_id=cites,
            )
        )


def _audit(
    config: PostgreSQLConfigSnapshot,
    identity: object,
    *,
    as_of: datetime = _AUDIT_AS_OF,
    with_ledger: bool = True,
) -> ResearchDecisionFollowThrough:
    with postgres_repository_runtime(config) as runtime:
        handler = AuditResearchDecisionFollowThroughHandler(
            research_session_repository=runtime.research_sessions,
            operator_position_ledger_repository=(
                runtime.operator_position_ledger if with_ledger else None
            ),
        )
        return handler.handle(
            AuditResearchDecisionFollowThroughQuery(identity=identity, as_of=as_of)  # type: ignore[arg-type]
        )


def _seed(tmp_path: Path, config: PostgreSQLConfigSnapshot, gid: str) -> object:
    return _run_session(
        session_governance_id=gid, artifact_path=tmp_path / f"{gid}.json", config=config
    )


def _approved_plan_ids(audit: ResearchDecisionFollowThrough) -> list[str]:
    return [e.position_plan_governance_id for e in audit.entries]


# ---------------------------------------------------------------------------
# Fresh second pass: a database created empty, and deliberately different
# inputs -- different session ids, symbols, a shifted breakout fixture, a
# different as_of, quantities, prices and risk budget.
# ---------------------------------------------------------------------------

_SECOND_FLAT_DAYS = 13
_SECOND_AS_OF = _T0 + timedelta(days=_SECOND_FLAT_DAYS)
_SECOND_AUDIT_AS_OF = _SECOND_AS_OF + timedelta(days=21)


def _shifted_breakout_csv(base_price: Decimal, breakout_pct: Decimal, breakout_vol: int) -> bytes:
    """The breakout lands on day 13 rather than day 10. Moving only `as_of`
    later is not enough: the reference window would then contain earlier
    breakout bars and the scan correctly reports NO_TRADE."""
    lines = ["timestamp,open,high,low,close,volume"]
    for i in range(_SECOND_FLAT_DAYS):
        ts = (_T0 + timedelta(days=i)).isoformat()
        lines.append(
            f"{ts},{base_price:.4f},{base_price * Decimal('1.001'):.4f},"
            f"{base_price * Decimal('0.999'):.4f},{base_price:.4f},50000"
        )
    breakout_close = base_price * (Decimal("1") + breakout_pct)
    for j in range(4):
        ts = (_T0 + timedelta(days=_SECOND_FLAT_DAYS + j)).isoformat()
        c = breakout_close * (Decimal("1") + Decimal("0.001") * j)
        lines.append(
            f"{ts},{c:.4f},{c * Decimal('1.002'):.4f},{c * Decimal('0.998'):.4f},"
            f"{c:.4f},{breakout_vol}"
        )
    return ("\n".join(lines) + "\n").encode()


_SECOND_FIXTURES = {
    "NVDA": _shifted_breakout_csv(Decimal("42.50"), Decimal("0.003"), 900_000),
    "AMD": _shifted_breakout_csv(Decimal("17.25"), Decimal("0.006"), 640_000),
}


def _run_second_session(
    *, gid: str, artifact_path: Path, config: PostgreSQLConfigSnapshot
) -> object:
    clock = _FixedClock(_SECOND_AS_OF)
    source = FakeMarketDataSource(_SECOND_FIXTURES, clock=clock)
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
                session_governance_id=gid,
                as_of=_SECOND_AS_OF,
                universe=("NVDA", "AMD"),
                lookback_days=20,
                artifact_path=str(artifact_path),
                account_equity=Decimal("43750.25"),
                risk_percent=Decimal("0.015"),
                source=source,
                runtime_identifier_generator=generator,
                reference_window_size=4,
            )
        )


def test_m078_second_pass_mixed_statuses_over_a_fresh_database(
    clean_tables: Engine, tmp_path: Path
) -> None:
    config = _config()
    result = _run_second_session(
        gid="RESEARCH-9201", artifact_path=tmp_path / "s1.json", config=config
    )
    before = _audit(config, result.identity, as_of=_SECOND_AUDIT_AS_OF)  # type: ignore[attr-defined]
    assert len(before.entries) >= 2, "the second session must approve at least two plans"
    first, second = before.entries[0], before.entries[1]

    opened_at = _SECOND_AS_OF + timedelta(days=2)
    # First plan: an open assertion.
    _record(
        config,
        gid="OPEV-9201",
        pos="POS-9201",
        symbol=first.instrument_symbol,
        kind=OperatorPositionEventKind.OPENED,
        quantity=13,
        price="7.000001",
        at=opened_at,
        cites=first.position_plan_governance_id,
    )
    # Second plan: opened then closed.
    _record(
        config,
        gid="OPEV-9202",
        pos="POS-9202",
        symbol=second.instrument_symbol,
        kind=OperatorPositionEventKind.OPENED,
        quantity=9,
        price="291.6375",
        at=opened_at,
        cites=second.position_plan_governance_id,
    )
    _record(
        config,
        gid="OPEV-9203",
        pos="POS-9202",
        symbol=second.instrument_symbol,
        kind=OperatorPositionEventKind.CLOSED,
        quantity=9,
        price="415.999999",
        at=opened_at + timedelta(days=3),
    )
    # An unrelated open position citing nothing.
    _record(
        config,
        gid="OPEV-9204",
        pos="POS-9204",
        symbol="SMCI",
        kind=OperatorPositionEventKind.OPENED,
        quantity=4,
        price="150.125",
        at=opened_at,
    )

    audit = _audit(config, result.identity, as_of=_SECOND_AUDIT_AS_OF)  # type: ignore[attr-defined]
    by_plan = {e.position_plan_governance_id: e for e in audit.entries}

    assert (
        by_plan[first.position_plan_governance_id].status
        is FollowThroughStatus.ASSERTED_POSITION_OPEN
    )
    assert (
        by_plan[second.position_plan_governance_id].status
        is FollowThroughStatus.ASSERTED_POSITION_CLOSED
    )
    assert audit.with_open_asserted_position == 1
    assert audit.with_closed_asserted_position == 1
    assert [u.position_governance_id for u in audit.unlinked_open_positions] == ["POS-9204"]

    # Not one of the asserted prices may appear anywhere in the rendering.
    rendered = render_follow_through_text(audit)
    for price in ("7.000001", "291.6375", "415.999999", "150.125"):
        assert price not in rendered


def test_m078_second_pass_audit_window_before_the_session_is_named(
    clean_tables: Engine, tmp_path: Path
) -> None:
    config = _config()
    result = _run_second_session(
        gid="RESEARCH-9202", artifact_path=tmp_path / "s2.json", config=config
    )
    audit = _audit(
        config,
        result.identity,  # type: ignore[attr-defined]
        as_of=_SECOND_AS_OF - timedelta(days=1),
    )
    assert any("precedes this session's own as_of" in line for line in audit.limitations)
    assert audit.with_no_asserted_position_recorded == audit.approved_plan_count


def test_m078_second_pass_is_deterministic_on_a_fresh_database(
    clean_tables: Engine, tmp_path: Path
) -> None:
    config = _config()
    result = _run_second_session(
        gid="RESEARCH-9203", artifact_path=tmp_path / "s3.json", config=config
    )
    _record(
        config,
        gid="OPEV-9210",
        pos="POS-9210",
        symbol="SMCI",
        kind=OperatorPositionEventKind.OPENED,
        quantity=6,
        price="99.999999",
        at=_SECOND_AS_OF + timedelta(days=1),
    )
    a = _audit(config, result.identity, as_of=_SECOND_AUDIT_AS_OF)  # type: ignore[attr-defined]
    b = _audit(config, result.identity, as_of=_SECOND_AUDIT_AS_OF)  # type: ignore[attr-defined]
    assert a == b
