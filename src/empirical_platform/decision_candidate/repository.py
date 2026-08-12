"""Domain-facing DecisionCandidate repository contract (MILESTONE-057)."""

from __future__ import annotations

from typing import Protocol

from empirical_platform.decision_candidate.candidate import DecisionCandidate
from empirical_platform.identifiers.pairs import DomainIdentity
from empirical_platform.identifiers.types import DecisionCandidateId


class DecisionCandidateRepository(Protocol):
    """Domain-facing, persistence-neutral repository contract for
    DecisionCandidate.

    Deliberately narrower than the CQRS `get()`/`add()`/`save()` contract
    used by the four lifecycle aggregates: `DecisionCandidate` is immutable
    and never mutated after creation, so there is no `save()` and no
    optimistic-concurrency concept -- `add()` alone is the complete write
    surface.
    """

    def get(self, identity: DomainIdentity[DecisionCandidateId]) -> DecisionCandidate:
        """Load a DecisionCandidate by canonical identity.

        Raises `AggregateNotFound` when no persisted DecisionCandidate
        exists for the identity.
        """
        ...

    def get_by_governance_id(self, governance_id: DecisionCandidateId) -> DecisionCandidate:
        """MILESTONE-072. Load a DecisionCandidate by governance id alone.

        `governance_id` already carries a unique constraint, so this is
        unambiguous without a runtime_id. Added so a caller holding only
        a referenced governance id (e.g. `ResearchDecisionEntry
        .decision_candidate_governance_id`) can retrieve the full
        record -- including its rejection-reason codes -- without
        recomputing anything.

        Raises `AggregateNotFound` when no persisted DecisionCandidate
        exists for the governance id.
        """
        ...

    def add(self, candidate: DecisionCandidate) -> None:
        """Persist a new DecisionCandidate that must not already exist.

        Raises `AggregateAlreadyExists` on duplicate `DomainIdentity`,
        governance_id, or runtime_id.
        """
        ...
