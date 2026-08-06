"""MILESTONE-047 real-PostgreSQL integration tests for
`CancelCampaignHandler`.

Exercises the full frozen vertical slice against a real, migrated
PostgreSQL database (never mocked): `CommandEntryPoint` -> concrete
`CancelCampaignHandler` -> `Campaign` aggregate -> the real, frozen
`PostgresCampaignRepository` -> PostgreSQL. The `CampaignRepository`
instance is obtained externally (this test's own fixtures), exactly as the
frozen design requires -- the `usecases` package itself never imports
persistence. A Campaign is first persisted through the existing, frozen
M030 `CreateCampaignHandler`. To reach `AUTHORIZED` (one of `cancel()`'s
five allowed source states, and the only one where `reason` is required),
`Campaign.record_authorization()` is called directly on an independently
loaded aggregate and persisted via the repository's own `save()` -- no
production command exists for this transition yet (out of this
milestone's scope per the macro scope document, Section 8), so this is
test setup only, mirroring the established pattern of driving predecessor
state via direct domain-method calls when no handler exists (test setup
only; never invoked by any production code).

The deterministic optimistic-concurrency conflict scenario is frozen
exactly by the M047 design (Section 13): the interfering write
independently loads the same identity and calls
`Campaign.revise_scope_statement()` -- the identical M032 mechanism,
re-applied here to a new target transition (`cancel()` instead of
`prepare_for_authorization()`) -- to advance the persisted version while
preserving `DRAFT`, so the command under test can still execute its own
`cancel()` call before the stale-version `save()` fails.
`revise_scope_statement()` is test setup only; it is never invoked by any
production code.

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
from empirical_platform.usecases.cancel_campaign import (
    CancelCampaignCommand,
    CancelCampaignHandler,
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
        application_name="empirical-platform-m047-test",
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


def _persist_authorized_campaign(
    campaign_repo: PostgresCampaignRepository,
    *,
    governance_id: str,
    runtime_id: str,
) -> DomainIdentity[CampaignId]:
    identity = _persist_draft_campaign(
        campaign_repo, governance_id=governance_id, runtime_id=runtime_id
    )
    loaded = campaign_repo.get(identity)
    loaded.aggregate.prepare_for_authorization(actor="tester", occurred_at=_OCCURRED_AT)
    loaded.aggregate.record_authorization(
        reason="approved", actor="tester", occurred_at=_OCCURRED_AT
    )
    campaign_repo.save(loaded.aggregate, expected_persisted_version=AggregateVersion(0))
    return identity


def test_golden_path_cancels_campaign_from_draft(
    campaign_repo: PostgresCampaignRepository,
) -> None:
    identity = _persist_draft_campaign(campaign_repo, governance_id="CAMP-0001")

    handler = CancelCampaignHandler(campaign_repository=campaign_repo)
    entry_point = CommandEntryPoint(handler)
    command = CancelCampaignCommand(
        identity=identity,
        expected_persisted_version=AggregateVersion(0),
        actor="tester",
        occurred_at=_OCCURRED_AT,
        reason="scope abandoned",
        correlation_id="corr-golden",
    )

    result = entry_point(command)

    assert result.operation is SaveOperation.UPDATED
    assert result.persisted_version == AggregateVersion(1)

    reloaded = campaign_repo.get(identity)
    assert reloaded.aggregate.state is CampaignLifecycleState.CANCELLED
    assert reloaded.persisted_version == AggregateVersion(1)
    record = reloaded.aggregate.transition_history[-1]
    assert record.from_state == "DRAFT"
    assert record.to_state == "CANCELLED"
    assert record.actor == "tester"
    assert record.correlation_id == "corr-golden"
    assert record.reason == "scope abandoned"


def test_golden_path_cancels_campaign_from_authorized_with_required_reason(
    campaign_repo: PostgresCampaignRepository,
) -> None:
    identity = _persist_authorized_campaign(
        campaign_repo, governance_id="CAMP-0002", runtime_id="22345678-1234-4321-8765-1234567890ab"
    )
    loaded = campaign_repo.get(identity)
    assert loaded.aggregate.state is CampaignLifecycleState.AUTHORIZED
    assert loaded.persisted_version == AggregateVersion(2)

    handler = CancelCampaignHandler(campaign_repository=campaign_repo)
    entry_point = CommandEntryPoint(handler)
    command = CancelCampaignCommand(
        identity=identity,
        expected_persisted_version=AggregateVersion(2),
        actor="tester",
        occurred_at=_OCCURRED_AT,
        reason="authorization revoked",
    )

    result = entry_point(command)

    assert result.operation is SaveOperation.UPDATED
    reloaded = campaign_repo.get(identity)
    assert reloaded.aggregate.state is CampaignLifecycleState.CANCELLED
    assert reloaded.aggregate.transition_history[-1].from_state == "AUTHORIZED"
    assert reloaded.aggregate.transition_history[-1].reason == "authorization revoked"


def test_missing_reason_when_required_raises_type_error(
    campaign_repo: PostgresCampaignRepository,
) -> None:
    identity = _persist_authorized_campaign(
        campaign_repo, governance_id="CAMP-0003", runtime_id="32345678-1234-4321-8765-1234567890ab"
    )

    handler = CancelCampaignHandler(campaign_repository=campaign_repo)
    entry_point = CommandEntryPoint(handler)
    command = CancelCampaignCommand(
        identity=identity,
        expected_persisted_version=AggregateVersion(2),
        actor="tester",
        occurred_at=_OCCURRED_AT,
        reason=None,
    )

    with pytest.raises(TypeError, match="cancellation reason must be a string"):
        entry_point(command)

    reloaded = campaign_repo.get(identity)
    assert reloaded.aggregate.state is CampaignLifecycleState.AUTHORIZED
    assert reloaded.persisted_version == AggregateVersion(2)


def test_invalid_state_completed_raises_domain_error_without_persisting(
    campaign_repo: PostgresCampaignRepository,
) -> None:
    identity = _persist_authorized_campaign(
        campaign_repo, governance_id="CAMP-0004", runtime_id="42345678-1234-4321-8765-1234567890ab"
    )
    loaded = campaign_repo.get(identity)
    loaded.aggregate.activate(reason="go", actor="tester", occurred_at=_OCCURRED_AT)
    loaded.aggregate.complete(reason="done", actor="tester", occurred_at=_OCCURRED_AT)
    campaign_repo.save(loaded.aggregate, expected_persisted_version=AggregateVersion(2))

    handler = CancelCampaignHandler(campaign_repository=campaign_repo)
    entry_point = CommandEntryPoint(handler)
    command = CancelCampaignCommand(
        identity=identity,
        expected_persisted_version=AggregateVersion(4),
        actor="tester",
        occurred_at=_OCCURRED_AT,
        reason="too late",
    )

    with pytest.raises(ValueError, match="cannot transition from COMPLETED"):
        entry_point(command)

    reloaded = campaign_repo.get(identity)
    assert reloaded.aggregate.state is CampaignLifecycleState.COMPLETED
    assert reloaded.persisted_version == AggregateVersion(4)


def test_missing_campaign_raises_aggregate_not_found(
    campaign_repo: PostgresCampaignRepository,
) -> None:
    _persist_draft_campaign(campaign_repo, governance_id="CAMP-0005")
    missing_identity = DomainIdentity(
        governance_id=CampaignId("CAMP-9999"),
        runtime_id=RuntimeIdentifier(_MISSING_RUNTIME_ID_VALUE),
    )
    handler = CancelCampaignHandler(campaign_repository=campaign_repo)
    entry_point = CommandEntryPoint(handler)

    with pytest.raises(AggregateNotFound):
        entry_point(
            CancelCampaignCommand(
                identity=missing_identity,
                expected_persisted_version=AggregateVersion.initial(),
                actor="tester",
                occurred_at=_OCCURRED_AT,
                reason="should never persist",
            )
        )


def test_stale_expected_version_raises_optimistic_concurrency_conflict(
    campaign_repo: PostgresCampaignRepository,
) -> None:
    identity = _persist_draft_campaign(campaign_repo, governance_id="CAMP-0006")

    # Simulate an interfering writer: independently reload the same identity
    # and advance the persisted version via revise_scope_statement() -- the
    # identical M032 mechanism, re-applied to this new target transition.
    # Test setup only; never invoked by any production code.
    interfering = campaign_repo.get(identity)
    interfering.aggregate.revise_scope_statement(
        CampaignScopeStatement("revised by another writer")
    )
    campaign_repo.save(interfering.aggregate, expected_persisted_version=AggregateVersion(0))

    advanced = campaign_repo.get(identity)
    assert advanced.persisted_version == AggregateVersion(1)
    assert advanced.aggregate.state is CampaignLifecycleState.DRAFT

    handler = CancelCampaignHandler(campaign_repository=campaign_repo)
    entry_point = CommandEntryPoint(handler)
    stale_command = CancelCampaignCommand(
        identity=identity,
        expected_persisted_version=AggregateVersion(0),  # stale: real durable version is 1
        actor="tester",
        occurred_at=_OCCURRED_AT,
        reason="should never persist",
    )

    with pytest.raises(OptimisticConcurrencyConflict) as excinfo:
        entry_point(stale_command)

    assert excinfo.value.expected_persisted_version == AggregateVersion(0)
    assert excinfo.value.actual_persisted_version == AggregateVersion(1)

    reloaded = campaign_repo.get(identity)
    assert reloaded.aggregate.state is CampaignLifecycleState.DRAFT
    assert str(reloaded.aggregate.scope_statement) == "revised by another writer"
    assert reloaded.persisted_version == AggregateVersion(1)


def test_no_production_composition_machinery_is_required(
    campaign_repo: PostgresCampaignRepository,
) -> None:
    """The handler is constructed directly from the externally-obtained
    repository -- no FoundationRuntime, no registry, no composition root
    of any kind."""
    identity = _persist_draft_campaign(campaign_repo, governance_id="CAMP-0099")

    handler = CancelCampaignHandler(campaign_repository=campaign_repo)
    result = handler.handle(
        CancelCampaignCommand(
            identity=identity,
            expected_persisted_version=AggregateVersion(0),
            actor="tester",
            occurred_at=_OCCURRED_AT,
            reason="a reason",
        )
    )

    assert result.operation is SaveOperation.UPDATED
