"""The persisted, immutable trading evaluation record.

MILESTONE-057. `DecisionCandidate` is deliberately NOT a lifecycle
aggregate: a trading evaluation is a fact computed once from a fixed input
(an `ObservationWindow`) and a fixed strategy version -- it never
transitions between states and is never mutated after creation. It is
therefore persisted with a single `add()` (no `save()`, no optimistic
concurrency, no transition history) -- the same class of simplification
already applied to `DatasetManifest` (M055), extended here to a full
top-level, independently retrievable record because a trading evaluation
has its own genuine identity and must be independently auditable.

`target_evidence_package_id` is the typed link into the existing evidence
core (see MILESTONE_057_TRADING_EVALUATION_SCOPE_AND_DESIGN.md Section 10):
every DecisionCandidate targets exactly one EvidencePackage, mirroring how
`Review.target` already references an EvidencePackageId. The same
DecisionCandidate's own governance_id is additionally recorded as an
ArtifactReference on that EvidencePackage (via the already-frozen M040
entrypoint, unmodified) so the link is discoverable from either side.

`evaluation_timestamp` is the evaluation bar's own timestamp -- fully
deterministic, derived from the input data, not a wall-clock read -- and is
the one timestamp this record carries, per this milestone's own instruction
to include a created/evaluated timestamp only where deterministic semantics
are clear.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from empirical_platform.decision_candidate.market_data import BarInterval, Instrument
from empirical_platform.decision_candidate.strategy import EvaluationOutcome
from empirical_platform.identifiers.pairs import DomainIdentity
from empirical_platform.identifiers.types import DecisionCandidateId, EvidencePackageId


@dataclass(frozen=True, slots=True)
class DecisionCandidate:
    """One immutable, persisted, independently-auditable trading evaluation."""

    identity: DomainIdentity[DecisionCandidateId]
    target_evidence_package_id: EvidencePackageId
    instrument: Instrument
    interval: BarInterval
    evaluation_timestamp: datetime
    strategy_id: str
    strategy_version: str
    reference_window_size: int
    outcome: EvaluationOutcome

    def __post_init__(self) -> None:
        if not isinstance(self.identity, DomainIdentity):
            raise TypeError("identity must be a DomainIdentity[DecisionCandidateId]")
        if not isinstance(self.identity.governance_id, DecisionCandidateId):
            raise TypeError("identity governance_id must be a DecisionCandidateId")
        if not isinstance(self.target_evidence_package_id, EvidencePackageId):
            raise TypeError("target_evidence_package_id must be an EvidencePackageId")
        if not isinstance(self.instrument, Instrument):
            raise TypeError("instrument must be an Instrument")
        if not isinstance(self.interval, BarInterval):
            raise TypeError("interval must be a BarInterval")
        if not isinstance(self.evaluation_timestamp, datetime):
            raise TypeError("evaluation_timestamp must be a datetime")
        if self.evaluation_timestamp.tzinfo is None:
            raise ValueError("evaluation_timestamp must be timezone-aware")
        if not self.strategy_id.strip():
            raise ValueError("strategy_id must be non-empty")
        if not self.strategy_version.strip():
            raise ValueError("strategy_version must be non-empty")
        if self.reference_window_size < 1:
            raise ValueError("reference_window_size must be at least 1")
        if not isinstance(self.outcome, EvaluationOutcome):
            raise TypeError("outcome must be an EvaluationOutcome")
