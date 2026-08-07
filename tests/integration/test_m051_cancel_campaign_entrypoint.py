"""MILESTONE-051 real-PostgreSQL integration tests for the
`entrypoints.cancel_campaign` composition root.

Exercises `run_cancel_campaign()` itself -- the first write command ever
composed through a production entrypoint, pairing with MILESTONE-050's own
read-only `get_campaign` composition. Composition chain: environment-shaped
configuration -> real `PostgresPersistenceService` -> the frozen M025
`PostgresRepositoryRuntime` -> the frozen M047 `CancelCampaignHandler` ->
the frozen `CommandEntryPoint` -> `SaveResult`. A Campaign is first
persisted through the existing, frozen M030 `CreateCampaignHandler`, reusing
the identical fixture pattern `tests/integration/test_m047_cancel_campaign_usecase.py`
already established, via a `PostgresCampaignRepository` obtained through the
same `PostgresRepositoryRuntime` this milestone's own production code
composes.

The genuine `OptimisticConcurrencyConflict` reproduction reuses M047's own
frozen mechanism exactly: an independently-loaded interferer calls
`Campaign.revise_scope_statement()` (state-preserving from `DRAFT`) to
advance the persisted version while the stale caller's own captured version
becomes outdated -- proving, for the first time, that this genuine conflict
propagates correctly through a real production entrypoint, not only through
a handler invoked directly inside a test.

Opt-in via ``EMPIRICAL_PLATFORM_RUN_POSTGRES_TESTS=1``, following the same
convention as every prior milestone's own PostgreSQL integration tests.
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
from empirical_platform.entrypoints.cancel_campaign import run_cancel_campaign
from empirical_platform.identifiers.pairs import DomainIdentity
from empirical_platform.identifiers.types import CampaignId
from empirical_platform.shared.config.settings import PostgreSQLConfigSnapshot
from empirical_platform.shared.contracts.repository import (
    AggregateNotFound,
    OptimisticConcurrencyConflict,
    SaveOperation,
)
from empirical_platform.shared.domain.versioning import AggregateVersion
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
        application_name="empirical-platform-m051-test",
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
    and inspect fixture data -- kept entirely separate from the service
    `run_cancel_campaign` itself constructs and owns, so the test never
    shares connection state with the real composition root under test."""
    svc = PostgresPersistenceService(_config())
    svc.initialize()
    try:
        yield svc
    finally:
        svc.close()


def _persist_draft_campaign(
    seeding_service: PostgresPersistenceService,
    *,
    governance_id: str,
    runtime_id: str,
    scope_statement: str = "initial scope",
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


def test_golden_path_cancels_a_real_freshly_created_campaign(
    seeding_service: PostgresPersistenceService,
) -> None:
    identity = _persist_draft_campaign(
        seeding_service,
        governance_id="CAMP-0001",
        runtime_id=_RUNTIME_ID_VALUE,
    )

    result = run_cancel_campaign(
        campaign_governance_id=str(identity.governance_id),
        campaign_runtime_id=str(identity.runtime_id),
        expected_persisted_version=0,
        actor="tester",
        occurred_at=_OCCURRED_AT,
        reason="scope abandoned",
        correlation_id="corr-golden",
        config=_config(),
    )

    assert result.operation is SaveOperation.UPDATED
    assert result.persisted_version == AggregateVersion(1)

    runtime = PostgresRepositoryRuntime(seeding_service)
    reloaded = runtime.campaigns.get(identity)
    assert reloaded.aggregate.state is CampaignLifecycleState.CANCELLED
    assert reloaded.persisted_version == AggregateVersion(1)


def test_missing_campaign_raises_aggregate_not_found(
    seeding_service: PostgresPersistenceService,
) -> None:
    _persist_draft_campaign(
        seeding_service, governance_id="CAMP-0001", runtime_id=_RUNTIME_ID_VALUE
    )

    with pytest.raises(AggregateNotFound):
        run_cancel_campaign(
            campaign_governance_id="CAMP-9999",
            campaign_runtime_id=_MISSING_RUNTIME_ID_VALUE,
            expected_persisted_version=0,
            actor="tester",
            occurred_at=_OCCURRED_AT,
            reason="should never persist",
            config=_config(),
        )


def test_invalid_state_completed_raises_domain_error_without_persisting(
    seeding_service: PostgresPersistenceService,
) -> None:
    identity = _persist_draft_campaign(
        seeding_service,
        governance_id="CAMP-0002",
        runtime_id="22345678-1234-4321-8765-1234567890ab",
    )
    runtime = PostgresRepositoryRuntime(seeding_service)
    loaded = runtime.campaigns.get(identity)
    loaded.aggregate.prepare_for_authorization(actor="tester", occurred_at=_OCCURRED_AT)
    loaded.aggregate.record_authorization(
        reason="approved", actor="tester", occurred_at=_OCCURRED_AT
    )
    loaded.aggregate.activate(reason="go", actor="tester", occurred_at=_OCCURRED_AT)
    loaded.aggregate.complete(reason="done", actor="tester", occurred_at=_OCCURRED_AT)
    runtime.campaigns.save(loaded.aggregate, expected_persisted_version=AggregateVersion(0))

    with pytest.raises(ValueError, match="cannot transition from COMPLETED"):
        run_cancel_campaign(
            campaign_governance_id=str(identity.governance_id),
            campaign_runtime_id=str(identity.runtime_id),
            expected_persisted_version=4,
            actor="tester",
            occurred_at=_OCCURRED_AT,
            reason="too late",
            config=_config(),
        )

    reloaded = runtime.campaigns.get(identity)
    assert reloaded.aggregate.state is CampaignLifecycleState.COMPLETED
    assert reloaded.persisted_version == AggregateVersion(4)


def test_stale_expected_version_raises_optimistic_concurrency_conflict(
    seeding_service: PostgresPersistenceService,
) -> None:
    identity = _persist_draft_campaign(
        seeding_service,
        governance_id="CAMP-0003",
        runtime_id="32345678-1234-4321-8765-1234567890ab",
    )

    # Simulate an interfering writer: independently reload the same identity
    # and advance the persisted version via revise_scope_statement() -- the
    # identical M047 mechanism, re-applied here to prove it propagates
    # correctly through a real production entrypoint. Test setup only;
    # never invoked by any production code.
    runtime = PostgresRepositoryRuntime(seeding_service)
    interfering = runtime.campaigns.get(identity)
    interfering.aggregate.revise_scope_statement(
        CampaignScopeStatement("revised by another writer")
    )
    runtime.campaigns.save(interfering.aggregate, expected_persisted_version=AggregateVersion(0))

    advanced = runtime.campaigns.get(identity)
    assert advanced.persisted_version == AggregateVersion(1)
    assert advanced.aggregate.state is CampaignLifecycleState.DRAFT

    with pytest.raises(OptimisticConcurrencyConflict) as excinfo:
        run_cancel_campaign(
            campaign_governance_id=str(identity.governance_id),
            campaign_runtime_id=str(identity.runtime_id),
            expected_persisted_version=0,  # stale: real durable version is 1
            actor="tester",
            occurred_at=_OCCURRED_AT,
            reason="should never persist",
            config=_config(),
        )

    assert excinfo.value.expected_persisted_version == AggregateVersion(0)
    assert excinfo.value.actual_persisted_version == AggregateVersion(1)

    reloaded = runtime.campaigns.get(identity)
    assert reloaded.aggregate.state is CampaignLifecycleState.DRAFT
    assert str(reloaded.aggregate.scope_statement) == "revised by another writer"
    assert reloaded.persisted_version == AggregateVersion(1)


def test_default_config_resolves_from_environment(
    monkeypatch: pytest.MonkeyPatch,
    seeding_service: PostgresPersistenceService,
) -> None:
    """Proves the production default path -- omitting `config` -- really
    resolves through `resolve_foundation_config()` against this same
    disposable database, not just the explicit-override path every other
    test in this file exercises."""
    identity = _persist_draft_campaign(
        seeding_service,
        governance_id="CAMP-0004",
        runtime_id="42345678-1234-4321-8765-1234567890ab",
    )
    config = _config()
    monkeypatch.setenv("EMPIRICAL_PLATFORM_POSTGRES_HOST", config.host)
    monkeypatch.setenv("EMPIRICAL_PLATFORM_POSTGRES_PORT", str(config.port))
    monkeypatch.setenv("EMPIRICAL_PLATFORM_POSTGRES_DATABASE", config.database)
    monkeypatch.setenv("EMPIRICAL_PLATFORM_POSTGRES_USER", config.user)
    monkeypatch.setenv("EMPIRICAL_PLATFORM_POSTGRES_PASSWORD", config.password.get_secret_value())

    result = run_cancel_campaign(
        campaign_governance_id=str(identity.governance_id),
        campaign_runtime_id=str(identity.runtime_id),
        expected_persisted_version=0,
        actor="tester",
        occurred_at=_OCCURRED_AT,
        reason="env-resolved cancellation",
    )

    assert result.operation is SaveOperation.UPDATED
