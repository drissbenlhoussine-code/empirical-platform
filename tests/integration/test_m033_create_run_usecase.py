"""MILESTONE-033 real-PostgreSQL integration tests for `CreateRunHandler`.

Exercises the full frozen vertical slice against a real, migrated
PostgreSQL database (never mocked): `CommandEntryPoint` -> concrete
`CreateRunHandler` -> `Run` aggregate -> the real, frozen
`PostgresRunRepository` -> PostgreSQL. The `RunRepository` instance is
obtained externally (this test's own fixtures), exactly as the frozen
design requires -- the `usecases` package itself never imports persistence.
A Campaign is first persisted through the existing, frozen M030
`CreateCampaignHandler`, reusing the identical fixture pattern
`tests/integration/test_m030_create_campaign_usecase.py` and
`tests/integration/test_m032_prepare_campaign_for_authorization_usecase.py`
already established.

The missing-Campaign scenario is frozen exactly by the M033 design freeze
(Section 11/20): no application-level `CampaignRepository` lookup exists --
a nonexistent `campaign_governance_id` is rejected by the real database
foreign-key constraint (`run.campaign_id -> campaign.governance_id`,
MILESTONE-022), surfacing as an unmodified `FoundationError` with
`category=FoundationErrorCategory.PERSISTENCE`, never `AggregateNotFound`
or any Run-/Campaign-specific application error.

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
from empirical_platform.campaign.lifecycle import RunLifecycleState
from empirical_platform.identifiers.pairs import DomainIdentity
from empirical_platform.identifiers.types import CampaignId, RunId
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
from empirical_platform.shared.persistence.postgres_repositories.run_repository import (
    PostgresRunRepository,
)
from empirical_platform.usecases.create_campaign import (
    CreateCampaignCommand,
    CreateCampaignHandler,
)
from empirical_platform.usecases.create_run import CreateRunCommand, CreateRunHandler

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
_RUNTIME_ID_VALUE = "12345678-1234-4321-8765-1234567890ab"


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
        application_name="empirical-platform-m033-test",
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
    used only as test scaffolding to seed a real Campaign row; `usecases`
    never constructs or depends on this repository."""
    return PostgresCampaignRepository(service)


@pytest.fixture
def run_repo(service: PostgresPersistenceService) -> PostgresRunRepository:
    """The real, frozen M023 RunRepository, obtained externally -- exactly
    as the frozen design requires; `usecases` never constructs this
    itself."""
    return PostgresRunRepository(service)


def _persist_campaign(
    campaign_repo: PostgresCampaignRepository,
    *,
    governance_id: str,
    runtime_id: str = _RUNTIME_ID_VALUE,
) -> DomainIdentity[CampaignId]:
    create_handler = CreateCampaignHandler(
        campaign_repository=campaign_repo,
        runtime_identifier_generator=DeterministicRuntimeIdentifierGenerator([runtime_id]),
    )
    create_entry_point = CommandEntryPoint(create_handler)
    return create_entry_point(
        CreateCampaignCommand(
            campaign_governance_id=governance_id, scope_statement="seed campaign for M033 tests"
        )
    )


def test_golden_path_persists_via_command_entry_point_and_real_repository(
    campaign_repo: PostgresCampaignRepository,
    run_repo: PostgresRunRepository,
) -> None:
    _persist_campaign(campaign_repo, governance_id="CAMP-0001", runtime_id=_RUNTIME_ID_VALUE)

    run_runtime_id = "87654321-4321-4321-8765-0987654321ba"
    handler = CreateRunHandler(
        run_repository=run_repo,
        runtime_identifier_generator=DeterministicRuntimeIdentifierGenerator([run_runtime_id]),
    )
    entry_point = CommandEntryPoint(handler)
    command = CreateRunCommand(run_governance_id="RUN-0001", campaign_governance_id="CAMP-0001")

    result = entry_point(command)

    assert result.governance_id == RunId("RUN-0001")
    assert str(result.runtime_id) == run_runtime_id

    loaded = run_repo.get(result)
    assert loaded.aggregate.identity == result
    assert loaded.aggregate.campaign_id == CampaignId("CAMP-0001")
    assert loaded.aggregate.state is RunLifecycleState.CREATED
    assert loaded.persisted_version == AggregateVersion.initial()
    assert loaded.aggregate.manifests == ()
    assert loaded.aggregate.transition_history == ()


def test_duplicate_run_governance_id_raises_aggregate_already_exists(
    campaign_repo: PostgresCampaignRepository,
    run_repo: PostgresRunRepository,
) -> None:
    _persist_campaign(campaign_repo, governance_id="CAMP-0001", runtime_id=_RUNTIME_ID_VALUE)

    generator = DeterministicRuntimeIdentifierGenerator(
        ["87654321-4321-4321-8765-0987654321ba", "11111111-2222-4333-8444-555555555555"]
    )
    handler = CreateRunHandler(run_repository=run_repo, runtime_identifier_generator=generator)
    entry_point = CommandEntryPoint(handler)
    command = CreateRunCommand(run_governance_id="RUN-0001", campaign_governance_id="CAMP-0001")

    entry_point(command)

    duplicate_command = CreateRunCommand(
        run_governance_id="RUN-0001", campaign_governance_id="CAMP-0001"
    )
    with pytest.raises(AggregateAlreadyExists):
        entry_point(duplicate_command)


def test_duplicate_runtime_id_raises_aggregate_already_exists(
    campaign_repo: PostgresCampaignRepository,
    run_repo: PostgresRunRepository,
) -> None:
    """Two different Run governance IDs with the same generated runtime ID
    collide on the real `pk_run` primary-key constraint."""
    _persist_campaign(campaign_repo, governance_id="CAMP-0001", runtime_id=_RUNTIME_ID_VALUE)

    shared_runtime_id = "87654321-4321-4321-8765-0987654321ba"
    generator = DeterministicRuntimeIdentifierGenerator([shared_runtime_id, shared_runtime_id])
    handler = CreateRunHandler(run_repository=run_repo, runtime_identifier_generator=generator)
    entry_point = CommandEntryPoint(handler)

    entry_point(CreateRunCommand(run_governance_id="RUN-0001", campaign_governance_id="CAMP-0001"))

    with pytest.raises(AggregateAlreadyExists):
        entry_point(
            CreateRunCommand(run_governance_id="RUN-0002", campaign_governance_id="CAMP-0001")
        )


def test_missing_campaign_raises_raw_foundation_error_not_translated(
    run_repo: PostgresRunRepository,
) -> None:
    """No Campaign is seeded; the real `run.campaign_id -> campaign.governance_id`
    foreign key rejects the insert, surfacing as an unmodified
    `FoundationError` (category `PERSISTENCE`) -- exactly as the design
    freeze (Section 11/20) specifies. Explicitly not `AggregateNotFound`,
    not `AggregateAlreadyExists`, not any Run-/Campaign-specific error, and
    no Run row is persisted despite the failure."""
    handler = CreateRunHandler(
        run_repository=run_repo,
        runtime_identifier_generator=DeterministicRuntimeIdentifierGenerator([_RUNTIME_ID_VALUE]),
    )
    entry_point = CommandEntryPoint(handler)
    command = CreateRunCommand(run_governance_id="RUN-0001", campaign_governance_id="CAMP-9999")

    with pytest.raises(FoundationError) as excinfo:
        entry_point(command)

    assert excinfo.value.category is FoundationErrorCategory.PERSISTENCE
    assert not isinstance(excinfo.value, AggregateAlreadyExists)

    attempted_identity = DomainIdentity(
        governance_id=RunId("RUN-0001"),
        runtime_id=RuntimeIdentifier(_RUNTIME_ID_VALUE),
    )
    with pytest.raises(AggregateNotFound):
        run_repo.get(attempted_identity)


def test_no_production_composition_machinery_is_required(
    campaign_repo: PostgresCampaignRepository,
    run_repo: PostgresRunRepository,
) -> None:
    """The handler is constructed directly from the externally-obtained
    repository and a deterministic generator -- no FoundationRuntime, no
    registry, no composition root of any kind."""
    _persist_campaign(campaign_repo, governance_id="CAMP-0099", runtime_id=_RUNTIME_ID_VALUE)

    handler = CreateRunHandler(
        run_repository=run_repo,
        runtime_identifier_generator=DeterministicRuntimeIdentifierGenerator(
            ["87654321-4321-4321-8765-0987654321ba"]
        ),
    )
    result = handler.handle(
        CreateRunCommand(run_governance_id="RUN-0099", campaign_governance_id="CAMP-0099")
    )
    assert result.governance_id == RunId("RUN-0099")
    assert isinstance(result, DomainIdentity)
