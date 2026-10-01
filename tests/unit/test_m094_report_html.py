"""MILESTONE-094 Phase 21 -- report rendering: `report_page` must render successfully over
both classification outcomes without raising, and must embed the classification and the
locked-holdout reminder somewhere in the page."""

from __future__ import annotations

from empirical_platform.entrypoints import _m094_report_html as html

_BASE_RESULTS: dict = {
    "research_dataset": {
        "description": "M091 DEVELOPMENT UNION M092 VALIDATION",
        "session_count": 100,
        "symbol_session_pairs_non_empty": 785,
    },
    "selected_directions": [],
    "phase4_cost_turnover_diagnosis": {"conclusion": "test conclusion text"},
    "phase5_horizon_study": {
        "5m": {
            "n": 10,
            "mean_percent": 0.01,
            "median_percent": 0.01,
            "stdev_percent": 0.1,
            "sign_persistence_percent": 51.0,
        }
    },
    "phase7_regime": {
        "by_spy_vwap_position": {
            "SPY_ABOVE_VWAP": {"n": 5, "mean_30m_forward_return_percent": 0.02}
        },
        "by_spy_session_return_sign": {},
        "by_own_trailing_volatility_bucket": {},
    },
    "phase8_cross_sectional": {
        "by_bucket": {
            "STRONGEST": {"n": 5, "mean_30m_forward_return_percent": 0.03},
            "WEAKEST": {"n": 5, "mean_30m_forward_return_percent": -0.01},
        },
        "strongest_minus_weakest_spread_percent": 0.04,
    },
    "phase9_selectivity": {
        "top_1pct": {
            "n": 3,
            "mean_30m_forward_return_percent": 0.05,
            "max_single_symbol_share_percent": 33.0,
        }
    },
    "phase10_gap_study": {
        "by_gap_direction": {},
        "event_news_earnings_data": "EVENT_DATA_NOT_AVAILABLE",
        "event_data_note": "no event data port exists",
    },
    "phase16_scorecard": {
        "MULTI_TIMEFRAME_TREND": {
            "observed_information_strength": "weak",
            "cost_survivability": "not evaluated",
            "sample_size": 100,
        }
    },
}


def test_report_page_renders_no_promising_edge_source() -> None:
    results = {**_BASE_RESULTS, "classification": "NO_PROMISING_EDGE_SOURCE"}
    page = html.report_page(results)
    assert "NO_PROMISING_EDGE_SOURCE" in page
    assert "2026-03-18" in page and "2026-05-12" in page
    assert "<form" not in page.lower()
    assert "<button" not in page.lower()


def test_report_page_renders_promising_edge_sources_found() -> None:
    results = {
        **_BASE_RESULTS,
        "classification": "PROMISING_EDGE_SOURCES_FOUND",
        "selected_directions": ["CROSS_SECTIONAL_RELATIVE_STRENGTH"],
    }
    page = html.report_page(results)
    assert "PROMISING_EDGE_SOURCES_FOUND" in page
    assert "CROSS_SECTIONAL_RELATIVE_STRENGTH" in page
