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

from collections.abc import Iterator

import pytest
from pydantic import SecretStr
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

import empirical_platform.shared.persistence.postgres as postgres_module
from empirical_platform.shared.config.settings import PostgreSQLConfigSnapshot
from empirical_platform.shared.errors import FoundationError
from empirical_platform.shared.persistence.postgres import (
    PostgresPersistenceService,
    PostgresUnitOfWork,
)


def _sqlite_engine() -> object:
    return create_engine(
        "sqlite+pysqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )


def _config() -> PostgreSQLConfigSnapshot:
    return PostgreSQLConfigSnapshot(password=SecretStr("local-compose-placeholder"))


@pytest.fixture
def service() -> Iterator[PostgresPersistenceService]:
    svc = PostgresPersistenceService(_config(), engine=_sqlite_engine())
    svc.initialize()
    with svc.unit_of_work() as work:
        work.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, v TEXT)")
    try:
        yield svc
    finally:
        # Disposes the StaticPool's single underlying sqlite3 connection,
        # matching the existing tests/unit/test_postgres_persistence.py
        # convention -- otherwise it is only closed on GC finalization,
        # which surfaces as a ResourceWarning.
        svc.close()


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
    try:

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
    finally:
        other_service.close()


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
    try:

        def inner() -> None:
            other_service.run_composed([lambda: None])

        with pytest.raises(FoundationError, match="Nested persistence units of work"):
            service.run_composed([inner])
    finally:
        other_service.close()


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


# --- Entry publication cleanup (M024-IMPL-REVIEW-0001 correction) ------------


class _RaisingComposedScopeVar:
    """Stand-in for the module's `_active_composed_scope` ContextVar whose
    `set()` simulates a failure between real-UoW entry and ambient-scope
    publication. `contextvars.ContextVar.set` cannot be monkeypatched
    directly (it is a read-only C-level attribute), so the whole module
    global is swapped instead."""

    def get(self) -> None:
        return None

    def set(self, value: object) -> None:
        raise RuntimeError("simulated ContextVar publication failure")


def test_publication_failure_rolls_back_and_resets_reentrancy_guard(
    service: PostgresPersistenceService, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(postgres_module, "_active_composed_scope", _RaisingComposedScopeVar())

    with pytest.raises(RuntimeError, match="simulated ContextVar publication failure"):
        service.run_composed([lambda: None])

    # The real unit of work must have been rolled back and closed, and the
    # global `_active_unit_of_work` reentrancy guard reset -- proven by a
    # fresh standalone unit_of_work() succeeding immediately afterward.
    with service.unit_of_work() as work:
        work.execute("INSERT INTO t (id, v) VALUES (20, 'after-publication-failure')")
    with service.unit_of_work() as work:
        rows = work.execute("SELECT * FROM t WHERE id = 20")
    assert len(rows) == 1


def test_publication_failure_never_invokes_any_operation(
    service: PostgresPersistenceService, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(postgres_module, "_active_composed_scope", _RaisingComposedScopeVar())
    invoked = []

    def op() -> None:
        invoked.append(True)

    with pytest.raises(RuntimeError, match="simulated ContextVar publication failure"):
        service.run_composed([op])

    assert invoked == []


def test_publication_failure_returns_no_result_tuple(
    service: PostgresPersistenceService, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(postgres_module, "_active_composed_scope", _RaisingComposedScopeVar())
    observed_results = []

    try:
        result = service.run_composed([lambda: "should-never-be-returned"])
        observed_results.append(result)
    except RuntimeError:
        pass

    assert observed_results == []


def test_publication_failure_leaves_no_stale_composed_scope_for_next_call(
    service: PostgresPersistenceService, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(postgres_module, "_active_composed_scope", _RaisingComposedScopeVar())

    with pytest.raises(RuntimeError):
        service.run_composed([lambda: None])

    # Undo the monkeypatch and prove a subsequent, real composed scope opens
    # and commits normally -- no leftover scope or leaked connection blocks it.
    monkeypatch.undo()

    def op() -> str:
        with service.unit_of_work() as work:
            work.execute("INSERT INTO t (id, v) VALUES (21, 'recovered')")
        return "ok"

    result = service.run_composed([op])
    assert result == ("ok",)
    with service.unit_of_work() as work:
        rows = work.execute("SELECT * FROM t WHERE id = 21")
    assert len(rows) == 1


def test_cleanup_rollback_failure_surfaces_with_original_publication_failure_chained(
    service: PostgresPersistenceService, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When cleanup's own rollback also fails, the cleanup failure surfaces
    (matching the existing PostgresUnitOfWork.rollback()/FoundationError
    convention of always completing -- closing the connection and resetting
    the reentrancy guard -- even when the underlying rollback itself raises),
    with the original publication failure preserved via exception chaining.
    """
    monkeypatch.setattr(postgres_module, "_active_composed_scope", _RaisingComposedScopeVar())

    real_complete = PostgresUnitOfWork._complete

    def _raising_rollback(self: PostgresUnitOfWork) -> None:
        # Mirrors the real rollback()'s own contract: _complete() always
        # runs (closing the connection, resetting the reentrancy guard)
        # even when the rollback itself fails.
        real_complete(self)
        raise RuntimeError("simulated rollback failure during cleanup")

    monkeypatch.setattr(PostgresUnitOfWork, "rollback", _raising_rollback)

    with pytest.raises(RuntimeError, match="simulated rollback failure during cleanup") as excinfo:
        service.run_composed([lambda: None])

    assert isinstance(excinfo.value.__context__, RuntimeError)
    assert "simulated ContextVar publication failure" in str(excinfo.value.__context__)

    # _complete() still ran under the raising stub, so the reentrancy guard
    # was still reset -- prove a fresh standalone call succeeds afterward.
    monkeypatch.undo()
    with service.unit_of_work() as work:
        work.execute("INSERT INTO t (id, v) VALUES (22, 'after-cleanup-failure')")
    with service.unit_of_work() as work:
        rows = work.execute("SELECT * FROM t WHERE id = 22")
    assert len(rows) == 1
