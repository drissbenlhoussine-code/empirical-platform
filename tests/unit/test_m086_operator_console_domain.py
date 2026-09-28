"""MILESTONE-086 -- the console's vocabulary, language and confirmation tickets, in isolation."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from tests.unit._m085_fakes import _NOW

from empirical_platform.decision_candidate.paper_execution import (
    ExecutionAttempt,
    PaperExecutionState,
)
from empirical_platform.shared.brokerage.alpaca_paper import (
    BrokerAmbiguousDispatchError,
    BrokerNotSentError,
)
from empirical_platform.shared.brokerage.paper_time import PaperTimeUncertainError
from empirical_platform.usecases.decision_to_approval import NotFoundError
from empirical_platform.usecases.operator_console import (
    CAPABILITIES,
    CapabilityRefusedError,
    ConfirmationTicket,
    ConsoleRefusalError,
    ExecutionCapability,
    HmacSigner,
    HumanState,
    describe_failure,
    human_state_for_attempt,
    refuse_requested_environment,
)
from empirical_platform.usecases.paper_execution import PaperExecutionRefusedError


def _attempt(state: PaperExecutionState, failure_code: str | None = None) -> ExecutionAttempt:
    terminal = state in {
        PaperExecutionState.FILLED,
        PaperExecutionState.CANCELED,
        PaperExecutionState.REJECTED,
        PaperExecutionState.EXPIRED,
    }
    return ExecutionAttempt(
        attempt_id="ATT-1",
        intent_governance_id="INT-1",
        authorization_id="AUT-1",
        client_order_id="m085-x",
        request_fingerprint="a" * 64,
        state=state,
        claimed_at=_NOW,
        submitted_at=None,
        acknowledged_at=None,
        terminal_at=_NOW if terminal else None,
        broker_order_id=None,
        broker_status=None,
        filled_quantity=None,
        filled_avg_price=None,
        failure_code=failure_code,
        failure_detail=None,
    )


def test_every_engine_state_has_exactly_one_human_word() -> None:
    expected = {
        PaperExecutionState.DISPATCH_CLAIMED: HumanState.SUBMITTED,
        PaperExecutionState.SUBMISSION_IN_PROGRESS: HumanState.SUBMITTED,
        PaperExecutionState.PAPER_SUBMITTED: HumanState.SUBMITTED,
        PaperExecutionState.PAPER_ACCEPTED: HumanState.ACCEPTED,
        PaperExecutionState.PARTIALLY_FILLED: HumanState.PARTIALLY_FILLED,
        PaperExecutionState.FILLED: HumanState.FILLED,
        PaperExecutionState.CANCEL_REQUESTED: HumanState.CANCEL_REQUESTED,
        PaperExecutionState.CANCELED: HumanState.CANCELLED,
        PaperExecutionState.REJECTED: HumanState.REJECTED,
        PaperExecutionState.EXPIRED: HumanState.EXPIRED,
        PaperExecutionState.SUBMISSION_UNKNOWN: HumanState.NEEDS_ATTENTION,
    }
    for state, word in expected.items():
        assert human_state_for_attempt(_attempt(state)) is word, state
    # Rejected because nothing was ever sent reads as Blocked, not as a broker rejection.
    assert (
        human_state_for_attempt(_attempt(PaperExecutionState.REJECTED, "NOT_SENT"))
        is HumanState.BLOCKED
    )
    assert set(HumanState) == {
        HumanState.NEEDS_DECISION,
        HumanState.APPROVED,
        HumanState.REJECTED,
        HumanState.EXPIRED,
        HumanState.BLOCKED,
        HumanState.SUBMITTED,
        HumanState.ACCEPTED,
        HumanState.PARTIALLY_FILLED,
        HumanState.FILLED,
        HumanState.CANCEL_REQUESTED,
        HumanState.CANCELLED,
        HumanState.NEEDS_ATTENTION,
    }


@pytest.mark.parametrize(
    ("error", "title_fragment", "message_fragment"),
    [
        (PaperTimeUncertainError("clock"), "Execution blocked", "No order was sent"),
        (BrokerNotSentError("dns"), "Nothing was sent", "Nothing was sent"),
        (BrokerAmbiguousDispatchError("lost"), "do not retry", "do not send it again"),
        (
            PaperExecutionRefusedError("the kill switch is engaged"),
            "Execution blocked",
            "No order was sent",
        ),
        (ConsoleRefusalError("Expired", "This opportunity expired."), "Expired", "expired"),
        (NotFoundError("x"), "Not found", "Nothing was done"),
        (ValueError("quantity must be positive"), "Refused", "Nothing was sent"),
        (CapabilityRefusedError("browser"), "Refused", "browser"),
        (
            RuntimeError("psycopg.OperationalError: connection lost"),
            "Could not be recorded",
            "Nothing was executed",
        ),
    ],
)
def test_failures_speak_the_operators_language(
    error: BaseException, title_fragment: str, message_fragment: str
) -> None:
    title, message = describe_failure(error)
    assert title_fragment in title
    assert message_fragment in message
    assert "Traceback" not in message and "psycopg" not in message


def test_the_capability_table_is_closed_and_only_simulation_is_enabled() -> None:
    assert [c.capability for c in CAPABILITIES] == [
        ExecutionCapability.SIMULATION,
        ExecutionCapability.PAPER,
        ExecutionCapability.LIVE,
    ]
    assert [c.enabled for c in CAPABILITIES] == [True, False, False]
    assert "Locked pending M085 Paper Acceptance" in CAPABILITIES[1].label
    assert CAPABILITIES[2].label == "Live — Not authorized"
    for key in ("environment", "capability", "mode", "venue"):
        with pytest.raises(CapabilityRefusedError):
            refuse_requested_environment({key: "SIMULATION"})
    refuse_requested_environment(None)
    refuse_requested_environment({})


class TestConfirmationTickets:
    signer = HmacSigner(b"secret")

    def _ticket(self, now: datetime) -> ConfirmationTicket:
        return ConfirmationTicket("APPROVE", "PRP-1", 1, "f" * 64, now)

    def test_round_trip(self) -> None:
        now = datetime(2026, 9, 28, 12, 0, tzinfo=UTC)
        token = self._ticket(now).encode(self.signer)
        decoded = ConfirmationTicket.decode(
            token, signer=self.signer, now=now + timedelta(minutes=5)
        )
        assert decoded == self._ticket(now)

    def test_tampering_renaming_and_forging_are_refused(self) -> None:
        now = datetime(2026, 9, 28, 12, 0, tzinfo=UTC)
        token = self._ticket(now).encode(self.signer)
        for bad in (
            token.replace("PRP-1", "PRP-2"),
            token.replace("APPROVE", "REJECT"),
            token.replace("|1|", "|2|"),
            token[:-1] + ("0" if token[-1] != "0" else "1"),
            "APPROVE|PRP-1|1|" + "f" * 64 + "|0|nosig",
            "garbage",
            "",
        ):
            with pytest.raises(ConsoleRefusalError):
                ConfirmationTicket.decode(bad, signer=self.signer, now=now)
        other = HmacSigner(b"another process")
        with pytest.raises(ConsoleRefusalError):
            ConfirmationTicket.decode(token, signer=other, now=now)

    def test_age_limits(self) -> None:
        now = datetime(2026, 9, 28, 12, 0, tzinfo=UTC)
        token = self._ticket(now).encode(self.signer)
        with pytest.raises(ConsoleRefusalError) as old:
            ConfirmationTicket.decode(token, signer=self.signer, now=now + timedelta(minutes=16))
        assert old.value.title == "Confirmation expired"
        with pytest.raises(ConsoleRefusalError):
            ConfirmationTicket.decode(token, signer=self.signer, now=now - timedelta(minutes=5))
