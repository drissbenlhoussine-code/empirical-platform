"""MILESTONE-059 unit tests for the risk-gated trade-plan domain: risk
policy validation, geometry validation (including adversarial hostile
cases), and the full `build_trade_plan()` gate pipeline. Pure, no
PostgreSQL.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from empirical_platform.decision_candidate.candidate import DecisionCandidate
from empirical_platform.decision_candidate.market_data import BarInterval, Instrument
from empirical_platform.decision_candidate.scan import TradingOpportunityScan, build_scan
from empirical_platform.decision_candidate.strategy import (
    EvaluationMeasurements,
    EvaluationOutcome,
    EvaluationReasonCode,
    TradingDecision,
)
from empirical_platform.decision_candidate.trade_plan import (
    RISK_POLICY_ID,
    RISK_POLICY_VERSION,
    RiskPolicy,
    TradePlan,
    TradePlanGeometry,
    TradePlanRejectionReason,
    TradePlanStatus,
    build_geometry,
    build_trade_plan,
    compute_stop_price,
    compute_target_price,
)
from empirical_platform.identifiers.pairs import DomainIdentity
from empirical_platform.identifiers.types import (
    DecisionCandidateId,
    EvidencePackageId,
    TradePlanId,
    TradingOpportunityScanId,
)
from empirical_platform.shared.identifiers import RuntimeIdentifier

_CUTOFF = datetime(2026, 8, 10, 13, 45, 0, tzinfo=UTC)
_EVID = EvidencePackageId("EVID-0001")
_DEFAULT_POLICY = RiskPolicy()


def _measurements(
    *, close: str, volume: int = 1500, reference_high: str = "100.50"
) -> EvaluationMeasurements:
    return EvaluationMeasurements(
        current_close=Decimal(close),
        current_volume=volume,
        reference_high=Decimal(reference_high),
        reference_average_volume=Decimal("1012"),
    )


def _candidate(
    *,
    symbol: str,
    decision: TradingDecision,
    measurements: EvaluationMeasurements,
    n: int = 1,
) -> DecisionCandidate:
    reasons = (
        (
            EvaluationReasonCode.PRICE_ABOVE_REFERENCE_HIGH,
            EvaluationReasonCode.VOLUME_ABOVE_REFERENCE_AVERAGE,
        )
        if decision is TradingDecision.LONG_CANDIDATE
        else (
            EvaluationReasonCode.PRICE_NOT_ABOVE_REFERENCE_HIGH,
            EvaluationReasonCode.VOLUME_NOT_ABOVE_REFERENCE_AVERAGE,
        )
    )
    outcome = EvaluationOutcome(decision=decision, reasons=reasons, measurements=measurements)
    return DecisionCandidate(
        identity=DomainIdentity(
            governance_id=DecisionCandidateId(f"DCAND-{n:04d}"),
            runtime_id=RuntimeIdentifier(f"a000000{n}-0000-4000-8000-000000000001"),
        ),
        target_evidence_package_id=_EVID,
        instrument=Instrument(symbol),
        interval=BarInterval.ONE_MINUTE,
        evaluation_timestamp=_CUTOFF,
        strategy_id="PRIOR_WINDOW_BREAKOUT_VOLUME_CONFIRMATION",
        strategy_version="1",
        reference_window_size=5,
        outcome=outcome,
    )


def _scan(*, candidates: list[DecisionCandidate], n: int = 1) -> TradingOpportunityScan:
    universe = [
        (candidate.instrument, candidate.identity.governance_id, candidate.outcome)
        for candidate in candidates
    ]
    return build_scan(
        identity=DomainIdentity(
            governance_id=TradingOpportunityScanId(f"SCAN-{n:04d}"),
            runtime_id=RuntimeIdentifier(f"b000000{n}-0000-4000-8000-000000000001"),
        ),
        target_evidence_package_id=_EVID,
        strategy_id="PRIOR_WINDOW_BREAKOUT_VOLUME_CONFIRMATION",
        strategy_version="1",
        evaluation_cutoff=_CUTOFF,
        universe=universe,
    )


def _plan_identity(n: int = 1) -> DomainIdentity[TradePlanId]:
    return DomainIdentity(
        governance_id=TradePlanId(f"PLAN-{n:04d}"),
        runtime_id=RuntimeIdentifier(f"c000000{n}-0000-4000-8000-000000000001"),
    )


# --- RiskPolicy -------------------------------------------------------------


def test_risk_policy_identity_constants() -> None:
    assert RISK_POLICY_ID == "REFERENCE_HIGH_BREAKOUT_RISK_GATE"
    assert RISK_POLICY_VERSION == "1"


def test_default_risk_policy_uses_identity_constants() -> None:
    policy = RiskPolicy()
    assert policy.policy_id == RISK_POLICY_ID
    assert policy.policy_version == RISK_POLICY_VERSION


def test_risk_policy_rejects_non_positive_target_projection_percent() -> None:
    with pytest.raises(ValueError, match="target_projection_percent"):
        RiskPolicy(target_projection_percent=Decimal("0"))


def test_risk_policy_rejects_non_positive_minimum_reward_risk_ratio() -> None:
    with pytest.raises(ValueError, match="minimum_reward_risk_ratio"):
        RiskPolicy(minimum_reward_risk_ratio=Decimal("-1"))


# --- compute_stop_price / compute_target_price ------------------------------


def test_compute_stop_price_equals_reference_high() -> None:
    assert compute_stop_price(Decimal("100.50")) == Decimal("100.50")


def test_compute_target_price_applies_projection_percent() -> None:
    target = compute_target_price(
        Decimal("100.50"), RiskPolicy(target_projection_percent=Decimal("0.02"))
    )
    assert target == Decimal("100.50") * Decimal("1.02")


# --- build_geometry (adversarial) -------------------------------------------


def test_build_geometry_rejects_stop_equal_to_entry() -> None:
    result = build_geometry(
        entry_price=Decimal("100.00"), stop_price=Decimal("100.00"), target_price=Decimal("110.00")
    )
    assert result is TradePlanRejectionReason.INVALID_STOP_GEOMETRY


def test_build_geometry_rejects_stop_above_entry() -> None:
    result = build_geometry(
        entry_price=Decimal("100.00"), stop_price=Decimal("105.00"), target_price=Decimal("110.00")
    )
    assert result is TradePlanRejectionReason.INVALID_STOP_GEOMETRY


def test_build_geometry_rejects_target_equal_to_entry() -> None:
    result = build_geometry(
        entry_price=Decimal("100.00"), stop_price=Decimal("95.00"), target_price=Decimal("100.00")
    )
    assert result is TradePlanRejectionReason.INVALID_TARGET_GEOMETRY


def test_build_geometry_rejects_target_below_entry() -> None:
    result = build_geometry(
        entry_price=Decimal("100.00"), stop_price=Decimal("95.00"), target_price=Decimal("90.00")
    )
    assert result is TradePlanRejectionReason.INVALID_TARGET_GEOMETRY


def test_build_geometry_accepts_valid_geometry_and_computes_ratio() -> None:
    result = build_geometry(
        entry_price=Decimal("100.00"), stop_price=Decimal("95.00"), target_price=Decimal("110.00")
    )
    assert isinstance(result, TradePlanGeometry)
    assert result.risk_per_unit == Decimal("5.00")
    assert result.reward_per_unit == Decimal("10.00")
    assert result.reward_risk_ratio == Decimal("2")


def test_build_geometry_handles_huge_decimal_values_without_error() -> None:
    result = build_geometry(
        entry_price=Decimal("1000000000.123456"),
        stop_price=Decimal("999999999.123456"),
        target_price=Decimal("1000000002.123456"),
    )
    assert isinstance(result, TradePlanGeometry)
    assert result.risk_per_unit == Decimal("1.000000")
    assert result.reward_per_unit == Decimal("2.000000")


def test_trade_plan_geometry_rejects_zero_risk_directly() -> None:
    with pytest.raises(ValueError, match="risk_per_unit"):
        TradePlanGeometry(
            entry_price=Decimal("100"),
            stop_price=Decimal("100"),
            target_price=Decimal("110"),
            risk_per_unit=Decimal("0"),
            reward_per_unit=Decimal("10"),
            reward_risk_ratio=Decimal("999"),
        )


def test_trade_plan_geometry_rejects_negative_risk_directly() -> None:
    with pytest.raises(ValueError, match="risk_per_unit"):
        TradePlanGeometry(
            entry_price=Decimal("100"),
            stop_price=Decimal("105"),
            target_price=Decimal("110"),
            risk_per_unit=Decimal("-5"),
            reward_per_unit=Decimal("10"),
            reward_risk_ratio=Decimal("-2"),
        )


# --- TradePlan invariants ----------------------------------------------------


def _valid_geometry() -> TradePlanGeometry:
    result = build_geometry(
        entry_price=Decimal("101.10"), stop_price=Decimal("100.50"), target_price=Decimal("102.51")
    )
    assert isinstance(result, TradePlanGeometry)
    return result


def test_trade_plan_rejects_approved_status_without_geometry() -> None:
    with pytest.raises(ValueError, match="must carry geometry"):
        TradePlan(
            identity=_plan_identity(),
            source_scan_id=TradingOpportunityScanId("SCAN-0001"),
            source_decision_candidate_id=DecisionCandidateId("DCAND-0001"),
            target_evidence_package_id=_EVID,
            instrument=Instrument("AAAA"),
            evaluation_cutoff=_CUTOFF,
            strategy_id="PRIOR_WINDOW_BREAKOUT_VOLUME_CONFIRMATION",
            strategy_version="1",
            ranking_model_id="BREAKOUT_VOLUME_STRENGTH_SUM",
            ranking_model_version="1",
            policy_id=RISK_POLICY_ID,
            policy_version=RISK_POLICY_VERSION,
            status=TradePlanStatus.APPROVED_PLAN,
            geometry=None,
            reasons=(),
        )


def test_trade_plan_rejects_approved_status_with_reasons() -> None:
    with pytest.raises(ValueError, match="no rejection reasons"):
        TradePlan(
            identity=_plan_identity(),
            source_scan_id=TradingOpportunityScanId("SCAN-0001"),
            source_decision_candidate_id=DecisionCandidateId("DCAND-0001"),
            target_evidence_package_id=_EVID,
            instrument=Instrument("AAAA"),
            evaluation_cutoff=_CUTOFF,
            strategy_id="PRIOR_WINDOW_BREAKOUT_VOLUME_CONFIRMATION",
            strategy_version="1",
            ranking_model_id="BREAKOUT_VOLUME_STRENGTH_SUM",
            ranking_model_version="1",
            policy_id=RISK_POLICY_ID,
            policy_version=RISK_POLICY_VERSION,
            status=TradePlanStatus.APPROVED_PLAN,
            geometry=_valid_geometry(),
            reasons=(TradePlanRejectionReason.REWARD_RISK_BELOW_MINIMUM,),
        )


def test_trade_plan_rejects_rejected_status_without_reasons() -> None:
    with pytest.raises(ValueError, match="at least one rejection reason"):
        TradePlan(
            identity=_plan_identity(),
            source_scan_id=TradingOpportunityScanId("SCAN-0001"),
            source_decision_candidate_id=DecisionCandidateId("DCAND-0001"),
            target_evidence_package_id=_EVID,
            instrument=Instrument("AAAA"),
            evaluation_cutoff=_CUTOFF,
            strategy_id="PRIOR_WINDOW_BREAKOUT_VOLUME_CONFIRMATION",
            strategy_version="1",
            ranking_model_id="BREAKOUT_VOLUME_STRENGTH_SUM",
            ranking_model_version="1",
            policy_id=RISK_POLICY_ID,
            policy_version=RISK_POLICY_VERSION,
            status=TradePlanStatus.REJECTED_PLAN,
            geometry=None,
            reasons=(),
        )


def test_trade_plan_rejects_multiple_rejection_reasons() -> None:
    with pytest.raises(ValueError, match="exactly one rejection reason"):
        TradePlan(
            identity=_plan_identity(),
            source_scan_id=TradingOpportunityScanId("SCAN-0001"),
            source_decision_candidate_id=DecisionCandidateId("DCAND-0001"),
            target_evidence_package_id=_EVID,
            instrument=Instrument("AAAA"),
            evaluation_cutoff=_CUTOFF,
            strategy_id="PRIOR_WINDOW_BREAKOUT_VOLUME_CONFIRMATION",
            strategy_version="1",
            ranking_model_id="BREAKOUT_VOLUME_STRENGTH_SUM",
            ranking_model_version="1",
            policy_id=RISK_POLICY_ID,
            policy_version=RISK_POLICY_VERSION,
            status=TradePlanStatus.REJECTED_PLAN,
            geometry=None,
            reasons=(
                TradePlanRejectionReason.SOURCE_NOT_LONG_CANDIDATE,
                TradePlanRejectionReason.PROVENANCE_MISMATCH,
            ),
        )


# --- build_trade_plan (full pipeline) ---------------------------------------


def test_build_trade_plan_approves_valid_geometry_above_threshold() -> None:
    candidate = _candidate(
        symbol="AAPL",
        decision=TradingDecision.LONG_CANDIDATE,
        measurements=_measurements(close="101.10", volume=1600),
    )
    scan = _scan(candidates=[candidate])
    plan = build_trade_plan(
        identity=_plan_identity(),
        scan=scan,
        candidate=candidate,
        target_evidence_package_id=_EVID,
        policy=_DEFAULT_POLICY,
    )
    assert plan.status is TradePlanStatus.APPROVED_PLAN
    assert plan.reasons == ()
    assert plan.geometry is not None
    assert plan.geometry.reward_risk_ratio == Decimal("2.35")


def test_build_trade_plan_rejects_no_trade_source() -> None:
    candidate = _candidate(
        symbol="MSFT",
        decision=TradingDecision.NO_TRADE,
        measurements=_measurements(close="100.40", volume=900),
    )
    scan = _scan(candidates=[candidate])
    plan = build_trade_plan(
        identity=_plan_identity(),
        scan=scan,
        candidate=candidate,
        target_evidence_package_id=_EVID,
        policy=_DEFAULT_POLICY,
    )
    assert plan.status is TradePlanStatus.REJECTED_PLAN
    assert plan.reasons == (TradePlanRejectionReason.SOURCE_NOT_LONG_CANDIDATE,)
    assert plan.geometry is None


def test_build_trade_plan_rejects_invalid_target_geometry_for_extended_breakout() -> None:
    """AMZN-shaped case: entry so far above reference_high that the fixed
    target projection falls at or below entry -- geometrically invalid,
    not merely a poor ratio."""
    candidate = _candidate(
        symbol="AMZN",
        decision=TradingDecision.LONG_CANDIDATE,
        measurements=_measurements(close="103.00", volume=3000),
    )
    scan = _scan(candidates=[candidate])
    plan = build_trade_plan(
        identity=_plan_identity(),
        scan=scan,
        candidate=candidate,
        target_evidence_package_id=_EVID,
        policy=_DEFAULT_POLICY,
    )
    assert plan.status is TradePlanStatus.REJECTED_PLAN
    assert plan.reasons == (TradePlanRejectionReason.INVALID_TARGET_GEOMETRY,)
    assert plan.geometry is None


def test_build_trade_plan_rejects_reward_risk_below_minimum() -> None:
    candidate = _candidate(
        symbol="NVDA",
        decision=TradingDecision.LONG_CANDIDATE,
        measurements=_measurements(close="102.00", volume=2000),
    )
    scan = _scan(candidates=[candidate])
    plan = build_trade_plan(
        identity=_plan_identity(),
        scan=scan,
        candidate=candidate,
        target_evidence_package_id=_EVID,
        policy=_DEFAULT_POLICY,
    )
    assert plan.status is TradePlanStatus.REJECTED_PLAN
    assert plan.reasons == (TradePlanRejectionReason.REWARD_RISK_BELOW_MINIMUM,)
    assert plan.geometry is not None
    assert plan.geometry.reward_risk_ratio == Decimal("0.34")


def test_build_trade_plan_rejects_candidate_not_present_in_claimed_scan() -> None:
    candidate = _candidate(
        symbol="AAPL",
        decision=TradingDecision.LONG_CANDIDATE,
        measurements=_measurements(close="101.10", volume=1600),
    )
    other_candidate = _candidate(
        symbol="BBBB",
        decision=TradingDecision.LONG_CANDIDATE,
        measurements=_measurements(close="101.10", volume=1600),
        n=2,
    )
    scan = _scan(candidates=[other_candidate])  # scan does NOT include `candidate`
    plan = build_trade_plan(
        identity=_plan_identity(),
        scan=scan,
        candidate=candidate,
        target_evidence_package_id=_EVID,
        policy=_DEFAULT_POLICY,
    )
    assert plan.status is TradePlanStatus.REJECTED_PLAN
    assert plan.reasons == (TradePlanRejectionReason.PROVENANCE_MISMATCH,)
    assert plan.geometry is None


def test_build_trade_plan_boundary_exactly_at_minimum_ratio_is_approved() -> None:
    """R:R == minimum_reward_risk_ratio exactly must be APPROVED (inclusive `>=`)."""
    candidate = _candidate(
        symbol="BNDY",
        decision=TradingDecision.LONG_CANDIDATE,
        measurements=_measurements(close="101.17", volume=1100),
    )
    scan = _scan(candidates=[candidate])
    plan = build_trade_plan(
        identity=_plan_identity(),
        scan=scan,
        candidate=candidate,
        target_evidence_package_id=_EVID,
        policy=_DEFAULT_POLICY,
    )
    assert plan.geometry is not None
    assert plan.geometry.reward_risk_ratio == Decimal("2.0")
    assert plan.status is TradePlanStatus.APPROVED_PLAN


def test_build_trade_plan_just_below_minimum_ratio_is_rejected() -> None:
    candidate = _candidate(
        symbol="BNDY",
        decision=TradingDecision.LONG_CANDIDATE,
        measurements=_measurements(close="101.18", volume=1100),
    )
    scan = _scan(candidates=[candidate])
    plan = build_trade_plan(
        identity=_plan_identity(),
        scan=scan,
        candidate=candidate,
        target_evidence_package_id=_EVID,
        policy=_DEFAULT_POLICY,
    )
    assert plan.geometry is not None
    assert plan.geometry.reward_risk_ratio < Decimal("2.0")
    assert plan.status is TradePlanStatus.REJECTED_PLAN
    assert plan.reasons == (TradePlanRejectionReason.REWARD_RISK_BELOW_MINIMUM,)


def test_build_trade_plan_deterministic_replay_produces_identical_result() -> None:
    candidate = _candidate(
        symbol="AAPL",
        decision=TradingDecision.LONG_CANDIDATE,
        measurements=_measurements(close="101.10", volume=1600),
    )
    scan = _scan(candidates=[candidate])
    first = build_trade_plan(
        identity=_plan_identity(1),
        scan=scan,
        candidate=candidate,
        target_evidence_package_id=_EVID,
        policy=_DEFAULT_POLICY,
    )
    second = build_trade_plan(
        identity=_plan_identity(2),
        scan=scan,
        candidate=candidate,
        target_evidence_package_id=_EVID,
        policy=_DEFAULT_POLICY,
    )
    assert first.status == second.status
    assert first.reasons == second.reasons
    assert first.geometry == second.geometry


def test_build_trade_plan_preserves_strategy_ranking_and_policy_identity() -> None:
    candidate = _candidate(
        symbol="AAPL",
        decision=TradingDecision.LONG_CANDIDATE,
        measurements=_measurements(close="101.10", volume=1600),
    )
    scan = _scan(candidates=[candidate])
    plan = build_trade_plan(
        identity=_plan_identity(),
        scan=scan,
        candidate=candidate,
        target_evidence_package_id=_EVID,
        policy=_DEFAULT_POLICY,
    )
    assert plan.strategy_id == candidate.strategy_id
    assert plan.strategy_version == candidate.strategy_version
    assert plan.ranking_model_id == scan.ranking_model_id
    assert plan.ranking_model_version == scan.ranking_model_version
    assert plan.policy_id == RISK_POLICY_ID
    assert plan.policy_version == RISK_POLICY_VERSION
