"""Run one deterministic broad multi-window historical robustness study
end-to-end.

MILESTONE-063.
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
from empirical_platform.decision_candidate.robustness_study import (
    HistoricalRobustnessStudy,
    RobustnessDatasetBundle,
    build_robustness_study,
)
from empirical_platform.decision_candidate.robustness_study_repository import (
    HistoricalRobustnessStudyRepository,
)
from empirical_platform.decision_candidate.trade_plan import DEFAULT_RISK_POLICY, RiskPolicy
from empirical_platform.identifiers.pairs import DomainIdentity
from empirical_platform.identifiers.types import BacktestRunId, RobustnessStudyId
from empirical_platform.shared.identifiers import RuntimeIdentifierGenerator

# Explicit re-exports: `entrypoints` cannot import `decision_candidate`
# directly (architecture rule) -- the idiom established in
# M054/M057/M058/M059/M060/M061/M062.
__all__ = [
    "DEFAULT_COST_MODEL",
    "DEFAULT_EXECUTION_ASSUMPTION",
    "DEFAULT_OUTCOME_MODEL",
    "DEFAULT_RISK_POLICY",
    "DEFAULT_SIZING_POLICY",
    "HistoricalCostModel",
    "HistoricalExecutionAssumption",
    "HistoricalOutcomeModel",
    "HistoricalRobustnessStudy",
    "PositionSizingContext",
    "RiskPolicy",
    "RobustnessDatasetBundle",
    "RunHistoricalRobustnessStudyCommand",
    "RunHistoricalRobustnessStudyHandler",
    "SizingPolicy",
    "build_run_historical_robustness_study_command",
]


@dataclass(frozen=True, slots=True)
class RunHistoricalRobustnessStudyCommand:
    """Request to run one deterministic broad multi-window robustness study."""

    identity: DomainIdentity[RobustnessStudyId]
    bundle: RobustnessDatasetBundle
    sizing_context: PositionSizingContext
    runtime_identifier_generator: RuntimeIdentifierGenerator
    backtest_run_identity_for: Callable[[str], DomainIdentity[BacktestRunId]]
    reference_window_size: int = 5
    risk_policy: RiskPolicy = DEFAULT_RISK_POLICY
    sizing_policy: SizingPolicy = DEFAULT_SIZING_POLICY
    execution_assumption: HistoricalExecutionAssumption = DEFAULT_EXECUTION_ASSUMPTION
    outcome_model: HistoricalOutcomeModel = DEFAULT_OUTCOME_MODEL
    cost_model: HistoricalCostModel = DEFAULT_COST_MODEL


class RunHistoricalRobustnessStudyHandler:
    """Build and persist one immutable robustness study, and each of its
    N windows' own M061 `HistoricalBacktestRun` -- through the unmodified
    M061 repository, never a second persistence path."""

    __slots__ = ("_historical_backtest_run_repository", "_robustness_study_repository")

    def __init__(
        self,
        *,
        historical_backtest_run_repository: HistoricalBacktestRunRepository,
        robustness_study_repository: HistoricalRobustnessStudyRepository,
    ) -> None:
        self._historical_backtest_run_repository = historical_backtest_run_repository
        self._robustness_study_repository = robustness_study_repository

    def handle(self, command: RunHistoricalRobustnessStudyCommand) -> HistoricalRobustnessStudy:
        study, runs = build_robustness_study(
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
        self._robustness_study_repository.add(study)
        return study


def build_run_historical_robustness_study_command(
    *,
    study_governance_id: str,
    bundle: RobustnessDatasetBundle,
    backtest_run_governance_id_base: int,
    account_equity: Decimal,
    risk_percent: Decimal,
    runtime_identifier_generator: RuntimeIdentifierGenerator,
    reference_window_size: int = 5,
    holding_horizon_bars: int = 3,
) -> RunHistoricalRobustnessStudyCommand:
    """Build one real M063 command from plain application-layer inputs.

    Each window's own `BacktestRunId` is deterministically derived from
    `backtest_run_governance_id_base + (window.sequence_index + 1)`
    (4-digit-formatted) -- avoiding an unbounded CLI argument list for an
    arbitrary window count, while remaining fully deterministic and
    caller-controlled via the single base value.
    """
    sequence_index_by_window_id = {
        spec.window_id: spec.sequence_index for spec in bundle.window_specs
    }

    def _backtest_run_identity_for(window_id: str) -> DomainIdentity[BacktestRunId]:
        sequence_index = sequence_index_by_window_id[window_id]
        governance_number = backtest_run_governance_id_base + sequence_index + 1
        return DomainIdentity(
            governance_id=BacktestRunId(f"BTRUN-{governance_number:04d}"),
            runtime_id=runtime_identifier_generator.generate(),
        )

    return RunHistoricalRobustnessStudyCommand(
        identity=DomainIdentity(
            governance_id=RobustnessStudyId(study_governance_id),
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
