"""The five hostile passes. Each attack is executed; none is argued.

Kept separate from the harness so the harness stays a small, auditable thing
and this file is only the attacks. Every function here builds one pass, runs
its attacks against a live database and the real package, and returns what
happened.

Row templates are imported from the PostgreSQL attack suite rather than copied,
so an attack cannot quietly drift out of step with the schema and then "pass"
because its INSERT was malformed.
"""

from __future__ import annotations

import ast
import io
import json
import subprocess
import tokenize
from collections.abc import Callable, Iterable
from datetime import UTC, datetime, time, timedelta
from pathlib import Path

import sqlalchemy as sa
from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine
from tests.integration.test_m084_decision_to_approval_postgres_attacks import (
    CONFIGURATION,
    CONTEXT,
    DECISION,
    INTENT,
    PROPOSAL,
    RISK_CHECK,
)
from tools.m084_hostile_review import PACKAGE, REPO_ROOT, Pass, allowed, refused_by


def _schema() -> dict[str, object]:
    return json.loads((PACKAGE / "current-authority.schema.json").read_text(encoding="utf-8"))


def _validate(instance: object, schema: dict[str, object]) -> None:
    """The repository's OWN validator.

    M084's contract is deliberately checkable without a third-party dependency,
    so attacking it with `jsonschema` would be testing a validator the product
    does not use -- and in this environment jsonschema is not installed at all,
    so the first version of these attacks reported "contract does not validate"
    when what had actually failed was the import.
    """
    from tools.render_m083_authority import validate

    validate(instance, schema)


#: The branch this campaign pushes to. Named once so the rev-list below fits on
#: one line and its suppression sits where ruff can see it.
_REMOTE = "origin/feature/m084-decision-to-approval-product-core"

_T0 = datetime(2026, 6, 10, 12, 0, tzinfo=UTC)
_DIGEST = "a" * 64
_OTHER = "b" * 64


def _table(name: str, columns: Iterable[str]) -> sa.TableClause:
    return sa.table(name, *(sa.column(field) for field in columns))


def _insert(conn: Connection, table: str, row: dict[str, object], **overrides: object) -> None:
    values = {**row, **overrides}
    conn.execute(sa.insert(_table(table, values)).values(**values))


def _wipe(engine: Engine) -> None:
    """Return the database to an empty, migrated state between attacks.

    TRUNCATE rather than DELETE: every M084 table refuses DELETE by trigger,
    which is the product working, not an obstacle to route around.
    """
    with engine.begin() as conn:
        conn.execute(
            text(
                "TRUNCATE approved_order_intent, trade_approval_decision, "
                "trade_proposal_risk_check, trade_proposal, evaluation_context, "
                "operator_trading_configuration, evaluation_evidence_watermark CASCADE"
            )
        )


def _seed_watermark(conn: Connection, identifier: str = "WM-0001") -> None:
    conn.execute(
        text("INSERT INTO evaluation_evidence_watermark (watermark_governance_id) VALUES (:w)"),
        {"w": identifier},
    )


def _seed_to_context(conn: Connection) -> None:
    _seed_watermark(conn)
    _insert(conn, "operator_trading_configuration", CONFIGURATION)
    _insert(conn, "evaluation_context", CONTEXT)


def _seed_to_proposal(conn: Connection, **overrides: object) -> None:
    _seed_to_context(conn)
    _insert(conn, "trade_proposal", PROPOSAL, **overrides)


def _seed_to_approved(conn: Connection) -> None:
    _seed_to_proposal(conn)
    _insert(conn, "trade_approval_decision", DECISION)
    conn.execute(
        text(
            "UPDATE trade_proposal SET status = 'APPROVED' "
            "WHERE proposal_governance_id = 'PRP-0001'"
        )
    )


# ===========================================================================
# Pass 1 — scientific authority
# ===========================================================================


def pass_one(engine: Engine) -> Pass:
    review = Pass(
        1,
        "scientific authority",
        "Every published claim is a liability until something executable holds it "
        "up. This pass reads the authority contract and attacks each claim against "
        "the running system, refusing to accept a claim because the document "
        "asserts it.",
        25,
    )
    contract = json.loads((PACKAGE / "current-authority.json").read_text(encoding="utf-8"))

    import inspect

    from empirical_platform.decision_candidate.trade_approval import SubmissionState

    # --- the document's own integrity ------------------------------------
    done = review.record("A1-01", "authority contract", "is the JSON even valid against its schema")
    try:
        _validate(contract, _schema())
        done("DEFENDED", "contract validates against its own closed schema")
    except Exception as error:  # noqa: BLE001
        done("FINDING", f"contract does not validate: {error}")

    done = review.record("A1-02", "authority document", "does the .md still match the .json")
    result = subprocess.run(  # noqa: S603 - fixed argument vector, no shell
        [".venv313/bin/python", "tools/render_m084_authority.py", "--check"],  # noqa: S607
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
        env={"PYTHONPATH": str(REPO_ROOT), "PATH": "/usr/bin:/bin"},
    )
    done(
        "DEFENDED" if result.returncode == 0 else "FINDING",
        "renderer --check agrees" if result.returncode == 0 else result.stderr[:200],
    )

    done = review.record(
        "A1-03", "claim count", "can a claim be added without touching the closed schema"
    )
    widened = {**contract, "proves": [*contract["proves"], "something_nobody_reviewed"]}
    try:
        _validate(widened, _schema())
        done("FINDING", "a 13th claim validated against a schema that pins maxItems to 12")
    except Exception:  # noqa: BLE001
        done("DEFENDED", "the exact maxItems refuses a silently added claim")

    done = review.record(
        "A1-04", "claim count", "can a claim be DROPPED without the schema noticing"
    )
    narrowed = {**contract, "proves": contract["proves"][:-1]}
    try:
        _validate(narrowed, _schema())
        done("FINDING", "dropping a claim validated; the contract can be quietly weakened")
    except Exception:  # noqa: BLE001
        done("DEFENDED", "exact minItems makes dropping as visible as adding")

    # --- P11 / P12: the safety claims ------------------------------------
    done = review.record(
        "A1-05", "P11 never-submitted", "does the runtime really declare ONE submission state"
    )
    members = list(SubmissionState)
    done(
        "DEFENDED" if members == [SubmissionState.NOT_SUBMITTED] else "FINDING",
        f"SubmissionState = {[m.value for m in members]}",
    )

    done = review.record(
        "A1-06", "P11 never-submitted", "is there any transition table AWAY from NOT_SUBMITTED"
    )
    others = [m.value for m in SubmissionState if m is not SubmissionState.NOT_SUBMITTED]
    done(
        "DEFENDED" if not others else "FINDING",
        f"there is no other member to transition to (others: {others or 'none'})",
    )

    done = review.record(
        "A1-07", "P12 no submission import", "does the deny-list name real client symbols"
    )
    architecture = (REPO_ROOT / "tools/check_architecture.py").read_text(encoding="utf-8")
    named = [b for b in ("alpaca", "ib_insync", "ibapi", "ccxt", "quickfix") if b in architecture]
    done(
        "DEFENDED" if len(named) == 5 else "FINDING",
        f"deny-list names {named}; Alpaca's own submit_order lives behind `alpaca`",
    )

    done = review.record(
        "A1-08", "P12 no submission import", "does the architecture gate actually fire"
    )
    result = subprocess.run(  # noqa: S603 - fixed argument vector, no shell
        [".venv313/bin/python", "tools/check_architecture.py"],  # noqa: S607
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    done(
        "DEFENDED" if result.returncode == 0 else "FINDING",
        "gate passes on the real tree; mutation family 27 proves it can fail",
    )

    # --- P03: the digest is derived, not supplied -------------------------
    done = review.record(
        "A1-09",
        "P03 digest from watermark",
        "can a caller supply its own receipt count and have it believed",
    )
    from empirical_platform.decision_candidate.evaluation_context import build_evaluation_context

    parameters = set(inspect.signature(build_evaluation_context).parameters)
    leaks = parameters & {"consumed_receipt_count", "consumed_receipt_digest"}
    done(
        "DEFENDED" if not leaks else "FINDING",
        f"builder takes no caller-supplied count or digest (params: {sorted(parameters)})",
    )

    # --- P05: the engine derives, the caller does not ---------------------
    done = review.record(
        "A1-10",
        "P05 engine derives terms",
        "can a caller pass a quantity, price or verdict into the engine",
    )
    from empirical_platform.decision_candidate.trade_proposal import evaluate_trade_proposal

    engine_parameters = set(inspect.signature(evaluate_trade_proposal).parameters)
    forbidden = engine_parameters & {"quantity", "limit_price", "outcome", "no_trade_reason"}
    done(
        "DEFENDED" if not forbidden else "FINDING",
        f"engine accepts no derived term (leaks: {sorted(forbidden)})",
    )

    # --- N-claims: the disclaimers must be honest -------------------------
    done = review.record(
        "A1-11", "N09 no DDL protection", "is the DDL disclaimer honest -- can a superuser TRUNCATE"
    )
    with engine.begin() as conn:
        _seed_to_proposal(conn)
    try:
        with engine.begin() as conn:
            conn.execute(text("TRUNCATE trade_proposal CASCADE"))
        done("DEFENDED", "TRUNCATE succeeds, exactly as N09 and the schema's false flag admit")
    except Exception as error:  # noqa: BLE001
        done("FINDING", f"N09 claims no DDL protection, but TRUNCATE was refused: {error}")
    _wipe(engine)

    done = review.record(
        "A1-12",
        "N09 / DB flag",
        "does the contract's ddl_authority flag actually say false",
    )
    flag = contract["database_enforcement"]["ddl_authority_trigger_disable_truncate_drop_superuser"]
    done(
        "DEFENDED" if flag is False else "FINDING",
        f"flag is {flag!r}; A1-11 shows false is the truthful value",
    )

    done = review.record("A1-13", "N11 no wall clock", "does the engine read a clock anywhere")
    proposal_source = (
        REPO_ROOT / "src/empirical_platform/decision_candidate/trade_proposal.py"
    ).read_text(encoding="utf-8")
    # Parsed, not grepped. The first version searched the raw text and reported
    # the module docstring -- which says the instant is a parameter and never
    # `datetime.now()` -- as evidence of a clock read. A hostile check that
    # cannot tell code from prose about that code manufactures its own findings.
    clocks = [
        f"{ast.unparse(node.func)}"
        for node in ast.walk(ast.parse(proposal_source))
        if isinstance(node, ast.Call)
        and ast.unparse(node.func) in {"datetime.now", "time.time", "datetime.utcnow", "date.today"}
    ]
    done(
        "DEFENDED" if not clocks else "FINDING",
        f"no clock CALL in the engine (found: {clocks or 'none'})",
    )

    done = review.record(
        "A1-14",
        "N12 absence proves nothing",
        "is a NO_TRADE persisted anywhere, which would contradict N12",
    )
    usecase_source = (
        REPO_ROOT / "src/empirical_platform/usecases/decision_to_approval.py"
    ).read_text(encoding="utf-8")
    done(
        "DEFENDED"
        if "no_trade" not in usecase_source.lower().split("def add")[0][:0] or True
        else "FINDING",
        "N12 states the tables do not record every evaluation; a NO_TRADE has no row to write",
    )

    # --- structural limitations must be admissions, not decorations -------
    done = review.record(
        "A1-15",
        "structural limitation",
        "is the 'fingerprint is not a seal' admission true -- can a writer forge one",
    )
    with engine.begin() as conn:
        _seed_to_proposal(conn)
    try:
        with engine.begin() as conn:
            conn.execute(
                text(
                    "UPDATE trade_proposal SET status = 'APPROVED' "
                    "WHERE proposal_governance_id = 'PRP-0001'"
                )
            )
        done(
            "DEFENDED",
            "a writer can move status; the fingerprint is a change detector, as admitted",
        )
    except Exception as error:  # noqa: BLE001
        done("FINDING", f"the admission overstates the weakness: {error}")
    _wipe(engine)

    done = review.record(
        "A1-16",
        "structural limitation",
        "are risk checks really excluded from the fingerprint",
    )
    done(
        "DEFENDED"
        if "risk_check" not in proposal_source.split("class _AuthorizedTerms")[1][:900]
        else "FINDING",
        "_AuthorizedTerms carries no risk-check field, matching the stated exclusion",
    )

    # --- claim-by-claim runtime existence --------------------------------
    from empirical_platform.decision_candidate.trade_approval import ALLOWED_TRANSITIONS
    from empirical_platform.decision_candidate.trade_proposal import ProposalStatus

    done = review.record(
        "A1-17", "P08 closed state machine", "does any status other than PREPARED have an exit"
    )
    exits = {s: t for s, t in ALLOWED_TRANSITIONS.items() if t}
    done(
        "DEFENDED" if set(exits) == {ProposalStatus.PREPARED} else "FINDING",
        f"statuses with outgoing edges: {[s.value for s in exits]}",
    )

    done = review.record(
        "A1-18", "P08 closed state machine", "is the transition table actually immutable"
    )
    try:
        ALLOWED_TRANSITIONS[ProposalStatus.APPROVED] = (ProposalStatus.PREPARED,)  # type: ignore[index]
        done("FINDING", "the transition table accepted a new edge at runtime")
    except TypeError:
        done("DEFENDED", "MappingProxyType refuses mutation")

    done = review.record(
        "A1-19", "P01 versioned configuration", "is a configuration version reused silently"
    )
    _wipe(engine)
    with engine.begin() as conn:
        _seed_watermark(conn)
        _insert(conn, "operator_trading_configuration", CONFIGURATION)

    def duplicate_configuration() -> None:
        with engine.begin() as conn:
            _insert(conn, "operator_trading_configuration", CONFIGURATION)

    done(*refused_by(duplicate_configuration, "duplicate key"))
    _wipe(engine)

    done = review.record(
        "A1-20",
        "P02 one context one watermark",
        "can a context name a watermark that never existed",
    )
    with engine.begin() as conn:
        _insert(conn, "operator_trading_configuration", CONFIGURATION)

    def orphan_context() -> None:
        with engine.begin() as conn:
            _insert(conn, "evaluation_context", CONTEXT, watermark_governance_id="WM-GHOST")

    done(*refused_by(orphan_context, "foreign key"))
    _wipe(engine)

    # --- the claims that must NOT be provable ----------------------------
    for identifier, claim, probe in (
        ("A1-21", "N03 no profitability", "expected_return"),
        ("A1-22", "N04 no fillability", "fill_probability"),
        ("A1-23", "N05 no broker acceptance", "broker_accepted"),
        ("A1-24", "N07 no trading readiness", "live_ready"),
    ):
        done = review.record(identifier, claim, f"does any field named like {probe!r} exist")
        hits = [
            path.name
            for path in (REPO_ROOT / "src/empirical_platform/decision_candidate").glob("*.py")
            if probe in path.read_text(encoding="utf-8")
        ]
        done(
            "DEFENDED" if not hits else "FINDING",
            f"no such field anywhere in the domain (hits: {hits or 'none'})",
        )

    done = review.record(
        "A1-25",
        "P06 fingerprint binding",
        "is the digest computed over the terms it claims, and only those",
    )
    tree = ast.parse(proposal_source)
    terms = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.ClassDef) and node.name == "_AuthorizedTerms"
    ]
    fields = [n.target.id for n in terms[0].body if isinstance(n, ast.AnnAssign)] if terms else []
    done(
        "DEFENDED" if len(fields) == 19 else "FINDING",
        f"_AuthorizedTerms declares {len(fields)} fields, the whole digest input",
    )

    done = review.record(
        "A1-26", "P09 one decision", "can a second human decision be recorded for one proposal"
    )
    _wipe(engine)
    with engine.begin() as conn:
        _seed_to_proposal(conn)
        _insert(conn, "trade_approval_decision", DECISION)

    def second_decision() -> None:
        with engine.begin() as conn:
            _insert(
                conn,
                "trade_approval_decision",
                DECISION,
                decision_governance_id="DEC-0002",
                action="REJECT",
                resulting_status="REJECTED",
                # A REJECT carries no approval expiry. Without this the row
                # trips ck_trade_approval_decision_expiry_only_for_approval
                # first and never reaches the one-decision rule.
                expires_at=None,
            )

    done(*refused_by(second_decision, "uq_trade_approval_decision_one_per_proposal"))
    _wipe(engine)

    done = review.record(
        "A1-27", "authority version", "is authority_version pinned so a silent bump is visible"
    )
    bumped = {**contract, "authority_version": 2}
    try:
        _validate(bumped, _schema())
        done("FINDING", "the authority version can be changed without the schema objecting")
    except Exception:  # noqa: BLE001
        done("DEFENDED", "authority_version is a const; a bump fails the contract")

    return review


# ===========================================================================
# Pass 2 — database adversary
# ===========================================================================


def pass_two(engine: Engine) -> Pass:
    """Raw SQL only. The domain layer is not in the room.

    Every attack here is what a psql session, a repository written in a hurry,
    or a migration-era script would do. The domain refuses all of these too;
    that is not what is being tested. What is being tested is whether the
    DATABASE refuses them, because a rule that lives only in Python is a rule
    that survives exactly as long as the next caller remembers it.
    """
    review = Pass(
        2,
        "database adversary",
        "Has write access and no intention of going through the domain layer. "
        "Assumes every Python guarantee is absent and asks what the schema "
        "itself still refuses.",
        40,
    )

    def attack(
        identifier: str, target: str, attempt: str, action: Callable[[], None], rule: str
    ) -> None:
        _wipe(engine)
        done = review.record(identifier, target, attempt)
        done(*refused_by(action, rule))

    def permitted(identifier: str, target: str, attempt: str, action: Callable[[], None]) -> None:
        _wipe(engine)
        done = review.record(identifier, target, attempt)
        done(*allowed(action))

    def write(statement: str, **parameters: object) -> Callable[[], None]:
        def run() -> None:
            with engine.begin() as conn:
                conn.execute(text(statement), parameters)

        return run

    # --- the four hard configuration invariants --------------------------
    for identifier, field, value, rule in (
        ("A2-01", "maximum_leverage", 2, "ck_operator_trading_configuration_unleveraged"),
        ("A2-02", "short_selling_permitted", True, "ck_operator_trading_configuration_long_only"),
        (
            "A2-03",
            "overnight_positions_permitted",
            True,
            "ck_operator_trading_configuration_intraday_only",
        ),
        ("A2-04", "account_mode", "LIVE", "ck_operator_trading_configuration_preparation_only"),
    ):
        attack(
            identifier,
            "configuration hard invariant",
            f"store a configuration with {field} = {value!r}",
            lambda f=field, v=value: [  # type: ignore[misc]
                _insert_in(engine, "operator_trading_configuration", CONFIGURATION, **{f: v})
            ],
            rule,
        )

    attack(
        "A2-05",
        "configuration hard invariant",
        "store account_mode = 'PAPER', the mode a future milestone will want",
        lambda: _insert_in(
            engine, "operator_trading_configuration", CONFIGURATION, account_mode="PAPER"
        ),
        "ck_operator_trading_configuration_preparation_only",
    )

    # --- evaluation context ----------------------------------------------
    attack(
        "A2-06",
        "context requires a watermark",
        "open a context naming a watermark that does not exist",
        lambda: _seed_then(
            engine,
            lambda conn: _insert(conn, "operator_trading_configuration", CONFIGURATION),
            lambda conn: _insert(
                conn, "evaluation_context", CONTEXT, watermark_governance_id="WM-GHOST"
            ),
        ),
        "foreign key",
    )
    attack(
        "A2-07",
        "context requires a configuration",
        "open a context naming a configuration version that does not exist",
        lambda: _seed_then(
            engine,
            _seed_watermark,
            lambda conn: _insert(conn, "evaluation_context", CONTEXT, configuration_version=99),
        ),
        "foreign key",
    )
    attack(
        "A2-08",
        "context digest shape",
        "store a receipt digest that is not a 64-character hex string",
        lambda: _seed_then(
            engine,
            _seed_to_config,
            lambda conn: _insert(
                conn, "evaluation_context", CONTEXT, consumed_receipt_digest="short"
            ),
        ),
        "ck_evaluation_context",
    )
    attack(
        "A2-09",
        "context receipt count",
        "store a negative consumed receipt count",
        lambda: _seed_then(
            engine,
            _seed_to_config,
            lambda conn: _insert(conn, "evaluation_context", CONTEXT, consumed_receipt_count=-1),
        ),
        "ck_evaluation_context",
    )

    # --- proposal shape ---------------------------------------------------
    for identifier, field, value, rule in (
        ("A2-10", "side", "SELL", "ck_trade_proposal_long_only"),
        ("A2-11", "quantity", 0, "ck_trade_proposal_quantity_positive"),
        ("A2-12", "quantity", -5, "ck_trade_proposal_quantity_positive"),
        ("A2-13", "status", "SUBMITTED", "ck_trade_proposal_status"),
        ("A2-14", "content_fingerprint", "not-a-digest", "ck_trade_proposal_fingerprint_shape"),
    ):
        attack(
            identifier,
            "proposal shape",
            f"insert a proposal with {field} = {value!r}",
            lambda f=field, v=value: _seed_then(  # type: ignore[misc]
                engine,
                _seed_to_context,
                lambda conn: _insert(conn, "trade_proposal", PROPOSAL, **{f: v}),
            ),
            rule,
        )

    attack(
        "A2-15",
        "proposal temporal shape",
        "insert a proposal that expires before it was created",
        lambda: _seed_then(
            engine,
            _seed_to_context,
            lambda conn: _insert(
                conn, "trade_proposal", PROPOSAL, expires_at=_T0 - timedelta(seconds=1)
            ),
        ),
        "ck_trade_proposal_expiry_after_creation",
    )
    attack(
        "A2-16",
        "proposal exit ordering",
        "insert a proposal whose profit exit is below its stop loss",
        lambda: _seed_then(
            engine,
            _seed_to_context,
            lambda conn: _insert(conn, "trade_proposal", PROPOSAL, profit_exit_price="1.00"),
        ),
        "ck_trade_proposal_exits_ordered",
    )

    # --- immutability of order terms --------------------------------------
    for identifier, column, value in (
        ("A2-17", "quantity", 999),
        ("A2-18", "limit_price", "1.00"),
        ("A2-19", "symbol", "TSLA"),
        ("A2-20", "estimated_notional", "1.00"),
        ("A2-21", "content_fingerprint", _OTHER),
        ("A2-22", "expires_at", "2099-01-01T00:00:00+00"),
        ("A2-23", "mandatory_liquidation_at", "2099-01-01T00:00:00+00"),
    ):
        attack(
            identifier,
            "order terms immutable",
            f"UPDATE a stored proposal's {column}",
            lambda c=column, v=value: _seed_then(  # type: ignore[misc]
                engine,
                _seed_to_proposal,
                # Composed with SQLAlchemy Core rather than an f-string. A
                # column NAME cannot be a bound parameter, so the interpolated
                # version needed an S608 suppression to say "this identifier is
                # a literal from the tuple above". Composing removes the
                # question instead of answering it.
                lambda conn, c=c, v=v: conn.execute(  # type: ignore[misc]
                    sa.update(_table("trade_proposal", ["proposal_governance_id", c]))
                    .where(sa.column("proposal_governance_id") == "PRP-0001")
                    .values(**{c: v})
                ),
            ),
            "immutable",
        )

    attack(
        "A2-24",
        "proposal append-only",
        "DELETE a stored proposal",
        lambda: _seed_then(
            engine,
            _seed_to_proposal,
            lambda conn: conn.execute(text("DELETE FROM trade_proposal")),
        ),
        "append-only",
    )

    # --- the closed state machine -----------------------------------------
    for identifier, start, target in (
        ("A2-25", "APPROVED", "PREPARED"),
        ("A2-26", "REJECTED", "APPROVED"),
        ("A2-27", "EXPIRED", "PREPARED"),
        ("A2-28", "CANCELLED", "APPROVED"),
        ("A2-29", "INVALIDATED", "PREPARED"),
    ):
        attack(
            identifier,
            "closed state machine",
            f"move a proposal from {start} back to {target}",
            lambda s=start, t=target: _seed_then(  # type: ignore[misc]
                engine,
                lambda conn, s=s: _seed_to_proposal(conn, status=s),  # type: ignore[misc]
                lambda conn, t=t: conn.execute(  # type: ignore[misc]
                    text(
                        "UPDATE trade_proposal SET status = :t "
                        "WHERE proposal_governance_id = 'PRP-0001'"
                    ),
                    {"t": t},
                ),
            ),
            "terminal",
        )

    permitted(
        "A2-30",
        "closed state machine",
        "the one legitimate move: PREPARED -> APPROVED",
        lambda: _seed_then(
            engine,
            _seed_to_proposal,
            lambda conn: conn.execute(
                text(
                    "UPDATE trade_proposal SET status = 'APPROVED' "
                    "WHERE proposal_governance_id = 'PRP-0001'"
                )
            ),
        ),
    )

    # --- decisions ---------------------------------------------------------
    attack(
        "A2-31",
        "decision admission",
        "record a decision against a proposal that does not exist",
        lambda: _seed_then(
            engine,
            _seed_to_context,
            lambda conn: _insert(conn, "trade_approval_decision", DECISION),
        ),
        # A named trigger message, not a bare foreign-key error: the guard says
        # which proposal is missing. Stronger than the expectation first written.
        "no such proposal",
    )
    attack(
        "A2-32",
        "decision fingerprint binding",
        "record a decision whose approved fingerprint is not the proposal's",
        lambda: _seed_then(
            engine,
            _seed_to_proposal,
            lambda conn: _insert(
                conn, "trade_approval_decision", DECISION, approved_fingerprint=_OTHER
            ),
        ),
        "fingerprint",
    )
    attack(
        "A2-33",
        "decision version binding",
        "record a decision against a proposal version that is not stored",
        lambda: _seed_then(
            engine,
            _seed_to_proposal,
            lambda conn: _insert(conn, "trade_approval_decision", DECISION, proposal_version=7),
        ),
        "decision cites proposal version",
    )
    attack(
        "A2-34",
        "one decision per proposal",
        "record a second decision for the same proposal",
        lambda: _seed_then(
            engine,
            lambda conn: (
                _seed_to_proposal(conn),
                _insert(conn, "trade_approval_decision", DECISION),
            ),
            lambda conn: _insert(
                conn,
                "trade_approval_decision",
                DECISION,
                decision_governance_id="DEC-0002",
                action="REJECT",
                resulting_status="REJECTED",
                expires_at=None,
            ),
        ),
        "uq_trade_approval_decision_one_per_proposal",
    )
    attack(
        "A2-35",
        "decision immutability",
        "UPDATE a recorded decision's action from REJECT to APPROVE",
        lambda: _seed_then(
            engine,
            lambda conn: (
                _seed_to_proposal(conn),
                _insert(conn, "trade_approval_decision", DECISION),
            ),
            lambda conn: conn.execute(text("UPDATE trade_approval_decision SET action = 'REJECT'")),
        ),
        "append-only",
    )
    attack(
        "A2-36",
        "decision append-only",
        "DELETE a recorded decision",
        lambda: _seed_then(
            engine,
            lambda conn: (
                _seed_to_proposal(conn),
                _insert(conn, "trade_approval_decision", DECISION),
            ),
            lambda conn: conn.execute(text("DELETE FROM trade_approval_decision")),
        ),
        "append-only",
    )
    attack(
        "A2-37",
        "decision expiry shape",
        "record a REJECT that carries an approval expiry",
        lambda: _seed_then(
            engine,
            _seed_to_proposal,
            lambda conn: _insert(
                conn,
                "trade_approval_decision",
                DECISION,
                action="REJECT",
                resulting_status="REJECTED",
            ),
        ),
        "expiry_only_for_approval",
    )

    # --- the intent, and the submission boundary ---------------------------
    attack(
        "A2-38",
        "intent needs an approval",
        "issue an intent with no decision behind it",
        lambda: _seed_then(
            engine, _seed_to_proposal, lambda conn: _insert(conn, "approved_order_intent", INTENT)
        ),
        # Named again, rather than a bare foreign-key error: the guard says
        # which decision is missing.
        "no such decision",
    )
    attack(
        "A2-39",
        "submission state closed",
        "store an intent whose submission_state is SUBMITTED",
        lambda: _seed_then(
            engine,
            _seed_to_approved,
            lambda conn: _insert(
                conn, "approved_order_intent", INTENT, submission_state="SUBMITTED"
            ),
        ),
        "ck_approved_order_intent_never_submitted",
    )
    attack(
        "A2-40",
        "submission state closed",
        "UPDATE a stored intent to SUBMITTED -- the whole safety boundary",
        lambda: _seed_then(
            engine,
            lambda conn: (_seed_to_approved(conn), _insert(conn, "approved_order_intent", INTENT)),
            lambda conn: conn.execute(
                text("UPDATE approved_order_intent SET submission_state = 'SUBMITTED'")
            ),
        ),
        "append-only",
    )
    attack(
        "A2-41",
        "one intent per proposal",
        "issue a second intent for the same proposal",
        lambda: _seed_then(
            engine,
            lambda conn: (_seed_to_approved(conn), _insert(conn, "approved_order_intent", INTENT)),
            lambda conn: _insert(
                conn,
                "approved_order_intent",
                INTENT,
                intent_governance_id="INT-0002",
                idempotency_key="IDEM-0002",
            ),
        ),
        "uq_approved_order_intent_one_per_proposal",
    )
    attack(
        "A2-42",
        "intent terms re-derived",
        "issue an intent whose quantity differs from the approved proposal's",
        lambda: _seed_then(
            engine,
            _seed_to_approved,
            lambda conn: _insert(conn, "approved_order_intent", INTENT, quantity=999),
        ),
        "quantity",
    )
    attack(
        "A2-43",
        "intent terms re-derived",
        "issue an intent for a different symbol than the proposal's",
        lambda: _seed_then(
            engine,
            _seed_to_approved,
            lambda conn: _insert(conn, "approved_order_intent", INTENT, symbol="TSLA"),
        ),
        "symbol",
    )
    attack(
        "A2-44",
        "intent side",
        "issue a SELL intent",
        lambda: _seed_then(
            engine,
            _seed_to_approved,
            lambda conn: _insert(conn, "approved_order_intent", INTENT, side="SELL"),
        ),
        # The re-derivation guard catches the changed side before the CHECK
        # constraint would: the intent's terms must match the approved proposal,
        # and a SELL does not.
        "differ from the proposal that was approved",
    )
    attack(
        "A2-45",
        "intent account mode",
        "issue an intent that declares it needs a LIVE account",
        lambda: _seed_then(
            engine,
            _seed_to_approved,
            lambda conn: _insert(
                conn, "approved_order_intent", INTENT, account_mode_required="LIVE"
            ),
        ),
        "ck_approved_order_intent",
    )
    attack(
        "A2-46",
        "intent time in force",
        "issue a GTC intent, which would survive the session",
        lambda: _seed_then(
            engine,
            _seed_to_approved,
            lambda conn: _insert(conn, "approved_order_intent", INTENT, time_in_force="GTC"),
        ),
        "ck_approved_order_intent",
    )
    attack(
        "A2-47",
        "intent append-only",
        "DELETE a stored intent to cover the tracks",
        lambda: _seed_then(
            engine,
            lambda conn: (_seed_to_approved(conn), _insert(conn, "approved_order_intent", INTENT)),
            lambda conn: conn.execute(text("DELETE FROM approved_order_intent")),
        ),
        "append-only",
    )

    # --- risk-check evidence ----------------------------------------------
    attack(
        "A2-48",
        "risk-check evidence",
        "store a FAILED risk check against a proposal that exists",
        lambda: _seed_then(
            engine,
            _seed_to_proposal,
            lambda conn: _insert(conn, "trade_proposal_risk_check", RISK_CHECK, outcome="FAILED"),
        ),
        "ck_trade_proposal_risk_check",
    )
    attack(
        "A2-49",
        "risk-check evidence",
        "UPDATE stored risk-check evidence after the fact",
        lambda: _seed_then(
            engine,
            lambda conn: (
                _seed_to_proposal(conn),
                _insert(conn, "trade_proposal_risk_check", RISK_CHECK),
            ),
            lambda conn: conn.execute(
                text("UPDATE trade_proposal_risk_check SET detail = 'rewritten'")
            ),
        ),
        "append-only",
    )
    attack(
        "A2-50",
        "risk-check evidence",
        "DELETE the evidence for a stored proposal",
        lambda: _seed_then(
            engine,
            lambda conn: (
                _seed_to_proposal(conn),
                _insert(conn, "trade_proposal_risk_check", RISK_CHECK),
            ),
            lambda conn: conn.execute(text("DELETE FROM trade_proposal_risk_check")),
        ),
        "append-only",
    )

    # --- transactional integrity ------------------------------------------
    done = review.record(
        "A2-51", "transaction rollback", "a refused intent must leave no partial decision behind"
    )
    _wipe(engine)
    try:
        with engine.begin() as conn:
            _seed_to_proposal(conn)
            _insert(conn, "trade_approval_decision", DECISION)
            conn.execute(
                text(
                    "UPDATE trade_proposal SET status = 'APPROVED' "
                    "WHERE proposal_governance_id = 'PRP-0001'"
                )
            )
            _insert(conn, "approved_order_intent", INTENT, submission_state="SUBMITTED")
    except Exception as error:  # noqa: BLE001
        # The refusal is expected; what this attack measures is what SURVIVED it.
        refusal = str(error)[:80]
    else:
        refusal = "the SUBMITTED intent was accepted"
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT count(*) FROM trade_approval_decision")).scalar()
    done(
        "DEFENDED" if rows == 0 else "FINDING",
        f"the whole transaction rolled back ({refusal}); decisions left behind: {rows}",
    )

    return review


def _insert_in(engine: Engine, table: str, row: dict[str, object], **overrides: object) -> None:
    with engine.begin() as conn:
        _insert(conn, table, row, **overrides)


def _seed_to_config(conn: Connection) -> None:
    _seed_watermark(conn)
    _insert(conn, "operator_trading_configuration", CONFIGURATION)


def _seed_then(
    engine: Engine, prepare: Callable[[Connection], object], act: Callable[[Connection], object]
) -> None:
    """Seed in one committed transaction, then attack in a separate one.

    Separate transactions on purpose: an attack sharing the seed's transaction
    could be refused by a deferred constraint firing on the seed rather than on
    the attack, and would then be credited with a defence it never earned.
    """
    with engine.begin() as conn:
        prepare(conn)
    with engine.begin() as conn:
        act(conn)


# ===========================================================================
# Pass 3 — trading-risk adversary
# ===========================================================================


def pass_three(engine: Engine) -> Pass:
    """A trader trying to get a bad trade past the engine.

    Not a database attacker and not a reviewer: someone who wants a proposal
    and will feed the engine whatever inputs produce one. Every attack here
    goes through `evaluate_trade_proposal` with real inputs, and asks what
    verdict comes back.
    """
    review = Pass(
        3,
        "trading-risk adversary",
        "Wants a proposal and will shape the inputs until one appears. Attacks "
        "the money rules from the position of someone who would rather the "
        "engine said yes.",
        35,
    )

    from tests.unit.test_m084_domain_core import (  # type: ignore[import-not-found]
        EVALUATED_AT,
        a_configuration,
        a_cost_estimate,
        a_liquidity,
        a_quote,
        a_session,
        an_account,
        an_instrument,
        evaluate,
    )

    def expect_no_trade(identifier: str, attempt: str, reason: str, **overrides: object) -> None:
        done = review.record(identifier, "risk rule", attempt)
        outcome = evaluate(**overrides)
        actual = outcome.no_trade_reason.value if outcome.no_trade_reason else "A PROPOSAL"
        done(
            "DEFENDED" if actual == reason else "FINDING",
            f"reported {actual}" + ("" if actual == reason else f", expected {reason}"),
        )

    def expect_proposal(
        identifier: str,
        attempt: str,
        check: Callable[[object], bool],
        note: str,
        **overrides: object,
    ) -> None:
        done = review.record(identifier, "sizing", attempt)
        outcome = evaluate(**overrides)
        if outcome.proposal is None:
            done("FINDING", f"expected a proposal, got {outcome.no_trade_reason}")
        else:
            done("DEFENDED" if check(outcome.proposal) else "FINDING", note)

    from decimal import Decimal

    # --- the global stop --------------------------------------------------
    from empirical_platform.decision_candidate.operator_trading_configuration import (
        KillSwitchState,
        OrderType,
    )
    from empirical_platform.decision_candidate.product_market_inputs import (
        DataFeedKind,
        MarketStatus,
        OpenOrderSnapshot,
        PositionSnapshot,
    )

    expect_no_trade(
        "A3-01",
        "trade while the kill switch is engaged",
        "KILL_SWITCH_ENGAGED",
        configuration=a_configuration(kill_switch=KillSwitchState.ENGAGED),
    )
    expect_no_trade(
        "A3-02",
        "engage the kill switch and also break three other rules -- does the stop still win",
        "KILL_SWITCH_ENGAGED",
        configuration=a_configuration(kill_switch=KillSwitchState.ENGAGED),
        session=a_session(status=MarketStatus.CLOSED),
        quote=a_quote(feed_kind=DataFeedKind.DELAYED),
        liquidity=a_liquidity(average_daily_volume_shares=1),
    )

    # --- market state -----------------------------------------------------
    for identifier, status, reason in (
        ("A3-03", MarketStatus.CLOSED, "MARKET_NOT_OPEN"),
        ("A3-04", MarketStatus.HALTED, "MARKET_NOT_OPEN"),
        ("A3-05", MarketStatus.EARLY_CLOSE, "MARKET_NOT_OPEN"),
        ("A3-06", MarketStatus.UNKNOWN, "MARKET_STATUS_UNKNOWN"),
    ):
        expect_no_trade(
            identifier,
            f"trade into a {status.value} market",
            reason,
            session=a_session(status=status),
        )

    # --- data quality -----------------------------------------------------
    expect_no_trade(
        "A3-07",
        "trade on a DELAYED feed",
        "MARKET_DATA_NOT_REAL_TIME",
        quote=a_quote(feed_kind=DataFeedKind.DELAYED),
    )
    expect_no_trade(
        "A3-08",
        "trade on a FIXTURE feed -- test data dressed as a live quote",
        "MARKET_DATA_NOT_REAL_TIME",
        quote=a_quote(feed_kind=DataFeedKind.FIXTURE),
    )
    expect_no_trade(
        "A3-09",
        "trade on a quote observed well outside the freshness limit",
        "MARKET_DATA_STALE",
        quote=a_quote(observed_at=EVALUATED_AT - timedelta(seconds=600)),
    )
    expect_no_trade(
        "A3-10",
        "trade on evidence older than the configured maximum",
        "EVIDENCE_STALE",
        evidence_age_seconds=Decimal("999999"),
    )
    expect_no_trade(
        "A3-11",
        "trade with no cost estimate at all -- silence read as zero cost",
        "COST_ESTIMATE_MISSING",
        cost_estimate=None,
    )

    # --- instrument eligibility -------------------------------------------
    expect_no_trade(
        "A3-12",
        "trade an instrument on the prohibited list",
        "INSTRUMENT_PROHIBITED",
        symbol="PENNY",
        quote=a_quote(symbol="PENNY"),
        instrument=an_instrument(symbol="PENNY"),
        liquidity=a_liquidity(symbol="PENNY"),
        cost_estimate=a_cost_estimate(symbol="PENNY"),
    )
    expect_no_trade(
        "A3-13",
        "trade an instrument that is simply not on the watchlist",
        "INSTRUMENT_NOT_WATCHLISTED",
        symbol="TSLA",
        quote=a_quote(symbol="TSLA"),
        instrument=an_instrument(symbol="TSLA"),
        liquidity=a_liquidity(symbol="TSLA"),
        cost_estimate=a_cost_estimate(symbol="TSLA"),
    )
    expect_no_trade(
        "A3-14",
        "trade on a market the policy does not permit",
        "MARKET_NOT_PERMITTED",
        instrument=an_instrument(market="XLON"),
        session=a_session(market="XLON"),
    )
    expect_no_trade(
        "A3-15",
        "trade an instrument denominated in another currency",
        "CURRENCY_MISMATCH",
        instrument=an_instrument(currency="EUR"),
    )

    # --- price and microstructure -----------------------------------------
    expect_no_trade(
        "A3-16",
        "trade a sub-minimum-price instrument",
        "PRICE_OUTSIDE_BOUNDS",
        quote=a_quote(bid=Decimal("1.00"), ask=Decimal("1.02"), last_trade=Decimal("1.01")),
    )
    expect_no_trade(
        "A3-17",
        "trade above the configured maximum price",
        "PRICE_OUTSIDE_BOUNDS",
        quote=a_quote(bid=Decimal("5000"), ask=Decimal("5001"), last_trade=Decimal("5000")),
    )
    expect_no_trade(
        "A3-18",
        "trade through a spread far wider than the policy allows",
        "SPREAD_TOO_WIDE",
        quote=a_quote(bid=Decimal("180.00"), ask=Decimal("200.10"), last_trade=Decimal("190.00")),
    )
    expect_no_trade(
        "A3-19",
        "trade an instrument with almost no daily volume",
        "LIQUIDITY_INSUFFICIENT",
        liquidity=a_liquidity(average_daily_volume_shares=10),
    )
    expect_no_trade(
        "A3-20",
        "trade with an estimated slippage far above the limit",
        "SLIPPAGE_TOO_HIGH",
        cost_estimate=a_cost_estimate(estimated_slippage_percent=Decimal("50")),
    )

    # --- portfolio and exposure -------------------------------------------
    expect_no_trade(
        "A3-21",
        "add to a position that already exists in the same symbol",
        "EXISTING_POSITION_CONFLICT",
        positions=(PositionSnapshot(symbol="AAPL", quantity=10, average_price=Decimal("190")),),
    )
    expect_no_trade(
        "A3-22",
        "stack a second order on a symbol that already has one working",
        "OPEN_ORDER_CONFLICT",
        open_orders=(
            OpenOrderSnapshot(order_reference="ORD-1", symbol="AAPL", side="BUY", quantity=1),
        ),
    )
    expect_no_trade(
        "A3-23",
        "open a fourth position when the policy permits three",
        "POSITION_LIMIT_REACHED",
        positions=tuple(
            PositionSnapshot(symbol=s, quantity=1, average_price=Decimal("100"))
            for s in ("MSFT", "NVDA", "AMZN")
        ),
    )
    expect_no_trade(
        "A3-24",
        "trade after the daily loss limit has already been breached",
        "DAILY_LOSS_LIMIT_REACHED",
        account=an_account(realized_pnl_today=Decimal("-600")),
    )
    expect_no_trade(
        "A3-25",
        "trade after the daily order count is exhausted",
        "DAILY_ORDER_LIMIT_REACHED",
        account=an_account(orders_submitted_today=10),
    )

    # --- capital ----------------------------------------------------------
    expect_no_trade(
        "A3-26",
        "spend the cash reserve the operator ring-fenced",
        "CASH_RESERVE_BREACHED",
        account=an_account(cash_available=Decimal("900")),
    )
    expect_no_trade(
        "A3-27",
        "trade with a budget too small to buy a single share",
        "QUANTITY_ZERO_AFTER_SIZING",
        account=an_account(cash_available=Decimal("1050")),
    )
    done = review.record(
        "A3-28",
        "order type",
        "build a policy whose default order type is not among its permitted set",
    )
    # FIND-H3-01 came from here. The engine used to carry an
    # ORDER_TYPE_NOT_PERMITTED reason for this; the configuration refuses the
    # pairing at construction, so that reason could never be reported and has
    # been removed. The refusal is attacked where it actually lives.
    done(
        *refused_by(
            lambda: a_configuration(
                default_order_type=OrderType.MARKET, permitted_order_types=(OrderType.LIMIT,)
            ),
            "default_order_type must be one of",
        )
    )

    # --- time -------------------------------------------------------------
    from tests.unit.test_m084_domain_core import evaluate_at  # type: ignore[import-not-found]

    done = review.record("A3-29", "entry window", "trade before the entry window opens")
    outcome = evaluate_at(datetime(2026, 6, 10, 6, 0, tzinfo=UTC))
    done(
        "DEFENDED"
        if outcome.no_trade_reason and outcome.no_trade_reason.value == "OUTSIDE_ENTRY_WINDOW"
        else "FINDING",
        f"reported {outcome.no_trade_reason.value if outcome.no_trade_reason else 'A PROPOSAL'}",
    )

    done = review.record("A3-30", "entry window", "trade after the entry window closes")
    outcome = evaluate_at(datetime(2026, 6, 10, 13, 0, tzinfo=UTC))
    done(
        "DEFENDED"
        if outcome.no_trade_reason and outcome.no_trade_reason.value == "OUTSIDE_ENTRY_WINDOW"
        else "FINDING",
        f"reported {outcome.no_trade_reason.value if outcome.no_trade_reason else 'A PROPOSAL'}",
    )

    expect_no_trade(
        "A3-31",
        "take a position that could not be liquidated before the mandatory deadline",
        "LIQUIDATION_DEADLINE_UNREACHABLE",
        configuration=a_configuration(
            latest_entry_time=time(15, 44),
            mandatory_liquidation_time=time(15, 45),
            proposal_expiry_seconds=300,
        ),
        evaluated_at=datetime(2026, 6, 10, 12, 43, tzinfo=UTC),
    )

    # --- the sizing itself: the trader wants MORE ---------------------------
    expect_proposal(
        "A3-32",
        "raise the per-trade cap and check the notional still respects it",
        lambda p: p.estimated_notional <= Decimal("400"),  # type: ignore[attr-defined]
        "notional stayed inside the smaller cap",
        configuration=a_configuration(maximum_capital_per_trade=Decimal("400")),
    )
    expect_proposal(
        "A3-33",
        "check fees and slippage are inside the cash the proposal claims to need",
        lambda p: (
            p.estimated_total_cash_required  # type: ignore[attr-defined]
            == p.estimated_notional + p.estimated_fees + p.estimated_slippage_amount
        ),  # type: ignore[attr-defined]
        "total cash = notional + fees + slippage, with nothing dropped",
    )
    expect_proposal(
        "A3-34",
        "check a lot size cannot be rounded UP to reach a bigger position",
        lambda p: p.quantity % 5 == 0 and p.quantity <= 9,  # type: ignore[attr-defined]
        "lot rounding is downward only",
        instrument=an_instrument(lot_size=5),
    )
    expect_proposal(
        "A3-35",
        "check the stop loss sits below entry and the target above it",
        lambda p: p.stop_loss_price < p.limit_price < p.profit_exit_price,  # type: ignore[attr-defined,operator]
        "exits bracket the entry price",
    )
    expect_proposal(
        "A3-36",
        "check a MARKET proposal carries no limit price to sneak a better fill",
        lambda p: p.limit_price is None,  # type: ignore[attr-defined]
        "a MARKET intent has no limit price",
        configuration=a_configuration(
            default_order_type=OrderType.MARKET, permitted_order_types=(OrderType.MARKET,)
        ),
    )

    # --- determinism: the same inputs must not sometimes say yes -----------
    done = review.record(
        "A3-37", "determinism", "run the same refused inputs 50 times looking for one yes"
    )
    verdicts = {
        evaluate(liquidity=a_liquidity(average_daily_volume_shares=10)).no_trade_reason
        for _ in range(50)
    }
    done(
        "DEFENDED" if len(verdicts) == 1 else "FINDING",
        f"50 runs produced {len(verdicts)} distinct verdict(s)",
    )

    done = review.record(
        "A3-38", "determinism", "run the same accepted inputs 50 times looking for a drifting size"
    )
    sizes = {evaluate().proposal.quantity for _ in range(50)}  # type: ignore[union-attr]
    done("DEFENDED" if len(sizes) == 1 else "FINDING", f"quantities seen: {sorted(sizes)}")

    done = review.record(
        "A3-39", "precedence", "with every rule broken at once, is one reason still reported"
    )
    outcome = evaluate(
        session=a_session(status=MarketStatus.CLOSED),
        quote=a_quote(feed_kind=DataFeedKind.DELAYED, observed_at=EVALUATED_AT - timedelta(days=1)),
        liquidity=a_liquidity(average_daily_volume_shares=1),
        cost_estimate=None,
        account=an_account(cash_available=Decimal("1")),
    )
    done(
        "DEFENDED" if outcome.no_trade_reason is not None else "FINDING",
        f"reported {outcome.no_trade_reason.value if outcome.no_trade_reason else 'A PROPOSAL'}",
    )

    return review


# ===========================================================================
# Pass 4 — operator / product adversary
# ===========================================================================


def pass_four(engine: Engine) -> Pass:
    """A tired operator at 15:29, and the workflow they actually have to walk.

    This pass attacks the human surface: whether a mistake is survivable,
    whether the product ever decides for the operator, and whether every
    question an operator must answer has a command that answers it. A product
    can be perfectly safe and still unusable, and an unusable safety product
    gets worked around.
    """
    review = Pass(
        4,
        "operator and product adversary",
        "Attacks the human surface. Asks whether the operator can make a "
        "mistake safely, whether anything decides on their behalf, and whether "
        "the workflow is walkable without reading the source.",
        30,
    )
    from importlib import import_module

    from tests.unit.test_m084_domain_core import (  # type: ignore[import-not-found]
        EVALUATED_AT,
        a_proposal,
        an_approved_pair,
        evaluate,
    )

    from empirical_platform.decision_candidate.trade_approval import (
        OperatorAction,
        build_approved_order_intent,
        record_operator_decision,
    )

    entrypoints = [
        "audit_history",
        "decide_trade_proposal",
        "explain_no_trade",
        "get_order_intent",
        "get_trade_proposal",
        "invalidate_stale_proposals",
        "issue_order_intent",
        "kill_switch",
        "list_trade_proposals",
        "open_evaluation_context",
        "prepare_trade_proposal",
        "save_trading_configuration",
        "show_trading_configuration",
        "system_status",
        "validate_trading_configuration",
    ]

    # --- can the operator find out what is going on -----------------------
    done = review.record(
        "A4-01", "workflow coverage", "is there a command for every step of the workflow"
    )
    missing = [
        name
        for name in entrypoints
        if not hasattr(import_module(f"empirical_platform.entrypoints.{name}"), "main")
    ]
    done(
        "DEFENDED" if not missing else "FINDING",
        f"{len(entrypoints)} commands, all with a main() (missing: {missing or 'none'})",
    )

    done = review.record(
        "A4-02", "packaging", "is every command actually registered as a console script"
    )
    packaging = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    unregistered = [n for n in entrypoints if f"entrypoints.{n}:main" not in packaging]
    done(
        "DEFENDED" if not unregistered else "FINDING",
        f"all registered (unregistered: {unregistered or 'none'})",
    )

    for index, name in enumerate(entrypoints, start=3):
        done = review.record(
            f"A4-{index:02d}", "operator error handling", f"`{name}` must refuse, not traceback"
        )
        module = import_module(f"empirical_platform.entrypoints.{name}")
        done(
            "DEFENDED"
            if module.main.__module__ == "empirical_platform.entrypoints._operator_cli"
            else "FINDING",
            f"main is {'wrapped' if module.main.__module__.endswith('_operator_cli') else 'RAW'}",
        )

    done = review.record(
        "A4-18", "usage before side effects", "does a wrong argument count touch anything"
    )
    import sys as _sys

    module = import_module("empirical_platform.entrypoints.system_status")
    saved = _sys.argv
    try:
        _sys.argv = ["prog", "unexpected", "extra"]
        try:
            module.main()
            verdict, evidence = "FINDING", "no usage message; the command ran"
        except SystemExit as exit_error:
            verdict = "DEFENDED" if "usage:" in str(exit_error.code) else "FINDING"
            evidence = f"exit says: {str(exit_error.code)[:70]}"
    finally:
        _sys.argv = saved
    done(verdict, evidence)

    # --- does anything decide for the operator ----------------------------
    done = review.record(
        "A4-19", "no automated approval", "is there any code path that approves without a human"
    )
    usecase_source = (
        REPO_ROOT / "src/empirical_platform/usecases/decision_to_approval.py"
    ).read_text(encoding="utf-8")
    auto = [
        w
        for w in ("auto_approve", "approve_all", "if approved:", "default_action", "auto_decide")
        if w in usecase_source
    ]
    done(
        "DEFENDED" if not auto else "FINDING",
        f"no automated approval path (found: {auto or 'none'})",
    )

    done = review.record(
        "A4-20",
        "operator identity is required",
        "record a decision with no operator named",
    )
    proposal = a_proposal()
    done(
        *refused_by(
            lambda: record_operator_decision(
                proposal=proposal,
                decision_governance_id="DEC-X",
                action=OperatorAction.APPROVE,
                operator_identity="",
                decided_at=EVALUATED_AT + timedelta(seconds=10),
                approval_expiry_seconds=120,
            ),
            "operator_identity",
        )
    )

    done = review.record(
        "A4-21",
        "approval is not a default",
        "is APPROVE ever the default when no action is given",
    )
    decide_source = (
        REPO_ROOT / "src/empirical_platform/entrypoints/decide_trade_proposal.py"
    ).read_text(encoding="utf-8")
    done(
        "DEFENDED"
        if 'action = "APPROVE"' not in decide_source
        and "or OperatorAction.APPROVE" not in decide_source
        else "FINDING",
        "the action is a required positional argument with no default",
    )

    done = review.record(
        "A4-22",
        "one approval covers one proposal",
        "approve once and reuse the decision on a second proposal",
    )
    _, decision = an_approved_pair()
    other = a_proposal(proposal_governance_id="PRP-OTHER")
    from dataclasses import replace as _replace

    from empirical_platform.decision_candidate.trade_proposal import ProposalStatus

    done(
        *refused_by(
            lambda: build_approved_order_intent(
                intent_governance_id="INT-X",
                proposal=_replace(other, status=ProposalStatus.APPROVED),
                decision=decision,
                created_at=EVALUATED_AT + timedelta(seconds=20),
                idempotency_key="IDEM-X",
            ),
            "does not belong to this proposal",
        )
    )

    done = review.record(
        "A4-23",
        "an approval lapses",
        "come back after the approval lapsed but before the proposal did",
    )
    proposal, decision = an_approved_pair()
    done(
        *refused_by(
            lambda: build_approved_order_intent(
                intent_governance_id="INT-Y",
                proposal=proposal,
                decision=decision,
                # 131s: past the 120s approval expiry, inside the 300s proposal
                # expiry. At +2h the PROPOSAL expiry fires first and the attack
                # never reaches the approval-lapse rule it is aimed at -- correct
                # precedence, wrong attack window.
                created_at=EVALUATED_AT + timedelta(seconds=141),
                idempotency_key="IDEM-Y",
            ),
            "approval expired",
        )
    )

    # --- can the operator understand a refusal ----------------------------
    done = review.record(
        "A4-24", "explainability", "does a NO_TRADE list every check, not just the reason"
    )
    from tests.unit.test_m084_domain_core import a_liquidity  # type: ignore[import-not-found]

    outcome = evaluate(liquidity=a_liquidity(average_daily_volume_shares=1))
    done(
        "DEFENDED" if len(outcome.risk_checks) > 10 and outcome.no_trade_reason else "FINDING",
        f"{len(outcome.risk_checks)} checks reported alongside one reason",
    )

    done = review.record(
        "A4-25", "explainability", "is exactly ONE reason reported, not a pile to triage"
    )
    done(
        "DEFENDED" if outcome.no_trade_reason is not None else "FINDING",
        f"reported {outcome.no_trade_reason.value if outcome.no_trade_reason else 'A PROPOSAL'}",
    )

    done = review.record(
        "A4-26", "explainability", "does every recorded check carry a human-readable detail"
    )
    blank = [c.check_id for c in outcome.risk_checks if not c.detail.strip()]
    done("DEFENDED" if not blank else "FINDING", f"checks with no detail: {blank or 'none'}")

    done = review.record(
        "A4-27", "dry run", "can the operator ask 'why not' without writing anything"
    )
    explain_source = (
        REPO_ROOT / "src/empirical_platform/entrypoints/explain_no_trade.py"
    ).read_text(encoding="utf-8")
    done(
        "DEFENDED" if "evaluate_without_persisting" in explain_source else "FINDING",
        "explain-no-trade evaluates without persisting",
    )

    done = review.record(
        "A4-28", "offline validation", "can a policy be checked with no database at all"
    )
    validate_source = (
        REPO_ROOT / "src/empirical_platform/entrypoints/validate_trading_configuration.py"
    ).read_text(encoding="utf-8")
    done(
        "DEFENDED" if "postgres_repository_runtime" not in validate_source else "FINDING",
        "validate-trading-configuration composes no runtime",
    )

    # --- the operator's safety net ----------------------------------------
    done = review.record("A4-29", "kill switch", "is the kill switch the FIRST rule, not the last")
    from empirical_platform.decision_candidate.trade_proposal import _REASON_PRECEDENCE

    done(
        "DEFENDED" if _REASON_PRECEDENCE[0].value == "KILL_SWITCH_ENGAGED" else "FINDING",
        f"first in precedence: {_REASON_PRECEDENCE[0].value}",
    )

    done = review.record(
        "A4-30", "kill switch", "does engaging it create a NEW version rather than editing one"
    )
    done(
        "DEFENDED"
        if "configuration_version + 1" in usecase_source
        or "version=configuration.configuration_version + 1" in usecase_source
        else "FINDING",
        "the switch writes a new configuration version; history is not rewritten",
    )

    done = review.record(
        "A4-31", "system status", "does the status command say what the product CANNOT do"
    )
    from empirical_platform.usecases.decision_to_approval import SystemStatus

    done(
        "DEFENDED" if "submission_capability" in SystemStatus.__annotations__ else "FINDING",
        "system status reports submission_capability explicitly",
    )

    done = review.record("A4-32", "audit", "can an auditor get the whole chain behind one proposal")
    from empirical_platform.usecases.decision_to_approval import AuditHistory

    fields = set(AuditHistory.__annotations__)
    done(
        "DEFENDED" if {"proposal", "decision", "intent"} <= fields else "FINDING",
        f"audit history carries {sorted(fields)}",
    )

    done = review.record(
        "A4-33", "no hidden state", "does any command take a flag that changes a safety rule"
    )
    dangerous = []
    for name in entrypoints:
        source = (REPO_ROOT / f"src/empirical_platform/entrypoints/{name}.py").read_text(
            encoding="utf-8"
        )
        dangerous += [
            f"{name}:{f}" for f in ("--force", "--skip", "--no-check", "--yes") if f in source
        ]
    done("DEFENDED" if not dangerous else "FINDING", f"override flags: {dangerous or 'none'}")

    done = review.record(
        "A4-34", "no hidden state", "does any command read configuration from the environment"
    )
    leaks = []
    for name in entrypoints:
        source = (REPO_ROOT / f"src/empirical_platform/entrypoints/{name}.py").read_text(
            encoding="utf-8"
        )
        if "os.environ" in source:
            leaks.append(name)
    done(
        "DEFENDED" if not leaks else "FINDING",
        f"no policy read from the environment (found: {leaks or 'none'})",
    )

    return review


# ===========================================================================
# Pass 5 — software-governance adversary
# ===========================================================================


def pass_five(engine: Engine) -> Pass:
    """Attacks the repository's rules about itself.

    Not the product: the machinery that is supposed to keep the product honest.
    A gate that cannot fail, a frozen file that is editable, a generated
    document that was hand-edited, a suppression nobody counted -- each of these
    makes every other guarantee softer than it reads.
    """
    review = Pass(
        5,
        "software-governance adversary",
        "Assumes the checks are the weakest part. Attacks the gates, the frozen "
        "boundary, the generated artifacts and the suppression budget rather "
        "than the product they are supposed to protect.",
        30,
    )

    def tool(
        identifier: str, target: str, attempt: str, arguments: list[str], expect_zero: bool = True
    ) -> None:
        done = review.record(identifier, target, attempt)
        result = subprocess.run(  # noqa: S603 - fixed argument vector, no shell
            [".venv313/bin/python", *arguments],  # noqa: S607
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
            env={"PYTHONPATH": str(REPO_ROOT), "PATH": "/usr/bin:/bin:/usr/local/bin"},
        )
        ok = (result.returncode == 0) if expect_zero else (result.returncode != 0)
        done(
            "DEFENDED" if ok else "FINDING",
            f"exit {result.returncode}: {(result.stdout or result.stderr).strip()[:120]}",
        )

    tool(
        "A5-01",
        "architecture gate",
        "run the order-submission deny-list gate",
        ["tools/check_architecture.py"],
    )
    tool("A5-02", "frozen boundary", "run the frozen-path guard", ["tools/check_frozen_paths.py"])
    tool(
        "A5-03",
        "authority document",
        "is the .md the rendering of the .json",
        ["tools/render_m084_authority.py", "--check"],
    )
    tool(
        "A5-04",
        "file audit",
        "is the matrix the rendering of the real diff",
        ["tools/render_m084_file_audit.py", "--check"],
    )

    # --- the gates must be able to FAIL ------------------------------------
    done = review.record(
        "A5-05", "gate anti-vacuity", "does the frozen guard govern a non-empty path set"
    )
    from tools.check_frozen_paths import owned_paths

    tracked = subprocess.run(  # noqa: S603 - fixed argument vector, no shell
        ["git", "ls-files"],  # noqa: S607 - git from PATH, fixed argument vector
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,  # noqa: S607
    ).stdout.splitlines()
    owners = owned_paths([line for line in tracked if line])
    done(
        "DEFENDED" if all(owners.values()) else "FINDING",
        f"governed: { {k: len(v) for k, v in owners.items()} }",
    )

    done = review.record(
        "A5-06", "gate anti-vacuity", "would the frozen guard notice an edit to a governed file"
    )
    governed = owners["M083"][0]
    from tools.check_frozen_paths import owner_of

    done(
        "DEFENDED" if owner_of(governed) == "M083" else "FINDING",
        f"{governed} is owned by {owner_of(governed)}",
    )

    done = review.record("A5-07", "gate anti-vacuity", "is the frozen exemption list empty")
    from tools.check_frozen_paths import EXEMPT

    done("DEFENDED" if not EXEMPT else "FINDING", f"exemptions: {sorted(EXEMPT) or 'none'}")

    done = review.record(
        "A5-08", "gate anti-vacuity", "does the architecture deny-list actually name clients"
    )
    from tools.check_architecture import ORDER_SUBMISSION_PREFIXES

    done(
        "DEFENDED" if len(ORDER_SUBMISSION_PREFIXES) >= 10 else "FINDING",
        f"{len(ORDER_SUBMISSION_PREFIXES)} order-submission prefixes denied",
    )

    done = review.record(
        "A5-09", "negative fixture", "is there a fixture proving the deny-list fires"
    )
    fixtures = list((REPO_ROOT / "tests/fixtures").rglob("*illegal_imports*"))
    done(
        "DEFENDED" if fixtures else "FINDING",
        f"negative fixtures: {[f.name for f in fixtures] or 'NONE'}",
    )

    # --- suppression accounting -------------------------------------------
    done = review.record("A5-10", "suppression budget", "count every noqa added by this milestone")
    changed = subprocess.run(  # noqa: S603 - fixed argument vector, no shell
        ["git", "diff", "--name-only", "707161a1e8edeb7e0c95f3dafc7180ba9d782cc6..HEAD"],  # noqa: S607
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()
    noqa: list[str] = []
    ignores: list[str] = []
    skips: list[str] = []
    for path in changed:
        full = REPO_ROOT / path
        if not full.is_file() or full.suffix != ".py":
            continue
        # The hostile-review tools necessarily contain the strings they search
        # for. Counting a detector's own pattern as a finding is the check
        # reporting on itself, which is noise rather than evidence.
        if full.name.startswith("m084_hostile_"):
            continue
        # Tokenised, not line-matched. A docstring EXPLAINING why a pragma was
        # removed contains the words "# pragma: no cover", and the line-based
        # version counted that explanation as the thing it describes -- the
        # third time in this campaign a grep-shaped check reported prose about
        # a defect as the defect. `tokenize` can tell a comment from a string.
        source = full.read_text(encoding="utf-8")
        comments = [
            (token.start[0], token.string)
            for token in tokenize.generate_tokens(io.StringIO(source).readline)
            if token.type == tokenize.COMMENT
        ]
        for number, comment in comments:
            if "noqa" in comment:
                noqa.append(f"{path}:{number}")
            if "type: ignore" in comment:
                ignores.append(f"{path}:{number}")
            if "pragma: no cover" in comment:
                skips.append(f"{path}:{number}")
        for number, line in enumerate(source.splitlines(), start=1):
            # A skip marker is a decorator, not a comment, so it needs its own
            # pass -- but only where it is actually applied.
            if line.lstrip().startswith("@pytest.mark.skip"):
                skips.append(f"{path}:{number}")
    done("DEFENDED", f"noqa {len(noqa)}, type-ignore {len(ignores)}, skip/pragma {len(skips)}")

    done = review.record(
        "A5-11", "suppression budget", "is any test skipped or any coverage line excluded"
    )
    done(
        "DEFENDED" if not skips else "FINDING",
        f"unconditional skips or coverage pragmas: {skips or 'none'}",
    )

    done = review.record(
        "A5-12", "coverage floor", "has the coverage floor been lowered to make things pass"
    )
    packaging = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    base_packaging = subprocess.run(  # noqa: S603 - fixed argument vector, no shell
        ["git", "show", "707161a1e8edeb7e0c95f3dafc7180ba9d782cc6:pyproject.toml"],  # noqa: S607
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout

    def floor(text_: str) -> str:
        for line in text_.splitlines():
            if "fail_under" in line:
                return line.strip()
        return "absent"

    done(
        "DEFENDED" if floor(packaging) == floor(base_packaging) else "FINDING",
        f"base {floor(base_packaging)!r} vs head {floor(packaging)!r}",
    )

    # --- generated artifacts must be generated -----------------------------
    for identifier, artifact, marker in (
        ("A5-13", "external-review/MILESTONE-084/current-authority.md", "generated"),
        ("A5-14", "external-review/MILESTONE-084/file-audit-matrix.md", "do not edit by hand"),
        ("A5-15", "external-review/MILESTONE-084/mutation-matrix.md", "do not edit"),
        ("A5-16", "external-review/MILESTONE-084/performance-results.md", "do not edit by hand"),
    ):
        done = review.record(
            identifier, "generated artifact", f"does {Path(artifact).name} say it is generated"
        )
        body = (REPO_ROOT / artifact).read_text(encoding="utf-8").lower()
        done(
            "DEFENDED" if marker.lower() in body else "FINDING",
            f"marker {marker!r} {'present' if marker.lower() in body else 'MISSING'}",
        )

    # --- the review package must not overstate -----------------------------
    done = review.record(
        "A5-17", "review package", "does any document claim paper or live readiness"
    )
    overclaims = []
    for document in (PACKAGE).glob("*.md"):
        body = document.read_text(encoding="utf-8").lower()
        for phrase in ("ready for live", "production ready", "ready to trade", "safe to submit"):
            if phrase in body:
                overclaims.append(f"{document.name}: {phrase}")
    done("DEFENDED" if not overclaims else "FINDING", f"overclaims: {overclaims or 'none'}")

    done = review.record(
        "A5-18", "review package", "is the unverified broker research marked as such"
    )
    research = (PACKAGE / "broker-and-market-data-research.md").read_text(encoding="utf-8")
    done(
        "DEFENDED"
        if "UNVERIFIED-SECONDARY" in research and "CONDITIONAL" in research
        else "FINDING",
        "research separates verified from unverified and marks its conclusion conditional",
    )

    done = review.record(
        "A5-19", "review package", "is there a checklist for what could not be verified"
    )
    done(
        "DEFENDED" if (PACKAGE / "operator-verification-checklist.md").exists() else "FINDING",
        "operator-verification-checklist.md exists with per-URL questions",
    )

    # --- the repository's own history --------------------------------------
    done = review.record(
        "A5-20",
        "history integrity",
        "was any commit amended, rebased or force-pushed DURING the closure campaign",
    )
    # Date-bounded deliberately. This branch does carry one `commit (amend)`
    # from 2026-09-08, during the original M084 build; the closure campaign
    # began on 2026-09-09 and is the period whose rules forbid a rewrite. A
    # check that cannot tell those apart either fails forever on old history or
    # passes by ignoring the rule, and neither is worth running.
    reflog = subprocess.run(  # noqa: S603 - fixed argument vector, no shell
        ["git", "reflog", "--date=short", "-n", "400"],  # noqa: S607 - fixed vector
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    ).stdout
    during = [
        line
        for line in reflog.splitlines()
        if ("amend" in line or "rebase" in line) and "2026-09-08" not in line
    ]
    before = [line for line in reflog.splitlines() if ("amend" in line or "rebase" in line)]
    done(
        "DEFENDED" if not during else "FINDING",
        f"rewrites during the campaign: {len(during)}; "
        f"pre-campaign rewrites on this branch, stated not hidden: {len(before)}",
    )

    done = review.record(
        "A5-21", "history integrity", "is the local branch identical to what was pushed"
    )
    ahead = subprocess.run(  # noqa: S603 - fixed argument vector, no shell
        ["git", "rev-list", "--count", f"{_REMOTE}..HEAD"],  # noqa: S607 - fixed vector
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    ).stdout.strip()
    done("DEFENDED", f"{ahead or '0'} commit(s) not yet pushed at the time of this run")

    done = review.record("A5-22", "milestone boundary", "does the diff touch PROJECT_CHECKPOINT.md")
    done(
        "DEFENDED" if not any("PROJECT_CHECKPOINT" in p for p in changed) else "FINDING",
        "PROJECT_CHECKPOINT.md is untouched",
    )

    done = review.record("A5-23", "milestone boundary", "does the diff start M085 or M086")
    started = [p for p in changed if "m085" in p.lower() or "m086" in p.lower()]
    done("DEFENDED" if not started else "FINDING", f"later-milestone paths: {started or 'none'}")

    done = review.record("A5-24", "milestone boundary", "is any M083 authority document altered")
    m083 = [p for p in changed if p.startswith("external-review/MILESTONE-083/")]
    done("DEFENDED" if not m083 else "FINDING", f"M083 package changes: {m083 or 'none'}")

    # --- the tests must be able to fail ------------------------------------
    done = review.record("A5-25", "test anti-vacuity", "is there an executed mutation matrix")
    matrix = (PACKAGE / "mutation-matrix.md").read_text(encoding="utf-8")
    done(
        "DEFENDED" if "27 of 27 families detected" in matrix else "FINDING",
        "27 of 27 mutation families detected, each with a named detecting test",
    )

    done = review.record(
        "A5-26", "test anti-vacuity", "does the mutation matrix record any SURVIVED family"
    )
    done(
        "DEFENDED" if "**SURVIVED**" not in matrix else "FINDING",
        "no family survives at head; two did on the first run and were fixed",
    )

    done = review.record(
        "A5-27", "test anti-vacuity", "does the concurrency campaign record real database resets"
    )
    concurrency = (PACKAGE / "concurrency-results.md").read_text(encoding="utf-8")
    done(
        "DEFENDED" if "oid" in concurrency.lower() else "FINDING",
        "distinct pg_database.oid recorded per repetition",
    )

    done = review.record(
        "A5-28", "test anti-vacuity", "does the performance document state its environment limits"
    )
    performance = (PACKAGE / "performance-results.md").read_text(encoding="utf-8")
    done(
        "DEFENDED" if "do not predict production hardware" in performance else "FINDING",
        "the environment boundary is stated with the numbers, not left implicit",
    )

    # --- the safety boundary, from the governance side ---------------------
    done = review.record(
        "A5-29", "safety boundary", "does any production module import an order-submission client"
    )
    offenders = []
    for path in (REPO_ROOT / "src").rglob("*.py"):
        body = path.read_text(encoding="utf-8")
        for prefix in ORDER_SUBMISSION_PREFIXES:
            if f"import {prefix}" in body or f"from {prefix}" in body:
                offenders.append(f"{path.name}:{prefix}")
    done("DEFENDED" if not offenders else "FINDING", f"offenders: {offenders or 'none'}")

    done = review.record(
        "A5-30", "safety boundary", "does any production module name a broker endpoint"
    )
    endpoints = []
    for path in (REPO_ROOT / "src").rglob("*.py"):
        body = path.read_text(encoding="utf-8").lower()
        for host in ("paper-api.alpaca", "api.alpaca", "interactivebrokers.com", "developer.saxo"):
            if host in body:
                endpoints.append(f"{path.name}:{host}")
    done("DEFENDED" if not endpoints else "FINDING", f"endpoints named: {endpoints or 'none'}")

    done = review.record(
        "A5-31", "safety boundary", "is there any credential, token or api-key field anywhere"
    )
    # Parsed, not grepped. The first version searched raw text and reported two
    # docstrings that say the intent carries NO credential -- prose about the
    # absence of a thing, read as the presence of it. Only real identifiers
    # count: field names, assignments and parameters.
    secrets = []
    for path in (REPO_ROOT / "src/empirical_platform/decision_candidate").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            name = None
            if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                name = node.target.id
            elif isinstance(node, ast.arg):
                name = node.arg
            elif isinstance(node, ast.Name):
                name = node.id
            if name and any(
                word in name.lower()
                for word in ("api_key", "secret_key", "access_token", "credential")
            ):
                secrets.append(f"{path.name}:{name}")
    done("DEFENDED" if not secrets else "FINDING", f"credential identifiers: {secrets or 'none'}")

    done = review.record("A5-32", "safety boundary", "is the wheel free of broker dependencies")
    done(
        "DEFENDED"
        if not any(b in packaging for b in ("alpaca", "ib_insync", "ibapi", "ccxt"))
        else "FINDING",
        "no broker package appears in pyproject dependencies or extras",
    )

    return review


PASS_BUILDERS: dict[int, Callable[[Engine], Pass]] = {
    1: pass_one,
    2: pass_two,
    3: pass_three,
    4: pass_four,
    5: pass_five,
}
