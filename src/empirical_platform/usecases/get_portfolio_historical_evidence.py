"""Retrieve one portfolio capital-allocation evidence report.

MILESTONE-067.
"""

from __future__ import annotations

from dataclasses import dataclass

from empirical_platform.decision_candidate.portfolio_study import PortfolioEvidenceReport
from empirical_platform.decision_candidate.portfolio_study_repository import (
    PortfolioStudyRepository,
)
from empirical_platform.identifiers.pairs import DomainIdentity
from empirical_platform.identifiers.types import PortfolioStudyId


@dataclass(frozen=True, slots=True)
class GetPortfolioHistoricalEvidenceQuery:
    """Request to retrieve one portfolio evidence report by canonical
    identity."""

    identity: DomainIdentity[PortfolioStudyId]


class GetPortfolioHistoricalEvidenceHandler:
    """Retrieve one persisted portfolio evidence report."""

    __slots__ = ("_repository",)

    def __init__(self, *, repository: PortfolioStudyRepository) -> None:
        self._repository = repository

    def handle(self, query: GetPortfolioHistoricalEvidenceQuery) -> PortfolioEvidenceReport:
        return self._repository.get(query.identity)
