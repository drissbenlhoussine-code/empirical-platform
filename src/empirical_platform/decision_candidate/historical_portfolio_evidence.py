"""MILESTONE-074 -- Historical portfolio evidence compatibility domain.

Pure, I/O-free compatibility rule and read-only value objects for
binding a persisted, separately-produced M064 survivorship-aware
robustness study and its companion M067 portfolio evidence to an
already-persisted M070 daily ResearchSession, for surfacing inside the
M072 DailyResearchBrief under the honesty banner this module's
documentation mandates.

No I/O. No shared.persistence. No sqlalchemy. No psycopg. No boto3.
No network. No LLM. No broker. No paper account. No positions. No
current portfolio. No live risk. No profitability claim. No
survivorship-bias-elimination claim. This is read-only historical
research binding, nothing more.

Compatibility rules (see M074 owner architecture decision):

H1-H4 hard policy-identity match (strategy, ranking, risk, sizing).

U1 every M070 requested_universe symbol is represented in the UNION
   of M064 evaluated-instrument symbols across the whole study.
U2 at least one M064 window's resolved eligible-symbol set is a
   superset of the complete M070 requested_universe.

W  M064 window_count must be >= 2 (one-window M064 is rejected as
   degenerate survivorship robustness evidence).
C  M064 classification must be
   SURVIVORSHIP_AWARE_MEMBERSHIP_MECHANICS_PROVEN
   (INSUFFICIENT_SAMPLE rejected as below M074's evidence threshold).
L  M067 source_study_runtime_id must equal the selected M064
   runtime_id (lineage integrity). Enforced by the pure rule: an
   M067 report whose source_study_runtime_id does not match the
   M064 candidate's runtime_id is silently dropped, regardless of
   how `portfolio_lookup` was keyed.

Coverage / staleness:

T  historical_coverage_end = max(window.data_end_timestamp)
   is the authoritative historical-coverage timestamp.

S  session.as_of - historical_coverage_end > 90 days is STALE.
F  historical_coverage_end > session.as_of is FUTURE_EVIDENCE
   (impossible; rejected explicitly).
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from enum import StrEnum

from empirical_platform.decision_candidate.instrument_master import InstrumentId, InstrumentMaster
from empirical_platform.decision_candidate.portfolio_study import (
    PortfolioEvidenceReport,
)
from empirical_platform.decision_candidate.survivorship_study import (
    SurvivorshipAwareRobustnessStudy,
    SurvivorshipClassification,
)

#: M074 design constant. Not a business policy that M075 may revise --
# this is the M074 implementation constant.
HISTORICAL_EVIDENCE_STALENESS_DAYS: int = 90

#: Frozen M074 evidence threshold. M064 must have at least this many
# windows to qualify as "robustness" evidence (one-window M064 is
# rejected as degenerate).
MINIMUM_M064_WINDOW_COUNT: int = 2


class HistoricalEvidenceCompatibilityStatus(StrEnum):
    """Closed, conservative compatibility status vocabulary. Each
    candidate is annotated with exactly one of these."""

    COMPATIBLE = "COMPATIBLE"
    INCOMPATIBLE = "INCOMPATIBLE"
    STALE = "STALE"
    FUTURE_EVIDENCE = "FUTURE_EVIDENCE"


@dataclass(frozen=True, slots=True)
class HistoricalPortfolioEvidence:
    """One read-only summary of an M064 survivorship-aware study and its
    companion M067 portfolio evidence (if any), with a compatibility
    status annotation and the historical-coverage timestamp used for
    honest chronological ordering.

    No field here is computed by M074 except `coverage_end`,
    `compatibility_status`, and `compatibility_reasons`; everything
    else is read verbatim from the persisted M064 / M067 rows.

    A `M070_daily_session_policy` field exposes the M070 session's
    risk/sizing policy identities (the only thing the M070 session
    persists about its risk/sizing context) so the brief can render
    the policy-identity-vs-policy-value gap honestly.
    """

    survivorship_study_identity_runtime: str
    survivorship_study_identity_governance: str
    survivorship_study_window_count: int
    survivorship_study_total_executed_trade_count: int
    survivorship_study_all_window_net_pnl_total: str
    survivorship_study_classification: str
    survivorship_study_dataset_bundle_id: str
    survivorship_study_dataset_bundle_sha256: str
    survivorship_study_universe_id: str
    survivorship_study_universe_version: str
    survivorship_study_universe_membership_model: str
    survivorship_study_supplied_account_equity: str
    survivorship_study_supplied_risk_percent: str
    survivorship_study_stress_comparison: str
    coverage_end: datetime
    matched_window_resolved_eligible_symbols: tuple[str, ...]
    portfolio_study_identity_governance: str | None
    portfolio_study_allocated_count: int | None
    portfolio_study_realized_pnl: str | None
    portfolio_study_initial_capital: str | None
    portfolio_study_currency: str | None
    portfolio_study_max_concurrent_positions: int | None
    portfolio_study_max_capital_utilization_percent: str | None
    compatibility_status: HistoricalEvidenceCompatibilityStatus
    compatibility_reasons: tuple[str, ...] = field(default_factory=tuple)
    is_selected: bool = False


def _resolve_symbols(
    instrument_ids: Iterable[InstrumentId], instrument_master: InstrumentMaster | None
) -> tuple[str, ...]:
    """Resolve InstrumentIds to canonical ticker symbols via the
    persisted InstrumentMaster. Unknown InstrumentIds are dropped
    silently (with their absence reflected in U1/U2 logic upstream).
    No resolution at all if no InstrumentMaster is available.
    """
    if instrument_master is None:
        return ()
    resolved: list[str] = []
    for iid in instrument_ids:
        try:
            entry = instrument_master.entry_for(iid)
        except KeyError:
            continue
        resolved.append(str(entry.canonical_symbol))
    return tuple(sorted(set(resolved)))


def _evaluate_compatibility(
    *,
    survivorship_study: SurvivorshipAwareRobustnessStudy,
    m070_strategy_id: str | None,
    m070_strategy_version: str | None,
    m070_ranking_model_id: str | None,
    m070_ranking_model_version: str | None,
    m070_risk_policy_id: str | None,
    m070_risk_policy_version: str | None,
    m070_sizing_policy_id: str | None,
    m070_sizing_policy_version: str | None,
    m070_requested_universe: tuple[str, ...],
    m070_as_of: datetime,
    instrument_master: InstrumentMaster | None,
) -> tuple[HistoricalEvidenceCompatibilityStatus, tuple[str, ...], datetime, tuple[str, ...]]:
    """Pure compatibility rule. Returns
    (status, reasons, coverage_end, matched_window_resolved_symbols).

    H1-H4, W, C, U1, U2, S, F are checked in that order; first failure
    short-circuits and returns the corresponding status + reasons.
    A future-dated `historical_coverage_end` is checked AFTER the
    hard policy rules, before staleness, because future evidence is
    structurally impossible and deserves its own status.
    """
    reasons: list[str] = []
    # H1 strategy
    if m070_strategy_id is not None and survivorship_study.strategy_id != m070_strategy_id:
        reasons.append(
            f"strategy_id mismatch: M070={m070_strategy_id!r} M064="
            f"{survivorship_study.strategy_id!r}"
        )
    if (
        m070_strategy_version is not None
        and survivorship_study.strategy_version != m070_strategy_version
    ):
        reasons.append(
            f"strategy_version mismatch: M070={m070_strategy_version!r} M064="
            f"{survivorship_study.strategy_version!r}"
        )
    # H2 ranking
    if (
        m070_ranking_model_id is not None
        and survivorship_study.ranking_model_id != m070_ranking_model_id
    ):
        reasons.append(
            f"ranking_model_id mismatch: M070={m070_ranking_model_id!r} M064="
            f"{survivorship_study.ranking_model_id!r}"
        )
    if (
        m070_ranking_model_version is not None
        and survivorship_study.ranking_model_version != m070_ranking_model_version
    ):
        reasons.append(
            f"ranking_model_version mismatch: M070={m070_ranking_model_version!r} M064="
            f"{survivorship_study.ranking_model_version!r}"
        )
    # H3 risk
    if m070_risk_policy_id is not None and survivorship_study.risk_policy_id != m070_risk_policy_id:
        reasons.append(
            f"risk_policy_id mismatch: M070={m070_risk_policy_id!r} M064="
            f"{survivorship_study.risk_policy_id!r}"
        )
    if (
        m070_risk_policy_version is not None
        and survivorship_study.risk_policy_version != m070_risk_policy_version
    ):
        reasons.append(
            f"risk_policy_version mismatch: M070={m070_risk_policy_version!r} M064="
            f"{survivorship_study.risk_policy_version!r}"
        )
    # H4 sizing
    if (
        m070_sizing_policy_id is not None
        and survivorship_study.sizing_policy_id != m070_sizing_policy_id
    ):
        reasons.append(
            f"sizing_policy_id mismatch: M070={m070_sizing_policy_id!r} M064="
            f"{survivorship_study.sizing_policy_id!r}"
        )
    if (
        m070_sizing_policy_version is not None
        and survivorship_study.sizing_policy_version != m070_sizing_policy_version
    ):
        reasons.append(
            f"sizing_policy_version mismatch: M070={m070_sizing_policy_version!r} M064="
            f"{survivorship_study.sizing_policy_version!r}"
        )
    if reasons:
        return HistoricalEvidenceCompatibilityStatus.INCOMPATIBLE, tuple(reasons), datetime.min, ()

    # W: window_count >= 2
    if survivorship_study.window_count < MINIMUM_M064_WINDOW_COUNT:
        reasons.append(
            f"M064 window_count={survivorship_study.window_count} is below M074 threshold "
            f"of {MINIMUM_M064_WINDOW_COUNT}; one-window M064 is degenerate"
        )
        return HistoricalEvidenceCompatibilityStatus.INCOMPATIBLE, tuple(reasons), datetime.min, ()

    # C: classification
    if (
        survivorship_study.classification
        is not SurvivorshipClassification.SURVIVORSHIP_AWARE_MEMBERSHIP_MECHANICS_PROVEN
    ):
        reasons.append(
            f"M064 classification={survivorship_study.classification.value!r} does not meet "
            f"M074 evidence threshold"
        )
        return HistoricalEvidenceCompatibilityStatus.INCOMPATIBLE, tuple(reasons), datetime.min, ()

    # T: coverage end = max(window.data_end_timestamp)
    if not survivorship_study.window_results:
        reasons.append("M064 has no window_results; cannot derive coverage")
        return HistoricalEvidenceCompatibilityStatus.INCOMPATIBLE, tuple(reasons), datetime.min, ()
    coverage_end = max(result.data_end_timestamp for result in survivorship_study.window_results)

    # F: future evidence (must be checked before staleness)
    if coverage_end > m070_as_of:
        reasons.append(
            f"historical_coverage_end={coverage_end.isoformat()} is after M070.as_of="
            f"{m070_as_of.isoformat()}; future evidence is impossible"
        )
        return (
            HistoricalEvidenceCompatibilityStatus.FUTURE_EVIDENCE,
            tuple(reasons),
            coverage_end,
            (),
        )

    # S: staleness
    if m070_as_of - coverage_end > timedelta(days=HISTORICAL_EVIDENCE_STALENESS_DAYS):
        reasons.append(
            f"historical_coverage_end={coverage_end.isoformat()} is more than "
            f"{HISTORICAL_EVIDENCE_STALENESS_DAYS} days before M070.as_of="
            f"{m070_as_of.isoformat()}"
        )
        return HistoricalEvidenceCompatibilityStatus.STALE, tuple(reasons), coverage_end, ()

    # U1 / U2: universe compatibility.
    #
    # U1: every M070 requested symbol must be represented in the UNION
    #     of M064 *evaluated* instruments across the whole study. The
    #     evaluated set is what the M064 study actually exercised for
    #     that window; if no window ever evaluated a symbol, the M064
    #     study has no real evidence about that symbol's behaviour.
    #
    # U2: at least one M064 window's *eligible* set must be a superset
    #     of the complete M070 requested universe. The eligible set is
    #     the membership-gated scope the M064 study was *allowed* to
    #     consider. Using the evaluated set for U2 would be wrong: a
    #     window can evaluate a strict subset of its eligible universe
    #     (e.g. only the names that cleared a momentum gate), yet
    #     still legitimately prove that the study was *authorised* to
    #     consider the full M070 requested_universe.
    #
    # These are therefore resolved separately:
    #   evaluated_symbols -> U1 only
    #   eligible_symbols   -> U2 + matched_window_resolved_eligible_symbols
    requested = set(m070_requested_universe)
    if not requested:
        reasons.append("M070 requested_universe is empty")
        return HistoricalEvidenceCompatibilityStatus.INCOMPATIBLE, tuple(reasons), coverage_end, ()

    union_evaluated_symbols: set[str] = set()
    matched_window_resolved: tuple[str, ...] = ()
    for window in survivorship_study.window_results:
        evaluated_symbols = _resolve_symbols(
            window.snapshot.evaluated_instrument_ids, instrument_master
        )
        eligible_symbols = _resolve_symbols(
            window.snapshot.eligible_instrument_ids, instrument_master
        )
        # U1: feed the union from EVALUATED only.
        union_evaluated_symbols.update(evaluated_symbols)
        # U2: pick the first window whose ELIGIBLE set is a superset.
        if not matched_window_resolved and set(eligible_symbols).issuperset(requested):
            matched_window_resolved = eligible_symbols
    missing_union = requested - union_evaluated_symbols
    if missing_union:
        reasons.append(
            f"M070 requested_universe symbols not represented in any M064 evaluated set: "
            f"{sorted(missing_union)}"
        )
        return HistoricalEvidenceCompatibilityStatus.INCOMPATIBLE, tuple(reasons), coverage_end, ()

    if not matched_window_resolved:
        reasons.append(
            f"no M064 window's eligible symbol set is a superset of M070 "
            f"requested_universe={sorted(requested)}"
        )
        return HistoricalEvidenceCompatibilityStatus.INCOMPATIBLE, tuple(reasons), coverage_end, ()

    return (
        HistoricalEvidenceCompatibilityStatus.COMPATIBLE,
        (),
        coverage_end,
        matched_window_resolved,
    )


def _build_summary(
    *,
    survivorship_study: SurvivorshipAwareRobustnessStudy,
    coverage_end: datetime,
    matched_window_resolved: tuple[str, ...],
    portfolio_report: PortfolioEvidenceReport | None,
    status: HistoricalEvidenceCompatibilityStatus,
    reasons: tuple[str, ...],
    is_selected: bool,
) -> HistoricalPortfolioEvidence:
    return HistoricalPortfolioEvidence(
        survivorship_study_identity_runtime=str(survivorship_study.identity.runtime_id),
        survivorship_study_identity_governance=str(survivorship_study.identity.governance_id),
        survivorship_study_window_count=survivorship_study.window_count,
        survivorship_study_total_executed_trade_count=survivorship_study.total_executed_trade_count,
        survivorship_study_all_window_net_pnl_total=str(
            survivorship_study.all_window_net_pnl_total
        ),
        survivorship_study_classification=survivorship_study.classification.value,
        survivorship_study_dataset_bundle_id=str(survivorship_study.dataset_bundle_id),
        survivorship_study_dataset_bundle_sha256=survivorship_study.dataset_bundle_sha256,
        survivorship_study_universe_id=survivorship_study.universe_id,
        survivorship_study_universe_version=survivorship_study.universe_version,
        survivorship_study_universe_membership_model=survivorship_study.universe_membership_model,
        survivorship_study_supplied_account_equity=str(survivorship_study.supplied_account_equity),
        survivorship_study_supplied_risk_percent=str(survivorship_study.supplied_risk_percent),
        survivorship_study_stress_comparison=str(
            survivorship_study.current_universe_bias_stress.comparison.value
        ),
        coverage_end=coverage_end,
        matched_window_resolved_eligible_symbols=matched_window_resolved,
        portfolio_study_identity_governance=(
            str(portfolio_report.identity.governance_id) if portfolio_report is not None else None
        ),
        portfolio_study_allocated_count=(
            portfolio_report.allocated_count if portfolio_report is not None else None
        ),
        portfolio_study_realized_pnl=(
            str(portfolio_report.realized_pnl) if portfolio_report is not None else None
        ),
        portfolio_study_initial_capital=(
            str(portfolio_report.capital_policy.initial_capital)
            if portfolio_report is not None
            else None
        ),
        portfolio_study_currency=(
            portfolio_report.capital_policy.currency if portfolio_report is not None else None
        ),
        portfolio_study_max_concurrent_positions=(
            portfolio_report.capital_policy.max_concurrent_positions
            if portfolio_report is not None
            else None
        ),
        portfolio_study_max_capital_utilization_percent=(
            str(portfolio_report.capital_policy.max_capital_utilization_percent)
            if portfolio_report is not None
            else None
        ),
        compatibility_status=status,
        compatibility_reasons=reasons,
        is_selected=is_selected,
    )


def find_compatible_historical_evidence(
    *,
    m070_strategy_id: str | None,
    m070_strategy_version: str | None,
    m070_ranking_model_id: str | None,
    m070_ranking_model_version: str | None,
    m070_risk_policy_id: str | None,
    m070_risk_policy_version: str | None,
    m070_sizing_policy_id: str | None,
    m070_sizing_policy_version: str | None,
    m070_requested_universe: tuple[str, ...],
    m070_as_of: datetime,
    survivorship_candidates: tuple[SurvivorshipAwareRobustnessStudy, ...],
    portfolio_lookup: dict[str, PortfolioEvidenceReport],
    instrument_master: InstrumentMaster | None,
) -> tuple[HistoricalPortfolioEvidence, ...]:
    """Pure function. Takes M070 session policy identities + a set of
    M064 candidate studies + a portfolio-by-M064-runtime-id lookup +
    an optional instrument master. Returns a deterministically ordered
    tuple of HistoricalPortfolioEvidence summaries.

    Ordering is by `coverage_end` DESC (latest historical coverage
    first). Deterministic tiebreak: runtime_id ASC (a frozen,
    non-chronological identity tiebreaker -- never claimed to be
    chronological).

    M067 lookup is via `portfolio_lookup` keyed by M064
    `runtime_id`. If a portfolio report's source_study_runtime_id
    does not match the M064 candidate's runtime_id, it is
    silently dropped (lineage integrity, rule L). The M074 query
    adapter is responsible for keying the lookup correctly; the
    pure compatibility rule still validates lineage here, because
    a malicious or buggy caller (or a miskeyed adapter) must not
    cause an M067 report from study B to be attributed to study A.
    """
    summaries: list[HistoricalPortfolioEvidence] = []
    for study in survivorship_candidates:
        status, reasons, coverage_end, matched = _evaluate_compatibility(
            survivorship_study=study,
            m070_strategy_id=m070_strategy_id,
            m070_strategy_version=m070_strategy_version,
            m070_ranking_model_id=m070_ranking_model_id,
            m070_ranking_model_version=m070_ranking_model_version,
            m070_risk_policy_id=m070_risk_policy_id,
            m070_risk_policy_version=m070_risk_policy_version,
            m070_sizing_policy_id=m070_sizing_policy_id,
            m070_sizing_policy_version=m070_sizing_policy_version,
            m070_requested_universe=m070_requested_universe,
            m070_as_of=m070_as_of,
            instrument_master=instrument_master,
        )
        raw_report = portfolio_lookup.get(str(study.identity.runtime_id))
        # Rule L (lineage integrity). The M067 portfolio report carries
        # its own `source_study_runtime_id` field, which is the M074-
        # recognized FK back to the originating M064 study. Even if
        # `portfolio_lookup` keys a report under this study's runtime_id,
        # the report's own source_study_runtime_id is the truth. If it
        # doesn't match this study's runtime_id, the report belongs to a
        # different M064 study -- it is silently dropped. The M064
        # evidence is still surfaced; only the M067 attachment is omitted.
        if raw_report is not None and str(raw_report.source_study_runtime_id) == str(
            study.identity.runtime_id
        ):
            report = raw_report
        else:
            report = None
        summaries.append(
            _build_summary(
                survivorship_study=study,
                coverage_end=coverage_end,
                matched_window_resolved=matched,
                portfolio_report=report,
                status=status,
                reasons=reasons,
                is_selected=False,
            )
        )

    # Sort: COMPATIBLE items first (ordered by coverage_end DESC, then
    # runtime_id ASC as a deterministic tiebreak), then everything else
    # (also by coverage_end DESC, then runtime_id ASC). We use a single
    # sort key tuple. We do NOT use coverage_end.timestamp() (Windows
    # rejects datetime.min / pre-epoch datetimes).
    compat = [
        s
        for s in summaries
        if s.compatibility_status is HistoricalEvidenceCompatibilityStatus.COMPATIBLE
    ]
    other = [
        s
        for s in summaries
        if s.compatibility_status is not HistoricalEvidenceCompatibilityStatus.COMPATIBLE
    ]
    compat.sort(
        key=lambda s: (s.coverage_end, s.survivorship_study_identity_runtime), reverse=False
    )
    other.sort(key=lambda s: (s.coverage_end, s.survivorship_study_identity_runtime), reverse=False)
    # coverage_end DESC means we want the LATEST first. Tuples in Python
    # sort ascending by default, but for the date we want DESC. We
    # achieve this with reverse=True on the date, then ASC on the id,
    # by sorting in two steps.
    compat.sort(key=lambda s: s.coverage_end, reverse=True)
    # Within equal coverage, runtime_id ASC is the natural tiebreak (the
    # sort is stable in Python).
    other.sort(key=lambda s: s.coverage_end, reverse=True)
    ordered = compat + other

    selected_count = 0
    final: list[HistoricalPortfolioEvidence] = []
    for summary in ordered:
        if (
            summary.compatibility_status is HistoricalEvidenceCompatibilityStatus.COMPATIBLE
            and selected_count == 0
        ):
            summary = replace(summary, is_selected=True)
            selected_count += 1
        final.append(summary)
    return tuple(final)
