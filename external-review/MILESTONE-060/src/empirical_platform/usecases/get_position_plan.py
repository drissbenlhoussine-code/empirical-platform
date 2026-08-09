"""Retrieve a PositionPlan by full identity: concrete query and handler.

MILESTONE-060.
"""

from __future__ import annotations

from dataclasses import dataclass

from empirical_platform.decision_candidate.position_plan import PositionPlan as PositionPlan
from empirical_platform.decision_candidate.position_plan_repository import PositionPlanRepository
from empirical_platform.identifiers.pairs import DomainIdentity
from empirical_platform.identifiers.types import PositionPlanId


@dataclass(frozen=True, slots=True)
class GetPositionPlanQuery:
    """Request to retrieve one PositionPlan by its full frozen identity."""

    identity: DomainIdentity[PositionPlanId]


class GetPositionPlanHandler:
    """Retrieves a PositionPlan for one `GetPositionPlanQuery`."""

    __slots__ = ("_position_plan_repository",)

    def __init__(self, *, position_plan_repository: PositionPlanRepository) -> None:
        self._position_plan_repository = position_plan_repository

    def handle(self, query: GetPositionPlanQuery) -> PositionPlan:
        return self._position_plan_repository.get(query.identity)
