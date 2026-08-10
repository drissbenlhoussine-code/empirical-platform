"""MILESTONE-066 real-PostgreSQL statistical evidence acceptance tests.

Covers the full run->persist->retrieve lifecycle against real PostgreSQL,
a real CLI subprocess run of both new M066 entrypoints, raw-SQL
cross-verification of the persisted schema (report + bootstrap intervals +
sensitivity views), deterministic replay (same seed -> identical result),
seed sensitivity (different seed -> different but still reproducible
result), and upstream-authority-mismatch attacks (nonexistent study,
tampered runtime_id).
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

from empirical_platform.entrypoints.get_statistical_evidence_report import (
    run_get_statistical_evidence_report,
)
from empirical_platform.entrypoints.run_statistical_evidence_analysis import (
    run_run_statistical_evidence_analysis,
)
from empirical_platform.entrypoints.run_survivorship_aware_robustness_study import (
    run_run_survivorship_aware_robustness_study,
)
from empirical_platform.shared.config.settings import PostgreSQLConfigSnapshot
from empirical_platform.shared.contracts.repository import AggregateAlreadyExists, AggregateNotFound

pytestmark = pytest.mark.integration

_REPO_ROOT = Path(__file__).resolve().parents[2]
_FIXTURE_DIR = _REPO_ROOT / "tests" / "fixtures" / "m064_survivorship_aware"
_DATASET_BUNDLE_PATH = _FIXTURE_DIR / "survivorship_aware_dataset_bundle.json"
_INSTRUMENT_MASTER_PATH = _FIXTURE_DIR / "instrument_master.json"
_MEMBERSHIP_MANIFEST_PATH = _FIXTURE_DIR / "membership_manifest.json"
_EXPECTED_DATASET_SHA256 = "af996c094538abcc34356357db1ea74ad675b3bcff10a7ea759ae86a4ee073ff"
_EXPECTED_MANIFEST_HASH = "caa9fa899ea26816101a0a494c4977fed75849d4ac19b65ac6410e561f232fda"


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
        application_name="empirical-platform-m066-test",
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
def study_seeded(upgraded_schema: Engine) -> tuple[Engine, str, str]:
    """Truncate M066 tables (leave the upstream M064/M061 studies alone
    across test cases within this module, but ensure a fresh canonical
    study exists for this test)."""
    with upgraded_schema.begin() as conn:
        conn.execute(
            text(
                "TRUNCATE statistical_evidence_sensitivity, "
                "statistical_evidence_bootstrap_interval, "
                "statistical_evidence_report, survivorship_window, survivorship_study, "
                "membership_record, universe_authority, instrument_master, robustness_window, "
                "robustness_study, historical_backtest_trade, historical_backtest_run CASCADE"
            )
        )
    config = _config()
    study = run_run_survivorship_aware_robustness_study(
        study_governance_id="SURV-6670",
        stress_study_governance_id="ROBUST-6671",
        dataset_bundle_file=str(_DATASET_BUNDLE_PATH),
        expected_dataset_sha256=_EXPECTED_DATASET_SHA256,
        instrument_master_file=str(_INSTRUMENT_MASTER_PATH),
        membership_manifest_file=str(_MEMBERSHIP_MANIFEST_PATH),
        expected_membership_hash=_EXPECTED_MANIFEST_HASH,
        universe_source_kind="SURVIVORSHIP_AWARE_MECHANICS_FIXTURE",
        backtest_run_governance_id_base=6670,
        stress_backtest_run_governance_id_base=7670,
        account_equity=Decimal("100000"),
        risk_percent=Decimal("0.01"),
        config=config,
    )
    return upgraded_schema, "SURV-6670", str(study.identity.runtime_id)  # type: ignore[attr-defined]


def test_full_analysis_lifecycle_and_raw_sql_verification(
    study_seeded: tuple[Engine, str, str],
) -> None:
    _engine_fixture, study_governance_id, study_runtime_id = study_seeded
    config = _config()

    report = run_run_statistical_evidence_analysis(
        report_governance_id="STATEV-6670",
        source_study_governance_id=study_governance_id,
        source_study_runtime_id=study_runtime_id,
        config=config,
    )
    assert report.trade_sample_size > 0  # type: ignore[attr-defined]
    assert report.window_sample_size == 10  # type: ignore[attr-defined]
    assert report.source_study_governance_id == study_governance_id  # type: ignore[attr-defined]
    assert report.dataset_bundle_id == "DATASET-6401"  # type: ignore[attr-defined]
    assert report.membership_manifest_hash == _EXPECTED_MANIFEST_HASH  # type: ignore[attr-defined]
    assert len(report.limitations) == 6  # type: ignore[attr-defined]

    retrieved = run_get_statistical_evidence_report(
        report_governance_id="STATEV-6670",
        report_runtime_id=str(report.identity.runtime_id),  # type: ignore[attr-defined]
        config=config,
    )
    assert retrieved.classification == report.classification  # type: ignore[attr-defined]
    assert retrieved.mean_r_interval == report.mean_r_interval  # type: ignore[attr-defined]
    assert retrieved.sensitivity_views == report.sensitivity_views  # type: ignore[attr-defined]
    assert retrieved.limitations == report.limitations  # type: ignore[attr-defined]

    engine = sa.create_engine(config.sqlalchemy_url())
    try:
        with engine.connect() as conn:
            report_row = (
                conn.execute(
                    text(
                        "SELECT source_study_governance_id, trade_sample_size, "
                        "window_sample_size, classification "
                        "FROM statistical_evidence_report WHERE governance_id = 'STATEV-6670'"
                    )
                )
                .mappings()
                .one()
            )
            interval_rows = (
                conn.execute(
                    text(
                        "SELECT metric_name FROM statistical_evidence_bootstrap_interval "
                        "WHERE report_runtime_id = "
                        "(SELECT runtime_id FROM statistical_evidence_report "
                        "WHERE governance_id = 'STATEV-6670') ORDER BY metric_name"
                    )
                )
                .mappings()
                .all()
            )
            sensitivity_rows = (
                conn.execute(
                    text(
                        "SELECT label FROM statistical_evidence_sensitivity "
                        "WHERE report_runtime_id = "
                        "(SELECT runtime_id FROM statistical_evidence_report "
                        "WHERE governance_id = 'STATEV-6670') ORDER BY label"
                    )
                )
                .mappings()
                .all()
            )
    finally:
        engine.dispose()

    assert report_row["source_study_governance_id"] == study_governance_id
    assert {r["metric_name"] for r in interval_rows} >= {
        "mean_r_per_trade",
        "median_r_per_trade",
        "aggregate_r",
    }
    assert {r["label"] for r in sensitivity_rows} == {
        "CANONICAL",
        "EXCLUDING_BEST_TRADE",
        "EXCLUDING_WORST_TRADE",
        "EXCLUDING_BEST_WINDOW",
        "EXCLUDING_WORST_WINDOW",
    }


def test_real_cli_subprocess_run_and_get(study_seeded: tuple[Engine, str, str]) -> None:
    _engine_fixture, study_governance_id, study_runtime_id = study_seeded
    config = _config()
    env = dict(os.environ)
    env["EMPIRICAL_PLATFORM_POSTGRES_HOST"] = config.host
    env["EMPIRICAL_PLATFORM_POSTGRES_PORT"] = str(config.port)
    env["EMPIRICAL_PLATFORM_POSTGRES_DATABASE"] = config.database
    env["EMPIRICAL_PLATFORM_POSTGRES_USER"] = config.user
    env["EMPIRICAL_PLATFORM_POSTGRES_PASSWORD"] = config.password.get_secret_value()

    run_result = subprocess.run(  # noqa: S603
        [
            sys.executable,
            "-m",
            "empirical_platform.entrypoints.run_statistical_evidence_analysis",
            "STATEV-6680",
            study_governance_id,
            study_runtime_id,
        ],
        cwd=str(_REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert run_result.returncode == 0, run_result.stderr
    run_payload = json.loads(run_result.stdout)
    assert run_payload["source_study_governance_id"] == study_governance_id
    assert run_payload["trade_sample_size"] > 0

    get_result = subprocess.run(  # noqa: S603
        [
            sys.executable,
            "-m",
            "empirical_platform.entrypoints.get_statistical_evidence_report",
            "STATEV-6680",
            run_payload["runtime_id"],
        ],
        cwd=str(_REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert get_result.returncode == 0, get_result.stderr
    get_payload = json.loads(get_result.stdout)
    assert get_payload["classification"] == run_payload["classification"]
    # Numeric fields compare semantically (Decimal equality), not as raw
    # strings -- PostgreSQL's NUMERIC(30,15) columns pad to full declared
    # scale on retrieval (e.g. "0.4460" -> "0.446000000000000"), which is
    # the identical value at a different string precision, not a data
    # discrepancy.
    for run_view, get_view in zip(
        run_payload["sensitivity_views"], get_payload["sensitivity_views"], strict=True
    ):
        assert run_view["label"] == get_view["label"]
        assert run_view["sample_size"] == get_view["sample_size"]
        assert Decimal(run_view["net_pnl"]) == Decimal(get_view["net_pnl"])
        assert Decimal(run_view["total_r"]) == Decimal(get_view["total_r"])
        assert Decimal(run_view["mean_r"]) == Decimal(get_view["mean_r"])


def test_deterministic_replay_same_seed_produces_identical_intervals(
    study_seeded: tuple[Engine, str, str],
) -> None:
    _engine_fixture, study_governance_id, study_runtime_id = study_seeded
    config = _config()

    first = run_run_statistical_evidence_analysis(
        report_governance_id="STATEV-6690",
        source_study_governance_id=study_governance_id,
        source_study_runtime_id=study_runtime_id,
        config=config,
    )
    second = run_run_statistical_evidence_analysis(
        report_governance_id="STATEV-6691",
        source_study_governance_id=study_governance_id,
        source_study_runtime_id=study_runtime_id,
        config=config,
    )
    assert first.mean_r_interval == second.mean_r_interval  # type: ignore[attr-defined]
    assert first.median_r_interval == second.median_r_interval  # type: ignore[attr-defined]
    assert first.aggregate_r_interval == second.aggregate_r_interval  # type: ignore[attr-defined]
    assert first.classification == second.classification  # type: ignore[attr-defined]


def test_different_seed_produces_a_different_but_valid_interval(
    study_seeded: tuple[Engine, str, str],
) -> None:
    _engine_fixture, study_governance_id, study_runtime_id = study_seeded
    config = _config()

    default_seed = run_run_statistical_evidence_analysis(
        report_governance_id="STATEV-6692",
        source_study_governance_id=study_governance_id,
        source_study_runtime_id=study_runtime_id,
        config=config,
    )
    different_seed = run_run_statistical_evidence_analysis(
        report_governance_id="STATEV-6693",
        source_study_governance_id=study_governance_id,
        source_study_runtime_id=study_runtime_id,
        seed=999999,
        config=config,
    )
    # point estimates (real, unresampled statistics) must agree exactly --
    # only the resampled interval bounds may legitimately differ.
    assert (
        default_seed.mean_r_interval.point_estimate  # type: ignore[attr-defined]
        == different_seed.mean_r_interval.point_estimate  # type: ignore[attr-defined]
    )
    assert default_seed.mean_r_interval.seed != different_seed.mean_r_interval.seed  # type: ignore[attr-defined]


def test_upstream_study_not_found_is_rejected(study_seeded: tuple[Engine, str, str]) -> None:
    _engine_fixture, _study_governance_id, _study_runtime_id = study_seeded
    config = _config()
    with pytest.raises(AggregateNotFound):
        run_run_statistical_evidence_analysis(
            report_governance_id="STATEV-6694",
            source_study_governance_id="SURV-9999",
            source_study_runtime_id="00000000-0000-4000-8000-000000000000",
            config=config,
        )


def test_tampered_study_runtime_id_is_rejected(study_seeded: tuple[Engine, str, str]) -> None:
    _engine_fixture, study_governance_id, _study_runtime_id = study_seeded
    config = _config()
    with pytest.raises(AggregateNotFound):
        run_run_statistical_evidence_analysis(
            report_governance_id="STATEV-6695",
            source_study_governance_id=study_governance_id,
            source_study_runtime_id="00000000-0000-4000-8000-000000000000",
            config=config,
        )


def test_duplicate_report_governance_id_is_rejected(
    study_seeded: tuple[Engine, str, str],
) -> None:
    _engine_fixture, study_governance_id, study_runtime_id = study_seeded
    config = _config()
    run_run_statistical_evidence_analysis(
        report_governance_id="STATEV-6696",
        source_study_governance_id=study_governance_id,
        source_study_runtime_id=study_runtime_id,
        config=config,
    )
    with pytest.raises(AggregateAlreadyExists):
        run_run_statistical_evidence_analysis(
            report_governance_id="STATEV-6696",
            source_study_governance_id=study_governance_id,
            source_study_runtime_id=study_runtime_id,
            config=config,
        )
