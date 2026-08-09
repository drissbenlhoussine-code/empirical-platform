"""MILESTONE-063 real-PostgreSQL robustness-study acceptance tests."""

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

from empirical_platform.decision_candidate.historical_backtest import dataset_sha256
from empirical_platform.entrypoints.get_historical_robustness_study import (
    run_get_historical_robustness_study,
)
from empirical_platform.entrypoints.run_historical_robustness_study import (
    run_run_historical_robustness_study,
)
from empirical_platform.shared.config.settings import PostgreSQLConfigSnapshot
from empirical_platform.shared.contracts.repository import AggregateAlreadyExists
from empirical_platform.shared.identifiers import DeterministicRuntimeIdentifierGenerator

pytestmark = pytest.mark.integration

_REPO_ROOT = Path(__file__).resolve().parents[2]
_FIXTURE_PATH = (
    _REPO_ROOT
    / "tests"
    / "fixtures"
    / "m063_robustness_study"
    / "synthetic_broad_robustness_dataset_bundle.json"
)
_EXPECTED_SHA256 = "ca98478ce6156f41c4535eaa040fd3e161229a71acd771a477ee9648ac3dd506"


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
        application_name="empirical-platform-m063-test",
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
                "TRUNCATE robustness_window, robustness_study, validation_segment, "
                "validation_study, historical_backtest_trade, historical_backtest_run CASCADE"
            )
        )
    return upgraded_schema


def _run_study(
    *,
    study_id: str,
    dataset_file: Path,
    expected_sha256: str,
    run_base: int,
    seed: int,
    config: PostgreSQLConfigSnapshot,
) -> object:
    return run_run_historical_robustness_study(
        study_governance_id=study_id,
        dataset_bundle_file=str(dataset_file),
        expected_dataset_sha256=expected_sha256,
        backtest_run_governance_id_base=run_base,
        account_equity=Decimal("100000"),
        risk_percent=Decimal("0.01"),
        identifier_generator=DeterministicRuntimeIdentifierGenerator(
            [f"{seed:08d}-0000-4000-8000-{index:012d}" for index in range(1, 5000)]
        ),
        config=config,
    )


def test_full_robustness_study_lifecycle_and_raw_sql_verification(clean_tables: Engine) -> None:
    config = _config()
    study = _run_study(
        study_id="ROBUST-6301",
        dataset_file=_FIXTURE_PATH,
        expected_sha256=_EXPECTED_SHA256,
        run_base=6300,
        seed=63010000,
        config=config,
    )

    assert study.classification.value == "ROBUSTNESS_EVIDENCE_MIXED"
    assert study.universe_id == "UNIVERSE-6301"
    assert study.window_count == 10
    assert study.total_evaluated_cutoff_count == 80
    assert study.total_executed_trade_count == 59
    assert study.best_window_by_net_pnl.window_id == "W08"
    assert study.worst_window_by_net_pnl.window_id == "W07"
    assert study.excluding_best_window_net_pnl_total == Decimal("1914.24177280")

    retrieved = run_get_historical_robustness_study(
        study_governance_id="ROBUST-6301",
        study_runtime_id=str(study.identity.runtime_id),
        config=config,
    )
    assert retrieved.classification == study.classification
    assert retrieved.window_results[7].window.window_id == "W08"
    assert retrieved.dataset_bundle_sha256 == _EXPECTED_SHA256

    engine = sa.create_engine(config.sqlalchemy_url())
    try:
        with engine.connect() as conn:
            study_row = (
                conn.execute(
                    text(
                        "SELECT dataset_bundle_id, dataset_bundle_sha256, universe_id, "
                        "universe_version, universe_membership_model, classification, "
                        "window_count, total_executed_trade_count, "
                        "best_window_by_net_pnl_id, worst_window_by_net_pnl_id "
                        "FROM robustness_study WHERE governance_id = 'ROBUST-6301'"
                    )
                )
                .mappings()
                .one()
            )
            window_rows = (
                conn.execute(
                    text(
                        "SELECT window_id, sequence_index, regime_label, executed_trade_count, "
                        "net_pnl, total_r "
                        "FROM robustness_window WHERE study_runtime_id = :runtime_id "
                        "ORDER BY sequence_index"
                    ),
                    {"runtime_id": str(study.identity.runtime_id)},
                )
                .mappings()
                .all()
            )
    finally:
        engine.dispose()

    assert study_row["dataset_bundle_id"] == "DATASET-6301"
    assert study_row["dataset_bundle_sha256"] == _EXPECTED_SHA256
    assert study_row["universe_id"] == "UNIVERSE-6301"
    assert study_row["universe_version"] == "1"
    assert study_row["universe_membership_model"] == "FIXED_SYNTHETIC_UNIVERSE"
    assert study_row["classification"] == "ROBUSTNESS_EVIDENCE_MIXED"
    assert study_row["window_count"] == 10
    assert study_row["total_executed_trade_count"] == 59
    assert study_row["best_window_by_net_pnl_id"] == "W08"
    assert study_row["worst_window_by_net_pnl_id"] == "W07"
    assert len(window_rows) == 10
    assert [row["window_id"] for row in window_rows] == [f"W{index:02d}" for index in range(1, 11)]
    assert window_rows[7]["executed_trade_count"] == 8
    assert window_rows[7]["net_pnl"] == Decimal("1245.309991")


def test_dataset_tamper_is_rejected_before_any_study_is_persisted(
    clean_tables: Engine, tmp_path: Path
) -> None:
    tampered_path = tmp_path / "tampered_bundle.json"
    raw = json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))
    raw["instruments"][0]["bars"][150]["close"] = "999.99"
    tampered_path.write_text(json.dumps(raw), encoding="utf-8")

    config = _config()
    with pytest.raises(ValueError, match="tamper detected"):
        _run_study(
            study_id="ROBUST-6399",
            dataset_file=tampered_path,
            expected_sha256=_EXPECTED_SHA256,
            run_base=6390,
            seed=63990000,
            config=config,
        )

    engine = sa.create_engine(config.sqlalchemy_url())
    try:
        with engine.connect() as conn:
            count = conn.execute(
                text("SELECT count(*) FROM robustness_study WHERE governance_id = 'ROBUST-6399'")
            ).scalar_one()
    finally:
        engine.dispose()
    assert count == 0


def test_late_window_mutation_attack_changes_only_the_final_window(
    clean_tables: Engine, tmp_path: Path
) -> None:
    config = _config()
    baseline = _run_study(
        study_id="ROBUST-6310",
        dataset_file=_FIXTURE_PATH,
        expected_sha256=_EXPECTED_SHA256,
        run_base=6310,
        seed=63100000,
        config=config,
    )

    raw = json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))
    for instrument_entry in raw["instruments"]:
        for bar in instrument_entry["bars"][144:160]:
            bar["close"] = "1.00"
            bar["open"] = "1.00"
            bar["high"] = "1.00"
            bar["low"] = "1.00"
            bar["volume"] = 1
    mutated_bytes = json.dumps(raw).encode("utf-8")
    mutated_path = tmp_path / "mutated_late_window.json"
    mutated_path.write_bytes(mutated_bytes)
    mutated_sha256 = dataset_sha256(mutated_bytes)

    mutated = _run_study(
        study_id="ROBUST-6311",
        dataset_file=mutated_path,
        expected_sha256=mutated_sha256,
        run_base=6320,
        seed=63110000,
        config=config,
    )

    for baseline_result, mutated_result in zip(
        baseline.window_results[:9], mutated.window_results[:9], strict=True
    ):
        assert mutated_result.net_pnl == baseline_result.net_pnl
        assert mutated_result.total_r == baseline_result.total_r
        assert mutated_result.executed_trade_count == baseline_result.executed_trade_count
    assert mutated.window_results[9].net_pnl != baseline.window_results[9].net_pnl


def test_window_order_variation_preserves_canonical_study(
    clean_tables: Engine, tmp_path: Path
) -> None:
    config = _config()
    baseline = _run_study(
        study_id="ROBUST-6320",
        dataset_file=_FIXTURE_PATH,
        expected_sha256=_EXPECTED_SHA256,
        run_base=6330,
        seed=63200000,
        config=config,
    )

    raw = json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))
    raw["windows"] = list(reversed(raw["windows"]))
    shuffled_bytes = json.dumps(raw).encode("utf-8")
    shuffled_path = tmp_path / "shuffled_windows.json"
    shuffled_path.write_bytes(shuffled_bytes)
    shuffled_sha256 = dataset_sha256(shuffled_bytes)

    shuffled = _run_study(
        study_id="ROBUST-6321",
        dataset_file=shuffled_path,
        expected_sha256=shuffled_sha256,
        run_base=6340,
        seed=63210000,
        config=config,
    )

    assert shuffled.all_window_net_pnl_total == baseline.all_window_net_pnl_total
    assert shuffled.best_window_by_net_pnl == baseline.best_window_by_net_pnl
    assert [result.window.window_id for result in shuffled.window_results] == [
        result.window.window_id for result in baseline.window_results
    ]


def test_robustness_study_replay_is_deterministic(clean_tables: Engine) -> None:
    config = _config()
    study_one = _run_study(
        study_id="ROBUST-6330",
        dataset_file=_FIXTURE_PATH,
        expected_sha256=_EXPECTED_SHA256,
        run_base=6350,
        seed=63300000,
        config=config,
    )
    study_two = _run_study(
        study_id="ROBUST-6331",
        dataset_file=_FIXTURE_PATH,
        expected_sha256=_EXPECTED_SHA256,
        run_base=6360,
        seed=63310000,
        config=config,
    )

    assert study_one.classification == study_two.classification
    assert study_one.all_window_net_pnl_total == study_two.all_window_net_pnl_total
    assert study_one.best_window_by_total_r == study_two.best_window_by_total_r


def test_duplicate_robustness_study_identity_raises_aggregate_already_exists(
    clean_tables: Engine,
) -> None:
    config = _config()
    _run_study(
        study_id="ROBUST-6340",
        dataset_file=_FIXTURE_PATH,
        expected_sha256=_EXPECTED_SHA256,
        run_base=6370,
        seed=63400000,
        config=config,
    )
    with pytest.raises(AggregateAlreadyExists):
        _run_study(
            study_id="ROBUST-6340",
            dataset_file=_FIXTURE_PATH,
            expected_sha256=_EXPECTED_SHA256,
            run_base=6380,
            seed=63410000,
            config=config,
        )


def test_multiple_independent_robustness_studies_coexist(clean_tables: Engine) -> None:
    config = _config()
    study_a = _run_study(
        study_id="ROBUST-6350",
        dataset_file=_FIXTURE_PATH,
        expected_sha256=_EXPECTED_SHA256,
        run_base=6390,
        seed=63500000,
        config=config,
    )
    study_b = _run_study(
        study_id="ROBUST-6351",
        dataset_file=_FIXTURE_PATH,
        expected_sha256=_EXPECTED_SHA256,
        run_base=6400,
        seed=63510000,
        config=config,
    )
    retrieved_a = run_get_historical_robustness_study(
        study_governance_id="ROBUST-6350",
        study_runtime_id=str(study_a.identity.runtime_id),
        config=config,
    )
    retrieved_b = run_get_historical_robustness_study(
        study_governance_id="ROBUST-6351",
        study_runtime_id=str(study_b.identity.runtime_id),
        config=config,
    )
    assert retrieved_a.identity.governance_id != retrieved_b.identity.governance_id
    assert retrieved_a.all_window_net_pnl_total == retrieved_b.all_window_net_pnl_total


def test_cli_subprocess_runs_and_retrieves_real_study(clean_tables: Engine) -> None:
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
            (
                "from empirical_platform.entrypoints.run_historical_robustness_study "
                "import main; main()"
            ),
            "ROBUST-6360",
            str(_FIXTURE_PATH),
            _EXPECTED_SHA256,
            "6410",
            "100000",
            "0.01",
        ],
        capture_output=True,
        check=True,
        cwd=_REPO_ROOT,
        env=env,
        text=True,
    )
    payload = json.loads(run_result.stdout)
    assert payload["classification"] == "ROBUSTNESS_EVIDENCE_MIXED"
    assert payload["universe_id"] == "UNIVERSE-6301"
    assert payload["best_window_by_net_pnl"]["window_id"] == "W08"

    get_result = subprocess.run(  # noqa: S603
        [
            sys.executable,
            "-c",
            (
                "from empirical_platform.entrypoints.get_historical_robustness_study "
                "import main; main()"
            ),
            "ROBUST-6360",
            payload["runtime_id"],
        ],
        capture_output=True,
        check=True,
        cwd=_REPO_ROOT,
        env=env,
        text=True,
    )
    retrieved_payload = json.loads(get_result.stdout)
    assert retrieved_payload["dataset_bundle_sha256"] == _EXPECTED_SHA256
    assert retrieved_payload["window_count"] == 10
