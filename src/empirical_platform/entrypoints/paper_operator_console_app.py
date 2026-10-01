"""MILESTONE-088 -- the PAPER-composed console's routes.

REUSES `build_application` FROM `operator_console_app.py`, UNCHANGED. Every route Today,
Review, Confirm, Active trades, History, Safety and the exit-locked routes are the SAME
handler functions, the SAME CSRF/security/error-translation machinery
(`_operator_console_web.Router`), and the SAME HTML page functions -- because
`PaperConsoleBackend.service` is a real `OperatorConsoleService`, satisfying
`ConsoleBackend` exactly, just composed over Store B (see
`_paper_operator_console_composition`). This module adds exactly two PAPER-only routes that
have no SIMULATION equivalent to reuse:

    GET  /health              -- Phase 7: read-only broker/account/schema health
    POST /prepare-candidate   -- Phase 4/8: the one Owner-triggered action that
                                 originates a new bounded PAPER candidate

DELIBERATELY NOT NAMED /paper/*. A reverse proxy exposing this console privately commonly
does so under its OWN path prefix, e.g. Tailscale Serve's `--set-path /paper`. That prefix
is stripped before the request reaches this app, so an in-page absolute link the app itself
emits as `/paper/health` would, once loaded through such a prefix, resolve in the BROWSER
to `<host>/paper/health` -- which the proxy also routes to this app (since it still starts
with the proxy's own `/paper` prefix) and strips down to a bare `/health` this app never
registered: a 404 on a link the page itself rendered. Naming these routes without a leading
`/paper/` avoids that collision under any proxy path a deployment chooses to use.

`/simulation/load-day` stays wired (inherited from `build_application`) but
`PaperConsoleBackend.load_day()` always refuses cleanly -- there is no PAPER equivalent of a
scripted scenario day, and the console must say so rather than silently doing nothing.
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation

from empirical_platform.entrypoints import _operator_console_html as html
from empirical_platform.entrypoints._operator_console_web import (
    Request,
    Response,
    Router,
    SecuritySession,
    html_response,
    redirect,
)
from empirical_platform.entrypoints._paper_operator_console_composition import (
    PaperConsoleBackend,
)
from empirical_platform.entrypoints.operator_console_app import build_application
from empirical_platform.usecases.full_plan_approval import approve_full_plan
from empirical_platform.usecases.operator_console import (
    CapabilityRefusedError,
    ConsoleRefusalError,
    ExecutionSummary,
    describe_failure,
    refuse_requested_environment,
)
from empirical_platform.usecases.paper_execution import PaperExecutionRefusedError
from empirical_platform.usecases.paper_operator_console import (
    PaperCandidateBlockedError,
    paper_health,
)
from empirical_platform.usecases.v1_management_status import (
    ApprovedPlan,
    PositionExitAttempt,
    management_status,
)

__all__ = ["build_paper_application"]


def _decimal(value: str) -> Decimal | None:
    try:
        return Decimal(value)
    except (InvalidOperation, TypeError):
        return None


def _money(value: Decimal | None) -> str:
    return "Not available" if value is None else f"{value:,.2f}"


_REFUSED = (
    ConsoleRefusalError,
    CapabilityRefusedError,
    PaperExecutionRefusedError,
    PaperCandidateBlockedError,
    ValueError,
    PermissionError,
)


def active_plan_block_for_row(
    row: ExecutionSummary,
    plan: ApprovedPlan | None,
    attempt: PositionExitAttempt | None,
    quote_bid: str | None,
) -> str | None:
    """The APPROVED PLAN block HTML for one Active-trade row, or `None` if this row has no
    managed plan. Pulled out of the route handler so the per-row computation (unrealized
    P&L, max loss, management status) is directly unit-testable without a WSGI client or a
    real PAPER backend."""
    if plan is None:
        return None
    entry_avg = _decimal(row.filled_avg_price)
    current = _decimal(quote_bid) if quote_bid else None
    filled_qty = _decimal(row.filled_quantity)
    unrealized = (
        (current - entry_avg) * filled_qty
        if entry_avg is not None and current is not None and filled_qty is not None
        else None
    )
    max_loss = (
        _money(plan.approved_quantity * (entry_avg - plan.stop_price))
        if entry_avg is not None
        else "Not available"
    )
    return html.approved_plan_block(
        quantity=str(plan.approved_quantity),
        entry_avg_fill=row.filled_avg_price,
        current_price=_money(current),
        unrealized_pnl=_money(unrealized),
        stop_price=_money(plan.stop_price),
        target_price=_money(plan.target_price),
        mandatory_exit=plan.mandatory_liquidation_at.isoformat(timespec="minutes"),
        max_loss=max_loss,
        management_status=management_status(plan, attempt),
        review_manual_exit_url=(
            f"/exit/review?intent={row.intent_id}" if row.can_review_exit else None
        ),
    )


def history_plan_cell_for_row(
    plan: ApprovedPlan | None,
    attempt: PositionExitAttempt | None,
    entry_price: str,
) -> str | None:
    """The History "Plan" column cell HTML for one row, or `None` if this row has no managed
    plan. Pulled out of the route handler for the same reason as `active_plan_block_for_row`.
    """
    if plan is None:
        return None
    trigger = plan.triggered_exit_kind.value if plan.triggered_exit_kind else "—"
    verified = "Yes" if attempt is not None and attempt.position_closed else "No"
    exit_order = attempt.broker_order_id if attempt is not None and attempt.broker_order_id else "—"
    exit_fill = (
        f"{attempt.filled_quantity} @ {attempt.filled_avg_price}"
        if attempt is not None and attempt.filled_quantity is not None
        else "Not filled"
    )
    gross_pnl = "Not available"
    entry_avg = _decimal(entry_price)
    if (
        attempt is not None
        and attempt.filled_avg_price is not None
        and attempt.filled_quantity is not None
        and entry_avg is not None
    ):
        gross_pnl = _money((attempt.filled_avg_price - entry_avg) * attempt.filled_quantity)
    return (
        f"Candidate {plan.candidate_id}<br>Owner {plan.owner_approval_id}"
        f"<br>Trigger {trigger}<br>Exit order {exit_order}"
        f"<br>Exit fill {exit_fill}<br>Zero-verified {verified}"
        f"<br>Gross P&amp;L {gross_pnl}"
    )


def build_paper_application(
    backend: PaperConsoleBackend, *, security: SecuritySession | None = None
) -> Router:
    router = build_application(backend, security=security)
    service = backend.service

    def label() -> str:
        return service.capability.label

    def refusal(error: BaseException, status: str) -> Response:
        title, message = describe_failure(error)
        return html_response(
            html.message_page(
                title=title,
                message=message,
                capability_label=label(),
                kill_switch_engaged=False,
                back="/safety",
                tone="danger" if isinstance(error, CapabilityRefusedError) else "warn",
            ),
            status,
        )

    def paper_health_route(request: Request, csrf: str) -> Response:
        del request, csrf
        try:
            view = paper_health(
                broker=backend._broker,
                market_data=backend._market_data,
                now=datetime.now(UTC),
            )
        except _REFUSED as error:
            return refusal(error, "400 Bad Request")
        except Exception as error:  # noqa: BLE001 - never a traceback to the browser
            print(f"paper-console: unexpected {type(error).__name__}: {error}", file=sys.stderr)
            return refusal(error, "500 Internal Server Error")
        return html_response(html.paper_health_page(view, capability_label=label()))

    def prepare_candidate_route(request: Request, csrf: str) -> Response:
        del csrf
        refuse_requested_environment(request.form)
        try:
            backend.prepare_candidate()
        except _REFUSED as error:
            return refusal(error, "400 Bad Request")
        except Exception as error:  # noqa: BLE001 - never a traceback to the browser
            print(f"paper-console: unexpected {type(error).__name__}: {error}", file=sys.stderr)
            return refusal(error, "500 Internal Server Error")
        return redirect("/today")

    router.get("/health", paper_health_route)
    router.post("/prepare-candidate", prepare_candidate_route)

    # RELEASE v1: when this backend was composed WITH plan management
    # (`paper_operator_console_with_exit_runtime`, `backend._plans is not None`), ONE Owner
    # approval must create BOTH the entry authorization and the durable `ApprovedPlan` the
    # automatic manager later watches. This OVERRIDES the base router's `/confirm-approval`
    # registration (same path, registered again -- a later `router.post` for an existing
    # path replaces it) rather than editing `operator_console_app.py`'s own shared handler,
    # so the plain SIMULATION console and M088's own plain PAPER composition
    # (`backend._plans is None`) are completely untouched by this change.
    if backend._plans is not None:

        def confirm_approval_with_plan(request: Request, csrf: str) -> Response:
            del csrf
            proposal = request.first("proposal")
            try:
                refuse_requested_environment(request.form)
                assert backend._plans is not None
                result = approve_full_plan(
                    backend.service,
                    backend._repositories,
                    backend._plans,
                    proposal_id=proposal,
                    token=request.first("ticket"),
                    candidate_id=request.first("candidate", proposal),
                )
            except _REFUSED as error:
                return refusal(error, "400 Bad Request")
            except Exception as error:  # noqa: BLE001 - never a traceback to the browser
                print(f"paper-console: unexpected {type(error).__name__}: {error}", file=sys.stderr)
                return refusal(error, "500 Internal Server Error")
            if result.plan is not None:
                print(
                    f"paper-console: plan {result.plan.plan_id} for {proposal} "
                    f"{'created' if result.plan_created_now else 'already existed'}",
                    file=sys.stderr,
                )
            return redirect(f"/opportunity?id={proposal}")

        router.post("/confirm-approval", confirm_approval_with_plan)

        # RELEASE v1: Active and History likewise OVERRIDE the base router's registration
        # (same path, registered again) only for the exit-capable composition
        # (`backend._plans is not None`) -- SIMULATION and plain PAPER are untouched.

        def active_with_plan(request: Request, csrf: str) -> Response:
            del request
            try:
                assert backend._plans is not None
                assert backend._exits is not None
                rows = backend.service.active_trades()
                plan_blocks: dict[str, str] = {}
                for row in rows:
                    plan = backend._plans.for_entry(row.intent_id)
                    if plan is None:
                        continue
                    attempt = backend._exits.attempts.active_for_entry(row.intent_id)
                    quote = backend._market_data.fetch_quote(row.symbol)
                    block = active_plan_block_for_row(
                        row, plan, attempt, quote.bid if quote is not None else None
                    )
                    if block is not None:
                        plan_blocks[row.intent_id] = block
            except _REFUSED as error:
                return refusal(error, "400 Bad Request")
            except Exception as error:  # noqa: BLE001 - never a traceback to the browser
                print(f"paper-console: unexpected {type(error).__name__}: {error}", file=sys.stderr)
                return refusal(error, "500 Internal Server Error")
            return html_response(
                html.active_page(rows, csrf, label(), False, None, plan_blocks=plan_blocks)
            )

        def history_with_plan(request: Request, csrf: str) -> Response:
            del csrf
            try:
                assert backend._plans is not None
                assert backend._exits is not None
                filters = {
                    key: request.first(key)
                    for key in ("date", "symbol", "decision", "outcome")
                    if request.first(key)
                }
                rows = backend.service.history(
                    date=filters.get("date") or None,
                    symbol=filters.get("symbol") or None,
                    decision=filters.get("decision") or None,
                    outcome=filters.get("outcome") or None,
                )
                plan_cells: dict[str, str] = {}
                for row in rows:
                    if row.intent_id is None:
                        continue
                    plan = backend._plans.for_entry(row.intent_id)
                    if plan is None:
                        continue
                    attempt = backend._exits.attempts.active_for_entry(row.intent_id)
                    cell = history_plan_cell_for_row(plan, attempt, row.price)
                    if cell is not None:
                        plan_cells[row.intent_id] = cell
            except _REFUSED as error:
                return refusal(error, "400 Bad Request")
            except Exception as error:  # noqa: BLE001 - never a traceback to the browser
                print(f"paper-console: unexpected {type(error).__name__}: {error}", file=sys.stderr)
                return refusal(error, "500 Internal Server Error")
            return html_response(
                html.history_page(
                    rows,
                    filters=filters,
                    capability_label=label(),
                    kill_switch_engaged=False,
                    plan_cells=plan_cells,
                )
            )

        router.get("/active", active_with_plan)
        router.get("/history", history_with_plan)

    return router
