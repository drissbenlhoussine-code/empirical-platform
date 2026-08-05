"""MILESTONE-043 real-PostgreSQL integration tests for `GetReviewHandler`.

Exercises the full frozen vertical slice against a real, migrated
PostgreSQL database (never mocked): `QueryEntryPoint` -> concrete
`GetReviewHandler` -> the real, frozen `PostgresReviewRepository` ->
PostgreSQL -> `ReviewSnapshot`. The `ReviewRepository` instance is
obtained externally (this test's own fixtures), exactly as the frozen
design requires -- the `usecases` package itself never imports
persistence. A Campaign, Run, EvidencePackage, and Review are first
persisted through the existing, frozen M030 `CreateCampaignHandler`, M033
`CreateRunHandler`, M036 `CreateEvidencePackageHandler`, and M042
`CreateReviewHandler`, reusing the identical fixture pattern
`tests/integration/test_m042_create_review_usecase.py` already
established.

Opt-in via ``EMPIRICAL_PLATFORM_RUN_POSTGRES_TESTS=1``, following the same
convention as ``tests/integration/test_m023_postgres_repositories.py``.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command as alembic_command
from alembic.config import Config
from pydantic import SecretStr
from sqlalchemy import text
from sqlalchemy.engine import Engine

from empirical_platform.application.command import CommandEntryPoint
from empirical_platform.application.query import QueryEntryPoint
from empirical_platform.identifiers.pairs import DomainIdentity
from empirical_platform.identifiers.types import EvidencePackageId, ReviewId
from empirical_platform.review.lifecycle import ReviewLifecycleState
from empirical_platform.shared.config.settings import PostgreSQLConfigSnapshot
from empirical_platform.shared.contracts.repository import AggregateNotFound
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
from empirical_platform.usecases.get_review import (
    GetReviewHandler,
    GetReviewQuery,
    ReviewSnapshot,
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
        application_name="empirical-platform-m043-test",
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


def _persist_review(
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
            scope_statement="seed campaign for M043 tests",
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

    return CommandEntryPoint(
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


def test_golden_path_retrieves_via_query_entry_point_and_real_repository(
    campaign_repo: PostgresCampaignRepository,
    run_repo: PostgresRunRepository,
    evidence_package_repo: PostgresEvidencePackageRepository,
    review_repo: PostgresReviewRepository,
) -> None:
    review_identity = _persist_review(
        campaign_repo,
        run_repo,
        evidence_package_repo,
        review_repo,
        campaign_governance_id="CAMP-0001",
        run_governance_id="RUN-0001",
        evidence_package_governance_id="EVID-0001",
        review_governance_id="REVIEW-0001",
        reviewer_reference="reviewer-golden-path",
    )

    get_handler = GetReviewHandler(review_repository=review_repo)
    get_entry_point = QueryEntryPoint(get_handler)

    snapshot = get_entry_point(GetReviewQuery(identity=review_identity))

    assert isinstance(snapshot, ReviewSnapshot)
    assert snapshot.identity == review_identity
    assert snapshot.target_evidence_package_id == EvidencePackageId("EVID-0001")
    assert snapshot.reviewer_reference == "reviewer-golden-path"
    assert snapshot.state is ReviewLifecycleState.ASSIGNED
    assert set(ReviewSnapshot.__slots__) == {  # type: ignore[attr-defined]
        "identity",
        "target_evidence_package_id",
        "reviewer_reference",
        "state",
    }


def test_missing_full_identity_raises_aggregate_not_found(
    campaign_repo: PostgresCampaignRepository,
    run_repo: PostgresRunRepository,
    evidence_package_repo: PostgresEvidencePackageRepository,
    review_repo: PostgresReviewRepository,
) -> None:
    _persist_review(
        campaign_repo,
        run_repo,
        evidence_package_repo,
        review_repo,
        campaign_governance_id="CAMP-0001",
        run_governance_id="RUN-0001",
        evidence_package_governance_id="EVID-0001",
        review_governance_id="REVIEW-0001",
    )
    missing_identity = DomainIdentity(
        governance_id=ReviewId("REVIEW-9999"),
        runtime_id=RuntimeIdentifier(_MISSING_RUNTIME_ID_VALUE),
    )
    get_handler = GetReviewHandler(review_repository=review_repo)
    get_entry_point = QueryEntryPoint(get_handler)

    with pytest.raises(AggregateNotFound):
        get_entry_point(GetReviewQuery(identity=missing_identity))


def test_no_production_composition_machinery_is_required(
    campaign_repo: PostgresCampaignRepository,
    run_repo: PostgresRunRepository,
    evidence_package_repo: PostgresEvidencePackageRepository,
    review_repo: PostgresReviewRepository,
) -> None:
    """The handler is constructed directly from the externally-obtained
    repository -- no FoundationRuntime, no registry, no composition root
    of any kind."""
    review_identity = _persist_review(
        campaign_repo,
        run_repo,
        evidence_package_repo,
        review_repo,
        campaign_governance_id="CAMP-0099",
        run_governance_id="RUN-0099",
        evidence_package_governance_id="EVID-0099",
        review_governance_id="REVIEW-0099",
    )

    handler = GetReviewHandler(review_repository=review_repo)
    result = handler.handle(GetReviewQuery(identity=review_identity))

    assert isinstance(result, ReviewSnapshot)
    assert result.identity == review_identity


def test_finding_and_transition_tables_load_without_error(
    campaign_repo: PostgresCampaignRepository,
    run_repo: PostgresRunRepository,
    evidence_package_repo: PostgresEvidencePackageRepository,
    review_repo: PostgresReviewRepository,
) -> None:
    """Regression: `PostgresReviewRepository.get()` still loads
    `review_finding`/`review_transition` rows without error for a freshly
    created Review (which has none of either), proving the always-eager
    load path does not break even though its result is unused by this
    query. This additionally confirms retrieval succeeds without
    requiring an `EvidencePackageRepository` of any kind."""
    review_identity = _persist_review(
        campaign_repo,
        run_repo,
        evidence_package_repo,
        review_repo,
        campaign_governance_id="CAMP-0002",
        run_governance_id="RUN-0002",
        evidence_package_governance_id="EVID-0002",
        review_governance_id="REVIEW-0002",
    )

    get_handler = GetReviewHandler(review_repository=review_repo)
    get_entry_point = QueryEntryPoint(get_handler)
    snapshot = get_entry_point(GetReviewQuery(identity=review_identity))

    assert isinstance(snapshot, ReviewSnapshot)
    assert not hasattr(snapshot, "findings")
    assert not hasattr(snapshot, "transition_history")
    assert not hasattr(snapshot, "disposition")
    assert not hasattr(snapshot, "version")
    assert not hasattr(snapshot, "persisted_version")
