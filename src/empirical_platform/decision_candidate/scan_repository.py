"""Domain-facing TradingOpportunityScan repository contract (MILESTONE-058)."""

from __future__ import annotations

from typing import Protocol

from empirical_platform.decision_candidate.scan import TradingOpportunityScan
from empirical_platform.identifiers.pairs import DomainIdentity
from empirical_platform.identifiers.types import TradingOpportunityScanId


class TradingOpportunityScanRepository(Protocol):
    """Domain-facing, persistence-neutral repository contract for
    TradingOpportunityScan.

    Deliberately narrower than the CQRS `get()`/`add()`/`save()` contract
    used by the four lifecycle aggregates, mirroring `DecisionCandidateRepository`
    (MILESTONE-057): a scan is immutable and never mutated after creation, so
    there is no `save()` and no optimistic-concurrency concept -- `add()`
    alone is the complete write surface.
    """

    def get(self, identity: DomainIdentity[TradingOpportunityScanId]) -> TradingOpportunityScan:
        """Load a TradingOpportunityScan by canonical identity.

        Raises `AggregateNotFound` when no persisted scan exists for the
        identity.
        """
        ...

    def add(self, scan: TradingOpportunityScan) -> None:
        """Persist a new TradingOpportunityScan that must not already exist.

        Raises `AggregateAlreadyExists` on duplicate `DomainIdentity`,
        governance_id, or runtime_id.
        """
        ...
