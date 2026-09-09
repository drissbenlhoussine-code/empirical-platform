"""MILESTONE-085 -- what the DATABASE refuses, proved against a real PostgreSQL.

Every rule here is also enforced in the domain layer. That is not duplication:
the domain refusal is the legible one a developer meets first, and the refusal
below is the one that still applies to a `psql` session, a future repository
written in a hurry, or a direct SQL writer who never imported this package. A
capability boundary that exists only in application code is a boundary one
import away from being bypassed.

MOST OF THESE TESTS ATTACK WITH RAW SQL ON PURPOSE. Going through the repository
would prove the repository refuses -- which the domain suite already proves. The
question this file answers is different: if the application were wrong, or
absent, would the database still refuse? So the attacks are `INSERT`/`UPDATE`
statements issued straight at the engine.

THE LIMIT OF THIS CLAIM, STATED BEFORE THE EVIDENCE. What is proved is ROW-LEVEL
UPDATE/DELETE REFUSAL UNDER THE INSTALLED TRIGGERS. `TRUNCATE` is statement-level
and not intercepted by a row trigger; `DROP TRIGGER`, `DROP TABLE`,
`ALTER TABLE ... DISABLE TRIGGER`, `session_replication_role = replica` and a
superuser all remain outside the boundary. Two tests below EXECUTE that limit
rather than describing it, because a limitation asserted in prose is a limitation
nobody has checked.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
import sqlalchemy as sa
from sqlalchemy import text
from sqlalchemy.engine import Engine
from tests.integration._m085_support import (
    EVALUATED_AT,
    a_configuration,
    an_approved_intent,
    build_engine,
    config,
    database_identity,
    truncate_all,
)

from empirical_platform.decision_candidate.paper_execution import (
    ALLOWED_PAPER_TRANSITIONS,
    PAPER_ENDPOINT_HOST,
    TERMINAL_PAPER_STATES,
    BrokerAcknowledgement,
    ExecutionAuthorization,
    PaperAccountSnapshot,
    PaperEnvironment,
    PaperExecutionEvent,
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

_WATCHLIST = frozenset({"AAPL", "MSFT"})


@pytest.fixture(scope="module")
def engine() -> Iterator[Engine]:
    yield from build_engine()


@pytest.fixture
def clean(engine: Engine) -> Engine:
    truncate_all(engine)
    return engine


@pytest.fixture
def service(clean: Engine) -> Iterator[PostgresPersistenceService]:
    resolved = PostgresPersistenceService(config("m085-postgres-suite"))
    resolved.initialize()
    try:
        yield resolved
    finally:
        resolved.close()


@pytest.fixture
def paper(service: PostgresPersistenceService) -> PostgresPaperExecutionRuntime:
    return PostgresPaperExecutionRuntime(service)


def an_account(
    *, snapshot_id: str = "SNP-085-0001", buying_power: str = "100000"
) -> PaperAccountSnapshot:
    return PaperAccountSnapshot(
        snapshot_id=snapshot_id,
        environment=PaperEnvironment.PAPER,
        endpoint_host=PAPER_ENDPOINT_HOST,
        account_reference="ref:0123456789abcdef",
        account_status="ACTIVE",
        currency="USD",
        buying_power=Decimal(buying_power),
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


def a_full_chain(
    paper: PostgresPaperExecutionRuntime,
    *,
    validity_seconds: int = 120,
) -> tuple[str, ExecutionAuthorization]:
    """One real M084 intent, one stored preview, one stored authorization."""
    with postgres_repository_runtime(config("m085-chain")) as m084:
        intent = an_approved_intent(m084)

    account = paper.paper_account_snapshots.save(an_account())
    preview = build_submission_preview(
        preview_id="PVW-085-0001",
        intent=intent,
        account=account,
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

    # Anchored to the real clock, not to EVALUATED_AT. Several tests below
    # consume this authorization with raw SQL using `now()`, and the database
    # refuses consuming an expired authorization -- correctly. Anchoring the
    # window here keeps those tests attacking what they mean to attack instead
    # of all failing on expiry.
    authorization = authorize_submission(
        authorization_id="AUT-085-0001",
        preview=preview,
        authorized_by="owner",
        authorized_at=datetime.now(UTC),
        validity_seconds=validity_seconds,
    )
    paper.execution_authorizations.save(authorization)
    return intent.intent_governance_id, authorization


class TestTheChainRoundTrips:
    def test_the_whole_flow_persists_and_reads_back_unchanged(
        self, paper: PostgresPaperExecutionRuntime
    ) -> None:
        intent_id, authorization = a_full_chain(paper)
        assert paper.execution_authorizations.get(authorization.authorization_id) == authorization

        claim = paper.execution_attempts.claim_dispatch(
            attempt_id="ATT-085-0001",
            authorization=authorization,
            request_fingerprint_now=authorization.request_fingerprint,
            account_reference_now=authorization.account_reference,
            claimed_at=datetime.now(UTC),
        )
        assert claim.won is True
        assert claim.attempt.state is PaperExecutionState.DISPATCH_CLAIMED
        assert claim.attempt.client_order_id == authorization.client_order_id
        assert paper.execution_attempts.for_intent(intent_id) == claim.attempt
        assert (
            paper.execution_attempts.by_client_order_id(authorization.client_order_id)
            == claim.attempt
        )

        consumed = paper.execution_authorizations.get(authorization.authorization_id)
        assert consumed is not None
        assert consumed.is_consumed is True
        assert consumed.consumed_by_attempt_id == "ATT-085-0001"

    def test_every_decimal_survives_the_round_trip_exactly(
        self, paper: PostgresPaperExecutionRuntime
    ) -> None:
        # A limit price read back as a float would silently change what a human
        # authorized.
        saved = paper.paper_account_snapshots.save(an_account(buying_power="12345.67890000"))
        loaded = paper.paper_account_snapshots.get(saved.snapshot_id)
        assert loaded is not None
        assert isinstance(loaded.buying_power, Decimal)
        assert loaded.buying_power == Decimal("12345.67890000")


class TestTheDatabaseEnforcesSingleUse:
    def test_a_second_consumption_is_refused_by_the_trigger(
        self, paper: PostgresPaperExecutionRuntime, clean: Engine
    ) -> None:
        _, authorization = a_full_chain(paper)
        paper.execution_attempts.claim_dispatch(
            attempt_id="ATT-085-0001",
            authorization=authorization,
            request_fingerprint_now=authorization.request_fingerprint,
            account_reference_now=authorization.account_reference,
            claimed_at=datetime.now(UTC),
        )
        with pytest.raises(sa.exc.DatabaseError) as raised, clean.begin() as connection:
            connection.execute(
                text(
                    "UPDATE public.paper_execution_authorization "
                    "SET consumed_at = now(), consumed_by_attempt_id = 'ATT-085-0002' "
                    "WHERE authorization_id = :id"
                ),
                {"id": authorization.authorization_id},
            )
        assert "already been used" in str(raised.value)

    def test_consumption_cannot_be_undone(
        self, paper: PostgresPaperExecutionRuntime, clean: Engine
    ) -> None:
        _, authorization = a_full_chain(paper)
        paper.execution_attempts.claim_dispatch(
            attempt_id="ATT-085-0001",
            authorization=authorization,
            request_fingerprint_now=authorization.request_fingerprint,
            account_reference_now=authorization.account_reference,
            claimed_at=datetime.now(UTC),
        )
        with pytest.raises(sa.exc.DatabaseError), clean.begin() as connection:
            connection.execute(
                text(
                    "UPDATE public.paper_execution_authorization "
                    "SET consumed_at = NULL, consumed_by_attempt_id = NULL "
                    "WHERE authorization_id = :id"
                ),
                {"id": authorization.authorization_id},
            )

    def test_an_expired_authorization_cannot_be_consumed_even_by_raw_sql(
        self, paper: PostgresPaperExecutionRuntime, clean: Engine
    ) -> None:
        # The application refuses this too. The point here is that a caller who
        # read the row and then acted a minute later still cannot spend it.
        _, authorization = a_full_chain(paper, validity_seconds=1)
        with pytest.raises(sa.exc.DatabaseError) as raised, clean.begin() as connection:
            connection.execute(
                text(
                    "UPDATE public.paper_execution_authorization "
                    "SET consumed_at = :late, consumed_by_attempt_id = 'ATT-085-0009' "
                    "WHERE authorization_id = :id"
                ),
                {
                    "late": authorization.expires_at + timedelta(seconds=1),
                    "id": authorization.authorization_id,
                },
            )
        assert "expired" in str(raised.value)

    # Each statement is a LITERAL, not a formatted column name. Building these by
    # interpolation is what `ruff` S608 reports, and this milestone carries no
    # SQL-injection suppressions -- in tests either.
    @pytest.mark.parametrize(
        ("statement", "label"),
        [
            (
                "UPDATE public.paper_execution_authorization SET consumed_at = now(), "
                "consumed_by_attempt_id = 'A', request_fingerprint = :value "
                "WHERE authorization_id = :id",
                "request_fingerprint",
            ),
            (
                "UPDATE public.paper_execution_authorization SET consumed_at = now(), "
                "consumed_by_attempt_id = 'A', account_reference = :value "
                "WHERE authorization_id = :id",
                "account_reference",
            ),
            (
                "UPDATE public.paper_execution_authorization SET consumed_at = now(), "
                "consumed_by_attempt_id = 'A', client_order_id = :value "
                "WHERE authorization_id = :id",
                "client_order_id",
            ),
            (
                "UPDATE public.paper_execution_authorization SET consumed_at = now(), "
                "consumed_by_attempt_id = 'A', expires_at = CAST(:value AS timestamptz) "
                "WHERE authorization_id = :id",
                "expires_at",
            ),
            (
                "UPDATE public.paper_execution_authorization SET consumed_at = now(), "
                "consumed_by_attempt_id = 'A', authorized_by = :value "
                "WHERE authorization_id = :id",
                "authorized_by",
            ),
        ],
    )
    def test_nothing_but_consumption_may_change(
        self,
        paper: PostgresPaperExecutionRuntime,
        clean: Engine,
        statement: str,
        label: str,
    ) -> None:
        _, authorization = a_full_chain(paper)
        values = {
            "request_fingerprint": "f" * 64,
            "account_reference": "ref:somebody-else",
            "client_order_id": "m085-0000000000000000000000000000000000000000",
            "expires_at": "2099-01-01T00:00:00+00:00",
            "authorized_by": "not-the-owner",
        }
        with pytest.raises(sa.exc.DatabaseError) as raised, clean.begin() as connection:
            connection.execute(
                text(statement),
                {"value": values[label], "id": authorization.authorization_id},
            )
        assert "immutable" in str(raised.value), label


class TestTheDatabaseEnforcesOneDispatchPerIntent:
    def test_a_second_attempt_for_one_intent_is_refused(
        self, paper: PostgresPaperExecutionRuntime, clean: Engine
    ) -> None:
        intent_id, authorization = a_full_chain(paper)
        paper.execution_attempts.claim_dispatch(
            attempt_id="ATT-085-0001",
            authorization=authorization,
            request_fingerprint_now=authorization.request_fingerprint,
            account_reference_now=authorization.account_reference,
            claimed_at=datetime.now(UTC),
        )
        # The INSERT GUARD refuses this before the UNIQUE constraint is even
        # reached: the authorization already names the attempt that spent it, and
        # a second attempt is not that one. Asserting the guard's message rather
        # than a constraint name records which layer actually stopped it.
        with pytest.raises(sa.exc.DatabaseError) as raised, clean.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO public.paper_execution_attempt (attempt_id, "
                    "intent_governance_id, authorization_id, client_order_id, "
                    "request_fingerprint, state, claimed_at) VALUES "
                    "('ATT-085-0002', :intent, :auth, :cid, :fp, 'DISPATCH_CLAIMED', now())"
                ),
                {
                    "intent": intent_id,
                    "auth": authorization.authorization_id,
                    "cid": authorization.client_order_id,
                    "fp": authorization.request_fingerprint,
                },
            )
        assert "was consumed by attempt" in str(raised.value)

    def test_a_second_authorization_for_one_intent_cannot_also_be_consumed(
        self, paper: PostgresPaperExecutionRuntime, clean: Engine
    ) -> None:
        """The real second-dispatch barrier: one CONSUMED authorization per intent.

        A human may authorize again after one lapses unused, so unconsumed
        authorizations may accumulate. Only one may ever be SPENT, and that is a
        partial unique index rather than an application rule.
        """
        intent_id, first = a_full_chain(paper)
        paper.execution_attempts.claim_dispatch(
            attempt_id="ATT-085-0001",
            authorization=first,
            request_fingerprint_now=first.request_fingerprint,
            account_reference_now=first.account_reference,
            claimed_at=datetime.now(UTC),
        )
        second = ExecutionAuthorization(
            authorization_id="AUT-085-0002",
            intent_governance_id=intent_id,
            preview_id=first.preview_id,
            preview_version=first.preview_version,
            request_fingerprint=first.request_fingerprint,
            account_reference=first.account_reference,
            client_order_id=first.client_order_id,
            authorized_by="owner",
            authorized_at=datetime.now(UTC),
            expires_at=datetime.now(UTC) + timedelta(seconds=120),
            consumed_at=None,
            consumed_by_attempt_id=None,
        )
        # Even STORING a second authorization for the same preview is refused,
        # which is a tighter barrier again.
        #
        # The repository translates the driver error into a FoundationError whose
        # own message is deliberately generic -- it must not leak a DSN or driver
        # internals -- so the constraint that fired is read from the wrapped
        # cause rather than from the safe message.
        with pytest.raises(FoundationError) as raised:
            paper.execution_authorizations.save(second)
        assert "uq_paper_authorization_one_per_preview" in str(raised.value.__cause__)
        assert "password" not in str(raised.value)
        assert "postgresql://" not in str(raised.value)

    def test_the_backstop_unique_constraints_exist_in_the_catalog(self, clean: Engine) -> None:
        """The guards fire first, so these are proved structurally, not by firing.

        Recorded honestly: `uq_paper_attempt_one_per_intent` is unreachable while
        the insert guard and the partial index hold, so this test asserts it is
        PRESENT rather than pretending to have triggered it. A backstop nobody can
        reach is still worth having, and worth being clear about.
        """
        with clean.begin() as connection:
            names = {
                row[0]
                for row in connection.execute(
                    text(
                        "SELECT conname FROM pg_constraint c "
                        "JOIN pg_class t ON t.oid = c.conrelid "
                        "WHERE t.relname = 'paper_execution_attempt' AND c.contype = 'u'"
                    )
                ).all()
            }
        assert "uq_paper_attempt_one_per_intent" in names
        assert "uq_paper_attempt_client_order_id" in names
        assert "uq_paper_attempt_one_per_authorization" in names

    def test_an_attempt_without_a_consumed_authorization_is_refused(
        self, paper: PostgresPaperExecutionRuntime, clean: Engine
    ) -> None:
        intent_id, authorization = a_full_chain(paper)
        with pytest.raises(sa.exc.DatabaseError) as raised, clean.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO public.paper_execution_attempt (attempt_id, "
                    "intent_governance_id, authorization_id, client_order_id, "
                    "request_fingerprint, state, claimed_at) VALUES "
                    "('ATT-085-0003', :intent, :auth, :cid, :fp, 'DISPATCH_CLAIMED', now())"
                ),
                {
                    "intent": intent_id,
                    "auth": authorization.authorization_id,
                    "cid": authorization.client_order_id,
                    "fp": authorization.request_fingerprint,
                },
            )
        assert "consumed in the same transaction" in str(raised.value)

    def test_an_attempt_carrying_a_different_fingerprint_is_refused(
        self, paper: PostgresPaperExecutionRuntime, clean: Engine
    ) -> None:
        intent_id, authorization = a_full_chain(paper)
        with pytest.raises(sa.exc.DatabaseError) as raised, clean.begin() as connection:
            connection.execute(
                text(
                    "UPDATE public.paper_execution_authorization SET consumed_at = now(), "
                    "consumed_by_attempt_id = 'ATT-085-0004' WHERE authorization_id = :auth"
                ),
                {"auth": authorization.authorization_id},
            )
            connection.execute(
                text(
                    "INSERT INTO public.paper_execution_attempt (attempt_id, "
                    "intent_governance_id, authorization_id, client_order_id, "
                    "request_fingerprint, state, claimed_at) VALUES "
                    "('ATT-085-0004', :intent, :auth, :cid, :fp, 'DISPATCH_CLAIMED', now())"
                ),
                {
                    "intent": intent_id,
                    "auth": authorization.authorization_id,
                    "cid": authorization.client_order_id,
                    "fp": "a" * 64,
                },
            )
        assert "authorized request fingerprint" in str(raised.value)

    def test_an_attempt_carrying_a_different_client_order_id_is_refused(
        self, paper: PostgresPaperExecutionRuntime, clean: Engine
    ) -> None:
        intent_id, authorization = a_full_chain(paper)
        with pytest.raises(sa.exc.DatabaseError) as raised, clean.begin() as connection:
            connection.execute(
                text(
                    "UPDATE public.paper_execution_authorization SET consumed_at = now(), "
                    "consumed_by_attempt_id = 'ATT-085-0005' WHERE authorization_id = :auth"
                ),
                {"auth": authorization.authorization_id},
            )
            connection.execute(
                text(
                    "INSERT INTO public.paper_execution_attempt (attempt_id, "
                    "intent_governance_id, authorization_id, client_order_id, "
                    "request_fingerprint, state, claimed_at) VALUES "
                    "('ATT-085-0005', :intent, :auth, 'm085-somethingelse', :fp, "
                    "'DISPATCH_CLAIMED', now())"
                ),
                {
                    "intent": intent_id,
                    "auth": authorization.authorization_id,
                    "fp": authorization.request_fingerprint,
                },
            )
        assert "authorized client order id" in str(raised.value)

    def test_an_attempt_cannot_be_inserted_already_submitted(
        self, paper: PostgresPaperExecutionRuntime, clean: Engine
    ) -> None:
        # An attempt inserted as PAPER_SUBMITTED would be a submission with no
        # claim behind it, which is exactly the audit gap this refuses.
        intent_id, authorization = a_full_chain(paper)
        with pytest.raises(sa.exc.DatabaseError) as raised, clean.begin() as connection:
            connection.execute(
                text(
                    "UPDATE public.paper_execution_authorization SET consumed_at = now(), "
                    "consumed_by_attempt_id = 'ATT-085-0006' WHERE authorization_id = :auth"
                ),
                {"auth": authorization.authorization_id},
            )
            connection.execute(
                text(
                    "INSERT INTO public.paper_execution_attempt (attempt_id, "
                    "intent_governance_id, authorization_id, client_order_id, "
                    "request_fingerprint, state, claimed_at) VALUES "
                    "('ATT-085-0006', :intent, :auth, :cid, :fp, 'PAPER_SUBMITTED', now())"
                ),
                {
                    "intent": intent_id,
                    "auth": authorization.authorization_id,
                    "cid": authorization.client_order_id,
                    "fp": authorization.request_fingerprint,
                },
            )
        assert "must be inserted as DISPATCH_CLAIMED" in str(raised.value)


class TestTheTransitionTableIsClosedInTheDatabase:
    def test_the_database_table_matches_the_domain_table_exactly(
        self, paper: PostgresPaperExecutionRuntime, clean: Engine
    ) -> None:
        """The mirror test. Two copies of one table can only be trusted if compared.

        Walks EVERY ordered pair of attempt-holdable states and asks the real
        trigger whether it permits the edge, then requires the answer to equal
        the domain table's answer. A drift in either direction fails here.
        """
        attempt_states = [
            state
            for state in PaperExecutionState
            if state
            not in {
                PaperExecutionState.NOT_DISPATCHED,
                PaperExecutionState.AUTHORIZATION_PENDING,
                PaperExecutionState.AUTHORIZED,
            }
        ]
        disagreements: list[str] = []
        for source in attempt_states:
            for target in attempt_states:
                if source == target:
                    continue
                domain_allows = target in ALLOWED_PAPER_TRANSITIONS[source]
                database_allows = self._database_permits(clean, paper, source, target)
                if domain_allows != database_allows:
                    disagreements.append(
                        f"{source.value}->{target.value}: domain={domain_allows} "
                        f"database={database_allows}"
                    )
        assert disagreements == []

    @staticmethod
    def _database_permits(
        engine: Engine,
        paper: PostgresPaperExecutionRuntime,
        source: PaperExecutionState,
        target: PaperExecutionState,
    ) -> bool:
        """Force one attempt into `source`, then try `target`, then roll back.

        Everything happens inside a transaction that is rolled back, so the
        hundred-odd probes leave no rows behind and cannot influence each other.
        """
        truncate_all(engine)
        intent_id, authorization = a_full_chain(paper)
        with engine.connect() as connection:
            transaction = connection.begin()
            try:
                connection.execute(
                    text(
                        "UPDATE public.paper_execution_authorization SET consumed_at = now(), "
                        "consumed_by_attempt_id = 'ATT-PROBE' WHERE authorization_id = :auth"
                    ),
                    {"auth": authorization.authorization_id},
                )
                connection.execute(
                    text(
                        "INSERT INTO public.paper_execution_attempt (attempt_id, "
                        "intent_governance_id, authorization_id, client_order_id, "
                        "request_fingerprint, state, claimed_at) VALUES "
                        "('ATT-PROBE', :intent, :auth, :cid, :fp, 'DISPATCH_CLAIMED', now())"
                    ),
                    {
                        "intent": intent_id,
                        "auth": authorization.authorization_id,
                        "cid": authorization.client_order_id,
                        "fp": authorization.request_fingerprint,
                    },
                )
                # Reach `source` by disabling nothing -- walk there if the table
                # allows it, otherwise place the row there with the trigger
                # temporarily bypassed is NOT done; instead the probe is skipped
                # for unreachable sources by writing the state directly through a
                # SAVEPOINT that is rolled back on refusal.
                if source is not PaperExecutionState.DISPATCH_CLAIMED:
                    savepoint = connection.begin_nested()
                    try:
                        connection.execute(
                            text(
                                "UPDATE public.paper_execution_attempt SET state = :state, "
                                "terminal_at = CASE WHEN :terminal THEN now() ELSE NULL END "
                                "WHERE attempt_id = 'ATT-PROBE'"
                            ),
                            {
                                "state": source.value,
                                "terminal": source in TERMINAL_PAPER_STATES,
                            },
                        )
                        savepoint.commit()
                    except sa.exc.DatabaseError:
                        savepoint.rollback()
                        # `source` is not reachable in one step from
                        # DISPATCH_CLAIMED. Reach it through PAPER_SUBMITTED,
                        # which every remaining state is reachable from.
                        connection.execute(
                            text(
                                "UPDATE public.paper_execution_attempt "
                                "SET state = 'SUBMISSION_IN_PROGRESS' "
                                "WHERE attempt_id = 'ATT-PROBE'"
                            )
                        )
                        connection.execute(
                            text(
                                "UPDATE public.paper_execution_attempt "
                                "SET state = 'PAPER_SUBMITTED' WHERE attempt_id = 'ATT-PROBE'"
                            )
                        )
                        if source is not PaperExecutionState.PAPER_SUBMITTED:
                            connection.execute(
                                text(
                                    "UPDATE public.paper_execution_attempt SET state = :state, "
                                    "terminal_at = CASE WHEN :terminal THEN now() ELSE NULL END "
                                    "WHERE attempt_id = 'ATT-PROBE'"
                                ),
                                {
                                    "state": source.value,
                                    "terminal": source in TERMINAL_PAPER_STATES,
                                },
                            )
                probe = connection.begin_nested()
                try:
                    connection.execute(
                        text(
                            "UPDATE public.paper_execution_attempt SET state = :state, "
                            "terminal_at = CASE WHEN :terminal THEN now() ELSE NULL END "
                            "WHERE attempt_id = 'ATT-PROBE'"
                        ),
                        {"state": target.value, "terminal": target in TERMINAL_PAPER_STATES},
                    )
                    probe.commit()
                    return True
                except sa.exc.DatabaseError:
                    probe.rollback()
                    return False
            finally:
                transaction.rollback()

    def test_a_terminal_attempt_cannot_be_resurrected(
        self, paper: PostgresPaperExecutionRuntime, clean: Engine
    ) -> None:
        _, authorization = a_full_chain(paper)
        claim = paper.execution_attempts.claim_dispatch(
            attempt_id="ATT-085-0001",
            authorization=authorization,
            request_fingerprint_now=authorization.request_fingerprint,
            account_reference_now=authorization.account_reference,
            claimed_at=datetime.now(UTC),
        )
        paper.execution_attempts.transition(
            attempt_id=claim.attempt.attempt_id,
            target=PaperExecutionState.REJECTED,
            at=datetime.now(UTC),
            failure_code="TEST",
        )
        with pytest.raises(sa.exc.DatabaseError) as raised, clean.begin() as connection:
            connection.execute(
                text(
                    "UPDATE public.paper_execution_attempt SET state = 'PAPER_SUBMITTED', "
                    "terminal_at = NULL WHERE attempt_id = 'ATT-085-0001'"
                )
            )
        assert "terminal" in str(raised.value)

    def test_identity_columns_are_immutable_after_the_claim(
        self, paper: PostgresPaperExecutionRuntime, clean: Engine
    ) -> None:
        _, authorization = a_full_chain(paper)
        paper.execution_attempts.claim_dispatch(
            attempt_id="ATT-085-0001",
            authorization=authorization,
            request_fingerprint_now=authorization.request_fingerprint,
            account_reference_now=authorization.account_reference,
            claimed_at=datetime.now(UTC),
        )
        for statement, value in (
            (
                "UPDATE public.paper_execution_attempt SET client_order_id = :value "
                "WHERE attempt_id = 'ATT-085-0001'",
                "m085-0000000000000000000000000000000000000000",
            ),
            (
                "UPDATE public.paper_execution_attempt SET request_fingerprint = :value "
                "WHERE attempt_id = 'ATT-085-0001'",
                "b" * 64,
            ),
            (
                "UPDATE public.paper_execution_attempt "
                "SET claimed_at = CAST(:value AS timestamptz) "
                "WHERE attempt_id = 'ATT-085-0001'",
                "2099-01-01T00:00:00+00:00",
            ),
        ):
            with pytest.raises(sa.exc.DatabaseError) as raised, clean.begin() as connection:
                connection.execute(text(statement), {"value": value})
            assert "immutable" in str(raised.value), statement


#: One literal INSERT, every value bound. Each attack below overrides exactly one
#: parameter, so the statement never changes and the CHECK that fires is
#: attributable to the single value that moved.
_PREVIEW_INSERT_PROBE = (
    "INSERT INTO public.paper_submission_preview (preview_id, intent_governance_id, "
    "preview_version, account_snapshot_id, account_reference, symbol, side, quantity, "
    "order_type, limit_price, time_in_force, extended_hours, client_order_id, "
    "request_fingerprint, approved_fingerprint, market_is_open, quote_source, "
    "asset_tradable, asset_status, asset_class, asset_exchange, asset_fractionable, "
    "refusals, created_at) "
    "VALUES (:preview_id, :intent_governance_id, :preview_version, :account_snapshot_id, "
    ":account_reference, :symbol, :side, CAST(:quantity AS bigint), :order_type, "
    "CAST(:limit_price AS numeric), :time_in_force, CAST(:extended_hours AS boolean), "
    ":client_order_id, :request_fingerprint, :approved_fingerprint, "
    "CAST(:market_is_open AS boolean), :quote_source, CAST(:asset_tradable AS boolean), "
    ":asset_status, :asset_class, :asset_exchange, CAST(:asset_fractionable AS boolean), "
    ":refusals, CAST(:created_at AS timestamptz))"
)


class TestTheHardProductInvariantsAreCheckConstraints:
    @pytest.mark.parametrize(
        ("override", "constraint"),
        [
            ({"side": "SELL"}, "ck_paper_preview_long_only"),
            ({"extended_hours": "true"}, "ck_paper_preview_no_extended_hours"),
            ({"time_in_force": "GTC"}, "ck_paper_preview_time_in_force"),
            ({"quantity": "0"}, "ck_paper_preview_quantity_positive"),
            ({"quantity": "-5"}, "ck_paper_preview_quantity_positive"),
            ({"client_order_id": "not-m085"}, "ck_paper_preview_client_order_id_prefix"),
            ({"request_fingerprint": "NOTAHEXDIGEST"}, "ck_paper_preview_request_fingerprint"),
            (
                {"order_type": "STOP", "limit_price": None},
                "ck_paper_preview_order_type",
            ),
            (
                {"order_type": "LIMIT", "limit_price": None},
                "ck_paper_preview_limit_price_shape",
            ),
            (
                {"order_type": "MARKET", "limit_price": "10"},
                "ck_paper_preview_limit_price_shape",
            ),
        ],
    )
    def test_a_preview_expressing_a_forbidden_order_cannot_be_stored(
        self,
        paper: PostgresPaperExecutionRuntime,
        clean: Engine,
        override: dict[str, object],
        constraint: str,
    ) -> None:
        """A preview is what a human authorizes, so a forbidden one must not exist."""
        intent_id, authorization = a_full_chain(paper)
        parameters: dict[str, object] = {
            "preview_id": "PVW-ATTACK",
            "intent_governance_id": intent_id,
            "preview_version": 99,
            "account_snapshot_id": "SNP-085-0001",
            "account_reference": authorization.account_reference,
            "symbol": "AAPL",
            "side": "BUY",
            "quantity": "1",
            "order_type": "LIMIT",
            "limit_price": "200.10",
            "time_in_force": "DAY",
            "extended_hours": "false",
            "client_order_id": authorization.client_order_id,
            "request_fingerprint": authorization.request_fingerprint,
            "approved_fingerprint": "a" * 64,
            "market_is_open": "true",
            "quote_source": "alpaca-iex",
            "asset_tradable": "true",
            "asset_status": "active",
            "asset_class": "us_equity",
            "asset_exchange": "NASDAQ",
            "asset_fractionable": "true",
            "refusals": "[]",
            "created_at": "2026-06-10T12:00:25+00:00",
        }
        # A control: the base parameters must be ACCEPTED, or every refusal below
        # could be caused by something other than the value under test. Rolled
        # back rather than deleted, because the append-only trigger refuses a
        # DELETE -- which is itself the behaviour a later test asserts.
        with clean.connect() as connection:
            transaction = connection.begin()
            connection.execute(text(_PREVIEW_INSERT_PROBE), dict(parameters))
            transaction.rollback()

        parameters.update(override)
        with pytest.raises(sa.exc.IntegrityError) as raised, clean.begin() as connection:
            connection.execute(text(_PREVIEW_INSERT_PROBE), parameters)
        assert constraint in str(raised.value), override

    def test_a_live_environment_account_snapshot_cannot_be_stored(self, clean: Engine) -> None:
        with pytest.raises(sa.exc.IntegrityError) as raised, clean.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO public.paper_account_snapshot (snapshot_id, environment, "
                    "endpoint_host, account_reference, account_status, currency, buying_power, "
                    "cash, equity, multiplier, shorting_enabled, trading_blocked, "
                    "transfers_blocked, account_blocked, trade_suspended_by_user, captured_at) "
                    "VALUES ('SNP-LIVE', 'LIVE', 'paper-api.alpaca.markets', 'ref:x', 'ACTIVE', "
                    "'USD', 1, 1, 1, '1', false, false, false, false, false, now())"
                )
            )
        assert "ck_paper_account_environment" in str(raised.value)

    def test_a_live_endpoint_host_cannot_be_stored(self, clean: Engine) -> None:
        # The adapter refuses a live URL. This is the same refusal at the row
        # level, so a row describing a dispatch to a live host cannot exist even
        # if the adapter were bypassed entirely.
        with pytest.raises(sa.exc.IntegrityError) as raised, clean.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO public.paper_account_snapshot (snapshot_id, environment, "
                    "endpoint_host, account_reference, account_status, currency, buying_power, "
                    "cash, equity, multiplier, shorting_enabled, trading_blocked, "
                    "transfers_blocked, account_blocked, trade_suspended_by_user, captured_at) "
                    "VALUES ('SNP-LIVE2', 'PAPER', 'api.alpaca.markets', 'ref:x', 'ACTIVE', "
                    "'USD', 1, 1, 1, '1', false, false, false, false, false, now())"
                )
            )
        assert "ck_paper_account_endpoint_host" in str(raised.value)

    def test_a_terminal_state_without_a_terminal_instant_cannot_be_stored(
        self, paper: PostgresPaperExecutionRuntime, clean: Engine
    ) -> None:
        intent_id, authorization = a_full_chain(paper)
        with pytest.raises(sa.exc.IntegrityError) as raised, clean.begin() as connection:
            connection.execute(
                text(
                    "UPDATE public.paper_execution_authorization SET consumed_at = now(), "
                    "consumed_by_attempt_id = 'ATT-T' WHERE authorization_id = :auth"
                ),
                {"auth": authorization.authorization_id},
            )
            connection.execute(
                text(
                    "INSERT INTO public.paper_execution_attempt (attempt_id, "
                    "intent_governance_id, authorization_id, client_order_id, "
                    "request_fingerprint, state, claimed_at, terminal_at) VALUES "
                    "('ATT-T', :intent, :auth, :cid, :fp, 'DISPATCH_CLAIMED', now(), now())"
                ),
                {
                    "intent": intent_id,
                    "auth": authorization.authorization_id,
                    "cid": authorization.client_order_id,
                    "fp": authorization.request_fingerprint,
                },
            )
        assert "ck_paper_attempt_terminal_at_matches_state" in str(raised.value)


class TestEveryAppendOnlyTableRefusesUpdateAndDelete:
    # Literal statements, one pair per table. The append-only claim covers four
    # tables, so all four are named here rather than derived from a list that a
    # new table could be forgotten from -- and a test below cross-checks this
    # against the tables the schema actually installed the trigger on.
    @pytest.mark.parametrize(
        ("table", "count_statement", "update_statement", "delete_statement"),
        [
            (
                "paper_account_snapshot",
                "SELECT count(*) AS n FROM public.paper_account_snapshot",
                "UPDATE public.paper_account_snapshot SET captured_at = now()",
                "DELETE FROM public.paper_account_snapshot",
            ),
            (
                "paper_submission_preview",
                "SELECT count(*) AS n FROM public.paper_submission_preview",
                "UPDATE public.paper_submission_preview SET created_at = now()",
                "DELETE FROM public.paper_submission_preview",
            ),
            (
                "paper_execution_event",
                "SELECT count(*) AS n FROM public.paper_execution_event",
                "UPDATE public.paper_execution_event SET occurred_at = now()",
                "DELETE FROM public.paper_execution_event",
            ),
            (
                "paper_execution_kill_switch",
                "SELECT count(*) AS n FROM public.paper_execution_kill_switch",
                "UPDATE public.paper_execution_kill_switch SET changed_at = now()",
                "DELETE FROM public.paper_execution_kill_switch",
            ),
            (
                "paper_broker_acknowledgement",
                "SELECT count(*) AS n FROM public.paper_broker_acknowledgement",
                "UPDATE public.paper_broker_acknowledgement SET observed_at = now()",
                "DELETE FROM public.paper_broker_acknowledgement",
            ),
        ],
    )
    def test_update_and_delete_are_both_refused(
        self,
        paper: PostgresPaperExecutionRuntime,
        clean: Engine,
        table: str,
        count_statement: str,
        update_statement: str,
        delete_statement: str,
    ) -> None:
        # EVERY guarded table needs at least one row, or an UPDATE/DELETE that
        # matches nothing fires no row trigger and the test would pass without
        # having attacked anything.
        intent_id, authorization = a_full_chain(paper)
        paper.execution_kill_switch.engage(
            changed_by="owner", changed_at=EVALUATED_AT, reason="test"
        )
        paper.paper_execution_events.append(
            PaperExecutionEvent(
                event_id="EVT-085-0001",
                intent_governance_id=intent_id,
                attempt_id=None,
                event_type="TEST",
                occurred_at=EVALUATED_AT,
                detail="probe",
            )
        )
        claim = paper.execution_attempts.claim_dispatch(
            attempt_id="ATT-085-0001",
            authorization=authorization,
            request_fingerprint_now=authorization.request_fingerprint,
            account_reference_now=authorization.account_reference,
            claimed_at=datetime.now(UTC),
        )
        paper.broker_acknowledgements.append(
            BrokerAcknowledgement(
                acknowledgement_id="ACK-085-0001",
                attempt_id=claim.attempt.attempt_id,
                sequence=paper.broker_acknowledgements.next_sequence(claim.attempt.attempt_id),
                kind="SUBMIT",
                observed_at=datetime.now(UTC),
                http_status=200,
                broker_order_id="broker-1",
                broker_status="accepted",
                client_order_id_echo=authorization.client_order_id,
                payload_digest="c" * 64,
                sanitized_payload="{}",
            )
        )
        with clean.begin() as connection:
            populated = connection.execute(text(count_statement)).scalar_one()
        assert populated > 0, f"{table} has no rows, so the refusal below would be vacuous"

        for statement in (update_statement, delete_statement):
            with pytest.raises(sa.exc.DatabaseError) as raised, clean.begin() as connection:
                connection.execute(text(statement))
            assert "append-only" in str(raised.value), (table, statement)

    def test_the_four_tables_above_are_exactly_the_ones_the_schema_guards(
        self, clean: Engine
    ) -> None:
        # Anti-vacuity for the parametrization: if the migration installs the
        # append-only trigger on a fifth table, the list above is incomplete and
        # this fails rather than silently leaving that table unchecked.
        # Scoped to M085's own tables: earlier milestones install their own
        # append-only triggers, and sweeping those in would make this assert
        # somebody else's schema.
        with clean.begin() as connection:
            guarded = {
                row[0]
                for row in connection.execute(
                    text(
                        "SELECT c.relname FROM pg_trigger t "
                        "JOIN pg_class c ON c.oid = t.tgrelid "
                        "WHERE NOT t.tgisinternal AND t.tgname LIKE '%append_only%' "
                        "AND c.relname LIKE 'paper%'"
                    )
                ).all()
            }
        assert guarded == {
            "paper_account_snapshot",
            "paper_submission_preview",
            "paper_execution_event",
            "paper_execution_kill_switch",
            "paper_broker_acknowledgement",
        }


class TestTheReadPathFailsClosed:
    def test_an_unknown_stored_state_is_refused_rather_than_defaulted(
        self, paper: PostgresPaperExecutionRuntime, clean: Engine
    ) -> None:
        """A value the enum does not name must not become one that it does.

        Written with the trigger dropped, because that is the only way such a row
        can exist -- which is exactly the scenario the read path must survive.
        """
        _, authorization = a_full_chain(paper)
        paper.execution_attempts.claim_dispatch(
            attempt_id="ATT-085-0001",
            authorization=authorization,
            request_fingerprint_now=authorization.request_fingerprint,
            account_reference_now=authorization.account_reference,
            claimed_at=datetime.now(UTC),
        )
        # BOTH the trigger and the CHECK have to be stood down to create such a
        # row, which is the point: nothing short of DDL authority can produce it.
        # The read path still has to refuse it rather than coerce it.
        with clean.begin() as connection:
            connection.execute(
                text(
                    "ALTER TABLE public.paper_execution_attempt "
                    "DISABLE TRIGGER paper_execution_attempt_guard_update_trigger"
                )
            )
            connection.execute(
                text(
                    "ALTER TABLE public.paper_execution_attempt "
                    "DROP CONSTRAINT ck_paper_attempt_state"
                )
            )
            connection.execute(
                text(
                    "UPDATE public.paper_execution_attempt SET state = 'DEFINITELY_FINE' "
                    "WHERE attempt_id = 'ATT-085-0001'"
                )
            )
        try:
            with pytest.raises(FoundationError) as raised:
                paper.execution_attempts.get("ATT-085-0001")
            assert "DEFINITELY_FINE" in str(raised.value)
            assert "refusing to map it onto a known member" in str(raised.value)
        finally:
            with clean.begin() as connection:
                connection.execute(
                    text(
                        "UPDATE public.paper_execution_attempt SET state = 'DISPATCH_CLAIMED' "
                        "WHERE attempt_id = 'ATT-085-0001'"
                    )
                )
                connection.execute(
                    text(
                        "ALTER TABLE public.paper_execution_attempt ADD CONSTRAINT "
                        "ck_paper_attempt_state CHECK (state IN ('DISPATCH_CLAIMED', "
                        "'SUBMISSION_IN_PROGRESS', 'PAPER_SUBMITTED', 'PAPER_ACCEPTED', "
                        "'PARTIALLY_FILLED', 'FILLED', 'CANCEL_REQUESTED', 'CANCELED', "
                        "'REJECTED', 'EXPIRED', 'SUBMISSION_UNKNOWN'))"
                    )
                )
                connection.execute(
                    text(
                        "ALTER TABLE public.paper_execution_attempt "
                        "ENABLE TRIGGER paper_execution_attempt_guard_update_trigger"
                    )
                )


class TestTheStatedLimitsAreRealLimits:
    """The boundary, executed rather than described."""

    def test_disabling_the_trigger_does_defeat_the_append_only_guarantee(
        self, paper: PostgresPaperExecutionRuntime, clean: Engine
    ) -> None:
        # This test PASSES by demonstrating the documented hole. If it ever
        # failed, the limitation section would be overstating the risk -- and
        # that matters as much as understating it.
        # `paper_execution_event` is used rather than the preview table because
        # the preview is referenced by a foreign key, and that FK -- not the
        # trigger -- would be what refused the DELETE. The hole being
        # demonstrated is the trigger's, so the demonstration must not be
        # accidentally saved by something else.
        intent_id, _ = a_full_chain(paper)
        paper.paper_execution_events.append(
            PaperExecutionEvent(
                event_id="EVT-085-0003",
                intent_governance_id=intent_id,
                attempt_id=None,
                event_type="TEST",
                occurred_at=EVALUATED_AT,
                detail="probe",
            )
        )
        with clean.begin() as connection:
            connection.execute(
                text(
                    "ALTER TABLE public.paper_execution_event "
                    "DISABLE TRIGGER paper_execution_event_append_only_trigger"
                )
            )
            connection.execute(text("DELETE FROM public.paper_execution_event"))
            remaining = connection.execute(
                text("SELECT count(*) AS n FROM public.paper_execution_event")
            ).scalar_one()
            connection.execute(
                text(
                    "ALTER TABLE public.paper_execution_event "
                    "ENABLE TRIGGER paper_execution_event_append_only_trigger"
                )
            )
        assert remaining == 0

    def test_truncate_is_not_intercepted_by_the_row_triggers(
        self, paper: PostgresPaperExecutionRuntime, clean: Engine
    ) -> None:
        paper.execution_kill_switch.engage(
            changed_by="owner", changed_at=EVALUATED_AT, reason="test"
        )
        with clean.begin() as connection:
            connection.execute(text("TRUNCATE public.paper_execution_kill_switch"))
            remaining = connection.execute(
                text("SELECT count(*) AS n FROM public.paper_execution_kill_switch")
            ).scalar_one()
        assert remaining == 0


class TestSearchPathCannotBeSubverted:
    def test_a_pg_temp_shadow_of_the_guard_function_does_not_take_effect(
        self, paper: PostgresPaperExecutionRuntime, clean: Engine
    ) -> None:
        """Every guard pins `search_path`, so a temp-schema shadow is inert.

        Without the pin, a caller could define `pg_temp.m085_append_only()` and
        have the trigger call theirs instead of ours.
        """
        intent_id, _ = a_full_chain(paper)
        paper.paper_execution_events.append(
            PaperExecutionEvent(
                event_id="EVT-085-0002",
                intent_governance_id=intent_id,
                attempt_id=None,
                event_type="TEST",
                occurred_at=EVALUATED_AT,
                detail="probe",
            )
        )
        with clean.connect() as connection:
            connection.execute(text("SET search_path TO pg_temp, public"))
            connection.execute(
                text(
                    "CREATE FUNCTION pg_temp.m085_append_only() RETURNS trigger AS $$ "
                    "BEGIN RETURN NEW; END; $$ LANGUAGE plpgsql"
                )
            )
            connection.commit()
            with pytest.raises(sa.exc.DatabaseError) as raised:
                connection.execute(text("DELETE FROM public.paper_execution_event"))
                connection.commit()
            connection.rollback()
        assert "append-only" in str(raised.value)

    def test_every_m085_guard_function_pins_its_search_path(self, clean: Engine) -> None:
        with clean.begin() as connection:
            rows = (
                connection.execute(
                    text(
                        "SELECT p.proname, p.proconfig FROM pg_proc p "
                        "JOIN pg_namespace n ON n.oid = p.pronamespace "
                        "WHERE n.nspname = 'public' AND (p.proname LIKE '%m085%' "
                        "OR p.proname LIKE 'paper_execution%')"
                    )
                )
                .mappings()
                .all()
            )
        assert rows, "no M085 guard functions found at all"
        unpinned = [
            row["proname"]
            for row in rows
            if not row["proconfig"]
            or not any("search_path=" in setting for setting in row["proconfig"])
        ]
        assert unpinned == []


class TestMilestone084IsUntouched:
    """FIND-M085-01, held fixed.

    The first version of this schema linked to `approved_order_intent` with four
    FOREIGN KEYS. PostgreSQL refuses to TRUNCATE a referenced table, so M084's own
    `clean` fixture -- which truncates exactly that table -- became inexecutable
    and 97 M084 tests turned into errors at this head. The link is now a BEFORE
    INSERT trigger, which gives the same insert-time guarantee without the
    TRUNCATE dependency. These tests keep both halves of that fixed.
    """

    def test_the_m084_clean_fixture_truncate_still_works_at_this_head(
        self, paper: PostgresPaperExecutionRuntime, clean: Engine
    ) -> None:
        # Byte-for-byte the statement `tests/integration/
        # test_m084_decision_to_approval_lifecycle.py` issues before every test.
        # Rows are present first, so this is not vacuous.
        a_full_chain(paper)
        with clean.begin() as connection:
            connection.execute(
                text(
                    "TRUNCATE approved_order_intent, trade_approval_decision, "
                    "trade_proposal_risk_check, trade_proposal, evaluation_context, "
                    "operator_trading_configuration, evaluation_evidence_watermark"
                )
            )

    def test_no_m085_table_holds_a_foreign_key_into_m084(self, clean: Engine) -> None:
        # Structural, so the foreign key cannot come back by a well-meaning edit.
        with clean.begin() as connection:
            offenders = [
                row[0]
                for row in connection.execute(
                    text(
                        "SELECT c.conname FROM pg_constraint c "
                        "JOIN pg_class t ON t.oid = c.conrelid "
                        "JOIN pg_class r ON r.oid = c.confrelid "
                        "WHERE c.contype = 'f' AND t.relname LIKE 'paper%' "
                        "AND r.relname NOT LIKE 'paper%'"
                    )
                ).all()
            ]
        assert offenders == []

    def test_a_paper_row_naming_an_unknown_intent_is_still_refused(self, clean: Engine) -> None:
        # The half of the foreign key that mattered, kept.
        with pytest.raises(sa.exc.DatabaseError) as raised, clean.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO public.paper_execution_event (event_id, "
                    "intent_governance_id, attempt_id, event_type, occurred_at, detail) "
                    "VALUES ('EVT-ORPHAN', 'NO-SUCH-INTENT', NULL, 'X', now(), 'd')"
                )
            )
        assert "which does not exist" in str(raised.value)

    def test_the_intent_existence_trigger_pins_its_search_path(self, clean: Engine) -> None:
        with clean.begin() as connection:
            configuration = connection.execute(
                text(
                    "SELECT p.proconfig FROM pg_proc p "
                    "JOIN pg_namespace n ON n.oid = p.pronamespace "
                    "WHERE n.nspname = 'public' "
                    "AND p.proname = 'paper_requires_approved_intent'"
                )
            ).scalar_one()
        assert configuration is not None
        assert any("search_path=" in setting for setting in configuration)

    def test_the_m085_schema_adds_no_trigger_to_any_m084_table(self, clean: Engine) -> None:
        with clean.begin() as connection:
            rows = (
                connection.execute(
                    text(
                        "SELECT c.relname AS table_name, t.tgname AS trigger_name "
                        "FROM pg_trigger t JOIN pg_class c ON c.oid = t.tgrelid "
                        "WHERE NOT t.tgisinternal AND c.relname IN "
                        "('approved_order_intent', 'trade_approval_decision', 'trade_proposal', "
                        "'trade_proposal_risk_check', 'evaluation_context', "
                        "'operator_trading_configuration')"
                    )
                )
                .mappings()
                .all()
            )
        assert all("paper" not in row["trigger_name"] for row in rows), rows
        assert all("m085" not in row["trigger_name"] for row in rows), rows

    def test_the_approved_intent_is_still_not_submitted_after_a_dispatch(
        self, paper: PostgresPaperExecutionRuntime, clean: Engine
    ) -> None:
        """M085 records execution WITHOUT moving M084's submission state.

        This is the whole shape of the additive design: if this ever failed, M085
        would have rewritten the record a human approved.
        """
        intent_id, authorization = a_full_chain(paper)
        claim = paper.execution_attempts.claim_dispatch(
            attempt_id="ATT-085-0001",
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
        with clean.begin() as connection:
            state = connection.execute(
                text(
                    "SELECT submission_state FROM public.approved_order_intent "
                    "WHERE intent_governance_id = :intent"
                ),
                {"intent": intent_id},
            ).scalar_one()
        assert state == "NOT_SUBMITTED"

    def test_the_configuration_kill_switch_and_the_execution_kill_switch_are_separate(
        self, paper: PostgresPaperExecutionRuntime
    ) -> None:
        # M084's switch refuses to PROPOSE; M085's refuses to DISPATCH. Engaging
        # one must not be read as engaging the other.
        assert paper.execution_kill_switch.is_engaged() is False
        assert a_configuration().kill_switch.value == "DISENGAGED"
        assert paper.execution_kill_switch.engage(
            changed_by="owner", changed_at=EVALUATED_AT, reason="separate"
        )
        assert paper.execution_kill_switch.is_engaged() is True


class TestTheKillSwitchIsVersionedAndHonest:
    def test_moving_the_switch_to_where_it_already_is_writes_nothing(
        self, paper: PostgresPaperExecutionRuntime, clean: Engine
    ) -> None:
        assert paper.execution_kill_switch.engage(
            changed_by="owner", changed_at=EVALUATED_AT, reason="first"
        )
        assert not paper.execution_kill_switch.engage(
            changed_by="owner", changed_at=EVALUATED_AT, reason="again"
        )
        with clean.begin() as connection:
            count = connection.execute(
                text("SELECT count(*) AS n FROM public.paper_execution_kill_switch")
            ).scalar_one()
        assert count == 1

    def test_each_move_writes_a_new_version(self, paper: PostgresPaperExecutionRuntime) -> None:
        paper.execution_kill_switch.engage(changed_by="owner", changed_at=EVALUATED_AT, reason="on")
        paper.execution_kill_switch.disengage(
            changed_by="owner", changed_at=EVALUATED_AT, reason="off"
        )
        assert paper.execution_kill_switch.is_engaged() is False


class TestTheDatabaseIdentityIsRecorded:
    def test_the_identity_names_a_real_database_and_a_real_table(self, clean: Engine) -> None:
        # Used by the concurrency campaign to show three repetitions ran against
        # three genuinely rebuilt schemas.
        identity = database_identity(clean)
        assert identity["database"]
        assert int(identity["database_oid"]) > 0
        assert int(identity["schema_oid"]) > 0
        assert int(identity["attempt_oid"]) > 0
        assert uuid.UUID(int=int(identity["attempt_oid"])).int > 0
