"""MILESTONE-085 corrective pass: the domain rules the independent review found missing.

Each class names the review finding it closes. Pure domain -- no network, no database --
so a failure names a rule. Boundaries are tested AT the limit and ONE TICK past it,
because a rule tested only well inside and well outside its limit can move its boundary
without any test noticing.

  D1  send-time limits were command arguments, unbound to the authorization;
  D2  an uncertain broker answer was recorded as a definitive refusal;
  T1  the time-of-day liquidation deadline was extended by host clock skew;
  P3  nothing compared an authorization with the preview it names;
  S1  the final guard did not check spread or the entry window.
"""

from __future__ import annotations

import dataclasses
from dataclasses import replace
from datetime import UTC, datetime, time, timedelta
from decimal import Decimal

import pytest
from tests.unit._m085_fakes import (
    _NOW,
    a_configuration,
    a_policy,
    a_preview,
    a_provenance,
    an_intent,
)

from empirical_platform.decision_candidate.operator_trading_configuration import OrderType
from empirical_platform.decision_candidate.paper_execution import (
    DEFINITIVE_BROKER_REFUSAL_STATUSES,
    ExecutionAuthorization,
    SubmissionPreview,
    act_chronology_refusal,
    authorization_binding_refusal,
    authorize_submission,
    effective_liquidation_deadline,
    entry_window_refusal,
    execution_policy_from_configuration,
    final_send_refusal,
    is_definitive_broker_refusal,
    liquidation_session_refusal,
    m084_deadline_refusal_on_broker_time,
    quote_refusal,
)
from empirical_platform.shared.brokerage.paper_time import BoundedInstant, BrokerTimeBasis
from empirical_platform.usecases.paper_execution import (
    PreviewPaperSubmissionCommand,
    SubmitAuthorizedPaperOrderCommand,
)

_TICK = timedelta(microseconds=1)


def _at(moment: datetime) -> BoundedInstant:
    return BoundedInstant(earliest=moment, latest=moment)


def _basis(at: datetime = _NOW, *, offset: timedelta = timedelta(0)) -> BrokerTimeBasis:
    return BrokerTimeBasis(
        host_requested_at=at,
        host_at=at,
        broker_earliest_at=at + offset,
        broker_latest_at=at + offset,
    )


def _new_york(hour: int, minute: int, second: int = 0) -> datetime:
    """A wall-clock instant on `_NOW`'s date in New York (EDT, UTC-4)."""
    return datetime(2026, 9, 10, hour + 4, minute, second, tzinfo=UTC)


# ---------------------------------------------------------------------------
# D1 -- the policy comes from the configuration, and nothing else
# ---------------------------------------------------------------------------


class TestThePolicyComesFromTheConfigurationOnly:
    def test_no_command_has_a_field_that_could_state_a_limit(self) -> None:
        # The reproduced defect passed `500 99999 AAPL,TSLA` to submit. There is now
        # nowhere to put those values: the command types have identities and an instant.
        limits = {"maximum_notional", "quote_maximum_age_seconds", "approved_watchlist"}
        for command in (PreviewPaperSubmissionCommand, SubmitAuthorizedPaperOrderCommand):
            names = {field.name for field in dataclasses.fields(command)}
            assert not names & limits, command
            assert not any("spread" in name or "window" in name for name in names), command

    def test_every_send_time_limit_is_the_configurations(self) -> None:
        configuration = a_configuration(
            maximum_capital_per_trade=Decimal("7"),
            maximum_market_data_age_seconds=45,
            maximum_spread_percent=Decimal("2.5"),
            watchlist=("AAPL", "MSFT"),
            prohibited_instruments=("PENNY",),
            earliest_entry_time=time(10, 0),
            latest_entry_time=time(15, 0),
        )
        policy = execution_policy_from_configuration(configuration)
        assert policy.configuration_governance_id == configuration.configuration_governance_id
        assert policy.configuration_version == configuration.configuration_version
        assert policy.maximum_notional == Decimal("7")
        assert policy.quote_maximum_age_seconds == 45
        assert policy.maximum_spread_percent == Decimal("2.5")
        assert policy.watchlist == ("AAPL", "MSFT")
        assert policy.prohibited_instruments == ("PENNY",)
        assert (policy.earliest_entry_time, policy.latest_entry_time) == (time(10, 0), time(15, 0))
        assert policy.operator_timezone == configuration.operator_timezone

    @pytest.mark.parametrize(
        "override",
        [
            {"maximum_capital_per_trade": Decimal("5.01")},
            {"maximum_market_data_age_seconds": 61},
            {"maximum_spread_percent": Decimal("5.01")},
            {"watchlist": ("AAPL", "TSLA")},
            {"prohibited_instruments": ("OTHER", "PENNY")},
            {"earliest_entry_time": time(9, 30)},
            {"latest_entry_time": time(15, 31)},
            {"operator_timezone": "America/Chicago"},
            {"configuration_version": 2},
        ],
    )
    def test_every_limit_is_part_of_the_policy_fingerprint(
        self, override: dict[str, object]
    ) -> None:
        assert a_policy(**override).fingerprint != a_policy().fingerprint

    @pytest.mark.parametrize(
        ("change", "fragment"),
        [
            ({"watchlist": ("MSFT", "AAPL")}, "sorted"),
            ({"watchlist": ()}, "at least one symbol"),
            ({"quote_maximum_age_seconds": 0}, "positive"),
            ({"maximum_spread_percent": Decimal("-1")}, "non-negative"),
            ({"earliest_entry_time": time(16, 0)}, "precede"),
            ({"operator_timezone": "Not/AZone"}, "timezone"),
            ({"maximum_notional": Decimal("0")}, "positive"),
        ],
    )
    def test_a_malformed_policy_cannot_exist(
        self, change: dict[str, object], fragment: str
    ) -> None:
        with pytest.raises(ValueError, match=fragment):
            replace(a_policy(), **change)


# ---------------------------------------------------------------------------
# S1 -- the preview applies spread, entry window and liquidation date
# ---------------------------------------------------------------------------


class TestThePreviewAppliesThePolicy:
    def test_a_policy_for_another_configuration_version_refuses(self) -> None:
        preview = a_preview(policy=a_policy(configuration_version=2))
        assert any("configuration version the intent names" in r for r in preview.refusals)
        assert preview.is_authorizable is False

    def test_a_prohibited_symbol_refuses(self) -> None:
        preview = a_preview(policy=replace(a_policy(), prohibited_instruments=("AAPL", "PENNY")))
        assert any("prohibited instrument" in r for r in preview.refusals)

    @pytest.mark.parametrize(
        ("bid", "ask", "fragment"),
        [
            (Decimal("97.5"), Decimal("102.51"), "spread"),
            (Decimal("300.00"), Decimal("299.99"), "crossed"),
            (Decimal("0"), Decimal("299.70"), "positive"),
            (Decimal("299.63"), None, "no usable bid and ask"),
        ],
    )
    def test_an_unusable_quote_refuses(
        self, bid: Decimal, ask: Decimal | None, fragment: str
    ) -> None:
        preview = a_preview(quote_bid=bid, quote_ask=ask)
        assert any(fragment in r for r in preview.refusals), preview.refusals
        assert preview.is_authorizable is False

    def test_a_clean_preview_at_the_acceptance_limits_is_authorizable(self) -> None:
        assert a_preview().is_authorizable, a_preview().refusals


class TestTheSpreadBoundary:
    def test_exactly_the_limit_is_permitted_and_one_hundredth_more_is_not(self) -> None:
        policy = a_policy()  # 5 %
        fresh = _NOW - timedelta(seconds=1)
        # Mid 100, spread 5: exactly 5 % of the mid.
        assert (
            quote_refusal(
                bid=Decimal("97.5"),
                ask=Decimal("102.5"),
                captured_at=fresh,
                policy=policy,
                broker_now=_at(_NOW),
            )
            is None
        )
        refusal = quote_refusal(
            bid=Decimal("97.5"),
            ask=Decimal("102.51"),
            captured_at=fresh,
            policy=policy,
            broker_now=_at(_NOW),
        )
        assert refusal is not None and "spread" in refusal


class TestTheQuoteAgeBoundary:
    def test_exactly_sixty_seconds_is_permitted_and_one_microsecond_more_is_not(self) -> None:
        policy = a_policy()
        common = {"bid": Decimal("4.00"), "ask": Decimal("4.01"), "policy": policy}
        assert (
            quote_refusal(captured_at=_NOW - timedelta(seconds=60), broker_now=_at(_NOW), **common)  # type: ignore[arg-type]
            is None
        )
        refusal = quote_refusal(
            captured_at=_NOW - timedelta(seconds=60) - _TICK,
            broker_now=_at(_NOW),
            **common,  # type: ignore[arg-type]
        )
        assert refusal is not None and "older than the 60s limit" in refusal

    def test_the_oldest_end_of_the_broker_interval_decides(self) -> None:
        # Captured 59 s before the earliest end, 61 s before the latest end.
        refusal = quote_refusal(
            bid=Decimal("4.00"),
            ask=Decimal("4.01"),
            captured_at=_NOW - timedelta(seconds=59),
            policy=a_policy(),
            broker_now=BoundedInstant(earliest=_NOW, latest=_NOW + timedelta(seconds=2)),
        )
        assert refusal is not None and "older than" in refusal


class TestTheEntryWindowIsJudgedOnTheBrokerClock:
    @pytest.mark.parametrize(
        ("moment", "permitted"),
        [
            (_new_york(9, 45) - _TICK, False),
            (_new_york(9, 45), True),
            (_new_york(15, 30), True),
            (_new_york(15, 30) + _TICK, False),
        ],
    )
    def test_the_boundaries_are_inclusive_and_one_tick_outside_refuses(
        self, moment: datetime, permitted: bool
    ) -> None:
        refusal = entry_window_refusal(policy=a_policy(), broker_now=_at(moment))
        assert (refusal is None) is permitted, refusal

    def test_an_interval_straddling_the_close_of_the_window_refuses(self) -> None:
        refusal = entry_window_refusal(
            policy=a_policy(),
            broker_now=BoundedInstant(earliest=_new_york(15, 29, 59), latest=_new_york(15, 30, 1)),
        )
        assert refusal is not None and "entry window" in refusal

    def test_an_interval_spanning_two_dates_refuses(self) -> None:
        midnight = datetime(2026, 9, 11, 4, 0, tzinfo=UTC)  # 00:00 in New York
        refusal = entry_window_refusal(
            policy=a_policy(),
            broker_now=BoundedInstant(earliest=midnight - _TICK, latest=midnight),
        )
        assert refusal is not None and "two calendar dates" in refusal


# ---------------------------------------------------------------------------
# T1 -- the liquidation deadline is never extended by host skew
# ---------------------------------------------------------------------------


class TestTheLiquidationDeadlineIsNeverExtendedBySkew:
    def test_a_slow_host_at_evaluation_does_not_move_the_deadline_later(self) -> None:
        # THE REVIEW'S REPRODUCTION. Host 30 minutes slow at evaluation: the broker read
        # 30 minutes AHEAD. Mapping 15:45 through that basis gave 16:15.
        liquidation = _new_york(15, 45)
        slow_host = _basis(_NOW, offset=timedelta(minutes=30))
        assert slow_host.on_broker_timeline(liquidation) == _new_york(16, 15)
        assert (
            effective_liquidation_deadline(liquidation_at=liquidation, proposal_basis=slow_host)
            == liquidation
        )

    def test_a_fast_host_at_evaluation_still_moves_it_earlier(self) -> None:
        liquidation = _new_york(15, 45)
        fast_host = _basis(_NOW, offset=timedelta(minutes=-30))
        assert effective_liquidation_deadline(
            liquidation_at=liquidation, proposal_basis=fast_host
        ) == _new_york(15, 15)

    def test_a_dispatch_at_1550_after_a_slow_host_evaluation_is_refused(self) -> None:
        intent = an_intent(
            mandatory_liquidation_at=_new_york(15, 45), expires_at=_NOW + timedelta(hours=8)
        )
        provenance = a_provenance(intent, proposal_offset=timedelta(minutes=30))
        refusal = m084_deadline_refusal_on_broker_time(
            intent=intent, provenance=provenance, broker_now=_at(_new_york(15, 50))
        )
        assert refusal == "the mandatory liquidation deadline has passed on the broker's clock"

    def test_the_deadline_is_inclusive_to_the_tick(self) -> None:
        intent = an_intent(
            mandatory_liquidation_at=_new_york(15, 45), expires_at=_NOW + timedelta(hours=8)
        )
        provenance = a_provenance(intent, proposal_offset=timedelta(minutes=30))
        before = m084_deadline_refusal_on_broker_time(
            intent=intent, provenance=provenance, broker_now=_at(_new_york(15, 45) - _TICK)
        )
        at_it = m084_deadline_refusal_on_broker_time(
            intent=intent, provenance=provenance, broker_now=_at(_new_york(15, 45))
        )
        assert before is None
        assert at_it == "the mandatory liquidation deadline has passed on the broker's clock"

    def test_an_issuance_after_the_calendar_deadline_is_refused_under_the_same_skew(self) -> None:
        intent = an_intent(
            mandatory_liquidation_at=_new_york(15, 45), expires_at=_NOW + timedelta(hours=8)
        )
        issued_at_1550 = _new_york(15, 50) - intent.created_at
        provenance = a_provenance(
            intent, proposal_offset=timedelta(minutes=30), intent_offset=issued_at_1550
        )
        assert provenance.proposal is not None and provenance.decision is not None
        assert provenance.intent is not None
        refusal = act_chronology_refusal(
            proposal=provenance.proposal,
            decision=replace(
                provenance.decision,
                decision_expires_at=provenance.decision.decided_at + timedelta(hours=9),
            ),
            issued=provenance.intent.time_basis,
        )
        assert refusal == (
            "the mandatory liquidation deadline had passed on the broker's clock when the "
            "intent was issued"
        )

    def test_a_deadline_written_for_another_date_cannot_be_evaluated(self) -> None:
        refusal = liquidation_session_refusal(
            liquidation_at=_new_york(15, 45),
            policy=a_policy(),
            broker_now=_at(_new_york(15, 45) + timedelta(days=1) - timedelta(hours=6)),
        )
        assert refusal is not None and "2026-09-10" in refusal
        assert (
            liquidation_session_refusal(
                liquidation_at=_new_york(15, 45), policy=a_policy(), broker_now=_at(_NOW)
            )
            is None
        )


# ---------------------------------------------------------------------------
# P3 -- an authorization is bound to its exact preview
# ---------------------------------------------------------------------------


def _authorized(
    *, preview: SubmissionPreview | None = None, validity_seconds: int = 300
) -> tuple[SubmissionPreview, ExecutionAuthorization]:
    shown = a_preview() if preview is None else preview
    return shown, authorize_submission(
        authorization_id="AUT-1",
        preview=shown,
        authorized_by="owner",
        authorized_at=_NOW,
        validity_seconds=validity_seconds,
        time_basis=_basis(_NOW),
    )


class TestAnAuthorizationIsBoundToItsExactPreview:
    def test_the_authorization_copies_what_the_human_was_shown(self) -> None:
        preview, authorization = _authorized()
        assert authorization_binding_refusal(authorization=authorization, preview=preview) is None
        assert authorization.maximum_notional == preview.policy.maximum_notional == Decimal("5")
        assert authorization.policy_fingerprint == preview.policy.fingerprint
        assert authorization.preview_binding_fingerprint == preview.binding_fingerprint
        assert (authorization.quote_bid, authorization.quote_ask) == (
            preview.quote_bid,
            preview.quote_ask,
        )

    @pytest.mark.parametrize(
        ("field", "value"),
        [
            ("symbol", "MSFT"),
            ("side", "SELL"),
            ("quantity", 2),
            ("order_type", OrderType.MARKET),
            ("limit_price", Decimal("4.01")),
            ("maximum_notional", Decimal("500")),
            ("quote_bid", Decimal("1.00")),
            ("quote_ask", Decimal("999.00")),
            ("quote_captured_at", _NOW - timedelta(hours=1)),
            ("configuration_governance_id", "CFG-2"),
            ("configuration_version", 2),
            ("policy_fingerprint", "b" * 64),
            ("preview_binding_fingerprint", "c" * 64),
            ("request_fingerprint", "d" * 64),
            ("account_reference", "ref:somebody-else"),
            ("client_order_id", "m085-somebody-else"),
            ("preview_version", 2),
            ("intent_governance_id", "INT-2"),
            ("preview_id", "PVW-2"),
        ],
    )
    def test_tampering_with_any_bound_field_is_named(self, field: str, value: object) -> None:
        preview, authorization = _authorized()
        tampered = replace(authorization, **{field: value})
        refusal = authorization_binding_refusal(authorization=tampered, preview=preview)
        assert refusal is not None
        assert field in refusal

    def test_a_preview_with_refusals_authorizes_nothing(self) -> None:
        preview, authorization = _authorized()
        refused = replace(preview, refusals=("the execution kill switch is engaged",))
        # The binding digest does not cover the refusal list, so only this rule catches it.
        assert refused.binding_fingerprint == preview.binding_fingerprint
        assert authorization_binding_refusal(authorization=authorization, preview=refused) == (
            "the authorization names a preview that was not authorizable"
        )

    def test_an_authorization_may_last_exactly_as_long_as_the_intent_and_no_longer(self) -> None:
        # an_intent() expires one hour after _NOW.
        _, exact = _authorized(validity_seconds=3600)
        assert exact.expires_at == an_intent().expires_at
        with pytest.raises(ValueError, match="outlive the approved intent"):
            _authorized(validity_seconds=3601)

    def test_a_stored_authorization_outliving_its_intent_is_refused(self) -> None:
        preview, authorization = _authorized()
        stretched = replace(authorization, expires_at=preview.intent_expires_at + _TICK)
        assert authorization_binding_refusal(authorization=stretched, preview=preview) == (
            "the authorization outlives the approved intent it would dispatch"
        )

    def test_a_preview_older_than_the_freshness_limit_cannot_be_authorized(self) -> None:
        preview = a_preview()

        def authorize(host_at: datetime) -> ExecutionAuthorization:
            return authorize_submission(
                authorization_id="AUT-1",
                preview=preview,
                authorized_by="owner",
                authorized_at=_NOW,
                validity_seconds=300,
                time_basis=_basis(host_at),
            )

        assert authorize(preview.created_at + timedelta(seconds=60)).is_consumed is False
        with pytest.raises(ValueError, match="older than the configured quote freshness limit"):
            authorize(preview.created_at + timedelta(seconds=60) + _TICK)


# ---------------------------------------------------------------------------
# Item 7 -- the final send guard
# ---------------------------------------------------------------------------


def _guard(
    *,
    authorization: ExecutionAuthorization | None = None,
    preview: SubmissionPreview | None = None,
    **overrides: object,
) -> str | None:
    shown, granted = _authorized() if authorization is None else (preview, authorization)
    assert shown is not None
    intent = overrides.pop("intent", an_intent())
    arguments: dict[str, object] = {
        "intent": intent,
        "provenance": a_provenance(intent),  # type: ignore[arg-type]
        "authorization": granted,
        "policy_now": a_policy(),
        "request_fingerprint_now": shown.request_fingerprint,
        "account_reference_now": shown.account_reference,
        "host_now": _NOW,
        "broker_now": _at(_NOW),
        "market_is_open": True,
        "market_next_close": _NOW + timedelta(hours=2),
        "quote_bid": Decimal("299.63"),
        "quote_ask": Decimal("299.70"),
        "quote_captured_at": _NOW - timedelta(seconds=5),
        "kill_switch_engaged": False,
    }
    arguments.update(overrides)
    return final_send_refusal(**arguments)  # type: ignore[arg-type]


class TestTheFinalSendGuard:
    def test_the_authorized_order_on_fresh_evidence_passes(self) -> None:
        assert _guard() is None

    def test_the_kill_switch_refuses(self) -> None:
        assert _guard(kill_switch_engaged=True) == "the execution kill switch is engaged"

    @pytest.mark.parametrize(
        "looser",
        [
            {"maximum_capital_per_trade": Decimal("500")},
            {"maximum_market_data_age_seconds": 99999},
            {"watchlist": ("AAPL", "TSLA")},
            {"maximum_spread_percent": Decimal("50")},
            {"latest_entry_time": time(15, 40)},
        ],
    )
    def test_a_loosened_configuration_cannot_satisfy_an_authorization(
        self, looser: dict[str, object]
    ) -> None:
        # D1 AT THE LAST BOUNDARY. Whatever the stored policy now says, the send is
        # judged against the one the human authorized, and a different one refuses.
        refusal = _guard(policy_now=a_policy(**looser))
        assert refusal is not None and "not the policy the human authorized" in refusal

    def test_a_policy_of_another_configuration_version_refuses(self) -> None:
        refusal = _guard(policy_now=a_policy(configuration_version=2))
        assert refusal is not None and "configuration version" in refusal

    def test_a_quote_exactly_at_the_limit_passes_and_one_tick_older_refuses(self) -> None:
        assert _guard(quote_captured_at=_NOW - timedelta(seconds=60)) is None
        refusal = _guard(quote_captured_at=_NOW - timedelta(seconds=60) - _TICK)
        assert refusal is not None and "older than the 60s limit" in refusal

    def test_a_missing_or_crossed_or_wide_quote_refuses(self) -> None:
        assert "no quote was captured" in (_guard(quote_captured_at=None) or "")
        assert "crossed" in (_guard(quote_bid=Decimal("300"), quote_ask=Decimal("299")) or "")
        assert "spread" in (_guard(quote_bid=Decimal("97.5"), quote_ask=Decimal("102.51")) or "")

    def test_the_market_close_is_inclusive_to_the_tick(self) -> None:
        assert _guard(market_next_close=_NOW + _TICK) is None
        assert _guard(market_next_close=_NOW) == "the regular market session is closed"
        assert _guard(market_is_open=False) == "the regular market session is closed"
        assert _guard(market_next_close=None) == "the regular market session is closed"

    def test_the_entry_window_is_inclusive_to_the_tick(self) -> None:
        # A configuration whose window closes at _NOW, 10:00 in New York.
        policy = a_policy(latest_entry_time=time(10, 0))
        preview, authorization = _authorized(preview=a_preview(policy=policy))
        assert _guard(preview=preview, authorization=authorization, policy_now=policy) is None
        refusal = _guard(
            preview=preview,
            authorization=authorization,
            policy_now=policy,
            host_now=_NOW + _TICK,
            broker_now=_at(_NOW + _TICK),
            quote_captured_at=_NOW,
        )
        assert refusal is not None and "entry window" in refusal

    def test_the_host_liquidation_deadline_refuses(self) -> None:
        intent = an_intent(mandatory_liquidation_at=_NOW + timedelta(minutes=2))
        preview, authorization = _authorized(preview=a_preview(intent=intent))
        later = _NOW + timedelta(minutes=2)
        refusal = _guard(
            intent=intent,
            preview=preview,
            authorization=authorization,
            host_now=later,
            broker_now=_at(later - timedelta(minutes=1)),
            quote_captured_at=later - timedelta(minutes=1, seconds=5),
        )
        assert refusal == "the approved intent or liquidation deadline expired"

    def test_the_broker_intent_deadline_through_the_proposal_basis_refuses(self) -> None:
        intent = an_intent(expires_at=_NOW + timedelta(hours=1, seconds=1))
        refusal = _guard(
            intent=intent,
            provenance=a_provenance(intent, proposal_offset=timedelta(hours=-1)),
            broker_now=_at(_NOW + timedelta(seconds=1)),
        )
        assert refusal == "the approved intent has expired on the broker's clock"

    def test_a_liquidation_deadline_for_another_date_refuses(self) -> None:
        # A preview for such an intent already refuses (so it cannot be authorized);
        # the final guard asks again about the intent it is handed.
        intent = an_intent(mandatory_liquidation_at=_NOW + timedelta(days=1))
        assert any("not the broker's current date" in r for r in a_preview(intent=intent).refusals)
        refusal = _guard(intent=intent)
        assert refusal is not None and "not the broker's current date" in refusal

    def test_a_future_dated_authorization_refuses(self) -> None:
        assert _guard(host_now=_NOW - _TICK) == "the authorization is future-dated"

    def test_order_terms_other_than_the_intent_refuse(self) -> None:
        refusal = _guard(intent=an_intent(quantity=2))
        assert refusal == "the authorized order terms are not the approved intent's"

    def test_a_changed_request_or_account_refuses(self) -> None:
        assert "order changed" in (_guard(request_fingerprint_now="e" * 64) or "")
        assert "different paper account" in (_guard(account_reference_now="ref:other") or "")


# ---------------------------------------------------------------------------
# D2 -- an uncertain broker answer is never a refusal
# ---------------------------------------------------------------------------


class TestOnlyADefinitiveRefusalIsARefusal:
    def test_the_definitive_statuses_are_exactly_these(self) -> None:
        assert frozenset({400, 401, 403, 422}) == DEFINITIVE_BROKER_REFUSAL_STATUSES

    @pytest.mark.parametrize("status", [400, 401, 403, 422])
    def test_a_definitive_status_with_the_brokers_error_document_is_a_refusal(
        self, status: int
    ) -> None:
        assert is_definitive_broker_refusal(status, '{"code": 40010001, "message": "no"}')

    @pytest.mark.parametrize(
        ("status", "body"),
        [
            (400, "<html>Bad Request</html>"),
            (403, ""),
            (422, '{"message": "trunc'),
            (422, '["not", "an", "object"]'),
            (404, '{"message": "not found"}'),
            (408, '{"message": "timeout"}'),
            (409, '{"message": "conflict"}'),
            (429, '{"message": "too many requests"}'),
            (500, '{"message": "internal"}'),
            (502, "<html>Bad Gateway</html>"),
            (503, '{"message": "unavailable"}'),
            (504, '{"message": "gateway timeout"}'),
            (200, '{"id": "x"}'),
            (201, '{"id": "x"}'),
            (302, ""),
        ],
    )
    def test_anything_else_is_uncertain(self, status: int, body: str) -> None:
        assert is_definitive_broker_refusal(status, body) is False

    def test_a_boolean_is_not_a_status(self) -> None:
        assert is_definitive_broker_refusal(True, '{"message": "no"}') is False  # type: ignore[arg-type]
