"""MILESTONE-061 real-PostgreSQL historical backtest acceptance tests."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from collections.abc import Iterator
from decimal import Decimal
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command as alembic_command
from alembic.config import Config
from pydantic import SecretStr
from sqlalchemy import text
from sqlalchemy.engine import Engine

from empirical_platform.entrypoints.get_historical_backtest_run import (
    run_get_historical_backtest_run,
)
from empirical_platform.entrypoints.run_historical_backtest import run_historical_backtest
from empirical_platform.shared.config.settings import PostgreSQLConfigSnapshot
from empirical_platform.shared.contracts.repository import AggregateAlreadyExists
from empirical_platform.shared.identifiers import DeterministicRuntimeIdentifierGenerator

pytestmark = pytest.mark.integration

_REPO_ROOT = Path(__file__).resolve().parents[2]
_FIXTURE_PATH = str(
    _REPO_ROOT
    / "tests"
    / "fixtures"
    / "m061_historical_backtest"
    / "synthetic_6instrument_historical_backtest_dataset.json"
)


def _integration_enabled() -> bool:
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
        application_name="empirical-platform-m061-test",
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
    if not _integration_enabled():
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
        conn.execute(text("TRUNCATE historical_backtest_trade, historical_backtest_run CASCADE"))
    return upgraded_schema


def test_full_historical_backtest_lifecycle_and_raw_sql_verification(
    clean_tables: Engine,
) -> None:
    config = _config()
    generator = DeterministicRuntimeIdentifierGenerator(
        [f"61010000-0000-4000-8000-{index:012d}" for index in range(1, 500)]
    )
    run = run_historical_backtest(
        run_governance_id="BTRUN-6101",
        dataset_file=_FIXTURE_PATH,
        account_equity=Decimal("10000"),
        risk_percent=Decimal("0.01"),
        identifier_generator=generator,
        config=config,
    )
    retrieved = run_get_historical_backtest_run(
        backtest_run_governance_id="BTRUN-6101",
        backtest_run_runtime_id=str(run.identity.runtime_id),
        config=config,
    )

    assert retrieved.identity == run.identity
    assert retrieved.dataset_id == run.dataset_id
    assert retrieved.dataset_sha256 == run.dataset_sha256
    assert retrieved.simulated_trade_count == 5
    assert [trade.outcome.value for trade in retrieved.trades] == [
        "TARGET_HIT",
        "STOP_HIT",
        "STOP_HIT",
        "NO_ENTRY",
        "TIME_EXIT",
    ]

    engine = sa.create_engine(config.sqlalchemy_url())
    try:
        with engine.connect() as conn:
            run_row = (
                conn.execute(
                    text(
                        "SELECT governance_id, dataset_id, dataset_version, dataset_sha256, "
                        "approved_trade_plan_count, simulated_trade_count, net_pnl "
                        "FROM historical_backtest_run WHERE governance_id = 'BTRUN-6101'"
                    )
                )
                .mappings()
                .one()
            )
            trade_rows = (
                conn.execute(
                    text(
                        "SELECT instrument_symbol, outcome, net_pnl, ambiguity_triggered "
                        "FROM historical_backtest_trade "
                        "WHERE backtest_run_runtime_id = :runtime_id ORDER BY trade_sequence"
                    ),
                    {"runtime_id": str(run.identity.runtime_id)},
                )
                .mappings()
                .all()
            )
    finally:
        engine.dispose()

    assert run_row["dataset_id"] == "DATASET-6101"
    assert run_row["dataset_version"] == "1"
    assert run_row["dataset_sha256"] == run.dataset_sha256
    assert run_row["approved_trade_plan_count"] == 5
    assert run_row["simulated_trade_count"] == 5
    assert run_row["net_pnl"] == Decimal("9.734280")
    assert [(row["instrument_symbol"], row["outcome"]) for row in trade_rows] == [
        ("AAPL", "TARGET_HIT"),
        ("AMZN", "STOP_HIT"),
        ("NVDA", "STOP_HIT"),
        ("GOOG", "NO_ENTRY"),
        ("TSLA", "TIME_EXIT"),
    ]
    assert trade_rows[2]["ambiguity_triggered"] is True


def test_historical_backtest_replay_is_deterministic(clean_tables: Engine) -> None:
    config = _config()
    run_one = run_historical_backtest(
        run_governance_id="BTRUN-6102",
        dataset_file=_FIXTURE_PATH,
        account_equity=Decimal("10000"),
        risk_percent=Decimal("0.01"),
        identifier_generator=DeterministicRuntimeIdentifierGenerator(
            [f"61020000-0000-4000-8000-{index:012d}" for index in range(1, 500)]
        ),
        config=config,
    )
    run_two = run_historical_backtest(
        run_governance_id="BTRUN-6103",
        dataset_file=_FIXTURE_PATH,
        account_equity=Decimal("10000"),
        risk_percent=Decimal("0.01"),
        identifier_generator=DeterministicRuntimeIdentifierGenerator(
            [f"61030000-0000-4000-8000-{index:012d}" for index in range(1, 500)]
        ),
        config=config,
    )

    assert [
        (str(trade.instrument), trade.outcome, trade.net_pnl, trade.holding_bars)
        for trade in run_one.trades
    ] == [
        (str(trade.instrument), trade.outcome, trade.net_pnl, trade.holding_bars)
        for trade in run_two.trades
    ]
    assert run_one.net_pnl == run_two.net_pnl
    assert run_one.maximum_realized_pnl_drawdown == run_two.maximum_realized_pnl_drawdown


def test_duplicate_historical_backtest_identity_raises_aggregate_already_exists(
    clean_tables: Engine,
) -> None:
    config = _config()
    run_historical_backtest(
        run_governance_id="BTRUN-6104",
        dataset_file=_FIXTURE_PATH,
        account_equity=Decimal("10000"),
        risk_percent=Decimal("0.01"),
        identifier_generator=DeterministicRuntimeIdentifierGenerator(
            [f"61040000-0000-4000-8000-{index:012d}" for index in range(1, 500)]
        ),
        config=config,
    )
    with pytest.raises(AggregateAlreadyExists):
        run_historical_backtest(
            run_governance_id="BTRUN-6104",
            dataset_file=_FIXTURE_PATH,
            account_equity=Decimal("10000"),
            risk_percent=Decimal("0.01"),
            identifier_generator=DeterministicRuntimeIdentifierGenerator(
                [f"61050000-0000-4000-8000-{index:012d}" for index in range(1, 500)]
            ),
            config=config,
        )


def test_cli_subprocess_runs_and_retrieves_real_backtest(clean_tables: Engine) -> None:
    env = os.environ.copy()
    env["EMPIRICAL_PLATFORM_POSTGRES_HOST"] = _config().host
    env["EMPIRICAL_PLATFORM_POSTGRES_PORT"] = str(_config().port)
    env["EMPIRICAL_PLATFORM_POSTGRES_DATABASE"] = _config().database
    env["EMPIRICAL_PLATFORM_POSTGRES_USER"] = _config().user
    env["EMPIRICAL_PLATFORM_POSTGRES_PASSWORD"] = _config().password.get_secret_value()
    env["PYTHONPATH"] = str(_REPO_ROOT / "src")

    run_result = subprocess.run(  # noqa: S603
        [
            sys.executable,
            "-c",
            ("from empirical_platform.entrypoints.run_historical_backtest import main; main()"),
            "BTRUN-6105",
            _FIXTURE_PATH,
            "10000",
            "0.01",
        ],
        capture_output=True,
        check=True,
        cwd=_REPO_ROOT,
        env=env,
        text=True,
    )
    payload = json.loads(run_result.stdout)
    assert payload["simulated_trade_count"] == 5

    get_result = subprocess.run(  # noqa: S603
        [
            sys.executable,
            "-c",
            ("from empirical_platform.entrypoints.get_historical_backtest_run import main; main()"),
            "BTRUN-6105",
            payload["runtime_id"],
        ],
        capture_output=True,
        check=True,
        cwd=_REPO_ROOT,
        env=env,
        text=True,
    )
    retrieved_payload = json.loads(get_result.stdout)
    assert retrieved_payload["dataset_id"] == "DATASET-6101"
    assert retrieved_payload["trades"][3]["outcome"] == "NO_ENTRY"
