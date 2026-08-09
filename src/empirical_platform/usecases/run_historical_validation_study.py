"""Run one deterministic multi-period historical validation study
end-to-end.

MILESTONE-062.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal

from empirical_platform.decision_candidate.historical_backtest import (
    DEFAULT_COST_MODEL,
    DEFAULT_EXECUTION_ASSUMPTION,
    DEFAULT_OUTCOME_MODEL,
    HistoricalCostModel,
    HistoricalExecutionAssumption,
    HistoricalOutcomeModel,
)
from empirical_platform.decision_candidate.historical_backtest_repository import (
    HistoricalBacktestRunRepository,
)
from empirical_platform.decision_candidate.position_plan import (
    DEFAULT_SIZING_POLICY,
    PositionSizingContext,
    SizingPolicy,
)
from empirical_platform.decision_candidate.trade_plan import DEFAULT_RISK_POLICY, RiskPolicy
from empirical_platform.decision_candidate.validation_study import (
    HistoricalValidationStudy,
    ValidationDatasetBundle,
    build_validation_study,
)
from empirical_platform.decision_candidate.validation_study_repository import (
    HistoricalValidationStudyRepository,
)
from empirical_platform.identifiers.pairs import DomainIdentity
from empirical_platform.identifiers.types import BacktestRunId, ValidationStudyId
from empirical_platform.shared.identifiers import RuntimeIdentifierGenerator

# Explicit re-exports: `entrypoints` cannot import `decision_candidate`
# directly (architecture rule), so this usecase re-exports the domain
# types its own entrypoint needs to construct -- the idiom established in
# M054/M057/M058/M059/M060/M061.
__all__ = [
    "DEFAULT_COST_MODEL",
    "DEFAULT_EXECUTION_ASSUMPTION",
    "DEFAULT_OUTCOME_MODEL",
    "DEFAULT_RISK_POLICY",
    "DEFAULT_SIZING_POLICY",
    "HistoricalCostModel",
    "HistoricalExecutionAssumption",
    "HistoricalOutcomeModel",
    "HistoricalValidationStudy",
    "PositionSizingContext",
    "RiskPolicy",
    "RunHistoricalValidationStudyCommand",
    "RunHistoricalValidationStudyHandler",
    "SizingPolicy",
    "ValidationDatasetBundle",
    "build_run_historical_validation_study_command",
]


@dataclass(frozen=True, slots=True)
class RunHistoricalValidationStudyCommand:
    """Request to run one deterministic multi-period validation study."""

    identity: DomainIdentity[ValidationStudyId]
    bundle: ValidationDatasetBundle
    sizing_context: PositionSizingContext
    runtime_identifier_generator: RuntimeIdentifierGenerator
    backtest_run_identity_for: Callable[[str], DomainIdentity[BacktestRunId]]
    reference_window_size: int = 5
    risk_policy: RiskPolicy = DEFAULT_RISK_POLICY
    sizing_policy: SizingPolicy = DEFAULT_SIZING_POLICY
    execution_assumption: HistoricalExecutionAssumption = DEFAULT_EXECUTION_ASSUMPTION
    outcome_model: HistoricalOutcomeModel = DEFAULT_OUTCOME_MODEL
    cost_model: HistoricalCostModel = DEFAULT_COST_MODEL


class RunHistoricalValidationStudyHandler:
    """Build and persist one immutable validation study, and each of its
    three segments' own M061 `HistoricalBacktestRun` -- through the
    unmodified M061 repository, never a second persistence path."""

    __slots__ = ("_historical_backtest_run_repository", "_validation_study_repository")

    def __init__(
        self,
        *,
        historical_backtest_run_repository: HistoricalBacktestRunRepository,
        validation_study_repository: HistoricalValidationStudyRepository,
    ) -> None:
        self._historical_backtest_run_repository = historical_backtest_run_repository
        self._validation_study_repository = validation_study_repository

    def handle(self, command: RunHistoricalValidationStudyCommand) -> HistoricalValidationStudy:
        study, runs = build_validation_study(
            identity=command.identity,
            bundle=command.bundle,
            sizing_context=command.sizing_context,
            runtime_identifier_generator=command.runtime_identifier_generator,
            backtest_run_identity_for=command.backtest_run_identity_for,
            reference_window_size=command.reference_window_size,
            risk_policy=command.risk_policy,
            sizing_policy=command.sizing_policy,
            execution_assumption=command.execution_assumption,
            outcome_model=command.outcome_model,
            cost_model=command.cost_model,
        )
        for run in runs:
            self._historical_backtest_run_repository.add(run)
        self._validation_study_repository.add(study)
        return study


def build_run_historical_validation_study_command(
    *,
    study_governance_id: str,
    bundle: ValidationDatasetBundle,
    development_backtest_run_governance_id: str,
    holdout_1_backtest_run_governance_id: str,
    holdout_2_backtest_run_governance_id: str,
    account_equity: Decimal,
    risk_percent: Decimal,
    runtime_identifier_generator: RuntimeIdentifierGenerator,
    reference_window_size: int = 5,
    holding_horizon_bars: int = 3,
) -> RunHistoricalValidationStudyCommand:
    """Build one real M062 command from plain application-layer inputs."""
    run_governance_ids = {
        "DEV": development_backtest_run_governance_id,
        "HOLDOUT_1": holdout_1_backtest_run_governance_id,
        "HOLDOUT_2": holdout_2_backtest_run_governance_id,
    }

    def _backtest_run_identity_for(segment_id: str) -> DomainIdentity[BacktestRunId]:
        return DomainIdentity(
            governance_id=BacktestRunId(run_governance_ids[segment_id]),
            runtime_id=runtime_identifier_generator.generate(),
        )

    return RunHistoricalValidationStudyCommand(
        identity=DomainIdentity(
            governance_id=ValidationStudyId(study_governance_id),
            runtime_id=runtime_identifier_generator.generate(),
        ),
        bundle=bundle,
        sizing_context=PositionSizingContext(
            account_equity=account_equity, risk_percent=risk_percent
        ),
        runtime_identifier_generator=runtime_identifier_generator,
        backtest_run_identity_for=_backtest_run_identity_for,
        reference_window_size=reference_window_size,
        execution_assumption=HistoricalExecutionAssumption(),
        outcome_model=HistoricalOutcomeModel(holding_horizon_bars=holding_horizon_bars),
        cost_model=HistoricalCostModel(),
    )
