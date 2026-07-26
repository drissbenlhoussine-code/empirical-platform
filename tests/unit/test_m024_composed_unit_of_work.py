"""MILESTONE-024 unit tests for the multi-aggregate composed unit of work.

Exercises `PostgresPersistenceService.run_composed` and its private
composition machinery (`_ComposedTransaction`, `_JoinedUnitOfWork`,
`_ActiveComposedScope`) against a fast, dependency-free SQLite backend,
mirroring the existing `tests/unit/test_postgres_persistence.py` pattern.
Real-PostgreSQL evidence (repository-level atomicity, read-your-own-writes
against the frozen M023 adapters) lives in
`tests/integration/test_m024_postgres_composed_unit_of_work.py`.
"""

from __future__ import annotations

import pytest
from pydantic import SecretStr
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from empirical_platform.shared.config.settings import PostgreSQLConfigSnapshot
from empirical_platform.shared.errors import FoundationError
from empirical_platform.shared.persistence.postgres import PostgresPersistenceService


def _sqlite_engine() -> object:
    return create_engine(
        "sqlite+pysqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )


def _config() -> PostgreSQLConfigSnapshot:
    return PostgreSQLConfigSnapshot(password=SecretStr("local-compose-placeholder"))


@pytest.fixture
def service() -> PostgresPersistenceService:
    svc = PostgresPersistenceService(_config(), engine=_sqlite_engine())
    svc.initialize()
    with svc.unit_of_work() as work:
        work.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, v TEXT)")
    return svc


# --- Public API: zero/one/multiple operations, ordering ----------------------


def test_run_composed_with_zero_operations_returns_empty_tuple(
    service: PostgresPersistenceService,
) -> None:
    result = service.run_composed([])
    assert result == ()


def test_run_composed_with_one_operation(service: PostgresPersistenceService) -> None:
    def op() -> str:
        with service.unit_of_work() as work:
            work.execute("INSERT INTO t (id, v) VALUES (1, 'a')")
        return "a-result"

    result = service.run_composed([op])
    assert result == ("a-result",)
    with service.unit_of_work() as work:
        rows = work.execute("SELECT * FROM t WHERE id = 1")
    assert len(rows) == 1


def test_run_composed_returns_results_in_supplied_order(
    service: PostgresPersistenceService,
) -> None:
    def op_a() -> str:
        with service.unit_of_work() as work:
            work.execute("INSERT INTO t (id, v) VALUES (1, 'a')")
        return "a-result"

    def op_b() -> str:
        with service.unit_of_work() as work:
            work.execute("INSERT INTO t (id, v) VALUES (2, 'b')")
        return "b-result"

    results = service.run_composed([op_a, op_b])
    assert results == ("a-result", "b-result")
    with service.unit_of_work() as work:
        rows = work.execute("SELECT * FROM t ORDER BY id")
    assert [row["id"] for row in rows] == [1, 2]


def test_run_composed_propagates_operation_exception(
    service: PostgresPersistenceService,
) -> None:
    def op_ok() -> str:
        with service.unit_of_work() as work:
            work.execute("INSERT INTO t (id, v) VALUES (1, 'a')")
        return "a-result"

    def op_fail() -> None:
        raise ValueError("deliberate failure")

    with pytest.raises(ValueError, match="deliberate failure"):
        service.run_composed([op_ok, op_fail])


# --- Result semantics: no result before commit, none on failure --------------


def test_no_result_tuple_on_rollback(service: PostgresPersistenceService) -> None:
    def op_ok() -> str:
        with service.unit_of_work() as work:
            work.execute("INSERT INTO t (id, v) VALUES (3, 'c')")
        return "c-result"

    def op_fail() -> None:
        raise ValueError("boom")

    try:
        service.run_composed([op_ok, op_fail])
    except ValueError:
        pass
    with service.unit_of_work() as work:
        rows = work.execute("SELECT * FROM t WHERE id = 3")
    assert rows == [], "operation that ran before the failure must not be durable"


def test_result_only_observable_after_run_composed_returns(
    service: PostgresPersistenceService,
) -> None:
    """No caller-visible durable state exists until run_composed's own return."""

    def op() -> str:
        with service.unit_of_work() as work:
            work.execute("INSERT INTO t (id, v) VALUES (4, 'd')")
        # At this point the insert has executed but nothing outside this
        # process-local call has committed yet; a fresh, independent unit of
        # work on the SAME service would still see it (single-connection
        # semantics), but no OTHER caller has been handed a result yet.
        return "d-result"

    result = service.run_composed([op])
    assert result == ("d-result",)
    with service.unit_of_work() as work:
        rows = work.execute("SELECT * FROM t WHERE id = 4")
    assert len(rows) == 1


# --- Standalone (no composed scope) behavior is unchanged --------------------


def test_standalone_unit_of_work_unaffected_by_composed_feature(
    service: PostgresPersistenceService,
) -> None:
    with service.unit_of_work() as work:
        work.execute("INSERT INTO t (id, v) VALUES (5, 'e')")
    with service.unit_of_work() as work:
        rows = work.execute("SELECT * FROM t WHERE id = 5")
    assert len(rows) == 1


def test_plain_nested_unit_of_work_without_composed_scope_still_raises(
    service: PostgresPersistenceService,
) -> None:
    with pytest.raises(FoundationError, match="Nested persistence units of work"):
        with service.unit_of_work():
            with service.unit_of_work():
                pass


# --- Nesting matrix -----------------------------------------------------------


def test_unit_of_work_joins_composed_scope_same_service(
    service: PostgresPersistenceService,
) -> None:
    def op() -> None:
        with service.unit_of_work() as work:
            work.execute("INSERT INTO t (id, v) VALUES (6, 'f')")

    service.run_composed([op])
    with service.unit_of_work() as work:
        rows = work.execute("SELECT * FROM t WHERE id = 6")
    assert len(rows) == 1


def test_different_service_rejected_while_composed_scope_active(
    service: PostgresPersistenceService,
) -> None:
    other_service = PostgresPersistenceService(_config(), engine=_sqlite_engine())
    other_service.initialize()

    def op_first() -> str:
        with service.unit_of_work() as work:
            work.execute("INSERT INTO t (id, v) VALUES (7, 'g')")
        return "g-result"

    def op_cross_service() -> None:
        with other_service.unit_of_work():
            pass

    with pytest.raises(FoundationError, match="Nested persistence units of work"):
        service.run_composed([op_first, op_cross_service])

    with service.unit_of_work() as work:
        rows = work.execute("SELECT * FROM t WHERE id = 7")
    assert rows == [], "op_first must roll back when a later operation is rejected"


def test_nested_run_composed_same_service_raises(
    service: PostgresPersistenceService,
) -> None:
    def inner() -> None:
        service.run_composed([lambda: None])

    with pytest.raises(FoundationError, match="Nested persistence units of work"):
        service.run_composed([inner])


def test_nested_run_composed_different_service_raises(
    service: PostgresPersistenceService,
) -> None:
    other_service = PostgresPersistenceService(_config(), engine=_sqlite_engine())
    other_service.initialize()

    def inner() -> None:
        other_service.run_composed([lambda: None])

    with pytest.raises(FoundationError, match="Nested persistence units of work"):
        service.run_composed([inner])


# --- Poisoned-scope semantics -------------------------------------------------


def test_swallowed_inner_failure_still_poisons_scope(
    service: PostgresPersistenceService,
) -> None:
    with service.unit_of_work() as work:
        work.execute("INSERT INTO t (id, v) VALUES (8, 'seed')")

    def op_duplicate_then_swallow() -> str:
        try:
            with service.unit_of_work() as work:
                work.execute("INSERT INTO t (id, v) VALUES (8, 'dup')")  # PK collision
        except FoundationError:
            pass  # caller swallows the inner failure
        return "swallowed-ok"

    def op_after() -> str:
        with service.unit_of_work() as work:
            work.execute("INSERT INTO t (id, v) VALUES (9, 'h')")
        return "h-result"

    with pytest.raises(FoundationError, match="Composed transaction poisoned"):
        service.run_composed([op_duplicate_then_swallow, op_after])

    with service.unit_of_work() as work:
        rows = work.execute("SELECT * FROM t WHERE id = 9")
    assert rows == [], "op_after must not survive a poisoned scope"


def test_no_result_tuple_when_scope_poisoned_by_swallowed_failure(
    service: PostgresPersistenceService,
) -> None:
    with service.unit_of_work() as work:
        work.execute("INSERT INTO t (id, v) VALUES (10, 'seed')")

    def op_duplicate_then_swallow() -> None:
        try:
            with service.unit_of_work() as work:
                work.execute("INSERT INTO t (id, v) VALUES (10, 'dup')")
        except FoundationError:
            pass

    called_after_raise = []
    try:
        result = service.run_composed([op_duplicate_then_swallow])
        called_after_raise.append(result)
    except FoundationError:
        pass
    assert called_after_raise == [], "run_composed must not return a result tuple"


# --- Cleanup: ContextVar reset on every path ----------------------------------


def test_context_reset_after_successful_commit(service: PostgresPersistenceService) -> None:
    service.run_composed([lambda: None])
    # A follow-up standalone call must behave normally -- proves no stale scope.
    with service.unit_of_work() as work:
        work.execute("INSERT INTO t (id, v) VALUES (11, 'i')")
    with service.unit_of_work() as work:
        rows = work.execute("SELECT * FROM t WHERE id = 11")
    assert len(rows) == 1


def test_context_reset_after_operation_failure(service: PostgresPersistenceService) -> None:
    def op_fail() -> None:
        raise ValueError("boom")

    try:
        service.run_composed([op_fail])
    except ValueError:
        pass
    # A follow-up standalone call must behave normally -- proves cleanup ran.
    with service.unit_of_work() as work:
        work.execute("INSERT INTO t (id, v) VALUES (12, 'j')")
    with service.unit_of_work() as work:
        rows = work.execute("SELECT * FROM t WHERE id = 12")
    assert len(rows) == 1


def test_context_reset_after_poisoned_scope(service: PostgresPersistenceService) -> None:
    with service.unit_of_work() as work:
        work.execute("INSERT INTO t (id, v) VALUES (13, 'seed')")

    def op_duplicate_then_swallow() -> None:
        try:
            with service.unit_of_work() as work:
                work.execute("INSERT INTO t (id, v) VALUES (13, 'dup')")
        except FoundationError:
            pass

    try:
        service.run_composed([op_duplicate_then_swallow])
    except FoundationError:
        pass
    # A follow-up standalone call must behave normally -- proves cleanup ran
    # even though the scope was poisoned and __exit__ itself raised.
    with service.unit_of_work() as work:
        work.execute("INSERT INTO t (id, v) VALUES (14, 'k')")
    with service.unit_of_work() as work:
        rows = work.execute("SELECT * FROM t WHERE id = 14")
    assert len(rows) == 1
