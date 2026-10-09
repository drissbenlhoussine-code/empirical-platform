"""MILESTONE-086 -- the Operator Console pages, rendered as plain HTML.

No template engine, no script, no inline style: every page is a function of a read model
from `usecases.operator_console`, every dynamic value passes through `html.escape`, and the
only stylesheet is served from this process. The design is deliberately calm: a light
neutral surface, one strong typeface stack, cards with room, status chips, and red kept
for genuine danger. A large SIMULATION badge is in the header of every page.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from datetime import UTC, datetime
from html import escape
from types import MappingProxyType

from empirical_platform.usecases.operator_console import (
    NOT_AVAILABLE,
    ActionOutcome,
    ConfirmationView,
    ExecutionSummary,
    HistoryEntry,
    HumanState,
    OpportunityCard,
    SafetyView,
    TodayView,
)
from empirical_platform.usecases.operator_console_exits import ExitReviewView, ExitSummary
from empirical_platform.usecases.operator_console_fixtures import SimulationDayReport
from empirical_platform.usecases.paper_operator_console import PaperHealthView

__all__ = [
    "STYLESHEET",
    "active_page",
    "confirmation_page",
    "execution_page",
    "exit_cancel_confirmation_page",
    "exit_review_page",
    "history_page",
    "kill_switch_confirmation_page",
    "loaded_day_page",
    "message_page",
    "opportunity_page",
    "paper_health_page",
    "safety_page",
    "today_page",
    "url_for",
    "validate_base_path",
]

#: RELEASE v1 Release Blocker (/paper base-path escape). A reverse proxy (Tailscale Serve's
#: `--set-path /paper`) strips its own prefix before the request reaches this process --
#: route REGISTRATION below needs no change. But every URL THIS MODULE GENERATES (hrefs, form
#: actions, redirects) is an ABSOLUTE path the browser resolves against the PROXY'S origin, so
#: it must carry that same prefix back or the next click escapes it entirely -- exactly the
#: 2026-10-07 incident, where clicking Prepare on `/paper/today` landed on the root SIMULATION
#: console. This mirrors M090's own `_opportunity_engine_html.validate_base_path`/`url_for`
#: exactly (see that module's docstring for the full design rationale); it is reimplemented
#: here, not imported, because this module must not depend on the separate M090 console.
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
            "as '/paper' (no scheme/host, no trailing slash, no '//', no '..')"
        )
    return base_path


def url_for(base_path: str, path: str) -> str:
    """Prefix one of this module's own literal route paths with the configured base path.
    `path` must already start with '/' and never itself carry `base_path` -- every call site
    passes a hardcoded route literal (or one built only from hardcoded literals and escaped
    identifiers, never a caller-supplied path), so this can never double-prefix or accept
    external input. `base_path` is assumed already validated by `validate_base_path` at
    startup, once, not per request."""
    assert path.startswith("/"), f"url_for path must be absolute, got {path!r}"
    return base_path + path


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


#: MILESTONE-088. The footer must state the ACTUAL composed environment in plain text, never
#: just the badge colour -- keyed by `capability_label.upper()`, which for every capability this
#: module composes is exactly the `ExecutionCapability` value ("SIMULATION" / "PAPER"). A label
#: this table does not recognise falls back to the original SIMULATION-only wording, so an
#: unexpected label fails safe toward the most conservative statement rather than a blank line.
_FOOTER_NOTE = {
    "SIMULATION": (
        "Simulation only. No order can reach any venue from this console. "
        "Paper execution locked — acceptance pending. Live — not authorized."
    ),
    "PAPER": (
        "PAPER environment — orders reach the real Alpaca PAPER endpoint only "
        "(paper-api.alpaca.markets). This is not real money and not a real-market execution. "
        "Live — not authorized."
    ),
}


def _e(value: object) -> str:
    return escape(str(value), quote=True)


def _when(value: datetime | None) -> str:
    if value is None:
        return "Not available"
    return value.astimezone(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")


def _chip(state: HumanState) -> str:
    return f'<span class="{_CHIP_CLASS[state]}">{_e(state.value)}</span>'


def _env_badge_class(label: str) -> str:
    """RELEASE v1: PAPER gets its own persistent, visually distinct badge color -- the
    exact Owner mistake this answers is mistaking the always-running SIMULATION console
    (teal) for the real-Alpaca-endpoint PAPER one, because both showed the same color and
    differed only in text a small mobile screen makes easy to miss."""
    return "env-badge env-badge-paper" if label.strip().upper() == "PAPER" else "env-badge"


def _layout(
    *,
    title: str,
    active: str,
    body: str,
    capability_label: str,
    kill_switch_engaged: bool,
    flash: ActionOutcome | None = None,
    base_path: str = "",
) -> str:
    nav = "".join(
        f'<a class="nav-link{" nav-active" if href == active else ""}" href="{_e(url_for(base_path, href))}">{_e(label)}</a>'
        for href, label in _NAV
    )
    stop = (
        '<div class="banner banner-danger" role="alert">Kill switch engaged — no new execution can '
        f'start. Existing orders stay visible. <a href="{_e(url_for(base_path, "/safety"))}">Safety</a></div>'
        if kill_switch_engaged
        else ""
    )
    flash_html = ""
    if flash is not None:
        tone = "good" if flash.ok else ("danger" if flash.sent == "unknown" else "warn")
        # MILESTONE-089: this banner renders after BOTH an entry-order confirmation and an
        # exit confirmation, on both SIMULATION and PAPER; "simulated broker" was hardcoded
        # here even though `capability_label` was already a parameter of this function.
        sent_broker = (
            "simulated broker"
            if capability_label.upper() == "SIMULATION"
            else "Alpaca paper endpoint"
        )
        fact = {
            "nothing_sent": "Nothing was sent.",
            "sent": f"An order was sent to the {sent_broker}.",
            "unknown": "Outcome unknown — do not retry.",
            "none": "",
        }.get(flash.sent, "")
        flash_html = (
            f'<div class="banner banner-{tone}" role="status"><strong>{_e(flash.title)}.</strong> '
            f"{_e(flash.message)} <em>{_e(fact)}</em></div>"
        )
    footer_note = _FOOTER_NOTE.get(
        capability_label.upper(),
        "Simulation only. No order can reach any venue from this console. "
        "Paper execution locked — acceptance pending. Live — not authorized.",
    )
    return (
        "<!DOCTYPE html>"
        '<html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>{_e(title)} — Operator Console</title>"
        f'<link rel="stylesheet" href="{_e(url_for(base_path, "/static/console.css"))}"></head>'
        '<body><header class="top"><div class="brand"><span class="brand-name">Operator Console</span>'
        f'<span class="{_env_badge_class(capability_label)}">{_e(capability_label.upper())}</span></div>'
        f'<nav class="nav" aria-label="Primary">{nav}</nav></header>'
        f'<main class="page">{stop}{flash_html}{body}</main>'
        f'<footer class="foot">{_e(footer_note)}</footer>'
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


def today_page(
    view: TodayView, csrf: str, flash: ActionOutcome | None = None, *, base_path: str = ""
) -> str:
    stats = (
        '<section class="stats">'
        f'<div class="stat"><span class="stat-label">Session</span><span class="stat-value">{_e(view.session_date)}</span></div>'
        f'<div class="stat"><span class="stat-label">System</span><span class="stat-value small">{_e(view.system_status)}</span></div>'
        f'<div class="stat"><span class="stat-label">Market</span><span class="stat-value small">{_e(view.market_status)}</span></div>'
        f'<div class="stat"><span class="stat-label">Kill switch</span><span class="stat-value small">'
        f"{'Engaged' if view.kill_switch_engaged else 'Released'}</span></div>"
        f'<div class="stat"><span class="stat-label">Open opportunities</span><span class="stat-value">{view.open_opportunities_count}</span></div>'
        f'<div class="stat stat-accent"><span class="stat-label">Need your decision</span><span class="stat-value">{view.needs_action_count}</span></div>'
        f'<div class="stat"><span class="stat-label">Active executions</span><span class="stat-value">{view.active_executions_count}</span></div>'
        f'<div class="stat"><span class="stat-label">Positions</span><span class="stat-value">{view.active_positions_count}</span></div>'
        "</section>"
    )
    # RELEASE v1 Release Blocker (in-console Owner gate): the Prepare action is appended
    # after the cards, not only shown when the list is empty. `prepare_v1_paper_candidate`
    # is explicitly NOT day-idempotent -- the whole in-console acceptance workflow proved
    # today needs a fresh live-priced candidate each time one expires or is refused, which
    # the OLD "only when nothing exists yet" placement made impossible after the first one.
    prepare_form = ""
    if view.capability.capability.value == "PAPER":
        prepare_form = (
            '<section class="prepare">'
            "<p>Prepare a fresh bounded Paper candidate: the engine re-reads the live market, "
            "the account and your configuration fresh, right now. Nothing is sent until you "
            "explicitly approve and confirm it.</p>"
            f'<form method="post" action="{_e(url_for(base_path, "/prepare-candidate"))}">{_csrf(csrf)}'
            '<button class="btn btn-primary" type="submit">Prepare a fresh Paper candidate</button></form>'
            "</section>"
        )
    if view.opportunities:
        cards = (
            '<section class="cards">'
            + "".join(_card(c, csrf, base_path=base_path) for c in view.opportunities)
            + "</section>"
        ) + prepare_form
    elif view.capability.capability.value == "PAPER":
        # MILESTONE-088: PAPER has no opportunity-scanning engine yet (mission scope).
        cards = (
            '<section class="empty"><h2>No opportunities today</h2>'
            "<p>PAPER has no opportunity-scanning engine in this milestone.</p>"
            "</section>"
        ) + prepare_form
    else:
        cards = (
            '<section class="empty"><h2>No opportunities today</h2>'
            "<p>The engine has proposed nothing for this session. In simulation you can stage a "
            "deterministic day: twelve staged symbols, each exercising one broker behaviour.</p>"
            f'<form method="post" action="{_e(url_for(base_path, "/simulation/load-day"))}">{_csrf(csrf)}'
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
        base_path=base_path,
    )


#: RELEASE v1. Every "RESEARCH CANDIDATE" card carries exactly this banner. Checked by a
#: dedicated whole-module lint test (`test_v1_research_candidate_labeling.py`) that this
#: wording stays plain and un-superlative.
_RESEARCH_CANDIDATE_BANNER = "Research strategy — profitability has not been validated."


def _card(card: OpportunityCard, csrf: str, *, base_path: str = "") -> str:
    t = card.terms
    numbers = (
        '<div class="numbers">'
        f'<div><span class="num-label">Entry</span><span class="num">{_e(t.limit_price)}</span></div>'
        f'<div><span class="num-label">Stop</span><span class="num">{_e(card.stop_price)}</span></div>'
        f'<div><span class="num-label">Target</span><span class="num">{_e(card.target_price)}</span></div>'
        f'<div><span class="num-label">Quantity</span><span class="num">{t.quantity}</span></div>'
        f'<div><span class="num-label">Max Loss</span><span class="num">{_e(card.risk_amount)}</span></div>'
        f'<div><span class="num-label">Configured maximum shares</span><span class="num">{_e(card.maximum_quantity_shares)}</span></div>'
        f'<div><span class="num-label">Configured maximum planned loss</span><span class="num">{_e(card.maximum_planned_loss)}</span></div>'
        f'<div><span class="num-label">Target Gain</span><span class="num">{_e(card.target_gain)}</span></div>'
        f'<div><span class="num-label">R:R</span><span class="num">{_e(card.reward_risk_ratio)}</span></div>'
        f'<div><span class="num-label">Mandatory Exit</span><span class="num">{_when(card.mandatory_exit)}</span></div>'
        f'<div><span class="num-label">Notional</span><span class="num">{_e(t.notional)} {_e(t.currency)}</span></div>'
        f'<div><span class="num-label">Max capital</span><span class="num">{_e(card.maximum_capital)}</span></div>'
        "</div>"
    )
    notes = ""
    if card.blocked_note:
        notes += f'<p class="note note-danger">{_e(card.blocked_note)}</p>'
    if card.attention_note:
        notes += f'<p class="note note-warn">{_e(card.attention_note)}</p>'
    approve_href = _e(url_for(base_path, f"/confirm?action=APPROVE&proposal={card.proposal_id}"))
    reject_href = _e(url_for(base_path, f"/confirm?action=REJECT&proposal={card.proposal_id}"))
    execution_href = (
        _e(url_for(base_path, f"/execution?intent={card.execution.intent_id}"))
        if card.execution is not None
        else ""
    )
    actions = ""
    if card.decision_available and not card.blocked_note:
        actions = (
            '<div class="actions">'
            f'<a class="btn btn-primary" href="{approve_href}">REVIEW PLAN</a>'
            f'<a class="btn btn-secondary" href="{reject_href}">Reject</a>'
            "</div>"
        )
    elif card.decision_available and card.blocked_note:
        actions = f'<div class="actions"><a class="btn btn-secondary" href="{reject_href}">Reject</a></div>'
    elif card.execution is not None:
        actions = (
            f'<div class="actions"><a class="btn btn-secondary" href="{execution_href}">'
            "View execution</a></div>"
        )
    # MILESTONE-088. A settled card (its decision is final -- rejected, expired, blocked,
    # or an execution that reached a terminal state) is evidence, not a current opportunity.
    # `card.reason` and the risk-check count are real historical facts and are not altered
    # or hidden here; this banner only makes the card's CURRENT status unambiguous so it
    # cannot be read as an active recommendation.
    historical = ""
    if card.state_is_settled():
        filled = (
            ""
            if card.execution is None
            else f" Filled quantity: {_e(card.execution.filled_quantity)}."
        )
        historical = (
            '<p class="note note-info"><strong>Historical record — not actionable.</strong> '
            f"This decision is final ({_e(card.state.value).lower()}).{filled} Shown for "
            "evidence, not as a current opportunity.</p>"
        )
    evidence = "".join(f"<li>{_e(line)}</li>" for line in card.evidence) or "<li>Not available</li>"
    invalid_if = (
        "The review page shows different terms than this card ({}), or the authorization "
        "window ({} after review) expires before you confirm.".format(
            "a changed price/quantity/fingerprint", "a short, policy-bounded interval"
        )
    )
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
        + f'<p class="muted">Why this candidate</p><ul class="evidence">{evidence}</ul>'
        + f'<p class="muted">Invalid if</p><p class="reason">{_e(invalid_if)}</p>',
    )
    return (
        f'<article class="card" aria-label="{_e(card.symbol)}">'
        '<div class="badge-row">'
        '<span class="badge badge-research">RESEARCH CANDIDATE</span></div>'
        f'<p class="note note-info">{_e(_RESEARCH_CANDIDATE_BANNER)}</p>'
        f'<div class="card-head"><span class="ticker">{_e(card.symbol)}</span>'
        f'<span class="side">{_e(t.side)}</span>{_chip(card.state)}</div>'
        f"{historical}"
        f'<p class="reason"><strong>Evidence/Quality:</strong> {_e(card.reason)}</p>{numbers}{notes}'
        f'<p class="muted">Proposed {_when(card.created_at)} · expires {_when(card.expires_at)}</p>'
        f"{actions}{details}</article>"
    )


def opportunity_page(
    card: OpportunityCard,
    csrf: str,
    capability_label: str,
    kill_switch_engaged: bool,
    flash: ActionOutcome | None,
    *,
    base_path: str = "",
) -> str:
    today_href = _e(url_for(base_path, "/today"))
    body = f'<a class="back" href="{today_href}">← Today</a><h1>{_e(card.symbol)}</h1>{_card(card, csrf, base_path=base_path)}'
    if card.execution is not None:
        body += _execution_block(card.execution, csrf, base_path=base_path)
    return _layout(
        title=card.symbol,
        active="/today",
        body=body,
        capability_label=capability_label,
        kill_switch_engaged=kill_switch_engaged,
        flash=flash,
        base_path=base_path,
    )


# ---------------------------------------------------------------------------
# Confirmation
# ---------------------------------------------------------------------------


def confirmation_page(
    view: ConfirmationView, csrf: str, capability_label: str, *, base_path: str = ""
) -> str:
    t = view.terms
    approve = view.action == "APPROVE"
    heading = "Confirm approval" if approve else "Confirm rejection"
    verb = "CONFIRM APPROVAL" if approve else "CONFIRM REJECTION"
    action = url_for(base_path, "/confirm-approval" if approve else "/confirm-rejection")
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
            ("Approved stop", view.stop_price),
            ("Target", view.target_price),
            ("Evaluated planned loss", view.planned_loss),
            ("Configured maximum shares", view.maximum_quantity_shares),
            ("Configured maximum planned loss", view.maximum_planned_loss),
            ("Target gain", view.target_gain),
            ("Reward:risk", view.reward_risk_ratio),
            (
                "Mandatory exit",
                _when(view.mandatory_exit) if view.mandatory_exit else NOT_AVAILABLE,
            ),
            ("Time in force", t.time_in_force),
            ("Extended hours", t.extended_hours),
            ("Environment", view.environment),
            ("Account", view.account),
            ("Reference", t.fingerprint_short),
            ("Configuration", f"{view.configuration_governance_id} v{view.configuration_version}"),
            ("Plan fingerprint", view.fingerprint_full),
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
    today_href = _e(url_for(base_path, "/today"))
    body = (
        f'<a class="back" href="{today_href}">← Today</a>'
        f'<section class="confirm"><div class="{_env_badge_class(view.environment)} env-badge-large">{_e(view.environment)}</div>'
        f'<h1>{heading}</h1><p class="lead">{_e(intro)}</p>{warning}'
        f'<div class="terms">{terms}</div>'
        f'<form method="post" action="{_e(action)}" class="confirm-form">{_csrf(csrf)}'
        f'<input type="hidden" name="proposal" value="{_e(view.proposal_id)}">'
        f'<input type="hidden" name="ticket" value="{_e(view.ticket)}">'
        f'<button class="btn {"btn-primary" if approve else "btn-danger"} btn-big" type="submit">{verb}</button>'
        f'<a class="btn btn-secondary btn-big" href="{today_href}">Cancel</a></form></section>'
    )
    return _layout(
        title=heading,
        active="/today",
        body=body,
        capability_label=capability_label,
        kill_switch_engaged=view.kill_switch_engaged,
        base_path=base_path,
    )


def kill_switch_confirmation_page(
    *,
    engage: bool,
    csrf: str,
    capability_label: str,
    kill_switch_engaged: bool,
    base_path: str = "",
) -> str:
    heading = "Activate kill switch" if engage else "Deactivate kill switch"
    effect = (
        "No new execution can start. Pending decisions cannot be confirmed. Existing orders stay "
        "visible and keep being reconciled."
        if engage
        else "Execution can be confirmed again. Nothing is sent by releasing it."
    )
    safety_href = _e(url_for(base_path, "/safety"))
    body = (
        f'<a class="back" href="{safety_href}">← Safety</a>'
        f'<section class="confirm"><h1>{heading}</h1><p class="lead">{_e(effect)}</p>'
        f'<form method="post" action="{_e(url_for(base_path, "/safety/kill-switch"))}" class="confirm-form">{_csrf(csrf)}'
        f'<input type="hidden" name="action" value="{"engage" if engage else "release"}">'
        '<label class="field">Reason (optional)<input type="text" name="reason" maxlength="200"></label>'
        f'<button class="btn {"btn-danger" if engage else "btn-primary"} btn-big" type="submit">'
        f"{'ACTIVATE KILL SWITCH' if engage else 'DEACTIVATE KILL SWITCH'}</button>"
        f'<a class="btn btn-secondary btn-big" href="{safety_href}">Cancel</a></form></section>'
    )
    return _layout(
        title=heading,
        active="/safety",
        body=body,
        capability_label=capability_label,
        kill_switch_engaged=kill_switch_engaged,
        base_path=base_path,
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


def _execution_block(
    summary: ExecutionSummary,
    csrf: str,
    *,
    with_actions: bool = True,
    plan_block: str = "",
    base_path: str = "",
) -> str:
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
            + (
                "</p>"
                if summary.can_review_exit or summary.exit is not None
                else " No exit path exists in this milestone; nothing is sent.</p>"
            )
        )
    if summary.deadline_note:
        pending += f'<p class="note note-{_e(summary.deadline_tone)}"><strong>Liquidation deadline.</strong> {_e(summary.deadline_note)}</p>'
    actions = ""
    buttons = ""
    if with_actions and summary.can_cancel:
        href = _e(url_for(base_path, f"/execution/cancel?intent={summary.intent_id}"))
        buttons += f'<a class="btn btn-secondary" href="{href}">Request cancel</a>'
    if with_actions and summary.can_review_exit:
        href = _e(url_for(base_path, f"/exit/review?intent={summary.intent_id}"))
        buttons += f'<a class="btn btn-primary" href="{href}">Review exit</a>'
    if with_actions and summary.exit is not None and summary.exit.can_cancel:
        href = _e(url_for(base_path, f"/exit/cancel?attempt={summary.exit.attempt_id}"))
        buttons += f'<a class="btn btn-secondary" href="{href}">Request exit cancel</a>'
    if buttons:
        actions = f'<div class="actions">{buttons}</div>'
    exit_block = _exit_block(summary.exit) if summary.exit is not None else ""
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
        f'<span class="side">{_e(t.side)}</span><span class="category">{_e(summary.category)}</span>{_chip(summary.state)}</div>'
        f"{plan_block}{pending}{warnings}{_timeline(summary)}{facts}{exit_block}{actions}"
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


def approved_plan_block(
    *,
    quantity: str,
    entry_avg_fill: str,
    current_price: str,
    unrealized_pnl: str,
    stop_price: str,
    target_price: str,
    mandatory_exit: str,
    max_loss: str,
    management_status: str,
    review_manual_exit_url: str | None,
) -> str:
    """RELEASE v1 -- the APPROVED PLAN block on an Active Trade card.

    Pure string rendering: every value is already computed by the caller (route layer),
    which is where `ApprovedPlan`/`PositionExitAttempt` data actually lives -- this module
    never imports `decision_candidate` directly (entrypoints may only import usecases).
    """
    manual_exit = (
        f'<p class="muted"><a href="{_e(review_manual_exit_url)}">REVIEW MANUAL EXIT</a> '
        "-- a human-authorized escape hatch; automatic management never depends on it "
        "being used.</p>"
        if review_manual_exit_url
        else ""
    )
    return (
        '<section class="card plan-card">'
        f'<h3>Approved plan <span class="chip">{_e(management_status)}</span></h3>'
        '<p class="note note-info">Automatic management is limited to the Owner-approved '
        "Paper plan.</p>"
        '<div class="numbers">'
        f'<div><span class="num-label">Quantity</span><span class="num">{_e(quantity)}</span></div>'
        f'<div><span class="num-label">Entry avg fill</span><span class="num">{_e(entry_avg_fill)}</span></div>'
        f'<div><span class="num-label">Current price</span><span class="num">{_e(current_price)}</span></div>'
        f'<div><span class="num-label">Unrealized P&amp;L</span><span class="num">{_e(unrealized_pnl)}</span></div>'
        f'<div><span class="num-label">Stop</span><span class="num">{_e(stop_price)}</span></div>'
        f'<div><span class="num-label">Target</span><span class="num">{_e(target_price)}</span></div>'
        f'<div><span class="num-label">Mandatory Exit</span><span class="num">{_e(mandatory_exit)}</span></div>'
        f'<div><span class="num-label">Max Loss</span><span class="num">{_e(max_loss)}</span></div>'
        "</div>"
        f"{manual_exit}"
        "</section>"
    )


def _exit_block(x: ExitSummary) -> str:
    """The exit's own timeline and facts: Open position → ... → Position closed."""
    steps = "".join(
        f'<li class="{"step done" if s.reached else "step"}"><span class="step-label">{_e(s.label)}</span>'
        f'<span class="step-when">{_when(s.at) if s.at else ("" if not s.reached else "recorded")}</span>'
        f"{f'<span class="step-note">{_e(s.note)}</span>' if s.note else ''}</li>"
        for s in x.timeline
    )
    notes = ""
    if x.pending_reason:
        tone = "danger" if not x.outcome_known else "info"
        notes += f'<p class="note note-{tone}">{_e(x.pending_reason)}</p>'
    notes += "".join(f'<p class="note note-warn">{_e(w)}</p>' for w in x.warnings)
    facts = _kv(
        [
            ("Exit", f"SELL TO CLOSE {x.quantity} @ {x.limit_price}"),
            ("Exit state", x.state.value),
            ("Exit broker order", x.broker_order_id),
            ("Exit submitted", _when(x.submitted_at)),
            ("Exit final", _when(x.terminal_at) if x.terminal_at else "Not yet"),
            ("Exit filled quantity", x.filled_quantity),
            ("Exit average fill price", x.filled_avg_price),
            (
                "Position closed",
                f"Yes — verified {_when(x.closed_verified_at)}" if x.position_closed else "No",
            ),
            ("Result", x.result_text),
        ]
    )
    return (
        f'<section class="exit" aria-label="exit"><h3>Exit {_chip(x.state)}</h3>{notes}'
        f'<ol class="timeline">{steps}</ol>{facts}'
        + _details(
            "Exit details",
            _kv([("Exit attempt", x.attempt_id), ("Exit engine state", x.raw_state)]),
        )
        + "</section>"
    )


_GROUPS = ("Needs attention", "Exit in progress", "Open position", "Working entry order")


def active_page(
    rows: tuple[ExecutionSummary, ...],
    csrf: str,
    capability_label: str,
    kill_switch_engaged: bool,
    flash: ActionOutcome | None,
    *,
    plan_blocks: Mapping[str, str] = MappingProxyType({}),
    base_path: str = "",
) -> str:
    refresh = (
        f'<form method="post" action="{_e(url_for(base_path, "/active/refresh"))}" class="inline">{_csrf(csrf)}'
        '<button class="btn btn-secondary" type="submit">Check with broker now</button></form>'
    )
    if rows:
        sections = []
        for group in _GROUPS:
            members = [r for r in rows if r.category == group]
            if not members:
                continue
            sections.append(
                f'<h2 class="group">{_e(group)} <span class="muted">({len(members)})</span></h2>'
                '<section class="cards">'
                + "".join(
                    _execution_block(
                        r, csrf, plan_block=plan_blocks.get(r.intent_id, ""), base_path=base_path
                    )
                    for r in members
                )
                + "</section>"
            )
        cards = "".join(sections)
    else:
        cards = '<section class="empty"><h2>No active trades or open positions</h2><p>Every execution has reached a final state and no filled position is held. Closed positions are in History.</p></section>'
    body = f'<div class="title-row"><h1>Active trades</h1>{refresh}</div>{cards}'
    return _layout(
        title="Active trades",
        active="/active",
        body=body,
        capability_label=capability_label,
        kill_switch_engaged=kill_switch_engaged,
        flash=flash,
        base_path=base_path,
    )


def execution_page(
    summary: ExecutionSummary,
    csrf: str,
    capability_label: str,
    kill_switch_engaged: bool,
    flash: ActionOutcome | None,
    *,
    base_path: str = "",
) -> str:
    active_href = _e(url_for(base_path, "/active"))
    body = f'<a class="back" href="{active_href}">← Active trades</a><h1>{_e(summary.symbol)}</h1>{_execution_block(summary, csrf, base_path=base_path)}'
    return _layout(
        title=f"{summary.symbol} execution",
        active="/active",
        body=body,
        capability_label=capability_label,
        kill_switch_engaged=kill_switch_engaged,
        flash=flash,
        base_path=base_path,
    )


def cancel_confirmation_page(
    summary: ExecutionSummary,
    csrf: str,
    capability_label: str,
    kill_switch_engaged: bool,
    *,
    base_path: str = "",
) -> str:
    execution_href = _e(url_for(base_path, f"/execution?intent={summary.intent_id}"))
    body = (
        f'<a class="back" href="{execution_href}">← Execution</a>'
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
        + f'<form method="post" action="{_e(url_for(base_path, "/execution/confirm-cancel"))}" class="confirm-form">{_csrf(csrf)}'
        f'<input type="hidden" name="intent" value="{_e(summary.intent_id)}">'
        '<button class="btn btn-danger btn-big" type="submit">CONFIRM CANCEL REQUEST</button>'
        f'<a class="btn btn-secondary btn-big" href="{execution_href}">Back</a></form></section>'
    )
    return _layout(
        title="Request cancellation",
        active="/active",
        body=body,
        capability_label=capability_label,
        kill_switch_engaged=kill_switch_engaged,
        base_path=base_path,
    )


def exit_review_page(
    view: ExitReviewView, csrf: str, capability_label: str, *, base_path: str = ""
) -> str:
    """The exit review: exact immutable terms, environment badge, one CONFIRM EXIT button.

    THIS PAGE IS ALSO THE FINAL CONFIRMATION (MILESTONE-089). There is no separate screen:
    the ONE "CONFIRM EXIT" button below submits exactly the frozen, ticket-bound terms shown
    above. `final_action_sentence` states that action in one unambiguous sentence, naming the
    real endpoint for PAPER, immediately above the button -- so a click is never mistaken for
    a generic action.
    """
    broker_target = (
        "the simulated broker"
        if view.environment == "SIMULATION"
        else "the real Alpaca PAPER endpoint (not real money, not a live-market execution)"
    )
    final_action_sentence = (
        f"Pressing CONFIRM EXIT will submit one {view.environment} SELL TO CLOSE for the FULL "
        f"attributable position in {view.symbol} ({view.exit_quantity} shares) to {broker_target}. "
        "This cannot be undone, and a second click cannot create a second order."
    )
    warning = ""
    if view.kill_switch_engaged:
        warning = (
            '<div class="banner banner-danger">The kill switch is engaged. This exit cannot be '
            "submitted until it is released on the Safety page. Nothing will be sent.</div>"
        )
    terms = _kv(
        [
            ("Symbol", view.symbol),
            ("Action", "SELL TO CLOSE (full close only)"),
            ("Current verified holding", f"{view.current_holding} shares"),
            ("Exit quantity", f"{view.exit_quantity} shares (full close)"),
            ("Side", view.side),
            ("Order type", view.order_type),
            ("Limit price", view.limit_price),
            ("Time in force", "DAY"),
            ("Extended hours", "No"),
            ("Environment", view.environment),
            ("Account", view.account),
            ("Entry average fill price", view.entry_avg_fill_price),
            ("Current bid / ask", f"{view.current_bid} / {view.current_ask}"),
            ("Price evidence captured", _when(view.quote_captured_at)),
            ("Broker position evidence captured", _when(view.position_captured_at)),
            ("Exit reference (request fingerprint)", view.fingerprint_short),
            ("Client order id (deterministic)", view.client_order_id),
            ("Mandatory liquidation deadline", _when(view.liquidation_deadline)),
            ("Authorization expires", _when(view.authorization_expires_at)),
        ]
    )
    execution_href = _e(url_for(base_path, f"/execution?intent={view.intent_id}"))
    body = (
        f'<a class="back" href="{execution_href}">← Execution</a>'
        f'<section class="confirm"><div class="{_env_badge_class(view.environment)} env-badge-large">{_e(view.environment)}</div>'
        "<h1>Review exit</h1>"
        '<p class="lead">You are about to authorize exactly these terms: one SELL TO CLOSE of the '
        "whole verified position. Nothing has been sent. The engine re-reads the position, the "
        "entry, the kill switch and these terms when you confirm and refuses if anything changed.</p>"
        f'<p class="note note-warn"><strong>Full close.</strong> {_e(view.full_close_warning)}</p>'
        f'<p class="note note-{_e(view.deadline_tone)}"><strong>Liquidation deadline.</strong> {_e(view.deadline_note)}</p>'
        f"{warning}"
        f'<div class="terms">{terms}</div>'
        f'<p class="note note-danger"><strong>Final confirmation.</strong> {_e(final_action_sentence)}</p>'
        f'<form method="post" action="{_e(url_for(base_path, "/exit/confirm"))}" class="confirm-form">{_csrf(csrf)}'
        f'<input type="hidden" name="intent" value="{_e(view.intent_id)}">'
        f'<input type="hidden" name="ticket" value="{_e(view.ticket)}">'
        '<button class="btn btn-danger btn-big" type="submit">CONFIRM EXIT</button>'
        f'<a class="btn btn-secondary btn-big" href="{execution_href}">Cancel</a></form></section>'
    )
    return _layout(
        title="Review exit",
        active="/active",
        body=body,
        capability_label=capability_label,
        kill_switch_engaged=view.kill_switch_engaged,
        base_path=base_path,
    )


def exit_cancel_confirmation_page(
    summary: ExecutionSummary,
    csrf: str,
    capability_label: str,
    kill_switch_engaged: bool,
    *,
    base_path: str = "",
) -> str:
    x = summary.exit
    assert x is not None
    broker = "simulated broker" if capability_label == "Simulation" else "Alpaca paper endpoint"
    execution_href = _e(url_for(base_path, f"/execution?intent={summary.intent_id}"))
    body = (
        f'<a class="back" href="{execution_href}">← Execution</a>'
        '<section class="confirm"><h1>Request exit cancellation</h1><p class="lead">A cancel request is '
        f"sent to the {broker} for this exact exit order. A request is not a cancellation: the "
        "exit may still fill before it is cancelled. The position stays open until an exit fills and "
        "is verified.</p>"
        + _kv(
            [
                ("Symbol", summary.symbol),
                ("Exit broker order", x.broker_order_id),
                ("Exit state", x.state.value),
            ]
        )
        + f'<form method="post" action="{_e(url_for(base_path, "/exit/confirm-cancel"))}" class="confirm-form">{_csrf(csrf)}'
        f'<input type="hidden" name="attempt" value="{_e(x.attempt_id)}">'
        f'<input type="hidden" name="intent" value="{_e(summary.intent_id)}">'
        '<button class="btn btn-danger btn-big" type="submit">CONFIRM EXIT CANCEL REQUEST</button>'
        f'<a class="btn btn-secondary btn-big" href="{execution_href}">Back</a></form></section>'
    )
    return _layout(
        title="Request exit cancellation",
        active="/active",
        body=body,
        capability_label=capability_label,
        kill_switch_engaged=kill_switch_engaged,
        base_path=base_path,
    )


# ---------------------------------------------------------------------------
# History
# ---------------------------------------------------------------------------


def _history_view_link(r: HistoryEntry, base_path: str) -> str:
    href = (
        url_for(base_path, f"/execution?intent={r.intent_id}")
        if r.intent_id
        else url_for(base_path, f"/opportunity?id={r.proposal_id}")
    )
    return f'<a href="{_e(href)}">View</a>'


def history_page(
    rows: tuple[HistoryEntry, ...],
    *,
    filters: dict[str, str],
    capability_label: str,
    kill_switch_engaged: bool,
    plan_cells: Mapping[str, str] = MappingProxyType({}),
    base_path: str = "",
) -> str:
    def option(name: str, value: str, label: str) -> str:
        selected = " selected" if filters.get(name, "") == value else ""
        return f'<option value="{_e(value)}"{selected}>{_e(label)}</option>'

    form = (
        f'<form method="get" action="{_e(url_for(base_path, "/history"))}" class="filters">'
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
    show_plan_column = bool(plan_cells)

    def _plan_cell(r: HistoryEntry) -> str:
        if not show_plan_column:
            return ""
        return f"<td>{plan_cells.get(r.intent_id or r.proposal_id, '—')}</td>"

    if rows:
        table_rows = "".join(
            "<tr>"
            f"<td>{_when(r.timestamp)}</td>"
            f'<td><span class="ticker small">{_e(r.symbol)}</span></td>'
            f"<td>{_e(r.proposal_state)}</td>"
            f'<td>{_e(r.decision)}<span class="muted block">{_e(r.decided_by)}</span></td>'
            f'<td>{_e(r.execution_kind)}<span class="muted block">{_e(r.execution_outcome)}</span></td>'
            f"<td>{_chip(r.final_state)}</td>"
            f"<td>{_e(r.quantity)} @ {_e(r.price)}</td>"
            f"<td>{_e(r.result)}</td>"
            f"{_plan_cell(r)}"
            f"<td>{_history_view_link(r, base_path)}</td>"
            "</tr>"
            for r in rows
        )
        plan_header = "<th>Plan</th>" if show_plan_column else ""
        table = (
            '<div class="table-wrap"><table class="history"><thead><tr><th>When</th><th>Symbol</th>'
            "<th>Model proposal</th><th>Owner decision</th><th>Execution</th><th>Final state</th>"
            f"<th>Qty @ price</th><th>Result</th>{plan_header}<th></th></tr></thead>"
            f"<tbody>{table_rows}</tbody></table></div>"
        )
    else:
        table = '<section class="empty"><h2>Nothing matches</h2></section>'
    # MILESTONE-089: this used to hardcode "simulation execution. Broker/Paper execution --
    # future only." even when the console composed here was PAPER -- by then no longer true,
    # since PAPER execution and PAPER exits are real and current, not a future capability.
    execution_clause = (
        "the simulation execution. Broker/Paper execution — future only."
        if capability_label.upper() == "SIMULATION"
        else "the Alpaca Paper execution. Orders and exits reach the real Alpaca PAPER endpoint; "
        "not real money and not a live-market execution."
    )
    legend = (
        '<p class="muted">Columns distinguish the model proposal, the Owner decision and '
        + execution_clause
        + " Results are shown only when the platform records one; no P&amp;L is computed from "
        "incomplete data.</p>"
    )
    body = f"<h1>History</h1>{form}{legend}{table}"
    return _layout(
        title="History",
        active="/history",
        body=body,
        capability_label=capability_label,
        kill_switch_engaged=kill_switch_engaged,
        base_path=base_path,
    )


# ---------------------------------------------------------------------------
# Safety
# ---------------------------------------------------------------------------


def safety_page(
    view: SafetyView, csrf: str, flash: ActionOutcome | None, *, base_path: str = ""
) -> str:
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
            f'<a class="btn btn-primary btn-big" href="{_e(url_for(base_path, "/safety/kill-switch?action=release"))}">DEACTIVATE KILL SWITCH</a>'
            if engaged
            else f'<a class="btn btn-danger btn-big" href="{_e(url_for(base_path, "/safety/kill-switch?action=engage"))}">ACTIVATE KILL SWITCH</a>'
        )
        + "</div>"
        f'<p class="muted">Configuration kill switch (proposal stage): {_e(view.configuration_kill_switch)}.</p>'
        "</section>"
    )
    rules = _kv([(r.label, r.value) for r in view.rules]) if view.rules else "<p>Not available</p>"
    # MILESTONE-088: a PAPER-composed console links to its own read-only broker/schema
    # health page from here; a SIMULATION-composed one has nothing there and shows nothing.
    paper_link = (
        '<section class="card"><h2>Paper broker &amp; schema health</h2>'
        '<p class="muted">Endpoint, account, market clock, positions and quote -- read-only.'
        f'</p><a class="btn btn-secondary" href="{_e(url_for(base_path, "/health"))}">Open Paper health</a></section>'
        if view.active_capability.capability.value == "PAPER"
        else ""
    )
    # RELEASE v1. Exactly the mission's required statements, plain text, no interpretation.
    v1_statements = (
        '<section class="card"><h2>What this system is</h2>'
        '<ul class="limits">'
        "<li>Environment: <strong>PAPER</strong></li>"
        "<li>Live: <strong>UNAVAILABLE</strong></li>"
        "<li>Strategy profitability: <strong>NOT VALIDATED</strong></li>"
        "<li>Automatic authority: <strong>POSITION-REDUCING ONLY, AFTER THE OWNER APPROVES "
        "A FULL PLAN</strong> -- see /today → Research Candidates for how a plan is "
        f'approved and <a href="{_e(url_for(base_path, "/active"))}">Active</a> for what is currently being managed.</li>'
        "</ul>"
        '<p class="muted">No:</p>'
        '<ul class="limits">'
        "<li>automatic new opportunities becoming orders</li>"
        "<li>autonomous entry without Owner approval</li>"
        "<li>shorting</li>"
        "<li>leverage escalation</li>"
        "<li>overnight intention</li>"
        "</ul></section>"
    )
    body = (
        "<h1>Safety</h1>"
        f'<section class="card env-card"><div class="{_env_badge_class(view.active_capability.capability.value)} env-badge-large">{_e(view.active_capability.capability.value)}</div>'
        f'<p class="lead">{_e(view.active_capability.note)}</p><ul class="caps">{capabilities}</ul></section>'
        f"{v1_statements}"
        f"{switch}"
        f'<section class="card"><h2>Trading rules</h2><p class="muted">From configuration {_e(view.configuration_id)} '
        f"version {_e(view.configuration_version)}. Read-only.</p>{rules}</section>"
        f"{paper_link}"
    )
    return _layout(
        title="Safety",
        active="/safety",
        body=body,
        capability_label=view.active_capability.label,
        kill_switch_engaged=engaged,
        flash=flash,
        base_path=base_path,
    )


def paper_health_page(view: PaperHealthView, *, capability_label: str, base_path: str = "") -> str:
    """MILESTONE-088 Phase 7/13: read-only PAPER broker and account health.

    No field of `PaperHealthView` can hold a credential (see its own docstring), and none
    is rendered here beyond what that view already carries.
    """
    warnings: list[str] = []
    if not view.is_pinned_paper_host:
        warnings.append(f"Trading endpoint is {view.trading_endpoint!r}, not the pinned host.")
    if view.trading_blocked:
        warnings.append("Trading is BLOCKED on this account.")
    if view.account_blocked:
        warnings.append("This account is BLOCKED.")
    if view.trade_suspended_by_user:
        warnings.append("Trading is suspended by the account owner.")
    banner = f'<div class="banner banner-danger">{_e(" ".join(warnings))}</div>' if warnings else ""
    facts = _kv(
        [
            ("Trading endpoint", view.trading_endpoint),
            ("Pinned PAPER host", "Yes" if view.is_pinned_paper_host else "NO"),
            ("Market data endpoint", view.market_data_endpoint),
            ("Account reachable", "Yes" if view.account_reachable else "No"),
            ("Account status", view.account_status),
            ("Account reference", view.account_reference),
            ("Trading blocked", "Yes" if view.trading_blocked else "No"),
            ("Account blocked", "Yes" if view.account_blocked else "No"),
            ("Trade suspended by user", "Yes" if view.trade_suspended_by_user else "No"),
            ("Market is open", "Yes" if view.market_is_open else "No"),
            ("Next open", _when(view.next_open)),
            ("Next close", _when(view.next_close)),
            ("Symbol", view.symbol),
            ("Asset tradable", "Yes" if view.asset_tradable else "No"),
            ("Asset status", view.asset_status),
            ("Current position (shares)", view.position_quantity),
            ("Quote bid / ask", f"{view.quote_bid} / {view.quote_ask}"),
            ("Quote captured at", _when(view.quote_captured_at)),
            ("Quote age (s)", view.quote_age_seconds),
            ("Quote source", view.quote_source),
        ]
    )
    body = (
        f'<a class="back" href="{_e(url_for(base_path, "/safety"))}">← Safety</a>'
        "<h1>Paper health</h1>"
        '<p class="lead">Read-only. Every fact below came from a GET request to the real '
        "Alpaca PAPER endpoint or its market-data endpoint; nothing here can place or cancel "
        "an order.</p>"
        f"{banner}"
        f'<section class="card">{facts}</section>'
    )
    return _layout(
        title="Paper health",
        active="/safety",
        body=body,
        capability_label=capability_label,
        kill_switch_engaged=False,
        base_path=base_path,
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
    base_path: str = "",
) -> str:
    # ONE application point for `back`: every caller passes a bare route literal (optionally
    # with its own query string, e.g. "/opportunity?id=X") and this is the only place that
    # prefixes it -- callers never hand-build the prefix themselves.
    body = (
        f'<section class="confirm"><div class="banner banner-{_e(tone)}"><strong>{_e(title)}.</strong> {_e(message)}</div>'
        f'<a class="btn btn-secondary" href="{_e(url_for(base_path, back))}">Back</a></section>'
    )
    return _layout(
        title=title,
        active="",
        body=body,
        capability_label=capability_label,
        kill_switch_engaged=kill_switch_engaged,
        base_path=base_path,
    )


def loaded_day_page(
    report: SimulationDayReport,
    capability_label: str,
    kill_switch_engaged: bool,
    *,
    base_path: str = "",
) -> str:
    refused = "".join(f"<li>{_e(s)}: {_e(r)}</li>" for s, r in report.refused) or "<li>None</li>"
    today_href = _e(url_for(base_path, "/today"))
    body = (
        f'<a class="back" href="{today_href}">← Today</a><h1>Simulation day loaded</h1>'
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
        f'<a class="btn btn-primary" href="{today_href}">Go to Today</a>'
    )
    return _layout(
        title="Simulation day loaded",
        active="/today",
        body=body,
        capability_label=capability_label,
        kill_switch_engaged=kill_switch_engaged,
        base_path=base_path,
    )


STYLESHEET = """
:root{--bg:#f6f7f9;--surface:#ffffff;--ink:#1c2430;--muted:#5b6573;--line:#e3e7ec;--accent:#1f5fbf;
--accent-ink:#ffffff;--good:#1d7a4d;--good-bg:#e6f4ec;--warn:#8a5a00;--warn-bg:#fff4dc;--danger:#b3261e;
--danger-bg:#fde8e6;--info:#1f5fbf;--info-bg:#e7eefb;--progress:#6b4fbb;--progress-bg:#efeafb;--sim:#0b7285;
--paper:#9a3412;}
*{box-sizing:border-box}html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,
"Helvetica Neue",Arial,sans-serif}
a{color:var(--accent)}
.top{background:var(--surface);border-bottom:1px solid var(--line);padding:12px 16px;display:flex;flex-wrap:wrap;gap:12px;
align-items:center;justify-content:space-between;position:sticky;top:0;z-index:2}
.brand{display:flex;align-items:center;gap:12px}.brand-name{font-weight:700;font-size:18px;letter-spacing:.2px}
.env-badge{background:var(--sim);color:#fff;font-weight:800;letter-spacing:.12em;padding:7px 14px;border-radius:8px;font-size:14px}
.env-badge-paper{background:var(--paper);box-shadow:0 0 0 2px #fff,0 0 0 4px var(--paper)}
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
.category{font-size:12px;color:var(--muted);text-transform:uppercase;letter-spacing:.06em}
.group{margin:20px 0 10px;font-size:18px}
.exit{border-top:2px solid var(--line);padding-top:10px;display:flex;flex-direction:column;gap:10px}
.exit h3{margin:0;font-size:16px;display:flex;align-items:center;gap:10px}
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
.badge-row{display:flex;flex-wrap:wrap;gap:6px;margin-bottom:8px}
.badge{background:var(--bg);border:1px solid var(--line);border-radius:6px;padding:3px 9px;font-size:11px;font-weight:700;letter-spacing:.03em}
.badge-research{background:var(--info-bg);color:var(--info);border-color:var(--info)}
ul.limits{margin:0 0 10px;padding-left:20px}ul.limits li{margin:4px 0;font-size:14px}
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
