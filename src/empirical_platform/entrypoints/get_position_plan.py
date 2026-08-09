"""Real end-to-end PositionPlan retrieval composition root."""

from __future__ import annotations

import json
import sys

from empirical_platform.application.query import QueryEntryPoint
from empirical_platform.entrypoints._composition import postgres_repository_runtime
from empirical_platform.identifiers.pairs import DomainIdentity
from empirical_platform.identifiers.types import PositionPlanId
from empirical_platform.shared.config.settings import PostgreSQLConfigSnapshot
from empirical_platform.shared.identifiers import RuntimeIdentifier
from empirical_platform.usecases.get_position_plan import (
    GetPositionPlanHandler,
    GetPositionPlanQuery,
    PositionPlan,
)


def run_get_position_plan(
    *,
    position_plan_governance_id: str,
    position_plan_runtime_id: str,
    config: PostgreSQLConfigSnapshot | None = None,
) -> PositionPlan:
    """Retrieve one PositionPlan end-to-end against real PostgreSQL."""
    with postgres_repository_runtime(config) as runtime:
        handler = GetPositionPlanHandler(position_plan_repository=runtime.position_plans)
        entry_point = QueryEntryPoint(handler)
        return entry_point(
            GetPositionPlanQuery(
                identity=DomainIdentity(
                    governance_id=PositionPlanId(position_plan_governance_id),
                    runtime_id=RuntimeIdentifier(position_plan_runtime_id),
                )
            )
        )


def _plan_payload(plan: PositionPlan) -> dict[str, object]:
    sizing = plan.sizing
    return {
        "governance_id": str(plan.identity.governance_id),
        "runtime_id": str(plan.identity.runtime_id),
        "source_trade_plan_id": str(plan.source_trade_plan_id),
        "instrument": str(plan.instrument),
        "policy_id": plan.policy_id,
        "policy_version": plan.policy_version,
        "policy_maximum_risk_percent": str(plan.policy_maximum_risk_percent),
        "policy_maximum_notional_percent": str(plan.policy_maximum_notional_percent),
        "policy_allow_fractional_shares": plan.policy_allow_fractional_shares,
        "supplied_account_equity": str(plan.supplied_account_equity),
        "supplied_risk_percent": str(plan.supplied_risk_percent),
        "status": plan.status.value,
        "reasons": [reason.value for reason in plan.reasons],
        "sizing": (
            {
                "entry_price": str(sizing.entry_price),
                "stop_price": str(sizing.stop_price),
                "risk_per_unit": str(sizing.risk_per_unit),
                "allowed_risk_amount": str(sizing.allowed_risk_amount),
                "maximum_notional": str(sizing.maximum_notional),
                "risk_based_quantity": sizing.risk_based_quantity,
                "capital_based_quantity": sizing.capital_based_quantity,
                "quantity": sizing.quantity,
                "position_notional": str(sizing.position_notional),
                "actual_risk": str(sizing.actual_risk),
            }
            if sizing is not None
            else None
        ),
    }


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit("usage: empirical-platform-get-position-plan <governance_id> <runtime_id>")
    plan = run_get_position_plan(
        position_plan_governance_id=sys.argv[1],
        position_plan_runtime_id=sys.argv[2],
    )
    print(json.dumps(_plan_payload(plan), sort_keys=True))


if __name__ == "__main__":
    main()
