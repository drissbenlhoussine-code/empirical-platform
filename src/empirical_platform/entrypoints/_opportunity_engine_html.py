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

MOBILE-FIRST OWNER UI (post-acceptance redesign). This file renders presentation only -- every
number shown here is read verbatim off `TradingOpportunity`, never recomputed, rounded
differently, or re-derived. Engine logic, scoring, gates, ranking, and the database schema are
untouched by this pass; only markup/CSS and how existing fields are laid out changed.

BASE-PATH AWARE, FOR REVERSE-PROXY SUBPATH DEPLOYMENT. A Tailscale (or any) reverse proxy that
serves this console under a path prefix (e.g. `/m090-review`) strips that prefix before the
request reaches this process -- routing itself needs no change. But every URL THIS MODULE
GENERATES (the stylesheet link, form actions, internal hrefs, redirects) is an ABSOLUTE path
the browser resolves against the proxy's own origin, so it must carry the same prefix back, or
the next click escapes it. `url_for(base_path, path)` is the one place that prefix is applied;
every function below threads a `base_path` parameter through to it rather than hand-building a
URL. `path` given to `url_for` is always one of this module's own hardcoded route literals
(`"/today"`, `"/opportunity/review"`, ...) -- never anything read from a request -- so this
can never become an open redirect or point at a different origin. `validate_base_path` fails
closed on anything that is not empty or a bare absolute-path prefix (no scheme, no host, no
`..`, no trailing slash, no empty segment).
"""

from __future__ import annotations

import re
from datetime import datetime
from decimal import Decimal
from html import escape as _e
from urllib.parse import quote as _urlquote

from empirical_platform.usecases.opportunity_engine import OpportunityStatus, TradingOpportunity

__all__ = [
    "STYLESHEET",
    "approve_confirmation_page",
    "ignore_confirmation_page",
    "message_page",
    "review_page",
    "today_page",
    "url_for",
    "validate_base_path",
]

_MAXIMUM_BASE_PATH_LENGTH = 128
_BASE_PATH_PATTERN = re.compile(r"(?:/[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?)+")


def validate_base_path(base_path: str) -> str:
    """ "" (root behaviour, unchanged) or a bare absolute-path prefix -- no scheme, no host,
    no trailing slash, no empty segment (`//`), no `..`, ASCII only, and bounded in length.
    Raises `ValueError` (fail closed) on anything else; never silently normalizes."""
    if base_path == "":
        return base_path
    if len(base_path) > _MAXIMUM_BASE_PATH_LENGTH or not _BASE_PATH_PATTERN.fullmatch(base_path):
        raise ValueError(
            f"invalid base_path {base_path!r}: must be empty or an absolute path prefix such "
            "as '/m090-review' (no scheme/host, no trailing slash, no '//', no '..')"
        )
    return base_path


def url_for(base_path: str, path: str) -> str:
    """Prefix one of this module's own literal route paths with the configured base path.
    `path` must already start with '/' and never itself carry `base_path` -- every call site
    passes a hardcoded route literal, so this can never double-prefix or accept external
    input. `base_path` is assumed already validated by `validate_base_path` at startup."""
    assert path.startswith("/"), f"url_for path must be absolute, got {path!r}"
    return base_path + path


def _review_link(base_path: str, opportunity_id: str) -> str:
    return url_for(base_path, "/opportunity/review") + "?id=" + _urlquote(opportunity_id, safe="")


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
header {
  padding: 14px 16px;
  border-bottom: 1px solid #232735;
}
.brand { font-weight: 700; font-size: 17px; margin-bottom: 8px; }
.badge-row { display: flex; flex-wrap: wrap; gap: 6px; }
.badge {
  background: #1c2333;
  border: 1px solid #313a52;
  border-radius: 6px;
  padding: 4px 10px;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: .03em;
}
.badge-research { background: #123a2a; color: #5fe3a5; border-color: #1e5c42; }
.badge-approval { background: #12203a; color: #8fb4e3; border-color: #1e3a5c; }
main { padding: 16px; max-width: 640px; margin: 0 auto; }
h1 { font-size: 21px; margin: 4px 0 6px; }
.muted { color: #93a0b8; font-size: 13.5px; }
.card {
  background: #141826;
  border: 1px solid #232735;
  border-radius: 14px;
  padding: 18px;
  margin-bottom: 18px;
}

/* -- Trade card top row: symbol + quality -- */
.trade-top { display: flex; align-items: center; flex-wrap: wrap; gap: 10px; margin-bottom: 2px; }
.symbol { font-size: 26px; font-weight: 800; letter-spacing: .01em; }
.quality-pill {
  display: inline-block;
  padding: 4px 12px;
  border-radius: 20px;
  font-size: 12px;
  font-weight: 800;
  letter-spacing: .04em;
}
.quality-strong { background: #123a2a; color: #5fe3a5; }
.quality-moderate { background: #3a3312; color: #e3c95f; }
.quality-weak { background: #3a1616; color: #e35f5f; }
.quality-score { color: #93a0b8; font-size: 13px; margin: 2px 0 14px; }
.trade-intent { color: #93a0b8; font-size: 13px; margin: 0 0 14px; }

/* -- Trade plan grid: two large touch-friendly tiles per row -- */
.plan-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
  margin: 4px 0 16px;
}
.plan-tile {
  background: #0f1420;
  border: 1px solid #202536;
  border-radius: 10px;
  padding: 10px 12px;
}
.plan-tile.wide { grid-column: 1 / -1; }
.plan-label {
  color: #7c8aa3;
  font-size: 11px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: .05em;
  margin-bottom: 3px;
}
.plan-value {
  font-size: 19px;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
}
.plan-value.loss { color: #e79a9a; }
.plan-value.gain { color: #7fd9a8; }

/* -- Why this trade / Invalid if -- */
.section-label {
  font-size: 12px;
  font-weight: 800;
  letter-spacing: .05em;
  text-transform: uppercase;
  color: #93a0b8;
  margin: 16px 0 8px;
}
ul.plain-list { list-style: none; margin: 0; padding: 0; }
ul.plain-list li {
  padding: 7px 0;
  border-bottom: 1px solid #1c2333;
  font-size: 14.5px;
  display: flex;
  gap: 8px;
}
ul.plain-list li:last-child { border-bottom: none; }
.mark-good { color: #5fe3a5; font-weight: 800; flex: 0 0 auto; }
.mark-bad { color: #93a0b8; flex: 0 0 auto; }

.note { border-radius: 10px; padding: 12px 14px; margin: 12px 0; font-size: 14px; }
.note-warn { background: #3a3312; color: #e3c95f; }
.note-danger { background: #3a1616; color: #e79a9a; }
.note-info { background: #12203a; color: #8fb4e3; }

/* -- Buttons: large touch targets, full width on mobile -- */
.btn {
  display: inline-block;
  min-height: 48px;
  padding: 13px 18px;
  border-radius: 12px;
  border: 1px solid transparent;
  font-size: 16px;
  font-weight: 700;
  text-decoration: none;
  text-align: center;
  cursor: pointer;
}
.btn-primary { background: #2a63e0; color: #fff; }
.btn-danger { background: #7a2323; color: #fff; }
.btn-secondary { background: #1c2333; color: #e7ebf3; border-color: #313a52; }
.btn-block { display: block; width: 100%; margin-top: 6px; }
form.block { display: block; margin-top: 10px; }
form.block + form.block { margin-top: 10px; }

/* -- Compact cards for rejected / terminal opportunities (no tables on mobile) -- */
.compact-list { display: flex; flex-direction: column; gap: 8px; }
.compact-item {
  background: #0f1420;
  border: 1px solid #202536;
  border-radius: 10px;
  padding: 12px 14px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  flex-wrap: wrap;
}
.compact-main { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.compact-symbol { font-weight: 800; font-size: 15px; }
.status-pill {
  display: inline-block;
  padding: 3px 9px;
  border-radius: 20px;
  font-size: 10.5px;
  font-weight: 800;
  letter-spacing: .04em;
  text-transform: uppercase;
  background: #2a1c1c;
  color: #e79a9a;
}
.status-pill.candidate { background: #1c2333; color: #93a0b8; }
.status-pill.terminal { background: #1c2333; color: #7c8aa3; }
.compact-reason { color: #93a0b8; font-size: 13px; }
.compact-link { color: #8fb4e3; font-size: 13px; text-decoration: none; }
.section-divider { margin: 28px 0 12px; border-top: 1px solid #232735; padding-top: 18px; }
.section-title { font-size: 15px; font-weight: 700; margin: 0 0 10px; }
.terminal-block { opacity: .82; }

/* -- Review page: quick-scan summary card -- */
.summary-card { padding: 6px 18px 4px; }
.summary-row { padding: 11px 0; border-bottom: 1px solid #1c2333; }
.summary-row:last-child { border-bottom: none; }
.summary-q {
  font-size: 11.5px;
  font-weight: 800;
  letter-spacing: .04em;
  text-transform: uppercase;
  color: #7c8aa3;
  margin-bottom: 3px;
}
.summary-a { font-size: 16px; font-weight: 600; }
.summary-a.loss { color: #e79a9a; }
.summary-a.gain { color: #7fd9a8; }
"""


def _quality_label(score: Decimal | None) -> tuple[str, str]:
    """(css class, label). Never "chance of profit"/"win probability" -- a research quality
    label over measurable, already-gated evidence, per Phase 14."""
    if score is None:
        return "quality-weak", "NOT SCORED"
    if score >= Decimal("70"):
        return "quality-strong", "STRONG"
    if score >= Decimal("40"):
        return "quality-moderate", "MODERATE"
    return "quality-weak", "WEAK"


def _when(value: datetime | None) -> str:
    """Full date + time, for less prominent contexts (page-level timestamps)."""
    if value is None:
        return "Not available"
    return value.astimezone(value.tzinfo).strftime("%b %d, %H:%M %Z")


def _time_only(value: datetime | None) -> str:
    """Just the clock time, for a trade-plan tile a mobile Owner glances at."""
    if value is None:
        return "Not available"
    return value.astimezone(value.tzinfo).strftime("%H:%M %Z")


def _money(value: Decimal | None) -> str:
    return "Not available" if value is None else f"${value:,.2f}"


def _ratio(value: Decimal | None) -> str:
    return "Not available" if value is None else f"{value:.2f} : 1"


def _layout(*, title: str, body: str, base_path: str = "") -> str:
    stylesheet_href = _e(url_for(base_path, "/static/opportunity-engine.css"))
    return (
        "<!DOCTYPE html>"
        '<html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1, '
        'viewport-fit=cover">'
        f"<title>{_e(title)} — Opportunity Engine</title>"
        f'<link rel="stylesheet" href="{stylesheet_href}"></head>'
        '<body><header><div class="brand">Opportunity Engine</div>'
        '<div class="badge-row">'
        '<span class="badge badge-research">RESEARCH — NOT AUTOMATIC TRADING</span>'
        '<span class="badge badge-approval">OWNER APPROVAL REQUIRED</span>'
        "</div></header>"
        f"<main>{body}</main></body></html>"
    )


def _csrf(csrf: str) -> str:
    return f'<input type="hidden" name="csrf_token" value="{_e(csrf)}">'


def message_page(*, title: str, message: str, back: str = "/today", base_path: str = "") -> str:
    back_href = _e(url_for(base_path, back))
    body = (
        f"<h1>{_e(title)}</h1>"
        f'<p class="note note-warn">{_e(message)}</p>'
        f'<a class="btn btn-secondary" href="{back_href}">← Back</a>'
    )
    return _layout(title=title, body=body, base_path=base_path)


def _rejection_summary(opportunity: TradingOpportunity) -> str:
    reasons = ", ".join(r.value.replace("_", " ").title() for r in opportunity.rejection_reasons)
    return reasons or "Not available"


def _plan_tile(label: str, value: str, *, wide: bool = False, tone: str = "") -> str:
    classes = "plan-tile" + (" wide" if wide else "")
    value_classes = "plan-value" + (f" {tone}" if tone else "")
    return (
        f'<div class="{classes}"><div class="plan-label">{_e(label)}</div>'
        f'<div class="{value_classes}">{_e(value)}</div></div>'
    )


def _invalid_if_items(opportunity: TradingOpportunity) -> tuple[str, ...]:
    """The same invalidation conditions the Review page's own re-verification enforces
    (Phase 16), split into short, scannable bullets instead of one dense paragraph."""
    if opportunity.stop_price is None:
        return ("Any hard gate (session, data quality, liquidity, structure, risk) fails.",)
    return (
        f"Price reaches the stop ({_money(opportunity.stop_price)})",
        "The quote becomes stale",
        "The spread exceeds policy",
        "The entry moves outside tolerance",
        "The mandatory exit time passes",
    )


def _opportunity_card(opportunity: TradingOpportunity, csrf: str, *, base_path: str = "") -> str:
    quality_class, quality_label = _quality_label(opportunity.quality_score)
    score_text = (
        "Not scored"
        if opportunity.quality_score is None
        else f"Opportunity Quality {opportunity.quality_score:.1f}"
    )
    evidence_items = "".join(
        f'<li><span class="mark-good">✓</span><span>{_e(item)}</span></li>'
        for item in opportunity.evidence
    )
    invalid_items = "".join(
        f'<li><span class="mark-bad">–</span><span>{_e(item)}</span></li>'
        for item in _invalid_if_items(opportunity)
    )
    potential_gain = (
        None
        if opportunity.reward_per_share is None or opportunity.quantity is None
        else opportunity.reward_per_share * Decimal(opportunity.quantity)
    )
    quantity_text = "Not available" if opportunity.quantity is None else str(opportunity.quantity)

    plan = (
        '<div class="plan-grid">'
        + _plan_tile("Entry", _money(opportunity.entry_price))
        + _plan_tile("Stop", _money(opportunity.stop_price), tone="loss")
        + _plan_tile("Target", _money(opportunity.target_price), tone="gain")
        + _plan_tile("Quantity", quantity_text)
        + _plan_tile("Max loss", _money(opportunity.maximum_loss), tone="loss")
        + _plan_tile("Target gain", _money(potential_gain), tone="gain")
        + _plan_tile("Risk / reward", _ratio(opportunity.reward_risk_ratio))
        + _plan_tile("Mandatory exit", _time_only(opportunity.mandatory_liquidation_at))
        + "</div>"
    )

    return (
        '<section class="card">'
        '<div class="trade-top">'
        f'<span class="symbol">{_e(opportunity.symbol)}</span>'
        f'<span class="quality-pill {quality_class}">{_e(quality_label)}</span>'
        "</div>"
        f'<div class="quality-score">{_e(score_text)}</div>'
        f'<p class="trade-intent">BUY — research plan only, not yet approved or sent. '
        f"Evidence as of {_when(opportunity.evidence_as_of)}.</p>"
        f"{plan}"
        f'<div class="section-label">Why this trade</div>'
        f'<ul class="plain-list">{evidence_items}</ul>'
        f'<div class="section-label">Invalid if</div>'
        f'<ul class="plain-list">{invalid_items}</ul>'
        f'<form class="block" method="get" '
        f'action="{_e(url_for(base_path, "/opportunity/review"))}">{_csrf(csrf)}'
        f'<input type="hidden" name="id" value="{_e(opportunity.opportunity_id)}">'
        '<button class="btn btn-primary btn-block" type="submit">REVIEW TRADE</button></form>'
        "</section>"
    )


def _compact_item(
    *, symbol: str, status_label: str, status_class: str, detail: str, link: str | None = None
) -> str:
    link_html = f'<a class="compact-link" href="{_e(link)}">view →</a>' if link else ""
    return (
        '<div class="compact-item">'
        '<div class="compact-main">'
        f'<span class="compact-symbol">{_e(symbol)}</span>'
        f'<span class="status-pill {status_class}">{_e(status_label)}</span>'
        f'<span class="compact-reason">{_e(detail)}</span>'
        "</div>"
        f"{link_html}"
        "</div>"
    )


def today_page(
    *,
    actionable: tuple[TradingOpportunity, ...],
    candidates: tuple[TradingOpportunity, ...],
    rejected: tuple[TradingOpportunity, ...],
    other: tuple[TradingOpportunity, ...] = (),
    csrf: str,
    generated_at: datetime | None,
    base_path: str = "",
) -> str:
    """Phase 15's Today page. `actionable` is already the ranked, capped top-N (Phase 14) --
    this function does not rank or cap; it only renders."""
    header = (
        "<h1>Today</h1>"
        f'<p class="muted">Generated {_when(generated_at)}. Research plans only: nothing here '
        "has been sent to any broker. Every plan requires your explicit REVIEW and APPROVE "
        "before anything downstream can act on it.</p>"
    )
    if actionable:
        cards = "".join(_opportunity_card(o, csrf, base_path=base_path) for o in actionable)
    else:
        cards = (
            '<section class="card"><p class="muted">'
            "No actionable opportunities right now.</p></section>"
        )

    candidate_html = ""
    if candidates:
        items = "".join(
            _compact_item(
                symbol=c.symbol,
                status_label="Watching",
                status_class="candidate",
                detail=f"Planned entry {_money(c.entry_price)} · {_when(c.evidence_as_of)}",
            )
            for c in candidates
        )
        candidate_html = (
            '<div class="section-divider"><h2 class="section-title">'
            f'Research candidates (not actionable yet)</h2><div class="compact-list">{items}'
            "</div></div>"
        )

    rejected_html = ""
    if rejected:
        items = "".join(
            _compact_item(
                symbol=r.symbol,
                status_label="Rejected",
                status_class="rejected",
                detail=_rejection_summary(r),
            )
            for r in rejected
        )
        rejected_html = (
            '<div class="section-divider"><h2 class="section-title">Rejected candidates</h2>'
            f'<div class="compact-list">{items}</div></div>'
        )

    other_html = ""
    if other:
        items = "".join(
            _compact_item(
                symbol=o.symbol,
                status_label=o.status.value.replace("_", " ").title(),
                status_class="terminal",
                detail=f"Evidence as of {_when(o.evidence_as_of)}",
                link=_review_link(base_path, o.opportunity_id),
            )
            for o in other
        )
        other_html = (
            '<div class="section-divider terminal-block"><h2 class="section-title">'
            f'No longer actionable (history)</h2><div class="compact-list">{items}</div></div>'
        )

    return _layout(
        title="Today",
        body=header + cards + candidate_html + rejected_html + other_html,
        base_path=base_path,
    )


def _summary_row(question: str, answer: str, *, tone: str = "") -> str:
    classes = "summary-a" + (f" {tone}" if tone else "")
    return (
        f'<div class="summary-row"><div class="summary-q">{_e(question)}</div>'
        f'<div class="{classes}">{_e(answer)}</div></div>'
    )


def _review_summary_card(opportunity: TradingOpportunity) -> str:
    o = opportunity
    quantity_text = "Not available" if o.quantity is None else str(o.quantity)
    what = (
        f"{quantity_text} shares of {o.symbol} at {_money(o.entry_price)}"
        if o.quantity is not None
        else f"{o.symbol} at {_money(o.entry_price)}"
    )
    potential_gain = (
        None
        if o.reward_per_share is None or o.quantity is None
        else o.reward_per_share * Decimal(o.quantity)
    )
    target_answer = f"{_money(o.target_price)} (+{_money(potential_gain)} potential)"
    why = "; ".join(o.evidence) if o.evidence else "Not available"
    invalid_answer = "; ".join(_invalid_if_items(o))
    rows = (
        _summary_row("What am I buying?", what)
        + _summary_row("How much can I lose?", f"{_money(o.maximum_loss)} max", tone="loss")
        + _summary_row("What is the target?", target_answer, tone="gain")
        + _summary_row("When does the plan expire?", _when(o.expires_at))
        + _summary_row("Why did the engine pick this?", why)
        + _summary_row("What invalidates it?", invalid_answer)
    )
    return f'<section class="card summary-card">{rows}</section>'


def review_page(
    opportunity: TradingOpportunity, csrf: str, *, error: str | None = None, base_path: str = ""
) -> str:
    """Phase 16: immutable exact terms. This page is ALSO the final confirmation -- one
    ticket-less form (M090 has no dispatch to authorize, so there is no signed ticket to
    carry; APPROVE only ever records a durable Owner decision, never a broker send).

    Leads with a quick-scan summary card answering the Owner's six questions before any
    prose, per the mobile-first redesign -- the full trade-plan card (identical terms, more
    detail) follows immediately after.
    """
    warning = f'<p class="note note-danger">{_e(error)}</p>' if error else ""
    today_href = _e(url_for(base_path, "/today"))
    body = (
        f'<a class="muted" href="{today_href}">← Today</a>'
        f"<h1>{_e(opportunity.symbol)}</h1>{warning}"
    )
    if opportunity.status is OpportunityStatus.ACTIONABLE:
        body += _review_summary_card(opportunity)
    body += f"{_opportunity_card(opportunity, csrf, base_path=base_path)}"
    if opportunity.status is OpportunityStatus.ACTIONABLE:
        approve_action = _e(url_for(base_path, "/opportunity/approve"))
        ignore_action = _e(url_for(base_path, "/opportunity/ignore"))
        body += (
            f'<p class="note note-warn"><strong>Final confirmation.</strong> Pressing APPROVE '
            f"will record that you approved a BUY research plan for {_e(opportunity.symbol)} "
            f"({opportunity.quantity} shares, entry {_money(opportunity.entry_price)}, stop "
            f"{_money(opportunity.stop_price)}, target {_money(opportunity.target_price)}). "
            "THIS DOES NOT SEND ANYTHING TO ANY BROKER — this milestone's engineering ends at "
            "recording your decision; a later, separately built and separately approved "
            "milestone would be required before any order could ever be submitted.</p>"
            f'<form class="block" method="post" action="{approve_action}">'
            f"{_csrf(csrf)}"
            f'<input type="hidden" name="id" value="{_e(opportunity.opportunity_id)}">'
            '<button class="btn btn-primary btn-block" type="submit">APPROVE</button></form>'
            f'<form class="block" method="post" action="{ignore_action}">'
            f"{_csrf(csrf)}"
            f'<input type="hidden" name="id" value="{_e(opportunity.opportunity_id)}">'
            '<button class="btn btn-danger btn-block" type="submit">IGNORE</button></form>'
        )
    else:
        body += (
            f'<p class="note note-info">This opportunity is no longer actionable (status: '
            f"{_e(opportunity.status.value)}) — no APPROVE or IGNORE action is available.</p>"
        )
    return _layout(title="Review opportunity", body=body, base_path=base_path)


def approve_confirmation_page(opportunity: TradingOpportunity, *, base_path: str = "") -> str:
    today_href = _e(url_for(base_path, "/today"))
    body = (
        f"<h1>Approved — {_e(opportunity.symbol)}</h1>"
        f'<p class="note note-info">Recorded: {_e(opportunity.status.value)}. Nothing was sent '
        "to any broker. This plan now waits for a future, separately approved milestone that "
        "would bind it to real execution.</p>"
        f'<a class="btn btn-secondary" href="{today_href}">← Today</a>'
    )
    return _layout(title="Approved", body=body, base_path=base_path)


def ignore_confirmation_page(opportunity: TradingOpportunity, *, base_path: str = "") -> str:
    today_href = _e(url_for(base_path, "/today"))
    body = (
        f"<h1>Ignored — {_e(opportunity.symbol)}</h1>"
        f'<p class="note note-info">Recorded: {_e(opportunity.status.value)}. Nothing was sent '
        "to any broker.</p>"
        f'<a class="btn btn-secondary" href="{today_href}">← Today</a>'
    )
    return _layout(title="Ignored", body=body, base_path=base_path)
