"""MILESTONE-023 real-PostgreSQL integration tests for the four repository adapters.

Exercises `PostgresCampaignRepository`, `PostgresRunRepository`,
`PostgresEvidencePackageRepository`, and `PostgresReviewRepository` against a
real, migrated PostgreSQL database (never mocked), covering: get/add/save
across all four aggregates, full-identity predicates, deterministic child
ordering, atomic child-collection replacement, optimistic concurrency
(equal/greater/lower/stale version), duplicate detection, commit-before-return,
and rollback-on-failure leaving no partial state.

Opt-in via ``EMPIRICAL_PLATFORM_RUN_POSTGRES_TESTS=1``, following the same
convention as ``tests/integration/test_m022_schema_migration.py``.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from pydantic import SecretStr
from sqlalchemy import text
from sqlalchemy.engine import Engine

from empirical_platform.campaign.aggregate import Campaign, CampaignScopeStatement
from empirical_platform.datasets import DatasetManifest
from empirical_platform.evidence.package import ArtifactReference, EvidencePackage
from empirical_platform.evidence.results import CriterionResult
from empirical_platform.identifiers.pairs import DomainIdentity
from empirical_platform.identifiers.types import (
    CampaignId,
    EvidencePackageId,
    ReviewId,
    RunId,
)
from empirical_platform.review.aggregate import Review, ReviewerReference, ReviewTargetReference
from empirical_platform.review.lifecycle import ReviewDisposition, ReviewLifecycleState
from empirical_platform.run.aggregate import Run
from empirical_platform.run.mapper import ConcreteRunMapper, DatasetManifestDurableRecord
from empirical_platform.shared.config.settings import PostgreSQLConfigSnapshot
from empirical_platform.shared.contracts.repository import (
    AggregateAlreadyExists,
    AggregateNotFound,
    InvalidAggregateForPersistence,
    InvalidPersistedAggregateState,
    OptimisticConcurrencyConflict,
    SaveOperation,
)
from empirical_platform.shared.domain.versioning import AggregateVersion
from empirical_platform.shared.errors import FoundationError
from empirical_platform.shared.identifiers import RuntimeIdentifier
from empirical_platform.shared.persistence.postgres import PostgresPersistenceService
from empirical_platform.shared.persistence.postgres_repositories.campaign_repository import (
    PostgresCampaignRepository,
)
from empirical_platform.shared.persistence.postgres_repositories.evidence_package_repository import (  # noqa: E501
    PostgresEvidencePackageRepository,
)
from empirical_platform.shared.persistence.postgres_repositories.review_repository import (
    PostgresReviewRepository,
)
from empirical_platform.shared.persistence.postgres_repositories.run_repository import (
    PostgresRunRepository,
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

OCCURRED_AT = datetime(2026, 7, 26, tzinfo=UTC)


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
        application_name="empirical-platform-m023-test",
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
def campaign_repo(service: PostgresPersistenceService) -> PostgresCampaignRepository:
    return PostgresCampaignRepository(service)


@pytest.fixture
def run_repo(service: PostgresPersistenceService) -> PostgresRunRepository:
    return PostgresRunRepository(service)


@pytest.fixture
def evidence_repo(service: PostgresPersistenceService) -> PostgresEvidencePackageRepository:
    return PostgresEvidencePackageRepository(service)


@pytest.fixture
def review_repo(service: PostgresPersistenceService) -> PostgresReviewRepository:
    return PostgresReviewRepository(service)


@pytest.fixture
def seeded_parents(
    campaign_repo: PostgresCampaignRepository,
    run_repo: PostgresRunRepository,
    evidence_repo: PostgresEvidencePackageRepository,
) -> dict[str, DomainIdentity[Any]]:
    """Seed CAMP-0001 -> RUN-0001 -> EVID-0001 via the real repositories."""
    campaign_identity = DomainIdentity(
        governance_id=CampaignId("CAMP-0001"), runtime_id=_runtime_id()
    )
    campaign_repo.add(
        Campaign(identity=campaign_identity, scope_statement=CampaignScopeStatement("scope"))
    )
    run_identity = DomainIdentity(governance_id=RunId("RUN-0001"), runtime_id=_runtime_id())
    run_repo.add(Run(identity=run_identity, campaign_id=CampaignId("CAMP-0001")))
    evidence_identity = DomainIdentity(
        governance_id=EvidencePackageId("EVID-0001"), runtime_id=_runtime_id()
    )
    evidence_repo.add(EvidencePackage(identity=evidence_identity, run_id=RunId("RUN-0001")))
    return {
        "campaign": campaign_identity,
        "run": run_identity,
        "evidence_package": evidence_identity,
    }


# --- Campaign: get/add/save full matrix ---------------------------------------


def test_campaign_get_returns_authoritative_version_and_state(
    campaign_repo: PostgresCampaignRepository,
) -> None:
    identity = DomainIdentity(governance_id=CampaignId("CAMP-0001"), runtime_id=_runtime_id())
    campaign_repo.add(Campaign(identity=identity, scope_statement=CampaignScopeStatement("scope")))

    loaded = campaign_repo.get(identity)

    assert loaded.persisted_version == AggregateVersion(0)
    assert loaded.aggregate.identity == identity
    assert str(loaded.aggregate.scope_statement) == "scope"


def test_campaign_get_missing_identity_raises_not_found(
    campaign_repo: PostgresCampaignRepository,
) -> None:
    identity = DomainIdentity(governance_id=CampaignId("CAMP-9999"), runtime_id=_runtime_id())
    with pytest.raises(AggregateNotFound):
        campaign_repo.get(identity)


def test_campaign_get_mismatched_governance_id_raises_invalid_persisted_state(
    campaign_repo: PostgresCampaignRepository,
) -> None:
    identity = DomainIdentity(governance_id=CampaignId("CAMP-0001"), runtime_id=_runtime_id())
    campaign_repo.add(Campaign(identity=identity, scope_statement=CampaignScopeStatement("scope")))

    wrong_identity = DomainIdentity(
        governance_id=CampaignId("CAMP-0002"), runtime_id=identity.runtime_id
    )
    with pytest.raises(InvalidPersistedAggregateState):
        campaign_repo.get(wrong_identity)


def test_campaign_add_commits_before_return_and_is_visible_from_new_connection(
    campaign_repo: PostgresCampaignRepository, service: PostgresPersistenceService
) -> None:
    identity = DomainIdentity(governance_id=CampaignId("CAMP-0001"), runtime_id=_runtime_id())
    result = campaign_repo.add(
        Campaign(identity=identity, scope_statement=CampaignScopeStatement("scope"))
    )
    assert result.operation is SaveOperation.CREATED
    assert result.persisted_version == AggregateVersion(0)

    other_service = PostgresPersistenceService(_config())
    other_service.initialize()
    try:
        other_repo = PostgresCampaignRepository(other_service)
        loaded = other_repo.get(identity)
        assert loaded.aggregate.identity == identity
    finally:
        other_service.close()


def test_campaign_add_duplicate_runtime_id_raises_already_exists(
    campaign_repo: PostgresCampaignRepository,
) -> None:
    identity = DomainIdentity(governance_id=CampaignId("CAMP-0001"), runtime_id=_runtime_id())
    campaign_repo.add(Campaign(identity=identity, scope_statement=CampaignScopeStatement("a")))

    duplicate_identity = DomainIdentity(
        governance_id=CampaignId("CAMP-0002"), runtime_id=identity.runtime_id
    )
    with pytest.raises(AggregateAlreadyExists):
        campaign_repo.add(
            Campaign(identity=duplicate_identity, scope_statement=CampaignScopeStatement("b"))
        )


def test_campaign_add_duplicate_governance_id_raises_already_exists(
    campaign_repo: PostgresCampaignRepository,
) -> None:
    identity = DomainIdentity(governance_id=CampaignId("CAMP-0001"), runtime_id=_runtime_id())
    campaign_repo.add(Campaign(identity=identity, scope_statement=CampaignScopeStatement("a")))

    duplicate_identity = DomainIdentity(
        governance_id=CampaignId("CAMP-0001"), runtime_id=_runtime_id()
    )
    with pytest.raises(AggregateAlreadyExists):
        campaign_repo.add(
            Campaign(identity=duplicate_identity, scope_statement=CampaignScopeStatement("b"))
        )


def test_campaign_save_lower_version_rejected_opens_no_transaction_and_executes_no_sql(
    campaign_repo: PostgresCampaignRepository,
    service: PostgresPersistenceService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    identity = DomainIdentity(governance_id=CampaignId("CAMP-0001"), runtime_id=_runtime_id())
    campaign = Campaign(identity=identity, scope_statement=CampaignScopeStatement("scope"))
    campaign_repo.add(campaign)

    unit_of_work_call_count = 0
    original_unit_of_work = service.unit_of_work

    def _counting_unit_of_work() -> object:
        nonlocal unit_of_work_call_count
        unit_of_work_call_count += 1
        return original_unit_of_work()

    monkeypatch.setattr(service, "unit_of_work", _counting_unit_of_work)

    with pytest.raises(InvalidAggregateForPersistence):
        campaign_repo.save(campaign, expected_persisted_version=AggregateVersion(5))

    assert unit_of_work_call_count == 0

    reloaded = campaign_repo.get(identity)
    assert reloaded.persisted_version == AggregateVersion(0)


def test_campaign_save_equal_version_returns_unchanged_after_commit(
    campaign_repo: PostgresCampaignRepository,
) -> None:
    identity = DomainIdentity(governance_id=CampaignId("CAMP-0001"), runtime_id=_runtime_id())
    campaign = Campaign(identity=identity, scope_statement=CampaignScopeStatement("scope"))
    campaign_repo.add(campaign)
    loaded = campaign_repo.get(identity)

    result = campaign_repo.save(
        loaded.aggregate, expected_persisted_version=loaded.persisted_version
    )

    assert result.operation is SaveOperation.UNCHANGED
    assert result.persisted_version == AggregateVersion(0)


def test_campaign_save_greater_version_returns_updated_with_exact_persisted_version(
    campaign_repo: PostgresCampaignRepository,
) -> None:
    identity = DomainIdentity(governance_id=CampaignId("CAMP-0001"), runtime_id=_runtime_id())
    campaign = Campaign(identity=identity, scope_statement=CampaignScopeStatement("scope"))
    campaign_repo.add(campaign)
    loaded = campaign_repo.get(identity)
    aggregate = loaded.aggregate
    aggregate.prepare_for_authorization(actor="tester", occurred_at=OCCURRED_AT)

    result = campaign_repo.save(aggregate, expected_persisted_version=loaded.persisted_version)

    assert result.operation is SaveOperation.UPDATED
    assert result.persisted_version == aggregate.version
    reloaded = campaign_repo.get(identity)
    assert reloaded.aggregate.state == aggregate.state
    assert len(reloaded.aggregate.transition_history) == 1


def test_campaign_save_stale_version_raises_optimistic_concurrency_conflict(
    campaign_repo: PostgresCampaignRepository,
) -> None:
    identity = DomainIdentity(governance_id=CampaignId("CAMP-0001"), runtime_id=_runtime_id())
    campaign = Campaign(identity=identity, scope_statement=CampaignScopeStatement("scope"))
    campaign_repo.add(campaign)
    loaded = campaign_repo.get(identity)
    aggregate = loaded.aggregate
    aggregate.prepare_for_authorization(actor="tester", occurred_at=OCCURRED_AT)
    campaign_repo.save(aggregate, expected_persisted_version=loaded.persisted_version)

    aggregate.record_authorization(reason="ok", actor="tester", occurred_at=OCCURRED_AT)
    with pytest.raises(OptimisticConcurrencyConflict) as excinfo:
        campaign_repo.save(aggregate, expected_persisted_version=AggregateVersion(0))

    assert excinfo.value.actual_persisted_version == AggregateVersion(1)


def test_campaign_save_missing_aggregate_raises_not_found(
    campaign_repo: PostgresCampaignRepository,
) -> None:
    identity = DomainIdentity(governance_id=CampaignId("CAMP-9999"), runtime_id=_runtime_id())
    campaign = Campaign(identity=identity, scope_statement=CampaignScopeStatement("scope"))
    with pytest.raises(AggregateNotFound):
        campaign_repo.save(campaign, expected_persisted_version=AggregateVersion(0))


def test_campaign_save_identity_mismatch_raises_invalid_persisted_state(
    campaign_repo: PostgresCampaignRepository,
) -> None:
    identity = DomainIdentity(governance_id=CampaignId("CAMP-0001"), runtime_id=_runtime_id())
    campaign_repo.add(Campaign(identity=identity, scope_statement=CampaignScopeStatement("scope")))

    mismatched = Campaign(
        identity=DomainIdentity(
            governance_id=CampaignId("CAMP-0002"), runtime_id=identity.runtime_id
        ),
        scope_statement=CampaignScopeStatement("scope"),
    )
    with pytest.raises(InvalidPersistedAggregateState):
        campaign_repo.save(mismatched, expected_persisted_version=AggregateVersion(0))


def test_campaign_concurrent_saves_only_one_succeeds(
    campaign_repo: PostgresCampaignRepository,
) -> None:
    identity = DomainIdentity(governance_id=CampaignId("CAMP-0001"), runtime_id=_runtime_id())
    campaign_repo.add(Campaign(identity=identity, scope_statement=CampaignScopeStatement("scope")))

    first_view = campaign_repo.get(identity).aggregate
    second_view = campaign_repo.get(identity).aggregate
    first_view.prepare_for_authorization(actor="tester-a", occurred_at=OCCURRED_AT)
    second_view.prepare_for_authorization(actor="tester-b", occurred_at=OCCURRED_AT)

    first_result = campaign_repo.save(first_view, expected_persisted_version=AggregateVersion(0))
    assert first_result.operation is SaveOperation.UPDATED

    with pytest.raises(OptimisticConcurrencyConflict):
        campaign_repo.save(second_view, expected_persisted_version=AggregateVersion(0))


def test_campaign_repository_never_increments_version_beyond_aggregate(
    campaign_repo: PostgresCampaignRepository,
) -> None:
    identity = DomainIdentity(governance_id=CampaignId("CAMP-0001"), runtime_id=_runtime_id())
    campaign = Campaign(identity=identity, scope_statement=CampaignScopeStatement("scope"))
    campaign_repo.add(campaign)
    loaded = campaign_repo.get(identity)

    result = campaign_repo.save(
        loaded.aggregate, expected_persisted_version=loaded.persisted_version
    )

    assert result.persisted_version == loaded.aggregate.version
    assert result.operation is SaveOperation.UNCHANGED


# --- Run: children ordering, atomic replacement, rollback ---------------------


def test_run_get_reconstructs_manifests_in_deterministic_position_order(
    run_repo: PostgresRunRepository, seeded_parents: dict[str, DomainIdentity[Any]]
) -> None:
    identity = DomainIdentity(governance_id=RunId("RUN-0002"), runtime_id=_runtime_id())
    run = Run(identity=identity, campaign_id=CampaignId("CAMP-0001"))
    run.authorize(actor="tester", occurred_at=OCCURRED_AT)
    run.start_acquisition(actor="tester", occurred_at=OCCURRED_AT)
    run.append_manifest(
        DatasetManifest(run_id=RunId("RUN-0002"), recorded_at=OCCURRED_AT, source="first")
    )
    run.append_manifest(
        DatasetManifest(run_id=RunId("RUN-0002"), recorded_at=OCCURRED_AT, source="second")
    )
    run.append_manifest(
        DatasetManifest(run_id=RunId("RUN-0002"), recorded_at=OCCURRED_AT, source="third")
    )
    run_repo.add(run)

    loaded = run_repo.get(identity)

    assert [m.source for m in loaded.aggregate.manifests] == ["first", "second", "third"]


def test_run_add_persists_root_and_children_atomically(
    run_repo: PostgresRunRepository, seeded_parents: dict[str, DomainIdentity[Any]]
) -> None:
    identity = DomainIdentity(governance_id=RunId("RUN-0002"), runtime_id=_runtime_id())
    run = Run(identity=identity, campaign_id=CampaignId("CAMP-0001"))
    run.authorize(actor="tester", occurred_at=OCCURRED_AT)
    run.append_manifest(
        DatasetManifest(run_id=RunId("RUN-0002"), recorded_at=OCCURRED_AT, source="acquired")
    )

    result = run_repo.add(run)

    assert result.operation is SaveOperation.CREATED
    loaded = run_repo.get(identity)
    assert len(loaded.aggregate.manifests) == 1
    assert len(loaded.aggregate.transition_history) == 1


def test_run_save_updated_replaces_manifests_atomically(
    run_repo: PostgresRunRepository, seeded_parents: dict[str, DomainIdentity[Any]]
) -> None:
    identity = DomainIdentity(governance_id=RunId("RUN-0002"), runtime_id=_runtime_id())
    run = Run(identity=identity, campaign_id=CampaignId("CAMP-0001"))
    run.append_manifest(
        DatasetManifest(run_id=RunId("RUN-0002"), recorded_at=OCCURRED_AT, source="old")
    )
    run_repo.add(run)
    loaded = run_repo.get(identity)
    aggregate = loaded.aggregate
    aggregate.authorize(actor="tester", occurred_at=OCCURRED_AT)
    aggregate.append_manifest(
        DatasetManifest(run_id=RunId("RUN-0002"), recorded_at=OCCURRED_AT, source="new")
    )

    result = run_repo.save(aggregate, expected_persisted_version=loaded.persisted_version)
    assert result.operation is SaveOperation.UPDATED

    reloaded = run_repo.get(identity)
    assert [m.source for m in reloaded.aggregate.manifests] == ["old", "new"]


def test_run_save_unchanged_does_not_rewrite_manifests(
    run_repo: PostgresRunRepository, seeded_parents: dict[str, DomainIdentity[Any]]
) -> None:
    identity = DomainIdentity(governance_id=RunId("RUN-0002"), runtime_id=_runtime_id())
    run = Run(identity=identity, campaign_id=CampaignId("CAMP-0001"))
    run.append_manifest(
        DatasetManifest(run_id=RunId("RUN-0002"), recorded_at=OCCURRED_AT, source="stable")
    )
    run_repo.add(run)
    loaded = run_repo.get(identity)

    result = run_repo.save(loaded.aggregate, expected_persisted_version=loaded.persisted_version)
    assert result.operation is SaveOperation.UNCHANGED

    reloaded = run_repo.get(identity)
    assert [m.source for m in reloaded.aggregate.manifests] == ["stable"]


class _DuplicatingManifestMapper:
    """Test-only mapper wrapper that duplicates the first manifest row.

    Both the `Run` aggregate's own `append_manifest` and the internal
    `_reconstruct_run` factory already reject a duplicate `manifest_id` in
    memory, so that state is not reachable through normal aggregate usage.
    This wrapper injects the duplicate only at the mapper boundary (via the
    repository's documented `mapper=` constructor seam) to reach the real
    `ix_run_manifest_manifest_id_partial_unique` DB constraint directly,
    proving the repository's `save()` rolls back the whole transaction --
    root update included -- when a child-row insert fails.
    """

    def __init__(self, real_mapper: ConcreteRunMapper) -> None:
        self._real = real_mapper

    def to_durable_record(self, aggregate: Run) -> object:
        record = self._real.to_durable_record(aggregate)
        duplicate = DatasetManifestDurableRecord(
            run_id=record.identity.governance_id,
            recorded_at=OCCURRED_AT,
            source="poisoned",
            acquisition_method=None,
            normalization_method=None,
            manifest_id="DATASET-0001",
            notes=(),
        )
        return type(record)(
            identity=record.identity,
            campaign_id=record.campaign_id,
            lifecycle_state=record.lifecycle_state,
            manifests=(duplicate, duplicate),
            version=record.version,
            next_transition_sequence=record.next_transition_sequence,
            transition_history=record.transition_history,
        )

    def from_durable_record(self, record: object) -> object:
        return self._real.from_durable_record(record)  # type: ignore[arg-type]


def test_run_child_write_failure_rolls_back_root_update(
    service: PostgresPersistenceService, seeded_parents: dict[str, DomainIdentity[Any]]
) -> None:
    """A child-row DB constraint violation must roll back the whole save, root included."""
    real_repo = PostgresRunRepository(service)
    identity = DomainIdentity(governance_id=RunId("RUN-0002"), runtime_id=_runtime_id())
    run = Run(identity=identity, campaign_id=CampaignId("CAMP-0001"))
    real_repo.add(run)
    loaded = real_repo.get(identity)
    aggregate = loaded.aggregate
    aggregate.authorize(actor="tester", occurred_at=OCCURRED_AT)

    poisoned_repo = PostgresRunRepository(
        service,
        mapper=_DuplicatingManifestMapper(ConcreteRunMapper()),  # type: ignore[arg-type]
    )

    with pytest.raises(FoundationError):
        poisoned_repo.save(aggregate, expected_persisted_version=loaded.persisted_version)

    reloaded = real_repo.get(identity)
    assert reloaded.persisted_version == loaded.persisted_version
    assert reloaded.aggregate.manifests == ()


# --- EvidencePackage: two independent child collections -----------------------


def test_evidence_package_get_reconstructs_both_child_collections_independently_ordered(
    evidence_repo: PostgresEvidencePackageRepository, seeded_parents: dict[str, DomainIdentity[Any]]
) -> None:
    identity = DomainIdentity(
        governance_id=EvidencePackageId("EVID-0002"), runtime_id=_runtime_id()
    )
    package = EvidencePackage(identity=identity, run_id=RunId("RUN-0001"))
    package.start_collection(actor="tester", occurred_at=OCCURRED_AT)
    package.add_criterion_result(
        CriterionResult(
            evidence_package_id=EvidencePackageId("EVID-0002"),
            criterion_id="crit-a",
            recorded_at=OCCURRED_AT,
            result_label="PASS",
        )
    )
    package.add_criterion_result(
        CriterionResult(
            evidence_package_id=EvidencePackageId("EVID-0002"),
            criterion_id="crit-b",
            recorded_at=OCCURRED_AT,
            result_label="FAIL",
        )
    )
    package.add_artifact_reference(ArtifactReference("artifact-x"))
    package.add_artifact_reference(ArtifactReference("artifact-y"))
    evidence_repo.add(package)

    loaded = evidence_repo.get(identity)

    assert [c.criterion_id for c in loaded.aggregate.criterion_results] == ["crit-a", "crit-b"]
    assert [str(a) for a in loaded.aggregate.artifact_references] == ["artifact-x", "artifact-y"]


def test_evidence_package_save_updated_replaces_both_child_collections_atomically(
    evidence_repo: PostgresEvidencePackageRepository, seeded_parents: dict[str, DomainIdentity[Any]]
) -> None:
    identity = DomainIdentity(
        governance_id=EvidencePackageId("EVID-0002"), runtime_id=_runtime_id()
    )
    package = EvidencePackage(identity=identity, run_id=RunId("RUN-0001"))
    package.start_collection(actor="tester", occurred_at=OCCURRED_AT)
    package.add_criterion_result(
        CriterionResult(
            evidence_package_id=EvidencePackageId("EVID-0002"),
            criterion_id="crit-old",
            recorded_at=OCCURRED_AT,
            result_label="PASS",
        )
    )
    package.add_artifact_reference(ArtifactReference("artifact-old"))
    evidence_repo.add(package)
    loaded = evidence_repo.get(identity)
    aggregate = loaded.aggregate
    aggregate.add_criterion_result(
        CriterionResult(
            evidence_package_id=EvidencePackageId("EVID-0002"),
            criterion_id="crit-new",
            recorded_at=OCCURRED_AT,
            result_label="FAIL",
        )
    )
    aggregate.add_artifact_reference(ArtifactReference("artifact-new"))

    result = evidence_repo.save(aggregate, expected_persisted_version=loaded.persisted_version)
    assert result.operation is SaveOperation.UPDATED

    reloaded = evidence_repo.get(identity)
    assert [c.criterion_id for c in reloaded.aggregate.criterion_results] == [
        "crit-old",
        "crit-new",
    ]
    assert [str(a) for a in reloaded.aggregate.artifact_references] == [
        "artifact-old",
        "artifact-new",
    ]


def test_evidence_package_save_stale_version_raises_conflict_with_actual_version(
    evidence_repo: PostgresEvidencePackageRepository, seeded_parents: dict[str, DomainIdentity[Any]]
) -> None:
    identity = DomainIdentity(
        governance_id=EvidencePackageId("EVID-0002"), runtime_id=_runtime_id()
    )
    package = EvidencePackage(identity=identity, run_id=RunId("RUN-0001"))
    evidence_repo.add(package)
    loaded = evidence_repo.get(identity)
    aggregate = loaded.aggregate
    aggregate.start_collection(actor="tester", occurred_at=OCCURRED_AT)
    evidence_repo.save(aggregate, expected_persisted_version=loaded.persisted_version)

    with pytest.raises(OptimisticConcurrencyConflict) as excinfo:
        evidence_repo.save(aggregate, expected_persisted_version=AggregateVersion(0))
    assert excinfo.value.actual_persisted_version == AggregateVersion(1)


# --- Review: findings with own sequence field, nullable disposition -----------


def test_review_get_reconstructs_findings_ordered_by_sequence(
    review_repo: PostgresReviewRepository, seeded_parents: dict[str, DomainIdentity[Any]]
) -> None:
    identity = DomainIdentity(governance_id=ReviewId("REVIEW-0001"), runtime_id=_runtime_id())
    review = Review(
        identity=identity,
        target=ReviewTargetReference(EvidencePackageId("EVID-0001")),
        reviewer=ReviewerReference("reviewer-1"),
    )
    review.start(actor="tester", occurred_at=OCCURRED_AT)
    review.add_finding(text="finding one")
    review.add_finding(text="finding two")
    review.add_finding(text="finding three")
    review_repo.add(review)

    loaded = review_repo.get(identity)

    assert [f.sequence for f in loaded.aggregate.findings] == [1, 2, 3]
    assert [f.text for f in loaded.aggregate.findings] == [
        "finding one",
        "finding two",
        "finding three",
    ]


def test_review_save_persists_disposition_and_final_rationale(
    review_repo: PostgresReviewRepository, seeded_parents: dict[str, DomainIdentity[Any]]
) -> None:
    identity = DomainIdentity(governance_id=ReviewId("REVIEW-0001"), runtime_id=_runtime_id())
    review = Review(
        identity=identity,
        target=ReviewTargetReference(EvidencePackageId("EVID-0001")),
        reviewer=ReviewerReference("reviewer-1"),
    )
    review_repo.add(review)
    loaded = review_repo.get(identity)
    aggregate = loaded.aggregate
    aggregate.start(actor="tester", occurred_at=OCCURRED_AT)
    aggregate.add_finding(text="looks fine")
    aggregate.complete(
        disposition=ReviewDisposition.ACCEPTED,
        final_disposition_rationale="satisfies criteria",
        actor="tester",
        occurred_at=OCCURRED_AT,
    )

    result = review_repo.save(aggregate, expected_persisted_version=loaded.persisted_version)
    assert result.operation is SaveOperation.UPDATED

    reloaded = review_repo.get(identity)
    assert reloaded.aggregate.state is ReviewLifecycleState.COMPLETED
    assert reloaded.aggregate.disposition is ReviewDisposition.ACCEPTED
    assert reloaded.aggregate.final_disposition_rationale == "satisfies criteria"


def test_review_add_duplicate_governance_id_raises_already_exists(
    review_repo: PostgresReviewRepository, seeded_parents: dict[str, DomainIdentity[Any]]
) -> None:
    identity = DomainIdentity(governance_id=ReviewId("REVIEW-0001"), runtime_id=_runtime_id())
    review_repo.add(
        Review(
            identity=identity,
            target=ReviewTargetReference(EvidencePackageId("EVID-0001")),
            reviewer=ReviewerReference("reviewer-1"),
        )
    )

    duplicate_identity = DomainIdentity(
        governance_id=ReviewId("REVIEW-0001"), runtime_id=_runtime_id()
    )
    with pytest.raises(AggregateAlreadyExists):
        review_repo.add(
            Review(
                identity=duplicate_identity,
                target=ReviewTargetReference(EvidencePackageId("EVID-0001")),
                reviewer=ReviewerReference("reviewer-2"),
            )
        )


def test_review_get_missing_raises_not_found(
    review_repo: PostgresReviewRepository,
) -> None:
    identity = DomainIdentity(governance_id=ReviewId("REVIEW-9999"), runtime_id=_runtime_id())
    with pytest.raises(AggregateNotFound):
        review_repo.get(identity)
