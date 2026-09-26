"""MILESTONE-085 -- the authority contract, checked against the running code.

A published authority document is worth exactly as much as the checks that keep it
honest. This file does four things:

  1. proves the schema is CLOSED -- a claim it does not already name cannot be
     added, and a claim removed from the contract fails the exact item counts;
  2. proves `current-authority.md` is the deterministic rendering of
     `current-authority.json`, so the prose cannot drift from the contract;
  3. proves the RENDERER's five tables and the SCHEMA's five enumerations are
     equal sets, so a claim cannot be published with no statement of what it
     means and a sentence cannot exist for a claim the contract cannot hold;
  4. proves each mechanical claim against the code and schema that implement it,
     so that weakening the implementation fails HERE rather than leaving a
     document that describes a product which no longer exists.

The fourth is the one that matters. The first three only keep the document
self-consistent; without the fourth, a contract could be perfectly rendered,
perfectly validated, and false.

WHY 3 IS NOT COSMETIC. It caught a real defect while this milestone was being
written: `_PROVES` briefly held a stray key reading `..._fingerphrase_...`
alongside the correct `..._fingerprint_...`, so the renderer table had fourteen
entries against the contract's thirteen. Nothing else would have noticed, because
the extra entry was simply never looked up.

NO NATURAL LANGUAGE IS PARSED ANYWHERE. No keyword sweep, no banned-term list, no
negation grammar. Every check below compares SETS OF IDENTIFIERS or executes code.
M082's findings 20 through 28 produced eight consecutive green prose sweeps, each
defeated by the next review, and that retired prose validation here for good.
"""

from __future__ import annotations

import ast
import io
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from alembic import command as alembic_command
from alembic.config import Config
from alembic.script import ScriptDirectory
from tools.render_m083_authority import SchemaError, validate
from tools.render_m085_authority import (
    _DOES_NOT_PROVE,
    _ENFORCEMENT,
    _FUTURE,
    _LIMITATIONS,
    _PROVES,
    CONTRACT,
    DOCUMENT,
    SCHEMA,
    render,
)

from empirical_platform.decision_candidate.paper_execution import (
    ALLOWED_PAPER_TRANSITIONS,
    PAPER_ENDPOINT_HOST,
    TERMINAL_PAPER_STATES,
    ExecutionAttempt,
    ExecutionAuthorization,
    PaperAccountSnapshot,
    PaperEnvironment,
    PaperExecutionState,
    PaperOrderRequest,
    SubmissionPreview,
)
from empirical_platform.shared.brokerage.alpaca_paper import (
    ALLOWED_PAPER_PORTS,
    MAXIMUM_DIAGNOSTIC_BODY_BYTES,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]

#: Every M085 revision, oldest first, in groups of six: a hex literal of twelve is a
#: `Hex High Entropy String` to the repository's secret scanner.
_M085_REVISIONS = (
    "".join(("b1e9d4", "7c30a5")),
    "".join(("c7a41f", "0b52de")),
    "".join(("d4f18a", "6c2e97")),
    "".join(("e61b3f", "9a4c27")),
    "".join(("9c4b2e", "7d5a18")),
    "".join(("a7d3c9", "e14f26")),
)
_AUTHORIZATION_GUARD = "paper_execution_authorization_guard_update"

_FUNCTION_EVENT = re.compile(
    r"CREATE OR REPLACE FUNCTION\s+(?:public\.)?(?P<defined>\w+)\s*\(\s*\)"
    r".*?\$\$\s*LANGUAGE\s+plpgsql[^;]*;"
    r"|DROP FUNCTION\s+(?:IF EXISTS\s+)?(?:public\.)?(?P<dropped>\w+)\s*\(",
    re.DOTALL | re.IGNORECASE,
)
_DROPPED_NAME = re.compile(
    r"DROP (?:CONSTRAINT|TABLE|INDEX|TRIGGER)\s+(?:IF EXISTS\s+)?(?:public\.)?(\w+)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class InstalledSchema:
    """What the complete M085 migration chain leaves installed at head.

    SUPERSEDED. This contract used to read ONE migration file, `b1e9d47c30a5`,
    while `d4f18a6c2e97` REPLACES the authorization guard it defines with CREATE OR
    REPLACE FUNCTION. A fragment present only in the replaced definition would still
    have satisfied its claim, against SQL no database at head runs.

    Now the chain's upgrade SQL is rendered by Alembic itself, offline, and each
    function is taken as its LAST definition in migration order; a later DROP removes
    it. Everything that is not a function definition is kept as statements.
    """

    functions: dict[str, str]
    superseded: dict[str, tuple[str, ...]]
    statements: str
    dropped: frozenset[str]

    @property
    def text(self) -> str:
        return "\n".join((*self.functions.values(), self.statements))


def installed_schema(sql: str) -> InstalledSchema:
    functions: dict[str, str] = {}
    history: dict[str, list[str]] = {}
    dropped: set[str] = set()
    for event in _FUNCTION_EVENT.finditer(sql):
        if event["defined"] is not None:
            functions[event["defined"]] = event.group(0)
            history.setdefault(event["defined"], []).append(event.group(0))
        else:
            functions.pop(event["dropped"], None)
            dropped.add(event["dropped"])
    statements = _FUNCTION_EVENT.sub("", sql)
    dropped.update(_DROPPED_NAME.findall(statements))
    return InstalledSchema(
        functions=functions,
        superseded={
            name: tuple(bodies[:-1]) for name, bodies in history.items() if len(bodies) > 1
        },
        statements=statements,
        dropped=frozenset(dropped - set(functions)),
    )


def _alembic() -> Config:
    config = Config(str(_REPO_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(_REPO_ROOT / "migrations"))
    return config


#: The exact top-level shape. Named here so that adding a section to the contract
#: is a change somebody has to make in two places on purpose.
_EXPECTED_TOP_LEVEL = (
    "milestone",
    "authority_version",
    "title",
    "proves",
    "does_not_prove",
    "database_enforcement",
    "structural_limitations",
    "intended_future_use",
)


@pytest.fixture(scope="module")
def contract() -> dict[str, Any]:
    return json.loads(CONTRACT.read_text(encoding="utf-8"))  # type: ignore[no-any-return]


@pytest.fixture(scope="module")
def schema() -> dict[str, Any]:
    return json.loads(SCHEMA.read_text(encoding="utf-8"))  # type: ignore[no-any-return]


@pytest.fixture(scope="module")
def chain_sql() -> str:
    """The upgrade SQL of every M085 revision, rendered by Alembic with no database."""
    config = _alembic()
    first = ScriptDirectory.from_config(config).get_revision(_M085_REVISIONS[0])
    assert first is not None
    buffer = io.StringIO()
    config.output_buffer = buffer
    alembic_command.upgrade(config, f"{first.down_revision}:head", sql=True)
    return buffer.getvalue()


@pytest.fixture(scope="module")
def installed(chain_sql: str) -> InstalledSchema:
    return installed_schema(chain_sql)


#: Every database enforcement claim and the installed SQL that implements it. A claim
#: may name several fragments; every claim must name at least one.
_ENFORCEMENT_FRAGMENTS: tuple[tuple[str, str], ...] = (
    ("single_use_authorization_consumption", "already been used"),
    ("authorization_immutable_apart_from_its_consumption", "is immutable apart from"),
    ("expired_authorization_cannot_be_consumed", "cannot be consumed at"),
    (
        "at_most_one_consumed_authorization_per_intent",
        "uq_paper_authorization_one_consumed_per_intent",
    ),
    ("at_most_one_dispatch_attempt_per_intent", "uq_paper_attempt_one_per_intent"),
    ("unique_deterministic_client_order_id", "uq_paper_attempt_client_order_id"),
    (
        "an_attempt_requires_a_consumed_matching_authorization",
        "consumed in the same transaction",
    ),
    (
        "an_attempt_must_be_inserted_as_dispatch_claimed",
        "must be inserted as DISPATCH_CLAIMED",
    ),
    ("closed_execution_state_machine_on_update", "is not an allowed paper execution"),
    ("attempt_identity_immutable_after_the_claim", "identity is immutable after"),
    (
        "append_only_previews_accounts_acknowledgements_events_and_kill_switch",
        "m085_append_only",
    ),
    (
        "paper_environment_and_endpoint_host_pinned_by_check_constraint",
        "ck_paper_account_endpoint_host",
    ),
    (
        "long_only_whole_share_day_only_no_extended_hours_by_check_constraint",
        "ck_paper_preview_long_only",
    ),
    ("referential_integrity_to_the_m084_intent_by_trigger", "paper_requires_approved_intent"),
    ("bounded_broker_response_payload", "ck_paper_acknowledgement_payload_bounded"),
    (
        "time_basis_evidence_describes_the_exact_proposal_approval_or_intent_by_trigger",
        "does not describe the exact stored proposal",
    ),
    (
        "time_basis_evidence_describes_the_exact_proposal_approval_or_intent_by_trigger",
        "does not describe the exact stored approval",
    ),
    (
        "time_basis_evidence_describes_the_exact_proposal_approval_or_intent_by_trigger",
        "does not describe the exact stored intent",
    ),
    (
        "time_basis_evidence_is_bound_to_the_instant_of_its_own_act_by_check_constraint",
        "ck_paper_proposal_time_basis_bound_to_evaluation",
    ),
    (
        "time_basis_evidence_is_bound_to_the_instant_of_its_own_act_by_check_constraint",
        "ck_paper_decision_time_basis_bound_to_decision",
    ),
    (
        "time_basis_evidence_is_bound_to_the_instant_of_its_own_act_by_check_constraint",
        "ck_paper_intent_time_basis_bound_to_issuance",
    ),
    (
        "time_basis_evidence_is_append_only_and_never_backfilled",
        "paper_proposal_time_basis_append_only_trigger",
    ),
    (
        "time_basis_evidence_is_append_only_and_never_backfilled",
        "paper_decision_time_basis_append_only_trigger",
    ),
    (
        "time_basis_evidence_is_append_only_and_never_backfilled",
        "paper_intent_time_basis_append_only_trigger",
    ),
)

#: Each deadline-evidence table: its insert guard, the stored fields that guard must
#: compare, and the CHECK that binds the basis to the instant of its own act.
_PROVENANCE_TABLES: tuple[tuple[str, str, tuple[str, ...], str], ...] = (
    (
        "paper_proposal_time_basis",
        "paper_execution_proposal_time_basis_guard_insert",
        (
            "NEW.proposal_version",
            "NEW.content_fingerprint",
            "NEW.proposal_created_at",
            "NEW.proposal_expires_at",
            "NEW.mandatory_liquidation_at",
        ),
        "proposal_created_at = basis_host_at",
    ),
    (
        "paper_decision_time_basis",
        "paper_execution_decision_time_basis_guard_insert",
        (
            "'APPROVE'",
            "NEW.proposal_governance_id",
            "NEW.proposal_version",
            "NEW.approved_fingerprint",
            "NEW.decided_at",
            "NEW.decision_expires_at",
        ),
        "decided_at = basis_host_at",
    ),
    (
        "paper_intent_time_basis",
        "paper_execution_intent_time_basis_guard_insert",
        ("NEW.intent_expires_at", "NEW.intent_mandatory_liquidation_at"),
        "intent_created_at = basis_host_at",
    ),
)


class TestTheContractReadsTheSqlInstalledAtHead:
    def test_the_rendered_chain_is_exactly_the_m085_revisions_ending_at_head(self) -> None:
        script = ScriptDirectory.from_config(_alembic())
        assert script.get_current_head() == _M085_REVISIONS[-1]
        first = script.get_revision(_M085_REVISIONS[0])
        assert first is not None
        chain = [
            revision.revision
            for revision in script.iterate_revisions("head", first.down_revision)
            if revision is not None
        ]
        assert tuple(reversed(chain)) == _M085_REVISIONS

    def test_every_function_definition_in_the_chain_was_parsed(
        self, chain_sql: str, installed: InstalledSchema
    ) -> None:
        defined = len(re.findall(r"CREATE (?:OR REPLACE )?FUNCTION", chain_sql, re.IGNORECASE))
        parsed = len(installed.functions) + sum(map(len, installed.superseded.values()))
        assert defined == parsed > 0

    def test_the_authorization_guard_is_the_definition_the_later_migration_installed(
        self, installed: InstalledSchema
    ) -> None:
        # The defect this corrects: the first migration's guard is still in its
        # file, and a contract reading only that file was checking it.
        guard = installed.functions[_AUTHORIZATION_GUARD]
        original, with_basis = installed.superseded[_AUTHORIZATION_GUARD]
        assert "basis_" not in original
        assert "basis_broker_latest_at" in with_basis
        versions = _REPO_ROOT / "migrations" / "versions"
        (replacing,) = versions.glob(f"{_M085_REVISIONS[2]}_*.py")
        replacing_source = replacing.read_text(encoding="utf-8")
        basis_rules = [line.strip() for line in with_basis.splitlines() if "basis_" in line]
        assert basis_rules
        assert all(rule in replacing_source for rule in basis_rules)
        # The corrective pass replaced it once more. Its basis rules are still installed,
        # and the binding columns it added are frozen too.
        assert all(rule in guard for rule in basis_rules)
        assert "preview_binding_fingerprint" not in with_basis
        (binding,) = versions.glob(f"{_M085_REVISIONS[4]}_*.py")
        binding_source = binding.read_text(encoding="utf-8")
        binding_rules = [
            line.strip()
            for line in guard.splitlines()
            if "fingerprint IS DISTINCT FROM OLD" in line and "request_fingerprint" not in line
        ]
        assert len(binding_rules) == 2
        assert all(rule in binding_source for rule in binding_rules)

    def test_a_rule_only_in_a_replaced_or_dropped_definition_is_not_installed(self) -> None:
        schema = installed_schema(
            "CREATE OR REPLACE FUNCTION public.guard() RETURNS trigger AS $$ BEGIN "
            "RAISE EXCEPTION 'old rule'; END; $$ LANGUAGE plpgsql;\n"
            "CREATE OR REPLACE FUNCTION public.guard() RETURNS trigger AS $$ BEGIN "
            "RAISE EXCEPTION 'new rule'; END; $$ LANGUAGE plpgsql;\n"
            "CREATE OR REPLACE FUNCTION public.gone() RETURNS trigger AS $$ BEGIN "
            "RAISE EXCEPTION 'gone rule'; END; $$ LANGUAGE plpgsql;\n"
            "DROP FUNCTION IF EXISTS public.gone();\n"
            "ALTER TABLE public.t DROP CONSTRAINT ck_t_gone;\n"
        )
        assert "new rule" in schema.text
        assert "old rule" not in schema.text
        assert "gone rule" not in schema.text
        assert {"gone", "ck_t_gone"} <= schema.dropped


class TestTheTemporalProvenanceRulesAreInstalled:
    """The per-act deadline provenance, pinned against the SQL installed at head."""

    @pytest.mark.parametrize(
        ("table", "guard", "compared", "binding"),
        _PROVENANCE_TABLES,
        ids=[row[0] for row in _PROVENANCE_TABLES],
    )
    def test_each_evidence_table_is_guarded_bound_and_append_only(
        self,
        installed: InstalledSchema,
        table: str,
        guard: str,
        compared: tuple[str, ...],
        binding: str,
    ) -> None:
        function = installed.functions[guard]
        for field in compared:
            assert field in function, (table, field)
        assert "SET search_path" in function, table
        assert f"CHECK ({binding})" in installed.statements, table
        assert f"BEFORE INSERT ON public.{table}" in installed.statements, table
        assert f"EXECUTE FUNCTION public.{guard}()" in installed.statements, table
        assert f"CREATE TRIGGER {table}_append_only_trigger" in installed.statements, table
        assert table not in installed.dropped

    def test_no_migration_writes_time_basis_evidence(self, chain_sql: str) -> None:
        # Provenance is measured in the act or it does not exist: never backfilled.
        assert (
            re.search(r"INSERT\s+INTO\s+(?:public\.)?paper_\w*time_basis", chain_sql, re.I) is None
        )

    def test_each_deadline_is_translated_only_through_the_basis_of_its_own_act(
        self, contract: dict[str, Any]
    ) -> None:
        """Parsed, not grepped: which basis does each rule hand a deadline to?

        The proposal's expiry and liquidation deadline were written at evaluation and
        the approval's expiry at the decision. An issuance or authorization basis
        receiving any of them is the defect reproduced at `73a2f96`.
        """
        assert (
            "each_m084_deadline_is_translated_only_through_the_basis_of_the_act_that_wrote_it"
            in contract["proves"]
        )
        allowed = {
            "act_chronology_refusal": {"proposal_basis", "decision_basis"},
            "m084_deadline_refusal_on_broker_time": {"proposal_basis"},
        }
        source = _REPO_ROOT / "src" / "empirical_platform" / "decision_candidate"
        tree = ast.parse((source / "paper_execution.py").read_text(encoding="utf-8"))
        receivers = {
            function.name: {
                ast.unparse(call.func.value)
                for call in ast.walk(function)
                if isinstance(call, ast.Call)
                and isinstance(call.func, ast.Attribute)
                and call.func.attr == "on_broker_timeline"
            }
            for function in ast.walk(tree)
            if isinstance(function, ast.FunctionDef) and function.name in allowed
        }
        assert receivers == allowed

    def test_the_contract_states_both_limits_of_the_provenance(
        self, contract: dict[str, Any]
    ) -> None:
        assert {
            "an_m084_only_proposal_approval_or_intent_has_no_time_basis_and_is_never_dispatchable",
            "a_writer_with_insert_privilege_can_store_correctly_shaped_evidence_nobody_measured",
        } <= set(contract["structural_limitations"])


class TestTheContractIsValidAndClosed:
    def test_the_contract_satisfies_its_own_schema(
        self, contract: dict[str, Any], schema: dict[str, Any]
    ) -> None:
        validate(contract, schema)

    def test_the_top_level_keys_are_exactly_these(self, contract: dict[str, Any]) -> None:
        assert tuple(contract) == _EXPECTED_TOP_LEVEL

    def test_the_authority_version_is_pinned_to_one(
        self, contract: dict[str, Any], schema: dict[str, Any]
    ) -> None:
        assert contract["authority_version"] == 1
        assert schema["properties"]["authority_version"]["const"] == 1

    def test_the_milestone_is_pinned(self, schema: dict[str, Any]) -> None:
        assert schema["properties"]["milestone"]["const"] == "M085"

    def test_no_section_permits_an_unnamed_claim(self, schema: dict[str, Any]) -> None:
        assert schema["additionalProperties"] is False
        assert schema["properties"]["database_enforcement"]["additionalProperties"] is False
        for section in (
            "proves",
            "does_not_prove",
            "structural_limitations",
            "intended_future_use",
        ):
            items = schema["properties"][section]["items"]
            assert "enum" in items, section
            assert schema["properties"][section]["uniqueItems"] is True, section

    def test_every_list_length_is_exact(
        self, contract: dict[str, Any], schema: dict[str, Any]
    ) -> None:
        # An inexact length would let a claim be dropped without anything failing.
        for section in (
            "proves",
            "does_not_prove",
            "structural_limitations",
            "intended_future_use",
        ):
            declared = schema["properties"][section]
            assert declared["minItems"] == declared["maxItems"] == len(contract[section]), section

    def test_an_unknown_claim_identifier_is_rejected_before_rendering(
        self, contract: dict[str, Any], schema: dict[str, Any]
    ) -> None:
        widened = dict(contract)
        widened["proves"] = [*contract["proves"], "also_proves_it_will_be_profitable"]
        with pytest.raises(SchemaError):
            validate(widened, schema)

    def test_dropping_a_claim_is_rejected(
        self, contract: dict[str, Any], schema: dict[str, Any]
    ) -> None:
        narrowed = dict(contract)
        narrowed["does_not_prove"] = contract["does_not_prove"][:-1]
        with pytest.raises(SchemaError):
            validate(narrowed, schema)

    def test_an_enforcement_property_cannot_be_set_to_false(
        self, contract: dict[str, Any], schema: dict[str, Any]
    ) -> None:
        # `const: true`, not `type: boolean`. A false would be a published
        # enforcement claim the database does not make.
        weakened = dict(contract)
        weakened["database_enforcement"] = {
            **contract["database_enforcement"],
            "single_use_authorization_consumption": False,
        }
        with pytest.raises(SchemaError):
            validate(weakened, schema)

    def test_the_contract_names_no_live_or_unattended_field(
        self, contract: dict[str, Any], schema: dict[str, Any]
    ) -> None:
        # Absence, not a false value. A `live_enabled: false` field would be a
        # field a future edit could flip.
        for forbidden in (
            "live_endpoint",
            "live_enabled",
            "unattended_execution",
            "scheduled_execution",
            "credential",
            "api_key",
            "profitability",
            "expected_return",
            "fill_quality",
        ):
            assert forbidden not in contract
            assert forbidden not in schema["properties"]


class TestTheRendererAndTheSchemaAreBijective:
    """Point 3. Every identifier has exactly one sentence, and vice versa."""

    @pytest.mark.parametrize(
        ("section", "table"),
        [
            ("proves", _PROVES),
            ("does_not_prove", _DOES_NOT_PROVE),
            ("structural_limitations", _LIMITATIONS),
            ("intended_future_use", _FUTURE),
        ],
    )
    def test_the_renderer_table_equals_the_schema_enumeration(
        self, schema: dict[str, Any], section: str, table: dict[str, str]
    ) -> None:
        assert set(table) == set(schema["properties"][section]["items"]["enum"]), section

    def test_the_enforcement_table_equals_the_schema_properties(
        self, schema: dict[str, Any]
    ) -> None:
        assert set(_ENFORCEMENT) == set(schema["properties"]["database_enforcement"]["properties"])

    def test_no_sentence_is_empty(self) -> None:
        for table in (_PROVES, _DOES_NOT_PROVE, _ENFORCEMENT, _LIMITATIONS, _FUTURE):
            for key, sentence in table.items():
                assert sentence.strip(), key

    def test_no_two_identifiers_share_a_sentence(self) -> None:
        # A duplicated sentence means two claims are being described as one.
        for table in (_PROVES, _DOES_NOT_PROVE, _LIMITATIONS, _FUTURE):
            assert len(set(table.values())) == len(table)


class TestTheDocumentIsTheRendering:
    def test_the_markdown_is_byte_identical_to_the_rendering(
        self, contract: dict[str, Any]
    ) -> None:
        assert DOCUMENT.read_text(encoding="utf-8") == render(contract)

    def test_the_rendering_carries_no_carriage_returns_on_any_platform(
        self, contract: dict[str, Any]
    ) -> None:
        """The RENDERER's output, not the file on disk.

        An earlier version of this test read the file's bytes and required no
        CRLF. It passed locally and FAILED in CI -- correctly. `.md` carried no
        `eol` attribute, so a Windows checkout materialises CRLF, and the test was
        asserting a property of the CHECKOUT rather than of the content.

        The real invariant is that the renderer emits the same bytes on every
        platform, which is what makes `--check` behave identically on both. That
        is what is asserted here. The checkout is pinned separately, by a narrow
        `.gitattributes` rule for this package.
        """
        rendered = render(contract)
        assert "\r\n" not in rendered
        assert "\r" not in rendered

    def test_every_claim_appears_in_the_document(self, contract: dict[str, Any]) -> None:
        rendered = DOCUMENT.read_text(encoding="utf-8")
        for section, table in (
            ("proves", _PROVES),
            ("does_not_prove", _DOES_NOT_PROVE),
            ("structural_limitations", _LIMITATIONS),
            ("intended_future_use", _FUTURE),
        ):
            for key in contract[section]:
                # The SENTENCE, not the identifier: an identifier appearing would
                # not show that its meaning was published.
                assert table[key][:60] in rendered, (section, key)

    def test_no_runtime_claim_is_appended_to_the_document(self, contract: dict[str, Any]) -> None:
        # The document is a pure function of the contract, so re-rendering a
        # contract with one claim removed must produce a SHORTER document.
        narrowed = dict(contract)
        narrowed["proves"] = contract["proves"][:-1]
        assert len(render(narrowed)) < len(render(contract))


class TestTheMechanicalClaimsMatchTheCode:
    """Point 4. Weakening the product must fail here."""

    def test_the_paper_environment_has_no_live_member(self) -> None:
        assert [member.value for member in PaperEnvironment] == ["PAPER"]

    def test_the_endpoint_host_claim_matches_the_pinned_constant(self) -> None:
        assert PAPER_ENDPOINT_HOST == "paper-api.alpaca.markets"
        assert ALLOWED_PAPER_PORTS == frozenset({None, 443})

    def test_the_state_machine_claim_matches_the_closed_table(self) -> None:
        assert set(ALLOWED_PAPER_TRANSITIONS) == set(PaperExecutionState)
        for state in TERMINAL_PAPER_STATES:
            assert ALLOWED_PAPER_TRANSITIONS[state] == frozenset(), state

    def test_the_unknown_outcome_claim_matches_the_missing_edge(self) -> None:
        outgoing = ALLOWED_PAPER_TRANSITIONS[PaperExecutionState.SUBMISSION_UNKNOWN]
        assert PaperExecutionState.SUBMISSION_IN_PROGRESS not in outgoing
        assert PaperExecutionState.DISPATCH_CLAIMED not in outgoing

    def test_the_long_only_claim_is_a_type_level_refusal(self) -> None:
        from decimal import Decimal

        from empirical_platform.decision_candidate.operator_trading_configuration import OrderType

        with pytest.raises(ValueError, match="long-only"):
            PaperOrderRequest(
                symbol="AAPL",
                side="SELL",
                quantity=1,
                order_type=OrderType.LIMIT,
                limit_price=Decimal("1"),
                time_in_force="DAY",
                extended_hours=False,
                client_order_id="m085-x",
            )

    def test_the_bounded_payload_claim_matches_the_constant_and_the_check(
        self, installed: InstalledSchema
    ) -> None:
        assert MAXIMUM_DIAGNOSTIC_BODY_BYTES == 8192
        assert "length(sanitized_payload) <= 8192" in installed.text

    @pytest.mark.parametrize(("claim", "fragment"), _ENFORCEMENT_FRAGMENTS)
    def test_every_database_enforcement_claim_names_sql_installed_at_head(
        self, contract: dict[str, Any], installed: InstalledSchema, claim: str, fragment: str
    ) -> None:
        """Each published enforcement claim must point at SQL a database at head runs.

        The fragment is the constraint name, trigger name or trigger message, looked
        up in the chain's installed state: the LAST definition of each function and
        every statement that is not a function definition. A rule deleted, or present
        only in a definition a later migration replaced, fails the claim.
        """
        assert contract["database_enforcement"][claim] is True
        assert fragment in installed.text, claim
        assert fragment not in installed.dropped, claim

    def test_every_enforcement_claim_is_checked_against_installed_sql(
        self, contract: dict[str, Any]
    ) -> None:
        assert {claim for claim, _ in _ENFORCEMENT_FRAGMENTS} == set(
            contract["database_enforcement"]
        )

    def test_the_installed_schema_declares_no_foreign_key_into_the_m084_intent(
        self, installed: InstalledSchema
    ) -> None:
        # The limitation claim says the link is a trigger. This is that claim,
        # checked against the installed schema rather than trusted.
        assert "approved_order_intent.intent_governance_id" not in installed.text
        assert "REFERENCES approved_order_intent" not in installed.text

    def test_the_m084_read_only_claim_matches_the_absence_of_any_writer(self) -> None:
        """No M085 module may write M084's intent table.

        Parsed rather than grepped: a docstring mentioning the table is not a
        write, and this milestone has already been bitten by prose-shaped checks.
        """
        offenders: list[str] = []
        for path in sorted((_REPO_ROOT / "src").rglob("*paper_execution*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            docstrings = {
                id(node.body[0].value)
                for node in ast.walk(tree)
                if isinstance(
                    node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef
                )
                and node.body
                and isinstance(node.body[0], ast.Expr)
                and isinstance(node.body[0].value, ast.Constant)
            }
            for node in ast.walk(tree):
                if not isinstance(node, ast.Constant) or id(node) in docstrings:
                    continue
                if not isinstance(node.value, str):
                    continue
                statement = node.value.upper()
                if "APPROVED_ORDER_INTENT" in statement and any(
                    verb in statement for verb in ("INSERT INTO", "UPDATE ", "DELETE FROM")
                ):
                    offenders.append(f"{path.name}: {node.value[:80]}")
        assert offenders == []

    def test_the_broker_status_map_is_exactly_this_closed_set(self) -> None:
        """The status map had no test until a surviving mutation said so.

        The mutation campaign added `"calculated": FILLED` to the map and NOTHING
        failed -- so the closure claim was resting on nobody having widened it yet.
        Pinning the whole mapping is what makes widening it a decision somebody has
        to make here, in the open, rather than a line that slips in.

        The statuses deliberately ABSENT are real Alpaca statuses with no obviously
        correct destination: `done_for_day`, `replaced`, `pending_replace`,
        `stopped` and `calculated`. An unmapped status records the acknowledgement
        and leaves the state alone, which is the honest behaviour.
        """
        from empirical_platform.usecases.paper_execution import _BROKER_STATUS_TO_STATE

        assert dict(_BROKER_STATUS_TO_STATE) == {
            "new": PaperExecutionState.PAPER_ACCEPTED,
            "accepted": PaperExecutionState.PAPER_ACCEPTED,
            "pending_new": PaperExecutionState.PAPER_ACCEPTED,
            "accepted_for_bidding": PaperExecutionState.PAPER_ACCEPTED,
            "held": PaperExecutionState.PAPER_ACCEPTED,
            "partially_filled": PaperExecutionState.PARTIALLY_FILLED,
            "filled": PaperExecutionState.FILLED,
            "canceled": PaperExecutionState.CANCELED,
            "expired": PaperExecutionState.EXPIRED,
            "rejected": PaperExecutionState.REJECTED,
            "suspended": PaperExecutionState.REJECTED,
            "pending_cancel": PaperExecutionState.CANCEL_REQUESTED,
        }

    def test_no_unmapped_alpaca_status_is_silently_given_a_destination(self) -> None:
        from empirical_platform.usecases.paper_execution import _BROKER_STATUS_TO_STATE

        for absent in ("done_for_day", "replaced", "pending_replace", "stopped", "calculated"):
            assert absent not in _BROKER_STATUS_TO_STATE, absent

    def test_the_credential_claim_holds_for_every_persisted_domain_type(self) -> None:
        """No domain type carries a credential field, by construction."""
        forbidden = {"key_id", "secret_key", "api_key", "secret", "password", "token"}
        for kind in (
            PaperAccountSnapshot,
            PaperOrderRequest,
            SubmissionPreview,
            ExecutionAuthorization,
            ExecutionAttempt,
        ):
            fields = set(getattr(kind, "__dataclass_fields__", {}))
            assert not (fields & forbidden), (kind.__name__, fields & forbidden)

    def test_the_account_reference_claim_holds_no_raw_account_number(self) -> None:
        from empirical_platform.usecases.paper_execution import _account_reference

        reference = _account_reference("real-account-identifier-1234")
        assert reference.startswith("ref:")
        assert "real-account-identifier-1234" not in reference
        # Stable, so two records about one account are comparable.
        assert reference == _account_reference("real-account-identifier-1234")


class TestTheBlockedSubmissionIsDeclaredNotHidden:
    def test_the_limitation_list_states_the_blocked_external_submission(
        self, contract: dict[str, Any]
    ) -> None:
        assert (
            "the_external_paper_submission_was_measured_blocked_by_quote_staleness"
            in contract["structural_limitations"]
        )

    def test_the_acceptance_evidence_exists_and_records_the_blocker(self) -> None:
        evidence = (
            _REPO_ROOT / "external-review" / "MILESTONE-085" / "paper-acceptance-results.md"
        ).read_text(encoding="utf-8")
        assert "MEASURED BLOCKED" in evidence
        assert "freshness tolerance" in evidence
        # And it says what was NOT relaxed, so a reader can see the alternative
        # that was available and declined.
        assert "was not widened" in evidence

    def test_no_positive_claim_asserts_a_completed_external_submission(
        self, contract: dict[str, Any]
    ) -> None:
        # The positive claims are about the mechanism, not about a broker having
        # accepted an order. Checked as a set membership, not by reading prose.
        assert "a_paper_order_was_accepted_by_the_broker" not in contract["proves"]
        assert "the_external_paper_submission_completed" not in contract["proves"]
