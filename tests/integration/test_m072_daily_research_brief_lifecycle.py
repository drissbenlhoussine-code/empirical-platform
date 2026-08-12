"""MILESTONE-072 real-PostgreSQL daily research brief acceptance tests.

Covers a genuine day-over-day product demo (two real sessions against
real PostgreSQL, the later session's brief making the change visible in
human-readable text -- not raw JSON), raw-SQL cross-verification of risk
evidence, no-prior-session/day-1 semantics, a FAILED-session warning,
and the real installed `empirical-platform-daily-brief` CLI subprocess
(default-latest-session selection, explicit selection, `--json`).
Mirrors the established M070/M071 offline-acceptance pattern
(`FakeMarketDataSource` + real PostgreSQL, zero network dependency).
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
from empirical_platform.usecases.build_daily_research_brief import (
    BuildDailyResearchBriefHandler,
    BuildDailyResearchBriefQuery,
)
from empirical_platform.usecases.daily_research_brief_io import render_daily_research_brief_text
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
        application_name="empirical-platform-m072-test",
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


def test_full_lifecycle_brief_reflects_real_evidence_with_raw_sql_verification(
    clean_tables: Engine, tmp_path: Path
) -> None:
    """The genuine day-over-day product demo: two real sessions, the
    second session's own brief makes the NO_TRADE -> LONG_CANDIDATE
    change and its full risk evidence visible without raw JSON."""
    config = _config()
    day_a = _run_session(
        session_governance_id="RESEARCH-8001",
        artifact_path=tmp_path / "day_a.json",
        config=config,
        as_of=_AS_OF_FLAT,
    )
    day_b = _run_session(
        session_governance_id="RESEARCH-8002",
        artifact_path=tmp_path / "day_b.json",
        config=config,
        as_of=_AS_OF_BREAKOUT,
    )
    assert day_a.status.value == "COMPLETED"  # type: ignore[attr-defined]
    assert day_b.status.value == "COMPLETED"  # type: ignore[attr-defined]

    brief = _build_brief(config, day_b.identity)  # type: ignore[attr-defined]

    assert brief.baseline_session_governance_id == "RESEARCH-8001"  # type: ignore[attr-defined]
    by_symbol = {e.instrument_symbol: e for e in brief.entries}  # type: ignore[attr-defined]
    assert by_symbol["AAPL"].comparison_outcome.value == "CHANGED"
    assert by_symbol["AAPL"].attention_level.value == "ACTION_CANDIDATE"
    assert by_symbol["AAPL"].risk_evidence is not None
    assert by_symbol["MSFT"].comparison_outcome.value == "CHANGED"

    # Raw SQL cross-verification: the brief's own risk evidence must
    # equal the underlying trade_plan/position_plan rows exactly, not
    # through any production query path.
    with clean_tables.begin() as conn:
        row = conn.execute(
            text(
                "SELECT tp.entry_price, tp.reward_risk_ratio, pp.quantity, pp.position_notional "
                "FROM research_session_decision rd "
                "JOIN research_session r ON r.runtime_id = rd.session_runtime_id "
                "JOIN trade_plan tp ON tp.governance_id = rd.trade_plan_governance_id "
                "JOIN position_plan pp ON pp.governance_id = rd.position_plan_governance_id "
                "WHERE r.governance_id = 'RESEARCH-8002' AND rd.instrument_symbol = 'AAPL'"
            )
        ).fetchone()
    assert row is not None
    assert str(row.entry_price) == by_symbol["AAPL"].risk_evidence.entry_price
    assert str(row.reward_risk_ratio) == by_symbol["AAPL"].risk_evidence.reward_risk_ratio
    assert row.quantity == by_symbol["AAPL"].risk_evidence.quantity
    assert str(row.position_notional) == by_symbol["AAPL"].risk_evidence.position_notional

    # Human-readable text must make the change visible without the
    # operator ever reading raw JSON.
    rendered = render_daily_research_brief_text(brief)  # type: ignore[arg-type]
    assert "CHANGED" in rendered
    assert "AAPL" in rendered
    assert "ACTION_CANDIDATE" in rendered


def test_brief_no_prior_session_is_day_one(clean_tables: Engine, tmp_path: Path) -> None:
    config = _config()
    session = _run_session(
        session_governance_id="RESEARCH-8101",
        artifact_path=tmp_path / "only.json",
        config=config,
    )
    assert session.status.value == "COMPLETED"  # type: ignore[attr-defined]

    brief = _build_brief(config, session.identity)  # type: ignore[attr-defined]

    assert brief.baseline_session_governance_id is None  # type: ignore[attr-defined]
    assert brief.baseline_note is not None  # type: ignore[attr-defined]
    assert "first session" in brief.baseline_note  # type: ignore[attr-defined]
    assert all(e.comparison_outcome.value == "NEW" for e in brief.entries)  # type: ignore[attr-defined]


def test_brief_failed_session_surfaces_warning_and_still_renders(
    clean_tables: Engine, tmp_path: Path
) -> None:
    """An unregistered symbol forces a genuine FAILED session (same
    technique as M071's own FAILED-baseline test) -- the brief must
    surface a session-level WARNING and still render cleanly, never
    crash on partial data."""
    config = _config()
    failed = _run_session(
        session_governance_id="RESEARCH-8201",
        artifact_path=tmp_path / "failed.json",
        config=config,
        universe=("AAPL", "ZZZZ"),
        fixtures={"AAPL": _FIXTURES["AAPL"]},
        as_of=_AS_OF_FLAT,
    )
    assert failed.status.value == "FAILED"  # type: ignore[attr-defined]

    brief = _build_brief(config, failed.identity)  # type: ignore[attr-defined]

    assert brief.session_warnings  # type: ignore[attr-defined]
    assert any("FAILED" in w for w in brief.session_warnings)  # type: ignore[attr-defined]
    rendered = render_daily_research_brief_text(brief)  # type: ignore[arg-type]
    assert "WARNING" in rendered


def test_real_cli_daily_brief_default_selects_latest_and_json_matches_text(
    clean_tables: Engine, tmp_path: Path
) -> None:
    """The real installed CLI, run as genuine subprocesses -- default
    (no args) selects the single most recent session; `--json` and
    the default text renderer must agree on the same underlying facts."""
    config = _config()
    day_a = _run_session(
        session_governance_id="RESEARCH-8301",
        artifact_path=tmp_path / "cli_a.json",
        config=config,
        as_of=_AS_OF_FLAT,
    )
    day_b = _run_session(
        session_governance_id="RESEARCH-8302",
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

    text_result = subprocess.run(  # noqa: S603
        [sys.executable, "-m", "empirical_platform.entrypoints.build_daily_research_brief"],
        cwd=str(_REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
        check=True,
        timeout=60,
    )
    assert "RESEARCH-8302" in text_result.stdout
    assert (
        "RESEARCH-8301" not in text_result.stdout.split("compared against")[0].split("SESSION")[0]
    )

    json_result = subprocess.run(  # noqa: S603
        [
            sys.executable,
            "-m",
            "empirical_platform.entrypoints.build_daily_research_brief",
            "--json",
        ],
        cwd=str(_REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
        check=True,
        timeout=60,
    )
    payload = json.loads(json_result.stdout)
    assert payload["SESSION"]["session_governance_id"] == "RESEARCH-8302"
    assert payload["SESSION"]["baseline_session_governance_id"] == "RESEARCH-8301"
    changed_symbols = {e["instrument_symbol"] for e in payload["CHANGED"]}
    assert changed_symbols == {"AAPL", "MSFT"}

    explicit_result = subprocess.run(  # noqa: S603
        [
            sys.executable,
            "-m",
            "empirical_platform.entrypoints.build_daily_research_brief",
            "RESEARCH-8301",
            str(day_a.identity.runtime_id),  # type: ignore[attr-defined]
        ],
        cwd=str(_REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
        check=True,
        timeout=60,
    )
    assert "RESEARCH-8301" in explicit_result.stdout


def test_real_cli_daily_brief_no_session_ever_run_fails_cleanly(clean_tables: Engine) -> None:
    config = _config()
    env = dict(os.environ)
    env["EMPIRICAL_PLATFORM_POSTGRES_HOST"] = config.host
    env["EMPIRICAL_PLATFORM_POSTGRES_PORT"] = str(config.port)
    env["EMPIRICAL_PLATFORM_POSTGRES_DATABASE"] = config.database
    env["EMPIRICAL_PLATFORM_POSTGRES_USER"] = config.user
    env["EMPIRICAL_PLATFORM_POSTGRES_PASSWORD"] = config.password.get_secret_value()

    result = subprocess.run(  # noqa: S603
        [sys.executable, "-m", "empirical_platform.entrypoints.build_daily_research_brief"],
        cwd=str(_REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode != 0
    assert "no daily research session has ever been run" in result.stderr
