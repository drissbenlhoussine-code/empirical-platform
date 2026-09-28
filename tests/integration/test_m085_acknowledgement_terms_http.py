"""The REAL adapter refuses an acknowledgement that differs from the authorized order on ANY term.

Through real HTTP framing against a hostile local server. Every mismatch below is reported as
UNCERTAIN (`BrokerAmbiguousDispatchError`): the broker may hold an order, so a differing
acknowledgement is never an ordinary refusal and never an acceptance. Missing required fields
are refused, never substituted with the expected values.
"""

from __future__ import annotations

import pytest
from tests.integration.test_m085_hostile_http import (  # noqa: F401 - fixtures
    _json_response,
    _Script,
    an_order,
    an_order_payload,
    client,
    hostile,
)

from empirical_platform.shared.brokerage.alpaca_paper import (
    AlpacaPaperClient,
    BrokerAmbiguousDispatchError,
)

pytestmark = pytest.mark.integration


def test_an_exact_acknowledgement_is_accepted(
    client: AlpacaPaperClient,  # noqa: F811
    hostile: _Script,  # noqa: F811
) -> None:
    hostile.then(_json_response(200, an_order_payload()))
    status, view, _ = client.submit_order(an_order())
    assert status == 200
    assert view is not None
    assert (view.time_in_force, view.extended_hours, view.limit_price) == ("day", False, "4.00")


@pytest.mark.parametrize(
    "overrides",
    [
        {"limit_price": "5.00"},
        {"time_in_force": "gtc"},
        {"extended_hours": True},
        {"symbol": "TSLA"},
        {"qty": "2"},
        {"side": "sell"},
        {"type": "market"},
        {"client_order_id": "m085-someoneelse000000"},
    ],
)
def test_a_differing_acknowledgement_is_uncertain(
    client: AlpacaPaperClient,  # noqa: F811
    hostile: _Script,  # noqa: F811
    overrides: dict[str, object],
) -> None:
    hostile.then(_json_response(200, an_order_payload(**overrides)))
    with pytest.raises(BrokerAmbiguousDispatchError):
        client.submit_order(an_order())
    assert len(hostile.requests) == 1


@pytest.mark.parametrize(
    "missing", ["time_in_force", "extended_hours", "limit_price", "qty", "symbol"]
)
def test_a_missing_required_field_is_refused_not_substituted(
    client: AlpacaPaperClient,  # noqa: F811
    hostile: _Script,  # noqa: F811
    missing: str,
) -> None:
    payload = an_order_payload()
    del payload[missing]
    hostile.then(_json_response(200, payload))
    with pytest.raises(BrokerAmbiguousDispatchError):
        client.submit_order(an_order())


def test_a_looked_up_order_reports_every_term(
    client: AlpacaPaperClient,  # noqa: F811
    hostile: _Script,  # noqa: F811
) -> None:
    hostile.then(_json_response(200, an_order_payload(time_in_force="gtc", extended_hours=True)))
    status, view, _ = client.fetch_order_by_client_order_id("m085-abcdef0123456789")
    assert status == 200 and view is not None
    assert (view.time_in_force, view.extended_hours) == ("gtc", True)
