"""MILESTONE-072. Deterministic rendering of a `DailyResearchBrief` --
one human-readable plain-text renderer and one JSON renderer, both pure
functions over the same authoritative brief model so the two
representations can never semantically diverge. Neither renderer calls
an LLM, a network service, or any non-deterministic function: the same
`DailyResearchBrief` value always produces byte-identical output."""

from __future__ import annotations

from empirical_platform.decision_candidate.daily_research_brief import (
    AttentionLevel,
    BriefInstrumentEntry,
    DailyResearchBrief,
    HistoricalPortfolioEvidence,
)
from empirical_platform.decision_candidate.portfolio_aware_capital_feasibility import (
    PORTFOLIO_AWARE_FEASIBILITY_BANNER,
    PortfolioAwareCapitalAssessment,
    PortfolioAwareOutcome,
)
from empirical_platform.decision_candidate.research_session import SessionComparisonOutcome
from empirical_platform.decision_candidate.same_day_capital_feasibility import (
    CAPITAL_FEASIBILITY_BANNER,
    SameDayCapitalAssessment,
    SameDayCapitalOutcome,
)

__all__ = [
    "render_daily_research_brief_json",
    "render_daily_research_brief_text",
]


def _entries_with_outcome(
    brief: DailyResearchBrief, outcome: SessionComparisonOutcome
) -> tuple[BriefInstrumentEntry, ...]:
    return tuple(e for e in brief.entries if e.comparison_outcome is outcome)


def _attention_entries(brief: DailyResearchBrief) -> tuple[BriefInstrumentEntry, ...]:
    return tuple(
        e
        for e in brief.entries
        if e.attention_level in (AttentionLevel.ACTION_CANDIDATE, AttentionLevel.REVIEW)
    )


def _rejected_entries(brief: DailyResearchBrief) -> tuple[BriefInstrumentEntry, ...]:
    return tuple(e for e in brief.entries if e.rejection_reasons)


def _evidenced_entries(brief: DailyResearchBrief) -> tuple[BriefInstrumentEntry, ...]:
    return tuple(e for e in brief.entries if e.risk_evidence is not None)


def _entry_json(entry: BriefInstrumentEntry) -> dict[str, object]:
    risk = entry.risk_evidence
    return {
        "instrument_symbol": entry.instrument_symbol,
        "attention_level": entry.attention_level.value,
        "outcome": entry.comparison_outcome.value,
        "scan_decision": entry.scan_decision,
        "trade_plan_decision": entry.trade_plan_decision,
        "position_plan_status": entry.position_plan_status,
        "baseline_scan_decision": entry.baseline_scan_decision,
        "baseline_trade_plan_decision": entry.baseline_trade_plan_decision,
        "rejection_reasons": list(entry.rejection_reasons),
        "risk_evidence": (
            None
            if risk is None
            else {
                "entry_price": risk.entry_price,
                "stop_price": risk.stop_price,
                "target_price": risk.target_price,
                "reward_risk_ratio": risk.reward_risk_ratio,
                "quantity": risk.quantity,
                "position_notional": risk.position_notional,
                "actual_risk": risk.actual_risk,
            }
        ),
    }


def render_daily_research_brief_json(brief: DailyResearchBrief) -> dict[str, object]:
    """The same eight-section hierarchy as the text renderer, structured
    for machine consumption. Semantically identical content -- verified
    against the text renderer by a dedicated test. MILESTONE-074 adds
    a HISTORICAL_PORTFOLIO_EVIDENCE section between DATA_QUALITY and
    LIMITATIONS when historical evidence is present."""
    return {
        "SESSION": {
            "session_governance_id": brief.session_governance_id,
            "session_runtime_id": brief.session_runtime_id,
            "as_of": brief.as_of.isoformat(),
            "requested_universe": list(brief.requested_universe),
            "completion_status": brief.completion_status,
            "warnings": list(brief.session_warnings),
            "baseline_session_governance_id": brief.baseline_session_governance_id,
            "baseline_as_of": (
                brief.baseline_as_of.isoformat() if brief.baseline_as_of is not None else None
            ),
            "baseline_note": brief.baseline_note,
        },
        "ATTENTION": [_entry_json(e) for e in _attention_entries(brief)],
        "NEW": [_entry_json(e) for e in _entries_with_outcome(brief, SessionComparisonOutcome.NEW)],
        "CHANGED": [
            _entry_json(e) for e in _entries_with_outcome(brief, SessionComparisonOutcome.CHANGED)
        ],
        "DROPPED": [
            _entry_json(e) for e in _entries_with_outcome(brief, SessionComparisonOutcome.DROPPED)
        ],
        "UNCHANGED": [
            _entry_json(e) for e in _entries_with_outcome(brief, SessionComparisonOutcome.UNCHANGED)
        ],
        "REJECTIONS": [_entry_json(e) for e in _rejected_entries(brief)],
        "RISK_AND_EVIDENCE": {
            "entries": [_entry_json(e) for e in _evidenced_entries(brief)],
            "backtest_run_governance_id": brief.backtest_run_governance_id,
            "backtest_evaluated_opportunity_count": brief.backtest_evaluated_opportunity_count,
            "backtest_executed_trade_count": brief.backtest_executed_trade_count,
            "backtest_note": brief.backtest_note,
        },
        "DATA_QUALITY": {
            "data_source": brief.data_source,
            "dataset_sha256": brief.dataset_sha256,
            "as_of": brief.as_of.isoformat(),
        },
        "HISTORICAL_PORTFOLIO_EVIDENCE": _historical_evidence_json(
            brief.historical_portfolio_evidence
        ),
        "SAME_DAY_CAPITAL_FEASIBILITY": _capital_feasibility_json(
            brief.same_day_capital_assessment
        ),
        "PORTFOLIO_AWARE_CAPITAL_FEASIBILITY": _portfolio_aware_json(
            brief.portfolio_aware_capital_assessment
        ),
        "LIMITATIONS": list(brief.limitations),
        "AUDIT": {
            "campaign_governance_id": brief.campaign_governance_id,
            "run_governance_id": brief.run_governance_id,
            "evidence_package_governance_id": brief.evidence_package_governance_id,
            "scan_governance_id": brief.scan_governance_id,
            "stage_manifest_summary": list(brief.stage_manifest_summary),
        },
    }


_HISTORICAL_BANNER = (
    "separately persisted historical research evidence, structurally "
    "compatible with this daily session. NOT today's portfolio; NOT open "
    "positions; NOT live risk; NOT a paper account; NOT a profitability "
    "claim; NOT proof that survivorship bias was eliminated."
)


def _historical_evidence_json(
    items: tuple[HistoricalPortfolioEvidence, ...],
) -> dict[str, object]:
    """Render the historical portfolio evidence section as a JSON
    object. Returns either a populated list (with the honesty banner)
    or an explicit absence placeholder -- never fabricated evidence."""
    if not items:
        return {
            "honesty_banner": _HISTORICAL_BANNER,
            "candidates": [],
            "selected_compatible": None,
            "absence_reason": (
                "no compatible historical evidence available -- to produce one, run "
                "empirical-platform-run-survivorship-aware-robustness-study and "
                "optionally empirical-platform-run-portfolio-historical-evidence "
                "with matching strategy, risk, sizing, and universe authority"
            ),
        }
    serialized: list[dict[str, object]] = []
    for item in items:
        serialized.append(
            {
                "is_selected": item.is_selected,
                "compatibility_status": item.compatibility_status,
                "compatibility_reasons": list(item.compatibility_reasons),
                "survivorship_study_identity_runtime": item.survivorship_study_identity_runtime,
                "survivorship_study_identity_governance": (
                    item.survivorship_study_identity_governance
                ),
                "survivorship_study_window_count": (item.survivorship_study_window_count),
                "survivorship_study_total_executed_trade_count": (
                    item.survivorship_study_total_executed_trade_count
                ),
                "survivorship_study_all_window_net_pnl_total": (
                    item.survivorship_study_all_window_net_pnl_total
                ),
                "survivorship_study_classification": (item.survivorship_study_classification),
                "survivorship_study_dataset_bundle_id": (item.survivorship_study_dataset_bundle_id),
                "survivorship_study_dataset_bundle_sha256": (
                    item.survivorship_study_dataset_bundle_sha256
                ),
                "survivorship_study_universe_id": item.survivorship_study_universe_id,
                "survivorship_study_universe_version": (item.survivorship_study_universe_version),
                "survivorship_study_universe_membership_model": (
                    item.survivorship_study_universe_membership_model
                ),
                "survivorship_study_supplied_account_equity": (
                    item.survivorship_study_supplied_account_equity
                ),
                "survivorship_study_supplied_risk_percent": (
                    item.survivorship_study_supplied_risk_percent
                ),
                "survivorship_study_stress_comparison": (item.survivorship_study_stress_comparison),
                "coverage_end": item.coverage_end.isoformat(),
                "matched_window_resolved_eligible_symbols": list(
                    item.matched_window_resolved_eligible_symbols
                ),
                "portfolio_study_identity_governance": (item.portfolio_study_identity_governance),
                "portfolio_study_allocated_count": item.portfolio_study_allocated_count,
                "portfolio_study_realized_pnl": item.portfolio_study_realized_pnl,
                "portfolio_study_initial_capital": item.portfolio_study_initial_capital,
                "portfolio_study_currency": item.portfolio_study_currency,
                "portfolio_study_max_concurrent_positions": (
                    item.portfolio_study_max_concurrent_positions
                ),
                "portfolio_study_max_capital_utilization_percent": (
                    item.portfolio_study_max_capital_utilization_percent
                ),
            }
        )
    selected = next((item for item in items if item.is_selected), None)
    return {
        "honesty_banner": _HISTORICAL_BANNER,
        "candidates": serialized,
        "selected_compatible": (
            {
                "survivorship_study_governance_id": (
                    selected.survivorship_study_identity_governance
                ),
                "coverage_end": selected.coverage_end.isoformat(),
                "window_count": selected.survivorship_study_window_count,
            }
            if selected is not None
            else None
        ),
    }


def _entry_line(entry: BriefInstrumentEntry) -> str:
    decision = (
        entry.scan_decision if entry.scan_decision is not None else entry.baseline_scan_decision
    )
    plan = entry.trade_plan_decision if entry.trade_plan_decision is not None else "--"
    return f"  [{entry.attention_level.value}] {entry.instrument_symbol}: {decision}, {plan}"


def _section(title: str, lines: list[str]) -> list[str]:
    body = lines if lines else ["  (none)"]
    return [title, *body, ""]


def _portfolio_aware_json(
    assessment: PortfolioAwareCapitalAssessment | None,
) -> dict[str, object]:
    """MILESTONE-077. Absence is reported as absence, never as a pass."""
    if assessment is None:
        return {
            "computed": False,
            "banner": PORTFOLIO_AWARE_FEASIBILITY_BANNER,
            "note": (
                "portfolio-aware capital feasibility was not computed for this brief; "
                "this is not a finding that the session's approved plans fit within "
                "capital after already-asserted exposure"
            ),
        }
    return {
        "computed": True,
        "banner": PORTFOLIO_AWARE_FEASIBILITY_BANNER,
        "outcome": assessment.outcome.value,
        "unassessable_reason": (
            None if assessment.unassessable_reason is None else assessment.unassessable_reason.value
        ),
        "policy_id": assessment.policy_id,
        "policy_version": assessment.policy_version,
        "currency": assessment.currency,
        "capital_base": assessment.capital_base,
        "max_concurrent_positions": assessment.max_concurrent_positions,
        "max_capital_utilization_percent": assessment.max_capital_utilization_percent,
        "capital_ceiling": assessment.capital_ceiling,
        "held_position_count": assessment.held_position_count,
        "held_asserted_notional": assessment.held_asserted_notional,
        "remaining_capital_under_policy": assessment.remaining_capital_under_policy,
        "requested_plan_count": assessment.requested_plan_count,
        "admitted_plan_count": assessment.admitted_plan_count,
        "excluded_plan_count": assessment.excluded_plan_count,
        "total_admitted_notional": assessment.total_admitted_notional,
        "projected_committed_notional": assessment.projected_committed_notional,
        "projected_utilization_percent_of_ceiling": (
            assessment.projected_utilization_percent_of_ceiling
        ),
        "excluded_future_event_count": assessment.excluded_future_event_count,
        "plans_already_acted_upon": list(assessment.plans_already_acted_upon),
        "held_positions": [
            {
                "position_governance_id": position.position_governance_id,
                "instrument_symbol": position.instrument_symbol,
                "open_quantity": position.open_quantity,
                "asserted_entry_price": position.asserted_entry_price,
                "asserted_open_notional": position.asserted_open_notional,
                "source_position_plan_governance_id": (position.source_position_plan_governance_id),
            }
            for position in assessment.held_positions
        ],
        "verdicts": [
            {
                "rank": verdict.rank,
                "instrument_symbol": verdict.instrument_symbol,
                "position_plan_governance_id": verdict.position_plan_governance_id,
                "quantity": verdict.quantity,
                "position_notional": verdict.position_notional,
                "fits": verdict.fits,
                "rejection_reason": (
                    None if verdict.rejection_reason is None else verdict.rejection_reason.value
                ),
                "cumulative_committed_notional": verdict.cumulative_committed_notional,
            }
            for verdict in assessment.verdicts
        ],
        "limitations": list(assessment.limitations),
    }


def _capital_feasibility_json(
    assessment: SameDayCapitalAssessment | None,
) -> dict[str, object]:
    """MILESTONE-075. `assessment is None` means the assessment was not
    computed at all (suppressed by flag) -- reported as such, never as a
    feasible verdict."""
    if assessment is None:
        return {
            "honesty_banner": CAPITAL_FEASIBILITY_BANNER,
            "computed": False,
            "outcome": None,
            "note": (
                "same-day capital feasibility was not computed for this brief; this is "
                "not a finding that the session's approved plans fit within capital"
            ),
        }
    return {
        "honesty_banner": CAPITAL_FEASIBILITY_BANNER,
        "computed": True,
        "outcome": assessment.outcome.value,
        "unassessable_reason": (
            assessment.unassessable_reason.value
            if assessment.unassessable_reason is not None
            else None
        ),
        "policy_id": assessment.policy_id,
        "policy_version": assessment.policy_version,
        "currency": assessment.currency,
        "capital_base": assessment.capital_base,
        "max_concurrent_positions": assessment.max_concurrent_positions,
        "max_capital_utilization_percent": assessment.max_capital_utilization_percent,
        "capital_ceiling": assessment.capital_ceiling,
        "requested_plan_count": assessment.requested_plan_count,
        "admitted_plan_count": assessment.admitted_plan_count,
        "excluded_plan_count": assessment.excluded_plan_count,
        "total_requested_notional": assessment.total_requested_notional,
        "total_admitted_notional": assessment.total_admitted_notional,
        "total_admitted_risk": assessment.total_admitted_risk,
        "utilization_percent_of_ceiling": assessment.utilization_percent_of_ceiling,
        "requested_percent_of_capital_base": assessment.requested_percent_of_capital_base,
        "verdicts": [
            {
                "rank": v.rank,
                "instrument_symbol": v.instrument_symbol,
                "position_plan_governance_id": v.position_plan_governance_id,
                "quantity": v.quantity,
                "position_notional": v.position_notional,
                "actual_risk": v.actual_risk,
                "fits": v.fits,
                "rejection_reason": (
                    v.rejection_reason.value if v.rejection_reason is not None else None
                ),
                "cumulative_committed_notional": v.cumulative_committed_notional,
            }
            for v in assessment.verdicts
        ],
        "limitations": list(assessment.limitations),
    }


def render_daily_research_brief_text(brief: DailyResearchBrief) -> str:
    """Fixed-order plain-text template over the brief model's own
    already-formatted values -- no current-time insertion, no random
    ordering, no environment-dependent formatting."""
    out: list[str] = []
    out.append(f"DAILY RESEARCH BRIEF -- {brief.session_governance_id}")
    out.append("=" * 70)
    out.append("")

    session_lines = [
        f"  as_of: {brief.as_of.isoformat()}",
        f"  universe: {', '.join(brief.requested_universe)}",
        f"  status: {brief.completion_status}",
    ]
    for warning in brief.session_warnings:
        session_lines.append(f"  [WARNING] {warning}")
    if brief.baseline_session_governance_id is not None:
        session_lines.append(
            f"  compared against: {brief.baseline_session_governance_id} "
            f"(as_of {brief.baseline_as_of.isoformat() if brief.baseline_as_of else '?'})"
        )
    elif brief.baseline_note is not None:
        session_lines.append(f"  {brief.baseline_note}")
    out.extend(_section("SESSION", session_lines))

    out.extend(_section("ATTENTION", [_entry_line(e) for e in _attention_entries(brief)]))
    out.extend(
        _section(
            "NEW",
            [_entry_line(e) for e in _entries_with_outcome(brief, SessionComparisonOutcome.NEW)],
        )
    )
    out.extend(
        _section(
            "CHANGED",
            [
                _entry_line(e)
                for e in _entries_with_outcome(brief, SessionComparisonOutcome.CHANGED)
            ],
        )
    )
    out.extend(
        _section(
            "DROPPED",
            [
                _entry_line(e)
                for e in _entries_with_outcome(brief, SessionComparisonOutcome.DROPPED)
            ],
        )
    )
    out.extend(
        _section(
            "UNCHANGED",
            [
                _entry_line(e)
                for e in _entries_with_outcome(brief, SessionComparisonOutcome.UNCHANGED)
            ],
        )
    )

    rejection_lines = [
        f"  {e.instrument_symbol}: {'; '.join(e.rejection_reasons)}"
        for e in _rejected_entries(brief)
    ]
    out.extend(_section("REJECTIONS", rejection_lines))

    risk_lines = [
        f"  {e.instrument_symbol}: entry={e.risk_evidence.entry_price} "
        f"stop={e.risk_evidence.stop_price} target={e.risk_evidence.target_price} "
        f"rr={e.risk_evidence.reward_risk_ratio} qty={e.risk_evidence.quantity} "
        f"notional={e.risk_evidence.position_notional} risk={e.risk_evidence.actual_risk}"
        for e in _evidenced_entries(brief)
        if e.risk_evidence is not None
    ]
    if brief.backtest_note is not None:
        risk_lines.append(f"  historical evidence: {brief.backtest_note}")
    out.extend(_section("RISK & EVIDENCE", risk_lines))

    out.extend(
        _section(
            "DATA QUALITY",
            [
                f"  data_source: {brief.data_source}",
                f"  dataset_sha256: {brief.dataset_sha256}",
                f"  as_of: {brief.as_of.isoformat()}",
            ],
        )
    )

    historical_lines = [f"  {line}" for line in _HISTORICAL_BANNER.split(". ") if line]
    if brief.historical_portfolio_evidence:
        for item in brief.historical_portfolio_evidence:
            selected_marker = " [SELECTED]" if item.is_selected else ""
            historical_lines.append(
                f"  candidate{selected_marker}: "
                f"{item.survivorship_study_identity_governance} "
                f"status={item.compatibility_status} "
                f"windows={item.survivorship_study_window_count} "
                f"trades={item.survivorship_study_total_executed_trade_count} "
                f"pnl={item.survivorship_study_all_window_net_pnl_total} "
                f"classification={item.survivorship_study_classification} "
                f"coverage_end={item.coverage_end.isoformat()}"
            )
            for reason in item.compatibility_reasons:
                historical_lines.append(f"    reason: {reason}")
        selected = next(
            (item for item in brief.historical_portfolio_evidence if item.is_selected),
            None,
        )
        if selected is not None:
            historical_lines.append("")
            historical_lines.append(
                f"  selected compatible study: "
                f"{selected.survivorship_study_identity_governance} "
                f"(latest historical coverage ending at {selected.coverage_end.isoformat()})"
            )
            if selected.portfolio_study_identity_governance is not None:
                historical_lines.append(
                    f"  attached M067 portfolio report: "
                    f"{selected.portfolio_study_identity_governance} "
                    f"allocated={selected.portfolio_study_allocated_count} "
                    f"pnl={selected.portfolio_study_realized_pnl} "
                    f"initial_capital={selected.portfolio_study_initial_capital} "
                    f"max_concurrent={selected.portfolio_study_max_concurrent_positions}"
                )
            else:
                historical_lines.append("  no M067 portfolio report attached for this M064 study")
    else:
        historical_lines.append(
            "  no compatible historical evidence available -- to produce one, run "
            "empirical-platform-run-survivorship-aware-robustness-study and "
            "optionally empirical-platform-run-portfolio-historical-evidence "
            "with matching strategy, risk, sizing, and universe authority"
        )
    out.extend(_section("HISTORICAL PORTFOLIO EVIDENCE", historical_lines))

    capital_lines = [f"  {line}" for line in CAPITAL_FEASIBILITY_BANNER.split(". ") if line]
    assessment = brief.same_day_capital_assessment
    if assessment is None:
        capital_lines.append(
            "  not computed for this brief -- this is NOT a finding that the approved "
            "plans fit within capital"
        )
    else:
        capital_lines.append(f"  outcome: {assessment.outcome}")
        if assessment.unassessable_reason is not None:
            capital_lines.append(f"  not assessable: {assessment.unassessable_reason}")
        if assessment.outcome in (
            SameDayCapitalOutcome.FITS_WITHIN_CAPITAL,
            SameDayCapitalOutcome.EXCEEDS_CAPITAL,
        ):
            capital_lines.append(
                f"  policy: {assessment.policy_id} v{assessment.policy_version} "
                f"capital_base={assessment.capital_base} {assessment.currency} "
                f"ceiling={assessment.capital_ceiling} "
                f"max_concurrent={assessment.max_concurrent_positions}"
            )
            capital_lines.append(
                f"  requested {assessment.requested_plan_count} plan(s) totalling "
                f"{assessment.total_requested_notional} "
                f"({assessment.requested_percent_of_capital_base} of capital base); "
                f"{assessment.admitted_plan_count} fit, totalling "
                f"{assessment.total_admitted_notional}"
            )
            for v in assessment.verdicts:
                rank = "-" if v.rank is None else str(v.rank)
                if v.fits:
                    capital_lines.append(
                        f"    [{rank}] {v.instrument_symbol} qty={v.quantity} "
                        f"notional={v.position_notional} FITS "
                        f"(cumulative {v.cumulative_committed_notional})"
                    )
                else:
                    capital_lines.append(
                        f"    [{rank}] {v.instrument_symbol} qty={v.quantity} "
                        f"notional={v.position_notional} DOES NOT FIT "
                        f"({v.rejection_reason})"
                    )
        for limitation in assessment.limitations:
            capital_lines.append(f"  limitation: {limitation}")

    out.extend(_section("SAME-DAY CAPITAL FEASIBILITY", capital_lines))

    portfolio_lines = [
        f"  {line}" for line in PORTFOLIO_AWARE_FEASIBILITY_BANNER.split(". ") if line
    ]
    portfolio = brief.portfolio_aware_capital_assessment
    if portfolio is None:
        portfolio_lines.append(
            "  not computed for this brief -- this is NOT a finding that the approved "
            "plans fit within capital after already-asserted exposure"
        )
    else:
        portfolio_lines.append(f"  outcome: {portfolio.outcome}")
        if portfolio.unassessable_reason is not None:
            portfolio_lines.append(f"  not assessable: {portfolio.unassessable_reason}")
        if portfolio.outcome is not PortfolioAwareOutcome.NOT_ASSESSABLE:
            portfolio_lines.append(
                f"  policy: {portfolio.policy_id} v{portfolio.policy_version} "
                f"capital_base={portfolio.capital_base} {portfolio.currency} "
                f"ceiling={portfolio.capital_ceiling} "
                f"max_concurrent={portfolio.max_concurrent_positions}"
            )
            portfolio_lines.append(
                f"  operator-asserted open positions: {portfolio.held_position_count}, "
                f"asserted notional {portfolio.held_asserted_notional}; remaining under "
                f"policy {portfolio.remaining_capital_under_policy}"
            )
            for position in portfolio.held_positions:
                cited = position.source_position_plan_governance_id or "-"
                portfolio_lines.append(
                    f"    held {position.instrument_symbol} qty={position.open_quantity} "
                    f"asserted_entry={position.asserted_entry_price} "
                    f"asserted_notional={position.asserted_open_notional} "
                    f"cites_plan={cited}"
                )
            portfolio_lines.append(
                f"  proposed {portfolio.requested_plan_count} plan(s); "
                f"{portfolio.admitted_plan_count} fit after held exposure, totalling "
                f"{portfolio.total_admitted_notional}; projected utilisation "
                f"{portfolio.projected_utilization_percent_of_ceiling}"
            )
            for verdict in portfolio.verdicts:
                rank = "-" if verdict.rank is None else str(verdict.rank)
                if verdict.fits:
                    portfolio_lines.append(
                        f"    [{rank}] {verdict.instrument_symbol} "
                        f"qty={verdict.quantity} notional={verdict.position_notional} "
                        f"FITS (cumulative {verdict.cumulative_committed_notional})"
                    )
                else:
                    portfolio_lines.append(
                        f"    [{rank}] {verdict.instrument_symbol} "
                        f"qty={verdict.quantity} notional={verdict.position_notional} "
                        f"DOES NOT FIT ({verdict.rejection_reason})"
                    )
        for plan_id in portfolio.plans_already_acted_upon:
            portfolio_lines.append(
                f"  already acted upon: plan {plan_id} is cited by an open "
                "operator-asserted position and was not counted again"
            )
        for limitation in portfolio.limitations:
            portfolio_lines.append(f"  limitation: {limitation}")

    out.extend(_section("PORTFOLIO-AWARE CAPITAL FEASIBILITY", portfolio_lines))

    out.extend(_section("LIMITATIONS", [f"  - {limitation}" for limitation in brief.limitations]))

    audit_lines = [
        f"  campaign: {brief.campaign_governance_id}",
        f"  run: {brief.run_governance_id}",
        f"  evidence_package: {brief.evidence_package_governance_id}",
        f"  scan: {brief.scan_governance_id}",
        *[f"  stage: {s}" for s in brief.stage_manifest_summary],
    ]
    out.extend(_section("AUDIT", audit_lines))

    return "\n".join(out).rstrip() + "\n"
