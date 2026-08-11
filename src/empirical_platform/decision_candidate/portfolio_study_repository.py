"""Persistence-neutral repository contract for M067 portfolio
capital-allocation evidence reports."""

from __future__ import annotations

from typing import Protocol

from empirical_platform.decision_candidate.portfolio_study import PortfolioEvidenceReport
from empirical_platform.identifiers.pairs import DomainIdentity
from empirical_platform.identifiers.types import PortfolioStudyId


class PortfolioStudyRepository(Protocol):
    """Persistence-neutral repository contract for immutable portfolio
    capital-allocation evidence reports."""

    def get(self, identity: DomainIdentity[PortfolioStudyId]) -> PortfolioEvidenceReport:
        """Load a portfolio evidence report by canonical identity."""
        ...

    def add(self, report: PortfolioEvidenceReport) -> None:
        """Persist a new portfolio evidence report that must not already
        exist."""
        ...
