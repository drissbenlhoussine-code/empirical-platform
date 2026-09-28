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
from empirical_platform.usecases.operator_console import (
    CapabilityRefusedError,
    ConsoleRefusalError,
    describe_failure,
    refuse_requested_environment,
)
from empirical_platform.usecases.paper_execution import PaperExecutionRefusedError
from empirical_platform.usecases.paper_operator_console import (
    PaperCandidateBlockedError,
    paper_health,
)

__all__ = ["build_paper_application"]

_REFUSED = (
    ConsoleRefusalError,
    CapabilityRefusedError,
    PaperExecutionRefusedError,
    PaperCandidateBlockedError,
    ValueError,
    PermissionError,
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
    return router
