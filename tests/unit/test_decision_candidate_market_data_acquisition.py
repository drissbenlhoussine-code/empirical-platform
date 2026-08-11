"""Pure, offline unit tests for MILESTONE-069's `MarketDataSource`
adapter boundary, the `FakeMarketDataSource` test double, and the
Yahoo-chart-JSON translation pipeline.

No network access anywhere in this file -- the real adapter's own
`fetch()` HTTP path is exercised only by the explicitly opt-in
`EMPIRICAL_PLATFORM_RUN_NETWORK_TESTS`-gated integration test.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from empirical_platform.decision_candidate.market_data import BarInterval
from empirical_platform.decision_candidate.market_data_acquisition import (
    FAKE_SOURCE_NAME,
    YAHOO_FINANCE_SOURCE_NAME,
    FakeMarketDataSource,
    MarketDataAcquisitionError,
    MarketDataFetchRequest,
    MarketDataFetchResult,
    YahooFinanceChartMarketDataSource,
    translate_fetch_result_to_pipeline_csv,
    translate_yahoo_chart_json_to_pipeline_csv,
)
from empirical_platform.shared.interfaces.clock import FixedWallClock

_REAL_FIXTURE_PATH = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "m069_market_data_acquisition"
    / "real_yahoo_chart_aapl_sample.json"
)
_CLOCK = FixedWallClock(datetime(2026, 8, 11, 12, 0, tzinfo=UTC))


def test_fetch_request_rejects_empty_symbol() -> None:
    with pytest.raises(ValueError, match="symbol must be non-empty"):
        MarketDataFetchRequest(
            symbol="",
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 2),
            interval=BarInterval.ONE_DAY,
        )


def test_fetch_request_rejects_start_not_before_end() -> None:
    with pytest.raises(ValueError, match="start_date must be strictly before end_date"):
        MarketDataFetchRequest(
            symbol="AAPL",
            start_date=date(2024, 1, 2),
            end_date=date(2024, 1, 2),
            interval=BarInterval.ONE_DAY,
        )


def test_fetch_result_rejects_empty_raw_bytes() -> None:
    with pytest.raises(ValueError, match="empty raw_bytes"):
        MarketDataFetchResult(
            symbol="AAPL",
            source_format="X",
            raw_bytes=b"",
            source_reference="ref",
            fetched_at=_CLOCK.now(),
        )


def test_fetch_result_rejects_naive_fetched_at() -> None:
    with pytest.raises(ValueError, match="fetched_at must be timezone-aware"):
        MarketDataFetchResult(
            symbol="AAPL",
            source_format="X",
            raw_bytes=b"data",
            source_reference="ref",
            fetched_at=datetime(2026, 1, 1),  # noqa: DTZ001
        )


def test_fake_source_returns_registered_fixture() -> None:
    source = FakeMarketDataSource({"AAPL": b"timestamp,open,high,low,close,volume\n"}, clock=_CLOCK)
    assert source.source_name == FAKE_SOURCE_NAME
    result = source.fetch(
        MarketDataFetchRequest(
            symbol="AAPL",
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 2),
            interval=BarInterval.ONE_DAY,
        )
    )
    assert result.source_format == "EMPIRICAL_PLATFORM_NORMALIZED_CSV"
    assert result.fetched_at == _CLOCK.now()


def test_fake_source_raises_for_unregistered_symbol() -> None:
    source = FakeMarketDataSource({}, clock=_CLOCK)
    with pytest.raises(MarketDataAcquisitionError, match="no fixture bars registered"):
        source.fetch(
            MarketDataFetchRequest(
                symbol="ZZZZ",
                start_date=date(2024, 1, 1),
                end_date=date(2024, 1, 2),
                interval=BarInterval.ONE_DAY,
            )
        )


def test_yahoo_source_rejects_non_daily_interval() -> None:
    source = YahooFinanceChartMarketDataSource(clock=_CLOCK)
    assert source.source_name == YAHOO_FINANCE_SOURCE_NAME
    with pytest.raises(MarketDataAcquisitionError, match="only supports BarInterval.ONE_DAY"):
        source.fetch(
            MarketDataFetchRequest(
                symbol="AAPL",
                start_date=date(2024, 1, 1),
                end_date=date(2024, 1, 2),
                interval=BarInterval.ONE_MINUTE,
            )
        )


def test_translate_real_captured_yahoo_json_produces_valid_csv() -> None:
    raw = _REAL_FIXTURE_PATH.read_bytes()
    csv_bytes = translate_yahoo_chart_json_to_pipeline_csv(raw, symbol="AAPL")
    text = csv_bytes.decode("utf-8")
    lines = text.strip().splitlines()
    assert lines[0] == "timestamp,open,high,low,close,volume"
    assert len(lines) == 21  # header + 20 real trading days
    # Chronological order, UTC-midnight timestamps.
    first_row = lines[1].split(",")
    assert first_row[0] == "2024-06-03T00:00:00+00:00"


def test_translate_rejects_invalid_json() -> None:
    with pytest.raises(MarketDataAcquisitionError, match="not valid JSON"):
        translate_yahoo_chart_json_to_pipeline_csv(b"not json", symbol="AAPL")


def test_translate_rejects_yahoo_error_payload() -> None:
    payload = json.dumps(
        {"chart": {"result": None, "error": {"code": "Not Found", "description": "no data"}}}
    ).encode("utf-8")
    with pytest.raises(MarketDataAcquisitionError, match="Yahoo chart API returned an error"):
        translate_yahoo_chart_json_to_pipeline_csv(payload, symbol="ZZZZ")


def test_translate_rejects_empty_result() -> None:
    payload = json.dumps({"chart": {"result": [], "error": None}}).encode("utf-8")
    with pytest.raises(MarketDataAcquisitionError, match="has no result"):
        translate_yahoo_chart_json_to_pipeline_csv(payload, symbol="AAPL")


def test_translate_rejects_zero_bars() -> None:
    payload = json.dumps(
        {
            "chart": {
                "result": [
                    {
                        "timestamp": [],
                        "indicators": {
                            "quote": [
                                {"open": [], "high": [], "low": [], "close": [], "volume": []}
                            ]
                        },
                    }
                ],
                "error": None,
            }
        }
    ).encode("utf-8")
    with pytest.raises(MarketDataAcquisitionError, match="has zero bars"):
        translate_yahoo_chart_json_to_pipeline_csv(payload, symbol="AAPL")


def test_translate_skips_null_rows_never_fabricates() -> None:
    payload = json.dumps(
        {
            "chart": {
                "result": [
                    {
                        "timestamp": [1717372800, 1717459200],
                        "indicators": {
                            "quote": [
                                {
                                    "open": [100.0, None],
                                    "high": [101.0, None],
                                    "low": [99.0, None],
                                    "close": [100.5, None],
                                    "volume": [1000, None],
                                }
                            ]
                        },
                    }
                ],
                "error": None,
            }
        }
    ).encode("utf-8")
    csv_bytes = translate_yahoo_chart_json_to_pipeline_csv(payload, symbol="AAPL")
    lines = csv_bytes.decode("utf-8").strip().splitlines()
    assert len(lines) == 2  # header + exactly the one genuinely-complete row


def test_translate_rejects_all_null_rows() -> None:
    payload = json.dumps(
        {
            "chart": {
                "result": [
                    {
                        "timestamp": [1717372800],
                        "indicators": {
                            "quote": [
                                {
                                    "open": [None],
                                    "high": [None],
                                    "low": [None],
                                    "close": [None],
                                    "volume": [None],
                                }
                            ]
                        },
                    }
                ],
                "error": None,
            }
        }
    ).encode("utf-8")
    with pytest.raises(MarketDataAcquisitionError, match="only incomplete/null rows"):
        translate_yahoo_chart_json_to_pipeline_csv(payload, symbol="AAPL")


def test_translate_dispatch_normalized_csv_passthrough() -> None:
    csv_bytes = b"timestamp,open,high,low,close,volume\n"
    result = MarketDataFetchResult(
        symbol="AAPL",
        source_format="EMPIRICAL_PLATFORM_NORMALIZED_CSV",
        raw_bytes=csv_bytes,
        source_reference="fake://x",
        fetched_at=_CLOCK.now(),
    )
    assert translate_fetch_result_to_pipeline_csv(result) == csv_bytes


def test_translate_dispatch_unknown_format_raises() -> None:
    result = MarketDataFetchResult(
        symbol="AAPL",
        source_format="UNKNOWN_VENDOR_FORMAT",
        raw_bytes=b"data",
        source_reference="fake://x",
        fetched_at=_CLOCK.now(),
    )
    with pytest.raises(MarketDataAcquisitionError, match="no translator registered"):
        translate_fetch_result_to_pipeline_csv(result)
