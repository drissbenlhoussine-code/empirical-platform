"""Build a risk-gated trade plan from an already-persisted, authoritative
M057 DecisionCandidate and M058 TradingOpportunityScan.

Concrete command and handler. MILESTONE-059.

Loads BOTH the source scan and the source DecisionCandidate from their
authoritative persisted repositories by identity alone -- never trusts
caller-supplied measurements, decision, or scan/strategy/ranking metadata
(see MILESTONE_059 scope Section 15). The provenance check (does the
candidate genuinely belong to the claimed scan) and the full risk-gate
pipeline both live in the pure `decision_candidate.trade_plan.build_trade_plan()`
function (M059); this handler's own job is only to load the two
authoritative sources and persist the result -- composing exactly one
aggregate mutation (`TradePlanRepository.add()`), matching the established
one-aggregate-mutation-per-command discipline.
"""

from __future__ import annotations

from dataclasses import dataclass

from empirical_platform.decision_candidate.repository import DecisionCandidateRepository
from empirical_platform.decision_candidate.scan_repository import TradingOpportunityScanRepository
from empirical_platform.decision_candidate.trade_plan import (
    DEFAULT_RISK_POLICY as DEFAULT_RISK_POLICY,
)
from empirical_platform.decision_candidate.trade_plan import RiskPolicy as RiskPolicy
from empirical_platform.decision_candidate.trade_plan import TradePlan as TradePlan
from empirical_platform.decision_candidate.trade_plan import build_trade_plan
from empirical_platform.decision_candidate.trade_plan_repository import TradePlanRepository
from empirical_platform.identifiers.pairs import DomainIdentity
from empirical_platform.identifiers.types import (
    DecisionCandidateId,
    EvidencePackageId,
    TradePlanId,
    TradingOpportunityScanId,
)


@dataclass(frozen=True, slots=True)
class BuildTradePlanCommand:
    """Request to build one risk-gated trade plan, identified by the
    caller, from an already-persisted scan and DecisionCandidate.

    Carries only identities and the risk policy to apply -- no market
    measurements, no decision, no strategy/ranking metadata. All of that
    is loaded from the authoritative persisted sources by the handler,
    never accepted from the caller.
    """

    identity: DomainIdentity[TradePlanId]
    source_scan_identity: DomainIdentity[TradingOpportunityScanId]
    source_decision_candidate_identity: DomainIdentity[DecisionCandidateId]
    target_evidence_package_id: EvidencePackageId
    policy: RiskPolicy = DEFAULT_RISK_POLICY


class BuildTradePlanHandler:
    """Loads the authoritative source scan and DecisionCandidate, builds
    the risk-gated plan, and persists it for one `BuildTradePlanCommand`."""

    __slots__ = (
        "_decision_candidate_repository",
        "_trading_opportunity_scan_repository",
        "_trade_plan_repository",
    )

    def __init__(
        self,
        *,
        decision_candidate_repository: DecisionCandidateRepository,
        trading_opportunity_scan_repository: TradingOpportunityScanRepository,
        trade_plan_repository: TradePlanRepository,
    ) -> None:
        self._decision_candidate_repository = decision_candidate_repository
        self._trading_opportunity_scan_repository = trading_opportunity_scan_repository
        self._trade_plan_repository = trade_plan_repository

    def handle(self, command: BuildTradePlanCommand) -> TradePlan:
        scan = self._trading_opportunity_scan_repository.get(command.source_scan_identity)
        candidate = self._decision_candidate_repository.get(
            command.source_decision_candidate_identity
        )
        plan = build_trade_plan(
            identity=command.identity,
            scan=scan,
            candidate=candidate,
            target_evidence_package_id=command.target_evidence_package_id,
            policy=command.policy,
        )
        self._trade_plan_repository.add(plan)
        return plan
