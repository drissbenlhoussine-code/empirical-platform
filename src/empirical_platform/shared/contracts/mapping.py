"""Persistence-neutral mapper-local error model (MILESTONE-021).

Distinct from `RepositoryContractError` (empirical_platform.shared.contracts.repository):
a mapper is not a repository and must remain callable and testable independent of any
repository implementation. A future repository implementation, not the mapper itself,
is responsible for wrapping `MapperError` into `InvalidPersistedAggregateState` or
`InvalidAggregateForPersistence` (MILESTONE-021 Design, Section 13).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


@dataclass(frozen=True, slots=True)
class IdentityDurableRecord:
    """Persistence-neutral representation of a `DomainIdentity` governance/runtime pair."""

    governance_id: str
    runtime_id: str


@dataclass(frozen=True, slots=True)
class TransitionDurableRecord:
    """Persistence-neutral representation of a `StateTransitionRecord`, any aggregate."""

    from_state: str | None
    to_state: str
    version: int
    sequence: int
    actor: str
    occurred_at: datetime
    identity_reference: IdentityDurableRecord | None = None
    correlation_id: str | None = None
    reason: str | None = None


class MapperErrorCategory(StrEnum):
    """Closed mapper-local error vocabulary."""

    INVALID_DURABLE_RECORD = "invalid_durable_record"
    INVALID_AGGREGATE_FOR_MAPPING = "invalid_aggregate_for_mapping"


class MapperError(Exception):
    """Persistence-neutral mapper failure, independent of repository error vocabulary."""

    def __init__(
        self,
        category: MapperErrorCategory,
        message: str,
        *,
        aggregate_kind: str,
        field: str | None = None,
    ) -> None:
        self.category = category
        self.safe_message = message
        self.aggregate_kind = aggregate_kind
        self.field = field
        super().__init__(message)
