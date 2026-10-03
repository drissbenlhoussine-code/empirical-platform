"""Additive read-only market panel in the existing console, never a second server."""

from datetime import UTC, datetime
from html import escape

from empirical_platform.entrypoints._operator_console_html import _layout
from empirical_platform.entrypoints._operator_console_web import (
    Request,
    Response,
    Router,
    html_response,
)
from empirical_platform.usecases.market_console import MarketReviewService, market_status


def register_market_routes(router: Router, reviews: MarketReviewService | None = None) -> None:
    def markets(request: Request, csrf: str) -> Response:
        del request, csrf
        fields = "".join(
            f"<dt>{escape(k)}</dt><dd>{escape(v)}</dd>" for k, v in market_status(datetime.now(UTC))
        )
        body = (
            '<h1>Markets</h1><section class="card"><h2>NASDAQ HELSINKI</h2>'
            f'<dl>{fields}</dl></section><section class="card"><h2>US</h2>'
            '<p>ALPACA PAPER · USD</p><a href="/health">Read account and session status</a>'
            "</section><p>Live trading is unavailable.</p>"
        )
        return html_response(
            _layout(
                title="Markets",
                active="/today",
                body=body,
                capability_label="PAPER",
                kill_switch_engaged=False,
            )
        )

    router.get("/markets", markets)
    if reviews is None:
        return

    def review(request: Request, csrf: str) -> Response:
        del csrf
        assert reviews is not None
        try:
            fields = reviews.plan(request.first("plan"))
        except Exception:
            return html_response("Market evidence unavailable. No order was sent.", "409 Conflict")
        body = (
            "<h1>Exact Paper plan</h1><dl>"
            + "".join(f"<dt>{escape(k)}</dt><dd>{escape(v)}</dd>" for k, v in fields)
            + "</dl>"
        )
        body += (
            "<p>Owner approval authorizes only this exact immutable Paper entry and, after a "
            "confirmed fill, full SELL_TO_CLOSE of its attributable position on the first STOP, "
            "TARGET or MANDATORY EXIT. No second entry, changed terms, increased quantity, wider "
            "stop, changed target, shorting, overnight holding or Live trading is authorized.</p>"
            "<p>Expired evidence or changed terms require a new plan and new explicit approval. "
            "This read-only page does not approve or submit an order.</p>"
        )
        return html_response(
            _layout(
                title="Paper plan",
                active="/today",
                body=body,
                capability_label="PAPER",
                kill_switch_engaged=False,
            )
        )

    def history(request: Request, csrf: str) -> Response:
        del request, csrf
        assert reviews is not None
        try:
            rows = reviews.history()
        except Exception:
            return html_response("Market history unavailable.", "409 Conflict")
        body = "<h1>Market history</h1><p>Price P&amp;L is EUR, before fees.</p><table>"
        body += (
            "<tr><th>Plan</th><th>Broker</th><th>Market</th><th>Currency</th>"
            "<th>Status</th><th>Price P&amp;L</th></tr>"
        )
        body += "".join(
            "<tr>" + "".join(f"<td>{escape(v)}</td>" for v in row) + "</tr>" for row in rows
        )
        body += '</table><a href="/history">Alpaca history</a>'
        return html_response(
            _layout(
                title="Market history",
                active="/history",
                body=body,
                capability_label="PAPER",
                kill_switch_engaged=False,
            )
        )

    router.get("/markets/review", review)
    router.get("/markets/history", history)
