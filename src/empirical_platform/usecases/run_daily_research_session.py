"""Run one complete, one-command daily research session end-to-end.

MILESTONE-070. Coordinates the frozen M051-M054 governance chain
(Campaign -> Run -> EvidencePackage, created transparently to satisfy
the real M058 foreign-key requirement -- an operator never has to think
about it), the frozen M069 real-data acquisition, the frozen
M057/M058 candidate evaluation and ranking, the frozen M059 risk gate,
the frozen M060 position sizing, and the frozen M061 historical
backtest -- never reimplementing any of their own business logic. Each
stage's own attempt is recorded in an ordered stage manifest; a failure
in any stage halts the session, marks it FAILED, and preserves every
already-completed stage's own evidence (mission Phase 9).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal

from empirical_platform.campaign.aggregate import Campaign, CampaignScopeStatement
from empirical_platform.campaign.repository import CampaignRepository
from empirical_platform.decision_candidate.dataset_snapshot_repository import (
    DatasetSnapshotRepository,
)
from empirical_platform.decision_candidate.historical_backtest_repository import (
    HistoricalBacktestRunRepository,
)
from empirical_platform.decision_candidate.instrument_master import InstrumentMasterRepository
from empirical_platform.decision_candidate.market_data import BarInterval
from empirical_platform.decision_candidate.market_data_acquisition import MarketDataSource
from empirical_platform.decision_candidate.position_plan import (
    DEFAULT_SIZING_POLICY,
    PositionPlanStatus,
    PositionSizingContext,
)
from empirical_platform.decision_candidate.position_plan_repository import PositionPlanRepository
from empirical_platform.decision_candidate.ranking import RANKING_MODEL_ID, RANKING_MODEL_VERSION
from empirical_platform.decision_candidate.repository import DecisionCandidateRepository
from empirical_platform.decision_candidate.research_session import (
    RESEARCH_SESSION_CLAIM_HONESTY_LIMITATIONS,
    ResearchDecisionEntry,
    ResearchSession,
    ResearchSessionStatus,
    StageName,
    StageRecord,
    StageStatus,
    derive_observation_window,
    derive_shared_evaluation_timestamp,
)
from empirical_platform.decision_candidate.research_session_repository import (
    ResearchSessionRepository,
)
from empirical_platform.decision_candidate.scan_repository import TradingOpportunityScanRepository
from empirical_platform.decision_candidate.strategy import (
    STRATEGY_ID,
    STRATEGY_VERSION,
    StrategyParameters,
    TradingDecision,
)
from empirical_platform.decision_candidate.trade_plan import DEFAULT_RISK_POLICY, TradePlanStatus
from empirical_platform.decision_candidate.trade_plan_repository import TradePlanRepository
from empirical_platform.evidence.package import EvidencePackage
from empirical_platform.evidence.repository import EvidencePackageRepository
from empirical_platform.identifiers.pairs import DomainIdentity
from empirical_platform.identifiers.types import (
    CampaignId,
    DecisionCandidateId,
    EvidencePackageId,
    PositionPlanId,
    ResearchSessionId,
    RunId,
    TradePlanId,
    TradingOpportunityScanId,
)
from empirical_platform.run.aggregate import Run
from empirical_platform.run.repository import RunRepository
from empirical_platform.shared.identifiers import RuntimeIdentifierGenerator
from empirical_platform.shared.interfaces.clock import WallClock
from empirical_platform.usecases.acquire_market_data_snapshot import (
    AcquireMarketDataSnapshotHandler,
    build_acquire_market_data_snapshot_command,
    build_trivial_instrument_master,
)
from empirical_platform.usecases.build_position_plan import (
    BuildPositionPlanCommand,
    BuildPositionPlanHandler,
)
from empirical_platform.usecases.build_trade_plan import (
    BuildTradePlanCommand,
    BuildTradePlanHandler,
)
from empirical_platform.usecases.historical_backtest_io import (
    parse_historical_backtest_dataset_file,
)
from empirical_platform.usecases.run_historical_backtest import (
    RunHistoricalBacktestHandler,
    build_run_historical_backtest_command,
)
from empirical_platform.usecases.run_trading_opportunity_scan import (
    RunTradingOpportunityScanCommand,
    RunTradingOpportunityScanHandler,
    ScanUniverseEntry,
)

__all__ = [
    "RESEARCH_SESSION_CLAIM_HONESTY_LIMITATIONS",
    "BarInterval",
    "PositionSizingContext",
    "ResearchSession",
    "RunDailyResearchSessionCommand",
    "RunDailyResearchSessionHandler",
    "build_run_daily_research_session_command",
]


@dataclass(frozen=True, slots=True)
class RunDailyResearchSessionCommand:
    """Request to run one complete daily research session. Deliberately
    minimal: only genuinely operator-necessary inputs, with sensible
    frozen defaults for everything else (mission Phase 5: "avoid a
    30-argument CLI")."""

    identity: DomainIdentity[ResearchSessionId]
    as_of: datetime
    universe: tuple[str, ...]
    lookback_days: int
    artifact_path: str
    account_equity: Decimal
    risk_percent: Decimal
    source: MarketDataSource
    reference_window_size: int = 5


class RunDailyResearchSessionHandler:
    """Coordinates the full daily research pipeline over one shared set
    of frozen repositories. Never reimplements strategy, ranking, risk,
    sizing, backtest, correlation, or market-data-parsing logic -- every
    stage below is exactly one already-frozen handler's own call."""

    __slots__ = (
        "_campaigns",
        "_runs",
        "_evidence_packages",
        "_dataset_snapshots",
        "_instrument_masters",
        "_decision_candidates",
        "_trading_opportunity_scans",
        "_trade_plans",
        "_position_plans",
        "_historical_backtests",
        "_research_sessions",
        "_clock",
        "_runtime_identifier_generator",
    )

    def __init__(
        self,
        *,
        campaign_repository: CampaignRepository,
        run_repository: RunRepository,
        evidence_package_repository: EvidencePackageRepository,
        dataset_snapshot_repository: DatasetSnapshotRepository,
        instrument_master_repository: InstrumentMasterRepository,
        decision_candidate_repository: DecisionCandidateRepository,
        trading_opportunity_scan_repository: TradingOpportunityScanRepository,
        trade_plan_repository: TradePlanRepository,
        position_plan_repository: PositionPlanRepository,
        historical_backtest_repository: HistoricalBacktestRunRepository,
        research_session_repository: ResearchSessionRepository,
        clock: WallClock,
        runtime_identifier_generator: RuntimeIdentifierGenerator,
    ) -> None:
        self._campaigns = campaign_repository
        self._runs = run_repository
        self._evidence_packages = evidence_package_repository
        self._dataset_snapshots = dataset_snapshot_repository
        self._instrument_masters = instrument_master_repository
        self._decision_candidates = decision_candidate_repository
        self._trading_opportunity_scans = trading_opportunity_scan_repository
        self._trade_plans = trade_plan_repository
        self._position_plans = position_plan_repository
        self._historical_backtests = historical_backtest_repository
        self._research_sessions = research_session_repository
        self._clock = clock
        self._runtime_identifier_generator = runtime_identifier_generator

    def handle(self, command: RunDailyResearchSessionCommand) -> ResearchSession:
        stages: list[StageRecord] = []
        created_at = self._clock.now()
        session_governance_id = str(command.identity.governance_id)
        session_runtime_id_str = str(command.identity.runtime_id)
        suffix = session_governance_id.split("-")[-1]
        campaign_governance_id = f"CAMP-{suffix}"
        run_governance_id = f"RUN-{suffix}"
        evidence_package_governance_id = f"EVID-{suffix}"

        def fail_session(
            *,
            stage_name: StageName,
            stage_version: str | None,
            input_authority: str,
            started_at: datetime,
            exc: Exception,
            dataset_id: str | None = None,
            dataset_version: str | None = None,
            dataset_sha256: str | None = None,
            scan_governance_id: str | None = None,
            decisions: tuple[ResearchDecisionEntry, ...] = (),
            candidate_count: int = 0,
            accepted_trade_plan_count: int = 0,
            rejected_trade_plan_count: int = 0,
            position_plan_count: int = 0,
            backtest_run_governance_id: str | None = None,
            backtest_evaluated_opportunity_count: int | None = None,
            backtest_executed_trade_count: int | None = None,
        ) -> ResearchSession:
            completed_at = self._clock.now()
            stages.append(
                StageRecord(
                    stage_name=stage_name,
                    stage_version=stage_version,
                    started_at=started_at,
                    completed_at=completed_at,
                    status=StageStatus.FAILED,
                    input_authority=input_authority,
                    output_identity=None,
                    error_type=type(exc).__name__,
                    error_message=str(exc),
                )
            )
            session = ResearchSession(
                identity=command.identity,
                created_at=created_at,
                as_of=command.as_of,
                requested_universe=command.universe,
                data_source=command.source.source_name,
                dataset_id=dataset_id,
                dataset_version=dataset_version,
                dataset_sha256=dataset_sha256,
                strategy_id=STRATEGY_ID if candidate_count or decisions else None,
                strategy_version=STRATEGY_VERSION if candidate_count or decisions else None,
                ranking_model_id=RANKING_MODEL_ID if decisions else None,
                ranking_model_version=RANKING_MODEL_VERSION if decisions else None,
                risk_policy_id=DEFAULT_RISK_POLICY.policy_id if decisions else None,
                risk_policy_version=DEFAULT_RISK_POLICY.policy_version if decisions else None,
                sizing_policy_id=DEFAULT_SIZING_POLICY.policy_id if position_plan_count else None,
                sizing_policy_version=(
                    DEFAULT_SIZING_POLICY.policy_version if position_plan_count else None
                ),
                campaign_governance_id=campaign_governance_id,
                run_governance_id=run_governance_id,
                evidence_package_governance_id=evidence_package_governance_id,
                scan_governance_id=scan_governance_id,
                status=ResearchSessionStatus.FAILED,
                failed_stage=stage_name,
                failure_type=type(exc).__name__,
                failure_message=str(exc),
                completed_at=completed_at,
                stage_manifest=tuple(stages),
                decisions=decisions,
                candidate_count=candidate_count,
                accepted_trade_plan_count=accepted_trade_plan_count,
                rejected_trade_plan_count=rejected_trade_plan_count,
                position_plan_count=position_plan_count,
                backtest_run_governance_id=backtest_run_governance_id,
                backtest_evaluated_opportunity_count=backtest_evaluated_opportunity_count,
                backtest_executed_trade_count=backtest_executed_trade_count,
                limitations=RESEARCH_SESSION_CLAIM_HONESTY_LIMITATIONS,
            )
            self._research_sessions.add(session)
            return session

        # -------------------------------------------------------------
        # Stage 1: GOVERNANCE_SETUP -- transparently satisfy the real
        # M058 foreign-key requirement (scan.target_evidence_package_id
        # -> evidence_package.governance_id -> run.governance_id ->
        # campaign.governance_id). The operator never supplies these.
        # -------------------------------------------------------------
        stage_started = self._clock.now()
        try:
            self._campaigns.add(
                Campaign(
                    identity=DomainIdentity(
                        governance_id=CampaignId(campaign_governance_id),
                        runtime_id=self._runtime_identifier_generator.generate(),
                    ),
                    scope_statement=CampaignScopeStatement(
                        f"Daily research session {session_governance_id}"
                    ),
                )
            )
            self._runs.add(
                Run(
                    identity=DomainIdentity(
                        governance_id=RunId(run_governance_id),
                        runtime_id=self._runtime_identifier_generator.generate(),
                    ),
                    campaign_id=CampaignId(campaign_governance_id),
                )
            )
            self._evidence_packages.add(
                EvidencePackage(
                    identity=DomainIdentity(
                        governance_id=EvidencePackageId(evidence_package_governance_id),
                        runtime_id=self._runtime_identifier_generator.generate(),
                    ),
                    run_id=RunId(run_governance_id),
                )
            )
        except Exception as exc:  # noqa: BLE001 - deliberately captured into the session record
            return fail_session(
                stage_name=StageName.GOVERNANCE_SETUP,
                stage_version=None,
                input_authority=f"session={session_governance_id}",
                started_at=stage_started,
                exc=exc,
            )
        stages.append(
            StageRecord(
                stage_name=StageName.GOVERNANCE_SETUP,
                stage_version=None,
                started_at=stage_started,
                completed_at=self._clock.now(),
                status=StageStatus.COMPLETED,
                input_authority=f"session={session_governance_id}",
                output_identity=(
                    f"{campaign_governance_id}/{run_governance_id}/{evidence_package_governance_id}"
                ),
                error_type=None,
                error_message=None,
            )
        )

        # -------------------------------------------------------------
        # Stage 2: DATA_ACQUISITION -- the real, frozen M069 pipeline.
        # The as-of firewall's first layer: the acquisition request
        # itself is bounded to end_date = as_of's own date, never later.
        # -------------------------------------------------------------
        stage_started = self._clock.now()
        dataset_governance_id = f"DATASET-{suffix}"
        try:
            instrument_master = build_trivial_instrument_master(command.universe)
            acquisition_handler = AcquireMarketDataSnapshotHandler(
                dataset_snapshot_repository=self._dataset_snapshots,
                instrument_master_repository=self._instrument_masters,
                source=command.source,
                clock_now=self._clock.now(),
            )
            acquisition_result = acquisition_handler.handle(
                build_acquire_market_data_snapshot_command(
                    dataset_id=dataset_governance_id,
                    dataset_version="1",
                    symbols=command.universe,
                    start_date=_days_before(command.as_of.date(), command.lookback_days),
                    end_date=command.as_of.date(),
                    interval=BarInterval.ONE_DAY,
                    instrument_master=instrument_master,
                    artifact_path=command.artifact_path,
                    license_note=(
                        "Real historical daily bars acquired for one daily research "
                        "session -- see MILESTONE-069 for full source provenance."
                    ),
                )
            )
        except Exception as exc:  # noqa: BLE001
            return fail_session(
                stage_name=StageName.DATA_ACQUISITION,
                stage_version=command.source.source_name,
                input_authority=(
                    f"universe={list(command.universe)}, as_of={command.as_of.isoformat()}"
                ),
                started_at=stage_started,
                exc=exc,
            )
        stages.append(
            StageRecord(
                stage_name=StageName.DATA_ACQUISITION,
                stage_version=command.source.source_name,
                started_at=stage_started,
                completed_at=self._clock.now(),
                status=StageStatus.COMPLETED,
                input_authority=(
                    f"universe={list(command.universe)}, as_of={command.as_of.isoformat()}"
                ),
                output_identity=f"{dataset_governance_id}/1",
                error_type=None,
                error_message=None,
            )
        )

        # -------------------------------------------------------------
        # Stage 3: DATASET_INTEGRITY_CHECK -- reuse the frozen M061
        # artifact parser (never reimplemented), then verify its own
        # freshly-recomputed hash matches what was just persisted --
        # the mandatory source-tamper defense (mission Phase 20).
        # -------------------------------------------------------------
        stage_started = self._clock.now()
        try:
            dataset = parse_historical_backtest_dataset_file(command.artifact_path)
            if dataset.authority.sha256 != acquisition_result.artifact_sha256:
                raise ValueError(
                    "dataset artifact hash mismatch: the file on disk no longer matches "
                    "its own declared dataset snapshot -- refusing to proceed"
                )
        except Exception as exc:  # noqa: BLE001
            return fail_session(
                stage_name=StageName.DATASET_INTEGRITY_CHECK,
                stage_version=None,
                input_authority=f"artifact_sha256={acquisition_result.artifact_sha256}",
                started_at=stage_started,
                exc=exc,
                dataset_id=dataset_governance_id,
                dataset_version="1",
                dataset_sha256=acquisition_result.artifact_sha256,
            )
        stages.append(
            StageRecord(
                stage_name=StageName.DATASET_INTEGRITY_CHECK,
                stage_version=None,
                started_at=stage_started,
                completed_at=self._clock.now(),
                status=StageStatus.COMPLETED,
                input_authority=f"artifact_sha256={acquisition_result.artifact_sha256}",
                output_identity=dataset.authority.sha256,
                error_type=None,
                error_message=None,
            )
        )

        # -------------------------------------------------------------
        # Stage 4: CANDIDATE_SCAN -- the as-of firewall's second layer
        # (shared evaluation cutoff, never a bar after as_of), then the
        # real, frozen M057/M058 evaluation + ranking.
        # -------------------------------------------------------------
        stage_started = self._clock.now()
        series_by_instrument = {str(series.instrument): series for series in dataset.series}
        scan_input_authority = (
            f"dataset={dataset_governance_id}/1, as_of={command.as_of.isoformat()}"
        )
        try:
            evaluation_timestamp = derive_shared_evaluation_timestamp(
                series_by_instrument, as_of=command.as_of
            )
            if evaluation_timestamp is None:
                raise ValueError(
                    "no shared bar timestamp exists across the requested universe at or "
                    "before as_of -- cannot build a synchronized scan universe"
                )
            windows = []
            for symbol in command.universe:
                series = series_by_instrument.get(symbol)
                if series is None:
                    raise ValueError(f"acquired dataset is missing requested instrument {symbol}")
                window = derive_observation_window(
                    series,
                    evaluation_timestamp=evaluation_timestamp,
                    reference_window_size=command.reference_window_size,
                )
                if window is None:
                    raise ValueError(
                        f"insufficient history for {symbol}: fewer than "
                        f"{command.reference_window_size} reference bars before "
                        f"{evaluation_timestamp.isoformat()}"
                    )
                windows.append(window)

            scan_governance_id = f"SCAN-{suffix}"
            candidate_identities = tuple(
                DomainIdentity(
                    governance_id=DecisionCandidateId(
                        _derived_governance_id("DCAND", session_runtime_id_str, i)
                    ),
                    runtime_id=self._runtime_identifier_generator.generate(),
                )
                for i in range(len(windows))
            )
            universe_entries = tuple(
                ScanUniverseEntry(decision_candidate_identity=identity, window=window)
                for identity, window in zip(candidate_identities, windows, strict=True)
            )
            scan_handler = RunTradingOpportunityScanHandler(
                decision_candidate_repository=self._decision_candidates,
                trading_opportunity_scan_repository=self._trading_opportunity_scans,
            )
            scan = scan_handler.handle(
                RunTradingOpportunityScanCommand(
                    scan_identity=DomainIdentity(
                        governance_id=TradingOpportunityScanId(scan_governance_id),
                        runtime_id=self._runtime_identifier_generator.generate(),
                    ),
                    target_evidence_package_id=EvidencePackageId(evidence_package_governance_id),
                    universe=universe_entries,
                    parameters=StrategyParameters(
                        reference_window_size=command.reference_window_size
                    ),
                )
            )
        except Exception as exc:  # noqa: BLE001
            return fail_session(
                stage_name=StageName.CANDIDATE_SCAN,
                stage_version=f"{STRATEGY_ID}/{STRATEGY_VERSION}",
                input_authority=scan_input_authority,
                started_at=stage_started,
                exc=exc,
                dataset_id=dataset_governance_id,
                dataset_version="1",
                dataset_sha256=dataset.authority.sha256,
            )
        stages.append(
            StageRecord(
                stage_name=StageName.CANDIDATE_SCAN,
                stage_version=f"{STRATEGY_ID}/{STRATEGY_VERSION}",
                started_at=stage_started,
                completed_at=self._clock.now(),
                status=StageStatus.COMPLETED,
                input_authority=scan_input_authority,
                output_identity=scan_governance_id,
                error_type=None,
                error_message=None,
            )
        )

        # -------------------------------------------------------------
        # Stage 5: TRADE_PLANNING -- the real, frozen M059 risk gate,
        # for every ranked LONG_CANDIDATE.
        # -------------------------------------------------------------
        stage_started = self._clock.now()
        decisions: list[ResearchDecisionEntry] = []
        accepted_trade_plan_count = 0
        rejected_trade_plan_count = 0
        trade_plan_identity_by_governance_id: dict[str, DomainIdentity[TradePlanId]] = {}
        candidate_identity_by_governance_id = {
            str(identity.governance_id): identity for identity in candidate_identities
        }
        trade_plan_handler = BuildTradePlanHandler(
            decision_candidate_repository=self._decision_candidates,
            trading_opportunity_scan_repository=self._trading_opportunity_scans,
            trade_plan_repository=self._trade_plans,
        )
        try:
            for entry in scan.evaluations:
                trade_plan_governance_id: str | None = None
                trade_plan_decision: str | None = None
                if entry.decision is TradingDecision.LONG_CANDIDATE:
                    assert entry.rank is not None
                    trade_plan_governance_id = _derived_governance_id(
                        "PLAN", session_runtime_id_str, entry.rank - 1
                    )
                    source_candidate_identity = candidate_identity_by_governance_id[
                        str(entry.decision_candidate_id)
                    ]
                    trade_plan_identity = DomainIdentity(
                        governance_id=TradePlanId(trade_plan_governance_id),
                        runtime_id=self._runtime_identifier_generator.generate(),
                    )
                    plan = trade_plan_handler.handle(
                        BuildTradePlanCommand(
                            identity=trade_plan_identity,
                            source_scan_identity=scan.identity,
                            source_decision_candidate_identity=source_candidate_identity,
                            target_evidence_package_id=EvidencePackageId(
                                evidence_package_governance_id
                            ),
                        )
                    )
                    trade_plan_identity_by_governance_id[trade_plan_governance_id] = (
                        trade_plan_identity
                    )
                    trade_plan_decision = plan.status.value
                    if plan.status is TradePlanStatus.APPROVED_PLAN:
                        accepted_trade_plan_count += 1
                    else:
                        rejected_trade_plan_count += 1
                decisions.append(
                    ResearchDecisionEntry(
                        rank=entry.rank,
                        instrument_symbol=str(entry.instrument),
                        decision_candidate_governance_id=str(entry.decision_candidate_id),
                        scan_decision=entry.decision.value,
                        trade_plan_governance_id=trade_plan_governance_id,
                        trade_plan_decision=trade_plan_decision,
                        position_plan_governance_id=None,
                    )
                )
        except Exception as exc:  # noqa: BLE001
            return fail_session(
                stage_name=StageName.TRADE_PLANNING,
                stage_version=f"{DEFAULT_RISK_POLICY.policy_id}/{DEFAULT_RISK_POLICY.policy_version}",
                input_authority=f"scan={scan_governance_id}",
                started_at=stage_started,
                exc=exc,
                dataset_id=dataset_governance_id,
                dataset_version="1",
                dataset_sha256=dataset.authority.sha256,
                scan_governance_id=scan_governance_id,
                decisions=tuple(decisions),
                candidate_count=scan.candidate_count,
            )
        stages.append(
            StageRecord(
                stage_name=StageName.TRADE_PLANNING,
                stage_version=f"{DEFAULT_RISK_POLICY.policy_id}/{DEFAULT_RISK_POLICY.policy_version}",
                started_at=stage_started,
                completed_at=self._clock.now(),
                status=StageStatus.COMPLETED,
                input_authority=f"scan={scan_governance_id}",
                output_identity=(
                    f"accepted={accepted_trade_plan_count}, rejected={rejected_trade_plan_count}"
                ),
                error_type=None,
                error_message=None,
            )
        )

        # -------------------------------------------------------------
        # Stage 6: POSITION_SIZING -- the real, frozen M060 sizing gate,
        # for every APPROVED_PLAN trade plan.
        # -------------------------------------------------------------
        stage_started = self._clock.now()
        position_plan_count = 0
        position_plan_handler = BuildPositionPlanHandler(
            trade_plan_repository=self._trade_plans,
            position_plan_repository=self._position_plans,
        )
        sizing_context = PositionSizingContext(
            account_equity=command.account_equity, risk_percent=command.risk_percent
        )
        try:
            for i, decision in enumerate(decisions):
                if decision.trade_plan_decision != TradePlanStatus.APPROVED_PLAN.value:
                    continue
                assert decision.trade_plan_governance_id is not None
                assert decision.rank is not None
                position_plan_governance_id = _derived_governance_id(
                    "POS", session_runtime_id_str, decision.rank - 1
                )
                source_trade_plan_identity = trade_plan_identity_by_governance_id[
                    decision.trade_plan_governance_id
                ]
                position_plan = position_plan_handler.handle(
                    BuildPositionPlanCommand(
                        identity=DomainIdentity(
                            governance_id=PositionPlanId(position_plan_governance_id),
                            runtime_id=self._runtime_identifier_generator.generate(),
                        ),
                        source_trade_plan_identity=source_trade_plan_identity,
                        sizing_context=sizing_context,
                    )
                )
                if position_plan.status is PositionPlanStatus.APPROVED_POSITION_PLAN:
                    position_plan_count += 1
                    decisions[i] = ResearchDecisionEntry(
                        rank=decision.rank,
                        instrument_symbol=decision.instrument_symbol,
                        decision_candidate_governance_id=decision.decision_candidate_governance_id,
                        scan_decision=decision.scan_decision,
                        trade_plan_governance_id=decision.trade_plan_governance_id,
                        trade_plan_decision=decision.trade_plan_decision,
                        position_plan_governance_id=position_plan_governance_id,
                    )
        except Exception as exc:  # noqa: BLE001
            return fail_session(
                stage_name=StageName.POSITION_SIZING,
                stage_version=f"{DEFAULT_SIZING_POLICY.policy_id}/{DEFAULT_SIZING_POLICY.policy_version}",
                input_authority=f"accepted_trade_plans={accepted_trade_plan_count}",
                started_at=stage_started,
                exc=exc,
                dataset_id=dataset_governance_id,
                dataset_version="1",
                dataset_sha256=dataset.authority.sha256,
                scan_governance_id=scan_governance_id,
                decisions=tuple(decisions),
                candidate_count=scan.candidate_count,
                accepted_trade_plan_count=accepted_trade_plan_count,
                rejected_trade_plan_count=rejected_trade_plan_count,
            )
        stages.append(
            StageRecord(
                stage_name=StageName.POSITION_SIZING,
                stage_version=(
                    f"{DEFAULT_SIZING_POLICY.policy_id}/{DEFAULT_SIZING_POLICY.policy_version}"
                ),
                started_at=stage_started,
                completed_at=self._clock.now(),
                status=StageStatus.COMPLETED,
                input_authority=f"accepted_trade_plans={accepted_trade_plan_count}",
                output_identity=f"position_plans={position_plan_count}",
                error_type=None,
                error_message=None,
            )
        )

        # -------------------------------------------------------------
        # Stage 7: BACKTEST_EVIDENCE -- the real, frozen M061 backtest,
        # over the exact same real, hash-verified dataset -- historical
        # evidence, never a claim about the live candidates above.
        # -------------------------------------------------------------
        stage_started = self._clock.now()
        backtest_run_governance_id = f"BTRUN-{suffix}"
        try:
            backtest_handler = RunHistoricalBacktestHandler(repository=self._historical_backtests)
            backtest_run = backtest_handler.handle(
                build_run_historical_backtest_command(
                    run_governance_id=backtest_run_governance_id,
                    dataset=dataset,
                    account_equity=command.account_equity,
                    risk_percent=command.risk_percent,
                    runtime_identifier_generator=self._runtime_identifier_generator,
                    reference_window_size=command.reference_window_size,
                )
            )
        except Exception as exc:  # noqa: BLE001
            return fail_session(
                stage_name=StageName.BACKTEST_EVIDENCE,
                stage_version=None,
                input_authority=f"dataset={dataset_governance_id}/1",
                started_at=stage_started,
                exc=exc,
                dataset_id=dataset_governance_id,
                dataset_version="1",
                dataset_sha256=dataset.authority.sha256,
                scan_governance_id=scan_governance_id,
                decisions=tuple(decisions),
                candidate_count=scan.candidate_count,
                accepted_trade_plan_count=accepted_trade_plan_count,
                rejected_trade_plan_count=rejected_trade_plan_count,
                position_plan_count=position_plan_count,
            )
        stages.append(
            StageRecord(
                stage_name=StageName.BACKTEST_EVIDENCE,
                stage_version=None,
                started_at=stage_started,
                completed_at=self._clock.now(),
                status=StageStatus.COMPLETED,
                input_authority=f"dataset={dataset_governance_id}/1",
                output_identity=backtest_run_governance_id,
                error_type=None,
                error_message=None,
            )
        )

        session = ResearchSession(
            identity=command.identity,
            created_at=created_at,
            as_of=command.as_of,
            requested_universe=command.universe,
            data_source=command.source.source_name,
            dataset_id=dataset_governance_id,
            dataset_version="1",
            dataset_sha256=dataset.authority.sha256,
            strategy_id=STRATEGY_ID,
            strategy_version=STRATEGY_VERSION,
            ranking_model_id=RANKING_MODEL_ID,
            ranking_model_version=RANKING_MODEL_VERSION,
            risk_policy_id=DEFAULT_RISK_POLICY.policy_id,
            risk_policy_version=DEFAULT_RISK_POLICY.policy_version,
            sizing_policy_id=DEFAULT_SIZING_POLICY.policy_id,
            sizing_policy_version=DEFAULT_SIZING_POLICY.policy_version,
            campaign_governance_id=campaign_governance_id,
            run_governance_id=run_governance_id,
            evidence_package_governance_id=evidence_package_governance_id,
            scan_governance_id=scan_governance_id,
            status=ResearchSessionStatus.COMPLETED,
            failed_stage=None,
            failure_type=None,
            failure_message=None,
            completed_at=self._clock.now(),
            stage_manifest=tuple(stages),
            decisions=tuple(decisions),
            candidate_count=scan.candidate_count,
            accepted_trade_plan_count=accepted_trade_plan_count,
            rejected_trade_plan_count=rejected_trade_plan_count,
            position_plan_count=position_plan_count,
            backtest_run_governance_id=backtest_run_governance_id,
            backtest_evaluated_opportunity_count=backtest_run.evaluated_opportunity_count,
            backtest_executed_trade_count=backtest_run.executed_trade_count,
            limitations=RESEARCH_SESSION_CLAIM_HONESTY_LIMITATIONS,
        )
        self._research_sessions.add(session)
        return session


def _days_before(day: date, days: int) -> date:
    return day - timedelta(days=days)


def _derived_governance_id(prefix: str, session_runtime_id: str, offset: int) -> str:
    """Derive one additional, per-session governance id, spread
    pseudo-uniformly across the frozen `Identifier` pattern's own exact
    4-digit keyspace via a hash of the session's own genuinely unique
    `runtime_id` (a UUID) plus a small offset -- deliberately NOT a
    simple arithmetic offset from the caller-chosen governance id
    suffix, which would deterministically collide between two sessions
    with nearby governance ids (e.g. RESEARCH-9001 and RESEARCH-9002
    would otherwise mint overlapping derived candidate ids). An operator
    only ever supplies the session's own governance id (mission Phase
    23), never these derived ones. A residual collision probability
    remains inherent to any 10000-value keyspace shared across
    independently-generated sessions; `add()`'s own `AggregateAlreadyExists`
    is the honest, disclosed backstop (mission Phase 22) -- it is never
    silently swallowed, it fails the session with full inspectable
    error metadata."""
    digest = hashlib.sha256(f"{session_runtime_id}:{offset}".encode()).hexdigest()
    return f"{prefix}-{int(digest[:8], 16) % 10000:04d}"


def build_run_daily_research_session_command(
    *,
    session_governance_id: str,
    as_of: datetime,
    universe: tuple[str, ...],
    lookback_days: int,
    artifact_path: str,
    account_equity: Decimal,
    risk_percent: Decimal,
    source: MarketDataSource,
    runtime_identifier_generator: RuntimeIdentifierGenerator,
    reference_window_size: int = 5,
) -> RunDailyResearchSessionCommand:
    """Build one real M070 command from plain application-layer inputs."""
    return RunDailyResearchSessionCommand(
        identity=DomainIdentity(
            governance_id=ResearchSessionId(session_governance_id),
            runtime_id=runtime_identifier_generator.generate(),
        ),
        as_of=as_of,
        universe=universe,
        lookback_days=lookback_days,
        artifact_path=artifact_path,
        account_equity=account_equity,
        risk_percent=risk_percent,
        source=source,
        reference_window_size=reference_window_size,
    )
