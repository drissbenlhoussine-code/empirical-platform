"""MILESTONE-092 -- HTML rendering for the read-only V2 strategy-rework report.

NO TRADING CONTROLS. This page has no form, no button, no POST route, no CSRF token --
there is nothing here to authorize, approve, or submit. It renders ONE already-computed
JSON results file (`external-review/MILESTONE-092/results-v2.json`, produced entirely
offline by `tools/m092_validate_holdout.py`) plus the DEVELOPMENT candidate-comparison
table (hand-transcribed from `external-review/MILESTONE-092/candidate-comparison.md`, since
the three failed candidates are not themselves in the JSON). No broker client, no
persistence, no usecase handler is reachable from this module -- see
`tests/architecture/test_m092_report_boundaries.py`.

MOBILE-FIRST, reusing the same visual language as the M090/M091 Owner consoles for a
consistent Owner experience -- not shared code (no import of either prior report module).
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
.classification-no_edge_v2 { background: #3a1616; color: #e79a9a; }
.classification-candidate_edge_v2 { background: #123a2a; color: #5fe3a5; }
.classification-inconclusive_v2 { background: #3a3312; color: #e3c95f; }
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
.pill {
  display: inline-block; padding: 3px 9px; border-radius: 20px; font-size: 10.5px;
  font-weight: 800; letter-spacing: .04em; text-transform: uppercase;
  background: #1c2333; color: #93a0b8;
}
.pill.selected { background: #123a2a; color: #5fe3a5; }
"""


def _format_money(d: Decimal) -> str:
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


def _magnitude_money(value: object) -> str:
    """A plain dollar magnitude (e.g. max drawdown) -- never signed, since it is not a
    P&amp;L figure and a "+" prefix would misleadingly read as a gain."""
    try:
        d = abs(Decimal(str(value)))
    except Exception:  # noqa: BLE001
        return "Not available"
    return f"${d:,.2f}"


def _pct(value: object) -> str:
    try:
        d = Decimal(str(value))
    except Exception:  # noqa: BLE001
        return "Not available"
    return f"{d:.1f}%"


def _pct_fraction(value: object) -> str:
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
        f"<title>{_e(title)} — M092 V2 Report</title>"
        '<link rel="stylesheet" href="/static/v2-report.css"></head>'
        '<body><header><div class="brand">M092 Strategy Rework (V2)</div>'
        '<div class="badge-row">'
        '<span class="badge badge-research">RESEARCH REPORT — READ ONLY</span>'
        '<span class="badge badge-readonly">NO TRADING CONTROLS</span>'
        "</div></header>"
        f"<main>{body}</main></body></html>"
    )


#: The three DEVELOPMENT candidates -- not in results-v2.json (only the SELECTED one's
#: VALIDATION/HOLDOUT numbers are), transcribed from candidate-comparison.md's own table so
#: Phase 20's "show failed candidates too" requirement is visible on this page, not just in
#: the markdown report.
_DEVELOPMENT_CANDIDATES: tuple[dict[str, str], ...] = (
    {
        "name": "V2-A",
        "description": "entry quality only",
        "trades": "285",
        "net": "-519.34",
        "pf": "0.63",
        "avg": "-1.82",
        "unresolved": "28",
        "selected": "",
    },
    {
        "name": "V2-B",
        "description": "+ normalized liquidity",
        "trades": "4,085",
        "net": "-6298.56",
        "pf": "0.56",
        "avg": "-1.54",
        "unresolved": "33",
        "selected": "",
    },
    {
        "name": "V2-C",
        "description": "+ time-to-target feasibility",
        "trades": "3,337",
        "net": "-5090.61",
        "pf": "0.54",
        "avg": "-1.53",
        "unresolved": "0",
        "selected": "selected",
    },
)


def _period_card(title: str, metrics: dict[str, Any], concentration: dict[str, Any] | None) -> str:
    net1 = Decimal(str(metrics["cost_model_1"]["net_pnl"]))
    tone = "loss" if net1 < 0 else "gain"
    net1_text = _money(metrics["cost_model_1"]["net_pnl"])
    body = (
        f'<section class="card"><h2>{_e(title)}</h2>'
        '<div class="plan-grid">'
        + _plan_tile("Trades resolved", str(metrics["cost_model_1"]["trades_resolved"]))
        + _plan_tile("Net P&amp;L (base cost)", net1_text, tone=tone)
        + _plan_tile("Profit factor", _num(metrics["cost_model_1"]["profit_factor"]))
        + _plan_tile("Average trade", _plain_money(metrics["cost_model_1"]["average_trade"]))
        + _plan_tile("Max drawdown", _magnitude_money(metrics["cost_model_1"]["max_drawdown"]))
        + _plan_tile("Hit rate", _pct_fraction(metrics["cost_model_1"]["hit_rate"]))
        + "</div>"
        '<table class="report"><tr><th>Cost model</th><th>Net P&amp;L</th>'
        "<th>Profit factor</th></tr>"
        f"<tr><td>Idealized</td><td>{_plain_money(metrics['cost_model_0']['net_pnl'])}</td>"
        f"<td>{_num(metrics['cost_model_0']['profit_factor'])}</td></tr>"
        f"<tr><td>Base conservative</td><td>{_plain_money(metrics['cost_model_1']['net_pnl'])}</td>"
        f"<td>{_num(metrics['cost_model_1']['profit_factor'])}</td></tr>"
        f"<tr><td>Stress</td><td>{_plain_money(metrics['cost_model_2']['net_pnl'])}</td>"
        f"<td>{_num(metrics['cost_model_2']['profit_factor'])}</td></tr></table>"
    )
    c1 = metrics["cost_model_1"]
    resolved = Decimal(str(c1["trades_resolved"]))
    if resolved > 0:
        stop_share = _pct_fraction(Decimal(str(c1["stop_hits"])) / resolved)
        target_share = _pct_fraction(Decimal(str(c1["target_hits"])) / resolved)
        mandatory_share = _pct_fraction(Decimal(str(c1["mandatory_exits"])) / resolved)
        body += (
            '<table class="report"><tr><th>Outcome</th><th>Count</th><th>Share</th></tr>'
            f"<tr><td>Stop hit</td><td>{c1['stop_hits']}</td><td>{stop_share}</td></tr>"
            f"<tr><td>Target hit</td><td>{c1['target_hits']}</td><td>{target_share}</td></tr>"
            f"<tr><td>Mandatory exit</td><td>{c1['mandatory_exits']}</td>"
            f"<td>{mandatory_share}</td></tr></table>"
        )
    if concentration is not None:
        top_symbol_count = _e(concentration["top_symbol_by_trade_count"])
        top_symbol_count_share = _pct(concentration["top_symbol_trade_count_share_percent"])
        top_symbol_profit = _e(concentration["top_symbol_by_gross_profit"])
        top_symbol_profit_share = _pct(concentration["top_symbol_gross_profit_share_percent"])
        top_day_profit = _e(concentration["top_day_by_gross_profit"])
        top_day_profit_share = _pct(concentration["top_day_gross_profit_share_percent"])
        body += (
            '<table class="report">'
            f"<tr><td>Top symbol (trade count)</td>"
            f"<td>{top_symbol_count} ({top_symbol_count_share})</td></tr>"
            f"<tr><td>Top symbol (gross profit)</td>"
            f"<td>{top_symbol_profit} ({top_symbol_profit_share})</td></tr>"
            f"<tr><td>Top day (gross profit)</td>"
            f"<td>{top_day_profit} ({top_day_profit_share})</td></tr>"
            "</table>"
        )
    body += "</section>"
    return body


def report_page(results: dict[str, Any]) -> str:
    classification = results["classification"]["classification"]
    class_class = "classification-" + classification.lower()

    headline = (
        '<section class="card headline">'
        f"<h1>{_e(classification)}</h1>"
        f'<div class="classification {class_class}">{_e(classification)}</div>'
        f'<p class="muted">Selected candidate: {_e(results["selected_candidate"])} '
        f"&middot; fingerprint {_e(results['frozen_fingerprint'][:16])}&hellip;</p>"
        "</section>"
    )

    sample = (
        '<section class="card"><h2>Periods</h2>'
        '<div class="plan-grid">'
        + _plan_tile("Development sessions", str(len(results["development_dates"])), wide=True)
        + _plan_tile("Validation sessions", str(len(results["validation_dates"])))
        + _plan_tile(
            "Holdout sessions",
            str(len(results["holdout_dates"])) if results["holdout_dates"] else "Not run",
        )
        + "</div>"
        "</section>"
    )

    candidate_rows = "".join(
        f"<tr><td>{_e(c['name'])} "
        f'<span class="pill{" selected" if c["selected"] else ""}">'
        f"{'selected' if c['selected'] else ''}</span></td>"
        f"<td>{_e(c['description'])}</td><td>{c['trades']}</td>"
        f"<td>{_plain_money(c['net'])}</td><td>{c['pf']}</td><td>{c['unresolved']}</td></tr>"
        for c in _DEVELOPMENT_CANDIDATES
    )
    candidates_section = (
        '<section class="card"><h2>Development candidates (none selected for best P&amp;L)</h2>'
        '<p class="muted">All three failed to show a development edge; V2-C was selected for '
        "structural robustness (zero unresolved trades), not performance.</p>"
        '<table class="report"><tr><th>Candidate</th><th>Change</th><th>Trades</th>'
        "<th>Net P&amp;L</th><th>PF</th><th>Unresolved</th></tr>"
        f"{candidate_rows}</table></section>"
    )

    validation_section = _period_card(
        "Validation (unseen data, run once)",
        results["validation"],
        results["validation"].get("concentration_cost_model_1"),
    )

    if results["holdout"] is not None:
        holdout_section = _period_card(
            "Final holdout (unseen data, run once)",
            results["holdout"],
            results["holdout"].get("concentration_cost_model_1"),
        )
    else:
        holdout_section = (
            '<section class="card"><h2>Final holdout</h2>'
            '<p class="note note-info">Never fetched or evaluated. Validation did not clear '
            "the bar required to proceed (net &gt; 0, profit factor &gt; 1, average trade "
            "&gt; 0) -- per the mission's own rule, the holdout period remains genuinely "
            "unseen.</p></section>"
        )

    rationale_section = (
        '<section class="card"><h2>Classification rationale</h2>'
        f'<p class="muted">{_e(results["classification"]["rationale"])}</p></section>'
    )

    limitations = (
        '<section class="card"><h2>Key limitations</h2><ul class="limits">'
        "<li>Real historical bid/ask spread evidence is not available through the existing "
        "read-only client — COST MODEL 1/2 are modeled assumptions, identical to M091's, not "
        "measurements.</li>"
        "<li>This result describes one FROZEN V2-C policy over one unseen validation sample "
        "— not a verdict on whether any rework of this engine could ever work.</li>"
        "<li>No claim of guaranteed or expected future profitability is made under any "
        "classification.</li>"
        "<li>Full detail: <code>external-review/MILESTONE-092/owner-report.md</code>, "
        "<code>candidate-comparison.md</code>, and <code>results-v2.json</code>.</li>"
        "</ul></section>"
    )

    body = (
        headline
        + sample
        + candidates_section
        + validation_section
        + holdout_section
        + rationale_section
        + limitations
    )
    return _layout(title=classification, body=body)
