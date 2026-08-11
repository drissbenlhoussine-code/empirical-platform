"""MILESTONE-068 real-PostgreSQL cross-instrument dependence acceptance
tests.

Covers the full run->persist->retrieve lifecycle against real PostgreSQL,
a real CLI subprocess run of both new M068 entrypoints, raw-SQL
cross-verification of the persisted schema (report + pairwise dependence
+ concurrent-exposure states), deterministic replay (same estimation
policy -> identical result), estimation-policy sensitivity, and
upstream-authority-mismatch/tamper attacks (nonexistent portfolio study,
tampered runtime_id, duplicate governance_id, tampered dataset hash) --
built end-to-end from the real M064/M065 canonical fixture and a real
M067 portfolio evidence report, not fabricated upstream objects.
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

from empirical_platform.entrypoints.get_portfolio_dependence_evidence import (
    run_get_portfolio_dependence_evidence,
)
from empirical_platform.entrypoints.run_portfolio_dependence_evidence import (
    run_run_portfolio_dependence_evidence,
)
from empirical_platform.entrypoints.run_portfolio_historical_evidence import (
    run_run_portfolio_historical_evidence,
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
        application_name="empirical-platform-m068-test",
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
def portfolio_seeded(upgraded_schema: Engine) -> tuple[Engine, str, str]:
    """Fresh M064/M065 survivorship-aware study + M067 portfolio evidence
    report, seeded via the real, unmodified upstream usecases -- the
    only thing this fixture builds new is the upstream chain M068
    depends on, never M068 itself."""
    with upgraded_schema.begin() as conn:
        conn.execute(
            text(
                "TRUNCATE portfolio_dependence_concurrent_state, "
                "portfolio_dependence_pair, portfolio_dependence_report, "
                "portfolio_capital_sensitivity, portfolio_equity_observation, "
                "portfolio_allocation_decision, portfolio_study, survivorship_window, "
                "survivorship_study, membership_record, universe_authority, "
                "instrument_master, robustness_window, robustness_study, "
                "historical_backtest_trade, historical_backtest_run CASCADE"
            )
        )
    config = _config()
    study = run_run_survivorship_aware_robustness_study(
        study_governance_id="SURV-6810",
        stress_study_governance_id="ROBUST-6811",
        dataset_bundle_file=str(_DATASET_BUNDLE_PATH),
        expected_dataset_sha256=_EXPECTED_DATASET_SHA256,
        instrument_master_file=str(_INSTRUMENT_MASTER_PATH),
        membership_manifest_file=str(_MEMBERSHIP_MANIFEST_PATH),
        expected_membership_hash=_EXPECTED_MANIFEST_HASH,
        universe_source_kind="SURVIVORSHIP_AWARE_MECHANICS_FIXTURE",
        backtest_run_governance_id_base=6810,
        stress_backtest_run_governance_id_base=7810,
        account_equity=Decimal("100000"),
        risk_percent=Decimal("0.01"),
        config=config,
    )
    portfolio = run_run_portfolio_historical_evidence(
        report_governance_id="PORT-6810",
        source_study_governance_id="SURV-6810",
        source_study_runtime_id=str(study.identity.runtime_id),  # type: ignore[attr-defined]
        config=config,
    )
    return (
        upgraded_schema,
        "PORT-6810",
        str(portfolio.identity.runtime_id),  # type: ignore[attr-defined]
    )


def test_full_analysis_lifecycle_and_raw_sql_verification(
    portfolio_seeded: tuple[Engine, str, str],
) -> None:
    _engine_fixture, portfolio_governance_id, portfolio_runtime_id = portfolio_seeded
    config = _config()

    report = run_run_portfolio_dependence_evidence(
        report_governance_id="DEPEND-6810",
        source_portfolio_study_governance_id=portfolio_governance_id,
        source_portfolio_study_runtime_id=portfolio_runtime_id,
        dataset_bundle_file=str(_DATASET_BUNDLE_PATH),
        config=config,
    )
    assert report.source_portfolio_study_governance_id == portfolio_governance_id  # type: ignore[attr-defined]
    assert report.dataset_bundle_sha256 == _EXPECTED_DATASET_SHA256  # type: ignore[attr-defined]
    assert report.pair_count == report.defined_pair_count + report.undefined_pair_count  # type: ignore[attr-defined]
    assert len(report.pairwise_dependence) == report.pair_count  # type: ignore[attr-defined]

    retrieved = run_get_portfolio_dependence_evidence(
        report_governance_id="DEPEND-6810",
        report_runtime_id=str(report.identity.runtime_id),  # type: ignore[attr-defined]
        config=config,
    )
    assert retrieved.pairwise_dependence == report.pairwise_dependence  # type: ignore[attr-defined]
    assert (
        retrieved.concurrent_exposure_states == report.concurrent_exposure_states  # type: ignore[attr-defined]
    )
    assert retrieved.classification == report.classification  # type: ignore[attr-defined]
    assert retrieved.limitations == report.limitations  # type: ignore[attr-defined]

    engine = sa.create_engine(config.sqlalchemy_url())
    try:
        with engine.connect() as conn:
            report_row = (
                conn.execute(
                    text(
                        "SELECT source_portfolio_study_governance_id, instrument_count, "
                        "pair_count, defined_pair_count, undefined_pair_count, "
                        "classification "
                        "FROM portfolio_dependence_report WHERE governance_id = 'DEPEND-6810'"
                    )
                )
                .mappings()
                .one()
            )
            pair_count = (
                conn.execute(
                    text(
                        "SELECT COUNT(*) AS n FROM portfolio_dependence_pair "
                        "WHERE report_runtime_id = "
                        "(SELECT runtime_id FROM portfolio_dependence_report "
                        "WHERE governance_id = 'DEPEND-6810')"
                    )
                )
                .mappings()
                .one()
            )
            state_count = (
                conn.execute(
                    text(
                        "SELECT COUNT(*) AS n FROM portfolio_dependence_concurrent_state "
                        "WHERE report_runtime_id = "
                        "(SELECT runtime_id FROM portfolio_dependence_report "
                        "WHERE governance_id = 'DEPEND-6810')"
                    )
                )
                .mappings()
                .one()
            )
    finally:
        engine.dispose()

    assert report_row["source_portfolio_study_governance_id"] == portfolio_governance_id
    assert int(pair_count["n"]) == report.pair_count  # type: ignore[attr-defined]
    assert int(state_count["n"]) == report.concurrent_exposure_state_count  # type: ignore[attr-defined]
    assert report_row["classification"] == report.classification.value  # type: ignore[attr-defined]


def test_real_cli_subprocess_run_and_get(portfolio_seeded: tuple[Engine, str, str]) -> None:
    _engine_fixture, portfolio_governance_id, portfolio_runtime_id = portfolio_seeded
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
            "empirical_platform.entrypoints.run_portfolio_dependence_evidence",
            "DEPEND-6820",
            portfolio_governance_id,
            portfolio_runtime_id,
            str(_DATASET_BUNDLE_PATH),
        ],
        cwd=str(_REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert run_result.returncode == 0, run_result.stderr
    run_payload = json.loads(run_result.stdout)
    assert run_payload["source_portfolio_study_governance_id"] == portfolio_governance_id
    assert run_payload["pair_count"] == (
        run_payload["defined_pair_count"] + run_payload["undefined_pair_count"]
    )

    get_result = subprocess.run(  # noqa: S603
        [
            sys.executable,
            "-m",
            "empirical_platform.entrypoints.get_portfolio_dependence_evidence",
            "DEPEND-6820",
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
    for run_pair, get_pair in zip(
        run_payload["pairwise_dependence"], get_payload["pairwise_dependence"], strict=True
    ):
        assert run_pair["instrument_a"] == get_pair["instrument_a"]
        assert run_pair["instrument_b"] == get_pair["instrument_b"]
        assert run_pair["status"] == get_pair["status"]
        run_corr = run_pair["correlation"]
        get_corr = get_pair["correlation"]
        if run_corr is None:
            assert get_corr is None
        else:
            assert Decimal(run_corr) == Decimal(get_corr)


def test_deterministic_replay_same_policy_produces_identical_result(
    portfolio_seeded: tuple[Engine, str, str],
) -> None:
    _engine_fixture, portfolio_governance_id, portfolio_runtime_id = portfolio_seeded
    config = _config()

    first = run_run_portfolio_dependence_evidence(
        report_governance_id="DEPEND-6830",
        source_portfolio_study_governance_id=portfolio_governance_id,
        source_portfolio_study_runtime_id=portfolio_runtime_id,
        dataset_bundle_file=str(_DATASET_BUNDLE_PATH),
        config=config,
    )
    second = run_run_portfolio_dependence_evidence(
        report_governance_id="DEPEND-6831",
        source_portfolio_study_governance_id=portfolio_governance_id,
        source_portfolio_study_runtime_id=portfolio_runtime_id,
        dataset_bundle_file=str(_DATASET_BUNDLE_PATH),
        config=config,
    )
    assert first.pairwise_dependence == second.pairwise_dependence  # type: ignore[attr-defined]
    assert (
        first.concurrent_exposure_states == second.concurrent_exposure_states  # type: ignore[attr-defined]
    )
    assert first.classification == second.classification  # type: ignore[attr-defined]


def test_different_estimation_policy_produces_a_different_but_valid_result(
    portfolio_seeded: tuple[Engine, str, str],
) -> None:
    _engine_fixture, portfolio_governance_id, portfolio_runtime_id = portfolio_seeded
    config = _config()

    default_policy = run_run_portfolio_dependence_evidence(
        report_governance_id="DEPEND-6832",
        source_portfolio_study_governance_id=portfolio_governance_id,
        source_portfolio_study_runtime_id=portfolio_runtime_id,
        dataset_bundle_file=str(_DATASET_BUNDLE_PATH),
        config=config,
    )
    narrow_policy = run_run_portfolio_dependence_evidence(
        report_governance_id="DEPEND-6833",
        source_portfolio_study_governance_id=portfolio_governance_id,
        source_portfolio_study_runtime_id=portfolio_runtime_id,
        dataset_bundle_file=str(_DATASET_BUNDLE_PATH),
        lookback_bar_count=5,
        minimum_overlapping_observations=3,
        config=config,
    )
    assert default_policy.estimation_policy != narrow_policy.estimation_policy  # type: ignore[attr-defined]
    # A materially shorter lookback is a genuinely different, still-valid
    # evaluation -- no requirement that correlation be higher or lower
    # (mission Phase 30: weak/uninteresting evidence is acceptable).
    assert narrow_policy.estimation_policy.lookback_bar_count == 5  # type: ignore[attr-defined]


def test_upstream_portfolio_study_not_found_is_rejected(
    portfolio_seeded: tuple[Engine, str, str],
) -> None:
    _engine_fixture, _portfolio_governance_id, _portfolio_runtime_id = portfolio_seeded
    config = _config()
    with pytest.raises(AggregateNotFound):
        run_run_portfolio_dependence_evidence(
            report_governance_id="DEPEND-6834",
            source_portfolio_study_governance_id="PORT-9999",
            source_portfolio_study_runtime_id="00000000-0000-4000-8000-000000000000",
            dataset_bundle_file=str(_DATASET_BUNDLE_PATH),
            config=config,
        )


def test_tampered_portfolio_study_runtime_id_is_rejected(
    portfolio_seeded: tuple[Engine, str, str],
) -> None:
    _engine_fixture, portfolio_governance_id, _portfolio_runtime_id = portfolio_seeded
    config = _config()
    with pytest.raises(AggregateNotFound):
        run_run_portfolio_dependence_evidence(
            report_governance_id="DEPEND-6835",
            source_portfolio_study_governance_id=portfolio_governance_id,
            source_portfolio_study_runtime_id="00000000-0000-4000-8000-000000000000",
            dataset_bundle_file=str(_DATASET_BUNDLE_PATH),
            config=config,
        )


def test_duplicate_report_governance_id_is_rejected(
    portfolio_seeded: tuple[Engine, str, str],
) -> None:
    _engine_fixture, portfolio_governance_id, portfolio_runtime_id = portfolio_seeded
    config = _config()
    run_run_portfolio_dependence_evidence(
        report_governance_id="DEPEND-6836",
        source_portfolio_study_governance_id=portfolio_governance_id,
        source_portfolio_study_runtime_id=portfolio_runtime_id,
        dataset_bundle_file=str(_DATASET_BUNDLE_PATH),
        config=config,
    )
    with pytest.raises(AggregateAlreadyExists):
        run_run_portfolio_dependence_evidence(
            report_governance_id="DEPEND-6836",
            source_portfolio_study_governance_id=portfolio_governance_id,
            source_portfolio_study_runtime_id=portfolio_runtime_id,
            dataset_bundle_file=str(_DATASET_BUNDLE_PATH),
            config=config,
        )


def test_tampered_dataset_bundle_hash_is_rejected(
    portfolio_seeded: tuple[Engine, str, str], tmp_path: Path
) -> None:
    """Mission Phase 4/27: a dataset bundle file whose own computed
    SHA-256 no longer matches the upstream M067 report's declared
    `dataset_bundle_sha256` must be rejected before any correlation
    computation is attempted -- no untraceable dependence report."""
    _engine_fixture, portfolio_governance_id, portfolio_runtime_id = portfolio_seeded
    config = _config()

    tampered_path = tmp_path / "tampered_dataset_bundle.json"
    original = json.loads(_DATASET_BUNDLE_PATH.read_text())
    original["instruments"][0]["bars"][0]["close"] = "999999.99"
    tampered_path.write_text(json.dumps(original))

    with pytest.raises(ValueError, match="(?i)sha256|hash|integrity|mismatch"):
        run_run_portfolio_dependence_evidence(
            report_governance_id="DEPEND-6837",
            source_portfolio_study_governance_id=portfolio_governance_id,
            source_portfolio_study_runtime_id=portfolio_runtime_id,
            dataset_bundle_file=str(tampered_path),
            config=config,
        )
