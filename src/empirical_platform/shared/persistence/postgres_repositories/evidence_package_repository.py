"""Concrete PostgreSQL `EvidencePackageRepository` adapter (MILESTONE-023).

Implements the frozen `EvidencePackageRepository` Protocol (MILESTONE-020)
against the frozen `evidence_package`/`evidence_package_criterion_result`/
`evidence_package_artifact_reference`/`evidence_package_transition` schema
(MILESTONE-022), using the frozen `EvidencePackageMapper` contract
(MILESTONE-021), exactly per
MILESTONE_023_POSTGRESQL_REPOSITORY_ADAPTER_DESIGN.md Sections 6-9.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, cast

from empirical_platform.evidence._reconstruction import _reconstruct_evidence_package
from empirical_platform.evidence.mapper import (
    ConcreteEvidencePackageMapper,
    CriterionResultDurableRecord,
    EvidencePackageDurableRecord,
    EvidencePackageMapper,
)
from empirical_platform.evidence.package import EvidencePackage
from empirical_platform.identifiers.pairs import DomainIdentity
from empirical_platform.identifiers.types import EvidencePackageId
from empirical_platform.shared.contracts.mapping import (
    IdentityDurableRecord,
    MapperError,
    TransitionDurableRecord,
)
from empirical_platform.shared.contracts.repository import (
    AggregateAlreadyExists,
    AggregateNotFound,
    InvalidAggregateForPersistence,
    InvalidPersistedAggregateState,
    LoadedAggregate,
    OptimisticConcurrencyConflict,
    SaveOperation,
    SaveResult,
)
from empirical_platform.shared.domain.reconstruction import ReconstructionError
from empirical_platform.shared.domain.versioning import AggregateVersion
from empirical_platform.shared.errors import FoundationError
from empirical_platform.shared.persistence.postgres import PostgresPersistenceService
from empirical_platform.shared.persistence.postgres_repositories._errors import (
    unique_violation_constraint_name,
)

_AGGREGATE_KIND = "EvidencePackage"
_ROOT_UNIQUE_CONSTRAINTS = {"pk_evidence_package", "uq_evidence_package_governance_id"}


def _row_to_transition(row: Mapping[str, Any]) -> TransitionDurableRecord:
    identity_reference: IdentityDurableRecord | None = None
    if row["identity_runtime_id"] is not None:
        identity_reference = IdentityDurableRecord(
            governance_id=str(row["identity_governance_id"]),
            runtime_id=str(row["identity_runtime_id"]),
        )
    return TransitionDurableRecord(
        from_state=row["from_state"],
        to_state=str(row["to_state"]),
        version=cast(int, row["version"]),
        sequence=cast(int, row["sequence"]),
        actor=str(row["actor"]),
        occurred_at=row["occurred_at"],
        identity_reference=identity_reference,
        correlation_id=row["correlation_id"],
        reason=row["reason"],
    )


def _transition_params(
    evidence_package_runtime_id: str, transition: TransitionDurableRecord
) -> dict[str, Any]:
    identity_reference = transition.identity_reference
    return {
        "evidence_package_runtime_id": evidence_package_runtime_id,
        "sequence": transition.sequence,
        "from_state": transition.from_state,
        "to_state": transition.to_state,
        "version": transition.version,
        "actor": transition.actor,
        "occurred_at": transition.occurred_at,
        "identity_governance_id": (
            identity_reference.governance_id if identity_reference is not None else None
        ),
        "identity_runtime_id": (
            identity_reference.runtime_id if identity_reference is not None else None
        ),
        "correlation_id": transition.correlation_id,
        "reason": transition.reason,
    }


def _row_to_criterion(
    row: Mapping[str, Any], evidence_package_governance_id: str
) -> CriterionResultDurableRecord:
    return CriterionResultDurableRecord(
        evidence_package_id=evidence_package_governance_id,
        criterion_id=str(row["criterion_id"]),
        recorded_at=row["recorded_at"],
        result_label=str(row["result_label"]),
        summary=row["summary"],
        evidence_references=tuple(row["evidence_references"]),
    )


def _criterion_params(
    evidence_package_runtime_id: str, position: int, result: CriterionResultDurableRecord
) -> dict[str, Any]:
    return {
        "evidence_package_runtime_id": evidence_package_runtime_id,
        "position": position,
        "criterion_id": result.criterion_id,
        "recorded_at": result.recorded_at,
        "result_label": result.result_label,
        "summary": result.summary,
        "evidence_references": list(result.evidence_references),
    }


class PostgresEvidencePackageRepository:
    """Concrete, storage-aware `EvidencePackageRepository` implementation."""

    def __init__(
        self,
        service: PostgresPersistenceService,
        mapper: EvidencePackageMapper | None = None,
    ) -> None:
        self._service = service
        self._mapper: EvidencePackageMapper = (
            mapper if mapper is not None else ConcreteEvidencePackageMapper()
        )

    def get(self, identity: DomainIdentity[EvidencePackageId]) -> LoadedAggregate[EvidencePackage]:
        """Load an EvidencePackage by canonical identity (Design Section 6)."""
        with self._service.unit_of_work() as work:
            rows = work.execute(
                "SELECT * FROM evidence_package WHERE runtime_id = :runtime_id "
                "AND governance_id = :governance_id",
                {
                    "runtime_id": str(identity.runtime_id),
                    "governance_id": str(identity.governance_id),
                },
            )
            if not rows:
                diagnostic_rows = work.execute(
                    "SELECT governance_id FROM evidence_package WHERE runtime_id = :runtime_id",
                    {"runtime_id": str(identity.runtime_id)},
                )
                if not diagnostic_rows:
                    raise AggregateNotFound(aggregate_kind=_AGGREGATE_KIND, identity=identity)
                raise InvalidPersistedAggregateState(
                    aggregate_kind=_AGGREGATE_KIND,
                    reason=(
                        "persisted governance_id does not match the requested "
                        "identity's governance_id for this runtime_id"
                    ),
                    identity=identity,
                )
            root = rows[0]
            criterion_rows = work.execute(
                "SELECT * FROM evidence_package_criterion_result "
                "WHERE evidence_package_runtime_id = :runtime_id ORDER BY position",
                {"runtime_id": str(identity.runtime_id)},
            )
            artifact_rows = work.execute(
                "SELECT * FROM evidence_package_artifact_reference "
                "WHERE evidence_package_runtime_id = :runtime_id ORDER BY position",
                {"runtime_id": str(identity.runtime_id)},
            )
            transition_rows = work.execute(
                "SELECT * FROM evidence_package_transition "
                "WHERE evidence_package_runtime_id = :runtime_id ORDER BY sequence",
                {"runtime_id": str(identity.runtime_id)},
            )
            record = EvidencePackageDurableRecord(
                identity=IdentityDurableRecord(
                    governance_id=str(root["governance_id"]),
                    runtime_id=str(root["runtime_id"]),
                ),
                run_id=str(root["run_id"]),
                lifecycle_state=str(root["lifecycle_state"]),
                criterion_results=tuple(
                    _row_to_criterion(row, str(root["governance_id"])) for row in criterion_rows
                ),
                artifact_references=tuple(str(row["value"]) for row in artifact_rows),
                version=cast(int, root["version"]),
                next_transition_sequence=cast(int, root["next_transition_sequence"]),
                transition_history=tuple(_row_to_transition(row) for row in transition_rows),
            )
            try:
                state = self._mapper.from_durable_record(record)
            except MapperError as exc:
                raise InvalidPersistedAggregateState(
                    aggregate_kind=_AGGREGATE_KIND, reason=exc.safe_message, identity=identity
                ) from exc
            try:
                aggregate = _reconstruct_evidence_package(state)
            except ReconstructionError as exc:
                raise InvalidPersistedAggregateState(
                    aggregate_kind=_AGGREGATE_KIND, reason=str(exc), identity=identity
                ) from exc
            persisted_version = AggregateVersion(cast(int, root["version"]))
        return LoadedAggregate(aggregate=aggregate, persisted_version=persisted_version)

    def add(self, aggregate: EvidencePackage) -> SaveResult:
        """Persist a new EvidencePackage that must not already exist (Design Section 7)."""
        identity = aggregate.identity
        try:
            record = self._mapper.to_durable_record(aggregate)
        except MapperError as exc:
            raise InvalidAggregateForPersistence(
                aggregate_kind=_AGGREGATE_KIND, reason=exc.safe_message
            ) from exc

        with self._service.unit_of_work() as work:
            try:
                work.execute(
                    "INSERT INTO evidence_package "
                    "(runtime_id, governance_id, run_id, lifecycle_state, "
                    "version, next_transition_sequence) "
                    "VALUES (:runtime_id, :governance_id, :run_id, "
                    ":lifecycle_state, :version, :next_transition_sequence)",
                    {
                        "runtime_id": record.identity.runtime_id,
                        "governance_id": record.identity.governance_id,
                        "run_id": record.run_id,
                        "lifecycle_state": record.lifecycle_state,
                        "version": record.version,
                        "next_transition_sequence": record.next_transition_sequence,
                    },
                )
                for position, criterion in enumerate(record.criterion_results):
                    work.execute(
                        "INSERT INTO evidence_package_criterion_result "
                        "(evidence_package_runtime_id, position, criterion_id, "
                        "recorded_at, result_label, summary, evidence_references) "
                        "VALUES (:evidence_package_runtime_id, :position, :criterion_id, "
                        ":recorded_at, :result_label, :summary, :evidence_references)",
                        _criterion_params(record.identity.runtime_id, position, criterion),
                    )
                for position, value in enumerate(record.artifact_references):
                    work.execute(
                        "INSERT INTO evidence_package_artifact_reference "
                        "(evidence_package_runtime_id, position, value) "
                        "VALUES (:evidence_package_runtime_id, :position, :value)",
                        {
                            "evidence_package_runtime_id": record.identity.runtime_id,
                            "position": position,
                            "value": value,
                        },
                    )
                for transition in record.transition_history:
                    work.execute(
                        "INSERT INTO evidence_package_transition "
                        "(evidence_package_runtime_id, sequence, from_state, to_state, "
                        "version, actor, occurred_at, identity_governance_id, "
                        "identity_runtime_id, correlation_id, reason) "
                        "VALUES (:evidence_package_runtime_id, :sequence, :from_state, "
                        ":to_state, :version, :actor, :occurred_at, "
                        ":identity_governance_id, :identity_runtime_id, :correlation_id, "
                        ":reason)",
                        _transition_params(record.identity.runtime_id, transition),
                    )
            except FoundationError as exc:
                constraint_name = unique_violation_constraint_name(exc)
                if constraint_name in _ROOT_UNIQUE_CONSTRAINTS:
                    raise AggregateAlreadyExists(
                        aggregate_kind=_AGGREGATE_KIND, identity=identity
                    ) from exc
                raise

        return SaveResult(
            operation=SaveOperation.CREATED,
            persisted_version=AggregateVersion(record.version),
        )

    def save(
        self, aggregate: EvidencePackage, *, expected_persisted_version: AggregateVersion
    ) -> SaveResult:
        """Persist an existing EvidencePackage guarded by optimistic concurrency.

        See Design Section 8.
        """
        identity = aggregate.identity
        try:
            record = self._mapper.to_durable_record(aggregate)
        except MapperError as exc:
            raise InvalidAggregateForPersistence(
                aggregate_kind=_AGGREGATE_KIND, reason=exc.safe_message
            ) from exc

        if record.version < expected_persisted_version.value:
            raise InvalidAggregateForPersistence(
                aggregate_kind=_AGGREGATE_KIND,
                reason="aggregate current version is lower than expected persisted version",
                identity=identity,
            )

        intended_operation = (
            SaveOperation.UNCHANGED
            if record.version == expected_persisted_version.value
            else SaveOperation.UPDATED
        )

        with self._service.unit_of_work() as work:
            update_rows = work.execute(
                "UPDATE evidence_package "
                "SET run_id = :run_id, lifecycle_state = :lifecycle_state, "
                "next_transition_sequence = :next_transition_sequence, "
                "version = :record_version "
                "WHERE runtime_id = :runtime_id AND governance_id = :governance_id "
                "AND version = :expected_persisted_version "
                "RETURNING version",
                {
                    "run_id": record.run_id,
                    "lifecycle_state": record.lifecycle_state,
                    "next_transition_sequence": record.next_transition_sequence,
                    "record_version": record.version,
                    "runtime_id": record.identity.runtime_id,
                    "governance_id": record.identity.governance_id,
                    "expected_persisted_version": expected_persisted_version.value,
                },
            )
            if not update_rows:
                diagnostic_rows = work.execute(
                    "SELECT governance_id, version FROM evidence_package "
                    "WHERE runtime_id = :runtime_id",
                    {"runtime_id": record.identity.runtime_id},
                )
                if not diagnostic_rows:
                    raise AggregateNotFound(aggregate_kind=_AGGREGATE_KIND, identity=identity)
                diagnostic_row = diagnostic_rows[0]
                if diagnostic_row["governance_id"] != record.identity.governance_id:
                    raise InvalidPersistedAggregateState(
                        aggregate_kind=_AGGREGATE_KIND,
                        reason=(
                            "persisted governance_id does not match the aggregate's "
                            "identity for this runtime_id"
                        ),
                        identity=identity,
                    )
                raise OptimisticConcurrencyConflict(
                    aggregate_kind=_AGGREGATE_KIND,
                    identity=identity,
                    expected_persisted_version=expected_persisted_version,
                    aggregate_current_version=AggregateVersion(record.version),
                    actual_persisted_version=AggregateVersion(cast(int, diagnostic_row["version"])),
                )

            if intended_operation is SaveOperation.UPDATED:
                work.execute(
                    "DELETE FROM evidence_package_criterion_result "
                    "WHERE evidence_package_runtime_id = :runtime_id",
                    {"runtime_id": record.identity.runtime_id},
                )
                work.execute(
                    "DELETE FROM evidence_package_artifact_reference "
                    "WHERE evidence_package_runtime_id = :runtime_id",
                    {"runtime_id": record.identity.runtime_id},
                )
                work.execute(
                    "DELETE FROM evidence_package_transition "
                    "WHERE evidence_package_runtime_id = :runtime_id",
                    {"runtime_id": record.identity.runtime_id},
                )
                for position, criterion in enumerate(record.criterion_results):
                    work.execute(
                        "INSERT INTO evidence_package_criterion_result "
                        "(evidence_package_runtime_id, position, criterion_id, "
                        "recorded_at, result_label, summary, evidence_references) "
                        "VALUES (:evidence_package_runtime_id, :position, :criterion_id, "
                        ":recorded_at, :result_label, :summary, :evidence_references)",
                        _criterion_params(record.identity.runtime_id, position, criterion),
                    )
                for position, value in enumerate(record.artifact_references):
                    work.execute(
                        "INSERT INTO evidence_package_artifact_reference "
                        "(evidence_package_runtime_id, position, value) "
                        "VALUES (:evidence_package_runtime_id, :position, :value)",
                        {
                            "evidence_package_runtime_id": record.identity.runtime_id,
                            "position": position,
                            "value": value,
                        },
                    )
                for transition in record.transition_history:
                    work.execute(
                        "INSERT INTO evidence_package_transition "
                        "(evidence_package_runtime_id, sequence, from_state, to_state, "
                        "version, actor, occurred_at, identity_governance_id, "
                        "identity_runtime_id, correlation_id, reason) "
                        "VALUES (:evidence_package_runtime_id, :sequence, :from_state, "
                        ":to_state, :version, :actor, :occurred_at, "
                        ":identity_governance_id, :identity_runtime_id, :correlation_id, "
                        ":reason)",
                        _transition_params(record.identity.runtime_id, transition),
                    )

            operation = intended_operation
            persisted_version = AggregateVersion(record.version)

        return SaveResult(operation=operation, persisted_version=persisted_version)
