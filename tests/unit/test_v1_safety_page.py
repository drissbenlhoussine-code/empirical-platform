"""RELEASE v1 -- the Safety page carries exactly the mission's required statements, over
the real router (not just a unit call on the renderer), reusing the SAME `Client`/`Backend`
test harness `test_m086_operator_console_routes.py` already proves against the real routes.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from tests.unit._m086_fakes import World, simulation_world
from tests.unit.test_m086_operator_console_routes import Backend, Client

from empirical_platform.entrypoints._operator_console_web import SecuritySession
from empirical_platform.entrypoints.operator_console_app import build_application


@pytest.fixture
def world(tmp_path: Path) -> World:
    return simulation_world(tmp_path)


@pytest.fixture
def client(world: World) -> Client:
    return Client(build_application(Backend(world), security=SecuritySession()))  # type: ignore[arg-type]


def test_the_safety_page_carries_every_required_v1_statement(client: Client) -> None:
    body = client.get("/safety").body
    for required in (
        "Environment: <strong>PAPER</strong>",
        "Live: <strong>UNAVAILABLE</strong>",
        "Strategy profitability: <strong>NOT VALIDATED</strong>",
        "POSITION-REDUCING ONLY, AFTER THE OWNER APPROVES A FULL PLAN",
        "automatic new opportunities becoming orders",
        "autonomous entry without Owner approval",
        "shorting",
        "leverage escalation",
        "overnight intention",
    ):
        assert required in body, required
