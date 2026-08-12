"""Domain-facing TradePlan repository contract (MILESTONE-059)."""

from __future__ import annotations

from typing import Protocol

from empirical_platform.decision_candidate.trade_plan import TradePlan
from empirical_platform.identifiers.pairs import DomainIdentity
from empirical_platform.identifiers.types import TradePlanId


class TradePlanRepository(Protocol):
    """Domain-facing, persistence-neutral repository contract for
    TradePlan.

    Deliberately narrower than the CQRS `get()`/`add()`/`save()` contract
    used by the four lifecycle aggregates, mirroring
    `DecisionCandidateRepository` (M057) and `TradingOpportunityScanRepository`
    (M058): a trade plan is immutable and never mutated after creation --
    if market conditions change, a new evaluation/scan/plan is built rather
    than revising the old one -- so there is no `save()` and no
    optimistic-concurrency concept. `add()` alone is the complete write
    surface.
    """

    def get(self, identity: DomainIdentity[TradePlanId]) -> TradePlan:
        """Load a TradePlan by canonical identity.

        Raises `AggregateNotFound` when no persisted plan exists for the
        identity.
        """
        ...

    def get_by_governance_id(self, governance_id: TradePlanId) -> TradePlan:
        """MILESTONE-072. Load a TradePlan by governance id alone (unique
        constraint makes this unambiguous), mirroring
        `DecisionCandidateRepository.get_by_governance_id`.

        Raises `AggregateNotFound` when no persisted plan exists for the
        governance id.
        """
        ...

    def add(self, plan: TradePlan) -> None:
        """Persist a new TradePlan that must not already exist.

        Raises `AggregateAlreadyExists` on duplicate `DomainIdentity`,
        governance_id, or runtime_id.
        """
        ...
