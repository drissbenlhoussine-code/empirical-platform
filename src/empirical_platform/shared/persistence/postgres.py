"""PostgreSQL connectivity foundation without domain schemas."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from contextvars import ContextVar, Token
from dataclasses import dataclass
from typing import Any, Literal, cast

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.exc import DBAPIError, OperationalError, SQLAlchemyError, TimeoutError

from empirical_platform.shared.config.settings import PostgreSQLConfigSnapshot
from empirical_platform.shared.errors import FoundationError, FoundationErrorCategory
from empirical_platform.shared.health import HealthState, LayerHealth

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

    def unit_of_work(self) -> PostgresUnitOfWork:
        """Create a bounded unit of work. Nested units are rejected."""
        self._ensure_can_work("unit_of_work")
        return PostgresUnitOfWork(self)

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
