"""Persistence-neutral repository contract for MILESTONE-070 daily
research sessions."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from empirical_platform.decision_candidate.research_session import (
    ResearchSession,
    ResearchSessionSummary,
)
from empirical_platform.identifiers.pairs import DomainIdentity
from empirical_platform.identifiers.types import ResearchSessionId
from empirical_platform.shared.identifiers import RuntimeIdentifier


class ResearchSessionRepository(Protocol):
    """Persistence-neutral repository contract for immutable daily
    research sessions -- compute once, persist once, never mutated
    afterward (mirrors the established M057-M069 pattern)."""

    def get(self, identity: DomainIdentity[ResearchSessionId]) -> ResearchSession:
        """Load a research session by its own canonical identity."""
        ...

    def add(self, session: ResearchSession) -> None:
        """Persist a new research session that must not already exist."""
        ...

    def list_recent(
        self, *, universe: tuple[str, ...] | None, limit: int
    ) -> tuple[ResearchSessionSummary, ...]:
        """MILESTONE-071. Most recent sessions first (by as_of, then
        created_at), optionally restricted to an exact universe (set
        -equality, order-independent). Never requires the caller to
        already know a session's own runtime id."""
        ...

    def find_most_recent_prior(
        self,
        *,
        universe: tuple[str, ...],
        before_as_of: datetime,
        exclude_runtime_id: RuntimeIdentifier,
    ) -> ResearchSession | None:
        """MILESTONE-071. The most recent session (by as_of, then
        created_at) with an exactly-matching universe and as_of strictly
        before `before_as_of`, excluding `exclude_runtime_id`. Returns
        `None` honestly when no prior session exists -- day-1 usage must
        not error."""
        ...
