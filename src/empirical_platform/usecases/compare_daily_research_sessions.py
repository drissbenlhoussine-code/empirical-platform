"""Compare one daily research session against its own most recent prior
session sharing the same universe.

MILESTONE-071. Closes the "day-over-day change detection"/"research
-session comparison" gap: an operator can see exactly what changed
since the last research session for the same instruments -- new
candidates, dropped candidates, and changed decisions -- without any new
strategy/ranking/risk math. The comparison is computed on demand from
two already-persisted sessions and is never itself persisted as a new
entity.
"""

from __future__ import annotations

from dataclasses import dataclass

from empirical_platform.decision_candidate.research_session import (
    ResearchSession,
    SessionComparisonEntry,
    compare_session_decisions,
)
from empirical_platform.decision_candidate.research_session_repository import (
    ResearchSessionRepository,
)
from empirical_platform.identifiers.pairs import DomainIdentity
from empirical_platform.identifiers.types import ResearchSessionId

__all__ = [
    "CompareDailyResearchSessionsHandler",
    "CompareDailyResearchSessionsQuery",
    "SessionComparisonResult",
]


@dataclass(frozen=True, slots=True)
class CompareDailyResearchSessionsQuery:
    """Request to compare one target session against its own most
    recent prior session sharing the same requested universe."""

    identity: DomainIdentity[ResearchSessionId]


@dataclass(frozen=True, slots=True)
class SessionComparisonResult:
    """One immutable day-over-day comparison result: the target session,
    its own baseline (the most recent prior session sharing the same
    universe, or `None` when no prior session exists -- day-1 usage is
    never an error), and the per-instrument diff."""

    target: ResearchSession
    baseline: ResearchSession | None
    entries: tuple[SessionComparisonEntry, ...]


class CompareDailyResearchSessionsHandler:
    """Compare one daily research session against its own most recent
    prior session sharing the same universe."""

    __slots__ = ("_repository",)

    def __init__(self, *, repository: ResearchSessionRepository) -> None:
        self._repository = repository

    def handle(self, query: CompareDailyResearchSessionsQuery) -> SessionComparisonResult:
        target = self._repository.get(query.identity)
        baseline = self._repository.find_most_recent_prior(
            universe=target.requested_universe,
            before_as_of=target.as_of,
            exclude_runtime_id=target.identity.runtime_id,
        )
        entries = compare_session_decisions(
            target_decisions=target.decisions,
            baseline_decisions=baseline.decisions if baseline is not None else None,
        )
        return SessionComparisonResult(target=target, baseline=baseline, entries=entries)
