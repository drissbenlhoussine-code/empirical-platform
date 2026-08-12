"""Domain-facing PositionPlan repository contract (MILESTONE-060)."""

from __future__ import annotations

from typing import Protocol

from empirical_platform.decision_candidate.position_plan import PositionPlan
from empirical_platform.identifiers.pairs import DomainIdentity
from empirical_platform.identifiers.types import PositionPlanId


class PositionPlanRepository(Protocol):
    """Persistence-neutral repository contract for immutable PositionPlan."""

    def get(self, identity: DomainIdentity[PositionPlanId]) -> PositionPlan:
        """Load a PositionPlan by canonical identity."""
        ...

    def get_by_governance_id(self, governance_id: PositionPlanId) -> PositionPlan:
        """MILESTONE-072. Load a PositionPlan by governance id alone
        (unique constraint makes this unambiguous), mirroring
        `DecisionCandidateRepository.get_by_governance_id`."""
        ...

    def add(self, plan: PositionPlan) -> None:
        """Persist a new PositionPlan that must not already exist."""
        ...
