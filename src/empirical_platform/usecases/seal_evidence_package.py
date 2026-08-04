"""Seal an existing, COLLECTING EvidencePackage: concrete command and handler.

MILESTONE-041.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from empirical_platform.evidence.repository import EvidencePackageRepository
from empirical_platform.identifiers.pairs import DomainIdentity
from empirical_platform.identifiers.types import EvidencePackageId
from empirical_platform.shared.contracts.repository import SaveResult
from empirical_platform.shared.domain.versioning import AggregateVersion


@dataclass(frozen=True, slots=True)
class SealEvidencePackageCommand:
    """Request to transition an existing EvidencePackage from COLLECTING to SEALED."""

    identity: DomainIdentity[EvidencePackageId]
    expected_persisted_version: AggregateVersion
    actor: str
    occurred_at: datetime
    correlation_id: str | None = None
    reason: str | None = None


class SealEvidencePackageHandler:
    """Loads, seals, and persists one EvidencePackage for one command."""

    __slots__ = ("_evidence_package_repository",)

    def __init__(self, *, evidence_package_repository: EvidencePackageRepository) -> None:
        self._evidence_package_repository = evidence_package_repository

    def handle(self, command: SealEvidencePackageCommand) -> SaveResult:
        """Transition the identified EvidencePackage to SEALED and persist it."""
        loaded = self._evidence_package_repository.get(command.identity)
        package = loaded.aggregate
        package.seal(
            actor=command.actor,
            occurred_at=command.occurred_at,
            correlation_id=command.correlation_id,
            reason=command.reason,
        )
        return self._evidence_package_repository.save(
            package, expected_persisted_version=command.expected_persisted_version
        )
