"""Deterministic ranking model for LONG_CANDIDATE trading opportunities.

MILESTONE-058. Reuses the M057 `EvaluationMeasurements` unchanged -- this
module adds no new market-data or strategy concept, only a deterministic
scoring/ordering rule applied to already-produced M057 outcomes.

`RANKING_MODEL_ID`/`RANKING_MODEL_VERSION` are versioned exactly like
`STRATEGY_ID`/`STRATEGY_VERSION` (see `strategy.py`), for the same
reproducibility reason: a persisted ranking must remain explainable and
reproducible from its own recorded identity, independent of any future
ranking-model change.
"""

from __future__ import annotations

from decimal import Decimal

from empirical_platform.decision_candidate.market_data import Instrument
from empirical_platform.decision_candidate.strategy import EvaluationMeasurements

RANKING_MODEL_ID = "BREAKOUT_VOLUME_STRENGTH_SUM"
RANKING_MODEL_VERSION = "1"


def compute_ranking_score(measurements: EvaluationMeasurements) -> Decimal:
    """Score one LONG_CANDIDATE evaluation for ranking against its peers.

    breakout_strength = (current_close - reference_high) / reference_high
        -- how far, proportionally, the close broke above the reference
        high; always > 0 for a genuine LONG_CANDIDATE (that is exactly the
        price condition the M057 strategy already enforced to reach this
        decision).

    volume_strength = current_volume / reference_average_volume
        -- how many multiples of the reference average volume traded;
        always > 1 for a genuine LONG_CANDIDATE (the volume condition the
        M057 strategy already enforced).

    ranking_score = breakout_strength + volume_strength
        -- an explicit, unweighted, dimensionless-ratio sum. No hidden
        weights, no historical calibration, no randomness: both terms are
        proportional-strength measures already implied by the strategy's
        own two conditions, added with equal, explicit weight of 1 each.
    """
    breakout_strength = (
        measurements.current_close - measurements.reference_high
    ) / measurements.reference_high
    volume_strength = Decimal(measurements.current_volume) / measurements.reference_average_volume
    return breakout_strength + volume_strength


def rank_sort_key(score: Decimal, instrument: Instrument) -> tuple[Decimal, str]:
    """Deterministic ordering key: score descending, then instrument symbol
    ascending on an exact score tie.

    `sorted(..., key=rank_sort_key)` sorts ascending by default, so
    negating `score` inverts the primary ordering to descending while the
    secondary key (`instrument.symbol`) remains ascending.
    """
    return (-score, instrument.symbol)
