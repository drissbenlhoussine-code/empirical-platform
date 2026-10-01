"""MILESTONE-095 -- HTML rendering for the read-only event-driven-edge-research report.

NO TRADING CONTROLS. This page has no form, no button, no POST route, no CSRF token --
there is nothing here to authorize, approve, or submit. It renders ONE already-computed
JSON results file (`external-review/MILESTONE-095/event-study-results.json`, produced
entirely offline by `tools/m095_event_study.py`). No broker client, no persistence, no
usecase handler is reachable from this module -- see
`tests/architecture/test_m095_report_boundaries.py`.

MOBILE-FIRST, reusing the same visual language as the M090-M094 Owner consoles for a
consistent Owner experience -- no import of any prior report module.
"""

from __future__ import annotations

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
.classification-no_event_edge_found { background: #3a1616; color: #e79a9a; }
.classification-event_edge_directions_found { background: #123a2a; color: #5fe3a5; }
.classification-event_data_blocked { background: #3a1616; color: #e79a9a; }
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
    if value is None:
        return "n/a"
    try:
        v = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return "n/a"
    sign = "+" if v > 0 else ""
    return f"{sign}{v:.4f}%"


def _percent_class(value: object) -> str:
    if value is None:
        return ""
    try:
        v = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return ""
    return "pos" if v > 0 else ("neg" if v < 0 else "")


def _layout(*, title: str, body: str) -> str:
    return (
        "<!DOCTYPE html>"
        '<html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1, '
        'viewport-fit=cover">'
        f"<title>{_e(title)} — M095 Event Report</title>"
        '<link rel="stylesheet" href="/static/event-report.css"></head>'
        '<body><header><div class="brand">M095 Event-Driven Edge Research</div>'
        '<div class="badge-row">'
        '<span class="badge badge-research">RESEARCH REPORT — READ ONLY</span>'
        '<span class="badge badge-readonly">NO TRADING CONTROLS</span>'
        '<span class="badge badge-locked">HOLDOUT LOCKED</span>'
        "</div></header>"
        f"<main>{body}</main></body></html>"
    )


def _horizon_stats_row(label: str, stats: dict[str, Any]) -> str:
    n = stats.get("n", 0)
    if not n:
        return f"<tr><td>{_e(label)}</td><td class='num'>0</td><td colspan='2'>n/a</td></tr>"
    mean = stats.get("mean")
    pf = stats.get("positive_fraction")
    pf_text = f"{pf * 100:.1f}%" if pf is not None else "n/a"
    return (
        f"<tr><td>{_e(label)}</td><td class='num'>{n}</td>"
        f"<td class='num {_percent_class(mean)}'>{_percent(mean)}</td>"
        f"<td class='num'>{pf_text}</td></tr>"
    )


def _event_vs_control_section(control: dict[str, Any]) -> str:
    rows = ""
    for bucket_name, groups in control.items():
        with_event = groups.get("with_event", {}).get("30m", {})
        without_event = groups.get("without_event", {}).get("30m", {})
        rows += _horizon_stats_row(f"{bucket_name} + event", with_event)
        rows += _horizon_stats_row(f"{bucket_name} no event", without_event)
    return (
        '<section class="card"><h2>Event + gap vs. control (30m forward return)</h2>'
        '<table class="report"><tr><th>Group</th><th>n</th><th>Mean</th><th>Positive %</th></tr>'
        f"{rows}</table>"
        '<p class="muted">Gap-up sessions with a company-specific news event known before '
        "the open, vs. gap-up sessions of the same magnitude bucket with no known "
        "event.</p></section>"
    )


def _gap_bucket_section(gap_table: dict[str, Any]) -> str:
    order = ["GAP_DOWN_LARGE", "GAP_DOWN_SMALL", "FLAT", "GAP_UP_SMALL", "GAP_UP_LARGE"]
    rows = "".join(
        _horizon_stats_row(label, gap_table[label]["30m"]) for label in order if label in gap_table
    )
    return (
        '<section class="card"><h2>Gap bucket table (30m forward return, all sessions)</h2>'
        '<table class="report"><tr><th>Bucket</th><th>n</th><th>Mean</th><th>Positive %</th></tr>'
        f"{rows}</table></section>"
    )


def _cost_section(cost: dict[str, Any]) -> str:
    mean_move = cost.get("event_gap_up_30m_mean_move_percent")
    survives1 = cost.get("survives_cost1")
    survives2 = cost.get("survives_cost2")
    verdict1 = (
        '<strong class="pos">survives</strong>'
        if survives1
        else '<strong class="neg">does not survive</strong>'
    )
    verdict2 = (
        '<strong class="pos">survives</strong>'
        if survives2
        else '<strong class="neg">does not survive</strong>'
    )
    return (
        '<section class="card"><h2>Cost survivability</h2>'
        f'<p>Event + gap-up mean 30m move: <strong class="{_percent_class(mean_move)}">'
        f"{_percent(mean_move)}</strong></p>"
        f"<p>COST1 round trip: {cost.get('cost1_round_trip_percent', 'n/a')}% — {verdict1}</p>"
        f"<p>COST2 round trip: {cost.get('cost2_round_trip_percent', 'n/a')}% — {verdict2}</p>"
        "</section>"
    )


def _temporal_section(temporal: dict[str, Any]) -> str:
    first = temporal.get("first_half_mean_event_gap_up_30m")
    second = temporal.get("second_half_mean_event_gap_up_30m")
    return (
        '<section class="card"><h2>Temporal stability</h2>'
        f"<p>First half (n={temporal.get('first_half_n', 0)}): "
        f'<span class="{_percent_class(first)}">{_percent(first)}</span></p>'
        f"<p>Second half (n={temporal.get('second_half_n', 0)}): "
        f'<span class="{_percent_class(second)}">{_percent(second)}</span></p>'
        "</section>"
    )


def _cross_symbol_section(cross_symbol: dict[str, Any]) -> str:
    rows = "".join(
        f"<tr><td>{_e(symbol)}</td><td class='num'>{stats['n']}</td>"
        f"<td class='num {_percent_class(stats['mean_30m'])}'>"
        f"{_percent(stats['mean_30m'])}</td></tr>"
        for symbol, stats in sorted(cross_symbol.items())
    )
    return (
        '<section class="card"><h2>Cross-symbol stability (event + gap-up, 30m)</h2>'
        '<table class="report"><tr><th>Symbol</th><th>n</th><th>Mean</th></tr>'
        f"{rows}</table></section>"
    )


def _selectivity_section(selectivity: dict[str, Any]) -> str:
    ic = selectivity.get("spearman_ic")
    ic_text = f"{ic:.4f}" if ic is not None else "n/a"
    return (
        '<section class="card"><h2>Selectivity (gap magnitude vs. 30m forward return)</h2>'
        f"<p>n={selectivity.get('n', 0)}, Spearman IC = {ic_text}</p>"
        '<p class="muted">Among event-present gap-up observations: does a larger gap '
        "correspond to a larger subsequent move?</p></section>"
    )


def _frequency_section(frequency: dict[str, Any]) -> str:
    return (
        '<section class="card"><h2>Frequency economics</h2>'
        f"<p>Events per symbol per month: {frequency.get('events_per_symbol_month', 'n/a')}</p>"
        "<p>Event + gap-up opportunities per month (all symbols): "
        f"{frequency.get('event_gap_up_opportunities_per_month_all_symbols', 'n/a')}</p>"
        "<p>Event + gap-up opportunities per week (all symbols): "
        f"{frequency.get('event_gap_up_opportunities_per_week_all_symbols', 'n/a')}</p>"
        "</section>"
    )


def _directions_section(directions: list[dict[str, Any]]) -> str:
    rows = "".join(
        f"<li><strong>{_e(d['direction'])}</strong> — "
        f"cost1: {'✓' if d['survives_cost1'] else '✗'}, "
        f"temporal: {'✓' if d['temporally_stable'] else '✗'}, "
        f"not concentrated: {'✓' if not d['cross_symbol_concentrated'] else '✗'}, "
        f"sign agreement: {'✓' if d['cross_symbol_sign_agreement'] else '✗'} — "
        f"<strong class='{'pos' if d['eligible'] else 'neg'}'>"
        f"{'ELIGIBLE' if d['eligible'] else 'NOT ELIGIBLE'}</strong></li>"
        for d in directions
    )
    return (
        '<section class="card"><h2>Candidate direction gate</h2>'
        f'<ul class="limits">{rows}</ul></section>'
    )


def _data_provider_section(event_data: dict[str, Any]) -> str:
    return (
        '<section class="card"><h2>Data provider</h2>'
        f"<p>Source: {_e(event_data.get('source', 'n/a'))}</p>"
        f"<p>Company-specific articles: {event_data.get('total_company_specific_articles', 0)} "
        f"({event_data.get('earnings_keyword_articles', 0)} earnings-keyword, "
        f"{event_data.get('other_news_articles', 0)} other)</p>"
        '<p class="muted">Qualified for event-presence + a predeclared earnings-keyword flag '
        "only — no structured earnings-surprise, guidance, or analyst-rating fields are "
        "available from any already-credentialed source. See "
        "<code>external-review/MILESTONE-095/data-source-qualification.md</code>.</p></section>"
    )


def report_page(results: dict[str, Any]) -> str:
    classification = results["classification"]
    class_class = "classification-" + classification.lower()
    dataset = results["research_dataset"]

    headline = (
        '<section class="card headline">'
        f"<h1>{_e(classification)}</h1>"
        f'<div class="classification {class_class}">{_e(classification)}</div>'
        f'<p class="muted">{dataset["session_count"]} sessions '
        f"({dataset['first_date']} → {dataset['last_date']}), "
        f"{len(dataset['symbols_ranked'])} ranked symbols</p>"
        "</section>"
    )

    holdout = results["locked_holdout"]
    holdout_section = (
        '<section class="card"><h2>Locked final holdout</h2>'
        f'<p class="note note-locked"><strong>{holdout["start"]} through {holdout["end"]}</strong> '
        f"— accessed: {'YES — VIOLATION' if holdout['accessed'] else 'NO'}. Enforced by the "
        "same machine-enforced guard M093/M094 used, carried forward unchanged, covering both "
        "the bar fetch and the news fetch independently.</p></section>"
    )

    broker = results["broker_writes"]
    broker_section = (
        '<section class="card"><h2>Broker writes</h2>'
        f"<p>BUY {broker['buy']} · SELL {broker['sell']} · CANCEL {broker['cancel']} · "
        f"LIVE {broker['live']}</p></section>"
    )

    body = (
        headline
        + _data_provider_section(results["event_data"])
        + _gap_bucket_section(results["gap_bucket_table"])
        + _event_vs_control_section(results["event_vs_control"])
        + _cost_section(results["cost_survivability"])
        + _temporal_section(results["temporal_stability"])
        + _cross_symbol_section(results["cross_symbol_stability"])
        + _selectivity_section(results["selectivity"])
        + _frequency_section(results["frequency"])
        + _directions_section(results["selected_directions"])
        + holdout_section
        + broker_section
    )
    return _layout(title=classification, body=body)
