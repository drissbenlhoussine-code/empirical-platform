"""MILESTONE-074 -- Read-only M074-owned query boundary.

A M074-specific persistence-neutral query interface that composes
read-only queries over existing frozen M064 (survivorship_study,
survivorship_window, instrument_master) and M067 (portfolio_study)
persisted authorities, without modifying any frozen M064 or M067
repository contract.

This is the only place M074 reads those tables. M074 does not write
or mutate any persisted row.
"""

from __future__ import annotations

from typing import Protocol

from empirical_platform.decision_candidate.instrument_master import InstrumentMaster
from empirical_platform.decision_candidate.portfolio_study import PortfolioEvidenceReport
from empirical_platform.decision_candidate.survivorship_study import (
    SurvivorshipAwareRobustnessStudy,
)


class HistoricalPortfolioEvidenceQueryRepository(Protocol):
    """Read-only M074-owned query boundary. Composes existing frozen
    tables; does not add, remove, or alter any persisted row."""

    def list_survivorship_candidates(
        self,
    ) -> tuple[SurvivorshipAwareRobustnessStudy, ...]:
        """Return all persisted survivorship studies. Caller is
        responsible for further compatibility filtering."""
        ...

    def find_portfolio_report_for(
        self, source_study_runtime_id: str
    ) -> PortfolioEvidenceReport | None:
        """Return the M067 portfolio report whose persisted
        source_study_runtime_id equals the given M064 runtime id, or
        None."""
        ...

    def load_instrument_master(self) -> InstrumentMaster | None:
        """Return the current persisted InstrumentMaster, or None if
        the table is empty."""
        ...
