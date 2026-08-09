"""Real end-to-end TradePlan retrieval composition root.

Composes the MILESTONE-059 retrieval vertical slice through the shared
MILESTONE-053 resource-lifecycle helper.
"""

from __future__ import annotations

import json
import sys

from empirical_platform.application.query import QueryEntryPoint
from empirical_platform.entrypoints._composition import postgres_repository_runtime
from empirical_platform.identifiers.pairs import DomainIdentity
from empirical_platform.identifiers.types import TradePlanId
from empirical_platform.shared.config.settings import PostgreSQLConfigSnapshot
from empirical_platform.shared.identifiers import RuntimeIdentifier
from empirical_platform.usecases.get_trade_plan import (
    GetTradePlanHandler,
    GetTradePlanQuery,
    TradePlan,
)


def run_get_trade_plan(
    *,
    plan_governance_id: str,
    plan_runtime_id: str,
    config: PostgreSQLConfigSnapshot | None = None,
) -> TradePlan:
    """Retrieve one TradePlan end-to-end against real PostgreSQL."""
    with postgres_repository_runtime(config) as runtime:
        handler = GetTradePlanHandler(trade_plan_repository=runtime.trade_plans)
        entry_point = QueryEntryPoint(handler)
        identity = DomainIdentity(
            governance_id=TradePlanId(plan_governance_id),
            runtime_id=RuntimeIdentifier(plan_runtime_id),
        )
        return entry_point(GetTradePlanQuery(identity=identity))


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
    """Retrieve one TradePlan by identity, supplied as two CLI arguments,
    and print it."""
    if len(sys.argv) != 3:
        raise SystemExit("usage: empirical-platform-get-trade-plan <governance_id> <runtime_id>")
    plan = run_get_trade_plan(
        plan_governance_id=sys.argv[1],
        plan_runtime_id=sys.argv[2],
    )
    print(json.dumps(_plan_payload(plan), sort_keys=True))


if __name__ == "__main__":
    main()
