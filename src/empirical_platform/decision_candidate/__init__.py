"""Decision candidate boundary.

MILESTONE-057 gave this boundary its first real behavior: a deterministic,
versioned trading-strategy evaluation over real-shaped market bar data,
producing an immutable, persisted, auditable `DecisionCandidate`. MILESTONE-058
adds a multi-instrument opportunity scan and deterministic ranking on top of
the unmodified M057 evaluation. See
MILESTONE_057_TRADING_EVALUATION_SCOPE_AND_DESIGN.md and
MILESTONE_058_TRADING_OPPORTUNITY_SCANNER_SCOPE_AND_DESIGN.md for the full
scope, contracts, and explicit non-profitability disclaimer.
"""

from empirical_platform.decision_candidate.candidate import DecisionCandidate
from empirical_platform.decision_candidate.market_data import (
    Bar,
    BarInterval,
    Instrument,
    ObservationWindow,
)
from empirical_platform.decision_candidate.ranking import (
    RANKING_MODEL_ID,
    RANKING_MODEL_VERSION,
    compute_ranking_score,
)
from empirical_platform.decision_candidate.repository import DecisionCandidateRepository
from empirical_platform.decision_candidate.scan import (
    ScanEvaluationEntry,
    TradingOpportunityScan,
    build_scan,
    validate_scan_universe,
)
from empirical_platform.decision_candidate.scan_repository import TradingOpportunityScanRepository
from empirical_platform.decision_candidate.strategy import (
    STRATEGY_ID,
    STRATEGY_VERSION,
    EvaluationMeasurements,
    EvaluationOutcome,
    EvaluationReasonCode,
    StrategyParameters,
    TradingDecision,
    evaluate,
)

__all__ = [
    "RANKING_MODEL_ID",
    "RANKING_MODEL_VERSION",
    "STRATEGY_ID",
    "STRATEGY_VERSION",
    "Bar",
    "BarInterval",
    "DecisionCandidate",
    "DecisionCandidateRepository",
    "EvaluationMeasurements",
    "EvaluationOutcome",
    "EvaluationReasonCode",
    "Instrument",
    "ObservationWindow",
    "ScanEvaluationEntry",
    "StrategyParameters",
    "TradingDecision",
    "TradingOpportunityScan",
    "TradingOpportunityScanRepository",
    "build_scan",
    "compute_ranking_score",
    "evaluate",
    "validate_scan_universe",
]
