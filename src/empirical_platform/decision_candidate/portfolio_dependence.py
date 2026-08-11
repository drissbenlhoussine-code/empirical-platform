"""Cross-instrument dependence / correlation-aware portfolio risk domain.

MILESTONE-068. A `PortfolioDependenceReport` is a post-hoc, read-only
statistical evaluation of cross-instrument return dependence among the
instruments an already-frozen M067 `PortfolioEvidenceReport` actually
held *concurrently* open. It never re-runs, re-allocates, or optimizes
anything upstream -- it only asks: when several concurrently-held
positions look diversified by capital weight alone, does their
historical price dependence tell a different story?

This is historical risk EVIDENCE, not portfolio optimization, not
forecasting, not hedging, and not live risk management. See
`MILESTONE_068_CROSS_INSTRUMENT_DEPENDENCE_CORRELATION_AWARE_PORTFOLIO_RISK_EVIDENCE_AND_CONCENTRATED_EXPOSURE_FIREWALL_SCOPE_AND_DESIGN.md`
for the full design rationale.

Return series are simple arithmetic returns (`(close_t - close_{t-1}) /
close_{t-1}`) over the same per-instrument bar grid the source M064/M065
dataset bundle already declares -- the smallest, most transparent choice
available, deliberately avoiding a second, harder-to-audit convention
(e.g. log returns) the rest of this codebase has never needed. Pairwise
Pearson correlation is computed only over bars strictly at or before each
estimation cutoff, using the frozen, explicit `DependenceEstimationPolicy`
lookback -- never a lookahead, never a search over lookback lengths.

Concurrent exposure is derived directly from the real M067 event
timeline: dependence is evaluated only among instruments the portfolio
genuinely held open at the same historical instant, never between
positions that merely both existed in the same study but never
overlapped in time.

FALSE_DIVERSIFICATION_FIREWALL_LIMITATIONS is persisted verbatim on
every report, mirroring the M066 false-confidence-firewall precedent:
historical correlation is not future correlation, low observed
correlation is not guaranteed diversification, negative correlation is
not a guaranteed hedge, and dependence evidence is not an optimal
allocation or a profitability claim.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum

from empirical_platform.decision_candidate.historical_backtest import HistoricalInstrumentSeries
from empirical_platform.decision_candidate.portfolio_study import (
    PortfolioAllocationOutcome,
    PortfolioEvidenceReport,
)
from empirical_platform.identifiers.pairs import DomainIdentity
from empirical_platform.identifiers.types import PortfolioDependenceReportId

_RATIO_QUANT = Decimal("0.0001")

#: Explicit, conservative classification bands over
#: `peak_dependence_aware_concentration` -- descriptive only, never a
#: safety/optimality claim (mission Phase 18).
_LOW_DEPENDENCE_CEILING = Decimal("0.40")
_MIXED_DEPENDENCE_CEILING = Decimal("0.70")

#: A pairwise correlation delta between the first-half and second-half
#: of one estimation window larger than this is reported as instability
#: (mission Phase 19). Explicit, not searched.
_INSTABILITY_THRESHOLD = Decimal("0.30")


class PairDependenceStatus(StrEnum):
    """Closed vocabulary for one pairwise dependence computation's own
    outcome. Never silently defaulted to a numeric value when undefined
    (mission Phase 14: "Do not return fake 0 correlation")."""

    DEFINED = "DEFINED"
    INSUFFICIENT_OBSERVATIONS = "INSUFFICIENT_OBSERVATIONS"
    UNDEFINED_ZERO_VARIANCE = "UNDEFINED_ZERO_VARIANCE"


class DependenceEvidenceClassification(StrEnum):
    """Conservative, deterministic, descriptive-only classification.
    Deliberately never worded as a safety/optimality claim -- see
    `FALSE_DIVERSIFICATION_FIREWALL_LIMITATIONS`."""

    INSUFFICIENT_DEPENDENCE_EVIDENCE = "INSUFFICIENT_DEPENDENCE_EVIDENCE"
    LOW_OBSERVED_DEPENDENCE = "LOW_OBSERVED_DEPENDENCE"
    MIXED_OBSERVED_DEPENDENCE = "MIXED_OBSERVED_DEPENDENCE"
    HIGH_OBSERVED_DEPENDENCE = "HIGH_OBSERVED_DEPENDENCE"


#: Persisted verbatim on every report (mission Phase 31: mandatory claim
#: -honesty invariants). Never conditionally omitted.
FALSE_DIVERSIFICATION_FIREWALL_LIMITATIONS: tuple[str, ...] = (
    "Historical correlation does not imply future correlation.",
    "Low observed correlation does not guarantee actual diversification.",
    "Negative observed correlation does not guarantee a hedge.",
    "Dependence evidence does not identify or imply an optimal allocation.",
    "This report is not evidence of profitability.",
    "This report is not evidence of live-trading readiness.",
)


@dataclass(frozen=True, slots=True)
class DependenceEstimationPolicy:
    """Explicit, versioned, immutable estimation authority. No field
    here may ever be silently defaulted at the point of use -- every
    report persists the exact policy that produced it. No lookback
    search: exactly one predeclared window is ever used (mission Phase
    16)."""

    policy_id: str
    version: str
    lookback_bar_count: int
    minimum_overlapping_observations: int

    def __post_init__(self) -> None:
        if not self.policy_id.strip():
            raise ValueError("policy_id must be non-empty")
        if not self.version.strip():
            raise ValueError("version must be non-empty")
        if self.lookback_bar_count < 3:
            raise ValueError("lookback_bar_count must be at least 3")
        if self.minimum_overlapping_observations < 2:
            raise ValueError("minimum_overlapping_observations must be at least 2")
        if self.minimum_overlapping_observations > self.lookback_bar_count:
            raise ValueError("minimum_overlapping_observations must not exceed lookback_bar_count")


DEFAULT_DEPENDENCE_ESTIMATION_POLICY = DependenceEstimationPolicy(
    policy_id="DEPENDENCE-ESTIMATION-DEFAULT",
    version="1",
    lookback_bar_count=20,
    minimum_overlapping_observations=10,
)


@dataclass(frozen=True, slots=True)
class PairwiseDependenceEvidence:
    """One immutable pairwise historical dependence computation.
    Canonically ordered (`instrument_a <= instrument_b` lexicographically)
    so `(A, B)` and `(B, A)` are always the same one persisted record
    (mission Phase 8: no duplicate semantic pairs)."""

    instrument_a: str
    instrument_b: str
    observation_count: int
    estimation_start: datetime
    estimation_end: datetime
    correlation: Decimal | None
    status: PairDependenceStatus

    def __post_init__(self) -> None:
        if not self.instrument_a.strip() or not self.instrument_b.strip():
            raise ValueError("instrument_a/instrument_b must be non-empty")
        if self.instrument_a > self.instrument_b:
            raise ValueError("instrument_a must be <= instrument_b (canonical pair order)")
        if self.observation_count < 0:
            raise ValueError("observation_count must be non-negative")
        if self.estimation_start.tzinfo is None or self.estimation_end.tzinfo is None:
            raise ValueError("estimation_start/estimation_end must be timezone-aware")
        if self.estimation_end < self.estimation_start:
            raise ValueError("estimation_end must not precede estimation_start")
        if self.status is PairDependenceStatus.DEFINED:
            if self.correlation is None:
                raise ValueError("a DEFINED pair must carry a correlation value")
            if not (Decimal("-1") <= self.correlation <= Decimal("1")):
                raise ValueError("correlation must be in [-1, 1]")
        elif self.correlation is not None:
            raise ValueError("a non-DEFINED pair must not carry a correlation value")


@dataclass(frozen=True, slots=True)
class ConcurrentExposureState:
    """One immutable snapshot of genuinely concurrent open exposure,
    derived directly from the real M067 event timeline -- never from
    positions that merely coexist in the same study without ever
    overlapping in time (mission Phase 9)."""

    state_sequence: int
    as_of_timestamp: datetime
    open_instruments: tuple[str, ...]
    weights: tuple[Decimal, ...]
    nominal_concentration: Decimal
    dependence_aware_concentration: Decimal | None
    undefined_pair_count: int

    def __post_init__(self) -> None:
        if self.state_sequence < 1:
            raise ValueError("state_sequence must be at least 1")
        if self.as_of_timestamp.tzinfo is None:
            raise ValueError("as_of_timestamp must be timezone-aware")
        if len(self.open_instruments) != len(self.weights):
            raise ValueError("open_instruments and weights must be the same length")
        if not self.open_instruments:
            raise ValueError("a concurrent exposure state must have at least 1 open instrument")
        if self.nominal_concentration < 0 or self.nominal_concentration > 1:
            raise ValueError("nominal_concentration must be in [0, 1]")
        if self.dependence_aware_concentration is not None and (
            self.dependence_aware_concentration < 0 or self.dependence_aware_concentration > 1
        ):
            raise ValueError("dependence_aware_concentration must be in [0, 1] when defined")
        if self.undefined_pair_count < 0:
            raise ValueError("undefined_pair_count must be non-negative")


@dataclass(frozen=True, slots=True)
class ConcentrationStressResult:
    """Diagnostic-only comparison: canonical peak dependence-aware
    concentration vs. the same portfolio under a deliberately assumed
    perfect-correlation stress. Never alters the canonical M067
    allocation or the canonical concentration figures (mission Phase
    20)."""

    canonical_peak_dependence_aware_concentration: Decimal | None
    stressed_perfect_correlation_concentration: Decimal | None


@dataclass(frozen=True, slots=True)
class PortfolioDependenceReport:
    """One immutable, persisted, post-hoc cross-instrument dependence
    evaluation of one already-frozen M067 portfolio study. A fact
    computed once, never mutated -- mirrors every other M061-M067
    study/result record in this codebase."""

    identity: DomainIdentity[PortfolioDependenceReportId]

    # Upstream authority lineage -- copied verbatim from the source
    # M067 report, never independently re-derived (mission Phase 4).
    source_portfolio_study_governance_id: str
    source_portfolio_study_runtime_id: str
    source_study_governance_id: str
    source_study_runtime_id: str
    dataset_bundle_id: str
    dataset_bundle_version: str
    dataset_bundle_sha256: str
    dataset_source_kind: str
    capital_policy_id: str
    capital_policy_version: str

    estimation_policy: DependenceEstimationPolicy

    instrument_count: int
    pair_count: int
    defined_pair_count: int
    undefined_pair_count: int

    highest_pair_a: str | None
    highest_pair_b: str | None
    highest_pair_correlation: Decimal | None
    lowest_pair_a: str | None
    lowest_pair_b: str | None
    lowest_pair_correlation: Decimal | None

    concurrent_exposure_state_count: int
    peak_nominal_concentration: Decimal | None
    peak_dependence_aware_concentration: Decimal | None

    correlation_instability_observed: bool
    max_window_instability_delta: Decimal | None

    concentration_stress: ConcentrationStressResult

    pairwise_dependence: tuple[PairwiseDependenceEvidence, ...]
    concurrent_exposure_states: tuple[ConcurrentExposureState, ...]

    classification: DependenceEvidenceClassification
    limitations: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.identity, DomainIdentity):
            raise TypeError("identity must be a DomainIdentity[PortfolioDependenceReportId]")
        if not isinstance(self.identity.governance_id, PortfolioDependenceReportId):
            raise TypeError("identity governance_id must be a PortfolioDependenceReportId")
        for field_name in (
            "source_portfolio_study_governance_id",
            "source_portfolio_study_runtime_id",
            "source_study_governance_id",
            "source_study_runtime_id",
            "dataset_bundle_id",
            "dataset_bundle_version",
            "dataset_bundle_sha256",
            "dataset_source_kind",
            "capital_policy_id",
            "capital_policy_version",
        ):
            if not getattr(self, field_name).strip():
                raise ValueError(f"{field_name} must be non-empty")
        if self.instrument_count < 0:
            raise ValueError("instrument_count must be non-negative")
        if self.pair_count < 0:
            raise ValueError("pair_count must be non-negative")
        if self.defined_pair_count + self.undefined_pair_count != self.pair_count:
            raise ValueError("defined_pair_count + undefined_pair_count must equal pair_count")
        if len(self.pairwise_dependence) != self.pair_count:
            raise ValueError("pairwise_dependence length must equal pair_count")
        if len(self.concurrent_exposure_states) != self.concurrent_exposure_state_count:
            raise ValueError(
                "concurrent_exposure_states length must equal concurrent_exposure_state_count"
            )
        if tuple(self.limitations) != FALSE_DIVERSIFICATION_FIREWALL_LIMITATIONS:
            raise ValueError(
                "limitations must be exactly FALSE_DIVERSIFICATION_FIREWALL_LIMITATIONS"
            )


def _quantize_ratio(value: Decimal) -> Decimal:
    return value.quantize(_RATIO_QUANT, rounding=ROUND_HALF_UP)


def _simple_returns(
    bars_by_timestamp: tuple[tuple[datetime, Decimal], ...],
) -> dict[datetime, Decimal]:
    """Simple arithmetic returns keyed by the *later* bar's own
    timestamp, computed strictly from consecutive, already-chronological
    closes -- `(close_t - close_{t-1}) / close_{t-1}`."""
    returns: dict[datetime, Decimal] = {}
    for (_prev_ts, prev_close), (ts, close) in zip(
        bars_by_timestamp, bars_by_timestamp[1:], strict=False
    ):
        if prev_close == 0:
            continue
        returns[ts] = (close - prev_close) / prev_close
    return returns


def _derive_return_series(
    series: HistoricalInstrumentSeries, *, as_of: datetime, lookback_bar_count: int
) -> dict[datetime, Decimal]:
    """Simple returns for one instrument, using only bars with
    `timestamp <= as_of` (mission Phase 6: temporal firewall -- a future
    bar can never affect an earlier estimation cutoff's own evidence),
    restricted to the most recent `lookback_bar_count` bars at or before
    that cutoff. No forward-filling of missing bars (mission Phase 5)."""
    eligible_bars = tuple(
        (bar.timestamp, bar.close) for bar in series.bars if bar.timestamp <= as_of
    )
    windowed_bars = eligible_bars[-(lookback_bar_count + 1) :] if eligible_bars else ()
    return _simple_returns(windowed_bars)


def _pearson_correlation(
    returns_a: dict[datetime, Decimal],
    returns_b: dict[datetime, Decimal],
    *,
    minimum_overlapping_observations: int,
) -> tuple[Decimal | None, int, PairDependenceStatus]:
    """Deterministic Pearson correlation over the timestamp-aligned
    intersection of two return series -- no forward-filling, no
    fabricated alignment (mission Phase 5/15)."""
    shared_timestamps = sorted(set(returns_a) & set(returns_b))
    n = len(shared_timestamps)
    if n < minimum_overlapping_observations:
        return None, n, PairDependenceStatus.INSUFFICIENT_OBSERVATIONS

    xs = tuple(returns_a[ts] for ts in shared_timestamps)
    ys = tuple(returns_b[ts] for ts in shared_timestamps)
    mean_x = sum(xs, Decimal("0")) / n
    mean_y = sum(ys, Decimal("0")) / n
    cov = sum(((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys, strict=True)), Decimal("0"))
    var_x = sum(((x - mean_x) ** 2 for x in xs), Decimal("0"))
    var_y = sum(((y - mean_y) ** 2 for y in ys), Decimal("0"))
    if var_x == 0 or var_y == 0:
        return None, n, PairDependenceStatus.UNDEFINED_ZERO_VARIANCE

    correlation = cov / (var_x.sqrt() * var_y.sqrt())
    # Clamp only for floating-point-style rounding noise at the exact
    # mathematical boundary -- never to hide a genuine out-of-range
    # result, which would itself indicate a real defect.
    correlation = max(Decimal("-1"), min(Decimal("1"), correlation))
    return _quantize_ratio(correlation), n, PairDependenceStatus.DEFINED


def build_pairwise_dependence(
    series_by_instrument: dict[str, HistoricalInstrumentSeries],
    *,
    as_of: datetime,
    policy: DependenceEstimationPolicy,
) -> tuple[PairwiseDependenceEvidence, ...]:
    """Build one canonically-ordered, deterministic pairwise dependence
    record for every instrument pair (including the diagonal, `A == A`)
    among the supplied instruments -- order-independent of the caller's
    own dict iteration order (mission Phase 8/23)."""
    symbols = sorted(series_by_instrument)
    returns_by_symbol = {
        symbol: _derive_return_series(
            series_by_instrument[symbol], as_of=as_of, lookback_bar_count=policy.lookback_bar_count
        )
        for symbol in symbols
    }
    pairs: list[PairwiseDependenceEvidence] = []
    for i, symbol_a in enumerate(symbols):
        for symbol_b in symbols[i:]:
            correlation, n, status = _pearson_correlation(
                returns_by_symbol[symbol_a],
                returns_by_symbol[symbol_b],
                minimum_overlapping_observations=policy.minimum_overlapping_observations,
            )
            shared = sorted(set(returns_by_symbol[symbol_a]) & set(returns_by_symbol[symbol_b]))
            start = shared[0] if shared else as_of
            end = shared[-1] if shared else as_of
            pairs.append(
                PairwiseDependenceEvidence(
                    instrument_a=symbol_a,
                    instrument_b=symbol_b,
                    observation_count=n,
                    estimation_start=start,
                    estimation_end=end,
                    correlation=correlation,
                    status=status,
                )
            )
    return tuple(pairs)


def _lookup_pair(
    pairs_by_key: dict[tuple[str, str], PairwiseDependenceEvidence], symbol_a: str, symbol_b: str
) -> PairwiseDependenceEvidence | None:
    key = (symbol_a, symbol_b) if symbol_a <= symbol_b else (symbol_b, symbol_a)
    return pairs_by_key.get(key)


def _dependence_weighted_concentration(
    open_instruments: tuple[str, ...],
    weights: tuple[Decimal, ...],
    pairs_by_key: dict[tuple[str, str], PairwiseDependenceEvidence],
) -> tuple[Decimal | None, int]:
    """`w' C w` using the pairwise correlation matrix `C` as the
    dependence weighting -- no expected returns anywhere (mission Phase
    10). An undefined pair is conservatively treated as correlation =
    1.0 for this weighting only (never silently assumed independent,
    which would understate concentration risk) -- documented explicitly
    in the report's own limitations."""
    undefined_count = 0
    total = Decimal("0")
    for i, symbol_a in enumerate(open_instruments):
        for j, symbol_b in enumerate(open_instruments):
            if i == j:
                correlation = Decimal("1")
            else:
                pair = _lookup_pair(pairs_by_key, symbol_a, symbol_b)
                if pair is None or pair.correlation is None:
                    correlation = Decimal("1")
                    if j > i:
                        undefined_count += 1
                else:
                    correlation = pair.correlation
            total += weights[i] * weights[j] * correlation
    if total < 0:
        total = Decimal("0")
    if total > 1:
        total = Decimal("1")
    return _quantize_ratio(total), undefined_count


def build_concurrent_exposure_states(
    portfolio: PortfolioEvidenceReport,
    pairwise_by_cutoff: dict[datetime, tuple[PairwiseDependenceEvidence, ...]],
) -> tuple[ConcurrentExposureState, ...]:
    """Derive genuinely concurrent exposure states directly from the
    real M067 event timeline: at every OPEN instant of an allocated
    position, determine every other allocated position whose own
    `[entry_timestamp, exit_timestamp]` interval covers that same
    instant (mission Phase 9). Positions that never overlap in real time
    are never treated as simultaneous exposure."""
    allocated = tuple(
        d
        for d in portfolio.allocation_decisions
        if d.decision is PortfolioAllocationOutcome.ALLOCATED
    )
    states: list[ConcurrentExposureState] = []
    open_instants = sorted({d.entry_timestamp for d in allocated})
    for sequence, instant in enumerate(open_instants, start=1):
        concurrent = tuple(d for d in allocated if d.entry_timestamp <= instant <= d.exit_timestamp)
        if len(concurrent) < 1:
            continue
        total_risk = sum((d.risk_amount for d in concurrent), Decimal("0"))
        if total_risk <= 0:
            continue
        open_instruments = tuple(d.instrument_symbol for d in concurrent)
        weights = tuple(_quantize_ratio(d.risk_amount / total_risk) for d in concurrent)
        nominal_concentration = _quantize_ratio(sum((w**2 for w in weights), Decimal("0")))

        pairwise = pairwise_by_cutoff.get(instant, ())
        pairs_by_key = {(p.instrument_a, p.instrument_b): p for p in pairwise}
        dependence_aware: Decimal | None
        if len(open_instruments) == 1:
            dependence_aware, undefined_count = Decimal("1.0000"), 0
        else:
            dependence_aware, undefined_count = _dependence_weighted_concentration(
                open_instruments, weights, pairs_by_key
            )

        states.append(
            ConcurrentExposureState(
                state_sequence=sequence,
                as_of_timestamp=instant,
                open_instruments=open_instruments,
                weights=weights,
                nominal_concentration=nominal_concentration,
                dependence_aware_concentration=dependence_aware,
                undefined_pair_count=undefined_count,
            )
        )
    return tuple(states)


def _classify(
    *, concurrent_states: tuple[ConcurrentExposureState, ...], defined_pair_count: int
) -> DependenceEvidenceClassification:
    """Deterministic, conservative, descriptive-only classification
    (mission Phase 18) -- never a safety/optimality claim."""
    multi_position_states = tuple(s for s in concurrent_states if len(s.open_instruments) >= 2)
    if not multi_position_states or defined_pair_count == 0:
        return DependenceEvidenceClassification.INSUFFICIENT_DEPENDENCE_EVIDENCE
    peak = max(
        (
            s.dependence_aware_concentration
            for s in multi_position_states
            if s.dependence_aware_concentration is not None
        ),
        default=None,
    )
    if peak is None:
        return DependenceEvidenceClassification.INSUFFICIENT_DEPENDENCE_EVIDENCE
    if peak <= _LOW_DEPENDENCE_CEILING:
        return DependenceEvidenceClassification.LOW_OBSERVED_DEPENDENCE
    if peak <= _MIXED_DEPENDENCE_CEILING:
        return DependenceEvidenceClassification.MIXED_OBSERVED_DEPENDENCE
    return DependenceEvidenceClassification.HIGH_OBSERVED_DEPENDENCE


def _window_instability(
    series_by_instrument: dict[str, HistoricalInstrumentSeries],
    *,
    as_of: datetime,
    policy: DependenceEstimationPolicy,
) -> tuple[bool, Decimal | None]:
    """Compare pairwise correlation computed over the first half vs. the
    second half of the same estimation lookback window (mission Phase
    19) -- reports the largest single-pair delta, never averages
    instability away into one misleading score."""
    half = max(3, policy.lookback_bar_count // 2)
    first_half_policy = DependenceEstimationPolicy(
        policy_id=f"{policy.policy_id}-FIRST-HALF",
        version=policy.version,
        lookback_bar_count=half,
        minimum_overlapping_observations=min(policy.minimum_overlapping_observations, half),
    )
    all_timestamps = sorted(
        {
            bar.timestamp
            for series in series_by_instrument.values()
            for bar in series.bars
            if bar.timestamp <= as_of
        }
    )
    if len(all_timestamps) < policy.lookback_bar_count:
        return False, None
    midpoint = all_timestamps[-(policy.lookback_bar_count + 1) + half]

    first_half_pairs = {
        (p.instrument_a, p.instrument_b): p
        for p in build_pairwise_dependence(
            series_by_instrument, as_of=midpoint, policy=first_half_policy
        )
    }
    second_half_pairs = {
        (p.instrument_a, p.instrument_b): p
        for p in build_pairwise_dependence(
            series_by_instrument, as_of=as_of, policy=first_half_policy
        )
    }

    max_delta: Decimal | None = None
    for key, first in first_half_pairs.items():
        second = second_half_pairs.get(key)
        if first.correlation is None or second is None or second.correlation is None:
            continue
        delta = abs(first.correlation - second.correlation)
        if max_delta is None or delta > max_delta:
            max_delta = delta
    instability_observed = max_delta is not None and max_delta > _INSTABILITY_THRESHOLD
    return instability_observed, max_delta


def build_portfolio_dependence_report(
    *,
    identity: DomainIdentity[PortfolioDependenceReportId],
    portfolio: PortfolioEvidenceReport,
    series_by_instrument: dict[str, HistoricalInstrumentSeries],
    policy: DependenceEstimationPolicy = DEFAULT_DEPENDENCE_ESTIMATION_POLICY,
) -> PortfolioDependenceReport:
    """Build one immutable cross-instrument dependence report from an
    already-persisted M067 `PortfolioEvidenceReport` and the raw
    per-instrument bar series of its own upstream dataset bundle. Pure
    and deterministic. Never mutates, re-allocates, or re-optimizes
    anything upstream."""
    allocated = tuple(
        d
        for d in portfolio.allocation_decisions
        if d.decision is PortfolioAllocationOutcome.ALLOCATED
    )
    all_instruments_ever_open = sorted({d.instrument_symbol for d in allocated})
    open_instants = sorted({d.entry_timestamp for d in allocated})

    pairwise_by_cutoff: dict[datetime, tuple[PairwiseDependenceEvidence, ...]] = {}
    for instant in open_instants:
        concurrent_symbols = sorted(
            {
                d.instrument_symbol
                for d in allocated
                if d.entry_timestamp <= instant <= d.exit_timestamp
            }
        )
        relevant_series = {
            symbol: series_by_instrument[symbol]
            for symbol in concurrent_symbols
            if symbol in series_by_instrument
        }
        pairwise_by_cutoff[instant] = build_pairwise_dependence(
            relevant_series, as_of=instant, policy=policy
        )

    # Canonical, deduplicated pairwise set across every instrument the
    # portfolio ever actually held, evaluated once at the final known
    # cutoff (the study's own last open instant) for top-level reporting
    # -- per-state pairwise evidence above already respects each state's
    # own temporal firewall.
    final_cutoff = open_instants[-1] if open_instants else None
    canonical_series = {
        symbol: series_by_instrument[symbol]
        for symbol in all_instruments_ever_open
        if symbol in series_by_instrument
    }
    canonical_pairs = (
        build_pairwise_dependence(canonical_series, as_of=final_cutoff, policy=policy)
        if final_cutoff is not None
        else ()
    )

    defined_pairs = tuple(p for p in canonical_pairs if p.status is PairDependenceStatus.DEFINED)
    off_diagonal_defined = tuple(p for p in defined_pairs if p.instrument_a != p.instrument_b)

    def _pair_correlation(pair: PairwiseDependenceEvidence) -> Decimal:
        assert pair.correlation is not None  # DEFINED pairs always carry a correlation
        return pair.correlation

    highest = max(off_diagonal_defined, key=_pair_correlation, default=None)
    lowest = min(off_diagonal_defined, key=_pair_correlation, default=None)

    concurrent_states = build_concurrent_exposure_states(portfolio, pairwise_by_cutoff)
    multi_states = tuple(s for s in concurrent_states if len(s.open_instruments) >= 2)
    peak_nominal = max((s.nominal_concentration for s in multi_states), default=None)
    peak_dependence_aware = max(
        (
            s.dependence_aware_concentration
            for s in multi_states
            if s.dependence_aware_concentration is not None
        ),
        default=None,
    )

    instability_observed, max_delta = (
        _window_instability(canonical_series, as_of=final_cutoff, policy=policy)
        if final_cutoff is not None
        else (False, None)
    )

    if peak_dependence_aware is None:
        stress_result = ConcentrationStressResult(
            canonical_peak_dependence_aware_concentration=None,
            stressed_perfect_correlation_concentration=None,
        )
    else:
        widest_state = max(multi_states, key=lambda s: len(s.open_instruments))
        # Perfect-correlation stress: w' J w where J is the all-ones
        # matrix == (sum of weights)^2 == 1 for any fully-allocated
        # concurrent state (weights sum to 1 by construction).
        stressed = _quantize_ratio(sum(widest_state.weights, Decimal("0")) ** 2)
        stress_result = ConcentrationStressResult(
            canonical_peak_dependence_aware_concentration=peak_dependence_aware,
            stressed_perfect_correlation_concentration=stressed,
        )

    classification = _classify(
        concurrent_states=concurrent_states, defined_pair_count=len(defined_pairs)
    )

    return PortfolioDependenceReport(
        identity=identity,
        source_portfolio_study_governance_id=str(portfolio.identity.governance_id),
        source_portfolio_study_runtime_id=str(portfolio.identity.runtime_id),
        source_study_governance_id=portfolio.source_study_governance_id,
        source_study_runtime_id=portfolio.source_study_runtime_id,
        dataset_bundle_id=portfolio.dataset_bundle_id,
        dataset_bundle_version=portfolio.dataset_bundle_version,
        dataset_bundle_sha256=portfolio.dataset_bundle_sha256,
        dataset_source_kind=portfolio.dataset_source_kind,
        capital_policy_id=portfolio.capital_policy.policy_id,
        capital_policy_version=portfolio.capital_policy.version,
        estimation_policy=policy,
        instrument_count=len(all_instruments_ever_open),
        pair_count=len(canonical_pairs),
        defined_pair_count=len(defined_pairs),
        undefined_pair_count=len(canonical_pairs) - len(defined_pairs),
        highest_pair_a=highest.instrument_a if highest else None,
        highest_pair_b=highest.instrument_b if highest else None,
        highest_pair_correlation=highest.correlation if highest else None,
        lowest_pair_a=lowest.instrument_a if lowest else None,
        lowest_pair_b=lowest.instrument_b if lowest else None,
        lowest_pair_correlation=lowest.correlation if lowest else None,
        concurrent_exposure_state_count=len(concurrent_states),
        peak_nominal_concentration=peak_nominal,
        peak_dependence_aware_concentration=peak_dependence_aware,
        correlation_instability_observed=instability_observed,
        max_window_instability_delta=max_delta,
        concentration_stress=stress_result,
        pairwise_dependence=canonical_pairs,
        concurrent_exposure_states=concurrent_states,
        classification=classification,
        limitations=FALSE_DIVERSIFICATION_FIREWALL_LIMITATIONS,
    )
