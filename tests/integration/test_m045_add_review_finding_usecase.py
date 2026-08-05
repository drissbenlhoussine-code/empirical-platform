"""MILESTONE-045 real-PostgreSQL integration tests for
`AddReviewFindingHandler`.

Exercises the full frozen vertical slice against a real, migrated
PostgreSQL database (never mocked): `CommandEntryPoint` -> concrete
`AddReviewFindingHandler` -> `Review` aggregate -> the real, frozen
`PostgresReviewRepository` -> PostgreSQL. The `ReviewRepository` instance
is obtained externally (this test's own fixtures), exactly as the frozen
design requires -- the `usecases` package itself never imports
persistence. A Campaign, Run, EvidencePackage, and Review are first
persisted through the existing, frozen M030/M033/M036/M042 handlers, and
the Review is transitioned to IN_PROGRESS through the existing, frozen
M044 `StartReviewHandler`, reusing the identical fixture pattern
`tests/integration/test_m044_start_review_usecase.py` already
established.

The deterministic optimistic-concurrency conflict scenario is frozen
exactly by the M045 design (Section 6, empirically confirmed during
implementation, Section 19): unlike M044's `start()` (which had no
state-preserving interfering write available while ASSIGNED),
`add_finding()` operates on IN_PROGRESS without changing state, so a
second, independently-loaded `add_finding()` call -- itself, not a
different method, since no other state-preserving Review mutation exists
-- serves as the interfering write. The interfering write independently
loads the same identity and calls `Review.add_finding()` directly (never
through `AddReviewFindingHandler`) to advance the persisted version while
preserving IN_PROGRESS, so the command under test can still execute its
own `add_finding()` call before the stale-version `save()` fails. This is
test setup only; the interfering call is never made through any
production command.

Opt-in via ``EMPIRICAL_PLATFORM_RUN_POSTGRES_TESTS=1``, following the same
convention as ``tests/integration/test_m023_postgres_repositories.py``.
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
from empirical_platform.identifiers.types import ReviewId
from empirical_platform.review.lifecycle import ReviewLifecycleState
from empirical_platform.shared.config.settings import PostgreSQLConfigSnapshot
from empirical_platform.shared.contracts.repository import (
    AggregateNotFound,
    OptimisticConcurrencyConflict,
    SaveOperation,
)
from empirical_platform.shared.domain.versioning import AggregateVersion
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
from empirical_platform.usecases.add_review_finding import (
    AddReviewFindingCommand,
    AddReviewFindingHandler,
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
from empirical_platform.usecases.start_review import StartReviewCommand, StartReviewHandler

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
        application_name="empirical-platform-m045-test",
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
    -- test scaffolding only, seeds a real EvidencePackage row."""
    return PostgresEvidencePackageRepository(service)


@pytest.fixture
def review_repo(service: PostgresPersistenceService) -> PostgresReviewRepository:
    """The real, frozen M023 ReviewRepository, obtained externally --
    exactly as the frozen design requires; `usecases` never constructs
    this itself."""
    return PostgresReviewRepository(service)


def _persist_in_progress_review(
    campaign_repo: PostgresCampaignRepository,
    run_repo: PostgresRunRepository,
    evidence_package_repo: PostgresEvidencePackageRepository,
    review_repo: PostgresReviewRepository,
    *,
    campaign_governance_id: str,
    run_governance_id: str,
    evidence_package_governance_id: str,
    review_governance_id: str,
    reviewer_reference: str = "reviewer-1",
    campaign_runtime_id: str = _CAMPAIGN_RUNTIME_ID_VALUE,
    run_runtime_id: str = _RUN_RUNTIME_ID_VALUE,
    evidence_runtime_id: str = _EVIDENCE_RUNTIME_ID_VALUE,
    review_runtime_id: str = _REVIEW_RUNTIME_ID_VALUE,
) -> DomainIdentity[ReviewId]:
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
            scope_statement="seed campaign for M045 tests",
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

    CommandEntryPoint(
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

    identity = CommandEntryPoint(
        CreateReviewHandler(
            review_repository=review_repo,
            runtime_identifier_generator=DeterministicRuntimeIdentifierGenerator(
                [review_runtime_id]
            ),
        )
    )(
        CreateReviewCommand(
            review_governance_id=review_governance_id,
            target_evidence_package_governance_id=evidence_package_governance_id,
            reviewer_reference=reviewer_reference,
        )
    )

    CommandEntryPoint(StartReviewHandler(review_repository=review_repo))(
        StartReviewCommand(
            identity=identity,
            expected_persisted_version=AggregateVersion.initial(),
            actor="tester",
            occurred_at=_OCCURRED_AT,
        )
    )

    return identity


def test_golden_path_adds_finding_via_command_entry_point_and_real_repository(
    campaign_repo: PostgresCampaignRepository,
    run_repo: PostgresRunRepository,
    evidence_package_repo: PostgresEvidencePackageRepository,
    review_repo: PostgresReviewRepository,
) -> None:
    identity = _persist_in_progress_review(
        campaign_repo,
        run_repo,
        evidence_package_repo,
        review_repo,
        campaign_governance_id="CAMP-0001",
        run_governance_id="RUN-0001",
        evidence_package_governance_id="EVID-0001",
        review_governance_id="REVIEW-0001",
    )

    handler = AddReviewFindingHandler(review_repository=review_repo)
    entry_point = CommandEntryPoint(handler)
    command = AddReviewFindingCommand(
        identity=identity,
        expected_persisted_version=AggregateVersion(1),
        text="a real, golden-path finding",
        rationale="clearly documented rationale",
        evidence_references=("s3://bucket/artifact-1",),
    )

    result = entry_point(command)

    assert result.operation is SaveOperation.UPDATED
    assert result.persisted_version == AggregateVersion(2)

    loaded = review_repo.get(identity)
    assert loaded.aggregate.state is ReviewLifecycleState.IN_PROGRESS
    assert loaded.persisted_version == AggregateVersion(2)
    assert len(loaded.aggregate.findings) == 1
    finding = loaded.aggregate.findings[0]
    assert finding.sequence == 1
    assert finding.text == "a real, golden-path finding"
    assert finding.rationale == "clearly documented rationale"
    assert finding.evidence_references == ("s3://bucket/artifact-1",)
    assert len(loaded.aggregate.transition_history) == 1  # only the M044 start() transition


def test_invalid_state_raises_domain_value_error(
    campaign_repo: PostgresCampaignRepository,
    run_repo: PostgresRunRepository,
    evidence_package_repo: PostgresEvidencePackageRepository,
    review_repo: PostgresReviewRepository,
) -> None:
    """A Review still ASSIGNED (never started) rejects add_finding() with a
    domain ValueError, independently reproduced against real PostgreSQL."""
    CommandEntryPoint(
        CreateCampaignHandler(
            campaign_repository=campaign_repo,
            runtime_identifier_generator=DeterministicRuntimeIdentifierGenerator(
                [_CAMPAIGN_RUNTIME_ID_VALUE]
            ),
        )
    )(CreateCampaignCommand(campaign_governance_id="CAMP-0002", scope_statement="seed"))
    CommandEntryPoint(
        CreateRunHandler(
            run_repository=run_repo,
            runtime_identifier_generator=DeterministicRuntimeIdentifierGenerator(
                [_RUN_RUNTIME_ID_VALUE]
            ),
        )
    )(CreateRunCommand(run_governance_id="RUN-0002", campaign_governance_id="CAMP-0002"))
    CommandEntryPoint(
        CreateEvidencePackageHandler(
            evidence_package_repository=evidence_package_repo,
            runtime_identifier_generator=DeterministicRuntimeIdentifierGenerator(
                [_EVIDENCE_RUNTIME_ID_VALUE]
            ),
        )
    )(
        CreateEvidencePackageCommand(
            evidence_package_governance_id="EVID-0002", run_governance_id="RUN-0002"
        )
    )
    identity = CommandEntryPoint(
        CreateReviewHandler(
            review_repository=review_repo,
            runtime_identifier_generator=DeterministicRuntimeIdentifierGenerator(
                [_REVIEW_RUNTIME_ID_VALUE]
            ),
        )
    )(
        CreateReviewCommand(
            review_governance_id="REVIEW-0002",
            target_evidence_package_governance_id="EVID-0002",
            reviewer_reference="reviewer-1",
        )
    )
    # deliberately never started -- still ASSIGNED

    handler = AddReviewFindingHandler(review_repository=review_repo)
    entry_point = CommandEntryPoint(handler)

    with pytest.raises(ValueError, match="may be added only while IN_PROGRESS"):
        entry_point(
            AddReviewFindingCommand(
                identity=identity,
                expected_persisted_version=AggregateVersion.initial(),
                text="should never be persisted",
            )
        )

    loaded = review_repo.get(identity)
    assert loaded.aggregate.state is ReviewLifecycleState.ASSIGNED
    assert loaded.aggregate.findings == ()


def test_missing_full_identity_raises_aggregate_not_found(
    campaign_repo: PostgresCampaignRepository,
    run_repo: PostgresRunRepository,
    evidence_package_repo: PostgresEvidencePackageRepository,
    review_repo: PostgresReviewRepository,
) -> None:
    _persist_in_progress_review(
        campaign_repo,
        run_repo,
        evidence_package_repo,
        review_repo,
        campaign_governance_id="CAMP-0003",
        run_governance_id="RUN-0003",
        evidence_package_governance_id="EVID-0003",
        review_governance_id="REVIEW-0003",
    )
    missing_identity = DomainIdentity(
        governance_id=ReviewId("REVIEW-9999"),
        runtime_id=RuntimeIdentifier(_MISSING_RUNTIME_ID_VALUE),
    )
    handler = AddReviewFindingHandler(review_repository=review_repo)
    entry_point = CommandEntryPoint(handler)

    with pytest.raises(AggregateNotFound):
        entry_point(
            AddReviewFindingCommand(
                identity=missing_identity,
                expected_persisted_version=AggregateVersion.initial(),
                text="should never be persisted",
            )
        )


def test_stale_expected_version_raises_genuine_optimistic_concurrency_conflict(
    campaign_repo: PostgresCampaignRepository,
    run_repo: PostgresRunRepository,
    evidence_package_repo: PostgresEvidencePackageRepository,
    review_repo: PostgresReviewRepository,
) -> None:
    identity = _persist_in_progress_review(
        campaign_repo,
        run_repo,
        evidence_package_repo,
        review_repo,
        campaign_governance_id="CAMP-0004",
        run_governance_id="RUN-0004",
        evidence_package_governance_id="EVID-0004",
        review_governance_id="REVIEW-0004",
    )

    # Simulate an interfering writer: independently reload the same identity
    # and advance the persisted version via add_finding() -- the only
    # existing Review mutation, other than itself, that bumps
    # AggregateVersion without changing lifecycle state, preserving
    # IN_PROGRESS so the command under test can still execute
    # add_finding() afterward. Test setup only; never invoked by any
    # production code.
    interfering = review_repo.get(identity)
    interfering.aggregate.add_finding(text="interfering writer's finding")
    review_repo.save(interfering.aggregate, expected_persisted_version=AggregateVersion(1))

    handler = AddReviewFindingHandler(review_repository=review_repo)
    entry_point = CommandEntryPoint(handler)

    with pytest.raises(OptimisticConcurrencyConflict):
        entry_point(
            AddReviewFindingCommand(
                identity=identity,
                expected_persisted_version=AggregateVersion(1),  # stale: real durable version is 2
                text="command-under-test's finding",
            )
        )

    # The command-under-test's own finding was never persisted -- the
    # interfering writer's finding remains the only durable change beyond
    # the initial start() transition.
    loaded = review_repo.get(identity)
    assert loaded.persisted_version == AggregateVersion(2)
    assert len(loaded.aggregate.findings) == 1
    assert loaded.aggregate.findings[0].text == "interfering writer's finding"


def test_no_production_composition_machinery_is_required(
    campaign_repo: PostgresCampaignRepository,
    run_repo: PostgresRunRepository,
    evidence_package_repo: PostgresEvidencePackageRepository,
    review_repo: PostgresReviewRepository,
) -> None:
    """The handler is constructed directly from the externally-obtained
    repository -- no FoundationRuntime, no registry, no composition root
    of any kind."""
    identity = _persist_in_progress_review(
        campaign_repo,
        run_repo,
        evidence_package_repo,
        review_repo,
        campaign_governance_id="CAMP-0099",
        run_governance_id="RUN-0099",
        evidence_package_governance_id="EVID-0099",
        review_governance_id="REVIEW-0099",
    )

    handler = AddReviewFindingHandler(review_repository=review_repo)
    result = handler.handle(
        AddReviewFindingCommand(
            identity=identity,
            expected_persisted_version=AggregateVersion(1),
            text="a finding",
        )
    )

    assert result.operation is SaveOperation.UPDATED
