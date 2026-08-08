"""MILESTONE-056 real-PostgreSQL cross-aggregate acceptance test.

This is the CORE ENGINE closure proof (Phase 10/14 of the M056 mission): now
that Campaign (M056), Run (M055), EvidencePackage (M053), and Review (M054)
are each independently composed into real production entrypoints, this test
proves a real caller can invoke them SEQUENTIALLY -- through their actual,
already-frozen entrypoints, no new orchestration layer, no dispatcher, no
automation framework -- to drive one coherent chain from Campaign creation
all the way through a completed Review and a completed Campaign:

Campaign created -> revised -> prepared -> authorized -> activated (ACTIVE)
  -> Run created under that Campaign -> authorized -> acquisition -> manifest
     -> normalization -> validation -> execution completed
  -> EvidencePackage created under that Run -> collection started
     -> criterion result recorded -> artifact reference recorded -> sealed
  -> Review created targeting that sealed EvidencePackage -> started
     -> finding added -> completed
  -> Campaign completed

Final state of all four aggregates is independently verified via direct SQL,
bypassing every repository read path.

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

from empirical_platform.entrypoints.activate_campaign import run_activate_campaign
from empirical_platform.entrypoints.add_review_finding import run_add_review_finding
from empirical_platform.entrypoints.append_run_manifest import run_append_run_manifest
from empirical_platform.entrypoints.authorize_run import run_authorize_run
from empirical_platform.entrypoints.complete_campaign import run_complete_campaign
from empirical_platform.entrypoints.complete_review import run_complete_review
from empirical_platform.entrypoints.complete_run_execution import run_complete_run_execution
from empirical_platform.entrypoints.create_campaign import run_create_campaign
from empirical_platform.entrypoints.create_evidence_package import run_create_evidence_package
from empirical_platform.entrypoints.create_review import run_create_review
from empirical_platform.entrypoints.create_run import run_create_run
from empirical_platform.entrypoints.prepare_campaign_for_authorization import (
    run_prepare_campaign_for_authorization,
)
from empirical_platform.entrypoints.record_campaign_authorization import (
    run_record_campaign_authorization,
)
from empirical_platform.entrypoints.record_evidence_package_artifact_reference import (
    run_record_evidence_package_artifact_reference,
)
from empirical_platform.entrypoints.record_evidence_package_criterion_result import (
    run_record_evidence_package_criterion_result,
)
from empirical_platform.entrypoints.revise_campaign_scope_statement import (
    run_revise_campaign_scope_statement,
)
from empirical_platform.entrypoints.seal_evidence_package import run_seal_evidence_package
from empirical_platform.entrypoints.start_evidence_package_collection import (
    run_start_evidence_package_collection,
)
from empirical_platform.entrypoints.start_review import run_start_review
from empirical_platform.entrypoints.start_run_acquisition import run_start_run_acquisition
from empirical_platform.entrypoints.start_run_normalization import run_start_run_normalization
from empirical_platform.entrypoints.start_run_validation import run_start_run_validation
from empirical_platform.review.lifecycle import ReviewDisposition
from empirical_platform.shared.config.settings import PostgreSQLConfigSnapshot
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
        application_name="empirical-platform-m056-cross-aggregate-test",
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


def test_full_core_engine_chain_campaign_run_evidence_review(clean_tables: Engine) -> None:
    """Drives one real caller through the entire core engine, sequentially
    invoking already-frozen production entrypoints across all four
    aggregates -- no new orchestration layer -- proving the core engine is
    now functionally closed end-to-end."""
    config = _config()

    # --- Campaign: created -> revised -> prepared -> authorized -> ACTIVE ---
    campaign_identity = run_create_campaign(
        campaign_governance_id="CAMP-9001",
        scope_statement="cross-aggregate chain campaign",
        identifier_generator=DeterministicRuntimeIdentifierGenerator(
            ["a0000001-0000-4000-8000-000000000001"]
        ),
        config=config,
    )
    campaign_runtime_id = str(campaign_identity.runtime_id)
    run_revise_campaign_scope_statement(
        campaign_governance_id="CAMP-9001",
        campaign_runtime_id=campaign_runtime_id,
        expected_persisted_version=0,
        scope_statement="cross-aggregate chain campaign, revised",
        config=config,
    )
    run_prepare_campaign_for_authorization(
        campaign_governance_id="CAMP-9001",
        campaign_runtime_id=campaign_runtime_id,
        expected_persisted_version=1,
        actor="chain-operator",
        occurred_at=datetime(2026, 8, 8, 7, 0, 0, tzinfo=UTC),
        config=config,
    )
    run_record_campaign_authorization(
        campaign_governance_id="CAMP-9001",
        campaign_runtime_id=campaign_runtime_id,
        expected_persisted_version=2,
        reason="approved",
        actor="chain-operator",
        occurred_at=datetime(2026, 8, 8, 7, 5, 0, tzinfo=UTC),
        config=config,
    )
    run_activate_campaign(
        campaign_governance_id="CAMP-9001",
        campaign_runtime_id=campaign_runtime_id,
        expected_persisted_version=3,
        reason="beginning execution",
        actor="chain-operator",
        occurred_at=datetime(2026, 8, 8, 7, 10, 0, tzinfo=UTC),
        config=config,
    )

    # --- Run: created under the now-ACTIVE Campaign -> full execution lifecycle ---
    run_identity = run_create_run(
        run_governance_id="RUN-9001",
        campaign_governance_id="CAMP-9001",
        identifier_generator=DeterministicRuntimeIdentifierGenerator(
            ["a0000002-0000-4000-8000-000000000001"]
        ),
        config=config,
    )
    run_runtime_id = str(run_identity.runtime_id)
    run_authorize_run(
        run_governance_id="RUN-9001",
        run_runtime_id=run_runtime_id,
        expected_persisted_version=0,
        actor="chain-operator",
        occurred_at=datetime(2026, 8, 8, 7, 15, 0, tzinfo=UTC),
        config=config,
    )
    run_start_run_acquisition(
        run_governance_id="RUN-9001",
        run_runtime_id=run_runtime_id,
        expected_persisted_version=1,
        actor="chain-operator",
        occurred_at=datetime(2026, 8, 8, 7, 20, 0, tzinfo=UTC),
        config=config,
    )
    run_append_run_manifest(
        run_governance_id="RUN-9001",
        run_runtime_id=run_runtime_id,
        expected_persisted_version=2,
        recorded_at=datetime(2026, 8, 8, 7, 25, 0, tzinfo=UTC),
        source="s3://chain-bucket/RUN-9001/raw.csv",
        acquisition_method="bulk-download",
        config=config,
    )
    run_start_run_normalization(
        run_governance_id="RUN-9001",
        run_runtime_id=run_runtime_id,
        expected_persisted_version=3,
        actor="chain-operator",
        occurred_at=datetime(2026, 8, 8, 7, 30, 0, tzinfo=UTC),
        config=config,
    )
    run_start_run_validation(
        run_governance_id="RUN-9001",
        run_runtime_id=run_runtime_id,
        expected_persisted_version=4,
        actor="chain-operator",
        occurred_at=datetime(2026, 8, 8, 7, 35, 0, tzinfo=UTC),
        config=config,
    )
    run_complete_run_execution(
        run_governance_id="RUN-9001",
        run_runtime_id=run_runtime_id,
        expected_persisted_version=5,
        actor="chain-operator",
        occurred_at=datetime(2026, 8, 8, 7, 40, 0, tzinfo=UTC),
        config=config,
    )

    # --- EvidencePackage: created under the completed Run -> SEALED ---
    ep_identity = run_create_evidence_package(
        evidence_package_governance_id="EVID-9001",
        run_governance_id="RUN-9001",
        identifier_generator=DeterministicRuntimeIdentifierGenerator(
            ["a0000003-0000-4000-8000-000000000001"]
        ),
        config=config,
    )
    ep_runtime_id = str(ep_identity.runtime_id)
    run_start_evidence_package_collection(
        evidence_package_governance_id="EVID-9001",
        evidence_package_runtime_id=ep_runtime_id,
        expected_persisted_version=0,
        actor="chain-operator",
        occurred_at=datetime(2026, 8, 8, 7, 45, 0, tzinfo=UTC),
        config=config,
    )
    run_record_evidence_package_criterion_result(
        evidence_package_governance_id="EVID-9001",
        evidence_package_runtime_id=ep_runtime_id,
        expected_persisted_version=1,
        criterion_id="criterion-chain-1",
        recorded_at=datetime(2026, 8, 8, 7, 50, 0, tzinfo=UTC),
        result_label="PASS",
        config=config,
    )
    run_record_evidence_package_artifact_reference(
        evidence_package_governance_id="EVID-9001",
        evidence_package_runtime_id=ep_runtime_id,
        expected_persisted_version=2,
        value="s3://chain-bucket/EVID-9001/report.json",
        config=config,
    )
    run_seal_evidence_package(
        evidence_package_governance_id="EVID-9001",
        evidence_package_runtime_id=ep_runtime_id,
        expected_persisted_version=3,
        actor="chain-operator",
        occurred_at=datetime(2026, 8, 8, 7, 55, 0, tzinfo=UTC),
        config=config,
    )

    # --- Review: created targeting the sealed EvidencePackage -> COMPLETED ---
    review_identity = run_create_review(
        review_governance_id="REVIEW-9001",
        target_evidence_package_governance_id="EVID-9001",
        reviewer_reference="chain-reviewer",
        identifier_generator=DeterministicRuntimeIdentifierGenerator(
            ["a0000004-0000-4000-8000-000000000001"]
        ),
        config=config,
    )
    review_runtime_id = str(review_identity.runtime_id)
    run_start_review(
        review_governance_id="REVIEW-9001",
        review_runtime_id=review_runtime_id,
        expected_persisted_version=0,
        actor="chain-reviewer",
        occurred_at=datetime(2026, 8, 8, 8, 0, 0, tzinfo=UTC),
        config=config,
    )
    run_add_review_finding(
        review_governance_id="REVIEW-9001",
        review_runtime_id=review_runtime_id,
        expected_persisted_version=1,
        text="Evidence is complete and internally consistent.",
        config=config,
    )
    run_complete_review(
        review_governance_id="REVIEW-9001",
        review_runtime_id=review_runtime_id,
        expected_persisted_version=2,
        disposition=ReviewDisposition.ACCEPTED,
        final_disposition_rationale="Chain acceptance criteria satisfied.",
        actor="chain-reviewer",
        occurred_at=datetime(2026, 8, 8, 8, 5, 0, tzinfo=UTC),
        config=config,
    )

    # --- Campaign: completed, closing the full chain ---
    run_complete_campaign(
        campaign_governance_id="CAMP-9001",
        campaign_runtime_id=campaign_runtime_id,
        expected_persisted_version=4,
        reason="full chain executed and reviewed successfully",
        actor="chain-operator",
        occurred_at=datetime(2026, 8, 8, 8, 10, 0, tzinfo=UTC),
        config=config,
    )

    # Independent verification via direct SQL, bypassing every repository
    # read path -- the final truth of all four aggregates in one chain.
    engine = sa.create_engine(config.sqlalchemy_url())
    with engine.connect() as conn:
        campaign_row = (
            conn.execute(
                text("SELECT lifecycle_state, version FROM campaign WHERE governance_id = :g"),
                {"g": "CAMP-9001"},
            )
            .mappings()
            .one()
        )
        run_row = (
            conn.execute(
                text(
                    "SELECT lifecycle_state, version, campaign_id FROM run WHERE governance_id = :g"
                ),
                {"g": "RUN-9001"},
            )
            .mappings()
            .one()
        )
        ep_row = (
            conn.execute(
                text(
                    "SELECT lifecycle_state, version, run_id FROM evidence_package "
                    "WHERE governance_id = :g"
                ),
                {"g": "EVID-9001"},
            )
            .mappings()
            .one()
        )
        review_row = (
            conn.execute(
                text(
                    "SELECT lifecycle_state, disposition, version, target_evidence_package_id "
                    "FROM review WHERE governance_id = :g"
                ),
                {"g": "REVIEW-9001"},
            )
            .mappings()
            .one()
        )
    engine.dispose()

    assert campaign_row["lifecycle_state"] == "COMPLETED"
    assert campaign_row["version"] == 5
    assert run_row["lifecycle_state"] == "EXECUTION_COMPLETED"
    assert run_row["version"] == 6
    assert run_row["campaign_id"] == "CAMP-9001"
    assert ep_row["lifecycle_state"] == "SEALED"
    assert ep_row["version"] == 4
    assert ep_row["run_id"] == "RUN-9001"
    assert review_row["lifecycle_state"] == "COMPLETED"
    assert review_row["disposition"] == "ACCEPTED"
    assert review_row["version"] == 3
    assert review_row["target_evidence_package_id"] == "EVID-9001"
