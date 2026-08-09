"""Real end-to-end risk-gated trade-plan composition root.

Composes the MILESTONE-059 vertical slice through the shared MILESTONE-053
resource-lifecycle helper. A real caller identifies an already-persisted
M058 `TradingOpportunityScan` and an already-persisted M057
`DecisionCandidate` by identity alone -- this entrypoint accepts no market
measurements, no decision, no strategy/ranking metadata -- and receives the
structured, persisted risk-gate decision.
"""

from __future__ import annotations

import json
import sys

from empirical_platform.application.command import CommandEntryPoint
from empirical_platform.entrypoints._composition import postgres_repository_runtime
from empirical_platform.identifiers.pairs import DomainIdentity
from empirical_platform.identifiers.types import (
    DecisionCandidateId,
    EvidencePackageId,
    TradePlanId,
    TradingOpportunityScanId,
)
from empirical_platform.shared.config.settings import PostgreSQLConfigSnapshot
from empirical_platform.shared.identifiers import (
    RuntimeIdentifier,
    RuntimeIdentifierGenerator,
    UuidRuntimeIdentifierGenerator,
)
from empirical_platform.usecases.build_trade_plan import (
    DEFAULT_RISK_POLICY,
    BuildTradePlanCommand,
    BuildTradePlanHandler,
    TradePlan,
)


def run_build_trade_plan(
    *,
    plan_governance_id: str,
    source_scan_governance_id: str,
    source_scan_runtime_id: str,
    source_decision_candidate_governance_id: str,
    source_decision_candidate_runtime_id: str,
    target_evidence_package_governance_id: str,
    identifier_generator: RuntimeIdentifierGenerator | None = None,
    config: PostgreSQLConfigSnapshot | None = None,
) -> TradePlan:
    """Build one risk-gated trade plan, end-to-end, against real PostgreSQL."""
    resolved_generator = identifier_generator or UuidRuntimeIdentifierGenerator()
    with postgres_repository_runtime(config) as runtime:
        handler = BuildTradePlanHandler(
            decision_candidate_repository=runtime.decision_candidates,
            trading_opportunity_scan_repository=runtime.trading_opportunity_scans,
            trade_plan_repository=runtime.trade_plans,
        )
        entry_point = CommandEntryPoint(handler)
        plan_identity = DomainIdentity(
            governance_id=TradePlanId(plan_governance_id),
            runtime_id=resolved_generator.generate(),
        )
        command = BuildTradePlanCommand(
            identity=plan_identity,
            source_scan_identity=DomainIdentity(
                governance_id=TradingOpportunityScanId(source_scan_governance_id),
                runtime_id=RuntimeIdentifier(source_scan_runtime_id),
            ),
            source_decision_candidate_identity=DomainIdentity(
                governance_id=DecisionCandidateId(source_decision_candidate_governance_id),
                runtime_id=RuntimeIdentifier(source_decision_candidate_runtime_id),
            ),
            target_evidence_package_id=EvidencePackageId(target_evidence_package_governance_id),
            policy=DEFAULT_RISK_POLICY,
        )
        return entry_point(command)


def _plan_payload(plan: TradePlan) -> dict[str, object]:
    """Return a plain, JSON-serializable representation of one TradePlan."""
    geometry = plan.geometry
    return {
        "governance_id": str(plan.identity.governance_id),
        "runtime_id": str(plan.identity.runtime_id),
        "source_scan_id": str(plan.source_scan_id),
        "source_decision_candidate_id": str(plan.source_decision_candidate_id),
        "target_evidence_package_id": str(plan.target_evidence_package_id),
        "instrument": str(plan.instrument),
        "evaluation_cutoff": plan.evaluation_cutoff.isoformat(),
        "strategy_id": plan.strategy_id,
        "strategy_version": plan.strategy_version,
        "ranking_model_id": plan.ranking_model_id,
        "ranking_model_version": plan.ranking_model_version,
        "policy_id": plan.policy_id,
        "policy_version": plan.policy_version,
        "status": plan.status.value,
        "reasons": [reason.value for reason in plan.reasons],
        "geometry": (
            {
                "entry_price": str(geometry.entry_price),
                "stop_price": str(geometry.stop_price),
                "target_price": str(geometry.target_price),
                "risk_per_unit": str(geometry.risk_per_unit),
                "reward_per_unit": str(geometry.reward_per_unit),
                "reward_risk_ratio": str(geometry.reward_risk_ratio),
            }
            if geometry is not None
            else None
        ),
    }


def main() -> None:
    """Build one risk-gated trade plan from CLI arguments, and print the result."""
    if len(sys.argv) != 7:
        raise SystemExit(
            "usage: empirical-platform-build-trade-plan "
            "<plan_governance_id> <source_scan_governance_id> <source_scan_runtime_id> "
            "<source_decision_candidate_governance_id> <source_decision_candidate_runtime_id> "
            "<target_evidence_package_governance_id>"
        )
    plan = run_build_trade_plan(
        plan_governance_id=sys.argv[1],
        source_scan_governance_id=sys.argv[2],
        source_scan_runtime_id=sys.argv[3],
        source_decision_candidate_governance_id=sys.argv[4],
        source_decision_candidate_runtime_id=sys.argv[5],
        target_evidence_package_governance_id=sys.argv[6],
    )
    print(json.dumps(_plan_payload(plan), sort_keys=True))


if __name__ == "__main__":
    main()
