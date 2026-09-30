"""MILESTONE-093 Phase 11-19 -- proving the committed screening/revision/robustness driver
(`tools/m093_family_screening.py`) itself never reaches the locked FINAL HOLDOUT, and that
its own research-date source is exactly the already-proven-safe 100-session dataset.

This is a regression test tied to the actual committed Phase 11 entry point, distinct from
`test_m093_holdout_guard.py` (proves the guard mechanism itself) and
`test_m093_research_data.py` (proves the 100-date research dataset has zero holdout
overlap) -- both of which this tool reuses rather than reimplementing."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from tools.m093_family_screening import FAMILY_NAMES, SYMBOLS, research_session_dates

from empirical_platform.decision_candidate.m093_holdout_guard import (
    HOLDOUT_END,
    HOLDOUT_START,
    assert_not_holdout,
)

_TOOL_SOURCE = Path("tools/m093_family_screening.py").read_text(encoding="utf-8")


def test_research_session_dates_is_exactly_100_sessions() -> None:
    dates = research_session_dates()
    assert len(dates) == 100
    assert dates == tuple(sorted(set(dates)))  # no duplicates, chronological order
    assert dates[0].isoformat() == "2026-05-13"
    assert dates[-1].isoformat() == "2026-09-29"


def test_research_session_dates_never_falls_inside_the_locked_holdout() -> None:
    for session_date in research_session_dates():
        assert_not_holdout(session_date)  # must not raise for any date this tool would fetch


def test_research_session_dates_matches_the_already_proven_safe_dataset() -> None:
    """Reproduces `test_m093_research_data.py`'s own 100-date computation independently, to
    prove this tool's date source is the SAME dataset, not a different one that happens to
    also avoid the holdout by coincidence."""
    import json
    from datetime import date

    from tools.m090_replay import recent_completed_session_dates

    development = tuple(
        date.fromisoformat(d)
        for d in json.loads(
            Path("external-review/MILESTONE-091/results.json").read_text(encoding="utf-8")
        )["session_dates"]
    )
    validation = recent_completed_session_dates(40, before=date(2026, 7, 8))
    expected = tuple(sorted(set(development) | set(validation)))
    assert research_session_dates() == expected


def test_the_only_fetch_call_in_this_tool_goes_through_the_guarded_entry_point() -> None:
    """Static proof (AST-based, not a substring grep) that `_fetch` -- the only function in
    this module that touches network I/O -- calls exclusively
    `fw.fetch_session_bars_guarded`, never any other fetch function."""
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


def test_no_date_construction_call_produces_a_holdout_date_anywhere_in_the_tool_source() -> None:
    """Static check (Phase 19's own suggested 'test or static check'): every `date(y, m, d)`
    or `date.fromisoformat("...")` call literal anywhere in this tool's source, if it
    constructs a fixed calendar date, must not fall inside the locked holdout range. This is
    AST-based (not a prose/docstring substring scan) so the module's own descriptive text
    about the locked range (e.g. in its docstring) is correctly not flagged."""
    tree = ast.parse(_TOOL_SOURCE)
    constructed_dates = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func_name = ast.unparse(node.func)
        all_constant_args = all(isinstance(a, ast.Constant) for a in node.args)
        if not all_constant_args:
            continue
        if func_name == "date" and len(node.args) == 3:
            args = [ast.literal_eval(a) for a in node.args]
            constructed_dates.append(HOLDOUT_START.__class__(*args))
        elif func_name == "date.fromisoformat" and len(node.args) == 1:
            value = ast.literal_eval(node.args[0])
            constructed_dates.append(HOLDOUT_START.__class__.fromisoformat(value))

    assert constructed_dates, "expected at least one literal date construction in this tool"
    for constructed in constructed_dates:
        assert not (HOLDOUT_START <= constructed <= HOLDOUT_END)


@pytest.mark.parametrize("symbol", SYMBOLS)
def test_every_symbol_is_part_of_the_fixed_8_symbol_universe(symbol: str) -> None:
    assert symbol in {"AAPL", "AMZN", "GOOGL", "META", "MSFT", "NVDA", "QQQ", "SPY"}


def test_family_names_cover_all_5_families_and_both_opening_range_variants() -> None:
    assert set(FAMILY_NAMES) == {
        "TREND_CONTINUATION",
        "VWAP_PULLBACK",
        "OPENING_RANGE_5",
        "OPENING_RANGE_15",
        "MEAN_REVERSION",
        "RELATIVE_STRENGTH",
    }
