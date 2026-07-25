"""Shared typed contract boundary."""

from empirical_platform.shared.contracts.repository import (
    AggregateAlreadyExists,
    AggregateNotFound,
    InvalidAggregateForPersistence,
    InvalidPersistedAggregateState,
    LoadedAggregate,
    OptimisticConcurrencyConflict,
    RepositoryContractError,
    SaveOperation,
    SaveResult,
)

__all__ = [
    "AggregateAlreadyExists",
    "AggregateNotFound",
    "InvalidAggregateForPersistence",
    "InvalidPersistedAggregateState",
    "LoadedAggregate",
    "OptimisticConcurrencyConflict",
    "RepositoryContractError",
    "SaveOperation",
    "SaveResult",
]
