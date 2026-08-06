"""MILESTONE-049 real-PostgreSQL integration tests for `CancelReviewHandler`.

Exercises the full frozen vertical slice against a real, migrated
PostgreSQL database (never mocked): `CommandEntryPoint` -> concrete
`CancelReviewHandler` -> `Review` aggregate -> the real, frozen
`PostgresReviewRepository` -> PostgreSQL. The `ReviewRepository` instance
is obtained externally (this test's own fixtures), exactly as the frozen
design requires -- the `usecases` package itself never imports
persistence. A Campaign, Run, EvidencePackage, and Review are first
persisted through the existing, frozen M030/M033/M036/M042 handlers, and
the Review is transitioned to IN_PROGRESS through the existing, frozen
M044 `StartReviewHandler` where needed.

The deterministic optimistic-concurrency conflict scenario is frozen
exactly by the M049 design (Section 13): `Review.add_finding()` (M045's
own frozen interfering write, already reused once by M046 for
`complete()`) is reused a third time here, re-applied to `cancel()`. The
interfering write independently loads the same identity and calls
`Review.add_finding()` directly (never through `AddReviewFindingHandler`)
to advance the persisted version while preserving IN_PROGRESS, so the
command under test can still execute its own `cancel()` call before the
stale-version `save()` fails. This is test setup only; the interfering
call is never made through any production command in this milestone.

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
from empirical_platform.review.lifecycle import ReviewDisposition, ReviewLifecycleState
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
from empirical_platform.usecases.cancel_review import CancelReviewCommand, CancelReviewHandler
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
        application_name="empirical-platform-m049-test",
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


def _persist_assigned_review(
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
    campaign_runtime_id: str,
    run_runtime_id: str,
    evidence_runtime_id: str,
    review_runtime_id: str,
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
            campaign_governance_id=campaign_governance_id, scope_statement="seed campaign"
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
    campaign_runtime_id: str,
    run_runtime_id: str,
    evidence_runtime_id: str,
    review_runtime_id: str,
) -> DomainIdentity[ReviewId]:
    identity = _persist_assigned_review(
        campaign_repo,
        run_repo,
        evidence_package_repo,
        review_repo,
        campaign_governance_id=campaign_governance_id,
        run_governance_id=run_governance_id,
        evidence_package_governance_id=evidence_package_governance_id,
        review_governance_id=review_governance_id,
        campaign_runtime_id=campaign_runtime_id,
        run_runtime_id=run_runtime_id,
        evidence_runtime_id=evidence_runtime_id,
        review_runtime_id=review_runtime_id,
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


def test_golden_path_cancels_review_from_assigned(
    campaign_repo: PostgresCampaignRepository,
    run_repo: PostgresRunRepository,
    evidence_package_repo: PostgresEvidencePackageRepository,
    review_repo: PostgresReviewRepository,
) -> None:
    identity = _persist_assigned_review(
        campaign_repo,
        run_repo,
        evidence_package_repo,
        review_repo,
        campaign_governance_id="CAMP-0001",
        run_governance_id="RUN-0001",
        evidence_package_governance_id="EVID-0001",
        review_governance_id="REVIEW-0001",
        campaign_runtime_id="b1111111-1111-4111-8111-111111111111",
        run_runtime_id="b2222222-2222-4222-8222-222222222222",
        evidence_runtime_id="b3333333-3333-4333-8333-333333333333",
        review_runtime_id="b4444444-4444-4444-8444-444444444444",
    )

    handler = CancelReviewHandler(review_repository=review_repo)
    entry_point = CommandEntryPoint(handler)
    command = CancelReviewCommand(
        identity=identity,
        expected_persisted_version=AggregateVersion(0),
        reason="assignment withdrawn",
        actor="tester",
        occurred_at=_OCCURRED_AT,
        correlation_id="corr-golden",
    )

    result = entry_point(command)

    assert result.operation is SaveOperation.UPDATED
    assert result.persisted_version == AggregateVersion(1)

    reloaded = review_repo.get(identity)
    assert reloaded.aggregate.state is ReviewLifecycleState.CANCELLED
    assert reloaded.persisted_version == AggregateVersion(1)
    record = reloaded.aggregate.transition_history[-1]
    assert record.from_state == "ASSIGNED"
    assert record.to_state == "CANCELLED"
    assert record.reason == "assignment withdrawn"
    assert record.correlation_id == "corr-golden"


def test_golden_path_cancels_review_from_in_progress(
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
        campaign_governance_id="CAMP-0002",
        run_governance_id="RUN-0002",
        evidence_package_governance_id="EVID-0002",
        review_governance_id="REVIEW-0002",
        campaign_runtime_id="b5555555-5555-4555-8555-555555555555",
        run_runtime_id="b6666666-6666-4666-8666-666666666666",
        evidence_runtime_id="b7777777-7777-4777-8777-777777777777",
        review_runtime_id="b8888888-8888-4888-8888-888888888888",
    )

    handler = CancelReviewHandler(review_repository=review_repo)
    entry_point = CommandEntryPoint(handler)
    command = CancelReviewCommand(
        identity=identity,
        expected_persisted_version=AggregateVersion(1),
        reason="withdrawn mid-review",
        actor="tester",
        occurred_at=_OCCURRED_AT,
    )

    result = entry_point(command)

    assert result.operation is SaveOperation.UPDATED
    reloaded = review_repo.get(identity)
    assert reloaded.aggregate.state is ReviewLifecycleState.CANCELLED
    assert reloaded.aggregate.transition_history[-1].from_state == "IN_PROGRESS"


def test_invalid_state_completed_raises_domain_error_without_persisting(
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
        campaign_governance_id="CAMP-0003",
        run_governance_id="RUN-0003",
        evidence_package_governance_id="EVID-0003",
        review_governance_id="REVIEW-0003",
        campaign_runtime_id="b9999999-9999-4999-8999-999999999999",
        run_runtime_id="baaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        evidence_runtime_id="bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
        review_runtime_id="bccccccc-cccc-4ccc-8ccc-cccccccccccc",
    )
    loaded = review_repo.get(identity)
    loaded.aggregate.add_finding(text="a real finding")
    review_repo.save(loaded.aggregate, expected_persisted_version=AggregateVersion(1))
    loaded = review_repo.get(identity)
    loaded.aggregate.complete(
        disposition=ReviewDisposition.ACCEPTED,
        final_disposition_rationale="all criteria satisfied",
        actor="tester",
        occurred_at=_OCCURRED_AT,
    )
    review_repo.save(loaded.aggregate, expected_persisted_version=AggregateVersion(2))

    handler = CancelReviewHandler(review_repository=review_repo)
    entry_point = CommandEntryPoint(handler)
    command = CancelReviewCommand(
        identity=identity,
        expected_persisted_version=AggregateVersion(3),
        reason="too late",
        actor="tester",
        occurred_at=_OCCURRED_AT,
    )

    with pytest.raises(ValueError, match="cannot transition from COMPLETED"):
        entry_point(command)

    reloaded = review_repo.get(identity)
    assert reloaded.aggregate.state is ReviewLifecycleState.COMPLETED
    assert reloaded.persisted_version == AggregateVersion(3)


def test_empty_reason_raises_domain_value_error(
    campaign_repo: PostgresCampaignRepository,
    run_repo: PostgresRunRepository,
    evidence_package_repo: PostgresEvidencePackageRepository,
    review_repo: PostgresReviewRepository,
) -> None:
    identity = _persist_assigned_review(
        campaign_repo,
        run_repo,
        evidence_package_repo,
        review_repo,
        campaign_governance_id="CAMP-0004",
        run_governance_id="RUN-0004",
        evidence_package_governance_id="EVID-0004",
        review_governance_id="REVIEW-0004",
        campaign_runtime_id="c1111111-1111-4111-8111-111111111111",
        run_runtime_id="c2222222-2222-4222-8222-222222222222",
        evidence_runtime_id="c3333333-3333-4333-8333-333333333333",
        review_runtime_id="c4444444-4444-4444-8444-444444444444",
    )

    handler = CancelReviewHandler(review_repository=review_repo)
    entry_point = CommandEntryPoint(handler)
    command = CancelReviewCommand(
        identity=identity,
        expected_persisted_version=AggregateVersion(0),
        reason="   ",
        actor="tester",
        occurred_at=_OCCURRED_AT,
    )

    with pytest.raises(ValueError, match="must be non-empty"):
        entry_point(command)

    reloaded = review_repo.get(identity)
    assert reloaded.aggregate.state is ReviewLifecycleState.ASSIGNED
    assert reloaded.persisted_version == AggregateVersion(0)


def test_missing_review_raises_aggregate_not_found(
    review_repo: PostgresReviewRepository,
) -> None:
    missing_identity = DomainIdentity(
        governance_id=ReviewId("REVIEW-9999"),
        runtime_id=RuntimeIdentifier(_MISSING_RUNTIME_ID_VALUE),
    )
    handler = CancelReviewHandler(review_repository=review_repo)
    entry_point = CommandEntryPoint(handler)

    with pytest.raises(AggregateNotFound):
        entry_point(
            CancelReviewCommand(
                identity=missing_identity,
                expected_persisted_version=AggregateVersion.initial(),
                reason="should never persist",
                actor="tester",
                occurred_at=_OCCURRED_AT,
            )
        )


def test_stale_expected_version_raises_optimistic_concurrency_conflict(
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
        campaign_governance_id="CAMP-0005",
        run_governance_id="RUN-0005",
        evidence_package_governance_id="EVID-0005",
        review_governance_id="REVIEW-0005",
        campaign_runtime_id="c5555555-5555-4555-8555-555555555555",
        run_runtime_id="c6666666-6666-4666-8666-666666666666",
        evidence_runtime_id="c7777777-7777-4777-8777-777777777777",
        review_runtime_id="c8888888-8888-4888-8888-888888888888",
    )

    # Simulate an interfering writer: independently reload the same identity
    # and advance the persisted version via add_finding() -- reused a third
    # time (after M045's self-reuse, M046's reuse for complete()), still
    # state-preserving, does not touch cancel()'s own preconditions. Test
    # setup only; never invoked as an interfering write by any production
    # code.
    interfering = review_repo.get(identity)
    interfering.aggregate.add_finding(text="interfering writer's finding")
    review_repo.save(interfering.aggregate, expected_persisted_version=AggregateVersion(1))

    handler = CancelReviewHandler(review_repository=review_repo)
    entry_point = CommandEntryPoint(handler)
    stale_command = CancelReviewCommand(
        identity=identity,
        expected_persisted_version=AggregateVersion(1),  # stale: real durable version is 2
        reason="should never persist",
        actor="tester",
        occurred_at=_OCCURRED_AT,
    )

    with pytest.raises(OptimisticConcurrencyConflict) as excinfo:
        entry_point(stale_command)

    assert excinfo.value.expected_persisted_version == AggregateVersion(1)
    assert excinfo.value.actual_persisted_version == AggregateVersion(2)

    reloaded = review_repo.get(identity)
    assert reloaded.aggregate.state is ReviewLifecycleState.IN_PROGRESS
    assert len(reloaded.aggregate.findings) == 1
    assert reloaded.persisted_version == AggregateVersion(2)


def test_no_production_composition_machinery_is_required(
    campaign_repo: PostgresCampaignRepository,
    run_repo: PostgresRunRepository,
    evidence_package_repo: PostgresEvidencePackageRepository,
    review_repo: PostgresReviewRepository,
) -> None:
    """The handler is constructed directly from the externally-obtained
    repository -- no FoundationRuntime, no registry, no composition root
    of any kind."""
    identity = _persist_assigned_review(
        campaign_repo,
        run_repo,
        evidence_package_repo,
        review_repo,
        campaign_governance_id="CAMP-0099",
        run_governance_id="RUN-0099",
        evidence_package_governance_id="EVID-0099",
        review_governance_id="REVIEW-0099",
        campaign_runtime_id="c9999999-9999-4999-8999-999999999999",
        run_runtime_id="caaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        evidence_runtime_id="cbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
        review_runtime_id="cccccccc-cccc-4ccc-8ccc-cccccccccccc",
    )

    handler = CancelReviewHandler(review_repository=review_repo)
    result = handler.handle(
        CancelReviewCommand(
            identity=identity,
            expected_persisted_version=AggregateVersion(0),
            reason="a reason",
            actor="tester",
            occurred_at=_OCCURRED_AT,
        )
    )

    assert result.operation is SaveOperation.UPDATED
