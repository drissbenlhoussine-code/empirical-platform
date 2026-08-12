"""Persistence-neutral repository contract for MILESTONE-070 daily
research sessions."""

from __future__ import annotations

from typing import Protocol

from empirical_platform.decision_candidate.research_session import ResearchSession
from empirical_platform.identifiers.pairs import DomainIdentity
from empirical_platform.identifiers.types import ResearchSessionId


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
