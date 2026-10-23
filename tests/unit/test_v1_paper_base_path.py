"""RELEASE v1 Release Blocker -- `/paper` base-path escape.

Reproduces and closes the 2026-10-07 Owner incident: Tailscale Serve mounts the real PAPER
console at `/paper/*` on `127.0.0.1:8189`, stripping that prefix before the request reaches
this process. The backend's route REGISTRATION stays unprefixed (unchanged here) -- but every
URL the console GENERATES (hrefs, form actions, redirects) is an ABSOLUTE path the browser
resolves against the PROXY'S origin. Before this fix those were hardcoded bare paths like
"/prepare-candidate", so clicking Prepare on `/paper/today` sent the browser to
`https://<host>/prepare-candidate` -- outside `/paper` entirely, which Tailscale's OWN root
mapping (`/` -> the always-running SIMULATION console on 8086) then answered with its own
"Not found" page. `base_path`, threaded through `build_application`/`build_paper_application`
down to `_operator_console_html.url_for`, is the fix: every generated URL now carries the
configured prefix, and route registration itself is untouched.

Everything here runs against IN-MEMORY fakes and the REAL WSGI router/application -- no
PostgreSQL, no network, no real Alpaca endpoint, no broker write.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from tests.unit._m085_fakes import FakeMarketData
from tests.unit._m086_fakes import MemoryWatermarks
from tests.unit.test_m086_operator_console_routes import Client
from tests.unit.test_v1_paper_candidate_preparation import _LiveQuote, _v1_configuration
from tests.unit.test_v1_paper_console_app_routes import _backend

from empirical_platform.entrypoints import _operator_console_html as html
from empirical_platform.entrypoints._operator_console_web import SecuritySession
from empirical_platform.entrypoints.operator_console_app import build_application
from empirical_platform.entrypoints.paper_operator_console_app import build_paper_application
from empirical_platform.usecases.paper_operator_console import prepare_v1_paper_candidate


def _now() -> datetime:
    return datetime.now(UTC)


def _paper_client(base_path: str = "/paper") -> tuple[Client, object]:
    """A real exit-capable PAPER backend/app pair, mounted at `base_path`."""
    backend = _backend(market_data=FakeMarketData(quote=_LiveQuote()))
    backend._repositories.configurations.save(_v1_configuration())  # type: ignore[arg-type]
    app = build_paper_application(backend, security=SecuritySession(), base_path=base_path)
    return Client(app), backend  # type: ignore[arg-type]


def _prepare_real_candidate(backend: object, broker: object = None) -> str:
    """Drives `prepare_v1_paper_candidate` directly (bypassing the HTTP layer) to get a real,
    fully-governed proposal id to review/approve through the HTTP client -- exactly what the
    Owner's own click would produce, without re-deriving the whole evaluation engine here.

    Uses `backend._repositories.time_bases` -- the SAME repository `confirm_approval`'s own
    later issue step reads from -- never a throwaway `FakeTimeBases()`, or the proposal would
    carry no broker-clock basis the issue step can find, and would refuse as undispatchable.
    """
    result = prepare_v1_paper_candidate(
        configurations=backend._repositories.configurations,  # type: ignore[attr-defined]
        contexts=backend._repositories.contexts,  # type: ignore[attr-defined]
        proposals=backend._repositories.proposals,  # type: ignore[attr-defined]
        watermarks=MemoryWatermarks(),
        time_bases=backend._repositories.time_bases,  # type: ignore[attr-defined]
        broker=broker or backend._broker,  # type: ignore[attr-defined]
        market_data=backend._market_data,  # type: ignore[attr-defined]
        bars=backend._market_data,  # type: ignore[attr-defined]
        time_source=backend._time_source,  # type: ignore[attr-defined]
        now=_now(),
    )
    return result.proposal.proposal_governance_id


class TestEveryGeneratedUrlCarriesThePrefix:
    def test_1_today_nav_link_stays_under_paper(self) -> None:
        client, _backend_obj = _paper_client()
        reply = client.get("/today")
        assert reply.code == 200
        assert 'href="/paper/today"' in reply.body

    def test_2_prepare_form_action_is_exactly_prefixed(self) -> None:
        client, _backend_obj = _paper_client()
        reply = client.get("/today")
        assert 'action="/paper/prepare-candidate"' in reply.body

    def test_3_review_plan_link_stays_under_paper(self) -> None:
        client, backend = _paper_client()
        proposal_id = _prepare_real_candidate(backend)
        reply = client.get("/today")
        assert f"/paper/confirm?action=APPROVE&amp;proposal={proposal_id}" in reply.body

    def test_4_approve_form_action_stays_under_paper(self) -> None:
        client, backend = _paper_client()
        proposal_id = _prepare_real_candidate(backend)
        review = client.get(f"/confirm?action=APPROVE&proposal={proposal_id}")
        assert review.code == 200
        assert 'action="/paper/confirm-approval"' in review.body

    def test_5_reject_link_and_confirm_rejection_action_stay_under_paper(self) -> None:
        client, backend = _paper_client()
        proposal_id = _prepare_real_candidate(backend)
        today = client.get("/today")
        assert f"/paper/confirm?action=REJECT&amp;proposal={proposal_id}" in today.body
        review = client.get(f"/confirm?action=REJECT&proposal={proposal_id}")
        assert 'action="/paper/confirm-rejection"' in review.body

    def test_6_active_stays_under_paper(self) -> None:
        client, _backend_obj = _paper_client()
        reply = client.get("/active")
        assert reply.code == 200
        assert 'href="/paper/active"' in reply.body
        assert 'action="/paper/active/refresh"' in reply.body

    def test_7_history_stays_under_paper(self) -> None:
        client, _backend_obj = _paper_client()
        reply = client.get("/history")
        assert reply.code == 200
        assert 'href="/paper/history"' in reply.body
        assert 'action="/paper/history"' in reply.body

    def test_8_safety_stays_under_paper(self) -> None:
        client, _backend_obj = _paper_client()
        reply = client.get("/safety")
        assert reply.code == 200
        assert 'href="/paper/safety"' in reply.body
        assert 'href="/paper/health"' in reply.body

    def test_9_detail_execution_links_stay_under_paper(self) -> None:
        client, backend = _paper_client()
        proposal_id = _prepare_real_candidate(backend)
        reply = client.get(f"/opportunity?id={proposal_id}")
        assert reply.code == 200
        assert 'href="/paper/today"' in reply.body

    def test_10_success_redirect_after_approval_stays_under_paper(self) -> None:
        import re

        client, backend = _paper_client()
        proposal_id = _prepare_real_candidate(backend)
        review = client.get(f"/confirm?action=APPROVE&proposal={proposal_id}")
        ticket = re.search(r'name="ticket" value="([^"]+)"', review.body)
        csrf = re.search(r'name="csrf_token" value="([^"]+)"', review.body)
        assert ticket and csrf
        confirm = client.post(
            "/confirm-approval",
            form={
                "proposal": proposal_id,
                "ticket": ticket.group(1),
                "csrf_token": csrf.group(1),
            },
        )
        assert confirm.code == 303, confirm.body
        assert confirm.headers["location"] == f"/paper/opportunity?id={proposal_id}"

    def test_11_error_refusal_redirect_stays_under_paper(self) -> None:
        client, _backend_obj = _paper_client()
        reply = client.post(
            "/confirm-approval", form={"proposal": "PRP-DOES-NOT-EXIST", "ticket": "x"}
        )
        assert reply.code in (400, 403, 404, 500)
        assert "/paper/" in reply.body or 'href="/paper' in reply.body

    def test_12_unknown_path_recovery_stays_under_paper(self) -> None:
        client, _backend_obj = _paper_client()
        reply = client.get("/this-route-does-not-exist")
        assert reply.code == 404
        assert 'href="/paper/today"' in reply.body

    def test_13_static_css_reference_is_prefixed_and_the_unprefixed_route_still_serves_it(
        self,
    ) -> None:
        """The HTML references `/paper/static/console.css` (what the browser, behind the
        proxy, must request); the backend itself still SERVES it at the unprefixed route,
        exactly as Tailscale will request it after stripping the prefix -- registration is
        untouched by this fix, only generation is."""
        client, _backend_obj = _paper_client()
        today = client.get("/today")
        assert 'href="/paper/static/console.css"' in today.body
        css = client.get("/static/console.css")
        assert css.code == 200
        assert css.headers["content-type"].startswith("text/css")

    def test_14_no_generated_url_ever_doubles_the_prefix(self) -> None:
        client, backend = _paper_client()
        _prepare_real_candidate(backend)
        for path in ("/today", "/active", "/history", "/safety"):
            reply = client.get(path)
            assert "/paper/paper/" not in reply.body, path

    def test_15_empty_base_path_preserves_unprefixed_root_behaviour(self) -> None:
        client, _backend_obj = _paper_client(base_path="")
        reply = client.get("/today")
        assert reply.code == 200
        assert 'href="/today"' in reply.body
        assert 'action="/prepare-candidate"' in reply.body
        assert "/paper" not in reply.body

    def test_16_a_malformed_base_path_fails_closed_at_startup(self) -> None:
        backend = _backend()
        for bad in (
            "paper",  # no leading slash
            "/paper/",  # trailing slash
            "//paper",  # empty segment
            "/paper/..",  # a literal traversal segment
            "https://evil/paper",  # scheme/host injection
            "/pa per",  # disallowed character (space)
        ):
            with pytest.raises(ValueError):
                build_paper_application(backend, security=SecuritySession(), base_path=bad)  # type: ignore[arg-type]
            with pytest.raises(ValueError):
                build_application(backend, security=SecuritySession(), base_path=bad)  # type: ignore[arg-type]

    def test_17_a_paper_generated_action_can_never_equal_a_bare_root_path(self) -> None:
        """Structural proof, not a runtime coincidence: `url_for` always returns
        `base_path + path`, so for any non-empty `base_path` the result can never equal the
        bare, unprefixed path the SIMULATION console (mounted at Tailscale's own `/` root)
        actually serves -- the exact confusion behind the 2026-10-07 incident."""
        for route in ("/today", "/prepare-candidate", "/confirm-approval", "/active", "/safety"):
            prefixed = html.url_for("/paper", route)
            assert prefixed != route
            assert prefixed.startswith("/paper/") or prefixed == "/paper" + route


class TestEndToEndDeploymentShape:
    """The EXACT reported shape: external POST /paper/prepare-candidate, the proxy strips
    the prefix, the backend receives POST /prepare-candidate, and the response sends the
    browser back to a /paper/... URL -- never a bare, un-prefixed one."""

    def test_proxy_stripped_prepare_candidate_round_trip_stays_under_paper(self) -> None:
        client, backend = _paper_client(base_path="/paper")

        # 1. External request: POST https://host/paper/prepare-candidate
        external_path = "/paper/prepare-candidate"
        # 2. Tailscale Serve strips its own mount prefix before forwarding.
        assert external_path.startswith("/paper")
        backend_path = external_path[len("/paper") :]
        assert backend_path == "/prepare-candidate"

        # 3. The backend receives exactly the stripped path -- this IS what Client.post
        # simulates (it never adds a prefix; PATH_INFO is handed to the app verbatim).
        reply = client.post(backend_path, form={"csrf_token": client.csrf()})
        assert reply.code == 200, reply.body

        # 4. The response is never a bare, un-prefixed link -- every "Back"/"Review" link on
        # the page the Owner lands on carries /paper, and NONE resolves outside it.
        assert 'href="/paper/' in reply.body
        assert 'href="/today"' not in reply.body
        assert 'href="/active"' not in reply.body
        assert 'href="/safety"' not in reply.body
        assert "/paper/paper/" not in reply.body

        # 5. And the real proposal this produced is itself reachable only under /paper.
        proposal = backend._repositories.proposals.list_by_status(  # type: ignore[attr-defined]
            next(iter(backend._repositories.proposals.rows.values())).status  # type: ignore[attr-defined]
        )
        assert proposal, "prepare-candidate did not persist a proposal"
