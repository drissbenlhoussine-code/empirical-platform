"""MILESTONE-060 unit tests for pure PositionPlan sizing and capital gate."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from empirical_platform.decision_candidate.market_data import Instrument
from empirical_platform.decision_candidate.position_plan import (
    DEFAULT_SIZING_POLICY,
    PositionPlan,
    PositionPlanRejectionReason,
    PositionPlanStatus,
    PositionSizingContext,
    SizingPolicy,
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

_EVID = EvidencePackageId("EVID-0001")


def _position_identity(n: int = 1) -> DomainIdentity[PositionPlanId]:
    return DomainIdentity(
        governance_id=PositionPlanId(f"POS-{n:04d}"),
        runtime_id=RuntimeIdentifier(f"2000000{n}-0000-4000-8000-000000000001"),
    )


def _trade_identity(n: int = 1) -> DomainIdentity[TradePlanId]:
    return DomainIdentity(
        governance_id=TradePlanId(f"PLAN-{n:04d}"),
        runtime_id=RuntimeIdentifier(f"1000000{n}-0000-4000-8000-000000000001"),
    )


def _geometry(
    *,
    entry_price: str = "100.00",
    stop_price: str = "95.00",
    target_price: str = "112.00",
) -> TradePlanGeometry:
    entry = Decimal(entry_price)
    stop = Decimal(stop_price)
    target = Decimal(target_price)
    return TradePlanGeometry(
        entry_price=entry,
        stop_price=stop,
        target_price=target,
        risk_per_unit=entry - stop,
        reward_per_unit=target - entry,
        reward_risk_ratio=(target - entry) / (entry - stop),
    )


def _trade_plan(
    *,
    status: TradePlanStatus = TradePlanStatus.APPROVED_PLAN,
    geometry: TradePlanGeometry | None = None,
) -> TradePlan:
    resolved_geometry = geometry if geometry is not None else _geometry()
    return TradePlan(
        identity=_trade_identity(),
        source_scan_id=TradingOpportunityScanId("SCAN-0001"),
        source_decision_candidate_id=DecisionCandidateId("DCAND-0001"),
        target_evidence_package_id=_EVID,
        instrument=Instrument("AAPL"),
        evaluation_cutoff=datetime(2026, 8, 9, 12, 0, tzinfo=UTC),
        strategy_id="strategy",
        strategy_version="1",
        ranking_model_id="ranking",
        ranking_model_version="1",
        policy_id="REFERENCE_HIGH_BREAKOUT_RISK_GATE",
        policy_version="1",
        status=status,
        geometry=resolved_geometry if status is TradePlanStatus.APPROVED_PLAN else None,
        reasons=()
        if status is TradePlanStatus.APPROVED_PLAN
        else (TradePlanRejectionReason.SOURCE_NOT_LONG_CANDIDATE,),
    )


def _rejected_trade_plan() -> TradePlan:
    return TradePlan(
        identity=_trade_identity(2),
        source_scan_id=TradingOpportunityScanId("SCAN-0001"),
        source_decision_candidate_id=DecisionCandidateId("DCAND-0001"),
        target_evidence_package_id=_EVID,
        instrument=Instrument("AAPL"),
        evaluation_cutoff=datetime(2026, 8, 9, 12, 0, tzinfo=UTC),
        strategy_id="strategy",
        strategy_version="1",
        ranking_model_id="ranking",
        ranking_model_version="1",
        policy_id="REFERENCE_HIGH_BREAKOUT_RISK_GATE",
        policy_version="1",
        status=TradePlanStatus.REJECTED_PLAN,
        geometry=None,
        reasons=(TradePlanRejectionReason.SOURCE_NOT_LONG_CANDIDATE,),
    )


def test_sizing_policy_rejects_fractional_shares_in_v1() -> None:
    with pytest.raises(ValueError, match="fractional shares are not supported"):
        SizingPolicy(allow_fractional_shares=True)


def test_position_sizing_context_rejects_non_decimal_fields() -> None:
    with pytest.raises(TypeError, match="account_equity must be a Decimal"):
        PositionSizingContext(account_equity=1000, risk_percent=Decimal("0.01"))  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="risk_percent must be a Decimal"):
        PositionSizingContext(account_equity=Decimal("1000"), risk_percent=0.01)  # type: ignore[arg-type]


def test_position_plan_rejects_approved_status_without_sizing() -> None:
    with pytest.raises(ValueError, match="must carry sizing"):
        PositionPlan(
            identity=_position_identity(),
            source_trade_plan_id=TradePlanId("PLAN-0001"),
            instrument=Instrument("AAPL"),
            policy_id="policy",
            policy_version="1",
            policy_maximum_risk_percent=Decimal("0.02"),
            policy_maximum_notional_percent=Decimal("0.25"),
            policy_allow_fractional_shares=False,
            supplied_account_equity=Decimal("10000"),
            supplied_risk_percent=Decimal("0.01"),
            status=PositionPlanStatus.APPROVED_POSITION_PLAN,
            sizing=None,
            reasons=(),
        )


def test_build_position_plan_approves_and_caps_by_capital_limit_when_needed() -> None:
    plan = build_position_plan(
        identity=_position_identity(),
        trade_plan=_trade_plan(),
        sizing_context=PositionSizingContext(
            account_equity=Decimal("10000"),
            risk_percent=Decimal("0.02"),
        ),
    )

    assert plan.status is PositionPlanStatus.APPROVED_POSITION_PLAN
    assert plan.reasons == ()
    assert plan.sizing is not None
    assert plan.sizing.allowed_risk_amount == Decimal("200.0000")
    assert plan.sizing.maximum_notional == Decimal("2500.0000")
    assert plan.sizing.risk_based_quantity == 40
    assert plan.sizing.capital_based_quantity == 25
    assert plan.sizing.quantity == 25
    assert plan.sizing.position_notional == Decimal("2500.00")
    assert plan.sizing.actual_risk == Decimal("125.00")
    assert plan.policy_maximum_risk_percent == DEFAULT_SIZING_POLICY.maximum_risk_percent
    assert plan.policy_maximum_notional_percent == DEFAULT_SIZING_POLICY.maximum_notional_percent


def test_build_position_plan_rejects_source_trade_plan_not_approved() -> None:
    plan = build_position_plan(
        identity=_position_identity(),
        trade_plan=_rejected_trade_plan(),
        sizing_context=PositionSizingContext(
            account_equity=Decimal("10000"),
            risk_percent=Decimal("0.01"),
        ),
    )

    assert plan.status is PositionPlanStatus.REJECTED_POSITION_PLAN
    assert plan.reasons == (PositionPlanRejectionReason.SOURCE_PLAN_NOT_APPROVED,)
    assert plan.sizing is None


@pytest.mark.parametrize(
    ("equity", "risk_percent", "reason"),
    [
        (Decimal("0"), Decimal("0.01"), PositionPlanRejectionReason.INVALID_EQUITY),
        (Decimal("-1"), Decimal("0.01"), PositionPlanRejectionReason.INVALID_EQUITY),
        (Decimal("1000"), Decimal("0"), PositionPlanRejectionReason.INVALID_RISK_BUDGET),
        (Decimal("1000"), Decimal("-0.01"), PositionPlanRejectionReason.INVALID_RISK_BUDGET),
    ],
)
def test_build_position_plan_rejects_invalid_context_values(
    equity: Decimal,
    risk_percent: Decimal,
    reason: PositionPlanRejectionReason,
) -> None:
    plan = build_position_plan(
        identity=_position_identity(),
        trade_plan=_trade_plan(),
        sizing_context=PositionSizingContext(account_equity=equity, risk_percent=risk_percent),
    )
    assert plan.status is PositionPlanStatus.REJECTED_POSITION_PLAN
    assert plan.reasons == (reason,)
    assert plan.sizing is None


def test_build_position_plan_rejects_risk_percent_above_policy_maximum() -> None:
    plan = build_position_plan(
        identity=_position_identity(),
        trade_plan=_trade_plan(),
        sizing_context=PositionSizingContext(
            account_equity=Decimal("10000"),
            risk_percent=Decimal("0.020000000000001"),
        ),
    )
    assert plan.status is PositionPlanStatus.REJECTED_POSITION_PLAN
    assert plan.reasons == (PositionPlanRejectionReason.POLICY_VIOLATION,)
    assert plan.sizing is None


def test_build_position_plan_boundary_exactly_at_policy_risk_maximum_is_allowed() -> None:
    plan = build_position_plan(
        identity=_position_identity(),
        trade_plan=_trade_plan(),
        sizing_context=PositionSizingContext(
            account_equity=Decimal("10000"),
            risk_percent=DEFAULT_SIZING_POLICY.maximum_risk_percent,
        ),
    )
    assert plan.status is PositionPlanStatus.APPROVED_POSITION_PLAN


def test_build_position_plan_rejects_zero_size_when_budget_below_one_share_risk() -> None:
    plan = build_position_plan(
        identity=_position_identity(),
        trade_plan=_trade_plan(),
        sizing_context=PositionSizingContext(
            account_equity=Decimal("100"),
            risk_percent=Decimal("0.01"),
        ),
    )
    assert plan.status is PositionPlanStatus.REJECTED_POSITION_PLAN
    assert plan.reasons == (PositionPlanRejectionReason.ZERO_POSITION_SIZE,)
    assert plan.sizing is not None
    assert plan.sizing.quantity == 0
    assert plan.sizing.risk_based_quantity == 0


def test_build_position_plan_rejects_capital_limit_exceeded_when_one_share_is_too_expensive() -> (
    None
):
    geometry = _geometry(entry_price="1000.00", stop_price="999.50", target_price="1005.00")
    plan = build_position_plan(
        identity=_position_identity(),
        trade_plan=_trade_plan(geometry=geometry),
        sizing_context=PositionSizingContext(
            account_equity=Decimal("1000"),
            risk_percent=Decimal("0.01"),
        ),
    )
    assert plan.status is PositionPlanStatus.REJECTED_POSITION_PLAN
    assert plan.reasons == (PositionPlanRejectionReason.CAPITAL_LIMIT_EXCEEDED,)
    assert plan.sizing is not None
    assert plan.sizing.risk_based_quantity == 20
    assert plan.sizing.capital_based_quantity == 0
    assert plan.sizing.quantity == 0


def test_build_position_plan_handles_repeating_decimal_division_deterministically() -> None:
    geometry = _geometry(entry_price="100.00", stop_price="99.32", target_price="102.00")
    plan = build_position_plan(
        identity=_position_identity(),
        trade_plan=_trade_plan(geometry=geometry),
        sizing_context=PositionSizingContext(
            account_equity=Decimal("10000"),
            risk_percent=Decimal("0.01"),
        ),
    )
    assert plan.sizing is not None
    assert plan.sizing.risk_based_quantity == 147
    assert plan.sizing.quantity == 25


def test_build_position_plan_is_deterministic_for_identical_inputs() -> None:
    first = build_position_plan(
        identity=_position_identity(1),
        trade_plan=_trade_plan(),
        sizing_context=PositionSizingContext(
            account_equity=Decimal("10000"),
            risk_percent=Decimal("0.01"),
        ),
    )
    second = build_position_plan(
        identity=_position_identity(2),
        trade_plan=_trade_plan(),
        sizing_context=PositionSizingContext(
            account_equity=Decimal("10000"),
            risk_percent=Decimal("0.01"),
        ),
    )
    assert first.source_trade_plan_id == second.source_trade_plan_id
    assert first.status == second.status
    assert first.sizing == second.sizing
