"""MILESTONE-048 real-PostgreSQL integration tests for `FailRunHandler`.

Exercises the full frozen vertical slice against a real, migrated
PostgreSQL database (never mocked): `CommandEntryPoint` -> concrete
`FailRunHandler` -> `Run` aggregate -> the real, frozen
`PostgresRunRepository` -> PostgreSQL. The `RunRepository` instance is
obtained externally (this test's own fixtures), exactly as the frozen
design requires -- the `usecases` package itself never imports
persistence. A Campaign and Run are first persisted through the existing,
frozen M030/M033 handlers, and the Run is transitioned to `AUTHORIZED`
through the existing, frozen M035 `AuthorizeRunHandler`. `ACQUIRING` is
then reached via a direct `start_acquisition()` call on an independently
loaded aggregate -- no production command exists for this transition yet
(out of this milestone's scope per the macro scope document, Section 8),
so this is test setup only, mirroring the established pattern of driving
predecessor state via direct domain-method calls when no handler exists
(never invoked by any production code).

The deterministic optimistic-concurrency conflict scenario is frozen
exactly by the M048 design (Section 13): unlike M047's reuse of
`Campaign.revise_scope_statement()`, `Run` has no method analogous to a
dedicated scope-revision mutation -- `Run.append_manifest()` (M035's own
interfering write) is reused again here, re-applied to a third target
transition (`fail()` instead of `authorize()`). The interfering write
independently loads the same identity and calls `Run.append_manifest()`
directly (never through any production command) to advance the persisted
version while preserving `ACQUIRING`, so the command under test can still
execute its own `fail()` call before the stale-version `save()` fails.
This is test setup only; the interfering call is never made through any
production command in this milestone.

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
from empirical_platform.usecases.fail_run import FailRunCommand, FailRunHandler

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
        application_name="empirical-platform-m048-test",
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


def _persist_authorized_run(
    campaign_repo: PostgresCampaignRepository,
    run_repo: PostgresRunRepository,
    *,
    campaign_governance_id: str,
    run_governance_id: str,
    campaign_runtime_id: str,
    run_runtime_id: str,
) -> DomainIdentity[RunId]:
    CommandEntryPoint(
        CreateCampaignHandler(
            campaign_repository=campaign_repo,
            runtime_identifier_generator=DeterministicRuntimeIdentifierGenerator(
                [campaign_runtime_id]
            ),
        )
    )(
        CreateCampaignCommand(
            campaign_governance_id=campaign_governance_id, scope_statement="seed campaign"
        )
    )

    identity = CommandEntryPoint(
        CreateRunHandler(
            run_repository=run_repo,
            runtime_identifier_generator=DeterministicRuntimeIdentifierGenerator([run_runtime_id]),
        )
    )(
        CreateRunCommand(
            run_governance_id=run_governance_id, campaign_governance_id=campaign_governance_id
        )
    )

    CommandEntryPoint(AuthorizeRunHandler(run_repository=run_repo))(
        AuthorizeRunCommand(
            identity=identity,
            expected_persisted_version=AggregateVersion.initial(),
            actor="tester",
            occurred_at=_OCCURRED_AT,
        )
    )
    return identity


def _persist_acquiring_run(
    campaign_repo: PostgresCampaignRepository,
    run_repo: PostgresRunRepository,
    *,
    campaign_governance_id: str,
    run_governance_id: str,
    campaign_runtime_id: str,
    run_runtime_id: str,
) -> DomainIdentity[RunId]:
    identity = _persist_authorized_run(
        campaign_repo,
        run_repo,
        campaign_governance_id=campaign_governance_id,
        run_governance_id=run_governance_id,
        campaign_runtime_id=campaign_runtime_id,
        run_runtime_id=run_runtime_id,
    )
    # start_acquisition() has no production command yet (out of M048's
    # scope) -- test setup only, driven directly on the aggregate.
    loaded = run_repo.get(identity)
    loaded.aggregate.start_acquisition(actor="tester", occurred_at=_OCCURRED_AT)
    run_repo.save(loaded.aggregate, expected_persisted_version=AggregateVersion(1))
    return identity


def test_golden_path_fails_run_from_acquiring(
    campaign_repo: PostgresCampaignRepository,
    run_repo: PostgresRunRepository,
) -> None:
    identity = _persist_acquiring_run(
        campaign_repo,
        run_repo,
        campaign_governance_id="CAMP-0001",
        run_governance_id="RUN-0001",
        campaign_runtime_id="a1111111-1111-4111-8111-111111111111",
        run_runtime_id="a2222222-2222-4222-8222-222222222222",
    )

    handler = FailRunHandler(run_repository=run_repo)
    entry_point = CommandEntryPoint(handler)
    command = FailRunCommand(
        identity=identity,
        expected_persisted_version=AggregateVersion(2),
        reason="acquisition source unavailable",
        actor="tester",
        occurred_at=_OCCURRED_AT,
        correlation_id="corr-golden",
    )

    result = entry_point(command)

    assert result.operation is SaveOperation.UPDATED
    assert result.persisted_version == AggregateVersion(3)

    reloaded = run_repo.get(identity)
    assert reloaded.aggregate.state is RunLifecycleState.FAILED
    assert reloaded.persisted_version == AggregateVersion(3)
    record = reloaded.aggregate.transition_history[-1]
    assert record.from_state == "ACQUIRING"
    assert record.to_state == "FAILED"
    assert record.reason == "acquisition source unavailable"
    assert record.correlation_id == "corr-golden"


def test_invalid_state_still_authorized_raises_domain_value_error(
    campaign_repo: PostgresCampaignRepository,
    run_repo: PostgresRunRepository,
) -> None:
    """A Run still AUTHORIZED (never started) rejects fail() with a domain
    ValueError, independently reproduced against real PostgreSQL."""
    identity = _persist_authorized_run(
        campaign_repo,
        run_repo,
        campaign_governance_id="CAMP-0002",
        run_governance_id="RUN-0002",
        campaign_runtime_id="a3333333-3333-4333-8333-333333333333",
        run_runtime_id="a4444444-4444-4444-8444-444444444444",
    )

    handler = FailRunHandler(run_repository=run_repo)
    entry_point = CommandEntryPoint(handler)

    with pytest.raises(ValueError, match="cannot transition from AUTHORIZED"):
        entry_point(
            FailRunCommand(
                identity=identity,
                expected_persisted_version=AggregateVersion(1),
                reason="should never persist",
                actor="tester",
                occurred_at=_OCCURRED_AT,
            )
        )

    reloaded = run_repo.get(identity)
    assert reloaded.aggregate.state is RunLifecycleState.AUTHORIZED
    assert reloaded.persisted_version == AggregateVersion(1)


def test_empty_reason_raises_domain_value_error(
    campaign_repo: PostgresCampaignRepository,
    run_repo: PostgresRunRepository,
) -> None:
    identity = _persist_acquiring_run(
        campaign_repo,
        run_repo,
        campaign_governance_id="CAMP-0003",
        run_governance_id="RUN-0003",
        campaign_runtime_id="a5555555-5555-4555-8555-555555555555",
        run_runtime_id="a6666666-6666-4666-8666-666666666666",
    )

    handler = FailRunHandler(run_repository=run_repo)
    entry_point = CommandEntryPoint(handler)

    with pytest.raises(ValueError, match="must be non-empty"):
        entry_point(
            FailRunCommand(
                identity=identity,
                expected_persisted_version=AggregateVersion(2),
                reason="   ",
                actor="tester",
                occurred_at=_OCCURRED_AT,
            )
        )

    reloaded = run_repo.get(identity)
    assert reloaded.aggregate.state is RunLifecycleState.ACQUIRING
    assert reloaded.persisted_version == AggregateVersion(2)


def test_missing_run_raises_aggregate_not_found(
    run_repo: PostgresRunRepository,
) -> None:
    missing_identity = DomainIdentity(
        governance_id=RunId("RUN-9999"),
        runtime_id=RuntimeIdentifier(_MISSING_RUNTIME_ID_VALUE),
    )
    handler = FailRunHandler(run_repository=run_repo)
    entry_point = CommandEntryPoint(handler)

    with pytest.raises(AggregateNotFound):
        entry_point(
            FailRunCommand(
                identity=missing_identity,
                expected_persisted_version=AggregateVersion.initial(),
                reason="should never persist",
                actor="tester",
                occurred_at=_OCCURRED_AT,
            )
        )


def test_stale_expected_version_raises_optimistic_concurrency_conflict(
    campaign_repo: PostgresCampaignRepository,
    run_repo: PostgresRunRepository,
) -> None:
    identity = _persist_acquiring_run(
        campaign_repo,
        run_repo,
        campaign_governance_id="CAMP-0004",
        run_governance_id="RUN-0004",
        campaign_runtime_id="a7777777-7777-4777-8777-777777777777",
        run_runtime_id="a8888888-8888-4888-8888-888888888888",
    )

    # Simulate an interfering writer: independently reload the same identity
    # and advance the persisted version via append_manifest() -- reused a
    # third time (after M035's authorize(), M048's own reuse here), still
    # state-preserving, does not touch fail()'s own preconditions. Test
    # setup only; never invoked as an interfering write by any production
    # code.
    interfering = run_repo.get(identity)
    interfering.aggregate.append_manifest(
        DatasetManifest(
            run_id=identity.governance_id,
            recorded_at=_OCCURRED_AT,
            source="interfering-writer",
        )
    )
    run_repo.save(interfering.aggregate, expected_persisted_version=AggregateVersion(2))

    handler = FailRunHandler(run_repository=run_repo)
    entry_point = CommandEntryPoint(handler)
    stale_command = FailRunCommand(
        identity=identity,
        expected_persisted_version=AggregateVersion(2),  # stale: real durable version is 3
        reason="should never persist",
        actor="tester",
        occurred_at=_OCCURRED_AT,
    )

    with pytest.raises(OptimisticConcurrencyConflict) as excinfo:
        entry_point(stale_command)

    assert excinfo.value.expected_persisted_version == AggregateVersion(2)
    assert excinfo.value.actual_persisted_version == AggregateVersion(3)

    reloaded = run_repo.get(identity)
    assert reloaded.aggregate.state is RunLifecycleState.ACQUIRING
    assert reloaded.persisted_version == AggregateVersion(3)
    assert len(reloaded.aggregate.manifests) == 1
    assert reloaded.aggregate.manifests[0].source == "interfering-writer"


def test_no_production_composition_machinery_is_required(
    campaign_repo: PostgresCampaignRepository,
    run_repo: PostgresRunRepository,
) -> None:
    """The handler is constructed directly from the externally-obtained
    repository -- no FoundationRuntime, no registry, no composition root
    of any kind."""
    identity = _persist_acquiring_run(
        campaign_repo,
        run_repo,
        campaign_governance_id="CAMP-0099",
        run_governance_id="RUN-0099",
        campaign_runtime_id="a9999999-9999-4999-8999-999999999999",
        run_runtime_id="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
    )

    handler = FailRunHandler(run_repository=run_repo)
    result = handler.handle(
        FailRunCommand(
            identity=identity,
            expected_persisted_version=AggregateVersion(2),
            reason="a reason",
            actor="tester",
            occurred_at=_OCCURRED_AT,
        )
    )

    assert result.operation is SaveOperation.UPDATED
