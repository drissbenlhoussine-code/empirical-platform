"""MILESTONE-038 real-PostgreSQL integration tests for
`StartEvidencePackageCollectionHandler`.

Exercises the full frozen vertical slice against a real, migrated
PostgreSQL database (never mocked): `CommandEntryPoint` -> concrete
`StartEvidencePackageCollectionHandler` -> `EvidencePackage` aggregate ->
the real, frozen `PostgresEvidencePackageRepository` -> PostgreSQL. The
`EvidencePackageRepository` instance is obtained externally (this test's
own fixtures), exactly as the frozen design requires -- the `usecases`
package itself never imports persistence. A Campaign, Run, and
EvidencePackage are first persisted through the existing, frozen M030
`CreateCampaignHandler`, M033 `CreateRunHandler`, and M036
`CreateEvidencePackageHandler`, reusing the identical fixture pattern
`tests/integration/test_m037_get_evidence_package_usecase.py` already
established.

The "conflict" scenario is frozen exactly by the M038 design (Section 6):
`EvidencePackage` has no method analogous to `Campaign.revise_scope_statement()`
or `Run.append_manifest()` available while `INITIALIZED` -- `start_collection()`
is the only method that operates on that state. Two independently loaded
callers racing the same transition therefore produce a domain-level
`ValueError` (the second caller's own `start_collection()` call is invalid
against the now-`COLLECTING` durable state, so it never reaches `save()`),
not a repository-level `OptimisticConcurrencyConflict` -- this is an
independently-derived, disclosed boundary of this specific transition, not
a gap; `OptimisticConcurrencyConflict` propagation itself remains proven at
the unit level (`tests/unit/test_start_evidence_package_collection_usecase.py`)
via a fake repository unconstrained by the aggregate's own state machine.

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
from empirical_platform.evidence.lifecycle import EvidencePackageLifecycleState
from empirical_platform.identifiers.pairs import DomainIdentity
from empirical_platform.identifiers.types import EvidencePackageId
from empirical_platform.shared.config.settings import PostgreSQLConfigSnapshot
from empirical_platform.shared.contracts.repository import AggregateNotFound, SaveOperation
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
        application_name="empirical-platform-m038-test",
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


def _persist_evidence_package(
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
    create_campaign_handler = CreateCampaignHandler(
        campaign_repository=campaign_repo,
        runtime_identifier_generator=DeterministicRuntimeIdentifierGenerator([campaign_runtime_id]),
    )
    CommandEntryPoint(create_campaign_handler)(
        CreateCampaignCommand(
            campaign_governance_id=campaign_governance_id,
            scope_statement="seed campaign for M038 tests",
        )
    )

    create_run_handler = CreateRunHandler(
        run_repository=run_repo,
        runtime_identifier_generator=DeterministicRuntimeIdentifierGenerator([run_runtime_id]),
    )
    CommandEntryPoint(create_run_handler)(
        CreateRunCommand(
            run_governance_id=run_governance_id, campaign_governance_id=campaign_governance_id
        )
    )

    create_evidence_handler = CreateEvidencePackageHandler(
        evidence_package_repository=evidence_package_repo,
        runtime_identifier_generator=DeterministicRuntimeIdentifierGenerator([evidence_runtime_id]),
    )
    return CommandEntryPoint(create_evidence_handler)(
        CreateEvidencePackageCommand(
            evidence_package_governance_id=evidence_package_governance_id,
            run_governance_id=run_governance_id,
        )
    )


def test_golden_path_starts_collection_via_command_entry_point_and_real_repository(
    campaign_repo: PostgresCampaignRepository,
    run_repo: PostgresRunRepository,
    evidence_package_repo: PostgresEvidencePackageRepository,
) -> None:
    identity = _persist_evidence_package(
        campaign_repo,
        run_repo,
        evidence_package_repo,
        campaign_governance_id="CAMP-0001",
        run_governance_id="RUN-0001",
        evidence_package_governance_id="EVID-0001",
    )

    handler = StartEvidencePackageCollectionHandler(
        evidence_package_repository=evidence_package_repo
    )
    entry_point = CommandEntryPoint(handler)
    command = StartEvidencePackageCollectionCommand(
        identity=identity,
        expected_persisted_version=AggregateVersion.initial(),
        actor="tester",
        occurred_at=_OCCURRED_AT,
    )

    result = entry_point(command)

    assert result.operation is SaveOperation.UPDATED
    assert result.persisted_version == AggregateVersion(1)

    loaded = evidence_package_repo.get(identity)
    assert loaded.aggregate.state is EvidencePackageLifecycleState.COLLECTING
    assert loaded.persisted_version == AggregateVersion(1)
    assert len(loaded.aggregate.transition_history) == 1
    record = loaded.aggregate.transition_history[0]
    assert record.from_state == "INITIALIZED"
    assert record.to_state == "COLLECTING"


def test_two_racing_callers_second_start_collection_raises_domain_value_error(
    campaign_repo: PostgresCampaignRepository,
    run_repo: PostgresRunRepository,
    evidence_package_repo: PostgresEvidencePackageRepository,
) -> None:
    """Independently reproduces the design's disclosed boundary (Section 6):
    the second independently-loaded caller's own start_collection() call is
    invalid once the first caller has already advanced the durable state to
    COLLECTING, so it raises a domain ValueError before save() is ever
    reached -- never OptimisticConcurrencyConflict."""
    identity = _persist_evidence_package(
        campaign_repo,
        run_repo,
        evidence_package_repo,
        campaign_governance_id="CAMP-0002",
        run_governance_id="RUN-0002",
        evidence_package_governance_id="EVID-0002",
    )

    first_handler = StartEvidencePackageCollectionHandler(
        evidence_package_repository=evidence_package_repo
    )
    CommandEntryPoint(first_handler)(
        StartEvidencePackageCollectionCommand(
            identity=identity,
            expected_persisted_version=AggregateVersion.initial(),
            actor="first-caller",
            occurred_at=_OCCURRED_AT,
        )
    )

    second_handler = StartEvidencePackageCollectionHandler(
        evidence_package_repository=evidence_package_repo
    )
    with pytest.raises(ValueError, match="cannot transition from"):
        CommandEntryPoint(second_handler)(
            StartEvidencePackageCollectionCommand(
                identity=identity,
                expected_persisted_version=AggregateVersion.initial(),
                actor="second-caller",
                occurred_at=_OCCURRED_AT,
            )
        )

    loaded = evidence_package_repo.get(identity)
    assert loaded.aggregate.state is EvidencePackageLifecycleState.COLLECTING
    assert loaded.persisted_version == AggregateVersion(1)
    assert len(loaded.aggregate.transition_history) == 1


def test_missing_full_identity_raises_aggregate_not_found(
    evidence_package_repo: PostgresEvidencePackageRepository,
) -> None:
    missing_identity = DomainIdentity(
        governance_id=EvidencePackageId("EVID-9999"),
        runtime_id=RuntimeIdentifier(_MISSING_RUNTIME_ID_VALUE),
    )
    handler = StartEvidencePackageCollectionHandler(
        evidence_package_repository=evidence_package_repo
    )
    entry_point = CommandEntryPoint(handler)
    command = StartEvidencePackageCollectionCommand(
        identity=missing_identity,
        expected_persisted_version=AggregateVersion.initial(),
        actor="tester",
        occurred_at=_OCCURRED_AT,
    )

    with pytest.raises(AggregateNotFound):
        entry_point(command)


def test_no_production_composition_machinery_is_required(
    campaign_repo: PostgresCampaignRepository,
    run_repo: PostgresRunRepository,
    evidence_package_repo: PostgresEvidencePackageRepository,
) -> None:
    """The handler is constructed directly from the externally-obtained
    repository -- no FoundationRuntime, no registry, no composition root
    of any kind."""
    identity = _persist_evidence_package(
        campaign_repo,
        run_repo,
        evidence_package_repo,
        campaign_governance_id="CAMP-0099",
        run_governance_id="RUN-0099",
        evidence_package_governance_id="EVID-0099",
    )

    handler = StartEvidencePackageCollectionHandler(
        evidence_package_repository=evidence_package_repo
    )
    result = handler.handle(
        StartEvidencePackageCollectionCommand(
            identity=identity,
            expected_persisted_version=AggregateVersion.initial(),
            actor="tester",
            occurred_at=_OCCURRED_AT,
        )
    )

    assert result.operation is SaveOperation.UPDATED
    assert result.persisted_version == AggregateVersion(1)
