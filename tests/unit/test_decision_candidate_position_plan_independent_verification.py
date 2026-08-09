"""Independent mathematical verification for MILESTONE-060 PositionPlan."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import ROUND_FLOOR, Decimal

import pytest

from empirical_platform.decision_candidate.market_data import Instrument
from empirical_platform.decision_candidate.position_plan import (
    DEFAULT_SIZING_POLICY,
    PositionPlanRejectionReason,
    PositionPlanStatus,
    PositionSizingContext,
    build_position_plan,
)
from empirical_platform.decision_candidate.trade_plan import (
    TradePlan,
    TradePlanGeometry,
    TradePlanRejectionReason,
    TradePlanStatus,
)
from empirical_platform.identifiers.pairs import DomainIdentity
from empirical_platform.identifiers.types import (
    DecisionCandidateId,
    EvidencePackageId,
    PositionPlanId,
    TradePlanId,
    TradingOpportunityScanId,
)
from empirical_platform.shared.identifiers import RuntimeIdentifier


def _trade_plan(
    *,
    status: TradePlanStatus = TradePlanStatus.APPROVED_PLAN,
    entry_price: str = "100.00",
    stop_price: str = "95.00",
    target_price: str = "112.00",
) -> TradePlan:
    geometry: TradePlanGeometry | None = None
    if status is TradePlanStatus.APPROVED_PLAN:
        entry = Decimal(entry_price)
        stop = Decimal(stop_price)
        target = Decimal(target_price)
        geometry = TradePlanGeometry(
            entry_price=entry,
            stop_price=stop,
            target_price=target,
            risk_per_unit=entry - stop,
            reward_per_unit=target - entry,
            reward_risk_ratio=(target - entry) / (entry - stop),
        )
    return TradePlan(
        identity=DomainIdentity(
            governance_id=TradePlanId("PLAN-0001"),
            runtime_id=RuntimeIdentifier("30000001-0000-4000-8000-000000000001"),
        ),
        source_scan_id=TradingOpportunityScanId("SCAN-0001"),
        source_decision_candidate_id=DecisionCandidateId("DCAND-0001"),
        target_evidence_package_id=EvidencePackageId("EVID-0001"),
        instrument=Instrument("AAPL"),
        evaluation_cutoff=datetime(2026, 8, 9, 12, 0, tzinfo=UTC),
        strategy_id="strategy",
        strategy_version="1",
        ranking_model_id="ranking",
        ranking_model_version="1",
        policy_id="REFERENCE_HIGH_BREAKOUT_RISK_GATE",
        policy_version="1",
        status=status,
        geometry=geometry,
        reasons=()
        if status is TradePlanStatus.APPROVED_PLAN
        else (TradePlanRejectionReason.SOURCE_NOT_LONG_CANDIDATE,),
    )


def _independently_size(
    *,
    trade_plan: TradePlan,
    account_equity: Decimal,
    risk_percent: Decimal,
) -> tuple[PositionPlanStatus, PositionPlanRejectionReason | None, dict[str, Decimal | int] | None]:
    if trade_plan.status is not TradePlanStatus.APPROVED_PLAN:
        return (
            PositionPlanStatus.REJECTED_POSITION_PLAN,
            PositionPlanRejectionReason.SOURCE_PLAN_NOT_APPROVED,
            None,
        )
    if account_equity <= 0:
        return (
            PositionPlanStatus.REJECTED_POSITION_PLAN,
            PositionPlanRejectionReason.INVALID_EQUITY,
            None,
        )
    if risk_percent <= 0:
        return (
            PositionPlanStatus.REJECTED_POSITION_PLAN,
            PositionPlanRejectionReason.INVALID_RISK_BUDGET,
            None,
        )
    if risk_percent > DEFAULT_SIZING_POLICY.maximum_risk_percent:
        return (
            PositionPlanStatus.REJECTED_POSITION_PLAN,
            PositionPlanRejectionReason.POLICY_VIOLATION,
            None,
        )

    geometry = trade_plan.geometry
    assert geometry is not None
    allowed_risk_amount = account_equity * risk_percent
    maximum_notional = account_equity * DEFAULT_SIZING_POLICY.maximum_notional_percent
    risk_based_quantity = int(
        (allowed_risk_amount / geometry.risk_per_unit).to_integral_value(rounding=ROUND_FLOOR)
    )
    capital_based_quantity = int(
        (maximum_notional / geometry.entry_price).to_integral_value(rounding=ROUND_FLOOR)
    )

    if risk_based_quantity <= 0:
        return (
            PositionPlanStatus.REJECTED_POSITION_PLAN,
            PositionPlanRejectionReason.ZERO_POSITION_SIZE,
            {
                "allowed_risk_amount": allowed_risk_amount,
                "maximum_notional": maximum_notional,
                "risk_based_quantity": risk_based_quantity,
                "capital_based_quantity": capital_based_quantity,
                "quantity": 0,
                "position_notional": Decimal("0"),
                "actual_risk": Decimal("0"),
            },
        )
    if capital_based_quantity <= 0:
        return (
            PositionPlanStatus.REJECTED_POSITION_PLAN,
            PositionPlanRejectionReason.CAPITAL_LIMIT_EXCEEDED,
            {
                "allowed_risk_amount": allowed_risk_amount,
                "maximum_notional": maximum_notional,
                "risk_based_quantity": risk_based_quantity,
                "capital_based_quantity": capital_based_quantity,
                "quantity": 0,
                "position_notional": Decimal("0"),
                "actual_risk": Decimal("0"),
            },
        )
    quantity = min(risk_based_quantity, capital_based_quantity)
    return (
        PositionPlanStatus.APPROVED_POSITION_PLAN,
        None,
        {
            "allowed_risk_amount": allowed_risk_amount,
            "maximum_notional": maximum_notional,
            "risk_based_quantity": risk_based_quantity,
            "capital_based_quantity": capital_based_quantity,
            "quantity": quantity,
            "position_notional": Decimal(quantity) * geometry.entry_price,
            "actual_risk": Decimal(quantity) * geometry.risk_per_unit,
        },
    )


@pytest.mark.parametrize(
    ("status", "entry", "stop", "target", "equity", "risk_percent"),
    [
        (
            TradePlanStatus.APPROVED_PLAN,
            "100.00",
            "95.00",
            "112.00",
            Decimal("10000"),
            Decimal("0.02"),
        ),
        (
            TradePlanStatus.APPROVED_PLAN,
            "1000.00",
            "999.50",
            "1005.00",
            Decimal("1000"),
            Decimal("0.01"),
        ),
        (
            TradePlanStatus.APPROVED_PLAN,
            "100.00",
            "95.00",
            "112.00",
            Decimal("100"),
            Decimal("0.01"),
        ),
        (
            TradePlanStatus.REJECTED_PLAN,
            "100.00",
            "95.00",
            "112.00",
            Decimal("10000"),
            Decimal("0.01"),
        ),
    ],
)
def test_independent_math_matches_production(
    status: TradePlanStatus,
    entry: str,
    stop: str,
    target: str,
    equity: Decimal,
    risk_percent: Decimal,
) -> None:
    trade_plan = _trade_plan(
        status=status,
        entry_price=entry,
        stop_price=stop,
        target_price=target,
    )
    production = build_position_plan(
        identity=DomainIdentity(
            governance_id=PositionPlanId("POS-0001"),
            runtime_id=RuntimeIdentifier("30000002-0000-4000-8000-000000000001"),
        ),
        trade_plan=trade_plan,
        sizing_context=PositionSizingContext(account_equity=equity, risk_percent=risk_percent),
    )
    expected_status, expected_reason, expected_sizing = _independently_size(
        trade_plan=trade_plan,
        account_equity=equity,
        risk_percent=risk_percent,
    )

    assert production.status is expected_status
    if expected_reason is None:
        assert production.reasons == ()
    else:
        assert production.reasons == (expected_reason,)
    if expected_sizing is None:
        assert production.sizing is None
    else:
        assert production.sizing is not None
        assert production.sizing.allowed_risk_amount == expected_sizing["allowed_risk_amount"]
        assert production.sizing.maximum_notional == expected_sizing["maximum_notional"]
        assert production.sizing.risk_based_quantity == expected_sizing["risk_based_quantity"]
        assert production.sizing.capital_based_quantity == expected_sizing["capital_based_quantity"]
        assert production.sizing.quantity == expected_sizing["quantity"]
        assert production.sizing.position_notional == expected_sizing["position_notional"]
        assert production.sizing.actual_risk == expected_sizing["actual_risk"]
