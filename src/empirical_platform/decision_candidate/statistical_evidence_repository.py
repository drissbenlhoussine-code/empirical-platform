"""Persistence-neutral repository contract for M066 statistical evidence
reports."""

from __future__ import annotations

from typing import Protocol

from empirical_platform.decision_candidate.statistical_evidence import StatisticalEvidenceReport
from empirical_platform.identifiers.pairs import DomainIdentity
from empirical_platform.identifiers.types import StatisticalEvidenceReportId


class StatisticalEvidenceReportRepository(Protocol):
    """Persistence-neutral repository contract for immutable statistical
    evidence reports."""

    def get(
        self, identity: DomainIdentity[StatisticalEvidenceReportId]
    ) -> StatisticalEvidenceReport:
        """Load a statistical evidence report by canonical identity."""
        ...

    def add(self, report: StatisticalEvidenceReport) -> None:
        """Persist a new statistical evidence report that must not
        already exist."""
        ...
