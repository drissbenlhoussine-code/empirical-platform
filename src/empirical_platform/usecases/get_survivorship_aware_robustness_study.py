"""Retrieve one survivorship-aware robustness study by full identity.

MILESTONE-064.
"""

from __future__ import annotations

from dataclasses import dataclass

from empirical_platform.decision_candidate.survivorship_study import (
    SurvivorshipAwareRobustnessStudy,
)
from empirical_platform.decision_candidate.survivorship_study_repository import (
    SurvivorshipAwareRobustnessStudyRepository,
)
from empirical_platform.identifiers.pairs import DomainIdentity
from empirical_platform.identifiers.types import SurvivorshipStudyId


@dataclass(frozen=True, slots=True)
class GetSurvivorshipAwareRobustnessStudyQuery:
    """Request to retrieve one survivorship-aware robustness study by
    canonical identity."""

    identity: DomainIdentity[SurvivorshipStudyId]


class GetSurvivorshipAwareRobustnessStudyHandler:
    """Retrieve one persisted survivorship-aware robustness study."""

    __slots__ = ("_repository",)

    def __init__(self, *, repository: SurvivorshipAwareRobustnessStudyRepository) -> None:
        self._repository = repository

    def handle(
        self, query: GetSurvivorshipAwareRobustnessStudyQuery
    ) -> SurvivorshipAwareRobustnessStudy:
        return self._repository.get(query.identity)
