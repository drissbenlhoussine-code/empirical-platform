from __future__ import annotations

import os

import pytest
from pydantic import SecretStr

from empirical_platform.shared.config.settings import PostgreSQLConfigSnapshot
from empirical_platform.shared.errors import FoundationError
from empirical_platform.shared.health import HealthState
from empirical_platform.shared.persistence.postgres import PostgresPersistenceService

pytestmark = pytest.mark.integration


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
        application_name="empirical-platform-test",
    )


@pytest.fixture
def postgres_service() -> PostgresPersistenceService:
    if not _integration_enabled():
        pytest.skip("PostgreSQL integration tests require explicit opt-in")
    service = PostgresPersistenceService(_config())
    service.initialize()
    try:
        yield service
    finally:
        service.close()


def test_postgres_connectivity_probe_and_select(
    postgres_service: PostgresPersistenceService,
) -> None:
    assert postgres_service.check()
    assert postgres_service.health().dependency_health is HealthState.PASS

    with postgres_service.unit_of_work() as work:
        assert work.execute("SELECT 1 AS value") == [{"value": 1}]


def test_postgres_transaction_commit_and_rollback_without_schema_artifacts(
    postgres_service: PostgresPersistenceService,
) -> None:
    with postgres_service.unit_of_work() as work:
        work.execute("CREATE TEMPORARY TABLE m008_commit(value INTEGER) ON COMMIT DROP")
        work.execute("INSERT INTO m008_commit(value) VALUES (1)")
        assert work.execute("SELECT value FROM m008_commit") == [{"value": 1}]

    with pytest.raises(RuntimeError, match="abort"):
        with postgres_service.unit_of_work() as work:
            work.execute("CREATE TEMPORARY TABLE m008_rollback(value INTEGER) ON COMMIT DROP")
            raise RuntimeError("abort")


def test_postgres_connection_failure_is_translated_safely() -> None:
    if not _integration_enabled():
        pytest.skip("PostgreSQL integration tests require explicit opt-in")
    service = PostgresPersistenceService(
        PostgreSQLConfigSnapshot(
            host="127.0.0.1",
            port=1,
            database="empirical_platform",
            user="empirical",
            password=SecretStr("local-compose-placeholder"),
            connection_timeout_seconds=1,
        )
    )

    with pytest.raises(FoundationError) as exc_info:
        service.initialize()

    payload = exc_info.value.as_dict()
    assert payload["category"] == "persistence_error"
    assert "local-compose-placeholder" not in str(payload)
