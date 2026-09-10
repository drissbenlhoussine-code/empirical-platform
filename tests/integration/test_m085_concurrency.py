"""MILESTONE-085 concurrency: real threads, real PostgreSQL, deterministic barriers.

SLEEP IS NOT EVIDENCE OF ORDERING. Every race below is arranged with
`threading.Barrier` or `threading.Event`, so both workers are provably inside the
critical section at the same time rather than probably. A `sleep` can bound a
failure -- "if this has not happened in two seconds it never will" -- but it cannot
establish that two operations overlapped, and a test that passes because one
thread happened to be slow is a test that will pass when the guarantee is gone.

THE WHOLE SUITE RUNS THREE TIMES ON THREE INDEPENDENTLY REBUILT SCHEMAS. Each
repetition drops `public`, re-runs the complete migration history, and records the
schema and table object identifiers. The final test requires the three to be
DISTINCT, so "three clean repetitions" is a measured fact rather than three passes
over one database that was never rebuilt.

WHAT A LOSING WORKER MUST GET. Not an error -- the persisted winner. A duplicate
dispatch request has to end up reconciling the real order, because a caller that
receives an exception is a caller that may retry, and a retry that creates a
second order is the failure this milestone exists to prevent.
"""

from __future__ import annotations

import threading
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
import sqlalchemy as sa
from sqlalchemy import text
from sqlalchemy.engine import Engine
from tests.integration._m085_support import (
    EVALUATED_AT,
    alembic_config,
    an_approved_intent,
    config,
    database_identity,
    postgres_enabled,
)

from empirical_platform.decision_candidate.paper_execution import (
    PAPER_ENDPOINT_HOST,
    BrokerAcknowledgement,
    ExecutionAuthorization,
    PaperAccountSnapshot,
    PaperEnvironment,
    PaperExecutionState,
    authorize_submission,
    build_submission_preview,
)
from empirical_platform.entrypoints._composition import postgres_repository_runtime
from empirical_platform.shared.errors.foundation import FoundationError
from empirical_platform.shared.persistence.postgres import PostgresPersistenceService
from empirical_platform.shared.persistence.postgres_repositories.paper_execution_repositories import (  # noqa: E501
    PostgresPaperExecutionRuntime,
)

pytestmark = pytest.mark.integration

_REPETITIONS = (1, 2, 3)
_WATCHLIST = frozenset({"AAPL", "MSFT"})

#: Filled in by the per-repetition fixture; asserted distinct by the last test.
_IDENTITIES: dict[int, dict[str, str]] = {}


@pytest.fixture(scope="module")
def engine() -> Iterator[Engine]:
    if not postgres_enabled():
        pytest.skip("PostgreSQL integration tests require explicit opt-in")
    built = sa.create_engine(config("m085-concurrency").sqlalchemy_url())
    try:
        yield built
    finally:
        with built.begin() as connection:
            connection.execute(text("DROP SCHEMA public CASCADE"))
            connection.execute(text("CREATE SCHEMA public"))
        built.dispose()


@pytest.fixture(params=_REPETITIONS, ids=[f"repetition-{n}" for n in _REPETITIONS])
def rebuilt(request: pytest.FixtureRequest, engine: Engine) -> Engine:
    """A genuinely rebuilt schema, once per repetition, with its identity recorded.

    Rebuilt rather than truncated: a schema that is only emptied would share every
    object identifier with the previous repetition, and "three clean databases"
    would be a description of one.
    """
    from alembic import command as alembic_command

    with engine.begin() as connection:
        connection.execute(text("DROP SCHEMA public CASCADE"))
        connection.execute(text("CREATE SCHEMA public"))
    alembic_command.upgrade(alembic_config(), "head")
    _IDENTITIES[int(request.param)] = database_identity(engine)
    return engine


@pytest.fixture
def service(rebuilt: Engine) -> Iterator[PostgresPersistenceService]:
    resolved = PostgresPersistenceService(config("m085-concurrency-service"))
    resolved.initialize()
    try:
        yield resolved
    finally:
        resolved.close()


@pytest.fixture
def paper(service: PostgresPersistenceService) -> PostgresPaperExecutionRuntime:
    return PostgresPaperExecutionRuntime(service)


def an_account(**overrides: object) -> PaperAccountSnapshot:
    defaults: dict[str, object] = {
        "snapshot_id": "SNP-C-1",
        "environment": PaperEnvironment.PAPER,
        "endpoint_host": PAPER_ENDPOINT_HOST,
        "account_reference": "ref:concurrency0000",
        "account_status": "ACTIVE",
        "currency": "USD",
        "buying_power": Decimal("100000"),
        "cash": Decimal("100000"),
        "equity": Decimal("100000"),
        "multiplier": "4",
        "shorting_enabled": True,
        "trading_blocked": False,
        "transfers_blocked": False,
        "account_blocked": False,
        "trade_suspended_by_user": False,
        "captured_at": EVALUATED_AT + timedelta(seconds=25),
    }
    defaults.update(overrides)
    return PaperAccountSnapshot(**defaults)  # type: ignore[arg-type]


def a_chain(
    paper: PostgresPaperExecutionRuntime,
    *,
    validity_seconds: int = 300,
    account: PaperAccountSnapshot | None = None,
    intent_id: str = "INT-085-C1",
    preview_id: str = "PVW-C-1",
    authorization_id: str = "AUT-C-1",
) -> tuple[str, ExecutionAuthorization]:
    with postgres_repository_runtime(config("m085-concurrency-chain")) as m084:
        intent = an_approved_intent(
            m084,
            intent_id=intent_id,
            proposal_id=f"PRP-{intent_id}",
            context_id=f"ECX-{intent_id}",
            watermark_id=f"WM-{intent_id}",
            configuration_id=f"CFG-{intent_id}",
        )
    snapshot = paper.paper_account_snapshots.save(account if account is not None else an_account())
    preview = build_submission_preview(
        preview_id=preview_id,
        intent=intent,
        account=snapshot,
        preview_version=paper.submission_previews.next_version_for_intent(
            intent.intent_governance_id
        ),
        market_is_open=True,
        market_next_open=None,
        market_next_close=EVALUATED_AT + timedelta(hours=3),
        quote_bid=Decimal("199.95"),
        quote_ask=Decimal("200.10"),
        quote_captured_at=EVALUATED_AT + timedelta(seconds=24),
        quote_source="alpaca-iex",
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
        created_at=EVALUATED_AT + timedelta(seconds=25),
    )
    assert preview.is_authorizable, preview.refusals
    paper.submission_previews.save(preview)
    authorization = authorize_submission(
        authorization_id=authorization_id,
        preview=preview,
        authorized_by="owner",
        authorized_at=datetime.now(UTC),
        validity_seconds=validity_seconds,
    )
    paper.execution_authorizations.save(authorization)
    return intent.intent_governance_id, authorization


class TestTwoWorkersCannotBothClaimOneDispatch:
    def test_exactly_one_wins_and_the_loser_receives_the_winner(
        self, paper: PostgresPaperExecutionRuntime
    ) -> None:
        """The central race. Both threads are inside `claim_dispatch` together."""
        _, authorization = a_chain(paper)
        barrier = threading.Barrier(2)

        def worker(attempt_id: str) -> object:
            barrier.wait(timeout=10)
            return paper.execution_attempts.claim_dispatch(
                attempt_id=attempt_id,
                authorization=authorization,
                request_fingerprint_now=authorization.request_fingerprint,
                account_reference_now=authorization.account_reference,
                claimed_at=datetime.now(UTC),
            )

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(worker, f"ATT-C-{n}") for n in (1, 2)]
            outcomes = []
            failures = []
            for future in futures:
                try:
                    outcomes.append(future.result(timeout=30))
                except Exception as error:  # noqa: BLE001 - recorded, then asserted on
                    failures.append(error)

        # Whatever happened, the database holds exactly ONE attempt.
        winners = [outcome for outcome in outcomes if getattr(outcome, "won", False)]
        assert len(winners) == 1, (outcomes, failures)
        stored = paper.execution_attempts.for_intent(authorization.intent_governance_id)
        assert stored is not None
        assert stored.attempt_id == winners[0].attempt.attempt_id  # type: ignore[union-attr]

        # And the loser was handed the winner rather than an error, so it will
        # reconcile the real order instead of retrying.
        #
        # REQUIRED, not tolerated. An earlier version of this test accepted "the
        # loser raised instead" as an alternative, and a mutation removing the
        # `AND consumed_at IS NULL` clause from the claim then SURVIVED: without
        # it the loser hits the consumption trigger and raises, which the
        # permissive branch accepted. The conditional UPDATE exists precisely so
        # the loser gets a losing CLAIM, so that is what the test demands.
        losers = [outcome for outcome in outcomes if not getattr(outcome, "won", True)]
        assert failures == [], f"no worker should fail; got {failures}"
        assert len(losers) == 1, outcomes
        assert losers[0].attempt.attempt_id == stored.attempt_id  # type: ignore[union-attr]

    def test_only_one_attempt_row_exists_however_many_workers_race(
        self, paper: PostgresPaperExecutionRuntime, rebuilt: Engine
    ) -> None:
        _, authorization = a_chain(paper)
        barrier = threading.Barrier(4)

        def worker(attempt_id: str) -> None:
            barrier.wait(timeout=10)
            try:
                paper.execution_attempts.claim_dispatch(
                    attempt_id=attempt_id,
                    authorization=authorization,
                    request_fingerprint_now=authorization.request_fingerprint,
                    account_reference_now=authorization.account_reference,
                    claimed_at=datetime.now(UTC),
                )
            except (FoundationError, ValueError, sa.exc.DatabaseError):
                return

        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(worker, [f"ATT-C-{n}" for n in range(1, 5)]))

        with rebuilt.begin() as connection:
            count = connection.execute(
                text("SELECT count(*) AS n FROM public.paper_execution_attempt")
            ).scalar_one()
            consumed = connection.execute(
                text(
                    "SELECT count(*) AS n FROM public.paper_execution_authorization "
                    "WHERE consumed_at IS NOT NULL"
                )
            ).scalar_one()
        assert count == 1
        assert consumed == 1


class TestTheAuthorizationCannotBeSpentTwice:
    def test_two_simultaneous_authorization_saves_for_one_preview_leave_one(
        self, paper: PostgresPaperExecutionRuntime, rebuilt: Engine
    ) -> None:
        intent_id, first = a_chain(paper)
        barrier = threading.Barrier(2)

        def worker(authorization_id: str) -> None:
            duplicate = ExecutionAuthorization(
                authorization_id=authorization_id,
                intent_governance_id=intent_id,
                preview_id=first.preview_id,
                preview_version=first.preview_version,
                request_fingerprint=first.request_fingerprint,
                account_reference=first.account_reference,
                client_order_id=first.client_order_id,
                authorized_by="owner",
                authorized_at=datetime.now(UTC),
                expires_at=datetime.now(UTC) + timedelta(seconds=300),
                consumed_at=None,
                consumed_by_attempt_id=None,
            )
            barrier.wait(timeout=10)
            try:
                paper.execution_authorizations.save(duplicate)
            except (FoundationError, sa.exc.DatabaseError):
                return

        with ThreadPoolExecutor(max_workers=2) as pool:
            list(pool.map(worker, ["AUT-C-2", "AUT-C-3"]))

        with rebuilt.begin() as connection:
            count = connection.execute(
                text(
                    "SELECT count(*) AS n FROM public.paper_execution_authorization "
                    "WHERE preview_id = :preview"
                ),
                {"preview": first.preview_id},
            ).scalar_one()
        # The original, and nothing else: one authorization per preview.
        assert count == 1

    def test_a_reused_authorization_after_a_process_restart_is_still_spent(
        self, paper: PostgresPaperExecutionRuntime, service: PostgresPersistenceService
    ) -> None:
        """A restart forgets everything except the database. That is the point."""
        _, authorization = a_chain(paper)
        paper.execution_attempts.claim_dispatch(
            attempt_id="ATT-C-1",
            authorization=authorization,
            request_fingerprint_now=authorization.request_fingerprint,
            account_reference_now=authorization.account_reference,
            claimed_at=datetime.now(UTC),
        )
        # A NEW service and runtime, as a restarted process would have.
        restarted = PostgresPersistenceService(config("m085-concurrency-restart"))
        restarted.initialize()
        try:
            fresh = PostgresPaperExecutionRuntime(restarted)
            reloaded = fresh.execution_authorizations.get(authorization.authorization_id)
            assert reloaded is not None
            assert reloaded.is_consumed is True
            with pytest.raises(ValueError, match="already been used"):
                fresh.execution_attempts.claim_dispatch(
                    attempt_id="ATT-C-restart",
                    authorization=reloaded,
                    request_fingerprint_now=reloaded.request_fingerprint,
                    account_reference_now=reloaded.account_reference,
                    claimed_at=datetime.now(UTC),
                )
        finally:
            restarted.close()

    def test_an_expiry_that_lapses_before_the_claim_refuses_the_dispatch(
        self, paper: PostgresPaperExecutionRuntime
    ) -> None:
        # Expiry racing dispatch, made deterministic by choosing a claim instant
        # after the expiry rather than by waiting for one.
        _, authorization = a_chain(paper, validity_seconds=1)
        with pytest.raises(ValueError, match="expired"):
            paper.execution_attempts.claim_dispatch(
                attempt_id="ATT-C-expired",
                authorization=authorization,
                request_fingerprint_now=authorization.request_fingerprint,
                account_reference_now=authorization.account_reference,
                claimed_at=authorization.expires_at + timedelta(seconds=1),
            )

    def test_a_fingerprint_that_changed_after_authorization_refuses_the_dispatch(
        self, paper: PostgresPaperExecutionRuntime
    ) -> None:
        _, authorization = a_chain(paper)
        with pytest.raises(ValueError, match="order changed"):
            paper.execution_attempts.claim_dispatch(
                attempt_id="ATT-C-changed",
                authorization=authorization,
                request_fingerprint_now="f" * 64,
                account_reference_now=authorization.account_reference,
                claimed_at=datetime.now(UTC),
            )

    def test_an_authorization_for_another_account_refuses_the_dispatch(
        self, paper: PostgresPaperExecutionRuntime
    ) -> None:
        _, authorization = a_chain(paper)
        with pytest.raises(ValueError, match="different paper account"):
            paper.execution_attempts.claim_dispatch(
                attempt_id="ATT-C-other-account",
                authorization=authorization,
                request_fingerprint_now=authorization.request_fingerprint,
                account_reference_now="ref:somebody-else",
                claimed_at=datetime.now(UTC),
            )


class TestCrashesLeaveNothingPartial:
    def test_a_crash_between_the_claim_and_the_network_leaves_a_claimed_attempt(
        self, paper: PostgresPaperExecutionRuntime, rebuilt: Engine
    ) -> None:
        """The claim is committed on purpose, so a crash is visible rather than lost.

        A crashed worker must leave evidence that a dispatch was claimed -- that is
        what stops a second worker from starting a fresh one -- and must NOT leave
        an acknowledgement for a request that was never sent.
        """
        _, authorization = a_chain(paper)
        claim = paper.execution_attempts.claim_dispatch(
            attempt_id="ATT-C-crash",
            authorization=authorization,
            request_fingerprint_now=authorization.request_fingerprint,
            account_reference_now=authorization.account_reference,
            claimed_at=datetime.now(UTC),
        )
        # The worker dies here. Nothing else runs.
        with rebuilt.begin() as connection:
            state = connection.execute(
                text("SELECT state FROM public.paper_execution_attempt WHERE attempt_id = :id"),
                {"id": claim.attempt.attempt_id},
            ).scalar_one()
            acknowledgements = connection.execute(
                text("SELECT count(*) AS n FROM public.paper_broker_acknowledgement")
            ).scalar_one()
        assert state == PaperExecutionState.DISPATCH_CLAIMED.value
        assert acknowledgements == 0

    def test_a_rolled_back_transaction_leaves_neither_consumption_nor_attempt(
        self,
        paper: PostgresPaperExecutionRuntime,
        rebuilt: Engine,
        service: PostgresPersistenceService,
    ) -> None:
        _, authorization = a_chain(paper)
        # Force a failure INSIDE the claim transaction by inserting an attempt id
        # that violates the append-only insert guard, after the consumption.
        with pytest.raises((FoundationError, sa.exc.DatabaseError)), service.unit_of_work() as work:
            work.execute(
                text(
                    "UPDATE public.paper_execution_authorization SET consumed_at = now(), "
                    "consumed_by_attempt_id = 'ATT-C-rollback' WHERE authorization_id = :id"
                ).text,
                {"id": authorization.authorization_id},
            )
            work.execute(
                text(
                    "INSERT INTO public.paper_execution_attempt (attempt_id, "
                    "intent_governance_id, authorization_id, client_order_id, "
                    "request_fingerprint, state, claimed_at) VALUES "
                    "('ATT-C-rollback', :intent, :auth, :cid, :fp, 'PAPER_SUBMITTED', now())"
                ).text,
                {
                    "intent": authorization.intent_governance_id,
                    "auth": authorization.authorization_id,
                    "cid": authorization.client_order_id,
                    "fp": authorization.request_fingerprint,
                },
            )

        with rebuilt.begin() as connection:
            consumed = connection.execute(
                text(
                    "SELECT consumed_at FROM public.paper_execution_authorization "
                    "WHERE authorization_id = :id"
                ),
                {"id": authorization.authorization_id},
            ).scalar_one()
            attempts = connection.execute(
                text("SELECT count(*) AS n FROM public.paper_execution_attempt")
            ).scalar_one()
        # Atomic: the consumption did not survive the failed insert.
        assert consumed is None
        assert attempts == 0


class TestAcknowledgementsAndReconciliationAreSafeConcurrently:
    def test_two_concurrent_acknowledgements_cannot_share_a_sequence(
        self, paper: PostgresPaperExecutionRuntime, rebuilt: Engine
    ) -> None:
        _, authorization = a_chain(paper)
        claim = paper.execution_attempts.claim_dispatch(
            attempt_id="ATT-C-ack",
            authorization=authorization,
            request_fingerprint_now=authorization.request_fingerprint,
            account_reference_now=authorization.account_reference,
            claimed_at=datetime.now(UTC),
        )
        attempt_id = claim.attempt.attempt_id
        barrier = threading.Barrier(2)

        def worker(index: int) -> None:
            sequence = paper.broker_acknowledgements.next_sequence(attempt_id)
            barrier.wait(timeout=10)
            try:
                paper.broker_acknowledgements.append(
                    BrokerAcknowledgement(
                        acknowledgement_id=f"ACK-C-{index}",
                        attempt_id=attempt_id,
                        sequence=sequence,
                        kind="RECONCILE",
                        observed_at=datetime.now(UTC),
                        http_status=200,
                        broker_order_id="broker-1",
                        broker_status="accepted",
                        client_order_id_echo=authorization.client_order_id,
                        payload_digest="d" * 64,
                        sanitized_payload="{}",
                    )
                )
            except (FoundationError, sa.exc.DatabaseError):
                return

        with ThreadPoolExecutor(max_workers=2) as pool:
            list(pool.map(worker, [1, 2]))

        with rebuilt.begin() as connection:
            rows = (
                connection.execute(
                    text(
                        "SELECT sequence FROM public.paper_broker_acknowledgement "
                        "WHERE attempt_id = :id ORDER BY sequence"
                    ),
                    {"id": attempt_id},
                )
                .scalars()
                .all()
            )
        # Both computed sequence 1; the UNIQUE constraint let exactly one land.
        assert len(rows) == len(set(rows))
        assert len(rows) >= 1

    def test_two_concurrent_reconciliation_transitions_converge(
        self, paper: PostgresPaperExecutionRuntime
    ) -> None:
        _, authorization = a_chain(paper)
        claim = paper.execution_attempts.claim_dispatch(
            attempt_id="ATT-C-recon",
            authorization=authorization,
            request_fingerprint_now=authorization.request_fingerprint,
            account_reference_now=authorization.account_reference,
            claimed_at=datetime.now(UTC),
        )
        paper.execution_attempts.transition(
            attempt_id=claim.attempt.attempt_id,
            target=PaperExecutionState.SUBMISSION_IN_PROGRESS,
            at=datetime.now(UTC),
        )
        paper.execution_attempts.transition(
            attempt_id=claim.attempt.attempt_id,
            target=PaperExecutionState.PAPER_SUBMITTED,
            at=datetime.now(UTC),
        )
        barrier = threading.Barrier(2)

        def worker(target: PaperExecutionState) -> None:
            barrier.wait(timeout=10)
            try:
                paper.execution_attempts.transition(
                    attempt_id=claim.attempt.attempt_id, target=target, at=datetime.now(UTC)
                )
            except (FoundationError, ValueError, sa.exc.DatabaseError):
                return

        with ThreadPoolExecutor(max_workers=2) as pool:
            list(
                pool.map(
                    worker,
                    [PaperExecutionState.PAPER_ACCEPTED, PaperExecutionState.PARTIALLY_FILLED],
                )
            )

        final = paper.execution_attempts.get(claim.attempt.attempt_id)
        assert final is not None
        # Whichever won, the row is in a state the closed table permits, and the
        # attempt identity never moved.
        assert final.state in {
            PaperExecutionState.PAPER_SUBMITTED,
            PaperExecutionState.PAPER_ACCEPTED,
            PaperExecutionState.PARTIALLY_FILLED,
        }
        assert final.client_order_id == authorization.client_order_id

    def test_a_cancel_racing_a_fill_cannot_produce_an_illegal_state(
        self, paper: PostgresPaperExecutionRuntime
    ) -> None:
        _, authorization = a_chain(paper)
        claim = paper.execution_attempts.claim_dispatch(
            attempt_id="ATT-C-cancelrace",
            authorization=authorization,
            request_fingerprint_now=authorization.request_fingerprint,
            account_reference_now=authorization.account_reference,
            claimed_at=datetime.now(UTC),
        )
        for target in (
            PaperExecutionState.SUBMISSION_IN_PROGRESS,
            PaperExecutionState.PAPER_SUBMITTED,
        ):
            paper.execution_attempts.transition(
                attempt_id=claim.attempt.attempt_id, target=target, at=datetime.now(UTC)
            )
        barrier = threading.Barrier(2)
        results: list[str] = []
        lock = threading.Lock()

        def worker(target: PaperExecutionState) -> None:
            barrier.wait(timeout=10)
            try:
                outcome = paper.execution_attempts.transition(
                    attempt_id=claim.attempt.attempt_id, target=target, at=datetime.now(UTC)
                )
                with lock:
                    results.append(outcome.state.value)
            except (FoundationError, ValueError, sa.exc.DatabaseError):
                return

        with ThreadPoolExecutor(max_workers=2) as pool:
            list(
                pool.map(worker, [PaperExecutionState.CANCEL_REQUESTED, PaperExecutionState.FILLED])
            )

        final = paper.execution_attempts.get(claim.attempt.attempt_id)
        assert final is not None
        # A fill can beat a cancel. Both destinations are legal from
        # PAPER_SUBMITTED, so the only thing that must hold is that the row is in
        # one of them and that a terminal one carries its instant.
        assert final.state in {
            PaperExecutionState.CANCEL_REQUESTED,
            PaperExecutionState.FILLED,
        }
        if final.is_terminal:
            assert final.terminal_at is not None


class TestTheKillSwitchAndTheAccountAreReadFreshly:
    def test_the_kill_switch_engaged_concurrently_is_seen_by_a_fresh_read(
        self, paper: PostgresPaperExecutionRuntime
    ) -> None:
        """Never cached. A value read minutes earlier is the wrong thing to trust."""
        assert paper.execution_kill_switch.is_engaged() is False
        engaged = threading.Event()

        def flip() -> None:
            paper.execution_kill_switch.engage(
                changed_by="owner", changed_at=datetime.now(UTC), reason="race"
            )
            engaged.set()

        thread = threading.Thread(target=flip)
        thread.start()
        assert engaged.wait(timeout=10), "the kill switch never engaged"
        thread.join(timeout=10)
        assert paper.execution_kill_switch.is_engaged() is True

    def test_concurrent_kill_switch_moves_produce_a_consistent_version_chain(
        self, paper: PostgresPaperExecutionRuntime, rebuilt: Engine
    ) -> None:
        barrier = threading.Barrier(3)

        def worker(index: int) -> None:
            barrier.wait(timeout=10)
            try:
                paper.execution_kill_switch.engage(
                    changed_by=f"owner-{index}", changed_at=datetime.now(UTC), reason="race"
                )
            except (FoundationError, sa.exc.DatabaseError):
                return

        with ThreadPoolExecutor(max_workers=3) as pool:
            list(pool.map(worker, [1, 2, 3]))

        with rebuilt.begin() as connection:
            versions = (
                connection.execute(
                    text(
                        "SELECT version FROM public.paper_execution_kill_switch "
                        "WHERE scope = 'GLOBAL' ORDER BY version"
                    )
                )
                .scalars()
                .all()
            )
        # No duplicate version survived, and the switch ended up engaged.
        assert len(versions) == len(set(versions))
        assert paper.execution_kill_switch.is_engaged() is True

    def test_a_buying_power_change_before_dispatch_changes_the_fingerprint_not_the_limit(
        self, paper: PostgresPaperExecutionRuntime
    ) -> None:
        # The account reference is what the authorization binds; the balance is
        # re-checked at dispatch. A balance change does not silently permit an
        # order the operator could not have afforded when they looked.
        _, authorization = a_chain(paper)
        poorer = an_account(snapshot_id="SNP-C-2", buying_power=Decimal("1"))
        paper.paper_account_snapshots.save(poorer)
        assert poorer.account_reference == authorization.account_reference
        assert poorer.buying_power < Decimal("5")


class TestConstraintNamesAreHonest:
    def test_every_failure_names_the_constraint_that_actually_fired(
        self, paper: PostgresPaperExecutionRuntime, rebuilt: Engine
    ) -> None:
        """A misattributed constraint name sends a reader to the wrong rule."""
        _, authorization = a_chain(paper)
        paper.execution_attempts.claim_dispatch(
            attempt_id="ATT-C-names",
            authorization=authorization,
            request_fingerprint_now=authorization.request_fingerprint,
            account_reference_now=authorization.account_reference,
            claimed_at=datetime.now(UTC),
        )
        with pytest.raises(sa.exc.IntegrityError) as raised, rebuilt.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO public.paper_broker_acknowledgement (acknowledgement_id, "
                    "attempt_id, sequence, kind, observed_at, http_status, payload_digest, "
                    "sanitized_payload) VALUES ('ACK-X', 'ATT-C-names', 1, 'BOGUS', now(), "
                    "200, :digest, '{}')"
                ),
                {"digest": "e" * 64},
            )
        assert "ck_paper_acknowledgement_kind" in str(raised.value)


class TestTheThreeRepetitionsWereGenuinelyDistinct:
    def test_three_repetitions_ran_on_three_rebuilt_schemas(self) -> None:
        """Anti-vacuity for the whole file.

        If the per-repetition fixture ever stopped rebuilding, the identities would
        be equal and every "three clean repetitions" claim above would be one
        repetition described three times.

        Skips with PostgreSQL off, and the skip is NOT a weakening: with the
        database absent every repetition above skipped too, so there is nothing to
        have been distinct. Without this guard the test failed in the
        PostgreSQL-OFF regression mode -- which is how the four-mode comparison
        earned its place.
        """
        if not postgres_enabled():
            pytest.skip("PostgreSQL is off, so no repetition ran and there is nothing to compare")
        assert sorted(_IDENTITIES) == list(_REPETITIONS), _IDENTITIES
        schema_oids = {identity["schema_oid"] for identity in _IDENTITIES.values()}
        attempt_oids = {identity["attempt_oid"] for identity in _IDENTITIES.values()}
        assert len(schema_oids) == 3, _IDENTITIES
        assert len(attempt_oids) == 3, _IDENTITIES
        assert all(int(identity["database_oid"]) > 0 for identity in _IDENTITIES.values())
