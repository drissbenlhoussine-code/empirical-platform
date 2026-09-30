"""MILESTONE-091 -- HTML rendering for the read-only strategy-validation report.

NO TRADING CONTROLS. This page has no form, no button, no POST route, no CSRF token --
there is nothing here to authorize, approve, or submit. It renders ONE already-computed
JSON results file (`external-review/MILESTONE-091/results.json`, produced entirely offline
by `tools/m091_validation.py`) and nothing else. No broker client, no persistence, no
usecase handler is reachable from this module -- see
`tests/architecture/test_m091_report_boundaries.py`.

MOBILE-FIRST, matching the M090 Owner console's own established visual language (same
palette/card/plan-tile conventions), reused here for a consistent Owner experience across
consoles -- not shared code (this module has no import of `_opportunity_engine_html.py`;
the two pages serve different purposes and must never accidentally couple).
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
main { padding: 16px; max-width: 680px; margin: 0 auto; }
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
.classification-no_edge_found { background: #3a1616; color: #e79a9a; }
.classification-candidate_edge { background: #123a2a; color: #5fe3a5; }
.classification-inconclusive { background: #3a3312; color: #e3c95f; }
.plan-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin: 4px 0 4px; }
.plan-tile {
  background: #0f1420; border: 1px solid #202536; border-radius: 10px; padding: 10px 12px;
}
.plan-tile.wide { grid-column: 1 / -1; }
.plan-label {
  color: #7c8aa3; font-size: 11px; font-weight: 700; text-transform: uppercase;
  letter-spacing: .05em; margin-bottom: 3px;
}
.plan-value { font-size: 19px; font-weight: 700; font-variant-numeric: tabular-nums; }
.plan-value.loss { color: #e79a9a; }
.plan-value.gain { color: #7fd9a8; }
table.report { width: 100%; border-collapse: collapse; font-size: 13.5px; margin-top: 6px; }
table.report th, table.report td {
  padding: 7px 6px; border-bottom: 1px solid #1c2333; text-align: left;
}
table.report th { color: #7c8aa3; font-weight: 700; font-size: 11px; text-transform: uppercase; }
.note { border-radius: 10px; padding: 12px 14px; margin: 12px 0; font-size: 14px; }
.note-info { background: #12203a; color: #8fb4e3; }
.note-warn { background: #3a3312; color: #e3c95f; }
ul.limits { margin: 0; padding-left: 20px; }
ul.limits li { margin: 6px 0; font-size: 14px; }
"""


def _format_money(d: Decimal) -> str:
    """ "$1,234.56" / "-$1,234.56" / "+$1,234.56" -- the sign always sits before the "$",
    never between it and the digits."""
    if d < 0:
        return f"-${-d:,.2f}"
    if d > 0:
        return f"+${d:,.2f}"
    return f"${d:,.2f}"


def _money(value: object) -> str:
    try:
        d = Decimal(str(value))
    except Exception:  # noqa: BLE001 - render "Not available" for any unparsable value
        return "Not available"
    tone = "gain" if d > 0 else ("loss" if d < 0 else "")
    formatted = _format_money(d)
    return f'<span class="{tone}">{formatted}</span>' if tone else formatted


def _plain_money(value: object) -> str:
    try:
        d = Decimal(str(value))
    except Exception:  # noqa: BLE001
        return "Not available"
    return _format_money(d)


def _num(value: object, *, digits: int = 2) -> str:
    try:
        d = Decimal(str(value))
    except Exception:  # noqa: BLE001
        return "Not available"
    return f"{d:.{digits}f}"


def _pct(value: object) -> str:
    try:
        d = Decimal(str(value)) * 100
    except Exception:  # noqa: BLE001
        return "Not available"
    return f"{d:.1f}%"


def _plan_tile(label: str, value: str, *, tone: str = "", wide: bool = False) -> str:
    classes = "plan-tile" + (" wide" if wide else "")
    value_classes = "plan-value" + (f" {tone}" if tone else "")
    return (
        f'<div class="{classes}"><div class="plan-label">{_e(label)}</div>'
        f'<div class="{value_classes}">{value}</div></div>'
    )


def _layout(*, title: str, body: str) -> str:
    return (
        "<!DOCTYPE html>"
        '<html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1, '
        'viewport-fit=cover">'
        f"<title>{_e(title)} — M091 Validation Report</title>"
        '<link rel="stylesheet" href="/static/validation-report.css"></head>'
        '<body><header><div class="brand">M091 Strategy Validation</div>'
        '<div class="badge-row">'
        '<span class="badge badge-research">RESEARCH REPORT — READ ONLY</span>'
        '<span class="badge badge-readonly">NO TRADING CONTROLS</span>'
        "</div></header>"
        f"<main>{body}</main></body></html>"
    )


def report_page(results: dict[str, Any]) -> str:
    classification = results["classification"]["classification"]
    class_class = "classification-" + classification.lower()
    full0 = results["full_sample"]["cost_model_0"]
    full1 = results["full_sample"]["cost_model_1"]
    full2 = results["full_sample"]["cost_model_2"]
    block_a = results["block_a_cost_model_1"]
    block_b = results["block_b_cost_model_1"]
    concentration = results["concentration_cost_model_1"]

    headline = (
        '<section class="card headline">'
        f"<h1>{_e(classification)}</h1>"
        f'<div class="classification {class_class}">{_e(classification)}</div>'
        f'<p class="muted">{_e(results["classification"]["rationale"])}</p>'
        "</section>"
    )

    pairs_excluded_text = f"{results['pairs_excluded']} of {results['total_pairs_requested']}"
    sample = (
        '<section class="card"><h2>Sample</h2>'
        '<div class="plan-grid">'
        + _plan_tile("Sessions", str(len(results["session_dates"])))
        + _plan_tile("Symbols", str(len(results["symbols"])))
        + _plan_tile("Pairs excluded", pairs_excluded_text)
        + _plan_tile("Excluded fraction", _pct(results["excluded_fraction"]))
        + _plan_tile("Opportunities", str(full1["opportunities"]), wide=True)
        + _plan_tile("Trades resolved", str(full1["trades_resolved"]), wide=True)
        + "</div>"
        f'<p class="muted">Policy fingerprint: {_e(results["fingerprint"])}</p>'
        "</section>"
    )

    net_pnl_tone = "loss" if Decimal(full1["net_pnl"]) < 0 else "gain"
    costs = (
        '<section class="card"><h2>Base-cost result (full sample)</h2>'
        '<div class="plan-grid">'
        + _plan_tile("Net P&amp;L", _money(full1["net_pnl"]), tone=net_pnl_tone)
        + _plan_tile("Profit factor", _num(full1["profit_factor"]))
        + _plan_tile("Hit rate", _pct(full1["hit_rate"]))
        + _plan_tile("Max drawdown", _plain_money(full1["max_drawdown"]))
        + "</div>"
        '<table class="report"><tr><th>Cost model</th><th>Net P&amp;L</th>'
        "<th>Profit factor</th></tr>"
        f"<tr><td>Idealized (zero friction)</td><td>{_plain_money(full0['net_pnl'])}</td>"
        f"<td>{_num(full0['profit_factor'])}</td></tr>"
        f"<tr><td>Base conservative (modeled)</td><td>{_plain_money(full1['net_pnl'])}</td>"
        f"<td>{_num(full1['profit_factor'])}</td></tr>"
        f"<tr><td>Stress (modeled)</td><td>{_plain_money(full2['net_pnl'])}</td>"
        f"<td>{_num(full2['profit_factor'])}</td></tr></table>"
        '<p class="note note-warn">COST MODEL 1/2 are modeled assumptions, never real '
        "historical spread/slippage measurements.</p>"
        "</section>"
    )

    blocks = (
        '<section class="card"><h2>Block A vs Block B (base cost)</h2>'
        '<table class="report"><tr><th></th><th>Trades</th><th>Net P&amp;L</th>'
        "<th>Profit factor</th><th>Avg trade</th></tr>"
        f"<tr><td>Block A</td><td>{block_a['trades_resolved']}</td>"
        f"<td>{_plain_money(block_a['net_pnl'])}</td><td>{_num(block_a['profit_factor'])}</td>"
        f"<td>{_plain_money(block_a['average_trade'])}</td></tr>"
        f"<tr><td>Block B</td><td>{block_b['trades_resolved']}</td>"
        f"<td>{_plain_money(block_b['net_pnl'])}</td><td>{_num(block_b['profit_factor'])}</td>"
        f"<td>{_plain_money(block_b['average_trade'])}</td></tr></table>"
        "</section>"
    )

    resolved = Decimal(full1["trades_resolved"])
    stop_share = _pct(Decimal(full1["stop_hits"]) / resolved)
    mandatory_share = _pct(Decimal(full1["mandatory_exits"]) / resolved)
    target_share = _pct(Decimal(full1["target_hits"]) / resolved)
    outcomes = (
        '<section class="card"><h2>Stop / Target / Mandatory Exit</h2>'
        '<table class="report"><tr><th>Outcome</th><th>Count</th><th>Share</th></tr>'
        f"<tr><td>Stop hit</td><td>{full1['stop_hits']}</td><td>{stop_share}</td></tr>"
        f"<tr><td>Mandatory exit</td><td>{full1['mandatory_exits']}</td>"
        f"<td>{mandatory_share}</td></tr>"
        f"<tr><td>Target hit</td><td>{full1['target_hits']}</td><td>{target_share}</td></tr>"
        "</table></section>"
    )

    per_symbol = results["per_symbol_cost_model_1"]
    symbol_rows = "".join(
        f"<tr><td>{_e(symbol)}</td><td>{row['trades_resolved']}</td>"
        f"<td>{_plain_money(row['net_pnl'])}</td><td>{_num(row['profit_factor'])}</td>"
        f"<td>{_pct(row['hit_rate']) if row['hit_rate'] is not None else 'n/a'}</td></tr>"
        for symbol, row in per_symbol.items()
    )
    symbols_section = (
        '<section class="card"><h2>Symbol breakdown (base cost)</h2>'
        '<table class="report"><tr><th>Symbol</th><th>Trades</th><th>Net P&amp;L</th>'
        f"<th>PF</th><th>Hit rate</th></tr>{symbol_rows}</table></section>"
    )

    per_hour = results["per_hour_utc_cost_model_1"]
    hour_rows = "".join(
        f"<tr><td>{_e(str(hour))}:00 UTC</td><td>{row['trades_resolved']}</td>"
        f"<td>{_plain_money(row['net_pnl'])}</td></tr>"
        for hour, row in sorted(per_hour.items(), key=lambda kv: int(kv[0]))
    )
    hours_section = (
        '<section class="card"><h2>Time-of-day breakdown (base cost)</h2>'
        '<table class="report"><tr><th>Decision hour</th><th>Trades</th>'
        f"<th>Net P&amp;L</th></tr>{hour_rows}</table></section>"
    )

    largest_winner = _plain_money(concentration["largest_winning_trade_pnl"])
    net_excluding_winner = _plain_money(concentration["net_pnl_excluding_largest_winner"])
    concentration_section = (
        '<section class="card"><h2>Concentration</h2>'
        '<table class="report">'
        f"<tr><td>Best symbol</td><td>{_e(concentration['best_symbol'])} "
        f"({_plain_money(concentration['best_symbol_pnl'])})</td></tr>"
        f"<tr><td>Best day</td><td>{_e(concentration['best_day'])} "
        f"({_plain_money(concentration['best_day_pnl'])})</td></tr>"
        f"<tr><td>Largest winning trade</td><td>{largest_winner}</td></tr>"
        "<tr><td>Net P&amp;L excluding largest winner</td>"
        f"<td>{net_excluding_winner}</td></tr>"
        "</table>"
        '<p class="note note-info">NVDA alone produced the large majority of resolved '
        "trades by count in this sample — a fragility signal, even where the mechanical "
        "P&amp;L-share concentration check above did not flag it (see the Owner report's "
        "own note on this).</p>"
        "</section>"
    )

    limitations = (
        '<section class="card"><h2>Key limitations</h2><ul class="limits">'
        "<li>Real historical bid/ask spread evidence is not available through the existing "
        "read-only client — COST MODEL 1/2 are modeled assumptions, not measurements.</li>"
        "<li>This result describes one FROZEN policy version over one historical sample — "
        "not a permanent verdict on intraday trading in general.</li>"
        "<li>No claim of guaranteed or expected future profitability is made under any "
        "classification.</li>"
        "<li>Full detail: <code>external-review/MILESTONE-091/owner-report.md</code> and "
        "<code>results.json</code>.</li>"
        "</ul></section>"
    )

    body = (
        headline
        + sample
        + costs
        + blocks
        + outcomes
        + symbols_section
        + hours_section
        + concentration_section
        + limitations
    )
    return _layout(title=classification, body=body)
