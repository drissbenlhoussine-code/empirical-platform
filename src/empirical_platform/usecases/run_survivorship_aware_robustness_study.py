"""Run one deterministic survivorship-aware historical robustness study
end-to-end.

MILESTONE-064.
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
from empirical_platform.decision_candidate.instrument_master import (
    InstrumentMaster,
    InstrumentMasterRepository,
)
from empirical_platform.decision_candidate.membership import (
    MembershipManifest,
    UniverseMembershipRepository,
)
from empirical_platform.decision_candidate.position_plan import (
    DEFAULT_SIZING_POLICY,
    PositionSizingContext,
    SizingPolicy,
)
from empirical_platform.decision_candidate.robustness_study import RobustnessDatasetBundle
from empirical_platform.decision_candidate.robustness_study_repository import (
    HistoricalRobustnessStudyRepository,
)
from empirical_platform.decision_candidate.survivorship_study import (
    SurvivorshipAwareRobustnessStudy,
    build_survivorship_aware_robustness_study,
)
from empirical_platform.decision_candidate.survivorship_study_repository import (
    SurvivorshipAwareRobustnessStudyRepository,
)
from empirical_platform.decision_candidate.trade_plan import DEFAULT_RISK_POLICY, RiskPolicy
from empirical_platform.decision_candidate.universe_authority import UniverseAuthority
from empirical_platform.identifiers.pairs import DomainIdentity
from empirical_platform.identifiers.types import (
    BacktestRunId,
    RobustnessStudyId,
    SurvivorshipStudyId,
)
from empirical_platform.shared.identifiers import RuntimeIdentifierGenerator

# Explicit re-exports: `entrypoints` cannot import `decision_candidate`
# directly (architecture rule) -- the idiom established in
# M054/M057/M058/M059/M060/M061/M062/M063.
__all__ = [
    "DEFAULT_COST_MODEL",
    "DEFAULT_EXECUTION_ASSUMPTION",
    "DEFAULT_OUTCOME_MODEL",
    "DEFAULT_RISK_POLICY",
    "DEFAULT_SIZING_POLICY",
    "HistoricalCostModel",
    "HistoricalExecutionAssumption",
    "HistoricalOutcomeModel",
    "InstrumentMaster",
    "MembershipManifest",
    "PositionSizingContext",
    "RiskPolicy",
    "RobustnessDatasetBundle",
    "RunSurvivorshipAwareRobustnessStudyCommand",
    "RunSurvivorshipAwareRobustnessStudyHandler",
    "SizingPolicy",
    "SurvivorshipAwareRobustnessStudy",
    "UniverseAuthority",
    "build_run_survivorship_aware_robustness_study_command",
]


@dataclass(frozen=True, slots=True)
class RunSurvivorshipAwareRobustnessStudyCommand:
    """Request to run one deterministic survivorship-aware robustness
    study, plus its `CURRENT_UNIVERSE_BIAS_STRESS` diagnostic."""

    identity: DomainIdentity[SurvivorshipStudyId]
    stress_study_identity: DomainIdentity[RobustnessStudyId]
    bundle: RobustnessDatasetBundle
    instrument_master: InstrumentMaster
    membership_manifest: MembershipManifest
    universe_authority: UniverseAuthority
    sizing_context: PositionSizingContext
    runtime_identifier_generator: RuntimeIdentifierGenerator
    backtest_run_identity_for: Callable[[str], DomainIdentity[BacktestRunId]]
    stress_backtest_run_identity_for: Callable[[str], DomainIdentity[BacktestRunId]]
    reference_window_size: int = 5
    risk_policy: RiskPolicy = DEFAULT_RISK_POLICY
    sizing_policy: SizingPolicy = DEFAULT_SIZING_POLICY
    execution_assumption: HistoricalExecutionAssumption = DEFAULT_EXECUTION_ASSUMPTION
    outcome_model: HistoricalOutcomeModel = DEFAULT_OUTCOME_MODEL
    cost_model: HistoricalCostModel = DEFAULT_COST_MODEL


class RunSurvivorshipAwareRobustnessStudyHandler:
    """Build and persist one immutable survivorship-aware study, its own
    canonical-window `HistoricalBacktestRun`s, the diagnostic
    `CURRENT_UNIVERSE_BIAS_STRESS` `HistoricalRobustnessStudy` (a genuine
    M063 study) and its own `HistoricalBacktestRun`s, and the small
    instrument-master / universe-authority / membership-record reference
    data -- all through the unmodified M061/M063 repositories plus the two
    new small M064 reference repositories, never a second persistence
    path."""

    __slots__ = (
        "_historical_backtest_run_repository",
        "_robustness_study_repository",
        "_survivorship_study_repository",
        "_instrument_master_repository",
        "_universe_membership_repository",
    )

    def __init__(
        self,
        *,
        historical_backtest_run_repository: HistoricalBacktestRunRepository,
        robustness_study_repository: HistoricalRobustnessStudyRepository,
        survivorship_study_repository: SurvivorshipAwareRobustnessStudyRepository,
        instrument_master_repository: InstrumentMasterRepository,
        universe_membership_repository: UniverseMembershipRepository,
    ) -> None:
        self._historical_backtest_run_repository = historical_backtest_run_repository
        self._robustness_study_repository = robustness_study_repository
        self._survivorship_study_repository = survivorship_study_repository
        self._instrument_master_repository = instrument_master_repository
        self._universe_membership_repository = universe_membership_repository

    def handle(
        self, command: RunSurvivorshipAwareRobustnessStudyCommand
    ) -> SurvivorshipAwareRobustnessStudy:
        study, canonical_runs, stress_study, stress_runs = (
            build_survivorship_aware_robustness_study(
                identity=command.identity,
                stress_study_identity=command.stress_study_identity,
                bundle=command.bundle,
                instrument_master=command.instrument_master,
                membership_manifest=command.membership_manifest,
                sizing_context=command.sizing_context,
                runtime_identifier_generator=command.runtime_identifier_generator,
                backtest_run_identity_for=command.backtest_run_identity_for,
                stress_backtest_run_identity_for=command.stress_backtest_run_identity_for,
                reference_window_size=command.reference_window_size,
                risk_policy=command.risk_policy,
                sizing_policy=command.sizing_policy,
                execution_assumption=command.execution_assumption,
                outcome_model=command.outcome_model,
                cost_model=command.cost_model,
            )
        )
        self._instrument_master_repository.add_all(command.instrument_master)
        self._universe_membership_repository.add_universe(command.universe_authority)
        self._universe_membership_repository.add_membership(command.membership_manifest)
        for run in canonical_runs:
            self._historical_backtest_run_repository.add(run)
        for run in stress_runs:
            self._historical_backtest_run_repository.add(run)
        self._robustness_study_repository.add(stress_study)
        self._survivorship_study_repository.add(study)
        return study


def build_run_survivorship_aware_robustness_study_command(
    *,
    study_governance_id: str,
    stress_study_governance_id: str,
    bundle: RobustnessDatasetBundle,
    instrument_master: InstrumentMaster,
    membership_manifest: MembershipManifest,
    universe_source_kind: str,
    backtest_run_governance_id_base: int,
    stress_backtest_run_governance_id_base: int,
    account_equity: Decimal,
    risk_percent: Decimal,
    runtime_identifier_generator: RuntimeIdentifierGenerator,
    reference_window_size: int = 5,
    holding_horizon_bars: int = 3,
) -> RunSurvivorshipAwareRobustnessStudyCommand:
    """Build one real M064 command from plain application-layer inputs.

    Each canonical window's own `BacktestRunId` is deterministically
    derived from `backtest_run_governance_id_base + (sequence_index + 1)`;
    each diagnostic-stress window's own `BacktestRunId` is deterministically
    derived from a SEPARATE `stress_backtest_run_governance_id_base` --
    avoiding governance-ID collisions between the two parallel run sets
    while remaining fully deterministic and caller-controlled (the same
    scheme M063 already established, applied twice)."""
    sequence_index_by_window_id = {
        spec.window_id: spec.sequence_index for spec in bundle.window_specs
    }

    def _identity_for(base: int) -> Callable[[str], DomainIdentity[BacktestRunId]]:
        def _backtest_run_identity_for(window_id: str) -> DomainIdentity[BacktestRunId]:
            sequence_index = sequence_index_by_window_id[window_id]
            governance_number = base + sequence_index + 1
            return DomainIdentity(
                governance_id=BacktestRunId(f"BTRUN-{governance_number:04d}"),
                runtime_id=runtime_identifier_generator.generate(),
            )

        return _backtest_run_identity_for

    return RunSurvivorshipAwareRobustnessStudyCommand(
        identity=DomainIdentity(
            governance_id=SurvivorshipStudyId(study_governance_id),
            runtime_id=runtime_identifier_generator.generate(),
        ),
        stress_study_identity=DomainIdentity(
            governance_id=RobustnessStudyId(stress_study_governance_id),
            runtime_id=runtime_identifier_generator.generate(),
        ),
        bundle=bundle,
        instrument_master=instrument_master,
        membership_manifest=membership_manifest,
        universe_authority=UniverseAuthority(
            universe_id=membership_manifest.universe_id,
            universe_version=membership_manifest.universe_version,
            source_kind=universe_source_kind,
        ),
        sizing_context=PositionSizingContext(
            account_equity=account_equity, risk_percent=risk_percent
        ),
        runtime_identifier_generator=runtime_identifier_generator,
        backtest_run_identity_for=_identity_for(backtest_run_governance_id_base),
        stress_backtest_run_identity_for=_identity_for(stress_backtest_run_governance_id_base),
        reference_window_size=reference_window_size,
        execution_assumption=HistoricalExecutionAssumption(),
        outcome_model=HistoricalOutcomeModel(holding_horizon_bars=holding_horizon_bars),
        cost_model=HistoricalCostModel(),
    )
