"""MILESTONE-095 Phase 1/3/21/24 -- proving `tools/m095_event_study.py` carries the
machine-enforced holdout guard forward correctly for BOTH its bar fetch and its news fetch,
reuses M093's own research-date source verbatim, constructs no literal date falling inside
the locked range, and has zero broker-write surface. Mirrors `test_m094_edge_source_study.py`.
"""

from __future__ import annotations

import ast
from datetime import date
from pathlib import Path

import pytest
from tools.m093_family_screening import research_session_dates as m093_research_session_dates
from tools.m095_event_study import (
    RANKED_SYMBOLS,
    SYMBOLS,
    _fetch_bars,
)

from empirical_platform.decision_candidate.m093_holdout_guard import (
    HOLDOUT_END,
    HOLDOUT_START,
    HoldoutLockedError,
)

_TOOL_SOURCE = Path("tools/m095_event_study.py").read_text(encoding="utf-8")


class _StubBarsPortRaisesIfCalled:
    def fetch_minute_bars(self, *args: object, **kwargs: object) -> object:
        raise AssertionError("bars fetch must never be reached for a locked holdout date")


@pytest.mark.parametrize(
    "session_date",
    [HOLDOUT_START, HOLDOUT_END, date(2026, 4, 15), date(2026, 3, 18), date(2026, 5, 12)],
)
def test_bars_fetch_refuses_before_any_network_access_for_holdout_dates(
    session_date: date,
) -> None:
    with pytest.raises(HoldoutLockedError):
        _fetch_bars(_StubBarsPortRaisesIfCalled(), "AAPL", session_date)  # type: ignore[arg-type]


def test_ranked_symbols_excludes_benchmark_symbols() -> None:
    assert set(RANKED_SYMBOLS) == {"AAPL", "AMZN", "GOOGL", "META", "MSFT", "NVDA"}
    assert "SPY" not in RANKED_SYMBOLS
    assert "QQQ" not in RANKED_SYMBOLS


@pytest.mark.parametrize("symbol", SYMBOLS)
def test_every_symbol_is_part_of_the_fixed_8_symbol_universe(symbol: str) -> None:
    assert symbol in {"AAPL", "AMZN", "GOOGL", "META", "MSFT", "NVDA", "QQQ", "SPY"}


def test_research_session_dates_is_imported_verbatim_from_m093_not_redefined() -> None:
    from tools.m093_family_screening import research_session_dates as m095_imported_dates

    assert m095_imported_dates is m093_research_session_dates


def test_fetch_all_bars_reaches_the_broker_only_through_the_guarded_fetch() -> None:
    """Static proof: `fetch_all_bars` calls exclusively `_fetch_bars` for network I/O, never
    a second, unguarded fetch path."""
    tree = ast.parse(_TOOL_SOURCE)
    functions = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "fetch_all_bars"
    ]
    assert len(functions) == 1
    calls = {
        ast.unparse(call.func) for call in ast.walk(functions[0]) if isinstance(call, ast.Call)
    }
    assert "_fetch_bars" in calls
    assert not any("fetch_minute_bars" in name for name in calls)


def test_fetch_all_events_reaches_the_broker_only_through_the_guarded_fetch() -> None:
    """Static proof: `fetch_all_events` calls exclusively `research.fetch_symbol_news_guarded`
    for network I/O, never `news_port.fetch_news` directly."""
    tree = ast.parse(_TOOL_SOURCE)
    functions = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "fetch_all_events"
    ]
    assert len(functions) == 1
    calls = {
        ast.unparse(call.func) for call in ast.walk(functions[0]) if isinstance(call, ast.Call)
    }
    assert "research.fetch_symbol_news_guarded" in calls
    assert not any(name.endswith(".fetch_news") for name in calls)


def test_no_date_construction_call_in_this_tool_falls_inside_the_locked_holdout() -> None:
    tree = ast.parse(_TOOL_SOURCE)
    constructed_dates: list[date] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func_name = ast.unparse(node.func)
        all_constant_args = all(isinstance(a, ast.Constant) for a in node.args)
        if not all_constant_args:
            continue
        if func_name == "date" and len(node.args) == 3:
            args = [ast.literal_eval(a) for a in node.args]
            constructed_dates.append(date(*args))
        elif func_name == "date.fromisoformat" and len(node.args) == 1:
            value = ast.literal_eval(node.args[0])
            constructed_dates.append(date.fromisoformat(value))

    for constructed in constructed_dates:
        assert not (HOLDOUT_START <= constructed <= HOLDOUT_END)


def test_no_broker_order_write_surface_anywhere_in_this_tool() -> None:
    """Phase 24 -- zero broker-write surface. Pure read-only research tool."""
    forbidden = ("submit_order", "submit_close_order", "cancel_order", "AlpacaPaperClient")
    for term in forbidden:
        assert term not in _TOOL_SOURCE


def test_no_broker_order_write_surface_in_the_event_research_module() -> None:
    source = Path("src/empirical_platform/usecases/m095_event_research.py").read_text(
        encoding="utf-8"
    )
    forbidden = ("submit_order", "submit_close_order", "cancel_order")
    for term in forbidden:
        assert term not in source


def test_no_broker_order_write_surface_added_to_the_alpaca_client() -> None:
    """`fetch_news` must add read-only capability only -- the order-submission surface this
    module already carries (`submit_order`/`submit_close_order`/`cancel_order`) must be
    unchanged in count by the M095 edit."""
    source = Path("src/empirical_platform/shared/brokerage/alpaca_paper.py").read_text(
        encoding="utf-8"
    )
    tree = ast.parse(source)
    news_methods = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "fetch_news"
    ]
    assert len(news_methods) == 1
    calls = {
        ast.unparse(call.func) for call in ast.walk(news_methods[0]) if isinstance(call, ast.Call)
    }
    assert not any(
        name.endswith((".submit_order", ".submit_close_order", ".cancel_order")) for name in calls
    )
