"""MILESTONE-090 -- HTML rendering for the Opportunity Engine's own console.

A SEPARATE, NEW CONSOLE, NOT A CHANGE TO THE EXISTING ONE. `_operator_console_html.py`
(M086-M089) is untouched by this module: Phase 22's own instruction is "do not alter stable
production consoles," and this milestone's Today page is its own thing, reached at its own
URL, never merged into the SIMULATION/PAPER console's `/today`. The web plumbing
(`_operator_console_web.Router`/`Request`/`Response`/`SecuritySession`/`serve`) IS reused --
it carries no business logic and was already written to be capability-neutral.

NO GENERIC "BUY" LANGUAGE, NO PROBABILITY LANGUAGE. Every card says "SELL_TO_CLOSE" nowhere
(this engine is entry-only, long-only) and says "BUY (research plan only -- not yet approved
or sent)" rather than a bare "Buy SYMBOL". "Opportunity Quality" is never rendered as "chance
of profit" or "win probability" anywhere in this file.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from html import escape as _e

from empirical_platform.usecases.opportunity_engine import OpportunityStatus, TradingOpportunity

__all__ = [
    "STYLESHEET",
    "approve_confirmation_page",
    "ignore_confirmation_page",
    "message_page",
    "review_page",
    "today_page",
]

STYLESHEET = """
body {
  font: 15px/1.5 -apple-system, Segoe UI, Helvetica, Arial, sans-serif;
  margin: 0;
  background: #0b0d12;
  color: #e7ebf3;
}
header {
  padding: 16px 20px;
  border-bottom: 1px solid #232735;
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.brand { font-weight: 700; font-size: 17px; }
.badge {
  background: #1c2333;
  border: 1px solid #313a52;
  border-radius: 6px;
  padding: 3px 10px;
  font-size: 12px;
  letter-spacing: .04em;
}
main { padding: 20px; max-width: 900px; margin: 0 auto; }
h1 { font-size: 20px; margin: 0 0 6px; }
.muted { color: #93a0b8; font-size: 13px; }
.grid { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; margin: 14px 0; }
.card {
  background: #141826;
  border: 1px solid #232735;
  border-radius: 10px;
  padding: 16px;
  margin-bottom: 16px;
}
.card h2 { margin: 0 0 4px; font-size: 18px; }
.quality {
  display: inline-block;
  padding: 2px 10px;
  border-radius: 20px;
  font-size: 12px;
  font-weight: 700;
  margin-left: 8px;
}
.quality-strong { background: #123a2a; color: #5fe3a5; }
.quality-moderate { background: #3a3312; color: #e3c95f; }
.quality-weak { background: #3a1616; color: #e35f5f; }
dl.kv { display: grid; grid-template-columns: auto 1fr; gap: 4px 14px; margin: 10px 0; }
dl.kv dt { color: #93a0b8; font-size: 12px; text-transform: uppercase; letter-spacing: .03em; }
dl.kv dd { margin: 0; font-variant-numeric: tabular-nums; }
ul.evidence { margin: 8px 0 0; padding-left: 18px; }
ul.evidence li { margin: 3px 0; }
.note { border-radius: 8px; padding: 10px 12px; margin: 10px 0; font-size: 13.5px; }
.note-warn { background: #3a3312; color: #e3c95f; }
.note-danger { background: #3a1616; color: #e79a9a; }
.note-info { background: #12203a; color: #8fb4e3; }
.btn {
  display: inline-block;
  padding: 9px 16px;
  border-radius: 8px;
  border: 1px solid transparent;
  font-size: 14px;
  font-weight: 600;
  text-decoration: none;
  cursor: pointer;
}
.btn-primary { background: #2a63e0; color: #fff; }
.btn-danger { background: #7a2323; color: #fff; }
.btn-secondary { background: #1c2333; color: #e7ebf3; border-color: #313a52; }
.rejected { opacity: .7; }
table.reject { width: 100%; border-collapse: collapse; font-size: 13px; }
table.reject td, table.reject th {
  padding: 6px 8px;
  border-bottom: 1px solid #232735;
  text-align: left;
}
"""


def _when(value: datetime | None) -> str:
    if value is None:
        return "Not available"
    return value.astimezone(value.tzinfo).strftime("%Y-%m-%d %H:%M:%S %Z")


def _money(value: Decimal | None) -> str:
    return "Not available" if value is None else f"${value:,.2f}"


def _quality_label(score: Decimal | None) -> tuple[str, str]:
    """(css class, label). Never "chance of profit"/"win probability" -- a research quality
    label over measurable, already-gated evidence, per Phase 14."""
    if score is None:
        return "quality-weak", "Not scored"
    if score >= Decimal("70"):
        return "quality-strong", "Strong"
    if score >= Decimal("40"):
        return "quality-moderate", "Moderate"
    return "quality-weak", "Weak"


def _layout(*, title: str, body: str) -> str:
    return (
        "<!DOCTYPE html>"
        '<html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>{_e(title)} — Opportunity Engine</title>"
        '<link rel="stylesheet" href="/static/opportunity-engine.css"></head>'
        '<body><header><div class="brand">Opportunity Engine '
        '<span class="badge">M090 · RESEARCH — NOT AUTOMATIC TRADING</span></div>'
        '<div class="badge">Long-only · Owner approval required</div></header>'
        f"<main>{body}</main></body></html>"
    )


def _csrf(csrf: str) -> str:
    return f'<input type="hidden" name="csrf_token" value="{_e(csrf)}">'


def message_page(*, title: str, message: str, back: str = "/today") -> str:
    body = (
        f"<h1>{_e(title)}</h1>"
        f'<p class="note note-warn">{_e(message)}</p>'
        f'<a class="btn btn-secondary" href="{_e(back)}">← Back</a>'
    )
    return _layout(title=title, body=body)


def _rejection_summary(opportunity: TradingOpportunity) -> str:
    reasons = ", ".join(r.value.replace("_", " ").title() for r in opportunity.rejection_reasons)
    return reasons or "Not available"


def _opportunity_card(opportunity: TradingOpportunity, csrf: str) -> str:
    quality_class, quality_label = _quality_label(opportunity.quality_score)
    score_text = "" if opportunity.quality_score is None else f" ({opportunity.quality_score})"
    evidence = "".join(f"<li>{_e(item)}</li>" for item in opportunity.evidence)
    potential_gain = (
        None
        if opportunity.reward_per_share is None or opportunity.quantity is None
        else opportunity.reward_per_share * Decimal(opportunity.quantity)
    )
    invalid_if = (
        f"Price falls to or reaches the stop (${opportunity.stop_price}), the quote goes stale "
        "or the spread widens beyond policy, the entry moves outside the allowed tolerance "
        "before you approve, or the mandatory exit time passes."
        if opportunity.stop_price is not None
        else "Any hard gate (session, data quality, liquidity, structure, risk) no longer passes."
    )
    quantity_text = (
        "Not available" if opportunity.quantity is None else f"{opportunity.quantity} shares"
    )
    reward_risk_text = (
        "Not available"
        if opportunity.reward_risk_ratio is None
        else str(opportunity.reward_risk_ratio)
    )
    terms = (
        '<dl class="kv">'
        f"<dt>Entry</dt><dd>{_money(opportunity.entry_price)}</dd>"
        f"<dt>Stop</dt><dd>{_money(opportunity.stop_price)}</dd>"
        f"<dt>Target</dt><dd>{_money(opportunity.target_price)}</dd>"
        f"<dt>Quantity</dt><dd>{quantity_text}</dd>"
        f"<dt>Notional</dt><dd>{_money(opportunity.notional)}</dd>"
        f"<dt>Max loss</dt><dd>{_money(opportunity.maximum_loss)}</dd>"
        f"<dt>Potential target gain</dt><dd>{_money(potential_gain)}</dd>"
        f"<dt>Reward / risk</dt><dd>{reward_risk_text}</dd>"
        f"<dt>Mandatory exit</dt><dd>{_when(opportunity.mandatory_liquidation_at)}</dd>"
        f"<dt>Current bid / ask</dt><dd>{opportunity.bid} / {opportunity.ask}</dd>"
        "</dl>"
    )
    return (
        '<section class="card">'
        f'<h2>{_e(opportunity.symbol)} <span class="quality {quality_class}">'
        f"{_e(quality_label)}{_e(score_text)}</span></h2>"
        f'<p class="muted">BUY (research plan only — not yet approved or sent). '
        f"Evidence as of {_when(opportunity.evidence_as_of)}.</p>"
        f"{terms}"
        f'<p class="muted"><strong>Why this trade:</strong></p><ul class="evidence">{evidence}</ul>'
        f'<p class="note note-info"><strong>Invalid if:</strong> {_e(invalid_if)}</p>'
        f'<form method="get" action="/opportunity/review">{_csrf(csrf)}'
        f'<input type="hidden" name="id" value="{_e(opportunity.opportunity_id)}">'
        '<button class="btn btn-primary" type="submit">REVIEW</button></form>'
        "</section>"
    )


def today_page(
    *,
    actionable: tuple[TradingOpportunity, ...],
    candidates: tuple[TradingOpportunity, ...],
    rejected: tuple[TradingOpportunity, ...],
    other: tuple[TradingOpportunity, ...] = (),
    csrf: str,
    generated_at: datetime | None,
) -> str:
    """Phase 15's Today page. `actionable` is already the ranked, capped top-N (Phase 14) --
    this function does not rank or cap; it only renders."""
    header = (
        "<h1>Today — Opportunities</h1>"
        f'<p class="muted">Generated {_when(generated_at)}. Research plans only: nothing here '
        "has been sent to any broker. Every plan requires your explicit REVIEW and APPROVE "
        "before anything downstream can act on it — and this milestone's engineering stops "
        "at APPROVE; no automatic entry or exit exists yet.</p>"
    )
    if actionable:
        cards = "".join(_opportunity_card(o, csrf) for o in actionable)
    else:
        cards = (
            '<section class="card"><p class="muted">'
            "No actionable opportunities right now.</p></section>"
        )

    candidate_html = ""
    if candidates:
        rows = "".join(
            f"<tr><td>{_e(c.symbol)}</td><td>{c.session.value}</td>"
            f"<td>{_money(c.entry_price)}</td><td>{_when(c.evidence_as_of)}</td></tr>"
            for c in candidates
        )
        candidate_html = (
            '<section class="card"><h2>Research candidates (not actionable yet)</h2>'
            '<table class="reject"><tr><th>Symbol</th><th>Session</th><th>Planned entry</th>'
            f"<th>Evidence as of</th></tr>{rows}</table></section>"
        )

    rejected_html = ""
    if rejected:
        rows = "".join(
            f"<tr><td>{_e(r.symbol)}</td><td>{_e(_rejection_summary(r))}</td>"
            f"<td>{_when(r.evidence_as_of)}</td></tr>"
            for r in rejected
        )
        rejected_html = (
            '<section class="card rejected"><h2>Rejected candidates</h2>'
            '<table class="reject"><tr><th>Symbol</th><th>Reason</th><th>Evidence as of</th></tr>'
            f"{rows}</table></section>"
        )

    other_html = ""
    if other:
        rows = "".join(
            f"<tr><td>{_e(o.symbol)}</td><td>{_e(o.status.value)}</td>"
            f"<td>{_when(o.evidence_as_of)}</td>"
            f'<td><a class="muted" href="/opportunity/review?id={_e(o.opportunity_id)}">view</a>'
            "</td></tr>"
            for o in other
        )
        other_html = (
            '<section class="card rejected"><h2>No longer actionable (history)</h2>'
            '<table class="reject"><tr><th>Symbol</th><th>Status</th><th>Evidence as of</th>'
            f"<th></th></tr>{rows}</table></section>"
        )

    return _layout(title="Today", body=header + cards + candidate_html + rejected_html + other_html)


def review_page(opportunity: TradingOpportunity, csrf: str, *, error: str | None = None) -> str:
    """Phase 16: immutable exact terms. This page is ALSO the final confirmation -- one
    ticket-less form (M090 has no dispatch to authorize, so there is no signed ticket to
    carry; APPROVE only ever records a durable Owner decision, never a broker send)."""
    warning = f'<p class="note note-danger">{_e(error)}</p>' if error else ""
    body = (
        f'<a class="muted" href="/today">← Today</a>'
        f"<h1>Review opportunity — {_e(opportunity.symbol)}</h1>"
        f'<p class="muted">Status: {_e(opportunity.status.value)}. Every gate below was '
        "re-verified against fresh evidence the instant this page was generated; approving "
        "commits to EXACTLY these terms, never a repriced plan.</p>"
        f"{warning}"
        f"{_opportunity_card(opportunity, csrf)}"
    )
    if opportunity.status is OpportunityStatus.ACTIONABLE:
        body += (
            f'<p class="note note-warn"><strong>Final confirmation.</strong> Pressing APPROVE '
            f"will record that you approved a BUY research plan for {_e(opportunity.symbol)} "
            f"({opportunity.quantity} shares, entry {_money(opportunity.entry_price)}, stop "
            f"{_money(opportunity.stop_price)}, target {_money(opportunity.target_price)}). "
            "THIS DOES NOT SEND ANYTHING TO ANY BROKER — this milestone's engineering ends at "
            "recording your decision; a later, separately built and separately approved "
            "milestone would be required before any order could ever be submitted.</p>"
            f'<form method="post" action="/opportunity/approve" style="display:inline">'
            f"{_csrf(csrf)}"
            f'<input type="hidden" name="id" value="{_e(opportunity.opportunity_id)}">'
            '<button class="btn btn-primary" type="submit">APPROVE</button></form> '
            f'<form method="post" action="/opportunity/ignore" style="display:inline">'
            f"{_csrf(csrf)}"
            f'<input type="hidden" name="id" value="{_e(opportunity.opportunity_id)}">'
            '<button class="btn btn-danger" type="submit">IGNORE</button></form>'
        )
    else:
        body += (
            f'<p class="note note-info">This opportunity is no longer actionable (status: '
            f"{_e(opportunity.status.value)}) — no APPROVE or IGNORE action is available.</p>"
        )
    return _layout(title="Review opportunity", body=body)


def approve_confirmation_page(opportunity: TradingOpportunity) -> str:
    body = (
        f"<h1>Approved — {_e(opportunity.symbol)}</h1>"
        f'<p class="note note-info">Recorded: {_e(opportunity.status.value)}. Nothing was sent '
        "to any broker. This plan now waits for a future, separately approved milestone that "
        "would bind it to real execution.</p>"
        f'<a class="btn btn-secondary" href="/today">← Today</a>'
    )
    return _layout(title="Approved", body=body)


def ignore_confirmation_page(opportunity: TradingOpportunity) -> str:
    body = (
        f"<h1>Ignored — {_e(opportunity.symbol)}</h1>"
        f'<p class="note note-info">Recorded: {_e(opportunity.status.value)}. Nothing was sent '
        "to any broker.</p>"
        f'<a class="btn btn-secondary" href="/today">← Today</a>'
    )
    return _layout(title="Ignored", body=body)
