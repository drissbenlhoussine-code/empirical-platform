"""MILESTONE-055 real-PostgreSQL end-to-end acceptance test for the Run
Execution Lifecycle vertical slice.

Proves the WHOLE new capability, not merely every entrypoint independently:
before this milestone, a Run could be created but could not genuinely
progress through its execution lifecycle via production composition. This
test drives the complete legal forward lifecycle -- create Run (M053) ->
authorize -> start acquisition -> record acquisition data -> start
normalization -> record normalization data (the second manifest append
proving a genuine optimistic-concurrency conflict, then a corrected retry)
-> start validation -> complete execution -> retrieve -- against one real,
migrated PostgreSQL database, independently verified via direct SQL
read-back that bypasses the repository read path. Also proves the negative
`fail_run` path from a legitimate active state, with manifest data
genuinely preserved across the failure transition, and the genuinely new
failure modes this slice introduces (an out-of-order transition attempt;
appending a manifest after execution has completed).

Opt-in via ``EMPIRICAL_PLATFORM_RUN_POSTGRES_TESTS=1``, following the same
convention as every prior milestone's own PostgreSQL integration tests.
"""

from __future__ import annotations

import os
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

from empirical_platform.entrypoints.append_run_manifest import run_append_run_manifest
from empirical_platform.entrypoints.authorize_run import run_authorize_run
from empirical_platform.entrypoints.complete_run_execution import run_complete_run_execution
from empirical_platform.entrypoints.create_campaign import run_create_campaign
from empirical_platform.entrypoints.create_run import run_create_run
from empirical_platform.entrypoints.fail_run import run_fail_run
from empirical_platform.entrypoints.get_run import run_get_run
from empirical_platform.entrypoints.start_run_acquisition import run_start_run_acquisition
from empirical_platform.entrypoints.start_run_normalization import run_start_run_normalization
from empirical_platform.entrypoints.start_run_validation import run_start_run_validation
from empirical_platform.shared.config.settings import PostgreSQLConfigSnapshot
from empirical_platform.shared.contracts.repository import OptimisticConcurrencyConflict
from empirical_platform.shared.identifiers import DeterministicRuntimeIdentifierGenerator

pytestmark = pytest.mark.integration

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ALL_TABLES = [
    "review_transition",
    "review_finding",
    "review",
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
        application_name="empirical-platform-m055-test",
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
        conn.execute(text(f"TRUNCATE {', '.join(_ALL_TABLES)} CASCADE"))  # noqa: S608
    return upgraded_schema


def _seed_run(*, suffix: str, campaign_id: str, run_id: str) -> str:
    """Seed a real Campaign and Run through the frozen M052/M053 entrypoints,
    returning the Run's runtime_id."""
    run_create_campaign(
        campaign_governance_id=campaign_id,
        scope_statement=f"M055 execution lifecycle seed campaign {suffix}",
        identifier_generator=DeterministicRuntimeIdentifierGenerator(
            [f"1000000{suffix}-0000-4000-8000-000000000001"]
        ),
        config=_config(),
    )
    run_identity = run_create_run(
        run_governance_id=run_id,
        campaign_governance_id=campaign_id,
        identifier_generator=DeterministicRuntimeIdentifierGenerator(
            [f"2000000{suffix}-0000-4000-8000-000000000001"]
        ),
        config=_config(),
    )
    return str(run_identity.runtime_id)


def test_full_run_execution_lifecycle_from_created_to_execution_completed(
    clean_tables: Engine,
) -> None:
    """Drives the entire M055 capability end-to-end against real PostgreSQL,
    proving the platform can genuinely take a Run through its complete legal
    execution lifecycle -- not merely that each individual entrypoint works
    in isolation."""
    run_runtime_id = _seed_run(suffix="1", campaign_id="CAMP-0001", run_id="RUN-0001")

    authorize_result = run_authorize_run(
        run_governance_id="RUN-0001",
        run_runtime_id=run_runtime_id,
        expected_persisted_version=0,
        actor="operator-alpha",
        occurred_at=datetime(2026, 8, 8, 8, 0, 0, tzinfo=UTC),
        config=_config(),
    )
    assert authorize_result.persisted_version.value == 1

    acquisition_result = run_start_run_acquisition(
        run_governance_id="RUN-0001",
        run_runtime_id=run_runtime_id,
        expected_persisted_version=1,
        actor="operator-alpha",
        occurred_at=datetime(2026, 8, 8, 8, 5, 0, tzinfo=UTC),
        config=_config(),
    )
    assert acquisition_result.persisted_version.value == 2

    manifest_one_result = run_append_run_manifest(
        run_governance_id="RUN-0001",
        run_runtime_id=run_runtime_id,
        expected_persisted_version=2,
        recorded_at=datetime(2026, 8, 8, 8, 10, 0, tzinfo=UTC),
        source="s3://acquisition-bucket/RUN-0001/raw.csv",
        acquisition_method="bulk-download",
        config=_config(),
    )
    assert manifest_one_result.persisted_version.value == 3

    normalization_result = run_start_run_normalization(
        run_governance_id="RUN-0001",
        run_runtime_id=run_runtime_id,
        expected_persisted_version=3,
        actor="operator-alpha",
        occurred_at=datetime(2026, 8, 8, 8, 15, 0, tzinfo=UTC),
        config=_config(),
    )
    assert normalization_result.persisted_version.value == 4

    # Genuine optimistic-concurrency conflict: retrying the second manifest
    # append with the now-stale expected_persisted_version=3 (rather than
    # the real current version, 4) must fail, proving a real durable version
    # check -- not a fabricated scenario.
    with pytest.raises(OptimisticConcurrencyConflict):
        run_append_run_manifest(
            run_governance_id="RUN-0001",
            run_runtime_id=run_runtime_id,
            expected_persisted_version=3,
            recorded_at=datetime(2026, 8, 8, 8, 20, 0, tzinfo=UTC),
            source="s3://normalization-bucket/RUN-0001/normalized.csv",
            normalization_method="z-score",
            config=_config(),
        )

    manifest_two_result = run_append_run_manifest(
        run_governance_id="RUN-0001",
        run_runtime_id=run_runtime_id,
        expected_persisted_version=4,
        recorded_at=datetime(2026, 8, 8, 8, 21, 0, tzinfo=UTC),
        source="s3://normalization-bucket/RUN-0001/normalized.csv",
        normalization_method="z-score",
        config=_config(),
    )
    assert manifest_two_result.persisted_version.value == 5

    validation_result = run_start_run_validation(
        run_governance_id="RUN-0001",
        run_runtime_id=run_runtime_id,
        expected_persisted_version=5,
        actor="operator-alpha",
        occurred_at=datetime(2026, 8, 8, 8, 25, 0, tzinfo=UTC),
        config=_config(),
    )
    assert validation_result.persisted_version.value == 6

    complete_result = run_complete_run_execution(
        run_governance_id="RUN-0001",
        run_runtime_id=run_runtime_id,
        expected_persisted_version=6,
        actor="operator-alpha",
        occurred_at=datetime(2026, 8, 8, 8, 30, 0, tzinfo=UTC),
        config=_config(),
    )
    assert complete_result.persisted_version.value == 7

    snapshot = run_get_run(
        run_governance_id="RUN-0001", run_runtime_id=run_runtime_id, config=_config()
    )
    assert snapshot.state.value == "EXECUTION_COMPLETED"
    assert snapshot.campaign_id.value == "CAMP-0001"

    # Independent verification via direct SQL, bypassing the repository
    # read path entirely.
    engine = sa.create_engine(_config().sqlalchemy_url())
    with engine.connect() as conn:
        run_row = (
            conn.execute(
                text("SELECT lifecycle_state, version FROM run WHERE governance_id = :g"),
                {"g": "RUN-0001"},
            )
            .mappings()
            .one()
        )
        manifest_rows = (
            conn.execute(
                text(
                    "SELECT position, source, acquisition_method, normalization_method "
                    "FROM run_manifest WHERE run_runtime_id = :r ORDER BY position"
                ),
                {"r": run_runtime_id},
            )
            .mappings()
            .all()
        )
        transition_rows = (
            conn.execute(
                text(
                    "SELECT from_state, to_state FROM run_transition "
                    "WHERE run_runtime_id = :r ORDER BY sequence"
                ),
                {"r": run_runtime_id},
            )
            .mappings()
            .all()
        )
    engine.dispose()

    assert run_row["lifecycle_state"] == "EXECUTION_COMPLETED"
    assert run_row["version"] == 7
    assert [
        (r["position"], r["source"], r["acquisition_method"], r["normalization_method"])
        for r in manifest_rows
    ] == [
        (0, "s3://acquisition-bucket/RUN-0001/raw.csv", "bulk-download", None),
        (1, "s3://normalization-bucket/RUN-0001/normalized.csv", None, "z-score"),
    ]
    assert [(r["from_state"], r["to_state"]) for r in transition_rows] == [
        ("CREATED", "AUTHORIZED"),
        ("AUTHORIZED", "ACQUIRING"),
        ("ACQUIRING", "NORMALIZING"),
        ("NORMALIZING", "VALIDATING"),
        ("VALIDATING", "EXECUTION_COMPLETED"),
    ]


def test_fail_run_from_a_legitimate_active_state_preserves_manifest_data(
    clean_tables: Engine,
) -> None:
    """Proves the negative terminal path: a Run genuinely fails from an
    active execution-stage state, with previously-recorded manifest data
    surviving the failure transition intact -- independently verified via
    direct SQL."""
    run_runtime_id = _seed_run(suffix="2", campaign_id="CAMP-0002", run_id="RUN-0002")

    run_authorize_run(
        run_governance_id="RUN-0002",
        run_runtime_id=run_runtime_id,
        expected_persisted_version=0,
        actor="operator-beta",
        occurred_at=datetime(2026, 8, 8, 9, 0, 0, tzinfo=UTC),
        config=_config(),
    )
    run_start_run_acquisition(
        run_governance_id="RUN-0002",
        run_runtime_id=run_runtime_id,
        expected_persisted_version=1,
        actor="operator-beta",
        occurred_at=datetime(2026, 8, 8, 9, 5, 0, tzinfo=UTC),
        config=_config(),
    )
    run_append_run_manifest(
        run_governance_id="RUN-0002",
        run_runtime_id=run_runtime_id,
        expected_persisted_version=2,
        recorded_at=datetime(2026, 8, 8, 9, 10, 0, tzinfo=UTC),
        source="s3://acquisition-bucket/RUN-0002/partial.csv",
        acquisition_method="streaming",
        config=_config(),
    )

    fail_result = run_fail_run(
        run_governance_id="RUN-0002",
        run_runtime_id=run_runtime_id,
        expected_persisted_version=3,
        reason="Upstream data source became unavailable mid-acquisition.",
        actor="operator-beta",
        occurred_at=datetime(2026, 8, 8, 9, 15, 0, tzinfo=UTC),
        config=_config(),
    )
    assert fail_result.persisted_version.value == 4

    engine = sa.create_engine(_config().sqlalchemy_url())
    with engine.connect() as conn:
        run_row = (
            conn.execute(
                text("SELECT lifecycle_state, version FROM run WHERE governance_id = :g"),
                {"g": "RUN-0002"},
            )
            .mappings()
            .one()
        )
        manifest_rows = (
            conn.execute(
                text("SELECT source FROM run_manifest WHERE run_runtime_id = :r"),
                {"r": run_runtime_id},
            )
            .mappings()
            .all()
        )
        transition_row = (
            conn.execute(
                text(
                    "SELECT from_state, to_state, reason FROM run_transition "
                    "WHERE run_runtime_id = :r ORDER BY sequence DESC LIMIT 1"
                ),
                {"r": run_runtime_id},
            )
            .mappings()
            .one()
        )
    engine.dispose()

    assert run_row["lifecycle_state"] == "FAILED"
    assert run_row["version"] == 4
    assert [r["source"] for r in manifest_rows] == ["s3://acquisition-bucket/RUN-0002/partial.csv"]
    assert transition_row["from_state"] == "ACQUIRING"
    assert transition_row["to_state"] == "FAILED"
    assert transition_row["reason"] == "Upstream data source became unavailable mid-acquisition."


def test_out_of_order_transition_raises_value_error(clean_tables: Engine) -> None:
    """New failure mode this slice's composition genuinely exercises: a Run
    cannot start acquisition before it has been authorized."""
    run_runtime_id = _seed_run(suffix="3", campaign_id="CAMP-0003", run_id="RUN-0003")

    with pytest.raises(ValueError, match="cannot transition from"):
        run_start_run_acquisition(
            run_governance_id="RUN-0003",
            run_runtime_id=run_runtime_id,
            expected_persisted_version=0,
            actor="operator-gamma",
            occurred_at=datetime(2026, 8, 8, 10, 0, 0, tzinfo=UTC),
            config=_config(),
        )


def test_append_manifest_after_execution_completed_raises_value_error(
    clean_tables: Engine,
) -> None:
    """New failure mode this slice's composition genuinely exercises: a
    Dataset Manifest cannot be appended once a Run has reached
    EXECUTION_COMPLETED."""
    run_runtime_id = _seed_run(suffix="4", campaign_id="CAMP-0004", run_id="RUN-0004")
    run_authorize_run(
        run_governance_id="RUN-0004",
        run_runtime_id=run_runtime_id,
        expected_persisted_version=0,
        actor="operator-delta",
        occurred_at=datetime(2026, 8, 8, 11, 0, 0, tzinfo=UTC),
        config=_config(),
    )
    run_start_run_acquisition(
        run_governance_id="RUN-0004",
        run_runtime_id=run_runtime_id,
        expected_persisted_version=1,
        actor="operator-delta",
        occurred_at=datetime(2026, 8, 8, 11, 5, 0, tzinfo=UTC),
        config=_config(),
    )
    run_start_run_normalization(
        run_governance_id="RUN-0004",
        run_runtime_id=run_runtime_id,
        expected_persisted_version=2,
        actor="operator-delta",
        occurred_at=datetime(2026, 8, 8, 11, 10, 0, tzinfo=UTC),
        config=_config(),
    )
    run_start_run_validation(
        run_governance_id="RUN-0004",
        run_runtime_id=run_runtime_id,
        expected_persisted_version=3,
        actor="operator-delta",
        occurred_at=datetime(2026, 8, 8, 11, 15, 0, tzinfo=UTC),
        config=_config(),
    )
    run_complete_run_execution(
        run_governance_id="RUN-0004",
        run_runtime_id=run_runtime_id,
        expected_persisted_version=4,
        actor="operator-delta",
        occurred_at=datetime(2026, 8, 8, 11, 20, 0, tzinfo=UTC),
        config=_config(),
    )

    with pytest.raises(ValueError, match="may not be appended"):
        run_append_run_manifest(
            run_governance_id="RUN-0004",
            run_runtime_id=run_runtime_id,
            expected_persisted_version=5,
            recorded_at=datetime(2026, 8, 8, 11, 25, 0, tzinfo=UTC),
            source="should-never-persist",
            config=_config(),
        )


def test_default_config_resolves_from_environment(
    monkeypatch: pytest.MonkeyPatch, clean_tables: Engine
) -> None:
    """Proves the production default path -- omitting `config` -- really
    resolves through `resolve_foundation_config()` against this same
    disposable database for the reused MILESTONE-053
    `_composition.postgres_repository_runtime()` helper."""
    config = _config()
    monkeypatch.setenv("EMPIRICAL_PLATFORM_POSTGRES_HOST", config.host)
    monkeypatch.setenv("EMPIRICAL_PLATFORM_POSTGRES_PORT", str(config.port))
    monkeypatch.setenv("EMPIRICAL_PLATFORM_POSTGRES_DATABASE", config.database)
    monkeypatch.setenv("EMPIRICAL_PLATFORM_POSTGRES_USER", config.user)
    monkeypatch.setenv("EMPIRICAL_PLATFORM_POSTGRES_PASSWORD", config.password.get_secret_value())

    run_runtime_id = _seed_run(suffix="5", campaign_id="CAMP-0005", run_id="RUN-0005")
    authorize_result = run_authorize_run(
        run_governance_id="RUN-0005",
        run_runtime_id=run_runtime_id,
        expected_persisted_version=0,
        actor="operator-epsilon",
        occurred_at=datetime(2026, 8, 8, 12, 0, 0, tzinfo=UTC),
    )

    assert authorize_result.persisted_version.value == 1
