"""MILESTONE-035 real-PostgreSQL integration tests for `AuthorizeRunHandler`.

Exercises the full frozen vertical slice against a real, migrated
PostgreSQL database (never mocked): `CommandEntryPoint` -> concrete
`AuthorizeRunHandler` -> `Run` aggregate -> the real, frozen
`PostgresRunRepository` -> PostgreSQL. The `RunRepository` instance is
obtained externally (this test's own fixtures), exactly as the frozen
design requires -- the `usecases` package itself never imports
persistence. A Campaign is first persisted through the existing, frozen
M030 `CreateCampaignHandler`, and a Run is then persisted through the
existing, frozen M033 `CreateRunHandler`, reusing the identical fixture
pattern `tests/integration/test_m032_prepare_campaign_for_authorization_usecase.py`
and `tests/integration/test_m034_get_run_usecase.py` already established.

The deterministic optimistic-concurrency conflict scenario is frozen
exactly by the M035 design freeze (Section 34): `Run` has no method
analogous to `Campaign.revise_scope_statement()`, so the interfering
write independently loads the same identity and calls
`Run.append_manifest()` -- never `authorize()` itself -- to advance the
persisted version while preserving `CREATED`, so the command under test
can still execute its own `authorize()` call before the stale-version
`save()` fails. `append_manifest()` is test setup only; it is never
invoked by any production code in this milestone.

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
from empirical_platform.campaign.lifecycle import RunLifecycleState
from empirical_platform.datasets import DatasetManifest
from empirical_platform.identifiers.pairs import DomainIdentity
from empirical_platform.identifiers.types import RunId
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
from empirical_platform.shared.persistence.postgres_repositories.run_repository import (
    PostgresRunRepository,
)
from empirical_platform.usecases.authorize_run import AuthorizeRunCommand, AuthorizeRunHandler
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
_CAMPAIGN_RUNTIME_ID_VALUE = "12345678-1234-4321-8765-1234567890ab"
_RUN_RUNTIME_ID_VALUE = "22345678-1234-4321-8765-1234567890ab"
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
        application_name="empirical-platform-m035-test",
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
    used only to seed a Campaign for Run creation."""
    return PostgresCampaignRepository(service)


@pytest.fixture
def run_repo(service: PostgresPersistenceService) -> PostgresRunRepository:
    """The real, frozen M023 RunRepository, obtained externally -- exactly
    as the frozen design requires; `usecases` never constructs this
    itself."""
    return PostgresRunRepository(service)


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
            campaign_governance_id=campaign_governance_id, scope_statement="initial scope"
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


def test_golden_path_authorizes_run_via_command_entry_point_and_real_repository(
    campaign_repo: PostgresCampaignRepository,
    run_repo: PostgresRunRepository,
) -> None:
    identity = _persist_run(
        campaign_repo, run_repo, campaign_governance_id="CAMP-0001", run_governance_id="RUN-0001"
    )

    handler = AuthorizeRunHandler(run_repository=run_repo)
    entry_point = CommandEntryPoint(handler)
    command = AuthorizeRunCommand(
        identity=identity,
        expected_persisted_version=AggregateVersion(0),
        actor="tester",
        occurred_at=_OCCURRED_AT,
        correlation_id="corr-golden",
        reason="ready for acquisition",
    )

    result = entry_point(command)

    assert result.operation is SaveOperation.UPDATED
    assert result.persisted_version == AggregateVersion(1)

    reloaded = run_repo.get(identity)
    assert reloaded.aggregate.state is RunLifecycleState.AUTHORIZED
    assert reloaded.persisted_version == AggregateVersion(1)
    assert len(reloaded.aggregate.transition_history) == 1
    record = reloaded.aggregate.transition_history[-1]
    assert record.from_state == "CREATED"
    assert record.to_state == "AUTHORIZED"
    assert record.actor == "tester"
    assert record.correlation_id == "corr-golden"
    assert record.reason == "ready for acquisition"


def test_invalid_transition_raises_domain_error_without_persisting(
    campaign_repo: PostgresCampaignRepository,
    run_repo: PostgresRunRepository,
) -> None:
    identity = _persist_run(
        campaign_repo, run_repo, campaign_governance_id="CAMP-0002", run_governance_id="RUN-0002"
    )

    handler = AuthorizeRunHandler(run_repository=run_repo)
    entry_point = CommandEntryPoint(handler)
    first_command = AuthorizeRunCommand(
        identity=identity,
        expected_persisted_version=AggregateVersion(0),
        actor="tester",
        occurred_at=_OCCURRED_AT,
    )
    entry_point(first_command)  # CREATED -> AUTHORIZED, succeeds

    second_command = AuthorizeRunCommand(
        identity=identity,
        expected_persisted_version=AggregateVersion(1),
        actor="tester",
        occurred_at=_OCCURRED_AT,
    )

    with pytest.raises(ValueError, match="cannot transition from"):
        entry_point(second_command)

    reloaded = run_repo.get(identity)
    assert reloaded.aggregate.state is RunLifecycleState.AUTHORIZED
    assert reloaded.persisted_version == AggregateVersion(1)
    assert len(reloaded.aggregate.transition_history) == 1


def test_missing_run_raises_aggregate_not_found(
    run_repo: PostgresRunRepository,
) -> None:
    missing_identity = DomainIdentity(
        governance_id=RunId("RUN-9999"),
        runtime_id=RuntimeIdentifier(_MISSING_RUNTIME_ID_VALUE),
    )
    handler = AuthorizeRunHandler(run_repository=run_repo)
    entry_point = CommandEntryPoint(handler)
    command = AuthorizeRunCommand(
        identity=missing_identity,
        expected_persisted_version=AggregateVersion(0),
        actor="tester",
        occurred_at=_OCCURRED_AT,
    )

    with pytest.raises(AggregateNotFound):
        entry_point(command)


def test_stale_expected_version_raises_optimistic_concurrency_conflict(
    campaign_repo: PostgresCampaignRepository,
    run_repo: PostgresRunRepository,
) -> None:
    identity = _persist_run(
        campaign_repo, run_repo, campaign_governance_id="CAMP-0003", run_governance_id="RUN-0003"
    )

    # Simulate an interfering writer: independently reload the same identity
    # and advance the persisted version via append_manifest() -- the only
    # existing Run mutation that bumps AggregateVersion without changing
    # lifecycle state, preserving CREATED so the command under test can
    # still execute authorize() afterward. Test setup only; never invoked
    # by any production code.
    interfering = run_repo.get(identity)
    interfering.aggregate.append_manifest(
        DatasetManifest(
            run_id=identity.governance_id,
            recorded_at=_OCCURRED_AT,
            source="interfering-writer",
        )
    )
    run_repo.save(interfering.aggregate, expected_persisted_version=AggregateVersion(0))

    advanced = run_repo.get(identity)
    assert advanced.persisted_version == AggregateVersion(1)
    assert advanced.aggregate.state is RunLifecycleState.CREATED
    assert len(advanced.aggregate.manifests) == 1

    handler = AuthorizeRunHandler(run_repository=run_repo)
    entry_point = CommandEntryPoint(handler)
    stale_command = AuthorizeRunCommand(
        identity=identity,
        expected_persisted_version=AggregateVersion(0),
        actor="tester",
        occurred_at=_OCCURRED_AT,
    )

    with pytest.raises(OptimisticConcurrencyConflict) as excinfo:
        entry_point(stale_command)

    assert excinfo.value.expected_persisted_version == AggregateVersion(0)
    assert excinfo.value.actual_persisted_version == AggregateVersion(1)

    reloaded = run_repo.get(identity)
    assert reloaded.aggregate.state is RunLifecycleState.CREATED
    assert reloaded.persisted_version == AggregateVersion(1)
    assert len(reloaded.aggregate.manifests) == 1
    assert reloaded.aggregate.manifests[0].source == "interfering-writer"
    assert len(reloaded.aggregate.transition_history) == 0


def test_no_production_composition_machinery_is_required(
    campaign_repo: PostgresCampaignRepository,
    run_repo: PostgresRunRepository,
) -> None:
    """The handler is constructed directly from the externally-obtained
    repository -- no FoundationRuntime, no registry, no composition root
    of any kind."""
    identity = _persist_run(
        campaign_repo, run_repo, campaign_governance_id="CAMP-0004", run_governance_id="RUN-0004"
    )

    handler = AuthorizeRunHandler(run_repository=run_repo)
    result = handler.handle(
        AuthorizeRunCommand(
            identity=identity,
            expected_persisted_version=AggregateVersion(0),
            actor="tester",
            occurred_at=_OCCURRED_AT,
        )
    )

    assert result.operation is SaveOperation.UPDATED
