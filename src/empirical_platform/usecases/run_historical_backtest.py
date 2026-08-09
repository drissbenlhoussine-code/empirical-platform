"""Run one deterministic historical validation backtest end-to-end.

MILESTONE-061.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from empirical_platform.decision_candidate.historical_backtest import (
    DEFAULT_COST_MODEL,
    DEFAULT_EXECUTION_ASSUMPTION,
    DEFAULT_OUTCOME_MODEL,
    HistoricalBacktestRun,
    HistoricalCostModel,
    HistoricalDataset,
    HistoricalExecutionAssumption,
    HistoricalOutcomeModel,
    build_historical_backtest_run,
)
from empirical_platform.decision_candidate.historical_backtest_repository import (
    HistoricalBacktestRunRepository,
)
from empirical_platform.decision_candidate.position_plan import (
    DEFAULT_SIZING_POLICY,
    PositionSizingContext,
    SizingPolicy,
)
from empirical_platform.decision_candidate.trade_plan import (
    DEFAULT_RISK_POLICY,
    RiskPolicy,
)
from empirical_platform.identifiers.pairs import DomainIdentity
from empirical_platform.identifiers.types import BacktestRunId
from empirical_platform.shared.identifiers import RuntimeIdentifierGenerator


@dataclass(frozen=True, slots=True)
class RunHistoricalBacktestCommand:
    """Request to run one deterministic historical backtest."""

    identity: DomainIdentity[BacktestRunId]
    dataset: HistoricalDataset
    sizing_context: PositionSizingContext
    runtime_identifier_generator: RuntimeIdentifierGenerator
    reference_window_size: int = 5
    risk_policy: RiskPolicy = DEFAULT_RISK_POLICY
    sizing_policy: SizingPolicy = DEFAULT_SIZING_POLICY
    execution_assumption: HistoricalExecutionAssumption = DEFAULT_EXECUTION_ASSUMPTION
    outcome_model: HistoricalOutcomeModel = DEFAULT_OUTCOME_MODEL
    cost_model: HistoricalCostModel = DEFAULT_COST_MODEL


class RunHistoricalBacktestHandler:
    """Build and persist one immutable historical backtest run."""

    __slots__ = ("_repository",)

    def __init__(self, *, repository: HistoricalBacktestRunRepository) -> None:
        self._repository = repository

    def handle(self, command: RunHistoricalBacktestCommand) -> HistoricalBacktestRun:
        run = build_historical_backtest_run(
            identity=command.identity,
            dataset=command.dataset,
            sizing_context=command.sizing_context,
            runtime_identifier_generator=command.runtime_identifier_generator,
            reference_window_size=command.reference_window_size,
            risk_policy=command.risk_policy,
            sizing_policy=command.sizing_policy,
            execution_assumption=command.execution_assumption,
            outcome_model=command.outcome_model,
            cost_model=command.cost_model,
        )
        self._repository.add(run)
        return run


def build_run_historical_backtest_command(
    *,
    run_governance_id: str,
    dataset: HistoricalDataset,
    account_equity: Decimal,
    risk_percent: Decimal,
    runtime_identifier_generator: RuntimeIdentifierGenerator,
    reference_window_size: int = 5,
    holding_horizon_bars: int = 3,
    entry_slippage_bps: Decimal = Decimal("5"),
    exit_slippage_bps: Decimal = Decimal("5"),
    fixed_commission_per_side: Decimal = Decimal("0"),
) -> RunHistoricalBacktestCommand:
    """Build one real M061 command from plain application-layer inputs."""
    return RunHistoricalBacktestCommand(
        identity=DomainIdentity(
            governance_id=BacktestRunId(run_governance_id),
            runtime_id=runtime_identifier_generator.generate(),
        ),
        dataset=dataset,
        sizing_context=PositionSizingContext(
            account_equity=account_equity,
            risk_percent=risk_percent,
        ),
        runtime_identifier_generator=runtime_identifier_generator,
        reference_window_size=reference_window_size,
        execution_assumption=HistoricalExecutionAssumption(),
        outcome_model=HistoricalOutcomeModel(holding_horizon_bars=holding_horizon_bars),
        cost_model=HistoricalCostModel(
            entry_slippage_bps=entry_slippage_bps,
            exit_slippage_bps=exit_slippage_bps,
            fixed_commission_per_side=fixed_commission_per_side,
        ),
    )
