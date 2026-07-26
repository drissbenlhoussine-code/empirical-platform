"""MILESTONE-024 real-PostgreSQL integration tests for `run_composed`.

Exercises `PostgresPersistenceService.run_composed` together with the real,
frozen MILESTONE-023 `PostgresCampaignRepository` and `PostgresRunRepository`
adapters (never mocked) against a real, migrated PostgreSQL database,
proving genuine cross-aggregate atomicity: a single composed transaction
spanning a Campaign write and a Run write commits or rolls back as one unit,
poisoning propagates even through a caller-swallowed inner failure, a
different service instance is rejected before any SQL executes, and every
MILESTONE-023 regression scenario (standalone get/add/save) is unaffected.

Opt-in via ``EMPIRICAL_PLATFORM_RUN_POSTGRES_TESTS=1``, following the same
convention as ``tests/integration/test_m023_postgres_repositories.py``.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime
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
from empirical_platform.shared.config.settings import PostgreSQLConfigSnapshot
from empirical_platform.shared.contracts.repository import (
    AggregateAlreadyExists,
    SaveOperation,
)
from empirical_platform.shared.errors import FoundationError
from empirical_platform.shared.identifiers import RuntimeIdentifier
from empirical_platform.shared.persistence.postgres import PostgresPersistenceService
from empirical_platform.shared.persistence.postgres_repositories.campaign_repository import (
    PostgresCampaignRepository,
)
from empirical_platform.shared.persistence.postgres_repositories.run_repository import (
    PostgresRunRepository,
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

OCCURRED_AT = datetime(2026, 7, 26, tzinfo=UTC)


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
        application_name="empirical-platform-m024-test",
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
def service(clean_tables: Engine) -> Iterator[PostgresPersistenceService]:
    svc = PostgresPersistenceService(_config())
    svc.initialize()
    try:
        yield svc
    finally:
        svc.close()


@pytest.fixture
def campaign_repo(service: PostgresPersistenceService) -> PostgresCampaignRepository:
    return PostgresCampaignRepository(service)


@pytest.fixture
def run_repo(service: PostgresPersistenceService) -> PostgresRunRepository:
    return PostgresRunRepository(service)


# --- Cross-aggregate atomic commit --------------------------------------------


def test_composed_commit_persists_campaign_and_run_atomically(
    service: PostgresPersistenceService,
    campaign_repo: PostgresCampaignRepository,
    run_repo: PostgresRunRepository,
) -> None:
    campaign_identity = DomainIdentity(
        governance_id=CampaignId("CAMP-0001"), runtime_id=_runtime_id()
    )
    run_identity = DomainIdentity(governance_id=RunId("RUN-0001"), runtime_id=_runtime_id())

    def add_campaign() -> object:
        return campaign_repo.add(
            Campaign(identity=campaign_identity, scope_statement=CampaignScopeStatement("scope"))
        )

    def add_run() -> object:
        return run_repo.add(Run(identity=run_identity, campaign_id=CampaignId("CAMP-0001")))

    results = service.run_composed([add_campaign, add_run])

    assert results[0].operation is SaveOperation.CREATED  # type: ignore[attr-defined]
    assert results[1].operation is SaveOperation.CREATED  # type: ignore[attr-defined]
    assert campaign_repo.get(campaign_identity).aggregate.identity == campaign_identity
    assert run_repo.get(run_identity).aggregate.identity == run_identity


def test_composed_commit_is_visible_from_a_fresh_connection(
    service: PostgresPersistenceService,
    campaign_repo: PostgresCampaignRepository,
    run_repo: PostgresRunRepository,
) -> None:
    campaign_identity = DomainIdentity(
        governance_id=CampaignId("CAMP-0001"), runtime_id=_runtime_id()
    )
    run_identity = DomainIdentity(governance_id=RunId("RUN-0001"), runtime_id=_runtime_id())

    def add_campaign() -> None:
        campaign_repo.add(
            Campaign(identity=campaign_identity, scope_statement=CampaignScopeStatement("scope"))
        )

    def add_run() -> None:
        run_repo.add(Run(identity=run_identity, campaign_id=CampaignId("CAMP-0001")))

    service.run_composed([add_campaign, add_run])

    other_service = PostgresPersistenceService(_config())
    other_service.initialize()
    try:
        other_campaign_repo = PostgresCampaignRepository(other_service)
        other_run_repo = PostgresRunRepository(other_service)
        assert other_campaign_repo.get(campaign_identity).aggregate.identity == campaign_identity
        assert other_run_repo.get(run_identity).aggregate.identity == run_identity
    finally:
        other_service.close()


# --- Cross-aggregate atomic rollback ------------------------------------------


def test_composed_rollback_leaves_no_partial_state_across_aggregates(
    service: PostgresPersistenceService,
    campaign_repo: PostgresCampaignRepository,
    run_repo: PostgresRunRepository,
) -> None:
    campaign_identity = DomainIdentity(
        governance_id=CampaignId("CAMP-0001"), runtime_id=_runtime_id()
    )
    run_identity = DomainIdentity(governance_id=RunId("RUN-0001"), runtime_id=_runtime_id())

    def add_campaign() -> None:
        campaign_repo.add(
            Campaign(identity=campaign_identity, scope_statement=CampaignScopeStatement("scope"))
        )

    def add_run_that_fails() -> None:
        # references a campaign governance id that will not exist at commit
        # time from this transaction's own perspective once poisoned; here we
        # force a real DB-level rejection via a duplicate governance id after
        # a first, successful run insert to prove partial work is discarded.
        run_repo.add(Run(identity=run_identity, campaign_id=CampaignId("CAMP-0001")))
        raise ValueError("deliberate failure after successful run insert")

    with pytest.raises(ValueError, match="deliberate failure"):
        service.run_composed([add_campaign, add_run_that_fails])

    from empirical_platform.shared.contracts.repository import AggregateNotFound

    with pytest.raises(AggregateNotFound):
        campaign_repo.get(campaign_identity)
    with pytest.raises(AggregateNotFound):
        run_repo.get(run_identity)


def test_composed_swallowed_repository_failure_with_no_further_sql_still_poisons(
    service: PostgresPersistenceService,
    campaign_repo: PostgresCampaignRepository,
) -> None:
    """Design Section 10, row 2: swallowed failure, nothing else attempts SQL after it.

    `_ComposedTransaction.__exit__` sees `exc_type is None` (the caller swallowed the
    exception) but `state is POISONED`, so it rolls back and raises the synthetic
    ``"Composed transaction poisoned by a failed operation"`` FoundationError itself.
    """
    campaign_identity = DomainIdentity(
        governance_id=CampaignId("CAMP-0001"), runtime_id=_runtime_id()
    )
    shared_runtime_id = _runtime_id()

    def add_campaign() -> None:
        campaign_repo.add(
            Campaign(
                identity=DomainIdentity(
                    governance_id=CampaignId("CAMP-0001"), runtime_id=shared_runtime_id
                ),
                scope_statement=CampaignScopeStatement("scope"),
            )
        )

    def add_duplicate_then_swallow() -> None:
        try:
            campaign_repo.add(
                Campaign(
                    identity=DomainIdentity(
                        governance_id=CampaignId("CAMP-0002"), runtime_id=shared_runtime_id
                    ),
                    scope_statement=CampaignScopeStatement("dup"),
                )
            )
        except AggregateAlreadyExists:
            pass  # caller deliberately swallows the failure

    with pytest.raises(FoundationError, match="Composed transaction poisoned"):
        service.run_composed([add_campaign, add_duplicate_then_swallow])

    from empirical_platform.shared.contracts.repository import AggregateNotFound

    with pytest.raises(AggregateNotFound):
        campaign_repo.get(campaign_identity)


def test_composed_execute_after_poisoning_fails_at_the_database_and_still_rolls_back(
    service: PostgresPersistenceService,
    campaign_repo: PostgresCampaignRepository,
    run_repo: PostgresRunRepository,
) -> None:
    """Design Section 10, row 3: a later operation's own execute() after poisoning is
    not pre-flight-blocked by `_JoinedUnitOfWork` -- PostgreSQL's own aborted-transaction
    state rejects it with its own SQLSTATE, translated to a generic FoundationError, and
    that (not the synthetic poisoned-scope message) is what propagates from run_composed.
    The whole transaction -- including the first, otherwise-successful operation -- still
    rolls back with no partial state.
    """
    campaign_identity = DomainIdentity(
        governance_id=CampaignId("CAMP-0001"), runtime_id=_runtime_id()
    )
    run_identity = DomainIdentity(governance_id=RunId("RUN-0001"), runtime_id=_runtime_id())
    shared_runtime_id = _runtime_id()

    def add_campaign() -> None:
        campaign_repo.add(
            Campaign(
                identity=DomainIdentity(
                    governance_id=CampaignId("CAMP-0001"), runtime_id=shared_runtime_id
                ),
                scope_statement=CampaignScopeStatement("scope"),
            )
        )

    def add_duplicate_then_swallow() -> None:
        try:
            campaign_repo.add(
                Campaign(
                    identity=DomainIdentity(
                        governance_id=CampaignId("CAMP-0002"), runtime_id=shared_runtime_id
                    ),
                    scope_statement=CampaignScopeStatement("dup"),
                )
            )
        except AggregateAlreadyExists:
            pass  # caller deliberately swallows the failure

    def add_run_after() -> None:
        run_repo.add(Run(identity=run_identity, campaign_id=CampaignId("CAMP-0001")))

    with pytest.raises(FoundationError, match="Persistence .* failed"):
        service.run_composed([add_campaign, add_duplicate_then_swallow, add_run_after])

    from empirical_platform.shared.contracts.repository import AggregateNotFound

    with pytest.raises(AggregateNotFound):
        campaign_repo.get(campaign_identity)
    with pytest.raises(AggregateNotFound):
        run_repo.get(run_identity)


# --- Same-identity sequencing within one composed scope -----------------------


def test_composed_read_your_own_writes_within_same_operation(
    service: PostgresPersistenceService,
    campaign_repo: PostgresCampaignRepository,
) -> None:
    identity = DomainIdentity(governance_id=CampaignId("CAMP-0001"), runtime_id=_runtime_id())

    def add_then_read_back() -> str:
        campaign_repo.add(Campaign(identity=identity, scope_statement=CampaignScopeStatement("a")))
        loaded = campaign_repo.get(identity)
        return str(loaded.aggregate.scope_statement)

    (scope_statement,) = service.run_composed([add_then_read_back])
    assert scope_statement == "a"


def test_composed_add_then_save_same_repository_instance_sequentially(
    service: PostgresPersistenceService,
    campaign_repo: PostgresCampaignRepository,
) -> None:
    identity = DomainIdentity(governance_id=CampaignId("CAMP-0001"), runtime_id=_runtime_id())

    def add_campaign() -> object:
        return campaign_repo.add(
            Campaign(identity=identity, scope_statement=CampaignScopeStatement("scope"))
        )

    def authorize_campaign() -> object:
        loaded = campaign_repo.get(identity)
        aggregate = loaded.aggregate
        aggregate.prepare_for_authorization(actor="tester", occurred_at=OCCURRED_AT)
        return campaign_repo.save(aggregate, expected_persisted_version=loaded.persisted_version)

    add_result, save_result = service.run_composed([add_campaign, authorize_campaign])
    assert add_result.operation is SaveOperation.CREATED  # type: ignore[attr-defined]
    assert save_result.operation is SaveOperation.UPDATED  # type: ignore[attr-defined]

    reloaded = campaign_repo.get(identity)
    assert len(reloaded.aggregate.transition_history) == 1


# --- Cross-service rejection before SQL ---------------------------------------


def test_composed_scope_rejects_a_different_service_instance_before_sql(
    service: PostgresPersistenceService,
    campaign_repo: PostgresCampaignRepository,
) -> None:
    other_service = PostgresPersistenceService(_config())
    other_service.initialize()
    try:
        campaign_identity = DomainIdentity(
            governance_id=CampaignId("CAMP-0001"), runtime_id=_runtime_id()
        )

        def add_campaign() -> None:
            campaign_repo.add(
                Campaign(
                    identity=campaign_identity, scope_statement=CampaignScopeStatement("scope")
                )
            )

        def join_other_service() -> None:
            with other_service.unit_of_work():
                pass

        with pytest.raises(FoundationError, match="Nested persistence units of work"):
            service.run_composed([add_campaign, join_other_service])

        from empirical_platform.shared.contracts.repository import AggregateNotFound

        with pytest.raises(AggregateNotFound):
            campaign_repo.get(campaign_identity)
    finally:
        other_service.close()


# --- Zero/one operation and empty-list behavior --------------------------------


def test_composed_with_zero_operations_returns_empty_tuple(
    service: PostgresPersistenceService,
) -> None:
    assert service.run_composed([]) == ()


def test_composed_with_one_operation_matches_standalone_behavior(
    service: PostgresPersistenceService,
    campaign_repo: PostgresCampaignRepository,
) -> None:
    identity = DomainIdentity(governance_id=CampaignId("CAMP-0001"), runtime_id=_runtime_id())

    def add_campaign() -> object:
        return campaign_repo.add(
            Campaign(identity=identity, scope_statement=CampaignScopeStatement("scope"))
        )

    (result,) = service.run_composed([add_campaign])
    assert result.operation is SaveOperation.CREATED  # type: ignore[attr-defined]
    assert campaign_repo.get(identity).aggregate.identity == identity


# --- Regression: standalone M023 usage is unaffected ---------------------------


def test_standalone_campaign_repository_usage_unaffected_by_m024(
    campaign_repo: PostgresCampaignRepository,
) -> None:
    identity = DomainIdentity(governance_id=CampaignId("CAMP-0001"), runtime_id=_runtime_id())
    result = campaign_repo.add(
        Campaign(identity=identity, scope_statement=CampaignScopeStatement("scope"))
    )
    assert result.operation is SaveOperation.CREATED
    loaded = campaign_repo.get(identity)
    assert loaded.aggregate.identity == identity


def test_standalone_nested_unit_of_work_still_rejected_outside_composed_scope(
    service: PostgresPersistenceService,
) -> None:
    with pytest.raises(FoundationError, match="Nested persistence units of work"):
        with service.unit_of_work():
            with service.unit_of_work():
                pass
