"""MILESTONE-050 real-PostgreSQL integration tests for the
`entrypoints.get_campaign` composition root.

Exercises `run_get_campaign()` itself -- not the already-frozen M031
vertical slice in isolation, but the full, real, first-in-production
composition chain: environment-shaped configuration -> real
`PostgresPersistenceService` -> the frozen M025 `PostgresRepositoryRuntime`
-> the frozen M031 `GetCampaignHandler` -> the frozen `QueryEntryPoint` ->
`CampaignSnapshot`. A Campaign is first persisted through the existing,
frozen M030 `CreateCampaignHandler`, reusing the identical fixture pattern
`tests/integration/test_m031_get_campaign_usecase.py` already established,
via a `PostgresCampaignRepository` obtained through the same
`PostgresRepositoryRuntime` this milestone's own production code composes.

Opt-in via ``EMPIRICAL_PLATFORM_RUN_POSTGRES_TESTS=1``, following the same
convention as every prior milestone's own PostgreSQL integration tests.
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
from empirical_platform.campaign.lifecycle import CampaignLifecycleState
from empirical_platform.entrypoints.get_campaign import run_get_campaign
from empirical_platform.identifiers.pairs import DomainIdentity
from empirical_platform.identifiers.types import CampaignId
from empirical_platform.shared.config.settings import PostgreSQLConfigSnapshot
from empirical_platform.shared.contracts.repository import AggregateNotFound
from empirical_platform.shared.identifiers import DeterministicRuntimeIdentifierGenerator
from empirical_platform.shared.persistence.postgres import PostgresPersistenceService
from empirical_platform.shared.persistence.postgres_repositories.runtime import (
    PostgresRepositoryRuntime,
)
from empirical_platform.usecases.create_campaign import (
    CreateCampaignCommand,
    CreateCampaignHandler,
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
        application_name="empirical-platform-m050-test",
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
def seeding_service(clean_tables: Engine) -> Iterator[PostgresPersistenceService]:
    """A second, independent `PostgresPersistenceService` used only to seed
    fixture data -- kept entirely separate from the service `run_get_campaign`
    itself constructs and owns, so the test never shares connection state
    with the real composition root under test."""
    svc = PostgresPersistenceService(_config())
    svc.initialize()
    try:
        yield svc
    finally:
        svc.close()


def _persist_campaign(
    seeding_service: PostgresPersistenceService,
    *,
    governance_id: str,
    runtime_id: str,
    scope_statement: str,
) -> DomainIdentity[CampaignId]:
    runtime = PostgresRepositoryRuntime(seeding_service)
    create_handler = CreateCampaignHandler(
        campaign_repository=runtime.campaigns,
        runtime_identifier_generator=DeterministicRuntimeIdentifierGenerator([runtime_id]),
    )
    create_entry_point = CommandEntryPoint(create_handler)
    return create_entry_point(
        CreateCampaignCommand(campaign_governance_id=governance_id, scope_statement=scope_statement)
    )


def test_golden_path_retrieves_a_real_freshly_created_campaign(
    seeding_service: PostgresPersistenceService,
) -> None:
    identity = _persist_campaign(
        seeding_service,
        governance_id="CAMP-0001",
        runtime_id=_RUNTIME_ID_VALUE,
        scope_statement="M050 end-to-end composition test scope",
    )

    snapshot = run_get_campaign(
        campaign_governance_id=str(identity.governance_id),
        campaign_runtime_id=str(identity.runtime_id),
        config=_config(),
    )

    assert snapshot.identity == identity
    assert str(snapshot.scope_statement) == "M050 end-to-end composition test scope"
    assert snapshot.state is CampaignLifecycleState.DRAFT


def test_missing_campaign_raises_aggregate_not_found(
    seeding_service: PostgresPersistenceService,
) -> None:
    _persist_campaign(
        seeding_service,
        governance_id="CAMP-0001",
        runtime_id=_RUNTIME_ID_VALUE,
        scope_statement="a persisted campaign",
    )

    with pytest.raises(AggregateNotFound):
        run_get_campaign(
            campaign_governance_id="CAMP-9999",
            campaign_runtime_id=_MISSING_RUNTIME_ID_VALUE,
            config=_config(),
        )


def test_malformed_identifier_raises_value_error(
    clean_tables: Engine,
) -> None:
    with pytest.raises(ValueError, match="."):
        run_get_campaign(
            campaign_governance_id="",
            campaign_runtime_id="not-a-uuid",
            config=_config(),
        )


def test_default_config_resolves_from_environment(
    monkeypatch: pytest.MonkeyPatch,
    seeding_service: PostgresPersistenceService,
) -> None:
    """Proves the production default path -- omitting `config` -- really
    resolves through `resolve_foundation_config()` against this same
    disposable database, not just the explicit-override path every other
    test in this file exercises."""
    identity = _persist_campaign(
        seeding_service,
        governance_id="CAMP-0002",
        runtime_id="22222222-2222-4222-8222-222222222222",
        scope_statement="default-config resolution path",
    )
    config = _config()
    monkeypatch.setenv("EMPIRICAL_PLATFORM_POSTGRES_HOST", config.host)
    monkeypatch.setenv("EMPIRICAL_PLATFORM_POSTGRES_PORT", str(config.port))
    monkeypatch.setenv("EMPIRICAL_PLATFORM_POSTGRES_DATABASE", config.database)
    monkeypatch.setenv("EMPIRICAL_PLATFORM_POSTGRES_USER", config.user)
    monkeypatch.setenv("EMPIRICAL_PLATFORM_POSTGRES_PASSWORD", config.password.get_secret_value())

    snapshot = run_get_campaign(
        campaign_governance_id=str(identity.governance_id),
        campaign_runtime_id=str(identity.runtime_id),
    )

    assert snapshot.identity == identity
