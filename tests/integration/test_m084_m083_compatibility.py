"""MILESTONE-084 -- what M084 does to the frozen M083 schema, tested by M084.

M084's `evaluation_context` carries a foreign key to M083's
`evaluation_evidence_watermark`. That is a real change to a frozen milestone's
neighbourhood, and it had two visible consequences in M083's own suite:

  * M083's reset runs `TRUNCATE evaluation_evidence_watermark, ...` without
    CASCADE, and PostgreSQL refuses to truncate a table a foreign key
    references unless the referencing table is in the same statement;
  * M083's up/down/up test resolves its downgrade target as "the revision below
    head", which was M083's own predecessor only while M083 was head.

Both are consequences of M084 existing, not defects in M083. The frozen files
are therefore left exactly as they were -- byte-for-byte, enforced by
`tools/check_frozen_paths.py` -- and the coverage they can no longer provide at
the M084 head is re-established HERE, in a file M084 owns, at M084's own
expense.

The distinction this file maintains, and never blurs:

  FROZEN M083 ACCEPTANCE is M083's own suite passing at M083's own revision,
  unmodified. It is executed by `tools/m084_frozen_m083_acceptance.py`, which
  checks the frozen commit out into its own worktree and runs M083's tests
  there against their own database. Nothing in this file claims that result.

  M084 COMPATIBILITY is what this file tests: that at the M084 head M083's
  table, constraints, triggers, rows and reset semantics are still exactly what
  M083 established, and that M084's downgrade hands the schema back unchanged.

Two results, separately obtained and separately reported. Neither stands in for
the other, and a failure in one is never reported as a pass in the other.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command as alembic_command
from alembic.config import Config
from alembic.script import ScriptDirectory
from pydantic import SecretStr
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import DBAPIError

from empirical_platform.shared.config.settings import PostgreSQLConfigSnapshot

pytestmark = pytest.mark.integration

_REPO_ROOT = Path(__file__).resolve().parents[2]
_T0 = datetime(2026, 2, 1, tzinfo=UTC)

#: M083's own reset statement, reproduced here verbatim and WITHOUT cascade.
#: Copied rather than imported so that this file exercises the frozen text as
#: frozen: if M083's reset were ever edited, this copy would stop matching it
#: and `test_the_frozen_reset_text_is_still_what_m083_ships` would say so.
_M083_RESET = (
    "TRUNCATE evaluation_evidence_watermark, operator_event_receipt, operator_position_event"
)

#: M084's tables, in an order that respects their own foreign keys.
_M084_TABLES = (
    "approved_order_intent",
    "trade_approval_decision",
    "trade_proposal_risk_check",
    "trade_proposal",
    "evaluation_context",
    "operator_trading_configuration",
)


def _postgres_enabled() -> bool:
    return os.environ.get("EMPIRICAL_PLATFORM_RUN_POSTGRES_TESTS") == "1"


def _config() -> PostgreSQLConfigSnapshot:
    return PostgreSQLConfigSnapshot(
        host=os.environ.get("EMPIRICAL_PLATFORM_POSTGRES_HOST", "localhost"),
        port=int(os.environ.get("EMPIRICAL_PLATFORM_POSTGRES_PORT", "5432")),
        database=os.environ.get("EMPIRICAL_PLATFORM_POSTGRES_DATABASE", "empirical_platform"),
        user=os.environ.get("EMPIRICAL_PLATFORM_POSTGRES_USER", "empirical"),
        password=SecretStr(os.environ["EMPIRICAL_PLATFORM_POSTGRES_PASSWORD"]),
        pool_size=4,
        max_overflow=4,
        connection_timeout_seconds=5,
        application_name="empirical-platform-m084-m083-compatibility",
    )


def _alembic_config() -> Config:
    cfg = Config(str(_REPO_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(_REPO_ROOT / "migrations"))
    return cfg


def _revision_of(cfg: Config, milestone: str) -> str:
    """The revision whose migration message names `milestone`.

    Resolved from the graph by name rather than as an offset from head. An
    offset is only ever correct for as long as nothing is stacked on top, which
    is exactly the assumption M084 invalidated.
    """
    for script in ScriptDirectory.from_config(cfg).walk_revisions():
        if script.doc.startswith(milestone):
            return str(script.revision)
    raise AssertionError(f"no migration in the graph is labelled {milestone}")


def _revision_below(cfg: Config, milestone: str) -> str:
    for script in ScriptDirectory.from_config(cfg).walk_revisions():
        if script.doc.startswith(milestone):
            assert script.down_revision is not None
            return str(script.down_revision)
    raise AssertionError(f"no migration in the graph is labelled {milestone}")


@pytest.fixture(scope="module")
def engine() -> Iterator[Engine]:
    if not _postgres_enabled():
        pytest.skip("PostgreSQL integration tests require explicit opt-in")
    eng = sa.create_engine(_config().sqlalchemy_url(), pool_size=6, max_overflow=6)
    try:
        yield eng
    finally:
        eng.dispose()


@pytest.fixture
def at_head(engine: Engine) -> Iterator[Engine]:
    """A schema rebuilt from nothing through the full migration history."""
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
    alembic_command.upgrade(_alembic_config(), "head")
    yield engine
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))


def _seed_watermark(
    engine: Engine, *, event_gid: str, receipt_gid: str, watermark_gid: str
) -> None:
    """One M082 receipt and the M083 watermark that captures it.

    Two separate transactions: M082 refuses a receipt whose event was written
    by the same still-open transaction, and tripping that guarantee here would
    be testing M082, not M084's effect on M083.
    """
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO operator_position_event (runtime_id, governance_id, "
                "position_governance_id, instrument_symbol, event_kind, quantity, "
                "asserted_price, event_timestamp, recorded_at) VALUES "
                "(:rt, :gid, :pos, 'AAPL', 'OPENED', 1, 100, :t, :t)"
            ),
            {"rt": f"rt-{event_gid}", "gid": event_gid, "pos": f"POS-{event_gid}", "t": _T0},
        )
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO operator_event_receipt (receipt_governance_id, "
                "event_governance_id, system_received_at, attested_by, attester_version) "
                "VALUES (:rid, :gid, now(), 'test', 'test.1')"
            ),
            {"rid": receipt_gid, "gid": event_gid},
        )
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO evaluation_evidence_watermark (watermark_governance_id) VALUES (:wid)"
            ),
            {"wid": watermark_gid},
        )


class TestM083SurvivesTheM084Migration:
    """M084 adds tables; it must not have altered M083's."""

    def test_the_watermark_table_still_has_exactly_its_m083_columns(self, at_head: Engine) -> None:
        with at_head.begin() as conn:
            columns = conn.execute(
                text(
                    "SELECT column_name, data_type, is_nullable FROM information_schema.columns "
                    "WHERE table_schema = 'public' "
                    "AND table_name = 'evaluation_evidence_watermark' ORDER BY column_name"
                )
            ).all()
        assert [(c[0], c[1], c[2]) for c in columns] == [
            ("receipt_governance_ids", "ARRAY", "NO"),
            ("watermark_governance_id", "character varying", "NO"),
        ]

    def test_the_m083_constraints_and_triggers_are_all_still_present(self, at_head: Engine) -> None:
        with at_head.begin() as conn:
            constraints = {
                row[0]
                for row in conn.execute(
                    text(
                        "SELECT conname FROM pg_constraint "
                        "WHERE conrelid = 'public.evaluation_evidence_watermark'::regclass"
                    )
                )
            }
            triggers = {
                row[0]
                for row in conn.execute(
                    text(
                        "SELECT tgname FROM pg_trigger "
                        "WHERE tgrelid = 'public.evaluation_evidence_watermark'::regclass "
                        "AND NOT tgisinternal"
                    )
                )
            }
        assert "ck_evaluation_evidence_watermark_id_present" in constraints
        assert "pk_evaluation_evidence_watermark" in constraints
        assert triggers, "M083's capture and immutability triggers must still be attached"

    def test_the_capture_trigger_still_fills_the_receipt_set(self, at_head: Engine) -> None:
        # The behaviour, not merely the object: a trigger that exists but no
        # longer fires would satisfy the check above and fail this one.
        _seed_watermark(
            at_head, event_gid="EV-COMPAT1", receipt_gid="RC-COMPAT1", watermark_gid="WM-COMPAT1"
        )
        with at_head.begin() as conn:
            captured = conn.execute(
                text(
                    "SELECT receipt_governance_ids FROM evaluation_evidence_watermark "
                    "WHERE watermark_governance_id = 'WM-COMPAT1'"
                )
            ).scalar()
        assert captured == ["RC-COMPAT1"]

    def test_the_watermark_is_still_immutable(self, at_head: Engine) -> None:
        _seed_watermark(
            at_head, event_gid="EV-COMPAT2", receipt_gid="RC-COMPAT2", watermark_gid="WM-COMPAT2"
        )
        with pytest.raises(DBAPIError), at_head.begin() as conn:
            conn.execute(
                text(
                    "UPDATE evaluation_evidence_watermark SET receipt_governance_ids = "
                    "'{}' WHERE watermark_governance_id = 'WM-COMPAT2'"
                )
            )


class TestTheFrozenResetCannotRunAtTheM084Head:
    """A measured limitation, stated exactly, not worked around.

    The first attempt at this class assumed M084 could earn the frozen reset
    back by clearing its own tables first. That assumption was wrong, and these
    tests are what corrected it: PostgreSQL refuses to truncate a table a
    foreign key REFERENCES, whether or not the referencing table holds a single
    row. The restriction is structural, so no ordering, no prior cleanup and no
    transaction shape lets M083's frozen statement run while
    `evaluation_context` exists.

    That leaves exactly one honest description, and it is recorded here rather
    than repaired away:

      * at the M084 head, M083's frozen reset is INEXECUTABLE, so M083's
        PostgreSQL lifecycle and extended-attack suites cannot run unmodified
        there. Frozen M083 acceptance is therefore obtained at M083's own
        revision by `tools/m084_frozen_m083_acceptance.py`, never here;
      * remove M084 and the untouched statement works exactly as M083 wrote it,
        which is what makes this a limitation of M084's presence rather than a
        defect in M083.

    The alternatives were considered and rejected. Editing M083's reset to
    CASCADE makes "M083 still passes" mean "M083 passes a test M084 rewrote".
    Dropping the foreign key trades a real integrity guarantee for a green
    suite. Both buy the appearance of compatibility by spending the thing the
    tests exist to protect.
    """

    def test_the_frozen_reset_text_is_still_what_m083_ships(self) -> None:
        # Guards the copy above. If M083's reset were ever edited, the tests
        # below would be exercising text M083 no longer uses, and would quietly
        # stop meaning anything.
        frozen = (
            _REPO_ROOT / "tests/integration/test_m083_evaluation_evidence_watermark_lifecycle.py"
        ).read_text(encoding="utf-8")
        assert '"TRUNCATE evaluation_evidence_watermark, operator_event_receipt, "' in frozen
        assert '"operator_position_event"' in frozen
        assert "operator_position_event CASCADE" not in frozen

    def test_the_frozen_reset_is_refused_while_a_watermark_is_referenced(
        self, at_head: Engine
    ) -> None:
        # The behaviour that broke M083's suite, asserted directly and owned by
        # M084 -- so the constraint is recorded as a consequence of M084's
        # foreign key rather than rediscovered from someone else's red suite.
        _seed_watermark(
            at_head, event_gid="EV-COMPAT3", receipt_gid="RC-COMPAT3", watermark_gid="WM-COMPAT3"
        )
        with pytest.raises(DBAPIError, match="foreign key"), at_head.begin() as conn:
            conn.execute(text(_M083_RESET))

    def test_it_is_refused_even_with_every_m084_table_already_empty(self, at_head: Engine) -> None:
        # The test that corrected the assumption. PostgreSQL's objection is to
        # the CONSTRAINT, not to the data: with `evaluation_context` verifiably
        # empty the refusal is identical, which is why no cleanup-first fixture
        # could have rescued the frozen statement.
        _seed_watermark(
            at_head, event_gid="EV-COMPAT4", receipt_gid="RC-COMPAT4", watermark_gid="WM-COMPAT4"
        )
        with at_head.begin() as conn:
            conn.execute(text(f"TRUNCATE {', '.join(_M084_TABLES)}"))  # noqa: S608
            assert conn.execute(text("SELECT count(*) FROM evaluation_context")).scalar() == 0
        with pytest.raises(DBAPIError, match="foreign key"), at_head.begin() as conn:
            conn.execute(text(_M083_RESET))

    def test_the_same_reset_with_cascade_would_have_succeeded(self, at_head: Engine) -> None:
        # Named so the rejected repair is on the record as tested, not merely
        # asserted: CASCADE does work, and was still the wrong answer, because
        # it silently extends an M083 statement's blast radius into M084's
        # tables and rewrites what M083's frozen suite verifies.
        _seed_watermark(
            at_head, event_gid="EV-COMPAT7", receipt_gid="RC-COMPAT7", watermark_gid="WM-COMPAT7"
        )
        with at_head.begin() as conn:
            conn.execute(text(f"{_M083_RESET} CASCADE"))
            assert (
                conn.execute(text("SELECT count(*) FROM evaluation_evidence_watermark")).scalar()
                == 0
            )


class TestM083SurvivesTheM084Downgrade:
    """Downgrading M084 must hand M083 back exactly as it was."""

    def test_m083_rows_are_untouched_by_the_m084_downgrade(self, at_head: Engine) -> None:
        _seed_watermark(
            at_head, event_gid="EV-COMPAT5", receipt_gid="RC-COMPAT5", watermark_gid="WM-COMPAT5"
        )
        cfg = _alembic_config()
        alembic_command.downgrade(cfg, _revision_of(cfg, "MILESTONE-083"))
        with at_head.begin() as conn:
            row = conn.execute(
                text(
                    "SELECT watermark_governance_id, receipt_governance_ids "
                    "FROM evaluation_evidence_watermark"
                )
            ).all()
        assert row == [("WM-COMPAT5", ["RC-COMPAT5"])]

    def test_the_m084_downgrade_removes_every_m084_table_and_no_m083_one(
        self, at_head: Engine
    ) -> None:
        cfg = _alembic_config()
        alembic_command.downgrade(cfg, _revision_of(cfg, "MILESTONE-083"))
        with at_head.begin() as conn:
            present = {
                row[0]
                for row in conn.execute(
                    text(
                        "SELECT table_name FROM information_schema.tables "
                        "WHERE table_schema = 'public'"
                    )
                )
            }
        assert not (present & set(_M084_TABLES)), "M084 left tables behind on downgrade"
        assert "evaluation_evidence_watermark" in present

    def test_the_frozen_reset_runs_again_once_m084_is_downgraded_away(
        self, at_head: Engine
    ) -> None:
        # The clearest statement of the relationship: M083's frozen reset is
        # not wrong, it is simply incomplete while M084 exists. Remove M084 and
        # the untouched statement works exactly as M083 wrote it.
        _seed_watermark(
            at_head, event_gid="EV-COMPAT6", receipt_gid="RC-COMPAT6", watermark_gid="WM-COMPAT6"
        )
        cfg = _alembic_config()
        alembic_command.downgrade(cfg, _revision_of(cfg, "MILESTONE-083"))
        with at_head.begin() as conn:
            conn.execute(text(_M083_RESET))
            assert (
                conn.execute(text("SELECT count(*) FROM evaluation_evidence_watermark")).scalar()
                == 0
            )

    def test_downgrading_past_m083_still_removes_the_watermark_table(self, at_head: Engine) -> None:
        # The property M083's own up/down/up test asserts. At the M084 head that
        # test aims at M083 itself, because it resolves its target as "below
        # head". Re-established here, under M084's ownership, against the
        # revision below M083 resolved by name.
        cfg = _alembic_config()
        alembic_command.downgrade(cfg, _revision_below(cfg, "MILESTONE-083"))
        with at_head.begin() as conn:
            assert not conn.execute(
                text("SELECT to_regclass('public.evaluation_evidence_watermark') IS NOT NULL")
            ).scalar()
        alembic_command.upgrade(cfg, "head")
        with at_head.begin() as conn:
            assert conn.execute(
                text("SELECT to_regclass('public.evaluation_evidence_watermark') IS NOT NULL")
            ).scalar()
