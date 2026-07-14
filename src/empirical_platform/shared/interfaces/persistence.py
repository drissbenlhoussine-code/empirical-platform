"""Metadata persistence interfaces without domain schemas."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Literal, Protocol

from empirical_platform.shared.health import LayerHealth


class ConnectivityCheck(Protocol):
    """Generic connectivity check interface."""

    def check(self) -> bool:
        """Return whether the dependency is reachable."""
        ...


class PersistenceUnitOfWork(Protocol):
    """Bounded persistence unit of work."""

    def __enter__(self) -> PersistenceUnitOfWork:
        """Begin the bounded unit of work."""
        ...

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> Literal[False]:
        """Commit on success or roll back on failure."""
        ...

    def execute(
        self, statement: str, parameters: Mapping[str, object] | None = None
    ) -> Sequence[Mapping[str, object]]:
        """Execute infrastructure-local SQL within the unit of work."""
        ...

    def commit(self) -> None:
        """Commit the unit of work exactly once."""
        ...

    def rollback(self) -> None:
        """Abort the unit of work exactly once."""
        ...


class PersistenceService(Protocol):
    """Persistence adapter lifecycle contract."""

    def initialize(self) -> None:
        """Initialize connectivity resources."""
        ...

    def unit_of_work(self) -> PersistenceUnitOfWork:
        """Create a new unit of work."""
        ...

    def check(self) -> bool:
        """Return whether the dependency is reachable."""
        ...

    def health(self) -> LayerHealth:
        """Return the latest persistence health signal."""
        ...

    def close(self) -> None:
        """Close resources idempotently."""
        ...
