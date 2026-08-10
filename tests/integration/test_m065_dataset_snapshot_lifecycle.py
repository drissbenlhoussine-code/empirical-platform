"""MILESTONE-065 real-PostgreSQL historical dataset snapshot + corporate-
action acceptance tests.

Covers the full import -> persist -> M061-backtest-reuse -> corporate-
action-stress-diagnostic lifecycle against real PostgreSQL, a real CLI
subprocess run of every M065 entrypoint plus the unmodified, frozen M061
`run-historical-backtest`/`get-historical-backtest-run` CLIs, raw-SQL
cross-verification of the persisted schema (including the polymorphic
`corporate_action` CHECK constraint), artifact-tamper rejection after
persistence, corporate-action-manifest tamper detection, and dataset-
version coexistence.
"""

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

from empirical_platform.entrypoints.get_corporate_action_semantics_stress import (
    run_get_corporate_action_semantics_stress,
)
from empirical_platform.entrypoints.get_historical_backtest_run import (
    run_get_historical_backtest_run,
)
from empirical_platform.entrypoints.get_historical_dataset_snapshot import (
    run_get_historical_dataset_snapshot,
)
from empirical_platform.entrypoints.import_historical_dataset_snapshot import (
    run_import_historical_dataset_snapshot,
)
from empirical_platform.entrypoints.run_corporate_action_semantics_stress import (
    run_run_corporate_action_semantics_stress,
)
from empirical_platform.entrypoints.run_historical_backtest import run_historical_backtest
from empirical_platform.shared.config.settings import PostgreSQLConfigSnapshot

pytestmark = pytest.mark.integration

_REPO_ROOT = Path(__file__).resolve().parents[2]
_FIXTURE_DIR = _REPO_ROOT / "tests" / "fixtures" / "m065_corporate_action_mechanics"
_INSTRUMENT_MASTER_PATH = _FIXTURE_DIR / "instrument_master.json"
_MANIFEST_PATH = _FIXTURE_DIR / "corporate_action_manifest.json"


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
        application_name="empirical-platform-m065-test",
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
        conn.execute(
            text(
                "TRUNCATE corporate_action_semantics_stress, corporate_action, "
                "dataset_snapshot_source_file, dataset_snapshot, historical_backtest_trade, "
                "historical_backtest_run, instrument_master CASCADE"
            )
        )
    return upgraded_schema


def _manifest_for(dataset_id: str, raw_version: str, tmp_path: Path) -> Path:
    """The corporate-action manifest is keyed to the exact (dataset_id,
    raw dataset_version) it describes -- synthesize a copy of the fixture
    manifest with those fields substituted so each test's own import call
    supplies a manifest the import handler's own validation will accept."""
    raw = json.loads(_MANIFEST_PATH.read_text(encoding="utf-8"))
    raw["dataset_id"] = dataset_id
    raw["dataset_version"] = raw_version
    path = tmp_path / f"manifest_{dataset_id}_{raw_version}.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    return path


def _run_import(
    *,
    dataset_id: str,
    raw_version: str,
    adjusted_version: str,
    raw_artifact: Path,
    adjusted_artifact: Path,
    config: PostgreSQLConfigSnapshot,
    tmp_path: Path,
    source_files_dir: Path = _FIXTURE_DIR,
    instrument_master_file: Path = _INSTRUMENT_MASTER_PATH,
    manifest_file: Path | None = None,
) -> object:
    resolved_manifest_file = manifest_file or _manifest_for(dataset_id, raw_version, tmp_path)
    return run_import_historical_dataset_snapshot(
        dataset_id=dataset_id,
        raw_dataset_version=raw_version,
        adjusted_dataset_version=adjusted_version,
        source_kind="CORPORATE_ACTION_MECHANICS_FIXTURE",
        source_name="M065 corporate action mechanics fixture",
        source_reference=str(source_files_dir),
        license_note="synthetic, no license required",
        interval="ONE_MINUTE",
        source_files_dir=str(source_files_dir),
        instrument_master_file=str(instrument_master_file),
        corporate_action_manifest_file=str(resolved_manifest_file),
        raw_artifact_path=str(raw_artifact),
        adjusted_artifact_path=str(adjusted_artifact),
        config=config,
    )


def test_full_import_lifecycle_and_raw_sql_verification(
    clean_tables: Engine, tmp_path: Path
) -> None:
    config = _config()
    raw_artifact = tmp_path / "raw.json"
    adjusted_artifact = tmp_path / "adjusted.json"

    result = _run_import(
        dataset_id="DATASET-6501",
        tmp_path=tmp_path,
        raw_version="1",
        adjusted_version="2-split-adjusted",
        raw_artifact=raw_artifact,
        adjusted_artifact=adjusted_artifact,
        config=config,
    )
    assert result.raw_snapshot.instrument_count == 4  # type: ignore[attr-defined]
    assert result.raw_snapshot.total_row_count == 120  # type: ignore[attr-defined]
    assert result.raw_snapshot.price_semantics.value == "RAW_UNADJUSTED"  # type: ignore[attr-defined]
    assert result.adjusted_snapshot is not None  # type: ignore[attr-defined]
    assert result.adjusted_snapshot.price_semantics.value == "SPLIT_ADJUSTED"  # type: ignore[attr-defined]
    assert (
        result.adjusted_snapshot.corporate_action_semantics.value  # type: ignore[attr-defined]
        == "SPLIT_AND_SYMBOL_CHANGE_AWARE"
    )
    assert (
        result.adjusted_snapshot.bundle_sha256 == result.raw_snapshot.bundle_sha256  # type: ignore[attr-defined]
    )
    assert (
        result.adjusted_snapshot.normalized_sha256  # type: ignore[attr-defined]
        != result.raw_snapshot.normalized_sha256  # type: ignore[attr-defined]
    )
    assert result.raw_artifact_sha256 == result.raw_snapshot.normalized_sha256  # type: ignore[attr-defined]
    assert (
        result.adjusted_artifact_sha256 == result.adjusted_snapshot.normalized_sha256  # type: ignore[attr-defined]
    )

    # Retrieval round trip.
    retrieved_adjusted = run_get_historical_dataset_snapshot(
        dataset_id="DATASET-6501", dataset_version="2-split-adjusted", config=config
    )
    assert retrieved_adjusted.normalized_sha256 == result.adjusted_snapshot.normalized_sha256  # type: ignore[attr-defined]

    # Real, unmodified, frozen M061 backtest CLI path reused verbatim against
    # the adjusted artifact -- proving "no parallel strategy/backtester".
    backtest_run = run_historical_backtest(
        run_governance_id="BTRUN-6501",
        dataset_file=str(adjusted_artifact),
        account_equity=Decimal("100000"),
        risk_percent=Decimal("0.01"),
        config=config,
    )
    assert backtest_run.dataset_sha256 == result.adjusted_snapshot.normalized_sha256  # type: ignore[attr-defined]

    retrieved_run = run_get_historical_backtest_run(
        backtest_run_governance_id="BTRUN-6501",
        backtest_run_runtime_id=str(backtest_run.identity.runtime_id),  # type: ignore[attr-defined]
        config=config,
    )
    assert retrieved_run.dataset_version == backtest_run.dataset_version  # type: ignore[attr-defined]

    # Corporate-action semantics stress diagnostic: correct (adjusted)
    # vs naive (raw) dataset interpretation.
    stress_result = run_run_corporate_action_semantics_stress(
        stress_governance_id="CASTR-6501",
        dataset_id="DATASET-6501",
        correct_dataset_version="2-split-adjusted",
        correct_dataset_file=str(adjusted_artifact),
        naive_dataset_version="1",
        naive_dataset_file=str(raw_artifact),
        correct_run_governance_id="BTRUN-6502",
        naive_run_governance_id="BTRUN-6503",
        account_equity=Decimal("100000"),
        risk_percent=Decimal("0.01"),
        config=config,
    )
    assert str(stress_result.dataset_id) == "DATASET-6501"  # type: ignore[attr-defined]

    retrieved_stress = run_get_corporate_action_semantics_stress(
        stress_governance_id="CASTR-6501",
        stress_runtime_id=str(stress_result.identity.runtime_id),  # type: ignore[attr-defined]
        config=config,
    )
    assert retrieved_stress.comparison == stress_result.comparison  # type: ignore[attr-defined]

    engine = sa.create_engine(config.sqlalchemy_url())
    try:
        with engine.connect() as conn:
            snapshot_rows = (
                conn.execute(
                    text(
                        "SELECT dataset_version, price_semantics, corporate_action_semantics, "
                        "bundle_sha256, normalized_sha256 FROM dataset_snapshot "
                        "WHERE dataset_id = 'DATASET-6501' ORDER BY dataset_version"
                    )
                )
                .mappings()
                .all()
            )
            source_file_count = conn.execute(
                text(
                    "SELECT count(*) FROM dataset_snapshot_source_file "
                    "WHERE dataset_id = 'DATASET-6501'"
                )
            ).scalar_one()
            action_rows = (
                conn.execute(
                    text(
                        "SELECT instrument_id, action_type, ratio_new_shares, ratio_old_shares, "
                        "old_symbol, new_symbol FROM corporate_action "
                        "WHERE dataset_id = 'DATASET-6501' ORDER BY instrument_id"
                    )
                )
                .mappings()
                .all()
            )
            instrument_count = conn.execute(
                text("SELECT count(*) FROM instrument_master")
            ).scalar_one()
            stress_row = (
                conn.execute(
                    text(
                        "SELECT comparison, correct_dataset_version, naive_dataset_version "
                        "FROM corporate_action_semantics_stress WHERE governance_id = 'CASTR-6501'"
                    )
                )
                .mappings()
                .one()
            )
    finally:
        engine.dispose()

    assert [row["dataset_version"] for row in snapshot_rows] == ["1", "2-split-adjusted"]
    assert snapshot_rows[0]["bundle_sha256"] == snapshot_rows[1]["bundle_sha256"]
    assert snapshot_rows[0]["normalized_sha256"] != snapshot_rows[1]["normalized_sha256"]
    # Two versions x 4 source files each.
    assert source_file_count == 8
    assert len(action_rows) == 3
    for row in action_rows:
        if row["action_type"] == "SYMBOL_CHANGE":
            assert row["ratio_new_shares"] is None
            assert row["ratio_old_shares"] is None
            assert row["old_symbol"] is not None
            assert row["new_symbol"] is not None
        else:
            assert row["ratio_new_shares"] is not None
            assert row["ratio_old_shares"] is not None
            assert row["old_symbol"] is None
            assert row["new_symbol"] is None
    assert instrument_count == 4
    assert stress_row["comparison"] in (
        "CORPORATE_ACTION_SEMANTICS_STRESS_IDENTICAL",
        "CORPORATE_ACTION_SEMANTICS_STRESS_DIFFERS",
    )
    assert stress_row["correct_dataset_version"] == "2-split-adjusted"
    assert stress_row["naive_dataset_version"] == "1"


def test_real_cli_subprocess_full_pipeline(clean_tables: Engine, tmp_path: Path) -> None:
    config = _config()
    env = dict(os.environ)
    env["EMPIRICAL_PLATFORM_POSTGRES_HOST"] = config.host
    env["EMPIRICAL_PLATFORM_POSTGRES_PORT"] = str(config.port)
    env["EMPIRICAL_PLATFORM_POSTGRES_DATABASE"] = config.database
    env["EMPIRICAL_PLATFORM_POSTGRES_USER"] = config.user
    env["EMPIRICAL_PLATFORM_POSTGRES_PASSWORD"] = config.password.get_secret_value()

    raw_artifact = tmp_path / "cli_raw.json"
    adjusted_artifact = tmp_path / "cli_adjusted.json"
    cli_manifest_path = _manifest_for("DATASET-6510", "1", tmp_path)

    import_result = subprocess.run(  # noqa: S603
        [
            sys.executable,
            "-m",
            "empirical_platform.entrypoints.import_historical_dataset_snapshot",
            "DATASET-6510",
            "1",
            "2-split-adjusted",
            "CORPORATE_ACTION_MECHANICS_FIXTURE",
            "M065 corporate action mechanics fixture",
            str(_FIXTURE_DIR),
            "synthetic, no license required",
            "ONE_MINUTE",
            str(_FIXTURE_DIR),
            str(_INSTRUMENT_MASTER_PATH),
            str(cli_manifest_path),
            str(raw_artifact),
            str(adjusted_artifact),
        ],
        cwd=str(_REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert import_result.returncode == 0, import_result.stderr
    import_payload = json.loads(import_result.stdout)
    assert import_payload["raw_snapshot"]["dataset_version"] == "1"
    assert import_payload["adjusted_snapshot"]["dataset_version"] == "2-split-adjusted"

    backtest_result = subprocess.run(  # noqa: S603
        [
            sys.executable,
            "-m",
            "empirical_platform.entrypoints.run_historical_backtest",
            "BTRUN-6510",
            str(adjusted_artifact),
            "100000",
            "0.01",
        ],
        cwd=str(_REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert backtest_result.returncode == 0, backtest_result.stderr
    backtest_payload = json.loads(backtest_result.stdout)
    assert (
        backtest_payload["dataset_sha256"]
        == import_payload["adjusted_snapshot"]["normalized_sha256"]
    )

    stress_result = subprocess.run(  # noqa: S603
        [
            sys.executable,
            "-m",
            "empirical_platform.entrypoints.run_corporate_action_semantics_stress",
            "CASTR-6510",
            "DATASET-6510",
            "2-split-adjusted",
            str(adjusted_artifact),
            "1",
            str(raw_artifact),
            "BTRUN-6511",
            "BTRUN-6512",
            "100000",
            "0.01",
        ],
        cwd=str(_REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert stress_result.returncode == 0, stress_result.stderr
    stress_payload = json.loads(stress_result.stdout)
    assert stress_payload["dataset_id"] == "DATASET-6510"

    get_snapshot_result = subprocess.run(  # noqa: S603
        [
            sys.executable,
            "-m",
            "empirical_platform.entrypoints.get_historical_dataset_snapshot",
            "DATASET-6510",
            "2-split-adjusted",
        ],
        cwd=str(_REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert get_snapshot_result.returncode == 0, get_snapshot_result.stderr
    get_snapshot_payload = json.loads(get_snapshot_result.stdout)
    assert (
        get_snapshot_payload["normalized_sha256"]
        == import_payload["adjusted_snapshot"]["normalized_sha256"]
    )

    get_stress_result = subprocess.run(  # noqa: S603
        [
            sys.executable,
            "-m",
            "empirical_platform.entrypoints.get_corporate_action_semantics_stress",
            "CASTR-6510",
            stress_payload["runtime_id"],
        ],
        cwd=str(_REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert get_stress_result.returncode == 0, get_stress_result.stderr
    get_stress_payload = json.loads(get_stress_result.stdout)
    assert get_stress_payload["comparison"] == stress_payload["comparison"]


def test_artifact_tamper_after_persist_is_rejected_by_stress_run(
    clean_tables: Engine, tmp_path: Path
) -> None:
    config = _config()
    raw_artifact = tmp_path / "raw.json"
    adjusted_artifact = tmp_path / "adjusted.json"
    _run_import(
        dataset_id="DATASET-6520",
        raw_version="1",
        adjusted_version="2-split-adjusted",
        raw_artifact=raw_artifact,
        adjusted_artifact=adjusted_artifact,
        config=config,
        tmp_path=tmp_path,
    )

    # Tamper the on-disk adjusted artifact AFTER the snapshot authority was
    # persisted -- its own hash no longer matches the persisted
    # `normalized_sha256`.
    tampered = json.loads(adjusted_artifact.read_text(encoding="utf-8"))
    tampered["instruments"][0]["bars"][0]["volume"] = (
        tampered["instruments"][0]["bars"][0]["volume"] + 999999
    )
    adjusted_artifact.write_text(json.dumps(tampered, sort_keys=True), encoding="utf-8")

    with pytest.raises(ValueError, match="does not match its own declared dataset snapshot"):
        run_run_corporate_action_semantics_stress(
            stress_governance_id="CASTR-6520",
            dataset_id="DATASET-6520",
            correct_dataset_version="2-split-adjusted",
            correct_dataset_file=str(adjusted_artifact),
            naive_dataset_version="1",
            naive_dataset_file=str(raw_artifact),
            correct_run_governance_id="BTRUN-6520",
            naive_run_governance_id="BTRUN-6521",
            account_equity=Decimal("100000"),
            risk_percent=Decimal("0.01"),
            config=config,
        )

    engine = sa.create_engine(config.sqlalchemy_url())
    try:
        with engine.connect() as conn:
            stress_count = conn.execute(
                text(
                    "SELECT count(*) FROM corporate_action_semantics_stress "
                    "WHERE governance_id = 'CASTR-6520'"
                )
            ).scalar_one()
    finally:
        engine.dispose()
    assert stress_count == 0


def test_reimporting_same_dataset_version_is_rejected(clean_tables: Engine, tmp_path: Path) -> None:
    config = _config()
    _run_import(
        dataset_id="DATASET-6530",
        raw_version="1",
        adjusted_version="2-split-adjusted",
        raw_artifact=tmp_path / "raw_a.json",
        adjusted_artifact=tmp_path / "adjusted_a.json",
        config=config,
        tmp_path=tmp_path,
    )
    with pytest.raises(Exception):  # noqa: B017, PT011
        _run_import(
            dataset_id="DATASET-6530",
            raw_version="1",
            adjusted_version="2-split-adjusted",
            raw_artifact=tmp_path / "raw_b.json",
            adjusted_artifact=tmp_path / "adjusted_b.json",
            config=config,
            tmp_path=tmp_path,
        )


def test_dataset_version_coexistence_third_import_does_not_remove_earlier_versions(
    clean_tables: Engine, tmp_path: Path
) -> None:
    config = _config()
    _run_import(
        dataset_id="DATASET-6540",
        raw_version="1",
        adjusted_version="2-split-adjusted",
        raw_artifact=tmp_path / "raw1.json",
        adjusted_artifact=tmp_path / "adjusted1.json",
        config=config,
        tmp_path=tmp_path,
    )

    # A second import of the SAME dataset_id under a NEW raw_version --
    # `_run_import` synthesizes a fresh manifest keyed to (dataset_id,
    # raw_version="3") automatically, since the manifest is keyed to the
    # exact raw dataset_version it describes.
    _run_import(
        dataset_id="DATASET-6540",
        raw_version="3",
        adjusted_version="4-split-adjusted",
        raw_artifact=tmp_path / "raw2.json",
        adjusted_artifact=tmp_path / "adjusted2.json",
        config=config,
        tmp_path=tmp_path,
    )

    # All four (dataset_id, dataset_version) rows coexist immutably -- the
    # second import did not overwrite or remove the first.
    original = run_get_historical_dataset_snapshot(
        dataset_id="DATASET-6540", dataset_version="1", config=config
    )
    still_present = run_get_historical_dataset_snapshot(
        dataset_id="DATASET-6540", dataset_version="2-split-adjusted", config=config
    )
    assert original.dataset_version == "1"  # type: ignore[attr-defined]
    assert still_present.dataset_version == "2-split-adjusted"  # type: ignore[attr-defined]

    engine = sa.create_engine(config.sqlalchemy_url())
    try:
        with engine.connect() as conn:
            count = conn.execute(
                text("SELECT count(*) FROM dataset_snapshot WHERE dataset_id = 'DATASET-6540'")
            ).scalar_one()
    finally:
        engine.dispose()
    assert count == 4
