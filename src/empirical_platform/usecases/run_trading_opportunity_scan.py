"""Run a deterministic multi-instrument trading opportunity scan: evaluate
every instrument through the unmodified M057 strategy, persist each
resulting DecisionCandidate, then deterministically rank the legitimate
candidates and persist the resulting TradingOpportunityScan.

Concrete command and handler. MILESTONE-058.

Reuses the frozen M057 `strategy.evaluate()` function verbatim for every
instrument -- this handler does not rewrite or reimplement any part of the
M057 strategy. The `DecisionCandidate` field mapping below mirrors
`EvaluateTradingObservationHandler.handle()` (M057) exactly, since both
handlers assemble the identical record shape from an evaluation outcome.

Composes N+1 aggregate mutations -- one `DecisionCandidateRepository.add()`
per instrument in the universe, plus one `TradingOpportunityScanRepository.add()`
for the scan itself -- a deliberate, documented exception to the
one-aggregate-mutation-per-command discipline used everywhere else in this
project (see MILESTONE_058 scope Section 9): a scan and its per-instrument
evaluations are one atomic business fact ("this scan happened, producing
exactly these N evaluations"), not N+1 independently meaningful business
events with separate actors or timing, unlike Campaign/Run/EvidencePackage/
Review.

This handler does NOT wrap all N+1 writes in a single database transaction
-- each `DecisionCandidateRepository.add()` commits independently, then the
scan (and its own child evaluation rows, atomically with each other via
`PostgresTradingOpportunityScanRepository.add()`'s own single unit of work)
commits as one further, separate transaction. This is an accepted, disclosed
limitation, consistent with how M056's own cross-aggregate chain is not
atomic across separate command invocations either: a crash mid-scan leaves
any already-persisted DecisionCandidates as individually valid, auditable
records, but with no scan yet referencing them.
"""

from __future__ import annotations

from dataclasses import dataclass

from empirical_platform.decision_candidate.candidate import DecisionCandidate as DecisionCandidate
from empirical_platform.decision_candidate.market_data import Bar as Bar
from empirical_platform.decision_candidate.market_data import BarInterval as BarInterval
from empirical_platform.decision_candidate.market_data import Instrument as Instrument
from empirical_platform.decision_candidate.market_data import ObservationWindow as ObservationWindow
from empirical_platform.decision_candidate.repository import DecisionCandidateRepository
from empirical_platform.decision_candidate.scan import (
    TradingOpportunityScan as TradingOpportunityScan,
)
from empirical_platform.decision_candidate.scan import build_scan, validate_scan_universe
from empirical_platform.decision_candidate.scan_repository import TradingOpportunityScanRepository
from empirical_platform.decision_candidate.strategy import (
    STRATEGY_ID,
    STRATEGY_VERSION,
    evaluate,
)
from empirical_platform.decision_candidate.strategy import StrategyParameters as StrategyParameters
from empirical_platform.identifiers.pairs import DomainIdentity
from empirical_platform.identifiers.types import (
    DecisionCandidateId,
    EvidencePackageId,
    TradingOpportunityScanId,
)


@dataclass(frozen=True, slots=True)
class ScanUniverseEntry:
    """One instrument's already-identified evaluation input within a scan
    universe: a caller-supplied DecisionCandidate identity paired with its
    ObservationWindow, in the caller's own universe order."""

    decision_candidate_identity: DomainIdentity[DecisionCandidateId]
    window: ObservationWindow


@dataclass(frozen=True, slots=True)
class RunTradingOpportunityScanCommand:
    """Request to evaluate a multi-instrument universe and persist the
    resulting ranked TradingOpportunityScan, identified by the caller and
    targeting an existing EvidencePackage.

    `universe` entries carry already-validated domain value objects and
    already-constructed identities, mirroring `EvaluateTradingObservationCommand`
    (M057) -- this handler performs no market-data parsing, only universe
    validation, strategy evaluation, ranking, and persistence.
    """

    scan_identity: DomainIdentity[TradingOpportunityScanId]
    target_evidence_package_id: EvidencePackageId
    universe: tuple[ScanUniverseEntry, ...]
    parameters: StrategyParameters


class RunTradingOpportunityScanHandler:
    """Evaluates every instrument in one scan universe through the frozen
    M057 strategy, persists each resulting DecisionCandidate, ranks the
    legitimate candidates, and persists the resulting TradingOpportunityScan."""

    __slots__ = ("_decision_candidate_repository", "_trading_opportunity_scan_repository")

    def __init__(
        self,
        *,
        decision_candidate_repository: DecisionCandidateRepository,
        trading_opportunity_scan_repository: TradingOpportunityScanRepository,
    ) -> None:
        self._decision_candidate_repository = decision_candidate_repository
        self._trading_opportunity_scan_repository = trading_opportunity_scan_repository

    def handle(self, command: RunTradingOpportunityScanCommand) -> TradingOpportunityScan:
        """Validate the universe, evaluate and persist every instrument,
        then rank and persist the resulting scan."""
        windows = tuple(entry.window for entry in command.universe)
        validate_scan_universe(windows)

        universe_outcomes = []
        for entry in command.universe:
            outcome = evaluate(entry.window, command.parameters)
            candidate = DecisionCandidate(
                identity=entry.decision_candidate_identity,
                target_evidence_package_id=command.target_evidence_package_id,
                instrument=entry.window.instrument,
                interval=entry.window.interval,
                evaluation_timestamp=entry.window.evaluation_bar.timestamp,
                strategy_id=STRATEGY_ID,
                strategy_version=STRATEGY_VERSION,
                reference_window_size=command.parameters.reference_window_size,
                outcome=outcome,
            )
            self._decision_candidate_repository.add(candidate)
            universe_outcomes.append(
                (
                    entry.window.instrument,
                    entry.decision_candidate_identity.governance_id,
                    outcome,
                )
            )

        scan = build_scan(
            identity=command.scan_identity,
            target_evidence_package_id=command.target_evidence_package_id,
            strategy_id=STRATEGY_ID,
            strategy_version=STRATEGY_VERSION,
            evaluation_cutoff=windows[0].evaluation_bar.timestamp,
            universe=universe_outcomes,
        )
        self._trading_opportunity_scan_repository.add(scan)
        return scan
