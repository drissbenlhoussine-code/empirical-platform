"""Concrete PostgreSQL `RunRepository` adapter (MILESTONE-023).

Implements the frozen `RunRepository` Protocol (MILESTONE-020) against the
frozen `run`/`run_manifest`/`run_transition` schema (MILESTONE-022), using the
frozen `RunMapper` contract (MILESTONE-021), exactly per
MILESTONE_023_POSTGRESQL_REPOSITORY_ADAPTER_DESIGN.md Sections 6-9.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, cast

from empirical_platform.identifiers.pairs import DomainIdentity
from empirical_platform.identifiers.types import RunId
from empirical_platform.run._reconstruction import _reconstruct_run
from empirical_platform.run.aggregate import Run
from empirical_platform.run.mapper import (
    ConcreteRunMapper,
    DatasetManifestDurableRecord,
    RunDurableRecord,
    RunMapper,
)
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

_AGGREGATE_KIND = "Run"
_ROOT_UNIQUE_CONSTRAINTS = {"pk_run", "uq_run_governance_id"}


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


def _transition_params(run_runtime_id: str, transition: TransitionDurableRecord) -> dict[str, Any]:
    identity_reference = transition.identity_reference
    return {
        "run_runtime_id": run_runtime_id,
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


def _row_to_manifest(
    row: Mapping[str, Any], run_governance_id: str
) -> DatasetManifestDurableRecord:
    return DatasetManifestDurableRecord(
        run_id=run_governance_id,
        recorded_at=row["recorded_at"],
        source=str(row["source"]),
        acquisition_method=row["acquisition_method"],
        normalization_method=row["normalization_method"],
        manifest_id=row["manifest_id"],
        notes=tuple(row["notes"]),
    )


def _manifest_params(
    run_runtime_id: str, position: int, manifest: DatasetManifestDurableRecord
) -> dict[str, Any]:
    return {
        "run_runtime_id": run_runtime_id,
        "position": position,
        "manifest_id": manifest.manifest_id,
        "recorded_at": manifest.recorded_at,
        "source": manifest.source,
        "acquisition_method": manifest.acquisition_method,
        "normalization_method": manifest.normalization_method,
        "notes": list(manifest.notes),
    }


class PostgresRunRepository:
    """Concrete, storage-aware `RunRepository` implementation."""

    def __init__(
        self,
        service: PostgresPersistenceService,
        mapper: RunMapper | None = None,
    ) -> None:
        self._service = service
        self._mapper: RunMapper = mapper if mapper is not None else ConcreteRunMapper()

    def get(self, identity: DomainIdentity[RunId]) -> LoadedAggregate[Run]:
        """Load a Run by canonical identity (Design Section 6)."""
        with self._service.unit_of_work() as work:
            rows = work.execute(
                "SELECT * FROM run WHERE runtime_id = :runtime_id "
                "AND governance_id = :governance_id",
                {
                    "runtime_id": str(identity.runtime_id),
                    "governance_id": str(identity.governance_id),
                },
            )
            if not rows:
                diagnostic_rows = work.execute(
                    "SELECT governance_id FROM run WHERE runtime_id = :runtime_id",
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
            manifest_rows = work.execute(
                "SELECT * FROM run_manifest WHERE run_runtime_id = :runtime_id ORDER BY position",
                {"runtime_id": str(identity.runtime_id)},
            )
            transition_rows = work.execute(
                "SELECT * FROM run_transition WHERE run_runtime_id = :runtime_id ORDER BY sequence",
                {"runtime_id": str(identity.runtime_id)},
            )
            record = RunDurableRecord(
                identity=IdentityDurableRecord(
                    governance_id=str(root["governance_id"]),
                    runtime_id=str(root["runtime_id"]),
                ),
                campaign_id=str(root["campaign_id"]),
                lifecycle_state=str(root["lifecycle_state"]),
                manifests=tuple(
                    _row_to_manifest(row, str(root["governance_id"])) for row in manifest_rows
                ),
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
                aggregate = _reconstruct_run(state)
            except ReconstructionError as exc:
                raise InvalidPersistedAggregateState(
                    aggregate_kind=_AGGREGATE_KIND, reason=str(exc), identity=identity
                ) from exc
            persisted_version = AggregateVersion(cast(int, root["version"]))
        return LoadedAggregate(aggregate=aggregate, persisted_version=persisted_version)

    def add(self, aggregate: Run) -> SaveResult:
        """Persist a new Run that must not already exist (Design Section 7)."""
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
                    "INSERT INTO run "
                    "(runtime_id, governance_id, campaign_id, lifecycle_state, "
                    "version, next_transition_sequence) "
                    "VALUES (:runtime_id, :governance_id, :campaign_id, "
                    ":lifecycle_state, :version, :next_transition_sequence)",
                    {
                        "runtime_id": record.identity.runtime_id,
                        "governance_id": record.identity.governance_id,
                        "campaign_id": record.campaign_id,
                        "lifecycle_state": record.lifecycle_state,
                        "version": record.version,
                        "next_transition_sequence": record.next_transition_sequence,
                    },
                )
                for position, manifest in enumerate(record.manifests):
                    work.execute(
                        "INSERT INTO run_manifest "
                        "(run_runtime_id, position, manifest_id, recorded_at, source, "
                        "acquisition_method, normalization_method, notes) "
                        "VALUES (:run_runtime_id, :position, :manifest_id, :recorded_at, "
                        ":source, :acquisition_method, :normalization_method, :notes)",
                        _manifest_params(record.identity.runtime_id, position, manifest),
                    )
                for transition in record.transition_history:
                    work.execute(
                        "INSERT INTO run_transition "
                        "(run_runtime_id, sequence, from_state, to_state, version, "
                        "actor, occurred_at, identity_governance_id, identity_runtime_id, "
                        "correlation_id, reason) "
                        "VALUES (:run_runtime_id, :sequence, :from_state, :to_state, "
                        ":version, :actor, :occurred_at, :identity_governance_id, "
                        ":identity_runtime_id, :correlation_id, :reason)",
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

    def save(self, aggregate: Run, *, expected_persisted_version: AggregateVersion) -> SaveResult:
        """Persist an existing Run guarded by optimistic concurrency (Design Section 8)."""
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
                "UPDATE run "
                "SET campaign_id = :campaign_id, lifecycle_state = :lifecycle_state, "
                "next_transition_sequence = :next_transition_sequence, "
                "version = :record_version "
                "WHERE runtime_id = :runtime_id AND governance_id = :governance_id "
                "AND version = :expected_persisted_version "
                "RETURNING version",
                {
                    "campaign_id": record.campaign_id,
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
                    "SELECT governance_id, version FROM run WHERE runtime_id = :runtime_id",
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
                    "DELETE FROM run_manifest WHERE run_runtime_id = :runtime_id",
                    {"runtime_id": record.identity.runtime_id},
                )
                work.execute(
                    "DELETE FROM run_transition WHERE run_runtime_id = :runtime_id",
                    {"runtime_id": record.identity.runtime_id},
                )
                for position, manifest in enumerate(record.manifests):
                    work.execute(
                        "INSERT INTO run_manifest "
                        "(run_runtime_id, position, manifest_id, recorded_at, source, "
                        "acquisition_method, normalization_method, notes) "
                        "VALUES (:run_runtime_id, :position, :manifest_id, :recorded_at, "
                        ":source, :acquisition_method, :normalization_method, :notes)",
                        _manifest_params(record.identity.runtime_id, position, manifest),
                    )
                for transition in record.transition_history:
                    work.execute(
                        "INSERT INTO run_transition "
                        "(run_runtime_id, sequence, from_state, to_state, version, "
                        "actor, occurred_at, identity_governance_id, identity_runtime_id, "
                        "correlation_id, reason) "
                        "VALUES (:run_runtime_id, :sequence, :from_state, :to_state, "
                        ":version, :actor, :occurred_at, :identity_governance_id, "
                        ":identity_runtime_id, :correlation_id, :reason)",
                        _transition_params(record.identity.runtime_id, transition),
                    )

            operation = intended_operation
            persisted_version = AggregateVersion(record.version)

        return SaveResult(operation=operation, persisted_version=persisted_version)
