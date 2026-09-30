"""MILESTONE-090 -- the Opportunity Engine's own routes. A new, separate console.

Presentation only: this module turns HTTP into calls on the M090 usecase handlers and their
results into HTML. It imports no persistence and no broker adapter directly -- the backend
object it is handed already composed those. Reuses `_operator_console_web`'s generic,
business-logic-free web plumbing (routing, CSRF, security headers, the threaded server) --
the SAME infrastructure M086-M089's console uses, never their route handlers or HTML.
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from typing import Protocol

from empirical_platform.entrypoints import _opportunity_engine_html as html
from empirical_platform.entrypoints._operator_console_web import (
    Request,
    Response,
    Router,
    SecuritySession,
    html_response,
    redirect,
)
from empirical_platform.usecases.opportunity_engine import (
    OpportunityEngineRefusedError,
    OpportunityStatus,
    TradingOpportunity,
    select_top_actionable,
)

__all__ = ["OpportunityEngineBackend", "build_opportunity_engine_application"]

_REFUSED = (OpportunityEngineRefusedError, ValueError)


class OpportunityEngineBackend(Protocol):
    """What the routes need from the composition root."""

    def today(self) -> tuple[TradingOpportunity, ...]:
        """Every opportunity from the most recent generation, any status."""
        ...

    def get(self, opportunity_id: str) -> TradingOpportunity | None: ...

    def approve(self, opportunity_id: str, *, approved_by: str) -> TradingOpportunity: ...

    def ignore(self, opportunity_id: str, *, ignored_by: str) -> TradingOpportunity: ...

    def top_n(self) -> int: ...


def build_opportunity_engine_application(
    backend: OpportunityEngineBackend, *, security: SecuritySession | None = None
) -> Router:
    security = security or SecuritySession()
    router = Router(security)

    def refusal(title: str, message: str) -> Response:
        return html_response(html.message_page(title=title, message=message))

    def stylesheet(request: Request, csrf: str) -> Response:
        del request, csrf
        body = html.STYLESHEET.encode("utf-8")
        return Response(
            "200 OK",
            [("Content-Type", "text/css; charset=utf-8"), ("Content-Length", str(len(body)))],
            body,
        )

    def guarded(handler: Callable[[Request, str], Response]) -> Callable[[Request, str], Response]:
        def wrapped(request: Request, csrf: str) -> Response:
            try:
                return handler(request, csrf)
            except _REFUSED as error:
                return refusal("Refused", str(error))
            except Exception as error:  # noqa: BLE001 - never a traceback to the browser
                print(
                    f"opportunity-engine: unexpected {type(error).__name__}: {error}",
                    file=sys.stderr,
                )
                return refusal("Something went wrong", "Nothing was sent. Try again.")

        return wrapped

    def today(request: Request, csrf: str) -> Response:
        del request
        opportunities = backend.today()
        actionable = select_top_actionable(opportunities, top_n=backend.top_n())
        candidates = tuple(o for o in opportunities if o.status is OpportunityStatus.CANDIDATE)
        rejected = tuple(o for o in opportunities if o.status is OpportunityStatus.REJECTED)
        shown = {o.opportunity_id for o in (*actionable, *candidates, *rejected)}
        other = tuple(o for o in opportunities if o.opportunity_id not in shown)
        generated_at = opportunities[0].generated_at if opportunities else None
        return html_response(
            html.today_page(
                actionable=actionable,
                candidates=candidates,
                rejected=rejected,
                other=other,
                csrf=csrf,
                generated_at=generated_at,
            )
        )

    def review(request: Request, csrf: str) -> Response:
        opportunity_id = request.first("id")
        opportunity = backend.get(opportunity_id)
        if opportunity is None:
            return refusal("Not found", f"No opportunity {opportunity_id!r} exists.")
        return html_response(html.review_page(opportunity, csrf))

    def approve(request: Request, csrf: str) -> Response:
        del csrf
        opportunity_id = request.first("id")
        approved = backend.approve(opportunity_id, approved_by="owner")
        return html_response(html.approve_confirmation_page(approved))

    def ignore(request: Request, csrf: str) -> Response:
        del csrf
        opportunity_id = request.first("id")
        ignored = backend.ignore(opportunity_id, ignored_by="owner")
        return html_response(html.ignore_confirmation_page(ignored))

    router.get("/static/opportunity-engine.css", stylesheet)
    router.get("/today", guarded(today))
    router.get("/", guarded(today))
    router.get("/opportunity/review", guarded(review))
    router.post("/opportunity/approve", guarded(approve))
    router.post("/opportunity/ignore", guarded(ignore))
    router.on_not_found(lambda request: redirect("/today"))
    return router
