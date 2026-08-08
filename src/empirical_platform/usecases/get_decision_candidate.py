"""Retrieve a DecisionCandidate by full identity: concrete query and handler.

MILESTONE-057.
"""

from __future__ import annotations

from dataclasses import dataclass

from empirical_platform.decision_candidate.candidate import DecisionCandidate as DecisionCandidate
from empirical_platform.decision_candidate.repository import DecisionCandidateRepository
from empirical_platform.identifiers.pairs import DomainIdentity
from empirical_platform.identifiers.types import DecisionCandidateId


@dataclass(frozen=True, slots=True)
class GetDecisionCandidateQuery:
    """Request to retrieve a DecisionCandidate by its full frozen identity."""

    identity: DomainIdentity[DecisionCandidateId]


class GetDecisionCandidateHandler:
    """Retrieves a DecisionCandidate for one `GetDecisionCandidateQuery`."""

    __slots__ = ("_decision_candidate_repository",)

    def __init__(self, *, decision_candidate_repository: DecisionCandidateRepository) -> None:
        self._decision_candidate_repository = decision_candidate_repository

    def handle(self, query: GetDecisionCandidateQuery) -> DecisionCandidate:
        """Load a DecisionCandidate by identity and return it.

        No bounded snapshot is needed here (unlike the four lifecycle
        aggregates' own query handlers): `DecisionCandidate` is already
        immutable and carries no mutation/version internals to hide.
        """
        return self._decision_candidate_repository.get(query.identity)
