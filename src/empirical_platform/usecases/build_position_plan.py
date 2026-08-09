"""Build a deterministic position-sized, capital-gated PositionPlan from an
already-persisted, authoritative M059 TradePlan.

Concrete command and handler. MILESTONE-060.
"""

from __future__ import annotations

from dataclasses import dataclass

from empirical_platform.decision_candidate.position_plan import (
    DEFAULT_SIZING_POLICY as DEFAULT_SIZING_POLICY,
)
from empirical_platform.decision_candidate.position_plan import (
    PositionPlan as PositionPlan,
)
from empirical_platform.decision_candidate.position_plan import (
    PositionSizingContext as PositionSizingContext,
)
from empirical_platform.decision_candidate.position_plan import SizingPolicy as SizingPolicy
from empirical_platform.decision_candidate.position_plan import build_position_plan
from empirical_platform.decision_candidate.position_plan_repository import PositionPlanRepository
from empirical_platform.decision_candidate.trade_plan_repository import TradePlanRepository
from empirical_platform.identifiers.pairs import DomainIdentity
from empirical_platform.identifiers.types import PositionPlanId, TradePlanId


@dataclass(frozen=True, slots=True)
class BuildPositionPlanCommand:
    """Request to build one deterministic position-sized plan from an
    already-persisted TradePlan plus caller-supplied sizing context."""

    identity: DomainIdentity[PositionPlanId]
    source_trade_plan_identity: DomainIdentity[TradePlanId]
    sizing_context: PositionSizingContext
    policy: SizingPolicy = DEFAULT_SIZING_POLICY


class BuildPositionPlanHandler:
    """Loads the authoritative source TradePlan, builds the PositionPlan,
    and persists it for one command."""

    __slots__ = ("_trade_plan_repository", "_position_plan_repository")

    def __init__(
        self,
        *,
        trade_plan_repository: TradePlanRepository,
        position_plan_repository: PositionPlanRepository,
    ) -> None:
        self._trade_plan_repository = trade_plan_repository
        self._position_plan_repository = position_plan_repository

    def handle(self, command: BuildPositionPlanCommand) -> PositionPlan:
        trade_plan = self._trade_plan_repository.get(command.source_trade_plan_identity)
        plan = build_position_plan(
            identity=command.identity,
            trade_plan=trade_plan,
            sizing_context=command.sizing_context,
            policy=command.policy,
        )
        self._position_plan_repository.add(plan)
        return plan
