"""List recent daily research sessions.

MILESTONE-071. Closes the "session history/navigation" gap: an operator
can find recent sessions -- optionally restricted to one universe --
without already knowing any session's own exact runtime id.
"""

from __future__ import annotations

from dataclasses import dataclass

from empirical_platform.decision_candidate.research_session import ResearchSessionSummary
from empirical_platform.decision_candidate.research_session_repository import (
    ResearchSessionRepository,
)

__all__ = [
    "ListDailyResearchSessionsHandler",
    "ListDailyResearchSessionsQuery",
    "ResearchSessionSummary",
]

_DEFAULT_LIMIT = 10
_MAX_LIMIT = 200


@dataclass(frozen=True, slots=True)
class ListDailyResearchSessionsQuery:
    """Request to list the most recent daily research sessions,
    optionally restricted to an exact universe (set-equality, order
    -independent)."""

    universe: tuple[str, ...] | None
    limit: int = _DEFAULT_LIMIT

    def __post_init__(self) -> None:
        if self.universe is not None and not self.universe:
            raise ValueError("universe must be non-empty when provided (use None for no filter)")
        if self.limit < 1:
            raise ValueError("limit must be at least 1")
        if self.limit > _MAX_LIMIT:
            raise ValueError(f"limit must not exceed {_MAX_LIMIT}")


class ListDailyResearchSessionsHandler:
    """List recent daily research sessions."""

    __slots__ = ("_repository",)

    def __init__(self, *, repository: ResearchSessionRepository) -> None:
        self._repository = repository

    def handle(self, query: ListDailyResearchSessionsQuery) -> tuple[ResearchSessionSummary, ...]:
        return self._repository.list_recent(universe=query.universe, limit=query.limit)
