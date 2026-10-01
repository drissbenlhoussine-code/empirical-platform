"""MILESTONE-094 -- HTML rendering for the read-only edge-source-investigation report.

NO TRADING CONTROLS. This page has no form, no button, no POST route, no CSRF token --
there is nothing here to authorize, approve, or submit. It renders ONE already-computed
JSON results file (`external-review/MILESTONE-094/edge-source-results.json`, produced
entirely offline by `tools/m094_edge_source_study.py`). No broker client, no persistence,
no usecase handler is reachable from this module -- see
`tests/architecture/test_m094_report_boundaries.py`.

MOBILE-FIRST, reusing the same visual language as the M090-M093 Owner consoles for a
consistent Owner experience -- no import of any prior report module.
"""

from __future__ import annotations

from decimal import Decimal
from html import escape as _e
from typing import Any

__all__ = ["STYLESHEET", "report_page"]

STYLESHEET = """
* { box-sizing: border-box; -webkit-tap-highlight-color: transparent; }
html { -webkit-text-size-adjust: 100%; }
body {
  font: 16px/1.5 -apple-system, "SF Pro Text", "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  margin: 0;
  background: #0b0d12;
  color: #e7ebf3;
  overflow-x: hidden;
}
header { padding: 14px 16px; border-bottom: 1px solid #232735; }
.brand { font-weight: 700; font-size: 17px; margin-bottom: 8px; }
.badge-row { display: flex; flex-wrap: wrap; gap: 6px; }
.badge {
  background: #1c2333; border: 1px solid #313a52; border-radius: 6px;
  padding: 4px 10px; font-size: 11px; font-weight: 700; letter-spacing: .03em;
}
.badge-research { background: #123a2a; color: #5fe3a5; border-color: #1e5c42; }
.badge-readonly { background: #12203a; color: #8fb4e3; border-color: #1e3a5c; }
.badge-locked { background: #3a1616; color: #e79a9a; border-color: #5c1e1e; }
main { padding: 16px; max-width: 700px; margin: 0 auto; }
h1 { font-size: 21px; margin: 4px 0 6px; }
h2 { font-size: 16px; margin: 0 0 10px; }
.muted { color: #93a0b8; font-size: 13.5px; }
.card {
  background: #141826; border: 1px solid #232735; border-radius: 14px;
  padding: 18px; margin-bottom: 18px;
}
.headline { text-align: center; padding: 22px 18px; }
.classification {
  display: inline-block; padding: 8px 18px; border-radius: 20px;
  font-size: 18px; font-weight: 800; letter-spacing: .03em; margin: 6px 0 10px;
}
.classification-no_promising_edge_source { background: #3a1616; color: #e79a9a; }
.classification-promising_edge_sources_found { background: #123a2a; color: #5fe3a5; }
table.report { width: 100%; border-collapse: collapse; font-size: 13px; margin-top: 6px; }
table.report th, table.report td {
  padding: 6px 5px; border-bottom: 1px solid #1c2333; text-align: left;
}
table.report th { color: #7c8aa3; font-weight: 700; font-size: 10.5px; text-transform: uppercase; }
table.report td.num { text-align: right; font-variant-numeric: tabular-nums; }
.note { border-radius: 10px; padding: 12px 14px; margin: 12px 0; font-size: 14px; }
.note-info { background: #12203a; color: #8fb4e3; }
.note-warn { background: #3a3312; color: #e3c95f; }
.note-locked { background: #3a1616; color: #e79a9a; }
ul.limits { margin: 0; padding-left: 20px; }
ul.limits li { margin: 6px 0; font-size: 14px; }
.pos { color: #7fd9a8; }
.neg { color: #e79a9a; }
"""


def _percent(value: object) -> str:
    try:
        d = Decimal(str(value))
    except Exception:  # noqa: BLE001
        return "n/a"
    sign = "+" if d > 0 else ("" if d == 0 else "")
    return f"{sign}{d:.4f}%"


def _percent_class(value: object) -> str:
    try:
        d = Decimal(str(value))
    except Exception:  # noqa: BLE001
        return ""
    return "pos" if d > 0 else ("neg" if d < 0 else "")


def _layout(*, title: str, body: str) -> str:
    return (
        "<!DOCTYPE html>"
        '<html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1, '
        'viewport-fit=cover">'
        f"<title>{_e(title)} — M094 Edge Source Report</title>"
        '<link rel="stylesheet" href="/static/edge-source-report.css"></head>'
        '<body><header><div class="brand">M094 Edge Source Investigation</div>'
        '<div class="badge-row">'
        '<span class="badge badge-research">RESEARCH REPORT — READ ONLY</span>'
        '<span class="badge badge-readonly">NO TRADING CONTROLS</span>'
        '<span class="badge badge-locked">HOLDOUT LOCKED</span>'
        "</div></header>"
        f"<main>{body}</main></body></html>"
    )


def _horizon_table(horizon: dict[str, Any]) -> str:
    order = ["5m", "15m", "30m", "60m", "120m", "to_liquidation"]
    rows = "".join(
        f"<tr><td>{_e(label)}</td><td class='num'>{stats['n']}</td>"
        f"<td class='num {_percent_class(stats['mean_percent'])}'>"
        f"{_percent(stats['mean_percent'])}</td>"
        f"<td class='num'>{_percent(stats['stdev_percent'])}</td>"
        f"<td class='num'>{stats['sign_persistence_percent']:.1f}%</td></tr>"
        for label in order
        if label in horizon
        for stats in (horizon[label],)
    )
    return (
        '<section class="card"><h2>Horizon study (own-symbol, unconditional)</h2>'
        '<table class="report"><tr><th>Horizon</th><th>n</th><th>Mean</th>'
        "<th>Stdev</th><th>Sign +</th></tr>"
        f"{rows}</table>"
        '<p class="muted">Forward return from each 5-minute decision mark to the stated '
        "horizon, pooled across all 6 non-benchmark symbols and the 100-session research "
        "window.</p></section>"
    )


def _cross_sectional_card(cross_sectional: dict[str, Any]) -> str:
    rows = "".join(
        f"<tr><td>{_e(bucket)}</td><td class='num'>{stats['n']}</td>"
        f"<td class='num {_percent_class(stats['mean_30m_forward_return_percent'])}'>"
        f"{_percent(stats['mean_30m_forward_return_percent'])}</td></tr>"
        for bucket, stats in sorted(cross_sectional.get("by_bucket", {}).items())
    )
    spread = cross_sectional.get("strongest_minus_weakest_spread_percent")
    return (
        '<section class="card"><h2>Cross-sectional ranking (relative return vs SPY)</h2>'
        '<table class="report"><tr><th>Bucket</th><th>n</th><th>Mean 30m fwd</th></tr>'
        f"{rows}</table>"
        f'<p class="muted">STRONGEST − WEAKEST spread: {_percent(spread)}.</p></section>'
    )


def _selectivity_card(selectivity: dict[str, Any]) -> str:
    rows = "".join(
        f"<tr><td>{_e(label)}</td><td class='num'>{stats['n']}</td>"
        f"<td class='num {_percent_class(stats['mean_30m_forward_return_percent'])}'>"
        f"{_percent(stats['mean_30m_forward_return_percent'])}</td>"
        f"<td class='num'>{stats['max_single_symbol_share_percent']:.1f}%</td></tr>"
        for label, stats in selectivity.items()
    )
    return (
        '<section class="card"><h2>Selectivity (top-X% by cross-sectional strength)</h2>'
        '<table class="report"><tr><th>Bucket</th><th>n</th><th>Mean 30m fwd</th>'
        "<th>Max symbol share</th></tr>"
        f"{rows}</table></section>"
    )


def _regime_card(regime: dict[str, Any]) -> str:
    def _rows(group: dict[str, Any]) -> str:
        return "".join(
            f"<tr><td>{_e(label)}</td><td class='num'>{stats['n']}</td>"
            f"<td class='num {_percent_class(stats['mean_30m_forward_return_percent'])}'>"
            f"{_percent(stats['mean_30m_forward_return_percent'])}</td></tr>"
            for label, stats in sorted(group.items())
        )

    return (
        '<section class="card"><h2>Regime conditioning</h2>'
        '<table class="report"><tr><th>Regime</th><th>n</th><th>Mean 30m fwd</th></tr>'
        f"{_rows(regime.get('by_spy_vwap_position', {}))}"
        f"{_rows(regime.get('by_spy_session_return_sign', {}))}"
        f"{_rows(regime.get('by_own_trailing_volatility_bucket', {}))}"
        "</table></section>"
    )


def _scorecard_card(scorecard: dict[str, Any]) -> str:
    rows = "".join(
        f"<tr><td>{_e(direction)}</td>"
        f"<td>{_e(str(entry.get('observed_information_strength', '')))}</td>"
        f"<td>{_e(str(entry.get('cost_survivability', '')))}</td>"
        f"<td class='num'>{entry.get('sample_size', 0)}</td></tr>"
        for direction, entry in sorted(scorecard.items())
    )
    return (
        '<section class="card"><h2>Feature-family scorecard</h2>'
        '<table class="report"><tr><th>Direction</th><th>Strength</th>'
        "<th>Cost survivability</th><th>n</th></tr>"
        f"{rows}</table></section>"
    )


def report_page(results: dict[str, Any]) -> str:
    classification = results["classification"]
    class_class = "classification-" + classification.lower()
    dataset = results["research_dataset"]
    selected = results.get("selected_directions", [])

    headline = (
        '<section class="card headline">'
        f"<h1>{_e(classification)}</h1>"
        f'<div class="classification {class_class}">{_e(classification)}</div>'
        f'<p class="muted">{_e(dataset["description"])} '
        f"({dataset['session_count']} sessions, "
        f"{dataset['symbol_session_pairs_non_empty']} non-empty symbol-sessions)</p>"
        "</section>"
    )

    selected_card = (
        '<section class="card"><h2>Selected research directions</h2>'
        + (
            "<ul class='limits'>" + "".join(f"<li>{_e(d)}</li>" for d in selected) + "</ul>"
            if selected
            else '<p class="note note-warn">No direction cleared the Phase 17 eligibility '
            "bar. Classification: NO_PROMISING_EDGE_SOURCE.</p>"
        )
        + "</section>"
    )

    diagnosis = results["phase4_cost_turnover_diagnosis"]
    diagnosis_card = (
        '<section class="card"><h2>Why did V1/V2/M093 fail?</h2>'
        f'<p class="muted">{_e(diagnosis["conclusion"])}</p></section>'
    )

    gap = results.get("phase10_gap_study", {})
    gap_card = (
        '<section class="card"><h2>Opening gap / early session</h2>'
        f'<p class="note note-info">{_e(gap.get("event_data_note", ""))}</p></section>'
    )

    holdout = (
        '<section class="card"><h2>Locked final holdout</h2>'
        '<p class="note note-locked"><strong>2026-03-18 through 2026-05-12</strong> was '
        "never fetched, inspected, or evaluated by any M094 code path -- confirmed by the "
        "machine-enforced holdout guard (carried forward verbatim from M093), a functional "
        "test proving the guard refuses before any network call, and a static check over "
        "this milestone's own study tool. It remains fully reserved for a future, separate "
        "milestone.</p></section>"
    )

    limitations = (
        '<section class="card"><h2>Key limitations</h2><ul class="limits">'
        "<li>This is an information-value survey, not a strategy backtest -- no entry/stop/"
        "target geometry or position sizing was built for any direction studied here.</li>"
        "<li>Real historical bid/ask spread evidence is not available -- COST MODEL 1/2 are "
        "the same modeled assumptions as M091/M092/M093, unchanged.</li>"
        "<li>No event/news/earnings data source exists in this repository "
        "(EVENT_DATA_NOT_AVAILABLE) -- the opening-gap study uses only prior-close/"
        "today-open displacement, which is legitimately available.</li>"
        "<li>No claim of guaranteed or expected future profitability is made under any "
        "classification.</li>"
        "<li>Full detail: <code>external-review/MILESTONE-094/owner-report.md</code> and "
        "<code>edge-source-results.json</code>.</li>"
        "</ul></section>"
    )

    body = (
        headline
        + selected_card
        + diagnosis_card
        + _horizon_table(results["phase5_horizon_study"])
        + _regime_card(results["phase7_regime"])
        + _cross_sectional_card(results["phase8_cross_sectional"])
        + _selectivity_card(results["phase9_selectivity"])
        + gap_card
        + _scorecard_card(results["phase16_scorecard"])
        + holdout
        + limitations
    )
    return _layout(title=classification, body=body)
