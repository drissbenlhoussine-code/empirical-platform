"""Retrieve one historical validation study by full identity.

MILESTONE-062.
"""

from __future__ import annotations

from dataclasses import dataclass

from empirical_platform.decision_candidate.validation_study import HistoricalValidationStudy
from empirical_platform.decision_candidate.validation_study_repository import (
    HistoricalValidationStudyRepository,
)
from empirical_platform.identifiers.pairs import DomainIdentity
from empirical_platform.identifiers.types import ValidationStudyId


@dataclass(frozen=True, slots=True)
class GetHistoricalValidationStudyQuery:
    """Request to retrieve one validation study by canonical identity."""

    identity: DomainIdentity[ValidationStudyId]


class GetHistoricalValidationStudyHandler:
    """Retrieve one persisted validation study."""

    __slots__ = ("_repository",)

    def __init__(self, *, repository: HistoricalValidationStudyRepository) -> None:
        self._repository = repository

    def handle(self, query: GetHistoricalValidationStudyQuery) -> HistoricalValidationStudy:
        return self._repository.get(query.identity)
