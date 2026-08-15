"""Build one operator-facing daily research brief.

MILESTONE-072. Composes the frozen M057 (`DecisionCandidate`), M059
(`TradePlan`), M060 (`PositionPlan`), M070 (`ResearchSession`), and M071
(`compare_session_decisions`) evidence into one authoritative
`DailyResearchBrief` model. This handler performs real I/O (fetching
already-persisted records by governance id) but no new evaluation,
ranking, risk, sizing, backtest, statistical, portfolio, or dependence
computation -- every fetched record is read verbatim and handed to the
pure `build_daily_research_brief` domain function unchanged.
"""

from __future__ import annotations

from dataclasses import dataclass

from empirical_platform.decision_candidate.daily_research_brief import (
    BriefRiskEvidence,
    DailyResearchBrief,
    FetchedInstrumentEvidence,
    build_daily_research_brief,
)
from empirical_platform.decision_candidate.historical_portfolio_evidence import (
    HistoricalPortfolioEvidence,
)
from empirical_platform.decision_candidate.historical_portfolio_evidence_query_repository import (
    HistoricalPortfolioEvidenceQueryRepository,
)
from empirical_platform.decision_candidate.position_plan import PositionPlan
from empirical_platform.decision_candidate.position_plan_repository import PositionPlanRepository
from empirical_platform.decision_candidate.repository import DecisionCandidateRepository
from empirical_platform.decision_candidate.research_session import (
    RESEARCH_SESSION_CLAIM_HONESTY_LIMITATIONS,
    ResearchDecisionEntry,
    ResearchSessionSummary,
    compare_session_decisions,
)
from empirical_platform.decision_candidate.research_session_repository import (
    ResearchSessionRepository,
)
from empirical_platform.decision_candidate.trade_plan import TradePlan
from empirical_platform.decision_candidate.trade_plan_repository import TradePlanRepository
from empirical_platform.identifiers.pairs import DomainIdentity
from empirical_platform.identifiers.types import (
    DecisionCandidateId,
    PositionPlanId,
    ResearchSessionId,
    TradePlanId,
)
from empirical_platform.usecases.discover_historical_portfolio_evidence import (
    DiscoverHistoricalPortfolioEvidenceHandler,
    DiscoverHistoricalPortfolioEvidenceQuery,
)

__all__ = [
    "BuildDailyResearchBriefHandler",
    "BuildDailyResearchBriefQuery",
    "DailyResearchBrief",
]

_BACKTEST_NOTE = (
    "Retrospective evidence over the same acquired historical window -- "
    "not a claim about the live candidates in this brief."
)
_NO_PRIOR_SESSION_NOTE = "no prior session found for this universe -- this is the first session"


@dataclass(frozen=True, slots=True)
class BuildDailyResearchBriefQuery:
    """Request to build a daily research brief for one already-persisted
    session, by canonical identity."""

    identity: DomainIdentity[ResearchSessionId]


def _risk_evidence_from(
    *, trade_plan: TradePlan, position_plan: PositionPlan
) -> BriefRiskEvidence | None:
    geometry = trade_plan.geometry
    sizing = position_plan.sizing
    if geometry is None or sizing is None:
        return None
    return BriefRiskEvidence(
        entry_price=str(geometry.entry_price),
        stop_price=str(geometry.stop_price),
        target_price=str(geometry.target_price),
        reward_risk_ratio=str(geometry.reward_risk_ratio),
        quantity=sizing.quantity,
        position_notional=str(sizing.position_notional),
        actual_risk=str(sizing.actual_risk),
    )


class BuildDailyResearchBriefHandler:
    """Build one operator-facing daily research brief. MILESTONE-074
    adds a read-only historical-evidence discovery step that surfaces
    compatible persisted M064 + M067 historical research evidence
    under a strict honesty banner."""

    __slots__ = (
        "_research_sessions",
        "_decision_candidates",
        "_trade_plans",
        "_position_plans",
        "_historical_evidence_discovery",
    )

    def __init__(
        self,
        *,
        research_session_repository: ResearchSessionRepository,
        decision_candidate_repository: DecisionCandidateRepository,
        trade_plan_repository: TradePlanRepository,
        position_plan_repository: PositionPlanRepository,
        historical_evidence_query_repository: HistoricalPortfolioEvidenceQueryRepository
        | None = None,
    ) -> None:
        self._research_sessions = research_session_repository
        self._decision_candidates = decision_candidate_repository
        self._trade_plans = trade_plan_repository
        self._position_plans = position_plan_repository
        self._historical_evidence_discovery = (
            DiscoverHistoricalPortfolioEvidenceHandler(
                query_repository=historical_evidence_query_repository
            )
            if historical_evidence_query_repository is not None
            else None
        )

    def handle(self, query: BuildDailyResearchBriefQuery) -> DailyResearchBrief:
        target = self._research_sessions.get(query.identity)
        baseline = self._research_sessions.find_most_recent_prior(
            universe=target.requested_universe,
            before_as_of=target.as_of,
            exclude_runtime_id=target.identity.runtime_id,
        )
        comparison_entries = compare_session_decisions(
            target_decisions=target.decisions,
            baseline_decisions=baseline.decisions if baseline is not None else None,
        )

        is_completed = target.status.value == "COMPLETED"
        evidence_by_governance_id = {
            decision.decision_candidate_governance_id: self._fetch_evidence(
                decision, session_is_completed=is_completed
            )
            for decision in target.decisions
        }

        summary = ResearchSessionSummary(
            identity=target.identity,
            as_of=target.as_of,
            requested_universe=target.requested_universe,
            status=target.status,
            created_at=target.created_at,
            completed_at=target.completed_at,
            candidate_count=target.candidate_count,
            failed_stage=target.failed_stage,
        )

        historical_evidence: tuple[HistoricalPortfolioEvidence, ...] = ()
        historical_evidence_discovery_failed = False
        if self._historical_evidence_discovery is not None and is_completed:
            try:
                historical_evidence = self._historical_evidence_discovery.handle(
                    DiscoverHistoricalPortfolioEvidenceQuery(
                        strategy_id=target.strategy_id,
                        strategy_version=target.strategy_version,
                        ranking_model_id=target.ranking_model_id,
                        ranking_model_version=target.ranking_model_version,
                        risk_policy_id=target.risk_policy_id,
                        risk_policy_version=target.risk_policy_version,
                        sizing_policy_id=target.sizing_policy_id,
                        sizing_policy_version=target.sizing_policy_version,
                        requested_universe=target.requested_universe,
                        as_of=target.as_of,
                    )
                )
            except Exception:  # noqa: BLE001 - discovery failure is non-fatal to the core brief
                historical_evidence = ()
                historical_evidence_discovery_failed = True

        session_warnings: tuple[str, ...] = ()
        if target.status.value == "FAILED":
            session_warnings = (
                f"session FAILED at stage "
                f"{target.failed_stage.value if target.failed_stage is not None else '?'}: "
                f"{target.failure_message}",
            )
        if historical_evidence_discovery_failed:
            session_warnings = (
                *session_warnings,
                "historical portfolio evidence discovery failed -- the HISTORICAL "
                "PORTFOLIO EVIDENCE section below reflects an unavailable lookup, "
                "not a confirmed absence of compatible evidence",
            )

        return build_daily_research_brief(
            session=summary,
            session_status=target.status.value,
            session_warnings=session_warnings,
            target_decisions=target.decisions,
            comparison_entries=comparison_entries,
            evidence_by_governance_id=evidence_by_governance_id,
            baseline_session_governance_id=(
                str(baseline.identity.governance_id) if baseline is not None else None
            ),
            baseline_as_of=baseline.as_of if baseline is not None else None,
            baseline_note=None if baseline is not None else _NO_PRIOR_SESSION_NOTE,
            data_source=target.data_source,
            dataset_sha256=target.dataset_sha256,
            backtest_run_governance_id=target.backtest_run_governance_id,
            backtest_evaluated_opportunity_count=target.backtest_evaluated_opportunity_count,
            backtest_executed_trade_count=target.backtest_executed_trade_count,
            backtest_note=(
                _BACKTEST_NOTE
                if is_completed and target.backtest_run_governance_id is not None
                else None
            ),
            limitations=RESEARCH_SESSION_CLAIM_HONESTY_LIMITATIONS,
            campaign_governance_id=target.campaign_governance_id,
            run_governance_id=target.run_governance_id,
            evidence_package_governance_id=target.evidence_package_governance_id,
            scan_governance_id=target.scan_governance_id,
            stage_manifest_summary=tuple(
                f"{stage.stage_name.value}: {stage.status.value}" for stage in target.stage_manifest
            ),
            historical_portfolio_evidence=historical_evidence,
        )

    def _fetch_evidence(
        self, decision: ResearchDecisionEntry, *, session_is_completed: bool
    ) -> FetchedInstrumentEvidence:
        candidate = self._decision_candidates.get_by_governance_id(
            DecisionCandidateId(decision.decision_candidate_governance_id)
        )
        evaluation_reason_codes = tuple(reason.value for reason in candidate.outcome.reasons)

        trade_plan: TradePlan | None = None
        trade_plan_reason_codes: tuple[str, ...] = ()
        if decision.trade_plan_governance_id is not None:
            trade_plan = self._trade_plans.get_by_governance_id(
                TradePlanId(decision.trade_plan_governance_id)
            )
            trade_plan_reason_codes = tuple(reason.value for reason in trade_plan.reasons)

        position_plan_status: str | None = None
        position_plan_reason_codes: tuple[str, ...] = ()
        position_plan_reason_unavailable = False
        risk_evidence: BriefRiskEvidence | None = None

        if decision.position_plan_governance_id is not None:
            position_plan = self._position_plans.get_by_governance_id(
                PositionPlanId(decision.position_plan_governance_id)
            )
            position_plan_status = position_plan.status.value
            position_plan_reason_codes = tuple(reason.value for reason in position_plan.reasons)
            if position_plan_status == "APPROVED_POSITION_PLAN" and trade_plan is not None:
                risk_evidence = _risk_evidence_from(
                    trade_plan=trade_plan, position_plan=position_plan
                )
        elif session_is_completed and decision.trade_plan_decision == "APPROVED_PLAN":
            # MILESTONE-070's own orchestrator attempts position sizing for
            # every APPROVED_PLAN trade plan and only persists
            # `position_plan_governance_id` on the APPROVED branch (see
            # `run_daily_research_session.py`). On a COMPLETED session this
            # invariant guarantees a rejected position plan was built here
            # -- its own reason is genuinely unavailable, not fabricated.
            position_plan_status = "REJECTED_POSITION_PLAN"
            position_plan_reason_unavailable = True

        return FetchedInstrumentEvidence(
            evaluation_reason_codes=evaluation_reason_codes,
            trade_plan_reason_codes=trade_plan_reason_codes,
            position_plan_status=position_plan_status,
            position_plan_reason_codes=position_plan_reason_codes,
            position_plan_reason_unavailable=position_plan_reason_unavailable,
            risk_evidence=risk_evidence,
        )
