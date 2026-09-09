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
import json
from pathlib import Path
from typing import Any

import pytest
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
_MIGRATION = (
    _REPO_ROOT / "migrations" / "versions" / "b1e9d47c30a5_create_m085_paper_execution_schema.py"
)

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
def migration_source() -> str:
    return _MIGRATION.read_text(encoding="utf-8")


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

    def test_the_document_is_stored_with_lf_endings(self) -> None:
        # So the rendering is the same bytes on Windows and on POSIX and `--check`
        # cannot pass on one platform and fail on the other.
        raw = DOCUMENT.read_bytes()
        assert b"\r\n" not in raw

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
        self, migration_source: str
    ) -> None:
        assert MAXIMUM_DIAGNOSTIC_BODY_BYTES == 8192
        assert "length(sanitized_payload) <= 8192" in migration_source

    @pytest.mark.parametrize(
        ("claim", "fragment"),
        [
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
            (
                "referential_integrity_to_the_m084_intent_by_trigger",
                "paper_requires_approved_intent",
            ),
            ("bounded_broker_response_payload", "ck_paper_acknowledgement_payload_bounded"),
        ],
    )
    def test_every_database_enforcement_claim_names_something_in_the_migration(
        self, contract: dict[str, Any], migration_source: str, claim: str, fragment: str
    ) -> None:
        """Each published enforcement claim must point at real installed SQL.

        The fragment is the constraint name or the trigger message the migration
        actually contains, so deleting the rule from the migration fails the claim
        that advertises it.
        """
        assert contract["database_enforcement"][claim] is True
        assert fragment in migration_source, claim

    def test_the_migration_declares_no_foreign_key_into_the_m084_intent(
        self, migration_source: str
    ) -> None:
        # The limitation claim says the link is a trigger. This is that claim,
        # checked against the migration rather than trusted.
        assert "approved_order_intent.intent_governance_id" not in migration_source

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
