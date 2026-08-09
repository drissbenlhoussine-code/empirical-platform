"""MILESTONE-062 Phase 22: independent verification path.

This module deliberately does NOT call `build_validation_study()`,
`_segment_dataset()`, `_segment_bar_ranges()`, or ANY M057-M061 production
function (`evaluate()`, `build_scan()`, `build_trade_plan()`,
`build_position_plan()`, `build_historical_backtest_run()`). It re-derives,
from the raw fixture JSON alone, using its own separately-authored
arithmetic:

- the dataset bundle's own SHA-256 (via `hashlib` directly);
- each segment's own bar-index range and membership (own loop over the
  bundle's own declared `segments` array, never calling
  `_segment_bar_ranges()`);
- confirmation that no bar index belongs to more than one segment;
- for the HOLDOUT_1 segment specifically, the full decision -> risk-gate
  -> position-sizing -> next-bar-open-entry -> STOP_FIRST -> holding-horizon
  trade simulation, per instrument per scored cutoff, reproducing every
  M057-M061 formula from its own frozen definition rather than by calling
  the frozen code.

Each independently-computed HOLDOUT_1 result is then compared against the
real, production-computed values recorded in
`tests/fixtures/m062_validation_study/README.md` (and independently
reproduced by `test_build_validation_study_against_real_fixture_matches_hand_verified_results`
in the sibling test module, which DOES call production code) -- agreement
between the two independently-authored paths is the actual verification.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from decimal import ROUND_FLOOR, Decimal
from pathlib import Path
from typing import Any

_FIXTURE_PATH = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "m062_validation_study"
    / "synthetic_multi_period_validation_dataset_bundle.json"
)
_EXPECTED_SHA256 = "3289c380b233b06495c865b1645185436318b2394d77faaea97be96bf787c9f3"

_REFERENCE_WINDOW = 5
_HOLDING_HORIZON = 3
_TARGET_PROJECTION_PERCENT = Decimal("0.02")
_MINIMUM_REWARD_RISK_RATIO = Decimal("2.0")
_ACCOUNT_EQUITY = Decimal("100000")
_RISK_PERCENT = Decimal("0.01")
_MAX_NOTIONAL_PERCENT = Decimal("0.25")
_SLIPPAGE_BPS = Decimal("5")


@dataclass(frozen=True)
class _IndependentTrade:
    instrument: str
    outcome: str  # "TARGET_HIT" | "STOP_HIT" | "TIME_EXIT" | "NO_ENTRY"
    net_pnl: Decimal


def _load_raw() -> dict[str, Any]:
    raw_bytes = _FIXTURE_PATH.read_bytes()
    return dict(json.loads(raw_bytes.decode("utf-8")))


def test_independent_sha256_matches_declared_value() -> None:
    raw_bytes = _FIXTURE_PATH.read_bytes()
    independent_digest = hashlib.sha256(raw_bytes).hexdigest()
    assert independent_digest == _EXPECTED_SHA256


def _independent_segment_ranges(segments_raw: list[dict[str, Any]]) -> list[tuple[int, int, str]]:
    """Own loop over the bundle's own declared segment sizes -- never calls
    `_segment_bar_ranges()`."""
    ranges = []
    cursor = 0
    for entry in segments_raw:
        total = (
            int(entry["warmup_bar_count"])
            + int(entry["scoring_bar_count"])
            + int(entry["buffer_bar_count"])
        )
        ranges.append((cursor, cursor + total, str(entry["segment_id"])))
        cursor += total
    return ranges


def test_independent_segment_ranges_never_overlap() -> None:
    raw = _load_raw()
    segments_raw: list[dict[str, Any]] = raw["segments"]
    ranges = _independent_segment_ranges(segments_raw)
    assert [segment_id for _, _, segment_id in ranges] == ["DEV", "HOLDOUT_1", "HOLDOUT_2"]
    seen_indices: set[int] = set()
    for start, end, segment_id in ranges:
        indices = set(range(start, end))
        assert not (indices & seen_indices), f"segment {segment_id} overlaps a prior segment"
        seen_indices |= indices
    total_bars = len(raw["instruments"][0]["bars"])
    assert seen_indices == set(range(total_bars))


def _independent_decision(
    bars: list[dict[str, Any]], cutoff_index: int
) -> tuple[bool, Decimal, Decimal]:
    """Reimplements the M057 LONG_CANDIDATE condition from scratch. Returns
    (is_long_candidate, reference_high, current_close)."""
    reference_rows = bars[cutoff_index - _REFERENCE_WINDOW : cutoff_index]
    evaluation_row = bars[cutoff_index]
    reference_high = max(Decimal(row["high"]) for row in reference_rows)
    reference_avg_volume = sum(Decimal(row["volume"]) for row in reference_rows) / Decimal(
        len(reference_rows)
    )
    current_close = Decimal(evaluation_row["close"])
    current_volume = Decimal(evaluation_row["volume"])
    is_long = current_close > reference_high and current_volume > reference_avg_volume
    return is_long, reference_high, current_close


def _independent_trade(
    bars: list[dict[str, Any]], cutoff_index: int, instrument: str
) -> _IndependentTrade | None:
    """Reimplements the full M059->M060->M061 pipeline from scratch for one
    instrument at one cutoff. Returns None if the cutoff is not
    LONG_CANDIDATE (no trade attempt at all -- distinct from an attempted
    but rejected/NO_ENTRY trade)."""
    is_long, reference_high, current_close = _independent_decision(bars, cutoff_index)
    if not is_long:
        return None

    stop = reference_high
    target = reference_high * (1 + _TARGET_PROJECTION_PERCENT)
    entry_for_geometry = current_close
    if not (stop < entry_for_geometry) or not (target > entry_for_geometry):
        return None  # invalid geometry -> REJECTED_PLAN, never simulated
    risk_per_unit = entry_for_geometry - stop
    reward_per_unit = target - entry_for_geometry
    ratio = reward_per_unit / risk_per_unit
    if ratio < _MINIMUM_REWARD_RISK_RATIO:
        return None  # REWARD_RISK_BELOW_MINIMUM -> REJECTED_PLAN, never simulated

    allowed_risk = _ACCOUNT_EQUITY * _RISK_PERCENT
    max_notional = _ACCOUNT_EQUITY * _MAX_NOTIONAL_PERCENT
    risk_based_qty = int((allowed_risk / risk_per_unit).to_integral_value(rounding=ROUND_FLOOR))
    capital_based_qty = int(
        (max_notional / entry_for_geometry).to_integral_value(rounding=ROUND_FLOOR)
    )
    quantity = min(risk_based_qty, capital_based_qty)
    if quantity <= 0:
        return None  # ZERO_POSITION_SIZE / CAPITAL_LIMIT_EXCEEDED -> REJECTED_POSITION_PLAN

    entry_bars = bars[cutoff_index + 1 : cutoff_index + 1 + _HOLDING_HORIZON]
    first_bar = entry_bars[0]
    actual_entry_price = Decimal(first_bar["open"])
    if actual_entry_price <= stop or actual_entry_price >= target:
        return _IndependentTrade(instrument=instrument, outcome="NO_ENTRY", net_pnl=Decimal("0"))

    outcome = None
    exit_price = None
    for bar in entry_bars:
        bar_high = Decimal(bar["high"])
        bar_low = Decimal(bar["low"])
        stop_hit = bar_low <= stop
        target_hit = bar_high >= target
        if stop_hit:  # STOP_FIRST: stop wins any same-bar ambiguity
            outcome = "STOP_HIT"
            exit_price = stop
            break
        if target_hit:
            outcome = "TARGET_HIT"
            exit_price = target
            break
    if outcome is None:
        outcome = "TIME_EXIT"
        exit_price = Decimal(entry_bars[_HOLDING_HORIZON - 1]["close"])

    assert exit_price is not None
    gross_pnl = (exit_price - actual_entry_price) * quantity
    entry_slippage = actual_entry_price * (_SLIPPAGE_BPS / Decimal("10000")) * quantity
    exit_slippage = exit_price * (_SLIPPAGE_BPS / Decimal("10000")) * quantity
    net_pnl = gross_pnl - entry_slippage - exit_slippage
    return _IndependentTrade(instrument=instrument, outcome=outcome, net_pnl=net_pnl)


def test_independent_holdout_1_trade_simulation_matches_production_summary() -> None:
    """Independently re-simulates the entire HOLDOUT_1 segment (bar indices
    16-31: warmup 16-20, scoring 21-28, buffer 29-31) and confirms the
    resulting executed/win/loss counts and net PnL match the real,
    production-computed values recorded in the fixture's own README.md
    (executed=3, win=1, loss=2, net_pnl=64.578130) -- reproduced here with
    zero shared code with `historical_backtest.py`/`validation_study.py`.
    """
    raw = _load_raw()
    segment_start, segment_end = 16, 32
    scoring_start, scoring_end = 21, 29  # [21, 29) -- 8 scored cutoffs

    trades: list[_IndependentTrade] = []
    instrument_entries: list[dict[str, Any]] = raw["instruments"]
    for instrument_entry in instrument_entries:
        symbol: str = instrument_entry["instrument"]
        segment_bars: list[dict[str, Any]] = instrument_entry["bars"][segment_start:segment_end]
        for local_cutoff_index in range(scoring_start - segment_start, scoring_end - segment_start):
            trade = _independent_trade(segment_bars, local_cutoff_index, symbol)
            if trade is not None and trade.outcome != "NO_ENTRY":
                trades.append(trade)

    executed = [t for t in trades if t.outcome != "NO_ENTRY"]
    wins = sum(1 for t in executed if t.net_pnl > 0)
    losses = sum(1 for t in executed if t.net_pnl < 0)
    net_pnl = sum((t.net_pnl for t in executed), Decimal("0"))

    assert len(executed) == 3
    assert wins == 1
    assert losses == 2
    assert net_pnl == Decimal("64.578130")
