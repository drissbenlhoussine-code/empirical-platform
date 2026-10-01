"""MILESTONE-094 Phase 1/3/21 -- proving `tools/m094_edge_source_study.py` carries the
machine-enforced holdout guard forward correctly: its own fetch wrapper refuses a locked
date BEFORE any network call, it reuses M093's own research-date source verbatim rather than
recomputing a second, possibly-drifted date range, and no literal date construction anywhere
in this tool's source falls inside the locked range.

Mirrors `test_m093_family_screening.py`'s own style for the equivalent M093 tool."""

from __future__ import annotations

import ast
from datetime import date
from pathlib import Path

import pytest
from tools.m093_family_screening import research_session_dates as m093_research_session_dates
from tools.m094_edge_source_study import (
    RANKED_SYMBOLS,
    SYMBOLS,
    _fetch,
    research_session_dates,
)

from empirical_platform.decision_candidate.m093_holdout_guard import (
    HOLDOUT_END,
    HOLDOUT_START,
    HoldoutLockedError,
)

_TOOL_SOURCE = Path("tools/m094_edge_source_study.py").read_text(encoding="utf-8")


class _StubBarsPortRaisesIfCalled:
    """Any network call reaching this stub proves the holdout guard did NOT fire first."""

    def fetch_minute_bars(self, *args: object, **kwargs: object) -> object:
        raise AssertionError("network fetch must never be reached for a locked holdout date")


@pytest.mark.parametrize(
    "session_date",
    [HOLDOUT_START, HOLDOUT_END, date(2026, 4, 15), date(2026, 3, 18), date(2026, 5, 12)],
)
def test_fetch_refuses_before_any_network_access_for_holdout_dates(session_date: date) -> None:
    with pytest.raises(HoldoutLockedError):
        _fetch(_StubBarsPortRaisesIfCalled(), "AAPL", session_date)  # type: ignore[arg-type]


def test_fetch_does_not_refuse_a_research_dataset_date() -> None:
    """Negative control: the same stub, called with a real research date, must reach the
    stub's own (intentionally failing) `fetch_minute_bars` -- proving the guard is
    discriminating, not refusing everything."""
    research_date = research_session_dates()[0]
    with pytest.raises(AssertionError, match="network fetch must never be reached"):
        _fetch(_StubBarsPortRaisesIfCalled(), "AAPL", research_date)  # type: ignore[arg-type]


def test_research_session_dates_is_imported_verbatim_from_m093_not_redefined() -> None:
    """M094 must reuse M093's own dataset definition, never recompute a second one that
    could silently drift from it."""
    assert research_session_dates is m093_research_session_dates
    assert research_session_dates() == m093_research_session_dates()


def test_ranked_symbols_excludes_benchmark_symbols() -> None:
    assert set(RANKED_SYMBOLS) == {"AAPL", "AMZN", "GOOGL", "META", "MSFT", "NVDA"}
    assert "SPY" not in RANKED_SYMBOLS
    assert "QQQ" not in RANKED_SYMBOLS


@pytest.mark.parametrize("symbol", SYMBOLS)
def test_every_symbol_is_part_of_the_fixed_8_symbol_universe(symbol: str) -> None:
    assert symbol in {"AAPL", "AMZN", "GOOGL", "META", "MSFT", "NVDA", "QQQ", "SPY"}


def test_the_only_fetch_call_in_this_tool_goes_through_the_guarded_entry_point() -> None:
    """Static proof (AST-based): `_fetch` -- the only function in this module that touches
    network I/O -- calls exclusively `fw.fetch_session_bars_guarded`, never any other fetch
    path, and never `bars_port.fetch_minute_bars` directly."""
    tree = ast.parse(_TOOL_SOURCE)
    fetch_functions = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "_fetch"
    ]
    assert len(fetch_functions) == 1
    calls = [node for node in ast.walk(fetch_functions[0]) if isinstance(node, ast.Call)]
    call_names = {ast.unparse(call.func) for call in calls}
    assert call_names == {"fw.fetch_session_bars_guarded"}


def test_fetch_research_bars_reaches_the_broker_only_through_fetch() -> None:
    """Static proof that the loop fetching the whole 100-session dataset also goes
    exclusively through `_fetch`, not a second, unguarded fetch path."""
    tree = ast.parse(_TOOL_SOURCE)
    functions = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "fetch_research_bars"
    ]
    assert len(functions) == 1
    calls = {
        ast.unparse(call.func) for call in ast.walk(functions[0]) if isinstance(call, ast.Call)
    }
    assert "_fetch" in calls
    assert not any("fetch_minute_bars" in name for name in calls)


def test_no_date_construction_call_in_this_tool_falls_inside_the_locked_holdout() -> None:
    """This tool constructs zero literal calendar dates of its own (it imports
    `research_session_dates` from M093 instead of recomputing a range) -- confirmed here so
    a future edit that DOES add a literal date is caught if it ever falls in the locked
    range."""
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
    """Phase 22 -- zero broker-write surface. This is a pure read-only research tool."""
    forbidden = ("submit_order", "submit_close_order", "cancel_order", "AlpacaPaperClient")
    for term in forbidden:
        assert term not in _TOOL_SOURCE
