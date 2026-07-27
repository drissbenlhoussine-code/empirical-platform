"""MILESTONE-025 real-PostgreSQL integration tests for `PostgresRepositoryRuntime`.

Exercises the runtime composition object against a real, migrated PostgreSQL
database using the actual, frozen M023 repository adapters (never mocked):
standalone get/add/save through all four exposed properties, cross-aggregate
atomic `run_composed` delegated through the runtime, rollback on failure,
independent-root coexistence and independence, post-close behavior, and
cross-root rejection under the existing, unmodified M024 same-service-identity
rule.

Opt-in via ``EMPIRICAL_PLATFORM_RUN_POSTGRES_TESTS=1``, following the same
convention as ``tests/integration/test_m024_postgres_composed_unit_of_work.py``.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from pydantic import SecretStr
from sqlalchemy import text
from sqlalchemy.engine import Engine

from empirical_platform.campaign.aggregate import Campaign, CampaignScopeStatement
from empirical_platform.evidence.package import EvidencePackage
from empirical_platform.identifiers.pairs import DomainIdentity
from empirical_platform.identifiers.types import CampaignId, EvidencePackageId, ReviewId, RunId
from empirical_platform.review.aggregate import Review, ReviewerReference, ReviewTargetReference
from empirical_platform.run.aggregate import Run
from empirical_platform.shared.config.settings import PostgreSQLConfigSnapshot
from empirical_platform.shared.contracts.repository import AggregateNotFound, SaveOperation
from empirical_platform.shared.errors import FoundationError
from empirical_platform.shared.identifiers import RuntimeIdentifier
from empirical_platform.shared.persistence.postgres import PostgresPersistenceService
from empirical_platform.shared.persistence.postgres_repositories.runtime import (
    PostgresRepositoryRuntime,
)

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

OCCURRED_AT = datetime(2026, 7, 27, tzinfo=UTC)


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
        application_name="empirical-platform-m025-test",
    )


def _alembic_config() -> Config:
    cfg = Config(str(_REPO_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(_REPO_ROOT / "migrations"))
    return cfg


def _reset_public_schema(engine: Engine) -> None:
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))


def _runtime_id() -> RuntimeIdentifier:
    return RuntimeIdentifier(str(uuid.uuid4()))


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
    command.upgrade(_alembic_config(), "head")
    yield engine
    _reset_public_schema(engine)


@pytest.fixture
def clean_tables(upgraded_schema: Engine) -> Engine:
    with upgraded_schema.begin() as conn:
        conn.execute(text(f"TRUNCATE {', '.join(_ALL_TABLES)} CASCADE"))  # noqa: S608
    return upgraded_schema


@pytest.fixture
def service(clean_tables: Engine) -> Iterator[PostgresPersistenceService]:
    svc = PostgresPersistenceService(_config())
    svc.initialize()
    try:
        yield svc
    finally:
        svc.close()


@pytest.fixture
def runtime(service: PostgresPersistenceService) -> PostgresRepositoryRuntime:
    return PostgresRepositoryRuntime(service)


# --- Construction and identity, against a real service -------------------------


def test_runtime_construction_from_one_initialized_service(
    service: PostgresPersistenceService,
) -> None:
    runtime = PostgresRepositoryRuntime(service)
    assert runtime.campaigns._service is service
    assert runtime.runs._service is service
    assert runtime.evidence_packages._service is service
    assert runtime.reviews._service is service


# --- Standalone add/get/save through all four exposed properties ---------------


def test_standalone_add_get_through_all_four_repository_properties(
    runtime: PostgresRepositoryRuntime,
) -> None:
    campaign_identity = DomainIdentity(
        governance_id=CampaignId("CAMP-0001"), runtime_id=_runtime_id()
    )
    runtime.campaigns.add(
        Campaign(identity=campaign_identity, scope_statement=CampaignScopeStatement("scope"))
    )
    loaded_campaign = runtime.campaigns.get(campaign_identity)
    assert loaded_campaign.aggregate.identity == campaign_identity

    run_identity = DomainIdentity(governance_id=RunId("RUN-0001"), runtime_id=_runtime_id())
    runtime.runs.add(Run(identity=run_identity, campaign_id=CampaignId("CAMP-0001")))
    loaded_run = runtime.runs.get(run_identity)
    assert loaded_run.aggregate.identity == run_identity

    evidence_identity = DomainIdentity(
        governance_id=EvidencePackageId("EVID-0001"), runtime_id=_runtime_id()
    )
    runtime.evidence_packages.add(
        EvidencePackage(identity=evidence_identity, run_id=RunId("RUN-0001"))
    )
    loaded_evidence = runtime.evidence_packages.get(evidence_identity)
    assert loaded_evidence.aggregate.identity == evidence_identity

    review_identity = DomainIdentity(
        governance_id=ReviewId("REVIEW-0001"), runtime_id=_runtime_id()
    )
    runtime.reviews.add(
        Review(
            identity=review_identity,
            target=ReviewTargetReference(EvidencePackageId("EVID-0001")),
            reviewer=ReviewerReference("reviewer-1"),
        )
    )
    loaded_review = runtime.reviews.get(review_identity)
    assert loaded_review.aggregate.identity == review_identity


# --- Cross-aggregate atomic run_composed, delegated through the runtime --------


def test_runtime_run_composed_commits_two_repositories_atomically(
    runtime: PostgresRepositoryRuntime,
) -> None:
    campaign_identity = DomainIdentity(
        governance_id=CampaignId("CAMP-0001"), runtime_id=_runtime_id()
    )
    run_identity = DomainIdentity(governance_id=RunId("RUN-0001"), runtime_id=_runtime_id())

    def add_campaign() -> object:
        return runtime.campaigns.add(
            Campaign(identity=campaign_identity, scope_statement=CampaignScopeStatement("scope"))
        )

    def add_run() -> object:
        return runtime.runs.add(Run(identity=run_identity, campaign_id=CampaignId("CAMP-0001")))

    results = runtime.run_composed([add_campaign, add_run])

    assert results[0].operation is SaveOperation.CREATED  # type: ignore[attr-defined]
    assert results[1].operation is SaveOperation.CREATED  # type: ignore[attr-defined]
    assert runtime.campaigns.get(campaign_identity).aggregate.identity == campaign_identity
    assert runtime.runs.get(run_identity).aggregate.identity == run_identity


def test_runtime_run_composed_rolls_back_both_repositories_on_failure(
    runtime: PostgresRepositoryRuntime,
) -> None:
    campaign_identity = DomainIdentity(
        governance_id=CampaignId("CAMP-0001"), runtime_id=_runtime_id()
    )
    run_identity = DomainIdentity(governance_id=RunId("RUN-0001"), runtime_id=_runtime_id())

    def add_campaign() -> None:
        runtime.campaigns.add(
            Campaign(identity=campaign_identity, scope_statement=CampaignScopeStatement("scope"))
        )

    def add_run_then_fail() -> None:
        runtime.runs.add(Run(identity=run_identity, campaign_id=CampaignId("CAMP-0001")))
        raise ValueError("deliberate failure after successful run insert")

    with pytest.raises(ValueError, match="deliberate failure"):
        runtime.run_composed([add_campaign, add_run_then_fail])

    with pytest.raises(AggregateNotFound):
        runtime.campaigns.get(campaign_identity)
    with pytest.raises(AggregateNotFound):
        runtime.runs.get(run_identity)


# --- Independent roots -----------------------------------------------------------


def test_two_independent_roots_operate_against_the_same_database_without_interference(
    service: PostgresPersistenceService,
) -> None:
    other_service = PostgresPersistenceService(_config())
    other_service.initialize()
    try:
        runtime_a = PostgresRepositoryRuntime(service)
        runtime_b = PostgresRepositoryRuntime(other_service)

        identity_a = DomainIdentity(governance_id=CampaignId("CAMP-0001"), runtime_id=_runtime_id())
        identity_b = DomainIdentity(governance_id=CampaignId("CAMP-0002"), runtime_id=_runtime_id())

        runtime_a.campaigns.add(
            Campaign(identity=identity_a, scope_statement=CampaignScopeStatement("a"))
        )
        runtime_b.campaigns.add(
            Campaign(identity=identity_b, scope_statement=CampaignScopeStatement("b"))
        )

        # Both roots see both rows -- they share the same underlying database,
        # proving root independence is about service *object* identity, not
        # about the two roots operating on isolated data.
        assert runtime_a.campaigns.get(identity_b).aggregate.identity == identity_b
        assert runtime_b.campaigns.get(identity_a).aggregate.identity == identity_a
    finally:
        other_service.close()


def test_closing_one_root_leaves_a_second_independent_root_operational(
    service: PostgresPersistenceService,
) -> None:
    other_service = PostgresPersistenceService(_config())
    other_service.initialize()
    try:
        runtime_a = PostgresRepositoryRuntime(service)
        runtime_b = PostgresRepositoryRuntime(other_service)

        runtime_a.close()

        with pytest.raises(FoundationError, match="closed"):
            with runtime_a.campaigns._service.unit_of_work():
                pass

        identity = DomainIdentity(governance_id=CampaignId("CAMP-0001"), runtime_id=_runtime_id())
        result = runtime_b.campaigns.add(
            Campaign(identity=identity, scope_statement=CampaignScopeStatement("still-usable"))
        )
        assert result.operation is SaveOperation.CREATED
    finally:
        other_service.close()


def test_cross_root_repositories_rejected_from_one_composed_transaction(
    service: PostgresPersistenceService,
) -> None:
    other_service = PostgresPersistenceService(_config())
    other_service.initialize()
    try:
        runtime_a = PostgresRepositoryRuntime(service)
        runtime_b = PostgresRepositoryRuntime(other_service)

        campaign_identity = DomainIdentity(
            governance_id=CampaignId("CAMP-0001"), runtime_id=_runtime_id()
        )

        def add_on_root_a() -> None:
            runtime_a.campaigns.add(
                Campaign(identity=campaign_identity, scope_statement=CampaignScopeStatement("a"))
            )

        def add_on_root_b() -> None:
            runtime_b.campaigns.add(
                Campaign(
                    identity=DomainIdentity(
                        governance_id=CampaignId("CAMP-0002"), runtime_id=_runtime_id()
                    ),
                    scope_statement=CampaignScopeStatement("b"),
                )
            )

        with pytest.raises(FoundationError, match="Nested persistence units of work"):
            runtime_a.run_composed([add_on_root_a, add_on_root_b])

        with pytest.raises(AggregateNotFound):
            runtime_a.campaigns.get(campaign_identity)
    finally:
        other_service.close()


# --- Post-close behavior ---------------------------------------------------------


def test_repository_operation_after_close_fails_through_existing_guard(
    runtime: PostgresRepositoryRuntime,
) -> None:
    runtime.close()
    identity = DomainIdentity(governance_id=CampaignId("CAMP-0001"), runtime_id=_runtime_id())
    with pytest.raises(FoundationError, match="closed"):
        runtime.campaigns.add(
            Campaign(identity=identity, scope_statement=CampaignScopeStatement("scope"))
        )


def test_run_composed_after_close_fails_through_existing_guard(
    runtime: PostgresRepositoryRuntime,
) -> None:
    runtime.close()
    with pytest.raises(FoundationError, match="closed"):
        runtime.run_composed([lambda: None])
