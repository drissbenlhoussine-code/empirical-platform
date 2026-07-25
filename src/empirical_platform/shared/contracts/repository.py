"""Persistence-neutral repository contract-support types (MILESTONE-020).

Exception names below (AggregateNotFound, AggregateAlreadyExists,
OptimisticConcurrencyConflict, InvalidAggregateForPersistence,
InvalidPersistedAggregateState) are frozen exactly by MILESTONE-020 Design
Section 23 and are not renamed with an "Error" suffix to satisfy ruff's N818;
each is marked `# noqa: N818` for that reason.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from empirical_platform.shared.domain.versioning import AggregateVersion


class SaveOperation(StrEnum):
    """Closed outcome vocabulary for a repository save operation."""

    CREATED = "created"
    UPDATED = "updated"
    UNCHANGED = "unchanged"


@dataclass(frozen=True, slots=True)
class LoadedAggregate[AggregateT]:
    """Immutable load result pairing a detached aggregate with its load-time persisted version."""

    aggregate: AggregateT
    persisted_version: AggregateVersion

    def __post_init__(self) -> None:
        if self.aggregate is None:
            raise TypeError("aggregate must not be None")
        if not isinstance(self.persisted_version, AggregateVersion):
            raise TypeError("persisted_version must be an AggregateVersion")


@dataclass(frozen=True, slots=True)
class SaveResult:
    """Persistence-neutral outcome of a repository add or save operation."""

    operation: SaveOperation
    persisted_version: AggregateVersion

    def __post_init__(self) -> None:
        if not isinstance(self.operation, SaveOperation):
            raise TypeError("operation must be a SaveOperation")
        if not isinstance(self.persisted_version, AggregateVersion):
            raise TypeError("persisted_version must be an AggregateVersion")


class RepositoryContractError(Exception):
    """Persistence-neutral base error for repository-domain contract violations."""

    def __init__(
        self, message: str, *, aggregate_kind: str, identity: object | None = None
    ) -> None:
        self.safe_message = message
        self.aggregate_kind = aggregate_kind
        self.identity = identity
        super().__init__(message)


class AggregateNotFound(RepositoryContractError):  # noqa: N818
    """Raised when no persisted aggregate exists for the requested identity."""

    def __init__(self, *, aggregate_kind: str, identity: object) -> None:
        super().__init__(
            f"{aggregate_kind} not found for the requested identity",
            aggregate_kind=aggregate_kind,
            identity=identity,
        )


class AggregateAlreadyExists(RepositoryContractError):  # noqa: N818
    """Raised when a create operation targets an identity that already exists."""

    def __init__(self, *, aggregate_kind: str, identity: object) -> None:
        super().__init__(
            f"{aggregate_kind} already exists for the requested identity",
            aggregate_kind=aggregate_kind,
            identity=identity,
        )


class OptimisticConcurrencyConflict(RepositoryContractError):  # noqa: N818
    """Raised when the expected persisted version does not match durable state."""

    def __init__(
        self,
        *,
        aggregate_kind: str,
        identity: object,
        expected_persisted_version: AggregateVersion,
        aggregate_current_version: AggregateVersion,
        actual_persisted_version: AggregateVersion | None = None,
    ) -> None:
        super().__init__(
            f"{aggregate_kind} optimistic concurrency conflict for the requested identity",
            aggregate_kind=aggregate_kind,
            identity=identity,
        )
        self.expected_persisted_version = expected_persisted_version
        self.aggregate_current_version = aggregate_current_version
        self.actual_persisted_version = actual_persisted_version


class InvalidAggregateForPersistence(RepositoryContractError):  # noqa: N818
    """Raised when an in-memory aggregate is not valid for a persistence operation."""

    def __init__(self, *, aggregate_kind: str, reason: str, identity: object | None = None) -> None:
        super().__init__(
            f"{aggregate_kind} is not valid for persistence: {reason}",
            aggregate_kind=aggregate_kind,
            identity=identity,
        )
        self.reason = reason


class InvalidPersistedAggregateState(RepositoryContractError):  # noqa: N818
    """Raised when durable state cannot be safely reconstructed into an aggregate."""

    def __init__(self, *, aggregate_kind: str, reason: str, identity: object | None = None) -> None:
        super().__init__(
            f"{aggregate_kind} persisted state is invalid: {reason}",
            aggregate_kind=aggregate_kind,
            identity=identity,
        )
        self.reason = reason
