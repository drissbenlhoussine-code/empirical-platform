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
)
from empirical_platform.decision_candidate.research_session import SessionComparisonOutcome

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
    against the text renderer by a dedicated test."""
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
        "LIMITATIONS": list(brief.limitations),
        "AUDIT": {
            "campaign_governance_id": brief.campaign_governance_id,
            "run_governance_id": brief.run_governance_id,
            "evidence_package_governance_id": brief.evidence_package_governance_id,
            "scan_governance_id": brief.scan_governance_id,
            "stage_manifest_summary": list(brief.stage_manifest_summary),
        },
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
