"""Immutable transition records for process-local domain lifecycle history."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from empirical_platform.shared.domain.versioning import AggregateVersion, TransitionSequence


@dataclass(frozen=True, slots=True)
class StateTransitionRecord[IdentityReferenceT]:
    """Historical lifecycle transition data, not a domain event or outbox message."""

    from_state: str | None
    to_state: str
    version: AggregateVersion
    sequence: TransitionSequence
    actor: str
    occurred_at: datetime
    identity_reference: IdentityReferenceT | None = None
    correlation_id: str | None = None
    reason: str | None = None

    def __post_init__(self) -> None:
        if self.from_state is not None and self.from_state.strip() == "":
            raise ValueError("from_state must be non-empty when provided")
        if self.to_state.strip() == "":
            raise ValueError("to_state must be non-empty")
        if self.actor.strip() == "":
            raise ValueError("actor must be non-empty")
        if self.correlation_id is not None and self.correlation_id.strip() == "":
            raise ValueError("correlation_id must be non-empty when provided")
        if self.reason is not None and self.reason.strip() == "":
            raise ValueError("reason must be non-empty when provided")
