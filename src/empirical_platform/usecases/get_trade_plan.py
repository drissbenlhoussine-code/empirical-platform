"""Retrieve a TradePlan by full identity: concrete query and handler.

MILESTONE-059.
"""

from __future__ import annotations

from dataclasses import dataclass

from empirical_platform.decision_candidate.trade_plan import TradePlan as TradePlan
from empirical_platform.decision_candidate.trade_plan_repository import TradePlanRepository
from empirical_platform.identifiers.pairs import DomainIdentity
from empirical_platform.identifiers.types import TradePlanId


@dataclass(frozen=True, slots=True)
class GetTradePlanQuery:
    """Request to retrieve a TradePlan by its full frozen identity."""

    identity: DomainIdentity[TradePlanId]


class GetTradePlanHandler:
    """Retrieves a TradePlan for one `GetTradePlanQuery`."""

    __slots__ = ("_trade_plan_repository",)

    def __init__(self, *, trade_plan_repository: TradePlanRepository) -> None:
        self._trade_plan_repository = trade_plan_repository

    def handle(self, query: GetTradePlanQuery) -> TradePlan:
        """Load a TradePlan by identity and return it.

        No bounded snapshot is needed here (unlike the four lifecycle
        aggregates' own query handlers): `TradePlan` is already immutable
        and carries no mutation/version internals to hide.
        """
        return self._trade_plan_repository.get(query.identity)
