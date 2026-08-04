"""MILESTONE-041 real-PostgreSQL integration tests for
`SealEvidencePackageHandler`.

Exercises the full frozen vertical slice against a real, migrated
PostgreSQL database (never mocked): `CommandEntryPoint` -> concrete
`SealEvidencePackageHandler` -> `EvidencePackage` aggregate -> the real,
frozen `PostgresEvidencePackageRepository` -> PostgreSQL. The
`EvidencePackageRepository` instance is obtained externally (this test's
own fixtures), exactly as the frozen design requires -- the `usecases`
package itself never imports persistence. A Campaign, Run, and
EvidencePackage are first persisted through the existing, frozen
M030/M033/M036 handlers, the EvidencePackage is transitioned to
COLLECTING through the existing, frozen M038
`StartEvidencePackageCollectionHandler`, and one CriterionResult/
ArtifactReference are recorded through the existing, frozen M039/M040
handlers -- reusing the identical fixture pattern
`tests/integration/test_m040_record_evidence_package_artifact_reference_usecase.py`
already established. For the first time in this lineage, every one of
this milestone's own preconditions is satisfiable using exclusively
frozen application commands (M041 design Section 3/scope Section 5).

The deterministic optimistic-concurrency conflict scenario is frozen
exactly by the M041 design (Section 10): `add_artifact_reference()`
(frozen since M040) is used as the interfering write -- an arbitrary but
fixed choice, since either it or `add_criterion_result()` would serve
equally. The interfering write independently loads the same identity and
calls `EvidencePackage.add_artifact_reference()` -- never `seal()` itself
-- to advance the persisted version while preserving COLLECTING, so the
command under test can still execute its own `seal()` call before the
stale-version `save()` fails. `add_artifact_reference()` is test setup
only here; it is never invoked as an interfering write by any production
code in this milestone.

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
from empirical_platform.evidence.lifecycle import EvidencePackageLifecycleState
from empirical_platform.evidence.package import ArtifactReference
from empirical_platform.identifiers.pairs import DomainIdentity
from empirical_platform.identifiers.types import EvidencePackageId
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
        application_name="empirical-platform-m041-test",
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


def _persist_collecting_evidence_package(
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
    """Seeds a Campaign, Run, and EvidencePackage transitioned to COLLECTING
    -- exclusively via frozen application commands (M030, M033, M036, M038)."""
    create_campaign_handler = CreateCampaignHandler(
        campaign_repository=campaign_repo,
        runtime_identifier_generator=DeterministicRuntimeIdentifierGenerator([campaign_runtime_id]),
    )
    CommandEntryPoint(create_campaign_handler)(
        CreateCampaignCommand(
            campaign_governance_id=campaign_governance_id,
            scope_statement="seed campaign for M041 tests",
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
    identity = CommandEntryPoint(create_evidence_handler)(
        CreateEvidencePackageCommand(
            evidence_package_governance_id=evidence_package_governance_id,
            run_governance_id=run_governance_id,
        )
    )

    start_collection_handler = StartEvidencePackageCollectionHandler(
        evidence_package_repository=evidence_package_repo
    )
    CommandEntryPoint(start_collection_handler)(
        StartEvidencePackageCollectionCommand(
            identity=identity,
            expected_persisted_version=AggregateVersion.initial(),
            actor="tester",
            occurred_at=_OCCURRED_AT,
        )
    )

    return identity


def _persist_sealable_evidence_package(
    campaign_repo: PostgresCampaignRepository,
    run_repo: PostgresRunRepository,
    evidence_package_repo: PostgresEvidencePackageRepository,
    *,
    campaign_governance_id: str,
    run_governance_id: str,
    evidence_package_governance_id: str,
) -> DomainIdentity[EvidencePackageId]:
    """Seeds a COLLECTING EvidencePackage with one CriterionResult and one
    ArtifactReference recorded -- exclusively via frozen application
    commands (M030, M033, M036, M038, M039, M040)."""
    identity = _persist_collecting_evidence_package(
        campaign_repo,
        run_repo,
        evidence_package_repo,
        campaign_governance_id=campaign_governance_id,
        run_governance_id=run_governance_id,
        evidence_package_governance_id=evidence_package_governance_id,
    )

    record_criterion_handler = RecordEvidencePackageCriterionResultHandler(
        evidence_package_repository=evidence_package_repo
    )
    CommandEntryPoint(record_criterion_handler)(
        RecordEvidencePackageCriterionResultCommand(
            identity=identity,
            expected_persisted_version=AggregateVersion(1),
            criterion_id="CRIT-001",
            recorded_at=_OCCURRED_AT,
            result_label="PASS",
        )
    )

    record_artifact_handler = RecordEvidencePackageArtifactReferenceHandler(
        evidence_package_repository=evidence_package_repo
    )
    CommandEntryPoint(record_artifact_handler)(
        RecordEvidencePackageArtifactReferenceCommand(
            identity=identity,
            expected_persisted_version=AggregateVersion(2),
            value="s3://bucket/artifact-1",
        )
    )

    return identity


def test_golden_path_seals_via_command_entry_point_and_real_repository(
    campaign_repo: PostgresCampaignRepository,
    run_repo: PostgresRunRepository,
    evidence_package_repo: PostgresEvidencePackageRepository,
) -> None:
    identity = _persist_sealable_evidence_package(
        campaign_repo,
        run_repo,
        evidence_package_repo,
        campaign_governance_id="CAMP-0001",
        run_governance_id="RUN-0001",
        evidence_package_governance_id="EVID-0001",
    )

    handler = SealEvidencePackageHandler(evidence_package_repository=evidence_package_repo)
    entry_point = CommandEntryPoint(handler)
    command = SealEvidencePackageCommand(
        identity=identity,
        expected_persisted_version=AggregateVersion(3),
        actor="tester",
        occurred_at=_OCCURRED_AT,
    )

    result = entry_point(command)

    assert result.operation is SaveOperation.UPDATED
    assert result.persisted_version == AggregateVersion(4)

    loaded = evidence_package_repo.get(identity)
    assert loaded.aggregate.state is EvidencePackageLifecycleState.SEALED
    assert loaded.persisted_version == AggregateVersion(4)
    assert len(loaded.aggregate.criterion_results) == 1
    assert len(loaded.aggregate.artifact_references) == 1
    record = loaded.aggregate.transition_history[-1]
    assert record.from_state == "COLLECTING"
    assert record.to_state == "SEALED"


def test_empty_criterion_results_raises_domain_value_error(
    campaign_repo: PostgresCampaignRepository,
    run_repo: PostgresRunRepository,
    evidence_package_repo: PostgresEvidencePackageRepository,
) -> None:
    identity = _persist_collecting_evidence_package(
        campaign_repo,
        run_repo,
        evidence_package_repo,
        campaign_governance_id="CAMP-0002",
        run_governance_id="RUN-0002",
        evidence_package_governance_id="EVID-0002",
    )

    record_artifact_handler = RecordEvidencePackageArtifactReferenceHandler(
        evidence_package_repository=evidence_package_repo
    )
    CommandEntryPoint(record_artifact_handler)(
        RecordEvidencePackageArtifactReferenceCommand(
            identity=identity,
            expected_persisted_version=AggregateVersion(1),
            value="s3://bucket/artifact-1",
        )
    )

    handler = SealEvidencePackageHandler(evidence_package_repository=evidence_package_repo)
    entry_point = CommandEntryPoint(handler)

    with pytest.raises(ValueError, match="requires at least one Criterion Result"):
        entry_point(
            SealEvidencePackageCommand(
                identity=identity,
                expected_persisted_version=AggregateVersion(2),
                actor="tester",
                occurred_at=_OCCURRED_AT,
            )
        )


def test_empty_artifact_references_raises_domain_value_error(
    campaign_repo: PostgresCampaignRepository,
    run_repo: PostgresRunRepository,
    evidence_package_repo: PostgresEvidencePackageRepository,
) -> None:
    identity = _persist_collecting_evidence_package(
        campaign_repo,
        run_repo,
        evidence_package_repo,
        campaign_governance_id="CAMP-0003",
        run_governance_id="RUN-0003",
        evidence_package_governance_id="EVID-0003",
    )

    record_criterion_handler = RecordEvidencePackageCriterionResultHandler(
        evidence_package_repository=evidence_package_repo
    )
    CommandEntryPoint(record_criterion_handler)(
        RecordEvidencePackageCriterionResultCommand(
            identity=identity,
            expected_persisted_version=AggregateVersion(1),
            criterion_id="CRIT-001",
            recorded_at=_OCCURRED_AT,
            result_label="PASS",
        )
    )

    handler = SealEvidencePackageHandler(evidence_package_repository=evidence_package_repo)
    entry_point = CommandEntryPoint(handler)

    with pytest.raises(ValueError, match="requires at least one artifact reference"):
        entry_point(
            SealEvidencePackageCommand(
                identity=identity,
                expected_persisted_version=AggregateVersion(2),
                actor="tester",
                occurred_at=_OCCURRED_AT,
            )
        )


def test_invalid_state_raises_domain_value_error(
    campaign_repo: PostgresCampaignRepository,
    run_repo: PostgresRunRepository,
    evidence_package_repo: PostgresEvidencePackageRepository,
) -> None:
    """An already-SEALED package cannot be sealed a second time."""
    identity = _persist_sealable_evidence_package(
        campaign_repo,
        run_repo,
        evidence_package_repo,
        campaign_governance_id="CAMP-0004",
        run_governance_id="RUN-0004",
        evidence_package_governance_id="EVID-0004",
    )

    handler = SealEvidencePackageHandler(evidence_package_repository=evidence_package_repo)
    entry_point = CommandEntryPoint(handler)
    entry_point(
        SealEvidencePackageCommand(
            identity=identity,
            expected_persisted_version=AggregateVersion(3),
            actor="tester",
            occurred_at=_OCCURRED_AT,
        )
    )

    with pytest.raises(ValueError, match="cannot transition from"):
        entry_point(
            SealEvidencePackageCommand(
                identity=identity,
                expected_persisted_version=AggregateVersion(4),
                actor="tester",
                occurred_at=_OCCURRED_AT,
            )
        )


def test_missing_full_identity_raises_aggregate_not_found(
    evidence_package_repo: PostgresEvidencePackageRepository,
) -> None:
    missing_identity = DomainIdentity(
        governance_id=EvidencePackageId("EVID-9999"),
        runtime_id=RuntimeIdentifier(_MISSING_RUNTIME_ID_VALUE),
    )
    handler = SealEvidencePackageHandler(evidence_package_repository=evidence_package_repo)
    entry_point = CommandEntryPoint(handler)

    with pytest.raises(AggregateNotFound):
        entry_point(
            SealEvidencePackageCommand(
                identity=missing_identity,
                expected_persisted_version=AggregateVersion.initial(),
                actor="tester",
                occurred_at=_OCCURRED_AT,
            )
        )


def test_stale_expected_version_raises_genuine_optimistic_concurrency_conflict(
    campaign_repo: PostgresCampaignRepository,
    run_repo: PostgresRunRepository,
    evidence_package_repo: PostgresEvidencePackageRepository,
) -> None:
    identity = _persist_sealable_evidence_package(
        campaign_repo,
        run_repo,
        evidence_package_repo,
        campaign_governance_id="CAMP-0005",
        run_governance_id="RUN-0005",
        evidence_package_governance_id="EVID-0005",
    )

    # Simulate an interfering writer: independently reload the same identity
    # and advance the persisted version via add_artifact_reference() -- an
    # arbitrary but fixed choice among the two frozen, state-preserving
    # owned-collection-append methods, preserving COLLECTING so the command
    # under test can still execute seal() afterward. Test setup only; never
    # invoked as an interfering write by any production code.
    interfering = evidence_package_repo.get(identity)
    interfering.aggregate.add_artifact_reference(ArtifactReference(value="interfering-writer"))
    evidence_package_repo.save(
        interfering.aggregate, expected_persisted_version=AggregateVersion(3)
    )

    handler = SealEvidencePackageHandler(evidence_package_repository=evidence_package_repo)
    entry_point = CommandEntryPoint(handler)

    with pytest.raises(OptimisticConcurrencyConflict):
        entry_point(
            SealEvidencePackageCommand(
                identity=identity,
                expected_persisted_version=AggregateVersion(3),  # stale: real durable version is 4
                actor="tester",
                occurred_at=_OCCURRED_AT,
            )
        )

    # The command-under-test's own seal was never persisted -- the
    # interfering writer's second artifact reference remains the only
    # durable change beyond the initial setup, and the package remains
    # COLLECTING, not SEALED.
    loaded = evidence_package_repo.get(identity)
    assert loaded.persisted_version == AggregateVersion(4)
    assert loaded.aggregate.state is EvidencePackageLifecycleState.COLLECTING
    assert len(loaded.aggregate.artifact_references) == 2


def test_no_production_composition_machinery_is_required(
    campaign_repo: PostgresCampaignRepository,
    run_repo: PostgresRunRepository,
    evidence_package_repo: PostgresEvidencePackageRepository,
) -> None:
    """The handler is constructed directly from the externally-obtained
    repository -- no FoundationRuntime, no registry, no composition root
    of any kind."""
    identity = _persist_sealable_evidence_package(
        campaign_repo,
        run_repo,
        evidence_package_repo,
        campaign_governance_id="CAMP-0099",
        run_governance_id="RUN-0099",
        evidence_package_governance_id="EVID-0099",
    )

    handler = SealEvidencePackageHandler(evidence_package_repository=evidence_package_repo)
    result = handler.handle(
        SealEvidencePackageCommand(
            identity=identity,
            expected_persisted_version=AggregateVersion(3),
            actor="tester",
            occurred_at=_OCCURRED_AT,
        )
    )

    assert result.operation is SaveOperation.UPDATED
    assert result.persisted_version == AggregateVersion(4)
