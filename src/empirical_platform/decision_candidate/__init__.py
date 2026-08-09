"""Decision candidate boundary.

MILESTONE-057 gave this boundary its first real behavior: a deterministic,
versioned trading-strategy evaluation over real-shaped market bar data,
producing an immutable, persisted, auditable `DecisionCandidate`. MILESTONE-058
added a multi-instrument opportunity scan and deterministic ranking on top of
the unmodified M057 evaluation. MILESTONE-059 adds a risk-gated trade plan
on top of the unmodified M057/M058 outputs: an explicit, versioned risk
policy that can approve or reject a ranked LONG_CANDIDATE. MILESTONE-060
adds deterministic position sizing and a capital-exposure gate on top of
the unmodified M059 output: an explicit, versioned sizing policy that can
approve or reject a concrete position quantity for an already-approved
trade plan. See
MILESTONE_057_TRADING_EVALUATION_SCOPE_AND_DESIGN.md,
MILESTONE_058_TRADING_OPPORTUNITY_SCANNER_SCOPE_AND_DESIGN.md, and
MILESTONE_059_RISK_GATED_TRADE_PLAN_SCOPE_AND_DESIGN.md,
MILESTONE_060_POSITION_SIZING_CAPITAL_EXPOSURE_GATE_SCOPE_AND_DESIGN.md
for the full scope, contracts, and explicit non-profitability disclaimer.
"""

from empirical_platform.decision_candidate.candidate import DecisionCandidate
from empirical_platform.decision_candidate.market_data import (
    Bar,
    BarInterval,
    Instrument,
    ObservationWindow,
)
from empirical_platform.decision_candidate.position_plan import (
    DEFAULT_SIZING_POLICY,
    SIZING_POLICY_ID,
    SIZING_POLICY_VERSION,
    PositionPlan,
    PositionPlanRejectionReason,
    PositionPlanStatus,
    PositionSizing,
    PositionSizingContext,
    SizingPolicy,
    build_position_plan,
)
from empirical_platform.decision_candidate.position_plan_repository import PositionPlanRepository
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
from empirical_platform.decision_candidate.trade_plan import (
    DEFAULT_RISK_POLICY,
    RISK_POLICY_ID,
    RISK_POLICY_VERSION,
    RiskPolicy,
    TradePlan,
    TradePlanGeometry,
    TradePlanRejectionReason,
    TradePlanStatus,
    build_trade_plan,
)
from empirical_platform.decision_candidate.trade_plan_repository import TradePlanRepository

__all__ = [
    "DEFAULT_RISK_POLICY",
    "DEFAULT_SIZING_POLICY",
    "RANKING_MODEL_ID",
    "RANKING_MODEL_VERSION",
    "RISK_POLICY_ID",
    "RISK_POLICY_VERSION",
    "SIZING_POLICY_ID",
    "SIZING_POLICY_VERSION",
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
    "PositionPlan",
    "PositionPlanRejectionReason",
    "PositionPlanRepository",
    "PositionPlanStatus",
    "PositionSizing",
    "PositionSizingContext",
    "RiskPolicy",
    "ScanEvaluationEntry",
    "SizingPolicy",
    "StrategyParameters",
    "TradePlan",
    "TradePlanGeometry",
    "TradePlanRejectionReason",
    "TradePlanRepository",
    "TradePlanStatus",
    "TradingDecision",
    "TradingOpportunityScan",
    "TradingOpportunityScanRepository",
    "build_position_plan",
    "build_scan",
    "build_trade_plan",
    "compute_ranking_score",
    "evaluate",
    "validate_scan_universe",
]
