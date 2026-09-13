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

from collections.abc import Callable, Iterator
from dataclasses import replace
from datetime import datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
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
    FakeClock,
    FakeEvents,
    FakeIntents,
    FakeKillSwitch,
    FakeMarketData,
    FakePreviews,
    FakeQuote,
    FakeSnapshots,
    FakeTimeBases,
    FakeView,
    a_preview,
    a_provenance,
    a_time_basis,
    an_intent,
    an_intent_time_basis,
    time_bases_for,
)

from empirical_platform.decision_candidate.paper_execution import (
    PAPER_ENDPOINT_HOST,
    BrokerAcknowledgement,
    DecisionTimeBasis,
    ExecutionAttempt,
    ExecutionAuthorization,
    IntentTimeBasis,
    PaperExecutionEvent,
    PaperExecutionState,
    ProposalTimeBasis,
    SubmissionPreview,
    authorize_submission,
)
from empirical_platform.shared.brokerage.alpaca_paper import (
    BrokerAmbiguousDispatchError,
    BrokerNotSentError,
)
from empirical_platform.shared.brokerage.paper_time import (
    PaperTimeReading,
    PaperTimeSource,
    PaperTimeUncertainError,
)
from empirical_platform.usecases import paper_execution as paper_execution_usecases
from empirical_platform.usecases.decision_to_approval import (
    DecideTradeProposalCommand,
    IssueApprovedOrderIntentCommand,
    NotFoundError,
    OperatorAction,
    PrepareTradeProposalCommand,
)
from empirical_platform.usecases.paper_execution import (
    AuthorizePaperSubmissionCommand,
    AuthorizePaperSubmissionHandler,
    CancelPaperOrderCommand,
    CancelPaperOrderHandler,
    DecidePaperBoundTradeProposalCommand,
    DecidePaperBoundTradeProposalHandler,
    InspectPaperAccountCommand,
    InspectPaperAccountHandler,
    IssuePaperBoundOrderIntentCommand,
    IssuePaperBoundOrderIntentHandler,
    ListPaperExecutionsHandler,
    ListPaperExecutionsQuery,
    M084TimeProvenance,
    PaperExecutionRefusedError,
    PaperExecutionStatusHandler,
    PaperExecutionStatusQuery,
    PreparePaperBoundTradeProposalCommand,
    PreparePaperBoundTradeProposalHandler,
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


class _ScriptedTime:
    """A host clock whose wall and monotonic readings move only when told to."""

    def __init__(self, utc: datetime) -> None:
        self.utc = utc
        self.monotonic = 0.0

    def read(self) -> PaperTimeReading:
        return PaperTimeReading(self.utc, self.monotonic)

    def advance(self, seconds: float) -> None:
        self.utc += timedelta(seconds=seconds)
        self.monotonic += seconds


class _SlowClockBroker(FakeBroker):
    """A truthful broker clock that takes `delay` seconds to answer.

    The broker stamps its reply as it sends it, so the timestamp is the true time at
    the END of the round trip -- the case in which pairing it with a host reading
    taken BEFORE the request adds the whole delay to the mapping.
    """

    def __init__(self, time: _ScriptedTime, *, delay: float) -> None:
        super().__init__()
        self.time = time
        self.delay = delay

    def fetch_clock(self) -> FakeClock:
        self.time.advance(self.delay)
        clock = FakeClock()
        clock.timestamp = self.time.utc
        return clock


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
        intents = fakes.get("intents") or FakeIntents(an_intent())
        return PreviewPaperSubmissionHandler(
            intents=intents,  # type: ignore[arg-type]
            time_bases=fakes.get("time_bases")  # type: ignore[arg-type]
            or time_bases_for(
                *(a_provenance(row) for row in intents.rows.values())  # type: ignore[attr-defined]
            ),
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
        assert any("dated after the latest possible" in reason for reason in preview.refusals)

    def test_an_intent_expiring_during_the_fetch_is_refused(
        self, operation_clock: FrozenDateTimeFactory
    ) -> None:
        # The evaluation instant must be read AFTER the evidence is fetched. The
        # command's own timestamp was taken before the account, clock, asset,
        # position and quote round trips; using it would forgive every second
        # those took. Here the intent expires during the fetch, so only a
        # post-fetch instant can refuse it.
        class SlowData(FakeMarketData):
            def fetch_quote(self, symbol: str) -> object:
                operation_clock.tick(delta=timedelta(seconds=4))
                return FakeQuote()

        intent = an_intent(expires_at=_NOW + timedelta(seconds=2))
        preview = self._handler(
            intents=FakeIntents(intent),
            # Evaluated while this host ran an hour BEHIND the broker, so on the broker's
            # clock the intent expires an hour later and ONLY the post-fetch host
            # instant can refuse it. With host == broker the broker-timeline check on
            # the proposal's basis refuses the same intent, and this test passed with
            # `evaluated_at` taken before the fetch (mutation campaign, post_fetch_time).
            time_bases=time_bases_for(a_provenance(intent, proposal_offset=timedelta(hours=1))),
            market_data=SlowData(),
        ).handle(self._command())
        assert preview.is_authorizable is False
        assert "the approved intent has expired" in preview.refusals
        assert not any("on the broker's clock" in reason for reason in preview.refusals)

    def test_the_preview_version_comes_from_stored_rows(self) -> None:
        previews = FakePreviews()
        handler = self._handler(previews=previews)
        first = handler.handle(self._command())
        second = handler.handle(self._command(preview_id="PVW-2"))
        assert (first.preview_version, second.preview_version) == (1, 2)


class TestAuthorizePaperSubmission:
    def _handler(self, previews: FakePreviews, authorizations: FakeAuthorizations):  # noqa: ANN202
        return AuthorizePaperSubmissionHandler(
            previews=previews,
            authorizations=authorizations,
            events=FakeEvents(),
            broker=FakeBroker(),
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
        if "time_bases" not in overrides:
            # Evidence for whichever intents THIS world holds, issued with the host
            # and broker clocks agreeing. A test that wants a different issuance
            # offset, or none, says so explicitly.
            world["time_bases"] = time_bases_for(
                *(a_provenance(intent) for intent in world["intents"].rows.values())
            )
        return world

    def _authorize(
        self, world: dict[str, Any], *, validity_seconds: int = 300
    ) -> ExecutionAuthorization:
        preview = PreviewPaperSubmissionHandler(
            intents=world["intents"],
            time_bases=world["time_bases"],
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
            # The world's own broker, so a test that changes the clock changes
            # the basis this authorization is bound to.
            broker=world["broker"],
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

    def _handler(
        self, world: dict[str, Any], *, time_source: PaperTimeSource | None = None
    ) -> SubmitAuthorizedPaperOrderHandler:
        return SubmitAuthorizedPaperOrderHandler(
            time_source=time_source,
            intents=world["intents"],
            time_bases=world["time_bases"],
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

    def test_a_deadline_crossed_during_a_database_lock_wait_never_submits(self) -> None:
        # The claim is where a contended row makes a process WAIT. Time spent
        # waiting must age the evidence: the claim re-reads the clock through
        # `claim_clock`, so an authorization that expires during the wait is
        # refused there, with nothing sent.
        with freeze_time(_NOW) as clock:
            world = self._world()
            self._authorize(world, validity_seconds=1)
            original = world["attempts"].claim_dispatch

            def contended_claim(**kwargs: object) -> object:
                clock.tick(delta=timedelta(seconds=5))
                return original(**kwargs)

            world["attempts"].claim_dispatch = contended_claim
            with pytest.raises((PaperExecutionRefusedError, ValueError), match="expired"):
                self._handler(world).handle(self._command())
            assert world["broker"].submitted == []

    def _dispatch_in_a_new_process(
        self,
        world: dict[str, Any],
        *,
        host_now: object,
        broker_time: datetime | None = None,
    ) -> object:
        """Dispatch as a FRESH process would: no monotonic memory of the approval.

        `broker_time` is what the broker's clock says -- real elapsed time, which
        a host clock step cannot alter. `host_now` is what THIS machine believes.
        Driving the two independently is the whole point: the dangerous case is
        real time passing while the host clock disagrees.
        """
        broker_time = _NOW if broker_time is None else broker_time
        original_clock = world["broker"].fetch_clock

        def truthful_broker_clock() -> object:
            value = original_clock()
            value.timestamp = broker_time
            value.next_close = broker_time + timedelta(hours=2)
            return value

        class TruthfulQuote(FakeQuote):
            captured_at = broker_time - timedelta(seconds=5)

        world["broker"].fetch_clock = truthful_broker_clock
        world["market_data"] = FakeMarketData(quote=TruthfulQuote())
        with freeze_time(host_now):
            return self._handler(world).handle(self._command())

    def test_a_backward_host_clock_step_between_processes_cannot_extend_an_approval(
        self,
    ) -> None:
        # THE CROSS-PROCESS DEFECT. An hour of REAL time passes -- the broker's
        # clock proves it -- but the approving process has exited and the host
        # clock has stepped back, so the stored host expiry still looks far away
        # and monotonic time has no memory to contradict it. Without the broker
        # basis this dispatched a 300-second permission an hour late.
        world = self._world()
        self._authorize(world, validity_seconds=300)
        with pytest.raises(PaperExecutionRefusedError, match="expired"):
            self._dispatch_in_a_new_process(
                world,
                host_now=_NOW - timedelta(hours=1),
                # Ten minutes of real broker time: past the 300-second approval,
                # but well inside the intent's one-hour expiry, so ONLY the
                # approval rule can produce this refusal.
                broker_time=_NOW + timedelta(minutes=10),
            )
        assert world["broker"].submitted == []
        assert world["attempts"].rows == {}

    def test_a_backward_host_clock_step_cannot_extend_the_m084_intent_deadline(self) -> None:
        # The same attack against MILESTONE-084's deadline rather than M085's own.
        # M084's stored value is frozen and untouched; it is additionally placed on
        # the broker timeline using the basis measured when the human authorized,
        # so real elapsed time expires it even though the host clock says otherwise.
        world = self._world(intents=FakeIntents(an_intent(expires_at=_NOW + timedelta(minutes=10))))
        self._authorize(world, validity_seconds=7200)
        with pytest.raises(PaperExecutionRefusedError, match="expired"):
            self._dispatch_in_a_new_process(
                world,
                host_now=_NOW - timedelta(hours=1),
                broker_time=_NOW + timedelta(minutes=30),
            )
        assert world["broker"].submitted == []
        assert world["attempts"].rows == {}

    def test_a_forward_host_clock_step_between_processes_still_expires_the_approval(
        self,
    ) -> None:
        # The safe direction must stay safe: a host clock jumped forward past the
        # expiry must refuse, and must not be rescued by the broker basis either.
        world = self._world()
        self._authorize(world, validity_seconds=300)
        with pytest.raises(PaperExecutionRefusedError, match="expired|uncertain|clock"):
            self._dispatch_in_a_new_process(world, host_now=_NOW + timedelta(hours=1))
        assert world["broker"].submitted == []
        assert world["attempts"].rows == {}

    def test_an_unmoved_host_clock_in_a_new_process_still_dispatches(self) -> None:
        # The guard must not break the ordinary case: a restart with a correct
        # clock, inside the validity window, still dispatches exactly once.
        world = self._world()
        self._authorize(world, validity_seconds=300)
        result = self._dispatch_in_a_new_process(world, host_now=_NOW + timedelta(seconds=5))
        assert result.dispatched is True  # type: ignore[attr-defined]
        assert len(world["broker"].submitted) == 1

    def test_an_interval_crossing_the_approval_expiry_refuses_the_submission(self) -> None:
        # The authorization expiry was written by THIS host's clock, so it is
        # judged on the host timeline -- and on the CONSERVATIVE end of it. An
        # operation whose uncertainty straddles the expiry is refused rather
        # than resolved in favour of sending.
        with freeze_time(_NOW) as clock:
            world = self._world()
            self._authorize(world, validity_seconds=2)
            original = world["market_data"].fetch_quote

            def straddling_fetch(symbol: str) -> object:
                # Elapsed work carries the operation across the expiry instant.
                clock.tick(delta=timedelta(seconds=3))
                return original(symbol)

            world["market_data"].fetch_quote = straddling_fetch
            with pytest.raises(PaperExecutionRefusedError, match="expired"):
                self._handler(world).handle(self._command())
            assert world["broker"].submitted == []
            assert world["attempts"].rows == {}

    def test_a_deadline_crossed_during_connection_preparation_never_submits(self) -> None:
        # Connecting takes time, and the pre-send guard runs AFTER connect. An
        # authorization that was valid when the claim was taken but has expired
        # by the time the socket is up must stop the order at the guard.
        with freeze_time(_NOW) as clock:
            world = self._world()
            self._authorize(world, validity_seconds=60)
            original = world["broker"].submit_order

            def slow_connect(
                order: object, *, before_send: Callable[[], None] | None = None
            ) -> tuple[int, object | None, str]:
                def guard() -> None:
                    clock.tick(delta=timedelta(seconds=120))
                    if before_send is not None:
                        before_send()

                return original(order, before_send=guard)

            world["broker"].submit_order = slow_connect
            result = self._handler(world).handle(self._command())
            assert result.dispatched is False
            assert world["broker"].submitted == []

    def test_a_market_close_crossed_during_preparation_never_submits(self) -> None:
        # The session close is the BROKER's deadline, so it is judged on the
        # broker timeline. A close that might already have passed counts as
        # passed, and nothing is sent.
        with freeze_time(_NOW) as clock:
            world = self._world()
            self._authorize(world)

            original_clock = world["broker"].fetch_clock

            def closing_soon() -> object:
                value = original_clock()
                value.next_close = _NOW + timedelta(seconds=30)
                return value

            world["broker"].fetch_clock = closing_soon
            original = world["broker"].submit_order

            def slow_connect(
                order: object, *, before_send: Callable[[], None] | None = None
            ) -> tuple[int, object | None, str]:
                def guard() -> None:
                    clock.tick(delta=timedelta(seconds=90))
                    if before_send is not None:
                        before_send()

                return original(order, before_send=guard)

            world["broker"].submit_order = slow_connect
            result = self._handler(world).handle(self._command())
            assert result.dispatched is False
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
            short_lived = an_intent(expires_at=_NOW + timedelta(seconds=1))
            world["intents"].rows["INT-1"] = short_lived
            # Its evidence must describe THIS intent, or dispatch is refused up front
            # for mismatched evidence and the elapsed-time rule is never reached
            # (mutation campaign, final_intent_expiry).
            world["time_bases"] = time_bases_for(a_provenance(short_lived))
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
        except ValueError as refused:
            # A refusal about the time-basis evidence would mean the setup, not the
            # elapsed deadline, refused this dispatch.
            assert "time broker basis" not in str(refused), refused
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

    def test_a_host_broker_clock_difference_alone_does_not_refuse(self) -> None:
        # THE CORRECTED RULE. The replaced model refused here, because a broker
        # reading outside the local request interval meant "the two clocks do not
        # appear to agree". Apparent agreement was never the safety property. What
        # matters is that every deadline still holds across the bounded
        # uncertainty, and at a one-second difference every one of them does.
        world = self._world()
        self._authorize(world)
        original = world["broker"].fetch_clock

        def offset_clock() -> object:
            value = original()
            value.timestamp = _NOW + timedelta(seconds=1)
            return value

        world["broker"].fetch_clock = offset_clock
        result = self._handler(world).handle(self._command())
        assert result.dispatched
        assert len(world["broker"].submitted) == 1

    def test_broker_time_too_uncertain_to_decide_freshness_refuses_before_claim(self) -> None:
        # The uncertainty bound is not a chosen constant: it is the MEASURED round
        # trip. When that round trip is not smaller than the freshness ceiling the
        # evidence cannot tell a fresh quote from a stale one, so it is refused --
        # before anything is claimed and before anything is sent.
        class SlowRoundTrip:
            def __init__(self) -> None:
                self.monotonic = 0.0

            def read(self) -> PaperTimeReading:
                self.monotonic += 90.0
                return PaperTimeReading(_NOW, self.monotonic)

        world = self._world()
        self._authorize(world)
        with pytest.raises(PaperTimeUncertainError, match="uncertain"):
            self._handler(world, time_source=SlowRoundTrip()).handle(self._command())
        assert world["broker"].submitted == []
        assert world["attempts"].rows == {}

    # -- the two time bases ------------------------------------------------

    def _preview(self, world: dict[str, Any]) -> SubmissionPreview:
        preview = PreviewPaperSubmissionHandler(
            intents=world["intents"],
            time_bases=world["time_bases"],
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
        return preview

    def _authorize_with(
        self,
        world: dict[str, Any],
        preview: SubmissionPreview,
        *,
        broker: object,
        authorized_at: datetime,
        validity_seconds: int,
        time_source: PaperTimeSource | None = None,
    ) -> ExecutionAuthorization:
        return AuthorizePaperSubmissionHandler(
            previews=world["previews"],
            authorizations=world["authorizations"],
            events=world["events"],
            broker=broker,  # type: ignore[arg-type]
            time_source=time_source,
        ).handle(
            AuthorizePaperSubmissionCommand(
                authorization_id="AUT-1",
                preview_id=preview.preview_id,
                expected_request_fingerprint=preview.request_fingerprint,
                authorized_by="owner",
                authorized_at=authorized_at,
                validity_seconds=validity_seconds,
            )
        )

    @staticmethod
    def _broker_clock_reads(world: dict[str, Any], at: datetime) -> None:
        def truthful() -> FakeClock:
            clock = FakeClock()
            clock.timestamp = at
            return clock

        world["broker"].fetch_clock = truthful

    def test_broker_fetch_latency_cannot_extend_the_authorization_deadline(self) -> None:
        # DEFECT 1, REPRODUCED AT ddce3c8 BEFORE THE FIX. The entrypoint stamps
        # `authorized_at`, then the handler reads the broker clock. With a 120 s
        # fetch the stored pair was (authorized_at, broker reply): a 300 s approval
        # mapped to 420 s, and this very dispatch was PERMITTED ("DID NOT RAISE").
        world = self._world()
        preview = self._preview(world)
        time = _ScriptedTime(_NOW)
        authorization = self._authorize_with(
            world,
            preview,
            broker=_SlowClockBroker(time, delay=120),
            time_source=time,
            authorized_at=_NOW,
            validity_seconds=300,
        )
        # The interval is recorded; the host reading the mapping uses is the later one.
        assert authorization.basis_host_requested_at == _NOW
        assert authorization.basis_host_at == _NOW + timedelta(seconds=120)
        assert authorization.basis_broker_earliest_at == _NOW + timedelta(seconds=120)
        assert authorization.on_broker_timeline(authorization.expires_at) <= _NOW + timedelta(
            seconds=300
        )
        # A new process 350 s of real time later, with the host clock an hour behind.
        with pytest.raises(
            PaperExecutionRefusedError, match="authorization has expired on the broker"
        ):
            self._dispatch_in_a_new_process(
                world,
                host_now=_NOW + timedelta(seconds=350) - timedelta(hours=1),
                broker_time=_NOW + timedelta(seconds=350),
            )
        assert world["broker"].submitted == []
        assert world["attempts"].rows == {}

    def _authorized_after_a_backward_host_step(
        self, *, validity_seconds: int
    ) -> tuple[dict[str, Any], ExecutionAuthorization]:
        # 1. The M084 intent is issued with host and broker agreeing (offset A = 0).
        intent = an_intent(
            created_at=_NOW - timedelta(minutes=1), expires_at=_NOW + timedelta(minutes=10)
        )
        world = self._world(intents=FakeIntents(intent))
        self._broker_clock_reads(world, _NOW)
        # 2. The host clock moves back an hour. 3. Authorization under offset B.
        with freeze_time(_NOW - timedelta(hours=1)):
            preview = self._preview(world)
            authorization = self._authorize_with(
                world,
                preview,
                broker=world["broker"],
                authorized_at=_NOW - timedelta(hours=1),
                validity_seconds=validity_seconds,
            )
        return world, authorization

    def test_a_host_clock_moved_between_intent_and_authorization_cannot_extend_the_m084_deadline(
        self,
    ) -> None:
        # DEFECT 2, REPRODUCED AT ddce3c8 BEFORE THE FIX: the M084 deadline was
        # translated through the authorization's basis, landed an hour late, and
        # this dispatch after the real deadline was PERMITTED ("DID NOT RAISE").
        world, authorization = self._authorized_after_a_backward_host_step(validity_seconds=7200)
        intent = world["intents"].rows["INT-1"]
        assert authorization.on_broker_timeline(intent.expires_at) == intent.expires_at + timedelta(
            hours=1
        ), "the borrowed mapping is the defect; it must not be the one enforced"
        # 4. A new dispatch process 30 min of real time later, host still behind.
        with pytest.raises(PaperExecutionRefusedError, match="intent has expired on the broker"):
            self._dispatch_in_a_new_process(
                world,
                host_now=_NOW - timedelta(minutes=30),
                broker_time=_NOW + timedelta(minutes=30),
            )
        assert world["broker"].submitted == []
        assert world["attempts"].rows == {}

    def test_the_same_offset_change_still_dispatches_before_the_real_m084_deadline(self) -> None:
        world, _ = self._authorized_after_a_backward_host_step(validity_seconds=7200)
        result = self._dispatch_in_a_new_process(
            world,
            host_now=_NOW - timedelta(minutes=55),
            broker_time=_NOW + timedelta(minutes=5),
        )
        assert result.dispatched is True  # type: ignore[attr-defined]
        assert len(world["broker"].submitted) == 1

    def test_a_host_clock_ahead_only_while_authorizing_cannot_extend_the_authorization(
        self,
    ) -> None:
        # The provenance separation in the other direction. The intent's basis says
        # host == broker; the authorization was taken with the host an hour AHEAD.
        # Mapping the authorization's expiry through the intent's basis would add
        # that hour back and permit this dispatch.
        intent = an_intent(
            expires_at=_NOW + timedelta(hours=3),
            mandatory_liquidation_at=_NOW + timedelta(hours=4),
        )
        world = self._world(intents=FakeIntents(intent))
        self._broker_clock_reads(world, _NOW)
        with freeze_time(_NOW + timedelta(hours=1)):
            preview = self._preview(world)
            self._authorize_with(
                world,
                preview,
                broker=world["broker"],
                authorized_at=_NOW + timedelta(hours=1),
                validity_seconds=300,
            )
        with pytest.raises(
            PaperExecutionRefusedError, match="authorization has expired on the broker"
        ):
            self._dispatch_in_a_new_process(
                world,
                host_now=_NOW + timedelta(minutes=10),
                broker_time=_NOW + timedelta(minutes=10),
            )
        assert world["broker"].submitted == []
        assert world["attempts"].rows == {}

    def test_an_intent_without_its_own_basis_is_refused_before_any_broker_call(self) -> None:
        world = self._world()
        self._authorize(world)
        world["time_bases"].intents.clear()
        reads: list[str] = []
        original = world["broker"].fetch_account

        def counted() -> tuple[int, dict[str, object]]:
            reads.append("account")
            return original()  # type: ignore[no-any-return]

        world["broker"].fetch_account = counted
        with pytest.raises(PaperExecutionRefusedError, match="no intent-time broker basis"):
            self._handler(world).handle(self._command())
        assert reads == []
        assert world["broker"].submitted == []
        assert world["attempts"].rows == {}

    @pytest.mark.parametrize(
        "change",
        [
            {"approved_fingerprint": "b" * 64},
            {"created_at": _NOW - timedelta(minutes=2)},
            {"expires_at": _NOW + timedelta(hours=2)},
            {"mandatory_liquidation_at": _NOW + timedelta(hours=4)},
        ],
        ids=["fingerprint", "created_at", "expires_at", "mandatory_liquidation_at"],
    )
    def test_evidence_describing_a_different_intent_is_refused(
        self, change: dict[str, object]
    ) -> None:
        world = self._world()
        self._authorize(world)
        world["time_bases"].intents["INT-1"] = an_intent_time_basis(an_intent(**change))
        with pytest.raises(PaperExecutionRefusedError, match="does not describe this exact intent"):
            self._handler(world).handle(self._command())
        assert world["broker"].submitted == []
        assert world["attempts"].rows == {}

    @pytest.mark.parametrize("phase", ["fetch", "claim", "prepare", "connect"])
    def test_an_m084_deadline_passing_only_on_the_broker_clock_never_submits(
        self, operation_clock: FrozenDateTimeFactory, phase: str
    ) -> None:
        # Evaluated while this host ran an hour AHEAD of the broker, so the stored host
        # expiry (_NOW+1h+1s) is _NOW+1s on the broker's clock. The host clock is now
        # correct: every host-timeline check passes throughout, and only the proposal's
        # basis can refuse -- during the fetch, the claim (the database lock wait
        # in production), preparation, or the connection.
        intent = an_intent(expires_at=_NOW + timedelta(hours=1, seconds=1))
        world = self._world(
            intents=FakeIntents(intent),
            time_bases=time_bases_for(a_provenance(intent, proposal_offset=timedelta(hours=-1))),
        )
        self._authorize(world)
        target, method = {
            "fetch": (world["market_data"], "fetch_quote"),
            "claim": (world["attempts"], "claim_dispatch"),
            "prepare": (world["attempts"], "transition"),
            "connect": (world["broker"], "submit_order"),
        }[phase]
        original = getattr(target, method)

        def delayed(*args: object, **kwargs: object) -> object:
            operation_clock.tick(delta=timedelta(seconds=2))
            return original(*args, **kwargs)

        setattr(target, method, delayed)
        try:
            result = self._handler(world).handle(self._command())
        except PaperExecutionRefusedError as refused:
            assert phase == "fetch", refused
            assert "intent has expired on the broker" in str(refused)
        else:
            assert phase != "fetch"
            assert result.dispatched is False
            assert result.attempt.state is PaperExecutionState.REJECTED
            assert "intent has expired on the broker" in (result.attempt.failure_detail or "")
            assert self._handler(world).handle(self._command()).dispatched is False
        assert world["broker"].submitted == []


def _stand_in_m084(intent: object) -> tuple[SimpleNamespace, SimpleNamespace, M084TimeProvenance]:
    """A stored proposal and approval, and the evidence their Paper-bound acts recorded.

    Stand-ins for the M084 repositories: the domain objects M084 would return carry
    exactly these attributes. The real M084 handlers and repositories are exercised
    through PostgreSQL in `tests/integration/test_m085_time_basis_postgres.py`.
    """
    provenance = a_provenance(intent)  # type: ignore[arg-type]
    assert provenance.proposal is not None and provenance.decision is not None
    proposal = SimpleNamespace(
        proposal_governance_id=provenance.proposal.proposal_governance_id,
        proposal_version=provenance.proposal.proposal_version,
        content_fingerprint=provenance.proposal.content_fingerprint,
        created_at=provenance.proposal.proposal_created_at,
        expires_at=provenance.proposal.proposal_expires_at,
        mandatory_liquidation_at=provenance.proposal.mandatory_liquidation_at,
    )
    decision = SimpleNamespace(
        decision_governance_id=provenance.decision.decision_governance_id,
        proposal_governance_id=provenance.decision.proposal_governance_id,
        proposal_version=provenance.decision.proposal_version,
        approved_fingerprint=provenance.decision.approved_fingerprint,
        decided_at=provenance.decision.decided_at,
        expires_at=provenance.decision.decision_expires_at,
    )
    return proposal, decision, provenance


class TestIssuePaperBoundOrderIntent:
    """The M085 issuance composition, with M084's own handler stood in for.

    The real M084 handler, real repositories and real PostgreSQL are exercised by
    `tests/integration/test_m085_time_basis_postgres.py`. Here the question is only
    the composition: what is required, what is measured, in what order, and what is
    refused BEFORE M084 writes anything.
    """

    _TEMPLATE = an_intent()

    def _handler(
        self,
        monkeypatch: pytest.MonkeyPatch,
        *,
        intents: FakeIntents,
        bases: FakeTimeBases | None = None,
        broker: object,
        time_source: PaperTimeSource | None = None,
        provenance: M084TimeProvenance | None = None,
    ) -> tuple[IssuePaperBoundOrderIntentHandler, list[object], FakeTimeBases]:
        issued: list[object] = []
        proposal, decision, recorded = _stand_in_m084(self._TEMPLATE)
        chosen = recorded if provenance is None else provenance
        store = bases if bases is not None else time_bases_for(replace(chosen, intent=None))

        class StandInM084Issuance:
            def __init__(self, **repositories: object) -> None:
                del repositories

            def handle(self, command: IssueApprovedOrderIntentCommand) -> object:
                issued.append(command)
                intent = an_intent(
                    intent_governance_id=command.intent_governance_id,
                    created_at=command.created_at,
                )
                intents.rows[intent.intent_governance_id] = intent
                return intent

        monkeypatch.setattr(
            paper_execution_usecases, "IssueApprovedOrderIntentHandler", StandInM084Issuance
        )
        handler = IssuePaperBoundOrderIntentHandler(
            approval_decisions=SimpleNamespace(for_proposal=lambda _id: decision),  # type: ignore[arg-type]
            intents=intents,  # type: ignore[arg-type]
            proposals=SimpleNamespace(get=lambda _id: proposal),  # type: ignore[arg-type]
            time_bases=store,  # type: ignore[arg-type]
            broker=broker,  # type: ignore[arg-type]
            time_source=time_source,
        )
        return handler, issued, store

    _COMMAND = IssuePaperBoundOrderIntentCommand(
        intent_governance_id="INT-1", proposal_governance_id="PRP-1", idempotency_key="IDEM-1"
    )

    def test_the_intent_is_issued_at_the_host_reading_taken_after_the_clock_response(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        time = _ScriptedTime(_NOW)
        broker = _SlowClockBroker(time, delay=120)
        intents = FakeIntents()
        handler, issued, bases = self._handler(
            monkeypatch, intents=intents, broker=broker, time_source=time
        )
        result = handler.handle(self._COMMAND)
        assert [command.created_at for command in issued] == [_NOW + timedelta(seconds=120)]  # type: ignore[attr-defined]
        evidence = bases.intents["INT-1"]
        assert evidence is result.time_basis
        assert evidence.basis_host_requested_at == _NOW
        assert evidence.basis_host_at == result.intent.created_at == _NOW + timedelta(seconds=120)
        assert evidence.basis_broker_latest_at == evidence.basis_broker_earliest_at + timedelta(
            seconds=120
        )
        assert broker.submitted == [], "issuing reads the clock and places nothing"

    def test_an_existing_intent_is_refused_and_no_basis_is_attached_to_it(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        broker = FakeBroker()
        reads: list[str] = []
        broker.fetch_clock = lambda: reads.append("clock") or FakeClock()  # type: ignore[method-assign]
        intents = FakeIntents(an_intent())
        handler, issued, bases = self._handler(monkeypatch, intents=intents, broker=broker)
        with pytest.raises(PaperExecutionRefusedError, match="never attached"):
            handler.handle(self._COMMAND)
        assert issued == [] and bases.intents == {} and reads == []

    @pytest.mark.parametrize(
        ("missing", "fragment"),
        [
            ("proposal", "no proposal-time broker basis"),
            ("decision", "no decision-time broker basis"),
        ],
    )
    def test_a_proposal_or_approval_without_its_own_basis_is_refused_before_m084_writes(
        self, monkeypatch: pytest.MonkeyPatch, missing: str, fragment: str
    ) -> None:
        # A proposal evaluated, or an approval recorded, through M084 alone. No basis is
        # borrowed from issuance and none is derived now.
        _, _, recorded = _stand_in_m084(self._TEMPLATE)
        broker = FakeBroker()
        reads: list[str] = []
        broker.fetch_clock = lambda: reads.append("clock") or FakeClock()  # type: ignore[method-assign]
        intents = FakeIntents()
        handler, issued, bases = self._handler(
            monkeypatch,
            intents=intents,
            broker=broker,
            provenance=replace(recorded, **{missing: None}),
        )
        with pytest.raises(PaperExecutionRefusedError, match=fragment):
            handler.handle(self._COMMAND)
        assert issued == [] and intents.rows == {} and bases.intents == {} and reads == []

    def test_a_proposal_that_expired_on_the_broker_clock_cannot_be_issued(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # THE INDEPENDENT REVIEW'S PATH, AT ISSUANCE. Proposal and approval recorded
        # with host and broker agreeing (the stand-in's evidence, offset 0). Real broker
        # time is now an hour past the proposal's expiry while this host's clock reads
        # barely past its creation, so M084's host-clock checks would all pass.
        _, _, recorded = _stand_in_m084(self._TEMPLATE)
        assert recorded.proposal is not None
        host_now = recorded.proposal.proposal_created_at + timedelta(seconds=30)
        broker_now = recorded.proposal.proposal_expires_at + timedelta(hours=1)

        def truthful() -> FakeClock:
            clock = FakeClock()
            clock.timestamp = broker_now
            return clock

        broker = FakeBroker()
        broker.fetch_clock = truthful  # type: ignore[method-assign]
        intents = FakeIntents()
        handler, issued, bases = self._handler(
            monkeypatch, intents=intents, broker=broker, time_source=_ScriptedTime(host_now)
        )
        with pytest.raises(
            PaperExecutionRefusedError,
            match="the proposal had expired on the broker's clock when the intent was issued",
        ):
            handler.handle(self._COMMAND)
        assert issued == [], "M084 must not write an intent for an expired proposal"
        assert intents.rows == {} and bases.intents == {}
        assert broker.submitted == []

    def test_a_crash_before_the_evidence_is_recorded_leaves_the_intent_undispatchable(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _, _, recorded = _stand_in_m084(self._TEMPLATE)

        class FailingBases(FakeTimeBases):
            def record_intent(self, evidence: IntentTimeBasis) -> IntentTimeBasis:
                raise RuntimeError("the process died here")

        assert recorded.proposal is not None and recorded.decision is not None
        bases = FailingBases(proposals=(recorded.proposal,), decisions=(recorded.decision,))
        intents = FakeIntents()
        handler, _, _ = self._handler(
            monkeypatch, intents=intents, bases=bases, broker=FakeBroker()
        )
        with pytest.raises(RuntimeError, match="died"):
            handler.handle(self._COMMAND)
        assert "INT-1" in intents.rows and bases.intents == {}
        preview = PreviewPaperSubmissionHandler(
            intents=intents,
            time_bases=bases,
            snapshots=FakeSnapshots(),
            previews=FakePreviews(),
            events=FakeEvents(),
            broker=FakeBroker(),
            market_data=FakeMarketData(),
            kill_switch=FakeKillSwitch(),
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
        assert preview.is_authorizable is False
        assert any("no intent-time broker basis" in reason for reason in preview.refusals)


class TestPreparePaperBoundTradeProposal:
    """The evaluation composition, with M084's own evaluation stood in for."""

    def _handler(
        self,
        monkeypatch: pytest.MonkeyPatch,
        *,
        broker: object,
        time_source: PaperTimeSource | None = None,
        no_trade: bool = False,
    ) -> tuple[PreparePaperBoundTradeProposalHandler, list[object], FakeTimeBases]:
        evaluated: list[object] = []
        _, _, recorded = _stand_in_m084(an_intent())
        assert recorded.proposal is not None
        template = recorded.proposal

        class StandInM084Evaluation:
            def __init__(self, **repositories: object) -> None:
                del repositories

            def handle(self, command: PrepareTradeProposalCommand) -> object:
                evaluated.append(command)
                if no_trade:
                    return SimpleNamespace(proposal=None, no_trade_reason="NO", risk_checks=())
                proposal = SimpleNamespace(
                    proposal_governance_id=command.proposal_governance_id,
                    proposal_version=1,
                    content_fingerprint=template.content_fingerprint,
                    created_at=command.evaluated_at,
                    expires_at=command.evaluated_at + timedelta(minutes=5),
                    mandatory_liquidation_at=command.evaluated_at + timedelta(hours=2),
                )
                return SimpleNamespace(proposal=proposal, no_trade_reason=None, risk_checks=())

        monkeypatch.setattr(
            paper_execution_usecases, "PrepareTradeProposalHandler", StandInM084Evaluation
        )
        monkeypatch.setattr(
            paper_execution_usecases,
            "bind_proposal_time_basis",
            lambda *, proposal, time_basis, broker_endpoint_host: ProposalTimeBasis(
                proposal_governance_id=proposal.proposal_governance_id,
                proposal_version=proposal.proposal_version,
                content_fingerprint=proposal.content_fingerprint,
                proposal_created_at=proposal.created_at,
                proposal_expires_at=proposal.expires_at,
                mandatory_liquidation_at=proposal.mandatory_liquidation_at,
                broker_endpoint_host=broker_endpoint_host,
                basis_host_requested_at=time_basis.host_requested_at,
                basis_host_at=time_basis.host_at,
                basis_broker_earliest_at=time_basis.broker_earliest_at,
                basis_broker_latest_at=time_basis.broker_latest_at,
            ),
        )
        bases = FakeTimeBases()
        handler = PreparePaperBoundTradeProposalHandler(
            configurations=object(),  # type: ignore[arg-type]
            contexts=object(),  # type: ignore[arg-type]
            proposals=SimpleNamespace(get=lambda _id: None),  # type: ignore[arg-type]
            time_bases=bases,
            broker=broker,  # type: ignore[arg-type]
            time_source=time_source,
        )
        return handler, evaluated, bases

    @staticmethod
    def _command() -> PreparePaperBoundTradeProposalCommand:
        return PreparePaperBoundTradeProposalCommand(
            proposal_governance_id="PRP-1",
            evaluation_context_id="ECX-1",
            symbol="AAPL",
            quote=object(),  # type: ignore[arg-type]
            account=object(),  # type: ignore[arg-type]
            session=object(),  # type: ignore[arg-type]
            instrument=object(),  # type: ignore[arg-type]
            liquidity=object(),  # type: ignore[arg-type]
            cost_estimate=None,
            positions=(),
            open_orders=(),
            evidence_age_seconds=Decimal("60"),
        )

    def test_the_proposal_is_evaluated_at_the_host_reading_taken_after_the_clock_response(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        time = _ScriptedTime(_NOW)
        handler, evaluated, bases = self._handler(
            monkeypatch, broker=_SlowClockBroker(time, delay=90), time_source=time
        )
        result = handler.handle(self._command())
        assert [command.evaluated_at for command in evaluated] == [_NOW + timedelta(seconds=90)]  # type: ignore[attr-defined]
        evidence = bases.proposals[("PRP-1", 1)]
        assert evidence is result.time_basis
        assert evidence.basis_host_requested_at == _NOW
        assert (
            evidence.proposal_created_at == evidence.basis_host_at == _NOW + timedelta(seconds=90)
        )

    def test_a_no_trade_records_no_basis(self, monkeypatch: pytest.MonkeyPatch) -> None:
        handler, evaluated, bases = self._handler(monkeypatch, broker=FakeBroker(), no_trade=True)
        assert handler.handle(self._command()).time_basis is None
        assert len(evaluated) == 1 and bases.proposals == {}


class TestDecidePaperBoundTradeProposal:
    """The decision composition, with M084's own decision stood in for."""

    def _handler(
        self,
        monkeypatch: pytest.MonkeyPatch,
        *,
        broker: object,
        time_source: PaperTimeSource | None = None,
        with_proposal_basis: bool = True,
    ) -> tuple[DecidePaperBoundTradeProposalHandler, list[object], FakeTimeBases, SimpleNamespace]:
        decided: list[object] = []
        proposal, _, recorded = _stand_in_m084(an_intent())

        class StandInM084Decision:
            def __init__(self, **repositories: object) -> None:
                del repositories

            def handle(self, command: DecideTradeProposalCommand) -> object:
                decided.append(command)
                approving = command.action is OperatorAction.APPROVE
                decision = SimpleNamespace(
                    decision_governance_id=command.decision_governance_id,
                    proposal_governance_id=command.proposal_governance_id,
                    proposal_version=1,
                    approved_fingerprint=proposal.content_fingerprint,
                    action=command.action,
                    decided_at=command.decided_at,
                    expires_at=command.decided_at + timedelta(minutes=2) if approving else None,
                )
                return SimpleNamespace(decision=decision, proposal=proposal)

        monkeypatch.setattr(
            paper_execution_usecases, "DecideTradeProposalHandler", StandInM084Decision
        )
        monkeypatch.setattr(
            paper_execution_usecases,
            "bind_decision_time_basis",
            lambda *, decision, time_basis, broker_endpoint_host: DecisionTimeBasis(
                decision_governance_id=decision.decision_governance_id,
                proposal_governance_id=decision.proposal_governance_id,
                proposal_version=decision.proposal_version,
                approved_fingerprint=decision.approved_fingerprint,
                decided_at=decision.decided_at,
                decision_expires_at=decision.expires_at,
                broker_endpoint_host=broker_endpoint_host,
                basis_host_requested_at=time_basis.host_requested_at,
                basis_host_at=time_basis.host_at,
                basis_broker_earliest_at=time_basis.broker_earliest_at,
                basis_broker_latest_at=time_basis.broker_latest_at,
            ),
        )
        bases = (
            time_bases_for(replace(recorded, decision=None, intent=None))
            if with_proposal_basis
            else FakeTimeBases()
        )
        handler = DecidePaperBoundTradeProposalHandler(
            configurations=object(),  # type: ignore[arg-type]
            decisions=object(),  # type: ignore[arg-type]
            proposals=SimpleNamespace(get=lambda _id: proposal),  # type: ignore[arg-type]
            time_bases=bases,
            broker=broker,  # type: ignore[arg-type]
            time_source=time_source,
        )
        return handler, decided, bases, proposal

    @staticmethod
    def _command(
        action: OperatorAction = OperatorAction.APPROVE,
    ) -> DecidePaperBoundTradeProposalCommand:
        return DecidePaperBoundTradeProposalCommand(
            proposal_governance_id="PRP-1",
            decision_governance_id="DEC-1",
            action=action,
            operator_identity="owner",
        )

    def test_an_approval_is_decided_at_the_host_reading_taken_after_the_clock_response(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _, _, recorded = _stand_in_m084(an_intent())
        assert recorded.proposal is not None
        start = recorded.proposal.proposal_created_at + timedelta(seconds=5)
        time = _ScriptedTime(start)
        handler, decided, bases, _ = self._handler(
            monkeypatch, broker=_SlowClockBroker(time, delay=30), time_source=time
        )
        result = handler.handle(self._command())
        assert [command.decided_at for command in decided] == [start + timedelta(seconds=30)]  # type: ignore[attr-defined]
        evidence = bases.decisions["DEC-1"]
        assert evidence is result.time_basis
        assert evidence.decided_at == evidence.basis_host_at == start + timedelta(seconds=30)

    def test_an_approval_of_a_proposal_without_its_own_basis_is_refused(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        handler, decided, bases, _ = self._handler(
            monkeypatch, broker=FakeBroker(), with_proposal_basis=False
        )
        with pytest.raises(PaperExecutionRefusedError, match="no proposal-time broker basis"):
            handler.handle(self._command())
        assert decided == [] and bases.decisions == {}

    def test_a_proposal_that_expired_on_the_broker_clock_cannot_be_approved(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Host clock still inside the proposal's life; broker clock past its expiry.
        handler, decided, bases, proposal = self._handler(monkeypatch, broker=FakeBroker())

        def past_expiry() -> FakeClock:
            clock = FakeClock()
            clock.timestamp = proposal.expires_at + timedelta(minutes=1)
            return clock

        handler._broker.fetch_clock = past_expiry  # type: ignore[attr-defined]
        with pytest.raises(PaperExecutionRefusedError, match="expired on the broker's clock"):
            handler.handle(self._command())
        assert decided == [] and bases.decisions == {}

    def test_a_rejection_records_no_basis_and_needs_none(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        handler, decided, bases, _ = self._handler(
            monkeypatch, broker=FakeBroker(), with_proposal_basis=False
        )
        assert handler.handle(self._command(OperatorAction.REJECT)).time_basis is None
        assert len(decided) == 1 and bases.decisions == {}


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
                time_basis=a_time_basis(),
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
                time_basis=a_time_basis(),
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
                time_basis=a_time_basis(),
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
                time_basis=a_time_basis(),
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
    from empirical_platform.shared.brokerage.paper_time import SystemPaperTimeSource

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
            time_bases=world["time_bases"],
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
        broker=FakeBroker(),
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
