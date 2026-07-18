"""Process-local Evidence Package aggregate behavior."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from empirical_platform.evidence.lifecycle import EvidencePackageLifecycleState
from empirical_platform.evidence.results import CriterionResult
from empirical_platform.identifiers import DomainIdentity, EvidencePackageId, RunId
from empirical_platform.shared.domain import (
    AggregateVersion,
    StateTransitionRecord,
    TransitionSequence,
)


@dataclass(frozen=True, slots=True)
class ArtifactReference:
    """Opaque domain-level evidence artifact reference."""

    value: str

    def __post_init__(self) -> None:
        if not isinstance(self.value, str):
            raise TypeError("artifact reference value must be a string")
        if self.value.strip() == "":
            raise ValueError("artifact reference value must be non-empty")

    def __str__(self) -> str:
        return self.value


class EvidencePackage:
    """Process-local Evidence Package aggregate root."""

    __slots__ = (
        "_artifact_references",
        "_criterion_results",
        "_identity",
        "_next_transition_sequence",
        "_run_id",
        "_state",
        "_transition_history",
        "_version",
    )

    def __init__(self, identity: DomainIdentity[EvidencePackageId], run_id: RunId) -> None:
        if not isinstance(identity, DomainIdentity):
            raise TypeError("identity must be a DomainIdentity[EvidencePackageId]")
        if not isinstance(identity.governance_id, EvidencePackageId):
            raise TypeError("identity governance_id must be an EvidencePackageId")
        if not isinstance(run_id, RunId):
            raise TypeError("run_id must be a RunId")
        self._identity = identity
        self._run_id = run_id
        self._state = EvidencePackageLifecycleState.INITIALIZED
        self._version = AggregateVersion.initial()
        self._next_transition_sequence = TransitionSequence.initial()
        self._transition_history: tuple[
            StateTransitionRecord[DomainIdentity[EvidencePackageId]], ...
        ] = ()
        self._criterion_results: tuple[CriterionResult, ...] = ()
        self._artifact_references: tuple[ArtifactReference, ...] = ()

    @property
    def identity(self) -> DomainIdentity[EvidencePackageId]:
        """Return the immutable aggregate identity."""
        return self._identity

    @property
    def run_id(self) -> RunId:
        """Return the immutable parent Run ID context."""
        return self._run_id

    @property
    def state(self) -> EvidencePackageLifecycleState:
        """Return the current lifecycle state."""
        return self._state

    @property
    def version(self) -> AggregateVersion:
        """Return the current aggregate version."""
        return self._version

    @property
    def next_transition_sequence(self) -> TransitionSequence:
        """Return the sequence available for the next lifecycle transition."""
        return self._next_transition_sequence

    @property
    def transition_history(
        self,
    ) -> tuple[StateTransitionRecord[DomainIdentity[EvidencePackageId]], ...]:
        """Return immutable lifecycle transition history."""
        return self._transition_history

    @property
    def criterion_results(self) -> tuple[CriterionResult, ...]:
        """Return immutable Criterion Result collection view."""
        return self._criterion_results

    @property
    def artifact_references(self) -> tuple[ArtifactReference, ...]:
        """Return immutable artifact-reference collection view."""
        return self._artifact_references

    def start_collection(
        self,
        *,
        actor: str,
        occurred_at: datetime,
        correlation_id: str | None = None,
        reason: str | None = None,
    ) -> None:
        """Transition the package from INITIALIZED to COLLECTING."""
        self._transition(
            expected_state=EvidencePackageLifecycleState.INITIALIZED,
            next_state=EvidencePackageLifecycleState.COLLECTING,
            actor=actor,
            occurred_at=occurred_at,
            correlation_id=correlation_id,
            reason=reason,
        )

    def add_criterion_result(self, result: CriterionResult) -> None:
        """Add a Criterion Result during collection."""
        if not isinstance(result, CriterionResult):
            raise TypeError("result must be a CriterionResult")
        if self._state is not EvidencePackageLifecycleState.COLLECTING:
            raise ValueError("Criterion Results may be added only while COLLECTING")
        if result.evidence_package_id != self._identity.governance_id:
            raise ValueError(
                "Criterion Result evidence_package_id must match Evidence Package identity"
            )
        if any(
            existing.criterion_id == result.criterion_id for existing in self._criterion_results
        ):
            raise ValueError("Criterion Result criterion_id already exists in Evidence Package")

        next_version = self._version.next()
        next_results = (*self._criterion_results, result)

        self._version = next_version
        self._criterion_results = next_results

    def add_artifact_reference(self, reference: ArtifactReference) -> None:
        """Add an opaque artifact reference during collection."""
        if not isinstance(reference, ArtifactReference):
            raise TypeError("reference must be an ArtifactReference")
        if self._state is not EvidencePackageLifecycleState.COLLECTING:
            raise ValueError("artifact references may be added only while COLLECTING")
        if any(existing.value == reference.value for existing in self._artifact_references):
            raise ValueError("artifact reference already exists in Evidence Package")

        next_version = self._version.next()
        next_references = (*self._artifact_references, reference)

        self._version = next_version
        self._artifact_references = next_references

    def seal(
        self,
        *,
        actor: str,
        occurred_at: datetime,
        correlation_id: str | None = None,
        reason: str | None = None,
    ) -> None:
        """Seal package contents and close collection writes."""
        if not self._criterion_results:
            raise ValueError("Evidence Package requires at least one Criterion Result before seal")
        if not self._artifact_references:
            raise ValueError(
                "Evidence Package requires at least one artifact reference before seal"
            )
        self._transition(
            expected_state=EvidencePackageLifecycleState.COLLECTING,
            next_state=EvidencePackageLifecycleState.SEALED,
            actor=actor,
            occurred_at=occurred_at,
            correlation_id=correlation_id,
            reason=reason,
        )

    def invalidate(
        self,
        *,
        reason: str,
        actor: str,
        occurred_at: datetime,
        correlation_id: str | None = None,
    ) -> None:
        """Invalidate a sealed package without mutating sealed contents."""
        _require_non_empty(reason, "reason")
        self._transition(
            expected_state=EvidencePackageLifecycleState.SEALED,
            next_state=EvidencePackageLifecycleState.INVALIDATED,
            actor=actor,
            occurred_at=occurred_at,
            correlation_id=correlation_id,
            reason=reason,
        )

    def _transition(
        self,
        *,
        expected_state: EvidencePackageLifecycleState,
        next_state: EvidencePackageLifecycleState,
        actor: str,
        occurred_at: datetime,
        correlation_id: str | None,
        reason: str | None,
    ) -> None:
        if self._state is not expected_state:
            raise ValueError(f"cannot transition from {self._state.value} to {next_state.value}")
        if not isinstance(occurred_at, datetime):
            raise TypeError("occurred_at must be a datetime")

        next_version = self._version.next()
        current_sequence = self._next_transition_sequence
        next_sequence = current_sequence.next()
        record = StateTransitionRecord(
            from_state=self._state.value,
            to_state=next_state.value,
            version=next_version,
            sequence=current_sequence,
            actor=actor,
            occurred_at=occurred_at,
            identity_reference=self._identity,
            correlation_id=correlation_id,
            reason=reason,
        )
        next_history = (*self._transition_history, record)

        self._state = next_state
        self._version = next_version
        self._next_transition_sequence = next_sequence
        self._transition_history = next_history


def _require_non_empty(value: str, field_name: str) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    if value.strip() == "":
        raise ValueError(f"{field_name} must be non-empty")
