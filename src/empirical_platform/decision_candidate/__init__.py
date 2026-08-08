"""Decision candidate boundary.

MILESTONE-057 gives this boundary its first real behavior: a deterministic,
versioned trading-strategy evaluation over real-shaped market bar data,
producing an immutable, persisted, auditable `DecisionCandidate`. See
MILESTONE_057_TRADING_EVALUATION_SCOPE_AND_DESIGN.md for the full scope,
market-data contract, strategy contract, and explicit non-profitability
disclaimer.
"""

from empirical_platform.decision_candidate.candidate import DecisionCandidate
from empirical_platform.decision_candidate.market_data import (
    Bar,
    BarInterval,
    Instrument,
    ObservationWindow,
)
from empirical_platform.decision_candidate.repository import DecisionCandidateRepository
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
    "StrategyParameters",
    "TradingDecision",
    "evaluate",
]
