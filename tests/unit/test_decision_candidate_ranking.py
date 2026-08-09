"""MILESTONE-058 unit tests for the deterministic ranking model.

Pure, no PostgreSQL: exercises `compute_ranking_score`/`rank_sort_key`
directly against hand-constructed `EvaluationMeasurements`.
"""

from __future__ import annotations

from decimal import Decimal

from empirical_platform.decision_candidate.market_data import Instrument
from empirical_platform.decision_candidate.ranking import compute_ranking_score, rank_sort_key
from empirical_platform.decision_candidate.strategy import EvaluationMeasurements


def test_compute_ranking_score_sums_breakout_and_volume_strength() -> None:
    measurements = EvaluationMeasurements(
        current_close=Decimal("110.00"),
        current_volume=2000,
        reference_high=Decimal("100.00"),
        reference_average_volume=Decimal("1000"),
    )
    # breakout_strength = (110 - 100) / 100 = 0.1
    # volume_strength = 2000 / 1000 = 2.0
    # score = 2.1
    assert compute_ranking_score(measurements) == Decimal("2.1")


def test_compute_ranking_score_is_deterministic_across_repeated_calls() -> None:
    measurements = EvaluationMeasurements(
        current_close=Decimal("101.37"),
        current_volume=1543,
        reference_high=Decimal("99.21"),
        reference_average_volume=Decimal("1011.60"),
    )
    first = compute_ranking_score(measurements)
    second = compute_ranking_score(measurements)
    assert first == second


def test_compute_ranking_score_higher_breakout_yields_higher_score() -> None:
    baseline = EvaluationMeasurements(
        current_close=Decimal("101.00"),
        current_volume=1500,
        reference_high=Decimal("100.00"),
        reference_average_volume=Decimal("1000"),
    )
    stronger_breakout = EvaluationMeasurements(
        current_close=Decimal("105.00"),
        current_volume=1500,
        reference_high=Decimal("100.00"),
        reference_average_volume=Decimal("1000"),
    )
    assert compute_ranking_score(stronger_breakout) > compute_ranking_score(baseline)


def test_compute_ranking_score_higher_volume_yields_higher_score() -> None:
    baseline = EvaluationMeasurements(
        current_close=Decimal("101.00"),
        current_volume=1500,
        reference_high=Decimal("100.00"),
        reference_average_volume=Decimal("1000"),
    )
    stronger_volume = EvaluationMeasurements(
        current_close=Decimal("101.00"),
        current_volume=3000,
        reference_high=Decimal("100.00"),
        reference_average_volume=Decimal("1000"),
    )
    assert compute_ranking_score(stronger_volume) > compute_ranking_score(baseline)


def test_rank_sort_key_orders_score_descending() -> None:
    low = rank_sort_key(Decimal("1.0"), Instrument("AAAA"))
    high = rank_sort_key(Decimal("5.0"), Instrument("BBBB"))
    assert sorted([low, high]) == [high, low]


def test_rank_sort_key_ties_break_by_instrument_symbol_ascending() -> None:
    same_score = Decimal("2.5")
    key_zzzz = rank_sort_key(same_score, Instrument("ZZZZ"))
    key_aaaa = rank_sort_key(same_score, Instrument("AAAA"))
    assert sorted([key_zzzz, key_aaaa]) == [key_aaaa, key_zzzz]
