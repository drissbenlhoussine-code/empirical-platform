"""Retrieve one persisted daily research session.

MILESTONE-070.
"""

from __future__ import annotations

from dataclasses import dataclass

from empirical_platform.decision_candidate.research_session import ResearchSession
from empirical_platform.decision_candidate.research_session_repository import (
    ResearchSessionRepository,
)
from empirical_platform.identifiers.pairs import DomainIdentity
from empirical_platform.identifiers.types import ResearchSessionId

__all__ = [
    "GetDailyResearchSessionHandler",
    "GetDailyResearchSessionQuery",
]


@dataclass(frozen=True, slots=True)
class GetDailyResearchSessionQuery:
    """Request to retrieve one daily research session by canonical
    identity -- a later process retrieves the persisted, completed
    session and its own final report without rerunning the pipeline
    (mission Phase 15)."""

    identity: DomainIdentity[ResearchSessionId]


class GetDailyResearchSessionHandler:
    """Retrieve one persisted daily research session."""

    __slots__ = ("_repository",)

    def __init__(self, *, repository: ResearchSessionRepository) -> None:
        self._repository = repository

    def handle(self, query: GetDailyResearchSessionQuery) -> ResearchSession:
        return self._repository.get(query.identity)
