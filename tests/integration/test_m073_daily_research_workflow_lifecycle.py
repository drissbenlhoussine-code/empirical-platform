"""MILESTONE-073 real-PostgreSQL, real-network one-command daily
research workflow acceptance tests.

The workflow entrypoint (`run_daily_research_workflow`) hardcodes the
real, network-capable `YahooFinanceChartMarketDataSource` with no
offline injection point at the entrypoint layer -- exactly mirroring
the established M070 precedent, where the underlying
`RunDailyResearchSessionHandler` is unit-tested offline with
`FakeMarketDataSource` at the usecase layer (reused, unmodified here),
while entrypoint-level acceptance is real-network-gated. Every test in
this file therefore requires both
`EMPIRICAL_PLATFORM_RUN_POSTGRES_TESTS=1` and
`EMPIRICAL_PLATFORM_RUN_NETWORK_TESTS=1`; none is required for
canonical CI.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from collections.abc import Iterator
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command as alembic_command
from alembic.config import Config
from pydantic import SecretStr
from sqlalchemy import text
from sqlalchemy.engine import Engine

from empirical_platform.entrypoints.run_daily_research_workflow import (
    run_daily_research_workflow,
)
from empirical_platform.shared.config.settings import PostgreSQLConfigSnapshot

pytestmark = pytest.mark.integration

_REPO_ROOT = Path(__file__).resolve().parents[2]

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


def _network_enabled() -> bool:
    return os.environ.get("EMPIRICAL_PLATFORM_RUN_NETWORK_TESTS") == "1"


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
        application_name="empirical-platform-m073-test",
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
    if not _network_enabled():
        pytest.skip("real-network tests require explicit opt-in")
    with upgraded_schema.begin() as conn:
        conn.execute(text(f"TRUNCATE {', '.join(_ALL_TABLES)} CASCADE"))  # noqa: S608
    return upgraded_schema


# A date safely in the past relative to any real-world "today" this
# suite might run on, so real Yahoo Finance data is guaranteed to
# exist for the requested as_of.
_AS_OF = (date.today() - timedelta(days=3)).isoformat()


def test_one_command_produces_a_complete_brief_for_the_session_it_just_created(
    clean_tables: Engine, tmp_path: Path
) -> None:
    """The central claim: one command, real data, one legible brief --
    no separate acquisition/research/brief steps, no manually-tracked
    session identifier."""
    config = _config()
    brief = run_daily_research_workflow(
        symbols=("AAPL", "MSFT"),
        as_of_date=_AS_OF,
        lookback_days=30,
        account_equity=Decimal("100000"),
        risk_percent=Decimal("0.01"),
        artifact_path=str(tmp_path / "artifact.json"),
        config=config,
    )

    assert brief.completion_status == "COMPLETED"
    assert brief.data_source == "YAHOO_FINANCE_UNOFFICIAL_CHART_JSON"
    assert brief.requested_universe == ("AAPL", "MSFT")
    assert brief.session_governance_id.startswith("RESEARCH-")

    # Raw SQL cross-verification: the session the workflow reports on
    # is genuinely the one it just persisted, independent of any
    # production query path.
    with clean_tables.begin() as conn:
        row = conn.execute(
            text(
                "SELECT data_source, requested_universe, status "
                "FROM research_session WHERE governance_id = :gid"
            ),
            {"gid": brief.session_governance_id},
        ).fetchone()
    assert row is not None
    assert row.status == "COMPLETED"
    assert row.data_source == "YAHOO_FINANCE_UNOFFICIAL_CHART_JSON"
    assert set(row.requested_universe) == {"AAPL", "MSFT"}


def test_second_invocation_compares_against_the_first(clean_tables: Engine, tmp_path: Path) -> None:
    config = _config()
    day_a = date.today() - timedelta(days=4)
    day_b = date.today() - timedelta(days=3)

    first = run_daily_research_workflow(
        symbols=("AAPL",),
        as_of_date=day_a.isoformat(),
        lookback_days=30,
        account_equity=Decimal("100000"),
        risk_percent=Decimal("0.01"),
        artifact_path=str(tmp_path / "a.json"),
        config=config,
    )
    second = run_daily_research_workflow(
        symbols=("AAPL",),
        as_of_date=day_b.isoformat(),
        lookback_days=30,
        account_equity=Decimal("100000"),
        risk_percent=Decimal("0.01"),
        artifact_path=str(tmp_path / "b.json"),
        config=config,
    )

    assert first.completion_status == "COMPLETED"
    assert second.completion_status == "COMPLETED"
    assert second.baseline_session_governance_id == first.session_governance_id


def test_invalid_symbol_produces_an_honest_failed_session_with_warning(
    clean_tables: Engine, tmp_path: Path
) -> None:
    """A real, non-existent ticker causes a genuine real-network
    failure (Yahoo returns HTTP 404) -- the workflow must not crash
    uninformatively; it must still return a brief carrying a
    session-level WARNING."""
    config = _config()
    brief = run_daily_research_workflow(
        symbols=("ZZZZINVALIDTICKER",),
        as_of_date=_AS_OF,
        lookback_days=30,
        account_equity=Decimal("100000"),
        risk_percent=Decimal("0.01"),
        artifact_path=str(tmp_path / "failed.json"),
        config=config,
    )

    assert brief.completion_status == "FAILED"
    assert brief.session_warnings
    assert any("FAILED" in w for w in brief.session_warnings)


def test_real_cli_subprocess_default_settings(clean_tables: Engine) -> None:
    """The real installed CLI, run as a genuine subprocess, using only
    its own documented defaults."""
    config = _config()
    env = dict(os.environ)
    env["EMPIRICAL_PLATFORM_POSTGRES_HOST"] = config.host
    env["EMPIRICAL_PLATFORM_POSTGRES_PORT"] = str(config.port)
    env["EMPIRICAL_PLATFORM_POSTGRES_DATABASE"] = config.database
    env["EMPIRICAL_PLATFORM_POSTGRES_USER"] = config.user
    env["EMPIRICAL_PLATFORM_POSTGRES_PASSWORD"] = config.password.get_secret_value()

    result = subprocess.run(  # noqa: S603
        [
            sys.executable,
            "-m",
            "empirical_platform.entrypoints.run_daily_research_workflow",
            "--json",
            "--as-of",
            _AS_OF,
            "GOOG",
        ],
        cwd=str(_REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
        check=True,
        timeout=60,
    )
    payload = json.loads(result.stdout)
    assert payload["SESSION"]["completion_status"] == "COMPLETED"
    assert payload["DATA_QUALITY"]["data_source"] == "YAHOO_FINANCE_UNOFFICIAL_CHART_JSON"
    assert payload["SESSION"]["session_governance_id"].startswith("RESEARCH-")
