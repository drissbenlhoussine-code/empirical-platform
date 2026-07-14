"""Deterministic persistence substitute for foundation tests."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from contextvars import ContextVar, Token
from dataclasses import dataclass, field
from typing import Literal

from empirical_platform.shared.errors import FoundationError, FoundationErrorCategory
from empirical_platform.shared.health import HealthState, LayerHealth

_active_fake_unit_of_work: ContextVar[bool] = ContextVar(
    "active_fake_persistence_unit_of_work", default=False
)


@dataclass(slots=True)
class FakeUnitOfWork:
    """In-memory unit of work substitute with atomic commit/rollback behavior."""

    service: FakePersistenceService
    staged: list[str] = field(default_factory=list)
    completed: bool = False
    token: Token[bool] | None = None

    def __enter__(self) -> FakeUnitOfWork:
        self.service._ensure_can_work("begin")
        if _active_fake_unit_of_work.get():
            raise FoundationError(
                category=FoundationErrorCategory.PERSISTENCE,
                message="Nested persistence units of work are not supported",
                layer="persistence",
                operation="begin",
            )
        self.token = _active_fake_unit_of_work.set(True)
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> Literal[False]:
        if self.completed:
            self._reset()
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
        self.staged.append(statement)
        if statement.strip().upper() == "SELECT 1":
            return [{"?column?": 1}]
        return []

    def commit(self) -> None:
        self._ensure_active("commit")
        self.service.committed.extend(self.staged)
        self.completed = True
        self._reset()

    def rollback(self) -> None:
        self._ensure_active("rollback")
        self.staged.clear()
        self.service.rollback_count += 1
        self.completed = True
        self._reset()

    def _ensure_active(self, operation: str) -> None:
        if self.completed:
            raise FoundationError(
                category=FoundationErrorCategory.PERSISTENCE,
                message="Persistence unit of work is not active",
                layer="persistence",
                operation=operation,
            )

    def _reset(self) -> None:
        if self.token is not None:
            _active_fake_unit_of_work.reset(self.token)
            self.token = None


class FakePersistenceService:
    """Deterministic test substitute for persistence connectivity."""

    def __init__(self, *, reachable: bool = True) -> None:
        self.reachable = reachable
        self.initialized = False
        self.closed = False
        self.committed: list[str] = []
        self.rollback_count = 0

    def initialize(self) -> None:
        if self.closed:
            raise FoundationError(
                category=FoundationErrorCategory.PERSISTENCE,
                message="Persistence service is closed",
                layer="persistence",
                operation="initialize",
            )
        if not self.reachable:
            raise FoundationError(
                category=FoundationErrorCategory.PERSISTENCE,
                message="Persistence initialize failed because dependency is unreachable",
                layer="persistence",
                operation="initialize",
            )
        self.initialized = True

    def unit_of_work(self) -> FakeUnitOfWork:
        self._ensure_can_work("unit_of_work")
        return FakeUnitOfWork(self)

    def check(self) -> bool:
        return self.initialized and not self.closed and self.reachable

    def health(self) -> LayerHealth:
        if not self.initialized:
            return LayerHealth(
                "persistence",
                liveness=HealthState.PASS,
                readiness=HealthState.UNKNOWN,
                dependency_health=HealthState.UNKNOWN,
            )
        if self.check():
            return LayerHealth(
                "persistence",
                liveness=HealthState.PASS,
                readiness=HealthState.PASS,
                dependency_health=HealthState.PASS,
            )
        return LayerHealth(
            "persistence",
            liveness=HealthState.PASS,
            readiness=HealthState.FAIL,
            dependency_health=HealthState.FAIL,
        )

    def close(self) -> None:
        self.closed = True
        self.initialized = False

    def _ensure_can_work(self, operation: str) -> None:
        if self.closed:
            raise FoundationError(
                category=FoundationErrorCategory.PERSISTENCE,
                message="Persistence service is closed",
                layer="persistence",
                operation=operation,
            )
        if not self.initialized:
            raise FoundationError(
                category=FoundationErrorCategory.PERSISTENCE,
                message="Persistence service is not initialized",
                layer="persistence",
                operation=operation,
            )
