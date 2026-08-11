"""Persistence-neutral repository contract for M068 cross-instrument
dependence / correlation-aware portfolio risk reports."""

from __future__ import annotations

from typing import Protocol

from empirical_platform.decision_candidate.portfolio_dependence import PortfolioDependenceReport
from empirical_platform.identifiers.pairs import DomainIdentity
from empirical_platform.identifiers.types import PortfolioDependenceReportId


class PortfolioDependenceReportRepository(Protocol):
    """Persistence-neutral repository contract for immutable
    cross-instrument dependence reports."""

    def get(
        self, identity: DomainIdentity[PortfolioDependenceReportId]
    ) -> PortfolioDependenceReport:
        """Load a portfolio dependence report by canonical identity."""
        ...

    def add(self, report: PortfolioDependenceReport) -> None:
        """Persist a new portfolio dependence report that must not
        already exist."""
        ...
