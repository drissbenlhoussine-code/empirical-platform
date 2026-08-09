"""Retrieve one historical robustness study by full identity.

MILESTONE-063.
"""

from __future__ import annotations

from dataclasses import dataclass

from empirical_platform.decision_candidate.robustness_study import HistoricalRobustnessStudy
from empirical_platform.decision_candidate.robustness_study_repository import (
    HistoricalRobustnessStudyRepository,
)
from empirical_platform.identifiers.pairs import DomainIdentity
from empirical_platform.identifiers.types import RobustnessStudyId


@dataclass(frozen=True, slots=True)
class GetHistoricalRobustnessStudyQuery:
    """Request to retrieve one robustness study by canonical identity."""

    identity: DomainIdentity[RobustnessStudyId]


class GetHistoricalRobustnessStudyHandler:
    """Retrieve one persisted robustness study."""

    __slots__ = ("_repository",)

    def __init__(self, *, repository: HistoricalRobustnessStudyRepository) -> None:
        self._repository = repository

    def handle(self, query: GetHistoricalRobustnessStudyQuery) -> HistoricalRobustnessStudy:
        return self._repository.get(query.identity)
