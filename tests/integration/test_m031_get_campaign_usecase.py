"""MILESTONE-031 real-PostgreSQL integration tests for `GetCampaignHandler`.

Exercises the full frozen vertical slice against a real, migrated
PostgreSQL database (never mocked): `QueryEntryPoint` -> concrete
`GetCampaignHandler` -> the real, frozen `PostgresCampaignRepository` ->
PostgreSQL -> `CampaignSnapshot`. The `CampaignRepository` instance is
obtained externally (this test's own fixtures), exactly as the frozen
design requires -- the `usecases` package itself never imports
persistence. A Campaign is first persisted through the existing, frozen
M030 `CreateCampaignHandler`, reusing the identical fixture pattern
`tests/integration/test_m030_create_campaign_usecase.py` already
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
from empirical_platform.campaign.lifecycle import CampaignLifecycleState
from empirical_platform.identifiers.pairs import DomainIdentity
from empirical_platform.identifiers.types import CampaignId
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
from empirical_platform.usecases.create_campaign import (
    CreateCampaignCommand,
    CreateCampaignHandler,
)
from empirical_platform.usecases.get_campaign import (
    CampaignSnapshot,
    GetCampaignHandler,
    GetCampaignQuery,
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
        application_name="empirical-platform-m031-test",
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


def _persist_campaign(
    campaign_repo: PostgresCampaignRepository,
    *,
    governance_id: str,
    runtime_id: str,
    scope_statement: str,
) -> DomainIdentity[CampaignId]:
    create_handler = CreateCampaignHandler(
        campaign_repository=campaign_repo,
        runtime_identifier_generator=DeterministicRuntimeIdentifierGenerator([runtime_id]),
    )
    create_entry_point = CommandEntryPoint(create_handler)
    return create_entry_point(
        CreateCampaignCommand(campaign_governance_id=governance_id, scope_statement=scope_statement)
    )


def test_golden_path_retrieves_via_query_entry_point_and_real_repository(
    campaign_repo: PostgresCampaignRepository,
) -> None:
    identity = _persist_campaign(
        campaign_repo,
        governance_id="CAMP-0001",
        runtime_id=_RUNTIME_ID_VALUE,
        scope_statement="integration test scope",
    )

    get_handler = GetCampaignHandler(campaign_repository=campaign_repo)
    get_entry_point = QueryEntryPoint(get_handler)

    snapshot = get_entry_point(GetCampaignQuery(identity=identity))

    assert isinstance(snapshot, CampaignSnapshot)
    assert snapshot.identity == identity
    assert str(snapshot.scope_statement) == "integration test scope"
    assert snapshot.state is CampaignLifecycleState.DRAFT


def test_missing_full_identity_raises_aggregate_not_found(
    campaign_repo: PostgresCampaignRepository,
) -> None:
    _persist_campaign(
        campaign_repo,
        governance_id="CAMP-0001",
        runtime_id=_RUNTIME_ID_VALUE,
        scope_statement="a persisted campaign",
    )
    missing_identity = DomainIdentity(
        governance_id=CampaignId("CAMP-9999"),
        runtime_id=RuntimeIdentifier(_MISSING_RUNTIME_ID_VALUE),
    )
    get_handler = GetCampaignHandler(campaign_repository=campaign_repo)
    get_entry_point = QueryEntryPoint(get_handler)

    with pytest.raises(AggregateNotFound):
        get_entry_point(GetCampaignQuery(identity=missing_identity))


def test_no_production_composition_machinery_is_required(
    campaign_repo: PostgresCampaignRepository,
) -> None:
    """The handler is constructed directly from the externally-obtained
    repository -- no FoundationRuntime, no registry, no composition root
    of any kind."""
    identity = _persist_campaign(
        campaign_repo,
        governance_id="CAMP-0099",
        runtime_id=_RUNTIME_ID_VALUE,
        scope_statement="direct call",
    )

    handler = GetCampaignHandler(campaign_repository=campaign_repo)
    result = handler.handle(GetCampaignQuery(identity=identity))

    assert isinstance(result, CampaignSnapshot)
    assert result.identity == identity
