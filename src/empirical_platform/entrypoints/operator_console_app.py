"""MILESTONE-086 -- the Operator Console's routes.

Presentation only. This module turns HTTP requests into calls on
`usecases.operator_console.OperatorConsoleService` and its results into pages. It imports
no persistence, no broker adapter and no domain module: the service object it is handed
already decided the capability (SIMULATION) and owns every repository.

Every state-changing route is a POST (the web layer enforces the CSRF token), refuses any
`environment` selection from the browser, and answers with a 303 to a GET page carrying a
one-shot flash message -- so a refresh re-reads the durable state and never re-submits.
"""

from __future__ import annotations

import sys
import threading
from collections.abc import Callable
from typing import Protocol

from empirical_platform.entrypoints import _operator_console_html as html
from empirical_platform.entrypoints._operator_console_web import (
    Request,
    Response,
    Router,
    SecuritySession,
    html_response,
    redirect,
)
from empirical_platform.usecases.decision_to_approval import NotFoundError
from empirical_platform.usecases.operator_console import (
    ActionOutcome,
    CapabilityRefusedError,
    ConsoleRefusalError,
    ExecutionCapability,
    OperatorConsoleService,
    describe_failure,
    refuse_requested_environment,
)
from empirical_platform.usecases.operator_console_fixtures import SimulationDayReport
from empirical_platform.usecases.paper_execution import PaperExecutionRefusedError

__all__ = ["ConsoleBackend", "build_application"]


class ConsoleBackend(Protocol):
    """What the routes need from the composition root."""

    @property
    def service(self) -> OperatorConsoleService: ...

    @property
    def configuration_id(self) -> str: ...

    def load_day(self) -> SimulationDayReport: ...


_REFUSED = (
    ConsoleRefusalError,
    CapabilityRefusedError,
    NotFoundError,
    PaperExecutionRefusedError,
    ValueError,
    PermissionError,
)


class _Flash:
    """One-shot messages keyed by the browser's session cookie. In-memory: a restart drops them."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._pending: dict[str, ActionOutcome] = {}

    def put(self, session_id: str, outcome: ActionOutcome) -> None:
        with self._lock:
            self._pending[session_id] = outcome

    def take(self, session_id: str) -> ActionOutcome | None:
        with self._lock:
            return self._pending.pop(session_id, None)


def build_application(
    backend: ConsoleBackend, *, security: SecuritySession | None = None, base_path: str = ""
) -> Router:
    # RELEASE v1 Release Blocker (/paper base-path escape): fail closed at composition time,
    # not per-request -- exactly `_opportunity_engine_html.validate_base_path`'s own contract.
    base_path = html.validate_base_path(base_path)
    security = security or SecuritySession()
    router = Router(security)
    flash = _Flash()
    service = backend.service

    def label() -> str:
        return service.capability.label

    def engaged() -> bool:
        try:
            return service.safety(backend.configuration_id).execution_kill_switch_engaged
        except Exception:  # noqa: BLE001 - the banner must not take the page down
            return False

    def session_of(request: Request) -> str:
        return request.cookies.get("operator_console_session", "")

    def refusal(request: Request, error: BaseException, status: str) -> Response:
        title, message = describe_failure(error)
        return html_response(
            html.message_page(
                title=title,
                message=message,
                capability_label=label(),
                kill_switch_engaged=engaged(),
                back="/today",
                tone="danger" if isinstance(error, CapabilityRefusedError) else "warn",
                base_path=base_path,
            ),
            status,
        )

    def guarded(handler: Callable[[Request, str], Response]) -> Callable[[Request, str], Response]:
        def wrapped(request: Request, csrf: str) -> Response:
            try:
                return handler(request, csrf)
            except CapabilityRefusedError as error:
                return refusal(request, error, "403 Forbidden")
            except NotFoundError as error:
                return refusal(request, error, "404 Not Found")
            except _REFUSED as error:
                return refusal(request, error, "400 Bad Request")
            except Exception as error:  # noqa: BLE001 - never a traceback to the browser
                print(
                    f"operator-console: unexpected {type(error).__name__}: {error}", file=sys.stderr
                )
                return refusal(request, error, "500 Internal Server Error")

        return wrapped

    # -- static ------------------------------------------------------------------------

    def stylesheet(request: Request, csrf: str) -> Response:
        del request, csrf
        body = html.STYLESHEET.encode("utf-8")
        return Response(
            "200 OK",
            [("Content-Type", "text/css; charset=utf-8"), ("Content-Length", str(len(body)))],
            body,
        )

    # -- pages -------------------------------------------------------------------------

    def home(request: Request, csrf: str) -> Response:
        del request, csrf
        return redirect(html.url_for(base_path, "/today"))

    def today(request: Request, csrf: str) -> Response:
        view = service.today()
        return html_response(
            html.today_page(view, csrf, flash.take(session_of(request)), base_path=base_path)
        )

    def opportunity(request: Request, csrf: str) -> Response:
        card = service.opportunity(request.first("id"))
        return html_response(
            html.opportunity_page(
                card,
                csrf,
                label(),
                engaged(),
                flash.take(session_of(request)),
                base_path=base_path,
            )
        )

    def confirm(request: Request, csrf: str) -> Response:
        refuse_requested_environment(request.query)
        action = request.first("action").upper()
        proposal = request.first("proposal")
        if action == "APPROVE":
            view = service.prepare_approval(proposal)
        elif action == "REJECT":
            view = service.prepare_rejection(proposal)
        else:
            raise ConsoleRefusalError(
                "Unknown action", "That action does not exist. Nothing was done."
            )
        return html_response(html.confirmation_page(view, csrf, label(), base_path=base_path))

    def confirm_approval(request: Request, csrf: str) -> Response:
        del csrf
        refuse_requested_environment(request.form)
        proposal = request.first("proposal")
        outcome = service.confirm_approval(proposal, request.first("ticket"))
        flash.put(session_of(request), outcome)
        return redirect(html.url_for(base_path, f"/opportunity?id={proposal}"))

    def confirm_rejection(request: Request, csrf: str) -> Response:
        del csrf
        refuse_requested_environment(request.form)
        proposal = request.first("proposal")
        outcome = service.confirm_rejection(proposal, request.first("ticket"))
        flash.put(session_of(request), outcome)
        return redirect(html.url_for(base_path, f"/opportunity?id={proposal}"))

    def active(request: Request, csrf: str) -> Response:
        rows = service.active_trades()
        return html_response(
            html.active_page(
                rows, csrf, label(), engaged(), flash.take(session_of(request)), base_path=base_path
            )
        )

    def refresh(request: Request, csrf: str) -> Response:
        del csrf
        refuse_requested_environment(request.form)
        refreshed = service.refresh_executions()
        # MILESTONE-088: PAPER also composes this service now, so the wording names the
        # actual broker rather than always claiming "simulated".
        broker = (
            "simulated broker"
            if service.capability.capability is ExecutionCapability.SIMULATION
            else "Alpaca paper endpoint"
        )
        flash.put(
            session_of(request),
            ActionOutcome(
                True,
                "Checked with the broker",
                f"{len(refreshed)} execution(s) were reconciled against the {broker}.",
                "none",
            ),
        )
        return redirect(html.url_for(base_path, "/active"))

    def execution(request: Request, csrf: str) -> Response:
        summary = service.execution(request.first("intent"))
        return html_response(
            html.execution_page(
                summary,
                csrf,
                label(),
                engaged(),
                flash.take(session_of(request)),
                base_path=base_path,
            )
        )

    def cancel(request: Request, csrf: str) -> Response:
        summary = service.execution(request.first("intent"))
        return html_response(
            html.cancel_confirmation_page(summary, csrf, label(), engaged(), base_path=base_path)
        )

    def confirm_cancel(request: Request, csrf: str) -> Response:
        del csrf
        refuse_requested_environment(request.form)
        intent = request.first("intent")
        outcome = service.cancel_execution(intent)
        flash.put(session_of(request), outcome)
        return redirect(html.url_for(base_path, f"/execution?intent={intent}"))

    # -- MILESTONE-087: exits --------------------------------------------------------

    def exits_or_refuse() -> object:
        exits = service.exits
        if exits is None:
            raise ConsoleRefusalError(
                "No exit path", "This console has no exit path composed. Nothing was done."
            )
        return exits

    def exit_review(request: Request, csrf: str) -> Response:
        refuse_requested_environment(request.query)
        exits = exits_or_refuse()
        view = exits.review(request.first("intent"))  # type: ignore[attr-defined]
        return html_response(html.exit_review_page(view, csrf, label(), base_path=base_path))

    def exit_confirm(request: Request, csrf: str) -> Response:
        del csrf
        refuse_requested_environment(request.form)
        exits = exits_or_refuse()
        intent = request.first("intent")
        outcome = exits.confirm(intent, request.first("ticket"))  # type: ignore[attr-defined]
        flash.put(session_of(request), outcome)
        return redirect(html.url_for(base_path, f"/execution?intent={intent}"))

    def exit_cancel(request: Request, csrf: str) -> Response:
        exits_or_refuse()
        attempt = request.first("attempt")
        rows = [
            r
            for r in service.active_trades()
            if r.exit is not None and r.exit.attempt_id == attempt
        ]
        if not rows:
            raise NotFoundError(f"no exit {attempt!r} is active")
        return html_response(
            html.exit_cancel_confirmation_page(
                rows[0], csrf, label(), engaged(), base_path=base_path
            )
        )

    def exit_confirm_cancel(request: Request, csrf: str) -> Response:
        del csrf
        refuse_requested_environment(request.form)
        exits = exits_or_refuse()
        outcome = exits.cancel(request.first("attempt"))  # type: ignore[attr-defined]
        flash.put(session_of(request), outcome)
        return redirect(html.url_for(base_path, f"/execution?intent={request.first('intent')}"))

    def history(request: Request, csrf: str) -> Response:
        del csrf
        filters = {
            key: request.first(key)
            for key in ("date", "symbol", "decision", "outcome")
            if request.first(key)
        }
        rows = service.history(
            date=filters.get("date") or None,
            symbol=filters.get("symbol") or None,
            decision=filters.get("decision") or None,
            outcome=filters.get("outcome") or None,
        )
        return html_response(
            html.history_page(
                rows,
                filters=filters,
                capability_label=label(),
                kill_switch_engaged=engaged(),
                base_path=base_path,
            )
        )

    def safety(request: Request, csrf: str) -> Response:
        view = service.safety(backend.configuration_id)
        return html_response(
            html.safety_page(view, csrf, flash.take(session_of(request)), base_path=base_path)
        )

    def kill_switch_form(request: Request, csrf: str) -> Response:
        action = request.first("action")
        if action not in {"engage", "release"}:
            raise ConsoleRefusalError(
                "Unknown action", "That action does not exist. Nothing was done."
            )
        return html_response(
            html.kill_switch_confirmation_page(
                engage=action == "engage",
                csrf=csrf,
                capability_label=label(),
                kill_switch_engaged=engaged(),
                base_path=base_path,
            )
        )

    def kill_switch(request: Request, csrf: str) -> Response:
        del csrf
        refuse_requested_environment(request.form)
        action = request.first("action")
        if action not in {"engage", "release"}:
            raise ConsoleRefusalError(
                "Unknown action", "That action does not exist. Nothing was done."
            )
        outcome = service.set_kill_switch(
            engaged=action == "engage", reason=request.first("reason")
        )
        flash.put(session_of(request), outcome)
        return redirect(html.url_for(base_path, "/safety"))

    def load_day(request: Request, csrf: str) -> Response:
        del csrf
        refuse_requested_environment(request.form)
        report = backend.load_day()
        return html_response(html.loaded_day_page(report, label(), engaged(), base_path=base_path))

    def not_found(request: Request) -> Response:
        del request
        return html_response(
            html.message_page(
                title="Not found",
                message="There is no such page. Nothing was done.",
                capability_label=label(),
                kill_switch_engaged=engaged(),
                base_path=base_path,
            ),
            "404 Not Found",
        )

    def csrf_refused(request: Request, reason: str) -> Response:
        del request
        return html_response(
            html.message_page(
                title="Not accepted",
                message=reason,
                capability_label=label(),
                kill_switch_engaged=engaged(),
                tone="danger",
                base_path=base_path,
            ),
            "403 Forbidden",
        )

    router.get("/static/console.css", stylesheet)
    router.get("/", guarded(home))
    router.get("/today", guarded(today))
    router.get("/opportunity", guarded(opportunity))
    router.get("/confirm", guarded(confirm))
    router.post("/confirm-approval", guarded(confirm_approval))
    router.post("/confirm-rejection", guarded(confirm_rejection))
    router.get("/active", guarded(active))
    router.post("/active/refresh", guarded(refresh))
    router.get("/execution", guarded(execution))
    router.get("/execution/cancel", guarded(cancel))
    router.post("/execution/confirm-cancel", guarded(confirm_cancel))
    router.get("/exit/review", guarded(exit_review))
    router.post("/exit/confirm", guarded(exit_confirm))
    router.get("/exit/cancel", guarded(exit_cancel))
    router.post("/exit/confirm-cancel", guarded(exit_confirm_cancel))
    router.get("/history", guarded(history))
    router.get("/safety", guarded(safety))
    router.get("/safety/kill-switch", guarded(kill_switch_form))
    router.post("/safety/kill-switch", guarded(kill_switch))
    router.post("/simulation/load-day", guarded(load_day))
    router.on_not_found(not_found)
    router.on_refused(csrf_refused)
    return router
