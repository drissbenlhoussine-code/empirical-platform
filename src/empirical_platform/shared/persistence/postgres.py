"""PostgreSQL connectivity foundation without domain schemas."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from contextvars import ContextVar, Token
from dataclasses import dataclass
from enum import Enum
from typing import Any, Literal, cast

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.exc import DBAPIError, OperationalError, SQLAlchemyError, TimeoutError

from empirical_platform.shared.config.settings import PostgreSQLConfigSnapshot
from empirical_platform.shared.errors import FoundationError, FoundationErrorCategory
from empirical_platform.shared.health import HealthState, LayerHealth
from empirical_platform.shared.interfaces.persistence import PersistenceUnitOfWork

_active_unit_of_work: ContextVar[bool] = ContextVar(
    "active_persistence_unit_of_work", default=False
)


def translate_persistence_error(
    exc: BaseException,
    *,
    operation: str,
    context: Mapping[str, object] | None = None,
) -> FoundationError:
    """Translate lower-level persistence failures into the foundation error model."""
    return FoundationError.wrap(
        exc,
        category=FoundationErrorCategory.PERSISTENCE,
        message=_safe_message_for(exc, operation),
        layer="persistence",
        operation=operation,
        context=context or {},
    )


def _safe_message_for(exc: BaseException, operation: str) -> str:
    if isinstance(exc, TimeoutError):
        return f"Persistence {operation} timed out"
    if isinstance(exc, OperationalError):
        return f"Persistence {operation} failed because PostgreSQL is unreachable"
    if isinstance(exc, DBAPIError):
        return f"Persistence {operation} failed in the database driver"
    if isinstance(exc, SQLAlchemyError):
        return f"Persistence {operation} failed"
    if isinstance(exc, FoundationError):
        return exc.safe_message
    return f"Persistence {operation} failed unexpectedly"


@dataclass(slots=True)
class PostgresUnitOfWork:
    """SQLAlchemy-backed unit of work with explicit completion semantics."""

    _service: PostgresPersistenceService
    _connection: Connection | None = None
    _transaction: Any | None = None
    _completed: bool = False
    _context_token: Token[bool] | None = None

    def __enter__(self) -> PostgresUnitOfWork:
        self._service._ensure_can_work("begin")
        if _active_unit_of_work.get():
            raise FoundationError(
                category=FoundationErrorCategory.PERSISTENCE,
                message="Nested persistence units of work are not supported",
                layer="persistence",
                operation="begin",
            )
        try:
            self._context_token = _active_unit_of_work.set(True)
            self._connection = self._service.engine.connect()
            self._transaction = self._connection.begin()
        except Exception as exc:
            self._reset_context()
            raise translate_persistence_error(
                exc,
                operation="begin",
                context=self._service.safe_context(),
            ) from exc
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> Literal[False]:
        if self._completed:
            self._reset_context()
            return False
        if exc_type is None:
            self.commit()
        else:
            self.rollback()
        return False

    def execute(
        self, statement: str, parameters: Mapping[str, object] | None = None
    ) -> Sequence[Mapping[str, object]]:
        self._ensure_active("execute")
        connection = cast(Connection, self._connection)
        try:
            result = connection.execute(text(statement), dict(parameters or {}))
            if not result.returns_rows:
                return []
            return [dict(row) for row in result.mappings().all()]
        except Exception as exc:
            raise translate_persistence_error(
                exc,
                operation="execute",
                context={"statement_kind": statement.split(maxsplit=1)[0].upper()},
            ) from exc

    def commit(self) -> None:
        self._ensure_active("commit")
        transaction = cast(Any, self._transaction)
        try:
            transaction.commit()
            self._complete()
        except Exception as exc:
            self._complete()
            raise translate_persistence_error(exc, operation="commit") from exc

    def rollback(self) -> None:
        self._ensure_active("rollback")
        transaction = cast(Any, self._transaction)
        try:
            transaction.rollback()
            self._complete()
        except Exception as exc:
            self._complete()
            raise translate_persistence_error(exc, operation="rollback") from exc

    def _ensure_active(self, operation: str) -> None:
        if self._completed or self._connection is None or self._transaction is None:
            raise FoundationError(
                category=FoundationErrorCategory.PERSISTENCE,
                message="Persistence unit of work is not active",
                layer="persistence",
                operation=operation,
            )

    def _complete(self) -> None:
        if self._connection is not None:
            self._connection.close()
        self._connection = None
        self._transaction = None
        self._completed = True
        self._reset_context()

    def _reset_context(self) -> None:
        if self._context_token is not None:
            _active_unit_of_work.reset(self._context_token)
            self._context_token = None


class _ComposedScopeState(Enum):
    """Lifecycle state of an ambient composed transaction (MILESTONE-024)."""

    ACTIVE = "active"
    POISONED = "poisoned"


@dataclass(slots=True)
class _ActiveComposedScope:
    """Owned record published while a composed transaction is open.

    ``owner_service`` is compared by Python object identity, never equality,
    so a different ``PostgresPersistenceService`` instance can never join.
    """

    owner_service: PostgresPersistenceService
    unit_of_work: PostgresUnitOfWork
    state: _ComposedScopeState


_active_composed_scope: ContextVar[_ActiveComposedScope | None] = ContextVar(
    "active_persistence_composed_scope", default=None
)


class _JoinedUnitOfWork:
    """Delegates to an ambient composed transaction's real unit of work.

    Never opens or closes a connection, never commits or rolls back -- the
    owning ``_ComposedTransaction`` holds exclusive ownership of the real
    transaction. Poisons the ambient scope if the operation using it raises.
    """

    __slots__ = ("_scope",)

    def __init__(self, scope: _ActiveComposedScope) -> None:
        self._scope = scope

    def __enter__(self) -> _JoinedUnitOfWork:
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> Literal[False]:
        if exc_type is not None:
            self._scope.state = _ComposedScopeState.POISONED
        return False

    def execute(
        self, statement: str, parameters: Mapping[str, object] | None = None
    ) -> Sequence[Mapping[str, object]]:
        return self._scope.unit_of_work.execute(statement, parameters)

    def commit(self) -> None:
        """No-op: the real transaction is owned exclusively by the composed scope."""

    def rollback(self) -> None:
        """No-op: the real transaction is owned exclusively by the composed scope."""


class _ComposedTransaction:
    """Owns exactly one real transaction that multiple repository operations can join.

    Private: not exported, never returned to a caller. The only sanctioned
    entry point is ``PostgresPersistenceService.run_composed``.
    """

    __slots__ = ("_service", "_unit_of_work", "_scope", "_token")

    def __init__(self, service: PostgresPersistenceService) -> None:
        self._service = service
        self._unit_of_work: PostgresUnitOfWork | None = None
        self._scope: _ActiveComposedScope | None = None
        self._token: Token[_ActiveComposedScope | None] | None = None

    def __enter__(self) -> _ComposedTransaction:
        # Constructed directly, never via the public `unit_of_work()` factory:
        # that factory is the one gaining the join branch below, and calling
        # it here would let a second composed scope on the same service find
        # `_active_composed_scope` already populated and silently join rather
        # than raise. Constructing PostgresUnitOfWork directly forces every
        # composed-scope entry through the one, unmodified reentrancy guard.
        unit_of_work = PostgresUnitOfWork(self._service)
        unit_of_work.__enter__()
        self._unit_of_work = unit_of_work
        try:
            scope = _ActiveComposedScope(
                owner_service=self._service,
                unit_of_work=unit_of_work,
                state=_ComposedScopeState.ACTIVE,
            )
            self._token = _active_composed_scope.set(scope)
            self._scope = scope
        except Exception:
            # The real unit of work already entered (connection open,
            # transaction started, `_active_unit_of_work` set) before this
            # point, but the ambient scope was never published -- nothing
            # will ever call `__exit__` to clean it up, since `with` only
            # invokes `__exit__` when `__enter__` returns successfully.
            # Roll back and close here so no connection/transaction leaks
            # and the global reentrancy guard is reset for the next caller.
            unit_of_work.rollback()
            raise
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> Literal[False]:
        scope = cast(_ActiveComposedScope, self._scope)
        unit_of_work = cast(PostgresUnitOfWork, self._unit_of_work)
        try:
            if exc_type is None and scope.state is _ComposedScopeState.ACTIVE:
                unit_of_work.commit()
            else:
                unit_of_work.rollback()
                if exc_type is None:
                    raise FoundationError(
                        category=FoundationErrorCategory.PERSISTENCE,
                        message="Composed transaction poisoned by a failed operation",
                        layer="persistence",
                        operation="run_composed",
                    )
        finally:
            if self._token is not None:
                _active_composed_scope.reset(self._token)
                self._token = None
        return False


class PostgresPersistenceService:
    """Narrow PostgreSQL connection, health, and unit-of-work adapter."""

    def __init__(
        self,
        config: PostgreSQLConfigSnapshot,
        *,
        engine: Engine | None = None,
    ) -> None:
        self._config = config
        self._engine_obj = engine
        self._initialized = False
        self._closed = False
        self._last_health = LayerHealth(
            "persistence",
            liveness=HealthState.PASS,
            readiness=HealthState.UNKNOWN,
            dependency_health=HealthState.UNKNOWN,
        )

    @property
    def engine(self) -> Engine:
        """Return the initialized SQLAlchemy engine."""
        if self._engine_obj is None:
            raise FoundationError(
                category=FoundationErrorCategory.PERSISTENCE,
                message="Persistence engine is not initialized",
                layer="persistence",
                operation="engine",
            )
        return self._engine_obj

    def initialize(self) -> None:
        """Initialize the connection pool and verify connectivity."""
        if self._initialized and not self._closed:
            return
        if self._closed:
            raise FoundationError(
                category=FoundationErrorCategory.PERSISTENCE,
                message="Persistence service is closed",
                layer="persistence",
                operation="initialize",
            )
        try:
            if self._engine_obj is None:
                self._engine_obj = create_engine(
                    self._config.sqlalchemy_url(),
                    pool_size=self._config.pool_size,
                    max_overflow=self._config.max_overflow,
                    pool_pre_ping=True,
                    connect_args={
                        "connect_timeout": self._config.connection_timeout_seconds,
                        "application_name": self._config.application_name,
                    },
                )
            self._probe()
            self._initialized = True
            self._last_health = LayerHealth(
                "persistence",
                liveness=HealthState.PASS,
                readiness=HealthState.PASS,
                dependency_health=HealthState.PASS,
            )
        except FoundationError:
            self._last_health = LayerHealth(
                "persistence",
                liveness=HealthState.PASS,
                readiness=HealthState.FAIL,
                dependency_health=HealthState.FAIL,
            )
            raise
        except Exception as exc:
            self._last_health = LayerHealth(
                "persistence",
                liveness=HealthState.PASS,
                readiness=HealthState.FAIL,
                dependency_health=HealthState.FAIL,
            )
            raise translate_persistence_error(
                exc,
                operation="initialize",
                context=self.safe_context(),
            ) from exc

    def unit_of_work(self) -> PersistenceUnitOfWork:
        """Create a bounded unit of work, or join this service's own active
        composed scope (MILESTONE-024) if one is currently open. A different
        service instance's active composed scope is never joined; nested
        units of work outside an active composed scope are still rejected."""
        self._ensure_can_work("unit_of_work")
        scope = _active_composed_scope.get()
        if scope is not None and scope.owner_service is self:
            return _JoinedUnitOfWork(scope)
        return PostgresUnitOfWork(self)

    def run_composed(self, operations: Sequence[Callable[[], object]]) -> tuple[object, ...]:
        """Execute repository operations atomically; return results only after commit.

        Every operation runs against one shared transaction. The returned
        tuple -- in the exact order ``operations`` was supplied -- is only
        ever constructed after that transaction has actually committed; on
        any failure (including one caught and swallowed by an operation,
        which still poisons the scope) this raises instead of returning.
        """
        self._ensure_can_work("run_composed")
        with _ComposedTransaction(self):
            results = tuple(operation() for operation in operations)
        return results

    def check(self) -> bool:
        """Return whether PostgreSQL is reachable."""
        try:
            if not self._initialized or self._closed:
                self._last_health = LayerHealth(
                    "persistence",
                    liveness=HealthState.PASS,
                    readiness=HealthState.UNKNOWN if not self._closed else HealthState.FAIL,
                    dependency_health=HealthState.UNKNOWN,
                )
                return False
            self._probe()
        except Exception:
            self._last_health = LayerHealth(
                "persistence",
                liveness=HealthState.PASS,
                readiness=HealthState.FAIL,
                dependency_health=HealthState.FAIL,
            )
            return False
        self._last_health = LayerHealth(
            "persistence",
            liveness=HealthState.PASS,
            readiness=HealthState.PASS,
            dependency_health=HealthState.PASS,
        )
        return True

    def health(self) -> LayerHealth:
        """Return the latest persistence health signal."""
        return self._last_health

    def close(self) -> None:
        """Close the pool idempotently and reject future work."""
        if self._closed:
            return
        self._closed = True
        self._initialized = False
        if self._engine_obj is not None:
            self._engine_obj.dispose()
        self._last_health = LayerHealth(
            "persistence",
            liveness=HealthState.PASS,
            readiness=HealthState.FAIL,
            dependency_health=HealthState.UNKNOWN,
        )

    def safe_context(self) -> dict[str, object]:
        """Return safe PostgreSQL diagnostics."""
        return self._config.safe_context()

    def _probe(self) -> None:
        with self.engine.connect() as connection:
            connection.execute(text("SELECT 1"))

    def _ensure_can_work(self, operation: str) -> None:
        if self._closed:
            raise FoundationError(
                category=FoundationErrorCategory.PERSISTENCE,
                message="Persistence service is closed",
                layer="persistence",
                operation=operation,
            )
        if not self._initialized:
            raise FoundationError(
                category=FoundationErrorCategory.PERSISTENCE,
                message="Persistence service is not initialized",
                layer="persistence",
                operation=operation,
            )
