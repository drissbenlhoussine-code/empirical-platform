"""The first deterministic, versioned trading strategy contract.

MILESTONE-057.

THIS STRATEGY EXISTS TO PROVE THE TRADING-EVALUATION ARCHITECTURE. ITS
PRESENCE IS NOT A CLAIM OF PROFITABILITY. See
MILESTONE_057_TRADING_EVALUATION_SCOPE_AND_DESIGN.md Section 6 for the full
candidate comparison and selection rationale.

`evaluate()` is a pure function: given the same `ObservationWindow` and the
same `StrategyParameters`, it always returns the same `EvaluationOutcome`.
It performs no I/O, no wall-clock reads, and no randomness. It reads
`window.reference_bars` (strictly prior bars only) and `window.evaluation_bar`
(the current bar) -- never anything from beyond the evaluation bar, because
`ObservationWindow` itself contains nothing beyond it (see `market_data.py`).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from empirical_platform.decision_candidate.market_data import ObservationWindow

STRATEGY_ID = "PRIOR_WINDOW_BREAKOUT_VOLUME_CONFIRMATION"
STRATEGY_VERSION = "1"


class TradingDecision(StrEnum):
    """Closed decision vocabulary. Long-only scope: no SHORT is offered."""

    LONG_CANDIDATE = "LONG_CANDIDATE"
    NO_TRADE = "NO_TRADE"


class EvaluationReasonCode(StrEnum):
    """Machine-readable reason codes explaining every evaluation outcome.

    Exactly one price-condition code and one volume-condition code is
    always present, whether the evaluation results in LONG_CANDIDATE or
    NO_TRADE -- NO_TRADE is explained, not merely the absence of a signal.
    """

    PRICE_ABOVE_REFERENCE_HIGH = "PRICE_ABOVE_REFERENCE_HIGH"
    PRICE_NOT_ABOVE_REFERENCE_HIGH = "PRICE_NOT_ABOVE_REFERENCE_HIGH"
    VOLUME_ABOVE_REFERENCE_AVERAGE = "VOLUME_ABOVE_REFERENCE_AVERAGE"
    VOLUME_NOT_ABOVE_REFERENCE_AVERAGE = "VOLUME_NOT_ABOVE_REFERENCE_AVERAGE"


@dataclass(frozen=True, slots=True)
class StrategyParameters:
    """Reproducibility-critical configuration for one evaluation.

    `reference_window_size` is the number of strictly-prior bars used to
    compute the reference high and reference average volume.
    """

    reference_window_size: int = 5

    def __post_init__(self) -> None:
        if not isinstance(self.reference_window_size, int) or isinstance(
            self.reference_window_size, bool
        ):
            raise TypeError("reference_window_size must be an int")
        if self.reference_window_size < 1:
            raise ValueError("reference_window_size must be at least 1")


@dataclass(frozen=True, slots=True)
class EvaluationMeasurements:
    """The exact numeric measurements the decision was computed from."""

    current_close: Decimal
    current_volume: int
    reference_high: Decimal
    reference_average_volume: Decimal


@dataclass(frozen=True, slots=True)
class EvaluationOutcome:
    """A structured, self-explaining trading evaluation result."""

    decision: TradingDecision
    reasons: tuple[EvaluationReasonCode, ...]
    measurements: EvaluationMeasurements


def evaluate(window: ObservationWindow, parameters: StrategyParameters) -> EvaluationOutcome:
    """Evaluate one ObservationWindow under this strategy's rule.

    LONG_CANDIDATE requires both: the evaluation bar's close exceeds the
    highest high of the prior `reference_window_size` bars, AND the
    evaluation bar's volume exceeds the average volume of those same prior
    bars. Otherwise NO_TRADE. Raises `ValueError` if the window does not
    contain enough reference bars for the configured window size --
    genuinely invalid input, not a silent NO_TRADE.
    """
    reference_bars = window.reference_bars
    if len(reference_bars) < parameters.reference_window_size:
        raise ValueError(
            f"ObservationWindow has {len(reference_bars)} reference bars; "
            f"strategy requires at least {parameters.reference_window_size}"
        )
    reference_window = reference_bars[-parameters.reference_window_size :]

    reference_high = max(bar.high for bar in reference_window)
    reference_average_volume = sum((bar.volume for bar in reference_window), start=0) / Decimal(
        len(reference_window)
    )

    current = window.evaluation_bar
    price_condition_met = current.close > reference_high
    volume_condition_met = Decimal(current.volume) > reference_average_volume

    reasons = (
        EvaluationReasonCode.PRICE_ABOVE_REFERENCE_HIGH
        if price_condition_met
        else EvaluationReasonCode.PRICE_NOT_ABOVE_REFERENCE_HIGH,
        EvaluationReasonCode.VOLUME_ABOVE_REFERENCE_AVERAGE
        if volume_condition_met
        else EvaluationReasonCode.VOLUME_NOT_ABOVE_REFERENCE_AVERAGE,
    )
    decision = (
        TradingDecision.LONG_CANDIDATE
        if price_condition_met and volume_condition_met
        else TradingDecision.NO_TRADE
    )
    measurements = EvaluationMeasurements(
        current_close=current.close,
        current_volume=current.volume,
        reference_high=reference_high,
        reference_average_volume=reference_average_volume,
    )
    return EvaluationOutcome(decision=decision, reasons=reasons, measurements=measurements)
