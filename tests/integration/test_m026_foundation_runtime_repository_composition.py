"""MILESTONE-026 real-PostgreSQL integration tests for Foundation Runtime
Repository Composition.

Exercises `initialize_infrastructure_runtime` and
`initialize_foundation_runtime_with_postgresql` against a real, migrated
PostgreSQL database, proving the bootstrap-composed `repository_runtime`
field works end-to-end through the actual, frozen M023 repository adapters
(never mocked): same-service identity, standalone add/get, cross-aggregate
atomic `run_composed`, post-close failure, and repr/credential safety
against a genuine `PostgresPersistenceService`.

Opt-in via ``EMPIRICAL_PLATFORM_RUN_POSTGRES_TESTS=1``, following the same
convention as ``tests/integration/test_m025_postgres_repository_runtime.py``.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from pydantic import SecretStr
from sqlalchemy import text
from sqlalchemy.engine import Engine

from empirical_platform.campaign.aggregate import Campaign, CampaignScopeStatement
from empirical_platform.identifiers.pairs import DomainIdentity
from empirical_platform.identifiers.types import CampaignId, RunId
from empirical_platform.run.aggregate import Run
from empirical_platform.shared.bootstrap import (
    initialize_foundation_runtime_with_postgresql,
    initialize_infrastructure_runtime,
)
from empirical_platform.shared.config.settings import PostgreSQLConfigSnapshot
from empirical_platform.shared.errors import FoundationError
from empirical_platform.shared.identifiers import RuntimeIdentifier
from empirical_platform.shared.object_storage.fake import FakeObjectStorageService
from empirical_platform.shared.persistence.postgres import PostgresPersistenceService
from empirical_platform.shared.persistence.postgres_repositories.runtime import (
    PostgresRepositoryRuntime,
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
    "campaign",
]


def _integration_enabled() -> bool:
    return os.environ.get("EMPIRICAL_PLATFORM_RUN_POSTGRES_TESTS") == "1"


def _real_password() -> str:
    return os.environ["EMPIRICAL_PLATFORM_POSTGRES_PASSWORD"]


def _config() -> PostgreSQLConfigSnapshot:
    return PostgreSQLConfigSnapshot(
        host=os.environ.get("EMPIRICAL_PLATFORM_POSTGRES_HOST", "localhost"),
        port=int(os.environ.get("EMPIRICAL_PLATFORM_POSTGRES_PORT", "5432")),
        database=os.environ.get("EMPIRICAL_PLATFORM_POSTGRES_DATABASE", "empirical_platform"),
        user=os.environ.get("EMPIRICAL_PLATFORM_POSTGRES_USER", "empirical"),
        password=SecretStr(_real_password()),
        pool_size=2,
        max_overflow=0,
        connection_timeout_seconds=5,
        application_name="empirical-platform-m026-test",
    )


def _alembic_config() -> Config:
    cfg = Config(str(_REPO_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(_REPO_ROOT / "migrations"))
    return cfg


def _reset_public_schema(engine: Engine) -> None:
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))


def _runtime_id() -> RuntimeIdentifier:
    return RuntimeIdentifier(str(uuid.uuid4()))


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
    command.upgrade(_alembic_config(), "head")
    yield engine
    _reset_public_schema(engine)


@pytest.fixture
def clean_tables(upgraded_schema: Engine) -> Engine:
    with upgraded_schema.begin() as conn:
        conn.execute(text(f"TRUNCATE {', '.join(_ALL_TABLES)} CASCADE"))  # noqa: S608
    return upgraded_schema


@pytest.fixture
def _tables_ready(clean_tables: Engine) -> None:
    return None


# --- Bootstrap-composed construction, against real PostgreSQL ---------------


def test_foundation_runtime_with_postgresql_produces_working_repository_runtime(
    _tables_ready: None,
) -> None:
    runtime = initialize_foundation_runtime_with_postgresql(
        {"EMPIRICAL_PLATFORM_ENVIRONMENT": "test"},
        persistence=PostgresPersistenceService(_config()),
    )
    try:
        assert runtime.repository_runtime is not None
        assert isinstance(runtime.repository_runtime, PostgresRepositoryRuntime)
        assert runtime.repository_runtime._service is runtime.persistence

        identity = DomainIdentity(governance_id=CampaignId("CAMP-0001"), runtime_id=_runtime_id())
        runtime.repository_runtime.campaigns.add(
            Campaign(identity=identity, scope_statement=CampaignScopeStatement("m026-scope"))
        )
        loaded = runtime.repository_runtime.campaigns.get(identity)
        assert loaded.aggregate.identity == identity
    finally:
        runtime.persistence.close()  # type: ignore[union-attr]


def test_initialize_infrastructure_runtime_produces_working_repository_runtime(
    _tables_ready: None,
) -> None:
    runtime = initialize_infrastructure_runtime(
        {
            "EMPIRICAL_PLATFORM_ENVIRONMENT": "test",
            "EMPIRICAL_PLATFORM_OBJECT_STORAGE_ACCESS_KEY": "-".join(("m026", "access")),
            "EMPIRICAL_PLATFORM_OBJECT_STORAGE_SECRET_KEY": "-".join(("m026", "secret")),
        },
        persistence=PostgresPersistenceService(_config()),
        object_storage=FakeObjectStorageService(),
    )
    try:
        assert runtime.repository_runtime is not None
        assert runtime.repository_runtime._service is runtime.persistence

        identity = DomainIdentity(governance_id=CampaignId("CAMP-0002"), runtime_id=_runtime_id())
        runtime.repository_runtime.campaigns.add(
            Campaign(identity=identity, scope_statement=CampaignScopeStatement("m026-infra-scope"))
        )
        assert runtime.repository_runtime.campaigns.get(identity).aggregate.identity == identity
    finally:
        runtime.close()


def test_same_root_run_composed_succeeds_atomically(_tables_ready: None) -> None:
    runtime = initialize_foundation_runtime_with_postgresql(
        {"EMPIRICAL_PLATFORM_ENVIRONMENT": "test"},
        persistence=PostgresPersistenceService(_config()),
    )
    try:
        assert runtime.repository_runtime is not None
        composed = runtime.repository_runtime

        campaign_identity = DomainIdentity(
            governance_id=CampaignId("CAMP-0003"), runtime_id=_runtime_id()
        )
        run_identity = DomainIdentity(governance_id=RunId("RUN-0003"), runtime_id=_runtime_id())

        def add_campaign() -> object:
            return composed.campaigns.add(
                Campaign(identity=campaign_identity, scope_statement=CampaignScopeStatement("m026"))
            )

        def add_run() -> object:
            return composed.runs.add(
                Run(identity=run_identity, campaign_id=CampaignId("CAMP-0003"))
            )

        composed.run_composed([add_campaign, add_run])

        assert composed.campaigns.get(campaign_identity).aggregate.identity == campaign_identity
        assert composed.runs.get(run_identity).aggregate.identity == run_identity
    finally:
        runtime.persistence.close()  # type: ignore[union-attr]


def test_close_makes_repository_operations_fail_safely(_tables_ready: None) -> None:
    runtime = initialize_foundation_runtime_with_postgresql(
        {"EMPIRICAL_PLATFORM_ENVIRONMENT": "test"},
        persistence=PostgresPersistenceService(_config()),
    )
    runtime.close()

    assert runtime.repository_runtime is not None
    identity = DomainIdentity(governance_id=CampaignId("CAMP-0004"), runtime_id=_runtime_id())
    with pytest.raises(FoundationError, match="closed"):
        runtime.repository_runtime.campaigns.add(
            Campaign(identity=identity, scope_statement=CampaignScopeStatement("m026-closed"))
        )
    with pytest.raises(FoundationError, match="closed"):
        runtime.repository_runtime.campaigns.get(identity)


# --- Repr / credential safety against a genuine PostgresPersistenceService --


def test_repr_does_not_expose_real_credentials(_tables_ready: None) -> None:
    real_password = _real_password()
    runtime = initialize_foundation_runtime_with_postgresql(
        {"EMPIRICAL_PLATFORM_ENVIRONMENT": "test"},
        persistence=PostgresPersistenceService(_config()),
    )
    try:
        assert runtime.repository_runtime is not None
        reprs = [
            repr(runtime),
            repr(runtime.repository_runtime),
            repr(runtime.repository_runtime.campaigns),
            repr(runtime.repository_runtime.runs),
            repr(runtime.repository_runtime.evidence_packages),
            repr(runtime.repository_runtime.reviews),
        ]
        for value in reprs:
            assert real_password not in value
            assert "postgresql://" not in value
    finally:
        runtime.persistence.close()  # type: ignore[union-attr]
