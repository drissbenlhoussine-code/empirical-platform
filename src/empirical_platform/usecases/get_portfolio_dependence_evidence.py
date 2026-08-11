"""Retrieve one cross-instrument portfolio dependence report.

MILESTONE-068.
"""

from __future__ import annotations

from dataclasses import dataclass

from empirical_platform.decision_candidate.portfolio_dependence import PortfolioDependenceReport
from empirical_platform.decision_candidate.portfolio_dependence_repository import (
    PortfolioDependenceReportRepository,
)
from empirical_platform.identifiers.pairs import DomainIdentity
from empirical_platform.identifiers.types import PortfolioDependenceReportId


@dataclass(frozen=True, slots=True)
class GetPortfolioDependenceEvidenceQuery:
    """Request to retrieve one portfolio dependence report by canonical
    identity."""

    identity: DomainIdentity[PortfolioDependenceReportId]


class GetPortfolioDependenceEvidenceHandler:
    """Retrieve one persisted portfolio dependence report."""

    __slots__ = ("_repository",)

    def __init__(self, *, repository: PortfolioDependenceReportRepository) -> None:
        self._repository = repository

    def handle(self, query: GetPortfolioDependenceEvidenceQuery) -> PortfolioDependenceReport:
        return self._repository.get(query.identity)
