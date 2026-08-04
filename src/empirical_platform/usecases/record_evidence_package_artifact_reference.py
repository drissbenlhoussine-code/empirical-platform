"""Record an ArtifactReference on an existing, COLLECTING EvidencePackage.

Concrete command and handler. MILESTONE-040.
"""

from __future__ import annotations

from dataclasses import dataclass

from empirical_platform.evidence.package import ArtifactReference
from empirical_platform.evidence.repository import EvidencePackageRepository
from empirical_platform.identifiers.pairs import DomainIdentity
from empirical_platform.identifiers.types import EvidencePackageId
from empirical_platform.shared.contracts.repository import SaveResult
from empirical_platform.shared.domain.versioning import AggregateVersion


@dataclass(frozen=True, slots=True)
class RecordEvidencePackageArtifactReferenceCommand:
    """Request to record one new ArtifactReference on an existing EvidencePackage."""

    identity: DomainIdentity[EvidencePackageId]
    expected_persisted_version: AggregateVersion
    value: str


class RecordEvidencePackageArtifactReferenceHandler:
    """Loads, records an ArtifactReference on, and persists one EvidencePackage for one command."""

    __slots__ = ("_evidence_package_repository",)

    def __init__(self, *, evidence_package_repository: EvidencePackageRepository) -> None:
        self._evidence_package_repository = evidence_package_repository

    def handle(self, command: RecordEvidencePackageArtifactReferenceCommand) -> SaveResult:
        """Record the requested ArtifactReference on the EvidencePackage, then persist it."""
        loaded = self._evidence_package_repository.get(command.identity)
        package = loaded.aggregate
        package.add_artifact_reference(ArtifactReference(value=command.value))
        return self._evidence_package_repository.save(
            package, expected_persisted_version=command.expected_persisted_version
        )
