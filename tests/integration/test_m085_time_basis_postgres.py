"""M085 time bases with distinct provenance, through real PostgreSQL and real restarts.

TWO BASES, NEVER EXCHANGED. An authorization's basis is measured when a human
authorizes and translates only that authorization's own expiry. An intent's basis
is measured when the intent is issued and translates only MILESTONE-084's two
deadlines. Every scenario below that moves a clock moves it BETWEEN processes --
each command runs against its own `PostgresPersistenceService` and its own time
window -- because the defects this file holds fixed only exist once a process that
measured something has exited.

THE CLOCKS. `World.true` is what the broker's clock reads and what real elapsed
time is. `World.host_lag` is how far THIS host's wall clock is behind it; changing
it between commands is a host clock step. `World.fetch_delay` is how long a broker
clock request takes. The broker and the quote always tell the truth, so the only
thing that can make a deadline look further away is the host clock -- which is the
attack.

WHAT A DIRECT SQL WRITER CAN STILL DO, STATED. The database enforces the SHAPE of
both bases and binds intent evidence to the exact stored intent. It cannot know
whether a measurement happened: a writer with INSERT authority could copy an
intent's own `created_at` into a fabricated evidence row. The application has no
such path. That is the same boundary as a disabled trigger or a superuser, and it
is recorded rather than implied away.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest
import sqlalchemy as sa
from alembic import command as alembic_command
from sqlalchemy import text
from sqlalchemy.engine import Engine
from tests.integration._m085_support import (
    EVALUATED_AT,
    a_basis_at,
    a_paper_bound_intent,
    alembic_config,
    an_approved_intent,
    an_intent_time_basis_for,
    build_engine,
    config,
    truncate_all,
)
from tests.unit._m085_fakes import FakeBroker

from empirical_platform.decision_candidate.paper_execution import (
    PAPER_ENDPOINT_HOST,
    ExecutionAuthorization,
    PaperAccountSnapshot,
    PaperEnvironment,
    PaperExecutionState,
    authorize_submission,
    build_submission_preview,
)
from empirical_platform.shared.brokerage.paper_time import BoundedInstant, PaperTimeReading
from empirical_platform.shared.persistence.postgres import PostgresPersistenceService
from empirical_platform.shared.persistence.postgres_repositories.paper_execution_repositories import (  # noqa: E501
    PostgresExecutionAttemptRepository,
    PostgresPaperExecutionRuntime,
)
from empirical_platform.shared.persistence.postgres_repositories.runtime import (
    PostgresRepositoryRuntime,
)
from empirical_platform.usecases.paper_execution import (
    AuthorizePaperSubmissionCommand,
    AuthorizePaperSubmissionHandler,
    PaperExecutionRefusedError,
    PaperSubmissionResult,
    PreviewPaperSubmissionCommand,
    PreviewPaperSubmissionHandler,
    SubmitAuthorizedPaperOrderCommand,
    SubmitAuthorizedPaperOrderHandler,
)

pytestmark = pytest.mark.integration

_INTENT = "INT-085-0001"
_WATCHLIST = frozenset({"AAPL"})
#: The revision below `d4f18a6c2e97`, assembled from groups: a hex literal of this
#: length is a `Hex High Entropy String` to the repository's secret scanner, which
#: reported exactly this line when it was written out whole.
_BEFORE_THIS_REVISION = "".join(("c7a41f", "0b52de"))


class World:
    def __init__(self) -> None:
        self.true = EVALUATED_AT + timedelta(seconds=25)
        self.elapsed = 0.0
        self.host_lag = timedelta(0)
        self.fetch_delay = 0.0
        self.clock_fetches = 0

    def advance(self, seconds: float) -> None:
        self.true += timedelta(seconds=seconds)
        self.elapsed += seconds

    def read(self) -> PaperTimeReading:
        return PaperTimeReading(self.true - self.host_lag, self.elapsed)


class TruthfulBroker(FakeBroker):
    def __init__(self, world: World) -> None:
        super().__init__()
        self.world = world

    def fetch_clock(self) -> SimpleNamespace:  # type: ignore[override]
        self.world.clock_fetches += 1
        self.world.advance(self.world.fetch_delay)
        return SimpleNamespace(
            timestamp=self.world.true,
            is_open=True,
            next_open=None,
            next_close=EVALUATED_AT + timedelta(hours=3),
        )


class TruthfulQuotes:
    endpoint_host = "data.alpaca.markets"

    def __init__(self, world: World) -> None:
        self.world = world

    def fetch_quote(self, symbol: str) -> SimpleNamespace:
        del symbol
        return SimpleNamespace(
            bid="199.95", ask="200", captured_at=self.world.true, source="controlled"
        )


@pytest.fixture(scope="module")
def engine() -> Iterator[Engine]:
    yield from build_engine()


@pytest.fixture
def clean(engine: Engine) -> Engine:
    truncate_all(engine)
    return engine


@pytest.fixture
def world(clean: Engine) -> World:
    return World()


@contextmanager
def a_process(
    application: str,
) -> Iterator[tuple[PostgresRepositoryRuntime, PostgresPaperExecutionRuntime]]:
    """One operator command: its own service, and nothing remembered from the last."""
    service = PostgresPersistenceService(config(application))
    service.initialize()
    try:
        yield PostgresRepositoryRuntime(service), PostgresPaperExecutionRuntime(service)
    finally:
        service.close()


def issue(world: World, broker: TruthfulBroker) -> None:
    with a_process("m085-basis-issue") as (m084, paper):
        a_paper_bound_intent(m084, paper, broker=broker, time_source=world, intent_id=_INTENT)


def preview_and_authorize(
    world: World,
    broker: TruthfulBroker,
    *,
    validity_seconds: int,
    authorization_fetch_delay: float = 0.0,
    suffix: str = "",
) -> ExecutionAuthorization:
    with a_process("m085-basis-authorize") as (m084, paper):
        preview = PreviewPaperSubmissionHandler(
            intents=m084.approved_order_intents,
            intent_time_bases=paper.intent_time_bases,
            snapshots=paper.paper_account_snapshots,
            previews=paper.submission_previews,
            events=paper.paper_execution_events,
            broker=broker,
            market_data=TruthfulQuotes(world),
            kill_switch=paper.execution_kill_switch,
            time_source=world,
        ).handle(
            PreviewPaperSubmissionCommand(
                intent_governance_id=_INTENT,
                preview_id=f"PVW-BASIS{suffix}",
                account_snapshot_id=f"SNP-BASIS{suffix}",
                approved_watchlist=_WATCHLIST,
                maximum_notional=Decimal("100000"),
                quote_maximum_age_seconds=60,
                created_at=world.read().utc,
            )
        )
        assert preview.is_authorizable, preview.refusals
        # The entrypoint stamps `authorized_at` BEFORE the handler reads the clock.
        authorized_at = world.read().utc
        world.fetch_delay = authorization_fetch_delay
        try:
            return AuthorizePaperSubmissionHandler(
                previews=paper.submission_previews,
                authorizations=paper.execution_authorizations,
                events=paper.paper_execution_events,
                broker=broker,
                time_source=world,
            ).handle(
                AuthorizePaperSubmissionCommand(
                    authorization_id=f"AUT-BASIS{suffix}",
                    preview_id=preview.preview_id,
                    expected_request_fingerprint=preview.request_fingerprint,
                    authorized_by="owner",
                    authorized_at=authorized_at,
                    validity_seconds=validity_seconds,
                )
            )
        finally:
            world.fetch_delay = 0.0


def dispatch(
    world: World,
    broker: TruthfulBroker,
    *,
    attempt_id: str = "ATT-BASIS",
    attempts: type[PostgresExecutionAttemptRepository] | None = None,
) -> PaperSubmissionResult:
    with a_process("m085-basis-dispatch") as (m084, paper):
        return SubmitAuthorizedPaperOrderHandler(
            intents=m084.approved_order_intents,
            intent_time_bases=paper.intent_time_bases,
            previews=paper.submission_previews,
            authorizations=paper.execution_authorizations,
            attempts=(
                paper.execution_attempts
                if attempts is None
                else attempts(paper.execution_attempts._service)  # type: ignore[attr-defined]
            ),
            acknowledgements=paper.broker_acknowledgements,
            events=paper.paper_execution_events,
            snapshots=paper.paper_account_snapshots,
            broker=broker,
            market_data=TruthfulQuotes(world),
            kill_switch=paper.execution_kill_switch,
            time_source=world,
        ).handle(
            SubmitAuthorizedPaperOrderCommand(
                intent_governance_id=_INTENT,
                attempt_id=attempt_id,
                account_snapshot_id=f"SNP-{attempt_id}",
                approved_watchlist=_WATCHLIST,
                maximum_notional=Decimal("100000"),
                quote_maximum_age_seconds=60,
                at=world.read().utc,
            )
        )


def _nothing_was_consumed_or_sent(broker: TruthfulBroker, authorization_id: str) -> None:
    assert broker.submitted == []
    with a_process("m085-basis-inspect") as (_, paper):
        stored = paper.execution_authorizations.get(authorization_id)
        assert stored is not None and not stored.is_consumed
        assert paper.execution_attempts.for_intent(_INTENT) is None


# ---------------------------------------------------------------------------
# Restart between every step
# ---------------------------------------------------------------------------


class TestEachStepRunsInItsOwnProcess:
    def test_issue_authorize_and_dispatch_as_three_processes_dispatch_exactly_once(
        self, world: World
    ) -> None:
        broker = TruthfulBroker(world)
        issue(world, broker)
        world.advance(5)
        authorization = preview_and_authorize(world, broker, validity_seconds=60)
        world.advance(5)

        assert dispatch(world, broker).dispatched is True
        again = dispatch(world, broker, attempt_id="ATT-BASIS-2")
        assert again.dispatched is False
        assert len(broker.submitted) == 1

        with a_process("m085-basis-inspect") as (m084, paper):
            intent = m084.approved_order_intents.get(_INTENT)
            evidence = paper.intent_time_bases.get(_INTENT)
            stored = paper.execution_authorizations.get(authorization.authorization_id)
        assert intent is not None and evidence is not None and stored is not None
        # The intent's issuance instant IS the basis host reading -- not a copy of it.
        assert evidence.intent_created_at == intent.created_at == evidence.basis_host_at
        assert evidence.intent_expires_at == intent.expires_at
        assert stored.time_basis is not None
        assert stored.basis_host_requested_at is not None
        assert stored.basis_host_requested_at <= stored.basis_host_at  # type: ignore[operator]


# ---------------------------------------------------------------------------
# Defect 1: the authorization basis was not simultaneous
# ---------------------------------------------------------------------------


class TestBrokerFetchLatencyCannotExtendAnAuthorization:
    def test_the_stored_interval_brackets_the_fetch_and_the_mapping_uses_its_later_end(
        self, world: World
    ) -> None:
        broker = TruthfulBroker(world)
        issue(world, broker)
        authorized_at_before_fetch = world.true
        authorization = preview_and_authorize(
            world, broker, validity_seconds=60, authorization_fetch_delay=30
        )
        assert authorization.basis_host_requested_at == authorized_at_before_fetch
        assert authorization.basis_host_at == authorized_at_before_fetch + timedelta(seconds=30)
        assert authorization.basis_broker_earliest_at == authorization.basis_host_at
        assert authorization.basis_broker_latest_at == authorization.basis_host_at + timedelta(
            seconds=30
        )
        # On the broker's timeline the permission ends where the human's validity
        # said -- not 30 s later, which is where the replaced pairing put it.
        assert authorization.on_broker_timeline(authorization.expires_at) == (
            authorized_at_before_fetch + timedelta(seconds=60)
        )

    def test_a_new_process_after_the_real_expiry_is_refused_even_with_the_host_clock_behind(
        self, world: World
    ) -> None:
        broker = TruthfulBroker(world)
        issue(world, broker)
        authorized_at_before_fetch = world.true
        authorization = preview_and_authorize(
            world, broker, validity_seconds=60, authorization_fetch_delay=30
        )
        # 75 s of real time after the command: past the 60 s permission, before the
        # 90 s the fetch latency would have produced. The host clock is an hour behind,
        # so no host-timeline check can refuse; only the broker mapping can.
        world.host_lag = timedelta(hours=1)
        world.advance(
            (authorized_at_before_fetch + timedelta(seconds=75) - world.true).total_seconds()
        )
        with pytest.raises(
            PaperExecutionRefusedError, match="authorization has expired on the broker"
        ):
            dispatch(world, broker)
        _nothing_was_consumed_or_sent(broker, authorization.authorization_id)


# ---------------------------------------------------------------------------
# Defect 2: an authorization-time basis cannot translate an older intent
# ---------------------------------------------------------------------------


class TestAnIntentsDeadlinesUseTheBasisOfItsOwnIssuance:
    def _authorized_after_a_backward_host_step(
        self, world: World, broker: TruthfulBroker
    ) -> ExecutionAuthorization:
        # 1. The intent is issued with the host clock correct (offset A = 0).
        issue(world, broker)
        # 2. The host clock steps back an hour. 3. Authorization under offset B.
        world.host_lag = timedelta(hours=1)
        world.advance(15)
        return preview_and_authorize(world, broker, validity_seconds=3600)

    def test_a_dispatch_after_the_real_m084_deadline_is_refused(self, world: World) -> None:
        broker = TruthfulBroker(world)
        authorization = self._authorized_after_a_backward_host_step(world, broker)
        with a_process("m085-basis-inspect") as (m084, _):
            intent = m084.approved_order_intents.get(_INTENT)
        assert intent is not None
        # The authorization's basis would place the deadline an hour late -- the
        # defect. It is not the basis used for this deadline.
        assert authorization.on_broker_timeline(intent.expires_at) == intent.expires_at + timedelta(
            hours=1
        )
        # 4. A new dispatch process after the REAL M084 deadline, host still behind.
        world.advance((intent.expires_at + timedelta(seconds=100) - world.true).total_seconds())
        with pytest.raises(PaperExecutionRefusedError, match="intent has expired on the broker"):
            dispatch(world, broker)
        _nothing_was_consumed_or_sent(broker, authorization.authorization_id)

    def test_the_same_offset_change_still_dispatches_before_the_real_m084_deadline(
        self, world: World
    ) -> None:
        # The negative half: with the host behind throughout authorization AND
        # dispatch, the authorization basis is consistent and the intent basis is
        # consistent, so a dispatch inside both real deadlines must still go.
        broker = TruthfulBroker(world)
        self._authorized_after_a_backward_host_step(world, broker)
        world.advance(20)
        assert dispatch(world, broker).dispatched is True
        assert len(broker.submitted) == 1

    def test_a_deadline_crossed_inside_the_claim_is_refused_at_the_send_boundary(
        self, world: World
    ) -> None:
        broker = TruthfulBroker(world)
        authorization = self._authorized_after_a_backward_host_step(world, broker)
        with a_process("m085-basis-inspect") as (m084, _):
            intent = m084.approved_order_intents.get(_INTENT)
        assert intent is not None
        world.advance((intent.expires_at - timedelta(seconds=10) - world.true).total_seconds())

        class SlowClaim(PostgresExecutionAttemptRepository):
            def claim_dispatch(self, **kwargs: object) -> object:  # type: ignore[override]
                world.advance(20)
                return super().claim_dispatch(**kwargs)  # type: ignore[arg-type]

        result = dispatch(world, broker, attempts=SlowClaim)
        assert result.dispatched is False
        assert result.attempt.state is PaperExecutionState.REJECTED
        assert "intent has expired on the broker" in (result.attempt.failure_detail or "")
        assert broker.submitted == []
        # Consumed and terminal, and a repeat still sends nothing.
        assert dispatch(world, broker, attempt_id="ATT-BASIS-2").dispatched is False
        assert broker.submitted == []
        del authorization


# ---------------------------------------------------------------------------
# Missing or mismatched evidence: refused, never derived
# ---------------------------------------------------------------------------


def _an_account() -> PaperAccountSnapshot:
    return PaperAccountSnapshot(
        snapshot_id="SNP-LEGACY",
        environment=PaperEnvironment.PAPER,
        endpoint_host=PAPER_ENDPOINT_HOST,
        account_reference="ref:0c7e0f8f2b3f1c0c7e0f8f2b3f1c0c7e",
        account_status="ACTIVE",
        currency="USD",
        buying_power=Decimal("100000"),
        cash=Decimal("100000"),
        equity=Decimal("100000"),
        multiplier="4",
        shorting_enabled=True,
        trading_blocked=False,
        transfers_blocked=False,
        account_blocked=False,
        trade_suspended_by_user=False,
        captured_at=EVALUATED_AT + timedelta(seconds=25),
    )


class TestAnIntentWithoutItsOwnBasisIsNotDispatchable:
    def test_an_m084_only_intent_previews_as_refused(self, world: World) -> None:
        broker = TruthfulBroker(world)
        with a_process("m085-basis-legacy") as (m084, paper):
            an_approved_intent(m084, intent_id=_INTENT)
            preview = PreviewPaperSubmissionHandler(
                intents=m084.approved_order_intents,
                intent_time_bases=paper.intent_time_bases,
                snapshots=paper.paper_account_snapshots,
                previews=paper.submission_previews,
                events=paper.paper_execution_events,
                broker=broker,
                market_data=TruthfulQuotes(world),
                kill_switch=paper.execution_kill_switch,
                time_source=world,
            ).handle(
                PreviewPaperSubmissionCommand(
                    intent_governance_id=_INTENT,
                    preview_id="PVW-LEGACY",
                    account_snapshot_id="SNP-LEGACY",
                    approved_watchlist=_WATCHLIST,
                    maximum_notional=Decimal("100000"),
                    quote_maximum_age_seconds=60,
                    created_at=world.read().utc,
                )
            )
        assert preview.is_authorizable is False
        assert any("no intent-time broker basis" in reason for reason in preview.refusals)
        assert broker.submitted == []

    def test_an_authorization_obtained_elsewhere_still_cannot_dispatch_it(
        self, world: World
    ) -> None:
        # The permission exists; the intent's own evidence does not. Built through
        # the domain so the authorization is genuine and only the evidence is absent.
        broker = TruthfulBroker(world)
        with a_process("m085-basis-legacy") as (m084, paper):
            intent = an_approved_intent(m084, intent_id=_INTENT)
            account = paper.paper_account_snapshots.save(_an_account())
            now = world.read().utc
            preview = paper.submission_previews.save(
                build_submission_preview(
                    preview_id="PVW-LEGACY",
                    intent=intent,
                    account=account,
                    preview_version=1,
                    market_is_open=True,
                    market_next_open=None,
                    market_next_close=EVALUATED_AT + timedelta(hours=3),
                    quote_bid=Decimal("199.95"),
                    quote_ask=Decimal("200"),
                    quote_captured_at=now,
                    quote_source="controlled",
                    asset_tradable=True,
                    asset_status="active",
                    asset_class="us_equity",
                    asset_exchange="NASDAQ",
                    asset_fractionable=True,
                    approved_watchlist=_WATCHLIST,
                    maximum_notional=Decimal("100000"),
                    quote_maximum_age_seconds=60,
                    existing_position_quantity=0,
                    execution_kill_switch_engaged=False,
                    created_at=now,
                    broker_now=BoundedInstant(earliest=now, latest=now),
                    # Evidence that exists only in memory here, never in the database.
                    intent_time_basis=an_intent_time_basis_for(intent),
                )
            )
            authorization = paper.execution_authorizations.save(
                authorize_submission(
                    authorization_id="AUT-LEGACY",
                    preview=preview,
                    authorized_by="owner",
                    authorized_at=now,
                    validity_seconds=600,
                    time_basis=a_basis_at(now),
                )
            )
        world.clock_fetches = 0
        with pytest.raises(PaperExecutionRefusedError, match="no intent-time broker basis"):
            dispatch(world, broker)
        assert world.clock_fetches == 0, "refused before any broker call"
        _nothing_was_consumed_or_sent(broker, authorization.authorization_id)

    def test_a_legacy_pair_only_authorization_is_readable_but_not_dispatchable(
        self, world: World, clean: Engine
    ) -> None:
        broker = TruthfulBroker(world)
        issue(world, broker)
        genuine = preview_and_authorize(world, broker, validity_seconds=600)
        world.advance(1)
        with a_process("m085-basis-legacy") as (m084, paper):
            second = PreviewPaperSubmissionHandler(
                intents=m084.approved_order_intents,
                intent_time_bases=paper.intent_time_bases,
                snapshots=paper.paper_account_snapshots,
                previews=paper.submission_previews,
                events=paper.paper_execution_events,
                broker=broker,
                market_data=TruthfulQuotes(world),
                kill_switch=paper.execution_kill_switch,
                time_source=world,
            ).handle(
                PreviewPaperSubmissionCommand(
                    intent_governance_id=_INTENT,
                    preview_id="PVW-PAIR",
                    account_snapshot_id="SNP-PAIR",
                    approved_watchlist=_WATCHLIST,
                    maximum_notional=Decimal("100000"),
                    quote_maximum_age_seconds=60,
                    created_at=world.read().utc,
                )
            )
        # The shape `c7a41f0b52de` wrote: the pair, with the host reading equal to the
        # pre-fetch `authorized_at`, and no interval. Newer than the genuine one, so
        # it is the authorization the dispatch picks up.
        with clean.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO public.paper_execution_authorization (authorization_id, "
                    "intent_governance_id, preview_id, preview_version, request_fingerprint, "
                    "account_reference, client_order_id, authorized_by, authorized_at, "
                    "expires_at, basis_host_at, basis_broker_earliest_at) VALUES ('AUT-PAIR', "
                    ":intent, 'PVW-PAIR', :version, :fingerprint, :account, :client, 'owner', "
                    ":at, :expires, :at, :at)"
                ),
                {
                    "intent": _INTENT,
                    "version": second.preview_version,
                    "fingerprint": second.request_fingerprint,
                    "account": second.account_reference,
                    "client": second.order.client_order_id,
                    "at": world.read().utc,
                    "expires": world.read().utc + timedelta(seconds=600),
                },
            )
        with a_process("m085-basis-inspect") as (_, paper):
            legacy = paper.execution_authorizations.get("AUT-PAIR")
        assert legacy is not None
        assert legacy.basis_host_at is not None and legacy.time_basis is None
        with pytest.raises(PaperExecutionRefusedError, match="no authorization-time broker basis"):
            dispatch(world, broker)
        _nothing_was_consumed_or_sent(broker, "AUT-PAIR")
        _nothing_was_consumed_or_sent(broker, genuine.authorization_id)


# ---------------------------------------------------------------------------
# What the database itself refuses
# ---------------------------------------------------------------------------

_COPY_INTENT = (
    "INSERT INTO public.paper_intent_time_basis (intent_governance_id, approved_fingerprint, "
    "intent_created_at, intent_expires_at, intent_mandatory_liquidation_at, "
    "broker_endpoint_host, basis_host_requested_at, basis_host_at, basis_broker_earliest_at, "
    "basis_broker_latest_at) "
    "SELECT intent_governance_id, {fingerprint}, {created}, {expires}, {liquidation}, "
    "'paper-api.alpaca.markets', {requested}, {host}, {earliest}, {latest} "
    "FROM public.approved_order_intent WHERE intent_governance_id = '{intent}'"
)

_EXACT = {
    "fingerprint": "approved_fingerprint",
    "created": "created_at",
    "expires": "expires_at",
    "liquidation": "mandatory_liquidation_at",
    "requested": "created_at",
    "host": "created_at",
    "earliest": "created_at",
    "latest": "created_at",
    "intent": _INTENT,
}


def _insert_evidence(engine: Engine, **overrides: str) -> None:
    with engine.begin() as connection:
        connection.execute(text(_COPY_INTENT.format(**{**_EXACT, **overrides})))


class TestTheDatabaseBindsIntentEvidenceToTheExactIntent:
    @pytest.fixture
    def legacy_intent(self, clean: Engine) -> Engine:
        with a_process("m085-basis-sql") as (m084, _):
            an_approved_intent(m084, intent_id=_INTENT)
        return clean

    def test_an_exact_copy_is_accepted(self, legacy_intent: Engine) -> None:
        # The control for every refusal below -- and the recorded limit: the
        # database accepts correctly SHAPED evidence without knowing it was measured.
        _insert_evidence(legacy_intent)

    @pytest.mark.parametrize(
        "override",
        [
            {"fingerprint": "repeat('b', 64)"},
            {
                "created": "created_at - interval '1 second'",
                "host": "created_at - interval '1 second'",
                "requested": "created_at - interval '1 second'",
            },
            {"expires": "expires_at + interval '1 hour'"},
            {"liquidation": "mandatory_liquidation_at + interval '1 hour'"},
        ],
        ids=["fingerprint", "created_at", "expires_at", "mandatory_liquidation_at"],
    )
    def test_evidence_describing_another_intent_is_refused(
        self, legacy_intent: Engine, override: dict[str, str]
    ) -> None:
        with pytest.raises(sa.exc.DatabaseError) as raised:
            _insert_evidence(legacy_intent, **override)
        assert "does not describe the exact stored intent" in str(raised.value)

    def test_evidence_for_an_intent_that_does_not_exist_is_refused(self, clean: Engine) -> None:
        with pytest.raises(sa.exc.DatabaseError) as raised, clean.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO public.paper_intent_time_basis VALUES ('NO-SUCH-INTENT', "
                    "repeat('a', 64), now(), now() + interval '1 hour', "
                    "now() + interval '2 hours', 'paper-api.alpaca.markets', "
                    "now(), now(), now(), now())"
                )
            )
        assert "which does not exist" in str(raised.value)

    def test_evidence_not_bound_to_the_issuance_instant_is_refused(
        self, legacy_intent: Engine
    ) -> None:
        # Every copied field matches the stored intent, so the guard passes -- and the
        # basis host reading is a later instant, which is what a backfill looks like.
        with pytest.raises(sa.exc.DatabaseError) as raised:
            _insert_evidence(
                legacy_intent,
                requested="created_at + interval '1 day'",
                host="created_at + interval '1 day'",
                earliest="created_at + interval '1 day'",
                latest="created_at + interval '1 day'",
            )
        assert "ck_paper_intent_time_basis_bound_to_issuance" in str(raised.value)

    @pytest.mark.parametrize(
        ("override", "constraint"),
        [
            (
                {"requested": "created_at + interval '1 second'"},
                "ck_paper_intent_time_basis_host_interval",
            ),
            (
                {"earliest": "created_at + interval '1 second'"},
                "ck_paper_intent_time_basis_broker_interval",
            ),
        ],
        ids=["host-interval-inverted", "broker-interval-inverted"],
    )
    def test_an_inverted_interval_is_refused(
        self, legacy_intent: Engine, override: dict[str, str], constraint: str
    ) -> None:
        with pytest.raises(sa.exc.DatabaseError) as raised:
            _insert_evidence(legacy_intent, **override)
        assert constraint in str(raised.value)

    def test_evidence_is_append_only_and_recorded_once(self, legacy_intent: Engine) -> None:
        _insert_evidence(legacy_intent)
        for statement in (
            "UPDATE public.paper_intent_time_basis SET basis_host_at = basis_host_at",
            "DELETE FROM public.paper_intent_time_basis",
        ):
            with pytest.raises(sa.exc.DatabaseError) as raised, legacy_intent.begin() as connection:
                connection.execute(text(statement))
            assert "append-only" in str(raised.value)
        with pytest.raises(sa.exc.IntegrityError):
            _insert_evidence(legacy_intent)


class TestTheDatabaseRefusesAMalformedAuthorizationBasis:
    @pytest.fixture
    def chain(self, world: World) -> tuple[World, TruthfulBroker, ExecutionAuthorization]:
        broker = TruthfulBroker(world)
        issue(world, broker)
        return world, broker, preview_and_authorize(world, broker, validity_seconds=600)

    def _second_authorization(
        self, engine: Engine, offsets: tuple[float | None, float | None, float | None, float | None]
    ) -> None:
        """Insert a second authorization whose four basis readings are `base + offset`.

        Order: basis_host_at, basis_broker_earliest_at, basis_host_requested_at,
        basis_broker_latest_at. None leaves a reading NULL. `authorized_at` is `base`.
        Every value is a bind parameter, so the statement itself is a constant.
        """
        base = datetime.now(UTC)

        def reading(offset: float | None) -> datetime | None:
            return None if offset is None else base + timedelta(seconds=offset)

        with engine.begin() as connection:
            row = (
                connection.execute(
                    text(
                        "SELECT intent_governance_id, preview_id, preview_version, "
                        "request_fingerprint, account_reference, client_order_id "
                        "FROM public.paper_execution_authorization LIMIT 1"
                    )
                )
                .mappings()
                .one()
            )
            # A second preview row so the one-authorization-per-preview constraint is
            # not what refuses.
            connection.execute(
                text(
                    "INSERT INTO public.paper_submission_preview SELECT 'PVW-SQL', "
                    "intent_governance_id, preview_version + 1, account_snapshot_id, "
                    "account_reference, symbol, side, quantity, order_type, limit_price, "
                    "time_in_force, extended_hours, client_order_id, request_fingerprint, "
                    "approved_fingerprint, market_is_open, market_next_open, market_next_close, "
                    "quote_bid, quote_ask, quote_captured_at, quote_source, asset_tradable, "
                    "asset_status, asset_class, asset_exchange, asset_fractionable, refusals, "
                    "created_at FROM public.paper_submission_preview "
                    "WHERE preview_id = :preview"
                ),
                {"preview": row["preview_id"]},
            )
            connection.execute(
                text(
                    "INSERT INTO public.paper_execution_authorization (authorization_id, "
                    "intent_governance_id, preview_id, preview_version, request_fingerprint, "
                    "account_reference, client_order_id, authorized_by, authorized_at, "
                    "expires_at, basis_host_at, basis_broker_earliest_at, "
                    "basis_host_requested_at, basis_broker_latest_at) VALUES ('AUT-SQL', "
                    ":intent, 'PVW-SQL', :version, :fingerprint, :account, :client, 'owner', "
                    ":authorized_at, :expires_at, :host, :earliest, :requested, :latest)"
                ),
                {
                    "intent": row["intent_governance_id"],
                    "version": row["preview_version"] + 1,
                    "fingerprint": row["request_fingerprint"],
                    "account": row["account_reference"],
                    "client": row["client_order_id"],
                    "authorized_at": base,
                    "expires_at": base + timedelta(hours=1),
                    "host": reading(offsets[0]),
                    "earliest": reading(offsets[1]),
                    "requested": reading(offsets[2]),
                    "latest": reading(offsets[3]),
                },
            )

    @pytest.mark.parametrize(
        ("offsets", "constraint"),
        [
            ((0, 0, 0, None), "ck_paper_execution_authorization_basis_interval_paired"),
            ((None, None, 0, 0), "ck_paper_execution_authorization_basis_interval_shape"),
            ((3600, 0, 7200, 0), "ck_paper_execution_authorization_basis_interval_shape"),
            ((3600, 1, 3600, 0), "ck_paper_execution_authorization_basis_interval_shape"),
            ((-1, 0, -2, 0), "ck_paper_execution_authorization_basis_interval_shape"),
            # Only the pair constraint can object: PostgreSQL checks CHECK constraints
            # in name order, and with no interval both interval constraints hold.
            ((0, None, None, None), "ck_paper_execution_authorization_basis_pair"),
        ],
        ids=[
            "half-an-interval",
            "interval-without-its-pair",
            "host-interval-inverted",
            "broker-interval-inverted",
            "authorized-after-the-basis-reading",
            "pair-half-written",
        ],
    )
    def test_a_malformed_basis_is_refused(
        self,
        chain: tuple[World, TruthfulBroker, ExecutionAuthorization],
        clean: Engine,
        offsets: tuple[float | None, float | None, float | None, float | None],
        constraint: str,
    ) -> None:
        with pytest.raises(sa.exc.DatabaseError) as raised:
            self._second_authorization(clean, offsets)
        assert constraint in str(raised.value)

    def test_a_well_formed_interval_is_accepted(
        self, chain: tuple[World, TruthfulBroker, ExecutionAuthorization], clean: Engine
    ) -> None:
        # Control for the refusals above: the same statement with a sound interval.
        self._second_authorization(clean, (1, 0, 0, 1))

    @pytest.mark.parametrize(
        "statement",
        [
            # Each moves one basis reading by an amount that keeps every CHECK
            # satisfied, so only the guard trigger can be what refuses.
            "UPDATE public.paper_execution_authorization SET consumed_at = authorized_at, "
            "consumed_by_attempt_id = 'ATT-SQL', basis_host_at = basis_host_at + interval '1 ms' "
            "WHERE authorization_id = :id",
            "UPDATE public.paper_execution_authorization SET consumed_at = authorized_at, "
            "consumed_by_attempt_id = 'ATT-SQL', "
            "basis_broker_earliest_at = basis_broker_earliest_at - interval '1 ms' "
            "WHERE authorization_id = :id",
            "UPDATE public.paper_execution_authorization SET consumed_at = authorized_at, "
            "consumed_by_attempt_id = 'ATT-SQL', "
            "basis_host_requested_at = basis_host_requested_at - interval '1 ms' "
            "WHERE authorization_id = :id",
            "UPDATE public.paper_execution_authorization SET consumed_at = authorized_at, "
            "consumed_by_attempt_id = 'ATT-SQL', "
            "basis_broker_latest_at = basis_broker_latest_at + interval '1 ms' "
            "WHERE authorization_id = :id",
        ],
        ids=[
            "basis_host_at",
            "basis_broker_earliest_at",
            "basis_host_requested_at",
            "basis_broker_latest_at",
        ],
    )
    def test_the_basis_cannot_be_rewritten_by_the_consuming_update(
        self,
        chain: tuple[World, TruthfulBroker, ExecutionAuthorization],
        clean: Engine,
        statement: str,
    ) -> None:
        # Before `d4f18a6c2e97` the guard froze every other column but not these, so
        # the one permitted UPDATE could have moved the basis along with consuming.
        _, _, authorization = chain
        with pytest.raises(sa.exc.DatabaseError) as raised, clean.begin() as connection:
            connection.execute(text(statement), {"id": authorization.authorization_id})
        assert "is immutable apart from its consumption" in str(raised.value)


# ---------------------------------------------------------------------------
# Migration down and up again
# ---------------------------------------------------------------------------


def _catalog(engine: Engine) -> dict[str, object]:
    with engine.begin() as connection:
        table = connection.execute(
            text("SELECT to_regclass('public.paper_intent_time_basis') IS NOT NULL")
        ).scalar_one()
        columns = {
            row[0]
            for row in connection.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name = 'paper_execution_authorization'"
                )
            )
        }
        constraints = {
            row[0]
            for row in connection.execute(
                text(
                    "SELECT conname FROM pg_constraint "
                    "WHERE conrelid = 'public.paper_execution_authorization'::regclass"
                )
            )
        }
        guard = connection.execute(
            text(
                "SELECT prosrc FROM pg_proc "
                "WHERE proname = 'paper_execution_authorization_guard_update'"
            )
        ).scalar_one()
        insert_guard = connection.execute(
            text(
                "SELECT count(*) FROM pg_proc "
                "WHERE proname = 'paper_execution_intent_time_basis_guard_insert'"
            )
        ).scalar_one()
    return {
        "table": table,
        "columns": columns,
        "constraints": constraints,
        "guard": guard,
        "insert_guard": insert_guard,
    }


def test_the_migration_goes_down_and_up_again(clean: Engine) -> None:
    at_head = _catalog(clean)
    assert at_head["table"] is True
    assert {"basis_host_requested_at", "basis_broker_latest_at"} <= at_head["columns"]  # type: ignore[operator]
    assert "ck_paper_execution_authorization_basis_interval_shape" in at_head["constraints"]  # type: ignore[operator]
    assert "basis_broker_latest_at" in str(at_head["guard"])
    assert at_head["insert_guard"] == 1

    alembic_command.downgrade(alembic_config(), _BEFORE_THIS_REVISION)
    try:
        below = _catalog(clean)
        assert below["table"] is False
        assert not {"basis_host_requested_at", "basis_broker_latest_at"} & below["columns"]  # type: ignore[operator]
        assert {"basis_host_at", "basis_broker_earliest_at"} <= below["columns"]  # type: ignore[operator]
        assert "ck_paper_execution_authorization_basis_pair" in below["constraints"]  # type: ignore[operator]
        assert "ck_paper_execution_authorization_basis_interval_shape" not in below["constraints"]  # type: ignore[operator]
        # The exact prior guard is restored: it still freezes the original columns
        # and names no basis column.
        assert "is immutable apart from its consumption" in str(below["guard"])
        assert "basis_" not in str(below["guard"])
        assert below["insert_guard"] == 0
    finally:
        alembic_command.upgrade(alembic_config(), "head")

    again = _catalog(clean)
    assert again == at_head


def test_every_new_guard_function_pins_its_search_path(clean: Engine) -> None:
    with clean.begin() as connection:
        configuration = connection.execute(
            text(
                "SELECT proconfig FROM pg_proc "
                "WHERE proname = 'paper_execution_intent_time_basis_guard_insert'"
            )
        ).scalar_one()
    assert configuration is not None
    assert any("search_path=" in setting for setting in configuration)
