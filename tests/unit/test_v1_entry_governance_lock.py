"""RELEASE v1 -- Release Blocker 3's governance regression lock.

CONTEXT. A real M089 Paper acceptance run found a governance failure: an approved entry
proposal expired, a new one was regenerated at different terms, and it was dispatched
WITHOUT a fresh Owner approval. The platform itself did not cause this -- the entry
pipeline's own fingerprint/expiry checks (`SubmitAuthorizedPaperOrderHandler`,
`AuthorizePaperSubmissionHandler`) already refuse a submission whose terms changed or
whose approval expired; this was an operator-process failure, not a code defect (see the
session's own M089 evidence). This file exists so that claim is not just asserted in a
commit message: it is independently re-proven here, at the current v1 head, as its own
dedicated, explicitly-labeled test -- not inferred from the pre-existing M085/M086 tests
that happen to cover the same mechanism (`test_m085_paper_execution_handlers.py`'s
`test_an_expired_authorization_refuses_the_dispatch` /
`test_a_mismatched_fingerprint_is_refused`;
`test_m086_operator_console_service.py`'s `test_a_proposal_that_expires_while_the_page_is_
open_is_refused` / `test_a_stale_tab_with_an_older_proposal_version_is_refused`).

Over the REAL simulation broker and the REAL M084/M085 handler chain -- not a fake.
"""

from __future__ import annotations

import copy
from dataclasses import replace
from pathlib import Path

import pytest
from tests.unit._m086_fakes import World, simulation_world

from empirical_platform.usecases.operator_console import ConsoleRefusalError


@pytest.fixture
def world(tmp_path: Path) -> World:
    return simulation_world(tmp_path)


def test_b_an_expired_approval_cannot_submit(world: World) -> None:
    world.load_day(("AAPL",))
    proposal_id = world.proposal_id("AAPL")
    view = world.service.prepare_approval(proposal_id)

    world.clock.advance(3601)  # past the configured proposal expiry

    with pytest.raises(ConsoleRefusalError):
        world.service.confirm_approval(proposal_id, view.ticket)
    assert world.repositories.decisions.for_proposal(proposal_id) is None
    assert world.broker.store.orders() == ()


def test_c_changed_entry_terms_require_a_new_approval(world: World) -> None:
    """The exact shape of the real M089 incident: a proposal regenerated at DIFFERENT
    terms (a new price) must never be dispatched against an approval ticket issued for the
    OLD terms. The fingerprint is bound to the exact reviewed terms; a mismatch refuses."""
    world.load_day(("AAPL",))
    proposal_id = world.proposal_id("AAPL")
    view = world.service.prepare_approval(proposal_id)

    current = world.repositories.proposals.get(proposal_id)
    assert current is not None
    from empirical_platform.decision_candidate.trade_proposal import compute_fingerprint

    # A genuinely regenerated proposal at a DIFFERENT limit price (the real M089 scenario:
    # $332.85 approved, $338.31 actually dispatched) -- same proposal id, new terms.
    regenerated = copy.copy(current)
    object.__setattr__(regenerated, "proposal_version", current.proposal_version + 1)
    object.__setattr__(regenerated, "limit_price", current.limit_price + 5)
    regenerated = replace(regenerated, content_fingerprint=compute_fingerprint(regenerated))
    world.repositories.proposals.rows[proposal_id] = regenerated  # type: ignore[attr-defined]

    with pytest.raises(ConsoleRefusalError):
        world.service.confirm_approval(proposal_id, view.ticket)
    assert world.repositories.decisions.for_proposal(proposal_id) is None
    assert world.broker.store.orders() == ()
