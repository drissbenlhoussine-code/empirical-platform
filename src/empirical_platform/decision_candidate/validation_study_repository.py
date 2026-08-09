"""Persistence-neutral repository contract for M062 historical validation
studies."""

from __future__ import annotations

from typing import Protocol

from empirical_platform.decision_candidate.validation_study import HistoricalValidationStudy
from empirical_platform.identifiers.pairs import DomainIdentity
from empirical_platform.identifiers.types import ValidationStudyId


class HistoricalValidationStudyRepository(Protocol):
    """Persistence-neutral repository contract for immutable validation
    studies."""

    def get(self, identity: DomainIdentity[ValidationStudyId]) -> HistoricalValidationStudy:
        """Load a validation study by canonical identity."""
        ...

    def add(self, study: HistoricalValidationStudy) -> None:
        """Persist a new validation study that must not already exist."""
        ...
