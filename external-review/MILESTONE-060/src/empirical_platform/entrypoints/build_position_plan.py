"""Real end-to-end deterministic position-sizing composition root."""

from __future__ import annotations

import json
import sys
from decimal import Decimal

from empirical_platform.application.command import CommandEntryPoint
from empirical_platform.entrypoints._composition import postgres_repository_runtime
from empirical_platform.identifiers.pairs import DomainIdentity
from empirical_platform.identifiers.types import PositionPlanId, TradePlanId
from empirical_platform.shared.config.settings import PostgreSQLConfigSnapshot
from empirical_platform.shared.identifiers import (
    RuntimeIdentifier,
    RuntimeIdentifierGenerator,
    UuidRuntimeIdentifierGenerator,
)
from empirical_platform.usecases.build_position_plan import (
    DEFAULT_SIZING_POLICY,
    BuildPositionPlanCommand,
    BuildPositionPlanHandler,
    PositionPlan,
    PositionSizingContext,
)


def run_build_position_plan(
    *,
    position_plan_governance_id: str,
    source_trade_plan_governance_id: str,
    source_trade_plan_runtime_id: str,
    account_equity: Decimal,
    risk_percent: Decimal,
    identifier_generator: RuntimeIdentifierGenerator | None = None,
    config: PostgreSQLConfigSnapshot | None = None,
) -> PositionPlan:
    """Build one deterministic PositionPlan end-to-end against real PostgreSQL."""
    resolved_generator = identifier_generator or UuidRuntimeIdentifierGenerator()
    with postgres_repository_runtime(config) as runtime:
        handler = BuildPositionPlanHandler(
            trade_plan_repository=runtime.trade_plans,
            position_plan_repository=runtime.position_plans,
        )
        entry_point = CommandEntryPoint(handler)
        command = BuildPositionPlanCommand(
            identity=DomainIdentity(
                governance_id=PositionPlanId(position_plan_governance_id),
                runtime_id=resolved_generator.generate(),
            ),
            source_trade_plan_identity=DomainIdentity(
                governance_id=TradePlanId(source_trade_plan_governance_id),
                runtime_id=RuntimeIdentifier(source_trade_plan_runtime_id),
            ),
            sizing_context=PositionSizingContext(
                account_equity=account_equity,
                risk_percent=risk_percent,
            ),
            policy=DEFAULT_SIZING_POLICY,
        )
        return entry_point(command)


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
    if len(sys.argv) != 6:
        raise SystemExit(
            "usage: empirical-platform-build-position-plan "
            "<position_plan_governance_id> <source_trade_plan_governance_id> "
            "<source_trade_plan_runtime_id> <account_equity> <risk_percent>"
        )
    plan = run_build_position_plan(
        position_plan_governance_id=sys.argv[1],
        source_trade_plan_governance_id=sys.argv[2],
        source_trade_plan_runtime_id=sys.argv[3],
        account_equity=Decimal(sys.argv[4]),
        risk_percent=Decimal(sys.argv[5]),
    )
    print(json.dumps(_plan_payload(plan), sort_keys=True))


if __name__ == "__main__":
    main()
