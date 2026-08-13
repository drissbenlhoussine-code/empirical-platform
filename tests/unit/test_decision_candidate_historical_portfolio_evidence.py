"""MILESTONE-074 -- Pure compatibility-rule unit tests.

No I/O. No PostgreSQL. No M070. No M072. No M073.

Exhaustive rule coverage for the pure
`find_compatible_historical_evidence` function and its internal
`_evaluate_compatibility` helper, in isolation.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from empirical_platform.decision_candidate.historical_portfolio_evidence import (
    HISTORICAL_EVIDENCE_STALENESS_DAYS,
    MINIMUM_M064_WINDOW_COUNT,
    HistoricalEvidenceCompatibilityStatus,
    _evaluate_compatibility,
    find_compatible_historical_evidence,
)
from empirical_platform.decision_candidate.instrument_master import (
    InstrumentId,
    InstrumentMaster,
    InstrumentMasterEntry,
    InstrumentType,
)
from empirical_platform.decision_candidate.market_data import Instrument
from empirical_platform.decision_candidate.portfolio_study import (
    PortfolioAllocationDecision,
    PortfolioAllocationOutcome,
    PortfolioCapitalPolicy,
    PortfolioEquityObservation,
    PortfolioEventKind,
    PortfolioEvidenceReport,
    PortfolioRejectionReason,
)
from empirical_platform.decision_candidate.robustness_study import WindowExtreme
from empirical_platform.decision_candidate.survivorship_study import (
    HISTORICAL_MEMBERSHIP_MODEL,
    BiasStressComparison,
    CurrentUniverseBiasStressResult,
    SurvivorshipAwareRobustnessStudy,
    SurvivorshipClassification,
    SurvivorshipStudyStatus,
    SurvivorshipWindowResult,
    WindowUniverseSnapshot,
)
from empirical_platform.identifiers.pairs import DomainIdentity
from empirical_platform.identifiers.types import (
    DatasetId,
    PortfolioStudyId,
    RobustnessStudyId,
    SurvivorshipStudyId,
)
from empirical_platform.shared.identifiers import RuntimeIdentifier, UuidRuntimeIdentifierGenerator

_STRATEGY_ID = "STRATEGY-X"
_STRATEGY_VERSION = "1"
_RANKING_ID = "RANKING-Y"
_RANKING_VERSION = "1"
_RISK_ID = "RISK-Z"
_RISK_VERSION = "1"
_SIZING_ID = "SIZING-W"
_SIZING_VERSION = "1"
_EXECUTION_ID = "EXEC-1"
_EXECUTION_VERSION = "1"
_OUTCOME_ID = "OUT-1"
_OUTCOME_VERSION = "1"
_COST_ID = "COST-1"
_COST_VERSION = "1"
_REGIME_ID = "REG-1"
_REGIME_VERSION = "1"
_CORP = "CORPORATE_ACTION_HANDLING_NOT_EXERCISED"


def _id_generator() -> UuidRuntimeIdentifierGenerator:
    return UuidRuntimeIdentifierGenerator()


def _build_window(
    *,
    window_id: str,
    sequence_index: int,
    data_end: datetime,
    evaluated_iids: tuple[InstrumentId, ...] = (),
    eligible_iids: tuple[InstrumentId, ...] = (),
) -> SurvivorshipWindowResult:
    snapshot = WindowUniverseSnapshot(
        window_id=window_id,
        sequence_index=sequence_index,
        universe_id="UNIVERSE-A",
        universe_version="1",
        membership_manifest_hash="mhash",
        eligible_instrument_ids=eligible_iids,
        evaluated_instrument_ids=evaluated_iids,
        missing_data_excluded_instrument_ids=(),
    )
    return SurvivorshipWindowResult(
        snapshot=snapshot,
        data_start_timestamp=data_end - timedelta(hours=1),
        data_end_timestamp=data_end,
        scoring_start_timestamp=data_end - timedelta(minutes=15),
        scoring_end_timestamp=data_end,
        backtest_run_id=None,
        backtest_run_runtime_id=None,
        regime_label=__import__(
            "empirical_platform.decision_candidate.robustness_study",
            fromlist=["RegimeLabel"],
        ).RegimeLabel.NORMAL_VOLATILITY,
        realized_volatility=Decimal("0.10"),
        evaluated_cutoff_count=8,
        simulated_trade_count=5,
        executed_trade_count=4,
        win_count=2,
        loss_count=2,
        time_exit_count=0,
        no_entry_count=1,
        gross_pnl=Decimal("100"),
        net_pnl=Decimal("80"),
        average_net_pnl=Decimal("20"),
        average_r=Decimal("0.5"),
        total_r=Decimal("2.0"),
        win_rate=Decimal("0.5"),
        profit_factor=Decimal("1.5"),
        maximum_realized_pnl_drawdown=Decimal("20"),
    )


def _build_study(
    *,
    study_runtime: RuntimeIdentifier,
    coverage_ends: tuple[datetime, ...],
    classification: SurvivorshipClassification = (
        SurvivorshipClassification.SURVIVORSHIP_AWARE_MEMBERSHIP_MECHANICS_PROVEN
    ),
    window_count: int | None = None,
    eligible_iids_per_window: tuple[tuple[InstrumentId, ...], ...] = (),
    evaluated_iids_per_window: tuple[tuple[InstrumentId, ...], ...] = (),
) -> SurvivorshipAwareRobustnessStudy:
    if window_count is None:
        window_count = len(coverage_ends)
    if not eligible_iids_per_window:
        eligible_iids_per_window = tuple(
            (InstrumentId("INSTR-AAPL-001"), InstrumentId("INSTR-MSFT-001"))
            for _ in range(window_count)
        )
    if not evaluated_iids_per_window:
        evaluated_iids_per_window = eligible_iids_per_window
    windows = tuple(
        _build_window(
            window_id=f"W{idx + 1:02d}",
            sequence_index=idx,
            data_end=coverage_ends[idx],
            eligible_iids=eligible_iids_per_window[idx],
            evaluated_iids=evaluated_iids_per_window[idx],
        )
        for idx in range(window_count)
    )
    identity = DomainIdentity(
        governance_id=SurvivorshipStudyId("SURV-6401"),
        runtime_id=study_runtime,
    )
    return SurvivorshipAwareRobustnessStudy(
        identity=identity,
        dataset_bundle_id=DatasetId("DATASET-6401"),
        dataset_bundle_version="1",
        dataset_bundle_sha256="a" * 64,
        dataset_source_kind="SURVIVORSHIP_AWARE_MECHANICS_FIXTURE",
        universe_id="UNIVERSE-6401",
        universe_version="1",
        universe_membership_model=HISTORICAL_MEMBERSHIP_MODEL,
        membership_manifest_hash="b" * 64,
        reference_window_size=5,
        strategy_id=_STRATEGY_ID,
        strategy_version=_STRATEGY_VERSION,
        ranking_model_id=_RANKING_ID,
        ranking_model_version=_RANKING_VERSION,
        risk_policy_id=_RISK_ID,
        risk_policy_version=_RISK_VERSION,
        sizing_policy_id=_SIZING_ID,
        sizing_policy_version=_SIZING_VERSION,
        execution_assumption_id=_EXECUTION_ID,
        execution_assumption_version=_EXECUTION_VERSION,
        outcome_model_id=_OUTCOME_ID,
        outcome_model_version=_OUTCOME_VERSION,
        cost_model_id=_COST_ID,
        cost_model_version=_COST_VERSION,
        holding_horizon_bars=3,
        supplied_account_equity=Decimal("100000"),
        supplied_risk_percent=Decimal("0.01"),
        regime_policy_id=_REGIME_ID,
        regime_policy_version=_REGIME_VERSION,
        corporate_action_handling=_CORP,
        status=SurvivorshipStudyStatus.STUDY_COMPLETED,
        classification=classification,
        window_results=windows,
        window_count=window_count,
        total_evaluated_cutoff_count=80,
        total_simulated_trade_count=50,
        total_executed_trade_count=35,
        positive_net_pnl_window_count=6,
        negative_net_pnl_window_count=4,
        positive_total_r_window_count=6,
        negative_total_r_window_count=4,
        median_window_net_pnl=Decimal("200"),
        median_window_total_r=Decimal("2"),
        best_window_by_net_pnl=WindowExtreme(window_id="W01", value=Decimal("500")),
        worst_window_by_net_pnl=WindowExtreme(window_id="W02", value=Decimal("-100")),
        best_window_by_total_r=WindowExtreme(window_id="W01", value=Decimal("3")),
        worst_window_by_total_r=WindowExtreme(window_id="W02", value=Decimal("-1")),
        all_window_net_pnl_total=Decimal("1000"),
        all_window_total_r_total=Decimal("20"),
        excluding_best_window_net_pnl_total=Decimal("500"),
        excluding_best_window_total_r_total=Decimal("10"),
        largest_positive_window_share_of_positive_pnl=Decimal("0.3"),
        largest_negative_window_share_of_absolute_negative_pnl=Decimal("0.4"),
        current_universe_bias_stress=CurrentUniverseBiasStressResult(
            stress_study_id=RobustnessStudyId("ROBUST-6402"),
            comparison=BiasStressComparison.CURRENT_UNIVERSE_BIAS_STRESS_DIFFERS,
            full_universe_size=6,
            canonical_total_executed_trade_count=35,
            stress_total_executed_trade_count=59,
            canonical_net_pnl_total=Decimal("1000"),
            stress_net_pnl_total=Decimal("2000"),
            canonical_total_r_total=Decimal("20"),
            stress_total_r_total=Decimal("40"),
            canonical_best_window_by_net_pnl=WindowExtreme(window_id="W01", value=Decimal("500")),
            stress_best_window_by_net_pnl=WindowExtreme(window_id="W03", value=Decimal("900")),
            canonical_worst_window_by_net_pnl=WindowExtreme(window_id="W02", value=Decimal("-100")),
            stress_worst_window_by_net_pnl=WindowExtreme(window_id="W05", value=Decimal("-200")),
        ),
    )


def _build_instrument_master() -> InstrumentMaster:
    return InstrumentMaster(
        entries=(
            InstrumentMasterEntry(
                instrument_id=InstrumentId("INSTR-AAPL-001"),
                canonical_symbol=Instrument(symbol="AAPL"),
                instrument_type=InstrumentType.EQUITY,
            ),
            InstrumentMasterEntry(
                instrument_id=InstrumentId("INSTR-MSFT-001"),
                canonical_symbol=Instrument(symbol="MSFT"),
                instrument_type=InstrumentType.EQUITY,
            ),
        )
    )


def _build_portfolio_report(
    study_runtime: RuntimeIdentifier,
    *,
    initial_capital: Decimal = Decimal("50000"),
    max_concurrent: int = 5,
) -> PortfolioEvidenceReport:
    return PortfolioEvidenceReport(
        identity=DomainIdentity(
            governance_id=PortfolioStudyId("PORT-6401"),
            runtime_id=_id_generator().generate(),
        ),
        source_study_governance_id="SURV-6401",
        source_study_runtime_id=str(study_runtime),
        dataset_bundle_id="DATASET-6401",
        dataset_bundle_version="1",
        dataset_bundle_sha256="a" * 64,
        dataset_source_kind="SURVIVORSHIP_AWARE_MECHANICS_FIXTURE",
        universe_id="UNIVERSE-6401",
        universe_version="1",
        membership_manifest_hash="b" * 64,
        strategy_id=_STRATEGY_ID,
        strategy_version=_STRATEGY_VERSION,
        ranking_model_id=_RANKING_ID,
        ranking_model_version=_RANKING_VERSION,
        risk_policy_id=_RISK_ID,
        risk_policy_version=_RISK_VERSION,
        sizing_policy_id=_SIZING_ID,
        sizing_policy_version=_SIZING_VERSION,
        capital_policy=PortfolioCapitalPolicy(
            policy_id="CAP-1",
            version="1",
            initial_capital=initial_capital,
            currency="USD",
            max_concurrent_positions=max_concurrent,
            max_capital_utilization_percent=Decimal("1.00"),
        ),
        total_opportunities=35,
        allocated_count=20,
        rejected_count=15,
        rejected_insufficient_capital_count=10,
        rejected_max_concurrent_count=5,
        rejected_max_utilization_count=0,
        initial_capital=initial_capital,
        ending_capital=Decimal("52000"),
        realized_pnl=Decimal("2000"),
        portfolio_return_percent=Decimal("0.04"),
        peak_equity=Decimal("53000"),
        max_drawdown=Decimal("500"),
        max_drawdown_percent=Decimal("0.01"),
        max_concurrent_positions_observed=4,
        average_concurrent_positions=Decimal("2.0"),
        peak_occupied_capital=Decimal("3000"),
        peak_capital_utilization_percent=Decimal("0.06"),
        largest_instrument_positive_contribution_symbol="AAPL",
        largest_instrument_positive_contribution_amount=Decimal("1000"),
        largest_instrument_negative_contribution_symbol="MSFT",
        largest_instrument_negative_contribution_amount=Decimal("-300"),
        largest_position_contribution_trade_sequence=5,
        largest_position_contribution_amount=Decimal("500"),
        largest_window_contribution_window_id="W03",
        largest_window_contribution_amount=Decimal("600"),
        allocation_decisions=tuple(
            PortfolioAllocationDecision(
                opportunity_sequence=seq,
                source_window_id=f"W{(seq % 10) + 1:02d}",
                trade_sequence=seq,
                instrument_symbol="AAPL" if seq % 2 == 0 else "MSFT",
                scan_rank=seq,
                entry_timestamp=datetime(2026, 1, 1, 10, 0, tzinfo=UTC),
                exit_timestamp=datetime(2026, 1, 1, 11, 0, tzinfo=UTC),
                risk_amount=Decimal("100"),
                net_pnl=Decimal("150") if seq % 2 == 0 else Decimal("-50"),
                decision=(
                    PortfolioAllocationOutcome.ALLOCATED
                    if seq < 20
                    else PortfolioAllocationOutcome.REJECTED
                ),
                rejection_reason=(
                    None
                    if seq < 20
                    else (
                        PortfolioRejectionReason.INSUFFICIENT_AVAILABLE_CAPITAL
                        if seq < 30
                        else PortfolioRejectionReason.MAX_CONCURRENT_POSITIONS
                    )
                ),
            )
            for seq in range(1, 36)
        ),
        equity_curve=(
            PortfolioEquityObservation(
                sequence_index=1,
                event_timestamp=datetime(2026, 1, 1, 10, 0, tzinfo=UTC),
                event_kind=PortfolioEventKind.OPEN,
                equity=Decimal("50000"),
                occupied_capital=Decimal("100"),
                available_capital=Decimal("49900"),
                open_position_count=1,
            ),
        ),
        capital_sensitivity_views=(
            __import__(
                "empirical_platform.decision_candidate.portfolio_study",
                fromlist=["CapitalSensitivityView"],
            ).CapitalSensitivityView(
                label=__import__(
                    "empirical_platform.decision_candidate.portfolio_study",
                    fromlist=["CapitalSensitivityLabel"],
                ).CapitalSensitivityLabel.CANONICAL,
                capital_policy_id="CAP-1",
                initial_capital=initial_capital,
                max_concurrent_positions=max_concurrent,
                allocated_count=20,
                rejected_count=15,
                ending_capital=Decimal("52000"),
                realized_pnl=Decimal("2000"),
                max_drawdown=Decimal("500"),
            ),
            __import__(
                "empirical_platform.decision_candidate.portfolio_study",
                fromlist=["CapitalSensitivityView"],
            ).CapitalSensitivityView(
                label=__import__(
                    "empirical_platform.decision_candidate.portfolio_study",
                    fromlist=["CapitalSensitivityLabel"],
                ).CapitalSensitivityLabel.REDUCED_CAPITAL,
                capital_policy_id="CAP-1",
                initial_capital=initial_capital / 2,
                max_concurrent_positions=max_concurrent,
                allocated_count=15,
                rejected_count=20,
                ending_capital=Decimal("51000"),
                realized_pnl=Decimal("1000"),
                max_drawdown=Decimal("400"),
            ),
            __import__(
                "empirical_platform.decision_candidate.portfolio_study",
                fromlist=["CapitalSensitivityView"],
            ).CapitalSensitivityView(
                label=__import__(
                    "empirical_platform.decision_candidate.portfolio_study",
                    fromlist=["CapitalSensitivityLabel"],
                ).CapitalSensitivityLabel.TIGHTER_MAX_CONCURRENCY,
                capital_policy_id="CAP-1",
                initial_capital=initial_capital,
                max_concurrent_positions=max(1, max_concurrent // 3),
                allocated_count=10,
                rejected_count=25,
                ending_capital=Decimal("50500"),
                realized_pnl=Decimal("500"),
                max_drawdown=Decimal("300"),
            ),
        ),
    )


_AS_OF = datetime(2026, 8, 20, 14, 0, tzinfo=UTC)
_COVERAGE_DATES = (
    datetime(2026, 8, 10, 13, 0, tzinfo=UTC),
    datetime(2026, 8, 12, 13, 0, tzinfo=UTC),
)


def _base_kwargs() -> dict[str, object]:
    return dict(
        m070_strategy_id=_STRATEGY_ID,
        m070_strategy_version=_STRATEGY_VERSION,
        m070_ranking_model_id=_RANKING_ID,
        m070_ranking_model_version=_RANKING_VERSION,
        m070_risk_policy_id=_RISK_ID,
        m070_risk_policy_version=_RISK_VERSION,
        m070_sizing_policy_id=_SIZING_ID,
        m070_sizing_policy_version=_SIZING_VERSION,
        m070_requested_universe=("AAPL", "MSFT"),
        m070_as_of=_AS_OF,
        instrument_master=_build_instrument_master(),
    )


def test_compatible_study_selected_in_order() -> None:
    study_runtime = _id_generator().generate()
    study = _build_study(study_runtime=study_runtime, coverage_ends=_COVERAGE_DATES)
    portfolio = _build_portfolio_report(study_runtime)
    out = find_compatible_historical_evidence(
        **_base_kwargs(),
        survivorship_candidates=(study,),
        portfolio_lookup={str(study_runtime): portfolio},
    )
    assert len(out) == 1
    item = out[0]
    assert item.compatibility_status is HistoricalEvidenceCompatibilityStatus.COMPATIBLE
    assert item.is_selected is True
    assert item.coverage_end == _COVERAGE_DATES[-1]
    assert item.matched_window_resolved_eligible_symbols == ("AAPL", "MSFT")
    assert item.portfolio_study_identity_governance == "PORT-6401"


def test_strategy_mismatch_makes_incompatible() -> None:
    study_runtime = _id_generator().generate()
    study = _build_study(study_runtime=study_runtime, coverage_ends=_COVERAGE_DATES)
    kwargs = _base_kwargs()
    kwargs["m070_strategy_id"] = "STRATEGY-OTHER"
    out = find_compatible_historical_evidence(
        **kwargs,
        survivorship_candidates=(study,),
        portfolio_lookup={},
    )
    assert out[0].compatibility_status is HistoricalEvidenceCompatibilityStatus.INCOMPATIBLE
    assert any("strategy_id mismatch" in r for r in out[0].compatibility_reasons)


def test_strategy_version_mismatch() -> None:
    study_runtime = _id_generator().generate()
    study = _build_study(study_runtime=study_runtime, coverage_ends=_COVERAGE_DATES)
    kwargs = _base_kwargs()
    kwargs["m070_strategy_version"] = "99"
    out = find_compatible_historical_evidence(
        **kwargs,
        survivorship_candidates=(study,),
        portfolio_lookup={},
    )
    assert out[0].compatibility_status is HistoricalEvidenceCompatibilityStatus.INCOMPATIBLE
    assert any("strategy_version mismatch" in r for r in out[0].compatibility_reasons)


def test_ranking_mismatch() -> None:
    study_runtime = _id_generator().generate()
    study = _build_study(study_runtime=study_runtime, coverage_ends=_COVERAGE_DATES)
    kwargs = _base_kwargs()
    kwargs["m070_ranking_model_id"] = "OTHER"
    out = find_compatible_historical_evidence(
        **kwargs,
        survivorship_candidates=(study,),
        portfolio_lookup={},
    )
    assert any("ranking_model_id" in r for r in out[0].compatibility_reasons)


def test_risk_policy_mismatch() -> None:
    study_runtime = _id_generator().generate()
    study = _build_study(study_runtime=study_runtime, coverage_ends=_COVERAGE_DATES)
    kwargs = _base_kwargs()
    kwargs["m070_risk_policy_id"] = "OTHER"
    out = find_compatible_historical_evidence(
        **kwargs,
        survivorship_candidates=(study,),
        portfolio_lookup={},
    )
    assert any("risk_policy_id" in r for r in out[0].compatibility_reasons)


def test_sizing_policy_mismatch() -> None:
    study_runtime = _id_generator().generate()
    study = _build_study(study_runtime=study_runtime, coverage_ends=_COVERAGE_DATES)
    kwargs = _base_kwargs()
    kwargs["m070_sizing_policy_id"] = "OTHER"
    out = find_compatible_historical_evidence(
        **kwargs,
        survivorship_candidates=(study,),
        portfolio_lookup={},
    )
    assert any("sizing_policy_id" in r for r in out[0].compatibility_reasons)


def test_requested_universe_not_in_any_window() -> None:
    study_runtime = _id_generator().generate()
    study = _build_study(
        study_runtime=study_runtime,
        coverage_ends=_COVERAGE_DATES,
        eligible_iids_per_window=(
            (InstrumentId("INSTR-AAPL-001"),),
            (InstrumentId("INSTR-AAPL-001"),),
        ),
        evaluated_iids_per_window=(
            (InstrumentId("INSTR-AAPL-001"),),
            (InstrumentId("INSTR-AAPL-001"),),
        ),
    )
    out = find_compatible_historical_evidence(
        **_base_kwargs(),
        survivorship_candidates=(study,),
        portfolio_lookup={},
    )
    assert out[0].compatibility_status is HistoricalEvidenceCompatibilityStatus.INCOMPATIBLE
    assert any("MSFT" in r for r in out[0].compatibility_reasons)


def test_one_window_study_is_rejected() -> None:
    study_runtime = _id_generator().generate()
    study = _build_study(
        study_runtime=study_runtime,
        coverage_ends=(datetime(2026, 8, 12, 13, 0, tzinfo=UTC),),
        window_count=1,
    )
    out = find_compatible_historical_evidence(
        **_base_kwargs(),
        survivorship_candidates=(study,),
        portfolio_lookup={},
    )
    assert out[0].compatibility_status is HistoricalEvidenceCompatibilityStatus.INCOMPATIBLE
    assert any("window_count" in r for r in out[0].compatibility_reasons)


def test_insufficient_sample_classification_rejected() -> None:
    study_runtime = _id_generator().generate()
    study = _build_study(
        study_runtime=study_runtime,
        coverage_ends=_COVERAGE_DATES,
        classification=SurvivorshipClassification.INSUFFICIENT_SAMPLE,
    )
    out = find_compatible_historical_evidence(
        **_base_kwargs(),
        survivorship_candidates=(study,),
        portfolio_lookup={},
    )
    assert out[0].compatibility_status is HistoricalEvidenceCompatibilityStatus.INCOMPATIBLE
    assert any("classification" in r for r in out[0].compatibility_reasons)


def test_future_evidence_rejected() -> None:
    study_runtime = _id_generator().generate()
    future_dates = (
        _AS_OF + timedelta(days=10),
        _AS_OF + timedelta(days=20),
    )
    study = _build_study(study_runtime=study_runtime, coverage_ends=future_dates)
    out = find_compatible_historical_evidence(
        **_base_kwargs(),
        survivorship_candidates=(study,),
        portfolio_lookup={},
    )
    assert out[0].compatibility_status is HistoricalEvidenceCompatibilityStatus.FUTURE_EVIDENCE
    assert any("future" in r.lower() for r in out[0].compatibility_reasons)


def test_stale_evidence_marked() -> None:
    study_runtime = _id_generator().generate()
    stale_dates = (
        _AS_OF - timedelta(days=120),
        _AS_OF - timedelta(days=100),
    )
    study = _build_study(study_runtime=study_runtime, coverage_ends=stale_dates)
    out = find_compatible_historical_evidence(
        **_base_kwargs(),
        survivorship_candidates=(study,),
        portfolio_lookup={},
    )
    assert out[0].compatibility_status is HistoricalEvidenceCompatibilityStatus.STALE
    assert any("more than" in r or "days" in r for r in out[0].compatibility_reasons)


def test_stale_boundary_91_days() -> None:
    study_runtime = _id_generator().generate()
    # coverage_end 91 days before as_of (latest window), earlier window 100 days before.
    # Tuple must be strictly increasing (earliest first) so M064 window
    # chronologically-disjoint invariant holds (data_start = data_end - 1h).
    boundary_dates = (
        _AS_OF - timedelta(days=HISTORICAL_EVIDENCE_STALENESS_DAYS + 10),
        _AS_OF - timedelta(days=HISTORICAL_EVIDENCE_STALENESS_DAYS + 1),
    )
    study = _build_study(study_runtime=study_runtime, coverage_ends=boundary_dates)
    out = find_compatible_historical_evidence(
        **_base_kwargs(),
        survivorship_candidates=(study,),
        portfolio_lookup={},
    )
    assert out[0].compatibility_status is HistoricalEvidenceCompatibilityStatus.STALE


def test_exactly_at_staleness_boundary_not_stale() -> None:
    study_runtime = _id_generator().generate()
    # coverage_end is exactly HISTORICAL_EVIDENCE_STALENESS_DAYS before as_of
    # (the comparison is `> 90 days`, so exactly 90 is NOT stale).
    # Tuple must be strictly increasing (earliest first) so M064 window
    # chronologically-disjoint invariant holds (data_start = data_end - 1h).
    boundary_dates = (
        _AS_OF - timedelta(days=200),
        _AS_OF - timedelta(days=HISTORICAL_EVIDENCE_STALENESS_DAYS),
    )
    study = _build_study(study_runtime=study_runtime, coverage_ends=boundary_dates)
    out = find_compatible_historical_evidence(
        **_base_kwargs(),
        survivorship_candidates=(study,),
        portfolio_lookup={},
    )
    # The latest coverage_end is 90 days before as_of which is NOT > 90 days
    # but the older window is much earlier, so the MAX coverage_end is 90 days
    # before -- this is exactly the boundary. The rule is `> 90 days = STALE`.
    # 90 days exactly is NOT stale.
    assert out[0].compatibility_status is HistoricalEvidenceCompatibilityStatus.COMPATIBLE


def test_missing_instrument_master_mapping_drops_resolved() -> None:
    study_runtime = _id_generator().generate()
    study = _build_study(study_runtime=study_runtime, coverage_ends=_COVERAGE_DATES)
    kwargs = _base_kwargs()
    kwargs["instrument_master"] = None
    out = find_compatible_historical_evidence(
        **kwargs,
        survivorship_candidates=(study,),
        portfolio_lookup={},
    )
    # With no InstrumentMaster, InstrumentIds cannot be resolved to symbols
    # → the U1/U2 rules fail because no symbol is in the union.
    assert out[0].compatibility_status is HistoricalEvidenceCompatibilityStatus.INCOMPATIBLE


def test_multiple_candidates_sorted_by_coverage_desc() -> None:
    r1 = _id_generator().generate()
    r2 = _id_generator().generate()
    older = _build_study(
        study_runtime=r1,
        coverage_ends=(
            _AS_OF - timedelta(days=30),
            _AS_OF - timedelta(days=20),
        ),
    )
    newer = _build_study(
        study_runtime=r2,
        coverage_ends=(_AS_OF - timedelta(days=15), _AS_OF - timedelta(days=5)),
    )
    out = find_compatible_historical_evidence(
        **_base_kwargs(),
        survivorship_candidates=(older, newer),
        portfolio_lookup={},
    )
    assert len(out) == 2
    assert out[0].coverage_end > out[1].coverage_end
    assert out[0].is_selected is True
    assert out[1].is_selected is False


def test_equal_coverage_uses_deterministic_runtime_id_tiebreak() -> None:
    import uuid

    r1 = RuntimeIdentifier(str(uuid.UUID("11111111-1111-4111-8111-111111111111")))
    r2 = RuntimeIdentifier(str(uuid.UUID("22222222-2222-4222-8222-222222222222")))
    # Use distinct coverage_ends per study so each study's windows are
    # chronologically valid, then have the latest coverage_end equal
    # across the two studies (so they tie on coverage, and tiebreak on
    # runtime_id).
    same_latest = _AS_OF - timedelta(days=5)
    s1 = _build_study(
        study_runtime=r1,
        coverage_ends=(same_latest - timedelta(days=15), same_latest),
    )
    s2 = _build_study(
        study_runtime=r2,
        coverage_ends=(same_latest - timedelta(days=10), same_latest),
    )
    out1 = find_compatible_historical_evidence(
        **_base_kwargs(),
        survivorship_candidates=(s1, s2),
        portfolio_lookup={},
    )
    out2 = find_compatible_historical_evidence(
        **_base_kwargs(),
        survivorship_candidates=(s2, s1),
        portfolio_lookup={},
    )
    # Same ordering regardless of input order
    assert [item.survivorship_study_identity_runtime for item in out1] == [
        item.survivorship_study_identity_runtime for item in out2
    ]
    # Tiebreak: lower runtime_id wins
    assert out1[0].survivorship_study_identity_runtime == str(r1)


def test_detached_m067_silently_dropped() -> None:
    study_runtime = _id_generator().generate()
    study = _build_study(study_runtime=study_runtime, coverage_ends=_COVERAGE_DATES)
    out = find_compatible_historical_evidence(
        **_base_kwargs(),
        survivorship_candidates=(study,),
        portfolio_lookup={},  # No M067 attached
    )
    assert out[0].compatibility_status is HistoricalEvidenceCompatibilityStatus.COMPATIBLE
    assert out[0].is_selected is True
    assert out[0].portfolio_study_identity_governance is None


def test_capital_policy_difference_annotated_not_rejected() -> None:
    study_runtime = _id_generator().generate()
    study = _build_study(study_runtime=study_runtime, coverage_ends=_COVERAGE_DATES)
    portfolio = _build_portfolio_report(
        study_runtime, initial_capital=Decimal("25000"), max_concurrent=3
    )
    out = find_compatible_historical_evidence(
        **_base_kwargs(),
        survivorship_candidates=(study,),
        portfolio_lookup={str(study_runtime): portfolio},
    )
    assert out[0].compatibility_status is HistoricalEvidenceCompatibilityStatus.COMPATIBLE
    assert out[0].portfolio_study_initial_capital == "25000"
    assert out[0].portfolio_study_max_concurrent_positions == 3


def test_m067_dataset_bundle_sha256_differs_from_m070_is_allowed() -> None:
    """The M070 session's dataset_sha256 is for a M069 single-window
    real-time snapshot. The M064 study's dataset_bundle_sha256 is for
    a M063 multi-window fixture. They MUST be allowed to differ."""
    study_runtime = _id_generator().generate()
    study = _build_study(study_runtime=study_runtime, coverage_ends=_COVERAGE_DATES)
    out = find_compatible_historical_evidence(
        **_base_kwargs(),
        survivorship_candidates=(study,),
        portfolio_lookup={},
    )
    # This is enforced by NOT requiring equality in the rule engine.
    # The test asserts the candidate is not rejected on SHA256 grounds.
    assert out[0].compatibility_status is HistoricalEvidenceCompatibilityStatus.COMPATIBLE
    assert out[0].is_selected is True


def test_minimum_m064_window_count_constant_is_2() -> None:
    assert MINIMUM_M064_WINDOW_COUNT == 2


def test_no_candidates_returns_empty_tuple() -> None:
    out = find_compatible_historical_evidence(
        **_base_kwargs(),
        survivorship_candidates=(),
        portfolio_lookup={},
    )
    assert out == ()


def test_evaluate_compatibility_pure_helper_short_circuits_in_order() -> None:
    """Verify that a single-rule failure short-circuits (no later
    rules checked). If strategy is wrong, we don't also report
    window_count or classification issues."""
    study = _build_study(
        study_runtime=_id_generator().generate(),
        coverage_ends=_COVERAGE_DATES,
        window_count=1,  # would fail W rule
        classification=SurvivorshipClassification.INSUFFICIENT_SAMPLE,  # would fail C
    )
    status, reasons, _, _ = _evaluate_compatibility(
        survivorship_study=study,
        m070_strategy_id="OTHER-STRATEGY",
        m070_strategy_version=None,
        m070_ranking_model_id=None,
        m070_ranking_model_version=None,
        m070_risk_policy_id=None,
        m070_risk_policy_version=None,
        m070_sizing_policy_id=None,
        m070_sizing_policy_version=None,
        m070_requested_universe=("AAPL",),
        m070_as_of=_AS_OF,
        instrument_master=_build_instrument_master(),
    )
    assert status is HistoricalEvidenceCompatibilityStatus.INCOMPATIBLE
    # Only H1 reason, not W or C reasons
    assert len(reasons) == 1
    assert "strategy_id mismatch" in reasons[0]


def test_universe_id_version_mismatch_in_persisted_data_does_not_block() -> None:
    """The M070 session has no universe_id/version (R6 in the design).
    M074 must not require this -- it uses the symbol-subset check
    (R5') instead."""
    study_runtime = _id_generator().generate()
    study = _build_study(
        study_runtime=study_runtime,
        coverage_ends=_COVERAGE_DATES,
    )
    # The _base_kwargs does not include universe_id/version (R6 N/A on M070)
    out = find_compatible_historical_evidence(
        **_base_kwargs(),
        survivorship_candidates=(study,),
        portfolio_lookup={},
    )
    assert out[0].compatibility_status is HistoricalEvidenceCompatibilityStatus.COMPATIBLE
