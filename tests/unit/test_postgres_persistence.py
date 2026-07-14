from __future__ import annotations

import pytest
from pydantic import SecretStr
from sqlalchemy import create_engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.pool import StaticPool

from empirical_platform.shared.config.settings import PostgreSQLConfigSnapshot
from empirical_platform.shared.errors import FoundationError
from empirical_platform.shared.health import HealthState, ProcessHealth
from empirical_platform.shared.persistence.postgres import (
    PostgresPersistenceService,
    translate_persistence_error,
)


class FailingTransaction:
    def __init__(self, *, fail_commit: bool = False, fail_rollback: bool = False) -> None:
        self.fail_commit = fail_commit
        self.fail_rollback = fail_rollback

    def commit(self) -> None:
        if self.fail_commit:
            raise SQLAlchemyError("commit failed")

    def rollback(self) -> None:
        if self.fail_rollback:
            raise SQLAlchemyError("rollback failed")


class FailingConnection:
    def __init__(self, transaction: FailingTransaction) -> None:
        self.transaction = transaction
        self.closed = False
        self.in_transaction = False

    def __enter__(self) -> FailingConnection:
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> bool:
        self.close()
        return False

    def begin(self) -> FailingTransaction:
        self.in_transaction = True
        return self.transaction

    def execute(self, statement: object, parameters: object | None = None) -> object:
        if not self.in_transaction:
            return object()
        raise SQLAlchemyError("driver failed")

    def close(self) -> None:
        self.closed = True


class FailingEngine:
    def __init__(self, transaction: FailingTransaction) -> None:
        self.connection = FailingConnection(transaction)

    def connect(self) -> FailingConnection:
        return self.connection


def _sqlite_engine() -> object:
    return create_engine(
        "sqlite+pysqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )


def _config() -> PostgreSQLConfigSnapshot:
    return PostgreSQLConfigSnapshot(password=SecretStr("local-compose-placeholder"))


def test_postgres_service_lifecycle_and_select_probe_with_injected_engine() -> None:
    service = PostgresPersistenceService(_config(), engine=_sqlite_engine())

    assert service.health().readiness is HealthState.UNKNOWN
    service.initialize()
    assert service.check()
    assert service.health().dependency_health is HealthState.PASS

    with service.unit_of_work() as work:
        assert work.execute("SELECT 1 AS value") == [{"value": 1}]

    service.close()
    service.close()
    assert service.health().readiness is HealthState.FAIL
    with pytest.raises(FoundationError):
        service.unit_of_work()


def test_unit_of_work_commit_and_rollback_have_atomic_boundaries() -> None:
    service = PostgresPersistenceService(_config(), engine=_sqlite_engine())
    service.initialize()

    with service.unit_of_work() as work:
        work.execute("CREATE TEMPORARY TABLE m008_temp(value INTEGER)")
        work.execute("INSERT INTO m008_temp(value) VALUES (1)")
        assert work.execute("SELECT value FROM m008_temp") == [{"value": 1}]

    with pytest.raises(RuntimeError, match="abort"):
        with service.unit_of_work() as work:
            work.execute("CREATE TEMPORARY TABLE m008_rollback(value INTEGER)")
            raise RuntimeError("abort")

    service.close()


def test_driver_exception_is_translated_without_public_type_leak() -> None:
    service = PostgresPersistenceService(
        _config(),
        engine=FailingEngine(FailingTransaction()),  # type: ignore[arg-type]
    )
    service.initialize()

    with pytest.raises(FoundationError) as exc_info:
        with service.unit_of_work() as work:
            work.execute("SELECT 1")

    payload = exc_info.value.as_dict()
    assert payload["category"] == "persistence_error"
    assert "SQLAlchemyError" not in str(payload)


def test_commit_and_rollback_failures_are_translated() -> None:
    commit_service = PostgresPersistenceService(
        _config(),
        engine=FailingEngine(FailingTransaction(fail_commit=True)),  # type: ignore[arg-type]
    )
    commit_service.initialize()
    with pytest.raises(FoundationError):
        with commit_service.unit_of_work():
            pass

    rollback_service = PostgresPersistenceService(
        _config(),
        engine=FailingEngine(FailingTransaction(fail_rollback=True)),  # type: ignore[arg-type]
    )
    rollback_service.initialize()
    with pytest.raises(FoundationError):
        with rollback_service.unit_of_work() as work:
            work.rollback()


def test_translate_persistence_error_uses_foundation_error_category() -> None:
    error = translate_persistence_error(
        SQLAlchemyError("driver detail"),
        operation="connect",
        context={"safe": "yes"},
    )

    assert error.category.value == "persistence_error"
    assert error.as_dict()["layer"] == "persistence"


def test_single_failed_operation_does_not_force_liveness_failure() -> None:
    service = PostgresPersistenceService(_config(), engine=_sqlite_engine())
    service.initialize()

    with pytest.raises(FoundationError):
        with service.unit_of_work() as work:
            work.execute("SELECT * FROM missing_table")

    assert service.health().liveness is HealthState.PASS
    assert ProcessHealth.PASS.value == "PASS"
    service.close()
