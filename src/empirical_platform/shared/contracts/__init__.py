"""Shared typed contract boundary."""

from empirical_platform.shared.contracts.command import CommandHandler
from empirical_platform.shared.contracts.mapping import (
    IdentityDurableRecord,
    MapperError,
    MapperErrorCategory,
    TransitionDurableRecord,
)
from empirical_platform.shared.contracts.query import QueryHandler
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
    "CommandHandler",
    "IdentityDurableRecord",
    "InvalidAggregateForPersistence",
    "InvalidPersistedAggregateState",
    "LoadedAggregate",
    "MapperError",
    "MapperErrorCategory",
    "OptimisticConcurrencyConflict",
    "QueryHandler",
    "RepositoryContractError",
    "SaveOperation",
    "SaveResult",
    "TransitionDurableRecord",
]
