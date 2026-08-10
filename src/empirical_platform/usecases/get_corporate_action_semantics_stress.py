"""Retrieve one corporate-action semantics stress diagnostic result.

MILESTONE-065.
"""

from __future__ import annotations

from dataclasses import dataclass

from empirical_platform.decision_candidate.corporate_action_stress import (
    CorporateActionSemanticsStressResult,
)
from empirical_platform.decision_candidate.dataset_snapshot_repository import (
    CorporateActionSemanticsStressRepository,
)
from empirical_platform.identifiers.pairs import DomainIdentity
from empirical_platform.identifiers.types import CorporateActionStressId


@dataclass(frozen=True, slots=True)
class GetCorporateActionSemanticsStressQuery:
    """Request to retrieve one stress diagnostic result by canonical
    identity."""

    identity: DomainIdentity[CorporateActionStressId]


class GetCorporateActionSemanticsStressHandler:
    """Retrieve one persisted stress diagnostic result."""

    __slots__ = ("_repository",)

    def __init__(self, *, repository: CorporateActionSemanticsStressRepository) -> None:
        self._repository = repository

    def handle(
        self, query: GetCorporateActionSemanticsStressQuery
    ) -> CorporateActionSemanticsStressResult:
        return self._repository.get(query.identity)
