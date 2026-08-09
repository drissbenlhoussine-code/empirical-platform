"""Persistence-neutral repository contract for M063 historical robustness
studies."""

from __future__ import annotations

from typing import Protocol

from empirical_platform.decision_candidate.robustness_study import HistoricalRobustnessStudy
from empirical_platform.identifiers.pairs import DomainIdentity
from empirical_platform.identifiers.types import RobustnessStudyId


class HistoricalRobustnessStudyRepository(Protocol):
    """Persistence-neutral repository contract for immutable robustness
    studies."""

    def get(self, identity: DomainIdentity[RobustnessStudyId]) -> HistoricalRobustnessStudy:
        """Load a robustness study by canonical identity."""
        ...

    def add(self, study: HistoricalRobustnessStudy) -> None:
        """Persist a new robustness study that must not already exist."""
        ...
