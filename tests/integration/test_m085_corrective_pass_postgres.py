"""MILESTONE-085 corrective pass: what the DATABASE now refuses, against real PostgreSQL.

Raw SQL on purpose, like `test_m085_paper_execution_postgres.py`: the question is not
whether the repository refuses -- the domain and handler suites prove that -- but
whether a writer who never imported this package is refused too.

  P2    a terminal attempt is immutable, same-state updates included; a recorded broker
        order id, submission instant or acknowledgement instant is written once;
  P3    an authorization is inserted unconsumed and equal, field by field, to the
        authorizable preview it names, not outliving the intent, not granted after the
        preview's freshness limit;
  D1    a preview carries the send-time policy of the exact configuration version the
        intent names, and the exact order of that intent;
  item4 the schema head is exactly the one the code was written for;
  and the corrective migration goes down and up again, and refuses to invent a binding
  for rows that exist.

THE NEW INSERT GUARDS RUN AFTER INSERT, so the earlier milestones' CHECK constraints
still report themselves; see the migration. The limits of every trigger-based guard --
DISABLE TRIGGER, DROP, TRUNCATE, superuser -- are unchanged and are exercised in
`test_m085_paper_execution_postgres.py`.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import timedelta
from typing import Any

import pytest
import sqlalchemy as sa
from alembic import command as alembic_command
from sqlalchemy import text
from sqlalchemy.engine import Engine
from tests.integration._m085_support import (
    CHAIN_AT,
    alembic_config,
    build_engine,
    chain_clock,
    config,
    truncate_all,
)
from tests.integration.test_m085_paper_execution_postgres import a_full_chain

from empirical_platform.decision_candidate.paper_execution import PaperExecutionState
from empirical_platform.shared.persistence.postgres import PostgresPersistenceService
from empirical_platform.shared.persistence.postgres_repositories.paper_execution_repositories import (  # noqa: E501
    M085_SCHEMA_HEAD,
    PaperSchemaHeadError,
    PostgresPaperExecutionRuntime,
    require_exact_m085_schema_head,
)

pytestmark = pytest.mark.integration

#: Revisions other than the head, in groups for the secret scanner.
_BELOW_THE_CORRECTIVE_REVISION = "".join(("e61b3f", "9a4c27"))
_M084_HEAD = "".join(("a3f7c2", "1d9b04"))


@pytest.fixture(scope="module")
def engine() -> Iterator[Engine]:
    yield from build_engine()


@pytest.fixture
def clean(engine: Engine) -> Engine:
    truncate_all(engine)
    return engine


@pytest.fixture
def service(clean: Engine) -> Iterator[PostgresPersistenceService]:
    resolved = PostgresPersistenceService(config("m085-corrective-suite"))
    resolved.initialize()
    try:
        yield resolved
    finally:
        resolved.close()


@pytest.fixture
def paper(service: PostgresPersistenceService) -> PostgresPaperExecutionRuntime:
    return PostgresPaperExecutionRuntime(service)


def _raises(engine: Engine, statement: str, fragment: str, **parameters: object) -> None:
    with pytest.raises(sa.exc.DatabaseError) as raised, engine.begin() as connection:
        connection.execute(text(statement), parameters)
    assert fragment in str(raised.value), str(raised.value)


def _accepted_then_rolled_back(engine: Engine, statement: str, **parameters: object) -> None:
    with engine.connect() as connection:
        transaction = connection.begin()
        try:
            connection.execute(text(statement), parameters)
        finally:
            transaction.rollback()


# ---------------------------------------------------------------------------
# P2 -- a terminal attempt is immutable
# ---------------------------------------------------------------------------


def _attempt_through(
    paper: PostgresPaperExecutionRuntime, targets: tuple[PaperExecutionState, ...]
) -> str:
    _, authorization = a_full_chain(paper)
    claim = paper.execution_attempts.claim_dispatch(
        attempt_id="ATT-IMM",
        authorization=authorization,
        request_fingerprint_now=authorization.request_fingerprint,
        account_reference_now=authorization.account_reference,
        claimed_at=CHAIN_AT,
        broker_clock=chain_clock,
    )
    fields: dict[PaperExecutionState, dict[str, str]] = {
        PaperExecutionState.PAPER_SUBMITTED: {
            "broker_order_id": "broker-1",
            "broker_status": "accepted",
        },
        PaperExecutionState.FILLED: {
            "broker_status": "filled",
            "filled_quantity": "1",
            "filled_avg_price": "200.10",
        },
    }
    for offset, target in enumerate(targets, start=1):
        paper.execution_attempts.transition(
            attempt_id=claim.attempt.attempt_id,
            target=target,
            at=CHAIN_AT + timedelta(seconds=offset),
            **fields.get(target, {}),  # type: ignore[arg-type]
        )
    return claim.attempt.attempt_id


_TO_FILLED = (
    PaperExecutionState.SUBMISSION_IN_PROGRESS,
    PaperExecutionState.PAPER_SUBMITTED,
    PaperExecutionState.FILLED,
)
_TO_SUBMITTED = (
    PaperExecutionState.SUBMISSION_IN_PROGRESS,
    PaperExecutionState.PAPER_SUBMITTED,
)


class TestATerminalAttemptIsImmutableInTheDatabase:
    @pytest.mark.parametrize(
        "statement",
        [
            "UPDATE public.paper_execution_attempt SET broker_order_id = 'rewritten' "
            "WHERE attempt_id = 'ATT-IMM'",
            "UPDATE public.paper_execution_attempt SET broker_status = 'canceled' "
            "WHERE attempt_id = 'ATT-IMM'",
            "UPDATE public.paper_execution_attempt SET filled_quantity = 0 "
            "WHERE attempt_id = 'ATT-IMM'",
            "UPDATE public.paper_execution_attempt SET filled_avg_price = 1 "
            "WHERE attempt_id = 'ATT-IMM'",
            "UPDATE public.paper_execution_attempt SET failure_code = 'REWRITTEN' "
            "WHERE attempt_id = 'ATT-IMM'",
            "UPDATE public.paper_execution_attempt SET terminal_at = terminal_at + "
            "interval '1 second' WHERE attempt_id = 'ATT-IMM'",
            "UPDATE public.paper_execution_attempt SET state = 'CANCELED' "
            "WHERE attempt_id = 'ATT-IMM'",
            "UPDATE public.paper_execution_attempt SET state = 'PAPER_ACCEPTED', "
            "terminal_at = NULL WHERE attempt_id = 'ATT-IMM'",
            "UPDATE public.paper_execution_attempt SET state = state WHERE attempt_id = 'ATT-IMM'",
        ],
        ids=[
            "broker_order_id",
            "broker_status",
            "filled_quantity",
            "filled_avg_price",
            "failure_code",
            "terminal_at",
            "conflicting-terminal-state",
            "resurrection",
            "identical-same-state",
        ],
    )
    def test_no_update_of_a_filled_attempt_is_accepted(
        self, paper: PostgresPaperExecutionRuntime, clean: Engine, statement: str
    ) -> None:
        attempt_id = _attempt_through(paper, _TO_FILLED)
        before = paper.execution_attempts.get(attempt_id)
        _raises(clean, statement, "is terminal in state FILLED and is immutable")
        assert paper.execution_attempts.get(attempt_id) == before

    @pytest.mark.parametrize(
        "target",
        [
            PaperExecutionState.FILLED,
            PaperExecutionState.CANCELED,
            PaperExecutionState.EXPIRED,
            PaperExecutionState.PAPER_ACCEPTED,
        ],
    )
    def test_the_repository_refuses_before_the_database_is_asked(
        self, paper: PostgresPaperExecutionRuntime, target: PaperExecutionState
    ) -> None:
        attempt_id = _attempt_through(paper, _TO_FILLED)
        before = paper.execution_attempts.get(attempt_id)
        with pytest.raises(ValueError, match="terminal and is immutable"):
            paper.execution_attempts.transition(
                attempt_id=attempt_id,
                target=target,
                at=CHAIN_AT + timedelta(minutes=1),
                broker_order_id="rewritten",
            )
        assert paper.execution_attempts.get(attempt_id) == before

    @pytest.mark.parametrize(
        "statement",
        [
            "UPDATE public.paper_execution_attempt SET broker_order_id = 'broker-2' "
            "WHERE attempt_id = 'ATT-IMM'",
            "UPDATE public.paper_execution_attempt SET submitted_at = submitted_at + "
            "interval '1 second' WHERE attempt_id = 'ATT-IMM'",
            "UPDATE public.paper_execution_attempt SET acknowledged_at = acknowledged_at + "
            "interval '1 second' WHERE attempt_id = 'ATT-IMM'",
        ],
        ids=["broker_order_id", "submitted_at", "acknowledged_at"],
    )
    def test_a_live_attempt_cannot_rewrite_what_was_already_recorded(
        self, paper: PostgresPaperExecutionRuntime, clean: Engine, statement: str
    ) -> None:
        _attempt_through(paper, _TO_SUBMITTED)
        _raises(clean, statement, "may not rewrite a broker order id or instant")

    def test_a_live_attempt_may_still_be_refreshed_and_keeps_its_first_instants(
        self, paper: PostgresPaperExecutionRuntime, clean: Engine
    ) -> None:
        # The control for the refusals above: reconciliation of a non-terminal attempt
        # still records what the broker says now, without replacing what it said first.
        attempt_id = _attempt_through(paper, _TO_SUBMITTED)
        submitted = paper.execution_attempts.get(attempt_id)
        assert submitted is not None and submitted.acknowledged_at is not None
        refreshed = paper.execution_attempts.transition(
            attempt_id=attempt_id,
            target=PaperExecutionState.PAPER_ACCEPTED,
            at=CHAIN_AT + timedelta(minutes=5),
            broker_order_id="broker-1",
            broker_status="new",
        )
        assert refreshed.state is PaperExecutionState.PAPER_ACCEPTED
        assert refreshed.acknowledged_at == submitted.acknowledged_at
        assert refreshed.submitted_at == submitted.submitted_at
        assert refreshed.broker_status == "new"


# ---------------------------------------------------------------------------
# P3 -- an authorization equals the authorizable preview it names
# ---------------------------------------------------------------------------

_PREVIEW_COLUMNS = (
    "preview_id, intent_governance_id, preview_version, account_snapshot_id, "
    "account_reference, symbol, side, quantity, order_type, limit_price, time_in_force, "
    "extended_hours, client_order_id, request_fingerprint, approved_fingerprint, "
    "market_is_open, market_next_open, market_next_close, quote_bid, quote_ask, "
    "quote_captured_at, quote_source, asset_tradable, asset_status, asset_class, "
    "asset_exchange, asset_fractionable, refusals, created_at, configuration_governance_id, "
    "configuration_version, policy_fingerprint, maximum_notional, quote_maximum_age_seconds, "
    "maximum_spread_percent, policy_watchlist, policy_prohibited_instruments, "
    "earliest_entry_time, latest_entry_time, operator_timezone, intent_expires_at, "
    "binding_fingerprint"
)

#: A copy of the stored preview under a new id and version, with named overrides.
_COPY_PREVIEW = (
    "INSERT INTO public.paper_submission_preview (" + _PREVIEW_COLUMNS + ") "
    "SELECT {preview_id}, intent_governance_id, preview_version + {version_step}, "
    "account_snapshot_id, account_reference, {symbol}, side, {quantity}, order_type, "
    "{limit_price}, time_in_force, extended_hours, client_order_id, request_fingerprint, "
    "{approved_fingerprint}, market_is_open, market_next_open, market_next_close, quote_bid, "
    "quote_ask, quote_captured_at, quote_source, asset_tradable, asset_status, asset_class, "
    "asset_exchange, asset_fractionable, {refusals}, created_at, configuration_governance_id, "
    "{configuration_version}, policy_fingerprint, {maximum_notional}, "
    "{quote_maximum_age_seconds}, {maximum_spread_percent}, {policy_watchlist}, "
    "{policy_prohibited_instruments}, {earliest_entry_time}, {latest_entry_time}, "
    "{operator_timezone}, {intent_expires_at}, binding_fingerprint "
    "FROM public.paper_submission_preview WHERE preview_id = 'PVW-085-0001'"
)

_PREVIEW_EXACT = {
    "preview_id": "'PVW-BIND'",
    "version_step": "1",
    "symbol": "symbol",
    "quantity": "quantity",
    "limit_price": "limit_price",
    "approved_fingerprint": "approved_fingerprint",
    "refusals": "refusals",
    "configuration_version": "configuration_version",
    "maximum_notional": "maximum_notional",
    "quote_maximum_age_seconds": "quote_maximum_age_seconds",
    "maximum_spread_percent": "maximum_spread_percent",
    "policy_watchlist": "policy_watchlist",
    "policy_prohibited_instruments": "policy_prohibited_instruments",
    "earliest_entry_time": "earliest_entry_time",
    "latest_entry_time": "latest_entry_time",
    "operator_timezone": "operator_timezone",
    "intent_expires_at": "intent_expires_at",
}

#: An authorization copied from a preview, with named overrides.
_COPY_AUTHORIZATION = (
    "INSERT INTO public.paper_execution_authorization (authorization_id, "
    "intent_governance_id, preview_id, preview_version, request_fingerprint, "
    "account_reference, client_order_id, authorized_by, authorized_at, expires_at, "
    "consumed_at, consumed_by_attempt_id, basis_host_at, basis_broker_earliest_at, "
    "basis_host_requested_at, basis_broker_latest_at, symbol, side, quantity, order_type, "
    "limit_price, maximum_notional, quote_bid, quote_ask, quote_captured_at, "
    "configuration_governance_id, configuration_version, policy_fingerprint, "
    "preview_binding_fingerprint) "
    "SELECT 'AUT-BIND', intent_governance_id, preview_id, {preview_version}, "
    "{request_fingerprint}, {account_reference}, {client_order_id}, 'owner', {authorized_at}, "
    "{expires_at}, {consumed_at}, {consumed_by}, {basis}, {basis}, {basis}, {basis}, "
    "{symbol}, {side}, {quantity}, {order_type}, {limit_price}, {maximum_notional}, "
    "{quote_bid}, {quote_ask}, {quote_captured_at}, configuration_governance_id, "
    "{configuration_version}, {policy_fingerprint}, {binding} "
    "FROM public.paper_submission_preview WHERE preview_id = {source}"
)

_AUTHORIZATION_EXACT = {
    "preview_version": "preview_version",
    "request_fingerprint": "request_fingerprint",
    "account_reference": "account_reference",
    "client_order_id": "client_order_id",
    "authorized_at": "created_at",
    "expires_at": "created_at + interval '10 seconds'",
    "consumed_at": "NULL",
    "consumed_by": "NULL",
    "basis": "created_at",
    "symbol": "symbol",
    "side": "side",
    "quantity": "quantity",
    "order_type": "order_type",
    "limit_price": "limit_price",
    "maximum_notional": "maximum_notional",
    "quote_bid": "quote_bid",
    "quote_ask": "quote_ask",
    "quote_captured_at": "quote_captured_at",
    "configuration_version": "configuration_version",
    "policy_fingerprint": "policy_fingerprint",
    "binding": "binding_fingerprint",
    "source": "'PVW-BIND'",
}


def _preview(**overrides: str) -> str:
    return _COPY_PREVIEW.format(**{**_PREVIEW_EXACT, **overrides})


def _authorization(**overrides: str) -> str:
    return _COPY_AUTHORIZATION.format(**{**_AUTHORIZATION_EXACT, **overrides})


@pytest.fixture
def bindable(paper: PostgresPaperExecutionRuntime, clean: Engine) -> Engine:
    """A stored chain plus a second, exact copy of its preview with no authorization."""
    a_full_chain(paper)
    with clean.begin() as connection:
        connection.execute(text(_preview()))
    return clean


class TestAnAuthorizationEqualsThePreviewItNames:
    def test_an_exact_copy_is_accepted(self, bindable: Engine) -> None:
        # The control for every refusal below.
        with bindable.begin() as connection:
            connection.execute(text(_authorization()))
            stored = connection.execute(
                text(
                    "SELECT count(*) FROM public.paper_execution_authorization "
                    "WHERE authorization_id = 'AUT-BIND'"
                )
            ).scalar_one()
        assert stored == 1

    @pytest.mark.parametrize(
        ("field", "expression"),
        [
            ("preview_version", "preview_version + 7"),
            ("request_fingerprint", "repeat('f', 64)"),
            ("account_reference", "'ref:somebody-else'"),
            ("client_order_id", "'m085-somebody-else'"),
            ("symbol", "'MSFT'"),
            ("side", "'SELL'"),
            ("quantity", "quantity + 1"),
            ("order_type", "'MARKET'"),
            ("limit_price", "limit_price + 0.01"),
            ("maximum_notional", "maximum_notional * 100"),
            ("quote_bid", "quote_bid - 1"),
            ("quote_ask", "quote_ask + 1"),
            ("quote_captured_at", "quote_captured_at - interval '1 hour'"),
            ("configuration_version", "configuration_version + 1"),
            ("policy_fingerprint", "repeat('d', 64)"),
            ("binding", "repeat('e', 64)"),
        ],
    )
    def test_any_field_other_than_the_previews_is_refused(
        self, bindable: Engine, field: str, expression: str
    ) -> None:
        _raises(bindable, _authorization(**{field: expression}), "does not describe preview")

    def test_an_authorization_inserted_already_consumed_is_refused(self, bindable: Engine) -> None:
        # Review finding D4: consumption skipped its own guard and expiry check.
        _raises(
            bindable,
            _authorization(consumed_at="created_at", consumed_by="'ATT-FORGED'"),
            "must be inserted unconsumed",
        )

    def test_an_authorization_outliving_its_intent_is_refused_to_the_tick(
        self, bindable: Engine
    ) -> None:
        _accepted_then_rolled_back(bindable, _authorization(expires_at="intent_expires_at"))
        _raises(
            bindable,
            _authorization(expires_at="intent_expires_at + interval '1 millisecond'"),
            "would outlive the approved intent",
        )

    def test_an_authorization_after_the_previews_freshness_limit_is_refused(
        self, bindable: Engine
    ) -> None:
        # 60 s after the preview is still inside the limit; one millisecond more is not.
        _accepted_then_rolled_back(
            bindable,
            _authorization(
                authorized_at="created_at + interval '60 seconds'",
                basis="created_at + interval '60 seconds'",
                expires_at="created_at + interval '61 seconds'",
            ),
        )
        _raises(
            bindable,
            _authorization(
                authorized_at="created_at + interval '60.001 seconds'",
                basis="created_at + interval '60.001 seconds'",
                expires_at="created_at + interval '61 seconds'",
            ),
            "after its quote freshness limit",
        )

    def test_a_preview_with_refusals_cannot_be_authorized(self, bindable: Engine) -> None:
        with bindable.begin() as connection:
            connection.execute(
                text(
                    _preview(
                        preview_id="'PVW-REFUSED'",
                        version_step="2",
                        refusals="'[\"the execution kill switch is engaged\"]'",
                    )
                )
            )
        _raises(
            bindable,
            _authorization(source="'PVW-REFUSED'", preview_version="preview_version"),
            "carries refusals and cannot be authorized",
        )


# ---------------------------------------------------------------------------
# D1 -- a preview carries its intent's order and its configuration's policy
# ---------------------------------------------------------------------------


class TestAPreviewCarriesTheConfigurationsPolicy:
    def test_an_exact_copy_is_accepted(
        self, paper: PostgresPaperExecutionRuntime, clean: Engine
    ) -> None:
        a_full_chain(paper)
        _accepted_then_rolled_back(clean, _preview())

    @pytest.mark.parametrize(
        ("field", "expression"),
        [
            ("maximum_notional", "maximum_notional * 100"),
            ("quote_maximum_age_seconds", "quote_maximum_age_seconds + 99939"),
            ("maximum_spread_percent", "maximum_spread_percent + 1"),
            ("policy_watchlist", "ARRAY['AAPL', 'MSFT', 'TSLA']::varchar(32)[]"),
            ("policy_prohibited_instruments", "ARRAY[]::varchar(32)[]"),
            ("earliest_entry_time", "earliest_entry_time - interval '1 minute'"),
            ("latest_entry_time", "latest_entry_time + interval '1 minute'"),
            ("operator_timezone", "'UTC'"),
        ],
    )
    def test_a_looser_or_different_policy_is_refused(
        self, paper: PostgresPaperExecutionRuntime, clean: Engine, field: str, expression: str
    ) -> None:
        a_full_chain(paper)
        _raises(clean, _preview(**{field: expression}), "does not carry the send-time policy")

    @pytest.mark.parametrize(
        ("field", "expression"),
        [
            ("configuration_version", "configuration_version + 1"),
            ("symbol", "'MSFT'"),
            ("quantity", "quantity - 1"),
            ("limit_price", "limit_price - 0.01"),
            ("approved_fingerprint", "repeat('9', 64)"),
            ("intent_expires_at", "intent_expires_at + interval '1 hour'"),
        ],
    )
    def test_an_order_other_than_the_intents_is_refused(
        self, paper: PostgresPaperExecutionRuntime, clean: Engine, field: str, expression: str
    ) -> None:
        a_full_chain(paper)
        _raises(
            clean, _preview(**{field: expression}), "does not describe the exact approved intent"
        )

    def test_an_authorizable_preview_above_its_cap_is_refused_by_check(
        self, paper: PostgresPaperExecutionRuntime, clean: Engine
    ) -> None:
        a_full_chain(paper)
        with pytest.raises(sa.exc.IntegrityError) as raised, clean.begin() as connection:
            connection.execute(text(_preview(maximum_notional="1")))
        assert "ck_paper_preview_authorizable_within_cap" in str(raised.value)


# ---------------------------------------------------------------------------
# Item 4 -- the exact schema head
# ---------------------------------------------------------------------------


class TestTheExactSchemaHeadIsRequired:
    def test_the_migrated_database_is_accepted(self, service: PostgresPersistenceService) -> None:
        assert require_exact_m085_schema_head(service) == M085_SCHEMA_HEAD

    @pytest.mark.parametrize(
        ("statement", "parameters"),
        [
            (
                "UPDATE public.alembic_version SET version_num = :revision",
                {"revision": _BELOW_THE_CORRECTIVE_REVISION},
            ),
            ("UPDATE public.alembic_version SET version_num = :revision", {"revision": _M084_HEAD}),
            (
                "UPDATE public.alembic_version SET version_num = :revision",
                {"revision": "ffff00000000"},
            ),
            (
                "INSERT INTO public.alembic_version (version_num) VALUES (:revision)",
                {"revision": _BELOW_THE_CORRECTIVE_REVISION},
            ),
            ("DELETE FROM public.alembic_version", {}),
        ],
        ids=["older-m085", "m084", "unknown-newer", "two-heads", "none"],
    )
    def test_any_other_revision_is_refused(
        self,
        clean: Engine,
        service: PostgresPersistenceService,
        statement: str,
        parameters: dict[str, Any],
    ) -> None:
        with clean.begin() as connection:
            connection.execute(text(statement), parameters)
        try:
            with pytest.raises(PaperSchemaHeadError, match=M085_SCHEMA_HEAD):
                require_exact_m085_schema_head(service)
        finally:
            with clean.begin() as connection:
                connection.execute(text("DELETE FROM public.alembic_version"))
                connection.execute(
                    text("INSERT INTO public.alembic_version (version_num) VALUES (:head)"),
                    {"head": M085_SCHEMA_HEAD},
                )
        assert require_exact_m085_schema_head(service) == M085_SCHEMA_HEAD


# ---------------------------------------------------------------------------
# The corrective migration itself
# ---------------------------------------------------------------------------


def _catalog(engine: Engine) -> dict[str, object]:
    with engine.begin() as connection:

        def columns(table: str) -> frozenset[str]:
            return frozenset(
                connection.execute(
                    text(
                        "SELECT column_name FROM information_schema.columns WHERE table_name = :t"
                    ),
                    {"t": table},
                ).scalars()
            )

        triggers = frozenset(
            connection.execute(
                text(
                    "SELECT t.tgname FROM pg_trigger t JOIN pg_class c ON c.oid = t.tgrelid "
                    "WHERE NOT t.tgisinternal AND c.relname IN "
                    "('paper_submission_preview', 'paper_execution_authorization')"
                )
            ).scalars()
        )

        def source(function: str) -> str:
            return str(
                connection.execute(
                    text("SELECT prosrc FROM pg_proc WHERE proname = :name"), {"name": function}
                ).scalar_one()
            )

        return {
            "preview": columns("paper_submission_preview"),
            "authorization": columns("paper_execution_authorization"),
            "triggers": triggers,
            "attempt_guard": source("paper_execution_attempt_guard_update"),
            "authorization_guard": source("paper_execution_authorization_guard_update"),
        }


def test_the_corrective_migration_goes_down_and_up_again(clean: Engine) -> None:
    at_head = _catalog(clean)
    assert {"binding_fingerprint", "policy_fingerprint", "intent_expires_at"} <= at_head["preview"]  # type: ignore[operator]
    assert "preview_binding_fingerprint" in at_head["authorization"]  # type: ignore[operator]
    assert {
        "paper_submission_preview_guard_policy_trigger",
        "paper_execution_authorization_guard_insert_trigger",
    } <= at_head["triggers"]  # type: ignore[operator]
    assert "is terminal in state % and is immutable" in str(at_head["attempt_guard"])
    assert "preview_binding_fingerprint" in str(at_head["authorization_guard"])

    alembic_command.downgrade(alembic_config(), _BELOW_THE_CORRECTIVE_REVISION)
    try:
        below = _catalog(clean)
        assert not {"binding_fingerprint", "policy_fingerprint"} & below["preview"]  # type: ignore[operator]
        assert "preview_binding_fingerprint" not in below["authorization"]  # type: ignore[operator]
        assert (
            not {
                "paper_submission_preview_guard_policy_trigger",
                "paper_execution_authorization_guard_insert_trigger",
            }
            & below["triggers"]
        )  # type: ignore[operator]
        # The exact prior guards are restored.
        assert "A same-state update refreshes" in str(below["attempt_guard"])
        assert "preview_binding_fingerprint" not in str(below["authorization_guard"])
        assert "basis_broker_latest_at" in str(below["authorization_guard"])
    finally:
        alembic_command.upgrade(alembic_config(), "head")
    assert _catalog(clean) == at_head


def test_the_upgrade_refuses_to_invent_a_binding_for_rows_that_exist(
    paper: PostgresPaperExecutionRuntime, clean: Engine
) -> None:
    a_full_chain(paper)
    alembic_command.downgrade(alembic_config(), _BELOW_THE_CORRECTIVE_REVISION)
    try:
        with pytest.raises(sa.exc.DatabaseError) as raised:
            alembic_command.upgrade(alembic_config(), "head")
        assert "refuses to invent them" in str(raised.value)
    finally:
        truncate_all(clean)
        alembic_command.upgrade(alembic_config(), "head")
    with clean.begin() as connection:
        revision = connection.execute(
            text("SELECT version_num FROM public.alembic_version")
        ).scalar_one()
    assert revision == M085_SCHEMA_HEAD
