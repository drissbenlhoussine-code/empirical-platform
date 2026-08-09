"""Trading opportunity scan: multiple M057 evaluations, ranked.

MILESTONE-058. A scan does not invent a parallel trading algorithm -- every
instrument in its universe is evaluated through the unmodified, frozen M057
`strategy.evaluate()` function (see `usecases/run_trading_opportunity_scan.py`
for the orchestration). This module owns exactly two things `strategy.py`
does not: universe consistency validation (Phase 3/14 -- same interval, same
evaluation cutoff, no duplicate instrument) and assembling the ranked,
persisted result from a set of already-computed `EvaluationOutcome`s.

`TradingOpportunityScan` is, like `DecisionCandidate`, deliberately NOT a
lifecycle aggregate: a scan is a fact computed once from a fixed universe of
inputs and never mutated afterward.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from empirical_platform.decision_candidate.market_data import Instrument, ObservationWindow
from empirical_platform.decision_candidate.ranking import (
    RANKING_MODEL_ID,
    RANKING_MODEL_VERSION,
    compute_ranking_score,
    rank_sort_key,
)
from empirical_platform.decision_candidate.strategy import (
    EvaluationMeasurements,
    EvaluationOutcome,
    EvaluationReasonCode,
    TradingDecision,
)
from empirical_platform.identifiers.pairs import DomainIdentity
from empirical_platform.identifiers.types import (
    DecisionCandidateId,
    EvidencePackageId,
    TradingOpportunityScanId,
)


def validate_scan_universe(windows: Sequence[ObservationWindow]) -> None:
    """Reject a malformed multi-instrument scan universe before any
    evaluation is attempted.

    A scan universe must contain at least one window; every window must
    share the same bar interval and the same evaluation cutoff (the
    evaluation bar's own timestamp); and no instrument may appear twice.
    Raises `ValueError` describing the first violation found.
    """
    if len(windows) < 1:
        raise ValueError("a scan universe must contain at least 1 instrument")
    first = windows[0]
    seen_instruments: set[Instrument] = set()
    for window in windows:
        if window.interval != first.interval:
            raise ValueError(
                "all windows in a scan universe must share one bar interval: "
                f"{window.instrument} has {window.interval}, expected {first.interval}"
            )
        if window.evaluation_bar.timestamp != first.evaluation_bar.timestamp:
            raise ValueError(
                "all windows in a scan universe must share one evaluation cutoff: "
                f"{window.instrument} has {window.evaluation_bar.timestamp}, "
                f"expected {first.evaluation_bar.timestamp}"
            )
        if window.instrument in seen_instruments:
            raise ValueError(f"duplicate instrument in scan universe: {window.instrument}")
        seen_instruments.add(window.instrument)


@dataclass(frozen=True, slots=True)
class ScanEvaluationEntry:
    """One instrument's evaluation result within a scan, in universe
    (caller-supplied) order.

    `rank`/`score` are set (1-based rank, computed score) if and only if
    `decision` is `LONG_CANDIDATE`; both are `None` for `NO_TRADE` --
    NO_TRADE evaluations remain fully present and explained here, but are
    never ranked (see MILESTONE-058 scope Section 6).
    """

    instrument: Instrument
    decision_candidate_id: DecisionCandidateId
    decision: TradingDecision
    measurements: EvaluationMeasurements
    reasons: tuple[EvaluationReasonCode, ...]
    rank: int | None
    score: Decimal | None

    def __post_init__(self) -> None:
        is_long_candidate = self.decision is TradingDecision.LONG_CANDIDATE
        if is_long_candidate and (self.rank is None or self.score is None):
            raise ValueError("a LONG_CANDIDATE entry must carry both rank and score")
        if not is_long_candidate and (self.rank is not None or self.score is not None):
            raise ValueError("a NO_TRADE entry must carry neither rank nor score")


@dataclass(frozen=True, slots=True)
class TradingOpportunityScan:
    """One immutable, persisted, independently-auditable trading opportunity
    scan: every instrument in one universe, evaluated at one common cutoff
    under one strategy version, with legitimate candidates deterministically
    ranked under one ranking-model version.
    """

    identity: DomainIdentity[TradingOpportunityScanId]
    target_evidence_package_id: EvidencePackageId
    strategy_id: str
    strategy_version: str
    ranking_model_id: str
    ranking_model_version: str
    evaluation_cutoff: datetime
    evaluations: tuple[ScanEvaluationEntry, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.identity, DomainIdentity):
            raise TypeError("identity must be a DomainIdentity[TradingOpportunityScanId]")
        if not isinstance(self.identity.governance_id, TradingOpportunityScanId):
            raise TypeError("identity governance_id must be a TradingOpportunityScanId")
        if not isinstance(self.target_evidence_package_id, EvidencePackageId):
            raise TypeError("target_evidence_package_id must be an EvidencePackageId")
        if not isinstance(self.evaluation_cutoff, datetime):
            raise TypeError("evaluation_cutoff must be a datetime")
        if self.evaluation_cutoff.tzinfo is None:
            raise ValueError("evaluation_cutoff must be timezone-aware")
        if not self.strategy_id.strip():
            raise ValueError("strategy_id must be non-empty")
        if not self.strategy_version.strip():
            raise ValueError("strategy_version must be non-empty")
        if not self.ranking_model_id.strip():
            raise ValueError("ranking_model_id must be non-empty")
        if not self.ranking_model_version.strip():
            raise ValueError("ranking_model_version must be non-empty")
        if len(self.evaluations) < 1:
            raise ValueError("a TradingOpportunityScan must evaluate at least 1 instrument")
        ranks = sorted(e.rank for e in self.evaluations if e.rank is not None)
        expected_ranks = list(range(1, len(ranks) + 1))
        if ranks != expected_ranks:
            raise ValueError(
                "ranked entries must form a contiguous 1..N sequence with no gaps or "
                f"duplicates; got {ranks}"
            )

    @property
    def total_instruments(self) -> int:
        """Total number of instruments evaluated in this scan."""
        return len(self.evaluations)

    @property
    def candidate_count(self) -> int:
        """Number of LONG_CANDIDATE evaluations in this scan."""
        return sum(1 for e in self.evaluations if e.decision is TradingDecision.LONG_CANDIDATE)

    @property
    def no_trade_count(self) -> int:
        """Number of NO_TRADE evaluations in this scan."""
        return sum(1 for e in self.evaluations if e.decision is TradingDecision.NO_TRADE)

    @property
    def ranked_opportunities(self) -> tuple[ScanEvaluationEntry, ...]:
        """LONG_CANDIDATE entries only, ordered by rank ascending (rank 1 first)."""
        ranked = [e for e in self.evaluations if e.decision is TradingDecision.LONG_CANDIDATE]
        ranked.sort(key=lambda e: e.rank if e.rank is not None else 0)
        return tuple(ranked)


def build_scan(
    *,
    identity: DomainIdentity[TradingOpportunityScanId],
    target_evidence_package_id: EvidencePackageId,
    strategy_id: str,
    strategy_version: str,
    evaluation_cutoff: datetime,
    universe: Sequence[tuple[Instrument, DecisionCandidateId, EvaluationOutcome]],
) -> TradingOpportunityScan:
    """Assemble one ranked `TradingOpportunityScan` from already-computed
    per-instrument evaluation outcomes, in the caller's own universe order.

    `universe` entries must already have been produced by the unmodified
    M057 `strategy.evaluate()` -- this function performs no evaluation of
    its own, only ranking and assembly. Ranks are assigned by sorting the
    LONG_CANDIDATE subset via `ranking.rank_sort_key` (score descending,
    instrument symbol ascending on ties); NO_TRADE entries never receive a
    rank or score.
    """
    scored: list[tuple[Instrument, DecisionCandidateId, EvaluationOutcome, Decimal | None]] = []
    for instrument, candidate_id, outcome in universe:
        score = (
            compute_ranking_score(outcome.measurements)
            if outcome.decision is TradingDecision.LONG_CANDIDATE
            else None
        )
        scored.append((instrument, candidate_id, outcome, score))

    long_candidates = [item for item in scored if item[3] is not None]
    long_candidates.sort(key=lambda item: rank_sort_key(item[3], item[0]))  # type: ignore[arg-type]
    rank_by_candidate_id = {
        candidate_id: rank for rank, (_, candidate_id, _, _) in enumerate(long_candidates, start=1)
    }

    evaluations = tuple(
        ScanEvaluationEntry(
            instrument=instrument,
            decision_candidate_id=candidate_id,
            decision=outcome.decision,
            measurements=outcome.measurements,
            reasons=outcome.reasons,
            rank=rank_by_candidate_id.get(candidate_id),
            score=score,
        )
        for instrument, candidate_id, outcome, score in scored
    )

    return TradingOpportunityScan(
        identity=identity,
        target_evidence_package_id=target_evidence_package_id,
        strategy_id=strategy_id,
        strategy_version=strategy_version,
        ranking_model_id=RANKING_MODEL_ID,
        ranking_model_version=RANKING_MODEL_VERSION,
        evaluation_cutoff=evaluation_cutoff,
        evaluations=evaluations,
    )
