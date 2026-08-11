"""MILESTONE-069 independent Yahoo-chart-JSON recomputation.

`_independent_parse` below is a self-contained, separately-authored
extraction (own loop, own OHLCV/timestamp logic) that never calls
`translate_yahoo_chart_json_to_pipeline_csv`,
`translate_fetch_result_to_pipeline_csv`, or `parse_source_csv` -- those
production functions are imported only afterward, to *compare against*
`_independent_parse`'s own result on the real, captured Yahoo chart JSON
fixture (bar count, first/last bar timestamp and close, chronological
ordering), never to help compute it.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from empirical_platform.decision_candidate.historical_import import parse_source_csv
from empirical_platform.decision_candidate.market_data import BarInterval, Instrument
from empirical_platform.decision_candidate.market_data_acquisition import (
    translate_yahoo_chart_json_to_pipeline_csv,
)

_FIXTURE_PATH = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "m069_market_data_acquisition"
    / "real_yahoo_chart_aapl_sample.json"
)


def _independent_parse(
    raw_bytes: bytes,
) -> list[tuple[datetime, Decimal, Decimal, Decimal, Decimal, int]]:
    """Own, separately-authored extraction: walk the raw JSON structure
    directly (no shared helper with production), skip any row with a
    missing field, and round OHLC to 4 decimal places via Python's own
    `round()` before building a `Decimal` from the rounded value's `str`
    -- deliberately not the same code path as
    `translate_yahoo_chart_json_to_pipeline_csv`."""
    payload = json.loads(raw_bytes)
    result = payload["chart"]["result"][0]
    timestamps = result["timestamp"]
    quote = result["indicators"]["quote"][0]
    rows: list[tuple[datetime, Decimal, Decimal, Decimal, Decimal, int]] = []
    for i, epoch in enumerate(timestamps):
        fields = (
            quote["open"][i],
            quote["high"][i],
            quote["low"][i],
            quote["close"][i],
            quote["volume"][i],
        )
        if any(f is None for f in fields):
            continue
        day = datetime.fromtimestamp(epoch, tz=UTC).date()
        ts = datetime(day.year, day.month, day.day, tzinfo=UTC)
        o, h, low, c, v = fields
        rows.append(
            (
                ts,
                Decimal(str(round(o, 4))),
                Decimal(str(round(h, 4))),
                Decimal(str(round(low, 4))),
                Decimal(str(round(c, 4))),
                int(v),
            )
        )
    return rows


def test_independent_bar_count_matches_production() -> None:
    raw_bytes = _FIXTURE_PATH.read_bytes()
    independent_rows = _independent_parse(raw_bytes)

    pipeline_csv = translate_yahoo_chart_json_to_pipeline_csv(raw_bytes, symbol="AAPL")
    production_bars = parse_source_csv(
        pipeline_csv, instrument=Instrument("AAPL"), interval=BarInterval.ONE_DAY
    )

    assert len(independent_rows) == len(production_bars)
    assert len(independent_rows) > 0


def test_independent_first_and_last_bar_match_production() -> None:
    raw_bytes = _FIXTURE_PATH.read_bytes()
    independent_rows = _independent_parse(raw_bytes)
    pipeline_csv = translate_yahoo_chart_json_to_pipeline_csv(raw_bytes, symbol="AAPL")
    production_bars = parse_source_csv(
        pipeline_csv, instrument=Instrument("AAPL"), interval=BarInterval.ONE_DAY
    )

    first_ts, first_o, first_h, first_l, first_c, first_v = independent_rows[0]
    assert production_bars[0].timestamp == first_ts
    assert production_bars[0].open == first_o
    assert production_bars[0].high == first_h
    assert production_bars[0].low == first_l
    assert production_bars[0].close == first_c
    assert production_bars[0].volume == first_v

    last_ts, last_o, last_h, last_l, last_c, last_v = independent_rows[-1]
    assert production_bars[-1].timestamp == last_ts
    assert production_bars[-1].close == last_c
    assert production_bars[-1].volume == last_v


def test_independent_parse_confirms_chronological_order() -> None:
    raw_bytes = _FIXTURE_PATH.read_bytes()
    independent_rows = _independent_parse(raw_bytes)
    timestamps = [row[0] for row in independent_rows]
    assert timestamps == sorted(timestamps)
    assert len(set(timestamps)) == len(timestamps)


def test_independent_parse_all_prices_positive_and_high_low_consistent() -> None:
    raw_bytes = _FIXTURE_PATH.read_bytes()
    independent_rows = _independent_parse(raw_bytes)
    for _ts, o, h, low, c, v in independent_rows:
        assert o > 0
        assert h >= low
        assert h >= o
        assert h >= c
        assert low <= o
        assert low <= c
        assert v > 0
