"""MILESTONE-062 real-PostgreSQL historical validation study acceptance
tests: full lifecycle, raw-SQL verification, dataset tamper detection,
temporal-isolation (holdout-firewall) mutation attacks, deterministic
replay, multi-study coexistence, and real subprocess CLI evidence.
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

from empirical_platform.decision_candidate.historical_backtest import dataset_sha256
from empirical_platform.entrypoints.get_historical_validation_study import (
    run_get_historical_validation_study,
)
from empirical_platform.entrypoints.run_historical_validation_study import (
    run_run_historical_validation_study,
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
    / "m062_validation_study"
    / "synthetic_multi_period_validation_dataset_bundle.json"
)
_EXPECTED_SHA256 = "3289c380b233b06495c865b1645185436318b2394d77faaea97be96bf787c9f3"


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
        application_name="empirical-platform-m062-test",
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
                "TRUNCATE validation_segment, validation_study, "
                "historical_backtest_trade, historical_backtest_run CASCADE"
            )
        )
    return upgraded_schema


def _run_study(
    *,
    study_id: str,
    dataset_file: Path,
    expected_sha256: str,
    run_prefix: str,
    seed: int,
    config: PostgreSQLConfigSnapshot,
) -> object:
    return run_run_historical_validation_study(
        study_governance_id=study_id,
        dataset_bundle_file=str(dataset_file),
        expected_dataset_sha256=expected_sha256,
        development_backtest_run_governance_id=f"BTRUN-{run_prefix}1",
        holdout_1_backtest_run_governance_id=f"BTRUN-{run_prefix}2",
        holdout_2_backtest_run_governance_id=f"BTRUN-{run_prefix}3",
        account_equity=Decimal("100000"),
        risk_percent=Decimal("0.01"),
        identifier_generator=DeterministicRuntimeIdentifierGenerator(
            [f"{seed:08d}-0000-4000-8000-{index:012d}" for index in range(1, 500)]
        ),
        config=config,
    )


def test_full_validation_study_lifecycle_and_raw_sql_verification(clean_tables: Engine) -> None:
    config = _config()
    study = _run_study(
        study_id="STUDY-6201",
        dataset_file=_FIXTURE_PATH,
        expected_sha256=_EXPECTED_SHA256,
        run_prefix="620",
        seed=62010000,
        config=config,
    )

    assert study.classification.value == "HOLDOUT_RESULTS_RECORDED"
    assert study.development.executed_trade_count == 4
    assert study.development.win_count == 4
    assert study.development.net_pnl == Decimal("933.84935670")
    assert study.holdout_1.executed_trade_count == 3
    assert study.holdout_1.win_count == 1
    assert study.holdout_1.net_pnl == Decimal("64.578130")
    assert study.holdout_2.executed_trade_count == 5
    assert study.holdout_2.win_count == 3
    assert study.holdout_2.net_pnl == Decimal("383.228590")

    retrieved = run_get_historical_validation_study(
        study_governance_id="STUDY-6201",
        study_runtime_id=str(study.identity.runtime_id),
        config=config,
    )
    assert retrieved.classification == study.classification
    assert retrieved.holdout_1.net_pnl == study.holdout_1.net_pnl

    engine = sa.create_engine(config.sqlalchemy_url())
    try:
        with engine.connect() as conn:
            study_row = (
                conn.execute(
                    text(
                        "SELECT dataset_bundle_id, dataset_bundle_sha256, classification, "
                        "holdout_1_net_pnl_delta, holdout_2_net_pnl_delta "
                        "FROM validation_study WHERE governance_id = 'STUDY-6201'"
                    )
                )
                .mappings()
                .one()
            )
            segment_rows = (
                conn.execute(
                    text(
                        "SELECT role, backtest_run_governance_id, executed_trade_count, "
                        "win_count, net_pnl "
                        "FROM validation_segment WHERE study_runtime_id = :runtime_id "
                        "ORDER BY role"
                    ),
                    {"runtime_id": str(study.identity.runtime_id)},
                )
                .mappings()
                .all()
            )
            backtest_run_rows = (
                conn.execute(
                    text(
                        "SELECT governance_id, dataset_sha256, simulated_trade_count "
                        "FROM historical_backtest_run WHERE governance_id IN "
                        "('BTRUN-6201', 'BTRUN-6202', 'BTRUN-6203') ORDER BY governance_id"
                    )
                )
                .mappings()
                .all()
            )
    finally:
        engine.dispose()

    assert study_row["dataset_bundle_id"] == "DATASET-6201"
    assert study_row["dataset_bundle_sha256"] == _EXPECTED_SHA256
    assert study_row["classification"] == "HOLDOUT_RESULTS_RECORDED"
    assert study_row["holdout_1_net_pnl_delta"] == Decimal("-869.271227")
    assert len(segment_rows) == 3
    roles = {row["role"] for row in segment_rows}
    assert roles == {"DEVELOPMENT_REFERENCE", "HOLDOUT_1", "HOLDOUT_2"}
    assert len(backtest_run_rows) == 3
    assert {row["governance_id"] for row in backtest_run_rows} == {
        "BTRUN-6201",
        "BTRUN-6202",
        "BTRUN-6203",
    }


def test_dataset_tamper_is_rejected_before_any_study_is_persisted(
    clean_tables: Engine, tmp_path: Path
) -> None:
    tampered_path = tmp_path / "tampered_bundle.json"
    raw = json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))
    # Mutate one byte of one bar's close price -- content differs, hash will not match.
    raw["instruments"][0]["bars"][10]["close"] = "999.99"
    tampered_path.write_text(json.dumps(raw), encoding="utf-8")

    config = _config()
    with pytest.raises(ValueError, match="tamper detected"):
        _run_study(
            study_id="STUDY-6299",
            dataset_file=tampered_path,
            expected_sha256=_EXPECTED_SHA256,  # the ORIGINAL, now-stale hash
            run_prefix="629",
            seed=62990000,
            config=config,
        )

    engine = sa.create_engine(config.sqlalchemy_url())
    try:
        with engine.connect() as conn:
            count = conn.execute(
                text("SELECT count(*) FROM validation_study WHERE governance_id = 'STUDY-6299'")
            ).scalar_one()
    finally:
        engine.dispose()
    assert count == 0


def test_holdout_mutation_attack_a_only_holdout_2_changes(
    clean_tables: Engine, tmp_path: Path
) -> None:
    """Aggressively mutate HOLDOUT_2's own bars (indices 32-47). Expected:
    DEVELOPMENT and HOLDOUT_1 semantic results are byte-for-byte unchanged;
    only HOLDOUT_2 may change."""
    config = _config()
    baseline = _run_study(
        study_id="STUDY-6210",
        dataset_file=_FIXTURE_PATH,
        expected_sha256=_EXPECTED_SHA256,
        run_prefix="621",
        seed=62100000,
        config=config,
    )

    raw = json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))
    for instrument_entry in raw["instruments"]:
        for bar in instrument_entry["bars"][32:48]:  # HOLDOUT_2's own private block
            bar["close"] = "1.00"
            bar["open"] = "1.00"
            bar["high"] = "1.00"
            bar["low"] = "1.00"
            bar["volume"] = 1
    mutated_bytes = json.dumps(raw).encode("utf-8")
    mutated_path = tmp_path / "mutated_holdout2.json"
    mutated_path.write_bytes(mutated_bytes)
    mutated_sha256 = dataset_sha256(mutated_bytes)

    mutated = _run_study(
        study_id="STUDY-6211",
        dataset_file=mutated_path,
        expected_sha256=mutated_sha256,
        run_prefix="622",
        seed=62110000,
        config=config,
    )

    assert mutated.development.net_pnl == baseline.development.net_pnl
    assert mutated.development.executed_trade_count == baseline.development.executed_trade_count
    assert mutated.holdout_1.net_pnl == baseline.holdout_1.net_pnl
    assert mutated.holdout_1.executed_trade_count == baseline.holdout_1.executed_trade_count
    assert mutated.holdout_2.net_pnl != baseline.holdout_2.net_pnl


def test_holdout_mutation_attack_b_dev_interior_mutation_does_not_reach_holdouts(
    clean_tables: Engine, tmp_path: Path
) -> None:
    """Mutate DEVELOPMENT_REFERENCE's own bars strictly inside its scoring
    range (indices 5-12), away from the tail bars HOLDOUT_1 borrows for its
    own warmup (indices 13-15 are untouched). Expected: HOLDOUT_1 and
    HOLDOUT_2 trade outcomes remain determined entirely by their own
    private slices -- unaffected by any DEV mutation, since neither
    holdout's own dataset slice ever includes a DEV bar."""
    config = _config()
    baseline = _run_study(
        study_id="STUDY-6220",
        dataset_file=_FIXTURE_PATH,
        expected_sha256=_EXPECTED_SHA256,
        run_prefix="623",
        seed=62200000,
        config=config,
    )

    raw = json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))
    for instrument_entry in raw["instruments"]:
        for bar in instrument_entry["bars"][5:13]:  # DEV's own scoring range only
            bar["close"] = "1.00"
            bar["open"] = "1.00"
            bar["high"] = "1.00"
            bar["low"] = "1.00"
            bar["volume"] = 1
    mutated_bytes = json.dumps(raw).encode("utf-8")
    mutated_path = tmp_path / "mutated_dev.json"
    mutated_path.write_bytes(mutated_bytes)
    mutated_sha256 = dataset_sha256(mutated_bytes)

    mutated = _run_study(
        study_id="STUDY-6221",
        dataset_file=mutated_path,
        expected_sha256=mutated_sha256,
        run_prefix="624",
        seed=62210000,
        config=config,
    )

    assert mutated.development.net_pnl != baseline.development.net_pnl
    assert mutated.holdout_1.net_pnl == baseline.holdout_1.net_pnl
    assert mutated.holdout_1.executed_trade_count == baseline.holdout_1.executed_trade_count
    assert mutated.holdout_2.net_pnl == baseline.holdout_2.net_pnl
    assert mutated.holdout_2.executed_trade_count == baseline.holdout_2.executed_trade_count


def test_validation_study_replay_is_deterministic(clean_tables: Engine) -> None:
    config = _config()
    study_one = _run_study(
        study_id="STUDY-6230",
        dataset_file=_FIXTURE_PATH,
        expected_sha256=_EXPECTED_SHA256,
        run_prefix="625",
        seed=62300000,
        config=config,
    )
    study_two = _run_study(
        study_id="STUDY-6231",
        dataset_file=_FIXTURE_PATH,
        expected_sha256=_EXPECTED_SHA256,
        run_prefix="626",
        seed=62310000,
        config=config,
    )

    assert study_one.classification == study_two.classification
    assert study_one.development.net_pnl == study_two.development.net_pnl
    assert study_one.holdout_1.total_r == study_two.holdout_1.total_r
    assert study_one.holdout_2.win_rate == study_two.holdout_2.win_rate


def test_duplicate_validation_study_identity_raises_aggregate_already_exists(
    clean_tables: Engine,
) -> None:
    config = _config()
    _run_study(
        study_id="STUDY-6240",
        dataset_file=_FIXTURE_PATH,
        expected_sha256=_EXPECTED_SHA256,
        run_prefix="627",
        seed=62400000,
        config=config,
    )
    with pytest.raises(AggregateAlreadyExists):
        _run_study(
            study_id="STUDY-6240",
            dataset_file=_FIXTURE_PATH,
            expected_sha256=_EXPECTED_SHA256,
            run_prefix="628",
            seed=62410000,
            config=config,
        )


def test_multiple_independent_studies_coexist(clean_tables: Engine) -> None:
    config = _config()
    study_a = _run_study(
        study_id="STUDY-6250",
        dataset_file=_FIXTURE_PATH,
        expected_sha256=_EXPECTED_SHA256,
        run_prefix="629",
        seed=62500000,
        config=config,
    )
    study_b = _run_study(
        study_id="STUDY-6251",
        dataset_file=_FIXTURE_PATH,
        expected_sha256=_EXPECTED_SHA256,
        run_prefix="630",
        seed=62510000,
        config=config,
    )
    retrieved_a = run_get_historical_validation_study(
        study_governance_id="STUDY-6250",
        study_runtime_id=str(study_a.identity.runtime_id),
        config=config,
    )
    retrieved_b = run_get_historical_validation_study(
        study_governance_id="STUDY-6251",
        study_runtime_id=str(study_b.identity.runtime_id),
        config=config,
    )
    assert retrieved_a.identity.governance_id != retrieved_b.identity.governance_id
    assert retrieved_a.development.net_pnl == retrieved_b.development.net_pnl


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
                "from empirical_platform.entrypoints.run_historical_validation_study "
                "import main; main()"
            ),
            "STUDY-6260",
            str(_FIXTURE_PATH),
            _EXPECTED_SHA256,
            "BTRUN-6261",
            "BTRUN-6262",
            "BTRUN-6263",
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
    assert payload["classification"] == "HOLDOUT_RESULTS_RECORDED"
    assert payload["holdout_1"]["net_pnl"] == "64.578130"

    get_result = subprocess.run(  # noqa: S603
        [
            sys.executable,
            "-c",
            (
                "from empirical_platform.entrypoints.get_historical_validation_study "
                "import main; main()"
            ),
            "STUDY-6260",
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
    assert retrieved_payload["holdout_2"]["win_count"] == 3
