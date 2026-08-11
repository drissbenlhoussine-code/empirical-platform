"""MILESTONE-069 real-PostgreSQL market-data acquisition acceptance
tests.

Covers the full acquire -> persist -> retrieve lifecycle against real
PostgreSQL using the deterministic, offline `FakeMarketDataSource` (the
one place a real network fetch would be needed -- the real installed CLI
subprocess -- is additionally gated behind
`EMPIRICAL_PLATFORM_RUN_NETWORK_TESTS=1`, kept separate from the
canonical, network-free Postgres acceptance path), raw-SQL
cross-verification against the unmodified, frozen M065
`dataset_snapshot`/`dataset_snapshot_source_file` schema (no new table:
MILESTONE-069 deliberately reuses M065's own persistence unmodified),
duplicate-version rejection, and dataset-version coexistence.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command as alembic_command
from alembic.config import Config
from pydantic import SecretStr
from sqlalchemy import text
from sqlalchemy.engine import Engine

from empirical_platform.decision_candidate.market_data import BarInterval
from empirical_platform.decision_candidate.market_data_acquisition import FakeMarketDataSource
from empirical_platform.entrypoints._composition import postgres_repository_runtime
from empirical_platform.entrypoints.get_historical_dataset_snapshot import (
    run_get_historical_dataset_snapshot,
)
from empirical_platform.shared.config.settings import PostgreSQLConfigSnapshot
from empirical_platform.shared.contracts.repository import AggregateAlreadyExists
from empirical_platform.usecases.acquire_market_data_snapshot import (
    AcquireMarketDataSnapshotHandler,
    build_acquire_market_data_snapshot_command,
    build_trivial_instrument_master,
)

pytestmark = pytest.mark.integration

_REPO_ROOT = Path(__file__).resolve().parents[2]
_CLOCK_NOW = datetime(2026, 8, 11, 12, 0, tzinfo=UTC)
_AAPL_CSV = (
    b"timestamp,open,high,low,close,volume\n"
    b"2024-06-03T00:00:00+00:00,192.9000,194.9900,192.5200,194.0300,50080500\n"
    b"2024-06-04T00:00:00+00:00,194.6400,195.3200,193.0300,194.3500,47471400\n"
    b"2024-06-05T00:00:00+00:00,195.4000,196.9000,194.8700,195.8700,54156800\n"
)
_MSFT_CSV = (
    b"timestamp,open,high,low,close,volume\n"
    b"2024-06-03T00:00:00+00:00,415.0000,417.5000,413.0000,416.2500,20000000\n"
    b"2024-06-04T00:00:00+00:00,416.5000,418.0000,414.0000,417.0000,19000000\n"
    b"2024-06-05T00:00:00+00:00,417.2000,419.0000,415.5000,418.8000,18500000\n"
)


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
        application_name="empirical-platform-m069-test",
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
        conn.execute(
            text(
                "TRUNCATE dataset_snapshot_source_file, dataset_snapshot, instrument_master CASCADE"
            )
        )
    return upgraded_schema


def _acquire(
    *,
    dataset_id: str,
    dataset_version: str,
    symbols: tuple[str, ...],
    fixtures: dict[str, bytes],
    artifact_path: Path,
    config: PostgreSQLConfigSnapshot,
) -> object:
    source = FakeMarketDataSource(fixtures, clock=_FixedClock())
    with postgres_repository_runtime(config) as runtime:
        handler = AcquireMarketDataSnapshotHandler(
            dataset_snapshot_repository=runtime.dataset_snapshots,
            instrument_master_repository=runtime.instrument_masters,
            source=source,
            clock_now=_CLOCK_NOW,
        )
        return handler.handle(
            build_acquire_market_data_snapshot_command(
                dataset_id=dataset_id,
                dataset_version=dataset_version,
                symbols=symbols,
                start_date=_CLOCK_NOW.date().replace(day=1),
                end_date=_CLOCK_NOW.date(),
                interval=BarInterval.ONE_DAY,
                instrument_master=build_trivial_instrument_master(symbols),
                artifact_path=str(artifact_path),
                license_note="deterministic offline fixture, no license required",
            )
        )


class _FixedClock:
    def now(self) -> datetime:
        return _CLOCK_NOW


def test_full_acquisition_lifecycle_and_raw_sql_verification(
    clean_tables: Engine, tmp_path: Path
) -> None:
    config = _config()
    result = _acquire(
        dataset_id="DATASET-6900",
        dataset_version="1",
        symbols=("AAPL", "MSFT"),
        fixtures={"AAPL": _AAPL_CSV, "MSFT": _MSFT_CSV},
        artifact_path=tmp_path / "artifact.json",
        config=config,
    )
    assert result.snapshot.instrument_count == 2  # type: ignore[attr-defined]
    assert result.snapshot.total_row_count == 6  # type: ignore[attr-defined]
    assert result.snapshot.source_kind == "MARKET_DATA_ACQUISITION"  # type: ignore[attr-defined]
    assert result.snapshot.source_name == "FAKE_OFFLINE_FIXTURE"  # type: ignore[attr-defined]
    assert result.snapshot.price_semantics.value == "RAW_UNADJUSTED"  # type: ignore[attr-defined]

    # Retrieval reuses the unmodified, frozen M065 entrypoint verbatim --
    # no second retrieval path introduced.
    retrieved = run_get_historical_dataset_snapshot(
        dataset_id="DATASET-6900", dataset_version="1", config=config
    )
    assert retrieved.normalized_sha256 == result.snapshot.normalized_sha256  # type: ignore[attr-defined]
    assert retrieved.source_file_manifest == result.snapshot.source_file_manifest  # type: ignore[attr-defined]

    engine = sa.create_engine(config.sqlalchemy_url())
    try:
        with engine.connect() as conn:
            snapshot_row = (
                conn.execute(
                    text(
                        "SELECT source_kind, source_name, instrument_count, total_row_count "
                        "FROM dataset_snapshot WHERE dataset_id = 'DATASET-6900'"
                    )
                )
                .mappings()
                .one()
            )
            source_file_rows = (
                conn.execute(
                    text(
                        "SELECT instrument_symbol, sha256 FROM dataset_snapshot_source_file "
                        "WHERE dataset_id = 'DATASET-6900' ORDER BY instrument_symbol"
                    )
                )
                .mappings()
                .all()
            )
    finally:
        engine.dispose()

    assert snapshot_row["source_kind"] == "MARKET_DATA_ACQUISITION"
    assert snapshot_row["source_name"] == "FAKE_OFFLINE_FIXTURE"
    assert snapshot_row["instrument_count"] == 2
    assert snapshot_row["total_row_count"] == 6
    assert [r["instrument_symbol"] for r in source_file_rows] == ["AAPL", "MSFT"]


def test_reacquiring_same_dataset_version_is_rejected(clean_tables: Engine, tmp_path: Path) -> None:
    config = _config()
    _acquire(
        dataset_id="DATASET-6901",
        dataset_version="1",
        symbols=("AAPL",),
        fixtures={"AAPL": _AAPL_CSV},
        artifact_path=tmp_path / "a.json",
        config=config,
    )
    with pytest.raises(AggregateAlreadyExists):
        _acquire(
            dataset_id="DATASET-6901",
            dataset_version="1",
            symbols=("AAPL",),
            fixtures={"AAPL": _AAPL_CSV},
            artifact_path=tmp_path / "b.json",
            config=config,
        )


def test_missing_symbol_fixture_raises_before_persistence(
    clean_tables: Engine, tmp_path: Path
) -> None:
    config = _config()
    with pytest.raises(Exception, match="no fixture bars registered"):
        _acquire(
            dataset_id="DATASET-6902",
            dataset_version="1",
            symbols=("ZZZZ",),
            fixtures={"AAPL": _AAPL_CSV},
            artifact_path=tmp_path / "artifact.json",
            config=config,
        )
    engine = sa.create_engine(config.sqlalchemy_url())
    try:
        with engine.connect() as conn:
            count = conn.execute(
                text("SELECT count(*) FROM dataset_snapshot WHERE dataset_id = 'DATASET-6902'")
            ).scalar_one()
    finally:
        engine.dispose()
    assert count == 0


def test_dataset_version_coexistence(clean_tables: Engine, tmp_path: Path) -> None:
    config = _config()
    _acquire(
        dataset_id="DATASET-6903",
        dataset_version="1",
        symbols=("AAPL",),
        fixtures={"AAPL": _AAPL_CSV},
        artifact_path=tmp_path / "v1.json",
        config=config,
    )
    _acquire(
        dataset_id="DATASET-6903",
        dataset_version="2",
        symbols=("AAPL", "MSFT"),
        fixtures={"AAPL": _AAPL_CSV, "MSFT": _MSFT_CSV},
        artifact_path=tmp_path / "v2.json",
        config=config,
    )
    v1 = run_get_historical_dataset_snapshot(
        dataset_id="DATASET-6903", dataset_version="1", config=config
    )
    v2 = run_get_historical_dataset_snapshot(
        dataset_id="DATASET-6903", dataset_version="2", config=config
    )
    assert v1.instrument_count == 1  # type: ignore[attr-defined]
    assert v2.instrument_count == 2  # type: ignore[attr-defined]

    engine = sa.create_engine(config.sqlalchemy_url())
    try:
        with engine.connect() as conn:
            count = conn.execute(
                text("SELECT count(*) FROM dataset_snapshot WHERE dataset_id = 'DATASET-6903'")
            ).scalar_one()
    finally:
        engine.dispose()
    assert count == 2


def test_real_cli_subprocess_acquire_and_get(clean_tables: Engine, tmp_path: Path) -> None:
    """The one CLI-subprocess test that genuinely exercises the real,
    installed `empirical-platform-acquire-market-data-snapshot` CLI --
    which always uses the real network adapter by design (it has no Fake
    -adapter injection point, deliberately, since it is the production
    composition root) -- gated behind BOTH PostgreSQL and network opt-in,
    never required for canonical CI."""
    if not _network_enabled():
        pytest.skip("real-network tests require explicit opt-in")
    config = _config()
    env = dict(os.environ)
    env["EMPIRICAL_PLATFORM_POSTGRES_HOST"] = config.host
    env["EMPIRICAL_PLATFORM_POSTGRES_PORT"] = str(config.port)
    env["EMPIRICAL_PLATFORM_POSTGRES_DATABASE"] = config.database
    env["EMPIRICAL_PLATFORM_POSTGRES_USER"] = config.user
    env["EMPIRICAL_PLATFORM_POSTGRES_PASSWORD"] = config.password.get_secret_value()

    artifact_path = tmp_path / "cli_artifact.json"
    today = datetime.now(UTC).date()
    start = today.replace(day=1)

    acquire_result = subprocess.run(  # noqa: S603
        [
            sys.executable,
            "-m",
            "empirical_platform.entrypoints.acquire_market_data_snapshot",
            "DATASET-6910",
            "1",
            start.isoformat(),
            today.isoformat(),
            str(artifact_path),
            "AAPL",
        ],
        cwd=str(_REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert acquire_result.returncode == 0, acquire_result.stderr
    acquire_payload = json.loads(acquire_result.stdout)
    assert acquire_payload["adapter_source_name"] == "YAHOO_FINANCE_UNOFFICIAL_CHART_JSON"
    assert acquire_payload["snapshot"]["dataset_id"] == "DATASET-6910"

    get_result = subprocess.run(  # noqa: S603
        [
            sys.executable,
            "-m",
            "empirical_platform.entrypoints.get_historical_dataset_snapshot",
            "DATASET-6910",
            "1",
        ],
        cwd=str(_REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert get_result.returncode == 0, get_result.stderr
    get_payload = json.loads(get_result.stdout)
    assert get_payload["normalized_sha256"] == acquire_payload["snapshot"]["normalized_sha256"]
