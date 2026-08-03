"""Record a CriterionResult on an existing, COLLECTING EvidencePackage.

Concrete command and handler. MILESTONE-039.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from empirical_platform.evidence.repository import EvidencePackageRepository
from empirical_platform.evidence.results import CriterionResult
from empirical_platform.identifiers.pairs import DomainIdentity
from empirical_platform.identifiers.types import EvidencePackageId
from empirical_platform.shared.contracts.repository import SaveResult
from empirical_platform.shared.domain.versioning import AggregateVersion


@dataclass(frozen=True, slots=True)
class RecordEvidencePackageCriterionResultCommand:
    """Request to record one new CriterionResult on an existing EvidencePackage."""

    identity: DomainIdentity[EvidencePackageId]
    expected_persisted_version: AggregateVersion
    criterion_id: str
    recorded_at: datetime
    result_label: str
    summary: str | None = None
    evidence_references: tuple[str, ...] = ()


class RecordEvidencePackageCriterionResultHandler:
    """Loads, records a CriterionResult on, and persists one EvidencePackage for one command."""

    __slots__ = ("_evidence_package_repository",)

    def __init__(self, *, evidence_package_repository: EvidencePackageRepository) -> None:
        self._evidence_package_repository = evidence_package_repository

    def handle(self, command: RecordEvidencePackageCriterionResultCommand) -> SaveResult:
        """Record the requested CriterionResult on the identified EvidencePackage and persist it."""
        loaded = self._evidence_package_repository.get(command.identity)
        package = loaded.aggregate
        result = CriterionResult(
            evidence_package_id=package.identity.governance_id,
            criterion_id=command.criterion_id,
            recorded_at=command.recorded_at,
            result_label=command.result_label,
            summary=command.summary,
            evidence_references=command.evidence_references,
        )
        package.add_criterion_result(result)
        return self._evidence_package_repository.save(
            package, expected_persisted_version=command.expected_persisted_version
        )
