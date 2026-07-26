"""Concrete PostgreSQL `CampaignRepository` adapter (MILESTONE-023).

Implements the frozen `CampaignRepository` Protocol (MILESTONE-020) against
the frozen `campaign`/`campaign_transition` schema (MILESTONE-022), using the
frozen `CampaignMapper` contract (MILESTONE-021), exactly per
MILESTONE_023_POSTGRESQL_REPOSITORY_ADAPTER_DESIGN.md Sections 6-9.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, cast

from empirical_platform.campaign._reconstruction import _reconstruct_campaign
from empirical_platform.campaign.aggregate import Campaign
from empirical_platform.campaign.mapper import (
    CampaignDurableRecord,
    CampaignMapper,
    ConcreteCampaignMapper,
)
from empirical_platform.identifiers.pairs import DomainIdentity
from empirical_platform.identifiers.types import CampaignId
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

_AGGREGATE_KIND = "Campaign"
_ROOT_UNIQUE_CONSTRAINTS = {"pk_campaign", "uq_campaign_governance_id"}


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
    campaign_runtime_id: str, transition: TransitionDurableRecord
) -> dict[str, Any]:
    identity_reference = transition.identity_reference
    return {
        "campaign_runtime_id": campaign_runtime_id,
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


class PostgresCampaignRepository:
    """Concrete, storage-aware `CampaignRepository` implementation."""

    def __init__(
        self,
        service: PostgresPersistenceService,
        mapper: CampaignMapper | None = None,
    ) -> None:
        self._service = service
        self._mapper: CampaignMapper = mapper if mapper is not None else ConcreteCampaignMapper()

    def get(self, identity: DomainIdentity[CampaignId]) -> LoadedAggregate[Campaign]:
        """Load a Campaign by canonical identity (Design Section 6)."""
        with self._service.unit_of_work() as work:
            rows = work.execute(
                "SELECT * FROM campaign WHERE runtime_id = :runtime_id "
                "AND governance_id = :governance_id",
                {
                    "runtime_id": str(identity.runtime_id),
                    "governance_id": str(identity.governance_id),
                },
            )
            if not rows:
                diagnostic_rows = work.execute(
                    "SELECT governance_id FROM campaign WHERE runtime_id = :runtime_id",
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
            transition_rows = work.execute(
                "SELECT * FROM campaign_transition WHERE campaign_runtime_id = :runtime_id "
                "ORDER BY sequence",
                {"runtime_id": str(identity.runtime_id)},
            )
            record = CampaignDurableRecord(
                identity=IdentityDurableRecord(
                    governance_id=str(root["governance_id"]),
                    runtime_id=str(root["runtime_id"]),
                ),
                scope_statement=str(root["scope_statement"]),
                lifecycle_state=str(root["lifecycle_state"]),
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
                aggregate = _reconstruct_campaign(state)
            except ReconstructionError as exc:
                raise InvalidPersistedAggregateState(
                    aggregate_kind=_AGGREGATE_KIND, reason=str(exc), identity=identity
                ) from exc
            persisted_version = AggregateVersion(cast(int, root["version"]))
        return LoadedAggregate(aggregate=aggregate, persisted_version=persisted_version)

    def add(self, aggregate: Campaign) -> SaveResult:
        """Persist a new Campaign that must not already exist (Design Section 7)."""
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
                    "INSERT INTO campaign "
                    "(runtime_id, governance_id, scope_statement, lifecycle_state, "
                    "version, next_transition_sequence) "
                    "VALUES (:runtime_id, :governance_id, :scope_statement, "
                    ":lifecycle_state, :version, :next_transition_sequence)",
                    {
                        "runtime_id": record.identity.runtime_id,
                        "governance_id": record.identity.governance_id,
                        "scope_statement": record.scope_statement,
                        "lifecycle_state": record.lifecycle_state,
                        "version": record.version,
                        "next_transition_sequence": record.next_transition_sequence,
                    },
                )
                for transition in record.transition_history:
                    work.execute(
                        "INSERT INTO campaign_transition "
                        "(campaign_runtime_id, sequence, from_state, to_state, version, "
                        "actor, occurred_at, identity_governance_id, identity_runtime_id, "
                        "correlation_id, reason) "
                        "VALUES (:campaign_runtime_id, :sequence, :from_state, :to_state, "
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

    def save(
        self, aggregate: Campaign, *, expected_persisted_version: AggregateVersion
    ) -> SaveResult:
        """Persist an existing Campaign guarded by optimistic concurrency (Design Section 8)."""
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
                "UPDATE campaign "
                "SET scope_statement = :scope_statement, lifecycle_state = :lifecycle_state, "
                "next_transition_sequence = :next_transition_sequence, "
                "version = :record_version "
                "WHERE runtime_id = :runtime_id AND governance_id = :governance_id "
                "AND version = :expected_persisted_version "
                "RETURNING version",
                {
                    "scope_statement": record.scope_statement,
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
                    "SELECT governance_id, version FROM campaign WHERE runtime_id = :runtime_id",
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
                    "DELETE FROM campaign_transition WHERE campaign_runtime_id = :runtime_id",
                    {"runtime_id": record.identity.runtime_id},
                )
                for transition in record.transition_history:
                    work.execute(
                        "INSERT INTO campaign_transition "
                        "(campaign_runtime_id, sequence, from_state, to_state, version, "
                        "actor, occurred_at, identity_governance_id, identity_runtime_id, "
                        "correlation_id, reason) "
                        "VALUES (:campaign_runtime_id, :sequence, :from_state, :to_state, "
                        ":version, :actor, :occurred_at, :identity_governance_id, "
                        ":identity_runtime_id, :correlation_id, :reason)",
                        _transition_params(record.identity.runtime_id, transition),
                    )

            operation = intended_operation
            persisted_version = AggregateVersion(record.version)

        return SaveResult(operation=operation, persisted_version=persisted_version)
