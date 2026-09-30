"""MILESTONE-093 -- HTML rendering for the read-only strategy-discovery report.

NO TRADING CONTROLS. This page has no form, no button, no POST route, no CSRF token --
there is nothing here to authorize, approve, or submit. It renders ONE already-computed
JSON results file (`external-review/MILESTONE-093/screening-results.json`, produced
entirely offline by `tools/m093_family_screening.py`) plus the candidate-selection
rationale. No broker client, no persistence, no usecase handler is reachable from this
module -- see `tests/architecture/test_m093_report_boundaries.py`.

MOBILE-FIRST, reusing the same visual language as the M090/M091/M092 Owner consoles for a
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
.classification-no_candidate_edge { background: #3a1616; color: #e79a9a; }
.classification-candidate_selected { background: #123a2a; color: #5fe3a5; }
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
.pf-bad { color: #e79a9a; }
.pf-ok { color: #7fd9a8; }
"""


def _money(value: object) -> str:
    try:
        d = Decimal(str(value))
    except Exception:  # noqa: BLE001
        return "Not available"
    sign = "+" if d > 0 else ("-" if d < 0 else "")
    return f"{sign}${abs(d):,.2f}"


def _magnitude_money(value: object) -> str:
    """A plain dollar magnitude (e.g. max drawdown) -- never signed, since it is not a
    P&amp;L figure and a "+" prefix would misleadingly read as a gain."""
    try:
        d = abs(Decimal(str(value)))
    except Exception:  # noqa: BLE001
        return "Not available"
    return f"${d:,.2f}"


def _num(value: object, *, digits: int = 3) -> str:
    try:
        d = Decimal(str(value))
    except Exception:  # noqa: BLE001
        return "n/a"
    return f"{d:.{digits}f}"


def _pf_class(value: object) -> str:
    try:
        d = Decimal(str(value))
    except Exception:  # noqa: BLE001
        return ""
    return "pf-ok" if d > 1 else "pf-bad"


def _layout(*, title: str, body: str) -> str:
    return (
        "<!DOCTYPE html>"
        '<html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1, '
        'viewport-fit=cover">'
        f"<title>{_e(title)} — M093 Discovery Report</title>"
        '<link rel="stylesheet" href="/static/discovery-report.css"></head>'
        '<body><header><div class="brand">M093 Strategy Discovery</div>'
        '<div class="badge-row">'
        '<span class="badge badge-research">RESEARCH REPORT — READ ONLY</span>'
        '<span class="badge badge-readonly">NO TRADING CONTROLS</span>'
        '<span class="badge badge-locked">HOLDOUT LOCKED</span>'
        "</div></header>"
        f"<main>{body}</main></body></html>"
    )


_FAMILY_LABELS: dict[str, str] = {
    "TREND_CONTINUATION": "A — Trend Continuation",
    "VWAP_PULLBACK": "B — VWAP Pullback",
    "OPENING_RANGE_5": "C — Opening Range (5min)",
    "OPENING_RANGE_15": "C — Opening Range (15min)",
    "MEAN_REVERSION": "D — Mean Reversion",
    "RELATIVE_STRENGTH": "E — Relative Strength",
}


def report_page(results: dict[str, Any]) -> str:
    classification = results["classification"]
    class_class = "classification-" + classification.lower()
    families = results["families"]

    headline = (
        '<section class="card headline">'
        f"<h1>{_e(classification)}</h1>"
        f'<div class="classification {class_class}">{_e(classification)}</div>'
        f'<p class="muted">{_e(results["research_dataset"]["description"])} '
        f"({results['research_dataset']['session_count']} sessions)</p>"
        "</section>"
    )

    rows = "".join(
        (
            lambda c1: (
                f"<tr><td>{_e(_FAMILY_LABELS.get(name, name))}</td>"
                f'<td class="num">{c1["resolved"]}</td>'
                f'<td class="num">{_money(c1["net_pnl"])}</td>'
                f'<td class="num {_pf_class(c1["profit_factor"])}">'
                f"{_num(c1['profit_factor'])}</td>"
                f'<td class="num">{_money(c1["average_trade"])}</td>'
                f'<td class="num">{_magnitude_money(c1["max_drawdown"])}</td></tr>'
            )
        )(fam["cost_models"]["COST_MODEL_1_BASE_CONSERVATIVE"])
        for name, fam in sorted(families.items())
    )
    comparison = (
        '<section class="card"><h2>Family comparison (base cost, full research sample)</h2>'
        '<table class="report"><tr><th>Family</th><th>Trades</th><th>Net P&amp;L</th>'
        "<th>PF</th><th>Avg trade</th><th>Max DD</th></tr>"
        f"{rows}</table>"
        '<p class="muted">No family clears profit factor 1.0. Full detail (per-symbol, '
        "time-of-day, and walk-forward breakdowns) in "
        "<code>external-review/MILESTONE-093/family-screening.md</code>.</p></section>"
    )

    walk_forward_rows = "".join(
        (
            lambda wf: (
                f"<tr><td>{_e(_FAMILY_LABELS.get(name, name))}</td>"
                f'<td class="num {_pf_class(wf["design"]["profit_factor"])}">'
                f"{_num(wf['design']['profit_factor'])}</td>"
                f'<td class="num {_pf_class(wf["observe"]["profit_factor"])}">'
                f"{_num(wf['observe']['profit_factor'])}</td></tr>"
            )
        )(fam["walk_forward_cost_model_1"])
        for name, fam in sorted(families.items())
    )
    walk_forward = (
        '<section class="card"><h2>Walk-forward stability (within research data only)</h2>'
        '<table class="report"><tr><th>Family</th><th>Design PF</th>'
        "<th>Observe PF</th></tr>"
        f"{walk_forward_rows}</table>"
        '<p class="muted">Design/observe chronological split within the 100-session '
        "research dataset — never the locked final holdout. Every family's profit factor "
        "stays below 1.0 in both halves.</p></section>"
    )

    time_bucket_rows = "".join(
        (
            lambda tod: "".join(
                f"<tr><td>{_e(_FAMILY_LABELS.get(name, name))}</td>"
                f"<td>{_e(bucket.replace('_', ' ').title())}</td>"
                f'<td class="num {_pf_class(stats["profit_factor"])}">'
                f"{_num(stats['profit_factor'])}</td>"
                f'<td class="num">{stats["resolved"]}</td></tr>'
                for bucket, stats in sorted(tod.items())
            )
        )(fam["time_of_day_cost_model_1"])
        for name, fam in sorted(families.items())
    )
    time_of_day = (
        '<section class="card"><h2>Time-of-day breakdown (base cost)</h2>'
        '<table class="report"><tr><th>Family</th><th>Bucket</th><th>PF</th>'
        "<th>Trades</th></tr>"
        f"{time_bucket_rows}</table>"
        '<p class="muted">No bucket for any family clears breakeven — no regime-narrow '
        "edge was found.</p></section>"
    )

    selection = (
        '<section class="card"><h2>Candidate selection</h2>'
        '<p class="note note-warn">No family was selected. The Relative Strength family had '
        "the least-bad profit factor (0.736) and the smallest walk-forward degradation, but "
        "this is reported as the most structurally consistent of six failing families — not "
        "as grounds for selection. Full rationale in "
        "<code>external-review/MILESTONE-093/candidate-selection.md</code>.</p></section>"
    )

    holdout = (
        '<section class="card"><h2>Locked final holdout</h2>'
        '<p class="note note-locked"><strong>2026-03-18 through 2026-05-12</strong> was '
        "never fetched, inspected, or evaluated by any M093 code path — confirmed by the "
        "machine-enforced holdout guard, a functional test proving the guard refuses before "
        "any network call, and a static check over this milestone's own screening tool. It "
        "remains fully reserved for a future, separate M094.</p></section>"
    )

    next_section = (
        '<section class="card"><h2>Next</h2>'
        '<p class="muted">No credible candidate exists to carry into a final holdout '
        "validation. The next step is further strategy discovery (a differently-designed "
        "family or feature set), not automation of any family tested here.</p></section>"
    )

    limitations = (
        '<section class="card"><h2>Key limitations</h2><ul class="limits">'
        "<li>Real historical bid/ask spread evidence is not available — COST MODEL 1/2 are "
        "the same modeled assumptions as M091/M092, unchanged.</li>"
        "<li>Five families is a meaningful but bounded search, not an exhaustive one — this "
        "does not establish that no long-only intraday edge could ever exist on this "
        "platform.</li>"
        "<li>No claim of guaranteed or expected future profitability is made under any "
        "classification.</li>"
        "<li>Full detail: <code>external-review/MILESTONE-093/owner-report.md</code>, "
        "<code>family-screening.md</code>, <code>candidate-selection.md</code>, and "
        "<code>screening-results.json</code>.</li>"
        "</ul></section>"
    )

    body = (
        headline
        + comparison
        + walk_forward
        + time_of_day
        + selection
        + holdout
        + next_section
        + limitations
    )
    return _layout(title=classification, body=body)
