"""MILESTONE-042 real-PostgreSQL integration tests for `CreateReviewHandler`.

Exercises the full frozen vertical slice against a real, migrated
PostgreSQL database (never mocked): `CommandEntryPoint` -> concrete
`CreateReviewHandler` -> `Review` aggregate -> the real, frozen
`PostgresReviewRepository` -> PostgreSQL. The `ReviewRepository` instance
is obtained externally (this test's own fixtures), exactly as the frozen
design requires -- the `usecases` package itself never imports
persistence. A Campaign, Run, and EvidencePackage are first persisted and
transitioned through to a genuinely `SEALED` state via the existing,
frozen M030/M033/M036/M038/M039/M040/M041 handlers, reusing the identical
fixture-composition pattern `tests/integration/test_m041_seal_evidence_package_usecase.py`
already established -- the real-world-aligned target this milestone's
scope (Section 7) explicitly anticipated.

The missing-target scenario is frozen exactly by the M042 design (Section
11): no application-level `EvidencePackageRepository` lookup exists -- a
nonexistent `target_evidence_package_governance_id` is rejected by the
real database foreign-key constraint
(`review.target_evidence_package_id -> evidence_package.governance_id`,
MILESTONE-022), surfacing as an unmodified `FoundationError` with
`category=FoundationErrorCategory.PERSISTENCE`, never `AggregateNotFound`
or any Review-/EvidencePackage-specific application error.

Opt-in via ``EMPIRICAL_PLATFORM_RUN_POSTGRES_TESTS=1``, following the
same convention as ``tests/integration/test_m023_postgres_repositories.py``.
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

from empirical_platform.application.command import CommandEntryPoint
from empirical_platform.identifiers.pairs import DomainIdentity
from empirical_platform.identifiers.types import EvidencePackageId, ReviewId
from empirical_platform.review.lifecycle import ReviewLifecycleState
from empirical_platform.shared.config.settings import PostgreSQLConfigSnapshot
from empirical_platform.shared.contracts.repository import (
    AggregateAlreadyExists,
    AggregateNotFound,
)
from empirical_platform.shared.domain.versioning import AggregateVersion
from empirical_platform.shared.errors import FoundationError, FoundationErrorCategory
from empirical_platform.shared.identifiers import (
    DeterministicRuntimeIdentifierGenerator,
    RuntimeIdentifier,
)
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
from empirical_platform.usecases.create_campaign import (
    CreateCampaignCommand,
    CreateCampaignHandler,
)
from empirical_platform.usecases.create_evidence_package import (
    CreateEvidencePackageCommand,
    CreateEvidencePackageHandler,
)
from empirical_platform.usecases.create_review import CreateReviewCommand, CreateReviewHandler
from empirical_platform.usecases.create_run import CreateRunCommand, CreateRunHandler
from empirical_platform.usecases.record_evidence_package_artifact_reference import (
    RecordEvidencePackageArtifactReferenceCommand,
    RecordEvidencePackageArtifactReferenceHandler,
)
from empirical_platform.usecases.record_evidence_package_criterion_result import (
    RecordEvidencePackageCriterionResultCommand,
    RecordEvidencePackageCriterionResultHandler,
)
from empirical_platform.usecases.seal_evidence_package import (
    SealEvidencePackageCommand,
    SealEvidencePackageHandler,
)
from empirical_platform.usecases.start_evidence_package_collection import (
    StartEvidencePackageCollectionCommand,
    StartEvidencePackageCollectionHandler,
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
_CAMPAIGN_RUNTIME_ID_VALUE = "12345678-1234-4321-8765-1234567890ab"
_RUN_RUNTIME_ID_VALUE = "22345678-1234-4321-8765-1234567890ab"
_EVIDENCE_RUNTIME_ID_VALUE = "32345678-1234-4321-8765-1234567890ab"
_REVIEW_RUNTIME_ID_VALUE = "42345678-1234-4321-8765-1234567890ab"
_MISSING_RUNTIME_ID_VALUE = "87654321-4321-4321-8765-0987654321ba"
_OCCURRED_AT = datetime(2026, 1, 1, tzinfo=UTC)


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
        application_name="empirical-platform-m042-test",
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
    """The real, frozen M023 CampaignRepository, obtained externally --
    test scaffolding only, seeds a real Campaign row."""
    return PostgresCampaignRepository(service)


@pytest.fixture
def run_repo(service: PostgresPersistenceService) -> PostgresRunRepository:
    """The real, frozen M023 RunRepository, obtained externally -- test
    scaffolding only, seeds a real Run row."""
    return PostgresRunRepository(service)


@pytest.fixture
def evidence_package_repo(
    service: PostgresPersistenceService,
) -> PostgresEvidencePackageRepository:
    """The real, frozen M023 EvidencePackageRepository, obtained externally
    -- test scaffolding only, seeds/transitions a real EvidencePackage row."""
    return PostgresEvidencePackageRepository(service)


@pytest.fixture
def review_repo(service: PostgresPersistenceService) -> PostgresReviewRepository:
    """The real, frozen M023 ReviewRepository, obtained externally --
    exactly as the frozen design requires; `usecases` never constructs
    this itself."""
    return PostgresReviewRepository(service)


def _persist_sealed_evidence_package(
    campaign_repo: PostgresCampaignRepository,
    run_repo: PostgresRunRepository,
    evidence_package_repo: PostgresEvidencePackageRepository,
    *,
    campaign_governance_id: str,
    run_governance_id: str,
    evidence_package_governance_id: str,
    campaign_runtime_id: str = _CAMPAIGN_RUNTIME_ID_VALUE,
    run_runtime_id: str = _RUN_RUNTIME_ID_VALUE,
    evidence_runtime_id: str = _EVIDENCE_RUNTIME_ID_VALUE,
) -> DomainIdentity[EvidencePackageId]:
    """Seeds a genuinely SEALED EvidencePackage -- exclusively via frozen
    application commands (M030, M033, M036, M038, M039, M040, M041) -- the
    real-world-aligned Review target this milestone's scope anticipated."""
    CommandEntryPoint(
        CreateCampaignHandler(
            campaign_repository=campaign_repo,
            runtime_identifier_generator=DeterministicRuntimeIdentifierGenerator(
                [campaign_runtime_id]
            ),
        )
    )(
        CreateCampaignCommand(
            campaign_governance_id=campaign_governance_id,
            scope_statement="seed campaign for M042 tests",
        )
    )

    CommandEntryPoint(
        CreateRunHandler(
            run_repository=run_repo,
            runtime_identifier_generator=DeterministicRuntimeIdentifierGenerator([run_runtime_id]),
        )
    )(
        CreateRunCommand(
            run_governance_id=run_governance_id, campaign_governance_id=campaign_governance_id
        )
    )

    identity = CommandEntryPoint(
        CreateEvidencePackageHandler(
            evidence_package_repository=evidence_package_repo,
            runtime_identifier_generator=DeterministicRuntimeIdentifierGenerator(
                [evidence_runtime_id]
            ),
        )
    )(
        CreateEvidencePackageCommand(
            evidence_package_governance_id=evidence_package_governance_id,
            run_governance_id=run_governance_id,
        )
    )

    CommandEntryPoint(
        StartEvidencePackageCollectionHandler(evidence_package_repository=evidence_package_repo)
    )(
        StartEvidencePackageCollectionCommand(
            identity=identity,
            expected_persisted_version=AggregateVersion.initial(),
            actor="tester",
            occurred_at=_OCCURRED_AT,
        )
    )

    CommandEntryPoint(
        RecordEvidencePackageCriterionResultHandler(
            evidence_package_repository=evidence_package_repo
        )
    )(
        RecordEvidencePackageCriterionResultCommand(
            identity=identity,
            expected_persisted_version=AggregateVersion(1),
            criterion_id="CRIT-001",
            recorded_at=_OCCURRED_AT,
            result_label="PASS",
        )
    )

    CommandEntryPoint(
        RecordEvidencePackageArtifactReferenceHandler(
            evidence_package_repository=evidence_package_repo
        )
    )(
        RecordEvidencePackageArtifactReferenceCommand(
            identity=identity,
            expected_persisted_version=AggregateVersion(2),
            value="s3://bucket/artifact-1",
        )
    )

    CommandEntryPoint(
        SealEvidencePackageHandler(evidence_package_repository=evidence_package_repo)
    )(
        SealEvidencePackageCommand(
            identity=identity,
            expected_persisted_version=AggregateVersion(3),
            actor="tester",
            occurred_at=_OCCURRED_AT,
        )
    )

    return identity


def test_golden_path_persists_via_command_entry_point_and_real_repository(
    campaign_repo: PostgresCampaignRepository,
    run_repo: PostgresRunRepository,
    evidence_package_repo: PostgresEvidencePackageRepository,
    review_repo: PostgresReviewRepository,
) -> None:
    target_identity = _persist_sealed_evidence_package(
        campaign_repo,
        run_repo,
        evidence_package_repo,
        campaign_governance_id="CAMP-0001",
        run_governance_id="RUN-0001",
        evidence_package_governance_id="EVID-0001",
    )

    handler = CreateReviewHandler(
        review_repository=review_repo,
        runtime_identifier_generator=DeterministicRuntimeIdentifierGenerator(
            [_REVIEW_RUNTIME_ID_VALUE]
        ),
    )
    entry_point = CommandEntryPoint(handler)
    command = CreateReviewCommand(
        review_governance_id="REVIEW-0001",
        target_evidence_package_governance_id="EVID-0001",
        reviewer_reference="reviewer-alice",
    )

    result = entry_point(command)

    assert result.governance_id == ReviewId("REVIEW-0001")
    assert str(result.runtime_id) == _REVIEW_RUNTIME_ID_VALUE

    loaded = review_repo.get(result)
    assert loaded.aggregate.identity == result
    assert loaded.aggregate.target.evidence_package_id == target_identity.governance_id
    assert str(loaded.aggregate.reviewer) == "reviewer-alice"
    assert loaded.aggregate.state is ReviewLifecycleState.ASSIGNED
    assert loaded.persisted_version == AggregateVersion.initial()
    assert loaded.aggregate.findings == ()
    assert loaded.aggregate.disposition is None
    assert loaded.aggregate.transition_history == ()


def test_duplicate_review_governance_id_raises_aggregate_already_exists(
    campaign_repo: PostgresCampaignRepository,
    run_repo: PostgresRunRepository,
    evidence_package_repo: PostgresEvidencePackageRepository,
    review_repo: PostgresReviewRepository,
) -> None:
    _persist_sealed_evidence_package(
        campaign_repo,
        run_repo,
        evidence_package_repo,
        campaign_governance_id="CAMP-0001",
        run_governance_id="RUN-0001",
        evidence_package_governance_id="EVID-0001",
    )

    generator = DeterministicRuntimeIdentifierGenerator(
        [_REVIEW_RUNTIME_ID_VALUE, "52345678-1234-4321-8765-1234567890ab"]
    )
    handler = CreateReviewHandler(
        review_repository=review_repo, runtime_identifier_generator=generator
    )
    entry_point = CommandEntryPoint(handler)
    command = CreateReviewCommand(
        review_governance_id="REVIEW-0001",
        target_evidence_package_governance_id="EVID-0001",
        reviewer_reference="reviewer-alice",
    )

    entry_point(command)

    with pytest.raises(AggregateAlreadyExists):
        entry_point(
            CreateReviewCommand(
                review_governance_id="REVIEW-0001",
                target_evidence_package_governance_id="EVID-0001",
                reviewer_reference="reviewer-bob",
            )
        )


def test_duplicate_runtime_id_raises_aggregate_already_exists(
    campaign_repo: PostgresCampaignRepository,
    run_repo: PostgresRunRepository,
    evidence_package_repo: PostgresEvidencePackageRepository,
    review_repo: PostgresReviewRepository,
) -> None:
    """Two different Review governance IDs with the same generated runtime
    ID collide on the real `pk_review` primary-key constraint."""
    _persist_sealed_evidence_package(
        campaign_repo,
        run_repo,
        evidence_package_repo,
        campaign_governance_id="CAMP-0001",
        run_governance_id="RUN-0001",
        evidence_package_governance_id="EVID-0001",
    )

    shared_runtime_id = _REVIEW_RUNTIME_ID_VALUE
    generator = DeterministicRuntimeIdentifierGenerator([shared_runtime_id, shared_runtime_id])
    handler = CreateReviewHandler(
        review_repository=review_repo, runtime_identifier_generator=generator
    )
    entry_point = CommandEntryPoint(handler)

    entry_point(
        CreateReviewCommand(
            review_governance_id="REVIEW-0001",
            target_evidence_package_governance_id="EVID-0001",
            reviewer_reference="reviewer-alice",
        )
    )

    with pytest.raises(AggregateAlreadyExists):
        entry_point(
            CreateReviewCommand(
                review_governance_id="REVIEW-0002",
                target_evidence_package_governance_id="EVID-0001",
                reviewer_reference="reviewer-bob",
            )
        )


def test_missing_target_evidence_package_raises_raw_foundation_error_not_translated(
    review_repo: PostgresReviewRepository,
) -> None:
    """No EvidencePackage is seeded; the real `review.target_evidence_package_id
    -> evidence_package.governance_id` foreign key rejects the insert,
    surfacing as an unmodified `FoundationError` (category `PERSISTENCE`)
    -- exactly as the design (Section 11) specifies. Explicitly not
    `AggregateNotFound`, not `AggregateAlreadyExists`, not any
    Review-/EvidencePackage-specific error, and no row is persisted
    despite the failure."""
    handler = CreateReviewHandler(
        review_repository=review_repo,
        runtime_identifier_generator=DeterministicRuntimeIdentifierGenerator(
            [_REVIEW_RUNTIME_ID_VALUE]
        ),
    )
    entry_point = CommandEntryPoint(handler)
    command = CreateReviewCommand(
        review_governance_id="REVIEW-0001",
        target_evidence_package_governance_id="EVID-9999",
        reviewer_reference="reviewer-alice",
    )

    with pytest.raises(FoundationError) as excinfo:
        entry_point(command)

    assert excinfo.value.category is FoundationErrorCategory.PERSISTENCE
    assert not isinstance(excinfo.value, AggregateAlreadyExists)

    attempted_identity = DomainIdentity(
        governance_id=ReviewId("REVIEW-0001"),
        runtime_id=RuntimeIdentifier(_REVIEW_RUNTIME_ID_VALUE),
    )
    with pytest.raises(AggregateNotFound):
        review_repo.get(attempted_identity)


def test_no_production_composition_machinery_is_required(
    campaign_repo: PostgresCampaignRepository,
    run_repo: PostgresRunRepository,
    evidence_package_repo: PostgresEvidencePackageRepository,
    review_repo: PostgresReviewRepository,
) -> None:
    """The handler is constructed directly from the externally-obtained
    repository and a deterministic generator -- no FoundationRuntime, no
    registry, no composition root of any kind."""
    _persist_sealed_evidence_package(
        campaign_repo,
        run_repo,
        evidence_package_repo,
        campaign_governance_id="CAMP-0099",
        run_governance_id="RUN-0099",
        evidence_package_governance_id="EVID-0099",
    )

    handler = CreateReviewHandler(
        review_repository=review_repo,
        runtime_identifier_generator=DeterministicRuntimeIdentifierGenerator(
            [_REVIEW_RUNTIME_ID_VALUE]
        ),
    )
    result = handler.handle(
        CreateReviewCommand(
            review_governance_id="REVIEW-0099",
            target_evidence_package_governance_id="EVID-0099",
            reviewer_reference="reviewer-alice",
        )
    )
    assert result.governance_id == ReviewId("REVIEW-0099")
    assert isinstance(result, DomainIdentity)
