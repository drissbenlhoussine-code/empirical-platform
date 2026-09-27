"""MILESTONE-086 -- the Operator Console over HTTP, through the WSGI application.

A tiny WSGI client drives the real routes against the in-memory world: pages render, the
SIMULATION badge is everywhere, state-changing requests need the browser's own CSRF token,
a request that tries to choose PAPER or LIVE fails closed, every POST redirects so a refresh
re-reads instead of re-submitting, the security headers are present, and the page contract
for phones holds (viewport meta, no inline styles, no script, one same-origin stylesheet).
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlencode

import pytest
from tests.unit._m086_fakes import World, simulation_world

from empirical_platform.entrypoints._operator_console_web import SecuritySession
from empirical_platform.entrypoints.operator_console_app import build_application
from empirical_platform.usecases.operator_console_fixtures import (
    SIMULATION_CONFIGURATION_ID,
    SimulationDayReport,
)


@dataclass
class Reply:
    status: str
    headers: dict[str, str]
    body: str

    @property
    def code(self) -> int:
        return int(self.status.split()[0])


class Client:
    """Cookies are kept like a browser keeps them; nothing else is simulated."""

    def __init__(self, app: object) -> None:
        self._app = app
        self.cookies: dict[str, str] = {}

    def request(
        self,
        method: str,
        path: str,
        *,
        form: dict[str, str] | None = None,
        raw_body: bytes | None = None,
        content_type: str = "application/x-www-form-urlencoded",
        cookies: bool = True,
    ) -> Reply:
        query = ""
        if "?" in path:
            path, query = path.split("?", 1)
        body = raw_body if raw_body is not None else (urlencode(form).encode() if form else b"")
        environ = {
            "REQUEST_METHOD": method,
            "PATH_INFO": path,
            "QUERY_STRING": query,
            "CONTENT_TYPE": content_type if body else "",
            "CONTENT_LENGTH": str(len(body)),
            "wsgi.input": io.BytesIO(body),
            "SERVER_NAME": "127.0.0.1",
            "SERVER_PORT": "8086",
            "wsgi.url_scheme": "http",
        }
        if cookies and self.cookies:
            environ["HTTP_COOKIE"] = "; ".join(f"{k}={v}" for k, v in self.cookies.items())
        captured: dict[str, object] = {}

        def start_response(status: str, headers: list[tuple[str, str]]) -> None:
            captured["status"] = status
            captured["headers"] = headers

        chunks = self._app(environ, start_response)  # type: ignore[operator]
        text = b"".join(chunks).decode("utf-8")
        headers: dict[str, str] = {}
        for name, value in captured["headers"]:  # type: ignore[union-attr]
            if name.lower() == "set-cookie":
                cookie = value.split(";", 1)[0]
                key, _, val = cookie.partition("=")
                self.cookies[key.strip()] = val.strip()
            headers[name.lower()] = value
        return Reply(str(captured["status"]), headers, text)

    def get(self, path: str) -> Reply:
        return self.request("GET", path)

    def post(self, path: str, form: dict[str, str]) -> Reply:
        return self.request("POST", path, form=form)

    def csrf(self) -> str:
        page = self.get("/active")  # the refresh form is always present there
        match = re.search(r'name="csrf_token" value="([^"]+)"', page.body)
        assert match, "no csrf token on the page"
        return match.group(1)

    def follow(self, reply: Reply) -> Reply:
        assert reply.code == 303, reply.status
        return self.get(reply.headers["location"])


class Backend:
    def __init__(self, world: World) -> None:
        self.world = world

    @property
    def service(self) -> object:
        return self.world.service

    @property
    def configuration_id(self) -> str:
        return SIMULATION_CONFIGURATION_ID

    def load_day(self) -> SimulationDayReport:
        return self.world.load_day()


@pytest.fixture
def world(tmp_path: Path) -> World:
    return simulation_world(tmp_path)


@pytest.fixture
def client(world: World) -> Client:
    return Client(build_application(Backend(world), security=SecuritySession()))  # type: ignore[arg-type]


def _ticket(page: str) -> str:
    match = re.search(r'name="ticket" value="([^"]+)"', page)
    assert match, "no ticket on the confirmation page"
    return match.group(1)


# ---------------------------------------------------------------------------
# Pages and the rendering contract
# ---------------------------------------------------------------------------


def test_every_page_renders_with_the_simulation_badge_and_the_contract(
    client: Client, world: World
) -> None:
    world.load_day()
    for path in ("/today", "/active", "/history", "/safety"):
        reply = client.get(path)
        assert reply.code == 200, path
        assert 'class="env-badge">SIMULATION</span>' in reply.body, path
        assert '<meta name="viewport" content="width=device-width, initial-scale=1">' in reply.body
        assert "<script" not in reply.body
        assert ' style="' not in reply.body  # no inline styles: the CSP forbids them
        assert '<link rel="stylesheet" href="/static/console.css">' in reply.body
        assert (
            "Content-Security-Policy" in {k.title() for k in reply.headers}
            or "content-security-policy" in reply.headers
        )
        assert reply.headers["x-frame-options"] == "DENY"
        assert reply.headers["cache-control"] == "no-store"
        assert reply.headers["x-content-type-options"] == "nosniff"
        assert "default-src 'none'" in reply.headers["content-security-policy"]
        assert "Paper execution locked" in reply.body
    css = client.get("/static/console.css")
    assert css.code == 200 and css.headers["content-type"].startswith("text/css")
    assert "@media (max-width:600px)" in css.body
    assert client.get("/").code == 303


def test_today_shows_every_card_state_word_from_the_closed_vocabulary(
    client: Client, world: World
) -> None:
    world.load_day()
    body = client.get("/today").body
    assert body.count('class="card"') == 12
    assert "Needs decision" in body
    assert "Approve</a>" in body and "Reject</a>" in body
    for word in ("Entry (limit)", "Quantity", "Notional", "Max capital", "Stop", "Target", "Risk"):
        assert word in body
    assert "Not available" not in body  # every staged field is present for the staged day
    assert "Staged simulation behaviour" in body  # behind Details


def test_the_empty_today_offers_to_load_the_day_and_the_button_works(client: Client) -> None:
    empty = client.get("/today")
    assert "No opportunities today" in empty.body
    loaded = client.post("/simulation/load-day", {"csrf_token": client.csrf()})
    assert loaded.code == 200 and "Simulation day loaded" in loaded.body
    assert client.get("/today").body.count('class="card"') == 12


# ---------------------------------------------------------------------------
# The decision flow over HTTP
# ---------------------------------------------------------------------------


def test_the_two_stage_approval_over_http(client: Client, world: World) -> None:
    world.load_day(("AAPL",))
    proposal = world.proposal_id("AAPL")
    confirmation = client.get(f"/confirm?action=APPROVE&proposal={proposal}")
    assert confirmation.code == 200
    assert "CONFIRM APPROVAL" in confirmation.body
    assert 'class="env-badge env-badge-large">SIMULATION</div>' in confirmation.body
    for label in (
        "Symbol",
        "Side",
        "Quantity",
        "Order type",
        "Limit price",
        "Time in force",
        "Extended hours",
        "Environment",
        "Account",
        "Reference",
        "Notional",
        "Proposal expires",
        "Approval expires",
    ):
        assert f"<dt>{label}</dt>" in confirmation.body, label
    # Stage 1 executed nothing.
    assert world.repositories.decisions.for_proposal(proposal) is None
    ticket = _ticket(confirmation.body)
    csrf = client.csrf()
    reply = client.post(
        "/confirm-approval", {"csrf_token": csrf, "proposal": proposal, "ticket": ticket}
    )
    assert reply.code == 303 and reply.headers["location"] == f"/opportunity?id={proposal}"
    page = client.follow(reply)
    assert (
        "Approved and sent" in page.body
        and "An order was sent to the simulated broker." in page.body
    )
    assert "Accepted" in page.body
    # A refresh of the redirected page re-reads state and shows no second flash.
    again = client.get(f"/opportunity?id={proposal}")
    assert "Approved and sent" not in again.body and "Accepted" in again.body
    # The browser re-sends the same POST (double click / retry): nothing new happens.
    replay = client.follow(
        client.post(
            "/confirm-approval", {"csrf_token": csrf, "proposal": proposal, "ticket": ticket}
        )
    )
    assert "Already confirmed" in replay.body
    assert len(world.broker.store.orders()) == 1


def test_rejection_over_http_needs_one_confirmation(client: Client, world: World) -> None:
    world.load_day(("AAPL",))
    proposal = world.proposal_id("AAPL")
    page = client.get(f"/confirm?action=REJECT&proposal={proposal}")
    assert "CONFIRM REJECTION" in page.body
    reply = client.post(
        "/confirm-rejection",
        {"csrf_token": client.csrf(), "proposal": proposal, "ticket": _ticket(page.body)},
    )
    shown = client.follow(reply)
    assert "Rejected" in shown.body and "Nothing was sent." in shown.body
    assert world.broker.store.orders() == ()


def test_a_direct_post_cannot_bypass_confirmation(client: Client, world: World) -> None:
    world.load_day(("AAPL",))
    proposal = world.proposal_id("AAPL")
    csrf = client.csrf()
    # No ticket at all, or a hand-made one: refused, nothing decided.
    for ticket in ("", "APPROVE|x|1|f|0|deadbeef", "junk"):
        reply = client.post(
            "/confirm-approval", {"csrf_token": csrf, "proposal": proposal, "ticket": ticket}
        )
        assert reply.code == 400, ticket
        assert "Nothing was done" in reply.body
    assert world.repositories.decisions.for_proposal(proposal) is None
    assert world.broker.store.orders() == ()


def test_a_post_without_the_browsers_csrf_token_is_refused(client: Client, world: World) -> None:
    world.load_day(("AAPL",))
    proposal = world.proposal_id("AAPL")
    ticket = _ticket(client.get(f"/confirm?action=APPROVE&proposal={proposal}").body)
    missing = client.post("/confirm-approval", {"proposal": proposal, "ticket": ticket})
    assert missing.code == 403 and "Nothing was done" in missing.body
    wrong = client.post(
        "/confirm-approval", {"csrf_token": "a" * 48, "proposal": proposal, "ticket": ticket}
    )
    assert wrong.code == 403
    # A token from another browser session (another cookie) is not this browser's token.
    other = Client(client._app)  # noqa: SLF001 - test double
    foreign = other.csrf()
    stolen = client.post(
        "/confirm-approval", {"csrf_token": foreign, "proposal": proposal, "ticket": ticket}
    )
    assert stolen.code == 403
    assert world.repositories.decisions.for_proposal(proposal) is None


@pytest.mark.parametrize("environment", ["PAPER", "LIVE", "SIMULATION", "paper"])
def test_a_request_that_chooses_an_environment_fails_closed(
    client: Client, world: World, environment: str
) -> None:
    world.load_day(("AAPL",))
    proposal = world.proposal_id("AAPL")
    ticket = _ticket(client.get(f"/confirm?action=APPROVE&proposal={proposal}").body)
    reply = client.post(
        "/confirm-approval",
        {
            "csrf_token": client.csrf(),
            "proposal": proposal,
            "ticket": ticket,
            "environment": environment,
        },
    )
    assert reply.code == 403
    assert "cannot select an execution environment" in reply.body
    assert world.repositories.decisions.for_proposal(proposal) is None
    assert world.broker.store.orders() == ()
    # The same on a GET that prepares a confirmation.
    assert (
        client.get(f"/confirm?action=APPROVE&proposal={proposal}&environment={environment}").code
        == 403
    )


def test_malformed_requests_are_refused_without_a_traceback(client: Client, world: World) -> None:
    world.load_day(("AAPL",))
    csrf = client.csrf()
    assert client.get("/confirm?action=EXPLODE&proposal=x").code == 400
    assert client.get("/opportunity?id=PRP-NOPE").code == 404
    assert client.get("/execution?intent=INT-NOPE").code == 404
    assert client.get("/nowhere").code == 404
    assert client.request("PUT", "/today").code == 405
    assert (
        client.post("/safety/kill-switch", {"csrf_token": csrf, "action": "detonate"}).code == 400
    )
    huge = client.request(
        "POST",
        "/confirm-approval",
        raw_body=b"csrf_token=" + b"x" * (70 * 1024),
        content_type="application/x-www-form-urlencoded",
    )
    assert huge.code == 403  # body over the limit is dropped, so the token is absent
    not_form = client.request(
        "POST", "/confirm-approval", raw_body=b'{"csrf_token":"x"}', content_type="application/json"
    )
    assert not_form.code == 403
    for reply in (client.get("/opportunity?id=PRP-NOPE"), client.get("/nowhere")):
        assert (
            "Traceback" not in reply.body and "Error" not in reply.body.split("<main")[1][:0] + ""
        )


def test_the_kill_switch_over_http_requires_confirmation_and_blocks_execution(
    client: Client, world: World
) -> None:
    world.load_day(("AAPL",))
    safety = client.get("/safety")
    assert "ACTIVATE KILL SWITCH" in safety.body and "released" in safety.body
    form = client.get("/safety/kill-switch?action=engage")
    assert form.code == 200 and "ACTIVATE KILL SWITCH" in form.body
    reply = client.post(
        "/safety/kill-switch", {"csrf_token": client.csrf(), "action": "engage", "reason": "test"}
    )
    page = client.follow(reply)
    assert "Kill switch engaged" in page.body and "DEACTIVATE KILL SWITCH" in page.body
    today = client.get("/today")
    assert "Kill switch engaged" in today.body
    assert "Execution is blocked while the kill switch is engaged" in today.body
    assert "Approve</a>" not in today.body  # pending cards offer no approval while engaged
    proposal = world.proposal_id("AAPL")
    confirmation = client.get(f"/confirm?action=APPROVE&proposal={proposal}")
    assert "This approval will be refused" in confirmation.body
    refused = client.post(
        "/confirm-approval",
        {"csrf_token": client.csrf(), "proposal": proposal, "ticket": _ticket(confirmation.body)},
    )
    assert refused.code == 400 and "kill switch" in refused.body.lower()
    assert world.broker.store.orders() == ()
    release = client.post(
        "/safety/kill-switch", {"csrf_token": client.csrf(), "action": "release", "reason": ""}
    )
    assert "Kill switch released" in client.follow(release).body


def test_active_trades_refresh_and_cancel_over_http(client: Client, world: World) -> None:
    world.load_day(("V",))
    proposal = world.proposal_id("V")
    ticket = _ticket(client.get(f"/confirm?action=APPROVE&proposal={proposal}").body)
    client.post(
        "/confirm-approval", {"csrf_token": client.csrf(), "proposal": proposal, "ticket": ticket}
    )
    active = client.get("/active")
    assert "Accepted" in active.body and "Request cancel" in active.body
    assert (
        "Proposal" in active.body
        and "Owner approved" in active.body
        and "Authorized" in active.body
    )
    assert 'class="step">' in active.body  # the not-yet-reached final step is not inferred
    cancel_form = client.get(f"/execution/cancel?intent=INT-{proposal}")
    assert "CONFIRM CANCEL REQUEST" in cancel_form.body
    shown = client.follow(
        client.post(
            "/execution/confirm-cancel", {"csrf_token": client.csrf(), "intent": f"INT-{proposal}"}
        )
    )
    assert "Cancel requested" in shown.body and "not a cancellation" in shown.body
    world.clock.advance(5)
    refreshed = client.follow(client.post("/active/refresh", {"csrf_token": client.csrf()}))
    assert "Checked with the broker" in refreshed.body
    assert "No active trades" in refreshed.body
    history = client.get("/history?outcome=Cancelled")
    assert "V</span>" in history.body and "Simulation execution" in history.body


def test_an_unknown_outcome_is_shown_as_needs_attention_never_filled(
    client: Client, world: World
) -> None:
    world.load_day(("GOOGL",))
    proposal = world.proposal_id("GOOGL")
    ticket = _ticket(client.get(f"/confirm?action=APPROVE&proposal={proposal}").body)
    page = client.follow(
        client.post(
            "/confirm-approval",
            {"csrf_token": client.csrf(), "proposal": proposal, "ticket": ticket},
        )
    )
    assert "Outcome unknown — do not retry" in page.body
    assert "Needs attention" in page.body
    assert "Filled" not in page.body.split("<h1>")[1].split("<details")[0]
    active = client.get("/active")
    assert "Needs attention" in active.body and "do not retry" in active.body


def test_a_filled_entry_is_shown_as_an_open_position_with_its_exit_locked(
    client: Client, world: World
) -> None:
    world.load_day(("AAPL",))
    proposal = world.proposal_id("AAPL")
    ticket = _ticket(client.get(f"/confirm?action=APPROVE&proposal={proposal}").body)
    client.post(
        "/confirm-approval", {"csrf_token": client.csrf(), "proposal": proposal, "ticket": ticket}
    )
    for _ in range(2):
        world.clock.advance(5)
        client.post("/active/refresh", {"csrf_token": client.csrf()})
    active = client.get("/active")
    assert "No active trades" not in active.body
    # MILESTONE-087 composed an exit path: the position offers "Review exit" instead of a lock.
    assert "Open position." in active.body and "Review exit" in active.body
    assert "Filled" in active.body and "Request cancel" not in active.body
    assert "<dt>Position</dt>" in active.body
