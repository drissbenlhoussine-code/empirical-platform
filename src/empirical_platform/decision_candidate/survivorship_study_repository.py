"""Persistence-neutral repository contract for M064 survivorship-aware
robustness studies."""

from __future__ import annotations

from typing import Protocol

from empirical_platform.decision_candidate.survivorship_study import (
    SurvivorshipAwareRobustnessStudy,
)
from empirical_platform.identifiers.pairs import DomainIdentity
from empirical_platform.identifiers.types import SurvivorshipStudyId


class SurvivorshipAwareRobustnessStudyRepository(Protocol):
    """Persistence-neutral repository contract for immutable
    survivorship-aware robustness studies."""

    def get(
        self, identity: DomainIdentity[SurvivorshipStudyId]
    ) -> SurvivorshipAwareRobustnessStudy:
        """Load a survivorship-aware robustness study by canonical identity."""
        ...

    def add(self, study: SurvivorshipAwareRobustnessStudy) -> None:
        """Persist a new survivorship-aware robustness study that must not already exist."""
        ...
