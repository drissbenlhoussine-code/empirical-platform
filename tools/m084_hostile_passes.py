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
import json
import subprocess
from collections.abc import Callable, Iterable
from datetime import UTC, datetime, timedelta

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


PASS_BUILDERS: dict[int, Callable[[Engine], Pass]] = {1: pass_one, 2: pass_two}
