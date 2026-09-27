"""MILESTONE-086 -- the Operator Console pages, rendered as plain HTML.

No template engine, no script, no inline style: every page is a function of a read model
from `usecases.operator_console`, every dynamic value passes through `html.escape`, and the
only stylesheet is served from this process. The design is deliberately calm: a light
neutral surface, one strong typeface stack, cards with room, status chips, and red kept
for genuine danger. A large SIMULATION badge is in the header of every page.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime
from html import escape

from empirical_platform.usecases.operator_console import (
    ActionOutcome,
    ConfirmationView,
    ExecutionSummary,
    HistoryEntry,
    HumanState,
    OpportunityCard,
    SafetyView,
    TodayView,
)
from empirical_platform.usecases.operator_console_fixtures import SimulationDayReport

__all__ = [
    "STYLESHEET",
    "active_page",
    "confirmation_page",
    "execution_page",
    "history_page",
    "kill_switch_confirmation_page",
    "loaded_day_page",
    "message_page",
    "opportunity_page",
    "safety_page",
    "today_page",
]

_NAV = (
    ("/today", "Today"),
    ("/active", "Active trades"),
    ("/history", "History"),
    ("/safety", "Safety"),
)

_CHIP_CLASS = {
    HumanState.NEEDS_DECISION: "chip chip-action",
    HumanState.APPROVED: "chip chip-info",
    HumanState.REJECTED: "chip chip-muted",
    HumanState.EXPIRED: "chip chip-muted",
    HumanState.BLOCKED: "chip chip-danger",
    HumanState.SUBMITTED: "chip chip-info",
    HumanState.ACCEPTED: "chip chip-info",
    HumanState.PARTIALLY_FILLED: "chip chip-progress",
    HumanState.FILLED: "chip chip-good",
    HumanState.CANCEL_REQUESTED: "chip chip-progress",
    HumanState.CANCELLED: "chip chip-muted",
    HumanState.NEEDS_ATTENTION: "chip chip-danger",
}


def _e(value: object) -> str:
    return escape(str(value), quote=True)


def _when(value: datetime | None) -> str:
    if value is None:
        return "Not available"
    return value.astimezone(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")


def _chip(state: HumanState) -> str:
    return f'<span class="{_CHIP_CLASS[state]}">{_e(state.value)}</span>'


def _layout(
    *,
    title: str,
    active: str,
    body: str,
    capability_label: str,
    kill_switch_engaged: bool,
    flash: ActionOutcome | None = None,
) -> str:
    nav = "".join(
        f'<a class="nav-link{" nav-active" if href == active else ""}" href="{href}">{_e(label)}</a>'
        for href, label in _NAV
    )
    stop = (
        '<div class="banner banner-danger" role="alert">Kill switch engaged — no new execution can '
        'start. Existing orders stay visible. <a href="/safety">Safety</a></div>'
        if kill_switch_engaged
        else ""
    )
    flash_html = ""
    if flash is not None:
        tone = "good" if flash.ok else ("danger" if flash.sent == "unknown" else "warn")
        fact = {
            "nothing_sent": "Nothing was sent.",
            "sent": "An order was sent to the simulated broker.",
            "unknown": "Outcome unknown — do not retry.",
            "none": "",
        }.get(flash.sent, "")
        flash_html = (
            f'<div class="banner banner-{tone}" role="status"><strong>{_e(flash.title)}.</strong> '
            f"{_e(flash.message)} <em>{_e(fact)}</em></div>"
        )
    return (
        "<!DOCTYPE html>"
        '<html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>{_e(title)} — Operator Console</title>"
        '<link rel="stylesheet" href="/static/console.css"></head>'
        '<body><header class="top"><div class="brand"><span class="brand-name">Operator Console</span>'
        f'<span class="env-badge">{_e(capability_label.upper())}</span></div>'
        f'<nav class="nav" aria-label="Primary">{nav}</nav></header>'
        f'<main class="page">{stop}{flash_html}{body}</main>'
        '<footer class="foot">Simulation only. No order can reach any venue from this console. '
        "Paper execution locked — acceptance pending. Live — not authorized.</footer>"
        "</body></html>"
    )


def _details(summary: str, inner: str) -> str:
    return f'<details class="details"><summary>{_e(summary)}</summary>{inner}</details>'


def _kv(rows: Iterable[tuple[str, str]]) -> str:
    return (
        '<dl class="kv">' + "".join(f"<dt>{_e(k)}</dt><dd>{_e(v)}</dd>" for k, v in rows) + "</dl>"
    )


def _csrf(csrf: str) -> str:
    return f'<input type="hidden" name="csrf_token" value="{_e(csrf)}">'


# ---------------------------------------------------------------------------
# Today
# ---------------------------------------------------------------------------


def today_page(view: TodayView, csrf: str, flash: ActionOutcome | None = None) -> str:
    stats = (
        '<section class="stats">'
        f'<div class="stat"><span class="stat-label">Session</span><span class="stat-value">{_e(view.session_date)}</span></div>'
        f'<div class="stat"><span class="stat-label">System</span><span class="stat-value small">{_e(view.system_status)}</span></div>'
        f'<div class="stat"><span class="stat-label">Market</span><span class="stat-value small">{_e(view.market_status)}</span></div>'
        f'<div class="stat"><span class="stat-label">Kill switch</span><span class="stat-value small">'
        f"{'Engaged' if view.kill_switch_engaged else 'Released'}</span></div>"
        f'<div class="stat"><span class="stat-label">Opportunities</span><span class="stat-value">{len(view.opportunities)}</span></div>'
        f'<div class="stat stat-accent"><span class="stat-label">Need your decision</span><span class="stat-value">{view.needs_action_count}</span></div>'
        f'<div class="stat"><span class="stat-label">Active executions</span><span class="stat-value">{view.active_executions_count}</span></div>'
        f'<div class="stat"><span class="stat-label">Positions</span><span class="stat-value">{view.active_positions_count}</span></div>'
        "</section>"
    )
    if view.opportunities:
        cards = (
            '<section class="cards">'
            + "".join(_card(c, csrf) for c in view.opportunities)
            + "</section>"
        )
    else:
        cards = (
            '<section class="empty"><h2>No opportunities today</h2>'
            "<p>The engine has proposed nothing for this session. In simulation you can stage a "
            "deterministic day: twelve staged symbols, each exercising one broker behaviour.</p>"
            f'<form method="post" action="/simulation/load-day">{_csrf(csrf)}'
            '<button class="btn btn-primary" type="submit">Load simulation day</button></form></section>'
        )
    body = f"<h1>Today</h1>{stats}{cards}"
    return _layout(
        title="Today",
        active="/today",
        body=body,
        capability_label=view.capability.label,
        kill_switch_engaged=view.kill_switch_engaged,
        flash=flash,
    )


def _card(card: OpportunityCard, csrf: str) -> str:
    t = card.terms
    numbers = (
        '<div class="numbers">'
        f'<div><span class="num-label">Entry (limit)</span><span class="num">{_e(t.limit_price)}</span></div>'
        f'<div><span class="num-label">Quantity</span><span class="num">{t.quantity}</span></div>'
        f'<div><span class="num-label">Notional</span><span class="num">{_e(t.notional)} {_e(t.currency)}</span></div>'
        f'<div><span class="num-label">Max capital</span><span class="num">{_e(card.maximum_capital)}</span></div>'
        f'<div><span class="num-label">Stop</span><span class="num">{_e(card.stop_price)}</span></div>'
        f'<div><span class="num-label">Target</span><span class="num">{_e(card.target_price)}</span></div>'
        f'<div><span class="num-label">Risk</span><span class="num">{_e(card.risk_amount)} ({_e(card.risk_percent)})</span></div>'
        "</div>"
    )
    notes = ""
    if card.blocked_note:
        notes += f'<p class="note note-danger">{_e(card.blocked_note)}</p>'
    if card.attention_note:
        notes += f'<p class="note note-warn">{_e(card.attention_note)}</p>'
    actions = ""
    if card.decision_available and not card.blocked_note:
        actions = (
            '<div class="actions">'
            f'<a class="btn btn-primary" href="/confirm?action=APPROVE&amp;proposal={_e(card.proposal_id)}">Approve</a>'
            f'<a class="btn btn-secondary" href="/confirm?action=REJECT&amp;proposal={_e(card.proposal_id)}">Reject</a>'
            "</div>"
        )
    elif card.decision_available and card.blocked_note:
        actions = (
            '<div class="actions">'
            f'<a class="btn btn-secondary" href="/confirm?action=REJECT&amp;proposal={_e(card.proposal_id)}">Reject</a>'
            "</div>"
        )
    elif card.execution is not None:
        actions = (
            '<div class="actions">'
            f'<a class="btn btn-secondary" href="/execution?intent={_e(card.execution.intent_id)}">View execution</a>'
            "</div>"
        )
    evidence = "".join(f"<li>{_e(line)}</li>" for line in card.evidence) or "<li>Not available</li>"
    details = _details(
        "Details",
        _kv(
            [
                ("Proposal", card.proposal_id),
                ("Version", str(card.proposal_version)),
                ("Order type", t.order_type),
                ("Time in force", t.time_in_force),
                ("Extended hours", t.extended_hours),
                ("Reference", t.fingerprint_short),
                ("Created", _when(card.created_at)),
                ("Expires", _when(card.expires_at)),
                ("Staged simulation behaviour", card.scenario or "Not available"),
            ]
        )
        + f'<p class="muted">Evidence</p><ul class="evidence">{evidence}</ul>',
    )
    return (
        f'<article class="card" aria-label="{_e(card.symbol)}">'
        f'<div class="card-head"><span class="ticker">{_e(card.symbol)}</span>'
        f'<span class="side">{_e(t.side)}</span>{_chip(card.state)}</div>'
        f'<p class="reason">{_e(card.reason)}</p>{numbers}{notes}'
        f'<p class="muted">Proposed {_when(card.created_at)} · expires {_when(card.expires_at)}</p>'
        f"{actions}{details}</article>"
    )


def opportunity_page(
    card: OpportunityCard,
    csrf: str,
    capability_label: str,
    kill_switch_engaged: bool,
    flash: ActionOutcome | None,
) -> str:
    body = f'<a class="back" href="/today">← Today</a><h1>{_e(card.symbol)}</h1>{_card(card, csrf)}'
    if card.execution is not None:
        body += _execution_block(card.execution, csrf)
    return _layout(
        title=card.symbol,
        active="/today",
        body=body,
        capability_label=capability_label,
        kill_switch_engaged=kill_switch_engaged,
        flash=flash,
    )


# ---------------------------------------------------------------------------
# Confirmation
# ---------------------------------------------------------------------------


def confirmation_page(view: ConfirmationView, csrf: str, capability_label: str) -> str:
    t = view.terms
    approve = view.action == "APPROVE"
    heading = "Confirm approval" if approve else "Confirm rejection"
    verb = "CONFIRM APPROVAL" if approve else "CONFIRM REJECTION"
    action = "/confirm-approval" if approve else "/confirm-rejection"
    warning = ""
    if approve and view.kill_switch_engaged:
        warning = (
            '<div class="banner banner-danger">The kill switch is engaged. This approval will be '
            "refused until it is released. Nothing will be sent.</div>"
        )
    terms = _kv(
        [
            ("Symbol", t.symbol),
            ("Side", t.side),
            ("Quantity", str(t.quantity)),
            ("Order type", t.order_type),
            ("Limit price", t.limit_price),
            ("Time in force", t.time_in_force),
            ("Extended hours", t.extended_hours),
            ("Environment", view.environment),
            ("Account", view.account),
            ("Reference", t.fingerprint_short),
            ("Notional", f"{t.notional} {t.currency}"),
            ("Proposal expires", _when(view.proposal_expires_at)),
            ("Approval expires", _when(view.approval_expires_at)),
        ]
    )
    intro = (
        "You are about to authorize exactly these terms. The engine re-reads the proposal when you "
        "confirm and refuses if anything changed or expired."
        if approve
        else "This records your rejection. Nothing will be sent."
    )
    body = (
        f'<a class="back" href="/today">← Today</a>'
        f'<section class="confirm"><div class="env-badge env-badge-large">{_e(view.environment)}</div>'
        f'<h1>{heading}</h1><p class="lead">{_e(intro)}</p>{warning}'
        f'<div class="terms">{terms}</div>'
        f'<form method="post" action="{action}" class="confirm-form">{_csrf(csrf)}'
        f'<input type="hidden" name="proposal" value="{_e(view.proposal_id)}">'
        f'<input type="hidden" name="ticket" value="{_e(view.ticket)}">'
        f'<button class="btn {"btn-primary" if approve else "btn-danger"} btn-big" type="submit">{verb}</button>'
        '<a class="btn btn-secondary btn-big" href="/today">Cancel</a></form></section>'
    )
    return _layout(
        title=heading,
        active="/today",
        body=body,
        capability_label=capability_label,
        kill_switch_engaged=view.kill_switch_engaged,
    )


def kill_switch_confirmation_page(
    *, engage: bool, csrf: str, capability_label: str, kill_switch_engaged: bool
) -> str:
    heading = "Activate kill switch" if engage else "Deactivate kill switch"
    effect = (
        "No new execution can start. Pending decisions cannot be confirmed. Existing orders stay "
        "visible and keep being reconciled."
        if engage
        else "Execution can be confirmed again. Nothing is sent by releasing it."
    )
    body = (
        '<a class="back" href="/safety">← Safety</a>'
        f'<section class="confirm"><h1>{heading}</h1><p class="lead">{_e(effect)}</p>'
        f'<form method="post" action="/safety/kill-switch" class="confirm-form">{_csrf(csrf)}'
        f'<input type="hidden" name="action" value="{"engage" if engage else "release"}">'
        '<label class="field">Reason (optional)<input type="text" name="reason" maxlength="200"></label>'
        f'<button class="btn {"btn-danger" if engage else "btn-primary"} btn-big" type="submit">'
        f"{'ACTIVATE KILL SWITCH' if engage else 'DEACTIVATE KILL SWITCH'}</button>"
        '<a class="btn btn-secondary btn-big" href="/safety">Cancel</a></form></section>'
    )
    return _layout(
        title=heading,
        active="/safety",
        body=body,
        capability_label=capability_label,
        kill_switch_engaged=kill_switch_engaged,
    )


# ---------------------------------------------------------------------------
# Active trades and one execution
# ---------------------------------------------------------------------------


def _timeline(summary: ExecutionSummary) -> str:
    steps = "".join(
        f'<li class="{"step done" if s.reached else "step"}"><span class="step-label">{_e(s.label)}</span>'
        f'<span class="step-when">{_when(s.at) if s.at else ("" if not s.reached else "recorded")}</span>'
        f"{f'<span class="step-note">{_e(s.note)}</span>' if s.note else ''}</li>"
        for s in summary.timeline
    )
    return f'<ol class="timeline">{steps}</ol>'


def _execution_block(summary: ExecutionSummary, csrf: str, *, with_actions: bool = True) -> str:
    t = summary.terms
    warnings = "".join(f'<p class="note note-warn">{_e(w)}</p>' for w in summary.warnings)
    pending = (
        f'<p class="note note-info">{_e(summary.pending_reason)}</p>'
        if summary.pending_reason
        else ""
    )
    if not summary.outcome_known:
        pending = (
            '<p class="note note-danger"><strong>Outcome unknown — do not retry.</strong> '
            + _e(summary.pending_reason or "")
            + "</p>"
        )
    if summary.position_open:
        pending += (
            '<p class="note note-info"><strong>Open position.</strong> '
            + _e(summary.exit_status)
            + " No exit path exists in this milestone; nothing is sent.</p>"
        )
    actions = ""
    if with_actions and summary.can_cancel:
        actions = (
            '<div class="actions">'
            f'<a class="btn btn-secondary" href="/execution/cancel?intent={_e(summary.intent_id)}">Request cancel</a>'
            "</div>"
        )
    facts = _kv(
        [
            ("Decision", f"Approved by {summary.decision_by}"),
            ("Decided", _when(summary.decided_at)),
            (
                "Terms",
                f"{t.side} {t.quantity} {t.symbol} {t.order_type} @ {t.limit_price} {t.time_in_force}",
            ),
            ("Broker order", summary.broker_order_id),
            ("Claimed", _when(summary.claimed_at)),
            ("Submitted", _when(summary.submitted_at)),
            ("Acknowledged", _when(summary.acknowledged_at)),
            ("Final", _when(summary.terminal_at) if summary.terminal_at else "Not yet"),
            ("Filled quantity", summary.filled_quantity),
            ("Average fill price", summary.filled_avg_price),
            ("Reconciliation", summary.reconciliation),
            ("Execution kind", summary.execution_kind),
            ("Position", summary.exit_status),
        ]
    )
    return (
        f'<article class="card exec" aria-label="{_e(summary.symbol)} execution">'
        f'<div class="card-head"><span class="ticker">{_e(summary.symbol)}</span>'
        f'<span class="side">{_e(t.side)}</span>{_chip(summary.state)}</div>'
        f"{pending}{warnings}{_timeline(summary)}{facts}{actions}"
        + _details(
            "Details",
            _kv(
                [
                    ("Intent", summary.intent_id),
                    ("Proposal", summary.proposal_id),
                    ("Engine state", summary.raw_state),
                ]
            ),
        )
        + "</article>"
    )


def active_page(
    rows: tuple[ExecutionSummary, ...],
    csrf: str,
    capability_label: str,
    kill_switch_engaged: bool,
    flash: ActionOutcome | None,
) -> str:
    refresh = (
        f'<form method="post" action="/active/refresh" class="inline">{_csrf(csrf)}'
        '<button class="btn btn-secondary" type="submit">Check with broker now</button></form>'
    )
    if rows:
        cards = (
            '<section class="cards">'
            + "".join(_execution_block(r, csrf) for r in rows)
            + "</section>"
        )
    else:
        cards = '<section class="empty"><h2>No active trades or open positions</h2><p>Every execution has reached a final state and no filled position is held.</p></section>'
    body = f'<div class="title-row"><h1>Active trades</h1>{refresh}</div>{cards}'
    return _layout(
        title="Active trades",
        active="/active",
        body=body,
        capability_label=capability_label,
        kill_switch_engaged=kill_switch_engaged,
        flash=flash,
    )


def execution_page(
    summary: ExecutionSummary,
    csrf: str,
    capability_label: str,
    kill_switch_engaged: bool,
    flash: ActionOutcome | None,
) -> str:
    body = f'<a class="back" href="/active">← Active trades</a><h1>{_e(summary.symbol)}</h1>{_execution_block(summary, csrf)}'
    return _layout(
        title=f"{summary.symbol} execution",
        active="/active",
        body=body,
        capability_label=capability_label,
        kill_switch_engaged=kill_switch_engaged,
        flash=flash,
    )


def cancel_confirmation_page(
    summary: ExecutionSummary, csrf: str, capability_label: str, kill_switch_engaged: bool
) -> str:
    body = (
        f'<a class="back" href="/execution?intent={_e(summary.intent_id)}">← Execution</a>'
        f'<section class="confirm"><h1>Request cancellation</h1><p class="lead">A cancel request is '
        "sent to the simulated broker for this exact order. A request is not a cancellation: the "
        "order may still fill before it is cancelled.</p>"
        + _kv(
            [
                ("Symbol", summary.symbol),
                ("Broker order", summary.broker_order_id),
                ("State", summary.state.value),
            ]
        )
        + f'<form method="post" action="/execution/confirm-cancel" class="confirm-form">{_csrf(csrf)}'
        f'<input type="hidden" name="intent" value="{_e(summary.intent_id)}">'
        '<button class="btn btn-danger btn-big" type="submit">CONFIRM CANCEL REQUEST</button>'
        f'<a class="btn btn-secondary btn-big" href="/execution?intent={_e(summary.intent_id)}">Back</a></form></section>'
    )
    return _layout(
        title="Request cancellation",
        active="/active",
        body=body,
        capability_label=capability_label,
        kill_switch_engaged=kill_switch_engaged,
    )


# ---------------------------------------------------------------------------
# History
# ---------------------------------------------------------------------------


def history_page(
    rows: tuple[HistoryEntry, ...],
    *,
    filters: dict[str, str],
    capability_label: str,
    kill_switch_engaged: bool,
) -> str:
    def option(name: str, value: str, label: str) -> str:
        selected = " selected" if filters.get(name, "") == value else ""
        return f'<option value="{_e(value)}"{selected}>{_e(label)}</option>'

    form = (
        '<form method="get" action="/history" class="filters">'
        f'<label>Date<input type="date" name="date" value="{_e(filters.get("date", ""))}"></label>'
        f'<label>Symbol<input type="text" name="symbol" maxlength="12" value="{_e(filters.get("symbol", ""))}"></label>'
        '<label>Decision<select name="decision">'
        + option("decision", "", "Any")
        + option("decision", "Approved", "Approved")
        + option("decision", "Rejected", "Rejected")
        + "</select></label>"
        '<label>Outcome<select name="outcome">'
        + option("outcome", "", "Any")
        + "".join(
            option("outcome", s.value, s.value)
            for s in (
                HumanState.FILLED,
                HumanState.CANCELLED,
                HumanState.EXPIRED,
                HumanState.REJECTED,
                HumanState.BLOCKED,
                HumanState.NEEDS_ATTENTION,
            )
        )
        + "</select></label>"
        '<button class="btn btn-secondary" type="submit">Filter</button></form>'
    )
    if rows:
        table_rows = "".join(
            "<tr>"
            f"<td>{_when(r.timestamp)}</td>"
            f'<td><span class="ticker small">{_e(r.symbol)}</span></td>'
            f"<td>{_e(r.proposal_state)}</td>"
            f'<td>{_e(r.decision)}<span class="muted block">{_e(r.decided_by)}</span></td>'
            f"<td>{_e(r.execution_kind)}</td>"
            f"<td>{_chip(r.final_state)}</td>"
            f"<td>{_e(r.quantity)} @ {_e(r.price)}</td>"
            f"<td>{_e(r.result)}</td>"
            f"<td>{f'<a href="/execution?intent={_e(r.intent_id)}">View</a>' if r.intent_id else f'<a href="/opportunity?id={_e(r.proposal_id)}">View</a>'}</td>"
            "</tr>"
            for r in rows
        )
        table = (
            '<div class="table-wrap"><table class="history"><thead><tr><th>When</th><th>Symbol</th>'
            "<th>Model proposal</th><th>Owner decision</th><th>Execution</th><th>Final state</th>"
            f"<th>Qty @ price</th><th>Result</th><th></th></tr></thead><tbody>{table_rows}</tbody></table></div>"
        )
    else:
        table = '<section class="empty"><h2>Nothing matches</h2></section>'
    legend = (
        '<p class="muted">Columns distinguish the model proposal, the Owner decision and the '
        "simulation execution. Broker/Paper execution — future only. Results are shown only when "
        "the platform records one; no P&amp;L is computed from incomplete data.</p>"
    )
    body = f"<h1>History</h1>{form}{legend}{table}"
    return _layout(
        title="History",
        active="/history",
        body=body,
        capability_label=capability_label,
        kill_switch_engaged=kill_switch_engaged,
    )


# ---------------------------------------------------------------------------
# Safety
# ---------------------------------------------------------------------------


def safety_page(view: SafetyView, csrf: str, flash: ActionOutcome | None) -> str:
    capabilities = "".join(
        f'<li class="cap {"cap-on" if c.enabled else "cap-off"}"><span class="cap-label">{_e(c.label)}</span>'
        f'<span class="cap-note">{_e(c.note)}</span></li>'
        for c in view.capabilities
    )
    engaged = view.execution_kill_switch_engaged
    switch = (
        '<section class="card">'
        "<h2>Kill switch</h2>"
        f'<p class="lead">Execution stop is <strong>{"ENGAGED" if engaged else "released"}</strong>.</p>'
        '<div class="actions">'
        + (
            '<a class="btn btn-primary btn-big" href="/safety/kill-switch?action=release">DEACTIVATE KILL SWITCH</a>'
            if engaged
            else '<a class="btn btn-danger btn-big" href="/safety/kill-switch?action=engage">ACTIVATE KILL SWITCH</a>'
        )
        + "</div>"
        f'<p class="muted">Configuration kill switch (proposal stage): {_e(view.configuration_kill_switch)}.</p>'
        "</section>"
    )
    rules = _kv([(r.label, r.value) for r in view.rules]) if view.rules else "<p>Not available</p>"
    body = (
        "<h1>Safety</h1>"
        f'<section class="card env-card"><div class="env-badge env-badge-large">{_e(view.active_capability.capability.value)}</div>'
        f'<p class="lead">{_e(view.active_capability.note)}</p><ul class="caps">{capabilities}</ul></section>'
        f"{switch}"
        f'<section class="card"><h2>Trading rules</h2><p class="muted">From configuration {_e(view.configuration_id)} '
        f"version {_e(view.configuration_version)}. Read-only.</p>{rules}</section>"
    )
    return _layout(
        title="Safety",
        active="/safety",
        body=body,
        capability_label=view.active_capability.label,
        kill_switch_engaged=engaged,
        flash=flash,
    )


# ---------------------------------------------------------------------------
# Messages
# ---------------------------------------------------------------------------


def message_page(
    *,
    title: str,
    message: str,
    capability_label: str,
    kill_switch_engaged: bool,
    back: str = "/today",
    tone: str = "warn",
) -> str:
    body = (
        f'<section class="confirm"><div class="banner banner-{_e(tone)}"><strong>{_e(title)}.</strong> {_e(message)}</div>'
        f'<a class="btn btn-secondary" href="{_e(back)}">Back</a></section>'
    )
    return _layout(
        title=title,
        active="",
        body=body,
        capability_label=capability_label,
        kill_switch_engaged=kill_switch_engaged,
    )


def loaded_day_page(
    report: SimulationDayReport, capability_label: str, kill_switch_engaged: bool
) -> str:
    refused = "".join(f"<li>{_e(s)}: {_e(r)}</li>" for s, r in report.refused) or "<li>None</li>"
    body = (
        '<a class="back" href="/today">← Today</a><h1>Simulation day loaded</h1>'
        + _kv(
            [
                ("Day", report.day),
                ("Configuration version", str(report.configuration_version)),
                ("Evaluation context", report.evaluation_context_id),
                ("Proposed", ", ".join(report.proposed) or "None"),
                ("Already present", ", ".join(report.already_present) or "None"),
            ]
        )
        + f'<p class="muted">Refused by the engine</p><ul class="evidence">{refused}</ul>'
        '<a class="btn btn-primary" href="/today">Go to Today</a>'
    )
    return _layout(
        title="Simulation day loaded",
        active="/today",
        body=body,
        capability_label=capability_label,
        kill_switch_engaged=kill_switch_engaged,
    )


STYLESHEET = """
:root{--bg:#f6f7f9;--surface:#ffffff;--ink:#1c2430;--muted:#5b6573;--line:#e3e7ec;--accent:#1f5fbf;
--accent-ink:#ffffff;--good:#1d7a4d;--good-bg:#e6f4ec;--warn:#8a5a00;--warn-bg:#fff4dc;--danger:#b3261e;
--danger-bg:#fde8e6;--info:#1f5fbf;--info-bg:#e7eefb;--progress:#6b4fbb;--progress-bg:#efeafb;--sim:#0b7285;}
*{box-sizing:border-box}html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,
"Helvetica Neue",Arial,sans-serif}
a{color:var(--accent)}
.top{background:var(--surface);border-bottom:1px solid var(--line);padding:12px 16px;display:flex;flex-wrap:wrap;gap:12px;
align-items:center;justify-content:space-between;position:sticky;top:0;z-index:2}
.brand{display:flex;align-items:center;gap:12px}.brand-name{font-weight:700;font-size:18px;letter-spacing:.2px}
.env-badge{background:var(--sim);color:#fff;font-weight:800;letter-spacing:.12em;padding:6px 12px;border-radius:8px;font-size:13px}
.env-badge-large{display:inline-block;font-size:18px;padding:10px 18px;margin-bottom:12px}
.nav{display:flex;gap:4px;flex-wrap:wrap}.nav-link{padding:8px 12px;border-radius:8px;text-decoration:none;color:var(--ink);font-weight:600}
.nav-link:hover{background:var(--bg)}.nav-active{background:var(--accent);color:var(--accent-ink)}
.page{max-width:1080px;margin:0 auto;padding:20px 16px 48px}
h1{font-size:28px;margin:8px 0 16px;letter-spacing:-.3px}h2{font-size:20px;margin:0 0 8px}
.title-row{display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:12px}
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin-bottom:20px}
.stat{background:var(--surface);border:1px solid var(--line);border-radius:12px;padding:12px 14px;display:flex;flex-direction:column;gap:4px}
.stat-accent{border-color:var(--accent);box-shadow:inset 0 0 0 1px var(--accent)}
.stat-label{font-size:12px;color:var(--muted);text-transform:uppercase;letter-spacing:.06em}
.stat-value{font-size:24px;font-weight:700}.stat-value.small{font-size:15px;font-weight:600}
.cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:16px}
.card{background:var(--surface);border:1px solid var(--line);border-radius:14px;padding:18px;display:flex;flex-direction:column;gap:12px}
.card-head{display:flex;align-items:center;gap:10px;flex-wrap:wrap}
.ticker{font-size:22px;font-weight:800;letter-spacing:.02em}.ticker.small{font-size:15px}
.side{font-weight:700;color:var(--good);background:var(--good-bg);padding:2px 8px;border-radius:6px;font-size:13px}
.chip{margin-left:auto;font-size:13px;font-weight:700;padding:4px 10px;border-radius:999px;white-space:nowrap}
.chip-action{background:var(--info-bg);color:var(--info);outline:2px solid var(--info)}
.chip-info{background:var(--info-bg);color:var(--info)}.chip-good{background:var(--good-bg);color:var(--good)}
.chip-muted{background:#eef0f3;color:var(--muted)}.chip-danger{background:var(--danger-bg);color:var(--danger)}
.chip-progress{background:var(--progress-bg);color:var(--progress)}
.reason{margin:0;color:var(--muted)}
.numbers{display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:10px;background:var(--bg);border-radius:10px;padding:12px}
.numbers div{display:flex;flex-direction:column}.num-label{font-size:12px;color:var(--muted)}.num{font-weight:700;font-size:17px;font-variant-numeric:tabular-nums}
.note{margin:0;padding:10px 12px;border-radius:10px;font-size:14px}.note-danger{background:var(--danger-bg);color:var(--danger)}
.note-warn{background:var(--warn-bg);color:var(--warn)}.note-info{background:var(--info-bg);color:var(--info)}
.muted{color:var(--muted);font-size:14px;margin:0}.muted.block{display:block}
.actions{display:flex;gap:10px;flex-wrap:wrap}.actions .btn{flex:1 1 140px;text-align:center}
.btn{display:inline-block;padding:12px 18px;border-radius:10px;border:1px solid transparent;font-weight:700;text-decoration:none;
cursor:pointer;font-size:15px;line-height:1.2}
.btn-primary{background:var(--accent);color:#fff}.btn-secondary{background:var(--surface);color:var(--ink);border-color:var(--line)}
.btn-danger{background:var(--danger);color:#fff}.btn-big{padding:16px 22px;font-size:17px;width:100%;text-align:center}
.details summary{cursor:pointer;color:var(--muted);font-size:14px}.details{border-top:1px solid var(--line);padding-top:8px}
.kv{display:grid;grid-template-columns:minmax(120px,max-content) 1fr;gap:6px 16px;margin:8px 0}
.kv dt{color:var(--muted);font-size:14px}.kv dd{margin:0;font-weight:600;overflow-wrap:anywhere}
.evidence{margin:4px 0 0;padding-left:18px;font-size:14px;color:var(--muted)}
.banner{padding:12px 16px;border-radius:12px;margin-bottom:16px;font-size:15px}
.banner-danger{background:var(--danger-bg);color:var(--danger);border:1px solid var(--danger)}
.banner-warn{background:var(--warn-bg);color:var(--warn)}.banner-good{background:var(--good-bg);color:var(--good)}
.confirm{max-width:560px;margin:0 auto;background:var(--surface);border:1px solid var(--line);border-radius:16px;padding:22px}
.lead{font-size:17px}.terms{background:var(--bg);border-radius:12px;padding:6px 14px;margin:14px 0}
.confirm-form{display:flex;flex-direction:column;gap:12px}.field{display:flex;flex-direction:column;gap:6px;font-weight:600}
.field input,.filters input,.filters select{padding:10px;border:1px solid var(--line);border-radius:8px;font-size:15px;background:#fff}
.timeline{list-style:none;padding:0;margin:0;display:grid;gap:6px}
.step{display:grid;grid-template-columns:1fr auto;gap:2px 12px;padding:8px 10px 8px 26px;position:relative;color:var(--muted);border-left:3px solid var(--line)}
.step.done{color:var(--ink);border-left-color:var(--good)}.step-label{font-weight:700}.step-when{font-size:13px;font-variant-numeric:tabular-nums}
.step-note{grid-column:1/-1;font-size:13px;color:var(--muted);overflow-wrap:anywhere}
.filters{display:flex;gap:12px;flex-wrap:wrap;align-items:end;background:var(--surface);border:1px solid var(--line);border-radius:12px;padding:12px;margin-bottom:12px}
.filters label{display:flex;flex-direction:column;gap:4px;font-size:13px;color:var(--muted);font-weight:600}
.table-wrap{overflow-x:auto;background:var(--surface);border:1px solid var(--line);border-radius:12px}
table.history{width:100%;border-collapse:collapse;font-size:14px}table.history th,table.history td{padding:10px 12px;text-align:left;border-bottom:1px solid var(--line);vertical-align:top}
table.history th{font-size:12px;text-transform:uppercase;letter-spacing:.06em;color:var(--muted)}
.caps{list-style:none;padding:0;margin:12px 0 0;display:grid;gap:8px}
.cap{display:flex;flex-direction:column;gap:2px;padding:10px 12px;border-radius:10px;border:1px solid var(--line)}
.cap-on{background:var(--good-bg);border-color:var(--good)}.cap-off{background:var(--bg);color:var(--muted)}.cap-label{font-weight:700}
.cap-note{font-size:14px}
.empty{background:var(--surface);border:1px dashed var(--line);border-radius:14px;padding:28px;text-align:center}
.back{display:inline-block;margin-bottom:8px;text-decoration:none;font-weight:600}
.foot{color:var(--muted);font-size:13px;text-align:center;padding:16px}
.inline{display:inline}
@media (max-width:600px){.page{padding:14px 12px 40px}h1{font-size:24px}.cards{grid-template-columns:1fr}
.kv{grid-template-columns:1fr}.kv dt{margin-top:6px}.stat-value{font-size:20px}.env-badge{font-size:12px;padding:5px 9px}
.numbers{grid-template-columns:repeat(2,1fr)}.chip{margin-left:0}.step{grid-template-columns:1fr}}
"""
