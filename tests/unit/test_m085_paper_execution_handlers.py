"""MILESTONE-085 handlers and renderers, with in-memory fakes.

WHY FAKES HERE WHEN THERE ARE 54 DATABASE TESTS AND 102 HOSTILE-HTTP TESTS. Those
answer "does PostgreSQL refuse this" and "does the adapter survive a hostile peer".
Neither answers "does the ORCHESTRATION do the right things in the right order",
which is a separate question and the one this file is about: that the kill switch is
read before the evidence is refreshed, that the fingerprint is RECOMPUTED rather than
reused, that a second submit sends nothing, that an ambiguous dispatch becomes
SUBMISSION_UNKNOWN, and that a 404 does not resolve an unknown outcome on its own.

The fakes are deliberately dumb -- dictionaries and lists, no behaviour of their own --
so a test that passes here cannot be passing because the fake was clever. Every
refusal asserted below is produced by the handler under test.

These also run with PostgreSQL OFF, which matters: CI has no database, so without
them the entire application layer would be untested in the environment that gates
the merge.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import timedelta
from decimal import Decimal
from typing import Any

import pytest
from freezegun import freeze_time
from freezegun.api import FrozenDateTimeFactory
from tests.unit._m085_fakes import (
    _DIGEST,
    _NOW,
    FakeAcknowledgements,
    FakeAttempts,
    FakeAuthorizations,
    FakeBroker,
    FakeEvents,
    FakeIntents,
    FakeKillSwitch,
    FakeMarketData,
    FakePreviews,
    FakeQuote,
    FakeSnapshots,
    FakeView,
    a_preview,
    an_intent,
)

from empirical_platform.decision_candidate.paper_execution import (
    PAPER_ENDPOINT_HOST,
    BrokerAcknowledgement,
    ExecutionAttempt,
    ExecutionAuthorization,
    PaperExecutionEvent,
    PaperExecutionState,
    authorize_submission,
)
from empirical_platform.shared.brokerage.alpaca_paper import (
    BrokerAmbiguousDispatchError,
    BrokerNotSentError,
)
from empirical_platform.usecases.decision_to_approval import NotFoundError
from empirical_platform.usecases.paper_execution import (
    AuthorizePaperSubmissionCommand,
    AuthorizePaperSubmissionHandler,
    CancelPaperOrderCommand,
    CancelPaperOrderHandler,
    InspectPaperAccountCommand,
    InspectPaperAccountHandler,
    ListPaperExecutionsHandler,
    ListPaperExecutionsQuery,
    PaperExecutionRefusedError,
    PaperExecutionStatusHandler,
    PaperExecutionStatusQuery,
    PreviewPaperSubmissionCommand,
    PreviewPaperSubmissionHandler,
    ReconcilePaperOrderCommand,
    ReconcilePaperOrderHandler,
    SetExecutionKillSwitchCommand,
    SetExecutionKillSwitchHandler,
    ShowPaperExecutionHandler,
    ShowPaperExecutionQuery,
    SubmitAuthorizedPaperOrderCommand,
    SubmitAuthorizedPaperOrderHandler,
    VerifyPaperEnvironmentHandler,
    VerifyPaperEnvironmentQuery,
)
from empirical_platform.usecases.paper_execution_io import (
    render_account_json,
    render_account_text,
    render_acknowledgement_json,
    render_attempt_json,
    render_attempt_text,
    render_authorization_json,
    render_authorization_text,
    render_environment_json,
    render_environment_text,
    render_event_json,
    render_preview_json,
    render_preview_text,
    render_status_json,
    render_status_text,
    render_submission_json,
    render_submission_text,
)

# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def operation_clock() -> Iterator[FrozenDateTimeFactory]:
    with freeze_time(_NOW) as clock:
        yield clock


class TestVerifyPaperEnvironment:
    def test_it_reports_the_pinned_host_and_a_redacted_account_reference(self) -> None:
        result = VerifyPaperEnvironmentHandler(
            broker=FakeBroker(), market_data=FakeMarketData()
        ).handle(VerifyPaperEnvironmentQuery())
        assert result.endpoint_host == PAPER_ENDPOINT_HOST
        assert result.is_the_pinned_paper_host is True
        assert result.account_reachable is True
        assert result.account_status == "ACTIVE"
        assert result.account_reference.startswith("ref:")
        assert "real-account-id" not in result.account_reference
        assert render_environment_json(result)["is_the_pinned_paper_host"] is True
        assert "PAPER" in render_environment_text(result)

    def test_an_unreachable_account_is_reported_not_raised(self) -> None:
        result = VerifyPaperEnvironmentHandler(
            broker=FakeBroker(account_status_code=503), market_data=FakeMarketData()
        ).handle(VerifyPaperEnvironmentQuery())
        assert result.account_reachable is False
        assert result.account_status == "unknown"


class TestInspectPaperAccount:
    def test_it_stores_a_snapshot_with_a_digest_not_an_account_number(self) -> None:
        snapshots = FakeSnapshots()
        snapshot = InspectPaperAccountHandler(broker=FakeBroker(), snapshots=snapshots).handle(
            InspectPaperAccountCommand(snapshot_id="SNP-9", captured_at=_NOW)
        )
        assert snapshot.account_reference.startswith("ref:")
        assert "real-account-id" not in snapshot.account_reference
        assert snapshots.rows["SNP-9"] == snapshot
        assert render_account_json(snapshot)["environment"] == "PAPER"
        assert "SIMULATED FUNDS" in render_account_text(snapshot)

    def test_a_non_200_account_is_a_refusal(self) -> None:
        with pytest.raises(PaperExecutionRefusedError, match="could not be read"):
            InspectPaperAccountHandler(
                broker=FakeBroker(account_status_code=500), snapshots=FakeSnapshots()
            ).handle(InspectPaperAccountCommand(snapshot_id="SNP-9", captured_at=_NOW))

    def test_a_non_boolean_account_flag_is_refused_rather_than_coerced(self) -> None:
        from empirical_platform.shared.brokerage.alpaca_paper import BrokerResponseInvalidError

        with pytest.raises(BrokerResponseInvalidError, match="trading_blocked"):
            InspectPaperAccountHandler(
                broker=FakeBroker(account_overrides={"trading_blocked": "false"}),
                snapshots=FakeSnapshots(),
            ).handle(InspectPaperAccountCommand(snapshot_id="SNP-9", captured_at=_NOW))


class TestPreviewPaperSubmission:
    def _handler(self, **fakes: object) -> PreviewPaperSubmissionHandler:
        return PreviewPaperSubmissionHandler(
            intents=fakes.get("intents") or FakeIntents(an_intent()),  # type: ignore[arg-type]
            snapshots=fakes.get("snapshots") or FakeSnapshots(),  # type: ignore[arg-type]
            previews=fakes.get("previews") or FakePreviews(),  # type: ignore[arg-type]
            events=fakes.get("events") or FakeEvents(),  # type: ignore[arg-type]
            broker=fakes.get("broker") or FakeBroker(),  # type: ignore[arg-type]
            market_data=fakes.get("market_data") or FakeMarketData(),  # type: ignore[arg-type]
            kill_switch=fakes.get("kill_switch") or FakeKillSwitch(),  # type: ignore[arg-type]
        )

    def _command(self, **overrides: object) -> PreviewPaperSubmissionCommand:
        arguments: dict[str, object] = {
            "intent_governance_id": "INT-1",
            "preview_id": "PVW-1",
            "account_snapshot_id": "SNP-1",
            "approved_watchlist": frozenset({"AAPL"}),
            "maximum_notional": Decimal("5"),
            "quote_maximum_age_seconds": 60,
            "created_at": _NOW,
        }
        arguments.update(overrides)
        return PreviewPaperSubmissionCommand(**arguments)  # type: ignore[arg-type]

    def test_an_unknown_intent_is_not_found(self) -> None:
        with pytest.raises(NotFoundError, match="INT-MISSING"):
            self._handler(intents=FakeIntents()).handle(
                self._command(intent_governance_id="INT-MISSING")
            )

    def test_a_clean_preview_is_stored_and_authorizable(self) -> None:
        previews, events = FakePreviews(), FakeEvents()
        preview = self._handler(previews=previews, events=events).handle(self._command())
        assert preview.is_authorizable is True
        assert previews.rows["PVW-1"] == preview
        assert [event.event_type for event in events.rows] == ["PREVIEW_CREATED"]
        assert render_preview_json(preview)["is_authorizable"] is True
        assert "REQUEST FINGERPRINT" in render_preview_text(preview)

    def test_an_engaged_kill_switch_produces_a_refusal_not_an_exception(self) -> None:
        preview = self._handler(kill_switch=FakeKillSwitch(engaged=True)).handle(self._command())
        assert preview.is_authorizable is False
        assert any("kill switch" in reason for reason in preview.refusals)
        # And it is STILL stored, so an operator asking "why can I not send this"
        # gets the list rather than an empty result.
        assert "REFUSED" in render_preview_text(preview)

    def test_an_absent_quote_refuses_on_freshness(self) -> None:
        preview = self._handler(market_data=FakeMarketData(quote=None)).handle(self._command())
        assert any("no quote was captured" in reason for reason in preview.refusals)
        assert render_preview_json(preview)["quote_source"] == "absent"

    def test_a_quote_newer_than_the_command_instant_is_authorizable(
        self, operation_clock: FrozenDateTimeFactory
    ) -> None:
        """FIND-P7-01, at the layer where it actually bit.

        The entrypoint stamps `created_at`, THEN the handler fetches the quote. In an
        open market the fetched quote is newer than that instant almost every time.
        This is the shape the real market-open run produced (3.15 s), and the first
        version of the rule refused it as "from the future".
        """

        class LaterQuote(FakeQuote):
            captured_at = _NOW + timedelta(seconds=3, milliseconds=150)

        class DelayedData(FakeMarketData):
            def fetch_quote(self, symbol: str) -> object:
                operation_clock.tick(delta=timedelta(seconds=4))
                return LaterQuote()

        preview = self._handler(market_data=DelayedData()).handle(self._command())
        assert preview.is_authorizable is True, preview.refusals

    def test_a_quote_far_ahead_of_the_command_instant_is_still_refused(self) -> None:
        class FarAheadQuote(FakeQuote):
            captured_at = _NOW + timedelta(seconds=1)

        preview = self._handler(market_data=FakeMarketData(quote=FarAheadQuote())).handle(
            self._command()
        )
        assert preview.is_authorizable is False
        assert any("dated after this preview" in reason for reason in preview.refusals)

    def test_the_preview_version_comes_from_stored_rows(self) -> None:
        previews = FakePreviews()
        handler = self._handler(previews=previews)
        first = handler.handle(self._command())
        second = handler.handle(self._command(preview_id="PVW-2"))
        assert (first.preview_version, second.preview_version) == (1, 2)


class TestAuthorizePaperSubmission:
    def _handler(self, previews: FakePreviews, authorizations: FakeAuthorizations):  # noqa: ANN202
        return AuthorizePaperSubmissionHandler(
            previews=previews, authorizations=authorizations, events=FakeEvents()
        )

    def test_an_unknown_preview_is_not_found(self) -> None:
        with pytest.raises(NotFoundError, match="PVW-MISSING"):
            self._handler(FakePreviews(), FakeAuthorizations()).handle(
                AuthorizePaperSubmissionCommand(
                    authorization_id="AUT-1",
                    preview_id="PVW-MISSING",
                    expected_request_fingerprint=_DIGEST,
                    authorized_by="owner",
                    authorized_at=_NOW,
                    validity_seconds=60,
                )
            )

    def test_a_mismatched_fingerprint_is_refused(self) -> None:
        previews = FakePreviews()
        preview = previews.save(a_preview())
        with pytest.raises(PaperExecutionRefusedError, match="does not match"):
            self._handler(previews, FakeAuthorizations()).handle(
                AuthorizePaperSubmissionCommand(
                    authorization_id="AUT-1",
                    preview_id=preview.preview_id,
                    expected_request_fingerprint="b" * 64,
                    authorized_by="owner",
                    authorized_at=_NOW,
                    validity_seconds=60,
                )
            )

    def test_a_preview_with_refusals_cannot_be_authorized(self) -> None:
        previews = FakePreviews()
        preview = previews.save(a_preview(execution_kill_switch_engaged=True))
        with pytest.raises(PaperExecutionRefusedError, match="cannot be authorized"):
            self._handler(previews, FakeAuthorizations()).handle(
                AuthorizePaperSubmissionCommand(
                    authorization_id="AUT-1",
                    preview_id=preview.preview_id,
                    expected_request_fingerprint=preview.request_fingerprint,
                    authorized_by="owner",
                    authorized_at=_NOW,
                    validity_seconds=60,
                )
            )

    def test_the_matching_fingerprint_produces_a_single_use_permission(self) -> None:
        previews, authorizations = FakePreviews(), FakeAuthorizations()
        preview = previews.save(a_preview())
        authorization = self._handler(previews, authorizations).handle(
            AuthorizePaperSubmissionCommand(
                authorization_id="AUT-1",
                preview_id=preview.preview_id,
                expected_request_fingerprint=preview.request_fingerprint,
                authorized_by="owner",
                authorized_at=_NOW,
                validity_seconds=300,
            )
        )
        assert authorization.is_consumed is False
        assert authorization.expires_at == _NOW + timedelta(seconds=300)
        assert authorizations.rows["AUT-1"] == authorization
        assert render_authorization_json(authorization)["is_consumed"] is False
        assert "SINGLE USE" in render_authorization_text(authorization)


class TestSubmitAuthorizedPaperOrder:
    """The dispatch path, driven through the real preview and authorize handlers.

    An ExecutionAuthorization is NOT hand-built here, and that is forced by the
    design rather than by convenience: the submit handler refreshes the account,
    clock, asset, position and quote and RECOMPUTES the fingerprint, then refuses
    anything the authorization is not bound to. So an authorization only matches if
    it was created from the same evidence the broker fake will report. Going
    through both real handlers is therefore the only honest setup -- and it makes
    each test cover the whole chain instead of one handler in isolation.
    """

    def _world(self, **overrides: object) -> dict[str, Any]:
        world: dict[str, Any] = {
            "intents": FakeIntents(an_intent()),
            "snapshots": FakeSnapshots(),
            "previews": FakePreviews(),
            "authorizations": FakeAuthorizations(),
            "attempts": FakeAttempts(),
            "acknowledgements": FakeAcknowledgements(),
            "events": FakeEvents(),
            "broker": FakeBroker(),
            "market_data": FakeMarketData(),
            "kill_switch": FakeKillSwitch(),
        }
        world.update(overrides)
        return world

    def _authorize(
        self, world: dict[str, Any], *, validity_seconds: int = 300
    ) -> ExecutionAuthorization:
        preview = PreviewPaperSubmissionHandler(
            intents=world["intents"],
            snapshots=world["snapshots"],
            previews=world["previews"],
            events=world["events"],
            broker=world["broker"],
            market_data=world["market_data"],
            kill_switch=world["kill_switch"],
        ).handle(
            PreviewPaperSubmissionCommand(
                intent_governance_id="INT-1",
                preview_id="PVW-1",
                account_snapshot_id="SNP-1",
                approved_watchlist=frozenset({"AAPL"}),
                maximum_notional=Decimal("5"),
                quote_maximum_age_seconds=60,
                created_at=_NOW,
            )
        )
        assert preview.is_authorizable, preview.refusals
        return AuthorizePaperSubmissionHandler(
            previews=world["previews"],
            authorizations=world["authorizations"],
            events=world["events"],
        ).handle(
            AuthorizePaperSubmissionCommand(
                authorization_id="AUT-1",
                preview_id=preview.preview_id,
                expected_request_fingerprint=preview.request_fingerprint,
                authorized_by="owner",
                authorized_at=_NOW,
                validity_seconds=validity_seconds,
            )
        )

    def _handler(self, world: dict[str, Any]) -> SubmitAuthorizedPaperOrderHandler:
        return SubmitAuthorizedPaperOrderHandler(
            intents=world["intents"],
            previews=world["previews"],
            authorizations=world["authorizations"],
            attempts=world["attempts"],
            acknowledgements=world["acknowledgements"],
            events=world["events"],
            snapshots=world["snapshots"],
            broker=world["broker"],
            market_data=world["market_data"],
            kill_switch=world["kill_switch"],
        )

    def _command(self, **overrides: object) -> SubmitAuthorizedPaperOrderCommand:
        arguments: dict[str, object] = {
            "intent_governance_id": "INT-1",
            "attempt_id": "ATT-1",
            "account_snapshot_id": "SNP-2",
            "approved_watchlist": frozenset({"AAPL"}),
            "maximum_notional": Decimal("5"),
            "quote_maximum_age_seconds": 60,
            "at": _NOW,
        }
        arguments.update(overrides)
        return SubmitAuthorizedPaperOrderCommand(**arguments)  # type: ignore[arg-type]

    def test_with_no_authorization_it_refuses_and_sends_nothing(self) -> None:
        world = self._world()
        with pytest.raises(PaperExecutionRefusedError, match="no human authorization"):
            self._handler(world).handle(self._command())
        assert world["broker"].submitted == []

    def test_an_unknown_intent_is_not_found(self) -> None:
        world = self._world()
        self._authorize(world)
        world["intents"] = FakeIntents()
        with pytest.raises(NotFoundError):
            self._handler(world).handle(self._command())

    def test_the_kill_switch_is_read_before_anything_is_sent(self) -> None:
        world = self._world()
        self._authorize(world)
        # Engaged AFTER a human authorized: the switch must still stop it.
        world["kill_switch"].engaged = True
        with pytest.raises(PaperExecutionRefusedError, match="kill switch"):
            self._handler(world).handle(self._command())
        assert world["broker"].submitted == []
        assert world["kill_switch"].reads >= 1

    def test_authorization_expiring_during_fetch_never_submits(self) -> None:
        from freezegun import freeze_time

        with freeze_time(_NOW) as clock:
            world = self._world()
            self._authorize(world, validity_seconds=1)
            original = world["market_data"].fetch_quote

            def delayed_quote(symbol: str) -> object:
                clock.tick(delta=timedelta(seconds=2))
                return original(symbol)

            world["market_data"].fetch_quote = delayed_quote
            with pytest.raises(PaperExecutionRefusedError, match="expired"):
                self._handler(world).handle(self._command())
            assert world["broker"].submitted == []

    def test_a_happy_dispatch_claims_then_submits_then_records(self) -> None:
        world = self._world()
        self._authorize(world)
        result = self._handler(world).handle(self._command())
        assert result.dispatched is True
        assert result.http_status == 200
        assert result.broker_status == "accepted"
        # The ORDER of the transitions is the design, so it is asserted.
        assert [state for _, state in world["attempts"].transitions][:2] == [
            PaperExecutionState.SUBMISSION_IN_PROGRESS,
            PaperExecutionState.PAPER_SUBMITTED,
        ]
        assert len(world["broker"].submitted) == 1
        assert [row.kind for row in world["acknowledgements"].rows] == ["SUBMIT"]
        assert render_submission_json(result)["dispatched"] is True
        assert "PAPER SUBMISSION RESULT" in render_submission_text(result)

    def test_a_dispatch_whose_refreshed_quote_is_newer_than_its_instant_proceeds(
        self, operation_clock: FrozenDateTimeFactory
    ) -> None:
        # FIND-P7-01 on the dispatch path: the re-check at `command.at` fetches a quote
        # newer than `at`. That must not read as "conditions changed".
        class LaterQuote(FakeQuote):
            captured_at = _NOW + timedelta(seconds=3, milliseconds=150)

        world = self._world()
        self._authorize(world)

        class DelayedData(FakeMarketData):
            def fetch_quote(self, symbol: str) -> object:
                operation_clock.tick(delta=timedelta(seconds=4))
                return LaterQuote()

        world["market_data"] = DelayedData()
        result = self._handler(world).handle(self._command())
        assert result.dispatched is True

    def test_the_derived_client_order_id_is_what_was_actually_sent(self) -> None:
        world = self._world()
        authorization = self._authorize(world)
        self._handler(world).handle(self._command())
        sent = world["broker"].submitted[0]
        assert sent.client_order_id == authorization.client_order_id
        assert sent.client_order_id.startswith("m085-")

    def test_a_second_submit_sends_nothing_and_returns_the_persisted_attempt(self) -> None:
        world = self._world()
        self._authorize(world)
        handler = self._handler(world)
        handler.handle(self._command())
        sent_once = len(world["broker"].submitted)
        again = handler.handle(self._command())
        assert again.dispatched is False
        assert again.http_status is None
        assert "already been dispatched" in again.note
        assert len(world["broker"].submitted) == sent_once

    def test_a_definitely_not_sent_failure_becomes_rejected(self) -> None:
        world = self._world()
        self._authorize(world)
        world["broker"].submit_raises = BrokerNotSentError("connection refused")
        result = self._handler(world).handle(self._command())
        assert result.dispatched is False
        assert result.attempt.state is PaperExecutionState.REJECTED
        assert result.attempt.failure_code == "NOT_SENT"
        assert "never reached the broker" in result.note

    def test_a_maybe_sent_failure_becomes_submission_unknown(self) -> None:
        world = self._world()
        self._authorize(world)
        world["broker"].submit_raises = BrokerAmbiguousDispatchError("no answer")
        result = self._handler(world).handle(self._command())
        assert result.dispatched is True
        assert result.attempt.state is PaperExecutionState.SUBMISSION_UNKNOWN
        assert result.attempt.outcome_is_known is False
        assert "do not send again" in result.note
        assert "OUTCOME UNKNOWN" in render_attempt_text(result.attempt)

    def test_a_broker_refusal_becomes_rejected_with_its_status(self) -> None:
        world = self._world()
        self._authorize(world)
        world["broker"].submit_status = 422
        world["broker"].submit_body = "refused"
        result = self._handler(world).handle(self._command())
        assert result.http_status == 422
        assert result.attempt.state is PaperExecutionState.REJECTED
        assert result.attempt.failure_code == "HTTP_422"

    def test_a_losing_claim_sends_nothing(self) -> None:
        world = self._world()
        self._authorize(world)
        world["attempts"].claim_wins = False
        result = self._handler(world).handle(self._command())
        assert result.dispatched is False
        assert world["broker"].submitted == []
        assert "another worker" in result.note

    def test_conditions_changing_after_the_preview_refuse_the_dispatch(self) -> None:
        world = self._world()
        self._authorize(world)
        # The account now forbids trading, so the RE-CHECK refuses even though a
        # human authorization exists and has not expired.
        world["broker"].account_overrides = {"trading_blocked": True}
        with pytest.raises(PaperExecutionRefusedError, match="conditions changed"):
            self._handler(world).handle(self._command())
        assert world["broker"].submitted == []

    def test_an_expired_authorization_refuses_the_dispatch(
        self, operation_clock: FrozenDateTimeFactory
    ) -> None:
        # A SHORT validity, then a dispatch 30s later, so the quote is still inside
        # its 60s tolerance and expiry is the only thing wrong. Simply advancing the
        # clock past a 300s validity would have staled the quote too, and the
        # freshness refusal fires first -- so that test would have passed without
        # expiry ever being checked.
        world = self._world()
        self._authorize(world, validity_seconds=10)
        operation_clock.tick(delta=timedelta(seconds=30))
        with pytest.raises(PaperExecutionRefusedError, match="expired"):
            self._handler(world).handle(self._command(at=_NOW + timedelta(seconds=30)))
        assert world["broker"].submitted == []

    def test_a_dispatch_inside_the_validity_window_is_allowed(self) -> None:
        # The negative half of the test above: same short validity, inside it.
        # Without this, "expired" could be refusing every dispatch.
        world = self._world()
        self._authorize(world, validity_seconds=10)
        result = self._handler(world).handle(self._command(at=_NOW + timedelta(seconds=5)))
        assert result.dispatched is True

    def test_a_filled_acknowledgement_moves_the_state_to_filled(self) -> None:
        world = self._world()
        self._authorize(world)
        world["broker"].submit_fields = {
            "status": "filled",
            "filled_quantity": "1",
            "filled_avg_price": "4.00",
        }
        result = self._handler(world).handle(self._command())
        assert result.attempt.state is PaperExecutionState.FILLED
        assert result.attempt.is_terminal is True

    def test_an_unmapped_broker_status_leaves_the_state_alone(self) -> None:
        world = self._world()
        self._authorize(world)
        world["broker"].submit_fields = {"status": "calculated"}
        result = self._handler(world).handle(self._command())
        # Recorded, and NOT guessed at.
        assert result.attempt.broker_status == "calculated"
        assert result.attempt.state is PaperExecutionState.PAPER_SUBMITTED

    @pytest.mark.parametrize("phase", ["fetch", "snapshot", "claim", "prepare", "connect"])
    @pytest.mark.parametrize("deadline", ["quote", "authorization", "intent", "session"])
    def test_elapsed_work_cannot_extend_a_deadline(
        self, operation_clock: FrozenDateTimeFactory, phase: str, deadline: str
    ) -> None:
        from dataclasses import replace

        world = self._world()
        self._authorize(world)
        if deadline == "authorization":
            auth = world["authorizations"].rows["AUT-1"]
            world["authorizations"].rows["AUT-1"] = replace(
                auth, expires_at=_NOW + timedelta(seconds=1)
            )
        if deadline == "intent":
            world["intents"].rows["INT-1"] = an_intent(expires_at=_NOW + timedelta(seconds=1))
        if deadline == "session":
            original_clock = world["broker"].fetch_clock

            def closing_clock() -> object:
                value = original_clock()
                value.next_close = _NOW + timedelta(seconds=1)
                return value

            world["broker"].fetch_clock = closing_clock
        delay = 61 if deadline == "quote" else 2
        target, method = {
            "fetch": (world["market_data"], "fetch_quote"),
            "snapshot": (world["snapshots"], "save"),
            "claim": (world["attempts"], "claim_dispatch"),
            "prepare": (world["attempts"], "transition"),
            "connect": (world["broker"], "submit_order"),
        }[phase]
        original = getattr(target, method)

        def delayed(*args: object, **kwargs: object) -> object:
            operation_clock.tick(delta=timedelta(seconds=delay))
            return original(*args, **kwargs)

        setattr(target, method, delayed)
        try:
            result = self._handler(world).handle(self._command())
        except ValueError:
            pass
        else:
            assert not result.dispatched
            assert result.attempt.state is PaperExecutionState.REJECTED
            # A spent/claimed identity never becomes an automatic retry.
            again = self._handler(world).handle(self._command())
            assert not again.dispatched
        assert world["broker"].submitted == []

    def test_rollback_after_claim_refuses_without_a_retry(
        self, operation_clock: FrozenDateTimeFactory
    ) -> None:
        world = self._world()
        self._authorize(world)
        original = world["broker"].submit_order

        def rollback(*args: object, **kwargs: object) -> object:
            operation_clock.tick(delta=timedelta(seconds=-1))
            return original(*args, **kwargs)

        world["broker"].submit_order = rollback
        result = self._handler(world).handle(self._command())
        assert not result.dispatched
        assert "rollback" in result.attempt.failure_detail
        assert world["broker"].submitted == []
        assert not self._handler(world).handle(self._command()).dispatched

    def test_broker_clock_uncertainty_refuses_before_claim(self) -> None:
        world = self._world()
        self._authorize(world)
        original = world["broker"].fetch_clock

        def future_clock() -> object:
            value = original()
            value.timestamp = _NOW + timedelta(seconds=1)
            return value

        world["broker"].fetch_clock = future_clock
        with pytest.raises(ValueError, match="alignment is uncertain"):
            self._handler(world).handle(self._command())
        assert world["broker"].submitted == []
        assert world["attempts"].rows == {}


class TestReconcilePaperOrder:
    def _dispatched(self) -> tuple[FakeAttempts, ExecutionAttempt]:
        preview = a_preview()
        authorizations = FakeAuthorizations()
        authorization = authorizations.save(
            authorize_submission(
                authorization_id="AUT-1",
                preview=preview,
                authorized_by="owner",
                authorized_at=_NOW,
                validity_seconds=300,
            )
        )
        attempts = FakeAttempts()
        claim = attempts.claim_dispatch(
            attempt_id="ATT-1",
            authorization=authorization,
            request_fingerprint_now=authorization.request_fingerprint,
            account_reference_now=authorization.account_reference,
            claimed_at=_NOW,
        )
        attempts.transition(
            attempt_id=claim.attempt.attempt_id,
            target=PaperExecutionState.SUBMISSION_IN_PROGRESS,
            at=_NOW,
        )
        attempt = attempts.transition(
            attempt_id=claim.attempt.attempt_id,
            target=PaperExecutionState.PAPER_SUBMITTED,
            at=_NOW,
            broker_order_id="broker-1",
        )
        return attempts, attempt

    def test_an_intent_with_no_attempt_is_not_found(self) -> None:
        with pytest.raises(NotFoundError):
            ReconcilePaperOrderHandler(
                attempts=FakeAttempts(),
                acknowledgements=FakeAcknowledgements(),
                events=FakeEvents(),
                broker=FakeBroker(),
            ).handle(ReconcilePaperOrderCommand(intent_governance_id="INT-1", at=_NOW))

    def test_it_asks_about_the_original_client_order_id(self) -> None:
        attempts, attempt = self._dispatched()
        broker = FakeBroker(
            lookup_view=FakeView(client_order_id=attempt.client_order_id, status="canceled")
        )
        result = ReconcilePaperOrderHandler(
            attempts=attempts,
            acknowledgements=FakeAcknowledgements(),
            events=FakeEvents(),
            broker=broker,
        ).handle(ReconcilePaperOrderCommand(intent_governance_id="INT-1", at=_NOW))
        assert broker.lookups == [attempt.client_order_id]
        assert result.state is PaperExecutionState.CANCELED

    def test_a_terminal_attempt_is_returned_without_asking(self) -> None:
        attempts, attempt = self._dispatched()
        attempts.transition(
            attempt_id=attempt.attempt_id, target=PaperExecutionState.FILLED, at=_NOW
        )
        broker = FakeBroker()
        ReconcilePaperOrderHandler(
            attempts=attempts,
            acknowledgements=FakeAcknowledgements(),
            events=FakeEvents(),
            broker=broker,
        ).handle(ReconcilePaperOrderCommand(intent_governance_id="INT-1", at=_NOW))
        assert broker.lookups == []

    def test_one_not_found_does_not_resolve_an_unknown_outcome(self) -> None:
        attempts, attempt = self._dispatched()
        events = FakeEvents()
        result = ReconcilePaperOrderHandler(
            attempts=attempts,
            acknowledgements=FakeAcknowledgements(),
            events=events,
            broker=FakeBroker(lookup_status=404, lookup_view=None),
        ).handle(ReconcilePaperOrderCommand(intent_governance_id="INT-1", at=_NOW))
        assert result.state is PaperExecutionState.PAPER_SUBMITTED
        assert any(event.event_type == "RECONCILE_NOT_FOUND_INSUFFICIENT" for event in events.rows)

    def test_the_bounded_policy_resolves_only_with_enough_observations_and_time(self) -> None:
        attempts, attempt = self._dispatched()
        acknowledgements, events = FakeAcknowledgements(), FakeEvents()
        handler = ReconcilePaperOrderHandler(
            attempts=attempts,
            acknowledgements=acknowledgements,
            events=events,
            broker=FakeBroker(lookup_status=404, lookup_view=None),
        )
        later = _NOW + timedelta(seconds=120)
        handler.handle(ReconcilePaperOrderCommand(intent_governance_id="INT-1", at=later))
        result = handler.handle(ReconcilePaperOrderCommand(intent_governance_id="INT-1", at=later))
        assert result.state is PaperExecutionState.REJECTED
        assert result.failure_code == "NOT_FOUND_AT_BROKER"
        assert any(event.event_type == "RECONCILE_RESOLVED_NOT_FOUND" for event in events.rows)

    def test_an_unusable_answer_records_an_event_and_changes_nothing(self) -> None:
        attempts, _ = self._dispatched()
        events = FakeEvents()
        result = ReconcilePaperOrderHandler(
            attempts=attempts,
            acknowledgements=FakeAcknowledgements(),
            events=events,
            broker=FakeBroker(lookup_status=500, lookup_view=None),
        ).handle(ReconcilePaperOrderCommand(intent_governance_id="INT-1", at=_NOW))
        assert result.state is PaperExecutionState.PAPER_SUBMITTED
        assert any(event.event_type == "RECONCILE_UNUSABLE_ANSWER" for event in events.rows)


class TestCancelPaperOrder:
    def _dispatched(self) -> FakeAttempts:
        attempts, _ = TestReconcilePaperOrder()._dispatched()
        return attempts

    def test_a_successful_request_moves_to_cancel_requested_not_canceled(self) -> None:
        # Asking to cancel is not a cancellation: the request races the venue.
        attempts = self._dispatched()
        result = CancelPaperOrderHandler(
            attempts=attempts,
            acknowledgements=FakeAcknowledgements(),
            events=FakeEvents(),
            broker=FakeBroker(cancel_status=204),
        ).handle(CancelPaperOrderCommand(intent_governance_id="INT-1", at=_NOW))
        assert result.state is PaperExecutionState.CANCEL_REQUESTED

    def test_a_refused_cancel_leaves_the_state_alone(self) -> None:
        attempts = self._dispatched()
        result = CancelPaperOrderHandler(
            attempts=attempts,
            acknowledgements=FakeAcknowledgements(),
            events=FakeEvents(),
            broker=FakeBroker(cancel_status=422),
        ).handle(CancelPaperOrderCommand(intent_governance_id="INT-1", at=_NOW))
        assert result.state is PaperExecutionState.PAPER_SUBMITTED

    def test_a_terminal_attempt_cannot_be_cancelled(self) -> None:
        attempts = self._dispatched()
        attempts.transition(attempt_id="ATT-1", target=PaperExecutionState.FILLED, at=_NOW)
        with pytest.raises(PaperExecutionRefusedError, match="already terminal"):
            CancelPaperOrderHandler(
                attempts=attempts,
                acknowledgements=FakeAcknowledgements(),
                events=FakeEvents(),
                broker=FakeBroker(),
            ).handle(CancelPaperOrderCommand(intent_governance_id="INT-1", at=_NOW))

    def test_an_attempt_with_no_broker_order_id_must_be_reconciled_first(self) -> None:
        preview = a_preview()
        authorizations = FakeAuthorizations()
        authorization = authorizations.save(
            authorize_submission(
                authorization_id="AUT-1",
                preview=preview,
                authorized_by="owner",
                authorized_at=_NOW,
                validity_seconds=300,
            )
        )
        attempts = FakeAttempts()
        attempts.claim_dispatch(
            attempt_id="ATT-1",
            authorization=authorization,
            request_fingerprint_now=authorization.request_fingerprint,
            account_reference_now=authorization.account_reference,
            claimed_at=_NOW,
        )
        with pytest.raises(PaperExecutionRefusedError, match="reconcile it first"):
            CancelPaperOrderHandler(
                attempts=attempts,
                acknowledgements=FakeAcknowledgements(),
                events=FakeEvents(),
                broker=FakeBroker(),
            ).handle(CancelPaperOrderCommand(intent_governance_id="INT-1", at=_NOW))

    def test_an_intent_with_no_attempt_is_not_found(self) -> None:
        with pytest.raises(NotFoundError):
            CancelPaperOrderHandler(
                attempts=FakeAttempts(),
                acknowledgements=FakeAcknowledgements(),
                events=FakeEvents(),
                broker=FakeBroker(),
            ).handle(CancelPaperOrderCommand(intent_governance_id="INT-1", at=_NOW))


class TestQueries:
    def test_an_untouched_intent_reports_not_dispatched(self) -> None:
        state = PaperExecutionStatusHandler(
            intents=FakeIntents(an_intent()),
            attempts=FakeAttempts(),
            authorizations=FakeAuthorizations(),
            previews=FakePreviews(),
        ).handle(PaperExecutionStatusQuery(intent_governance_id="INT-1"))
        assert state is PaperExecutionState.NOT_DISPATCHED

    def test_an_unknown_intent_is_refused_rather_than_called_not_dispatched(self) -> None:
        # The walkthrough found this: NOT_DISPATCHED about a nonexistent intent is a
        # confident answer to a question nobody asked.
        with pytest.raises(NotFoundError):
            PaperExecutionStatusHandler(
                intents=FakeIntents(),
                attempts=FakeAttempts(),
                authorizations=FakeAuthorizations(),
                previews=FakePreviews(),
            ).handle(PaperExecutionStatusQuery(intent_governance_id="INT-MISSING"))

    def test_a_stored_preview_reports_authorization_pending(self) -> None:
        previews = FakePreviews()
        previews.save(a_preview())
        state = PaperExecutionStatusHandler(
            intents=FakeIntents(an_intent()),
            attempts=FakeAttempts(),
            authorizations=FakeAuthorizations(),
            previews=previews,
        ).handle(PaperExecutionStatusQuery(intent_governance_id="INT-1"))
        assert state is PaperExecutionState.AUTHORIZATION_PENDING

    def test_an_unconsumed_authorization_reports_authorized(self) -> None:
        previews, authorizations = FakePreviews(), FakeAuthorizations()
        preview = previews.save(a_preview())
        authorizations.save(
            authorize_submission(
                authorization_id="AUT-1",
                preview=preview,
                authorized_by="owner",
                authorized_at=_NOW,
                validity_seconds=300,
            )
        )
        state = PaperExecutionStatusHandler(
            intents=FakeIntents(an_intent()),
            attempts=FakeAttempts(),
            authorizations=authorizations,
            previews=previews,
        ).handle(PaperExecutionStatusQuery(intent_governance_id="INT-1"))
        assert state is PaperExecutionState.AUTHORIZED

    def test_show_returns_the_whole_chain_and_renders(self) -> None:
        previews, authorizations = FakePreviews(), FakeAuthorizations()
        preview = previews.save(a_preview())
        authorizations.save(
            authorize_submission(
                authorization_id="AUT-1",
                preview=preview,
                authorized_by="owner",
                authorized_at=_NOW,
                validity_seconds=300,
            )
        )
        events = FakeEvents()
        events.append(
            PaperExecutionEvent(
                event_id="EVT-1",
                intent_governance_id="INT-1",
                attempt_id=None,
                event_type="PREVIEW_CREATED",
                occurred_at=_NOW,
                detail="v1",
            )
        )
        status = ShowPaperExecutionHandler(
            intents=FakeIntents(an_intent()),
            attempts=FakeAttempts(),
            authorizations=authorizations,
            previews=previews,
            acknowledgements=FakeAcknowledgements(),
            events=events,
        ).handle(ShowPaperExecutionQuery(intent_governance_id="INT-1"))
        assert status.state is PaperExecutionState.AUTHORIZED
        document = render_status_json(status)
        assert document["state"] == "AUTHORIZED"
        assert document["preview"] is not None
        assert document["attempt"] is None
        assert "PAPER EXECUTION HISTORY" in render_status_text(status)

    def test_show_refuses_an_unknown_intent(self) -> None:
        with pytest.raises(NotFoundError):
            ShowPaperExecutionHandler(
                intents=FakeIntents(),
                attempts=FakeAttempts(),
                authorizations=FakeAuthorizations(),
                previews=FakePreviews(),
                acknowledgements=FakeAcknowledgements(),
                events=FakeEvents(),
            ).handle(ShowPaperExecutionQuery(intent_governance_id="INT-MISSING"))

    def test_list_returns_recent_attempts(self) -> None:
        attempts, _ = TestReconcilePaperOrder()._dispatched()
        rows = ListPaperExecutionsHandler(attempts=attempts).handle(
            ListPaperExecutionsQuery(limit=10)
        )
        assert len(rows) == 1
        assert render_attempt_json(rows[0])["state"] == "PAPER_SUBMITTED"


class TestTheKillSwitchHandler:
    def test_engaging_reports_whether_it_changed_anything(self) -> None:
        kill_switch = FakeKillSwitch()
        handler = SetExecutionKillSwitchHandler(kill_switch=kill_switch)
        command = SetExecutionKillSwitchCommand(
            engaged=True, changed_by="owner", changed_at=_NOW, reason="test"
        )
        assert handler.handle(command) is True
        assert handler.handle(command) is False
        assert kill_switch.engaged is True

    def test_disengaging_reports_whether_it_changed_anything(self) -> None:
        kill_switch = FakeKillSwitch(engaged=True)
        handler = SetExecutionKillSwitchHandler(kill_switch=kill_switch)
        command = SetExecutionKillSwitchCommand(
            engaged=False, changed_by="owner", changed_at=_NOW, reason="test"
        )
        assert handler.handle(command) is True
        assert handler.handle(command) is False
        assert kill_switch.engaged is False


class TestTheRenderersRefuseFloats:
    def test_an_amount_that_is_not_a_decimal_is_refused(self) -> None:
        # A float would silently change what a limit price means.
        from empirical_platform.usecases.paper_execution_io import _money

        with pytest.raises(TypeError, match="never float"):
            _money(4.0)
        assert _money(None) is None
        assert _money(Decimal("4.00")) == "4.00"

    def test_an_acknowledgement_and_an_event_render(self) -> None:
        acknowledgement = BrokerAcknowledgement(
            acknowledgement_id="ACK-1",
            attempt_id="ATT-1",
            sequence=1,
            kind="SUBMIT",
            observed_at=_NOW,
            http_status=200,
            broker_order_id="broker-1",
            broker_status="accepted",
            client_order_id_echo="m085-x",
            payload_digest="c" * 64,
            sanitized_payload="{}",
        )
        assert render_acknowledgement_json(acknowledgement)["kind"] == "SUBMIT"
        event = PaperExecutionEvent(
            event_id="EVT-1",
            intent_governance_id="INT-1",
            attempt_id="ATT-1",
            event_type="PAPER_ORDER_SUBMITTED",
            occurred_at=_NOW,
            detail="broker_status=accepted",
        )
        assert render_event_json(event)["event_type"] == "PAPER_ORDER_SUBMITTED"


def test_entrypoint_composition_uses_the_injected_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    from contextlib import contextmanager
    from types import SimpleNamespace

    from empirical_platform.entrypoints import preview_paper_submission as preview_cli
    from empirical_platform.entrypoints import submit_authorized_paper_order as submit_cli
    from empirical_platform.shared.brokerage.paper_time import (
        PaperTimeReading,
        SystemPaperTimeSource,
    )

    class Clock(SystemPaperTimeSource):
        reads = 0

        def read(self) -> PaperTimeReading:
            self.reads += 1
            return super().read()

    clock = Clock()
    helper = TestSubmitAuthorizedPaperOrder()
    world = helper._world()
    context = SimpleNamespace(
        m084=SimpleNamespace(approved_order_intents=world["intents"]),
        paper=SimpleNamespace(
            paper_account_snapshots=world["snapshots"],
            submission_previews=world["previews"],
            execution_authorizations=world["authorizations"],
            execution_attempts=world["attempts"],
            broker_acknowledgements=world["acknowledgements"],
            paper_execution_events=world["events"],
            execution_kill_switch=world["kill_switch"],
        ),
        broker=world["broker"],
        market_data=world["market_data"],
        time_source=clock,
    )

    @contextmanager
    def runtime(config: object) -> Iterator[SimpleNamespace]:
        yield context

    monkeypatch.setattr(preview_cli, "paper_execution_runtime", runtime)
    monkeypatch.setattr(submit_cli, "paper_execution_runtime", runtime)
    preview = preview_cli.run_preview_paper_submission(
        intent_governance_id="INT-1",
        preview_id="PVW-1",
        snapshot_id="SNP-1",
        maximum_notional=Decimal("5"),
        quote_maximum_age_seconds=60,
        approved_watchlist=frozenset({"AAPL"}),
    )
    assert preview.is_authorizable
    assert clock.reads > 0
    preview_reads = clock.reads
    AuthorizePaperSubmissionHandler(
        previews=world["previews"],
        authorizations=world["authorizations"],
        events=world["events"],
    ).handle(
        AuthorizePaperSubmissionCommand(
            authorization_id="AUT-1",
            preview_id="PVW-1",
            expected_request_fingerprint=preview.request_fingerprint,
            authorized_by="test-fixture",
            authorized_at=_NOW,
            validity_seconds=60,
        )
    )
    result = submit_cli.run_submit_authorized_paper_order(
        intent_governance_id="INT-1",
        attempt_id="ATT-1",
        snapshot_id="SNP-2",
        maximum_notional=Decimal("5"),
        quote_maximum_age_seconds=60,
        approved_watchlist=frozenset({"AAPL"}),
    )
    assert clock.reads > preview_reads
    assert result.dispatched and len(world["broker"].submitted) == 1
