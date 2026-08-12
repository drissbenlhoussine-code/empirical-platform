"""MILESTONE-071 real-PostgreSQL daily research session continuity
acceptance tests.

Covers session-history listing, day-over-day comparison against a real,
multi-session PostgreSQL history, raw-SQL cross-verification, universe
-filter correctness, day-1 (no-prior-session) semantics, cross-universe
non-comparison, comparison against a FAILED baseline, and the real
installed list/compare CLI subprocesses. Mirrors the established M070
offline-acceptance pattern (`FakeMarketDataSource` + real PostgreSQL,
zero network dependency -- this milestone's own scope never touches
market-data acquisition).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
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
from empirical_platform.entrypoints._composition import postgres_repository_runtime
from empirical_platform.shared.config.settings import PostgreSQLConfigSnapshot
from empirical_platform.shared.identifiers import UuidRuntimeIdentifierGenerator
from empirical_platform.usecases.compare_daily_research_sessions import (
    CompareDailyResearchSessionsHandler,
    CompareDailyResearchSessionsQuery,
)
from empirical_platform.usecases.list_daily_research_sessions import (
    ListDailyResearchSessionsHandler,
    ListDailyResearchSessionsQuery,
)
from empirical_platform.usecases.run_daily_research_session import (
    RunDailyResearchSessionHandler,
    build_run_daily_research_session_command,
)

pytestmark = pytest.mark.integration

_REPO_ROOT = Path(__file__).resolve().parents[2]
_T0 = datetime(2026, 1, 1, tzinfo=UTC)

_ALL_TABLES = [
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
        application_name="empirical-platform-m071-test",
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
        c = breakout_close * (Decimal("1") + Decimal("0.01") * j)
        high = c * Decimal("1.01")
        low = c * Decimal("0.99")
        lines.append(f"{ts},{c:.4f},{high:.4f},{low:.4f},{c:.4f},{breakout_vol}")
    return ("\n".join(lines) + "\n").encode()


_FIXTURES = {
    "AAPL": _breakout_csv(Decimal("100"), Decimal("0.10"), 500000),
    "MSFT": _breakout_csv(Decimal("400"), Decimal("0.08"), 400000),
}
# The reference period (days 0-9) is flat -- no breakout, strategy
# evaluates NO_TRADE. The breakout period (days 10-15) genuinely
# triggers a LONG_CANDIDATE. Running the SAME fixture bytes at two
# different as_of dates therefore produces a genuine, unforced
# day-over-day state transition -- exactly the "meaningful day-over-day
# state/history semantics" the mission asks to be proven, not a
# fabricated difference between two hand-authored fixtures.
_AS_OF_FLAT = _T0 + timedelta(days=5)
# Day 10 is the first breakout bar. With reference_window_size=4 the
# reference window (days 6-9) stays entirely within the flat period, so
# day 10's own elevated close/volume genuinely clears both the price and
# volume conditions. One day later (day 11) the *reference window itself*
# would already include day 10's own elevated high, silently absorbing
# the breakout into the reference statistics and masking the signal --
# confirmed directly via smoke-testing, not assumed.
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


def test_full_lifecycle_list_and_compare_with_raw_sql_verification(
    clean_tables: Engine, tmp_path: Path
) -> None:
    config = _config()
    day_a = _run_session(
        session_governance_id="RESEARCH-7001",
        artifact_path=tmp_path / "day_a.json",
        config=config,
        as_of=_AS_OF_FLAT,
    )
    day_b = _run_session(
        session_governance_id="RESEARCH-7002",
        artifact_path=tmp_path / "day_b.json",
        config=config,
        as_of=_AS_OF_BREAKOUT,
    )
    assert day_a.status.value == "COMPLETED"  # type: ignore[attr-defined]
    assert day_b.status.value == "COMPLETED"  # type: ignore[attr-defined]

    with postgres_repository_runtime(config) as runtime:
        list_handler = ListDailyResearchSessionsHandler(repository=runtime.research_sessions)
        summaries = list_handler.handle(
            ListDailyResearchSessionsQuery(universe=("AAPL", "MSFT"), limit=10)
        )
        assert [str(s.identity.governance_id) for s in summaries] == [
            "RESEARCH-7002",
            "RESEARCH-7001",
        ]

        compare_handler = CompareDailyResearchSessionsHandler(repository=runtime.research_sessions)
        result = compare_handler.handle(
            CompareDailyResearchSessionsQuery(identity=day_b.identity)  # type: ignore[attr-defined]
        )

    assert result.baseline is not None
    assert result.baseline.identity == day_a.identity  # type: ignore[attr-defined]
    by_symbol = {e.instrument_symbol: e for e in result.entries}
    assert by_symbol["AAPL"].outcome.value == "CHANGED"
    assert by_symbol["AAPL"].baseline_scan_decision == "NO_TRADE"
    assert by_symbol["AAPL"].target_scan_decision == "LONG_CANDIDATE"
    assert by_symbol["MSFT"].outcome.value == "CHANGED"

    # Raw SQL cross-verification: independently confirm the two sessions
    # and their own scan_decision values, not through any production
    # query path.
    with clean_tables.begin() as conn:
        rows = conn.execute(
            text(
                "SELECT r.governance_id, rd.instrument_symbol, rd.scan_decision "
                "FROM research_session r "
                "JOIN research_session_decision rd ON rd.session_runtime_id = r.runtime_id "
                "WHERE r.governance_id IN ('RESEARCH-7001', 'RESEARCH-7002') "
                "ORDER BY r.governance_id, rd.instrument_symbol"
            )
        ).fetchall()
    raw = {(row.governance_id, row.instrument_symbol): row.scan_decision for row in rows}
    assert raw[("RESEARCH-7001", "AAPL")] == "NO_TRADE"
    assert raw[("RESEARCH-7002", "AAPL")] == "LONG_CANDIDATE"


def test_list_filters_by_universe(clean_tables: Engine, tmp_path: Path) -> None:
    config = _config()
    aapl_msft_session = _run_session(
        session_governance_id="RESEARCH-7101",
        artifact_path=tmp_path / "a.json",
        config=config,
        universe=("AAPL", "MSFT"),
    )
    goog_session = _run_session(
        session_governance_id="RESEARCH-7102",
        artifact_path=tmp_path / "b.json",
        config=config,
        universe=("MSFT", "GOOG"),
        fixtures={
            "MSFT": _FIXTURES["MSFT"],
            "GOOG": _breakout_csv(Decimal("150"), Decimal("0.05"), 10000),
        },
    )
    assert aapl_msft_session.status.value == "COMPLETED"  # type: ignore[attr-defined]
    assert goog_session.status.value == "COMPLETED"  # type: ignore[attr-defined]

    with postgres_repository_runtime(config) as runtime:
        handler = ListDailyResearchSessionsHandler(repository=runtime.research_sessions)
        aapl_msft_only = handler.handle(
            ListDailyResearchSessionsQuery(universe=("AAPL", "MSFT"), limit=10)
        )
        goog_msft_only = handler.handle(
            ListDailyResearchSessionsQuery(universe=("GOOG", "MSFT"), limit=10)
        )
        unfiltered = handler.handle(ListDailyResearchSessionsQuery(universe=None, limit=10))

    assert [str(s.identity.governance_id) for s in aapl_msft_only] == ["RESEARCH-7101"]
    assert [str(s.identity.governance_id) for s in goog_msft_only] == ["RESEARCH-7102"]
    assert len(unfiltered) == 2


def test_compare_no_prior_session_is_day_one(clean_tables: Engine, tmp_path: Path) -> None:
    config = _config()
    session = _run_session(
        session_governance_id="RESEARCH-7201",
        artifact_path=tmp_path / "only.json",
        config=config,
    )
    assert session.status.value == "COMPLETED"  # type: ignore[attr-defined]

    with postgres_repository_runtime(config) as runtime:
        handler = CompareDailyResearchSessionsHandler(repository=runtime.research_sessions)
        result = handler.handle(
            CompareDailyResearchSessionsQuery(identity=session.identity)  # type: ignore[attr-defined]
        )

    assert result.baseline is None
    assert len(result.entries) == 2
    assert all(e.outcome.value == "NEW" for e in result.entries)


def test_compare_different_universe_sessions_are_never_compared(
    clean_tables: Engine, tmp_path: Path
) -> None:
    config = _config()
    earlier_different_universe = _run_session(
        session_governance_id="RESEARCH-7301",
        artifact_path=tmp_path / "earlier.json",
        config=config,
        universe=("AAPL",),
        fixtures={"AAPL": _FIXTURES["AAPL"]},
        as_of=_AS_OF_FLAT,
    )
    later_target = _run_session(
        session_governance_id="RESEARCH-7302",
        artifact_path=tmp_path / "later.json",
        config=config,
        universe=("AAPL", "MSFT"),
        as_of=_AS_OF_BREAKOUT,
    )
    assert earlier_different_universe.status.value == "COMPLETED"  # type: ignore[attr-defined]
    assert later_target.status.value == "COMPLETED"  # type: ignore[attr-defined]

    with postgres_repository_runtime(config) as runtime:
        handler = CompareDailyResearchSessionsHandler(repository=runtime.research_sessions)
        result = handler.handle(
            CompareDailyResearchSessionsQuery(identity=later_target.identity)  # type: ignore[attr-defined]
        )

    # The single-instrument earlier session must never be picked as the
    # baseline for the two-instrument target -- universes must match
    # exactly.
    assert result.baseline is None
    assert all(e.outcome.value == "NEW" for e in result.entries)


def test_compare_against_failed_baseline_surfaces_diagnostic_info(
    clean_tables: Engine, tmp_path: Path
) -> None:
    config = _config()
    failed_baseline = _run_session(
        session_governance_id="RESEARCH-7401",
        artifact_path=tmp_path / "failed.json",
        config=config,
        universe=("AAPL", "ZZZZ"),
        fixtures={"AAPL": _FIXTURES["AAPL"]},
        as_of=_AS_OF_FLAT,
    )
    assert failed_baseline.status.value == "FAILED"  # type: ignore[attr-defined]

    successful_target = _run_session(
        session_governance_id="RESEARCH-7402",
        artifact_path=tmp_path / "success.json",
        config=config,
        universe=("AAPL", "ZZZZ"),
        fixtures={"AAPL": _FIXTURES["AAPL"], "ZZZZ": _FIXTURES["MSFT"]},
        as_of=_AS_OF_BREAKOUT,
    )
    assert successful_target.status.value == "COMPLETED"  # type: ignore[attr-defined]

    with postgres_repository_runtime(config) as runtime:
        handler = CompareDailyResearchSessionsHandler(repository=runtime.research_sessions)
        result = handler.handle(
            CompareDailyResearchSessionsQuery(identity=successful_target.identity)  # type: ignore[attr-defined]
        )

    assert result.baseline is not None
    assert result.baseline.status.value == "FAILED"
    # The FAILED baseline persisted zero decisions (partial-failure
    # semantics from M070), so every target instrument is honestly NEW.
    assert all(e.outcome.value == "NEW" for e in result.entries)


def test_real_cli_subprocess_list_and_compare(clean_tables: Engine, tmp_path: Path) -> None:
    """The real installed list/compare CLIs, run as genuine subprocesses
    against real PostgreSQL -- no Python shortcut for canonical
    acceptance."""
    config = _config()
    day_a = _run_session(
        session_governance_id="RESEARCH-7501",
        artifact_path=tmp_path / "cli_a.json",
        config=config,
        as_of=_AS_OF_FLAT,
    )
    day_b = _run_session(
        session_governance_id="RESEARCH-7502",
        artifact_path=tmp_path / "cli_b.json",
        config=config,
        as_of=_AS_OF_BREAKOUT,
    )
    assert day_a.status.value == "COMPLETED"  # type: ignore[attr-defined]
    assert day_b.status.value == "COMPLETED"  # type: ignore[attr-defined]

    env = dict(os.environ)
    env["EMPIRICAL_PLATFORM_POSTGRES_HOST"] = config.host
    env["EMPIRICAL_PLATFORM_POSTGRES_PORT"] = str(config.port)
    env["EMPIRICAL_PLATFORM_POSTGRES_DATABASE"] = config.database
    env["EMPIRICAL_PLATFORM_POSTGRES_USER"] = config.user
    env["EMPIRICAL_PLATFORM_POSTGRES_PASSWORD"] = config.password.get_secret_value()

    list_result = subprocess.run(  # noqa: S603
        [
            sys.executable,
            "-m",
            "empirical_platform.entrypoints.list_daily_research_sessions",
            "10",
            "AAPL",
            "MSFT",
        ],
        cwd=str(_REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
        check=True,
        timeout=60,
    )
    list_payload = json.loads(list_result.stdout)
    governance_ids = [s["session_governance_id"] for s in list_payload["FACT"]["sessions"]]
    assert governance_ids == ["RESEARCH-7502", "RESEARCH-7501"]

    compare_result = subprocess.run(  # noqa: S603
        [
            sys.executable,
            "-m",
            "empirical_platform.entrypoints.compare_daily_research_sessions",
            "RESEARCH-7502",
            str(day_b.identity.runtime_id),  # type: ignore[attr-defined]
        ],
        cwd=str(_REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
        check=True,
        timeout=60,
    )
    compare_payload = json.loads(compare_result.stdout)
    assert compare_payload["FACT"]["session_governance_id"] == "RESEARCH-7502"
    assert compare_payload["CONTINUITY"]["baseline_session_governance_id"] == "RESEARCH-7501"
    changed_symbols = {e["instrument_symbol"] for e in compare_payload["CONTINUITY"]["changed"]}
    assert changed_symbols == {"AAPL", "MSFT"}
