"""MILESTONE-078 -- research decision follow-through against real PostgreSQL.

Reuses M072's real-session seeding so today's proposals are genuinely
persisted rows, and M076's real ledger repository so held exposure is genuinely
persisted operator assertions. Every figure the assessment reports is
cross-checked against raw SQL read independently of the repository helpers.

Scaffolding (fixtures, session seeding, market-data fakes) is reused from the
M075 integration suite.
"""

from __future__ import annotations

import json
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
from empirical_platform.decision_candidate.operator_position_ledger import (
    OperatorAssertedPositionEvent,
    OperatorPositionEventKind,
)
from empirical_platform.decision_candidate.research_decision_follow_through import (
    FollowThroughOutcome,
    FollowThroughStatus,
    FollowThroughUnassessableReason,
    ResearchDecisionFollowThrough,
    UnlinkedPositionReason,
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
    render_follow_through_json,
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
        application_name="empirical-platform-m078-test",
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
# Over genuinely persisted rows
# ---------------------------------------------------------------------------


def test_m078_nothing_recorded_against_a_real_session(clean_tables: Engine, tmp_path: Path) -> None:
    config = _config()
    result = _seed(tmp_path, config, "RESEARCH-7801")
    audit = _audit(config, result.identity)  # type: ignore[attr-defined]

    assert audit.outcome is FollowThroughOutcome.AUDITED
    assert audit.approved_plan_count > 0
    assert audit.with_no_asserted_position_recorded == audit.approved_plan_count
    assert all(e.status is FollowThroughStatus.NO_ASSERTED_POSITION_RECORDED for e in audit.entries)
    assert any("not a finding that the operator did not act" in line for line in audit.limitations)


def test_m078_open_position_is_matched_to_its_plan_and_cross_checked_in_sql(
    clean_tables: Engine, tmp_path: Path
) -> None:
    config = _config()
    result = _seed(tmp_path, config, "RESEARCH-7802")
    before = _audit(config, result.identity)  # type: ignore[attr-defined]
    target = before.entries[0]

    _record(
        config,
        gid="OPEV-7810",
        pos="POS-7810",
        symbol=target.instrument_symbol,
        kind=OperatorPositionEventKind.OPENED,
        quantity=5,
        price="100",
        at=_AS_OF_BREAKOUT + timedelta(days=1),
        cites=target.position_plan_governance_id,
    )
    after = _audit(config, result.identity)  # type: ignore[attr-defined]
    entry = next(
        e
        for e in after.entries
        if e.position_plan_governance_id == target.position_plan_governance_id
    )
    assert entry.status is FollowThroughStatus.ASSERTED_POSITION_OPEN
    assert entry.position_governance_ids == ("POS-7810",)
    assert entry.mismatched_instrument_position_ids == ()

    # Raw SQL, independent of every repository helper.
    with clean_tables.begin() as conn:
        row = conn.execute(
            text(
                "SELECT source_position_plan_governance_id, instrument_symbol "
                "FROM operator_position_event WHERE governance_id = 'OPEV-7810'"
            )
        ).one()
    assert row.source_position_plan_governance_id == target.position_plan_governance_id
    assert row.instrument_symbol == target.instrument_symbol


def test_m078_closed_position_is_reported_as_closed_not_as_nothing_recorded(
    clean_tables: Engine, tmp_path: Path
) -> None:
    config = _config()
    result = _seed(tmp_path, config, "RESEARCH-7803")
    target = _audit(config, result.identity).entries[0]  # type: ignore[attr-defined]

    opened_at = _AS_OF_BREAKOUT + timedelta(days=1)
    _record(
        config,
        gid="OPEV-7820",
        pos="POS-7820",
        symbol=target.instrument_symbol,
        kind=OperatorPositionEventKind.OPENED,
        quantity=5,
        price="100",
        at=opened_at,
        cites=target.position_plan_governance_id,
    )
    _record(
        config,
        gid="OPEV-7821",
        pos="POS-7820",
        symbol=target.instrument_symbol,
        kind=OperatorPositionEventKind.CLOSED,
        quantity=5,
        price="110",
        at=opened_at + timedelta(days=1),
    )
    after = _audit(config, result.identity)  # type: ignore[attr-defined]
    entry = next(
        e
        for e in after.entries
        if e.position_plan_governance_id == target.position_plan_governance_id
    )
    assert entry.status is FollowThroughStatus.ASSERTED_POSITION_CLOSED
    assert entry.closed_position_count == 1
    # The 110 exit price exists in the database and must never surface here.
    assert "110" not in render_follow_through_text(after).replace("OPEV-", "")


def test_m078_unlinked_open_position_is_reported(clean_tables: Engine, tmp_path: Path) -> None:
    config = _config()
    result = _seed(tmp_path, config, "RESEARCH-7804")
    _record(
        config,
        gid="OPEV-7830",
        pos="POS-7830",
        symbol="TSLA",
        kind=OperatorPositionEventKind.OPENED,
        quantity=3,
        price="700",
        at=_AS_OF_BREAKOUT + timedelta(days=1),
    )
    audit = _audit(config, result.identity)  # type: ignore[attr-defined]
    assert len(audit.unlinked_open_positions) == 1
    unlinked = audit.unlinked_open_positions[0]
    assert unlinked.reason is UnlinkedPositionReason.CITES_NO_PLAN
    assert unlinked.open_quantity == 3


def test_m078_position_citing_a_foreign_plan_is_a_distinct_fact(
    clean_tables: Engine, tmp_path: Path
) -> None:
    config = _config()
    result = _seed(tmp_path, config, "RESEARCH-7805")
    _record(
        config,
        gid="OPEV-7840",
        pos="POS-7840",
        symbol="TSLA",
        kind=OperatorPositionEventKind.OPENED,
        quantity=3,
        price="700",
        at=_AS_OF_BREAKOUT + timedelta(days=1),
        cites="POSPLAN-0001",
    )
    audit = _audit(config, result.identity)  # type: ignore[attr-defined]
    unlinked = audit.unlinked_open_positions[0]
    assert unlinked.reason is UnlinkedPositionReason.CITES_PLAN_OUTSIDE_THIS_SESSION
    assert unlinked.cited_plan_governance_id == "POSPLAN-0001"


def test_m078_events_after_as_of_are_excluded_over_real_rows(
    clean_tables: Engine, tmp_path: Path
) -> None:
    config = _config()
    result = _seed(tmp_path, config, "RESEARCH-7806")
    target = _audit(config, result.identity).entries[0]  # type: ignore[attr-defined]
    _record(
        config,
        gid="OPEV-7850",
        pos="POS-7850",
        symbol=target.instrument_symbol,
        kind=OperatorPositionEventKind.OPENED,
        quantity=5,
        price="100",
        at=_AUDIT_AS_OF + timedelta(days=3),
        cites=target.position_plan_governance_id,
    )
    audit = _audit(config, result.identity)  # type: ignore[attr-defined]
    entry = next(
        e
        for e in audit.entries
        if e.position_plan_governance_id == target.position_plan_governance_id
    )
    assert entry.status is FollowThroughStatus.NO_ASSERTED_POSITION_RECORDED
    assert audit.excluded_future_event_count == 1


def test_m078_missing_ledger_is_withheld_not_reported_as_nothing_recorded(
    clean_tables: Engine, tmp_path: Path
) -> None:
    config = _config()
    result = _seed(tmp_path, config, "RESEARCH-7807")
    audit = _audit(config, result.identity, with_ledger=False)  # type: ignore[attr-defined]
    assert audit.outcome is FollowThroughOutcome.NOT_ASSESSABLE
    assert audit.unassessable_reason is FollowThroughUnassessableReason.LEDGER_UNAVAILABLE


def test_m078_naive_as_of_is_a_request_error_not_a_data_claim(
    clean_tables: Engine, tmp_path: Path
) -> None:
    """Implementation review R03: a naive as_of used to be reported as
    LEDGER_INCOHERENT, sending the operator hunting for corrupt data."""
    config = _config()
    result = _seed(tmp_path, config, "RESEARCH-7808")
    with pytest.raises(ValueError, match="timezone-aware"):
        _audit(
            config,
            result.identity,  # type: ignore[attr-defined]
            as_of=datetime(2026, 1, 20, 12, 0),  # noqa: DTZ001 - deliberately naive
        )


def test_m078_text_and_json_agree_and_carry_no_money(clean_tables: Engine, tmp_path: Path) -> None:
    config = _config()
    result = _seed(tmp_path, config, "RESEARCH-7809")
    target = _audit(config, result.identity).entries[0]  # type: ignore[attr-defined]
    _record(
        config,
        gid="OPEV-7860",
        pos="POS-7860",
        symbol=target.instrument_symbol,
        kind=OperatorPositionEventKind.OPENED,
        quantity=4,
        price="123.456789",
        at=_AS_OF_BREAKOUT + timedelta(days=1),
        cites=target.position_plan_governance_id,
    )
    audit = _audit(config, result.identity)  # type: ignore[attr-defined]
    payload = render_follow_through_json(audit)
    rendered = render_follow_through_text(audit)

    assert payload["outcome"] == audit.outcome.value
    assert payload["entries"][0]["status"] in rendered
    assert "123.456789" not in rendered
    assert "123.456789" not in json.dumps(payload)
    assert "NOT realized or unrealized P&L" in rendered


def test_m078_is_deterministic_across_two_independent_audits(
    clean_tables: Engine, tmp_path: Path
) -> None:
    config = _config()
    result = _seed(tmp_path, config, "RESEARCH-7810")
    _record(
        config,
        gid="OPEV-7870",
        pos="POS-7870",
        symbol="TSLA",
        kind=OperatorPositionEventKind.OPENED,
        quantity=2,
        price="700",
        at=_AS_OF_BREAKOUT + timedelta(days=1),
    )
    first = _audit(config, result.identity)  # type: ignore[attr-defined]
    second = _audit(config, result.identity)  # type: ignore[attr-defined]
    assert first == second


def test_m078_reads_a_consistent_snapshot_while_a_writer_appends(
    clean_tables: Engine, tmp_path: Path
) -> None:
    config = _config()
    result = _seed(tmp_path, config, "RESEARCH-7811")
    _record(
        config,
        gid="OPEV-7880",
        pos="POS-7880",
        symbol="TSLA",
        kind=OperatorPositionEventKind.OPENED,
        quantity=2,
        price="700",
        at=_AS_OF_BREAKOUT + timedelta(days=1),
    )
    barrier = threading.Barrier(2)

    def writer() -> None:
        barrier.wait(timeout=20)
        _record(
            config,
            gid="OPEV-7881",
            pos="POS-7881",
            symbol="NVDA",
            kind=OperatorPositionEventKind.OPENED,
            quantity=1,
            price="50",
            at=_AS_OF_BREAKOUT + timedelta(days=2),
        )

    def reader() -> ResearchDecisionFollowThrough:
        barrier.wait(timeout=20)
        return _audit(config, result.identity)  # type: ignore[attr-defined]

    with ThreadPoolExecutor(max_workers=2) as pool:
        writer_future = pool.submit(writer)
        reader_future = pool.submit(reader)
        writer_future.result(timeout=60)
        snapshot = reader_future.result(timeout=60)

    # Either the pre-write or the post-write ledger -- never a torn state.
    assert len(snapshot.unlinked_open_positions) in {1, 2}
    final = _audit(config, result.identity)  # type: ignore[attr-defined]
    assert len(final.unlinked_open_positions) == 2


def test_m078_m077_compatibility_both_artifacts_agree_on_the_same_ledger(
    clean_tables: Engine, tmp_path: Path
) -> None:
    """The frozen M077 view and the new M078 view must not contradict each
    other about what is open."""
    from empirical_platform.usecases.build_daily_research_brief import (
        BuildDailyResearchBriefHandler,
        BuildDailyResearchBriefQuery,
    )

    config = _config()
    result = _seed(tmp_path, config, "RESEARCH-7812")
    target = _audit(config, result.identity).entries[0]  # type: ignore[attr-defined]
    _record(
        config,
        gid="OPEV-7890",
        pos="POS-7890",
        symbol=target.instrument_symbol,
        kind=OperatorPositionEventKind.OPENED,
        quantity=5,
        price="100",
        at=_AS_OF_BREAKOUT - timedelta(days=1),
        cites=target.position_plan_governance_id,
    )
    audit = _audit(config, result.identity, as_of=_AS_OF_BREAKOUT)  # type: ignore[attr-defined]

    with postgres_repository_runtime(config) as runtime:
        brief_handler = BuildDailyResearchBriefHandler(
            research_session_repository=runtime.research_sessions,
            decision_candidate_repository=runtime.decision_candidates,
            trade_plan_repository=runtime.trade_plans,
            position_plan_repository=runtime.position_plans,
            operator_position_ledger_repository=runtime.operator_position_ledger,
        )
        brief = brief_handler.handle(
            BuildDailyResearchBriefQuery(identity=result.identity)  # type: ignore[attr-defined,arg-type]
        )
    portfolio = brief.portfolio_aware_capital_assessment
    assert portfolio is not None

    # M077 suppressed the plan as already acted upon; M078 reports the same
    # position as an open assertion citing it. Same ledger, same conclusion.
    assert target.position_plan_governance_id in portfolio.plans_already_acted_upon
    entry = next(
        e
        for e in audit.entries
        if e.position_plan_governance_id == target.position_plan_governance_id
    )
    assert entry.status is FollowThroughStatus.ASSERTED_POSITION_OPEN


# ---------------------------------------------------------------------------
# Owner correction: what the persistence layer itself permits, and the
# defensive read boundary either way
# ---------------------------------------------------------------------------


def test_m078_postgresql_rejects_a_blank_plan_reference_at_the_foreign_key(
    clean_tables: Engine, tmp_path: Path
) -> None:
    """Attack H, first half. The frozen M070 schema declares
    `position_plan_governance_id` as a FOREIGN KEY to `position_plan`, so a
    blank id cannot be persisted at all. That is proven here rather than
    assumed -- and M078's domain guard is retained anyway, because the read
    boundary must not depend on a constraint in another milestone's table.
    """
    config = _config()
    result = _seed(tmp_path, config, "RESEARCH-7813")
    with clean_tables.begin() as conn:
        decision = conn.execute(
            text(
                "SELECT session_runtime_id, instrument_symbol FROM "
                "research_session_decision WHERE position_plan_governance_id IS NOT NULL "
                "LIMIT 1"
            )
        ).one()
        with pytest.raises(Exception) as excinfo:  # noqa: PT011 - driver-specific type
            conn.execute(
                text(
                    "UPDATE research_session_decision SET position_plan_governance_id = '' "
                    "WHERE session_runtime_id = :sid AND instrument_symbol = :sym"
                ),
                {"sid": decision.session_runtime_id, "sym": decision.instrument_symbol},
            )
    assert "foreign key" in str(excinfo.value).lower()
    assert result is not None


def test_m078_postgresql_permits_one_plan_id_across_two_instruments(
    clean_tables: Engine, tmp_path: Path
) -> None:
    """Attack H, second half. The foreign key does NOT prevent two decisions
    citing one plan id with different instruments, so the malformed form M078
    must defend against is genuinely persistable -- and the usecase withholds
    over real rows rather than fabricating a join.
    """
    config = _config()
    result = _seed(tmp_path, config, "RESEARCH-7814")
    before = _audit(config, result.identity)  # type: ignore[attr-defined]
    assert len(before.entries) >= 2, "the session must approve at least two plans"
    keep, overwrite = before.entries[0], before.entries[1]

    # Point the second decision at the first decision's plan id. Both rows keep
    # their own instrument, so one plan id now names two instruments.
    with clean_tables.begin() as conn:
        conn.execute(
            text(
                "UPDATE research_session_decision "
                "SET position_plan_governance_id = :keep "
                "WHERE session_runtime_id = :sid AND instrument_symbol = :sym"
            ),
            {
                "keep": keep.position_plan_governance_id,
                "sid": str(result.identity.runtime_id),  # type: ignore[attr-defined]
                "sym": overwrite.instrument_symbol,
            },
        )
        rows = conn.execute(
            text(
                "SELECT instrument_symbol FROM research_session_decision "
                "WHERE position_plan_governance_id = :keep ORDER BY instrument_symbol"
            ),
            {"keep": keep.position_plan_governance_id},
        ).fetchall()
    assert len(rows) == 2, "PostgreSQL must permit the malformed form for this attack"

    after = _audit(config, result.identity)  # type: ignore[attr-defined]
    assert after.outcome is FollowThroughOutcome.NOT_ASSESSABLE
    assert (
        after.unassessable_reason
        is FollowThroughUnassessableReason.SESSION_PLAN_REFERENCES_INCOHERENT
    )
    assert after.entries == ()
    assert after.unlinked_open_positions == ()
    assert after.approved_plan_count == 0


def test_m078_ambiguous_session_withholds_in_both_renderings(
    clean_tables: Engine, tmp_path: Path
) -> None:
    """Attack I. Text and JSON must carry the same withholding reason, with no
    monetary data and no claim about the operator's conduct."""
    config = _config()
    result = _seed(tmp_path, config, "RESEARCH-7815")
    before = _audit(config, result.identity)  # type: ignore[attr-defined]
    keep, overwrite = before.entries[0], before.entries[1]
    with clean_tables.begin() as conn:
        conn.execute(
            text(
                "UPDATE research_session_decision "
                "SET position_plan_governance_id = :keep "
                "WHERE session_runtime_id = :sid AND instrument_symbol = :sym"
            ),
            {
                "keep": keep.position_plan_governance_id,
                "sid": str(result.identity.runtime_id),  # type: ignore[attr-defined]
                "sym": overwrite.instrument_symbol,
            },
        )

    audit = _audit(config, result.identity)  # type: ignore[attr-defined]
    payload = render_follow_through_json(audit)
    rendered = render_follow_through_text(audit)

    assert payload["outcome"] == "NOT_ASSESSABLE"
    assert payload["unassessable_reason"] == "SESSION_PLAN_REFERENCES_INCOHERENT"
    assert "SESSION_PLAN_REFERENCES_INCOHERENT" in rendered
    assert payload["entries"] == []
    assert payload["unlinked_open_positions"] == []
    # Conduct words must be absent. "profit" is NOT checked as a bare
    # substring: the banner legitimately contains "NOT a profitability claim",
    # so the meaningful assertion is that the DENIAL is present.
    for forbidden in ("ignored", "failed to", "did not act"):
        assert forbidden not in rendered.lower()
    assert "NOT a profitability claim" in rendered
    assert "no monetary value of any kind" in rendered
