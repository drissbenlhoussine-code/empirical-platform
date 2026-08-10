"""Retrieve one statistical evidence report.

MILESTONE-066.
"""

from __future__ import annotations

from dataclasses import dataclass

from empirical_platform.decision_candidate.statistical_evidence import StatisticalEvidenceReport
from empirical_platform.decision_candidate.statistical_evidence_repository import (
    StatisticalEvidenceReportRepository,
)
from empirical_platform.identifiers.pairs import DomainIdentity
from empirical_platform.identifiers.types import StatisticalEvidenceReportId


@dataclass(frozen=True, slots=True)
class GetStatisticalEvidenceReportQuery:
    """Request to retrieve one statistical evidence report by canonical
    identity."""

    identity: DomainIdentity[StatisticalEvidenceReportId]


class GetStatisticalEvidenceReportHandler:
    """Retrieve one persisted statistical evidence report."""

    __slots__ = ("_repository",)

    def __init__(self, *, repository: StatisticalEvidenceReportRepository) -> None:
        self._repository = repository

    def handle(self, query: GetStatisticalEvidenceReportQuery) -> StatisticalEvidenceReport:
        return self._repository.get(query.identity)
