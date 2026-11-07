"""RELEASE v1 -- the Active and History pages' plan-derived rendering: the APPROVED PLAN
block, the MANAGEMENT STATUS value, the History "Plan" column, and the same no-superlative
discipline the Research Candidate card already proves.
"""

from __future__ import annotations

from datetime import UTC, datetime

from empirical_platform.entrypoints import _operator_console_html as html
from empirical_platform.entrypoints._operator_console_html import (
    approved_plan_block,
    history_page,
)
from empirical_platform.usecases.operator_console import (
    ExecutionSummary,
    HistoryEntry,
    HumanState,
    TermsView,
)

_NOW = datetime(2026, 10, 1, 15, 0, tzinfo=UTC)

_FORBIDDEN_WORDS = ("recommended", "best trade", "profitable", "guaranteed")


def _a_summary(*, intent_id: str = "INT-1") -> ExecutionSummary:
    return ExecutionSummary(
        intent_id=intent_id,
        proposal_id="PRP-1",
        symbol="AAPL",
        state=HumanState.FILLED,
        raw_state="FILLED",
        terms=TermsView(
            symbol="AAPL",
            side="BUY",
            quantity=5,
            order_type="LIMIT",
            limit_price="100.00",
            time_in_force="DAY",
            extended_hours="No",
            currency="USD",
            notional="500.00",
            fingerprint_short="test-fp-ref",
        ),
        decision_by="owner",
        decided_at=_NOW,
        broker_order_id="BRK-1",
        claimed_at=_NOW,
        submitted_at=_NOW,
        acknowledged_at=_NOW,
        terminal_at=_NOW,
        filled_quantity="5",
        filled_avg_price="100.00",
        pending_reason=None,
        reconciliation="",
        warnings=(),
        timeline=(),
        is_terminal=True,
        outcome_known=True,
        can_cancel=False,
        execution_kind="entry",
        position_open=True,
        exit_status="open",
        category="Open position",
        can_review_exit=True,
    )


def test_approved_plan_block_renders_every_required_field() -> None:
    block = approved_plan_block(
        quantity="5",
        entry_avg_fill="100.00",
        current_price="105.00",
        unrealized_pnl="25.00",
        stop_price="95.00",
        target_price="110.00",
        mandatory_exit="2026-10-01T19:45",
        max_loss="25.00",
        management_status="Monitoring",
        review_manual_exit_url="/exit/review?intent=INT-1",
    )
    for required in (
        "Approved plan",
        "Monitoring",
        "Automatic management is limited to the Owner-approved Paper plan.",
        "Quantity",
        "Entry avg fill",
        "Current price",
        "Unrealized P&amp;L",
        "Stop",
        "Target",
        "Mandatory Exit",
        "Max Loss",
        "REVIEW MANUAL EXIT",
        "/exit/review?intent=INT-1",
    ):
        assert required in block, required


def test_approved_plan_block_omits_the_manual_exit_link_when_none_is_offered() -> None:
    block = approved_plan_block(
        quantity="5",
        entry_avg_fill="100.00",
        current_price="105.00",
        unrealized_pnl="25.00",
        stop_price="95.00",
        target_price="110.00",
        mandatory_exit="2026-10-01T19:45",
        max_loss="25.00",
        management_status="Closed",
        review_manual_exit_url=None,
    )
    assert "REVIEW MANUAL EXIT" not in block


def test_a_needs_attention_status_is_visible_on_the_active_page() -> None:
    summary = _a_summary()
    block = approved_plan_block(
        quantity="5",
        entry_avg_fill="100.00",
        current_price="Not available",
        unrealized_pnl="Not available",
        stop_price="95.00",
        target_price="110.00",
        mandatory_exit="2026-10-01T19:45",
        max_loss="25.00",
        management_status="Needs attention",
        review_manual_exit_url="/exit/review?intent=INT-1",
    )
    page = html.active_page(
        (summary,), "csrf-token", "Paper", False, None, plan_blocks={"INT-1": block}
    )
    assert "Needs attention" in page
    assert "Approved plan" in page


def test_the_plan_block_appears_only_for_the_matching_intent() -> None:
    a = _a_summary(intent_id="INT-1")
    b = _a_summary(intent_id="INT-2")
    block = approved_plan_block(
        quantity="5",
        entry_avg_fill="100.00",
        current_price="105.00",
        unrealized_pnl="25.00",
        stop_price="95.00",
        target_price="110.00",
        mandatory_exit="2026-10-01T19:45",
        max_loss="25.00",
        management_status="Monitoring",
        review_manual_exit_url=None,
    )
    page = html.active_page(
        (a, b), "csrf-token", "Paper", False, None, plan_blocks={"INT-1": block}
    )
    assert page.count("Approved plan") == 1


def test_history_page_shows_no_plan_column_when_no_cells_are_given() -> None:
    entry = HistoryEntry(
        proposal_id="PRP-1",
        symbol="AAPL",
        created_at=_NOW,
        proposal_state="Filled",
        decision="Approved",
        decided_at=_NOW,
        decided_by="owner",
        execution_kind="entry",
        execution_outcome="Filled",
        final_state=HumanState.FILLED,
        quantity="5",
        price="100.00",
        result="Closed",
        intent_id="INT-1",
        timestamp=_NOW,
    )
    page = history_page((entry,), filters={}, capability_label="Paper", kill_switch_engaged=False)
    assert "<th>Plan</th>" not in page


def test_history_page_shows_the_plan_column_with_every_required_fact_when_given() -> None:
    entry = HistoryEntry(
        proposal_id="PRP-1",
        symbol="AAPL",
        created_at=_NOW,
        proposal_state="Filled",
        decision="Approved",
        decided_at=_NOW,
        decided_by="owner",
        execution_kind="entry",
        execution_outcome="Filled",
        final_state=HumanState.FILLED,
        quantity="5",
        price="100.00",
        result="Closed",
        intent_id="INT-1",
        timestamp=_NOW,
    )
    cell = (
        "Candidate OPP-1<br>Owner DEC-PRP-1<br>Trigger STOP<br>Exit order BRK-2"
        "<br>Exit fill 5 @ 95.00<br>Zero-verified Yes<br>Gross P&amp;L -25.00"
    )
    page = history_page(
        (entry,),
        filters={},
        capability_label="Paper",
        kill_switch_engaged=False,
        plan_cells={"INT-1": cell},
    )
    assert "<th>Plan</th>" in page
    for required in (
        "Candidate OPP-1",
        "Owner DEC-PRP-1",
        "Trigger STOP",
        "Exit order BRK-2",
        "Exit fill 5 @ 95.00",
        "Zero-verified Yes",
        "Gross P&amp;L -25.00",
    ):
        assert required in page, required


def test_no_superlative_language_in_the_plan_rendering_source() -> None:
    import inspect

    source = inspect.getsource(approved_plan_block).lower()
    for word in _FORBIDDEN_WORDS:
        assert word not in source, word
