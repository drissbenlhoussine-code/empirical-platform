"""RELEASE v1 -- the console's own HTML source must never claim a Research Candidate is a
recommendation, the best trade, or a profitable one. A grep over the WHOLE module (not
just the card renderer) so a future addition elsewhere cannot slip the word in unnoticed.
"""

from __future__ import annotations

from pathlib import Path

_HTML_MODULE = Path("src/empirical_platform/entrypoints/_operator_console_html.py")

_FORBIDDEN_WORDS = ("recommended", "best trade", "profitable", "guaranteed")


def test_the_console_html_source_never_claims_a_candidate_is_recommended_or_profitable() -> None:
    source = _HTML_MODULE.read_text(encoding="utf-8").lower()
    for word in _FORBIDDEN_WORDS:
        assert word not in source, word


def test_the_research_candidate_banner_text_is_exact() -> None:
    source = _HTML_MODULE.read_text(encoding="utf-8")
    assert "Research strategy — profitability has not been validated." in source


def test_every_research_candidate_card_carries_the_banner_and_badge(tmp_path: Path) -> None:
    """A rendered card -- not just the source -- carries the badge and banner."""
    import sys

    sys.path.insert(0, "src")
    from datetime import UTC, datetime

    from empirical_platform.entrypoints import _operator_console_html as html
    from empirical_platform.usecases.operator_console import (
        CapabilityStatus,
        ExecutionCapability,
        HumanState,
        OpportunityCard,
        TermsView,
    )

    now = datetime(2026, 10, 1, 15, 0, tzinfo=UTC)
    card = OpportunityCard(
        proposal_id="PRP-TEST-1",
        proposal_version=1,
        symbol="AAPL",
        terms=TermsView(
            symbol="AAPL",
            side="BUY",
            quantity="5",
            order_type="LIMIT",
            limit_price="100.00",
            notional="500.00",
            currency="USD",
            time_in_force="DAY",
            extended_hours="No",
            fingerprint_short="test-fp-ref",
        ),
        maximum_capital="1000.00",
        stop_price="95.00",
        target_price="110.00",
        risk_amount="25.00",
        risk_percent="2.50%",
        target_gain="50.00",
        reward_risk_ratio="2.00:1",
        mandatory_exit=now,
        reason="Proposed by strategy TEST: 3 of 3 risk checks passed",
        evidence=("evidence line 1",),
        created_at=now,
        expires_at=now,
        state=HumanState.NEEDS_DECISION,
        decision_available=True,
        blocked_note=None,
        attention_note=None,
        intent_id=None,
        execution=None,
        scenario=None,
    )
    view_page = html.opportunity_page(
        card,
        "csrf-token",
        CapabilityStatus(ExecutionCapability.SIMULATION, True, "Simulation", "").label,
        False,
        None,
    )
    assert "RESEARCH CANDIDATE" in view_page
    assert "Research strategy — profitability has not been validated." in view_page
