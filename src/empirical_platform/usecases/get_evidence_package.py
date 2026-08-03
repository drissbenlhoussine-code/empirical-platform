"""Retrieve an EvidencePackage by full identity: concrete query and handler.

MILESTONE-037.
"""

from __future__ import annotations

from dataclasses import dataclass

from empirical_platform.evidence.lifecycle import EvidencePackageLifecycleState
from empirical_platform.evidence.repository import EvidencePackageRepository
from empirical_platform.identifiers.pairs import DomainIdentity
from empirical_platform.identifiers.types import EvidencePackageId, RunId


@dataclass(frozen=True, slots=True)
class GetEvidencePackageQuery:
    """Request to retrieve an EvidencePackage by its full frozen identity."""

    identity: DomainIdentity[EvidencePackageId]


@dataclass(frozen=True, slots=True)
class EvidencePackageSnapshot:
    """Immutable, milestone-local, bounded EvidencePackage header/status read value.

    Deliberately excludes `EvidencePackage.version` (aggregate domain state)
    and `LoadedAggregate.persisted_version` (repository concurrency
    metadata), and does not expose `criterion_results`, `artifact_references`,
    or `transition_history` -- see
    MILESTONE_037_CONCRETE_APPLICATION_QUERY_VERTICAL_SLICE_EVIDENCE_PACKAGE_RETRIEVAL_MACRO_DESIGN.md
    Section 6.
    """

    identity: DomainIdentity[EvidencePackageId]
    run_id: RunId
    state: EvidencePackageLifecycleState


class GetEvidencePackageHandler:
    """Retrieves an EvidencePackage for one `GetEvidencePackageQuery`."""

    __slots__ = ("_evidence_package_repository",)

    def __init__(self, *, evidence_package_repository: EvidencePackageRepository) -> None:
        self._evidence_package_repository = evidence_package_repository

    def handle(self, query: GetEvidencePackageQuery) -> EvidencePackageSnapshot:
        """Load an EvidencePackage by identity and return its bounded read-side snapshot."""
        loaded = self._evidence_package_repository.get(query.identity)
        return EvidencePackageSnapshot(
            identity=loaded.aggregate.identity,
            run_id=loaded.aggregate.run_id,
            state=loaded.aggregate.state,
        )
