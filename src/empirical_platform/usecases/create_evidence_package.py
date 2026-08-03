"""Create a new EvidencePackage for an existing Run: concrete command and handler.

MILESTONE-036.
"""

from __future__ import annotations

from dataclasses import dataclass

from empirical_platform.evidence.package import EvidencePackage
from empirical_platform.evidence.repository import EvidencePackageRepository
from empirical_platform.identifiers.pairs import DomainIdentity
from empirical_platform.identifiers.types import EvidencePackageId, RunId
from empirical_platform.shared.identifiers import RuntimeIdentifierGenerator


@dataclass(frozen=True, slots=True)
class CreateEvidencePackageCommand:
    """Request to create a new EvidencePackage for an existing Run.

    Carries raw, unvalidated data; `CreateEvidencePackageHandler` translates
    it into the already-frozen `EvidencePackageId` and `RunId` value
    objects, which perform all format validation. Run existence is not
    validated here or in the handler -- it is enforced by the database
    foreign-key constraint on the `evidence_package.run_id` column (see
    MILESTONE_036_CONCRETE_APPLICATION_COMMAND_VERTICAL_SLICE_EVIDENCE_PACKAGE_CREATION_DESIGN.md
    Section 5).
    """

    evidence_package_governance_id: str
    run_governance_id: str


class CreateEvidencePackageHandler:
    """Creates and persists a new EvidencePackage for one command."""

    __slots__ = ("_evidence_package_repository", "_runtime_identifier_generator")

    def __init__(
        self,
        *,
        evidence_package_repository: EvidencePackageRepository,
        runtime_identifier_generator: RuntimeIdentifierGenerator,
    ) -> None:
        self._evidence_package_repository = evidence_package_repository
        self._runtime_identifier_generator = runtime_identifier_generator

    def handle(self, command: CreateEvidencePackageCommand) -> DomainIdentity[EvidencePackageId]:
        """Create and persist a new EvidencePackage; return its identity."""
        identity = DomainIdentity(
            governance_id=EvidencePackageId(command.evidence_package_governance_id),
            runtime_id=self._runtime_identifier_generator.generate(),
        )
        package = EvidencePackage(
            identity=identity,
            run_id=RunId(command.run_governance_id),
        )
        self._evidence_package_repository.add(package)
        return package.identity
