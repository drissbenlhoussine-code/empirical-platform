"""MILESTONE-090 -- base-path-aware URL generation for reverse-proxy subpath deployment.

A Tailscale (or any) reverse proxy serving this console under a prefix such as
`/m090-review` strips that prefix before the request reaches this process -- routing itself
is untouched. What broke on the real device: every URL this module GENERATES (the
stylesheet link, form actions, internal hrefs, the not-found redirect) is an ABSOLUTE path
the browser resolves against the PROXY's own origin, so it must carry the same prefix back,
or the next click escapes it (REVIEW TRADE landed on the SIMULATION console's own root).
These tests prove `base_path=""` is a no-op (root/localhost behaviour, unchanged) and
`base_path="/m090-review"` prefixes every generated URL, never doubles it, and that a
malformed base_path is refused at construction -- fail closed, never per-request.
"""

from __future__ import annotations

import io
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import cast

import pytest

from empirical_platform.decision_candidate.opportunity_engine import (
    QUALITY_MODEL_ID,
    QUALITY_MODEL_VERSION,
    STRUCTURE_MODEL_ID,
    STRUCTURE_MODEL_VERSION,
    MarketSessionState,
    OpportunityStatus,
    RejectionReason,
    TradingOpportunity,
)
from empirical_platform.entrypoints import _opportunity_engine_html as html
from empirical_platform.entrypoints._operator_console_web import SecuritySession
from empirical_platform.entrypoints.opportunity_engine_app import (
    build_opportunity_engine_application,
)

_NOW = datetime(2026, 6, 10, 14, 0, tzinfo=UTC)


def _actionable(opportunity_id: str = "OPP-1") -> TradingOpportunity:
    return TradingOpportunity(
        opportunity_id=opportunity_id,
        policy_fingerprint="a" * 64,
        symbol="AAPL",
        generated_at=_NOW,
        expires_at=_NOW + timedelta(minutes=5),
        evidence_as_of=_NOW,
        session=MarketSessionState.REGULAR_SESSION,
        bid=Decimal("101.00"),
        ask=Decimal("101.05"),
        spread_percent=Decimal("0.05"),
        entry_price=Decimal("101.50"),
        stop_price=Decimal("99.00"),
        target_price=Decimal("106.50"),
        risk_per_share=Decimal("2.50"),
        reward_per_share=Decimal("5.00"),
        reward_risk_ratio=Decimal("2.00"),
        quantity=19,
        notional=Decimal("1928.50"),
        maximum_loss=Decimal("47.50"),
        mandatory_liquidation_at=_NOW + timedelta(hours=2),
        structure_model_id=STRUCTURE_MODEL_ID,
        structure_model_version=STRUCTURE_MODEL_VERSION,
        evidence=("Breakout above the 5-bar range high (101.00)",),
        quality_score=Decimal("78.4"),
        quality_model_id=QUALITY_MODEL_ID,
        quality_model_version=QUALITY_MODEL_VERSION,
        rejection_reasons=(),
        status=OpportunityStatus.ACTIONABLE,
    )


def _rejected(opportunity_id: str = "OPP-2") -> TradingOpportunity:
    return replace(
        _actionable(opportunity_id),
        symbol="MSFT",
        entry_price=None,
        stop_price=None,
        target_price=None,
        risk_per_share=None,
        reward_per_share=None,
        reward_risk_ratio=None,
        quantity=None,
        notional=None,
        maximum_loss=None,
        mandatory_liquidation_at=None,
        quality_score=None,
        rejection_reasons=(RejectionReason.INSUFFICIENT_LIQUIDITY,),
        status=OpportunityStatus.REJECTED,
    )


def _invalidated(opportunity_id: str = "OPP-3") -> TradingOpportunity:
    return replace(
        _rejected(opportunity_id), rejection_reasons=(), status=OpportunityStatus.INVALIDATED
    )


# ---------------------------------------------------------------------------
# validate_base_path -- fail closed
# ---------------------------------------------------------------------------


def test_empty_base_path_is_valid_and_unchanged() -> None:
    assert html.validate_base_path("") == ""


def test_a_bare_absolute_path_prefix_is_valid_and_unchanged() -> None:
    assert html.validate_base_path("/m090-review") == "/m090-review"
    assert html.validate_base_path("/a/b-c_d.e") == "/a/b-c_d.e"


@pytest.mark.parametrize(
    "invalid",
    [
        "m090-review",  # no leading slash
        "/m090-review/",  # trailing slash
        "//m090-review",  # empty segment
        "/m090-review//x",  # empty segment mid-path
        "/../etc",  # traversal
        "/m090-review/..",  # traversal
        "http://evil.example/m090-review",  # a full URL, not a path prefix
        "//evil.example",  # protocol-relative -- would change origin
        "/m090 review",  # space
        "/m090-review\n",  # control character
        "/" + "x" * 200,  # too long
    ],
)
def test_invalid_base_paths_fail_closed(invalid: str) -> None:
    with pytest.raises(ValueError):
        html.validate_base_path(invalid)


# ---------------------------------------------------------------------------
# url_for -- the one place a prefix is ever applied
# ---------------------------------------------------------------------------


def test_url_for_with_empty_base_path_is_a_no_op() -> None:
    assert html.url_for("", "/today") == "/today"


def test_url_for_prefixes_exactly_once() -> None:
    assert html.url_for("/m090-review", "/today") == "/m090-review/today"


# ---------------------------------------------------------------------------
# today_page / review_page / confirmation pages -- requirements 1-4, 7
# ---------------------------------------------------------------------------

_CSRF = "test-csrf-token"


def _today_html(base_path: str) -> str:
    return html.today_page(
        actionable=(_actionable(),),
        candidates=(),
        rejected=(_rejected(),),
        other=(_invalidated(),),
        csrf=_CSRF,
        generated_at=_NOW,
        base_path=base_path,
    )


def test_root_base_path_keeps_existing_unprefixed_urls() -> None:
    page = _today_html("")
    assert 'href="/static/opportunity-engine.css"' in page
    assert 'action="/opportunity/review"' in page
    assert "/opportunity/review?id=OPP-3" in page
    assert "/m090-review" not in page


def test_configured_base_path_prefixes_every_generated_url_on_today() -> None:
    page = _today_html("/m090-review")
    assert 'href="/m090-review/static/opportunity-engine.css"' in page
    assert 'action="/m090-review/opportunity/review"' in page  # REVIEW TRADE
    assert "/m090-review/opportunity/review?id=OPP-3" in page  # history link
    # No unprefixed occurrence of a route path (every href/action carries the prefix).
    assert 'href="/static' not in page
    assert 'action="/opportunity' not in page


def test_no_double_prefix_on_today() -> None:
    page = _today_html("/m090-review")
    assert "/m090-review/m090-review" not in page


def test_review_page_approve_and_ignore_actions_carry_the_prefix() -> None:
    page = html.review_page(_actionable(), _CSRF, base_path="/m090-review")
    assert 'action="/m090-review/opportunity/approve"' in page
    assert 'action="/m090-review/opportunity/ignore"' in page
    assert 'href="/m090-review/today"' in page  # "Today" back link
    assert 'href="/m090-review/static/opportunity-engine.css"' in page
    assert "/m090-review/m090-review" not in page


def test_review_page_with_root_base_path_is_unchanged() -> None:
    page = html.review_page(_actionable(), _CSRF, base_path="")
    assert 'action="/opportunity/approve"' in page
    assert 'action="/opportunity/ignore"' in page
    assert 'href="/today"' in page


def test_confirmation_pages_carry_the_prefix() -> None:
    approved = html.approve_confirmation_page(_actionable(), base_path="/m090-review")
    ignored = html.ignore_confirmation_page(_actionable(), base_path="/m090-review")
    assert 'href="/m090-review/today"' in approved
    assert 'href="/m090-review/today"' in ignored


def test_message_page_back_link_carries_the_prefix() -> None:
    page = html.message_page(title="Not found", message="gone", base_path="/m090-review")
    assert 'href="/m090-review/today"' in page


# ---------------------------------------------------------------------------
# App-level: redirects, and the CSS route stays reachable post-proxy-strip
# ---------------------------------------------------------------------------


@dataclass
class _Reply:
    status: str
    headers: dict[str, str]
    body: str

    @property
    def code(self) -> int:
        return int(self.status.split()[0])


class _Client:
    """A minimal WSGI client -- the same shape as test_m086's own `Client`, kept local so
    this file has no cross-suite import dependency."""

    def __init__(self, app: object) -> None:
        self._app = app

    def get(self, path: str) -> _Reply:
        query = ""
        if "?" in path:
            path, query = path.split("?", 1)
        environ = {
            "REQUEST_METHOD": "GET",
            "PATH_INFO": path,
            "QUERY_STRING": query,
            "CONTENT_TYPE": "",
            "CONTENT_LENGTH": "0",
            "wsgi.input": io.BytesIO(b""),
            "SERVER_NAME": "127.0.0.1",
            "SERVER_PORT": "8091",
            "wsgi.url_scheme": "http",
        }
        captured: dict[str, object] = {}

        def start_response(status: str, headers: list[tuple[str, str]]) -> None:
            captured["status"] = status
            captured["headers"] = headers

        chunks = self._app(environ, start_response)  # type: ignore[operator]
        text = b"".join(chunks).decode("utf-8")
        raw_headers = cast("list[tuple[str, str]]", captured["headers"])
        headers = {name.lower(): value for name, value in raw_headers}
        return _Reply(str(captured["status"]), headers, text)


class _EmptyBackend:
    def today(self) -> tuple[TradingOpportunity, ...]:
        return ()

    def get(self, opportunity_id: str) -> TradingOpportunity | None:
        del opportunity_id
        return None

    def approve(self, opportunity_id: str, *, approved_by: str) -> TradingOpportunity:
        raise AssertionError("not exercised in these tests")

    def ignore(self, opportunity_id: str, *, ignored_by: str) -> TradingOpportunity:
        raise AssertionError("not exercised in these tests")

    def top_n(self) -> int:
        return 5


def test_not_found_redirect_preserves_the_configured_base_path() -> None:
    app = build_opportunity_engine_application(
        _EmptyBackend(), security=SecuritySession(), base_path="/m090-review"
    )
    reply = _Client(app).get("/some/unknown/path")
    assert reply.code == 303
    assert reply.headers["location"] == "/m090-review/today"


def test_not_found_redirect_with_root_base_path_is_unchanged() -> None:
    app = build_opportunity_engine_application(_EmptyBackend(), security=SecuritySession())
    reply = _Client(app).get("/some/unknown/path")
    assert reply.code == 303
    assert reply.headers["location"] == "/today"


def test_the_css_route_itself_stays_unprefixed_because_the_proxy_already_stripped_it() -> None:
    """Whatever base_path is configured, THIS process only ever registers unprefixed
    routes -- a reverse proxy strips the prefix before the request reaches here. Requesting
    the CSS at its real, unprefixed path must succeed regardless of base_path, proving the
    Tailscale-forwarded request (which arrives here already stripped) resolves."""
    app = build_opportunity_engine_application(
        _EmptyBackend(), security=SecuritySession(), base_path="/m090-review"
    )
    reply = _Client(app).get("/static/opportunity-engine.css")
    assert reply.code == 200
    assert "text/css" in reply.headers["content-type"]
    assert reply.body == html.STYLESHEET


def test_an_invalid_base_path_is_refused_at_construction_not_per_request() -> None:
    with pytest.raises(ValueError):
        build_opportunity_engine_application(
            _EmptyBackend(), security=SecuritySession(), base_path="not-absolute"
        )


# ---------------------------------------------------------------------------
# Query parameters stay escaped when prefixed (no injection via an opportunity id)
# ---------------------------------------------------------------------------


def test_the_history_link_query_parameter_is_url_encoded() -> None:
    mischievous = _invalidated('OPP-3"><script>alert(1)</script>')
    page = html.today_page(
        actionable=(),
        candidates=(),
        rejected=(),
        other=(mischievous,),
        csrf=_CSRF,
        generated_at=_NOW,
        base_path="/m090-review",
    )
    assert "<script>" not in page
    assert "%3Cscript%3E" in page
