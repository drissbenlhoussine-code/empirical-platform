"""MILESTONE-064 real-PostgreSQL survivorship-aware robustness-study
acceptance tests."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from collections.abc import Iterator
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command as alembic_command
from alembic.config import Config
from pydantic import SecretStr
from sqlalchemy import text
from sqlalchemy.engine import Engine

from empirical_platform.decision_candidate.instrument_master import InstrumentId
from empirical_platform.decision_candidate.membership import (
    MembershipManifest,
    MembershipRecord,
    MembershipStatus,
    membership_manifest_hash,
)
from empirical_platform.entrypoints.get_survivorship_aware_robustness_study import (
    run_get_survivorship_aware_robustness_study,
)
from empirical_platform.entrypoints.run_survivorship_aware_robustness_study import (
    run_run_survivorship_aware_robustness_study,
)
from empirical_platform.shared.config.settings import PostgreSQLConfigSnapshot
from empirical_platform.shared.identifiers import DeterministicRuntimeIdentifierGenerator

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
        application_name="empirical-platform-m064-test",
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
                "TRUNCATE survivorship_window, survivorship_study, membership_record, "
                "universe_authority, instrument_master, robustness_window, robustness_study, "
                "validation_segment, validation_study, historical_backtest_trade, "
                "historical_backtest_run CASCADE"
            )
        )
    return upgraded_schema


def _run_study(
    *,
    study_id: str,
    stress_study_id: str,
    dataset_file: Path,
    expected_sha256: str,
    membership_file: Path,
    expected_membership_hash: str,
    run_base: int,
    stress_run_base: int,
    seed: int,
    config: PostgreSQLConfigSnapshot,
) -> object:
    return run_run_survivorship_aware_robustness_study(
        study_governance_id=study_id,
        stress_study_governance_id=stress_study_id,
        dataset_bundle_file=str(dataset_file),
        expected_dataset_sha256=expected_sha256,
        instrument_master_file=str(_INSTRUMENT_MASTER_PATH),
        membership_manifest_file=str(membership_file),
        expected_membership_hash=expected_membership_hash,
        universe_source_kind="SURVIVORSHIP_AWARE_MECHANICS_FIXTURE",
        backtest_run_governance_id_base=run_base,
        stress_backtest_run_governance_id_base=stress_run_base,
        account_equity=Decimal("100000"),
        risk_percent=Decimal("0.01"),
        identifier_generator=DeterministicRuntimeIdentifierGenerator(
            [f"{seed:08d}-0000-4000-8000-{index:012d}" for index in range(1, 8000)]
        ),
        config=config,
    )


def test_full_survivorship_study_lifecycle_and_raw_sql_verification(
    clean_tables: Engine,
) -> None:
    config = _config()
    study = _run_study(
        study_id="SURV-6401",
        stress_study_id="ROBUST-6402",
        dataset_file=_DATASET_BUNDLE_PATH,
        expected_sha256=_EXPECTED_DATASET_SHA256,
        membership_file=_MEMBERSHIP_MANIFEST_PATH,
        expected_membership_hash=_EXPECTED_MANIFEST_HASH,
        run_base=6400,
        stress_run_base=7400,
        seed=64010000,
        config=config,
    )

    assert study.window_count == 10
    assert study.classification.value == "SURVIVORSHIP_AWARE_MEMBERSHIP_MECHANICS_PROVEN"
    assert [r.snapshot.eligible_count for r in study.window_results] == [
        4,
        5,
        6,
        6,
        5,
        4,
        4,
        3,
        3,
        3,
    ]
    assert study.current_universe_bias_stress.comparison.value == (
        "CURRENT_UNIVERSE_BIAS_STRESS_DIFFERS"
    )

    retrieved = run_get_survivorship_aware_robustness_study(
        study_governance_id="SURV-6401",
        study_runtime_id=str(study.identity.runtime_id),
        config=config,
    )
    assert retrieved.classification == study.classification
    assert retrieved.window_count == study.window_count
    assert retrieved.membership_manifest_hash == _EXPECTED_MANIFEST_HASH
    assert [r.snapshot.eligible_count for r in retrieved.window_results] == [
        r.snapshot.eligible_count for r in study.window_results
    ]

    engine = sa.create_engine(config.sqlalchemy_url())
    try:
        with engine.connect() as conn:
            study_row = (
                conn.execute(
                    text(
                        "SELECT dataset_bundle_id, universe_id, universe_membership_model, "
                        "membership_manifest_hash, classification, window_count, "
                        "stress_study_governance_id, stress_comparison "
                        "FROM survivorship_study WHERE governance_id = 'SURV-6401'"
                    )
                )
                .mappings()
                .one()
            )
            window_rows = (
                conn.execute(
                    text(
                        "SELECT window_id, sequence_index, eligible_instrument_ids, "
                        "evaluated_instrument_ids, backtest_run_governance_id "
                        "FROM survivorship_window WHERE study_runtime_id = :runtime_id "
                        "ORDER BY sequence_index"
                    ),
                    {"runtime_id": str(study.identity.runtime_id)},
                )
                .mappings()
                .all()
            )
            stress_study_row = (
                conn.execute(
                    text(
                        "SELECT governance_id, window_count, classification "
                        "FROM robustness_study WHERE governance_id = :gid"
                    ),
                    {"gid": study_row["stress_study_governance_id"]},
                )
                .mappings()
                .one()
            )
            instrument_count = conn.execute(
                text("SELECT count(*) FROM instrument_master")
            ).scalar_one()
            membership_count = conn.execute(
                text("SELECT count(*) FROM membership_record WHERE universe_id = 'UNIVERSE-6401'")
            ).scalar_one()
    finally:
        engine.dispose()

    assert study_row["dataset_bundle_id"] == "DATASET-6401"
    assert study_row["universe_id"] == "UNIVERSE-6401"
    assert study_row["universe_membership_model"] == "HISTORICAL_MEMBERSHIP"
    assert study_row["membership_manifest_hash"] == _EXPECTED_MANIFEST_HASH
    assert study_row["classification"] == "SURVIVORSHIP_AWARE_MEMBERSHIP_MECHANICS_PROVEN"
    assert study_row["window_count"] == 10
    assert study_row["stress_comparison"] == "CURRENT_UNIVERSE_BIAS_STRESS_DIFFERS"
    assert len(window_rows) == 10
    assert [row["window_id"] for row in window_rows] == [f"W{index:02d}" for index in range(1, 11)]
    assert len(window_rows[2]["eligible_instrument_ids"]) == 6
    assert "INSTR-AMZN-001" not in window_rows[0]["eligible_instrument_ids"]
    assert "INSTR-AMZN-001" in window_rows[2]["eligible_instrument_ids"]
    assert stress_study_row["window_count"] == 10
    assert instrument_count == 6
    assert membership_count == 7


def test_real_cli_subprocess_run_and_get(clean_tables: Engine) -> None:
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
            "empirical_platform.entrypoints.run_survivorship_aware_robustness_study",
            "SURV-6410",
            "ROBUST-6411",
            str(_DATASET_BUNDLE_PATH),
            _EXPECTED_DATASET_SHA256,
            str(_INSTRUMENT_MASTER_PATH),
            str(_MEMBERSHIP_MANIFEST_PATH),
            _EXPECTED_MANIFEST_HASH,
            "SURVIVORSHIP_AWARE_MECHANICS_FIXTURE",
            "6500",
            "7500",
            "100000",
            "0.01",
        ],
        cwd=str(_REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert run_result.returncode == 0, run_result.stderr
    run_payload = json.loads(run_result.stdout)
    assert run_payload["classification"] == "SURVIVORSHIP_AWARE_MEMBERSHIP_MECHANICS_PROVEN"

    get_result = subprocess.run(  # noqa: S603
        [
            sys.executable,
            "-m",
            "empirical_platform.entrypoints.get_survivorship_aware_robustness_study",
            "SURV-6410",
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
    assert get_payload["window_count"] == run_payload["window_count"]
    assert get_payload["classification"] == run_payload["classification"]


def test_membership_tamper_is_rejected_before_any_study_is_persisted(
    clean_tables: Engine, tmp_path: Path
) -> None:
    raw = json.loads(_MEMBERSHIP_MANIFEST_PATH.read_text(encoding="utf-8"))
    raw["records"][0]["membership_status"] = "INACTIVE"
    tampered_path = tmp_path / "tampered_membership.json"
    tampered_path.write_text(json.dumps(raw), encoding="utf-8")

    config = _config()
    with pytest.raises(ValueError, match="tamper detected"):
        _run_study(
            study_id="SURV-6499",
            stress_study_id="ROBUST-6498",
            dataset_file=_DATASET_BUNDLE_PATH,
            expected_sha256=_EXPECTED_DATASET_SHA256,
            membership_file=tampered_path,
            expected_membership_hash=_EXPECTED_MANIFEST_HASH,
            run_base=6490,
            stress_run_base=7490,
            seed=64990000,
            config=config,
        )

    engine = sa.create_engine(config.sqlalchemy_url())
    try:
        with engine.connect() as conn:
            count = conn.execute(
                text("SELECT count(*) FROM survivorship_study WHERE governance_id = 'SURV-6499'")
            ).scalar_one()
    finally:
        engine.dispose()
    assert count == 0


def test_future_membership_edit_does_not_change_earlier_windows(
    clean_tables: Engine, tmp_path: Path
) -> None:
    config = _config()
    baseline = _run_study(
        study_id="SURV-6420",
        stress_study_id="ROBUST-6421",
        dataset_file=_DATASET_BUNDLE_PATH,
        expected_sha256=_EXPECTED_DATASET_SHA256,
        membership_file=_MEMBERSHIP_MANIFEST_PATH,
        expected_membership_hash=_EXPECTED_MANIFEST_HASH,
        run_base=6420,
        stress_run_base=7420,
        seed=64200000,
        config=config,
    )

    # Mutate ONLY a membership fact whose effective_from is strictly after
    # W09's own scoring cutoff (the final window's own boundary): move
    # AAPL's own effective_to earlier so it exits mid-way through the LAST
    # window only. AAPL is the only instrument present in every window, so
    # this is guaranteed to change window 10's own eligible set without
    # touching any earlier window's membership facts at all.
    raw = json.loads(_MEMBERSHIP_MANIFEST_PATH.read_text(encoding="utf-8"))
    late_cutoff = "2026-08-10T15:29:00+00:00"  # exactly W10's own scoring_start
    for record in raw["records"]:
        if record["instrument_id"] == "INSTR-AAPL-001":
            record["effective_to"] = late_cutoff
    mutated_path = tmp_path / "mutated_future_membership.json"
    mutated_path.write_text(json.dumps(raw), encoding="utf-8")

    mutated = _run_study(
        study_id="SURV-6422",
        stress_study_id="ROBUST-6423",
        dataset_file=_DATASET_BUNDLE_PATH,
        expected_sha256=_EXPECTED_DATASET_SHA256,
        membership_file=mutated_path,
        expected_membership_hash=_recompute_manifest_hash(mutated_path),
        run_base=6440,
        stress_run_base=7440,
        seed=64220000,
        config=config,
    )

    for baseline_result, mutated_result in zip(
        baseline.window_results[:9], mutated.window_results[:9], strict=True
    ):
        assert (
            mutated_result.snapshot.eligible_instrument_ids
            == baseline_result.snapshot.eligible_instrument_ids
        )
        assert mutated_result.net_pnl == baseline_result.net_pnl
        assert mutated_result.total_r == baseline_result.total_r
        assert mutated_result.executed_trade_count == baseline_result.executed_trade_count

    # The final window DOES change (AAPL is no longer eligible there).
    baseline_w10 = baseline.window_results[9]
    mutated_w10 = mutated.window_results[9]
    aapl = InstrumentId("INSTR-AAPL-001")
    assert aapl in baseline_w10.snapshot.eligible_instrument_ids
    assert aapl not in mutated_w10.snapshot.eligible_instrument_ids


def _recompute_manifest_hash(path: Path) -> str:
    """Compute the real production hash for an edited fixture file, exactly
    as `parse_membership_manifest_file` would, but WITHOUT an expected-hash
    tamper check -- used only to derive the caller-declared hash for a
    deliberately mutated test fixture, never in production code."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    records = tuple(
        MembershipRecord(
            universe_id=raw["universe_id"],
            universe_version=raw["universe_version"],
            instrument_id=InstrumentId(entry["instrument_id"]),
            effective_from=datetime.fromisoformat(entry["effective_from"]),
            effective_to=(
                datetime.fromisoformat(entry["effective_to"]) if entry.get("effective_to") else None
            ),
            membership_status=MembershipStatus(entry["membership_status"]),
            source_kind=entry["source_kind"],
        )
        for entry in raw["records"]
    )
    manifest = MembershipManifest(
        universe_id=raw["universe_id"], universe_version=raw["universe_version"], records=records
    )
    return membership_manifest_hash(manifest)
