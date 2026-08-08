"""MILESTONE-052 real-PostgreSQL integration tests for the
`entrypoints.create_campaign` composition root.

Exercises `run_create_campaign()` itself -- the first entrypoint to
exercise the repository's `.add()` code path and the first production
construction of `UuidRuntimeIdentifierGenerator`, completing a real-world-
usable create -> retrieve -> cancel trio for Campaign alongside
MILESTONE-050's `get_campaign` and MILESTONE-051's `cancel_campaign`.
Composition chain: environment-shaped configuration -> real
`PostgresPersistenceService` -> the frozen M025 `PostgresRepositoryRuntime`
-> the frozen M030 `CreateCampaignHandler` -> the frozen `CommandEntryPoint`
-> `DomainIdentity[CampaignId]`.

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

from empirical_platform.entrypoints.create_campaign import run_create_campaign
from empirical_platform.shared.config.settings import PostgreSQLConfigSnapshot
from empirical_platform.shared.contracts.repository import AggregateAlreadyExists
from empirical_platform.shared.identifiers import DeterministicRuntimeIdentifierGenerator

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
        application_name="empirical-platform-m052-test",
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


def test_golden_path_creates_a_real_campaign_with_real_uuid_generator(
    clean_tables: Engine,
) -> None:
    """Golden path using the real, production-default `UuidRuntimeIdentifierGenerator`
    -- not a deterministic override -- proving the first-ever production
    construction of that generator produces a genuinely valid, persisted
    Campaign, independently verified via direct SQL read-back."""
    identity = run_create_campaign(
        campaign_governance_id="CAMP-0001",
        scope_statement="a real end-to-end scope statement",
        config=_config(),
    )

    assert str(identity.governance_id) == "CAMP-0001"

    engine = sa.create_engine(_config().sqlalchemy_url())
    with engine.connect() as conn:
        row = (
            conn.execute(
                text(
                    "SELECT governance_id, runtime_id, scope_statement, lifecycle_state, version "
                    "FROM campaign WHERE governance_id = :g"
                ),
                {"g": "CAMP-0001"},
            )
            .mappings()
            .one()
        )
    engine.dispose()

    assert row["governance_id"] == "CAMP-0001"
    assert str(row["runtime_id"]) == str(identity.runtime_id)
    assert row["scope_statement"] == "a real end-to-end scope statement"
    assert row["lifecycle_state"] == "DRAFT"
    assert row["version"] == 0


def test_deterministic_generator_override_produces_exact_identity(
    clean_tables: Engine,
) -> None:
    identity = run_create_campaign(
        campaign_governance_id="CAMP-0002",
        scope_statement="deterministic scope",
        identifier_generator=DeterministicRuntimeIdentifierGenerator([_RUNTIME_ID_VALUE]),
        config=_config(),
    )

    assert str(identity.governance_id) == "CAMP-0002"
    assert str(identity.runtime_id) == _RUNTIME_ID_VALUE


def test_duplicate_governance_id_raises_aggregate_already_exists(
    clean_tables: Engine,
) -> None:
    run_create_campaign(
        campaign_governance_id="CAMP-0003",
        scope_statement="first campaign",
        identifier_generator=DeterministicRuntimeIdentifierGenerator(
            ["22345678-1234-4321-8765-1234567890ab"]
        ),
        config=_config(),
    )

    with pytest.raises(AggregateAlreadyExists):
        run_create_campaign(
            campaign_governance_id="CAMP-0003",
            scope_statement="a conflicting second campaign",
            identifier_generator=DeterministicRuntimeIdentifierGenerator(
                ["32345678-1234-4321-8765-1234567890ab"]
            ),
            config=_config(),
        )


def test_malformed_governance_id_raises_value_error(clean_tables: Engine) -> None:
    with pytest.raises(ValueError, match="."):
        run_create_campaign(
            campaign_governance_id="not-a-valid-governance-id",
            scope_statement="should never persist",
            config=_config(),
        )


def test_default_config_resolves_from_environment(
    monkeypatch: pytest.MonkeyPatch,
    clean_tables: Engine,
) -> None:
    """Proves the production default path -- omitting `config` -- really
    resolves through `resolve_foundation_config()` against this same
    disposable database, not just the explicit-override path every other
    test in this file exercises."""
    config = _config()
    monkeypatch.setenv("EMPIRICAL_PLATFORM_POSTGRES_HOST", config.host)
    monkeypatch.setenv("EMPIRICAL_PLATFORM_POSTGRES_PORT", str(config.port))
    monkeypatch.setenv("EMPIRICAL_PLATFORM_POSTGRES_DATABASE", config.database)
    monkeypatch.setenv("EMPIRICAL_PLATFORM_POSTGRES_USER", config.user)
    monkeypatch.setenv("EMPIRICAL_PLATFORM_POSTGRES_PASSWORD", config.password.get_secret_value())

    identity = run_create_campaign(
        campaign_governance_id="CAMP-0004",
        scope_statement="env-resolved creation",
        identifier_generator=DeterministicRuntimeIdentifierGenerator(
            ["42345678-1234-4321-8765-1234567890ab"]
        ),
    )

    assert str(identity.governance_id) == "CAMP-0004"
