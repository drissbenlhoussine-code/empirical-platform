"""CORPORATE_ACTION_SEMANTICS_STRESS: a diagnostic-only comparison between
a correctly-declared/adjusted dataset interpretation and a deliberately
naive/raw one, both fed through the identical, unmodified, frozen M061
`build_historical_backtest_run()`.

MILESTONE-065. This is not a second backtesting engine: it is the same
frozen function, called twice, over two different `HistoricalDataset`
objects that differ only in whether split-adjustment was applied. Its
purpose is to make visible, honestly, how corporate-action mishandling can
change trade candidates, prices, and PnL -- never to declare which
interpretation is "more real" beyond what the dataset snapshot's own
`price_semantics` field already states.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

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
from empirical_platform.decision_candidate.position_plan import (
    DEFAULT_SIZING_POLICY,
    PositionSizingContext,
    SizingPolicy,
)
from empirical_platform.decision_candidate.trade_plan import DEFAULT_RISK_POLICY, RiskPolicy
from empirical_platform.identifiers.pairs import DomainIdentity
from empirical_platform.identifiers.types import BacktestRunId, CorporateActionStressId, DatasetId
from empirical_platform.shared.identifiers import RuntimeIdentifierGenerator


class StressComparison(StrEnum):
    """Whether the naive/raw interpretation happens to agree with the
    correctly-adjusted one on this specific fixture -- reported honestly
    either way, never forced."""

    CORPORATE_ACTION_SEMANTICS_STRESS_IDENTICAL = "CORPORATE_ACTION_SEMANTICS_STRESS_IDENTICAL"
    CORPORATE_ACTION_SEMANTICS_STRESS_DIFFERS = "CORPORATE_ACTION_SEMANTICS_STRESS_DIFFERS"


@dataclass(frozen=True, slots=True)
class CorporateActionSemanticsStressResult:
    """One immutable, persisted comparison between the correctly-adjusted
    and the naive/raw interpretations of the same underlying raw source
    data, run through the identical frozen M061 engine."""

    identity: DomainIdentity[CorporateActionStressId]
    dataset_id: DatasetId
    correct_dataset_version: str
    correct_run_id: BacktestRunId
    naive_dataset_version: str
    naive_run_id: BacktestRunId
    comparison: StressComparison
    correct_executed_trade_count: int
    naive_executed_trade_count: int
    correct_net_pnl_total: Decimal
    naive_net_pnl_total: Decimal
    correct_total_r_total: Decimal
    naive_total_r_total: Decimal

    def __post_init__(self) -> None:
        if not isinstance(self.identity, DomainIdentity):
            raise TypeError("identity must be a DomainIdentity[CorporateActionStressId]")
        if not isinstance(self.identity.governance_id, CorporateActionStressId):
            raise TypeError("identity governance_id must be a CorporateActionStressId")
        for field_name in ("correct_dataset_version", "naive_dataset_version"):
            if not getattr(self, field_name).strip():
                raise ValueError(f"{field_name} must be non-empty")
        if self.correct_dataset_version == self.naive_dataset_version:
            raise ValueError(
                "correct_dataset_version and naive_dataset_version must be two distinct "
                "dataset versions of the same dataset_id"
            )


def build_corporate_action_semantics_stress(
    *,
    identity: DomainIdentity[CorporateActionStressId],
    correct_run_identity: DomainIdentity[BacktestRunId],
    naive_run_identity: DomainIdentity[BacktestRunId],
    correct_dataset: HistoricalDataset,
    naive_dataset: HistoricalDataset,
    sizing_context: PositionSizingContext,
    runtime_identifier_generator: RuntimeIdentifierGenerator,
    reference_window_size: int = 5,
    risk_policy: RiskPolicy = DEFAULT_RISK_POLICY,
    sizing_policy: SizingPolicy = DEFAULT_SIZING_POLICY,
    execution_assumption: HistoricalExecutionAssumption = DEFAULT_EXECUTION_ASSUMPTION,
    outcome_model: HistoricalOutcomeModel = DEFAULT_OUTCOME_MODEL,
    cost_model: HistoricalCostModel = DEFAULT_COST_MODEL,
) -> tuple[CorporateActionSemanticsStressResult, HistoricalBacktestRun, HistoricalBacktestRun]:
    """Run the real, unmodified M061 `build_historical_backtest_run()`
    twice -- once against `correct_dataset` (the properly split-adjusted
    interpretation) and once against `naive_dataset` (the raw
    interpretation, fed in as if it required no adjustment) -- and report
    the difference honestly. Both calls use the identical frozen policy
    stack; nothing is tuned between them."""
    correct_run = build_historical_backtest_run(
        identity=correct_run_identity,
        dataset=correct_dataset,
        sizing_context=sizing_context,
        runtime_identifier_generator=runtime_identifier_generator,
        reference_window_size=reference_window_size,
        risk_policy=risk_policy,
        sizing_policy=sizing_policy,
        execution_assumption=execution_assumption,
        outcome_model=outcome_model,
        cost_model=cost_model,
    )
    naive_run = build_historical_backtest_run(
        identity=naive_run_identity,
        dataset=naive_dataset,
        sizing_context=sizing_context,
        runtime_identifier_generator=runtime_identifier_generator,
        reference_window_size=reference_window_size,
        risk_policy=risk_policy,
        sizing_policy=sizing_policy,
        execution_assumption=execution_assumption,
        outcome_model=outcome_model,
        cost_model=cost_model,
    )
    comparison = (
        StressComparison.CORPORATE_ACTION_SEMANTICS_STRESS_IDENTICAL
        if (
            correct_run.executed_trade_count == naive_run.executed_trade_count
            and correct_run.net_pnl == naive_run.net_pnl
            and correct_run.total_r == naive_run.total_r
        )
        else StressComparison.CORPORATE_ACTION_SEMANTICS_STRESS_DIFFERS
    )
    result = CorporateActionSemanticsStressResult(
        identity=identity,
        dataset_id=correct_run.dataset_id,
        correct_dataset_version=correct_run.dataset_version,
        correct_run_id=correct_run.identity.governance_id,
        naive_dataset_version=naive_run.dataset_version,
        naive_run_id=naive_run.identity.governance_id,
        comparison=comparison,
        correct_executed_trade_count=correct_run.executed_trade_count,
        naive_executed_trade_count=naive_run.executed_trade_count,
        correct_net_pnl_total=correct_run.net_pnl,
        naive_net_pnl_total=naive_run.net_pnl,
        correct_total_r_total=correct_run.total_r,
        naive_total_r_total=naive_run.total_r,
    )
    return result, correct_run, naive_run
