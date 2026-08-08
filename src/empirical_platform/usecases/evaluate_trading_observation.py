"""Evaluate a market observation under one versioned trading strategy, and
persist the resulting DecisionCandidate.

Concrete command and handler. MILESTONE-057.

Composes exactly one aggregate mutation (`DecisionCandidateRepository.add()`),
per this milestone's own architecture decision (Section 5 of the scope
document): recording the resulting DecisionCandidate's governance_id as an
ArtifactReference on its target EvidencePackage is a *separate*, already-
frozen M040 command, invoked as its own explicit step by the caller -- not
merged into this handler, matching the established one-aggregate-per-command
discipline used by every other command in this project.
"""

from __future__ import annotations

from dataclasses import dataclass

from empirical_platform.decision_candidate.candidate import DecisionCandidate as DecisionCandidate
from empirical_platform.decision_candidate.market_data import Bar as Bar
from empirical_platform.decision_candidate.market_data import BarInterval as BarInterval
from empirical_platform.decision_candidate.market_data import Instrument as Instrument
from empirical_platform.decision_candidate.market_data import ObservationWindow as ObservationWindow
from empirical_platform.decision_candidate.repository import DecisionCandidateRepository
from empirical_platform.decision_candidate.strategy import (
    STRATEGY_ID,
    STRATEGY_VERSION,
    evaluate,
)
from empirical_platform.decision_candidate.strategy import StrategyParameters as StrategyParameters
from empirical_platform.identifiers.pairs import DomainIdentity
from empirical_platform.identifiers.types import DecisionCandidateId, EvidencePackageId


@dataclass(frozen=True, slots=True)
class EvaluateTradingObservationCommand:
    """Request to evaluate one ObservationWindow and persist the resulting
    DecisionCandidate, identified by the caller and targeting an existing
    EvidencePackage.

    `window` and `parameters` are already-validated domain value objects,
    constructed by the caller (mirroring how every other command already
    carries a pre-constructed `DomainIdentity`) -- this handler performs no
    market-data parsing, only strategy evaluation and persistence.
    """

    identity: DomainIdentity[DecisionCandidateId]
    target_evidence_package_id: EvidencePackageId
    window: ObservationWindow
    parameters: StrategyParameters


class EvaluateTradingObservationHandler:
    """Evaluates one ObservationWindow and persists the resulting
    DecisionCandidate for one command."""

    __slots__ = ("_decision_candidate_repository",)

    def __init__(self, *, decision_candidate_repository: DecisionCandidateRepository) -> None:
        self._decision_candidate_repository = decision_candidate_repository

    def handle(self, command: EvaluateTradingObservationCommand) -> DecisionCandidate:
        """Evaluate the window under the frozen strategy, persist, and return
        the resulting DecisionCandidate."""
        outcome = evaluate(command.window, command.parameters)
        candidate = DecisionCandidate(
            identity=command.identity,
            target_evidence_package_id=command.target_evidence_package_id,
            instrument=command.window.instrument,
            interval=command.window.interval,
            evaluation_timestamp=command.window.evaluation_bar.timestamp,
            strategy_id=STRATEGY_ID,
            strategy_version=STRATEGY_VERSION,
            reference_window_size=command.parameters.reference_window_size,
            outcome=outcome,
        )
        self._decision_candidate_repository.add(candidate)
        return candidate
