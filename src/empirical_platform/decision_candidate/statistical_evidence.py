"""Statistical evidence / false-confidence-firewall domain.

MILESTONE-066. A `StatisticalEvidenceReport` is a post-hoc, read-only
statistical evaluation of one already-frozen, already-persisted
`SurvivorshipAwareRobustnessStudy` (M064) plus the individual
`HistoricalBacktestRun`s (M061) that produced each of its windows. It
never re-runs, re-ranks, re-sizes, or re-optimizes anything -- it only
asks: how much genuine evidence do we actually have that the observed
performance is more than sample noise?

Two independent sample units are tracked separately and never conflated
(mission Phase 5): `TRADE_LEVEL_SAMPLE` (individual executed trades,
pooled across every window that produced at least one) and
`WINDOW_LEVEL_SAMPLE` (the study's own walk-forward windows). A
deterministic, explicitly-seeded, non-parametric percentile bootstrap
(stdlib `random.Random`, never global `random` state) estimates
uncertainty around the trade-level mean/median/aggregate R-multiple.
Concentration/outlier sensitivity views show how much the canonical
result depends on a single best/worst trade or window. A conservative,
breadth-and-stability-gated classification (never "probability of
profitability") is the only summary judgment persisted -- see
`FALSE_CONFIDENCE_FIREWALL_LIMITATIONS`, which is itself persisted on
every report.
"""

from __future__ import annotations

import statistics
from collections.abc import Callable
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum
from random import Random

from empirical_platform.decision_candidate.historical_backtest import HistoricalBacktestRun
from empirical_platform.decision_candidate.survivorship_study import (
    SurvivorshipAwareRobustnessStudy,
)
from empirical_platform.identifiers.pairs import DomainIdentity
from empirical_platform.identifiers.types import StatisticalEvidenceReportId

_QUANT4 = Decimal("0.0001")

#: Minimum sample breadth, in trades AND windows, below which a report is
#: `INSUFFICIENT_SAMPLE_BREADTH` regardless of how favorable the observed
#: outcome looks (mission Phase 24: weak-sample control).
_INSUFFICIENT_TRADE_THRESHOLD = 15
_INSUFFICIENT_WINDOW_THRESHOLD = 5
_LIMITED_TRADE_THRESHOLD = 30
_LIMITED_WINDOW_THRESHOLD = 10
_MODERATE_TRADE_THRESHOLD = 60
_MODERATE_WINDOW_THRESHOLD = 20

#: Only these confidence levels are supported -- an explicit, small,
#: reviewable set rather than accepting an arbitrary Decimal (mission
#: Phase 21: "unsupported confidence level" attack).
SUPPORTED_CONFIDENCE_LEVELS = (Decimal("0.80"), Decimal("0.90"), Decimal("0.95"), Decimal("0.99"))

#: Minimum resample count accepted by a `BootstrapPolicy` -- guards
#: against a policy that would produce a statistically meaningless
#: interval (mission Phase 21: "zero resamples" / "too few resamples").
MINIMUM_RESAMPLE_COUNT = 200

#: Persisted verbatim on every report (mission Phase 11: mandatory
#: false-confidence-firewall invariants). Never conditionally omitted.
FALSE_CONFIDENCE_FIREWALL_LIMITATIONS: tuple[str, ...] = (
    "Positive net PnL does not imply statistically reliable evidence.",
    "A high win rate does not imply statistically reliable evidence.",
    "A profit factor greater than 1 does not imply statistically reliable evidence.",
    "A positive bootstrap point estimate does not guarantee a real trading edge.",
    "A confidence interval entirely above zero is not proof of future or live profitability.",
    "A large trade count drawn from one narrow historical period is not broad temporal evidence.",
)


class SampleUnit(StrEnum):
    """Closed vocabulary distinguishing the two sample units this report
    tracks -- never conflated, never multiplied together."""

    TRADE_LEVEL_SAMPLE = "TRADE_LEVEL_SAMPLE"
    WINDOW_LEVEL_SAMPLE = "WINDOW_LEVEL_SAMPLE"


class BootstrapMethod(StrEnum):
    """Closed vocabulary of supported bootstrap algorithms. Only the
    simple, transparent percentile method is implemented -- deliberately,
    per the mission's own "avoid academic-statistics theater" guidance."""

    PERCENTILE_BOOTSTRAP = "PERCENTILE_BOOTSTRAP"


class SensitivityLabel(StrEnum):
    """Closed vocabulary of diagnostic sensitivity views. `CANONICAL` is
    the unmodified observed sample; every other value excludes exactly
    one observation for outlier-dependence diagnosis only -- canonical
    results themselves are never altered."""

    CANONICAL = "CANONICAL"
    EXCLUDING_BEST_TRADE = "EXCLUDING_BEST_TRADE"
    EXCLUDING_WORST_TRADE = "EXCLUDING_WORST_TRADE"
    EXCLUDING_BEST_WINDOW = "EXCLUDING_BEST_WINDOW"
    EXCLUDING_WORST_WINDOW = "EXCLUDING_WORST_WINDOW"


class StatisticalEvidenceClassification(StrEnum):
    """Conservative, deterministic sample-breadth-and-stability
    classification. Deliberately NOT named/worded as a probability of
    profitability -- see module docstring and
    `FALSE_CONFIDENCE_FIREWALL_LIMITATIONS`. Distinct root term
    ("SAMPLE_BREADTH") chosen so this vocabulary is never confused with
    M062's `INSUFFICIENT_EVIDENCE` or M063/M064's `INSUFFICIENT_SAMPLE`/
    `ROBUSTNESS_EVIDENCE_*` values."""

    INSUFFICIENT_SAMPLE_BREADTH = "INSUFFICIENT_SAMPLE_BREADTH"
    LIMITED_SAMPLE_BREADTH = "LIMITED_SAMPLE_BREADTH"
    MODERATE_SAMPLE_BREADTH = "MODERATE_SAMPLE_BREADTH"
    BROADER_HISTORICAL_SAMPLE_BREADTH = "BROADER_HISTORICAL_SAMPLE_BREADTH"


_CLASSIFICATION_RANK: dict[StatisticalEvidenceClassification, int] = {
    StatisticalEvidenceClassification.INSUFFICIENT_SAMPLE_BREADTH: 0,
    StatisticalEvidenceClassification.LIMITED_SAMPLE_BREADTH: 1,
    StatisticalEvidenceClassification.MODERATE_SAMPLE_BREADTH: 2,
    StatisticalEvidenceClassification.BROADER_HISTORICAL_SAMPLE_BREADTH: 3,
}


@dataclass(frozen=True, slots=True)
class BootstrapPolicy:
    """Explicit, versioned, deterministic bootstrap configuration. No
    field here may ever be silently defaulted at the point of use --
    every report persists the exact policy that produced it."""

    policy_id: str
    version: str
    method: BootstrapMethod
    resample_count: int
    seed: int
    confidence_level: Decimal

    def __post_init__(self) -> None:
        if not self.policy_id.strip():
            raise ValueError("policy_id must be non-empty")
        if not self.version.strip():
            raise ValueError("version must be non-empty")
        if self.resample_count < MINIMUM_RESAMPLE_COUNT:
            raise ValueError(
                f"resample_count must be at least {MINIMUM_RESAMPLE_COUNT}, "
                f"got {self.resample_count}"
            )
        if self.confidence_level not in SUPPORTED_CONFIDENCE_LEVELS:
            raise ValueError(
                f"confidence_level {self.confidence_level} is not supported; "
                f"must be one of {SUPPORTED_CONFIDENCE_LEVELS}"
            )


DEFAULT_BOOTSTRAP_POLICY = BootstrapPolicy(
    policy_id="STATEVID-BOOTSTRAP",
    version="1",
    method=BootstrapMethod.PERCENTILE_BOOTSTRAP,
    resample_count=2000,
    seed=6066001,
    confidence_level=Decimal("0.90"),
)


@dataclass(frozen=True, slots=True)
class BootstrapInterval:
    """One immutable percentile-bootstrap confidence interval for one
    named metric."""

    metric_name: str
    confidence_level: Decimal
    lower_bound: Decimal
    point_estimate: Decimal
    upper_bound: Decimal
    sample_size: int
    resample_count: int
    seed: int
    method: BootstrapMethod
    policy_version: str

    def __post_init__(self) -> None:
        if not self.metric_name.strip():
            raise ValueError("metric_name must be non-empty")
        if self.sample_size < 1:
            raise ValueError("sample_size must be at least 1")
        if self.lower_bound > self.upper_bound:
            raise ValueError("lower_bound must not exceed upper_bound")

    @property
    def excludes_zero(self) -> bool:
        """`True` only when the entire interval lies strictly on one side
        of zero -- i.e. the resampled sign is stable at this confidence
        level. This is NOT proof of a real edge (see
        `FALSE_CONFIDENCE_FIREWALL_LIMITATIONS`); it is one necessary
        (not sufficient) input to the classification gate."""
        return self.lower_bound > 0 or self.upper_bound < 0


@dataclass(frozen=True, slots=True)
class SensitivityView:
    """One diagnostic sensitivity view: the canonical sample, or the
    canonical sample with exactly one observation excluded."""

    label: SensitivityLabel
    sample_size: int
    net_pnl: Decimal
    total_r: Decimal
    mean_r: Decimal | None

    def __post_init__(self) -> None:
        if self.sample_size < 0:
            raise ValueError("sample_size must be non-negative")


@dataclass(frozen=True, slots=True)
class DrawdownPathEvidence:
    """Historical realized drawdown (the one actual chronological path)
    versus the distribution of maximum drawdown under many random
    reorderings of the identical realized trade outcomes -- path-order
    sensitivity, never a prediction of future drawdown."""

    historical_realized_max_drawdown: Decimal
    median_resampled_max_drawdown: Decimal
    upper_tail_resampled_max_drawdown: Decimal
    worst_resampled_max_drawdown: Decimal
    resample_count: int
    seed: int

    def __post_init__(self) -> None:
        if self.resample_count < 1:
            raise ValueError("resample_count must be at least 1")


@dataclass(frozen=True, slots=True)
class StatisticalEvidenceReport:
    """One immutable, persisted, post-hoc statistical evaluation of one
    already-frozen historical study. A fact computed once, never
    mutated -- mirrors every other M061-M065 study/result record in this
    codebase."""

    identity: DomainIdentity[StatisticalEvidenceReportId]

    # Upstream authority lineage (mission Phase 4) -- copied verbatim
    # from the source study, never independently re-derived.
    source_study_governance_id: str
    source_study_runtime_id: str
    dataset_bundle_id: str
    dataset_bundle_version: str
    dataset_bundle_sha256: str
    dataset_source_kind: str
    universe_id: str
    universe_version: str
    membership_manifest_hash: str
    strategy_id: str
    strategy_version: str
    ranking_model_id: str
    ranking_model_version: str
    risk_policy_id: str
    risk_policy_version: str
    sizing_policy_id: str
    sizing_policy_version: str

    trade_sample_size: int
    window_sample_size: int

    winning_trades: int
    losing_trades: int
    win_rate: Decimal | None
    net_pnl: Decimal
    total_r: Decimal
    mean_r_per_trade: Decimal | None
    median_r_per_trade: Decimal | None
    r_standard_deviation: Decimal | None
    best_trade_r: Decimal | None
    worst_trade_r: Decimal | None
    largest_trade_share_of_positive_pnl: Decimal | None
    profit_factor: Decimal | None

    positive_windows: int
    negative_windows: int
    median_window_net_pnl: Decimal | None
    median_window_total_r: Decimal | None

    bootstrap_policy: BootstrapPolicy
    mean_r_interval: BootstrapInterval
    median_r_interval: BootstrapInterval
    aggregate_r_interval: BootstrapInterval
    window_level_interval: BootstrapInterval | None

    sensitivity_views: tuple[SensitivityView, ...]
    drawdown_path_evidence: DrawdownPathEvidence

    classification: StatisticalEvidenceClassification
    limitations: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.identity, DomainIdentity):
            raise TypeError("identity must be a DomainIdentity[StatisticalEvidenceReportId]")
        if not isinstance(self.identity.governance_id, StatisticalEvidenceReportId):
            raise TypeError("identity governance_id must be a StatisticalEvidenceReportId")
        for field_name in (
            "source_study_governance_id",
            "source_study_runtime_id",
            "dataset_bundle_id",
            "dataset_bundle_version",
            "dataset_bundle_sha256",
            "dataset_source_kind",
            "universe_id",
            "universe_version",
            "membership_manifest_hash",
            "strategy_id",
            "strategy_version",
            "ranking_model_id",
            "ranking_model_version",
            "risk_policy_id",
            "risk_policy_version",
            "sizing_policy_id",
            "sizing_policy_version",
        ):
            if not getattr(self, field_name).strip():
                raise ValueError(f"{field_name} must be non-empty")
        if self.trade_sample_size < 0:
            raise ValueError("trade_sample_size must be non-negative")
        if self.window_sample_size < 0:
            raise ValueError("window_sample_size must be non-negative")
        if self.winning_trades + self.losing_trades > self.trade_sample_size:
            raise ValueError("winning_trades + losing_trades must not exceed trade_sample_size")
        if tuple(self.limitations) != FALSE_CONFIDENCE_FIREWALL_LIMITATIONS:
            raise ValueError("limitations must be exactly FALSE_CONFIDENCE_FIREWALL_LIMITATIONS")
        if not self.sensitivity_views:
            raise ValueError("sensitivity_views must be non-empty")


def _quantize(value: Decimal) -> Decimal:
    return value.quantize(_QUANT4, rounding=ROUND_HALF_UP)


def _mean(values: tuple[Decimal, ...]) -> Decimal | None:
    if not values:
        return None
    return _quantize(sum(values, Decimal("0")) / len(values))


def _median(values: tuple[Decimal, ...]) -> Decimal | None:
    if not values:
        return None
    return _quantize(Decimal(str(statistics.median(values))))


def _standard_deviation(values: tuple[Decimal, ...]) -> Decimal | None:
    if len(values) < 2:
        return None
    return _quantize(Decimal(str(statistics.stdev(values))))


def _percentile_bootstrap_interval(
    values: tuple[Decimal, ...],
    *,
    metric_name: str,
    statistic: str,
    policy: BootstrapPolicy,
) -> BootstrapInterval:
    """Deterministic non-parametric percentile bootstrap for `mean`,
    `median`, or `sum` over `values`. A fresh `random.Random(seed)`
    instance is created here and used nowhere else -- no hidden or
    shared randomness."""

    def _aggregate_sum(sample: tuple[Decimal, ...]) -> Decimal | None:
        return _quantize(sum(sample, Decimal("0")))

    aggregate: Callable[[tuple[Decimal, ...]], Decimal | None]
    if statistic == "mean":
        point = _mean(values) or Decimal("0")
        aggregate = _mean
    elif statistic == "median":
        point = _median(values) or Decimal("0")
        aggregate = _median
    elif statistic == "sum":
        point = _quantize(sum(values, Decimal("0")))
        aggregate = _aggregate_sum
    else:  # pragma: no cover - internal misuse guard
        raise ValueError(f"unsupported statistic: {statistic}")

    rng = Random(policy.seed)  # noqa: S311 - statistical bootstrap, not cryptographic use
    n = len(values)
    resample_values: list[Decimal] = []
    for _ in range(policy.resample_count):
        resample = tuple(values[rng.randrange(n)] for _ in range(n))
        resample_values.append(aggregate(resample) or Decimal("0"))
    resample_values.sort()

    tail = (Decimal("1") - policy.confidence_level) / 2
    lower_index = int(
        (tail * (policy.resample_count - 1)).to_integral_value(rounding=ROUND_HALF_UP)
    )
    upper_index = policy.resample_count - 1 - lower_index
    lower_index = max(0, min(lower_index, policy.resample_count - 1))
    upper_index = max(0, min(upper_index, policy.resample_count - 1))

    return BootstrapInterval(
        metric_name=metric_name,
        confidence_level=policy.confidence_level,
        lower_bound=resample_values[lower_index],
        point_estimate=point,
        upper_bound=resample_values[upper_index],
        sample_size=n,
        resample_count=policy.resample_count,
        seed=policy.seed,
        method=policy.method,
        policy_version=policy.version,
    )


def _historical_realized_drawdown(chronological_net_pnl: tuple[Decimal, ...]) -> Decimal:
    """Peak-to-trough drawdown over the ONE real chronological path,
    pooled across every window's own executed trades in cutoff order --
    a genuinely new, cross-window computation, not a reimplementation of
    M061's own single-run drawdown (which never spans multiple runs)."""
    running = Decimal("0")
    peak = Decimal("0")
    max_drawdown = Decimal("0")
    for pnl in chronological_net_pnl:
        running += pnl
        peak = max(peak, running)
        max_drawdown = max(max_drawdown, peak - running)
    return _quantize(max_drawdown)


def _resampled_drawdown_distribution(
    net_pnl_values: tuple[Decimal, ...], *, resample_count: int, seed: int
) -> tuple[Decimal, ...]:
    """Reorder (permute, no replacement) the identical realized trade
    outcomes `resample_count` times and recompute peak-to-trough drawdown
    for each ordering -- path-order sensitivity, not a market simulator
    and not a prediction: the multiset of outcomes never changes, only
    their sequence."""
    rng = Random(seed)  # noqa: S311 - statistical resampling, not cryptographic use
    distribution: list[Decimal] = []
    values = list(net_pnl_values)
    for _ in range(resample_count):
        shuffled = values.copy()
        rng.shuffle(shuffled)
        distribution.append(_historical_realized_drawdown(tuple(shuffled)))
    distribution.sort()
    return tuple(distribution)


def _classify(
    *, trade_sample_size: int, window_sample_size: int, mean_r_interval: BootstrapInterval
) -> StatisticalEvidenceClassification:
    """Deterministic, conservative classification. Governed by the
    WEAKER of the two sample units (mission Phase 5: trades and windows
    are never treated as equivalent evidence), then capped by sign
    stability (mission Phase 10/11/24/25: a profitable small or
    outlier-dominated sample must never classify strongly)."""
    if (
        trade_sample_size < _INSUFFICIENT_TRADE_THRESHOLD
        or window_sample_size < _INSUFFICIENT_WINDOW_THRESHOLD
    ):
        breadth = StatisticalEvidenceClassification.INSUFFICIENT_SAMPLE_BREADTH
    elif (
        trade_sample_size < _LIMITED_TRADE_THRESHOLD
        or window_sample_size < _LIMITED_WINDOW_THRESHOLD
    ):
        breadth = StatisticalEvidenceClassification.LIMITED_SAMPLE_BREADTH
    elif (
        trade_sample_size < _MODERATE_TRADE_THRESHOLD
        or window_sample_size < _MODERATE_WINDOW_THRESHOLD
    ):
        breadth = StatisticalEvidenceClassification.MODERATE_SAMPLE_BREADTH
    else:
        breadth = StatisticalEvidenceClassification.BROADER_HISTORICAL_SAMPLE_BREADTH

    if not mean_r_interval.excludes_zero:
        sign_cap = StatisticalEvidenceClassification.LIMITED_SAMPLE_BREADTH
    else:
        sign_cap = StatisticalEvidenceClassification.BROADER_HISTORICAL_SAMPLE_BREADTH

    return breadth if _CLASSIFICATION_RANK[breadth] <= _CLASSIFICATION_RANK[sign_cap] else sign_cap


def build_statistical_evidence_report(
    *,
    identity: DomainIdentity[StatisticalEvidenceReportId],
    study: SurvivorshipAwareRobustnessStudy,
    window_runs: tuple[HistoricalBacktestRun, ...],
    bootstrap_policy: BootstrapPolicy = DEFAULT_BOOTSTRAP_POLICY,
) -> StatisticalEvidenceReport:
    """Build one immutable statistical evidence report from an already
    -persisted `SurvivorshipAwareRobustnessStudy` and the individual
    `HistoricalBacktestRun`s referenced by its own windows. Pure and
    deterministic for a fixed `bootstrap_policy.seed`. Never mutates,
    re-ranks, re-sizes, or re-runs anything upstream."""
    all_trades = tuple(trade for run in window_runs for trade in run.trades if trade.executed)
    r_values = tuple(trade.r_multiple for trade in all_trades if trade.r_multiple is not None)
    trade_sample_size = len(r_values)

    winning_trades = sum(1 for r in r_values if r > 0)
    losing_trades = sum(1 for r in r_values if r < 0)
    win_rate = _quantize(Decimal(winning_trades) / trade_sample_size) if trade_sample_size else None
    net_pnl = _quantize(sum((trade.net_pnl for trade in all_trades), Decimal("0")))
    total_r = _quantize(sum(r_values, Decimal("0")))
    positive_r_sum = sum((r for r in r_values if r > 0), Decimal("0"))
    negative_r_sum = sum((r for r in r_values if r < 0), Decimal("0"))
    profit_factor = _quantize(positive_r_sum / abs(negative_r_sum)) if negative_r_sum != 0 else None
    best_trade_r = max(r_values) if r_values else None
    worst_trade_r = min(r_values) if r_values else None
    positive_pnl_trades = tuple(trade.net_pnl for trade in all_trades if trade.net_pnl > 0)
    largest_trade_share = (
        _quantize(max(positive_pnl_trades) / sum(positive_pnl_trades, Decimal("0")))
        if positive_pnl_trades
        else None
    )

    window_results = study.window_results
    window_sample_size = len(window_results)
    positive_windows = sum(1 for w in window_results if w.net_pnl > 0)
    negative_windows = sum(1 for w in window_results if w.net_pnl < 0)
    window_net_pnls = tuple(w.net_pnl for w in window_results)
    window_total_rs = tuple(w.total_r for w in window_results)

    mean_r_interval = _percentile_bootstrap_interval(
        r_values, metric_name="mean_r_per_trade", statistic="mean", policy=bootstrap_policy
    )
    median_r_interval = _percentile_bootstrap_interval(
        r_values, metric_name="median_r_per_trade", statistic="median", policy=bootstrap_policy
    )
    aggregate_r_interval = _percentile_bootstrap_interval(
        r_values, metric_name="aggregate_r", statistic="sum", policy=bootstrap_policy
    )
    window_level_interval = (
        _percentile_bootstrap_interval(
            window_total_rs,
            metric_name="window_total_r",
            statistic="mean",
            policy=bootstrap_policy,
        )
        if window_sample_size >= _INSUFFICIENT_WINDOW_THRESHOLD
        else None
    )

    canonical_view = SensitivityView(
        label=SensitivityLabel.CANONICAL,
        sample_size=trade_sample_size,
        net_pnl=net_pnl,
        total_r=total_r,
        mean_r=_mean(r_values),
    )
    sensitivity_views: list[SensitivityView] = [canonical_view]
    if all_trades:
        best_trade = max(all_trades, key=lambda t: t.net_pnl)
        worst_trade = min(all_trades, key=lambda t: t.net_pnl)
        for label, excluded in (
            (SensitivityLabel.EXCLUDING_BEST_TRADE, best_trade),
            (SensitivityLabel.EXCLUDING_WORST_TRADE, worst_trade),
        ):
            remaining = tuple(t for t in all_trades if t is not excluded)
            remaining_r = tuple(t.r_multiple for t in remaining if t.r_multiple is not None)
            sensitivity_views.append(
                SensitivityView(
                    label=label,
                    sample_size=len(remaining),
                    net_pnl=_quantize(sum((t.net_pnl for t in remaining), Decimal("0"))),
                    total_r=_quantize(sum(remaining_r, Decimal("0"))),
                    mean_r=_mean(remaining_r),
                )
            )
    if window_results:
        best_window = max(window_results, key=lambda w: w.net_pnl)
        worst_window = min(window_results, key=lambda w: w.net_pnl)
        for label, excluded_window in (
            (SensitivityLabel.EXCLUDING_BEST_WINDOW, best_window),
            (SensitivityLabel.EXCLUDING_WORST_WINDOW, worst_window),
        ):
            remaining_windows = tuple(w for w in window_results if w is not excluded_window)
            remaining_pnl = tuple(w.net_pnl for w in remaining_windows)
            remaining_r = tuple(w.total_r for w in remaining_windows)
            sensitivity_views.append(
                SensitivityView(
                    label=label,
                    sample_size=len(remaining_windows),
                    net_pnl=_quantize(sum(remaining_pnl, Decimal("0"))),
                    total_r=_quantize(sum(remaining_r, Decimal("0"))),
                    mean_r=_mean(remaining_r),
                )
            )

    chronological_trades = tuple(
        sorted(all_trades, key=lambda t: (t.evaluation_cutoff, t.trade_sequence))
    )
    chronological_pnl = tuple(t.net_pnl for t in chronological_trades)
    historical_drawdown = _historical_realized_drawdown(chronological_pnl)
    resampled_distribution = _resampled_drawdown_distribution(
        chronological_pnl,
        resample_count=bootstrap_policy.resample_count,
        seed=bootstrap_policy.seed,
    )
    upper_tail_index = max(
        0,
        min(
            len(resampled_distribution) - 1,
            int(
                (Decimal("0.95") * (len(resampled_distribution) - 1)).to_integral_value(
                    rounding=ROUND_HALF_UP
                )
            ),
        ),
    )
    drawdown_evidence = DrawdownPathEvidence(
        historical_realized_max_drawdown=historical_drawdown,
        median_resampled_max_drawdown=_median(resampled_distribution) or Decimal("0"),
        upper_tail_resampled_max_drawdown=resampled_distribution[upper_tail_index]
        if resampled_distribution
        else Decimal("0"),
        worst_resampled_max_drawdown=resampled_distribution[-1]
        if resampled_distribution
        else Decimal("0"),
        resample_count=bootstrap_policy.resample_count,
        seed=bootstrap_policy.seed,
    )

    classification = _classify(
        trade_sample_size=trade_sample_size,
        window_sample_size=window_sample_size,
        mean_r_interval=mean_r_interval,
    )

    return StatisticalEvidenceReport(
        identity=identity,
        source_study_governance_id=str(study.identity.governance_id),
        source_study_runtime_id=str(study.identity.runtime_id),
        dataset_bundle_id=str(study.dataset_bundle_id),
        dataset_bundle_version=study.dataset_bundle_version,
        dataset_bundle_sha256=study.dataset_bundle_sha256,
        dataset_source_kind=study.dataset_source_kind,
        universe_id=study.universe_id,
        universe_version=study.universe_version,
        membership_manifest_hash=study.membership_manifest_hash,
        strategy_id=study.strategy_id,
        strategy_version=study.strategy_version,
        ranking_model_id=study.ranking_model_id,
        ranking_model_version=study.ranking_model_version,
        risk_policy_id=study.risk_policy_id,
        risk_policy_version=study.risk_policy_version,
        sizing_policy_id=study.sizing_policy_id,
        sizing_policy_version=study.sizing_policy_version,
        trade_sample_size=trade_sample_size,
        window_sample_size=window_sample_size,
        winning_trades=winning_trades,
        losing_trades=losing_trades,
        win_rate=win_rate,
        net_pnl=net_pnl,
        total_r=total_r,
        mean_r_per_trade=_mean(r_values),
        median_r_per_trade=_median(r_values),
        r_standard_deviation=_standard_deviation(r_values),
        best_trade_r=best_trade_r,
        worst_trade_r=worst_trade_r,
        largest_trade_share_of_positive_pnl=largest_trade_share,
        profit_factor=profit_factor,
        positive_windows=positive_windows,
        negative_windows=negative_windows,
        median_window_net_pnl=_median(window_net_pnls),
        median_window_total_r=_median(window_total_rs),
        bootstrap_policy=bootstrap_policy,
        mean_r_interval=mean_r_interval,
        median_r_interval=median_r_interval,
        aggregate_r_interval=aggregate_r_interval,
        window_level_interval=window_level_interval,
        # Canonicalized by label so a construct-then-persist-then-retrieve
        # round trip is exact regardless of construction order -- the
        # Postgres repository's own retrieval query orders by the same
        # key (mirrors the M065 CorporateActionManifest fix).
        sensitivity_views=tuple(sorted(sensitivity_views, key=lambda view: view.label.value)),
        drawdown_path_evidence=drawdown_evidence,
        classification=classification,
        limitations=FALSE_CONFIDENCE_FIREWALL_LIMITATIONS,
    )
