"""MILESTONE-036 real-PostgreSQL integration tests for
`CreateEvidencePackageHandler`.

Exercises the full frozen vertical slice against a real, migrated
PostgreSQL database (never mocked): `CommandEntryPoint` -> concrete
`CreateEvidencePackageHandler` -> `EvidencePackage` aggregate -> the real,
frozen `PostgresEvidencePackageRepository` -> PostgreSQL. The
`EvidencePackageRepository` instance is obtained externally (this test's
own fixtures), exactly as the frozen design requires -- the `usecases`
package itself never imports persistence. A Campaign and Run are first
persisted through the existing, frozen M030 `CreateCampaignHandler` and
M033 `CreateRunHandler`, reusing the identical fixture pattern
`tests/integration/test_m033_create_run_usecase.py` already established.

The missing-Run scenario is frozen exactly by the M036 design (Section
10/16): no application-level `RunRepository` lookup exists -- a
nonexistent `run_governance_id` is rejected by the real database
foreign-key constraint (`evidence_package.run_id -> run.governance_id`,
MILESTONE-022), surfacing as an unmodified `FoundationError` with
`category=FoundationErrorCategory.PERSISTENCE`, never `AggregateNotFound`
or any EvidencePackage-/Run-specific application error.

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
from empirical_platform.evidence.lifecycle import EvidencePackageLifecycleState
from empirical_platform.identifiers.pairs import DomainIdentity
from empirical_platform.identifiers.types import EvidencePackageId, RunId
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
_CAMPAIGN_RUNTIME_ID_VALUE = "12345678-1234-4321-8765-1234567890ab"
_RUN_RUNTIME_ID_VALUE = "22345678-1234-4321-8765-1234567890ab"
_EVIDENCE_RUNTIME_ID_VALUE = "32345678-1234-4321-8765-1234567890ab"


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
        application_name="empirical-platform-m036-test",
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
    -- exactly as the frozen design requires; `usecases` never constructs
    this itself."""
    return PostgresEvidencePackageRepository(service)


def _persist_run(
    campaign_repo: PostgresCampaignRepository,
    run_repo: PostgresRunRepository,
    *,
    campaign_governance_id: str,
    run_governance_id: str,
    campaign_runtime_id: str = _CAMPAIGN_RUNTIME_ID_VALUE,
    run_runtime_id: str = _RUN_RUNTIME_ID_VALUE,
) -> DomainIdentity[RunId]:
    create_campaign_handler = CreateCampaignHandler(
        campaign_repository=campaign_repo,
        runtime_identifier_generator=DeterministicRuntimeIdentifierGenerator([campaign_runtime_id]),
    )
    CommandEntryPoint(create_campaign_handler)(
        CreateCampaignCommand(
            campaign_governance_id=campaign_governance_id,
            scope_statement="seed campaign for M036 tests",
        )
    )

    create_run_handler = CreateRunHandler(
        run_repository=run_repo,
        runtime_identifier_generator=DeterministicRuntimeIdentifierGenerator([run_runtime_id]),
    )
    return CommandEntryPoint(create_run_handler)(
        CreateRunCommand(
            run_governance_id=run_governance_id, campaign_governance_id=campaign_governance_id
        )
    )


def test_golden_path_persists_via_command_entry_point_and_real_repository(
    campaign_repo: PostgresCampaignRepository,
    run_repo: PostgresRunRepository,
    evidence_package_repo: PostgresEvidencePackageRepository,
) -> None:
    _persist_run(
        campaign_repo, run_repo, campaign_governance_id="CAMP-0001", run_governance_id="RUN-0001"
    )

    handler = CreateEvidencePackageHandler(
        evidence_package_repository=evidence_package_repo,
        runtime_identifier_generator=DeterministicRuntimeIdentifierGenerator(
            [_EVIDENCE_RUNTIME_ID_VALUE]
        ),
    )
    entry_point = CommandEntryPoint(handler)
    command = CreateEvidencePackageCommand(
        evidence_package_governance_id="EVID-0001", run_governance_id="RUN-0001"
    )

    result = entry_point(command)

    assert result.governance_id == EvidencePackageId("EVID-0001")
    assert str(result.runtime_id) == _EVIDENCE_RUNTIME_ID_VALUE

    loaded = evidence_package_repo.get(result)
    assert loaded.aggregate.identity == result
    assert loaded.aggregate.run_id == RunId("RUN-0001")
    assert loaded.aggregate.state is EvidencePackageLifecycleState.INITIALIZED
    assert loaded.persisted_version == AggregateVersion.initial()
    assert loaded.aggregate.criterion_results == ()
    assert loaded.aggregate.artifact_references == ()
    assert loaded.aggregate.transition_history == ()


def test_duplicate_evidence_package_governance_id_raises_aggregate_already_exists(
    campaign_repo: PostgresCampaignRepository,
    run_repo: PostgresRunRepository,
    evidence_package_repo: PostgresEvidencePackageRepository,
) -> None:
    _persist_run(
        campaign_repo, run_repo, campaign_governance_id="CAMP-0001", run_governance_id="RUN-0001"
    )

    generator = DeterministicRuntimeIdentifierGenerator(
        [_EVIDENCE_RUNTIME_ID_VALUE, "42345678-1234-4321-8765-1234567890ab"]
    )
    handler = CreateEvidencePackageHandler(
        evidence_package_repository=evidence_package_repo,
        runtime_identifier_generator=generator,
    )
    entry_point = CommandEntryPoint(handler)
    command = CreateEvidencePackageCommand(
        evidence_package_governance_id="EVID-0001", run_governance_id="RUN-0001"
    )

    entry_point(command)

    duplicate_command = CreateEvidencePackageCommand(
        evidence_package_governance_id="EVID-0001", run_governance_id="RUN-0001"
    )
    with pytest.raises(AggregateAlreadyExists):
        entry_point(duplicate_command)


def test_duplicate_runtime_id_raises_aggregate_already_exists(
    campaign_repo: PostgresCampaignRepository,
    run_repo: PostgresRunRepository,
    evidence_package_repo: PostgresEvidencePackageRepository,
) -> None:
    """Two different EvidencePackage governance IDs with the same generated
    runtime ID collide on the real `pk_evidence_package` primary-key
    constraint."""
    _persist_run(
        campaign_repo, run_repo, campaign_governance_id="CAMP-0001", run_governance_id="RUN-0001"
    )

    shared_runtime_id = _EVIDENCE_RUNTIME_ID_VALUE
    generator = DeterministicRuntimeIdentifierGenerator([shared_runtime_id, shared_runtime_id])
    handler = CreateEvidencePackageHandler(
        evidence_package_repository=evidence_package_repo,
        runtime_identifier_generator=generator,
    )
    entry_point = CommandEntryPoint(handler)

    entry_point(
        CreateEvidencePackageCommand(
            evidence_package_governance_id="EVID-0001", run_governance_id="RUN-0001"
        )
    )

    with pytest.raises(AggregateAlreadyExists):
        entry_point(
            CreateEvidencePackageCommand(
                evidence_package_governance_id="EVID-0002", run_governance_id="RUN-0001"
            )
        )


def test_missing_run_raises_raw_foundation_error_not_translated(
    evidence_package_repo: PostgresEvidencePackageRepository,
) -> None:
    """No Run is seeded; the real `evidence_package.run_id ->
    run.governance_id` foreign key rejects the insert, surfacing as an
    unmodified `FoundationError` (category `PERSISTENCE`) -- exactly as
    the design (Section 10/16) specifies. Explicitly not
    `AggregateNotFound`, not `AggregateAlreadyExists`, not any
    EvidencePackage-/Run-specific error, and no row is persisted despite
    the failure."""
    handler = CreateEvidencePackageHandler(
        evidence_package_repository=evidence_package_repo,
        runtime_identifier_generator=DeterministicRuntimeIdentifierGenerator(
            [_EVIDENCE_RUNTIME_ID_VALUE]
        ),
    )
    entry_point = CommandEntryPoint(handler)
    command = CreateEvidencePackageCommand(
        evidence_package_governance_id="EVID-0001", run_governance_id="RUN-9999"
    )

    with pytest.raises(FoundationError) as excinfo:
        entry_point(command)

    assert excinfo.value.category is FoundationErrorCategory.PERSISTENCE
    assert not isinstance(excinfo.value, AggregateAlreadyExists)

    attempted_identity = DomainIdentity(
        governance_id=EvidencePackageId("EVID-0001"),
        runtime_id=RuntimeIdentifier(_EVIDENCE_RUNTIME_ID_VALUE),
    )
    with pytest.raises(AggregateNotFound):
        evidence_package_repo.get(attempted_identity)


def test_no_production_composition_machinery_is_required(
    campaign_repo: PostgresCampaignRepository,
    run_repo: PostgresRunRepository,
    evidence_package_repo: PostgresEvidencePackageRepository,
) -> None:
    """The handler is constructed directly from the externally-obtained
    repository and a deterministic generator -- no FoundationRuntime, no
    registry, no composition root of any kind."""
    _persist_run(
        campaign_repo, run_repo, campaign_governance_id="CAMP-0099", run_governance_id="RUN-0099"
    )

    handler = CreateEvidencePackageHandler(
        evidence_package_repository=evidence_package_repo,
        runtime_identifier_generator=DeterministicRuntimeIdentifierGenerator(
            [_EVIDENCE_RUNTIME_ID_VALUE]
        ),
    )
    result = handler.handle(
        CreateEvidencePackageCommand(
            evidence_package_governance_id="EVID-0099", run_governance_id="RUN-0099"
        )
    )
    assert result.governance_id == EvidencePackageId("EVID-0099")
    assert isinstance(result, DomainIdentity)
