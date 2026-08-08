"""MILESTONE-054 real-PostgreSQL end-to-end acceptance test for the Review
Workflow Production Composition vertical slice.

Proves the WHOLE new capability as a genuine cross-milestone continuation,
not merely every entrypoint independently: this test drives a real
EvidencePackage through the frozen M053 entrypoints all the way to SEALED,
then continues directly into the new M054 Review entrypoints -- create
Review -> start Review -> add two Findings (the second proving a genuine
optimistic-concurrency conflict, then a corrected retry) -> complete Review
-> retrieve the completed Review -- against one real, migrated PostgreSQL
database, independently verified via direct SQL read-back that bypasses the
repository read path. Also proves the `cancel_review` alternate terminal
path on a separate Review, and the genuinely new failure modes this slice
introduces (complete without any finding; add a finding outside
IN_PROGRESS).

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

from empirical_platform.entrypoints.add_review_finding import run_add_review_finding
from empirical_platform.entrypoints.cancel_review import run_cancel_review
from empirical_platform.entrypoints.complete_review import run_complete_review
from empirical_platform.entrypoints.create_campaign import run_create_campaign
from empirical_platform.entrypoints.create_evidence_package import run_create_evidence_package
from empirical_platform.entrypoints.create_review import run_create_review
from empirical_platform.entrypoints.create_run import run_create_run
from empirical_platform.entrypoints.get_review import run_get_review
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
from empirical_platform.entrypoints.start_review import run_start_review
from empirical_platform.review.lifecycle import ReviewDisposition
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
        application_name="empirical-platform-m054-test",
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


def _seal_a_real_evidence_package(*, suffix: str, campaign_id: str, run_id: str, ep_id: str) -> str:
    """Drive a real EvidencePackage all the way to SEALED through the frozen
    M052/M053 entrypoints, returning its runtime_id. This is the genuine
    cross-milestone continuation point for M054."""
    run_create_campaign(
        campaign_governance_id=campaign_id,
        scope_statement=f"M054 continuation seed campaign {suffix}",
        identifier_generator=DeterministicRuntimeIdentifierGenerator(
            [f"1000000{suffix}-0000-4000-8000-000000000001"]
        ),
        config=_config(),
    )
    run_create_run(
        run_governance_id=run_id,
        campaign_governance_id=campaign_id,
        identifier_generator=DeterministicRuntimeIdentifierGenerator(
            [f"2000000{suffix}-0000-4000-8000-000000000001"]
        ),
        config=_config(),
    )
    ep_identity = run_create_evidence_package(
        evidence_package_governance_id=ep_id,
        run_governance_id=run_id,
        identifier_generator=DeterministicRuntimeIdentifierGenerator(
            [f"3000000{suffix}-0000-4000-8000-000000000001"]
        ),
        config=_config(),
    )
    ep_runtime_id = str(ep_identity.runtime_id)
    run_start_evidence_package_collection(
        evidence_package_governance_id=ep_id,
        evidence_package_runtime_id=ep_runtime_id,
        expected_persisted_version=0,
        actor="m054-seed-actor",
        occurred_at=datetime(2026, 8, 8, 9, 0, 0, tzinfo=UTC),
        config=_config(),
    )
    run_record_evidence_package_criterion_result(
        evidence_package_governance_id=ep_id,
        evidence_package_runtime_id=ep_runtime_id,
        expected_persisted_version=1,
        criterion_id="criterion-1",
        recorded_at=datetime(2026, 8, 8, 9, 5, 0, tzinfo=UTC),
        result_label="PASS",
        config=_config(),
    )
    run_record_evidence_package_artifact_reference(
        evidence_package_governance_id=ep_id,
        evidence_package_runtime_id=ep_runtime_id,
        expected_persisted_version=2,
        value=f"s3://evidence-bucket/{ep_id}/report.json",
        config=_config(),
    )
    run_seal_evidence_package(
        evidence_package_governance_id=ep_id,
        evidence_package_runtime_id=ep_runtime_id,
        expected_persisted_version=3,
        actor="m054-seed-actor",
        occurred_at=datetime(2026, 8, 8, 9, 10, 0, tzinfo=UTC),
        config=_config(),
    )
    return ep_runtime_id


def test_full_review_workflow_from_a_genuinely_sealed_evidence_package(
    clean_tables: Engine,
) -> None:
    """Drives the entire M054 capability end-to-end, continuing directly
    from a real, M053-composed, genuinely SEALED EvidencePackage -- proving
    the platform can take persisted evidence through a complete Review
    lifecycle and retrieve the completed result through real production
    composition."""
    _seal_a_real_evidence_package(
        suffix="1", campaign_id="CAMP-0001", run_id="RUN-0001", ep_id="EVID-0001"
    )

    review_identity = run_create_review(
        review_governance_id="REVIEW-0001",
        target_evidence_package_governance_id="EVID-0001",
        reviewer_reference="reviewer-alpha",
        identifier_generator=DeterministicRuntimeIdentifierGenerator(
            ["40000000-0000-4000-8000-000000000001"]
        ),
        config=_config(),
    )
    assert str(review_identity.governance_id) == "REVIEW-0001"
    review_runtime_id = str(review_identity.runtime_id)

    start_result = run_start_review(
        review_governance_id="REVIEW-0001",
        review_runtime_id=review_runtime_id,
        expected_persisted_version=0,
        actor="reviewer-alpha",
        occurred_at=datetime(2026, 8, 8, 10, 0, 0, tzinfo=UTC),
        config=_config(),
    )
    assert start_result.persisted_version.value == 1

    first_finding = run_add_review_finding(
        review_governance_id="REVIEW-0001",
        review_runtime_id=review_runtime_id,
        expected_persisted_version=1,
        text="Criterion coverage looks complete.",
        rationale="Reviewed against the sealed evidence package directly.",
        config=_config(),
    )
    assert first_finding.persisted_version.value == 2

    # Genuine optimistic-concurrency conflict: retrying with the now-stale
    # expected_persisted_version=1 must fail, proving a real durable version
    # check -- not a fabricated scenario.
    with pytest.raises(OptimisticConcurrencyConflict):
        run_add_review_finding(
            review_governance_id="REVIEW-0001",
            review_runtime_id=review_runtime_id,
            expected_persisted_version=1,
            text="A second finding, submitted with a stale version.",
            config=_config(),
        )

    second_finding = run_add_review_finding(
        review_governance_id="REVIEW-0001",
        review_runtime_id=review_runtime_id,
        expected_persisted_version=2,
        text="No missing artifact references observed.",
        config=_config(),
    )
    assert second_finding.persisted_version.value == 3

    complete_result = run_complete_review(
        review_governance_id="REVIEW-0001",
        review_runtime_id=review_runtime_id,
        expected_persisted_version=3,
        disposition=ReviewDisposition.ACCEPTED,
        final_disposition_rationale="Evidence is complete and consistent.",
        actor="reviewer-alpha",
        occurred_at=datetime(2026, 8, 8, 10, 30, 0, tzinfo=UTC),
        config=_config(),
    )
    assert complete_result.persisted_version.value == 4

    snapshot = run_get_review(
        review_governance_id="REVIEW-0001",
        review_runtime_id=review_runtime_id,
        config=_config(),
    )
    assert snapshot.state.value == "COMPLETED"
    assert str(snapshot.target_evidence_package_id) == "EVID-0001"
    assert snapshot.reviewer_reference == "reviewer-alpha"

    # Independent verification via direct SQL, bypassing the repository
    # read path entirely.
    engine = sa.create_engine(_config().sqlalchemy_url())
    with engine.connect() as conn:
        review_row = (
            conn.execute(
                text(
                    "SELECT lifecycle_state, disposition, final_disposition_rationale, version "
                    "FROM review WHERE governance_id = :g"
                ),
                {"g": "REVIEW-0001"},
            )
            .mappings()
            .one()
        )
        finding_rows = (
            conn.execute(
                text(
                    "SELECT sequence, text FROM review_finding "
                    "WHERE review_runtime_id = :r ORDER BY sequence"
                ),
                {"r": review_runtime_id},
            )
            .mappings()
            .all()
        )
    engine.dispose()

    assert review_row["lifecycle_state"] == "COMPLETED"
    assert review_row["disposition"] == "ACCEPTED"
    assert review_row["final_disposition_rationale"] == "Evidence is complete and consistent."
    assert review_row["version"] == 4
    assert [(r["sequence"], r["text"]) for r in finding_rows] == [
        (1, "Criterion coverage looks complete."),
        (2, "No missing artifact references observed."),
    ]


def test_cancel_review_alternate_terminal_path(clean_tables: Engine) -> None:
    """Proves the Review aggregate's own complete alternate terminal
    lifecycle path -- cancellation from ASSIGNED -- genuinely persists,
    independently verified via direct SQL."""
    _seal_a_real_evidence_package(
        suffix="2", campaign_id="CAMP-0002", run_id="RUN-0002", ep_id="EVID-0002"
    )
    review_identity = run_create_review(
        review_governance_id="REVIEW-0002",
        target_evidence_package_governance_id="EVID-0002",
        reviewer_reference="reviewer-beta",
        identifier_generator=DeterministicRuntimeIdentifierGenerator(
            ["40000000-0000-4000-8000-000000000002"]
        ),
        config=_config(),
    )
    review_runtime_id = str(review_identity.runtime_id)

    cancel_result = run_cancel_review(
        review_governance_id="REVIEW-0002",
        review_runtime_id=review_runtime_id,
        expected_persisted_version=0,
        reason="Evidence package requires re-collection before review.",
        actor="reviewer-beta",
        occurred_at=datetime(2026, 8, 8, 11, 0, 0, tzinfo=UTC),
        config=_config(),
    )
    assert cancel_result.persisted_version.value == 1

    engine = sa.create_engine(_config().sqlalchemy_url())
    with engine.connect() as conn:
        row = (
            conn.execute(
                text(
                    "SELECT lifecycle_state, cancellation_reason FROM review "
                    "WHERE governance_id = :g"
                ),
                {"g": "REVIEW-0002"},
            )
            .mappings()
            .one()
        )
    engine.dispose()

    assert row["lifecycle_state"] == "CANCELLED"
    assert row["cancellation_reason"] == "Evidence package requires re-collection before review."


def test_complete_without_any_finding_raises_value_error(clean_tables: Engine) -> None:
    """New failure mode this slice's composition genuinely exercises: a
    Review cannot complete while IN_PROGRESS with zero recorded findings."""
    _seal_a_real_evidence_package(
        suffix="3", campaign_id="CAMP-0003", run_id="RUN-0003", ep_id="EVID-0003"
    )
    review_identity = run_create_review(
        review_governance_id="REVIEW-0003",
        target_evidence_package_governance_id="EVID-0003",
        reviewer_reference="reviewer-gamma",
        identifier_generator=DeterministicRuntimeIdentifierGenerator(
            ["40000000-0000-4000-8000-000000000003"]
        ),
        config=_config(),
    )
    review_runtime_id = str(review_identity.runtime_id)
    run_start_review(
        review_governance_id="REVIEW-0003",
        review_runtime_id=review_runtime_id,
        expected_persisted_version=0,
        actor="reviewer-gamma",
        occurred_at=datetime(2026, 8, 8, 11, 0, 0, tzinfo=UTC),
        config=_config(),
    )

    with pytest.raises(ValueError, match="at least one finding"):
        run_complete_review(
            review_governance_id="REVIEW-0003",
            review_runtime_id=review_runtime_id,
            expected_persisted_version=1,
            disposition=ReviewDisposition.ACCEPTED,
            final_disposition_rationale="Should never persist.",
            actor="reviewer-gamma",
            occurred_at=datetime(2026, 8, 8, 11, 5, 0, tzinfo=UTC),
            config=_config(),
        )


def test_add_finding_before_review_started_raises_value_error(clean_tables: Engine) -> None:
    """New failure mode this slice's composition genuinely exercises: a
    finding cannot be added to a Review that is still ASSIGNED (never
    started)."""
    _seal_a_real_evidence_package(
        suffix="4", campaign_id="CAMP-0004", run_id="RUN-0004", ep_id="EVID-0004"
    )
    review_identity = run_create_review(
        review_governance_id="REVIEW-0004",
        target_evidence_package_governance_id="EVID-0004",
        reviewer_reference="reviewer-delta",
        identifier_generator=DeterministicRuntimeIdentifierGenerator(
            ["40000000-0000-4000-8000-000000000004"]
        ),
        config=_config(),
    )
    review_runtime_id = str(review_identity.runtime_id)

    with pytest.raises(ValueError, match="only while IN_PROGRESS"):
        run_add_review_finding(
            review_governance_id="REVIEW-0004",
            review_runtime_id=review_runtime_id,
            expected_persisted_version=0,
            text="Should never persist.",
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

    _seal_a_real_evidence_package(
        suffix="5", campaign_id="CAMP-0005", run_id="RUN-0005", ep_id="EVID-0005"
    )
    review_identity = run_create_review(
        review_governance_id="REVIEW-0005",
        target_evidence_package_governance_id="EVID-0005",
        reviewer_reference="reviewer-epsilon",
        identifier_generator=DeterministicRuntimeIdentifierGenerator(
            ["40000000-0000-4000-8000-000000000005"]
        ),
    )

    assert str(review_identity.governance_id) == "REVIEW-0005"
