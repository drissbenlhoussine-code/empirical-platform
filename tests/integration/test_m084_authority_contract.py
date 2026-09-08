"""MILESTONE-084 -- the authority contract, checked against the running code.

A published authority document is worth exactly as much as the checks that keep
it honest. This file does three things:

  1. proves the schema is CLOSED -- a claim it does not already name cannot be
     added, and a claim removed from the contract fails the exact item counts;
  2. proves `current-authority.md` is the deterministic rendering of
     `current-authority.json`, so the prose cannot drift from the contract;
  3. proves each mechanical claim against the code and schema that implement
     it, so that weakening the implementation fails here rather than leaving a
     document that describes a product that no longer exists.

The third is the one that matters. The first two only keep the document
self-consistent; without the third, a contract could be perfectly rendered,
perfectly validated, and false.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any

import pytest
from tools.render_m083_authority import SchemaError, validate
from tools.render_m084_authority import CONTRACT, DOCUMENT, SCHEMA, render

from empirical_platform.decision_candidate.trade_approval import (
    ALLOWED_TRANSITIONS,
    ApprovedOrderIntent,
    SubmissionState,
)
from empirical_platform.decision_candidate.trade_proposal import ProposalStatus
from empirical_platform.shared.persistence.postgres_repositories.decision_to_approval_repositories import (  # noqa: E501
    PostgresApprovedOrderIntentRepository,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_MIGRATION = (
    _REPO_ROOT
    / "migrations"
    / "versions"
    / "a3f7c21d9b04_create_m084_decision_to_approval_schema.py"
)


@pytest.fixture(scope="module")
def contract() -> dict[str, Any]:
    return json.loads(CONTRACT.read_text(encoding="utf-8"))  # type: ignore[no-any-return]


@pytest.fixture(scope="module")
def schema() -> dict[str, Any]:
    return json.loads(SCHEMA.read_text(encoding="utf-8"))  # type: ignore[no-any-return]


class TestTheContractIsValidAndClosed:
    def test_the_contract_satisfies_its_own_schema(
        self, contract: dict[str, Any], schema: dict[str, Any]
    ) -> None:
        validate(contract, schema)

    def test_the_document_is_the_deterministic_rendering_of_the_contract(
        self, contract: dict[str, Any]
    ) -> None:
        assert DOCUMENT.read_text(encoding="utf-8") == render(contract)

    def test_rendering_twice_produces_the_same_bytes(self, contract: dict[str, Any]) -> None:
        assert render(contract) == render(contract)

    @pytest.mark.parametrize(
        "section", ["proves", "does_not_prove", "structural_limitations", "intended_future_use"]
    )
    def test_a_claim_the_schema_does_not_name_cannot_be_added(
        self, contract: dict[str, Any], schema: dict[str, Any], section: str
    ) -> None:
        widened = {**contract, section: [*contract[section], "a_brand_new_claim"]}
        with pytest.raises(SchemaError):
            validate(widened, schema)

    @pytest.mark.parametrize(
        "section", ["proves", "does_not_prove", "structural_limitations", "intended_future_use"]
    )
    def test_a_claim_cannot_be_quietly_dropped(
        self, contract: dict[str, Any], schema: dict[str, Any], section: str
    ) -> None:
        # Exact minItems/maxItems: removing a limitation is as visible as adding
        # a claim, which is the direction over-claiming actually travels.
        narrowed = {**contract, section: contract[section][:-1]}
        with pytest.raises(SchemaError):
            validate(narrowed, schema)

    def test_an_unknown_top_level_property_is_refused(
        self, contract: dict[str, Any], schema: dict[str, Any]
    ) -> None:
        with pytest.raises(SchemaError):
            validate({**contract, "also_proves": ["anything"]}, schema)

    def test_the_enforcement_table_cannot_flip_a_no_into_a_yes(
        self, contract: dict[str, Any], schema: dict[str, Any]
    ) -> None:
        # The one row that says "no" is the one an over-claiming edit would want
        # to flip, so the schema pins it with `const: false`.
        flipped = {
            **contract,
            "database_enforcement": {
                **contract["database_enforcement"],
                "ddl_authority_trigger_disable_truncate_drop_superuser": True,
            },
        }
        with pytest.raises(SchemaError):
            validate(flipped, schema)

    def test_the_enforcement_table_cannot_flip_a_yes_into_a_no(
        self, contract: dict[str, Any], schema: dict[str, Any]
    ) -> None:
        flipped = {
            **contract,
            "database_enforcement": {
                **contract["database_enforcement"],
                "one_intent_per_proposal": False,
            },
        }
        with pytest.raises(SchemaError):
            validate(flipped, schema)

    def test_the_milestone_and_title_are_pinned(
        self, contract: dict[str, Any], schema: dict[str, Any]
    ) -> None:
        with pytest.raises(SchemaError):
            validate({**contract, "milestone": "M085"}, schema)


class TestTheClaimsMatchTheRunningCode:
    """Each mechanical claim, checked against what actually implements it."""

    def test_only_prepared_has_outgoing_transitions(self, contract: dict[str, Any]) -> None:
        assert (
            "a_closed_proposal_state_machine_in_which_only_prepared_has_outgoing_edges"
            in contract["proves"]
        )
        for status, targets in ALLOWED_TRANSITIONS.items():
            assert bool(targets) is (status is ProposalStatus.PREPARED)

    def test_not_submitted_is_the_only_submission_state_that_exists(
        self, contract: dict[str, Any]
    ) -> None:
        assert (
            "every_stored_intent_is_not_submitted_and_no_transition_away_from_it_exists"
            in contract["proves"]
        )
        assert list(SubmissionState) == [SubmissionState.NOT_SUBMITTED]

    def test_the_intent_repository_offers_no_way_to_submit(self) -> None:
        public = {
            name for name in dir(PostgresApprovedOrderIntentRepository) if not name.startswith("_")
        }
        assert public == {"issue", "get", "for_proposal"}

    def test_the_intent_type_carries_no_broker_or_submission_field(self) -> None:
        forbidden = ("broker", "credential", "token", "endpoint", "secret", "submitted_at")
        for field_name in ApprovedOrderIntent.__slots__:
            assert not any(word in field_name.lower() for word in forbidden), field_name

    @pytest.mark.parametrize(
        "constraint",
        [
            "ck_operator_trading_configuration_unleveraged",
            "ck_operator_trading_configuration_long_only",
            "ck_operator_trading_configuration_intraday_only",
            "ck_operator_trading_configuration_preparation_only",
            "ck_approved_order_intent_never_submitted",
            "uq_approved_order_intent_one_per_proposal",
            "uq_trade_approval_decision_one_per_proposal",
        ],
    )
    def test_each_claimed_database_rule_is_named_in_the_migration(self, constraint: str) -> None:
        # Named rather than merely present: a constraint the migration does not
        # name is a claim with nothing behind it.
        assert constraint in _MIGRATION.read_text(encoding="utf-8")

    def test_the_migration_installs_the_guards_the_contract_claims(
        self, contract: dict[str, Any]
    ) -> None:
        source = _MIGRATION.read_text(encoding="utf-8")
        assert contract["database_enforcement"]["order_terms_immutable_after_insert"] is True
        assert "trade_proposal_guard_update" in source
        assert contract["database_enforcement"]["closed_proposal_state_machine_on_update"] is True
        assert "is not an allowed transition" in source
        assert (
            contract["database_enforcement"][
                "decisions_intents_and_risk_check_evidence_append_only"
            ]
            is True
        )
        assert "m084_append_only" in source

    def test_the_contract_admits_the_limits_it_must(self, contract: dict[str, Any]) -> None:
        # The three most tempting things to leave out.
        assert (
            "row_level_refusals_do_not_cover_truncate_drop_disable_trigger_or_superuser"
            in contract["structural_limitations"]
        )
        assert (
            "market_inputs_are_operator_asserted_and_are_never_verified_against_a_venue"
            in contract["structural_limitations"]
        )
        assert (
            "the_fingerprint_is_a_change_detector_not_a_cryptographic_seal"
            in contract["structural_limitations"]
        )
        assert (
            contract["database_enforcement"][
                "ddl_authority_trigger_disable_truncate_drop_superuser"
            ]
            is False
        )

    def test_the_contract_does_not_claim_readiness_it_does_not_have(
        self, contract: dict[str, Any]
    ) -> None:
        for refusal in (
            "paper_or_live_trading_readiness",
            "profitability_expected_return_or_advice",
            "that_an_approved_intent_was_will_be_or_can_be_sent_to_any_venue",
            "regulatory_tax_or_reporting_compliance",
        ):
            assert refusal in contract["does_not_prove"]

    def test_no_source_module_imports_an_order_submission_dependency(
        self, contract: dict[str, Any]
    ) -> None:
        from tools.check_architecture import ORDER_SUBMISSION_PREFIXES

        assert (
            "no_module_of_the_package_imports_an_order_submission_dependency" in contract["proves"]
        )
        offenders: list[str] = []
        for path in (_REPO_ROOT / "src").rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    names = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom):
                    names = [node.module] if node.module else []
                else:
                    continue
                offenders.extend(
                    f"{path}: {name}"
                    for name in names
                    for prefix in ORDER_SUBMISSION_PREFIXES
                    if name == prefix or name.startswith(f"{prefix}.")
                )
        assert offenders == []


class TestTheFrozenM083PackageIsUntouched:
    def test_the_m083_authority_still_renders_to_its_committed_document(self) -> None:
        # M084 consumes M083's watermark. It must not have edited M083's claims
        # on the way past.
        from tools.render_m083_authority import CONTRACT as M083_CONTRACT
        from tools.render_m083_authority import DOCUMENT as M083_DOCUMENT
        from tools.render_m083_authority import SCHEMA as M083_SCHEMA
        from tools.render_m083_authority import render as render_m083

        m083 = json.loads(M083_CONTRACT.read_text(encoding="utf-8"))
        validate(m083, json.loads(M083_SCHEMA.read_text(encoding="utf-8")))
        assert M083_DOCUMENT.read_text(encoding="utf-8") == render_m083(m083)
