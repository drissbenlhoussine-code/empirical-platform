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
trade plan. MILESTONE-061 adds deterministic historical validation and
backtesting on top of the unmodified M057-M060 decision logic: a fixed
dataset, explicit execution/outcome assumptions, and immutable per-trade /
aggregate replay evidence. See
MILESTONE_057_TRADING_EVALUATION_SCOPE_AND_DESIGN.md,
MILESTONE_058_TRADING_OPPORTUNITY_SCANNER_SCOPE_AND_DESIGN.md, and
MILESTONE_059_RISK_GATED_TRADE_PLAN_SCOPE_AND_DESIGN.md,
MILESTONE_060_POSITION_SIZING_CAPITAL_EXPOSURE_GATE_SCOPE_AND_DESIGN.md,
MILESTONE_061_HISTORICAL_STRATEGY_VALIDATION_BACKTESTING_V1_SCOPE_AND_DESIGN.md
for the full scope, contracts, and explicit non-profitability disclaimer.
"""

from empirical_platform.decision_candidate.candidate import DecisionCandidate
from empirical_platform.decision_candidate.historical_backtest import (
    COST_MODEL_ID,
    COST_MODEL_VERSION,
    DECISION_CADENCE,
    DEFAULT_COST_MODEL,
    DEFAULT_EXECUTION_ASSUMPTION,
    DEFAULT_OUTCOME_MODEL,
    EXECUTION_ASSUMPTION_ID,
    EXECUTION_ASSUMPTION_VERSION,
    FIXED_TEST_UNIVERSE,
    OUTCOME_MODEL_ID,
    OUTCOME_MODEL_VERSION,
    HistoricalBacktestRun,
    HistoricalBacktestRunStatus,
    HistoricalCostModel,
    HistoricalDataset,
    HistoricalDatasetAuthority,
    HistoricalExecutionAssumption,
    HistoricalInstrumentSeries,
    HistoricalOutcomeModel,
    HistoricalTradeOutcome,
    HistoricalValidationClassification,
    SameBarAmbiguityPolicy,
    build_historical_backtest_run,
    dataset_sha256,
)
from empirical_platform.decision_candidate.historical_backtest_repository import (
    HistoricalBacktestRunRepository,
)
from empirical_platform.decision_candidate.historical_universe import universe_at
from empirical_platform.decision_candidate.instrument_master import (
    InstrumentId,
    InstrumentMaster,
    InstrumentMasterEntry,
    InstrumentType,
)
from empirical_platform.decision_candidate.market_data import (
    Bar,
    BarInterval,
    Instrument,
    ObservationWindow,
)
from empirical_platform.decision_candidate.membership import (
    MembershipManifest,
    MembershipRecord,
    MembershipStatus,
    canonical_membership_payload,
    membership_manifest_hash,
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
from empirical_platform.decision_candidate.robustness_study import (
    REGIME_POLICY_ID,
    REGIME_POLICY_VERSION,
    HistoricalRobustnessStudy,
    RegimeBreakdownEntry,
    RegimeLabel,
    RobustnessDatasetBundle,
    RobustnessDatasetBundleAuthority,
    RobustnessStudyClassification,
    RobustnessStudyStatus,
    RobustnessUniverseAuthority,
    RobustnessWindow,
    RobustnessWindowResult,
    RobustnessWindowSpec,
    WindowExtreme,
    build_robustness_study,
    regime_breakdown,
)
from empirical_platform.decision_candidate.robustness_study_repository import (
    HistoricalRobustnessStudyRepository,
)
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
from empirical_platform.decision_candidate.survivorship_study import (
    CORPORATE_ACTION_HANDLING_NOT_EXERCISED,
    HISTORICAL_MEMBERSHIP_MODEL,
    BiasStressComparison,
    CurrentUniverseBiasStressResult,
    StressWindowComparison,
    SurvivorshipAwareRobustnessStudy,
    SurvivorshipClassification,
    SurvivorshipStudyStatus,
    SurvivorshipWindowResult,
    WindowUniverseSnapshot,
    build_survivorship_aware_robustness_study,
)
from empirical_platform.decision_candidate.survivorship_study_repository import (
    SurvivorshipAwareRobustnessStudyRepository,
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
from empirical_platform.decision_candidate.universe_authority import UniverseAuthority
from empirical_platform.decision_candidate.validation_study import (
    SURVIVORSHIP_BIAS_DISCLOSURE,
    HistoricalValidationStudy,
    HistoricalValidationStudyClassification,
    HistoricalValidationStudyStatus,
    ValidationDatasetBundle,
    ValidationDatasetBundleAuthority,
    ValidationSegment,
    ValidationSegmentResult,
    ValidationSegmentRole,
    ValidationSegmentSpec,
    build_validation_study,
)
from empirical_platform.decision_candidate.validation_study_repository import (
    HistoricalValidationStudyRepository,
)

__all__ = [
    "DEFAULT_RISK_POLICY",
    "DEFAULT_SIZING_POLICY",
    "SURVIVORSHIP_BIAS_DISCLOSURE",
    "REGIME_POLICY_ID",
    "REGIME_POLICY_VERSION",
    "COST_MODEL_ID",
    "COST_MODEL_VERSION",
    "DECISION_CADENCE",
    "DEFAULT_COST_MODEL",
    "DEFAULT_EXECUTION_ASSUMPTION",
    "DEFAULT_OUTCOME_MODEL",
    "EXECUTION_ASSUMPTION_ID",
    "EXECUTION_ASSUMPTION_VERSION",
    "FIXED_TEST_UNIVERSE",
    "OUTCOME_MODEL_ID",
    "OUTCOME_MODEL_VERSION",
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
    "HistoricalBacktestRun",
    "HistoricalBacktestRunRepository",
    "HistoricalBacktestRunStatus",
    "HistoricalCostModel",
    "HistoricalDataset",
    "HistoricalDatasetAuthority",
    "HistoricalExecutionAssumption",
    "HistoricalInstrumentSeries",
    "HistoricalOutcomeModel",
    "HistoricalTradeOutcome",
    "HistoricalValidationClassification",
    "HistoricalValidationStudy",
    "HistoricalValidationStudyClassification",
    "HistoricalValidationStudyRepository",
    "HistoricalValidationStudyStatus",
    "Instrument",
    "ObservationWindow",
    "PositionPlan",
    "PositionPlanRejectionReason",
    "PositionPlanRepository",
    "PositionPlanStatus",
    "PositionSizing",
    "PositionSizingContext",
    "RiskPolicy",
    "SameBarAmbiguityPolicy",
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
    "ValidationDatasetBundle",
    "ValidationDatasetBundleAuthority",
    "ValidationSegment",
    "ValidationSegmentResult",
    "ValidationSegmentRole",
    "ValidationSegmentSpec",
    "HistoricalRobustnessStudy",
    "HistoricalRobustnessStudyRepository",
    "RegimeBreakdownEntry",
    "RegimeLabel",
    "RobustnessDatasetBundle",
    "RobustnessDatasetBundleAuthority",
    "RobustnessUniverseAuthority",
    "RobustnessStudyClassification",
    "RobustnessStudyStatus",
    "RobustnessWindow",
    "RobustnessWindowResult",
    "RobustnessWindowSpec",
    "WindowExtreme",
    "build_historical_backtest_run",
    "build_position_plan",
    "build_robustness_study",
    "build_scan",
    "build_trade_plan",
    "build_validation_study",
    "compute_ranking_score",
    "dataset_sha256",
    "evaluate",
    "regime_breakdown",
    "validate_scan_universe",
    "InstrumentId",
    "InstrumentMaster",
    "InstrumentMasterEntry",
    "InstrumentType",
    "MembershipManifest",
    "MembershipRecord",
    "MembershipStatus",
    "UniverseAuthority",
    "CORPORATE_ACTION_HANDLING_NOT_EXERCISED",
    "HISTORICAL_MEMBERSHIP_MODEL",
    "BiasStressComparison",
    "CurrentUniverseBiasStressResult",
    "StressWindowComparison",
    "SurvivorshipAwareRobustnessStudy",
    "SurvivorshipAwareRobustnessStudyRepository",
    "SurvivorshipClassification",
    "SurvivorshipStudyStatus",
    "SurvivorshipWindowResult",
    "WindowUniverseSnapshot",
    "build_survivorship_aware_robustness_study",
    "canonical_membership_payload",
    "membership_manifest_hash",
    "universe_at",
]
