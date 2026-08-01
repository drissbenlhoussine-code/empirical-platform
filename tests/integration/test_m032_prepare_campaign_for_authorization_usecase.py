"""MILESTONE-032 real-PostgreSQL integration tests for
`PrepareCampaignForAuthorizationHandler`.

Exercises the full frozen vertical slice against a real, migrated PostgreSQL
database (never mocked): `CommandEntryPoint` -> concrete
`PrepareCampaignForAuthorizationHandler` -> `Campaign` aggregate -> the real,
frozen `PostgresCampaignRepository` -> PostgreSQL. The `CampaignRepository`
instance is obtained externally (this test's own fixtures), exactly as the
frozen design requires -- the `usecases` package itself never imports
persistence. A Campaign is first persisted through the existing, frozen M030
`CreateCampaignHandler`, reusing the identical fixture pattern
`tests/integration/test_m030_create_campaign_usecase.py` and
`tests/integration/test_m031_get_campaign_usecase.py` already established.

The deterministic optimistic-concurrency conflict scenario is frozen exactly
by the M032 design freeze (Section 25): the interfering write independently
loads the same identity and calls `Campaign.revise_scope_statement()` --
never `prepare_for_authorization()` itself -- to advance the persisted
version while preserving `DRAFT`, so the command under test can still
execute its own `prepare_for_authorization()` call before the stale-version
`save()` fails. `revise_scope_statement()` is test setup only; it is never
invoked by any production code.

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
from empirical_platform.campaign.aggregate import CampaignScopeStatement
from empirical_platform.campaign.lifecycle import CampaignLifecycleState
from empirical_platform.identifiers.pairs import DomainIdentity
from empirical_platform.identifiers.types import CampaignId
from empirical_platform.shared.config.settings import PostgreSQLConfigSnapshot
from empirical_platform.shared.contracts.repository import (
    OptimisticConcurrencyConflict,
    SaveOperation,
)
from empirical_platform.shared.domain.versioning import AggregateVersion
from empirical_platform.shared.identifiers import DeterministicRuntimeIdentifierGenerator
from empirical_platform.shared.persistence.postgres import PostgresPersistenceService
from empirical_platform.shared.persistence.postgres_repositories.campaign_repository import (
    PostgresCampaignRepository,
)
from empirical_platform.usecases.create_campaign import (
    CreateCampaignCommand,
    CreateCampaignHandler,
)
from empirical_platform.usecases.prepare_campaign_for_authorization import (
    PrepareCampaignForAuthorizationCommand,
    PrepareCampaignForAuthorizationHandler,
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
_RUNTIME_ID_VALUE = "12345678-1234-4321-8765-1234567890ab"
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
        application_name="empirical-platform-m032-test",
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
    exactly as the frozen design requires; `usecases` never constructs
    this itself."""
    return PostgresCampaignRepository(service)


def _persist_draft_campaign(
    campaign_repo: PostgresCampaignRepository,
    *,
    governance_id: str,
    runtime_id: str = _RUNTIME_ID_VALUE,
    scope_statement: str = "initial scope",
) -> DomainIdentity[CampaignId]:
    create_handler = CreateCampaignHandler(
        campaign_repository=campaign_repo,
        runtime_identifier_generator=DeterministicRuntimeIdentifierGenerator([runtime_id]),
    )
    create_entry_point = CommandEntryPoint(create_handler)
    return create_entry_point(
        CreateCampaignCommand(campaign_governance_id=governance_id, scope_statement=scope_statement)
    )


def test_golden_path_transitions_campaign_via_command_entry_point_and_real_repository(
    campaign_repo: PostgresCampaignRepository,
) -> None:
    identity = _persist_draft_campaign(campaign_repo, governance_id="CAMP-0001")

    handler = PrepareCampaignForAuthorizationHandler(campaign_repository=campaign_repo)
    entry_point = CommandEntryPoint(handler)
    command = PrepareCampaignForAuthorizationCommand(
        identity=identity,
        expected_persisted_version=AggregateVersion(0),
        actor="tester",
        occurred_at=_OCCURRED_AT,
        correlation_id="corr-golden",
        reason="ready for review",
    )

    result = entry_point(command)

    assert result.operation is SaveOperation.UPDATED
    assert result.persisted_version == AggregateVersion(1)

    reloaded = campaign_repo.get(identity)
    assert reloaded.aggregate.state is CampaignLifecycleState.READY_FOR_AUTHORIZATION
    assert reloaded.persisted_version == AggregateVersion(1)
    record = reloaded.aggregate.transition_history[-1]
    assert record.actor == "tester"
    assert record.correlation_id == "corr-golden"
    assert record.reason == "ready for review"


def test_stale_expected_version_raises_optimistic_concurrency_conflict(
    campaign_repo: PostgresCampaignRepository,
) -> None:
    identity = _persist_draft_campaign(campaign_repo, governance_id="CAMP-0002")

    # Simulate an interfering writer: independently reload the same identity and
    # advance the persisted version via revise_scope_statement() -- the one
    # existing Campaign mutation that bumps AggregateVersion without changing
    # lifecycle state, preserving DRAFT so the command under test can still
    # execute prepare_for_authorization() afterward. Test setup only; never
    # invoked by production code.
    interfering = campaign_repo.get(identity)
    interfering.aggregate.revise_scope_statement(
        CampaignScopeStatement("revised by another writer")
    )
    campaign_repo.save(interfering.aggregate, expected_persisted_version=AggregateVersion(0))

    advanced = campaign_repo.get(identity)
    assert advanced.persisted_version == AggregateVersion(1)
    assert advanced.aggregate.state is CampaignLifecycleState.DRAFT

    handler = PrepareCampaignForAuthorizationHandler(campaign_repository=campaign_repo)
    entry_point = CommandEntryPoint(handler)
    stale_command = PrepareCampaignForAuthorizationCommand(
        identity=identity,
        expected_persisted_version=AggregateVersion(0),
        actor="tester",
        occurred_at=_OCCURRED_AT,
    )

    with pytest.raises(OptimisticConcurrencyConflict) as excinfo:
        entry_point(stale_command)

    assert excinfo.value.expected_persisted_version == AggregateVersion(0)
    assert excinfo.value.actual_persisted_version == AggregateVersion(1)

    reloaded = campaign_repo.get(identity)
    assert reloaded.aggregate.state is CampaignLifecycleState.DRAFT
    assert str(reloaded.aggregate.scope_statement) == "revised by another writer"
    assert reloaded.persisted_version == AggregateVersion(1)


def test_invalid_transition_raises_domain_error_without_persisting(
    campaign_repo: PostgresCampaignRepository,
) -> None:
    identity = _persist_draft_campaign(campaign_repo, governance_id="CAMP-0003")

    handler = PrepareCampaignForAuthorizationHandler(campaign_repository=campaign_repo)
    entry_point = CommandEntryPoint(handler)
    first_command = PrepareCampaignForAuthorizationCommand(
        identity=identity,
        expected_persisted_version=AggregateVersion(0),
        actor="tester",
        occurred_at=_OCCURRED_AT,
    )
    entry_point(first_command)  # DRAFT -> READY_FOR_AUTHORIZATION, succeeds

    second_command = PrepareCampaignForAuthorizationCommand(
        identity=identity,
        expected_persisted_version=AggregateVersion(1),
        actor="tester",
        occurred_at=_OCCURRED_AT,
    )

    with pytest.raises(ValueError, match="cannot transition from"):
        entry_point(second_command)

    reloaded = campaign_repo.get(identity)
    assert reloaded.aggregate.state is CampaignLifecycleState.READY_FOR_AUTHORIZATION
    assert reloaded.persisted_version == AggregateVersion(1)
