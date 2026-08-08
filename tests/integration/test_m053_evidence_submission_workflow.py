"""MILESTONE-053 real-PostgreSQL end-to-end acceptance test for the Evidence
Submission Workflow vertical slice.

Proves the WHOLE new capability, not merely every entrypoint independently:
before this milestone, nothing could be created downstream of a Campaign
(Run and EvidencePackage creation/retrieval, and every EvidencePackage
collection-writing transition, were unreachable from any real entrypoint).
This test drives the full chain through the real composed entrypoints --
create Run -> create EvidencePackage -> start collection -> record two
CriterionResults (the second proving a genuine optimistic-concurrency
conflict, then a corrected retry) -> record an ArtifactReference -> seal ->
retrieve both final Run and EvidencePackage states -- against one real,
migrated PostgreSQL database, independently verified via direct SQL
read-back that bypasses the repository read path. A Campaign is seeded via
the already-frozen MILESTONE-052 `run_create_campaign` entrypoint, since
Run creation requires an existing Campaign (enforced by the database's own
foreign key, not re-verified here).

Also proves the two new failure modes this slice genuinely introduces:
sealing an EvidencePackage with no recorded CriterionResult, and recording
a CriterionResult on an EvidencePackage that is not COLLECTING.

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

from empirical_platform.entrypoints.create_campaign import run_create_campaign
from empirical_platform.entrypoints.create_evidence_package import run_create_evidence_package
from empirical_platform.entrypoints.create_run import run_create_run
from empirical_platform.entrypoints.get_evidence_package import run_get_evidence_package
from empirical_platform.entrypoints.get_run import run_get_run
from empirical_platform.entrypoints.record_evidence_package_artifact_reference import (
    run_record_evidence_package_artifact_reference,
)
from empirical_platform.entrypoints.record_evidence_package_criterion_result import (
    run_record_evidence_package_criterion_result,
)
from empirical_platform.entrypoints.seal_evidence_package import run_seal_evidence_package
from empirical_platform.entrypoints.start_evidence_package_collection import (
    run_start_evidence_package_collection,
)
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
        application_name="empirical-platform-m053-test",
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


def _seed_campaign(campaign_governance_id: str, runtime_id_value: str) -> None:
    run_create_campaign(
        campaign_governance_id=campaign_governance_id,
        scope_statement="a seeded campaign for M053 evidence submission testing",
        identifier_generator=DeterministicRuntimeIdentifierGenerator([runtime_id_value]),
        config=_config(),
    )


def test_full_evidence_submission_workflow_golden_path(clean_tables: Engine) -> None:
    """Drives the entire M053 capability end-to-end against real PostgreSQL,
    proving the platform can genuinely go from an existing Campaign to a
    sealed, fully-populated EvidencePackage -- not merely that each
    individual entrypoint works in isolation."""
    _seed_campaign("CAMP-0001", "10000000-0000-4000-8000-000000000001")

    run_identity = run_create_run(
        run_governance_id="RUN-0001",
        campaign_governance_id="CAMP-0001",
        identifier_generator=DeterministicRuntimeIdentifierGenerator(
            ["20000000-0000-4000-8000-000000000001"]
        ),
        config=_config(),
    )
    assert str(run_identity.governance_id) == "RUN-0001"

    ep_identity = run_create_evidence_package(
        evidence_package_governance_id="EVID-0001",
        run_governance_id="RUN-0001",
        identifier_generator=DeterministicRuntimeIdentifierGenerator(
            ["30000000-0000-4000-8000-000000000001"]
        ),
        config=_config(),
    )
    assert str(ep_identity.governance_id) == "EVID-0001"

    start_result = run_start_evidence_package_collection(
        evidence_package_governance_id="EVID-0001",
        evidence_package_runtime_id=str(ep_identity.runtime_id),
        expected_persisted_version=0,
        actor="workflow-actor",
        occurred_at=datetime(2026, 8, 8, 12, 0, 0, tzinfo=UTC),
        config=_config(),
    )
    assert start_result.persisted_version.value == 1

    first_criterion_result = run_record_evidence_package_criterion_result(
        evidence_package_governance_id="EVID-0001",
        evidence_package_runtime_id=str(ep_identity.runtime_id),
        expected_persisted_version=1,
        criterion_id="criterion-1",
        recorded_at=datetime(2026, 8, 8, 12, 5, 0, tzinfo=UTC),
        result_label="PASS",
        summary="first criterion result",
        config=_config(),
    )
    assert first_criterion_result.persisted_version.value == 2

    # Genuine optimistic-concurrency conflict: retrying with the now-stale
    # expected_persisted_version=1 (rather than the real current version, 2)
    # must fail, proving a real durable version check -- not a fabricated
    # scenario.
    with pytest.raises(OptimisticConcurrencyConflict):
        run_record_evidence_package_criterion_result(
            evidence_package_governance_id="EVID-0001",
            evidence_package_runtime_id=str(ep_identity.runtime_id),
            expected_persisted_version=1,
            criterion_id="criterion-2",
            recorded_at=datetime(2026, 8, 8, 12, 6, 0, tzinfo=UTC),
            result_label="PASS",
            config=_config(),
        )

    second_criterion_result = run_record_evidence_package_criterion_result(
        evidence_package_governance_id="EVID-0001",
        evidence_package_runtime_id=str(ep_identity.runtime_id),
        expected_persisted_version=2,
        criterion_id="criterion-2",
        recorded_at=datetime(2026, 8, 8, 12, 7, 0, tzinfo=UTC),
        result_label="FAIL",
        summary="second criterion result, corrected version",
        config=_config(),
    )
    assert second_criterion_result.persisted_version.value == 3

    artifact_result = run_record_evidence_package_artifact_reference(
        evidence_package_governance_id="EVID-0001",
        evidence_package_runtime_id=str(ep_identity.runtime_id),
        expected_persisted_version=3,
        value="s3://evidence-bucket/EVID-0001/report.json",
        config=_config(),
    )
    assert artifact_result.persisted_version.value == 4

    seal_result = run_seal_evidence_package(
        evidence_package_governance_id="EVID-0001",
        evidence_package_runtime_id=str(ep_identity.runtime_id),
        expected_persisted_version=4,
        actor="workflow-actor",
        occurred_at=datetime(2026, 8, 8, 12, 10, 0, tzinfo=UTC),
        config=_config(),
    )
    assert seal_result.persisted_version.value == 5

    run_snapshot = run_get_run(
        run_governance_id="RUN-0001",
        run_runtime_id=str(run_identity.runtime_id),
        config=_config(),
    )
    assert run_snapshot.campaign_id.value == "CAMP-0001"

    ep_snapshot = run_get_evidence_package(
        evidence_package_governance_id="EVID-0001",
        evidence_package_runtime_id=str(ep_identity.runtime_id),
        config=_config(),
    )
    assert str(ep_snapshot.run_id) == "RUN-0001"
    assert ep_snapshot.state.value == "SEALED"

    # Independent verification via direct SQL, bypassing the repository
    # read path entirely.
    engine = sa.create_engine(_config().sqlalchemy_url())
    with engine.connect() as conn:
        ep_row = (
            conn.execute(
                text(
                    "SELECT lifecycle_state, version FROM evidence_package WHERE governance_id = :g"
                ),
                {"g": "EVID-0001"},
            )
            .mappings()
            .one()
        )
        criterion_rows = (
            conn.execute(
                text(
                    "SELECT criterion_id, result_label FROM evidence_package_criterion_result "
                    "WHERE evidence_package_runtime_id = :r ORDER BY position"
                ),
                {"r": str(ep_identity.runtime_id)},
            )
            .mappings()
            .all()
        )
        artifact_rows = (
            conn.execute(
                text(
                    "SELECT value FROM evidence_package_artifact_reference "
                    "WHERE evidence_package_runtime_id = :r"
                ),
                {"r": str(ep_identity.runtime_id)},
            )
            .mappings()
            .all()
        )
    engine.dispose()

    assert ep_row["lifecycle_state"] == "SEALED"
    assert ep_row["version"] == 5
    assert [(r["criterion_id"], r["result_label"]) for r in criterion_rows] == [
        ("criterion-1", "PASS"),
        ("criterion-2", "FAIL"),
    ]
    assert [r["value"] for r in artifact_rows] == ["s3://evidence-bucket/EVID-0001/report.json"]


def test_seal_without_any_recorded_criterion_result_raises_value_error(
    clean_tables: Engine,
) -> None:
    """New failure mode introduced by this slice: an EvidencePackage cannot
    be sealed while COLLECTING with zero recorded CriterionResults."""
    _seed_campaign("CAMP-0002", "10000000-0000-4000-8000-000000000002")
    run_create_run(
        run_governance_id="RUN-0002",
        campaign_governance_id="CAMP-0002",
        identifier_generator=DeterministicRuntimeIdentifierGenerator(
            ["20000000-0000-4000-8000-000000000002"]
        ),
        config=_config(),
    )
    ep_identity = run_create_evidence_package(
        evidence_package_governance_id="EVID-0002",
        run_governance_id="RUN-0002",
        identifier_generator=DeterministicRuntimeIdentifierGenerator(
            ["30000000-0000-4000-8000-000000000002"]
        ),
        config=_config(),
    )
    run_start_evidence_package_collection(
        evidence_package_governance_id="EVID-0002",
        evidence_package_runtime_id=str(ep_identity.runtime_id),
        expected_persisted_version=0,
        actor="workflow-actor",
        occurred_at=datetime(2026, 8, 8, 12, 0, 0, tzinfo=UTC),
        config=_config(),
    )

    with pytest.raises(ValueError, match="at least one Criterion Result"):
        run_seal_evidence_package(
            evidence_package_governance_id="EVID-0002",
            evidence_package_runtime_id=str(ep_identity.runtime_id),
            expected_persisted_version=1,
            actor="workflow-actor",
            occurred_at=datetime(2026, 8, 8, 12, 10, 0, tzinfo=UTC),
            config=_config(),
        )


def test_recording_criterion_result_before_collection_started_raises_value_error(
    clean_tables: Engine,
) -> None:
    """New failure mode introduced by this slice: a CriterionResult cannot be
    recorded on an EvidencePackage that is still INITIALIZED (collection
    never started)."""
    _seed_campaign("CAMP-0003", "10000000-0000-4000-8000-000000000003")
    run_create_run(
        run_governance_id="RUN-0003",
        campaign_governance_id="CAMP-0003",
        identifier_generator=DeterministicRuntimeIdentifierGenerator(
            ["20000000-0000-4000-8000-000000000003"]
        ),
        config=_config(),
    )
    ep_identity = run_create_evidence_package(
        evidence_package_governance_id="EVID-0003",
        run_governance_id="RUN-0003",
        identifier_generator=DeterministicRuntimeIdentifierGenerator(
            ["30000000-0000-4000-8000-000000000003"]
        ),
        config=_config(),
    )

    with pytest.raises(ValueError, match="only while COLLECTING"):
        run_record_evidence_package_criterion_result(
            evidence_package_governance_id="EVID-0003",
            evidence_package_runtime_id=str(ep_identity.runtime_id),
            expected_persisted_version=0,
            criterion_id="criterion-1",
            recorded_at=datetime(2026, 8, 8, 12, 5, 0, tzinfo=UTC),
            result_label="PASS",
            config=_config(),
        )


def test_default_config_resolves_from_environment(
    monkeypatch: pytest.MonkeyPatch, clean_tables: Engine
) -> None:
    """Proves the production default path -- omitting `config` -- really
    resolves through `resolve_foundation_config()` against this same
    disposable database for the new `_composition.postgres_repository_runtime()`
    helper, not just the explicit-override path every other test in this
    file exercises."""
    config = _config()
    monkeypatch.setenv("EMPIRICAL_PLATFORM_POSTGRES_HOST", config.host)
    monkeypatch.setenv("EMPIRICAL_PLATFORM_POSTGRES_PORT", str(config.port))
    monkeypatch.setenv("EMPIRICAL_PLATFORM_POSTGRES_DATABASE", config.database)
    monkeypatch.setenv("EMPIRICAL_PLATFORM_POSTGRES_USER", config.user)
    monkeypatch.setenv("EMPIRICAL_PLATFORM_POSTGRES_PASSWORD", config.password.get_secret_value())

    _seed_campaign("CAMP-0004", "10000000-0000-4000-8000-000000000004")
    run_identity = run_create_run(
        run_governance_id="RUN-0004",
        campaign_governance_id="CAMP-0004",
        identifier_generator=DeterministicRuntimeIdentifierGenerator(
            ["20000000-0000-4000-8000-000000000004"]
        ),
    )

    assert str(run_identity.governance_id) == "RUN-0004"
